"""A3 - the swing builder's solver (kit/anim/swing_mechanics.py, LIMITATIONS_FIXES_V4 13.4.1, card x9gk): every intent,
kind and weight plans a swing that keeps the contract (the chain pelvis +0 / torso +2 / shoulder +4 / arm +5 / blade +6
frames on the Hit, the lead foot planted >= 2 frames before it, a 0.25..0.60 stud pelvis drop carried by tilted legs,
the torso at 1,100..3,300 deg/s, a 0.6..1.7 stud shoulder slide, a 2..4 frame hold, an eased settle, the beats), and
check_swing catches each way a plan can break it - an arm-only swing, stilts, a sliding foot, no hold."""

import copy
import os
import sys
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import swing_mechanics as S  # noqa: E402

DESIGN = {"hit": 0.45, "duration": 0.95, "kind": "horizontal"}


class Plans(unittest.TestCase):
    def test_every_intent_kind_and_weight_keeps_the_contract(self):
        for intent in S.INTENT:
            for kind in S.AMPLITUDE:
                for weight in ("light", "heavy"):
                    plan = S.solve_swing({**DESIGN, "kind": kind, "weight": weight}, intent=intent)
                    self.assertEqual(S.check_swing(plan), [], (intent, kind, weight))

    def test_the_chain_peaks_in_order_and_the_blade_on_the_hit(self):
        plan = S.solve_swing(DESIGN)
        pk = plan["peaks"]
        self.assertEqual([pk[k] - pk["pelvis"] for k, _ in S.CHAIN], [d for _, d in S.CHAIN])
        self.assertEqual(pk["blade"], plan["hit"])

    def test_harder_intent_drops_lower_and_turns_faster_heavier_holds_longer(self):
        calm, hard = S.solve_swing(DESIGN, intent="calm"), S.solve_swing(DESIGN, intent="aggressive")
        self.assertLess(min(hard["channels"]["pelvis_y"]), min(calm["channels"]["pelvis_y"]))
        self.assertGreater(hard["params"]["turn"], calm["params"]["turn"])
        light = S.solve_swing({**DESIGN, "weight": "light"}, intent="calm")
        heavy = S.solve_swing({**DESIGN, "weight": "heavy"}, intent="calm")
        self.assertGreater(heavy["params"]["hold"], light["params"]["hold"])
        self.assertEqual(set(light["beats"]), {"windup", "strike", "hold", "settle"})

    def test_a_measured_reference_is_used_but_kept_in_the_contract(self):
        plan = S.solve_swing(DESIGN, ref_motion={"turn": 9000.0, "slide": 0.1, "drop": 0.33})
        self.assertEqual(plan["params"]["turn"], S.TURN[1])
        self.assertEqual(plan["params"]["slide"], S.SLIDE[0])
        self.assertAlmostEqual(plan["params"]["drop"], 0.33)
        self.assertEqual(S.check_swing(plan), [])

    def test_what_cannot_be_planned_is_said(self):
        for bad, word in (({**DESIGN, "kind": "spin"}, "kind"), ({**DESIGN, "hit": 0.05}, "Hit"),
                          ({**DESIGN, "hit": 1.2}, "Hit")):
            with self.assertRaises(ValueError) as e:
                S.solve_swing(bad)
            self.assertIn(word, str(e.exception))
        with self.assertRaises(ValueError):
            S.solve_swing(DESIGN, intent="furious")


class CheckCatches(unittest.TestCase):
    def setUp(self):
        self.plan = S.solve_swing(DESIGN, intent="proper")
        self.assertEqual(S.check_swing(self.plan), [])

    def broken(self, edit):
        p = copy.deepcopy(self.plan)
        edit(p)
        return " | ".join(S.check_swing(p))

    def test_an_arm_only_swing(self):   # (the body does not lead: the pelvis and torso peak with the arm)
        def edit(p):
            for k in ("pelvis_yaw", "torso_yaw"):
                v = np.asarray(p["channels"][k])
                p["channels"][k] = list(np.roll(v, 5))
        self.assertIn("chain:", self.broken(edit))

    def test_stilts(self):   # (the hip drops and the legs stay straight: the feet sink into the floor)
        self.assertIn("stilts", self.broken(lambda p: p["channels"].update(leg_tilt=[0.0] * p["frames"])))

    def test_a_foot_still_moving_at_the_hit(self):
        def edit(p):
            v = list(p["channels"]["lead_foot_z"])
            for f in range(p["hit"] - 3, p["hit"] + 1):
                v[f] = v[f] + 0.01 * (f - p["hit"] + 4)
            p["channels"]["lead_foot_z"] = v
        self.assertIn("lead foot", self.broken(edit))

    def test_no_hold_no_drop_no_slide_no_settle(self):
        self.assertIn("hold 0", self.broken(lambda p: p.update(hold_end=p["hit"])))
        self.assertIn("pelvis drop", self.broken(lambda p: p["channels"].update(
            pelvis_y=[0.0] * p["frames"], leg_tilt=[0.0] * p["frames"])))
        self.assertIn("shoulder slide", self.broken(lambda p: p["channels"].update(
            shoulder_slide=[x * 0.2 for x in p["channels"]["shoulder_slide"]])))
        self.assertIn("settle", self.broken(lambda p: p["beats"].update(settle=[0.9, 0.92])))


if __name__ == "__main__":
    unittest.main()
