"""v7.11: a console screen's text outside the TV title-safe 90% or under 24 px is flagged; a phone control in the
top-middle (the hardest thumb reach) is flagged"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ui"))
_spec = importlib.util.spec_from_file_location("kit_ui_preview_tv", os.path.join(HERE, "..", "..", "ui", "preview.py"))
preview = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preview)


def label(name, x, y, w, h, size, cls="TextLabel", text="Hello"):
    return {"Name": name, "ClassName": cls, "Properties": {
        "Position": {"UDim2": [[0, x], [0, y]]}, "Size": {"UDim2": [[0, w], [0, h]]}, "Text": text, "TextSize": size,
        "BackgroundTransparency": 1}}


def screen(kids, console=False):
    attrs = {"Kit_Console": {"Bool": True}} if console else {}
    return {"ClassName": "ScreenGui", "Properties": {"Attributes": {"Attributes": attrs}},
            "Children": [{"Name": "Root", "ClassName": "Frame", "Properties": {"Size": {"UDim2": [[1, 0], [1, 0]]},
                                                                               "BackgroundTransparency": 1}, "Children": kids}]}


class TestTv(unittest.TestCase):
    def test_title_safe_and_tv_text(self):
        m = screen([label("Edge", 10, 10, 300, 40, 30), label("Small", 600, 500, 300, 40, 16)], console=True)
        _, checks = preview.draw_screen(m, 1920, 1080, inset_px=0)
        kinds = {(k, p.split(".")[-1]) for k, p, _ in checks}
        self.assertIn(("title_safe", "Edge"), kinds)
        self.assertIn(("tv_text", "Small"), kinds)
        _, plain = preview.draw_screen(screen([label("Edge", 10, 10, 300, 40, 30)]), 1920, 1080, inset_px=0)
        self.assertFalse(any(k == "title_safe" for k, _, _ in plain))           # (only a console screen)

    def test_thumb_reach(self):
        m = screen([label("Play", 380, 40, 90, 48, 18, cls="TextButton", text="Play"),
                    label("Shop", 40, 320, 90, 48, 18, cls="TextButton", text="Shop")])
        _, checks = preview.draw_screen(m, 844, 390, inset_px=0)
        hard = {p.split(".")[-1] for k, p, _ in checks if k == "thumb_reach"}
        self.assertEqual(hard, {"Play"})


if __name__ == "__main__":
    unittest.main()
