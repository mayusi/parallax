"""kit vfx refs lore: wikitext becomes prose, variant TABLES become sentences, facts are tagged, off-topic pages filtered"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))  # lore imports refkit's helpers
_spec = importlib.util.spec_from_file_location("kit_vfx_lore", os.path.join(HERE, "..", "..", "vfx", "lore.py"))
lore = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lore)

TABLE = """=== Variations===
{| style="{{Radius|7px}} width:100%;" border="1"
! style="color:#FFFFFF" |'''Variant'''
! style="color:#FFFFFF" |'''Description'''
|-
{{!}} style="background-color: #000000; color:#FFF"{{!}}[[Image:Getsuga.gif|150px]]
{{!}} style="background-color: #000000; color:#FFF"{{!}}'''Black Getsuga Tenshō'''
{{!}} style="background-color: #000000; color:#FFF"{{!}}In [[Bankai]], the Getsuga Tenshō is black, and possesses explosively augmented power and speed.<ref>manga</ref>
{{!}} style="background-color: #000000; color:#FFF"{{!}}[[Ichigo Kurosaki]]
|}
"""


class TestLore(unittest.TestCase):
    def test_markup_is_stripped(self):
        got = lore.clean("The '''[[Zanpakutō|sword]]''' fires a {{nihongo|wave}} forward.<ref>ch. 1</ref> [[File:x.png|thumb]]")
        self.assertEqual(got.strip(), "The sword fires a  forward.")

    def test_a_variant_table_row_becomes_one_sentence(self):
        secs = dict(lore.sections(lore.clean(TABLE)))
        body = secs["Variations"]
        self.assertIn("Black Getsuga Tenshō: In Bankai, the Getsuga Tenshō is black, and possesses explosively augmented power and speed.", body)
        self.assertNotIn("style=", body)
        self.assertNotIn("Image:", body)

    def test_sections_split_on_headings(self):
        secs = lore.sections("intro text\n==Description==\nbody one\n===Variations===\nbody two\n")
        self.assertEqual([t for t, _ in secs], ["Intro", "Description", "Variations"])

    def test_tags_find_visual_facts(self):
        import re

        sent = "A massive black crescent wave flies forward."
        tags = [t for t, rx in lore.TAGS.items() if re.search(rx, sent, re.I)]
        for t in ("colour", "shape", "scale", "motion"):
            self.assertIn(t, tags)

    def test_fold_matches_macrons(self):
        self.assertIn("tensho", lore.fold("Getsuga Tenshō"))


_rk = importlib.util.spec_from_file_location("kit_vfx_refkit", os.path.join(HERE, "..", "..", "vfx", "refkit.py"))
refkit = importlib.util.module_from_spec(_rk)
_rk.loader.exec_module(refkit)


class TestHasLore(unittest.TestCase):
    """a breakdown measures <set>_scene while the lore is filed as <set>: refs measure must not cry NO LORE (2026-10-22)"""

    def test_scene_frames_find_the_sets_lore(self):
        import tempfile

        old = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                os.makedirs("assets/effects/refs_measured")
                open("assets/effects/refs_measured/t_set.lore.json", "w").write("{}")
                self.assertTrue(refkit.has_lore("t_set"))
                self.assertTrue(refkit.has_lore("t_set_scene"))
                self.assertFalse(refkit.has_lore("other_scene"))
                self.assertFalse(refkit.has_lore("t_se"))
            finally:
                os.chdir(old)


class TestLoreCitations(unittest.TestCase):
    """refs norms rule 5: the generator must QUOTE lore facts; short generic phrases are not citations"""

    def run_in(self, docstring):
        import json
        import tempfile

        old = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                os.makedirs("assets/effects/generators")
                os.makedirs("assets/effects/refs_measured")
                facts = [{"text": "The hands are then thrust forward to shoot out a streaming, powerful beam of energy."},
                         {"text": "Vivid light blue is its standard and original color."}]
                json.dump({"facts": facts}, open("assets/effects/refs_measured/t_set.lore.json", "w"))
                open("assets/effects/generators/g.py", "w", encoding="utf-8").write('"""' + docstring + ' (refs_measured/t_set.brief.md)"""\nx = "the hands are then" + "y"\n')
                return refkit.lore_citations({"about": "made by assets/effects/generators/g.py"})
            finally:
                os.chdir(old)

    def test_generic_phrases_repeated_do_not_count(self):
        st, cited, n = self.run_in('"the hands are then" "the hands are then" "standard and original"')
        self.assertEqual((st, cited, n), ("t_set", 0, 2))

    def test_real_quotes_count_once_each_even_wrapped(self):
        st, cited, _ = self.run_in('"The hands are then thrust forward to shoot out a\n    streaming, powerful beam" and “Vivid light blue is its standard and original color.”'
                                   ' twice: "Vivid light blue is its standard and original color."')
        self.assertEqual(cited, 2)


sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import silhouette  # noqa: E402


class TestSilhouette(unittest.TestCase):
    def flame(self, tongues):
        """an orange flame on black: a tall body with `tongues` sharp tips on top, away from the picture's edges"""
        import numpy as np
        from PIL import Image, ImageDraw

        im = Image.new("RGB", (240, 180), (0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([90, 70, 150, 165], fill=(255, 150, 20))
        for i in range(tongues):
            x = 90 + 60 * (i + 0.5) / tongues
            d.polygon([(x - 30 / tongues, 72), (x, 20), (x + 30 / tongues, 72)], fill=(255, 150, 20))
        arr = np.asarray(im).astype(int)
        noise = np.random.default_rng(1).integers(-25, 25, arr.shape)  # texture, so the flat-region filter keeps it
        return Image.fromarray(np.clip(arr + noise * (arr > 0), 0, 255).astype("uint8"))

    def test_tall_flame_with_three_tips(self):
        got = silhouette.silhouette(self.flame(3), (20, 45))
        self.assertIsNotNone(got)
        self.assertGreater(got["aspect"], 1.5)
        self.assertEqual(got["tips"], 3)
        self.assertLess(got["taper"], 1.0)

    def test_a_shape_cut_by_the_frame_is_not_measured(self):
        from PIL import Image

        im = Image.new("RGB", (240, 180), (255, 150, 20))
        self.assertIsNone(silhouette.silhouette(im, (20, 45)))


class TestBareMesh(unittest.TestCase):
    """refs norms rule 6: a big, untextured, hard-edged, opaque mesh reads as plastic (the Rasengan's old air ribbons)"""

    def test_the_old_solid_ribbon_is_bare(self):
        el = {"kind": "mesh", "shape": "spiral", "material": "Neon", "params": {"radius": 1, "width": 0.12},
              "transparency": [[0, 0.15], [1, 1]], "scale": [[0, [1, 2, 1]], [1, [4.4, 12, 4.4]]]}
        self.assertTrue(refkit.bare_mesh(el))

    def test_texture_fade_small_or_lines_are_fine(self):
        base = {"kind": "mesh", "shape": "tube", "transparency": [[0, 0.1], [1, 1]], "scale": [[0, [3, 9, 3]], [1, [3, 9, 3]]]}
        self.assertFalse(refkit.bare_mesh(dict(base, texture="wind_streaks_v")))
        self.assertFalse(refkit.bare_mesh(dict(base, params={"fadeOut": 0.4})))
        self.assertFalse(refkit.bare_mesh(dict(base, scale=[[0, [0.5, 0.5, 0.5]], [1, [1, 1, 1]]])))
        self.assertFalse(refkit.bare_mesh(dict(base, shape="bolt")))
        self.assertFalse(refkit.bare_mesh(dict(base, transparency=[[0, 0.7], [1, 1]])))
        self.assertFalse(refkit.bare_mesh({"kind": "sprite", "texture": None}))


if __name__ == "__main__":
    unittest.main()
