"""2026-10-24: derive.op_trim cuts a clip's sword / root tracks and moves its events with the joints; cutscene.py carries
a sword clip's blade in the right arm's frame and composes it back exactly (the KatanaDuel render)"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import cutscene as CS  # noqa: E402
import derive as D  # noqa: E402

JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]


def sword_clip(n=30, fps=60):
    def arm(i):
        a = math.radians(3 * i)                         # the right arm swings about X
        return [math.sin(a / 2), 0.0, 0.0, math.cos(a / 2), 0.0, 0.0, 0.0]
    joints = {j: {"frames": [arm(i) if j == "Right Arm" else [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for i in range(n)]}
              for j in JOINTS}
    tips = [[1.5, -1.0 + 0.05 * i, -2.0] for i in range(n)]
    grips = [[1.4, -1.0 + 0.02 * i, -1.0] for i in range(n)]
    edges = [[0.0, -1.0, 0.0] for _ in range(n)]
    return {"name": "Probe", "rig": "R6", "fps": fps, "times": [i / fps for i in range(n)], "joints": joints,
            "sword": {"tip": tips, "grip_path": grips, "edge": edges, "kind": "katana", "length": 3.6, "grip": 0.5},
            "root": [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, -0.01 * i] for i in range(n)],
            "events": [{"name": "Parry", "t": 0.1}, {"name": "Hit", "t": 0.3}]}


def test_trim_cuts_the_sword_root_and_events_with_the_joints():
    c = sword_clip()
    tip10 = list(c["sword"]["tip"][10])
    D.op_trim(c, start=10 / 60, end=25 / 60)
    assert len(c["times"]) == 16 and len(c["sword"]["tip"]) == 16 and len(c["sword"]["grip_path"]) == 16
    assert len(c["sword"]["edge"]) == 16 and len(c["root"]) == 16
    assert c["sword"]["tip"][0] == tip10
    ev = {e["name"]: e["t"] for e in c["events"]}
    assert "Parry" not in ev and abs(ev["Hit"] - (0.3 - 10 / 60)) < 1e-6   # (0.1 s fell before the cut)


def test_the_cutscene_sword_round_trips_through_the_arm():
    c = sword_clip()
    frames = CS.frames_of(c)
    assert all("_sword" in p for p in frames)
    for i in (0, 12, 29):
        M = CS.arm_mat(frames[i])
        t = (M @ np.r_[frames[i]["_sword"]["t"], 1.0])[:3]
        g = (M @ np.r_[frames[i]["_sword"]["g"], 1.0])[:3]
        assert np.allclose(t, c["sword"]["tip"][i], atol=1e-6) and np.allclose(g, c["sword"]["grip_path"][i], atol=1e-6)


def test_blend_keeps_the_sword_through_a_crossfade():
    frames = CS.frames_of(sword_clip())
    plain = {j: [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for j in JOINTS}            # an idle frame: no sword
    assert "_sword" in CS.blend(plain, frames[0], 0.3)                         # the sword clip's blade comes along
    assert "_sword" in CS.blend(frames[0], plain, 0.8)                         # and stays while fading out of it


def test_a_blade_held_rigidly_by_the_arm_has_one_place_in_the_arm():
    """a blade fixed in the right arm (moved by FK every frame) must come out at ONE arm-local place on every frame -
    a wrong part or an identity arm_mat gives a drifting one (the round trip above cannot tell)"""
    c = sword_clip()
    local_g, local_t = np.array([0.0, -1.0, -0.4]), np.array([0.0, -1.0, -3.9])
    frames = CS.frames_of({**c, "sword": {}})
    c["sword"]["grip_path"] = [list((CS.arm_mat(p) @ np.r_[local_g, 1.0])[:3]) for p in frames]
    c["sword"]["tip"] = [list((CS.arm_mat(p) @ np.r_[local_t, 1.0])[:3]) for p in frames]
    c["sword"].pop("edge")
    out = CS.frames_of(c)
    assert np.allclose(out[0]["_sword"]["t"], out[-1]["_sword"]["t"], atol=1e-6)
    assert not np.allclose(c["sword"]["tip"][0], c["sword"]["tip"][-1], atol=1e-3)   # the world blade did move
