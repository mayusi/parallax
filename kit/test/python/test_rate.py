"""kit rate (kit/grading/round.py + kit/grading/page/server.py): the OWNER grading page — the page server keeps a 0-10
score and the owner's words per model of the round (and refuses anything else: another asset, a score off the scale,
another origin, a path out of the round); import records each NEW score once through kit verdict asset, never a score
without words. On a temporary project."""

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "grading"))
sys.path.insert(0, os.path.join(ROOT, "kit", "grading", "page"))
import round as RD  # noqa: E402
import server as SV  # noqa: E402


class Page(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rdir = os.path.join(self.tmp.name, "build", "grading", "r1")
        os.makedirs(os.path.join(self.rdir, "models"))
        with open(os.path.join(self.rdir, "round.json"), "w") as fh:
            json.dump({"round": "r1", "items": [{"asset": "barrel", "glb": "models/barrel.glb", "refs": []}]}, fh)
        with open(os.path.join(self.rdir, "models", "barrel.glb"), "wb") as fh:
            fh.write(b"glTF")
        self._repo, SV.REPO = SV.REPO, self.tmp.name
        H, _root = SV.make_handler("r1")
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        SV.REPO = self._repo
        self.tmp.cleanup()

    def post(self, body, origin=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/rate", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    def test_a_score_and_words_are_kept_in_halves(self):
        code, j = self.post({"asset": "barrel", "score": 7.3, "words": "the hoops read, the wood is too clean"})
        self.assertEqual(code, 200, j)
        self.assertEqual(j["saved"]["score"], 7.5)
        saved = json.load(open(os.path.join(self.rdir, "ratings.json")))
        self.assertEqual(saved["barrel"]["words"], "the hoops read, the wood is too clean")
        self.assertEqual(json.loads(self.get("/api/ratings")[1])["barrel"]["score"], 7.5)

    def test_anything_else_is_refused(self):
        self.assertEqual(self.post({"asset": "crate", "score": 5})[0], 400)          # (not in the round)
        self.assertEqual(self.post({"asset": "barrel", "score": 11})[0], 400)        # (off the 0-10 scale)
        self.assertEqual(self.post({"asset": "barrel", "score": 5}, origin="http://evil.example")[0], 403)
        self.assertFalse(os.path.isfile(os.path.join(self.rdir, "ratings.json")))

    def test_another_host_name_is_refused_dns_rebinding(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/ratings", headers={"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 403)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/rate", data=b'{"asset": "barrel", "score": 5}',
                                     headers={"Host": f"evil.example:{self.port}", "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 403)

    def test_the_round_serves_its_own_files_only(self):
        self.assertEqual(self.get("/round/models/barrel.glb")[0], 200)
        self.assertEqual(self.get("/round/..%2F..%2F..%2Fround.json")[0], 404)
        self.assertEqual(self.get("/round/%2E%2E/%2E%2E/r1/round.json")[0], 404)


class Import(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._rounds, RD.ROUNDS = RD.ROUNDS, os.path.join(self.tmp.name, "grading")
        self.rdir = os.path.join(RD.ROUNDS, "r1")
        os.makedirs(self.rdir)
        with open(os.path.join(self.rdir, "round.json"), "w") as fh:
            json.dump({"round": "r1", "items": [{"asset": "barrel", "build_id": "b9"}, {"asset": "lamp"}]}, fh)

    def tearDown(self):
        RD.ROUNDS = self._rounds
        self.tmp.cleanup()

    def rate(self, data):
        with open(os.path.join(self.rdir, "ratings.json"), "w") as fh:
            json.dump(data, fh)

    def run_import(self):
        calls = []

        def fake(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout="ok", stderr="")

        out = io.StringIO()
        with mock.patch.object(RD.subprocess, "run", side_effect=fake), contextlib.redirect_stdout(out):
            RD.import_round("r1")
        return calls, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_each_new_score_goes_through_kit_verdict_once(self):
        self.rate({"barrel": {"score": 8, "words": "looks real", "at": "t1"}})
        calls, v = self.run_import()
        self.assertEqual(len(calls), 1)
        cmd = calls[0]
        self.assertEqual(cmd[2:8], ["kit", "verdict", "asset", "barrel", "8", "looks real"])
        self.assertIn("--build", cmd)
        self.assertEqual(cmd[cmd.index("--build") + 1], "b9")
        self.assertIn("--quoted-from", cmd)
        calls, v = self.run_import()   # (already in the record)
        self.assertEqual(calls, [])
        self.assertIn("nothing new", v["summary"])

    def test_a_score_without_words_is_not_recorded(self):
        self.rate({"lamp": {"score": 3, "words": "", "at": "t1"}})
        calls, v = self.run_import()
        self.assertEqual(calls, [])
        self.assertIn("a score without words", v["summary"])


if __name__ == "__main__":
    unittest.main()
