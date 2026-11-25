"""kit ui ink: a picture splits into ink / mid / paper by luminance, the mid-tone becomes a dot screen, a cut-out
picture is recognised by its transparent border"""
import os
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("kit_ui_ink", os.path.join(HERE, "..", "..", "ui", "ink.py"))
ink = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ink)


class TestInk(unittest.TestCase):
    def test_transparent_border_means_already_cut_out(self):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        for x in range(16, 48):
            for y in range(16, 48):
                im.putpixel((x, y), (200, 30, 30, 255))
        self.assertTrue(ink.has_transparent_border(im))
        self.assertFalse(ink.has_transparent_border(Image.new("RGBA", (64, 64), (200, 30, 30, 255))))
        self.assertFalse(ink.has_transparent_border(Image.new("RGB", (64, 64), (200, 30, 30))))

    def test_luminance_splits_dark_mid_light(self):
        rgb = np.array([[[0, 0, 0], [128, 128, 128], [250, 250, 250]]], dtype=np.float32)
        L = ink.luminance(rgb)
        self.assertLess(L[0, 0], 0.36)
        self.assertTrue(0.36 <= L[0, 1] < 0.68)
        self.assertGreaterEqual(L[0, 2], 0.68)

    def test_cel_identity_palette_maps_lightness_to_four_tones(self):
        # the poster palette used by --mode cel --palette identity: by lightness → ink, accent dark, accent, paper
        paper = np.array([240, 240, 240], dtype=np.float32)
        accent = np.array([162, 77, 255], dtype=np.float32)
        qa = np.array([[[10, 10, 10], [90, 90, 90], [150, 150, 150], [230, 230, 230]]], dtype=np.float32)
        Lq = ink.luminance(qa)
        dark, light = 0.22, 0.62
        out = np.zeros_like(qa)
        out[:] = paper
        out[Lq < light] = accent
        out[Lq < (dark + light) / 2] = accent * 0.55
        out[Lq < dark] = np.array([0, 0, 0], dtype=np.float32)
        self.assertEqual(out[0, 0].tolist(), [0, 0, 0])
        self.assertTrue(np.allclose(out[0, 1], accent * 0.55))
        self.assertTrue(np.allclose(out[0, 2], accent))
        self.assertTrue(np.allclose(out[0, 3], paper))

    def test_halftone_dots_grow_with_darkness(self):
        light = ink.halftone_mask(np.full((64, 64), 0.15, dtype=np.float32), pitch=8)
        dark = ink.halftone_mask(np.full((64, 64), 0.95, dtype=np.float32), pitch=8)
        self.assertLess(light.mean(), dark.mean())  # bigger dots where it is darker
        self.assertGreater(dark.mean(), 0.5)
        self.assertLess(light.mean(), 0.1)
        none = ink.halftone_mask(np.zeros((32, 32), dtype=np.float32), pitch=8)
        self.assertEqual(int(none.sum()), 0)


if __name__ == "__main__":
    unittest.main()
