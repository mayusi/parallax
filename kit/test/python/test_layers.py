"""rbx_layers: a material's own layers - a typed layer is checked where it is written; a layer covers the share that
was asked of the texels its source allows, the highest-ranked first, on its own material only; a layer laid through
a mask of 0 changes nothing; the named layers' tones are physically sane."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_layers as L  # noqa: E402
import rbx_wear as W  # noqa: E402

N = 96


def maps(seed=1):
    """the layering's arrays for a made-up map: a convex ridge, a concave seam, an occluded corner, an up ramp"""
    z = np.zeros((N, N, 1), np.float32)
    m = {k: z.copy() for k in ("convex", "concave", "reach", "up", "low", "chipped")}
    m["occ"] = np.ones((N, N, 1), np.float32)
    m["exposed"] = np.ones((N, N, 1), np.float32)
    m["convex"][:, 10:13] = 1.0
    m["reach"][:, 8:15] = 0.8
    m["concave"][:, 40:44] = 1.0
    m["occ"][70:, 70:] = 0.3
    m["exposed"][70:, 70:] = 0.0
    m["up"][:48] = 1.0
    m["up"][48:56] = np.linspace(1, 0, 8, dtype=np.float32)[:, None, None]
    m["low"][:] = np.linspace(1, 0, N, dtype=np.float32)[:, None, None]
    m["chipped"][20:30, 20:30] = 1.0
    return m


def noise(seed=3):
    return W.fbm(N, np.random.default_rng(seed))


