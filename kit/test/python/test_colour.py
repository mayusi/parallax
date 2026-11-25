"""kit/blender/rbx_colour.py: the colour arithmetic behind colour_match — CIELAB from sRGB, and a difference said in
words a builder can act on ("darker by 16 L*", "green where the reference is blue")."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_colour as C  # noqa: E402


class TestColour(unittest.TestCase):
    def test_white_black_and_a_known_red(self):
        np.testing.assert_allclose(C.srgb_to_lab((1.0, 1.0, 1.0)), (100.0, 0.0, 0.0), atol=0.05)
        np.testing.assert_allclose(C.srgb_to_lab((0.0, 0.0, 0.0)), (0.0, 0.0, 0.0), atol=0.05)
        np.testing.assert_allclose(C.srgb_to_lab((1.0, 0.0, 0.0)), (53.24, 80.09, 67.20), atol=0.3)  # sRGB red

    def test_a_whole_picture_converts_at_once(self):
        self.assertEqual(C.srgb_to_lab(np.zeros((4, 5, 3))).shape, (4, 5, 3))

    def test_the_same_colour_is_close(self):
        lab = C.srgb_to_lab((0.77, 0.64, 0.49))
        self.assertEqual(C.colour_words(lab, lab), "close")

    def test_a_darker_bronze_is_called_darker(self):
        words = C.colour_words(C.srgb_to_lab((0.62, 0.45, 0.33)), C.srgb_to_lab((0.80, 0.62, 0.45)))
        self.assertIn("darker by", words)

    def test_another_colour_altogether_names_both(self):
        words = C.colour_words(C.srgb_to_lab((0.49, 0.80, 0.54)), C.srgb_to_lab((0.49, 0.58, 0.80)))
        self.assertIn("green where the reference is blue", words)

    def test_a_hue_on_a_near_grey_is_not_named(self):
        words = C.colour_words(C.srgb_to_lab((0.52, 0.5, 0.5)), C.srgb_to_lab((0.5, 0.5, 0.52)))
        self.assertNotIn("where the reference is", words)

    def test_hue_names_follow_the_wheel(self):
        self.assertEqual([C.hue_name(d) for d in (30, 60, 95, 140, 200, 270)],
                         ["red", "orange", "yellow", "green", "cyan", "blue"])

    def test_another_hue_is_off_but_a_darker_same_hue_is_not(self):
        blue, green = C.srgb_to_lab((0.49, 0.58, 0.80)), C.srgb_to_lab((0.49, 0.80, 0.54))
        self.assertTrue(C.colour_off(green, blue))
        bronze, dark_bronze = C.srgb_to_lab((0.80, 0.62, 0.45)), C.srgb_to_lab((0.55, 0.42, 0.30))
        self.assertFalse(C.colour_off(dark_bronze, bronze))  # lightness is the picture's light: never judged

    def test_a_grey_where_the_reference_is_saturated_is_off(self):
        self.assertTrue(C.colour_off(C.srgb_to_lab((0.6, 0.6, 0.6)), C.srgb_to_lab((0.85, 0.45, 0.2))))


if __name__ == "__main__":
    unittest.main()
