"""Physically based values (kit/blender/rbx_pbr.py): a metal darker than any real one, half a metal, a non-metal
blacker than charcoal are named with their fix — every measured material and every finish passes; and the roughness
variation measured on a baked map tells a flat surface from a used one, inside each material's own zone."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_materials as M  # noqa: E402
import rbx_pbr as P  # noqa: E402


def _one_zone_as_it_was(zone, r):
    """the same-zone map as rough_zones made it until 2026-11-13: every shifted copy against the centre"""
    size = zone.shape[0]
    pad = np.pad(zone, 2 * r, mode="constant", constant_values=-2)
    same = np.ones(zone.shape, dtype=bool)
    for dy in range(4 * r + 1):
        for dx in range(4 * r + 1):
            same &= pad[dy:dy + size, dx:dx + size] == zone
    return same


class TestOneZone(unittest.TestCase):
    def zones(self, size, seed):
        rng = np.random.default_rng(seed)
        z = (rng.integers(0, 5, (size // 16 + 1, size // 16 + 1)) - 1).repeat(16, 0).repeat(16, 1)[:size, :size]
        z = z.astype(np.int16)
        z[rng.random((size, size)) < 0.002] = -1          # holes: texels no face covers
        return z

    def test_the_same_map_as_comparing_every_shifted_copy(self):
        for size, r in ((64, 1), (130, 1), (128, 2), (96, 3)):
            z = self.zones(size, size + r)
            self.assertTrue(np.array_equal(P.one_zone(z, r), _one_zone_as_it_was(z, r)), (size, r))

    def test_a_map_of_one_zone_is_one_zone_but_for_its_border(self):
        z = np.zeros((40, 40), np.int16)
        same = P.one_zone(z, 1)
        self.assertTrue(same[2:-2, 2:-2].all())
        self.assertFalse(same[:2].any() or same[-2:].any() or same[:, :2].any() or same[:, -2:].any())

    def test_rough_zones_measures_what_it_did(self):
        rng = np.random.default_rng(9)
        z = self.zones(256, 9)
        rough = rng.random((256, 256)).astype(np.float32)
        names = ["a", "b", None, "c"]
        now = P.rough_zones(rough, z, names)
        real, P.one_zone = P.one_zone, _one_zone_as_it_was
        try:
            was = P.rough_zones(rough, z, names)
        finally:
            P.one_zone = real
        self.assertEqual(now, was)


class TestNumbers(unittest.TestCase):
    def test_srgb_of_a_linear_colour(self):
        self.assertEqual(P.srgb((0.18, 0.18, 0.18)), 118)  # the grey card
        self.assertEqual(P.srgb((1, 1, 1)), 255)
        self.assertEqual(P.srgb((0, 0, 0)), 0)

    def test_scale_to_keeps_the_hue(self):
        c = P.scale_to((0.02, 0.01, 0.005), 60)
        self.assertAlmostEqual(P.srgb(c), 60, delta=1)
        self.assertAlmostEqual(c[0] / c[1], 2.0, delta=0.05)


class TestJudge(unittest.TestCase):
    def test_a_metal_at_60_srgb_is_a_coating(self):
        (p,) = P.judge("frame", (0.045, 0.046, 0.05), 1.0, 0.3)
        self.assertIn("a metal at 61 sRGB", p["what"])
        self.assertIn("painted / coated finish: metal 0", p["fix"])
        self.assertIn('rbx.finish("gunmetal_parkerized")', p["fix"])
        self.assertIn('rbx.real("', p["fix"])  # ... or the nearest measured bare metal
        self.assertTrue(P.say(p).startswith("frame: "))

    def test_half_a_metal_is_named_unless_satin(self):
        (p,) = P.judge("slide", (0.2, 0.2, 0.21), 0.5, 0.4)
        self.assertIn("half a metal", p["what"])
        self.assertIn("satin=True", p["fix"])
        self.assertEqual(P.judge("cloth", (0.35, 0.3, 0.4), 0.4, 0.5, satin=True), [])

    def test_near_zero_and_near_one_count_as_zero_and_one(self):
        self.assertEqual(P.judge("shell", (0.8, 0.8, 0.8), 0.1, 0.4), [])
        self.assertEqual(P.judge("steel", (0.55, 0.57, 0.62), 0.9, 0.45), [])

    def test_every_measured_metal_passes(self):
        for name in M.load():
            v = M.real(name)
            if v["metal"] >= 0.5:
                self.assertEqual(P.judge(name, v["color"], v["metal"], v["rough"]), [], name)

    def test_every_measured_opaque_non_metal_passes_even_strict(self):
        for name in M.load():
            v = M.real(name)
            if v["metal"] < 0.5 and 30 <= P.srgb(v["color"]) <= 240:  # (glass, lab blacks: no opaque base colour)
                self.assertEqual(P.judge(name, v["color"], 0.0, v["rough"], strict=True), [], name)

    def test_a_darker_metal_must_be_rough(self):
        dark = (0.38, 0.38, 0.38)  # 166 sRGB: no measured metal is this neutral grey
        (p,) = P.judge("cast", dark, 1.0, 0.3)
        self.assertIn("darker metal", p["what"])
        self.assertEqual(P.judge("cast", dark, 1.0, 0.55), [])

    def test_non_metal_range(self):
        self.assertIn("non-metal at 13 sRGB", P.judge("black", (0.004, 0.004, 0.004), 0.0, 0.5)[0]["what"])
        self.assertIn("non-metal at 248 sRGB", P.judge("white", (0.94, 0.94, 0.94), 0.0, 0.5)[0]["what"])  # (snow: 237)
        navy45 = P.scale_to((0.3, 0.4, 1.0), 45)  # a dark navy (a neutral 45 would be measured tyre: 42)
        self.assertEqual(P.judge("paint", navy45, 0.0, 0.5), [])  # tolerant range: 30+
        self.assertEqual(len(P.judge("paint", navy45, 0.0, 0.5, strict=True)), 1)  # strict (aaa): 50+

    def test_lights_and_tints_are_judged_on_metalness_only(self):
        self.assertEqual(P.judge("glow", (1, 1, 1), 0.0, 0.4, glow=True), [])
        self.assertEqual(P.judge("glass", (1, 1, 1), 0.0, 0.05, clear=True), [])
        self.assertEqual(len(P.judge("glass", (0.06, 0.12, 0.1), 0.3, 0.04, clear=True)), 1)

    def test_chips_wear_through_to_bare_metal(self):
        self.assertEqual(P.judge_under("paint", (0.56, 0.57, 0.6)), [])
        (p,) = P.judge_under("panel", (0.12, 0.12, 0.13))
        self.assertIn("under=", p["what"])


class TestFinishes(unittest.TestCase):
    def test_every_finish_passes_the_strict_rules(self):
        for name, kw, _about in P.finishes():
            self.assertEqual(P.judge(name, kw["color"], kw["metal"], kw["rough"], strict=True), [], name)
            self.assertIn(kw["metal"], (0.0, 1.0), name)

    def test_dark_gun_finishes_are_coatings(self):
        for name in ("gunmetal_parkerized", "blued_steel", "black_anodized"):
            kw = P.finish(name)
            self.assertEqual(kw["metal"], 0.0, name)
            self.assertLessEqual(P.srgb(kw["color"]), 70, name)

    def test_built_on_measured_entries(self):
        self.assertEqual(P.finish("polished_brass")["color"], M.real("Brass")["color"])
        self.assertEqual(P.finish("rubber")["color"], M.real("Tire")["color"])

    def test_overrides_and_unknown_names(self):
        kw = P.finish("painted_metal", color=(0.3, 0.05, 0.04), rough=0.4)
        self.assertEqual((kw["color"], kw["metal"], kw["rough"]), ((0.3, 0.05, 0.04), 0.0, 0.4))
        with self.assertRaises(KeyError):
            P.finish("unobtainium")


class TestDarkStory(unittest.TestCase):
    """dark_finishes: the Glock's frame / slide numbers, as judged by fresh judges (2026-10-10)"""

    @staticmethod
    def _row(name, grey, area, **k):
        return {"name": name, "color": (grey, grey, grey), "metal": 0.0, "area": area, **k}

    def test_the_rated_glock_reads_apart(self):
        rows = [self._row("slide", 0.028, 40, burnish=0.9, rub=0.3), self._row("frame", 0.095, 50, burnish=0.55)]
        story = P.dark_story(rows, worn=True)
        self.assertEqual(story["alike"], [])
        self.assertEqual(story["unworn"], [])

    def test_the_navy_blob_is_named(self):
        # frame 0.042 (57 sRGB) beside the 0.028 slide (47): "the same blue-navy" to two fresh judges
        story = P.dark_story([self._row("slide", 0.028, 40), self._row("frame", 0.042, 50)])
        self.assertEqual([(a, b) for a, b, _va, _vb in story["alike"]], [("frame", "slide")])
        self.assertEqual(story["unworn"], [])   # (worn=False: a prop is not asked)

    def test_small_bright_and_metal_materials_are_left_out(self):
        rows = [self._row("slide", 0.028, 80), self._row("screw", 0.03, 5),            # (under DARK_MAIN of the total)
                self._row("steel", 0.03, 40, metal=1.0), self._row("label", 0.6, 40)]  # (a metal; a bright one)
        self.assertEqual(P.dark_story(rows)["alike"], [])

    def test_a_hero_dark_finish_must_be_worn(self):
        story = P.dark_story([self._row("slide", 0.028, 40), self._row("frame", 0.095, 50, rub=0.2)], worn=True)
        self.assertEqual(story["unworn"], ["slide"])
        kw = P.finish("nitride")
        worn = P.life_of("used", kw["color"], kw["metal"], kw["rough"], finish="nitride")
        story = P.dark_story([{"name": "slide", "area": 40, **kw, **worn}], worn=True)
        self.assertEqual(story["unworn"], [])
        # a dark PAINT worn its own way (chips, no burnish) is worn too — never told to wear what it already wears
        paint = P.life_of("used", (0.03, 0.03, 0.03), 0.0, 0.5, finish="painted_metal")
        story = P.dark_story([{"name": "lid", "area": 40, "color": (0.03, 0.03, 0.03), "metal": 0.0, **paint}], worn=True)
        self.assertEqual(story["unworn"], [])