class Written(unittest.TestCase):
    def test_a_named_layer_brings_its_own_tone_and_place(self):
        d = L.layer("rust")
        self.assertEqual(d["color"], L.KINDS["rust"]["color"])
        self.assertEqual((d["where"], d["rough"], d["metal"], d["opacity"]), ("cavities", 0.78, 0.0, 1.0))
        self.assertEqual(d["thick_mm"], 0.4)                # (it lies that thick: relief)
        self.assertEqual(L.layer("soot")["thick_mm"], 0.0)  # a film
        self.assertEqual(L.layer("rust", thick_mm=0)["thick_mm"], 0.0)   # ... or a stain, when asked
        self.assertEqual(sorted(d), sorted(L.KEYS))

    def test_what_is_given_wins_over_the_named_layers_own(self):
        d = L.layer("rust", where="chipped", amount=0.8, opacity=0.5, rough=0.6, color=(0.3, 0.1, 0.05))
        self.assertEqual((d["where"], d["amount"], d["opacity"], d["rough"], d["color"]),
                         ("chipped", 0.8, 0.5, 0.6, (0.3, 0.1, 0.05)))

    def test_a_layer_of_ones_own_needs_its_colour(self):
        with self.assertRaises(ValueError) as e:
            L.layer("verdigris")
        self.assertIn("color=", str(e.exception))
        d = L.layer("verdigris", color=(0.1, 0.4, 0.35), where="cavities")
        self.assertIsNone(d["rough"])                      # (not given: the surface's own roughness stays)
        self.assertIsNone(d["metal"])
        self.assertEqual(d["thick_mm"], 0.0)               # (a layer of one's own is a stain unless given)
        self.assertEqual(L.layer("verdigris", color=(0.1, 0.4, 0.35), thick_mm=0.2)["thick_mm"], 0.2)

    def test_what_is_not_allowed_is_said_at_once(self):
        for bad in (dict(where="top"), dict(amount=1.5), dict(opacity=-0.1), dict(breakup=2), dict(grain="streaks"),
                    dict(color=(1.2, 0, 0)), dict(color=(0.1, 0.2)), dict(rough=1.4), dict(metal=-1),
                    dict(rough=0.0), dict(amount=None), dict(amount="much"), dict(color=0.3),
                    dict(thick_mm=-1), dict(thick_mm=80), dict(thick_mm="thin")):
            with self.assertRaises(ValueError, msg=bad):
                L.layer("rust", **bad)
        for bad in ("", None, 3, {"kind": "rust"}):
            with self.assertRaises(ValueError, msg=bad):
                L.layer(bad)

    def test_resolve_takes_layers_dicts_and_names(self):
        got = L.resolve([L.layer("rust", amount=0.4), {"kind": "soot", "where": "low"}, "moss"], "paint")
        self.assertEqual([d["kind"] for d in got], ["rust", "soot", "moss"])
        self.assertEqual(got[1]["where"], "low")
        self.assertTrue(all(sorted(d) == sorted(L.KEYS) for d in got))
        self.assertEqual(L.resolve(None), ())
        self.assertEqual(L.resolve([]), ())
        self.assertEqual([d["kind"] for d in L.resolve((L.layer("mud"), "soot"))], ["mud", "soot"])   # (a tuple too)

    def test_resolve_wants_a_list(self):
        for bad in ("rust", {"kind": "rust"}, 3, b"rust"):      # (a name alone was walked letter by letter)
            with self.assertRaises(ValueError) as e:
                L.resolve(bad, "frame")
            self.assertIn("LIST", str(e.exception))
            self.assertIn("frame", str(e.exception))

    def test_resolve_names_the_material_and_the_fault(self):
        for bad, word in (([{"kind": "rust", "strength": 1}], "strength"), ([7], "not a layer"),
                          ([{"where": "up"}], "not a layer"), ([{"kind": "rust", "where": "sideways"}], "sideways")):
            with self.assertRaises(ValueError) as e:
                L.resolve(bad, "frame")
            self.assertIn("frame", str(e.exception))
            self.assertIn(word, str(e.exception))

    def test_a_layer_is_plain_data_a_look_can_hold(self):
        import json

        d = L.layer("mud", amount=0.3)
        self.assertEqual(L.resolve([json.loads(json.dumps(d))])[0], d)

    def test_a_look_carries_its_layers(self):
        import rbx_looks

        real = dict(rbx_looks._all())
        rbx_looks._CACHE["looks"] = {**real, "_test_rusty": {"color": [0.2, 0.3, 0.2], "metal": 0.0, "rough": 0.6,
                                                             "layers": [{"kind": "rust", "amount": 0.2}, "soot"]}}
        try:
            kw = rbx_looks.look("_test_rusty")
            self.assertEqual([d["kind"] for d in L.resolve(kw["layers"], "frame")], ["rust", "soot"])
            over = rbx_looks.look("_test_rusty", layers=[L.layer("moss")])       # (any key overridden in look())
            self.assertEqual([d["kind"] for d in over["layers"]], ["moss"])
        finally:
            rbx_looks._CACHE["looks"] = real

    def test_the_helper_passes_its_sources_read(self):
        self.assertEqual(L.needs([L.layer("snow"), L.layer("mud"), L.layer("rust")]), ["lowmask", "upmask"])
        self.assertEqual(L.needs([L.layer("rust"), L.layer("soot")]), [])
        self.assertEqual(L.needs(()), [])

    def test_the_named_tones_are_real_surfaces(self):
        # (none is a metal; every colour inside what a non-metal reflects: 0.02 .. 0.9 linear - snow the lightest)
        for k, v in L.KINDS.items():
            self.assertEqual(v["metal"], 0.0, k)
            self.assertTrue(all(0.01 <= c <= 0.9 for c in v["color"]), k)
            self.assertTrue(0.3 <= v["rough"] <= 1.0, k)
            self.assertIn(v["where"], L.SOURCES, k)
            self.assertTrue(v["source"], k)
            self.assertTrue(0.0 <= v["thick_mm"] <= 20.0, k)
            self.assertTrue(v["thick_source"], k)          # (an estimate, and said to be one)
        r, g, b = L.KINDS["rust"]["color"]
        self.assertTrue(r > 2 * g > 2 * b)                 # rust is red-brown
        r, g, b = L.KINDS["moss"]["color"]
        self.assertTrue(g > r > b)                         # moss is green

    def test_a_seed_is_its_layers_own_wherever_it_stands_in_the_list(self):
        a, b, c, d = (L.layer("rust", where="chipped"), L.layer("rust"), L.layer("soot", where="low"),
                      L.layer("rust"))
        full = L.seeds("o", "paint", [a, b, c, d])
        self.assertEqual(full, L.seeds("o", "paint", [a, b, c, d]))               # the same every time
        self.assertEqual(len(set(full)), 4)                                       # two alike: each its own
        self.assertEqual(L.seeds("o", "paint", [b, c]), [full[1], full[2]])       # the FIRST one taken out
        self.assertEqual(L.seeds("o", "paint", [c, a, b]), [full[2], full[0], full[1]])   # moved
        self.assertEqual(L.seeds("o", "paint", [L.layer("moss"), a, b, c])[1:], full[:3])  # one put in front
        self.assertNotEqual(L.seeds("o", "steel", [a]), L.seeds("o", "paint", [a]))
        self.assertNotEqual(L.seeds("p", "paint", [a]), L.seeds("o", "paint", [a]))


