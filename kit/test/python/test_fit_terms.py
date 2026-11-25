"""kit fit (kit/blender/fit.py) is MULTI-CONSTRAINT (his V3 list, 3D stage A.3 / D-R01): beside the outline, the parts
and the openings, the CROSS-SECTIONS (a.section_match) and the 3D FORM against a real model (a.form_match: the
depth and the cavities no picture shows) are terms of its loss, each reported apart. The Blender worker is stood in
for, so the fit's own arithmetic is what is tested."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import fit as F  # noqa: E402


def row(h, build, ref):
    return {"h": h, "build": None if build is None else {"width_mm": build[0], "depth_mm": build[1]},
            "reference": None if ref is None else {"width_mm": ref[0], "depth_mm": ref[1]}}


class Sections(unittest.TestCase):
    def test_each_slice_s_relative_error_a_missing_one_is_a_full_miss(self):
        self.assertIsNone(F.section_miss({}))
        self.assertAlmostEqual(F.section_miss({"section_match": [row(0.3, (30, 20), (30, 20))]}), 0.0)
        self.assertAlmostEqual(F.section_miss({"section_match": [row(0.3, (33, 20), (30, 20))]}), 0.05)
        self.assertAlmostEqual(F.section_miss({"section_match": [row(0.3, (30, 20), (30, 20)),
                                                                 row(0.5, None, (30, 20))]}), 0.5)
        # (each measure capped at 1: ten times too wide, the depth right)
        self.assertAlmostEqual(F.section_miss({"section_match": [row(0.3, (300, 20), (30, 20))]}), 0.5)

    def test_a_boxy_slice_as_wide_and_deep_as_the_wrapped_one_is_still_a_miss(self):
        # (the real numbers of the fixtures build_section_boxy / build_section_wrapped: 30 x 50 mm both, squareness
        #  17.4 against the reference's 1.99)
        boxy = row(0.3, (30, 50), (30, 50))
        boxy["build"]["squareness"], boxy["reference"]["squareness"] = 17.4, 1.99
        self.assertAlmostEqual(F.section_miss({"section_match": [boxy]}), 1 / 3)
        wrapped = row(0.3, (30, 50), (30, 50))
        wrapped["build"]["squareness"], wrapped["reference"]["squareness"] = 1.98, 1.99
        self.assertLess(F.section_miss({"section_match": [wrapped]}), 0.01)

    def test_a_slice_the_reference_has_in_pieces_is_left_out(self):
        # (marked on the row, as rbx_inspect writes it: another reference's slice at the same height still counts)
        cut = row(0.45, (30, 20), (10, 5))
        cut["skipped"] = True
        deep = {"section_match": [row(0.3, (30, 20), (30, 20)), cut, row(0.45, (33, 20), (30, 20))]}
        self.assertAlmostEqual(F.section_miss(deep), 0.025)


class Form(unittest.TestCase):
    def test_the_mean_gap_both_ways_over_twice_the_bar(self):
        self.assertIsNone(F.form_miss({}))
        self.assertAlmostEqual(F.form_miss({"form_match": [{"extra_mean_mm": 1.0, "missing_mean_mm": 2.0,
                                                            "bar_mm": 3.0}]}), 0.5)
        self.assertAlmostEqual(F.form_miss({"form_match": [{"extra_mean_mm": 1.5, "missing_mean_mm": 1.5}]}),
                               3.0 / (2 * F.FORM_BAR_MM))
        self.assertAlmostEqual(F.form_miss({"form_match": [{"extra_mean_mm": 40, "missing_mean_mm": 9,
                                                            "bar_mm": 2}]}), 1.0)
        # (a side that measured nothing - an empty surface - is a full miss, never a perfect form)
        self.assertAlmostEqual(F.form_miss({"form_match": [{"extra_mean_mm": None, "missing_mean_mm": None}]}), 1.0)

    def test_a_crashed_trial_scores_worse_than_any_loss_the_terms_make(self):
        worst = {"facts": {"references": [{"view": "side", "iou": 0.0, "aspect_model_vs_ref": 3.0,
                                           "parts": {"a": {"error": "x"}}, "openings": {"iou": 0.0}}],
                           "deep": {"section_match": [row(0.3, None, (1, 1))],
                                    "form_match": [{"extra_mean_mm": None, "missing_mean_mm": None}]}}}
        self.assertLess(F.loss_of(worst)[0], F.CRASH_LOSS)


class Terms(unittest.TestCase):
    def test_every_term_reported_apart_and_summed(self):
        v = {"facts": {"references": [{"view": "side", "iou": 0.9, "aspect_model_vs_ref": 1.0,
                                       "openings": {"iou": 0.5}}],
                       "deep": {"section_match": [row(0.3, (33, 20), (30, 20))],
                                "form_match": [{"extra_mean_mm": 1.0, "missing_mean_mm": 2.0, "bar_mm": 3.0}]}}}
        terms, views = F.terms_of(v)
        self.assertEqual(set(terms), {"outline", "openings", "sections", "form"})
        self.assertAlmostEqual(terms["outline"], 0.1)
        self.assertAlmostEqual(terms["sections"], F.SECTION_WEIGHT * 0.05)
        self.assertAlmostEqual(terms["form"], F.FORM_WEIGHT * 0.5)
        self.assertAlmostEqual(F.loss_of(v)[0], sum(terms.values()))
        self.assertEqual(views, {"side": 0.9})

    def test_a_build_with_only_sections_or_form_can_still_be_fitted(self):
        v = {"facts": {"deep": {"section_match": [row(0.3, (30, 20), (30, 20))]}}}
        self.assertAlmostEqual(F.loss_of(v)[0], 0.0)
        self.assertIsNone(F.loss_of({"facts": {}})[0])


class Run(unittest.TestCase):
    """the whole fit, its worker stood in for: the section steers it where no picture does"""

    def test_a_slice_s_width_steers_the_fit(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "models"))
        with open(os.path.join(tmp.name, "models", "build_x.py"), "w", encoding="utf-8") as fh:
            fh.write("# a stand-in\n")
        keep = F.Worker
        self.addCleanup(setattr, F, "Worker", keep)

        class W:
            def __init__(self, _build):
                pass

            def build(self, _script, trial):
                x = trial.get("x", 0.2)     # the grip's width: 20 + 40 x mm; the reference's slice is 44 mm wide
                return {"facts": {"params": {"x": {"value": 0.2, "lo": 0.0, "hi": 1.0}},
                                  "deep": {"section_match": [row(0.3, (20 + 40 * x, 20), (44, 20))]}}}

        F.Worker = W
        out = io.StringIO()
        with redirect_stdout(out):
            F.main(["x", "--models", os.path.join(tmp.name, "models"), "--build", tmp.name, "--evals", "60"])
        r = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertEqual(r["status"], "pass", r["summary"])
        self.assertAlmostEqual(r["fit"]["params"]["x"], 0.6, delta=0.03)
        self.assertGreater(r["fit"]["terms_before"]["sections"], r["fit"]["terms_after"]["sections"])


if __name__ == "__main__":
    unittest.main()
