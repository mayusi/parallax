"""rbx_stamps — the detail stamps a.stamp bakes into the normal map: every kind is a height field in mm, 0 on its
border (nothing steps where a stamp ends), raised kinds stand proud, cut kinds go in; the facing table is a right-
handed view from outside each face."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_stamps as S  # noqa: E402

PROUD = {"rivets", "bolts", "weld"}
CUT = {"vent", "panel_line", "grille"}


class Kinds(unittest.TestCase):
    def test_every_kind_is_zero_on_its_border_and_not_empty(self):
        for k in S.KINDS:
            h = S.height(k, (30.0, 12.0), px_per_mm=8)
            border = np.r_[h[0], h[-1], h[:, 0], h[:, -1]]
            self.assertLess(float(np.abs(border).max()), 1e-6, k)
            self.assertGreater(float(np.abs(h).max()), 0.1, k)
            self.assertEqual(h.dtype, np.float32)

    def test_raised_kinds_stand_proud_cut_kinds_go_in(self):
        for k in PROUD:
            h = S.height(k, (30.0, 10.0))
            self.assertGreater(h.max(), 0.3, k)
            self.assertGreaterEqual(h.min(), 0.0, k)
        for k in CUT:
            h = S.height(k, (30.0, 16.0))
            self.assertLess(h.min(), -0.3, k)
            self.assertLessEqual(h.max(), 0.0, k)

    def test_count_and_size_follow_the_options(self):
        h = S.height("rivets", (40.0, 8.0), px_per_mm=10, count=4, radius_mm=2.0)
        row = h[h.shape[0] // 2] > 0
        self.assertEqual(int(np.sum(np.diff(row.astype(int)) == 1)), 4)   # (four separate domes along the row)
        self.assertAlmostEqual(float(h.max()), 2.0 * 0.45, delta=0.05)

    def test_vertical_box_runs_its_row_down(self):
        h = S.height("rivets", (8.0, 40.0), px_per_mm=10, count=3, radius_mm=2.0)
        col = h[:, h.shape[1] // 2] > 0
        self.assertEqual(int(np.sum(np.diff(col.astype(int)) == 1)), 3)

    def test_screw_drive_is_cut_into_its_head(self):
        h = S.height("screws", (12.0, 12.0), px_per_mm=20, count=1, radius_mm=4.0, drive="cross")
        cy, cx = h.shape[0] // 2, h.shape[1] // 2
        self.assertLess(h[cy, cx], 0)   # (the cross's middle)
        self.assertGreater(h[cy + int(2.5 * 20 * 0.7), cx + int(2.5 * 20 * 0.7)], 0)   # (the head between the arms)

    def test_unknown_kind_and_facing_are_refused(self):
        with self.assertRaises(ValueError):
            S.height("sprocket")
        with self.assertRaises(ValueError):
            S.facing_axes("Q")

    def test_options_are_checked(self):
        for kind, bad in (("rivets", {"cout": 5}), ("rivets", {"count": 0}), ("vent", {"depth_mm": -1}),
                          ("screws", {"drive": "torx"}), ("knurl", {"radius_mm": 2})):
            with self.assertRaises(ValueError, msg=(kind, bad)):
                S.height(kind, (20.0, 6.0), **bad)

    def test_finest_feature(self):
        self.assertAlmostEqual(S.finest_mm("rivets", (30.0, 6.0), radius_mm=2.0), 4.0)
        self.assertAlmostEqual(S.finest_mm("screws", (30.0, 6.0), radius_mm=3.0), 0.72)
        self.assertAlmostEqual(S.finest_mm("panel_line", (30.0, 20.0), width_mm=1.6), 1.6)
        self.assertAlmostEqual(S.finest_mm("knurl", (30.0, 20.0), pitch_mm=3.0), 1.5)
        for k in S.KINDS:   # (every kind answers, positive)
            self.assertGreater(S.finest_mm(k, (30.0, 12.0)), 0, k)

    def test_image_size_is_capped(self):
        h = S.height("panel_line", (900.0, 300.0), px_per_mm=8)   # (would be 7200 px wide)
        self.assertLessEqual(max(h.shape), S.MAX_PX + 1)


class Facing(unittest.TestCase):
    def test_axes_are_right_handed_seen_from_outside(self):
        for f in ("-Z", "+Z", "-X", "+X", "+Y", "-Y", "x"):
            n, r, u = S.facing_axes(f)
            self.assertAlmostEqual(float(np.dot(n, r)), 0.0)
            self.assertAlmostEqual(float(np.dot(n, u)), 0.0)
            # a viewer outside the face looks along -n: right x up points back at them (toward n)
            self.assertTrue(np.allclose(np.cross(r, u), n), f)


if __name__ == "__main__":
    unittest.main()
