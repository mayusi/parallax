"""rbx_wear: a dark finish's wear is visible (edges toward a satin grey, flats' roughness broken up) and never bare
metal, never darker, never outside 0.05..1 roughness; zero amounts change nothing. Colours are sRGB-ENCODED, as the
bake's colour image holds them (a black finish: ~0.18); the wear tones are linear constants, encoded before use."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_wear as W  # noqa: E402


def _flat(v, n=8, c=3):
    return np.full((n, n, c), v, dtype=np.float32)


def _fbm_as_it_was(n, rng, octaves=4, cells=6):
    """the layering's noise as rbx._fbm computed it until 2026-11-13 (four n x n gathers an octave): the reference"""
    out = np.zeros((n, n), dtype=np.float32)
    amp, total = 1.0, 0.0
    for _ in range(octaves):
        grid = rng.random((cells + 1, cells + 1)).astype(np.float32)
        t = np.linspace(0, cells, n, endpoint=False, dtype=np.float32)
        i = t.astype(np.int32)
        f = t - i
        f = f * f * (3 - 2 * f)
        a = grid[i][:, i]
        b = grid[i][:, i + 1]
        c = grid[i + 1][:, i]
        d = grid[i + 1][:, i + 1]
        fx, fy = f[None, :], f[:, None]
        out += amp * ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy)
        total += amp
        amp *= 0.5
        cells *= 2
    return out / total


def _box_blur_as_it_was(a, r):
    r = int(r)
    if r < 1:
        return a.astype(np.float32)
    out = a.astype(np.float32)
    for axis in (0, 1):
        pad = [(r + 1, r) if k == axis else (0, 0) for k in range(2)]
        c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis)
        n = out.shape[axis]
        out = (np.take(c, range(2 * r + 1, 2 * r + 1 + n), axis=axis)
               - np.take(c, range(0, n), axis=axis)) / (2 * r + 1)
    return out


class SameBits(unittest.TestCase):
    """the layering's helpers made faster (2026-11-13) give the SAME BITS as the forms they replaced: a baked map
    must not move by a level because a build got quicker"""

    def test_the_noise(self):
        for n in (64, 257, 512):
            for kw in ({}, {"octaves": 3, "cells": 28}, {"octaves": 3, "cells": 14}, {"octaves": 2, "cells": 5}):
                was = _fbm_as_it_was(n, np.random.default_rng(7), **kw)
                now = W.fbm(n, np.random.default_rng(7), **kw)
                self.assertEqual(now.dtype, np.float32)
                self.assertTrue(np.array_equal(was, now), (n, kw))

    def test_the_noise_draws_the_same_random_numbers(self):
        a, b = np.random.default_rng(3), np.random.default_rng(3)
        _fbm_as_it_was(96, a)
        W.fbm(96, b)
        self.assertEqual(a.random(), b.random())          # (the next field of the layering starts where it did)

    def test_the_box_blur(self):
        rng = np.random.default_rng(5)
        for shape in ((40, 40), (33, 70), (70, 33)):
            a = rng.random(shape).astype(np.float32)
            for r in (0, 1, 3, 8):
                self.assertTrue(np.array_equal(_box_blur_as_it_was(a, r), W.box_blur(a, r)), (shape, r))

    def test_one_channel_of_a_grey_pass_three_of_a_coloured_one(self):
        rng = np.random.default_rng(6)
        g = rng.random((8, 8, 1)).astype(np.float32)
        grey = np.concatenate([g, g, g, np.ones_like(g)], axis=-1)
        one = W.one_channel(grey)
        self.assertEqual(one.shape, (8, 8, 1))
        self.assertTrue(np.array_equal(one, g))
        one[0, 0, 0] = 9.0
        self.assertNotEqual(float(grey[0, 0, 0]), 9.0)       # a copy: the pass is not written through it
        col = rng.random((8, 8, 4)).astype(np.float32)
        three = W.one_channel(col)
        self.assertEqual(three.shape, (8, 8, 3))
        self.assertTrue(np.array_equal(three, col[..., :3]))
        self.assertTrue(three.flags["C_CONTIGUOUS"])


