"""kit refs font (kit/refs/font.py) — the font that drew a picture's text is found again: words rendered in one font
(light letters on a dark engraved-looking ground, a little blurred) rank that font first among others; the letters are
taken off either polarity of ground."""

import glob
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "refs"))
import font as F  # noqa: E402

KIT_FONTS = sorted(glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "fonts", "*", "*.ttf")))


@unittest.skipUnless(len(KIT_FONTS) >= 5, "the kit's font cache is not installed")
class FontMatch(unittest.TestCase):
    def test_the_drawing_font_ranks_first(self):
        import cv2  # noqa: PLC0415

        pick = [f for f in KIT_FONTS if any(k in os.path.basename(f).lower() for k in
                                            ("cinzel", "kaushan", "oswald", "merriweather", "bungee", "fondamento"))]
        self.assertGreaterEqual(len(pick), 4, pick)
        for truth in pick[:3]:
            m = F.render(truth, "Parsley ever joyous", h=60)
            pic = np.where(np.pad(m, 12), 215, 40).astype(np.uint8)         # (light letters, dark ground)
            pic = cv2.GaussianBlur(pic, (0, 0), 0.8)
            _t, top = F.rank(pic, "Parsley ever joyous", pick, top=3)
            self.assertEqual(top[0][1], truth, [(round(s, 3), os.path.basename(p)) for s, p in top])

    def test_letters_off_either_ground(self):
        m = F.render(KIT_FONTS[0], "Fair", h=40)
        dark_on_light = np.where(np.pad(m, 6), 20, 230).astype(np.uint8)
        light_on_dark = 255 - dark_on_light
        a, b = F.text_mask(dark_on_light), F.text_mask(light_on_dark)
        self.assertEqual(a.shape, b.shape)
        self.assertGreater(F.likeness(a, m), 0.9)


if __name__ == "__main__":
    unittest.main()
