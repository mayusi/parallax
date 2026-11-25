"""kit/refs/outline.py: a reference model's parts as exact outlines (kit refs outline — the route that took the ODM
swords from 4 to 9). A plate's outline and its real opening are found, a checker cell and a pixel gap are not; the
flat plane is the two longest axes; a stray backdrop is left out."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "refs"))
import outline as O  # noqa: E402


def grid_plate(x0, y0, x1, y1, n=40, hole=None, cell=None):
    """a flat plate (x0..x1, y0..y1) as triangles, optionally with a square hole and a tiny checker gap"""
    xs = np.linspace(x0, x1, n + 1)
    ys = np.linspace(y0, y1, n + 1)
    V, T = [], []
    for i in range(n):
        for j in range(n):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if hole and hole[0] < cx < hole[2] and hole[1] < cy < hole[3]:
                continue
            if cell and cell[0] < cx < cell[2] and cell[1] < cy < cell[3]:
                continue
            k = len(V)
            V += [(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])]
            T += [(k, k + 1, k + 2), (k, k + 2, k + 3)]
    return np.array(V, float), np.array(T, int)


class Outline(unittest.TestCase):
    def test_a_plates_outline_and_its_real_opening_a_checker_cell_is_no_hole(self):
        V, T = grid_plate(0, 0, 60, 40, n=60, hole=(20, 10, 34, 24), cell=(45, 30, 46.5, 31.5))
        polys = O.outline_part(V, T, res=0.25)
        outer = [p for p in polys if not p["hole"]]
        holes = [p for p in polys if p["hole"]]
        self.assertEqual(len(outer), 1)
        self.assertEqual(len(holes), 1, [h["area_mm2"] for h in holes])   # (the 14 x 14 window; the 1.5 mm cell: no)
        self.assertAlmostEqual(holes[0]["area_mm2"], 14 * 14, delta=30)
        box = np.array(outer[0]["pts"])
        self.assertAlmostEqual(np.ptp(box[:, 0]), 60, delta=1.5)
        self.assertAlmostEqual(np.ptp(box[:, 1]), 40, delta=1.5)


class Plane(unittest.TestCase):
    def test_the_flat_plane_is_the_two_longest_axes(self):
        pts = np.array([[0, 0, 0], [200, 5, 120], [100, 2, 60]], float)   # (thin along y)
        self.assertEqual(O.auto_plane(pts), (0, 2, 1))
        self.assertEqual(O.plane_of("xy", pts), (0, 1, 2))


class Strays(unittest.TestCase):
    def test_a_far_backdrop_is_left_out(self):
        centres = np.array([[0, 0, 0], [10, 5, 0], [5, -5, 0], [900, 0, 0]], float)
        sizes = np.array([[20, 20, 5], [10, 10, 5], [10, 10, 5], [5, 5, 5]], float)
        self.assertEqual(O.drop_strays(centres, sizes).tolist(), [False, False, False, True])


if __name__ == "__main__":
    unittest.main()
