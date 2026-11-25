"""the RELIEF inside a view, picture against model (kit/tools/depth_relief.py; his V3 list, 3D stage A.3 "depth
cavities"): a recess the picture has and the model does not is named where it is; a photo's depth is only relative,
so its scale and offset never matter; the model may face either way; and kit fit weighs it (fit.py's depth term)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import depth_relief as D  # noqa: E402
import fit as F  # noqa: E402

H, W = 200, 600


def mask():
    m = np.zeros((H, W), bool)
    m[20:180, 20:580] = True
    return m


def plate(recess=True, at=(380, 480)):
    """a gently curved plate, a recess cut in it (a fuller, a pocket); larger = nearer"""
    yy, xx = np.mgrid[:H, :W]
    n = -0.0005 * (xx - 300.0) ** 2 / 300.0
    if recess:
        n[60:140, at[0]:at[1]] -= 1.0
    return n


def photo(recess=True):
    rng = np.random.default_rng(0)       # (a relative depth: scaled, offset, a little noisy)
    return 0.3 * plate(recess) + 0.02 * rng.standard_normal((H, W)) + 5.0


class Relief(unittest.TestCase):
    def test_the_same_relief_runs_together_whatever_the_photo_s_scale(self):
        r = D.compare(photo(), mask(), plate(), mask())
        self.assertGreater(r["corr"], 0.8)
        self.assertEqual(r["windows"], [])
        self.assertAlmostEqual(r["scale"], 0.3, delta=0.05)

    def test_a_recess_the_model_lacks_is_named_where_it_is(self):
        r = D.compare(photo(), mask(), plate(recess=False), mask())
        self.assertLess(r["corr"], 0.2)
        first = r["windows"][0]
        self.assertEqual(first["kind"], "missing")
        self.assertEqual(first["across"], [62, 75])    # (the recess spans 64-82% of the plate's length)

    def test_a_recess_in_the_wrong_place_is_worse_than_the_right_one(self):
        right = D.compare(photo(), mask(), plate(), mask())["corr"]
        wrong = D.compare(photo(), mask(), plate(at=(100, 200)), mask())["corr"]   # (at the other END: the mirror
        #                                       image of the right place - its outline the same, never chosen for it)
        self.assertLess(wrong, right - 0.5)

    def test_the_model_facing_the_other_way_is_found_by_its_outline(self):
        m = mask()
        m[150:180, 20:120] = False                         # (an outline that is not its own mirror image)
        r = D.compare(photo(), m, plate()[:, ::-1], m[:, ::-1])
        self.assertTrue(r["mirrored"])
        self.assertGreater(r["corr"], 0.8)

    def test_nothing_shared_is_none(self):
        empty = np.zeros((H, W), bool)
        self.assertIsNone(D.compare(photo(), mask(), plate(), empty))


class FitTerm(unittest.TestCase):
    def test_the_relief_is_a_term_of_the_fit_weighed_by_the_view(self):
        v = {"facts": {"references": [{"view": "side", "iou": 1.0, "aspect_model_vs_ref": 1.0,
                                       "depth": {"corr": 0.4}}]}}
        terms, _ = F.terms_of(v)
        self.assertAlmostEqual(terms["depth"], F.DEPTH_WEIGHT * 0.3)
        v["facts"]["references"][0]["depth"] = {"error": "no photo depth"}
        self.assertNotIn("depth", F.terms_of(v)[0])          # (nothing compared: no term, never a free zero)
        self.assertNotIn("depth", F.terms_of(v, hold="side")[0])


if __name__ == "__main__":
    unittest.main()