class Mottle(unittest.TestCase):
    """a.material(wear=) on the baked passes: what its colour ramp and map range gave in the material's nodes"""

    def passes(self, n=6, c=0.5, r=0.4):
        return np.full((n, 3), c, np.float32), np.full((n, 3), r, np.float32)

    def test_no_wear_changes_nothing(self):
        color, rough = self.passes()
        fac = np.linspace(0, 1, 6).astype(np.float32)
        c2, r2 = W.mottle(color, rough, fac, np.zeros(6), np.zeros(6))
        self.assertTrue(np.allclose(c2, color, atol=1e-6))
        self.assertTrue(np.allclose(r2, rough, atol=1e-6))

    def test_low_noise_darkens_in_linear_light_high_noise_does_not(self):
        color, rough = self.passes()
        fac = np.array([0.0, 0.2, 0.35, 0.55, 0.75, 1.0], np.float32)
        c2, _r = W.mottle(color, rough, fac, np.ones(6), np.zeros(6))
        lin, lin0 = W.linear_of(c2)[:, 0], float(W.linear_of(np.float32(0.5)))
        keep = [1 - W.WEAR_DARK, 1 - W.WEAR_DARK, 1 - W.WEAR_DARK, 1 - W.WEAR_DARK * 0.5, 1.0, 1.0]
        self.assertTrue(np.allclose(lin, [lin0 * k for k in keep], atol=1e-5), lin)

    def test_it_is_the_ramp_the_nodes_had(self):
        # the nodes: a colour ramp from base x (1 - 0.55 wear) at 0.35 to base at 0.75, mixed in linear light
        base, wear = np.array([0.2, 0.35, 0.25], np.float32), 0.6
        fac = np.linspace(0, 1, 41).astype(np.float32)
        t = np.clip((fac - 0.35) / 0.4, 0, 1)[:, None]
        ramp = base * (1 - 0.55 * wear) * (1 - t) + base * t
        color = np.repeat(W.srgb_of(base)[None, :], 41, axis=0)
        c2, _r = W.mottle(color, np.zeros((41, 1), np.float32), fac, np.full(41, wear), np.zeros(41))
        self.assertTrue(np.allclose(W.linear_of(c2), ramp, atol=2e-5))

    def test_the_roughness_rises_where_the_noise_is_low_never_past_one(self):
        self.assertAlmostEqual(W.mottle_rougher(0.4, 1.0), 0.25)
        self.assertAlmostEqual(W.mottle_rougher(0.9, 1.0), 0.1)            # (0.9 + 0.25 would be past 1)
        self.assertEqual(W.mottle_rougher(0.4, 0.0), 0.0)
        color, rough = self.passes(n=3, r=0.9)
        _c, r2 = W.mottle(color, rough, np.array([0.0, 0.5, 1.0], np.float32), np.ones(3),
                          np.full(3, W.mottle_rougher(0.9, 1.0), np.float32))
        self.assertTrue(np.allclose(r2[:, 0], [1.0, 0.95, 0.9], atol=1e-6))

    def test_a_colour_over_one_is_darkened_before_it_is_clipped(self):
        # a scan lifts a bright colour to 1.6 (linear): the byte pass holds 1.0 and, beside it, (1.6 - 1) / WEAR_OVER.
        # The nodes gave min(1, keep x 1.6): at keep 0.56 that is 0.896 - never keep x 1.0 = 0.56
        color = np.ones((2, 3), np.float32)                                  # the pass, stopped at 1
        over = np.repeat(W.srgb_of(np.float32([[0.6 / W.WEAR_OVER]])), 3, axis=1).repeat(2, axis=0)
        fac = np.array([0.0, 1.0], np.float32)
        wear = np.full(2, 0.8, np.float32)
        c2, _r = W.mottle(color, np.zeros((2, 1), np.float32), fac, wear, np.zeros(2), over=over)
        lin = W.linear_of(c2)[:, 0]
        self.assertAlmostEqual(float(lin[0]), 1.6 * (1 - W.WEAR_DARK * 0.8), delta=0.01)   # 0.896
        self.assertAlmostEqual(float(lin[1]), 1.0, delta=1e-4)                             # untouched: clipped at 1
        c3, _r = W.mottle(color, np.zeros((2, 1), np.float32), fac, wear, np.zeros(2))     # (without it: too dark)
        self.assertLess(float(W.linear_of(c3)[0, 0]), 0.6)

    def test_the_srgb_curve_both_ways(self):
        v = np.array([0.0, 0.001, 0.0031308, 0.02, 0.18, 0.5, 1.0], np.float32)
        self.assertTrue(np.allclose(W.linear_of(W.srgb_of(v)), v, atol=1e-6))
        self.assertAlmostEqual(float(W.srgb_of(np.float32(0.18))), W.to_srgb(0.18), places=6)


