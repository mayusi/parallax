"""Procedural locomotion (kit/anim/gait.py): a walk loops seamlessly, its feet alternate contact, its planted foot
moves back at one ground speed (foot skate under the bar), and it passes every motion gate; a jump is a clean
one-shot; an idle breathes and loops."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C  # noqa: E402
import gait as G  # noqa: E402

LOCOMOTION = ("walk", "jog", "run", "back", "strafe_left", "strafe_right")


def fold_r6(clip):
    """the kit's R6 fold of a clip (kit/lib/anim.luau Anim.foldToR6, through kit/anim/clip_of.luau)"""
    tmp = tempfile.mkdtemp()
    src, out = os.path.join(tmp, "r15.clip.json"), os.path.join(tmp, "r6.clip.json")
    with open(src, "w", encoding="utf-8") as fh:
        json.dump(clip, fh)
    r = subprocess.run(["lune", "run", "kit/anim/clip_of.luau", src, out, "R6"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    with open(out, encoding="utf-8") as fh:
        return json.load(fh)


def sole_heights(clip, rig, foot):
    """the foot's sole centre over the rest floor, per frame"""
    frames = C.world_frames(clip, rig)
    ground = C.rest_ground(rig, C.feet_of(rig))
    sole = np.array([0.0, -rig["sizes"][foot][1] / 2, 0.0, 1.0])
    return [float((w[foot] @ sole)[1] - ground) for w in frames]


def generate(kind, strict=True, **params):
    """(clip, verdict) of kit/anim/gait.py for a kind and parameters; strict: the generator must pass"""
    tmp = tempfile.mkdtemp()
    gait = os.path.join(tmp, f"T_{kind}.gait.json")
    with open(gait, "w", encoding="utf-8") as fh:
        json.dump({"name": f"T_{kind}", "kind": kind, **params}, fh)
    out = os.path.join(tmp, "clip.json")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "gait.py"), gait, "--out", out],
                       capture_output=True, text=True, cwd=ROOT)
    verdict = json.loads(r.stdout.strip().splitlines()[-1])
    if strict:
        assert r.returncode == 0 and verdict["status"] == "pass", r.stdout + r.stderr
    if not os.path.isfile(out):
        return None, verdict
    with open(out, encoding="utf-8") as fh:
        return json.load(fh), verdict


