"""Quads or triangle soup (kit/blender/rbx_quads.py; LIMITATIONS_FIXES_V4 3D-X: the hybrid route's retopology and the
R6 clothing standard). Pure numpy. Measured on real meshes (merged at their UV seams, as the kit imports them):
an Instant Meshes quad remesh triangulated for export 0.93, a TRELLIS.2 crust 0.39, the same crust decimated 0.14."""

import math
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_quads as Q  # noqa: E402


def grid(n=20, m=20, jitter=0.0, split="fixed", seed=0):
    rng = np.random.default_rng(seed)
    co = np.array([(i + jitter * (rng.random() - 0.5), j + jitter * (rng.random() - 0.5), 0.0)
                   for j in range(m + 1) for i in range(n + 1)], float)
    quads = []
    for j in range(m):
        for i in range(n):
            a, b = j * (n + 1) + i, j * (n + 1) + i + 1
            quads.append((a, b, b + n + 1, a + n + 1))
    tris = []
    for a, b, c, d in quads:
        if split == "random" and rng.random() < 0.5:
            tris += [(a, b, d), (b, c, d)]
        else:
            tris += [(a, b, c), (a, c, d)]
    return co, quads, np.array(tris)


class QuadShare(unittest.TestCase):
    def test_a_quad_grid_split_for_export_pairs_back(self):
        co, _q, tris = grid()
        self.assertGreater(Q.quad_share(tris, co), 0.95)

    def test_the_same_grid_as_soup_does_not(self):
        co, _q, tris = grid(jitter=0.9, split="random", seed=3)
        self.assertLess(Q.quad_share(tris, co), 0.5)

    def test_a_skewed_quad_is_not_a_good_quad(self):
        # a rhombus of 30 / 150 degree corners: two triangles across the long diagonal, flat - but no loop
        s = math.radians(30)
        co = np.array([(0, 0, 0), (1, 0, 0), (1 + math.cos(s), math.sin(s), 0), (math.cos(s), math.sin(s), 0)])
        self.assertEqual(Q.quad_share(np.array([(0, 1, 2), (0, 2, 3)]), co), 0.0)
        # ... the same with square corners is one
        co2 = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], float)
        self.assertEqual(Q.quad_share(np.array([(0, 1, 2), (0, 2, 3)]), co2), 1.0)

    def test_a_folded_pair_is_not_a_quad(self):
        co = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0.0), (0, 1, 1.2)], float)   # (the second half turned up 50 deg)
        self.assertEqual(Q.quad_share(np.array([(0, 1, 2), (0, 2, 3)]), co), 0.0)

    def test_polygons_are_judged_not_trusted(self):
        # four-sided faces with corners of 30 / 150 degrees (what join-triangles makes of soup) are not quads
        co, quads, _t = grid(jitter=0.0)
        self.assertGreater(Q.polygon_share(quads, co)[0], 0.95)
        sk = co.copy()
        sk[:, 0] += sk[:, 1] * 1.8   # shear the grid: every corner 29 / 151 degrees
        share, tris = Q.polygon_share(quads, sk)
        self.assertEqual(tris, 2 * len(quads))
        self.assertLess(share, 0.05)

    def test_empty(self):
        self.assertEqual(Q.quad_share(np.zeros((0, 3), np.int64), np.zeros((0, 3))), 0.0)
        self.assertEqual(Q.polygon_share([], np.zeros((0, 3))), (0.0, 0))


if __name__ == "__main__":
    unittest.main()
