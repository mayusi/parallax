"""kit/vision/exif_fov.py: the lens a photo was taken with (35 mm equivalent focal length in its EXIF) becomes the field
of view camera fitting starts from — the one parameter a small subject's silhouette cannot show (lens and pitch trade
off at weak perspective). No EXIF: null, never a guess."""

import math
import os
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vision"))
import exif_fov as E  # noqa: E402


class TestExifLens(unittest.TestCase):
    def _photo(self, path, size, f35=None):
        img = Image.new("RGB", size, (200, 200, 200))
        if f35 is None:
            img.save(path)
            return
        exif = Image.Exif()
        exif.get_ifd(0x8769)[41989] = f35  # FocalLengthIn35mmFilm
        img.save(path, exif=exif)

    def test_landscape_50mm(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.jpg")
            self._photo(p, (600, 400), 50)
            fov, f35 = E.fov_of(p)
        self.assertEqual(f35, 50.0)
        self.assertAlmostEqual(fov, math.degrees(2 * math.atan(18 / 50)), places=1)  # 39.6 deg across 36 mm

    def test_portrait_uses_the_short_side(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.jpg")
            self._photo(p, (400, 600), 50)
            fov, _ = E.fov_of(p)
        self.assertAlmostEqual(fov, math.degrees(2 * math.atan(12 / 50)), places=1)

    def test_no_exif_is_null(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.png")
            self._photo(p, (300, 200))
            self.assertEqual(E.fov_of(p), (None, None))


if __name__ == "__main__":
    unittest.main()
