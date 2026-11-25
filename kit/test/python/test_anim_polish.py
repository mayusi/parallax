"""kit/anim/polish.py (AAA gaps v2 A4): a smooth strike passes every layer; a pop injected into the torso is named as
the layer to polish next, at its frame"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C     # noqa: E402
import polish as P   # noqa: E402
import strike as S   # noqa: E402

KEY = {"grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0], "right": [0.55, 0, 1.0],
       "left": [-0.57, 0, -0.7], "ease": "InOut"}
MOVE = {"name": "PolishProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "keys": [dict(KEY, t=0.0, yaw=0), dict(KEY, t=0.3, yaw=20, grip=[0.9, 0.6, -0.6], dir=[0.3, 0.6, 0.75]),
                 dict(KEY, t=0.6, yaw=-20, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8])]}


def test_smooth_passes_and_a_pop_is_named():
    c = S.generate(json.loads(json.dumps(MOVE)))[0]
    c["events"] = []                                        # no intended snaps to skip
    rows, first = P.report(c)
    assert first is None, rows
    import numpy as np
    f = c["joints"]["Torso"]["frames"]
    i = 15
    R = C.quat_mat(f[i][:4]) @ np.array([[0.0, -1, 0], [1, 0, 0], [0, 0, 1]])   # a 90 deg yaw for ONE frame: a pop
    f[i] = list(C.mat_quat(R)) + f[i][4:7]
    rows, first = P.report(c)
    assert first is not None and first["layer"] == "torso" and any(abs(k - i) <= 2 for k in first["spike_frames"])