class Burnish(unittest.TestCase):
    def test_black_edge_reads(self):
        color, rough = W.burnish(_flat(0.04), _flat(0.26, c=1), _flat(1.0, c=1))
        self.assertGreater(float(color.mean()), 0.3)                    # visible: from 0.04 toward the worn grey
        self.assertLess(float(color.mean()), W.to_srgb(W.BURNISH_TONE))  # never past it: no bare steel
        self.assertAlmostEqual(float(rough.mean()), 0.05, places=5)  # polished, clamped

    def test_light_surface_keeps_its_colour(self):
        color, _ = W.burnish(_flat(0.6), _flat(0.5, c=1), _flat(1.0, c=1))
        self.assertTrue(np.allclose(color, 0.6))               # only ever lighter: a light finish is not darkened

    def test_a_stored_black_finish_is_lifted(self):
        # (the bake's colour image holds sRGB: a 0.028 linear black slide is 0.18 there. Compared with the LINEAR tone
        #  0.16 it was already "lighter" — nothing burnished, on every dark finish, until 2026-10-10)
        black = W.to_srgb(0.028)
        color, _ = W.burnish(_flat(black), _flat(0.3, c=1), _flat(1.0, c=1))
        self.assertGreater(float(color.mean()), black + 0.15)

    def test_no_rub_no_change(self):
        c0, r0 = _flat(0.04), _flat(0.4, c=1)
        color, rough = W.burnish(c0, r0, _flat(0.0, c=1))
        self.assertTrue(np.allclose(color, c0) and np.allclose(rough, r0))


class Smudge(unittest.TestCase):
    def test_breaks_up_roughness_on_flats(self):
        blobs = np.linspace(0, 1, 64, dtype=np.float32).reshape(8, 8, 1)
        color, rough = W.smudge(_flat(0.04), _flat(0.3, c=1), blobs, _flat(1.0, c=1), _flat(1.0, c=1))
        spread = float(np.percentile(rough, 90) - np.percentile(rough, 10))
        self.assertGreater(spread, 0.15)                       # a visible breakup, not a flat value
        self.assertGreaterEqual(float(color.min()), 0.04 - 1e-6)  # never darker

    def test_edges_and_zero_amount_untouched(self):
        blobs = np.random.default_rng(1).random((8, 8, 1)).astype(np.float32)
        c0, r0 = _flat(0.04), _flat(0.3, c=1)
        for flat, amount in ((0.0, 1.0), (1.0, 0.0)):
            color, rough = W.smudge(c0, r0, blobs, _flat(flat, c=1), _flat(amount, c=1))
            self.assertTrue(np.allclose(color, c0) and np.allclose(rough, r0))


class Rub(unittest.TestCase):
    def test_worn_flat_reads_lighter_and_smoother(self):
        black = W.to_srgb(0.028)
        c, r = W.rub(_flat(black), _flat(0.6), _flat(1.0, c=1))
        self.assertGreater(float(c.mean()), black + 0.1)              # (a black flat worn to a satin grey, seen)
        self.assertLess(float(c.max()), W.to_srgb(W.RUB_TONE) + 1e-6)  # (never past the worn tone: not bare metal)
        self.assertLess(float(r.mean()), 0.6)

    def test_light_surface_and_zero_amount_unchanged(self):
        c, r = W.rub(_flat(0.5), _flat(0.4), _flat(1.0, c=1))
        self.assertTrue(np.allclose(c, 0.5))                 # (only ever lighter)
        c0, r0 = W.rub(_flat(0.03), _flat(0.6), _flat(0.0, c=1))
        self.assertTrue(np.allclose(c0, 0.03) and np.allclose(r0, 0.6))

    def test_patches_are_patchy(self):
        n = np.linspace(0.0, 1.0, 101, dtype=np.float32)[:, None]
        p = W.patches(n)
        self.assertEqual(float(p[:40].max()), 0.0)          # (most of the surface untouched)
        self.assertEqual(float(p[80:].min()), 1.0)
        self.assertTrue(np.all(np.diff(p[:, 0]) >= -1e-7))   # (smooth, monotone between)


