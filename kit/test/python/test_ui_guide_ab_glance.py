"""kit ui guide / ab / glance (v7.16): the style guide lists every token with its contrast and every screen wearing the
identity; the blind A/B hides the names and records the winner --vs the loser (a tie records nothing); the five-second
test passes only when what was seen first is the spec's focus"""
import importlib.util
import json
import os
import random
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "..", "..", "ui")
sys.path.insert(0, UI)


def _load(name):
    spec = importlib.util.spec_from_file_location(f"kit_ui_{name}", os.path.join(UI, f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


guide = _load("guide")
ab = _load("ab")
glance = _load("glance")


class TestGuide(unittest.TestCase):
    def test_page_has_tokens_contrast_and_screens(self):
        with tempfile.TemporaryDirectory() as d:
            ui, bld = os.path.join(d, "ui"), os.path.join(d, "build")
            os.makedirs(os.path.join(ui, "identities"))
            os.makedirs(os.path.join(ui, "art", "toy"))
            os.makedirs(bld)
            ident = {"name": "toy", "about": "a toy identity", "tokens": {"bg": "#000000", "text": "#ffffff", "accent": "#ff8408"},
                     "fonts": {"font": "Oswald"}, "roles": {"body": {"size": 20, "font": "font"}}, "bans": ["no gradients"],
                     "references": [{"game": "G", "screen": "hud", "image": "assets/ui/refs/x.jpg", "take": "t"}]}
            with open(os.path.join(ui, "identities", "toy.json"), "w", encoding="utf-8") as fh:
                json.dump(ident, fh)
            with open(os.path.join(ui, "ToyHud.json"), "w", encoding="utf-8") as fh:
                json.dump({"name": "ToyHud", "identity": "toy", "kind": "hud", "focus": "Hud.Bar"}, fh)
            with open(os.path.join(ui, "Other.json"), "w", encoding="utf-8") as fh:
                json.dump({"name": "Other", "identity": "else"}, fh)
            Image.new("RGB", (64, 36), (10, 10, 10)).save(os.path.join(bld, "ToyHud.desktop.png"))
            Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(os.path.join(ui, "art", "toy", "plate.png"))
            doc, st = guide.build("toy", ui, bld)
        self.assertEqual(st["tokens"], 3)
        self.assertEqual(st["screens"], 1)  # (only the screen wearing it)
        self.assertEqual(st["pieces"], 1)
        self.assertIn("21.0:1", doc)  # white on black
        self.assertIn("no gradients", doc)
        self.assertIn("ToyHud", doc)
        self.assertNotIn("Other", doc)
        self.assertNotIn("x.jpg\" src", doc)  # (references are linked, never inlined)

    def test_contrast(self):
        self.assertAlmostEqual(guide.contrast((255, 255, 255), (0, 0, 0)), 21.0, places=1)
        self.assertAlmostEqual(guide.contrast((128, 128, 128), (128, 128, 128)), 1.0, places=3)


class TestAB(unittest.TestCase):
    def test_order_is_random_and_complete(self):
        seen = set()
        for seed in range(20):
            o = ab.order("A", "B", random.Random(seed))
            self.assertEqual(sorted(o.values()), ["A", "B"])
            seen.add(o["X"])
        self.assertEqual(seen, {"A", "B"})

    def test_verdict_line(self):
        sides = {"X": "HudNew", "Y": "HudOld"}
        args = ab.verdict_args(sides, "X", 7, "cleaner")
        self.assertEqual(args[:5], ["verdict", "screen", "HudNew", "7", "cleaner"])
        self.assertIn("--vs", args)
        self.assertEqual(args[args.index("--vs") + 1], "HudOld")
        self.assertEqual(args[args.index("--tag") + 1], "ab")
        self.assertIsNone(ab.verdict_args(sides, "=", -1, ""))
        self.assertEqual(ab.verdict_args(sides, "Y", 4, "--x")[4], "(x)")  # (never read as a flag)
        two = ab.verdict_args({"X": "a/v1.png", "Y": "a/v2.png"}, "Y", 8, "", name="Hud")
        self.assertEqual(two[2], "Hud")
        self.assertEqual(two[two.index("--vs") + 1], "v1.png")

    def test_page_hides_names(self):
        with tempfile.TemporaryDirectory() as d:
            pa, pb = os.path.join(d, "a.png"), os.path.join(d, "b.png")
            Image.new("RGB", (8, 8)).save(pa)
            Image.new("RGB", (8, 8)).save(pb)
            page = ab.page({"X": "SecretNameA", "Y": "SecretNameB"}, {"X": pa, "Y": pb}, "tok")
        self.assertNotIn("SecretNameA", page)
        self.assertNotIn("SecretNameB", page)


class TestGlance(unittest.TestCase):
    MODEL = {"Children": [{"Name": "Hud", "ClassName": "Frame", "Children": [
        {"Name": "Ammo", "ClassName": "Frame", "Children": [{"Name": "Count", "ClassName": "TextLabel", "Properties": {"Text": "30 / 90"}}]},
        {"Name": "Tip", "ClassName": "TextLabel", "Properties": {"Text": "Press E to reload"}},
    ]}]}

    def test_texts_under_focus(self):
        self.assertEqual([t for _, t in glance.texts_under(self.MODEL, "Hud.Ammo")], ["30 / 90"])
        self.assertEqual(len(glance.texts_under(self.MODEL, "")), 2)

    def test_check(self):
        key = {"kind": "hud", "focus": "Hud.Ammo", "focus_words": ["ammo", "hud"], "focus_texts": ["30 / 90"], "big_texts": ["Press E to reload"]}
        good = glance.check(key, {"for": "a shooter hud", "first": "the ammo counter", "key": "30", "press": "reload"})
        self.assertTrue(all(ok for _, ok, _ in good))
        bad = glance.check(key, {"for": "?", "first": "the reload tip", "key": "no idea", "press": ""})
        self.assertFalse(dict((q, ok) for q, ok, _ in bad)["first"])
        self.assertFalse(dict((q, ok) for q, ok, _ in bad)["key"])


if __name__ == "__main__":
    unittest.main()
