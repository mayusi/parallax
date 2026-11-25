"""The judge packet's images reach a vision model at their own pixels: every image inside VISION_MAX_PX /
VISION_MAX_EDGE (a 2400 x 2220 sheet was shrunk to ~46 % in the judges' eyes — modelled detail judged missing)."""

import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import judge as J  # noqa: E402


def _cell(w, h, shade):
    img = Image.new("RGB", (w, h), (shade, shade, shade))
    img.paste((255, 255, 255), (w // 4, h // 4, w // 2, h // 2))   # (something drawn: not an empty cell)
    return img


class PacketImages(unittest.TestCase):
    def test_fits_vision_limits(self):
        self.assertTrue(J.fits_vision(1536, 600))
        self.assertFalse(J.fits_vision(2400, 2220))   # (the old one-sheet packet)
        self.assertFalse(J.fits_vision(1600, 300))    # (past the long-edge limit, however few pixels)
        self.assertFalse(J.fits_vision(1100, 1100))   # (past the pixel budget, however short the edges)

    def test_close_ups_packed_at_their_own_size(self):
        cells = [_cell(640, 480, 40 + i) for i in range(6)]
        imgs = J.pack_cells(cells, "MODEL close-ups")
        self.assertEqual(len(imgs), 3)   # two 640 x 480 views an image
        for img in imgs:
            self.assertTrue(J.fits_vision(*img.size), img.size)
            self.assertEqual(img.width, 1280)   # (the cells' own width: nothing shrunk)
        self.assertEqual(J.pack_cells([], "x"), [])

    def test_small_cells_share_an_image(self):
        imgs = J.pack_cells([_cell(300, 200, 50) for _ in range(10)], "parts")
        self.assertEqual(len(imgs), 1)
        self.assertTrue(J.fits_vision(*imgs[0].size))

    def test_empty_cells_dropped(self):
        grid = Image.new("RGB", (1920, 960), (24, 24, 26))
        grid.paste(_cell(640, 480, 60), (0, 0))
        grid.paste(_cell(640, 480, 70), (640, 480))
        self.assertEqual(len(J._cells(grid, 640, 480)), 2)   # (4 blank cells of a 3 x 2 sheet left out)


if __name__ == "__main__":
    unittest.main()
