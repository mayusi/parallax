"""kit/anim/rearm.py: a weapon put into a finished R6 clip - both hands reach the hilt, the blade follows the right
arm with momentum, Hits are re-timed to the blade tip, the body is untouched.
Run: python -m pytest -q kit/test/python/test_anim_rearm.py"""
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C       # noqa: E402
import gait_r6 as G    # noqa: E402
import rearm as R      # noqa: E402
import strike as S     # noqa: E402

RIG = C.load_rig("r6", ROOT)


def swing_clip():
    """a synthetic R6 one-shot: the right arm swings from overhead to forward over 0.4 s, the body still"""
    fps, n = 30, 13
    times = [round(i / fps, 6) for i in range(n)]
    joints = {k: {"frames": []} for k in ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")}
    for i in range(n):
        u = i / (n - 1)
        ang = 170.0 - 150.0 * (1 - (1 - u) ** 2)
        joints["Torso"]["frames"].append(S.frame_of(np.eye(3)))
        joints["Head"]["frames"].append(S.frame_of(np.eye(3)))
        joints["Right Arm"]["frames"].append(S.frame_of(S.euler((ang, 0.0, 0.0))))
        joints["Left Arm"]["frames"].append(S.frame_of(np.eye(3)))
        joints["Right Leg"]["frames"].append(S.frame_of(np.eye(3)))
        joints["Left Leg"]["frames"].append(S.frame_of(np.eye(3)))
    return {"schema": 1, "name": "Swing", "rig": "R6", "fps": fps, "duration": times[-1], "loop": False, "priority": "Action",
            "joints": joints, "times": times, "events": [], "source": {"kind": "import"}}


def test_both_hands_reach_the_hilt_and_the_body_is_kept():
    src = swing_clip()
    out, info = R.rearm(src, {"name": "GS", "from": "Swing", "sword": {"length": 4.8, "grip": 0.75}, "hands": 2, "lag": 0.03})
    assert out["joints"]["Torso"]["frames"] == src["joints"]["Torso"]["frames"]
    assert out["joints"]["Right Leg"]["frames"] == src["joints"]["Right Leg"]["frames"]
    frames = C.world_frames(out, RIG)
    grips, tips = out["sword"]["grip_path"], out["sword"]["tip"]
    for i, w in enumerate(frames):
        G_ = np.array(grips[i]); d = np.array(tips[i]) - G_
        d = d / np.linalg.norm(d)
        for arm, off in (("Right Arm", 0.375), ("Left Arm", -0.375)):
            hand = (w[arm] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
            assert np.linalg.norm(hand - (G_ + off * d)) < 0.12, (arm, i, hand, G_ + off * d)
    assert info["tip_peak"] > 20.0
    assert len(info["hits"]) == 1 and 0.05 < info["hits"][0] < 0.45


def test_momentum_smooths_a_whip():
    src = swing_clip()
    sharp, _ = R.rearm(src, {"name": "A", "from": "Swing", "sword": {"length": 4.8}, "lag": 0.0, "inertia": 0.0})
    heavy, _ = R.rearm(src, {"name": "B", "from": "Swing", "sword": {"length": 4.8}, "lag": 0.0, "inertia": 0.08})
    def peak(c):
        t = np.array(c["sword"]["tip"])
        return float(np.linalg.norm(np.diff(t, axis=0), axis=1).max())
    assert peak(heavy) < peak(sharp)


def test_one_hand_keeps_the_left_arm():
    src = swing_clip()
    out, _ = R.rearm(src, {"name": "C", "from": "Swing", "sword": {"length": 3.0}, "hands": 1})
    assert out["joints"]["Left Arm"]["frames"] == src["joints"]["Left Arm"]["frames"]


def test_a_gait_can_carry_a_sword():
    walk = G.generate({"name": "W", "kind": "walk", "fps": 30})
    out, info = R.rearm(walk, {"name": "WS", "from": "W", "sword": {"length": 4.0}, "hands": 1})
    assert out["loop"] is True and out["events"] == []
    m = C.metrics(out, RIG, None)
    assert not [p for p in m["problems"] if "Hit" in p]
    json.dumps(out)