class Noise(unittest.TestCase):
    def test_a_grains_noise_is_a_field_0_to_1_the_same_for_the_same_seed(self):
        for g in L.GRAINS:
            a = L.noise(64, np.random.default_rng(4), g)
            b = L.noise(64, np.random.default_rng(4), g)
            self.assertEqual((a.shape, a.dtype), ((64, 64), np.float32))
            self.assertTrue(np.array_equal(a, b))
            self.assertTrue(0.0 <= float(a.min()) and float(a.max()) <= 1.0)
            self.assertAlmostEqual(sum(w for _o, _c, w in L.GRAINS[g]), 1.0, places=6)

    def test_fine_is_finer_than_patches(self):
        def contour(a):
            m = a > np.median(a)
            return int((m[1:] != m[:-1]).sum() + (m[:, 1:] != m[:, :-1]).sum())

        self.assertGreater(contour(L.noise(256, np.random.default_rng(4), "fine")),
                           1.3 * contour(L.noise(256, np.random.default_rng(4), "patches")))

    def test_patches_have_a_ragged_contour(self):
        # (the length of the 50% contour: patches with their fine field against the broad field alone)
        def contour(a):
            m = a > np.median(a)
            return int((m[1:] != m[:-1]).sum() + (m[:, 1:] != m[:, :-1]).sum())

        broad = W.fbm(256, np.random.default_rng(4), octaves=4, cells=6)
        self.assertGreater(contour(L.noise(256, np.random.default_rng(4), "patches")), 1.5 * contour(broad))


class Field(unittest.TestCase):
    def test_each_source_is_where_it_says(self):
        m = maps()
        self.assertTrue((L.field("all", m) == 1).all())
        e = L.field("edges", m)
        self.assertGreater(float(e[:, 8:15].min()), 0.5)
        self.assertEqual(float(e[:, 30:].max()), 0.0)
        c = L.field("cavities", m)
        self.assertEqual(float(c[:60, 40:44].min()), 1.0)             # the seam
        self.assertGreater(float(c[80, 80, 0]), 0.9)                  # the occluded corner
        self.assertEqual(float(c[5, 60, 0]), 0.0)                     # an open flat
        f = L.field("flats", m)
        self.assertEqual(float(f[5, 60, 0]), 1.0)
        self.assertEqual(float(f[5, 11, 0]), 0.0)                     # not on the ridge
        self.assertEqual(float(f[5, 41, 0]), 0.0)                     # not in the seam
        self.assertEqual(float(f[80, 80, 0]), 0.0)                    # not where nothing reaches
        for k in ("up", "low", "chipped"):
            self.assertTrue(np.array_equal(L.field(k, m), m[k]), k)

    def test_a_source_with_no_map_is_nowhere(self):
        m = maps()
        for k in ("up", "low", "chipped"):
            del m[k]
            self.assertEqual(float(L.field(k, m).max()), 0.0)

    def test_an_unknown_source_raises(self):
        with self.assertRaises(ValueError):
            L.field("sideways", maps())


