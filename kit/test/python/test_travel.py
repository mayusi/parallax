"""Where along its travel a moving part is checked (kit/blender/rbx_travel.py; the owner's limitations page D-R05):
the stops set from how far the part moves and how deep it is, never five whatever the travel."""

import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_travel as T  # noqa: E402


class Path(unittest.TestCase):
    def test_a_slide_goes_as_far_as_its_travel(self):
        corners = [(0, 0, 0), (1, 0, 0)]
        got = T.path_length(lambda v: [(x + v, y, z) for x, y, z in corners], 0.0, 4.0)
        self.assertAlmostEqual(got, 4.0)

    def test_a_hinge_goes_as_far_as_its_furthest_corner_swings(self):
        def at(deg):   # a lid 2 long hinged at the origin, about z
            r = math.radians(deg)
            return [(0.5 * math.cos(r), 0.5 * math.sin(r), 0), (2 * math.cos(r), 2 * math.sin(r), 0)]
        self.assertAlmostEqual(T.path_length(at, 0.0, 90.0), math.pi, delta=0.01)   # a quarter turn at radius 2

    def test_nothing_moving_goes_nowhere(self):
        self.assertEqual(T.path_length(lambda v: [], 0.0, 1.0), 0.0)


class Step(unittest.TestCase):
    def test_half_the_parts_depth_within_the_models_bounds(self):
        self.assertAlmostEqual(T.step_for(0.3, 100.0), 0.2)       # floored: 0.2% of a 100-stud model
        self.assertAlmostEqual(T.step_for(0.3, 10.0), 0.15)       # half its depth
        self.assertAlmostEqual(T.step_for(5.0, 10.0), 0.2)        # capped: 2% of the model


class Stops(unittest.TestCase):
    def test_a_short_travel_keeps_the_five_stops(self):
        values, gap, coarse = T.stops(0.0, 1.0, 0.4, 0.15)
        self.assertEqual(values, [0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertFalse(coarse)
        self.assertAlmostEqual(gap, 0.1)

    def test_a_long_travel_gets_stops_no_further_apart_than_the_step(self):
        values, gap, coarse = T.stops(0.0, 4.0, 4.0, 0.15)
        self.assertEqual(len(values), 29)                          # 27 pieces, rounded up to 28
        self.assertLessEqual(gap, 0.15)
        self.assertFalse(coarse)
        for q in (0.0, 1.0, 2.0, 3.0, 4.0):                        # the quarter stops are still among them
            self.assertIn(q, values)
        self.assertTrue(all(b - a <= 0.15 for a, b in zip(values, values[1:])))

    def test_a_travel_too_long_for_the_most_stops_says_it_is_coarse(self):
        values, gap, coarse = T.stops(0.0, 100.0, 100.0, 0.1)
        self.assertEqual(len(values), 49)
        self.assertTrue(coarse)
        self.assertAlmostEqual(gap, 100.0 / 48)

    def test_a_joint_that_runs_backwards_and_one_that_does_not_move(self):
        values, _gap, _c = T.stops(90.0, 0.0, 3.0, 0.5)
        self.assertEqual((values[0], values[-1], len(values)), (0.0, 90.0, 9))
        self.assertEqual(T.stops(0.5, 0.5, 0.0, 0.1), ([0.5], 0.0, False))

    def test_which_stops_are_the_quarter_stops(self):
        self.assertTrue(T.is_quarter(1.0, 0.0, 4.0) and T.is_quarter(4.0, 0.0, 4.0))
        self.assertFalse(T.is_quarter(1.5, 0.0, 4.0))
        self.assertTrue(T.is_quarter(67.5, 90.0, 0.0))

    def test_every_travel_has_its_five_quarter_stops_however_odd_its_length(self):
        for lo, hi in ((0.0, 0.35 / 3), (0.0, 0.1234567), (10.0, 10.3333), (0.0, 2 / 7), (-0.3, 0.12)):
            values, _gap, _c = T.stops(lo, hi, abs(hi - lo), 0.01)
            self.assertEqual(sum(T.is_quarter(v, lo, hi) for v in values), 5, (lo, hi))
            self.assertTrue(T.is_quarter(values[0], lo, hi) and T.is_quarter(values[-1], lo, hi))


if __name__ == "__main__":
    unittest.main()