class TestLife(unittest.TestCase):
    """life="new|light|used|heavy" on ANY material: the owner-rated Glock's wear (85/100, 2026-10-10) for its class,
    the class worked out from the material's own values"""

    @staticmethod
    def _life(level, color, metal=0.0, rough=0.5, **k):
        return P.life_of(level, color, metal, rough, **k)

    def test_no_level_no_wear_keys(self):
        self.assertEqual(set(P.finish("nitride")), {"color", "metal", "rough"})   # (every existing call unchanged)
        self.assertEqual(P.finish("nitride", life="used")["life"], "used")
        self.assertEqual(P.finish("nitride", life="used")["finish"], "nitride")
        with self.assertRaises(KeyError):
            P.finish("nitride", life="ancient")   # (an unknown level fails at the line that named it)

    def test_used_is_the_rated_glock(self):
        kw = P.finish("nitride")
        slide = self._life("used", kw["color"], kw["metal"], kw["rough"], finish="nitride")
        self.assertEqual((slide["burnish"], slide["burnish_mm"], slide["rub"], slide["smudge"]), (0.9, 2.5, 0.3, 0.5))
        self.assertEqual(slide, self._life("carried", kw["color"], kw["metal"], kw["rough"], finish="nitride"))
        frame = self._life("used", (0.095, 0.094, 0.092), rough=0.72)   # (no finish named: dark + rough = polymer)
        self.assertEqual((frame["burnish"], frame["burnish_mm"], frame["rub"]), (0.55, 2.0, 0.15))
        self.assertNotIn("chip", slide)   # (chips on a black gun read as bake artifacts: paint only)

    def test_the_class_comes_from_the_material(self):
        self.assertEqual(P.life_class((0.6, 0.6, 0.6), 1.0, 0.3), "bare")
        self.assertEqual(P.life_class((0.03, 0.03, 0.03), 0.0, 0.2), "coating")
        self.assertEqual(P.life_class((0.03, 0.03, 0.03), 0.0, 0.8), "polymer")
        self.assertEqual(P.life_class((0.3, 0.05, 0.04), 0.0, 0.5, painted=True), "paint")
        self.assertEqual(P.life_class((0.35, 0.2, 0.1), 0.0, 0.6), "dielectric")   # (a wood, a stone, a fabric)
        self.assertEqual(P.life_class((0.03, 0.03, 0.03), 0.0, 0.5, finish="painted_metal"), "paint")
        self.assertEqual(P.life_class((0.6, 0.6, 0.6), 1.0, 0.3, finish="chrome"), "bare")
        wood = self._life("used", (0.35, 0.2, 0.1), rough=0.6)
        self.assertEqual(set(wood), {"wear", "grime", "smudge"})   # (no burnish: nothing to lift a light surface to)
        self.assertIn("chip", self._life("used", (0.3, 0.05, 0.04), painted=True))

    def test_levels_order_and_clamp(self):
        lv = [self._life(w, (0.032, 0.036, 0.05), rough=0.3) for w in ("new", "light", "used", "heavy")]
        for key in ("burnish", "rub", "smudge", "grime", "wear"):
            vals = [x[key] for x in lv]
            self.assertEqual(vals, sorted(vals), key)
            self.assertLessEqual(vals[-1], 1.0, key)
        self.assertEqual(lv[0]["burnish"], 0.0)

    def test_a_given_key_wins_and_the_rest_default(self):
        got = P.resolve_life({"rub": 0.8, "wear": 0.2}, "used", (0.033, 0.033, 0.034), 0.0, 0.2, finish="nitride")
        self.assertEqual((got["rub"], got["wear"], got["burnish"]), (0.8, 0.2, 0.9))   # (given; given; the level's)
        self.assertEqual(set(got), set(P.WEAR_KEYS))
        none = P.resolve_life({"wear": None}, None, (0.5, 0.5, 0.5), 0.0, 0.5)
        self.assertEqual(none, P.WEAR_DEFAULTS)   # (no level: the old defaults, every key)
        self.assertEqual(P.resolve_life({"chip": 0.0}, "used", (0.3, 0.05, 0.04), 0.0, 0.5, painted=True)["chip"], 0.0)


