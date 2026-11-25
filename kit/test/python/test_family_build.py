"""A FAMILY OF MODULES THAT SNAP through REAL builds (kit/selftest/blender/build_family.py + kit/tools/family.py): a
hall's straight and end meet with no seam and the family passes; a module whose walls are 0.1 stud thicker almost
meets them - the family fails on that seam, by name; every module carries its snap Attachments."""

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
OUT = os.path.join("build", "_test_family_build")
ENV = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)


def build(which):
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", "build_family.py"), "--", which,
                           "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1800, env=ENV,
                          encoding="utf-8", errors="replace")


def family(name="SelftestHall", only=None):
    extra = ["--only", ",".join(only)] if only else []
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "tools", "family.py"), name, *extra], cwd=ROOT,
                       capture_output=True, text=True, timeout=300, env=ENV, encoding="utf-8", errors="replace")
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = {w: build(w) for w in ("Straight", "End", "Bad", "WallA", "WallB")}
        cls.good = family(only=["_selftest_hall_Straight", "_selftest_hall_End"])   # (--only: the family named)
        cls.bad = family()
        cls.walls = family("SelftestWall")
        with open(os.path.join(ROOT, OUT, "families", "SelftestHall.json"), encoding="utf-8") as fh:
            cls.table = json.load(fh)

    def test_the_modules_built(self):
        for w, r in self.built.items():
            self.assertEqual(r.returncode, 0, (w, (r.stderr or r.stdout)[-1200:]))

    def test_the_straight_and_the_end_meet_and_the_family_passes(self):
        code, v = self.good
        self.assertEqual((code, v["status"]), (0, "pass"), v["summary"])
        s = self.table["sides"]
        straight = s["_selftest_hall_Straight"]
        self.assertEqual(straight["+X"][0][0], straight["-X"][0][0])        # (its two open ends: one shape)
        self.assertEqual(s["_selftest_hall_End"]["-X"][0][0], straight["+X"][0][0])
        self.assertIn("_selftest_hall_End.-X.0.0", self.table["meets"]["_selftest_hall_Straight.+X.0.0"])

    def test_walls_a_little_thicker_are_a_seam_and_the_family_fails_by_name(self):
        code, v = self.bad
        self.assertEqual((code, v["status"]), (1, "fail"), v["summary"])
        self.assertIn("_selftest_hall_Bad", v["summary"])
        self.assertIn("almost meets", v["summary"])
        self.assertNotIn("_selftest_hall_Bad.+X.0.0", self.table["meets"].get("_selftest_hall_Straight.-X.0.0", []))

    def test_walls_of_a_free_depth_a_little_deeper_are_a_seam_too(self):
        code, v = self.walls
        self.assertEqual((code, v["status"]), (1, "fail"), v["summary"])
        self.assertIn("almost meets", v["summary"])

    def test_every_module_carries_its_snap_attachments(self):
        with open(os.path.join(ROOT, OUT, "models", "_selftest_hall_Straight.manifest.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        snaps = {k: v for k, v in m["anchors"].items() if k.startswith("Snap")}
        self.assertEqual(snaps["SnapPX_0_0"], [4.0, 2.0, 2.0])
        self.assertEqual(snaps["SnapNX_0_0"], [0.0, 2.0, 2.0])
        self.assertEqual(len(snaps), 6)
        self.assertEqual(m["module"]["family"], "SelftestHall")


if __name__ == "__main__":
    unittest.main()
