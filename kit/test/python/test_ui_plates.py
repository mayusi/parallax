"""kit/ui/plates.py: an identity's plates are drawn from its shape language — every plate exists, is RGBA, has the
size its manifest says, every 9-slice centre sits inside the image, the colours are the identity's (a frame's line
is its gold, not white), and a plate override changes only that plate."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ui"))

# loaded under its own name: the kit's tests share one process
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("kit_ui_plates", os.path.join(HERE, "..", "..", "ui", "plates.py"))
plates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plates)

IDENTITY = {
    "name": "t",
    "shape": {"line": "#9a8350", "line2": "#3e3219", "fill": "#0a0908", "fill_alpha": 0.9, "width": 2, "corner": "flourish"},
    "plates": {"slot": {"line": "#ff0000"}},
}


def dominant_opaque(img):
    """the most common solid colour of an RGBA image (the fill is 0.86-0.9 alpha: solid enough to count)"""
    counts = {}
    for px in img.getdata():
        if px[3] > 200:
            counts[px[:3]] = counts.get(px[:3], 0) + 1
    return max(counts, key=counts.get) if counts else None


class TestPlates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.meta = plates.draw_identity(IDENTITY, cls.tmp)

    def test_every_plate_exists_rgba_at_its_manifest_size(self):
        from PIL import Image
        for name, (kind, size, slice_) in plates.PLATES.items():
            path = os.path.join(self.tmp, name + ".png")
            self.assertTrue(os.path.isfile(path), name)
            im = Image.open(path)
            self.assertEqual(im.mode, "RGBA", name)
            self.assertEqual(im.size, tuple(size), name)
            m = self.meta[name]
            declared = (m["size"], m["size"]) if isinstance(m["size"], int) else tuple(m["size"])
            self.assertEqual(im.size, declared, name)

    def test_cut_shapes_are_designed_not_noise(self):
        # a scissor-cut outline is a few long straight runs with sharp corners; a torn one is a per-point wobble.
        # the cut family must keep far fewer points than the torn one for the same box (design, not noise)
        cut = plates._cut_pts(960, 540, 7, 60, cuts_per_edge=2)
        torn = plates._jagged(960, 540, 7, 30, n_per_edge=16)
        self.assertLess(len(cut), len(torn) / 2)
        self.assertGreaterEqual(len(cut), 8)
        for name in ("cut", "cut_b", "cut_c", "cut_black", "cut_field", "cut_strip"):
            self.assertIn(name, plates.KINDS)
            self.assertIn(name, plates.PLATES)

    def test_nine_slice_centres_sit_inside_the_image(self):
        for name, (kind, size, slice_) in plates.PLATES.items():
            if slice_ is None:
                continue
            l, t, r, b = slice_
            self.assertTrue(0 < l < r < size[0], name)
            self.assertTrue(0 <= t < b <= size[1], name)
            self.assertEqual(self.meta[name]["slice"], slice_)

    def test_art_json_lists_every_plate(self):
        with open(os.path.join(self.tmp, "art.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        # every plate is listed; anything else is an entry the step DERIVES and marks (an atlas sheet the small pieces
        # were packed into, kit/ui/atlas.py, or a glint of a plate) - an unmarked extra entry still fails
        self.assertTrue(set(plates.PLATES) <= set(meta), set(plates.PLATES) - set(meta))
        for name in set(meta) - set(plates.PLATES):
            entry = meta[name]
            self.assertTrue(entry.get("atlas_sheet") or entry.get("glint_of"), f"unexpected art.json entry {name}")

    def test_frame_is_drawn_in_the_identity_colours(self):
        from PIL import Image
        im = Image.open(os.path.join(self.tmp, "frame.png")).convert("RGBA")
        fill = dominant_opaque(im)
        self.assertIsNotNone(fill)
        # the fill is the identity's ink (dark), and the gold line is present somewhere on the outline
        self.assertLess(sum(fill), 60, f"frame fill should be near-black ink, got {fill}")
        gold = plates.hex_rgb("#9a8350")
        found = any(abs(px[0] - gold[0]) < 40 and abs(px[1] - gold[1]) < 40 and abs(px[2] - gold[2]) < 40 and px[3] > 200
                    for px in im.getdata())
        self.assertTrue(found, "no gold line pixels: the frame ignored shape.line")

    def test_a_plate_override_changes_only_that_plate(self):
        from PIL import Image
        slot = Image.open(os.path.join(self.tmp, "slot.png")).convert("RGBA")
        red = any(px[0] > 200 and px[1] < 80 and px[2] < 80 and px[3] > 200 for px in slot.getdata())
        self.assertTrue(red, "slot override line=#ff0000 did not reach the slot")
        frame = Image.open(os.path.join(self.tmp, "frame.png")).convert("RGBA")
        red_in_frame = any(px[0] > 200 and px[1] < 80 and px[2] < 80 and px[3] > 200 for px in frame.getdata())
        self.assertFalse(red_in_frame, "the slot override leaked into the frame")

    def test_grain_tiles_and_band_fades_at_both_edges(self):
        from PIL import Image
        grain = Image.open(os.path.join(self.tmp, "grain.png")).convert("RGBA")
        alphas = [px[3] for px in grain.getdata()]
        self.assertGreater(max(alphas) - min(alphas), 40, "grain should vary")
        band = Image.open(os.path.join(self.tmp, "band.png")).convert("RGBA")
        top, mid, bottom = band.getpixel((0, 0))[3], band.getpixel((0, band.height // 2))[3], band.getpixel((0, band.height - 1))[3]
        self.assertLess(top, 20)
        self.assertLess(bottom, 20)
        self.assertGreater(mid, 200)


CHUNKY = {
    "name": "c",
    "tokens": {"good": "#4cd964", "rarity_epic": "#b26bff", "rarity_common": "#9aa5b1"},
    "shape": {"line": "#1b2a4a", "fill": "#fff8ea", "fill2": "#ffffff", "width": 5, "corner": "round", "gloss": 0.32,
              "shade": 0.16, "card": "#fff8ea", "buttons": ["good", "nope"]},
}


class TestChunkyPlates(unittest.TestCase):
    """the v3 family: bubbles, pills, badges, cards, banners, the chunky track, gloss, burst, close, plus - and
    the colour variants per shape.buttons token and per rarity_* token"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.meta = plates.draw_identity(CHUNKY, cls.tmp)

    def test_every_chunky_kind_is_drawn_for_any_identity(self):
        for name in ("bubble", "pill", "badge", "card", "banner", "track_chunky", "gloss", "burst", "close", "plus", "check", "slant"):
            self.assertIn(name, self.meta, name)
            self.assertTrue(os.path.exists(os.path.join(self.tmp, f"{name}.png")), name)

    def test_colour_variants_follow_the_identity_tokens(self):
        from PIL import Image
        # shape.buttons lists tokens: one bubble / pill / badge / banner per EXISTING token; "nope" is skipped
        for kind in ("bubble", "pill", "badge", "banner"):
            self.assertIn(f"{kind}_good", self.meta)
            self.assertNotIn(f"{kind}_nope", self.meta)
        # one card per rarity_* token
        self.assertIn("card_epic", self.meta)
        self.assertIn("card_common", self.meta)
        bubble = Image.open(os.path.join(self.tmp, "bubble_good.png")).convert("RGBA")
        r, g, b = dominant_opaque(bubble)
        self.assertGreater(g, r + 40)  # green body
        self.assertGreater(g, b + 40)

    def test_bubble_has_an_outline_a_gloss_and_a_shaded_bottom(self):
        from PIL import Image
        bubble = Image.open(os.path.join(self.tmp, "bubble_good.png")).convert("RGBA")
        w, h = bubble.size
        edge = bubble.getpixel((w // 2, 10))  # inside the 8 px margin: the outline
        self.assertLess(sum(edge[:3]) / 3, 90)
        top = bubble.getpixel((w // 2, int(h * 0.25)))
        bottom = bubble.getpixel((w // 2, int(h * 0.9)))
        self.assertGreater(sum(top[:3]), sum(bottom[:3]) + 60)  # lit above, shaded below
        self.assertEqual(bubble.getpixel((1, 1))[3], 0)  # transparent outside

    def test_card_edge_is_the_rarity_colour(self):
        from PIL import Image
        card = Image.open(os.path.join(self.tmp, "card_epic.png")).convert("RGBA")
        w, h = card.size
        px = card.getpixel((w // 2, 8 + 5 + 2))  # just inside the dark outline: the rarity edge
        self.assertGreater(px[2], 180)  # purple-ish: strong blue
        self.assertGreater(px[0], 120)

    def test_slant_is_a_white_parallelogram_leaning_right(self):
        from PIL import Image
        im = Image.open(os.path.join(self.tmp, "slant.png")).convert("RGBA")
        w, h = im.size
        self.assertEqual(im.getpixel((w // 2, h // 2))[:3], (255, 255, 255))  # white: it takes the node's tint
        self.assertEqual(im.getpixel((2, 2))[3], 0)  # the top-left corner is cut away (the lean)
        self.assertGreater(im.getpixel((2, h - 3))[3], 200)  # the bottom-left corner is solid

    def test_the_kits_thin_track_is_unchanged_by_the_chunky_one(self):
        self.assertIn("track", self.meta)
        self.assertEqual(self.meta["track"]["size"], 128)
        self.assertEqual(self.meta["track_chunky"]["size"], [192, 48])


class TestGlints(unittest.TestCase):
    def test_a_spec_fx_on_a_picture_gets_a_white_glint(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            ui = os.path.join(d, "ui")
            os.makedirs(os.path.join(ui, "identities"))
            os.makedirs(os.path.join(ui, "art", "zz"))
            json.dump({}, open(os.path.join(ui, "identities", "zz.json"), "w"))
            Image.new("RGBA", (8, 8), (200, 40, 10, 255)).save(os.path.join(ui, "art", "zz", "logo.png"))
            Image.new("RGBA", (8, 8), (10, 40, 200, 255)).save(os.path.join(ui, "art", "zz", "plain.png"))
            spec = {"name": "S", "identity": "zz", "root": {"type": "panel", "name": "R", "children": [
                {"type": "image", "name": "L", "image": "art:logo", "fx": [{"kind": "shimmer"}]},
                {"type": "image", "name": "P", "image": "art:zz/plain", "fx": [{"kind": "flicker"}]}]}}
            json.dump(spec, open(os.path.join(ui, "S.json"), "w"))
            self.assertEqual(plates.fx_glints(ui), {"zz": {"logo"}})        # (flicker needs no glint)
            out = os.path.join(d, "out")
            meta = plates.draw_identity({}, out, os.path.join(ui, "art", "zz"), {"logo"})
            self.assertEqual(meta["logo__glint"]["glint_of"], "logo")
            g = Image.open(os.path.join(out, "logo__glint.png")).convert("RGBA")
            self.assertEqual(g.getpixel((4, 4)), (255, 255, 255, 255))      # (white, the alpha kept)
            self.assertNotIn("plain__glint", meta)


if __name__ == "__main__":
    unittest.main()
