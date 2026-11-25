"""kit/vfx/starters.py: the record of the kit's starter texts (kit/vfx/starters.json) holds every starter piece as it is
now (the shipped record is complete), finds a starter it lacks, keeps every text a starter shipped with, and is
written only in the kit's home (kit/.source): in a project `--write` refuses, so a project cannot re-record a bent
kit/starter/ copy as a starter."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "..", "vfx", "starters.py"))
sys.path.insert(0, os.path.dirname(SCRIPT))

import starters  # noqa: E402


def run(*args):
    p = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, timeout=120)
    return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])


class Record(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.kit = os.path.join(self.tmp, "kit")
        for rel, text in (("starter/vfx/spark.json", '{"version": 3}\n'), ("starter/vfx/meshes/ring.json", "{}\n"),
                          ("starter/textures/glow.json", '{"recipe": "glow"}\n'),
                          ("starter/vfx/_deps/ex/textures/t.json", '{"source": "__DEPS__/textures/t.png"}\n')):
            path = os.path.join(self.kit, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        os.makedirs(os.path.join(self.kit, "vfx"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_shipped_record_holds_every_starter_piece(self):
        # (in the kit's home only, where the record is written: a project's kit/starter may hold a piece promoted
        # there until `sync` brings the home's record)
        if not os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(SCRIPT)), ".source")):
            self.skipTest("a project: the starter record is the kit home's (kit/.source)")
        code, out = run("--check")
        self.assertEqual(code, 0, out)
        self.assertGreater(len(starters.pieces()), 0)

    def test_write_refuses_outside_the_kits_home(self):
        code, out = run("--write", "--kit", self.kit)
        self.assertEqual(code, 1)
        self.assertIn("home only", out["summary"])
        self.assertFalse(os.path.isfile(os.path.join(self.kit, "vfx", "starters.json")))

    def test_check_names_a_starter_the_record_lacks_and_write_keeps_every_text(self):
        open(os.path.join(self.kit, ".source"), "w").close()
        code, out = run("--check", "--kit", self.kit)
        self.assertEqual(code, 1)
        self.assertIn("4 starter piece(s) not in the record", out["summary"])
        code, out = run("--write", "--kit", self.kit)
        self.assertEqual(code, 0, out)
        code, out = run("--check", "--kit", self.kit)
        self.assertEqual(code, 0, out)
        with open(os.path.join(self.kit, "starter", "vfx", "spark.json"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write('{"version": 3, "duration": 2}\n')
        self.assertEqual(run("--check", "--kit", self.kit)[0], 1)
        run("--write", "--kit", self.kit)
        with open(os.path.join(self.kit, "vfx", "starters.json"), encoding="utf-8") as fh:
            record = json.load(fh)["pieces"]
        self.assertEqual(sorted(record), ["effect/spark", "mesh/ring", "texture/glow", "texture/t"])
        self.assertEqual(len(record["effect/spark"]), 2)  # (both texts it shipped with)


if __name__ == "__main__":
    unittest.main()
