"""kit/ui/flash.py (WCAG 2.3.1: > 3 flashes a second over a quarter of a 10-degree field fails, red stricter) and
kit/ui/align.py (near-miss alignment and uneven gaps among siblings)"""
import importlib.util
import os
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"kit_ui_{name}", os.path.join(HERE, "..", "..", "ui", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


flash = load("flash")
align = load("align")


class TestFlash(unittest.TestCase):
    def test_a_big_strobe_fails_a_fade_and_a_small_blink_pass(self):
        strobe = [Image.new("RGB", (320, 180), (255, 255, 255) if (i // 2) % 2 == 0 else (0, 0, 0)) for i in range(48)]
        r = flash.flash_report(strobe, 24)
        self.assertTrue(r["fail"])
        self.assertEqual(r["max_hz"], 6)
        fade = [Image.new("RGB", (320, 180), (int(255 * i / 47),) * 3) for i in range(48)]
        self.assertFalse(flash.flash_report(fade, 24)["fail"])
        slow = [Image.new("RGB", (320, 180), (255, 255, 255) if (i // 6) % 2 == 0 else (0, 0, 0)) for i in range(48)]
        self.assertFalse(flash.flash_report(slow, 24)["fail"])            # (2 flashes a second: allowed)

    def test_a_red_strobe_counts_as_red(self):
        red = [Image.new("RGB", (320, 180), (255, 0, 0) if (i // 2) % 2 == 0 else (40, 0, 0)) for i in range(48)]
        r = flash.flash_report(red, 24)
        self.assertGreater(r["red_max_hz"], 3)
        self.assertTrue(r["fail"])


class TestAlign(unittest.TestCase):
    def test_near_misses_and_uneven_gaps(self):
        boxes = {"R": (0, 0, 500, 300), "R.A": (10, 10, 100, 40), "R.B": (12, 60, 100, 40), "R.C": (10, 110, 100, 40),
                 "R.Shadow": (13, 13, 100, 40)}
        found = align.near_misses(boxes)
        self.assertTrue(any(k == "near_align" and "R.A" in p + m for k, p, m in found))     # (2 px off on the left)
        self.assertFalse(any("Shadow" in p for _, p, _ in found))                           # (offset on purpose)
        row = {"R": (0, 0, 500, 100), "R.A": (0, 0, 50, 40), "R.B": (60, 0, 50, 40), "R.C": (123, 0, 50, 40)}
        self.assertTrue(any(k == "uneven_gap" for k, _, _ in align.near_misses(row)))      # (gaps 10 and 13)
        exact = {"R": (0, 0, 500, 100), "R.A": (0, 0, 50, 40), "R.B": (60, 0, 50, 40), "R.C": (120, 0, 50, 40)}
        self.assertEqual(align.near_misses(exact), [])


class TestPalette(unittest.TestCase):
    def test_busy_and_balanced(self):
        def fill(name, rgb, x):
            return {"Name": name, "ClassName": "Frame", "Properties": {"BackgroundColor3": {"Color3": rgb}, "BackgroundTransparency": 0}}
        cols = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (0.5, 0.2, 0.9), (0.9, 0.5, 0.1)]
        kids = [fill(f"P{i}", c, i) for i, c in enumerate(cols)]
        model = {"Children": [{"Name": "R", "ClassName": "Frame", "Properties": {"BackgroundTransparency": 1}, "Children": kids}]}
        boxes = {f"R.P{i}": (i * 50, 0, 50, 50) for i in range(len(cols))}
        kinds = {k for k, _, _ in align.palette(model, boxes)}
        self.assertIn("palette_count", kinds)                                  # (8 equal colours: busy, no dominant)
        self.assertIn("palette_balance", kinds)
        calm = {"Children": [{"Name": "R", "ClassName": "Frame", "Properties": {"BackgroundTransparency": 1},
                              "Children": [fill("Big", (0.1, 0.1, 0.12), 0), fill("Acc", (1, 0.6, 0), 1)]}]}
        self.assertEqual(align.palette(calm, {"R.Big": (0, 0, 600, 300), "R.Acc": (0, 0, 60, 30)}), [])


if __name__ == "__main__":
    unittest.main()
