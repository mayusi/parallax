"""The style report's silhouette measures (kit/vision/style.py): solidity, fill and aspect of a mask, the convex hull
they rest on, and the range check against the style's own images. Pure numpy — no model is loaded."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vision"))
import style as St  # noqa: E402


def rect(h, w, H=200, W=200):
    m = np.zeros((H, W), np.float32)
    m[10:10 + h, 10:10 + w] = 1
    return m


class TestShape(unittest.TestCase):
    def test_hull_of_a_square(self):
        self.assertAlmostEqual(St.hull_area([(0, 0), (4, 0), (4, 4), (0, 4), (2, 2)]), 16.0)

    def test_a_rectangle_is_solid_and_full(self):
        s = St.shape(rect(50, 100))
        self.assertAlmostEqual(s["solidity"], 1.0, places=2)
        self.assertAlmostEqual(s["fill"], 1.0, places=2)
        self.assertAlmostEqual(s["aspect"], 2.0, places=2)

    def test_an_l_shape_is_less_solid(self):
        m = rect(100, 100)
        m[10:60, 60:110] = 0  # cut a quarter out of the corner
        s = St.shape(m)
        self.assertLess(s["solidity"], 0.9)
        self.assertGreater(s["solidity"], 0.7)
        self.assertAlmostEqual(s["fill"], 0.75, places=2)

    def test_a_disc_fills_its_box_by_pi_over_four(self):
        yy, xx = np.mgrid[:200, :200]
        s = St.shape(((yy - 100) ** 2 + (xx - 100) ** 2 <= 80 ** 2).astype(np.float32))
        self.assertAlmostEqual(s["fill"], np.pi / 4, delta=0.02)
        self.assertGreater(s["solidity"], 0.97)

    def test_the_closest_view_is_compared(self):
        refs = [{"solidity": 0.35, "fill": 0.2, "aspect": 5.0}, {"solidity": 0.4, "fill": 0.22, "aspect": 6.0}]
        views = {"hero": {"solidity": 0.46, "fill": 0.26, "aspect": 7.8}, "front": {"solidity": 0.38, "fill": 0.21,
                 "aspect": 5.6}, "top": None}
        self.assertEqual(St.closest(views, refs)[0], "front")
        self.assertEqual(St.closest({}, refs), (None, None))

    def test_no_object(self):
        self.assertIsNone(St.shape(np.zeros((50, 50))))

    def test_range_check(self):
        refs = [{"solidity": 0.8, "fill": 0.6, "aspect": 2.0}, {"solidity": 0.9, "fill": 0.7, "aspect": 3.0}]
        self.assertEqual(St.outside({"solidity": 0.85, "fill": 0.65, "aspect": 2.5}, refs), [])
        off = St.outside({"solidity": 0.5, "fill": 0.65, "aspect": 6.0}, refs)
        self.assertEqual([k for k, *_ in off], ["solidity", "aspect"])
        self.assertEqual(St.outside(None, refs), [])


if __name__ == "__main__":
    unittest.main()
