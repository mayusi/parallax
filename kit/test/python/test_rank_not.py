"""kit refs rank --not "<a, b>": pictures that ARE one of those (a museum piece, a votive copy, a car) sink to the bottom
(kit/vision/run.py not_of / rank; his V3 list, 3D stage A.2 - the car rim's first search ranked museum objects
first, lesson L-3d-aab91e). The vision models are stood in for here: the rule is what is tested."""

import json
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vision"))
import run as V  # noqa: E402


class NotOf(unittest.TestCase):
    def test_a_title_that_names_the_term_is_it(self):
        self.assertEqual(V.not_of("Four-Spoked Votive Wheel", ["votive"]), "votive")
        self.assertEqual(V.not_of("Antique cart wheel, museum of transport", ["museum", "car"]), "museum")
        self.assertIsNone(V.not_of("Alloy wheel", ["museum", "votive"]))

    def test_whole_words_only(self):
        self.assertIsNone(V.not_of("Cartwheel in a carnival", ["car"]))     # (car is not in carnival)
        self.assertEqual(V.not_of("A car wheel", ["car"]), "car")

    def test_the_model_decides_when_the_title_says_nothing(self):
        self.assertEqual(V.not_of("", ["museum piece", "car"], probs=[0.1, 0.6], what_p=0.4), "car")
        self.assertIsNone(V.not_of("", ["museum piece"], probs=[0.2], what_p=0.5))


class Rank(unittest.TestCase):
    def setUp(self):
        from PIL import Image  # noqa: PLC0415

        self.tmp = tempfile.TemporaryDirectory()
        for name, title in (("a.png", "Alloy wheel"), ("b.png", "Wheel of the Law (museum object)"),
                            ("c.png", "Spoked wheel")):
            Image.new("RGB", (900, 900), (200, 200, 200)).save(os.path.join(self.tmp.name, name))
            with open(os.path.join(self.tmp.name, name + ".json"), "w", encoding="utf-8") as fh:
                json.dump({"title": title, "license": "cc0"}, fh)
        keep = {k: getattr(V, k) for k in ("view_of", "cutout", "zero_shot")}
        self.addCleanup(lambda: [setattr(V, k, v) for k, v in keep.items()])
        V.view_of = lambda img, what: ("side", {"side": 0.9, "front": 0.1})
        V.cutout = lambda img: np.pad(np.ones((500, 500)), 200)
        # (c is a museum piece by the model's eye only; text vs object always says object)
        V.zero_shot = lambda img, labels: ([0.1, 0.9] if labels[0].startswith("a page") else
                                           [0.5, 0.2] if img.getpixel((0, 0)) != (201, 200, 200) else [0.2, 0.7])
        from PIL import Image  # noqa: PLC0415, F811

        Image.new("RGB", (900, 900), (201, 200, 200)).save(os.path.join(self.tmp.name, "c.png"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_what_it_must_not_be_sinks_to_the_bottom_and_says_why(self):
        rows = V.rank(self.tmp.name, "a car wheel", ["museum"])
        self.assertEqual([r["file"] for r in rows][0], "a.png")
        sunk = {r["file"]: r["not"] for r in rows if r["not"]}
        self.assertEqual(sunk, {"b.png": "museum", "c.png": "museum"})
        self.assertAlmostEqual(rows[-1]["score"] / rows[0]["score"], V.NOT_SINK, places=3)

    def test_without_not_nothing_sinks(self):
        rows = V.rank(self.tmp.name, "a car wheel")
        self.assertTrue(all(r["not"] is None for r in rows))
        self.assertEqual(len({r["score"] for r in rows}), 1)


if __name__ == "__main__":
    unittest.main()
