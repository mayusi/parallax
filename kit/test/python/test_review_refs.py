"""The part review's reference rule: an answer counts only when it cites a picture that exists — the owner wants
every part (inside ones too) modelled from a reference, the exact object's or the closest similar one's."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import review_refs  # noqa: E402

BASE = "real: the hammer | attaches: its pin | works: cocks back"


class TestRefRule(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.repo, "refs"))
        with open(os.path.join(self.repo, "refs", "hammer_side.jpg"), "wb") as fh:
            fh.write(b"jpg")

    def test_no_ref_field(self):
        ok, probs = review_refs.ref_problems(BASE + " | verdict: ok", self.repo)
        self.assertEqual(ok, [])
        self.assertTrue(probs and "no ref" in probs[0])

    def test_prose_is_not_a_reference(self):
        _ok, probs = review_refs.ref_problems(BASE + " | ref: the 1911's usual hammer | verdict: ok", self.repo)
        self.assertTrue(probs and "names no picture" in probs[0])

    def test_missing_file(self):
        _ok, probs = review_refs.ref_problems(BASE + " | ref: refs/nope.png | verdict: ok", self.repo)
        self.assertTrue(probs and "not found" in probs[0])

    def test_existing_picture_with_a_note(self):
        body = BASE + " | ref: refs/hammer_side.jpg (a Colt's; similar ring hammer) | verdict: ok"
        ok, probs = review_refs.ref_problems(body, self.repo)
        self.assertEqual((ok, probs), (["refs/hammer_side.jpg"], []))

    def test_one_missing_of_two_is_named(self):
        body = BASE + " | ref: refs/hammer_side.jpg, refs/gone.png | verdict: ok"
        ok, probs = review_refs.ref_problems(body, self.repo)
        self.assertEqual(ok, ["refs/hammer_side.jpg"])
        self.assertTrue(any("gone.png" in p for p in probs))

    def test_a_dimension_row_is_a_reference(self):
        os.makedirs(os.path.join(self.repo, "kit", "real_specs"))
        with open(os.path.join(self.repo, "kit", "real_specs", "colt_m1911.json"), "w", encoding="utf-8") as fh:
            fh.write('[{"id": "4eb2b52b", "object": "colt m1911", "part": "safety", "dim": "pin", "value": 3.1}]')
        ok, probs = review_refs.ref_problems(BASE + " | ref: dims:4eb2b52b (the grip safety pin) | verdict: ok", self.repo)
        self.assertEqual((ok, probs), (["dims:4eb2b52b"], []))
        _ok, probs = review_refs.ref_problems(BASE + " | ref: dims:deadbeef | verdict: ok", self.repo)
        self.assertTrue(probs and "dims:deadbeef not found" in probs[0])

    def test_part_words(self):
        self.assertEqual(review_refs.part_words("SlideStopPlunger"), "slide stop plunger")
        self.assertEqual(review_refs.part_words("Round1Case"), "round case")


if __name__ == "__main__":
    unittest.main()
