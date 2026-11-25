"""A surface drawn by control points (kit/blender/rbx_nurbs.py; the owner's method lists: NURBS; the 3D methods
audit, stage K)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_nurbs as N  # noqa: E402


def flat(rows, cols):
    return np.array([[(c, 0.0, r) for c in range(cols)] for r in range(rows)], float)


class Pull(unittest.TestCase):
    def test_the_pulls_at_any_place_add_up_to_one(self):
        for n, degree in ((2, 1), (3, 2), (4, 3), (7, 3), (5, 2)):
            b = N.basis(n, degree, np.linspace(0, 1, 23))
            self.assertTrue(np.allclose(b.sum(axis=1), 1.0), (n, degree))
            self.assertTrue((b >= -1e-12).all())

    def test_the_ends_are_on_the_first_and_the_last_point(self):
        b = N.basis(6, 3, [0.0, 1.0])
        self.assertTrue(np.allclose(b[0], [1, 0, 0, 0, 0, 0]))
        self.assertTrue(np.allclose(b[1], [0, 0, 0, 0, 0, 1]))


class Surface(unittest.TestCase):
    def test_a_flat_net_draws_a_flat_surface_through_its_corners(self):
        net = flat(4, 5)
        s = N.surface(net, 8, 6)
        self.assertEqual(s.shape, (7, 9, 3))
        self.assertTrue(np.allclose(s[..., 1], 0.0))
        for (v, u), (r, c) in (((0, 0), (0, 0)), ((0, -1), (0, -1)), ((-1, 0), (-1, 0)), ((-1, -1), (-1, -1))):
            self.assertTrue(np.allclose(s[v, u], net[r, c]))

    def test_a_lifted_middle_pulls_the_surface_up_but_not_all_the_way(self):
        net = flat(4, 4)
        net[1:3, 1:3, 1] = 2.0
        s = N.surface(net, 12, 12)
        self.assertGreater(float(s[6, 6, 1]), 0.8)
        self.assertLess(float(s[..., 1].max()), 2.0)                  # inside the net's hull
        self.assertTrue(np.allclose(s[0, :, 1], 0.0) and np.allclose(s[:, 0, 1], 0.0))   # its rim stays down
        self.assertEqual(N.folded(s), 0.0)

    def test_two_points_draw_a_straight_line_and_a_net_too_small_is_refused(self):
        net = np.array([[(0, 0, 0), (4, 2, 0)], [(0, 0, 3), (4, 2, 3)]], float)
        s = N.surface(net, 4, 2)
        self.assertTrue(np.allclose(s[0, 2], (2, 1, 0)))
        with self.assertRaises(ValueError):
            N.surface(np.zeros((1, 4, 3)))

    def test_a_net_that_folds_over_itself_is_measured(self):
        net = flat(4, 4)
        net[:, 2, 0], net[:, 1, 0] = -2.0, 5.0                        # two columns crossed far over each other
        self.assertGreater(N.folded(N.surface(net, 16, 16)), 0.02)
        self.assertEqual(N.folded(N.surface(flat(4, 4), 16, 16)), 0.0)

    def test_a_fold_is_found_whatever_the_step_count(self):
        net = np.array([[(-1, 0, z), (1, 0, z), (-1, 0, z)] for z in (0.0, 1.0, 2.0)], float)     # doubles back on itself
        for steps in (8, 14, 15, 16, 32):
            self.assertGreater(N.folded(N.surface(net, steps, 8, 2)), 0.0, steps)
        self.assertGreater(N.net_folded(net, 2), 0.0)

    def test_a_tube_most_of_the_way_round_is_no_fold(self):
        ring = [(np.cos(a), np.sin(a)) for a in np.radians(np.linspace(0, 300, 9))]
        net = np.array([[(x, y, z) for x, y in ring] for z in (0.0, 1.0, 2.0)], float)
        self.assertEqual(N.net_folded(net), 0.0)
        self.assertEqual(N.folded(N.surface(net, 16, 4)), 0.0)

    def test_a_wall_thicker_than_the_bend_is_measured(self):
        ring = [(0.2 * np.cos(a), 0.2 * np.sin(a)) for a in np.radians(np.linspace(0, 180, 7))]
        net = np.array([[(x, y, z) for x, y in ring] for z in (0.0, 1.0)], float)
        grid = N.surface(net, 24, 4)
        inward = N.normals(grid) * (1 if N.normals(grid)[2, 12] @ np.array([0, -1, 0]) > 0 else -1)
        self.assertEqual(N.crossed(grid, grid + inward * 0.05), 0.0)       # a thin wall inside a 0.2 bend
        self.assertGreater(N.crossed(grid, grid + inward * 0.5), 0.2)      # a wall of 0.5 inside it: inside out

    def test_a_net_on_one_line_has_no_area_and_a_bad_point_is_refused(self):
        line = np.array([[(c, 0, 0) for c in range(3)] for _ in range(3)], float)
        self.assertLess(N.area(N.surface(line, 4, 4)), 1e-12)
        self.assertAlmostEqual(N.area(N.surface(flat(3, 3), 4, 4)), 4.0)
        bad = flat(3, 3)
        bad[1, 1, 1] = np.nan
        with self.assertRaises(ValueError):
            N.surface(bad)
        with self.assertRaises(ValueError):
            N.surface(flat(3, 3), degree=-1)

    def test_the_facing_is_the_rows_turned_into_the_columns(self):
        n = N.normals(N.surface(flat(3, 3), 4, 4))
        self.assertTrue(np.allclose(n[2, 2], (0, -1, 0)))             # x across, z down the rows: it faces -y
        up = N.normals(N.surface(flat(3, 3)[::-1], 4, 4))
        self.assertTrue(np.allclose(up[2, 2], (0, 1, 0)))             # the rows reversed: it faces +y


if __name__ == "__main__":
    unittest.main()