class Gait(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rig = C.load_rig("r15", ROOT)

    def test_walk_passes_the_gates_and_loops(self):
        clip, verdict = generate("walk")
        self.assertTrue(clip["loop"])
        self.assertGreater(clip["locomotion"]["speed"], 3.0)
        m = C.metrics(clip, self.rig)
        self.assertEqual(m["problems"], [], m["problems"])
        self.assertLess(m["loop_seam_deg"], 0.01)
        self.assertLess(m["feet"]["skate_max_studs_frame"], 0.15)
        # both feet touch the ground, and not at the same frames all the time
        cf = m["feet"]["contact_frames"]
        self.assertGreater(cf["RightFoot"], 3)
        self.assertGreater(cf["LeftFoot"], 3)
        self.assertLess(cf["RightFoot"] + cf["LeftFoot"], 2 * clip["duration"] * clip["fps"] + 2)
        self.assertIn("ground speed", C.summary(m))

    def test_run_is_faster_than_walk(self):
        walk, _ = generate("walk")
        run, _ = generate("run")
        self.assertGreater(run["locomotion"]["speed"], walk["locomotion"]["speed"])
        self.assertEqual(C.metrics(run, self.rig)["problems"], [])

    def test_strafe_and_back_pass(self):
        for kind in ("strafe_left", "strafe_right", "back"):
            clip, _ = generate(kind)
            m = C.metrics(clip, self.rig)
            self.assertEqual(m["problems"], [], (kind, m["problems"]))

    def test_idle_breathes_and_loops(self):
        clip, _ = generate("idle")
        self.assertTrue(clip["loop"])
        self.assertNotIn("locomotion", clip)
        m = C.metrics(clip, self.rig)
        self.assertEqual(m["problems"], [], m["problems"])
        self.assertLess(m["loop_seam_deg"], 0.01)

    def test_jump_fall_land_are_clean_one_shots_on_both_rigs(self):
        r6 = C.load_rig("r6", ROOT)
        for kind in ("jump", "fall", "land"):
            clip, _ = generate(kind)
            m = C.metrics(clip, self.rig)
            self.assertEqual(m["problems"], [], (kind, m["problems"]))
            m6 = C.metrics(fold_r6(clip), r6)
            self.assertEqual(m6["problems"], [], (kind, "R6", m6["problems"]))

    def test_other_parameters_still_pass(self):
        """a kind is a starting point: plausible edits of hip, knee, stance, cycle and roll keep every gate green"""
        for kind, params in (("walk", dict(hip=28, knee=70)), ("run", dict(cycle=0.36)), ("jog", dict(stance=16)),
                             ("walk", dict(roll=6)), ("back", dict(hip=20, cycle=0.7)), ("strafe_left", dict(hip=18))):
            clip, _ = generate(kind, **params)
            m = C.metrics(clip, self.rig)
            self.assertEqual(m["problems"], [], (kind, params, m["problems"]))
            self.assertTrue(all(len(v["frames"]) == len(clip["times"]) for v in clip["joints"].values()))
            m6 = C.metrics(fold_r6(clip), C.load_rig("r6", ROOT))
            self.assertEqual(m6["problems"], [], (kind, params, "R6", m6["problems"]))

    def test_impossible_parameters_are_refused_by_name(self):
        """the generator runs the gates itself and names the parameter to change (never a silent bad clip)"""
        clip, verdict = generate("walk", strict=False, hip=60)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertIsNone(clip)                                    # nothing shipped
        self.assertIn("penetration", verdict["summary"])
        self.assertTrue(verdict["next_action"].startswith("lower hip"), verdict["next_action"])
        _, verdict = generate("strafe_right", strict=False, stance=25)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertIn("skid", verdict["summary"])
        self.assertTrue(verdict["next_action"].startswith("lower stance"), verdict["next_action"])
        _, verdict = generate("walk", strict=False, stance=70)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertTrue(verdict["next_action"].startswith(("lower stance", "raise fps")), verdict["next_action"])
        _, verdict = generate("walk", strict=False, knee=5)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertTrue(verdict["next_action"].startswith("raise knee"), verdict["next_action"])

    def test_a_short_cycle_gets_a_finer_time_grid(self):
        """a 0.2 s sprint cannot be sampled at 30 fps (6 frames: the knee would snap) - it is keyed at 60"""
        clip, _ = generate("run", cycle=0.2)
        self.assertEqual(clip["fps"], math.ceil(G.MIN_FRAMES / 0.2))
        self.assertEqual(len(clip["times"]), G.MIN_FRAMES + 1)
        self.assertAlmostEqual(clip["duration"], 0.2, places=3)
        self.assertEqual(clip["locomotion"]["cycle"], 0.2)
        self.assertEqual(C.metrics(clip, self.rig)["problems"], [])
        clip24, _ = generate("run", fps=24)  # 0.4 s at 24 fps would be 10 frames: sampled finer instead
        self.assertEqual(clip24["fps"], math.ceil(G.MIN_FRAMES / 0.4))
        self.assertEqual(C.metrics(clip24, self.rig)["problems"], [])

    def test_every_locomotion_kind_passes_every_gate_on_both_rigs(self):
        r6 = C.load_rig("r6", ROOT)
        for kind in LOCOMOTION:
            clip, _ = generate(kind)
            m = C.metrics(clip, self.rig)
            self.assertEqual(m["problems"], [], (kind, "R15", m["problems"]))
            folded = fold_r6(clip)
            self.assertEqual(folded["rig"], "R6")
            self.assertEqual(folded["locomotion"]["speed"], clip["locomotion"]["speed"])
            m6 = C.metrics(folded, r6)
            self.assertEqual(m6["problems"], [], (kind, "R6", m6["problems"]))
            self.assertLess(m6["feet"]["skate_max_studs_frame"], 0.15, kind)
            # the straight R6 legs stand on the R6 floor and, in the air, skim at least 0.07 over it
            for leg in ("Right Leg", "Left Leg"):
                hs = sole_heights(folded, r6, leg)
                self.assertGreater(min(hs), -0.02, (kind, leg))
                self.assertTrue(all(h < 0.02 or h >= 0.05 for h in hs), (kind, leg, hs))
                self.assertTrue(any(h < 0.02 for h in hs), (kind, leg))

    def test_swing_foot_clears_the_floor_and_lands_once(self):
        """every frame has the foot's lowest edge on the floor (a flat sole, a heel strike or a toe-off) or in the
        air, the air frames form ONE span between the lift-off and the plant, and through the middle of that span
        the foot clears CLEAR: the swing never scuffs"""
        for kind in LOCOMOTION:
            clip, _ = generate(kind)
            frames = C.world_frames(clip, self.rig)
            ground = C.rest_ground(self.rig, C.feet_of(self.rig))
            for foot in ("RightFoot", "LeftFoot"):
                lows = [C.lowest(self.rig, foot, w[foot]) - ground for w in frames]
                for h in lows:
                    self.assertGreater(h, -0.04, (kind, foot, h))        # never through the floor
                air = [h >= 0.02 for h in lows]
                starts = [i for i in range(1, len(air)) if air[i] and not air[i - 1]]
                self.assertEqual(len(starts), 1, (kind, foot, lows))
                i0 = starts[0]
                i1 = next(i for i in range(i0, len(air) + i0) if not air[i % (len(air) - 1)])   # the plant (wraps)
                span = i1 - i0
                mid = [lows[i % (len(air) - 1)] for i in range(i0, i1) if 0.3 <= (i - i0) / span <= 0.65]
                self.assertTrue(all(h >= G.CLEAR - 1e-3 for h in mid), (kind, foot, mid))

    def test_the_r6_fold_keeps_the_strafes_up(self):
        """an R6 hip pivot sits half a stud off the leg's axis: a sideways lean must not sink the sole"""
        r6 = C.load_rig("r6", ROOT)
        clip, _ = generate("strafe_left")
        folded = fold_r6(clip)
        for leg in ("Right Leg", "Left Leg"):
            hs = sole_heights(folded, r6, leg)
            self.assertGreater(min(hs), -0.02, (leg, hs))
            self.assertLess(min(abs(h) for h in hs), 0.01, (leg, hs))  # it does stand

    def test_the_source_records_the_generator_and_the_rig(self):
        clip, _ = generate("walk")
        src = clip["source"]
        self.assertEqual(src["tool_sha256"], G.sha256_of_many([os.path.join(ROOT, "kit", "anim", "gait.py"),
                                                                os.path.join(ROOT, "kit", "anim", "clip.py")]))
        self.assertEqual(src["rig_sha256"], G.sha256_of(C.rig_path("r15", ROOT)))

    def test_parameters_override_defaults(self):
        clip, _ = generate("walk", hip=20)
        self.assertEqual(clip["source"]["params"]["hip"], 20)


if __name__ == "__main__":
    unittest.main()
