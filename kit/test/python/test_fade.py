"""See-through by degrees (kit/blender/rbx_cutout.py: grade_by_rule, grade_by_picture, alpha_graded; the owner's
method lists: transparency; the 3D methods audit, stage X)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_cutout as C  # noqa: E402

PTS = [(0, 0, 0), (0, 1, 0), (0, 2, 0), (0, 4, 0)]


class Fade(unittest.TestCase):
    def test_a_rule_says_how_solid_and_is_held_between_nothing_and_all(self):
        self.assertEqual(C.grade_by_rule(PTS, lambda p: p[1] / 2).tolist(), [0.0, 0.5, 1.0, 1.0])
        self.assertEqual(C.grade_by_rule(PTS, lambda p: p[1] > 0.5).tolist(), [0.0, 1.0, 1.0, 1.0])

    def test_a_picture_gives_its_own_value_and_nothing_outside_it(self):
        pic = np.tile(np.linspace(0, 1, 5)[::-1][:, None], (1, 4))          # solid at its top, clear at its foot
        frame = (np.array([0.0, 0, 0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 2.0, 4.0)
        got = C.grade_by_picture([(1, 0.2, 0), (1, 3.9, 0), (1, 2.0, 0), (5, 2, 0)], pic, frame)
        self.assertAlmostEqual(float(got[0]), 0.0)
        self.assertAlmostEqual(float(got[1]), 1.0)
        self.assertAlmostEqual(float(got[2]), 0.5)
        self.assertEqual(float(got[3]), 0.0)

    def test_the_map_carries_each_degree(self):
        m = C.alpha_graded(4, [0, 0, 1], [0, 1, 2], [0.0, 0.5, 1.0])
        self.assertEqual((int(m[0, 0]), int(m[0, 1]), int(m[1, 2]), int(m[3, 3])), (0, 128, 255, 255))
        self.assertAlmostEqual(C.clear([0.0, 0.5, 1.0]), 0.5)
        self.assertEqual(C.grades(np.linspace(0, 1, 100)), 100)
        self.assertEqual(C.grades([0.0, 1.0, 1.0]), 2)

    def test_what_a_fade_amounts_to(self):
        # (the review: an even half transparency was called "all-or-nothing")
        self.assertEqual(C.fade_kind(np.linspace(0, 1, 50)), "fade")
        self.assertEqual(C.fade_kind([0.0, 1.0, 1.0]), "cut")
        self.assertEqual(C.fade_kind([0.5, 0.5]), "even")
        self.assertEqual(C.fade_kind([0.3, 0.7]), "steps")

    def test_a_rule_that_answers_no_number_is_clear(self):
        self.assertEqual(C.grade_by_rule([(0, 0, 0)], lambda p: float("nan")).tolist(), [0.0])


if __name__ == "__main__":
    unittest.main()
