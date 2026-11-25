"""The animation pipeline's Python core (kit/anim/clip.py): forward kinematics lands every part on the engine-read
rest offsets, the R15 joint names fold onto R6 limbs, and the motion gates catch what they are for — a one-frame
snap, a planted foot that slides, a loop that ends elsewhere — while a clean eased swing with its Hit just after
the fastest frame passes."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C  # noqa: E402

FPS = 30


def qx(deg):
    """a rotation about X as {x, y, z, w}"""
    a = math.radians(deg) / 2
    return [math.sin(a), 0.0, 0.0, math.cos(a)]


def make_clip(name, joints, duration, loop=False, events=None, rig="R15"):
    n = int(round(duration * FPS)) + 1
    times = [i / FPS for i in range(n)]
    out = {"schema": 1, "name": name, "rig": rig, "fps": FPS, "duration": duration, "loop": loop, "priority": "Action",
           "joints": {}, "times": times, "events": events or []}
    for jname, fn in joints.items():
        out["joints"][jname] = {"frames": [fn(i, t) for i, t in enumerate(times)]}
    return out


class Rigs(unittest.TestCase):
    def test_rest_fk_matches_the_engine(self):
        for name in ("r6", "r15"):
            rig = C.load_rig(name, ROOT)
            world = C.fk(rig)
            for part in rig["order"]:
                got = world[part][:3, 3]
                want = np.array(rig["rest"][part][:3])
                self.assertLess(np.abs(got - want).max(), 2e-3, f"{name} {part}: {got} vs {want}")

    def test_r15_arm_forward(self):
        rig = C.load_rig("r15", ROOT)
        world = C.fk(rig, {"RightUpperArm": (C.euler_mat((90, 0, 0)), np.zeros(3))})
        hand = world["RightHand"][:3, 3]
        self.assertLess(hand[2], -1.5)
        self.assertAlmostEqual(hand[1], 0.85, delta=0.05)

def luau_clip(spec_path, rig=None):
    """the kit's own clip of a spec (kit/lib/anim.luau through kit/anim/clip_of.luau)"""
    out = os.path.join(tempfile.mkdtemp(), "clip.json")
    args = ["lune", "run", "kit/anim/clip_of.luau", spec_path, out] + ([rig] if rig else [])
    r = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    with open(out, encoding="utf-8") as fh:
        return json.load(fh)


class TwoSamplers(unittest.TestCase):
    def test_python_sampler_agrees_with_the_kit(self):
        tmp = tempfile.mkdtemp()
        spec_path = os.path.join(tmp, "T.json")
        with open(os.path.join(ROOT, "kit", "templates", "anim.json"), encoding="utf-8") as fh:
            spec = json.loads(fh.read().replace("__NAME__", "T"))
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        clip = luau_clip(spec_path)
        expected = C.spec_frames(spec, clip["times"])
        self.assertEqual(set(expected), set(clip["joints"]))
        worst = 0.0
        for name, frames in expected.items():
            got = clip["joints"][name]["frames"]
            self.assertEqual(len(got), len(frames))
            for a_, b_ in zip(frames, got):
                worst = max(worst, C.quat_angle(a_, b_))
                self.assertLess(max(abs(x - y) for x, y in zip(a_[4:], b_[4:])), 1e-4)
        self.assertLess(worst, 0.05, f"the two samplers differ by {worst:.3f} degrees")

    def test_the_r6_fold_keeps_the_feet_planted(self):
        tmp = tempfile.mkdtemp()
        spec_path = os.path.join(tmp, "W.json")
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump({"name": "W", "keys": [{"t": 0, "pose": {"UpperTorso": [0, 0, 0], "Right Arm": [20, 0, 0]}},
                                             {"t": 0.4, "pose": {"UpperTorso": [0, 40, 0], "Right Arm": [120, 0, 10]}}]}, fh)
        r6 = luau_clip(spec_path, "R6")
        self.assertEqual(r6["rig"], "R6")
        rig = C.load_rig("r6", ROOT)
        m = C.metrics(r6, rig)
        self.assertEqual([p for p in m["problems"] if p.startswith("foot")], [], m["problems"])
        self.assertLess(m["feet"]["slide_max_studs_frame"], 0.01)


