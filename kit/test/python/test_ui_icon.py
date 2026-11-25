"""kit ui icon: finding icons by name, styling a mask (fill, ink rim, glow), the CC BY credit line"""
import importlib.util
import os
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_icon", os.path.join(HERE, "..", "..", "ui", "icon.py"))
icon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(icon)


class TestIcon(unittest.TestCase):
    def test_style_puts_the_fill_inside_and_the_ink_rim_around(self):
        m = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(m).ellipse([30, 30, 70, 70], fill=(255, 255, 255, 255))
        out = icon.style(m, (240, 200, 140, 255), (10, 10, 10, 255), outline=5)
        self.assertEqual(out.getpixel((50, 50))[:3], (240, 200, 140))   # the fill inside
        self.assertEqual(out.getpixel((50, 27))[:3], (10, 10, 10))      # the ink rim just outside the shape
        self.assertEqual(out.getpixel((5, 5))[3], 0)                    # clear far outside

    def test_the_credit_names_author_and_licence(self):
        line = icon.credit_line("lorc", "trident", "ic_poseidon")
        self.assertIn("Lorc", line)
        self.assertIn("CC BY 3.0", line)
        self.assertIn("CC0", icon.credit_line("viscious-speed", "x", "p"))

    def test_a_remade_piece_replaces_its_credit_in_the_files_columns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            prov = os.path.join(d, "PROVENANCE.md")
            open(prov, "w", encoding="utf-8").write("# x\n\n| file | how | seed |\n|---|---|---|\n| pearl_lit | FLUX.2 render | 7 |\n| other | drawn | - |\n")
            icon.write_credit(prov, "x", "pearl_lit", icon.credit_line("lorc", "trident", "pearl_lit"))
            text = open(prov, encoding="utf-8").read()
            self.assertNotIn("FLUX.2", text)                       # the old (generated-art) row is gone
            row = [ln for ln in text.splitlines() if ln.startswith("| pearl_lit |")][0]
            self.assertEqual(row.count("|"), 4)                    # three columns, like the file
            self.assertIn("| other | drawn | - |", text)          # other rows untouched

    def test_find_ranks_whole_words_first(self):
        if not os.path.isdir(icon.ICONS):
            self.skipTest("the icon set is not cached here")
        hits = icon.find("trident", 5)
        self.assertIn(("lorc", "trident"), hits)

    def test_a_bare_name_is_an_artists_icon_not_a_badge(self):
        # (crown / shield / coins / fire resolved to the "badges" set and rendered as white discs — audit 2026-10-16)
        old = icon.index
        icon.index = lambda: [("badges", "crown"), ("lorc", "crown"), ("badges", "medal")]
        try:
            self.assertEqual(icon.locate("crown")[0], "lorc")
            self.assertEqual(icon.locate("medal")[0], "badges")          # only a badge: still found
        finally:
            icon.index = old


if __name__ == "__main__":
    unittest.main()
