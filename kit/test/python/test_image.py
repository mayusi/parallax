"""The quality judge's image measurements (kit/blender/rbx_image.py): see-through slits and visible texture. Each one
is checked against pictures whose answer is known: slats that do not meet, a window with square corners, wood-like
stripes, flat paint with render noise, dark seams that are geometry (never texture)."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_image as I  # noqa: E402

TEX_SEEN = 0.004  # (rbx_quality.TEX_SEEN: rbx_quality imports bpy, the value is mirrored here and checked below)


def slats(size, gap):
    """a lid of 6 slats seen from above, `gap` px between them, inside a frame (the gaps are enclosed holes)"""
    m = np.zeros((size, size), bool)
    m[size // 8: -size // 8, size // 8: -size // 8] = True
    inner_lo, inner_hi = size // 8 + size // 16, size - size // 8 - size // 16
    step = (inner_hi - inner_lo) // 6
    for k in range(1, 6):
        y = inner_lo + k * step
        m[y: y + gap, inner_lo:inner_hi] = False
    return m


class TestSeeThrough(unittest.TestCase):
    def test_slits_between_slats(self):
        self.assertGreater(I.see_through(slats(1024, 4)), 0.003)  # 1 px at the 256 px measuring width

    def test_window_with_square_corners_is_not_a_slit(self):
        m = np.zeros((1024, 1024), bool)
        m[100:900, 100:900] = True
        m[300:700, 250:750] = False  # a real window
        self.assertLess(I.see_through(m), 0.0005)

    def test_ladder_openings_are_not_slits(self):
        m = np.zeros((1024, 512), bool)
        m[40:1000, 60:110] = True
        m[40:1000, 400:450] = True
        for y in range(120, 1000, 180):
            m[y: y + 30, 60:450] = True
        self.assertLess(I.see_through(m), 0.0005)

    def test_open_to_the_outside_is_not_see_through(self):
        m = np.zeros((512, 512), bool)
        m[100:400, 100:400] = True
        m[240:244, 100:300] = False  # a slot open at the left edge of the part: background, not a hole
        self.assertEqual(I.see_through(m), 0.0)

    def test_one_pixel_slit_is_not_lost_by_resampling(self):
        """a 1 px slit in a 1024 px render: sampling every 4th pixel would keep ~1 row in 4 of it"""
        self.assertGreater(I.see_through(slats(1024, 1)), 0.003)

    def test_a_hairline_counts_its_true_area(self):
        """a 1 px slit in a 1024 px view is measured as 1 px of light, not as the 4 px block it falls in when the view
        is searched at 256 px (that read a hairline at 4x its share — past the threshold on its own)"""
        m = slats(1024, 1)
        true_share = float((~m[128:-128, 128:-128]).sum()) / float(m.sum())
        self.assertAlmostEqual(I.see_through(m), true_share, delta=0.25 * true_share)

    def test_same_shape_any_orientation(self):
        """the slit width is measured against the view's longer side: a tall view equals the same view turned"""
        m = np.zeros((1024, 420), bool)  # a tall lid: a frame with 6 horizontal slits, nothing behind them
        m[60:964, 40:380] = True
        for k in range(1, 7):
            m[60 + k * 128: 64 + k * 128, 70:350] = False
        a, b = I.see_through(m), I.see_through(np.ascontiguousarray(m.T))
        self.assertGreater(a, 0.003)
        self.assertAlmostEqual(a, b, delta=0.2 * max(a, b))

    def test_same_shape_any_resolution(self):
        a, b = I.see_through(slats(512, 2)), I.see_through(slats(2048, 8))
        self.assertGreater(a, 0.003)
        self.assertAlmostEqual(a, b, delta=0.35 * max(a, b))


def surface(h=400, w=600, seed=0, noise=0.002):
    rng = np.random.default_rng(seed)
    lum = 0.5 + noise * rng.standard_normal((h, w))
    mask = np.zeros((h, w), bool)
    mask[20:-20, 20:-20] = True
    return lum, mask


def median_seen(lum, mask, crease=None):
    edge, inner = I.creases(np.full(lum.shape, 0.6), mask)  # a flat cavity render: no creases
    if crease is not None:
        edge = edge | (crease & inner)
    c, ok = I.visible_texture(lum, inner, edge)
    return float(np.median(c[ok]))


class TestVisibleTexture(unittest.TestCase):
    def test_flat_paint_with_render_noise_is_blank(self):
        lum, mask = surface()
        self.assertLess(median_seen(lum, mask), TEX_SEEN / 2)

    def test_wood_like_stripes_are_seen(self):
        lum, mask = surface()
        y = np.arange(lum.shape[0])[:, None]
        lum = lum + 0.5 * 0.03 * np.sin(2 * np.pi * y / 28)  # soft grain bands: 3% contrast, 28 px period
        self.assertGreater(median_seen(lum, mask), TEX_SEEN)

    def test_dark_wood_counts_like_light_wood(self):
        lum, mask = surface(noise=0.0)
        y = np.arange(lum.shape[0])[:, None]
        light = median_seen(0.6 * (1 + 0.03 * np.sin(2 * np.pi * y / 28)) + 0 * lum, mask)
        dark = median_seen(0.15 * (1 + 0.03 * np.sin(2 * np.pi * y / 28)) + 0 * lum, mask)
        self.assertAlmostEqual(light, dark, delta=0.15 * light)

    def test_seams_are_geometry_not_texture(self):
        """dark gaps between flat boards are creases: they must not make the boards count as textured"""
        lum, mask = surface()
        seams = np.zeros_like(mask)
        for y in range(60, 380, 80):
            lum[y: y + 4, :] = 0.08
            seams[y - 1: y + 5, :] = True
        self.assertLess(median_seen(lum, mask, seams), TEX_SEEN / 2)

    def test_pixel_noise_counts_far_less_than_grain(self):
        """1-px noise (bake / render noise a player cannot resolve in game) is damped by the band-pass, not removed:
        at the SAME strength (RMS) as soft grain it must measure several times lower"""
        noisy, mask = surface(noise=0.02)
        flat, _ = surface(noise=0.0)
        y = np.arange(flat.shape[0])[:, None]
        grain = flat + 0.02 * np.sqrt(2) * np.sin(2 * np.pi * y / 28)  # RMS 0.02 like the noise
        self.assertGreater(median_seen(grain, mask), 3 * median_seen(noisy, mask))

    def test_creases_skip_the_outline(self):
        mask = np.zeros((100, 100), bool)
        mask[20:80, 20:80] = True
        gray = np.where(mask, 0.6, 0.0)
        edge, inner = I.creases(gray, mask)
        self.assertEqual(int(edge.sum()), 0)
        self.assertEqual(int(inner.sum()), 54 * 54)

    def test_threshold_mirrors_the_judge(self):
        with open(os.path.join(os.path.dirname(I.__file__), "rbx_quality.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn(f"TEX_SEEN = {TEX_SEEN}", src)


if __name__ == "__main__":
    unittest.main()