class Gates(unittest.TestCase):
    def setUp(self):
        self.rig = C.load_rig("r15", ROOT)

    def test_a_one_frame_snap_is_a_pop(self):
        clip = make_clip("Pop", {"RightUpperArm": lambda i, t: qx(0 if i < 10 else 150) + [0, 0, 0]}, 1.0)
        m = C.metrics(clip, self.rig)
        self.assertTrue(any(p.startswith("pops") for p in m["problems"]), m["problems"])
        self.assertEqual(m["joints"]["RightUpperArm"]["pops"][0]["frame"], 10)

    def test_planted_feet_must_not_slide(self):
        clip = make_clip("Slide", {"LowerTorso": lambda i, t: [0, 0, 0, 1, 6 * t, 0, 0]}, 1.0)
        m = C.metrics(clip, self.rig)
        self.assertTrue(any(p.startswith("foot slide") for p in m["problems"]), m["problems"])
        self.assertGreater(m["feet"]["slide_max_studs_frame"], 0.15)

    def test_a_loop_must_end_where_it_starts(self):
        clip = make_clip("Seam", {"Head": lambda i, t: qx(40 * t) + [0, 0, 0]}, 1.0, loop=True)
        m = C.metrics(clip, self.rig)
        self.assertTrue(any(p.startswith("loop seam") for p in m["problems"]), m["problems"])
        self.assertAlmostEqual(m["loop_seam_deg"], 40, delta=0.1)

    def test_a_clean_swing_with_the_hit_after_the_peak_passes(self):
        # the arm swings 0 -> 120 over frames 5..15 with an ease in and out (a cosine), so the hand is fastest in the
        # middle (frame 10); a Hit at frame 12 lands 1-2 frames after that peak: in the window
        def arm(i, t):
            k = min(max(i - 5, 0), 10)
            return qx(60 * (1 - math.cos(math.pi * k / 10))) + [0, 0, 0]

        clip = make_clip("Swing", {"RightUpperArm": arm}, 1.0, events=[{"t": 12 / FPS, "name": "Hit"}])
        m = C.metrics(clip, self.rig)
        self.assertEqual(m["problems"], [])
        self.assertEqual(m["fastest"], "RightHand")
        self.assertEqual(m["events"][0]["name"], "Hit")
        self.assertGreaterEqual(m["events"][0]["delta_frames"], 0)
        self.assertLessEqual(m["events"][0]["delta_frames"], 3)
        self.assertIn("phases", m)

    def test_a_hit_far_from_the_peak_fails(self):
        def arm(i, t):
            k = min(max(i - 5, 0), 10)
            return qx(60 * (1 - math.cos(math.pi * k / 10))) + [0, 0, 0]

        clip = make_clip("Early", {"RightUpperArm": arm}, 1.0, events=[{"t": 2 / FPS, "name": "Hit"}])
        m = C.metrics(clip, self.rig)
        self.assertTrue(any(p.startswith("Hit lands") for p in m["problems"]), m["problems"])

    def test_a_locomotion_touchdown_must_not_skid(self):
        """in a locomotion clip the pairs inside a contact span are measured against the ground speed (skate); the
        touchdown and lift-off pairs are not — but they are bounded by foot_slide (skid), so a foot that lands and
        then slides half a stud still fails"""
        rig = C.load_rig("r15", ROOT)
        I = [0, 0, 0, 1, 0, 0, 0]
        body = [I] * 3 + [[0, 0, 0, 1, 0, 0.3, 0]] * 6 + [I] + [[0, 0, 0, 1, 0.5, 0, 0]] * 5
        clip = {"rig": "R15", "fps": 30, "times": [i / 30 for i in range(len(body))], "loop": False, "events": [],
                "joints": {"LowerTorso": {"frames": body}}, "locomotion": {"speed": 0.001, "direction": [0, 0, -1]}}
        m = C.metrics(clip, rig)
        self.assertTrue(any(p.startswith("foot skid") for p in m["problems"]), m["problems"])
        self.assertLess(m["feet"]["skate_max_studs_frame"], 0.01)   # the transition pair is not skate
        self.assertGreater(m["feet"]["skid_max_studs_frame"], 0.4)
        del clip["locomotion"]
        m = C.metrics(clip, rig)
        self.assertTrue(any(p.startswith("foot slide") for p in m["problems"]), m["problems"])

    def test_summary_names_the_fastest_hand(self):
        clip = make_clip("S", {"RightUpperArm": lambda i, t: qx(min(i, 10) * 9) + [0, 0, 0]}, 0.5)
        m = C.metrics(clip, self.rig)
        self.assertIn("RightHand peaks", C.summary(m))


if __name__ == "__main__":
    unittest.main()
