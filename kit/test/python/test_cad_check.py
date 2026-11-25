"""kit cad check runs a build script WITHOUT Blender: a stand-in rbx must record every a.cad(...) call (inside mirror /
internal / floaters blocks too) with its params, and a script's own error must come out as a plain failure."""

import json
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import cad_check  # noqa: E402

SCRIPT = '''import os
import rbx
a = rbx.Asset("thing", size=(1, 1, 1), private=True)
a.material("steel", **rbx.finish("blued_steel"), wear=0.1)
a.cad("Body", os.path.join("cad", "body.py"), "steel", params={"w": 2.0})
with a.internal():
    a.cad("Pin", "inline code", "steel", tol=0.02, angle=8.0)
with a.mirror("X"):
    a.box("Side", (1, 1, 1), (0, 0, 0), "steel")
a.build()
'''


class TestRowOk(unittest.TestCase):
    def test_an_untrue_solid_is_no_green_part(self):
        good = {"status": "pass", "solids": 1, "open_edges": 0}
        self.assertTrue(cad_check.row_ok(good))
        self.assertFalse(cad_check.row_ok({**good, "volume_untrue": "its mesh is 9.5% off the solid's own volume"}))
        self.assertFalse(cad_check.row_ok({**good, "open_edges": 3}))
        self.assertFalse(cad_check.row_ok({"status": "fail"}))

    def test_a_solid_opencascade_calls_invalid_is_no_green_part(self):
        # revolver build 5's frame, as cad_run said it in the build (2026-11-11): pass, 1 solid, 0 open edges - and
        # valid false, which the build's cad_solid gate failed
        frame = {"status": "pass", "solids": 1, "open_edges": 0, "valid": False,
                 "fillets_reduced": [["fillet_auto", 0.8, "148 edge(s) left sharp: no radius took"]]}
        self.assertFalse(cad_check.row_ok(frame))
        self.assertTrue(cad_check.row_ok({**frame, "valid": True}))


class TestRecord(unittest.TestCase):
    def _script(self, text):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "build_thing.py")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def test_records_every_cad_call(self):
        before = sys.modules.get("rbx")
        calls = cad_check.record(self._script(SCRIPT))
        self.assertEqual([c[0] for c in calls], ["Body", "Pin"])
        self.assertEqual(calls[0][2], {"w": 2.0})
        self.assertEqual((calls[1][3], calls[1][4]), (0.02, 8.0))
        self.assertIs(sys.modules.get("rbx"), before)  # (the stand-in is taken back out)

    def test_script_error_is_a_plain_failure(self):
        bad = self._script("import rbx\na = rbx.Asset('x')\nraise RuntimeError('boom')\n")
        with self.assertRaises(RuntimeError):
            cad_check.record(bad)

    def test_unknown_asset_fails_with_a_verdict(self):
        out = []
        old = sys.stdout
        try:
            import io
            sys.stdout = io.StringIO()
            code = cad_check.main(["no_such_asset_here"])
            out = sys.stdout.getvalue().strip().splitlines()
        finally:
            sys.stdout = old
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out[-1])["status"], "fail")


class TestGame(unittest.TestCase):
    def test_a_games_piece_is_found_and_its_maker_read(self):
        # --game <Name> / KIT_GAME route the build script (a SampleRegion piece once came back "no build script"), and
        # the stand-in's a.maker returns the maker's language as data (a script reading lang["radius_mm"] runs)
        if not os.path.isdir(os.path.join(cad_check.REPO, "games")):
            self.skipTest("no games/ in this project")
        games = [g for g in os.listdir(os.path.join(cad_check.REPO, "games"))
                 if os.path.isdir(os.path.join(cad_check.REPO, "games", g)) and not g.startswith((".", "_"))]
        if not games:
            self.skipTest("no games/ in this project")
        self.assertTrue(games)
        self.assertEqual(cad_check.game_root(["x", "--game", games[0]]), os.path.join("games", games[0]))
        self.assertEqual(cad_check.game_root(["x", "--game", "none"]), "")
        mk = os.path.join(tempfile.mkdtemp(), "makers")
        os.makedirs(mk)
        with open(os.path.join(mk, "Nobody.md"), "w", encoding="utf-8") as fh:
            fh.write("# Nobody\n")
        text = ("import rbx\na = rbx.Asset('thing')\nlang = a.maker('Nobody', folder=%r)\n"
                "a.cad('Body', 'x', 'steel', params={'keys': sorted(lang)})\n" % mk)
        calls = cad_check.record(TestRecord._script(None, text))
        self.assertEqual(calls[0][0], "Body")
        self.assertIsInstance(calls[0][2]["keys"], list)


