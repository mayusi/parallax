"""kit look edges (kit/tools/look_edges.py) — the build's edges against the art's, region by region: a region whose
build edges are narrower ramps reads "sharper than the art", the same ramps "matches"; the next round_mm moves the
part's round by the difference, capped at half its thinnest side, and leaves designed parts (screws, gems) alone."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "refs"))
import look_edges as LE  # noqa: E402


class Compare(unittest.TestCase):
    def test_sharper_and_matching_regions(self):
        H, W = 100, 200
        art = np.full((H, W), np.nan, np.float32)
        build = np.full((H, W), np.nan, np.float32)
        art[:, :100:3] = 12.0                     # (the art's left half: wide ramps, a round edge)
        build[:, :100:3] = 2.0                    # (the build's: a step)
        art[:, 100::3] = 6.0
        build[:, 100::3] = 6.0
        left = np.zeros((H, W), bool)
        left[:, :100] = True
        res = LE.compare_regions(art, build, {"left": left, "right": ~left}, 0.15, margin=0.4)
        self.assertEqual(res["left"]["verdict"], "sharper than the art")
        self.assertEqual(res["right"]["verdict"], "matches")

    def test_next_round_moves_by_the_difference_capped_and_skips_designed_parts(self):
        res = {"hammer": {"diff_mm": -1.7}, "grip": {"diff_mm": -1.1}}
        cad = [{"part": "PHammer", "round_mm": 1.4, "bbox_mm": [[-4, 0, 0], [4, 30, 30]]},
               {"part": "PGripL", "round_mm": 0.9, "bbox_mm": [[-1.3, 0, 0], [1.3, 40, 60]]},
               {"part": "PGripScrewL1", "bbox_mm": [[-1.6, 0, 0], [1.6, 5, 5]]}]
        s = LE.suggest(res, cad, ["P"])
        self.assertAlmostEqual(s["PHammer"]["round_mm_next"], 3.1, places=2)
        self.assertAlmostEqual(s["PGripL"]["round_mm_next"], 0.48 * 2.6, places=2)
        self.assertTrue(s["PGripL"]["capped"])
        self.assertNotIn("PGripScrewL1", s)

    def test_part_ids_decode_both_ways(self):
        # ids 1, 17, 200 encoded as look_ortho --ids draws them; with no transform and through an sRGB curve
        ids = np.array([[1, 17, 200, 0]])
        rgb = np.zeros((1, 4, 4), np.uint8)
        for k, v in enumerate(ids[0]):
            if v:
                rgb[0, k] = [16 * (v % 16) + 8, 16 * (v // 16) + 8, 0, 255]
        self.assertEqual(LE.decode_ids(rgb).tolist(), ids.tolist())
        lin = rgb[..., :3].astype(np.float32) / 255.0
        srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
        enc = rgb.copy()
        enc[..., :3] = np.rint(srgb * 255).astype(np.uint8)
        self.assertEqual(LE.decode_ids(enc, "Standard").tolist(), ids.tolist())

    def test_cells_cover_the_object(self):
        m = np.zeros((90, 90), bool)
        m[10:80, 10:80] = True
        cs = LE.cells(m, 30)
        self.assertGreaterEqual(len(cs), 4)
        self.assertTrue(all((c & ~m).sum() == 0 for c in cs.values()))


if __name__ == "__main__":
    unittest.main()
