"""kit/world/frame_labels.py: a direction frame's plain-word labels (the owner, 2026-11-11, on an unlabelled frame:
"I don't know what I'm exactly looking at"). Tags stay on the picture, never overlap, and what the camera cannot see
goes to the bottom strip; the unlabelled render is kept."""

import json
import os
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "world"))
import frame_labels  # noqa: E402


class FrameLabels(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.png = os.path.join(self.dir, "Piece_B.png")
        Image.new("RGB", (800, 450), (20, 24, 34)).save(self.png)
        self.labels = os.path.join(self.dir, "Piece_B.labels.json")
        spec = {"size": [800, 450], "labels": [
            {"text": "the cathedral (ahead)", "px": [400, 120], "seen": True},
            {"text": "the stair up to the cathedral", "px": [410, 130], "seen": True},  # (crowded: must not overlap)
            {"text": "you (your R6 rig)", "px": [780, 440], "seen": True},  # (a corner: its tag stays inside)
            {"text": "lamp 2 (at the gate, behind you)", "px": [-50, 300], "seen": False},
        ]}
        with open(self.labels, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)

    def test_tags_inside_apart_and_the_unseen_in_the_strip(self):
        r = frame_labels.draw(self.png, self.labels)
        self.assertEqual(len(r["drawn"]), 3)
        self.assertEqual(r["not_in_view"], ["lamp 2 (at the gate, behind you)"])
        boxes = [d["box"] for d in r["drawn"]]
        strip_top = 450 - int(max(16, 800 // 58) * 2.2)
        for b in boxes:
            self.assertGreaterEqual(b[0], 0)
            self.assertGreaterEqual(b[1], 0)
            self.assertLessEqual(b[2], 800)
            self.assertLessEqual(b[3], strip_top)  # (a tag never covers the strip)
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                self.assertFalse(frame_labels.overlaps(boxes[i], boxes[j], pad=0), (boxes[i], boxes[j]))

    def test_keeps_the_raw_render_and_changes_the_shown_one(self):
        before = Image.open(self.png).convert("RGB").tobytes()
        r = frame_labels.draw(self.png, self.labels)
        self.assertTrue(os.path.isfile(r["raw"]))
        self.assertEqual(Image.open(r["raw"]).convert("RGB").tobytes(), before)
        self.assertNotEqual(Image.open(self.png).convert("RGB").tobytes(), before)
        # a second run draws on the RAW again, not on the labelled picture (no doubled tags)
        once = Image.open(self.png).convert("RGB").tobytes()
        frame_labels.draw(self.png, self.labels)
        self.assertEqual(Image.open(self.png).convert("RGB").tobytes(), once)

    def test_the_strip_of_what_is_not_in_view_never_runs_off_the_picture(self):
        # GothicCourtyard's establishing shot, 2026-11-12: seven of nine labels out of view and the strip ended
        # mid-word at the right edge ("... lamp 1: the stair's f")
        from PIL import ImageDraw

        d = ImageDraw.Draw(Image.new("RGB", (1920, 1080)))
        unseen = ["the cathedral (its lit windows)", "the stair up to the cathedral", "a house you can walk into",
                  "lamp 1: the stair's foot", "the well", "fire on the terrace", "the tower"]
        size = max(16, 1920 // 58)
        text, f = frame_labels.strip_text(d, unseen, size, 1920 - 28)
        self.assertLessEqual(d.textlength(text, font=f), 1920 - 28)
        self.assertTrue(all(u in text for u in unseen), text)  # (smaller type: every one is still named)
        # far too many for any type size: as many as fit are named and the rest are counted, never cut mid-word
        many = [f"lamp {i}: the stair's foot" for i in range(40)]
        text, f = frame_labels.strip_text(d, many, size, 1920 - 28)
        self.assertLessEqual(d.textlength(text, font=f), 1920 - 28)
        self.assertRegex(text, r"; \+\d+ more$")
        named = text.count("lamp ")
        self.assertEqual(int(text.rsplit("+", 1)[1].split()[0]), 40 - named)
        # a short list keeps the labels' own size
        text, f = frame_labels.strip_text(d, ["the tower"], size, 1920 - 28)
        self.assertEqual((text, f.size), ("Not in this view: the tower", size))


if __name__ == "__main__":
    unittest.main()
