"""A part broken beforehand (kit/blender/rbx_fracture.py; the owner's method lists: destructible preparation; the 3D
methods audit, stage O)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_fracture as F  # noqa: E402

CUBE = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], float)
TRIS = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7),
        (2, 7, 6), (3, 0, 4), (3, 4, 7)]


class Seeds(unittest.TestCase):
    def test_the_points_lie_in_the_box_apart_and_the_same_for_the_same_seed(self):
        a = F.seeds((0, 0, 0), (4, 2, 1), 8, seed=3)
        self.assertEqual(a.shape, (8, 3))
        self.assertTrue((a >= 0).all() and (a <= (4, 2, 1)).all())
        self.assertTrue(np.array_equal(a, F.seeds((0, 0, 0), (4, 2, 1), 8, seed=3)))
        self.assertFalse(np.array_equal(a, F.seeds((0, 0, 0), (4, 2, 1), 8, seed=4)))
        near = min(float(np.linalg.norm(a[i] - a[j])) for i in range(8) for j in range(i))
        self.assertGreater(near, 0.3)


class Cells(unittest.TestCase):
    def test_a_pieces_planes_lie_halfway_and_look_away_from_it(self):
        got = F.planes([(0, 0, 0), (2, 0, 0), (0, 4, 0)], 0)
        self.assertEqual(len(got), 2)
        self.assertTrue(np.allclose(got[0][0], (1, 0, 0)) and np.allclose(got[0][1], (1, 0, 0)))
        self.assertTrue(np.allclose(got[1][0], (0, 2, 0)) and np.allclose(got[1][1], (0, 1, 0)))
        self.assertEqual(F.planes([(0, 0, 0), (0, 0, 0)], 0), [])      # two points in one spot bound nothing

    def test_a_closed_meshs_volume(self):
        self.assertAlmostEqual(F.volume(CUBE, TRIS), 1.0)
        self.assertAlmostEqual(F.volume(CUBE * 2, TRIS), 8.0)


class Held(unittest.TestCase):
    def test_pieces_that_add_up_to_the_whole_pass(self):
        self.assertIsNone(F.problem("Crate", 8.0, [3.0, 2.5, 2.49]))

    def test_a_missing_or_an_empty_piece_is_said(self):
        self.assertIn("hold 75% of the part", F.problem("Crate", 8.0, [3.0, 3.0]))
        self.assertIn("1 of its 3 pieces came out empty", F.problem("Crate", 8.0, [4.0, 4.0, 0.0]))


class Burst(unittest.TestCase):
    def test_a_piece_is_pushed_away_from_the_centre_and_one_at_the_centre_goes_up(self):
        self.assertEqual(F.burst((0, 0, 0), (2, 0, 0), 10), (10.0, 0.0, 0.0))
        self.assertEqual(F.burst((1, 1, 1), (1, 1, 1), 10), (0.0, 10.0, 0.0))
        v = F.burst((0, 0, 0), (1, 1, 0), 10)
        self.assertAlmostEqual(v[0], 7.071, places=3)
        self.assertAlmostEqual(v[1], 7.071, places=3)


if __name__ == "__main__":
    unittest.main()
