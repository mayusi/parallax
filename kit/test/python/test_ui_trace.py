"""kit ui trace: green cells become empty wells with anchors; slivers are not cells"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("kit_ui_trace", os.path.join(HERE, "..", "..", "ui", "trace.py"))
trace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trace)


class TestTrace(unittest.TestCase):
    def plate(self):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (400, 60), (40, 42, 44))
        d = ImageDraw.Draw(im)
        for i in range(5):
            d.rectangle([20 + i * 60, 15, 60 + i * 60, 35], fill=(30, 220, 60))  # five green cells
        d.rectangle([330, 15, 334, 35], fill=(30, 220, 60))  # a 5 px glint: not a cell
        d.rectangle([20, 45, 160, 55], fill=(30, 220, 60))  # a second row, one long cell
        return im

    def test_cells_are_found_per_row_and_slivers_dropped(self):
        rows = trace.cells_from_mask(trace.green_mask(self.plate()))
        self.assertEqual([len(r) for r in rows], [5, 1])
        c = rows[0][0]
        self.assertEqual((c["x"], c["y"], c["w"], c["h"]), (20, 15, 41, 21))

    def test_blanked_cells_take_the_dark_well_colour(self):
        im = self.plate()
        rows = trace.cells_from_mask(trace.green_mask(im))
        out = trace.blank_cells(im, rows)
        r, g, b, a = out.getpixel((40, 25))
        self.assertLess(g, 60)  # no longer green
        self.assertLess(abs(r - g), 20)  # a dark grey well


if __name__ == "__main__":
    unittest.main()
