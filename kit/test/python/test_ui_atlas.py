"""kit/ui/atlas.py: an identity's small pieces packed into sheets — no two rects overlap, every rect sits inside its
sheet with a clear border, the sheet's pixels ARE the piece, a held / sliced / big piece never goes in"""
import importlib.util
import os
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_atlas", os.path.join(HERE, "..", "..", "ui", "atlas.py"))
atlas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(atlas)


class TestAtlas(unittest.TestCase):
    def test_pack_places_pieces_once_inside_their_sheets(self):
        with tempfile.TemporaryDirectory() as d:
            meta = {}
            for i in range(40):
                w, h = 40 + (i * 37) % 200, 30 + (i * 53) % 220
                Image.new("RGBA", (w, h), (i * 6 % 255, 80, 200, 255)).save(os.path.join(d, f"p{i}.png"))
                meta[f"p{i}"] = {"size": [w, h], "slice": None}
            Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(os.path.join(d, "held.png"))
            meta["held"] = {"size": 64, "slice": None}
            Image.new("RGBA", (64, 64), (0, 255, 0, 255)).save(os.path.join(d, "frame.png"))
            meta["frame"] = {"size": 64, "slice": [8, 8, 56, 56]}
            Image.new("RGBA", (512, 512), (0, 0, 255, 255)).save(os.path.join(d, "big.png"))
            meta["big"] = {"size": 512, "slice": None}
            made = atlas.pack(d, meta, held={"held"})
            self.assertNotIn("atlas", meta["held"])                          # (held: never in a sheet)
            self.assertNotIn("atlas", meta["frame"])                         # (9-sliced: its own picture)
            self.assertNotIn("atlas", meta["big"])                           # (too big to share)
            rects = {}
            for name, m in meta.items():
                if m.get("atlas"):
                    s, x, y, w, h = m["atlas"]
                    self.assertTrue(x >= atlas.PAD and y >= atlas.PAD)
                    self.assertTrue(x + w + atlas.PAD <= atlas.SHEET and y + h + atlas.PAD <= atlas.SHEET)
                    for (s2, x2, y2, w2, h2) in rects.values():
                        if s2 == s:
                            self.assertFalse(x < x2 + w2 and x2 < x + w and y < y2 + h2 and y2 < y + h)  # (no overlap)
                    rects[name] = (s, x, y, w, h)
            self.assertEqual(len(rects), 40)
            s, x, y, w, h = meta["p3"]["atlas"]
            with Image.open(os.path.join(d, f"{s}.png")) as sheet, Image.open(os.path.join(d, "p3.png")) as piece:
                self.assertEqual(sheet.convert("RGBA").getpixel((x + w // 2, y + h // 2)), piece.convert("RGBA").getpixel((w // 2, h // 2)))
            self.assertEqual(sum(len(v) for v in made.values()), 40)


if __name__ == "__main__":
    unittest.main()
