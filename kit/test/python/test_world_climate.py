"""test_world_climate.py - BIOMES BY TEMPERATURE AND MOISTURE (kit/world/terrain.py climate / paint; the owner's
method list: "Rule-based biome distribution", "Biome-based generation", "Procedural snow coverage").
On lands made of plain formulas - a ridge across the wind, a ridge with a north and a south face, a plain - the
painter is held to what a climate must do: the windward side wetter than the lee, colder with height, snow lower on
a north face, dry warm ground bare. And with no climate the painter paints exactly what it painted before.
Not claimed here: that a land painted this way looks right. That is a built world, looked at."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TERRAIN = os.path.join(HERE, "..", "..", "world", "terrain.py")
_spec = importlib.util.spec_from_file_location("kit_world_terrain_climate", TERRAIN)
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

N, CELL = 129, 4
X, Z = np.meshgrid(np.arange(N) * CELL, np.arange(N) * CELL, indexing="ij")  # (h[ix, iz]: axis 0 is x, axis 1 is z)
MID = (N - 1) * CELL / 2


def ridge_ns(height=90.0, half=120.0):
    """a ridge that runs north-south (along z) across the middle: its faces look west and east"""
    return height * np.clip(1 - np.abs(X - MID) / half, 0, 1)


def ridge_ew(height=90.0, half=120.0):
    """a ridge that runs east-west (along x): its faces look north (-z) and south (+z)"""
    return height * np.clip(1 - np.abs(Z - MID) / half, 0, 1)


def cfg(text):
    c, problems = T.climate_config(text)
    assert problems == [], problems
    return c


def share(roles, mask, name):
    return float((roles[mask] == T.ROLES.index(name)).mean())


class Config(unittest.TestCase):
    def test_a_climate_is_read_and_what_is_wrong_is_said(self):
        c, problems = T.climate_config("wind=90, rain=0.8")
        self.assertEqual(problems, [])
        self.assertEqual(c["wind"], 90.0)
        self.assertEqual(c["rain"], 0.8)
        self.assertEqual(c["sea"], T.CLIMATE["sea"])  # (what is not said is the kit's)
        self.assertEqual(T.climate_config({"lapse": 0.5})[0]["lapse"], 0.5)  # (a design's dict)
        for bad, text in (("wnd=90", "climate.wnd"), ("rain=2", "climate.rain is 0 to 1"), ("rain=wet", "is a number"),
                          ("wind", "is not key=value"), ("shade=-1", "climate.shade"), ("wind=400", "climate.wind")):
            _, problems = T.climate_config(bad)
            self.assertTrue(any(text in p for p in problems), (bad, problems))
        self.assertTrue(T.climate_config(5)[1])


class Moisture(unittest.TestCase):
    def test_the_side_the_wind_comes_from_is_wet_and_the_lee_is_dry(self):
        h = ridge_ns()
        west, east = X < MID - 130, X > MID + 130  # (the flats before and behind the ridge)
        _, m = T.climate(h, CELL, cfg("wind=270,rain=0.6"))  # from the west
        self.assertAlmostEqual(float(m[west].mean()), 0.6, places=2)  # (untouched air: its own wetness)
        lee = (X > MID + 125) & (X < MID + 180)  # (just behind the ridge's foot)
        self.assertLess(float(m[lee].mean()), 0.6 * 0.6)  # (behind a 90-stud ridge: a rain shadow)
        self.assertLess(float(m[east].mean()), 0.5)
        up = (X > MID - 110) & (X < MID - 10)  # (the slope that faces the wind: the air is lifted and rains)
        self.assertGreater(float(m[up].mean()), 0.8)
        # the same land, the wind from the east: the sides change places
        _, m2 = T.climate(h, CELL, cfg("wind=90,rain=0.6"))
        self.assertAlmostEqual(float(m2[east].mean()), 0.6, places=2)
        self.assertLess(float(m2[west].mean()), 0.5)
        # a wind along the ridge (from the north) crosses nothing: no side is dry
        _, m3 = T.climate(h, CELL, cfg("wind=0,rain=0.6"))
        self.assertAlmostEqual(float(m3[west].mean()), float(m3[east].mean()), places=2)
        self.assertGreater(float(m3[east].mean()), 0.55)

    def test_the_shadow_is_deeper_behind_a_higher_ridge_and_ends_behind_it(self):
        lee = (X > MID + 130) & (X < MID + 200)
        low = T.climate(ridge_ns(20), CELL, cfg("wind=270,rain=0.6"))[1]
        high = T.climate(ridge_ns(90), CELL, cfg("wind=270,rain=0.6"))[1]
        self.assertGreater(float(low[lee].mean()), float(high[lee].mean()) + 0.1)
        # 240 studs behind the ridge's foot and further the air is its own again
        narrow = 60 * np.clip(1 - np.abs(X - 100) / 40, 0, 1)
        m = T.climate(narrow, CELL, cfg("wind=270,rain=0.6"))[1]
        self.assertLess(float(m[(X > 150) & (X < 200)].mean()), 0.45)
        self.assertAlmostEqual(float(m[X > 100 + 40 + 250].mean()), 0.6, places=2)
        # ... and it fades on the way: 30 studs behind the foot is drier than 190 behind it
        near = float(m[(X > 165) & (X < 180)].mean())
        far = float(m[(X > 320) & (X < 340)].mean())
        self.assertLess(near, far - 0.1)

    def test_where_the_erosions_water_ran_is_wet_even_in_dry_air(self):
        h = np.zeros((N, N))
        flow = np.zeros((N, N))
        flow[:, 60:64] = 500.0  # (a channel)
        m = T.climate(h, CELL, cfg("rain=0.1"), flow)[1]
        self.assertGreater(float(m[:, 61].mean()), 0.45)
        self.assertLess(float(m[:, 10].mean()), 0.15)


    def test_a_hollows_own_rim_is_no_ridge_and_the_maps_edge_is_no_wall(self):
        # a bowl 80 studs deep in a plain: its floor is not in a rain shadow of its own rim, whatever the wind
        d = np.sqrt((X - MID) ** 2 + (Z - MID) ** 2)
        bowl = 100 - 80 * np.clip(1 - d / 150, 0, 1)
        mid = int(MID / CELL)
        for wind in (0, 90, 225):
            m = T.climate(bowl, CELL, cfg(f"wind={wind},rain=0.5"))[1]
            self.assertGreater(float(m[mid, mid]), 0.45, wind)
        # a hill ON the north border, a diagonal wind: the march used to slide along the border row and shade cells
        # far to the side of the hill. Off the map is open air.
        hill = 80 * np.clip(1 - np.sqrt((X - MID - 200) ** 2 + (Z - 0) ** 2) / 60, 0, 1)
        flat = np.zeros((N, N))
        a = T.climate(hill, CELL, cfg("wind=45,rain=0.5"))[1]
        b = T.climate(flat, CELL, cfg("wind=45,rain=0.5"))[1]
        row = 2  # (8 studs inside the border)
        for x in (MID + 60, MID + 100):  # (100 and 140 studs to the side of the hill)
            i = int(x / CELL)
            self.assertAlmostEqual(float(a[i, row]), float(b[i, row]), places=2)
        # ... the same hill well inside the map does shade what lies downwind of it (wind from the north-east blows
        # toward the south-west)
        inner = 80 * np.clip(1 - np.sqrt((X - MID) ** 2 + (Z - MID) ** 2) / 60, 0, 1)
        m = T.climate(inner, CELL, cfg("wind=45,rain=0.5"))[1]
        i, j = int((MID - 70) / CELL), int((MID + 70) / CELL)
        self.assertLess(float(m[i, j]), 0.35)


class Temperature(unittest.TestCase):
    def test_it_is_colder_with_height_by_the_lapse(self):
        h = ridge_ns()
        t = T.climate(h, CELL, cfg("sea=0.8,lapse=0.4,shade=0"))[0]
        self.assertAlmostEqual(float(t[0, 0]), 0.8, places=6)  # (the plain at height 0: the sea's warmth)
        top = int(MID / CELL)
        self.assertAlmostEqual(float(t[top, 5]), 0.8 - 0.4 * 0.9, places=6)  # (90 studs up)

    def test_a_north_face_is_colder_than_a_south_face_at_the_same_height(self):
        h = ridge_ew()  # (north face: z under the middle; -Z is north)
        t = T.climate(h, CELL, cfg("sea=0.8,lapse=0.4,shade=0.2"))[0]
        k = int((MID - 60) / CELL), int((MID + 60) / CELL)  # (60 studs each side of the crest: the same height)
        self.assertAlmostEqual(float(h[5, k[0]]), float(h[5, k[1]]), places=6)
        self.assertLess(float(t[5, k[0]]), float(t[5, k[1]]) - 0.2)  # (0.2 x 0.75 a face: 0.3 between them)
        # (the south face is warmer than level ground at that height by the shade, the north colder by it)
        level = 0.8 - 0.4 * float(h[5, k[1]]) / 100
        steep = min(1.0, 90.0 / 120.0)
        self.assertAlmostEqual(float(t[5, k[1]]), level + 0.2 * steep, places=6)
        self.assertAlmostEqual(float(t[5, k[0]]), level - 0.2 * steep, places=6)
        # a face steeper than 45 degrees is no colder than one at 45 (the shade is capped: 0.4 between the faces)
        crag = ridge_ew(300, 100)  # (72 degrees)
        tc = T.climate(crag, CELL, cfg("sea=0.8,lapse=0,shade=0.2"))[0]
        self.assertAlmostEqual(float(tc[5, int((MID + 50) / CELL)] - tc[5, int((MID - 50) / CELL)]), 0.4, places=6)
        # ... and with no shade the two are the same
        t0 = T.climate(h, CELL, cfg("sea=0.8,lapse=0.4,shade=0"))[0]
        self.assertAlmostEqual(float(t0[5, k[0]]), float(t0[5, k[1]]), places=6)


class Painted(unittest.TestCase):
    def paint(self, h, climate, flow=None, **more):
        opts = {"climate": cfg(climate) if climate is not None else None}
        opts.update(more)
        return T.paint(h, CELL, flow, None, 38, 7, opts)[0]

    def test_with_no_climate_the_painter_paints_what_it_painted_before(self):
        # (recorded from the painter as it stood before the climate, 2026-11-15: the same land, the same bytes)
        h = T.fbm(N, N * CELL, 180, 6, 3) * 80
        flow = np.abs(T.fbm(N, N * CELL, 60, 3, 9)) * 40
        dep = np.abs(T.fbm(N, N * CELL, 90, 3, 5))
        r = T.paint(h, CELL, flow, dep, 38, 7, {})[0]
        self.assertEqual(hashlib.sha1(r.tobytes()).hexdigest(), "4c275d2a82434928b67ee01dba6e6868ff8df3c1")
        r = T.paint(h, CELL, flow, dep, 38, 7, {"snowline": 55, "shore": 8})[0]
        self.assertEqual(hashlib.sha1(r.tobytes()).hexdigest(), "19559ae1144f06d3d46d8c2827585cd1d5ad51b5")
        r = T.paint(h, CELL, flow, dep, 38, 7, {"snowline": 55, "shore": 8, "climate": None})[0]
        self.assertEqual(hashlib.sha1(r.tobytes()).hexdigest(), "19559ae1144f06d3d46d8c2827585cd1d5ad51b5")

    def test_the_wet_side_is_lush_and_the_lee_is_not(self):
        h = ridge_ns(90, 200)  # (gentle faces: soil, not rock)
        r = self.paint(h, "wind=270,rain=0.6,sea=0.8,lapse=0.2")
        windward = (X > MID - 190) & (X < MID - 20)
        lee = (X > MID + 20) & (X < MID + 190)
        self.assertGreater(share(r, windward, "lush"), 0.6)
        self.assertLess(share(r, lee, "lush"), 0.05)
        # the wind turned round: so do they
        r2 = self.paint(h, "wind=90,rain=0.6,sea=0.8,lapse=0.2")
        self.assertGreater(share(r2, lee, "lush"), 0.6)
        self.assertLess(share(r2, windward, "lush"), 0.05)

    def test_dry_warm_ground_is_bare_then_sand_and_wet_ground_is_not(self):
        plain = np.zeros((N, N))
        everywhere = np.ones((N, N), bool)
        dry = self.paint(plain, "rain=0.05,sea=0.9")
        self.assertGreater(share(dry, everywhere, "sand"), 0.7)
        half = self.paint(plain, "rain=0.2,sea=0.9")
        self.assertGreater(share(half, everywhere, "dirt"), 0.5)
        self.assertLess(share(half, everywhere, "sand"), 0.2)
        wet = self.paint(plain, "rain=0.5,sea=0.9")
        self.assertEqual(share(wet, everywhere, "sand"), 0.0)
        self.assertEqual(share(wet, everywhere, "dirt"), 0.0)
        # dry and COLD is not sand (a cold desert keeps its ground)
        cold = self.paint(plain, "rain=0.05,sea=0.35")
        self.assertEqual(share(cold, everywhere, "sand"), 0.0)

    def test_the_lee_dries_at_the_settings_the_page_gives(self):
        # (a fresh reader: with the documented example nothing dried behind a ridge - only meadow turned lush)
        h = ridge_ns(90, 120)
        r = self.paint(h, "wind=270,rain=0.6,sea=0.8")
        lee = (X > MID + 125) & (X < MID + 190)  # (the flats just behind the ridge's foot)
        before = (X > 10) & (X < MID - 125)  # (the flats the wind reaches first)
        self.assertGreater(share(r, lee, "dirt") + share(r, lee, "sand"), 0.6)
        self.assertEqual(share(r, before, "dirt") + share(r, before, "sand"), 0.0)
        # ... and at the kit's own defaults (rain 0.5)
        r = self.paint(h, "wind=270")
        self.assertGreater(share(r, lee, "dirt") + share(r, lee, "sand"), 0.6)
        # far behind the ridge (past its 240 studs) the ground is not bared
        narrow = 60 * np.clip(1 - np.abs(X - 100) / 40, 0, 1)
        far = X > 100 + 40 + 250
        self.assertTrue(far.any())
        self.assertEqual(share(self.paint(narrow, "wind=270"), far, "dirt"), 0.0)
        self.assertGreater(share(self.paint(narrow, "wind=270"), (X > 145) & (X < 190), "dirt"), 0.5)

    def test_each_rule_of_the_painter_keeps_to_its_ground(self):
        plain = np.zeros((N, N))
        everywhere = np.ones((N, N), bool)
        channel = np.zeros((N, N), bool)
        channel[:, 60:64] = True
        flow = np.where(channel, 500.0, 0.0)
        # running water stays mud in a desert, and is not snowed over where it freezes
        high = np.full((N, N), 100.0)  # (100 studs up: well under freezing at sea 0)
        mud = self.paint(plain, None, flow) == T.ROLES.index("mud")  # (what is running water with no climate)
        self.assertGreater(int(mud.sum()), 100)
        dry = self.paint(plain, "rain=0.05,sea=0.9", flow)
        self.assertEqual(share(dry, mud, "mud"), 1.0)
        self.assertGreater(share(dry, ~channel, "sand"), 0.7)
        frozen = self.paint(high, "rain=0.5,sea=0.0", flow)
        self.assertEqual(share(frozen, mud, "mud"), 1.0)
        self.assertGreater(share(frozen, ~channel, "snow"), 0.95)
        # where the erosion dropped its sediment stays bare ground in wet country (lush does not grow over it)
        deposit = np.where(X < 100, 5.0, 0.0)
        wet = T.paint(plain, CELL, None, deposit, 38, 7, {"climate": cfg("rain=0.9,sea=0.8")})[0]
        self.assertGreater(share(wet, X < 80, "dirt"), 0.6)
        self.assertGreater(share(wet, X > 140, "lush"), 0.6)
        # a hollow is lush by the land's own shape; in dry country it is not (cold here, so it is not bared either)
        d = np.sqrt((X - MID) ** 2 + (Z - MID) ** 2)
        bowl = 40 * np.clip(d / 120, 0, 1) ** 2
        middle = d < 60
        self.assertGreater(share(self.paint(bowl, None), middle, "lush"), 0.3)
        self.assertEqual(share(self.paint(bowl, "rain=0.1,sea=0.25,lapse=0"), middle, "lush"), 0.0)
        # wet and COLD is not lush (nothing flowers just over freezing)
        cold = self.paint(plain, "rain=0.9,sea=0.08")
        self.assertEqual(share(cold, everywhere, "lush"), 0.0)
        # a dry warm slope of 21 degrees is bare ground, not sand (sand lies on flat ground)
        slope21 = X * np.tan(np.radians(21))
        tilted = self.paint(slope21, "rain=0.05,sea=1,lapse=0")
        inner = (X > 40) & (X < 470)
        self.assertEqual(share(tilted, inner, "sand"), 0.0)
        self.assertGreater(share(tilted, inner, "dirt"), 0.9)
        # scree is the land's shape: a climate leaves it scree (dry or wet)
        cliffs = ridge_ns(200, 90)
        a, b = self.paint(cliffs, None), self.paint(cliffs, "rain=0.05,sea=0.9")
        self.assertEqual(float((a == T.ROLES.index("scree")).mean()), float((b == T.ROLES.index("scree")).mean()))

    def test_where_it_freezes_cliffs_stay_and_a_frozen_shore_is_snow(self):
        h = ridge_ns(200, 90) + 100  # (faces of 66 degrees, on land 100 studs up: well under freezing at sea 0)
        warm = self.paint(h, None)
        cold = self.paint(h, "sea=0.0,rain=0.5")
        steep = (np.abs(X - MID) > 10) & (np.abs(X - MID) < 80)
        self.assertEqual(share(warm, steep, "cliff"), share(cold, steep, "cliff"))  # (too steep for snow to lie)
        self.assertGreater(share(cold, np.abs(X - MID) > 100, "snow"), 0.95)  # (the flats are under snow)
        # a shore: sand in a warm land, snow where the land is frozen
        plain = np.full((N, N), 100.0)
        self.assertGreater(share(self.paint(plain, "sea=0.9,lapse=0.1", shore=99), np.ones((N, N), bool), "sand"), 0.9)
        frozen = self.paint(plain, "sea=0.0", shore=99)
        self.assertEqual(share(frozen, np.ones((N, N), bool), "sand"), 0.0)
        self.assertGreater(share(frozen, np.ones((N, N), bool), "snow"), 0.95)

    def test_snow_lies_where_it_freezes_lower_on_the_north_face(self):
        h = ridge_ew(160, 220)  # (faces of 36 degrees: under the slope snow stays on)
        r = self.paint(h, "sea=0.5,lapse=0.4,shade=0.2,rain=0.5")
        snow = r == T.ROLES.index("snow")
        self.assertTrue(snow.any())
        north, south = Z < MID - 8, Z > MID + 8
        lowest_north = float(h[snow & north].min())
        lowest_south = float(h[snow & south].min())
        self.assertLess(lowest_north, lowest_south - 25)  # (the shade: the snowline 25 studs lower and more)
        # the crest is snow, the plain is not
        self.assertGreater(share(r, (Z < MID - 4) & (Z > MID - 60), "snow"), 0.9)  # (the north face under the crest)
        self.assertEqual(share(r, np.abs(Z - MID) > 215, "snow"), 0.0)
        # a warm land has none; a climate's snow takes the place of a typed snowline
        self.assertFalse((self.paint(h, "sea=0.95,lapse=0.2") == T.ROLES.index("snow")).any())
        typed = self.paint(h, "sea=0.95,lapse=0.2", snowline=10)
        self.assertFalse((typed == T.ROLES.index("snow")).any())

    def test_rock_and_cliff_are_the_lands_own_shape_whatever_the_climate(self):
        h = ridge_ns(200, 90)  # (faces of 66 degrees: rock and cliff)
        a = self.paint(h, None)
        b = self.paint(h, "rain=0.05,sea=0.9")
        steep = (np.abs(X - MID) > 10) & (np.abs(X - MID) < 80)
        for role in ("rock", "cliff"):
            self.assertEqual(share(a, steep, role), share(b, steep, role))
        self.assertGreater(share(b, steep, "rock") + share(b, steep, "cliff"), 0.8)


class CommandLine(unittest.TestCase):
    def run_terrain(self, out, *flags):
        res = subprocess.run([sys.executable, TERRAIN, out, "--size", "128", "--step", "4", "--seed", "7", "--relief",
                              "40", "--erosion", "500", "--thermal", "5", "--stream", "20", *flags],
                             capture_output=True, text=True, timeout=300)
        return res

    def test_a_terrain_made_with_a_climate_records_it_and_its_heights_are_the_same_land(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = os.path.join(tmp, "plain.hm.json")
            wet = os.path.join(tmp, "wet.hm.json")
            self.assertEqual(self.run_terrain(plain).returncode, 0)
            res = self.run_terrain(wet, "--climate", "wind=90,rain=0.1,sea=0.9")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            with open(plain, encoding="utf-8") as fh:
                a = json.load(fh)
            with open(wet, encoding="utf-8") as fh:
                b = json.load(fh)
            self.assertNotIn("climate", a)
            self.assertEqual(b["climate"]["wind"], 90.0)
            self.assertEqual(b["climate"]["rain"], 0.1)
            self.assertEqual(b["climate"]["lapse"], T.CLIMATE["lapse"])
            self.assertEqual(a["heights"], b["heights"])  # (the climate paints: it never moves the land)
            self.assertEqual(a["options"], b["options"])  # (the heights' recipe is the same: the route proof re-makes it)
            self.assertNotEqual(a["paint"], b["paint"])
            self.assertGreater(b["paint"].count(str(T.ROLES.index("sand"))), a["paint"].count(str(T.ROLES.index("sand"))))
            # a typed snowline beside a climate is refused (it was thrown away without a word: 80 % snow became none)
            both = os.path.join(tmp, "both.hm.json")
            res = self.run_terrain(both, "--snowline", "40", "--climate", "wind=270")
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("a climate makes its own snowline", res.stdout)
            self.assertFalse(os.path.exists(both))
            # --climate with no words after it is said, not passed over
            res = self.run_terrain(both, "--climate")
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("--climate needs its words", res.stdout)
            res = self.run_terrain(both, "--climate", "")
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("climate is empty", res.stdout)
            # a climate typed wrongly stops the command and writes nothing
            bad = os.path.join(tmp, "bad.hm.json")
            res = self.run_terrain(bad, "--climate", "wnd=90")
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("climate.wnd", res.stdout)
            self.assertFalse(os.path.exists(bad))


if __name__ == "__main__":
    unittest.main()
