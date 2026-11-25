"""rbx_garment — a sleeve draped by Blender's cloth simulation on an R6 arm (fixture
kit/selftest/blender/build_garment.py, run in Blender): its end lands at the forearm, nothing flies off (the hook once
turned the end ring by the part's quarter-turn frame; an even-offset wall once flung a bunched sleeve 88 studs), the slack
bunches into folds, the lining sits inside, and the wall is closed."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Garment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = os.path.join(REPO, "build", "models", "_selftest_garment.check.json")
        if os.path.isfile(out):
            os.remove(out)
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_garment.py")
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script], cwd=REPO, capture_output=True, text=True,
                       timeout=900)
        with open(out, encoding="utf-8") as fh:
            cls.check = json.load(fh)

    def test_the_end_is_pulled_up_to_the_forearm(self):
        lo, hi = self.check["y"]
        self.assertAlmostEqual(hi, 2.05, delta=0.05)
        self.assertGreater(lo, 0.6 - 0.2)            # (folds hang a little below the pulled ring)
        self.assertLess(lo, 0.6 + 0.1)

    def test_nothing_flies_off(self):
        self.assertLess(self.check["radius_max"], 1.0)   # (an R6 arm's corner is 0.71 out; the sleeve hugs it)

    def test_the_slack_bunches_into_folds(self):
        self.assertGreater(self.check["radius_spread"], 0.12)

    def test_the_lining_is_inside(self):
        self.assertLess(self.check["lining_radius_max"], self.check["radius_max"])
        self.assertIn("SleeveLining", self.check["parts"])

    def test_the_sleeve_covers_the_arm_on_every_side(self):
        cov = self.check["coverage"]   # (the sleeve ends at y 0.6: the arm's last 0.6 studs are bare by design)
        for face in ("front", "back", "left", "right"):
            self.assertGreater(cov[face], 0.65, face)
            self.assertLess(cov[face], 0.85, face)

    def test_the_wall_is_closed(self):
        self.assertEqual(self.check["non_manifold"], 0)


if __name__ == "__main__":
    unittest.main()
