"""kit/vision/upscale.py tiling (every core pasted once, read with its context, no seams) and kit/vision/vectorize.py
helpers (Otsu's level, ink on paper, the SVG count) — pure numpy / PIL, no model, no GPU."""

import os
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vision"))

import upscale  # noqa: E402
import vectorize  # noqa: E402


def nearest(scale):
    return lambda a: np.repeat(np.repeat(a, scale, axis=0), scale, axis=1)


def blur_then_nearest(scale):
    """a 3 x 3 box blur (edges repeated) then nearest x scale: each output pixel sees 1 px around its source"""
    def fn(a):
        p = np.pad(a, ((1, 1), (1, 1)) + ((0, 0),) * (a.ndim - 2), mode="edge")
        b = sum(p[dy:dy + a.shape[0], dx:dx + a.shape[1]] for dy in range(3) for dx in range(3)) / 9
        return nearest(scale)(b)
    return fn


class TestTiles(unittest.TestCase):
    def test_cores_cover_the_picture_exactly_once(self):
        for w, h, tile in ((1000, 700, 384), (385, 384, 384), (17, 9, 4), (5, 5, 0), (300, 200, 1000)):
            hits = np.zeros((h, w), np.int32)
            for (x0, y0, x1, y1), _read in upscale.tiles(w, h, tile):
                hits[y0:y1, x0:x1] += 1
                if tile > 0:
                    self.assertLessEqual(x1 - x0, tile)
                    self.assertLessEqual(y1 - y0, tile)
            self.assertTrue((hits == 1).all(), (w, h, tile))

    def test_tiles_are_even_with_no_sliver(self):
        widths = sorted({x1 - x0 for (x0, _y0, x1, _y1), _r in upscale.tiles(385, 10, 384)})
        self.assertEqual(widths, [192, 193])  # (not 384 + a 1 px sliver)

    def test_a_read_holds_its_core_with_at_most_pad_around_it_inside_the_picture(self):
        w, h = 1000, 700
        for (x0, y0, x1, y1), (rx0, ry0, rx1, ry1) in upscale.tiles(w, h, 300, pad=16):
            self.assertTrue(0 <= rx0 <= x0 and 0 <= ry0 <= y0 and x1 <= rx1 <= w and y1 <= ry1 <= h)
            self.assertEqual(x0 - rx0, min(16, x0))
            self.assertEqual(rx1 - x1, min(16, w - x1))

    def test_tiled_equals_whole_for_a_pointwise_model(self):
        img = np.random.default_rng(1).random((53, 71, 3)).astype(np.float32)
        whole = nearest(4)(img)
        self.assertTrue(np.array_equal(upscale.stitch(img, nearest(4), 4, tile=16, pad=0), whole))

    def test_context_removes_seams(self):
        img = np.random.default_rng(2).random((40, 50, 3)).astype(np.float32)
        fn = blur_then_nearest(4)
        whole = fn(img)
        np.testing.assert_allclose(upscale.stitch(img, fn, 4, tile=12, pad=1), whole, atol=1e-6)
        seams = np.abs(upscale.stitch(img, fn, 4, tile=12, pad=0) - whole).max()
        self.assertGreater(seams, 1e-3)  # (without context the tile edges differ: the test can fail)

    def test_a_model_of_the_wrong_scale_is_refused(self):
        with self.assertRaises(ValueError):
            upscale.stitch(np.zeros((8, 8, 3), np.float32), nearest(2), 4, tile=4)

    def test_output_size(self):
        self.assertEqual(upscale.out_size(300, 200, 2), (600, 400))


class TestVectorizeHelpers(unittest.TestCase):
    def test_otsu_splits_two_levels_between_them(self):
        g = np.array([30] * 500 + [220] * 1500, np.uint8)
        self.assertTrue(30 < vectorize.otsu(g) <= 220)
        self.assertEqual(vectorize.otsu(np.full(100, 77, np.uint8)), 128)  # (a flat picture: no split)

    def test_dark_lines_are_ink_and_transparency_is_paper(self):
        rgba = np.zeros((10, 10, 4), np.uint8)
        rgba[:, :, :3] = 240
        rgba[:, :, 3] = 255
        rgba[4:6, :, :3] = 20  # a dark line
        rgba[0, 0] = (0, 0, 0, 0)  # transparent black: paper, not ink
        out, level = vectorize.ink(Image.fromarray(rgba, "RGBA"), "auto")
        a = np.asarray(out)
        self.assertTrue((a[4:6] == 0).all())
        self.assertEqual(int(a[0, 0]), 255)
        self.assertEqual(int((a == 0).sum()), 20)
        self.assertTrue(20 < level <= 240)

    def test_invert_reads_light_lines_on_a_dark_ground(self):
        rgb = np.full((10, 10, 3), 15, np.uint8)
        rgb[:, 3] = 250
        a = np.asarray(vectorize.ink(Image.fromarray(rgb, "RGB"), 128, invert=True)[0])
        self.assertTrue((a[:, 3] == 0).all())
        self.assertEqual(int((a == 0).sum()), 10)

    def test_svg_stats_counts_paths_and_segments(self):
        svg = ('<svg version="1.1" xmlns="http://www.w3.org/2000/svg" width="64" height="32">'
               '<path d="M0 0 C1 1 2 2 3 3 L4 4 Z " fill="#000"/><path d="M5 5 C6 6 7 7 8 8 Z" fill="#000"/></svg>')
        self.assertEqual(vectorize.svg_stats(svg), {"paths": 2, "segments": 3, "width": 64, "height": 32})


if __name__ == "__main__":
    unittest.main()
