"""kit look silhouette (kit/tools/look_silhouette.py) — pure parts: a build twice the reference's size whose width is
25% too wide is scaled by its HEIGHT only (never stretched to fit), so the rows say +5 mm on a 20 mm part, the extra
split on both sides; a reference lying on its side is found in the right quarter turn."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import look_silhouette as LS  # noqa: E402


def rect(h, w, H=200, W=200, y0=20, x0=30):
    m = np.zeros((H, W), bool)
    m[y0:y0 + h, x0:x0 + w] = True
    return m


class Silhouette(unittest.TestCase):
    def test_scaled_by_height_never_stretched(self):
        ref = rect(80, 40)
        ren = rect(160, 100, H=400, W=400)          # (2x the size, its width 25% too wide)
        built, s = LS.align(ref, ren, "height")
        self.assertAlmostEqual(s, 0.5, places=3)
        rs = [r for r in LS.rows(ref, built, 0.5, "height") if r["ref_mm"] > 0]
        mid = rs[len(rs) // 2]
        self.assertAlmostEqual(mid["ref_mm"], 20.0, delta=0.6)
        self.assertAlmostEqual(mid["diff_mm"], 5.0, delta=1.0)
        self.assertAlmostEqual(mid["left_mm"], mid["right_mm"], delta=1.0)   # (centred: the extra on both sides)

    def test_length_axis_for_a_top_view(self):
        ref = rect(20, 120)
        ren = rect(30, 240, H=300, W=300)           # (2x long, 15 / 10 = 50% too wide across)
        built, s = LS.align(ref, ren, "length")
        self.assertAlmostEqual(s, 0.5, places=3)
        rs = [r for r in LS.rows(ref, built, 1.0, "length") if r["ref_mm"] > 0]
        self.assertAlmostEqual(rs[len(rs) // 2]["diff_mm"], -5.0, delta=1.0)   # (rows run along: 15 vs 20 tall)

    def test_a_turned_reference_is_found(self):
        ref = np.rot90(rect(30, 100))               # (a top view lying on its side)
        tags = {t: m for t, _k, _f, m in LS.orientations(ref)}
        self.assertEqual(len(tags), 8)
        ren = rect(30, 100)
        best = max(tags.items(), key=lambda kv: (LS.align(kv[1], ren, "length")[0] & kv[1]).sum()
                   / max(1, (LS.align(kv[1], ren, "length")[0] | kv[1]).sum()))
        self.assertIn(best[0].split("+")[0], ("rot90", "rot270"))


if __name__ == "__main__":
    unittest.main()
