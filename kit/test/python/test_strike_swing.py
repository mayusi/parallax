"""A3 in the strike builder (kit/anim/strike.py apply_swing, card x9gk): a move with `swing` is RETIMED as a whip - the
body reads the authored keys ahead of the clock and waits at its Hit pose, the blade snaps last - so the torso's turn
peaks BEFORE the blade's tip (GreatswordSlash1 as authored: the torso peaked at the Hit, after the blade - an arm-led
cut); the Hit pose is held and the events after it move with it; the body sinks at least the plan's drop (never two
drops); a move without `swing` is untouched; no Hit / the owner's own arm poses are refused."""

import copy
import json
import os
import sys
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import strike as S  # noqa: E402
import swing_mechanics as SM  # noqa: E402

MOVE = os.path.join(ROOT, "assets", "animations", "GreatswordSlash1.move.json")


def load():
    with open(MOVE, encoding="utf-8") as fh:
        return json.load(fh)


def torso_peak_t(clip):
    f = np.asarray(clip["joints"]["Torso"]["frames"], dtype=np.float64)
    x, y, z, w = f[:, 0], f[:, 1], f[:, 2], f[:, 3]
    yaw = np.degrees(np.unwrap(np.arctan2(2 * (w * y + x * z), 1 - 2 * (x * x + y * y))))
    rate = np.abs(np.diff(yaw))
    return float(np.asarray(clip["times"])[1:][int(np.argmax(rate))])


class StrikeSwing(unittest.TestCase):
    def test_a_move_without_swing_is_untouched(self):
        if not os.path.isfile(MOVE):
            self.skipTest("the author's assets/animations/GreatswordSlash1.move.json is not shipped with the kit")
        mv = load()
        keys = S.fill_keys(mv["keys"])
        out, m2 = S.apply_swing(keys, mv, 30)
        self.assertIs(out, keys)
        self.assertIs(m2, mv)

    def test_the_body_leads_and_the_blade_snaps_last(self):
        if not os.path.isfile(MOVE):
            self.skipTest("the author's assets/animations/GreatswordSlash1.move.json is not shipped with the kit")
        plain, _ = S.generate(copy.deepcopy(load()))
        mv = load()
        mv["swing"] = {"kind": "horizontal", "intent": "proper"}
        whip, stats = S.generate(copy.deepcopy(mv))
        hit = next(e["t"] for e in whip["events"] if e["name"] == "Hit")
        self.assertGreaterEqual(torso_peak_t(plain), 0.267)                 # as authored: torso at / after the blade
        self.assertLess(torso_peak_t(whip), stats["tip_peak_t"])           # retimed: the torso first
        self.assertLessEqual(stats["tip_peak_t"], hit + 1e-6)              # the blade by the Hit

    def test_the_hit_pose_is_held_and_later_events_move_with_it(self):
        if not os.path.isfile(MOVE):
            self.skipTest("the author's assets/animations/GreatswordSlash1.move.json is not shipped with the kit")
        mv = load()
        mv["swing"] = {"kind": "horizontal", "intent": "proper", "weight": "heavy"}
        keys, m2 = S.apply_swing(S.fill_keys(mv["keys"]), mv, 30)
        hold = SM.HOLD[1] / SM.FPS
        hit = next(e["t"] for e in mv["events"] if e["name"] == "Hit")
        self.assertAlmostEqual(float(keys[-1]["t"]), float(mv["keys"][-1]["t"]) + hold, places=3)
        old = {e["name"]: e["t"] for e in mv["events"]}
        new = {e["name"]: e["t"] for e in m2["events"]}
        self.assertAlmostEqual(new["Hit"], old["Hit"])
        for name, t in old.items():
            if t > hit:
                self.assertAlmostEqual(new[name], t + hold, places=5, msg=name)
        at_hit = [k for k in keys if abs(k["t"] - hit) < 1e-6 or (hit < k["t"] <= hit + hold)]
        self.assertTrue(all(k["grip"] == at_hit[0]["grip"] and k["dir"] == at_hit[0]["dir"] for k in at_hit))

    def test_the_body_sinks_at_least_the_plan_and_never_twice(self):
        if not os.path.isfile(MOVE):
            self.skipTest("the author's assets/animations/GreatswordSlash1.move.json is not shipped with the kit")
        mv = load()
        mv["swing"] = {"kind": "horizontal", "intent": "aggressive"}
        src = S.fill_keys(mv["keys"])
        keys, _ = S.apply_swing(src, mv, 30)
        hit = next(e["t"] for e in mv["events"] if e["name"] == "Hit")
        y0 = float(src[0]["pos"][1])
        k = next(k for k in keys if abs(k["t"] - hit) < 1e-6)
        self.assertLessEqual(k["pos"][1], y0 - SM.INTENT["aggressive"]["drop"] + 1e-4)   # at least the plan's depth
        authored = S.sample(src, hit)["pos"][1]
        self.assertGreaterEqual(k["pos"][1], min(authored, y0 - SM.INTENT["aggressive"]["drop"]) - 1e-4)  # not twice

    def test_what_cannot_be_retimed_is_refused(self):
        if not os.path.isfile(MOVE):
            self.skipTest("the author's assets/animations/GreatswordSlash1.move.json is not shipped with the kit")
        mv = load()
        mv["swing"] = {"kind": "horizontal"}
        mv["events"] = [e for e in mv["events"] if e["name"] != "Hit"]
        with self.assertRaises(ValueError) as e:
            S.apply_swing(S.fill_keys(mv["keys"]), mv, 30)
        self.assertIn("Hit", str(e.exception))
        mv = load()
        mv["swing"] = {"kind": "horizontal"}
        keys = S.fill_keys(mv["keys"])
        keys[2]["arms_pose"] = {"right": [0, 0, 0]}
        with self.assertRaises(ValueError) as e:
            S.apply_swing(keys, mv, 30)
        self.assertIn("arms_pose", str(e.exception))


if __name__ == "__main__":
    unittest.main()
