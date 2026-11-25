"""kit ui letter: the persona style mixes faces per glyph and outlines the WORD; the round outline grows by its width"""
import importlib.util
import os
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_letter", os.path.join(HERE, "..", "..", "ui", "letter.py"))
letter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(letter)


class TestLetter(unittest.TestCase):
    def test_dilate_grows_a_dot_by_its_width(self):
        a = Image.new("L", (101, 101), 0)
        a.putpixel((50, 50), 255)
        grown = np.array(letter.dilate(a, 10)) > 127
        ys, xs = np.where(grown)
        self.assertAlmostEqual(xs.max() - xs.min(), 20, delta=2)
        self.assertAlmostEqual(ys.max() - ys.min(), 20, delta=2)

    def test_the_persona_pool_is_several_distinct_faces(self):
        families = {f for f, _, _ in letter.PERSONA_POOL}
        self.assertGreaterEqual(len(families), 5)

    def test_cut_card_is_a_closed_polygon_around_the_box(self):
        pts = letter.cut_card(200, 100, 3, depth=12)
        self.assertGreaterEqual(len(pts), 8)
        xs = [p[0] for p in pts]
        self.assertLess(min(xs), 40)
        self.assertGreater(max(xs), 160)


    def test_drips_run_off_a_glyph_bottom_and_grow_with_their_phase(self):
        import argparse
        import random
        fm = Image.new("L", (300, 400), 0)
        fm.paste(255, (50, 40, 250, 200))  # a square 'glyph' fill, bottom at y 199
        glyphs = [{"x": 40, "w": 200, "dy": 0}]
        def run(phase):
            a = argparse.Namespace(drip=0.5, drip_share=1.0, drip_phase=phase, outline=0.06)
            return np.array(letter.drip_mask(fm, glyphs, 10, 200, a, random.Random(4))) > 127
        full, half, none = run(1.0), run(0.5), run(0.0)
        self.assertFalse(none.any())                                    # phase 0: the ink has not run yet
        low = lambda m: np.nonzero(m.any(axis=1))[0].max()
        self.assertGreater(low(full), 199 + 40)                          # it runs well below the glyph
        self.assertGreater(low(full), low(half))                         # and further the later the phase
        cols = np.nonzero(full[215:].any(axis=0))[0]
        self.assertTrue(cols.size and cols.min() >= 50 and cols.max() <= 250)   # from under the glyph, not beside it
        self.assertGreaterEqual(cols.max() - cols.min() + 1, int(2.2 * 0.06 * 200) - 2)  # fatter than a pin

    def test_a_drip_flipbook_keeps_one_size_and_phase_0_paints_no_stray_ink(self):
        import sys
        import tempfile
        sys.path.insert(0, os.path.join(HERE, "..", "..", "ui"))
        if not letter.font_file("fredoka"):
            self.skipTest("fredoka is not in the font cache")
        with tempfile.TemporaryDirectory() as d:
            sizes = []
            for k, ph in enumerate((0.0, 0.5, 1.0)):
                letter.main(["t/p%d" % k, "--text", "SPLAT", "--font", "fredoka", "--drip", "0.6", "--drip-share", "1",
                             "--drip-phase", str(ph), "--art", d])
                with Image.open(os.path.join(d, "t", "p%d.png" % k)) as im:
                    sizes.append(im.size)
                    if ph == 0.0:
                        corner = np.array(im.getchannel("A"))[:12, :12]
                        self.assertEqual(int(corner.max()), 0)           # no quarter-disc of ink in the corner
            self.assertEqual(len(set(sizes)), 1, sizes)                   # every phase the same canvas

    def test_an_arc_arches_the_word_up_and_a_negative_one_sags(self):
        import tempfile
        if not letter.font_file("luckiestguy"):
            self.skipTest("luckiestguy is not in the font cache")
        with tempfile.TemporaryDirectory() as d:
            tops = {}
            for name, arc in (("up", 40), ("sag", -30)):
                letter.main([f"t/{name}", "--text", "BRASS BRAWL", "--font", "luckiestguy", "--size", "120", "--arc", str(arc), "--lean", "0", "--art", d])
                with Image.open(os.path.join(d, "t", f"{name}.png")) as im:
                    a = np.array(im.getchannel("A")) > 128
                cols = np.nonzero(a.any(0))[0]
                top = [int(np.nonzero(a[:, c])[0].min()) for c in cols]
                n = len(top)
                tops[name] = (np.median(top[: n // 8]), np.median(top[n * 7 // 16: n * 9 // 16]), np.median(top[-n // 8:]))
            l, m, r = tops["up"]
            self.assertTrue(m < l - 20 and m < r - 20, tops["up"])      # the middle rides high
            l, m, r = tops["sag"]
            self.assertTrue(m > l + 8 and m > r + 8, tops["sag"])       # the middle sags

    def test_an_inline_runs_inside_the_fill(self):
        import tempfile
        if not letter.font_file("luckiestguy"):
            self.skipTest("luckiestguy is not in the font cache")
        with tempfile.TemporaryDirectory() as d:
            letter.main(["t/i", "--text", "O", "--font", "luckiestguy", "--size", "200", "--fill", "#000080", "--ink", "#000000",
                         "--shadow", "0", "--lean", "0", "--inline", "#ff0000", "--art", d])
            with Image.open(os.path.join(d, "t", "i.png")) as im:
                a = np.array(im.convert("RGBA")).astype(int)
        red = (a[..., 0] > 180) & (a[..., 1] < 80) & (a[..., 2] < 80) & (a[..., 3] > 200)
        self.assertGreater(int(red.sum()), 50)                                  # the line is drawn
        ys, xs = np.nonzero(red)
        ink = (a[..., 3] > 200) & (a[..., :3].sum(-1) < 40)
        # every inline pixel sits inside the glyph: ink (the outline) lies further out on its row
        for y, x in list(zip(ys, xs))[::25]:
            self.assertTrue(ink[y, :x].any() and ink[y, x:].any())

    def test_an_upright_face_is_picked_over_its_italic_twin(self):
        # (EBGaramond-Italic[wght].ttf sorts before EBGaramond[wght].ttf: YOU DIED came out slanted — 2026-10-16)
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fam = os.path.join(d, "fam")
            os.makedirs(fam)
            for f in ("Face-Italic[wght].ttf", "Face[wght].ttf"):
                open(os.path.join(fam, f), "wb").close()
            old = letter.F.fonts_dir
            letter.F.fonts_dir = lambda: d
            try:
                self.assertEqual(os.path.basename(letter.font_file("fam")), "Face[wght].ttf")
            finally:
                letter.F.fonts_dir = old

    def test_a_glow_is_a_soft_halo_outside_the_glyphs(self):
        import tempfile
        if not letter.font_file("luckiestguy"):
            self.skipTest("luckiestguy is not in the font cache")
        with tempfile.TemporaryDirectory() as d:
            common = ["--text", "I", "--font", "luckiestguy", "--size", "160", "--fill", "#ffffff", "--ink", "#000000",
                      "--outline", "0", "--shadow", "0", "--lean", "0", "--art", d]
            letter.main(["t/plain"] + common)
            letter.main(["t/glow"] + common + ["--glow", "#ff0000", "--glow-px", "0.15", "--glow-alpha", "0.7"])
            with Image.open(os.path.join(d, "t", "plain.png")) as p, Image.open(os.path.join(d, "t", "glow.png")) as g:
                pa, ga = np.array(p.convert("RGBA")).astype(int), np.array(g.convert("RGBA")).astype(int)
        self.assertGreater(ga.shape[1], pa.shape[1] + 20)                         # the halo widens the piece
        soft = (ga[..., 3] > 10) & (ga[..., 3] < 200) & (ga[..., 0] > ga[..., 1] + 60)
        self.assertGreater(int(soft.sum()), 200)                                  # a red, half-clear halo
        self.assertGreater(int(((ga[..., :3].min(-1) > 230) & (ga[..., 3] > 240)).sum()), 50)  # the white glyph on top

    def test_a_glyph_set_shares_one_cell_and_one_baseline(self):
        import json as _json
        import tempfile
        if not letter.font_file("oswald"):
            self.skipTest("oswald is not in the font cache")
        with tempfile.TemporaryDirectory() as d:
            letter.main(["n/dg", "--text", "0", "--font", "oswald", "--size", "120", "--shadow", "0", "--lean", "0", "--glyphs", "018:", "--art", d])
            side = _json.load(open(os.path.join(d, "n", "dg.glyphs.json")))
            sizes, bottoms = set(), []
            for code in ("0", "1", "8"):
                with Image.open(os.path.join(d, "n", f"dg_{code}.png")) as im:
                    sizes.add(im.size)
                    a = np.array(im.getchannel("A")) > 128
                    bottoms.append(int(np.nonzero(a.any(1))[0].max()))
            self.assertTrue(os.path.isfile(os.path.join(d, "n", "dg_u58.png")))   # (':' by its code point)
        self.assertEqual(len(sizes), 1)                                           # one cell for every glyph
        self.assertLessEqual(max(bottoms) - min(bottoms), 4)                      # one baseline (round glyphs overshoot a little)
        self.assertAlmostEqual(side["aspect"], side["cell"][0] / side["cell"][1], places=3)

    def test_widen_extends_the_face_across_not_up(self):
        import json as _json
        import tempfile
        if not letter.font_file("oswald"):
            self.skipTest("oswald is not in the font cache")
        with tempfile.TemporaryDirectory() as d:
            common = ["--text", "08", "--font", "oswald", "--size", "120", "--shadow", "0", "--lean", "0", "--art", d]
            letter.main(["w/plain"] + common)
            letter.main(["w/wide"] + common + ["--widen", "1.4"])
            with Image.open(os.path.join(d, "w", "plain.png")) as p, Image.open(os.path.join(d, "w", "wide.png")) as w:
                (pw, ph), (ww, wh) = p.size, w.size
            side = _json.load(open(os.path.join(d, "w", "wide.letter.json")))
        self.assertAlmostEqual(ww / pw, 1.4, delta=0.06)   # wider by the factor
        self.assertLessEqual(abs(wh - ph), 2)                 # not taller
        self.assertEqual(side["widen"], 1.4)                  # the sidecar remembers it

if __name__ == "__main__":
    unittest.main()
