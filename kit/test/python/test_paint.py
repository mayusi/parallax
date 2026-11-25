"""Vertex paint (kit/blender/rbx_paint.py; the owner's method lists: vertex colours, vertex-painted blending; the 3D
methods audit, S4)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_paint as P  # noqa: E402

PTS = [(0, 0, 0), (0, 1, 0), (0, 2, 0)]


class Tint(unittest.TestCase):
    def test_a_colour_a_grey_or_a_rule_giving_either(self):
        self.assertEqual(P.tint(PTS, (0.5, 0.6, 0.7)).tolist(), [[0.5, 0.6, 0.7]] * 3)
        self.assertEqual(P.tint(PTS, 0.25).tolist(), [[0.25] * 3] * 3)
        self.assertEqual(P.tint(PTS, lambda p: p[1] / 2).tolist(), [[0.0] * 3, [0.5] * 3, [1.0] * 3])
        self.assertEqual(P.tint(PTS, lambda p: (1, p[1] / 2, 0)).tolist(), [[1, 0, 0], [1, 0.5, 0], [1, 1, 0]])

    def test_a_paint_is_held_between_nothing_and_the_surface_as_it_is(self):
        self.assertEqual(P.tint(PTS, lambda p: p[1] * 3 - 1).tolist(), [[0.0] * 3, [1.0] * 3, [1.0] * 3])

    def test_two_paints_multiply(self):
        self.assertTrue(np.allclose(P.over(P.tint(PTS, 0.5), P.tint(PTS, (1, 0.5, 0))), [[0.5, 0.25, 0]] * 3))


class Said(unittest.TestCase):
    def test_its_mean_and_its_reach(self):
        got = P.said(P.tint(PTS, lambda p: p[1] / 2))
        self.assertEqual(got, {"mean": [0.5, 0.5, 0.5], "darkest": 0.0, "lightest": 1.0})
        self.assertEqual(P.said([])["mean"], [1.0, 1.0, 1.0])

    def test_the_file_is_held_to_the_paint(self):
        self.assertIsNone(P.read_problem([0.5, 0.5, 0.5], [0.52, 0.5, 0.49]))
        self.assertIn("holds no vertex colours", P.read_problem([0.5, 0.5, 0.5], None))
        self.assertIn("are not the paint the build wrote", P.read_problem([0.5, 0.5, 0.5], [1.0, 1.0, 1.0]))


class Corners(unittest.TestCase):
    def test_a_file_that_holds_the_paint_at_every_corner_passes_and_a_few_strays_do_too(self):
        self.assertIsNone(P.corner_problem([0.0, 0.01, 0.03, 0.002]))
        self.assertIsNone(P.corner_problem([0.0] * 99 + [0.5]))        # one corner in a hundred
        self.assertIsNone(P.corner_problem([]))

    def test_colours_on_the_wrong_corners_or_all_white_fail(self):
        # (the review: the paint shuffled onto other corners kept its mean and passed)
        said = P.corner_problem([0.0] * 50 + [0.4] * 50)
        self.assertIn("50% of the corners looked up are off", said)
        self.assertIn("the worst 0.40", said)


if __name__ == "__main__":
    unittest.main()
