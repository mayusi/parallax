"""The references, solved together (kit/blender/rbx_agree.py; his D-R01; the 3D methods audit, stage L)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_agree as A  # noqa: E402


def rifle(side=0.25):
    """a rifle 1000 long, 250 high, 60 wide by its sourced sizes, and a side trace's own proportion"""
    return [A.size("pack length", "length", 1000, "high"), A.size("pack height", "height", 250, "medium"),
            A.size("pack width", "width", 60, "medium"), A.ratio("side trace", "height", "length", side)]


class Solve(unittest.TestCase):
    def test_claims_that_agree_give_their_sizes_back(self):
        s = A.solve(rifle())
        self.assertAlmostEqual(s["sizes"]["length"], 1000, delta=0.5)
        self.assertAlmostEqual(s["sizes"]["height"], 250, delta=0.5)
        self.assertAlmostEqual(s["ratios"]["height/length"], 0.25, places=3)
        self.assertTrue(all(o < 0.001 for o in s["off"]))
        self.assertEqual(A.contradictions(rifle()), [])

    def test_the_trusted_claim_pulls_harder(self):
        s = A.solve([A.size("maker", "length", 1000, "high"), A.size("a wiki", "length", 1100, "low")])
        self.assertLess(s["sizes"]["length"], 1010)                  # near the maker's, not half way
        self.assertGreater(s["sizes"]["length"], 1000)

    def test_proportions_alone_fix_no_size_but_do_fix_the_proportion(self):
        s = A.solve([A.ratio("side trace", "height", "length", 0.25), A.ratio("front trace", "height", "width", 4)])
        self.assertEqual(s["sizes"], {"length": None, "height": None, "width": None})
        self.assertAlmostEqual(s["ratios"]["height/length"], 0.25, places=4)
        self.assertAlmostEqual(s["ratios"]["width/length"], 0.0625, places=4)   # through the height: never said

    def test_an_axis_nobody_speaks_of_is_left_open(self):
        s = A.solve([A.size("pack length", "length", 1000, "high")])
        self.assertIsNone(s["sizes"]["width"])
        self.assertIsNone(s["ratios"]["height/length"])


class HeldOut(unittest.TestCase):
    def test_each_claim_is_predicted_by_the_others(self):
        h = {r["name"]: r for r in A.held_out(rifle())}
        self.assertAlmostEqual(h["side trace"]["others"], 0.25, places=4)       # from the two sourced sizes
        self.assertAlmostEqual(h["pack height"]["others"], 250, delta=0.5)      # from the length and the trace
        self.assertIsNone(h["pack width"]["others"])                           # nothing else speaks of the width

    def test_a_ring_of_three_names_all_three_the_least_trusted_first(self):
        # the drawing's length, its height and a photo of another proportion: each is "wrong" by the other two
        said = A.contradictions(rifle(side=0.33)[:2] + rifle(side=0.33)[3:])
        self.assertEqual(len(said), 3)
        self.assertTrue(said[0].startswith("pack height"), said[0])         # medium (5%) before the photo (4%)
        self.assertTrue(said[-1].startswith("pack length"), said[-1])       # the drawing's high (2%) last
        self.assertTrue(any(s.startswith("side trace says height is 0.33 of the length; the other references "
                                         "together say 0.25") for s in said), said)

    def test_with_a_second_photo_only_the_odd_one_is_named(self):
        claims = rifle() + [A.ratio("another photo", "height", "length", 0.33)]
        said = A.contradictions(claims)
        self.assertEqual(len(said), 1, said)
        self.assertTrue(said[0].startswith("another photo says height is 0.33"), said[0])

    def test_a_trusted_claim_is_not_blamed_for_loose_ones(self):
        # the review: a maker's 1000 against one wiki's 1100 named the MAKER (scored by its own 2% alone)
        self.assertEqual(A.contradictions([A.size("maker", "length", 1000, "high"),
                                           A.size("a wiki", "length", 1060, "low")]), [])
        # and a photo 8% off two trusted sizes is the one named, not the sizes
        said = A.contradictions(rifle(side=0.27) + [A.ratio("another photo", "height", "length", 0.25)])
        self.assertTrue(all(not s.startswith("pack") for s in said), said)

    def test_an_unknown_trust_is_refused(self):
        with self.assertRaises(ValueError):
            A.size("x", "length", 10, "High")

    def test_a_small_difference_inside_the_tolerances_is_no_contradiction(self):
        self.assertEqual(A.contradictions(rifle(side=0.257)), [])

    def test_with_three_sizes_of_one_axis_the_odd_one_is_first(self):
        claims = [A.size("maker", "length", 1000, "high"), A.size("museum", "length", 1004, "high"),
                  A.size("a forum post", "length", 1300, "low")]
        said = A.contradictions(claims)
        self.assertEqual(len(said), 1, said)                         # the two that agree are not blamed
        self.assertIn("a forum post says length 1300 mm", said[0])


class Built(unittest.TestCase):
    def test_a_build_off_the_agreed_proportion_is_said(self):
        s = A.solve(rifle())
        self.assertEqual(A.build_off(s, {"length": 1000, "height": 252, "width": 60}), [])
        said = A.build_off(s, {"length": 1000, "height": 320, "width": 60})
        self.assertEqual(said, ["its height is 320 mm; the references agree on 250 (28% off)"])   # said once
        p = A.solve([A.ratio("side trace", "height", "length", 0.25)])
        self.assertEqual(A.build_off(p, {"length": 4, "height": 1.28, "width": 1}),
                         ["its height is 0.32 of its length; the references agree on 0.25 (28% off)"])

    def test_a_bad_claim_is_refused(self):
        with self.assertRaises(ValueError):
            A.size("x", "depth", 10, "high")
        with self.assertRaises(ValueError):
            A.ratio("x", "height", "height", 1.0)
        with self.assertRaises(ValueError):
            A.size("x", "length", 0, "high")


if __name__ == "__main__":
    unittest.main()
