"""strike.py arm_clearance: a two-hand grip close to the body pushes the reaching arm into the chest; the option pushes
the grip forward until the arms pass in front (owner 2026-10-18: the arms 'very kindish noticable')"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C      # noqa: E402
import strike as S    # noqa: E402

# the hilt held tight by the right hip: the left arm reaches across the belly
MOVE = {"name": "ArmClearProbe", "kind": "strike", "fps": 30, "rig": "R6", "arm_slide": 2.4,     # as the katana moves
        "sword": {"length": 4.6, "grip": 0.75, "grip_pitch": 0},
        "events": [{"name": "Hit", "t": 0.3}],
        "keys": [{"t": 0.0, "pitch": 0, "yaw": 0, "grip": [0.6, 0.2, -0.9], "dir": [0.3, 0.9, -0.3], "ease": "InOut"},
                 {"t": 0.2, "pitch": 0, "yaw": 0, "grip": [0.7, -0.6, -0.55], "dir": [0.6, 0.5, -0.6], "ease": "InOut"},
                 {"t": 0.3, "pitch": 5, "yaw": -30, "grip": [0.2, 0.1, -1.8], "dir": [-0.4, -0.3, -0.85], "ease": "InOut"},
                 {"t": 0.6, "pitch": 0, "yaw": 0, "grip": [0.5, 0.4, -1.3], "dir": [0.0, 1.0, -0.2], "ease": "InOut"}]}


def _sink(clip):
    """the worst share of either arm box inside the torso or the head, over the clip"""
    rig = C.load_rig("r6")
    sz = rig["sizes"]
    g = np.linspace(-0.45, 0.45, 5)
    pts = np.array([[x * sz["Left Arm"][0], y * sz["Left Arm"][1], z * sz["Left Arm"][2], 1.0]
                    for x in g for y in np.linspace(-0.48, 0.48, 9) for z in g])
    worst = 0.0
    for f in C.world_frames(clip, rig):
        for arm in ("Right Arm", "Left Arm"):
            p = (f[arm] @ pts.T).T
            inside = np.zeros(len(p), dtype=bool)
            for part, size in (("Torso", sz["Torso"]), ("Head", [1.25, 1.2, 1.25])):
                loc = (np.linalg.inv(f[part]) @ p.T).T[:, :3]
                inside |= np.all(np.abs(loc) < np.array(size) / 2 - 0.05, axis=1)
            worst = max(worst, float(inside.mean()))
    return worst


def _gen(**extra):
    m = json.loads(json.dumps(MOVE))
    m.update(extra)
    return S.generate(m)[0]


def test_arm_clearance_pulls_the_arms_out_of_the_body():
    before, after = _sink(_gen()), _sink(_gen(arm_clearance=0.15))
    assert before > 0.3                                     # the probe really sinks an arm
    assert after < before / 2 and after <= 0.3              # measured 0.57 -> 0.25 (the push is smoothed, finer grid)


def test_arm_clearance_off_is_unchanged_and_on_is_smooth():
    a, b = _gen(), _gen()
    assert a["joints"] == b["joints"]                       # deterministic without the option
    on = _gen(arm_clearance=0.15)
    grips = np.asarray(on["sword"]["grip_path"], dtype=float)
    steps = np.linalg.norm(np.diff(grips, axis=0), axis=1)
    assert steps.max() < 6 * np.median(steps) + 0.05        # the smoothed push never jumps the hands
