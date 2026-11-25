"""kit/audio/check.py - the take gate reads the owner's measured ear (kit/audio/booth.py's sfx_taste.json): a take far
from the loved takes on a trait the owner leans on is noted beside it (a report, never a gate); nothing until the booth
has its targets. Run: python kit/test/python/run.py -k sfx_ear"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "audio"))
import check as C  # noqa: E402

TASTE = {"verdicts": 7, "leans": [{"trait": "brightness_hz", "r": 0.7, "owner_prefers": "brighter sounds"},
                                  {"trait": "lufs", "r": 0.5, "owner_prefers": "louder sounds"}],
         "targets": {"brightness_hz": 4000.0, "lufs": -14.0, "tail_ms": 300.0}}


class EarTest(unittest.TestCase):
    def test_no_targets_yet_means_no_note(self):
        self.assertEqual(C.ear_notes({"brightness_hz": 500}, {"verdicts": 4, "leans": []}), [])
        self.assertEqual(C.ear_notes({"brightness_hz": 500}, {}), [])

    def test_a_take_far_from_the_loved_ones_on_a_leaned_trait_is_noted(self):
        notes = C.ear_notes({"brightness_hz": 1500, "lufs": -14.5, "tail_ms": 900}, TASTE)
        self.assertEqual(len(notes), 1)  # brightness 1.4 octaves off; loudness near; tail is no leaning
        self.assertIn("brightness_hz 1500 vs the loved takes' 4000", notes[0])
        self.assertIn("brighter sounds", notes[0])

    def test_close_takes_get_no_note(self):
        self.assertEqual(C.ear_notes({"brightness_hz": 3300, "lufs": -12.0}, TASTE), [])

    def test_the_taste_file_is_read_and_a_broken_one_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(TASTE, f)
            self.assertEqual(C.load_taste(p)["verdicts"], 7)
            with open(p, "w", encoding="utf-8") as f:
                f.write("{broken")
            self.assertEqual(C.load_taste(p), {})


if __name__ == "__main__":
    unittest.main()
