"""The ornament relief stamps (kit/blender/rbx_stamps.py: rope, fluting, milgrain, scales, scroll) - his V3 list, 3D
stage D.2 (2026-11-18). numpy only: no Blender. Each is a height field in mm; these hold what makes it read as itself."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_stamps as S  # noqa: E402


class Ornament(unittest.TestCase):
    def test_the_raised_ones_stand_proud_and_fluting_is_cut_in(self):
        for k in ("rope", "milgrain", "scales", "scroll"):
            h = S.height(k, (40.0, 12.0), px_per_mm=10)
            self.assertGreaterEqual(float(h.min()), 0.0, k)
            self.assertGreater(float(h.max()), 0.2, k)
        h = S.height("fluting", (40.0, 12.0), px_per_mm=10)
        self.assertLessEqual(float(h.max()), 0.0)
        self.assertLess(float(h.min()), -0.2)

    def test_milgrain_is_a_row_of_as_many_separate_beads_as_asked(self):
        h = S.height("milgrain", (40.0, 4.0), px_per_mm=20, count=9)
        row = h[h.shape[0] // 2] > 0.05
        self.assertEqual(int(np.sum(np.diff(row.astype(int)) == 1)), 9)

    def test_fluting_has_as_many_channels_as_asked_with_a_fillet_between(self):
        h = S.height("fluting", (40.0, 15.0), px_per_mm=20, count=5)
        col = h[:, h.shape[1] // 2] < -0.05
        self.assertEqual(int(np.sum(np.diff(col.astype(int)) == 1)), 5)
        self.assertGreater(int(np.sum(~col[5:-5])), 4 * 3)   # (a fillet of untouched surface between each)

    def test_a_rope_strand_groove_curves_with_the_helix(self):
        # (seen from the front a strand's groove is steep across the middle and turns along the rope at its edges)
        h = S.height("rope", (60.0, 12.0), px_per_mm=20)
        mid, edge = h.shape[0] // 2, int(h.shape[0] * 0.12)

        def groove_x(r):
            return int(np.argmin(h[r, 200:600])) + 200
        self.assertNotEqual(groove_x(mid) - groove_x(mid + 40), 0)       # (the groove moves along the rope)
        slope_mid = abs(groove_x(mid) - groove_x(mid + 20))
        slope_edge = abs(groove_x(edge) - groove_x(edge + 20))
        self.assertGreater(slope_edge, slope_mid)                          # (flatter toward the edge: it curves)

    def test_each_scale_lies_over_the_one_below(self):
        # (fish scales overlap toward the tail: going DOWN the stamp the height rises to a scale's free edge, then
        #  steps DOWN onto the scale under it - never the other way round)
        h = S.height("scales", (60.0, 24.0), px_per_mm=20, pitch_mm=10.0)
        col = h[40:-40, h.shape[1] // 2].astype(float)
        steps = np.diff(col)
        self.assertGreater(float(-steps.min()), 4 * float(steps.max()))   # (sharp drops down, gentle rises)

    def test_pointed_scales_have_a_point_round_ones_do_not(self):
        # (both cover the whole stamp: what differs is each free edge's outline - the drop onto the scale below)
        r = S.height("scales", (60.0, 24.0), px_per_mm=20, pitch_mm=10.0)
        p = S.height("scales", (60.0, 24.0), px_per_mm=20, pitch_mm=10.0, shape="pointed")
        er, ep = np.abs(np.diff(r, axis=0)) > 0.1, np.abs(np.diff(p, axis=0)) > 0.1
        self.assertGreater(float(np.mean(er != ep)), 0.005)
        with self.assertRaises(ValueError):
            S.height("scales", (60.0, 24.0), shape="hex")

    def test_a_scroll_has_one_spiral_a_wave_and_its_line_is_as_tall_as_asked(self):
        lines = S.scroll_line(60.0, 14.0, {})
        h = S.height("scroll", (60.0, 14.0), px_per_mm=20, height_mm=0.8)
        self.assertEqual(len(lines), 3)
        self.assertAlmostEqual(float(h.max()), 0.8, delta=0.02)
        for pts in lines:   # (each wave ends curled in: its last point near its spiral's centre, inside the band)
            self.assertTrue(np.all((pts[:, 1] > 0) & (pts[:, 1] < 14.0)))

    def test_a_vertical_box_runs_it_down(self):
        for k in ("rope", "fluting", "milgrain", "scroll"):
            a = S.height(k, (40.0, 10.0), px_per_mm=10)
            b = S.height(k, (10.0, 40.0), px_per_mm=10)
            self.assertLess(float(np.abs(a.T - b).max()), 0.02, k)

    def test_finest_feature_reads_the_options(self):
        self.assertAlmostEqual(S.finest_mm("milgrain", (40.0, 4.0), radius_mm=1.0), 1.0)
        self.assertAlmostEqual(S.finest_mm("rope", (40.0, 10.0), pitch_mm=8.0), 2.0)
        self.assertAlmostEqual(S.finest_mm("scroll", (60.0, 14.0), line_mm=1.2), 1.2)


if __name__ == "__main__":
    unittest.main()
