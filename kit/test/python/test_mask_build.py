"""A mask the author places, through REAL builds (kit/selftest/blender/build_mask.py and its unplaced twin; the 3D
methods audit, S3): the baked colour under points of the surface - gold in the stripe all the way round, rust in the
stain, plain paint elsewhere - the mesh's own maps written out, and a layer naming a mask nobody placed stops the
build by name."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_mask_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


def is_gold(c):
    return c[0] > 0.8 and c[1] > 0.7 and c[2] < 0.5


def is_paint(c):
    return c[1] > c[0] + 0.2 and c[1] > c[2] + 0.15


def is_rust(c):
    return c[0] > c[1] + 0.15 and c[0] > c[2] + 0.25 and c[0] < 0.8


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = run("build_mask.py")
        line = next((x for x in r.stdout.splitlines() if x.startswith("MASK ")), None)
        assert line, (r.stderr or r.stdout)[-800:]
        cls.at = json.loads(line[5:])
        cls.v = json.loads(next(x for x in reversed(r.stdout.splitlines())
                                if x.startswith("{") and '"status"' in x))
        cls.bad = run("build_mask_unplaced.py")
        again = run("build_mask.py")                # the same build once more: its maps come from the bake's cache
        cls.again = json.loads(next(x for x in reversed(again.stdout.splitlines())
                                    if x.startswith("{") and '"status"' in x))

    def test_the_stripe_is_gold_all_the_way_round_and_the_paint_elsewhere_is_paint(self):
        for where in ("stripe_front", "stripe_back", "stripe_side"):
            self.assertTrue(is_gold(self.at[where]), (where, self.at[where]))
        for where in ("plain_front", "plain_top"):
            self.assertTrue(is_paint(self.at[where]), (where, self.at[where]))

    def test_the_stain_is_rust_where_the_picture_puts_it_and_goes_straight_through(self):
        self.assertTrue(is_rust(self.at["stain_front"]), self.at["stain_front"])
        self.assertTrue(is_rust(self.at["stain_back"]), self.at["stain_back"])       # (said on the page)
        self.assertFalse(is_rust(self.at["plain_front"]))

    def test_the_build_says_how_much_of_the_surface_each_mask_is_on(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        masks = self.v["facts"]["masks"]["main"]
        # the stripe: half a stud of a 3-stud block's four sides (4 x 3 x 2 studs: sides 36 of 52 studs2) = 11.5%
        self.assertAlmostEqual(masks["stripe"]["on"], 0.5 * 12.0 / 52.0, delta=0.02)
        # the stain: a disc about 1.3 studs across on the front and on the back
        self.assertAlmostEqual(masks["stain"]["on"], 0.04, delta=0.02)
        self.assertIn("masks: stain on", self.v["summary"])
        rows = {r["where"]: r for r in self.v["facts"]["layers"]["main"]["paint"]}
        self.assertAlmostEqual(rows["mask:stripe"]["covered"], masks["stripe"]["on"], delta=0.03)
        self.assertIn('gold on the mask "stripe" 100%', self.v["summary"])

    def test_a_build_taken_from_the_cache_still_says_its_masks(self):
        # (found by running this file twice: the second build read its maps from the cache and said nothing)
        self.assertEqual(self.again["facts"]["masks"], self.v["facts"]["masks"])
        self.assertIn("masks: stain on", self.again["summary"])

    def test_the_meshs_own_maps_are_written_and_named(self):
        maps = self.at["mesh_maps"]
        self.assertEqual(sorted(maps), ["curvature", "material_id", "occlusion"])
        for path in maps.values():
            self.assertTrue(os.path.isfile(os.path.join(ROOT, path)), path)
        from PIL import Image  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        curv = np.asarray(Image.open(os.path.join(ROOT, maps["curvature"])).convert("L"), float) / 255.0
        self.assertAlmostEqual(float(np.median(curv)), 0.5, delta=0.03)              # a block is mostly flat
        self.assertGreater(float(curv.max()), 0.7)                                   # ... with outer edges

    def test_a_layer_naming_a_mask_nobody_placed_stops_the_build_by_name(self):
        self.assertNotEqual(self.bad.returncode, 0)
        said = self.bad.stderr + self.bad.stdout
        self.assertIn('no a.mask("stain"', said)
        self.assertNotIn("Cycles device", said)       # said before anything is baked
        self.assertIn("the model\'s masks: stripe", said)


if __name__ == "__main__":
    unittest.main()
