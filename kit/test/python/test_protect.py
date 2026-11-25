"""A protected place, in numbers (kit/blender/rbx_optimize.near / protect_bar / protect_problem; his D-R08)."""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
for _m in ("bpy", "mathutils", "mathutils.bvhtree"):   # (rbx_optimize imports Blender at the top: stubs for the pure part)
    sys.modules.setdefault(_m, types.ModuleType(_m))
sys.modules["mathutils.bvhtree"].BVHTree = object
import rbx_optimize as O  # noqa: E402


class Protect(unittest.TestCase):
    def test_which_points_lie_in_a_place(self):
        places = [((0, 0, 0), 1.0), ((5, 0, 0), 0.5)]
        self.assertEqual(O.near([(0.5, 0, 0), (2, 0, 0), (5.2, 0, 0)], places), [True, False, True])
        self.assertEqual(O.near([(0, 0, 0)], []), [False])

    def test_what_a_place_holds(self):
        self.assertAlmostEqual(O.protect_bar(0.4), 0.04)
        self.assertAlmostEqual(O.protect_bar(0.01), 0.005)          # never finer than the floor
        self.assertAlmostEqual(O.protect_bar(0.4, within=0.002), 0.002)

    def test_a_place_lost_and_a_place_off_the_model_are_said(self):
        self.assertIsNone(O.protect_problem("Notch", {"p99": 0.01, "points": 90}, 0.4))
        self.assertIn("0.08 studs off", O.protect_problem("Notch", {"p99": 0.08, "points": 90}, 0.4))
        self.assertIn("nothing there to protect", O.protect_problem("Notch", {"p99": None, "points": 0}, 0.4))


if __name__ == "__main__":
    unittest.main()