class Mask(unittest.TestCase):
    def cov(self, cols=slice(None)):
        c = np.zeros((N, N, 1), np.float32)
        c[:, cols] = 1.0
        return c

    def test_the_share_asked_of_the_material_is_covered(self):
        one = np.ones((N, N, 1), np.float32)
        for amount in (0.1, 0.25, 0.5, 0.8):
            m, f = L.mask(one, noise(), self.cov(), amount)
            self.assertEqual(f["eligible"], 1.0)
            self.assertAlmostEqual(f["covered"], amount, delta=0.03)        # (the soft edge: a few percent)
            self.assertAlmostEqual(float(m.mean()), amount, delta=0.03)

    def test_only_its_own_material(self):
        one = np.ones((N, N, 1), np.float32)
        m, f = L.mask(one, noise(), self.cov(slice(0, 30)), 0.5)
        self.assertEqual(float(m[:, 30:].max()), 0.0)
        self.assertAlmostEqual(f["covered"], 0.5, delta=0.04)               # ... half of ITS texels

    def test_only_where_the_source_is_and_the_strongest_first(self):
        src = L.field("cavities", maps())
        m, f = L.mask(src, noise(), self.cov(), 0.3, breakup=0.0)
        self.assertEqual(float(m[src <= L.ELIGIBLE].max()), 0.0)
        self.assertGreater(f["eligible"], 0.05)
        self.assertLess(f["eligible"], 0.2)
        covered, left = src[(m > 0.5)], src[(m < 0.01) & (src > L.ELIGIBLE)]
        self.assertGreater(covered.size, 0)
        self.assertGreater(left.size, 0)
        self.assertGreaterEqual(float(covered.min()), float(left.max()) - 0.08)   # ranked by the source first

    def test_a_flat_source_with_no_breakup_still_covers_the_share(self):
        # (every texel the same: the noise has the last word - never a half-strength film over all of it)
        one = np.ones((N, N, 1), np.float32)
        m, f = L.mask(one, noise(), self.cov(), 0.3, breakup=0.0)
        self.assertAlmostEqual(f["covered"], 0.3, delta=0.04)
        self.assertGreater(float((m > 0.95).mean()), 0.2)
        self.assertGreater(float((m < 0.05).mean()), 0.6)

    def test_a_faint_source_gives_less_room_and_the_share_is_of_the_room(self):
        # a ramp 1 .. 0: where the source is under FADE a texel takes less; `amount` is a share of that room
        src = np.repeat(np.linspace(1, 0, N, dtype=np.float32)[:, None, None], N, axis=1)
        full, f1 = L.mask(src, noise(), self.cov(), 1.0)
        row = int(np.argmin(np.abs(src[:, 0, 0] - 0.1)))
        self.assertAlmostEqual(float(full[row, 0, 0]), float(src[row, 0, 0]) / L.FADE, places=5)   # thinned
        self.assertEqual(float(full[2, 0, 0]), 1.0)
        self.assertAlmostEqual(f1["covered"], f1["eligible"], places=3)          # all of the room
        self.assertLess(f1["eligible"], 0.93)                                    # (less than every texel)
        for amount in (0.25, 0.5, 0.9):
            for b in (0.0, 0.5, 1.0):
                _m, f = L.mask(src, noise(), self.cov(), amount, breakup=b)
                self.assertAlmostEqual(f["covered"], amount * f["eligible"], delta=0.02, msg=(amount, b))
        weak = np.full((N, N, 1), 0.1, np.float32)                               # a faint source everywhere
        _m, f = L.mask(weak, noise(), self.cov(), 0.5)
        self.assertAlmostEqual(f["eligible"], 0.1 / L.FADE, places=3)
        self.assertAlmostEqual(f["covered"], 0.5 * f["eligible"], delta=0.02)

    def test_the_noise_is_not_made_when_there_is_nowhere_to_lie(self):
        def never():
            raise AssertionError("the noise was asked for")

        z = np.zeros((N, N, 1), np.float32)
        L.mask(z, never, self.cov(), 0.5)
        L.mask(np.ones_like(z), never, self.cov(), 0.0)
        L.mask(np.ones_like(z), never, self.cov(), 1.0)                          # (all of it: no ranking)
        m, f = L.mask(np.ones_like(z), lambda: noise(), self.cov(), 0.5)         # ... and made when needed
        self.assertAlmostEqual(f["covered"], 0.5, delta=0.03)

    def test_a_nan_in_a_source_is_no_source(self):
        src = np.ones((N, N, 1), np.float32)
        src[:10] = np.nan
        m, f = L.mask(src, noise(), self.cov(), 0.5)
        self.assertTrue(np.isfinite(m).all())
        self.assertEqual(float(m[:10].max()), 0.0)
        self.assertTrue(np.isfinite(f["covered"]) and np.isfinite(f["eligible"]))

    def test_all_of_it_and_none_of_it(self):
        src = L.field("up", maps())
        m, f = L.mask(src, noise(), self.cov(), 1.0)
        self.assertTrue((m[:48] == 1).all())                               # every texel that looks up
        self.assertEqual(float(m[60:].max()), 0.0)
        self.assertTrue(np.all(np.diff(m[48:56, 0, 0]) <= 0))              # thinning where the ramp ends
        m, f = L.mask(src, noise(), self.cov(), 0.0)
        self.assertEqual((float(m.max()), f["covered"]), (0.0, 0.0))
        self.assertGreater(f["eligible"], 0.4)                             # (it says where it COULD lie)

    def test_nowhere_to_lie(self):
        z = np.zeros((N, N, 1), np.float32)
        m, f = L.mask(z, noise(), self.cov(), 0.5)
        self.assertEqual((float(m.max()), f["eligible"], f["covered"]), (0.0, 0.0, 0.0))
        m, f = L.mask(np.ones_like(z), noise(), z, 0.5)                    # a material with no texel on this map
        self.assertEqual((float(m.max()), f["eligible"], f["covered"]), (0.0, 0.0, 0.0))

    def test_more_breakup_moves_it_off_the_sources_contours(self):
        src = L.field("low", maps())
        tight, _ = L.mask(src, noise(), self.cov(), 0.3, breakup=0.0)
        loose, _ = L.mask(src, noise(), self.cov(), 0.3, breakup=0.9)
        rows = lambda m: (m[..., 0] > 0.5).any(axis=1).sum()               # noqa: E731
        self.assertGreater(rows(loose), rows(tight))                       # patches reach further up

    def test_a_blended_edge_texel_takes_its_share(self):
        one = np.ones((N, N, 1), np.float32)
        c = self.cov()
        c[:, 50] = 0.7                                                     # an island's edge: 70% this material
        m, _ = L.mask(one, noise(), c, 1.0)
        self.assertAlmostEqual(float(m[5, 50, 0]), 0.7, places=5)

    def test_the_same_noise_the_same_mask(self):
        one = np.ones((N, N, 1), np.float32)
        a, _ = L.mask(one, noise(5), self.cov(), 0.4)
        b, _ = L.mask(one, noise(5), self.cov(), 0.4)
        self.assertTrue(np.array_equal(a, b))


