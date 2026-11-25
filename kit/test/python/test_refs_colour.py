"""kit refs colour: a reference picture's colour grade measured on a neutral surface and taken out (kit/refs/colour.py)
— a picture made with a blue grade (linear gains 0.80 / 0.95 / 1.20) is named graded and blue, its red sample comes
back to the true red; the same picture ungraded is neutral."""

import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import colour  # noqa: E402

TRUE_RED = np.array([0.80, 0.10, 0.10])  # sRGB


def picture(path, gains=(1.0, 1.0, 1.0)):
    img = np.zeros((100, 200, 3))
    img[:, :100] = 0.45          # a grey card (sRGB), left
    img[:, 100:] = TRUE_RED      # a red part, right
    lin = colour.to_linear(img) * np.array(gains)
    Image.fromarray((colour.to_srgb(lin) * 255).round().astype(np.uint8)).save(path)


class TestRefsColour(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_a_graded_picture_is_found_and_balanced(self):
        p = os.path.join(self.d, "graded.png")
        picture(p, gains=(0.80, 0.95, 1.20))
        res = colour.measure(p, neutral=(10, 10, 90, 90), samples=[("red", (110, 10, 190, 90))],
                             out=os.path.join(self.d, "b.png"))
        self.assertTrue(res["cast"]["graded"], res["cast"])
        self.assertIn(res["cast"]["hue"], ("blue", "cyan", "purple"))
        bal = np.array([int(res["samples"][0]["balanced"][i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
        self.assertLess(np.abs(bal - TRUE_RED).max(), 0.04)  # the true red, back
        self.assertTrue(os.path.isfile(res["balanced_picture"]))

    def test_found_without_a_box(self):
        p = os.path.join(self.d, "graded.png")
        picture(p, gains=(0.80, 0.95, 1.20))
        res = colour.measure(p, out=os.path.join(self.d, "b.png"))
        self.assertTrue(res["cast"]["graded"])

    def test_an_ungraded_picture_is_neutral(self):
        p = os.path.join(self.d, "plain.png")
        picture(p)
        res = colour.measure(p, neutral=(10, 10, 90, 90), out=os.path.join(self.d, "b.png"))
        self.assertFalse(res["cast"]["graded"], res["cast"])
        self.assertLess(res["cast"]["chroma"], 1.0)


if __name__ == "__main__":
    unittest.main()
