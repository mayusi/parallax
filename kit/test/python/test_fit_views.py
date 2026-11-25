"""kit fit (kit/blender/fit.py): the views weighed by how far their pictures are trusted, and one view HELD OUT - a fit
that improves the views it saw while the one it never saw gets worse is an overfit, said, and never written (his
V3 list, 3D stage A.3). The Blender worker is stood in for: a 'build' whose silhouette IoU per view is a function of
the trial value, so the fit's own logic is what is tested."""

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


def verdict(x, views):
    return {"facts": {"params": {"x": {"value": x, "lo": 0.0, "hi": 1.0}},
                      "references": [{"view": v, "iou": max(0.0, 1.0 - abs(x - best)), "aspect_model_vs_ref": 1.0}
                                     for v, best in views.items()]}}


class Loss(unittest.TestCase):
    def test_weights_tilt_the_loss_and_the_held_out_view_is_not_in_it(self):
        v = verdict(0.5, {"side": 0.5, "front": 0.0})          # side 1.0, front 0.5
        self.assertAlmostEqual(F.loss_of(v)[0], 0.25)
        self.assertAlmostEqual(F.loss_of(v, {"front": 0.0})[0], 0.0)
        self.assertAlmostEqual(F.loss_of(v, {"front": 0.4})[0], 1 - (1.0 + 0.4 * 0.5) / 1.4)
        loss, views = F.loss_of(v, hold="front")
        self.assertAlmostEqual(loss, 0.0)
        self.assertEqual(views, {"side": 1.0, "front": 0.5})  # (still measured and said)
        self.assertIsNone(F.loss_of(verdict(0.5, {"side": 0.5}), hold="side")[0])

    def test_the_linked_parts_are_in_the_loss_and_a_part_not_found_is_a_full_miss(self):
        v = verdict(0.5, {"side": 0.5})                           # the whole outline: a perfect match
        self.assertAlmostEqual(F.loss_of(v)[0], 0.0)
        v["facts"]["references"][0]["parts"] = {"guard": {"iou": 0.6}, "grip": {"iou": 1.0}}
        self.assertAlmostEqual(F.loss_of(v)[0], F.PART_WEIGHT * 0.2)
        v["facts"]["references"][0]["parts"]["pommel"] = {"error": "no model part named Pommel"}
        self.assertAlmostEqual(F.loss_of(v)[0], F.PART_WEIGHT * (1 - (0.6 + 1.0 + 0.0) / 3))
        self.assertIsNone(F.part_miss({"view": "side", "iou": 1.0}))

    def test_weights_are_read_and_checked(self):
        self.assertEqual(F.parse_weights("side=1, front=0.4"), {"side": 1.0, "front": 0.4})
        self.assertEqual(F.parse_weights(""), {})
        for bad in ("side", "side=1.5"):
            with self.assertRaises(ValueError):
                F.parse_weights(bad)


class Run(unittest.TestCase):
    """the whole fit, its worker stood in for"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, "models"))
        with open(os.path.join(self.tmp.name, "models", "build_x.py"), "w", encoding="utf-8") as fh:
            fh.write("# a stand-in\n")
        keep = F.Worker
        self.addCleanup(setattr, F, "Worker", keep)

    def tearDown(self):
        self.tmp.cleanup()

    def run_fit(self, views, *extra):
        class W:
            def __init__(self, _build):
                pass

            def build(self, _script, trial):
                return verdict(trial.get("x", 0.5), views)

        F.Worker = W
        out = io.StringIO()
        with redirect_stdout(out):
            F.main(["x", "--models", os.path.join(self.tmp.name, "models"), "--build", self.tmp.name, "--evals", "60",
                    *extra])
        return json.loads(out.getvalue().strip().splitlines()[-1])

    def written(self):
        return os.path.isfile(os.path.join(self.tmp.name, "models", "x.params.json"))

    def test_a_fit_that_the_held_out_view_disagrees_with_is_an_overfit_and_nothing_is_written(self):
        # (the side picture wants x = 0.9, the front x = 0.3: fitting to the side alone pulls the front away)
        r = self.run_fit({"side": 0.9, "front": 0.3}, "--hold", "front", "--write")
        self.assertEqual(r["status"], "fail")
        self.assertIn("OVERFIT", r["summary"])
        self.assertTrue(r["fit"]["held_out"]["overfit"])
        self.assertFalse(self.written())

    def test_a_fit_the_held_out_view_agrees_with_is_written(self):
        r = self.run_fit({"side": 0.8, "front": 0.8}, "--hold", "front", "--write")
        self.assertEqual(r["status"], "pass", r["summary"])
        held = r["fit"]["held_out"]
        self.assertFalse(held["overfit"])
        self.assertGreater(held["after"], held["before"])
        self.assertTrue(self.written())

    def test_a_held_out_view_the_asset_has_not_is_refused(self):
        r = self.run_fit({"side": 0.8}, "--hold", "top")
        self.assertEqual(r["status"], "fail")
        self.assertIn("no reference view of that name", r["summary"])

    def test_where_a_part_sits_steers_the_fit_when_the_whole_outline_cannot(self):
        # (the outline matches at any x - a guard slid along the blade leaves it the same - but the guard part
        #  sits right only at x = 0.7)
        class W:
            def __init__(self, _build):
                pass

            def build(self, _script, trial):
                x = trial.get("x", 0.2)
                v = verdict(x, {"side": x})
                v["facts"]["params"]["x"]["value"] = 0.2
                v["facts"]["references"][0]["parts"] = {"guard": {"iou": max(0.0, 1.0 - 2 * abs(x - 0.7))}}
                return v

        F.Worker = W
        out = io.StringIO()
        with redirect_stdout(out):
            F.main(["x", "--models", os.path.join(self.tmp.name, "models"), "--build", self.tmp.name, "--evals", "60"])
        r = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertAlmostEqual(r["fit"]["params"]["x"], 0.7, delta=0.05)

    def test_a_trusted_view_pulls_the_fit_its_way(self):
        r = self.run_fit({"side": 0.9, "front": 0.2}, "--weights", "side=1,front=0.1")
        self.assertGreater(r["fit"]["params"]["x"], 0.8)
        r = self.run_fit({"side": 0.9, "front": 0.2}, "--weights", "side=0.1,front=1")
        self.assertLess(r["fit"]["params"]["x"], 0.3)


if __name__ == "__main__":
    unittest.main()