class Apply(unittest.TestCase):
    def base(self):
        return (np.full((N, N, 3), 0.5, np.float32), np.full((N, N, 1), 0.4, np.float32),
                np.full((N, N, 1), 1.0, np.float32))

    def test_a_mask_of_zero_changes_nothing(self):
        c, r, mt = self.base()
        c2, r2, m2 = L.apply(c, r, mt, np.zeros((N, N, 1), np.float32), L.layer("rust"))
        self.assertTrue(np.array_equal(c, c2) and np.array_equal(r, r2) and np.array_equal(mt, m2))

    def test_a_full_mask_is_the_layer(self):
        c, r, mt = self.base()
        lay = L.layer("rust")
        c2, r2, m2 = L.apply(c, r, mt, np.ones((N, N, 1), np.float32), lay)
        self.assertTrue(np.allclose(c2[0, 0], [W.to_srgb(v) for v in lay["color"]], atol=1e-5))   # sRGB-encoded
        self.assertAlmostEqual(float(r2[0, 0, 0]), 0.78, places=5)
        self.assertAlmostEqual(float(m2[0, 0, 0]), 0.0, places=5)          # rust on steel is not metal
        self.assertEqual(c2.dtype, np.float32)

    def test_opacity_lets_the_surface_show(self):
        c, r, mt = self.base()
        lay = L.layer("soot", opacity=0.5)
        c2, r2, _ = L.apply(c, r, mt, np.ones((N, N, 1), np.float32), lay)
        want = 0.5 * 0.5 + 0.5 * W.to_srgb(0.04)
        self.assertAlmostEqual(float(c2[0, 0, 0]), want, places=5)
        self.assertAlmostEqual(float(r2[0, 0, 0]), 0.4 * 0.5 + 0.9 * 0.5, places=5)

    def test_a_layer_without_roughness_or_metal_leaves_them(self):
        c, r, mt = self.base()
        lay = L.layer("tint", color=(0.2, 0.2, 0.6))
        c2, r2, m2 = L.apply(c, r, mt, np.ones((N, N, 1), np.float32), lay)
        self.assertTrue(np.array_equal(r, r2) and np.array_equal(mt, m2))
        self.assertFalse(np.array_equal(c, c2))

    def test_three_channel_roughness_too(self):
        c, _, _ = self.base()
        r3 = np.full((N, N, 3), 0.4, np.float32)
        _, r2, _ = L.apply(c, r3, r3.copy(), np.ones((N, N, 1), np.float32), L.layer("rust"))
        self.assertEqual(r2.shape, (N, N, 3))

    def test_a_later_layer_covers_an_earlier_one(self):
        c, r, mt = self.base()
        full = np.ones((N, N, 1), np.float32)
        c1, r1, m1 = L.apply(c, r, mt, full, L.layer("rust"))
        c2, _, _ = L.apply(c1, r1, m1, full, L.layer("snow"))
        self.assertTrue(np.allclose(c2[0, 0], [W.to_srgb(v) for v in L.KINDS["snow"]["color"]], atol=1e-5))

    def test_a_layer_takes_the_shading_of_what_it_lies_on(self):
        c, r, mt = self.base()
        full = np.ones((N, N, 1), np.float32)
        shade = np.ones((N, N, 1), np.float32)
        shade[:, :10] = 0.5                                                  # a seam half in shadow
        lit, _, _ = L.apply(c, r, mt, full, L.layer("rust"))
        dark, _, _ = L.apply(c, r, mt, full, L.layer("rust"), shade)
        self.assertTrue(np.allclose(dark[:, :10], lit[:, :10] * 0.5, atol=1e-6))
        self.assertTrue(np.array_equal(dark[:, 10:], lit[:, 10:]))

    def test_the_roughness_never_goes_under_the_floor(self):
        c, r, mt = self.base()
        lay = dict(L.layer("film", color=(0.1, 0.1, 0.1), rough=0.05), rough=0.0)   # (a dict off a file, unchecked)
        _, r2, _ = L.apply(c, r, mt, np.ones((N, N, 1), np.float32), lay)
        self.assertAlmostEqual(float(r2.min()), L.ROUGH_MIN, places=6)

    def test_said_with_a_thickness(self):
        row = {"layer": "rust", "where": "chipped", "asked": 0.8, "eligible": 0.06, "covered": 0.05, "thick_mm": 0.4,
               "tilt_deg": 8.0, "bank_deg": 8.0, "top_deg": 3.0}
        self.assertEqual(L.said(row), "rust where chipped 80% -> 5%, 0.4 mm thick")
        self.assertEqual(L.said(dict(row, tilt_deg=0.6, bank_deg=0.6, top_deg=0.2)),
                         "rust where chipped 80% -> 5%, 0.4 mm thick (too flat to show: 0.6 deg)")
        self.assertEqual(L.said(dict(row, thick_mm=12.0, tilt_deg=63.4, bank_deg=63.4)),
                         "rust where chipped 80% -> 5%, 12 mm thick (too steep for this map: its bank is held at 63 deg)")
        self.assertEqual(L.said(dict(row, covered=0.0, eligible=0.0)), "rust where chipped 80% -> 0% (nowhere)")
        self.assertEqual(L.said(dict(row, thick_mm=0.0)), "rust where chipped 80% -> 5%")
        no_relief = {k: v for k, v in row.items() if k not in ("tilt_deg", "bank_deg", "top_deg")}
        self.assertEqual(L.said(no_relief), "rust where chipped 80% -> 5%")   # (no relief laid: no thickness said)

    def test_said(self):
        row = {"layer": "rust", "where": "chipped", "asked": 0.8, "eligible": 0.062, "covered": 0.0496}
        self.assertEqual(L.said(row), "rust where chipped 80% -> 5%")
        self.assertEqual(L.said(dict(row, where="cavities", asked=0.15, covered=0.03)), "rust in cavities 15% -> 3%")
        self.assertEqual(L.said(dict(row, eligible=0.0, covered=0.0)), "rust where chipped 80% -> 0% (nowhere)")
        self.assertEqual(L.said(dict(row, eligible=0.0, covered=0.0, not_laid="x")),
                         "rust where chipped 80% -> 0% (not laid)")
        self.assertEqual(sorted(L.PLACES), sorted(L.SOURCES))