class EdgeBand(unittest.TestCase):
    def _line(self):
        c = np.zeros((128, 128), dtype=np.float32)
        c[:, 63:65] = 1.0   # an edge two px wide
        return c

    def test_band_width_follows_the_density(self):
        thin = W.edge_band(self._line(), px_per_mm=2.0, width_mm=1.0)
        wide = W.edge_band(self._line(), px_per_mm=10.0, width_mm=1.0)
        self.assertGreater(int((wide[64] > 0.1).sum()), 3 * int((thin[64] > 0.1).sum()) - 4)
        self.assertAlmostEqual(float(wide.max()), 1.0, places=4)
        self.assertEqual(float(wide[64, 0]), 0.0)   # far from the edge: no rubbing

    def test_band_width_follows_the_material(self):
        # (a.material(burnish_mm=): a holstered slide's 2.5 mm band reaches well past the default 1 mm one)
        one = W.edge_band(self._line(), px_per_mm=4.0, width_mm=1.0)
        wide = W.edge_band(self._line(), px_per_mm=4.0, width_mm=2.5)
        self.assertGreater(int((wide[64] > 0.1).sum()), 2 * int((one[64] > 0.1).sum()) - 4)
        self.assertEqual(float(wide[64, 0]), 0.0)

    def test_no_density_falls_back(self):
        band = W.edge_band(self._line())
        self.assertTrue(0 < int((band[64] > 0.1).sum()) < 20)

    def test_flat_map_stays_flat(self):
        self.assertEqual(float(W.edge_band(np.zeros((32, 32), dtype=np.float32), 8.0).max()), 0.0)


if __name__ == "__main__":
    unittest.main()


class Vary(unittest.TestCase):
    """a.material(vary=): a material's colour varies about its own mean — never a flat fill, never a shifted average"""

    def setUp(self):
        rng = np.random.default_rng(3)
        self.lo = rng.uniform(0.3, 0.7, size=(64, 64, 1)).astype(np.float32)
        self.mid = rng.uniform(0.2, 0.8, size=(64, 64, 1)).astype(np.float32)
        self.col = np.full((64, 64, 3), 0.5, dtype=np.float32)

    def test_no_amount_no_change(self):
        out = W.vary(self.col, self.lo, self.mid, np.zeros((64, 64, 1)))
        self.assertTrue(np.array_equal(out, self.col))

    def test_it_varies_about_the_same_mean(self):
        out = W.vary(self.col, self.lo, self.mid, np.ones((64, 64, 1)))
        self.assertAlmostEqual(float(out[..., 1].mean()), 0.5, delta=0.01)   # (green: value only, no hue drift)
        self.assertGreater(float(out[..., 1].std()), 0.02)
        self.assertLessEqual(float(np.abs(out - 0.5).max()), 0.5 * (W.VARY_LO + W.VARY_MID + W.VARY_HUE) + 1e-6)
        self.assertGreater(float(np.abs(out[..., 0] - out[..., 2]).max()), 0.001)   # (a warm / cool drift)

    def test_more_amount_more_spread_and_only_where_asked(self):
        half = np.zeros((64, 64, 1))
        half[:, :32] = 1.0
        out = W.vary(self.col, self.lo, self.mid, half)
        self.assertTrue(np.array_equal(out[:, 32:], self.col[:, 32:]))   # (the other material untouched)
        weak = W.vary(self.col, self.lo, self.mid, np.full((64, 64, 1), 0.3))
        strong = W.vary(self.col, self.lo, self.mid, np.ones((64, 64, 1)))
        self.assertLess(float(weak[..., 1].std()), float(strong[..., 1].std()))
