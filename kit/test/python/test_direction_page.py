"""kit world board / kit sfx board: the owner's review board from a game's direction docs."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import direction_page  # noqa: E402


class Board(unittest.TestCase):
    def setUp(self):
        if not os.path.isdir(os.path.join("games", "SampleRegion", "assets", "worlds", "direction")):
            self.skipTest("SampleRegion's direction docs are not in this checkout")

    def build(self, *extra):
        out = os.path.join(tempfile.mkdtemp(), "board.html")
        self.assertEqual(direction_page.main(["SampleRegion", "--out", out, *extra]), 0)
        return open(out, encoding="utf-8").read()

    def test_world_board_shows_frames_and_no_sound(self):
        page = self.build("--lane", "world")
        self.assertIn("data:image/jpeg;base64,", page)
        self.assertNotIn("data:audio/mpeg", page)
        self.assertIn("Stormhold", page)
        self.assertIn("Pillars", page)

    def test_sound_board_plays_sketches_and_shows_no_frames(self):
        page = self.build("--lane", "sfx")
        self.assertIn("data:audio/mpeg;base64,", page)
        self.assertNotIn('<div class="card"><img', page)  # (no world frames; its own sound script image is fine)
        self.assertGreaterEqual(page.count('class="card sound"'), 3)

    def test_parse_reads_letters_axes_and_media(self):
        doc = direction_page.parse(os.path.join("games", "SampleRegion", "assets", "worlds", "direction", "Stormhold.md"))
        self.assertEqual([d["letter"] for d in doc["dirs"]], ["A", "B", "C"])
        self.assertTrue(all(d["axes"] and d["file"] and os.path.isfile(d["file"]) for d in doc["dirs"]))
        self.assertEqual(len(doc["pillars"]), 3)


    def test_an_unknown_lane_is_refused(self):
        self.assertEqual(direction_page.main(["SampleRegion", "--lane", "anim", "--out", os.path.join(tempfile.mkdtemp(), "x.html")]), 2)

if __name__ == "__main__":
    unittest.main()
