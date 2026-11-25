"""kit refs coverage <asset> --parts: EVERY part of the part review gets the best px/mm among the pictures its answer
cites — a library tile or close-up's known scale (kit library inspect), a traced view's — or counts as measured when
it cites a dimension row; the rest are named (the owner: close-ups for every part, not only the hero features)."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import coverage  # noqa: E402

REVIEW = """# x — part review
- Slide [aaaaaaaa]: real: the slide | ref: build/library/m/parts/01_slide.png | verdict: ok
- SafetyLever [bbbbbbbb]: real: the thumb safety | ref: build/library/m/part_safety_side_from_left.png | verdict: ok
- GripScrew [cccccccc]: real: a grip screw | ref: dims:59297d08 | verdict: ok
- Hammer [dddddddd]: real: the hammer | ref: refs/hammer.jpg | verdict: ok
"""


class TestPartsCoverage(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "assets", "models"))
        os.makedirs(os.path.join(self.root, "refs"))
        with open(os.path.join(self.root, "assets", "models", "x.parts.md"), "w", encoding="utf-8") as fh:
            fh.write(REVIEW)
        with open(os.path.join(self.root, "refs", "m.inspect.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": "m", "parts": [{"name": "Slide", "tile": "build/library/m/parts/01_slide.png",
                                               "tile_mm_per_px": 0.6}],
                       "closeups": [{"part": "Safety", "image": "build/library/m/part_safety_side_from_left.png",
                                     "mm_per_px": 0.1}]}, fh)

    def test_every_part_classified(self):
        rows = {r["family"]: r for r in coverage.parts_coverage("x", self.root)}
        self.assertAlmostEqual(rows["Slide"]["best_px_per_mm"], 1.67, places=2)      # a whole-part tile: too coarse
        self.assertAlmostEqual(rows["SafetyLever"]["best_px_per_mm"], 10.0, places=2)  # a close-up at 0.1 mm/px
        self.assertTrue(rows["GripScrew"]["measured"])
        self.assertIsNone(rows["Hammer"]["best_px_per_mm"])                          # a photo with no known scale
        self.assertFalse(rows["Hammer"]["measured"])

    def test_the_command_names_the_low_and_the_unknown(self):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            coverage.main(["x", "--parts", "--root", self.root])
        result = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertEqual(result["low"], ["Slide"])
        self.assertEqual(result["unknown"], ["Hammer"])


if __name__ == "__main__":
    unittest.main()
