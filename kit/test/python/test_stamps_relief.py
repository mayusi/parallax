"""The relief stamps added for H4 (his limitations review V3: "a 7-stamp relief library", 2026-11-17): socket,
treadplate, louver, hinge, rib, hammered, nameplate - each the shape its name says, measured on its height field
(rbx_stamps, numpy only). test_stamps holds every kind to the common rules (0 on its border, not empty, a finest
feature); this holds each to its own."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_stamps as S  # noqa: E402

PX = 16


def _at(h, size, x_mm, y_mm):
    H, W = h.shape
    return float(h[min(H - 1, int(y_mm / size[1] * H)), min(W - 1, int(x_mm / size[0] * W))])


class Relief(unittest.TestCase):
    def test_socket_a_round_head_with_a_hex_cut_into_it(self):
        size = (30.0, 12.0)
        h = S.height("socket", size, PX, count=1, radius_mm=4.0)
        self.assertLess(_at(h, size, 15, 6), -0.5)        # (the socket: cut in at its centre)
        self.assertGreater(_at(h, size, 15 + 3.0, 6), 1.0)  # (the head between socket and rim stands proud)
        self.assertEqual(_at(h, size, 15 + 5.0, 6), 0.0)   # (outside the head: the surface)
        # a hex, not a circle: 0.45 r to a corner (0 deg), 0.39 r to a flat (30 deg) - 0.42 r out, toward a corner
        # is down the socket's chamfered mouth, toward a flat the head's full height
        d = 0.42 * 4.0
        corner = _at(h, size, 15 + d, 6)
        flat = _at(h, size, 15 + d * np.cos(np.pi / 6), 6 + d * np.sin(np.pi / 6))
        self.assertLess(corner, flat - 0.5, (corner, flat))

    def test_treadplate_bars_turn_the_other_way_in_each_next_cell(self):
        size, pitch = (40.0, 40.0), 10.0
        h = S.height("treadplate", size, PX, pitch_mm=pitch)
        # cell (0, 0) centred at (5, 5): its bar runs one diagonal; cell (1, 0) at (15, 5) the other
        a = _at(h, size, 5 + 2.0, 5 + 2.0) > 0.2 and _at(h, size, 5 + 2.0, 5 - 2.0) < 0.05
        b = _at(h, size, 15 + 2.0, 5 - 2.0) > 0.2 and _at(h, size, 15 + 2.0, 5 + 2.0) < 0.05
        self.assertTrue(a and b, (a, b))
        self.assertGreaterEqual(float(h.min()), 0.0)        # (raised only)

    def test_louver_lips_stand_proud_and_slope_back_in(self):
        size = (40.0, 16.0)
        h = S.height("louver", size, PX, slats=5)
        row = h[h.shape[0] // 2]
        self.assertGreater(float(row.max()), 0.5)
        self.assertLess(float(row.min()), -0.3)
        # a sharp rise then a long slope: most of each slat is falling
        d = np.diff(row[row != 0])
        self.assertGreater(float((d < 0).mean()), 0.6)

    def test_hinge_knuckles_with_gaps(self):
        size = (40.0, 8.0)
        h = S.height("hinge", size, PX, knuckles=5)
        line = h[h.shape[0] // 2]
        on = line > 0.5
        runs = int(np.sum(on[1:] & ~on[:-1]) + (1 if on[0] else 0))
        self.assertEqual(runs, 5)

    def test_rib_count(self):
        size = (30.0, 12.0)
        h = S.height("rib", size, PX, count=6)
        line = h[h.shape[0] // 2]
        on = line > 0.2
        self.assertEqual(int(np.sum(on[1:] & ~on[:-1]) + (1 if on[0] else 0)), 6)

    def test_hammered_is_centred_deterministic_and_open(self):
        size = (40.0, 24.0)
        h1, h2 = S.height("hammered", size, PX), S.height("hammered", size, PX)
        self.assertTrue(np.array_equal(h1, h2))
        inner = h1[8:-8, 8:-8]
        self.assertLess(abs(float(inner.mean())), 0.05)       # (as proud as it is sunk: no blotches of recess)
        self.assertIn("hammered", S.OPEN_KINDS)                # (never darkened as a recess that holds dirt)

    def test_nameplate_a_plate_with_four_screws(self):
        size = (40.0, 20.0)
        h = S.height("nameplate", size, PX)
        mid = _at(h, size, 20, 10)
        self.assertGreater(mid, 0.3)
        tops = [(x, y) for x, y in ((6.0, 6.0), (34.0, 6.0), (6.0, 14.0), (34.0, 14.0))]
        domes = [max(_at(h, size, x + dx, y + dy) for dx in np.linspace(-2, 2, 9) for dy in np.linspace(-2, 2, 9))
                 for x, y in tops]
        self.assertTrue(all(d > mid + 0.1 for d in domes), (mid, domes))

    def test_options_are_held(self):
        with self.assertRaises(ValueError):
            S.check("hinge", knuckles=0)
        with self.assertRaises(ValueError):
            S.check("rib", spacing=3)
        for k in ("socket", "treadplate", "louver", "hinge", "rib", "hammered", "nameplate"):
            self.assertIn(k, S.KINDS)


if __name__ == "__main__":
    unittest.main()
