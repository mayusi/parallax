"""A tile and a stylised look, through REAL builds (kit/selftest/blender/build_tile.py and its twins; the 3D methods
audit, stage X): a tile's maps repeat both ways and its manifest names what a MaterialVariant takes; a map that
does not repeat fails; the painted light is in the colour map as flat tones on a matt surface; metal stops."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_tile_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


def verdict(r):
    got = next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x)
    return json.loads(got)   # (strict: the kit reads this line the same way)


def line(r, word):
    got = next((x for x in r.stdout.splitlines() if x.startswith(word + " ")), None)
    assert got, (r.stderr or r.stdout)[-800:]
    return json.loads(got[len(word) + 1:])


def check(v, name):
    return next(c for g in v["groups"].values() for c in g["checks"] if c["name"] == name)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Tile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_tile.py")
        cls.v = verdict(cls.good)
        cls.ramp = verdict(run("build_tile_ramp.py"))

    def test_the_maps_as_written_repeat_both_ways(self):
        import numpy as np  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        import rbx_tile  # noqa: PLC0415

        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        self.assertTrue(check(self.v, "tile_seam")["ok"])
        tile = line(self.good, "TILE")
        self.assertEqual(tile["studs"], 8.0)
        self.assertEqual(sorted(tile["maps"]), ["color", "metal", "normal", "rough"])
        # the file itself, read here: its left edge meets its right and its top its bottom
        path = os.path.join(ROOT, OUT, "models", "textures", tile["maps"]["color"])
        px = np.asarray(Image.open(path).convert("RGB"), float) / 255.0
        found = rbx_tile.steps(px)
        self.assertLess(found["u"]["step"], rbx_tile.TILE_BAR)
        self.assertLess(found["v"]["step"], rbx_tile.TILE_BAR)
        self.assertIn("tile: 8 studs a tile, repeats both ways", self.v["summary"])

    def test_a_map_that_does_not_repeat_fails(self):
        self.assertEqual(self.ramp["status"], "fail")
        c = check(self.ramp, "tile_seam")
        self.assertFalse(c["ok"])
        self.assertIn("does not repeat left to right", c["fix"])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Stylised(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_tile_ball.py")
        cls.v = verdict(cls.good)
        cls.again = verdict(run("build_tile_ball.py"))       # (its maps from the bake's cache)
        cls.metal = run("build_tile_metal.py")
        cls.unlit = verdict(run("build_tile_unlit.py"))

    def test_the_light_is_painted_into_the_colour_in_flat_tones_and_the_surface_is_matt(self):
        at = line(self.good, "STYLE")
        self.assertGreater(at["top"], 2.0 * at["under"])              # lit above, the shade below
        self.assertLessEqual(at["peaks"], 5)                          # three tones (and the bins they straddle)
        self.assertGreaterEqual(at["peaks"], 2)
        self.assertAlmostEqual(at["rough"], 0.9, delta=0.03)
        said = self.v["facts"]["stylised"]["main"][0]
        self.assertEqual((said["bands"], said["tones"], said["darkest"]), (3, 3, 0.4))
        self.assertIn("stylised: main all in 3 flat tones (lit ", self.v["summary"])
        # read off the written colour map: a shade of 0.4 is 0.665 as sRGB - the lit tone 1.5 times it
        self.assertAlmostEqual(said["lit_over_shade"], 1.5, delta=0.15)
        self.assertTrue(check(self.v, "stylised")["ok"])

    def test_a_look_that_never_reached_the_map_fails(self):
        self.assertEqual(self.unlit["status"], "fail")
        c = check(self.unlit, "stylised")
        self.assertFalse(c["ok"])
        self.assertIn("the light is not in the map", c["fix"])

    def test_a_cached_build_says_the_same(self):
        self.assertEqual(self.again["facts"]["stylised"], self.v["facts"]["stylised"])

    def test_a_metal_material_stops_the_build(self):
        self.assertNotEqual(self.metal.returncode, 0)
        self.assertIn('stylise: the material "clay" is metal', self.metal.stderr + self.metal.stdout)


if __name__ == "__main__":
    unittest.main()