def _halves(size):
    """two triangles per half of the UV square: zone 0 left (u < 0.5), zone 1 right"""
    tris, zones = [], []
    for z, (u0, u1) in enumerate(((0.0, 0.5), (0.5, 1.0))):
        tris += [[(u0, 0), (u1, 0), (u1, 1)], [(u0, 0), (u1, 1), (u0, 1)]]
        zones += [z, z]
    return P.zone_map(np.array(tris), np.array(zones), size)


class TestVariation(unittest.TestCase):
    def test_zone_map_covers_every_texel_centre(self):
        z = _halves(64)
        self.assertFalse((z < 0).any())
        self.assertTrue((z[:, :32] == 0).all() and (z[:, 32:] == 1).all())

    def test_scanline_matches_a_texel_by_texel_test(self):
        rng = np.random.default_rng(7)
        size, n = 48, 120
        centre = rng.random((n, 1, 2))
        tris = np.clip(centre + (rng.random((n, 3, 2)) - 0.5) * rng.choice([0.05, 0.3, 1.2], (n, 1, 1)), 0, 1)
        got = P.zone_map(tris, np.arange(n), size)
        want = np.full((size, size), -1)
        yy, xx = np.mgrid[0:size, 0:size] + 0.5
        for i, (a, b, c) in enumerate(tris * size):  # (later triangles win where they overlap, as in the bake)
            e = [(q[0] - p[0]) * (yy - p[1]) - (q[1] - p[1]) * (xx - p[0]) for p, q in ((a, b), (b, c), (c, a))]
            inside = ((e[0] >= 0) & (e[1] >= 0) & (e[2] >= 0)) | ((e[0] <= 0) & (e[1] <= 0) & (e[2] <= 0))
            want[inside] = i
        self.assertLessEqual(int((got != want).sum()), 2)  # (a centre exactly on an edge may round either way)

    def test_big_and_small_triangles_raster_the_same(self):
        big = P.zone_map(np.array([[(0.05, 0.1), (0.9, 0.2), (0.3, 0.95)]]), np.array([3]), 128)
        # the same triangle cut into 4^4 small ones (midpoint subdivision)
        tris = [np.array([(0.05, 0.1), (0.9, 0.2), (0.3, 0.95)])]
        for _ in range(4):
            nxt = []
            for a, b, c in tris:
                ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
                nxt += [np.array(t) for t in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))]
            tris = nxt
        small = P.zone_map(np.array(tris), np.full(len(tris), 3), 128)
        self.assertEqual(int((big == 3).sum()), int((small == 3).sum()))
        self.assertGreater(int((big == 3).sum()), 4000)

    def test_flat_and_varied_zones(self):
        size = 512
        z = _halves(size)
        rng = np.random.default_rng(1)
        rough = np.full((size, size), 0.5, np.float32)
        yy, xx = np.mgrid[0:size, 0:size] / size
        varied = (0.5 + 0.04 * rng.standard_normal((size, size))  # fine
                  + 0.06 * np.sin(xx * 2 * np.pi * 24) * np.sin(yy * 2 * np.pi * 24)  # mid blotches
                  + 0.1 * np.sin(yy * 2 * np.pi * 2))  # coarse patches
        rough[:, size // 2:] = varied[:, size // 2:]
        out = P.rough_zones(rough, z, ["flat", "used"])
        for s in P.SCALES:
            self.assertLess(out["flat"][s], P.FLAT_SPREAD, s)
            self.assertGreater(out["used"][s], P.FLAT_SPREAD, s)
        self.assertAlmostEqual(out["flat"]["share"], 0.5, delta=0.01)

    def test_a_neighbours_roughness_never_counts(self):
        size = 256
        z = _halves(size)
        rough = np.where(z == 0, 0.2, 0.9).astype(np.float32)  # two flat materials, very different
        out = P.rough_zones(rough, z, ["a", "b"])
        for name in ("a", "b"):
            for s in P.SCALES:
                self.assertLess(out[name][s], 0.005, (name, s))

    def test_merge_and_judge(self):
        maps = [{"body": {"texels": 900, "of": 1000, "share": 0.9, "fine": 0.0, "mid": 0.001, "coarse": 0.03},
                 "knob": {"texels": 40, "of": 1000, "share": 0.04, "fine": 0.0, "mid": 0.0, "coarse": 0.0}},
                {"body": {"texels": 100, "of": 1000, "share": 0.1, "fine": 0.0, "mid": 0.001, "coarse": 0.01}}]
        zones = P.merge_zones(maps)
        self.assertEqual(zones["body"]["texels"], 1000)
        self.assertAlmostEqual(zones["body"]["share"], 0.5)
        self.assertAlmostEqual(zones["body"]["coarse"], 0.028)
        specs = {"body": {"metal": 1.0, "wear": 0.1}, "knob": {}}
        (p,) = P.judge_variation(zones, specs.get, available=["Metal008", "Plastic010"])  # the knob is detail (4%)
        self.assertEqual(p["material"], "body")
        for cure in ('scan="Metal008"', 'pattern="brushed"', "wear=0.4 + grime=0.4"):
            self.assertIn(cure, p["fix"])

    def test_flat_at_one_scale_only_is_spared(self):
        zones = {"paint": {"texels": 10, "share": 1.0, "fine": 0.001, "mid": 0.05, "coarse": 0.08}}
        self.assertEqual(P.judge_variation(zones, lambda _n: {}, available=[]), [])

    def test_a_scanned_surface_varying_at_the_fine_scale_is_its_grain(self):
        # (the kit make chair the owner liked: wood scan, fine 0.076, even at mid / coarse — a new chair is)
        zones = {"wood": {"texels": 10, "share": 1.0, "fine": 0.076, "mid": 0.018, "coarse": 0.007}}
        self.assertEqual(P.judge_variation(zones, lambda _n: {"scan": "Wood096"}, available=[]), [])
        # ... with no scan the same numbers are still flagged, and flat at EVERY scale always is (the hydrant)
        self.assertEqual(len(P.judge_variation(zones, lambda _n: {}, available=[])), 1)
        flat = {"paint": {"texels": 10, "share": 1.0, "fine": 0.0, "mid": 0.0, "coarse": 0.0}}
        self.assertEqual(len(P.judge_variation(flat, lambda _n: {"scan": "Metal027"}, available=[])), 1)

    def test_a_scan_is_suggested_by_what_the_material_is(self):
        have = ["Leather037", "Metal008", "Plastic010", "Wood096"]
        self.assertEqual(P.scan_for("grip_leather", 0.0, have), "Leather037")
        self.assertEqual(P.scan_for("frame", 1.0, have), "Metal008")
        self.assertEqual(P.scan_for("paint", 0.0, have), "Plastic010")
        self.assertIsNone(P.scan_for("paint", 0.0, []))

    def test_organic_and_rusty_surfaces_find_their_scans(self):
        have = ["Bark013", "Bark014", "Fabric019", "Fabric030", "Fabric061", "Metal008", "Metal021", "Plastic010",
                "Rust009", "Wood096"]
        self.assertEqual(P.scan_for("trunk_bark", 0.0, have), "Bark013")   # (the first bark this machine has)
        self.assertEqual(P.scan_for("moss_cover", 0.0, have), "Bark013")   # (moss alone: only its own hint finds it)
        self.assertEqual(P.scan_for("grain_sack", 0.0, have), "Fabric061")
        self.assertEqual(P.scan_for("wool_blanket", 0.0, have), "Fabric019")
        self.assertEqual(P.scan_for("seat_cloth", 0.0, have), "Fabric019")   # (any fabric: the first one)
        self.assertEqual(P.scan_for("rust_patch", 0.0, have), "Rust009")
        self.assertEqual(P.scan_for("rusty_hull", 1.0, have), "Metal021")   # (rusted steel: still metal)
        self.assertEqual(P.scan_for("frame", 1.0, have), "Metal008")         # (plain steel unchanged)
        self.assertEqual(P.scan_for("RustyHull", 1.0, have), "Metal021")     # (camelCase names split)
        self.assertEqual(P.scan_for("gold_trim", 1.0, have), "Metal008")     # (whole words: "gold" is not "old")
        self.assertEqual(P.scan_for("rocket_body", 0.0, have), "Plastic010")  # ("rocket" is not "rock")
        self.assertEqual(P.scan_for("wooden_crate", 0.0, have), "Wood096")
        self.assertEqual(P.scan_for("hardwood_floor", 0.0, have), "Wood096")   # (compounds: the hint ends the word)
        self.assertEqual(P.scan_for("plywood", 0.0, have), "Wood096")


if __name__ == "__main__":
    unittest.main()
