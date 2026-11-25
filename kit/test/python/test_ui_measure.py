"""kit ui measure / identity_from: masks, boxes, top edges and slopes come from pixels; the accent is found"""
import os
import unittest

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location("kit_ui_" + name, os.path.join(HERE, "..", "..", "ui", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


measure = load("measure")
identity_from = load("identity_from")


def still(tmp):
    """a Persona-type frame: black, a red field lower-left whose top edge falls to the right, a white logo box"""
    im = Image.new("RGB", (640, 360), (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(0, 100), (400, 180), (640, 360), (0, 360)], fill=(230, 0, 18))
    d.rectangle([20, 20, 220, 90], fill=(240, 240, 240))
    im.save(tmp)
    return tmp


class TestMeasure(unittest.TestCase):
    def test_masks_boxes_and_slope(self):
        im = Image.open(still(os.path.join(HERE, "_measure_still.png"))).convert("RGB")
        arr = np.array(im).astype(np.int32)
        red = measure.colour_mask(arr, (230, 0, 18), 60)
        self.assertEqual(measure.bbox(red)[:2], [0, 100])
        edge = measure.top_edge(red, cols=8)
        s = measure.slope(edge)
        self.assertGreater(s, 0.2)  # falls to the right
        white = measure.colour_mask(arr, (240, 240, 240), 60)
        m = measure.masses(white)
        self.assertEqual(len(m), 1)
        x0, y0, x1, y1 = m[0]["box"]
        self.assertTrue(abs(x0 - 20) <= 4 and abs(y0 - 20) <= 4)
        os.remove(os.path.join(HERE, "_measure_still.png"))

    def test_dominant_accent_is_the_red(self):
        p = still(os.path.join(HERE, "_accent_still.png"))
        col, share = identity_from.dominant_accent(p)
        os.remove(p)
        r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        self.assertGreater(r, 180)
        self.assertLess(g, 60)
        self.assertGreater(share, 0.2)


if __name__ == "__main__":
    unittest.main()