class _Ran:
    """a stand-in subprocess.run: keeps each command line and timeout, answers with one passing cad_run verdict"""

    def __init__(self):
        self.calls = []

    def __call__(self, args, **kw):
        self.calls.append((list(args), kw.get("timeout")))
        return types.SimpleNamespace(stdout='{"status": "pass", "solids": 1, "open_edges": 0}', stderr="",
                                     returncode=0)


class TestFillet(unittest.TestCase):
    # revolver build 5 (2026-11-11): this check passed the frame, then the build's 0.8 mm fillet broke it - the stand-in
    # had dropped a.cad's fillet_mm and run_one never asked cad_run for it
    FILLETED = ("import rbx\na = rbx.Asset('thing')\n"
                "a.cad('Frame', 'x = 1', 'steel', fillet_mm=0.8)\n"
                "a.cad('Grip', 'x = 1', 'steel')\n"
                "a.cad('Bolt', 'x = 1', 'steel', None, None, 'main', {'d': 1}, 0.05, 12.0, None, None, 0.5)\n")

    def test_records_each_parts_fillet_mm(self):
        calls = cad_check.record(TestRecord._script(None, self.FILLETED))
        self.assertEqual([(c[0], c[5]) for c in calls], [("Frame", 0.8), ("Grip", None), ("Bolt", 0.5)])
        self.assertEqual(calls[2][2], {"d": 1})   # (positional arguments land where rbx.Asset.cad puts them)

    def _run(self, call, **kw):
        ran = _Ran()
        old = cad_check.subprocess.run
        cad_check.subprocess.run = ran
        try:
            said = cad_check.run_one("py", call, tempfile.mkdtemp(), **kw)[2]
        finally:
            cad_check.subprocess.run = old
        return ran.calls[0], said

    def test_a_filleted_part_is_filleted_as_the_build_does(self):
        (args, timeout), said = self._run(("Frame", "x = 1\n", {}, 0.05, 12.0, 0.8))
        self.assertEqual(args[args.index("--fillet") + 1], "0.8")
        self.assertEqual(timeout, 3600)   # (a.cad's own limit for a fillet search)
        self.assertEqual(said.get("fillet_mm"), 0.8)

    def test_no_fillet_and_unfilleted_parts_skip_it(self):
        for call, kw in ((("Frame", "x = 1\n", {}, 0.05, 12.0, 0.8), {"fillet": False}),
                         (("Grip", "x = 1\n", {}, 0.05, 12.0, None), {})):
            (args, timeout), said = self._run(call, **kw)
            self.assertNotIn("--fillet", args)
            self.assertEqual(timeout, 900)
            self.assertNotIn("fillet_mm", said)


class TestLook(unittest.TestCase):
    def test_failed_or_missing_parts_are_not_drawn(self):
        # a part that failed its check, or has no mesh, is never sent to Blender (no sheet, no crash)
        rows = [{"part": "Broken", "ok": False}, {"part": "NoMesh", "ok": True}]
        calls = []
        old_run = cad_check.subprocess.run
        cad_check.subprocess.run = lambda *a, **k: calls.append(a) or None
        try:
            self.assertEqual(cad_check.look("thing", rows, tempfile.mkdtemp(), None), {})
        finally:
            cad_check.subprocess.run = old_run
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
