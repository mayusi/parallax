""""A or B?" rounds (kit/grading/pairs.py): the owner's pairwise picks give their ranking (Bradley-Terry), say how
often a scorer agrees with them, and the page that collects the picks hides which build is which."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "grading"))
import pairs as P  # noqa: E402


def side(asset):
    return {"asset": asset, "project": "Parallax/grading", "script_sha": "abc", "tris": 100}


ROUND = [  # x beats y beats z, x beats z clearly
    {"a": side("x"), "b": side("y"), "winner": "a"},
    {"a": side("y"), "b": side("z"), "winner": "a"},
    {"a": side("z"), "b": side("x"), "winner": "b", "margin": 2},
    {"a": side("x"), "b": side("y"), "winner": "a"},
]


class TestPairs(unittest.TestCase):
    def test_strengths_recover_the_owners_order(self):
        st = P.strengths(ROUND)
        order = sorted(st, key=lambda n: -st[n])
        self.assertEqual([n.split("/")[-1] for n in order], ["x", "y", "z"])
        self.assertAlmostEqual(sum(st.values()), 3.0, places=6)

    def test_a_tie_splits_and_a_clear_win_counts_double(self):
        tie = P.strengths([{"a": side("p"), "b": side("q"), "winner": "tie"}])
        self.assertAlmostEqual(tie[P.key(side("p"))], tie[P.key(side("q"))], places=6)
        once = P.strengths([{"a": side("p"), "b": side("q"), "winner": "a"}, {"a": side("p"), "b": side("q"), "winner": "b"}])
        clear = P.strengths([{"a": side("p"), "b": side("q"), "winner": "a", "margin": 2},
                             {"a": side("p"), "b": side("q"), "winner": "b"}])
        self.assertAlmostEqual(once[P.key(side("p"))], once[P.key(side("q"))], places=6)
        self.assertGreater(clear[P.key(side("p"))], clear[P.key(side("q"))])

    def test_agreement_counts_the_owners_decided_pairs(self):
        share, right, decided, wrong, skipped = P.agreement(ROUND, {"x": 80, "y": 60, "z": 40})
        self.assertEqual((share, right, decided, skipped), (1.0, 4, 4, 0))
        share, right, decided, wrong, _ = P.agreement(ROUND, {"x": 40, "y": 60, "z": 80})
        self.assertEqual((share, right, decided), (0.0, 0, 4))
        self.assertEqual(len(wrong), 4)
        tied = P.agreement(ROUND + [{"a": side("x"), "b": side("z"), "winner": "tie"}], {"x": 80, "y": 60, "z": 40})
        self.assertEqual(tied[4], 1)  # the tie is skipped, never counted against the scorer

    def test_the_page_hides_which_build_is_which(self):
        from PIL import Image  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as d:
            for n in ("a.png", "b.png"):
                Image.new("RGB", (8, 8), (90, 90, 90)).save(os.path.join(d, n))
            lst = os.path.join(d, "list.json")
            with open(lst, "w", encoding="utf-8") as fh:
                json.dump({"title": "test", "pairs": [{"a": dict(side("x"), render="a.png"),
                                                       "b": dict(side("y"), render="b.png")}] * 3}, fh)
            out, n, missing = P.page(lst, os.path.join(d, "page.html"), seed=3)
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        self.assertEqual((n, missing), (3, []))
        self.assertNotIn("innerHTML", html)  # (built with DOM methods: nothing is parsed as markup)
        self.assertIn("local A-or-B page page.html", html)  # the round's source, for the import
        self.assertNotIn('"render"', html)  # file names never reach the page
        self.assertIn("data:image/jpeg;base64,", html)  # (shrunk to a JPEG: a page of render sheets stays light)


if __name__ == "__main__":
    unittest.main()
