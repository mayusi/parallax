"""A part's outline CUT BY ITS MAP (kit/blender/rbx_cutout.py; the owner's method lists, 2026-11-13: "alpha
clipping"; the 3D methods audit, S1): the point of the surface under every texel, a rule or a picture saying where
it stays, the map's alpha."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_cutout as C  # noqa: E402

# a sheet 2 wide (x), 1 tall (y), at z = 3, laid on the lower left quarter of the map
UV = np.array([[(0, 0), (0.5, 0), (0.5, 0.5)], [(0, 0), (0.5, 0.5), (0, 0.5)]], float)
PTS = np.array([[(0, 0, 3), (2, 0, 3), (2, 1, 3)], [(0, 0, 3), (2, 1, 3), (0, 1, 3)]], float)


class Texels(unittest.TestCase):
    def test_every_covered_texel_knows_its_point_of_the_surface(self):
        rows, cols, pts = C.texels(UV, PTS, 16)
        self.assertEqual(len(rows), 64)                                    # 8 x 8 of the 16 x 16 map
        self.assertTrue((rows < 8).all() and (cols < 8).all())
        self.assertTrue(np.allclose(pts[:, 2], 3.0))
        # the texel centre (c + 0.5) / 16 of the map is (c + 0.5) / 8 of the sheet's width 2
        self.assertTrue(np.allclose(pts[:, 0], (cols + 0.5) / 8 * 2))
        self.assertTrue(np.allclose(pts[:, 1], (rows + 0.5) / 8 * 1))

    def test_nothing_covered_gives_nothing(self):
        rows, cols, pts = C.texels(np.zeros((0, 3, 2)), np.zeros((0, 3, 3)), 16)
        self.assertEqual((len(rows), len(cols), pts.shape), (0, 0, (0, 3)))


class Rules(unittest.TestCase):
    def test_a_rule_says_where_the_surface_stays(self):
        rows, cols, pts = C.texels(UV, PTS, 16)
        kept = C.by_rule(pts, lambda p: p[0] < 1.0)                        # the left half stays
        self.assertAlmostEqual(C.share(kept), 0.5)
        a = C.alpha_map(16, rows, cols, kept)
        self.assertTrue((a[:8, :4] == 255).all() and (a[:8, 4:8] == 0).all())
        self.assertTrue((a[8:] == 255).all() and (a[:, 8:] == 255).all())   # what the part does not cover stays

    def test_bars_of_a_grille(self):
        _rows, _cols, pts = C.texels(UV, PTS, 64)
        kept = C.by_rule(pts, lambda p: (p[0] % 0.5) < 0.25)
        self.assertAlmostEqual(C.share(kept), 0.5, delta=0.02)


class Pictures(unittest.TestCase):
    def test_the_frame_is_the_sheets_own_plane_read_from_the_models_front(self):
        origin, across, up, width, height = C.frame_of(PTS.reshape(-1, 3))
        # the model is looked at from -Z, where its +X is on the viewer's LEFT: the picture runs toward -X
        self.assertTrue(np.allclose(across, (-1, 0, 0)) and np.allclose(up, (0, 1, 0)))
        self.assertTrue(np.allclose(origin, (2, 0, 3)))                    # its bottom left: the sheet's +X end
        self.assertAlmostEqual(width, 2.0)
        self.assertAlmostEqual(height, 1.0)
        # wound the other way: the same picture
        again = C.frame_of(PTS.reshape(-1, 3)[::-1])
        self.assertTrue(np.allclose(again[1], across) and np.allclose(again[0], origin))
        side = np.array([(1, 0, 0), (1, 0, 2), (1, 1, 2), (1, 1, 0)], float)   # a sheet facing X: seen from +X
        self.assertTrue(np.allclose(C.frame_of(side)[1], (0, 0, -1)))
        flat = np.array([(0, 1, 0), (2, 1, 0), (2, 1, 1), (0, 1, 1)], float)   # lying flat: seen from above
        _o, a_, u_, _w, _h = C.frame_of(flat)
        self.assertTrue(np.allclose(u_, (0, 0, 1)) and np.allclose(a_, (-1, 0, 0)))

    def test_a_picture_laid_on_the_sheet_cuts_its_outline(self):
        # a picture 4 wide, 2 tall: solid in its TOP row only (row 0 is the top)
        pic = np.array([[1, 1, 1, 1], [0, 0, 0, 0]], float)
        rows, cols, pts = C.texels(UV, PTS, 16)
        kept = C.by_picture(pts, pic, C.frame_of(PTS.reshape(-1, 3)))
        self.assertTrue((kept == (pts[:, 1] > 0.5)).all())                 # the upper half of the sheet stays
        left = np.array([[1, 0, 0, 0], [1, 0, 0, 0]], float)               # the picture's LEFT quarter
        kept = C.by_picture(pts, left, C.frame_of(PTS.reshape(-1, 3)))
        self.assertTrue((kept == (pts[:, 0] > 1.5)).all())                 # the viewer's left from the front: +X


class Margin(unittest.TestCase):
    def test_the_cut_is_carried_into_the_margin_round_an_island(self):
        covered = np.zeros((12, 12), bool)
        covered[4:8, 4:8] = True                                           # one island
        alpha = np.full((12, 12), 255, np.uint8)
        alpha[4:8, 4:6] = 0                                                # its left half cut away
        out = C.into_margin(alpha, covered, 2)
        self.assertTrue((out[4:8, 2:4] == 0).all())                        # the margin beside the cut half: cut
        self.assertTrue((out[4:8, 8:10] == 255).all())                     # beside the solid half: solid
        self.assertTrue((out[4:8, 4:8] == alpha[4:8, 4:8]).all())          # the island itself: as it was
        self.assertTrue((out[:, :2] == 255).all())                         # further than the reach: untouched

    def test_a_point_outside_the_picture_is_cut_away(self):
        frame = (np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 1.0, 1.0)
        kept = C.by_picture(np.array([(0.5, 0.5, 0), (1.5, 0.5, 0), (0.5, -0.2, 0)]), np.ones((2, 2)), frame)
        self.assertEqual(kept.tolist(), [True, False, False])


if __name__ == "__main__":
    unittest.main()
