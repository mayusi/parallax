"""An opening that must stay open (kit/blender/rbx_through.py; the owner's limitations page D-R12): the bundle of
rays the build looks down, and the words when something stops them."""

import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_through as T  # noqa: E402


class Rays(unittest.TestCase):
    def test_the_middle_line_and_a_ring_inside_the_width(self):
        rays = T.rays((0, 0, -1), (0, 0, 3), 1.0)
        self.assertEqual(len(rays), 15)                                          # the middle, 8 near the rim, 6 inside
        origin, direction, length = rays[0]
        self.assertEqual((origin, direction, length), ((0, 0, -1), (0.0, 0.0, 1.0), 4.0))
        for origin, direction, length in rays[1:]:
            self.assertAlmostEqual(origin[2], -1.0)                              # in the plane across the way
            self.assertEqual((direction, length), ((0.0, 0.0, 1.0), 4.0))
        for origin, _d, _l in rays[1:9]:
            self.assertAlmostEqual(math.hypot(origin[0], origin[1]), 0.4)        # 0.8 of the half width
        for origin, _d, _l in rays[9:]:
            self.assertAlmostEqual(math.hypot(origin[0], origin[1]), 0.2)        # 0.4 of it
        angles = sorted(round(math.degrees(math.atan2(o[1], o[0])) % 360) for o, _d, _l in rays[1:9])
        self.assertEqual([b - a for a, b in zip(angles, angles[1:])], [45] * 7)  # spread evenly round it

    def test_a_bar_across_the_opening_off_its_middle_stops_a_line(self):
        # the review's find: a bar 0.3 tall across a 1.6-wide opening, 0.32 off its middle, passed between 7 lines
        rays = T.rays((0, 0, -1), (0, 0, 1), 1.6)
        axis = 0 if any(abs(o[1]) > 1e-9 for o, _d, _l in rays[1:]) else 1
        up = 1 if axis == 0 else 0
        self.assertTrue(any(0.17 <= o[up] <= 0.47 for o, _d, _l in rays))
        self.assertTrue(any(-0.47 <= o[up] <= -0.17 for o, _d, _l in rays))

    def test_a_way_straight_up_has_its_ring_too(self):
        rays = T.rays((1, 0, 1), (1, 5, 1), 0.5)
        for origin, _d, _l in rays[1:9]:
            self.assertAlmostEqual(origin[1], 0.0)
            self.assertAlmostEqual(math.hypot(origin[0] - 1, origin[2] - 1), 0.2)

    def test_no_width_is_one_line_and_no_length_is_refused(self):
        self.assertEqual(len(T.rays((0, 0, 0), (1, 0, 0), 0.0)), 1)
        with self.assertRaises(ValueError):
            T.rays((1, 1, 1), (1, 1, 1), 0.5)


class Verdict(unittest.TestCase):
    def test_open_says_nothing_and_one_stopped_line_is_a_closed_opening(self):
        self.assertIsNone(T.verdict("Bore", 0, 15))
        said = T.verdict("Bore", 1, 15, (0.0, 0.5, 1.25), "Plug")
        self.assertEqual(said, "Bore: 1 of its 15 lines of sight are stopped by Plug at (0, 0.5, 1.25)")
        self.assertEqual(T.verdict("Bore", 15, 15), "Bore: 15 of its 15 lines of sight are stopped")


if __name__ == "__main__":
    unittest.main()
