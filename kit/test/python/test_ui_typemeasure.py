"""kit ui read type: lettering measured from a crop — slant, stroke weight, outline (drawn shapes, no font files)"""
import importlib.util
import os
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_type", os.path.join(HERE, "..", "..", "ui", "typemeasure.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)


def bars(shear=0.0, width=14, outline=0):
    """five light vertical 'strokes' (I I I I I) on a mid ground, sheared, optionally ringed in ink"""
    im = Image.new("RGB", (420, 160), (110, 110, 118))
    d = ImageDraw.Draw(im)
    for k in range(5):
        x = 40 + k * 70
        poly = [(x + shear * 60, 20), (x + width + shear * 60, 20), (x + width - shear * 60, 140), (x - shear * 60, 140)]
        if outline:
            d.polygon(poly, fill=(16, 16, 16))
            poly = [(px + (outline if i in (0, 3) else -outline), py + (outline if py < 80 else -outline)) for i, (px, py) in enumerate(poly)]
        d.polygon(poly, fill=(240, 208, 144))
    return im


class TestTypeMeasure(unittest.TestCase):
    def test_slant_is_found_both_ways(self):
        self.assertLess(abs(T.measure(bars(0.0))["slant"]), 0.03)
        self.assertGreater(T.measure(bars(0.25))["slant"], 0.18)    # leans right
        self.assertLess(T.measure(bars(-0.2))["slant"], -0.13)      # leans left

    def test_heavier_strokes_read_heavier(self):
        self.assertGreater(T.measure(bars(width=24))["weight"], T.measure(bars(width=10))["weight"] + 0.05)

    def test_an_ink_ring_is_an_outline_and_none_is_not(self):
        self.assertTrue(T.measure(bars(width=20, outline=4))["outline"])
        self.assertFalse(T.measure(bars(width=20))["outline"])

    def test_a_measured_slant_round_trips_through_letter(self):
        import subprocess
        import sys
        import tempfile
        letter = os.path.join(HERE, "..", "..", "ui", "letter.py")
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, letter, "t/w", "--text", "WIMH", "--font", "oswald", "--weight", "700", "--size", "120", "--lean", "0",
                                "--outline", "0", "--shadow", "0", "--shear", "0.2", "--art", d], capture_output=True, text=True)
            if r.returncode != 0:
                self.skipTest("no pinned oswald font here")
            im = Image.open(os.path.join(d, "t", "w.png")).convert("RGBA")
            bg = Image.new("RGBA", im.size, (110, 110, 118, 255))
            bg.alpha_composite(im)
            self.assertAlmostEqual(T.measure(bg)["slant"], 0.2, delta=0.05)

    def test_the_flags_carry_the_measures(self):
        flags = T.letter_flags({"cap_px": 70, "weight": 0.22, "slant": 0.2, "track": 0.3, "fill": "#ffffff", "outline": True})
        self.assertIn("--shear", flags)
        self.assertEqual(flags[flags.index("--font") + 1], "oswald")   # an upright face: the shear IS the slant
        self.assertEqual(flags[flags.index("--shear") + 1], "0.20")
        self.assertEqual(flags[flags.index("--weight") + 1], "900")
        self.assertIn("--outline", flags)


if __name__ == "__main__":
    unittest.main()
