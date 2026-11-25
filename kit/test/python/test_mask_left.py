"""What the placed-masks review left (card yp3e): a mask's share is of the SURFACE, not of its texels (a part laid
denser no longer leans the share); a picture's alpha is its mask only when the picture really uses it (one half-clear
pixel was read as an alpha mask); each texel's patch of surface (rbx_wear.texel_area)."""

import os
import subprocess
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_mask as M  # noqa: E402
import rbx_wear as W  # noqa: E402


class Share(unittest.TestCase):
    def test_by_surface(self):
        v = np.array([1.0, 1.0, 1.0, 0.0])           # three texels on, one off ...
        area = np.array([1.0, 1.0, 1.0, 9.0])        # ... the one off covers as much surface as nine of them
        self.assertEqual(M.said(v)["on"], 0.75)       # (by texels)
        self.assertEqual(M.said(v, area)["on"], 0.25)  # (by surface)
        self.assertEqual(M.said(v, area)["mean"], 0.25)


class Picture(unittest.TestCase):
    def test_one_half_clear_pixel_is_not_an_alpha_mask(self):
        px = np.ones((20, 20, 4))
        px[..., :3] = 0.0
        px[:10, :, :3] = 1.0                           # (light top half: the mask by lightness)
        px[0, 0, 3] = 0.5                              # (one stray half-clear pixel)
        v = M.picture_values(px)
        self.assertEqual(float(v[5, 5]), 1.0)
        self.assertEqual(float(v[15, 5]), 0.0)

    def test_a_real_alpha_is_the_mask(self):
        px = np.ones((20, 20, 4))
        px[10:, :, 3] = 0.0                            # (half the picture clear)
        v = M.picture_values(px)
        self.assertEqual(float(v[5, 5]), 1.0)
        self.assertEqual(float(v[15, 5]), 0.0)


class Area(unittest.TestCase):
    def test_a_texels_patch_of_surface(self):
        n = 32
        ys, xs = np.mgrid[0:n, 0:n].astype(float)
        p = np.stack([xs * 2.0, ys * 3.0, np.zeros_like(xs)], axis=2)   # (2 mm by 3 mm a texel)
        inside = np.ones((n, n), bool)
        inside[:, 20:] = False
        a = W.texel_area(p, inside)
        self.assertTrue(np.allclose(a[inside], 6.0))
        self.assertTrue((a[~inside] == 0).all())


BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Trimmed(unittest.TestCase):
    def test_a_mask_on_a_trimmed_part_stops_the_build(self):
        here = os.path.join(ROOT, "kit", "selftest", "blender")
        if not os.path.isfile(os.path.join(ROOT, "build", "models", "_selftest_trim_sheet.manifest.json")):
            subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(here, "build_trim_sheet.py")],
                           cwd=ROOT, capture_output=True, timeout=1200)
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                              os.path.join(here, "build_mask_trimmed.py")], cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=1200)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn('mask "stripe": Panel is laid into a trim sheet', out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
