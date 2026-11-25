"""kit/anim/anim_profile.py: the craft numbers measure what the research names (amplitude, opposition, twinning, snap, faults)"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import clip as C      # noqa: E402
import anim_profile as PR  # noqa: E402


def q_about_x(deg):
    a = math.radians(deg) / 2
    return [math.sin(a), 0.0, 0.0, math.cos(a)]


def cycle(right_leg, left_leg, right_arm, left_arm, n=40):
    """a loop clip whose limbs swing about x by the given per-frame functions (degrees, + = forward)"""
    times = [i / 60 for i in range(n + 1)]
    def frames(fn):
        return [q_about_x(-fn(i % n)) + [0.0, 0.0, 0.0] for i in range(n + 1)]   # Roblox: -x pitch swings the limb forward
    return {"name": "T", "rig": "R6", "fps": 60, "loop": True, "times": times,
            "joints": {"Right Leg": {"frames": frames(right_leg)}, "Left Leg": {"frames": frames(left_leg)},
                       "Right Arm": {"frames": frames(right_arm)}, "Left Arm": {"frames": frames(left_arm)},
                       "Torso": {"frames": [[0, 0, 0, 1, 0, 0, 0] for _ in times]}}}


def sine(amp, phase=0.0, n=40):
    return lambda i: amp * math.sin(2 * math.pi * (i / n + phase))


def test_amplitude_opposition_and_sine_snap():
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    p = PR.profile(c)
    assert abs(p["Right Leg swing amp"] - 60) < 1.5 and abs(p["Right Arm swing amp"] - 40) < 1.5
    assert abs(p["Left Arm phase"]) < 0.02 or abs(p["Left Arm phase"] - 1) < 0.02     # the left arm WITH the right leg
    assert abs(p["Right Arm phase"] - 0.5) < 0.02                                        # opposite its own leg
    assert 1.4 < p["Right Leg snap"] < 1.8                                               # a sine glides (~1.57)
    assert p["asymmetry deg"] < 0.5                                                      # a perfect mirror


def test_twinning_and_windmill_become_gap_sentences():
    ref = cycle(sine(60), sine(52, 0.5), sine(40, 0.5), sine(36))                    # alive: left and right differ
    twin = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), lambda i: 120 + 100 * math.sin(2 * math.pi * i / 40))
    g = PR.gaps(PR.profile(twin), PR.profile(ref))
    p = PR.profile(twin)
    assert any("OVER THE TOP" in f for f in p.get("faults", []))                        # 20..220: over the head
    assert any("twinned" in s for s in g) or p["asymmetry deg"] > 2                      # mirror flagged unless broken
