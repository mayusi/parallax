"""strike.py `overlap` - SUCCESSIVE BREAKING (AAA plan #4): the arms and the head drag behind the torso; the arms and the
sword drag together, so the hands never leave the hilt; off = unchanged"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C      # noqa: E402
import strike as S    # noqa: E402

MOVE = {"name": "OverlapProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4,
        "sword": {"length": 3.6, "grip": 0.5},
        "keys": [{"t": 0.0, "yaw": 30, "grip": [0.9, 1.2, 0.2], "dir": [0.3, 0.8, 0.5], "ease": "InOut"},
                 {"t": 0.25, "yaw": -40, "grip": [-0.3, -0.4, -2.0], "dir": [-0.5, -0.3, -0.8], "ease": "InOut"},
                 {"t": 0.6, "yaw": -30, "grip": [-0.4, -0.5, -1.6], "dir": [-0.3, -0.4, -0.87], "ease": "InOut"}]}


def _gen(ov=None):
    m = json.loads(json.dumps(MOVE))
    if ov:
        m["overlap"] = ov
    return S.generate(m)[0]


def test_off_is_unchanged():
    assert _gen() == _gen(None)


def test_arms_drag_with_the_sword_and_hands_stay_on_the_hilt():
    rig = C.load_rig("r6")
    base, c = _gen(), _gen({"arms": 3, "head": 2})
    sp = c["sword"]["grip"]
    for i, f in enumerate(C.world_frames(c, rig)):
        g = np.array(c["sword"]["grip_path"][i])
        d = np.array(c["sword"]["tip"][i]) - g
        d /= np.linalg.norm(d)
        hand = (f["Right Arm"] @ np.array([0, -1, 0, 1.0]))[:3]
        assert np.linalg.norm(hand - (g + d * sp / 2)) < 0.02
    # the arm (torso-relative) is the base's arm 3 frames earlier
    a, b = base["joints"]["Right Arm"]["frames"], c["joints"]["Right Arm"]["frames"]
    assert np.allclose(np.array(b[10][:4]), np.array(a[7][:4]), atol=1e-5)
    assert c["joints"]["Torso"]["frames"] == base["joints"]["Torso"]["frames"]
    assert c["joints"]["Right Leg"]["frames"] == base["joints"]["Right Leg"]["frames"]