class Relief(unittest.TestCase):
    def step(self):
        """a mask that is 0 on the left and 1 on the right, a ramp 8 texels wide between"""
        m = np.zeros((N, N, 1), np.float32)
        m[:, 52:] = 1.0
        m[:, 44:52, 0] = np.linspace(0, 1, 10, dtype=np.float32)[1:-1]
        return m

    def test_a_layers_height_is_its_mask_times_its_thickness_its_top_uneven(self):
        m = self.step()
        flat = L.height(m, 2.0, np.ones((N, N), np.float32))
        self.assertEqual(float(flat[0, 0]), 0.0)
        self.assertAlmostEqual(float(flat[0, 80]), 2.0, places=6)
        low = L.height(m, 2.0, np.zeros((N, N), np.float32))
        self.assertAlmostEqual(float(low[0, 80]), 2.0 * (1 - L.UNEVEN), places=6)      # the top's lowest
        top = L.top_noise(N, np.random.default_rng(2))
        self.assertEqual((top.shape, top.dtype), ((N, N), np.float32))
        self.assertTrue(np.array_equal(top, L.top_noise(N, np.random.default_rng(2))))

        def bumps(a):   # how often the field crosses its median along a row: more = finer
            m = a > np.median(a)
            return int((m[:, 1:] != m[:, :-1]).sum())

        thin = L.top_noise(256, np.random.default_rng(2), 0.4, 1.0)      # 0.8 mm bumps: held at TOP_PX texels
        thick = L.top_noise(256, np.random.default_rng(2), 6.0, 1.0)     # 12 mm bumps at 1 texel a mm
        dense = L.top_noise(256, np.random.default_rng(2), 6.0, 0.25)    # ... the same lumps on a coarser map
        self.assertGreater(bumps(thin), 2 * bumps(thick))                # a thick deposit's lumps are wide
        self.assertTrue(np.array_equal(dense, thin))                     # 12 mm x 0.25 px = 3 texels: the floor
        self.assertGreater(float(L.height(m, 2.0, top)[:, 60:].std()), 0.02)            # uneven

    def test_the_slope_is_millimetres_of_height_per_millimetre_of_surface(self):
        h = np.zeros((N, N), np.float32)                 # a height of its own: 1 mm over 9 texels
        h[:, 44:53] = np.linspace(0, 1, 11, dtype=np.float32)[1:-1]
        h[:, 53:] = 1.0
        gx, gy = L.slopes(h, 1.0)                        # 1 texel a millimetre
        self.assertAlmostEqual(float(gx[10, 48]), 0.1, places=4)
        self.assertEqual(float(np.abs(gy).max()), 0.0)   # the step runs along x only
        self.assertEqual(float(gx[10, 20]), 0.0)
        gx4, _ = L.slopes(h, 4.0)                        # four texels a millimetre: the same step is steeper
        self.assertAlmostEqual(float(gx4[10, 48]), 0.4, places=4)

    def test_the_hold_is_on_the_slopes_size_not_on_each_axis(self):
        gx, gy = np.full((4, 4), 9.0, np.float32), np.full((4, 4), 9.0, np.float32)     # a steep diagonal
        hx, hy = L.hold(gx, gy)
        self.assertAlmostEqual(float(np.hypot(hx, hy).max()), L.SLOPE_MAX, places=5)    # 63 degrees, not 70
        self.assertAlmostEqual(float(hx[0, 0]), float(hy[0, 0]), places=6)              # its direction kept
        sx, sy = L.hold(np.full((4, 4), 0.3, np.float32), np.full((4, 4), -0.1, np.float32))
        self.assertAlmostEqual(float(sx[0, 0]), 0.3, places=6)                          # a gentle one: untouched
        self.assertAlmostEqual(float(sy[0, 0]), -0.1, places=6)
        zx, zy = L.hold(np.zeros((4, 4), np.float32), np.zeros((4, 4), np.float32))
        self.assertTrue(np.isfinite(zx).all() and float(np.abs(zx).max()) == 0.0)

    def test_a_layer_that_reaches_its_materials_border_has_no_cliff_there(self):
        # 3 mm everywhere on the material's texels (columns 0..47); the next material's from 48 on
        own = np.zeros((N, N), bool)
        own[:, :48] = True
        h = np.where(own, 3.0, 0.0).astype(np.float32)
        cx, _ = L.slopes(h, 1.0)                                                        # (taken blind: a cliff)
        self.assertGreater(float(np.abs(cx).max()), 1.0)
        gx, gy = L.slopes(h, 1.0, own)
        self.assertEqual(float(np.abs(gx).max()), 0.0)                                  # carried over the border
        self.assertEqual(float(np.abs(gy).max()), 0.0)
        step = h.copy()                                                                 # a real bank inside it stays
        step[:, :20] = 0.0
        gx, _ = L.slopes(step, 1.0, own)
        self.assertGreater(float(gx[10, 19:21].max()), 1.0)
        self.assertEqual(float(np.abs(gx[:, 48:]).max()), 0.0)                          # none outside the material

    def test_the_normal_leans_away_from_the_rise(self):
        nrm = np.zeros((N, N, 4), np.float32)
        nrm[..., :3] = (0.5, 0.5, 1.0)                   # a flat tangent-space normal
        nrm[..., 3] = 1.0
        h = L.height(self.step(), 3.0, np.ones((N, N), np.float32))
        gx, gy = L.slopes(h, 1.0)
        out = L.raised(nrm, gx, gy)
        self.assertEqual(out.shape, (N, N, 3))
        self.assertTrue(np.allclose(out[10, 20], (0.5, 0.5, 1.0), atol=1e-5))           # off the layer: untouched
        self.assertTrue(np.allclose(out[10, 80], (0.5, 0.5, 1.0), atol=1e-5))           # on its flat top: too
        x = int(np.argmax(gx[10]))                       # the steepest of its bank
        n = out[10, x] * 2 - 1
        self.assertLess(float(n[0]), -0.2)               # height rises toward +x: the normal leans to -x
        self.assertAlmostEqual(float(n[1]), 0.0, places=5)
        self.assertAlmostEqual(float(np.linalg.norm(n)), 1.0, places=3)
        slope = float(gx[10, x])
        self.assertAlmostEqual(float(n[0]), -slope / (1 + slope * slope) ** 0.5, places=3)

    def test_a_deposit_has_a_bank_not_a_dome(self):
        # the colour's mask fades over 9 texels; the height is full where the mask passes BANK: a third of them
        m = self.step()
        h = L.height(m, 3.0, np.ones((N, N), np.float32))
        full = np.flatnonzero(h[10] > 3.0 - 1e-4)
        self.assertLess(float(m[10, full[0], 0]), L.BANK + 0.12)                        # full well inside the edge
        self.assertGreater(float(L.slopes(h, 1.0)[0].max()), 2.0 * 3.0 / 9.0)           # steeper than the fade
        self.assertTrue(np.all(np.diff(h[10]) >= -1e-6))                                # and never dips

    def test_a_thicker_layer_on_the_same_mask_tilts_more(self):
        m = self.step()
        one = np.ones((N, N), np.float32)
        a = L.tilts(*L.slopes(L.height(m, 0.4, one), 1.0), m)["bank"]
        b = L.tilts(*L.slopes(L.height(m, 3.0, one), 1.0), m)["bank"]
        self.assertGreater(b, 3.0 * a)

    def test_a_layers_bank_and_its_top_are_told_apart(self):
        m = self.step()
        flat_top = L.height(m, 3.0, np.ones((N, N), np.float32))                        # a bank, a level top
        t = L.tilts(*L.hold(*L.slopes(flat_top, 1.0)), m)
        self.assertGreater(t["bank"], float(np.degrees(np.arctan(3.0 / 9.0))))          # steeper than the fade
        self.assertEqual(t["top"], 0.0)                                                 # ... and its top is level
        lumpy = L.height(m, 3.0, L.top_noise(N, np.random.default_rng(2), 3.0, 1.0))
        t2 = L.tilts(*L.hold(*L.slopes(lumpy, 1.0)), m)
        self.assertGreater(t2["top"], 2.0)
        thin = L.height(m, 0.05, np.ones((N, N), np.float32))
        t3 = L.tilts(*L.hold(*L.slopes(thin, 1.0)), m)
        self.assertLess(max(t3.values()), L.SHOWS_DEG)                                  # too flat to show
        steep = L.tilts(*L.hold(*L.slopes(flat_top * 40.0, 1.0)), m)
        self.assertGreaterEqual(steep["bank"], L.HELD_DEG)                              # at the hold
        self.assertLessEqual(steep["bank"], 63.5)
        self.assertEqual(L.tilts(*L.slopes(flat_top, 1.0), np.zeros_like(m)), {"bank": 0.0, "top": 0.0})

    def test_on_a_bevel_the_relief_leans_from_the_bevels_own_normal(self):
        base = np.array([0.6, 0.0, 0.8], np.float32)                                    # a bevel's tilted normal
        nrm = np.zeros((N, N, 4), np.float32)
        nrm[..., :3] = base * 0.5 + 0.5
        gx = np.zeros((N, N), np.float32)
        gx[:, 40:50] = L.SLOPE_MAX                                                      # a 63 degree bank on it
        out = L.raised(nrm, gx, np.zeros((N, N), np.float32))
        n = out[10, 45] * 2 - 1
        turn = float(np.degrees(np.arccos(np.clip(float((n * base).sum()), -1, 1))))
        self.assertAlmostEqual(turn, float(np.degrees(np.arctan(L.SLOPE_MAX))), delta=0.5)   # 63 from the bevel
        self.assertAlmostEqual(float(np.linalg.norm(n)), 1.0, places=3)

    def test_a_texel_with_no_slope_is_left_to_the_bit(self):
        rng = np.random.default_rng(5)
        nrm = np.round(rng.uniform(0.3, 0.9, (N, N, 4)) * 255).astype(np.float32) / 255   # 8-bit, not unit length
        gx = np.zeros((N, N), np.float32)
        gx[:, 40:50] = 0.4
        out = L.raised(nrm, gx, np.zeros((N, N), np.float32))
        self.assertTrue(np.array_equal(out[:, :40], nrm[:, :40, :3]))
        self.assertTrue(np.array_equal(out[:, 50:], nrm[:, 50:, :3]))
        self.assertFalse(np.array_equal(out[:, 40:50], nrm[:, 40:50, :3]))
        self.assertTrue(np.isfinite(out).all())


if __name__ == "__main__":
    unittest.main()
