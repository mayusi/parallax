"""strike.py hip_offset: the owner's leg tops (2026-10-18, placed on his rig) - each leg aims from a moved hip socket;
the feet and the body stay where they were"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C      # noqa: E402
import strike as S    # noqa: E402

MOVE = {"name": "HipProbe", "kind": "strike", "fps": 30, "rig": "R6", "leg_slide": 1.3, "pelvis_drop_max": 0.3,
        "sword": {"length": 3.6, "grip": 0.5},
        "events": [{"name": "Hit", "t": 0.3}],
        "keys": [{"t": 0.0, "yaw": 0, "grip": [0.4, 0.2, -1.4], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0],
                  "right": [0.55, 0, 1.0], "left": [-0.57, 0, -0.7], "ease": "InOut"},
                 {"t": 0.3, "yaw": -30, "grip": [-0.3, -0.4, -2.2], "dir": [-0.2, -0.3, -0.93], "pos": [0, -0.6, 0],
                  "right": [0.6, 0, 1.0], "left": [-0.6, 0, -0.7], "ease": "InOut"},
                 {"t": 0.6, "yaw": 0, "grip": [0.4, 0.2, -1.4], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0],
                  "right": [0.55, 0, 1.0], "left": [-0.57, 0, -0.7], "ease": "InOut"}]}
HO = {"right": [-0.042, 0.246, -0.228], "left": [-0.083, 0.613, -0.495]}


def _parts(**extra):
    m = json.loads(json.dumps(MOVE))
    m.update(extra)
    clip = S.generate(m)[0]
    rig = C.load_rig("r6")
    out = []
    for f in C.world_frames(clip, rig):
        inv = np.linalg.inv(f["Torso"])
        out.append({lg: ((inv @ f[lg] @ [0, 1, 0, 1])[:3], (f[lg] @ [0, -1, 0, 1])[:3]) for lg in ("Right Leg", "Left Leg")}
                   | {"Torso": f["Torso"][:3, 3].copy()})
    return clip, out


def test_hip_offset_moves_the_leg_tops_not_the_feet_or_body():
    a_clip, a = _parts()
    b_clip, b = _parts(hip_offset=HO)
    for fa, fb in zip(a, b):
        assert np.allclose(fa["Torso"], fb["Torso"], atol=1e-4)                     # the body did not move
        for lg in ("Right Leg", "Left Leg"):
            assert np.linalg.norm(fa[lg][1] - fb[lg][1]) < 0.02                     # the sole stays on its spot
        assert fb["Left Leg"][0][2] < fa["Left Leg"][0][2] - 0.3                    # the front leg's top went forward
    assert a_clip["joints"]["Right Arm"] == b_clip["joints"]["Right Arm"]          # arms untouched


def test_no_hip_offset_is_unchanged():
    assert _parts()[0]["joints"] == _parts(hip_offset=None)[0]["joints"]
