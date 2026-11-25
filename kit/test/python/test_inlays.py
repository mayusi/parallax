"""kit refs inlays (kit/refs/inlays.py) — a view's coloured trim traced into polygons: the hue mask, a ring keeps its
hole, a reflection streak closes, a piece is cut at the split row, a crossed outline is repaired."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import inlays as I  # noqa: E402

GOLD = (230, 190, 60)


def canvas(w=200, h=160):
    return np.zeros((h, w, 3), np.uint8)


class Mask(unittest.TestCase):
    def test_gold_in_rose_out(self):
        im = canvas()
        im[10:40, 10:40] = GOLD
        im[60:90, 10:40] = (200, 80, 110)   # rose
        im[110:140, 10:40] = (40, 220, 90)  # a green gem
        m = I.colour_mask(im, (34, 72))
        self.assertTrue(m[20, 20])
        self.assertFalse(m[70, 20])
        self.assertFalse(m[120, 20])

    def test_dark_gold_shading_still_counts_above_the_floor(self):
        im = canvas()
        im[10:40, 10:40] = (120, 100, 30)
        self.assertTrue(I.colour_mask(im, (34, 72), val=0.3)[20, 20])
        self.assertFalse(I.colour_mask(im, (34, 72), val=0.6)[20, 20])


class Polys(unittest.TestCase):
    def ring(self):
        im = canvas()
        yy, xx = np.mgrid[0:160, 0:200]
        d = np.hypot(xx - 100, yy - 80)
        im[(d < 50) & (d > 30)] = GOLD
        return im

    def test_a_ring_keeps_its_hole(self):
        ps = I.polygons(I.colour_mask(self.ring(), (34, 72)), close=3, min_area=50)
        self.assertEqual(len(ps), 1)
        self.assertEqual(len(ps[0]["holes"]), 1)
        want = np.pi * (49.5 ** 2 - 30.5 ** 2)   # (a contour runs through the edge pixels' centres: half a pixel in)
        self.assertAlmostEqual(ps[0]["area_px"], want, delta=0.03 * want)

    def test_a_reflection_streak_is_closed(self):
        im = canvas()
        im[20:60, 20:180] = GOLD
        im[38:41, 20:180] = (20, 25, 40)   # (a dark reflection line across the band)
        self.assertEqual(len(I.polygons(I.colour_mask(im, (34, 72)), close=1, min_area=50)), 2)
        self.assertEqual(len(I.polygons(I.colour_mask(im, (34, 72)), close=7, min_area=50)), 1)

    def test_cut_at_the_split_row(self):
        ps = I.polygons(I.colour_mask(self.ring(), (34, 72)), close=3, min_area=50, split_y=80)
        self.assertEqual(sorted(p["side"] for p in ps), ["lower", "upper"])


class Clean(unittest.TestCase):
    def test_reflection_holes_fill_and_a_thin_line_survives(self):
        im = canvas(300, 200)
        im[20:120, 20:140] = GOLD                 # a wide band...
        im[60:66, 60:70] = (20, 25, 40)           # ...with a reflection speck in it
        im[150:156, 20:280] = GOLD                # a 6 px trim line
        m = I.clean(I.colour_mask(im, (34, 72)), close=3, fill_px=200)
        self.assertTrue(m[63, 65])                # the speck is filled
        self.assertTrue(m[153, 150])              # the thin line is still there (one strong blur erased it)
        self.assertEqual(len(I.polygons(m, close=1, min_area=50)), 2)

    def test_a_crossing_groove_is_bridged(self):
        im = canvas(200, 200)
        im[20:180, 60:140] = GOLD
        im[95:104, 60:140] = (150, 60, 80)        # a 9 px rose groove across the gold band
        m = I.clean(I.colour_mask(im, (34, 72)), close=1, bridge=15, fill_px=0)
        self.assertEqual(len(I.polygons(m, close=1, min_area=50)), 1)

    def test_trim_centrelines_carry_the_path_and_width(self):
        # a ring of trim 7 px wide and a straight bead 9 px wide: one CLOSED path round the ring at its radius, one
        # open path along the bead, each with its width (what cad_parts.bead sweeps)
        import cv2  # noqa: PLC0415

        m = np.zeros((200, 300), np.uint8)
        cv2.circle(m, (100, 100), 60, 1, 7)
        cv2.line(m, (180, 40), (280, 160), 1, 9)
        lines = I.centrelines(m.astype(bool))
        self.assertEqual(sorted(c["closed"] for c in lines), [False, True])
        ring = next(c for c in lines if c["closed"])
        r = [math.hypot(x - 100, y - 100) for x, y in ring["path"]]
        self.assertAlmostEqual(float(np.mean(r)), 60.0, delta=1.0)
        self.assertAlmostEqual(ring["width_px"], 7.0, delta=1.2)
        bead = next(c for c in lines if not c["closed"])
        self.assertAlmostEqual(bead["width_px"], 9.0, delta=1.2)
        (x0, y0), (x1, y1) = bead["path"][0], bead["path"][-1]
        self.assertGreater(math.hypot(x1 - x0, y1 - y0), 140)              # (end to end along the 156 px stroke)

    def test_a_wide_panel_gets_no_bead(self):
        m = np.zeros((200, 300), bool)
        m[40:120, 60:240] = True                  # (a gold PANEL 180 x 80: its medial axis is no trim)
        self.assertEqual(I.centrelines(m), [])


if __name__ == "__main__":
    unittest.main()
