"""a.cutout through a REAL build (kit/selftest/blender/build_cutout.py): the colour map of the cut group carries
the alpha, the manifest marks the group for Roblox's cut-out mode, the build says how much of each map is cut."""

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
OUT = os.path.join("build", "_test_cutout")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(ROOT, "kit", "selftest", "blender", "build_cutout.py"), "--",
                            "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
        assert line, (r.stderr or r.stdout)[-800:]
        cls.v = json.loads(line)
        with open(os.path.join(ROOT, OUT, "models", "_selftest_cutout.manifest.json"), encoding="utf-8") as fh:
            cls.manifest = json.load(fh)

    def test_the_build_passes_and_says_what_it_cut(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        cut = {r["part"]: r["cut"] for r in self.v["facts"]["cutouts"]["cut"]}
        self.assertAlmostEqual(cut["Grille"], 0.50, delta=0.04)          # six bars and a frame of a 1.2 x 1.0 sheet
        self.assertAlmostEqual(cut["Leaf"], 0.35, delta=0.04)            # a pointed oval of a 1.0 x 0.5 sheet
        self.assertAlmostEqual(cut["Sign"], 1 - 3.14159 * 30.0 ** 2 / 64 ** 2, delta=0.04)   # a disc of a square
        said = self.v["summary"][self.v["summary"].index("cut out: "):]
        self.assertTrue(said.startswith("cut out: Grille 5"), said[:60])
        self.assertIn(", Leaf 3", said[:60])
        self.assertIn(", Sign 3", said[:60])

    def test_only_the_cut_group_is_marked_for_the_cut_out_mode(self):
        groups = self.manifest["groups"]
        self.assertEqual(groups["cut"].get("alpha_mode"), "Transparency")
        self.assertNotIn("alpha_mode", groups["main"])
        self.assertEqual(groups["cut"]["transparency"], 0.0)             # (the part itself stays opaque: a hard cut)

    def test_the_colour_map_carries_the_alpha(self):
        from PIL import Image  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        name = self.manifest["groups"]["cut"]["textures"]["color"]
        self.assertTrue(name.endswith("_color_cut.png"), name)            # beside the bake's own, never over it
        plain = Image.open(os.path.join(ROOT, name[:-len("_cut.png")] + ".png"))
        self.assertTrue(plain.mode == "RGB" or np.array(plain)[..., 3].min() == 255)
        cut = np.array(Image.open(os.path.join(ROOT, name)))
        self.assertEqual(cut.shape[2], 4)
        self.assertTrue((cut[..., :3] == np.array(plain.convert("RGB"))).all())   # the colour: bit for bit
        a = cut[..., 3]
        self.assertEqual(sorted(np.unique(a).tolist()), [0, 255])        # a hard cut: nothing in between
        self.assertGreater(float((a == 0).mean()), 0.05)
        self.assertGreater(int(cut[..., :3][a == 255].max()), 20)        # ... and the colour is still there
        main = Image.open(os.path.join(ROOT, self.manifest["groups"]["main"]["textures"]["color"]))
        self.assertTrue(main.mode == "RGB" or np.array(main)[..., 3].min() == 255)


if __name__ == "__main__":
    unittest.main()
