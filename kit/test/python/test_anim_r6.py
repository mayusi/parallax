"""kit/anim/gait_r6.py - R6-native locomotion: every kind passes the kit's gates on the R6 rig, a stance sole runs at
the ground speed while it is on the floor, the swing leg clears the floor, the loop closes, the arms swing against
the legs. Run: python -m pytest -q kit/test/python/test_anim_r6.py"""
import math
import os
import sys

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C          # noqa: E402
import gait_r6 as G       # noqa: E402

R6 = C.load_rig("r6", ROOT)


def make(kind, **params):
    return G.generate({"name": f"T_{kind}", "kind": kind, "fps": 30, **params})


@pytest.mark.parametrize("kind", ["walk", "run", "sprint", "idle"])
def test_every_kind_passes_the_gates(kind):
    clip = make(kind)
    m = C.metrics(clip, R6, None)
    assert m["problems"] == [], m["problems"]
    assert clip["rig"] == "R6" and clip["loop"] is True
    assert clip["times"][0] == 0.0 and len(clip["times"]) >= 14


@pytest.mark.parametrize("kind", ["walk", "run", "sprint"])
def test_stance_sole_runs_at_the_ground_speed(kind):
    """while a sole is within the contact band of the floor, its horizontal step per frame is v * dt (sampled at
    120 fps: at 30 fps a run's sole crosses the 0.04 band in one or two frames)"""
    clip = make(kind, fps=120)
    v = clip["locomotion"]["speed"]
    frames = C.world_frames(clip, R6)
    ground = C.rest_ground(R6, C.feet_of(R6))
    dt = clip["times"][1] - clip["times"][0]
    checked = 0
    for leg in ("Right Leg", "Left Leg"):
        soles = [w[leg] @ np.array([0.0, -1.0, 0.0, 1.0]) for w in frames]
        for i in range(len(soles) - 1):
            if soles[i][1] - ground < 0.04 and soles[i + 1][1] - ground < 0.04:
                step = float(soles[i + 1][2] - soles[i][2])
                assert abs(step - v * dt) < 0.08, (leg, i, step, v * dt)
                checked += 1
    assert checked >= 2


@pytest.mark.parametrize("kind", ["walk", "run", "sprint"])
def test_no_leg_goes_under_the_floor(kind):
    clip = make(kind)
    frames = C.world_frames(clip, R6)
    ground = C.rest_ground(R6, C.feet_of(R6))
    for leg in ("Right Leg", "Left Leg"):
        low = min(float((w[leg] @ np.array([0.0, -1.0, 0.0, 1.0]))[1]) for w in frames) - ground
        assert low > -0.02, (leg, low)


def test_arms_swing_against_the_legs():
    clip = make("run")
    rl = [G.pitch_of_local(C.quat_mat(f[:4]), "Right Leg") for f in clip["joints"]["Right Leg"]["frames"]]
    ra = [math.degrees(math.atan2(-(C.quat_mat(f[:4]) @ np.array([0.0, -1.0, 0.0]))[2], 1.0)) for f in clip["joints"]["Right Arm"]["frames"]]
    # the leg is ahead at contact (frame 0); the same side's arm is back
    assert rl[0] > 30 and ra[0] < -10, (rl[0], ra[0])
    # and the correlation over the cycle is negative
    rl, ra = np.array(rl[:-1]), np.array(ra[:-1])
    corr = float(np.corrcoef(rl - rl.mean(), ra - ra.mean())[0, 1])
    assert corr < -0.6, corr


def test_amplitude_and_lean_are_parameters():
    a = make("run", amp_fwd=40.0, amp_back=40.0, lean=0.0)
    b = make("run", amp_fwd=65.0, amp_back=80.0, lean=20.0)
    pa = [G.pitch_of_local(C.quat_mat(f[:4]), "Right Leg") for f in a["joints"]["Right Leg"]["frames"]]
    pb = [G.pitch_of_local(C.quat_mat(f[:4]), "Right Leg") for f in b["joints"]["Right Leg"]["frames"]]
    assert max(pb) - min(pb) > max(pa) - min(pa) + 30
    ta = C.quat_mat(a["joints"]["Torso"]["frames"][0][:4]) @ np.array([0.0, 1.0, 0.0])
    tb = C.quat_mat(b["joints"]["Torso"]["frames"][0][:4]) @ np.array([0.0, 1.0, 0.0])
    assert tb[2] < ta[2] - 0.2          # a forward lean tips the torso's up vector forward (-z)


def test_unknown_kind_is_refused():
    with pytest.raises(ValueError):
        make("moonwalk")
