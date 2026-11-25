"""rbx_scatter: a raised-relief lattice covers its rectangle at its pitch (turned with the rake), and each frustum
stands square to its surface: foot below, top above, sides along the lattice."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_scatter as S  # noqa: E402


class Lattice(unittest.TestCase):
    def test_covers_the_rectangle_at_its_pitch(self):
        pts, a, b = S.lattice((0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0, 5.0, 3.0)
        self.assertEqual(len(pts), 11 * 7)   # (unturned: -5..5 x -3..3)
        self.assertTrue(np.all(np.abs(pts[:, 0]) <= 5.0) and np.all(np.abs(pts[:, 1]) <= 3.0))
        self.assertTrue(np.allclose(pts[:, 2], 0.0))

    def test_rake_turns_the_rows(self):
        _pts, a, b = S.lattice((0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0, 5.0, 5.0, rake_deg=30)
        self.assertAlmostEqual(math.degrees(math.atan2(a[1], a[0])), 30.0, places=6)
        self.assertAlmostEqual(float(np.dot(a, b)), 0.0, places=9)


class Frustum(unittest.TestCase):
    def test_square_to_its_surface(self):
        v, faces = S.frustum((0, 0, 0), (0, 0, 2), (1, 0, 0), foot=1.2, top=0.8, height=0.5, sink=0.1)
        self.assertEqual((len(v), len(faces)), (8, 6))   # (a closed solid: the foot face too)
        self.assertTrue(np.allclose(v[:4, 2], -0.1) and np.allclose(v[4:, 2], 0.5))
        self.assertAlmostEqual(float(np.ptp(v[:4, 0])), 1.2)
        self.assertAlmostEqual(float(np.ptp(v[4:, 0])), 0.8)

    def test_axis_projected_onto_a_tilted_surface(self):
        n = np.array([1.0, 0.0, 1.0]) / math.sqrt(2)
        v, _f = S.frustum((0, 0, 0), n, (1, 0, 0), foot=1.0, top=1.0, height=0.0, sink=0.0)
        edge = v[1] - v[0]
        self.assertAlmostEqual(float(np.dot(edge, n)), 0.0, places=9)   # its sides lie in the surface


if __name__ == "__main__":
    unittest.main()
