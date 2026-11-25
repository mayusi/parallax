"""Kits and exotic surfaces through REAL builds (kit/selftest/blender/build_kits.py and its twins; the 3D methods
audit, stage K): a surface drawn by a control net, balls that flow into one skin and a part lent by another build
are each a closed part of a passing model whose .glb reads back; a folded net and a lender the owner never
approved stop the build."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_kits_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


def verdict(r):
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)   # (strict: the kit reads this line the same way)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lender = run("build_topology.py")            # the build that lends its drum
        assert lender.returncode == 0, (lender.stderr or lender.stdout)[-600:]
        cls.first = run("build_kits.py")
        cls.good = run("build_kits.py")              # (twice: the second comes from the bake cache)
        cls.v = verdict(cls.good)
        cls.said = json.loads(next(x for x in cls.good.stdout.splitlines() if x.startswith("KITS "))[5:])
        cls.fold = run("build_kits_fold.py")
        cls.unloved = run("build_kits_unloved.py")

    def test_the_three_made_parts_are_in_a_passing_model_both_times(self):
        self.assertEqual(verdict(self.first)["status"], "pass", verdict(self.first)["summary"][:300])
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        self.assertIn("kit: 1 drawn by a net, 1 blob(s), 1 lent by another build, a .glb a group", self.v["summary"])
        self.assertEqual(self.said["tris"], 1802)   # (the same mesh every time: net, skin and lent part)

    def test_the_glb_is_there_and_read_back_as_the_group(self):
        self.assertTrue(self.said["glb"].endswith("_selftest_kits_good.glb"))
        self.assertTrue(self.said["glb_there"])
        c = next(x for x in self.v["groups"]["main"]["checks"] if x["name"] == "gltf")
        self.assertTrue(c["ok"], c)
        with open(os.path.join(ROOT, self.said["glb"]), "rb") as f:
            self.assertEqual(f.read(4), b"glTF")

    def test_a_net_folded_over_itself_stops_the_build(self):
        self.assertNotEqual(self.fold.returncode, 0)
        self.assertIn("its net folds the surface over itself", self.fold.stderr + self.fold.stdout)

    def test_a_build_the_owner_never_approved_lends_nothing(self):
        self.assertNotEqual(self.unloved.returncode, 0)
        self.assertIn("may not lend its geometry - only a build the owner approved does",
                      self.unloved.stderr + self.unloved.stdout)


if __name__ == "__main__":
    unittest.main()
