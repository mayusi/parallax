"""the see-through OPENINGS a traced view's outline encloses (a trigger guard's window, the gap between a guard and the
grip), measured by themselves (kit/tools/silhouette_holes.py openings, called by kit/blender/rbx_precision.py) and weighed by kit fit (his V3 list, 3D stage
A.3: cavities). One silhouette IoU barely moves when the model closes a window; this is what says it."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import fit as F  # noqa: E402
import silhouette_holes as P  # noqa: E402

N = 1024


def guard(window=True, x0=300):
    """a side view: a slab with a trigger guard below it, its window open or closed"""
    m = np.zeros((N, N), bool)
    m[200:400, 100:900] = True                       # the slab
    m[400:600, x0:x0 + 300] = True                   # the guard
    if window:
        m[400:560, x0 + 40:x0 + 260] = False         # its window (enclosed: the slab above, the guard round it)
    return m


class Openings(unittest.TestCase):
    def test_the_same_window_matches_and_a_closed_one_is_said(self):
        ref = guard()
        same = P.openings(ref, guard(), mm_per_px=0.2)
        self.assertEqual(same["iou"], 1.0)
        self.assertEqual(same["filled"], 0.0)
        self.assertEqual(same["unit"], "mm2")
        self.assertAlmostEqual(same["reference"], 160 * 220 * 0.04, delta=1.0)
        closed = P.openings(ref, guard(window=False))
        self.assertEqual(closed["iou"], 0.0)
        self.assertEqual(closed["filled"], 1.0)
        self.assertEqual(closed["model"], 0.0)
        # the whole outline hardly notices: what the openings measure exists because of this
        m = guard(window=False)
        self.assertGreater((ref & m).sum() / (ref | m).sum(), 0.8)

    def test_a_window_in_the_wrong_place_matches_in_part(self):
        o = P.openings(guard(), guard(x0=360))
        self.assertGreater(o["iou"], 0.3)
        self.assertLess(o["iou"], 0.9)

    def test_nothing_enclosed_is_none_and_a_notch_open_to_the_outside_is_no_opening(self):
        slab = np.zeros((N, N), bool)
        slab[200:400, 100:900] = True
        self.assertIsNone(P.openings(slab, slab))
        notch = slab.copy()
        notch[350:400, 300:400] = False                 # open to the outside below: an outline, not a window
        self.assertIsNone(P.openings(notch, notch))

    def test_specks_and_dont_care_boxes_are_left_out(self):
        slab = np.zeros((N, N), bool)
        slab[200:400, 100:900] = True
        speck = slab.copy()
        speck[300, 500] = speck[301, 500] = False       # a render's edge noise: no window
        self.assertIsNone(P.openings(slab, speck))
        ref = guard()
        box = (slice(380, 600), slice(280, 620))        # the guard in a don't-care box: nothing to compare
        self.assertIsNone(P.openings(ref, guard(window=False), skip=[box]))
        part = np.zeros((N, N), bool)                   # ... or a part traced "outlines only", as a mask, grown
        part[400:600, 300:600] = True
        self.assertIsNone(P.openings(ref, guard(window=False), skip=[P.grow(part, 10)]))
        self.assertEqual(P.grow(part, 10).sum(), (220 * 320) - 4 * (10 * 11 // 2))   # (4-connected: cut corners)


class NamedOnly(unittest.TestCase):
    """only the openings the picture NAMES are compared (the review, 2026-11-18)"""

    def test_a_lightening_cut_the_picture_never_names_is_left_out(self):
        model = guard()
        model[250:350, 700:800] = False                 # a cut through the slab the trace does not name
        self.assertEqual(P.openings(guard(), model)["iou"], 1.0)

    def test_nothing_named_left_says_nothing_of_the_model_s_openings(self):
        slab = np.zeros((N, N), bool)
        slab[200:400, 100:900] = True
        self.assertIsNone(P.openings(slab, guard()))   # (the model's window: no named opening to hold it to)
        box = (slice(380, 600), slice(280, 620))
        holed = guard()
        holed[250:350, 700:800] = False
        self.assertIsNone(P.openings(guard(), holed, skip=[box]))


class RealMasks(unittest.TestCase):
    """the revolver's build 4 (the owner, 2026-11-11: "is some of the body not fully filled in?"): its real side masks"""

    def test_the_revolver_s_window_is_broken_open_not_covered(self):
        refs = os.path.join(HERE, "..", "..", "selftest", "refs")
        ref = P._png(os.path.join(refs, "revolver_b4_side_ref.png"))
        model = P._png(os.path.join(refs, "revolver_b4_side_model.png"))
        o = P.openings(ref, model, mm_per_px=0.25)
        self.assertGreater(o["reference"], 400)        # the photo's trigger guard window (530 mm2)
        self.assertLess(o["model"], 50)                 # the model encloses almost none of it ...
        self.assertLess(o["filled"], 0.1)               # ... and covers almost none: the wedge broke it open
        self.assertLess(o["iou"], 0.1)                  # (one outline IoU said 0.936)
        self.assertEqual(P.openings(ref, ref, mm_per_px=0.25)["iou"], 1.0)


class FitLoss(unittest.TestCase):
    def verdict(self, iou, openings):
        r = {"view": "side", "iou": iou, "aspect_model_vs_ref": 1.0}
        if openings is not None:
            r["openings"] = {"iou": openings}
        return {"facts": {"references": [r]}}

    def test_a_closed_window_costs_the_fit_more_than_its_share_of_the_outline(self):
        open_, closed = F.loss_of(self.verdict(0.95, 1.0))[0], F.loss_of(self.verdict(0.96, 0.0))[0]
        self.assertAlmostEqual(open_, 0.05)
        self.assertAlmostEqual(closed, 0.04 + F.OPENING_WEIGHT)
        self.assertLess(open_, closed)                  # a hair of outline never buys a window
        self.assertAlmostEqual(F.loss_of(self.verdict(0.95, None))[0], 0.05)   # no openings named: as before

    def test_a_held_out_view_s_openings_stay_out_of_the_loss(self):
        v = self.verdict(0.9, 0.0)
        v["facts"]["references"].append({"view": "front", "iou": 0.9, "aspect_model_vs_ref": 1.0})
        self.assertAlmostEqual(F.loss_of(v, hold="side")[0], 0.1)


if __name__ == "__main__":
    unittest.main()
