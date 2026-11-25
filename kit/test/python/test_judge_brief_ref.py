"""The judge's reference when a build never set Asset(ref_image=) (kit/blender/judge.py brief_reference): the picture
the BRIEF names as its quality bar - the first picture path on its "- quality bar:" line that exists. Without it the
packet had no reference and a fresh judge marked the owner's own picked design down (celestial_sword, 2026-11-20)."""

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import judge  # noqa: E402


class BriefReference(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kit_judge_ref_")
        os.makedirs(os.path.join(self.root, "assets", "models", "direction"))
        open(os.path.join(self.root, "assets", "models", "direction", "Pick.concept.png"), "wb").write(b"png")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def brief(self, text):
        with open(os.path.join(self.root, "assets", "models", "thing.brief.md"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_the_first_existing_picture_on_the_quality_bar_line(self):
        self.brief("# thing\n- what: a sword\n- quality bar: the pick's concept, refs/missing.png, "
                   "assets/models/direction/Pick.concept.png (kept at IoU 0.96)\n- references: other.png\n")
        self.assertEqual(judge.brief_reference("thing", self.root), "assets/models/direction/Pick.concept.png")

    def test_no_quality_bar_picture_is_none(self):
        self.brief("# thing\n- quality bar: hero 75, no picture\n- references: assets/models/direction/Pick.concept.png\n")
        self.assertIsNone(judge.brief_reference("thing", self.root))   # (only the quality-bar line counts)
        self.assertIsNone(judge.brief_reference("nobrief", self.root))


if __name__ == "__main__":
    unittest.main()
