"""kit/vfx/evolve.py + kit/tools/gallery.py - the OWNER's evolve picks steer the next round's axes (research proposal
10); an agent's pick never counts, and with no pick of the owner's the alternating rule is exactly as before.
Run: python kit/test/python/run.py -k test_evolve_taste"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import evolve as E  # noqa: E402

ROUND1 = [{"k": 1, "axis": "tempo", "delta": {"time": 0.8}}, {"k": 2, "axis": "size", "delta": {"scale": 1.25}},
          {"k": 3, "axis": "colour", "delta": {"saturate": 0.3}}, {"k": 4, "axis": "layer mix", "delta": {"mute": ["ring*"]}}]


def state(by, k=3):
    return {"effect": "fx", "base": E.compose({}, ROUND1[k - 1]["delta"]),
            "rounds": [{"round": 1, "variants": [dict(v) for v in ROUND1], "pick": {"k": k, "words": "w", "by": by}}]}


class EvolveTasteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        os.makedirs(os.path.join("assets", "effects", "evolve"))
        layers = [{"name": f"ring_{i}", "kind": "sprite"} for i in range(3)] + [{"name": "spark_1", "kind": "sprite"}]
        json.dump({"layers": layers}, open(os.path.join("assets", "effects", "fx.json"), "w"))

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def make(self, st):
        json.dump(st, open(os.path.join("assets", "effects", "evolve", "fx.json"), "w"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            E.cmd_make("fx", {})
        return json.loads(buf.getvalue().strip().splitlines()[-1])

    def colour(self, r):
        return next(v for v in r["variants"] if v["axis"] == "colour")

    def test_an_owner_pick_steers_the_next_round(self):
        m, picks = E.taste(state("owner"))
        self.assertEqual((picks, m.evidence()), (1, 3))  # the colour variant beat the other three
        r = self.make(state("owner"))
        # round 2 is a "the other way" round (calmer colours by the rule); the owner picked MORE saturated
        self.assertGreater(self.colour(r)["delta"]["saturate"], 0)
        self.assertIn("colour", r["steered"])
        self.assertIn("steered by 1 pick(s) of the owner's", r["summary"])
        saved = json.load(open(os.path.join("assets", "effects", "evolve", "fx.json")))
        self.assertEqual(saved["rounds"][-1]["base"], {"saturate": 0.3})  # each round keeps its own base

    def test_an_agents_pick_never_counts_and_the_rule_stays(self):
        m, picks = E.taste(state("agent (owner blanket approval 2026-10-16)"))
        self.assertEqual((picks, m.evidence()), (0, 0))
        r = self.make(state("agent (owner blanket approval 2026-10-16)"))
        self.assertEqual(r["steered"], [])
        self.assertIn("an agent's pick never counts", r["summary"])
        # the rule: round 2 goes the other way, the picked axis (colour) further the same way, half a step
        self.assertAlmostEqual(self.colour(r)["delta"]["saturate"], 0.15)
        self.assertEqual(next(v for v in r["variants"] if v["axis"] == "tempo")["delta"], {"time": 1.25})

    def test_the_owners_lean_overrides_the_alternating_rule(self):
        """round 2 is a 'the other way' round: the rule takes colour DOWN (-0.25) - a model that has learned the owner
        wants MORE colour turns it up, a full step; an axis it has no opinion on keeps the rule's step"""

        class Leaning:
            def evidence(self):
                return 1

            def predict(self, points):
                import numpy as np  # noqa: PLC0415
                return np.asarray([p["saturate"] for p in points], float), np.zeros(len(points))

        st = state("owner", k=1)  # the owner's last pick was tempo: colour is not the 'further' axis
        saved = E.taste
        E.taste = lambda s: (Leaning(), 1)
        try:
            r = self.make(st)
        finally:
            E.taste = saved
        self.assertEqual(self.colour(r)["delta"], {"saturate": 0.3})  # up, a full step, against the rule's -0.25
        self.assertIn("your picks lean this way", self.colour(r)["words"])
        self.assertEqual(r["steered"], ["colour"])
        size = next(v for v in r["variants"] if v["axis"] == "size")
        self.assertEqual(size["delta"], {"scale": 0.85})  # no opinion on size: the rule's step stays

    def test_none_beat_the_base_teaches_too(self):
        st = state("owner")
        st["rounds"][0]["pick"] = {"k": 0, "words": "none", "by": "owner"}
        st["base"] = {}
        m, picks = E.taste(st)
        self.assertEqual((picks, m.evidence()), (1, 4))  # the base beat all four


if __name__ == "__main__":
    unittest.main()
