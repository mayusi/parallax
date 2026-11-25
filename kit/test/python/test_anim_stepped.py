"""strike.py `step` - LIMITED ANIMATION (Arc System Works, GDC 2015: interpolation off, every frame a key, imperfection
per key): held poses that snap on the declared beats; the gates skip the intended steps; the dossier measures the
smooth motion underneath"""
import copy
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C      # noqa: E402
import snaps as SN    # noqa: E402
import strike as S    # noqa: E402

MOVE = {"name": "StepProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "beats": {"anticipation": [0.0, 0.2], "strike": [0.2, 0.4], "hold": [0.4, 0.7]},
        "keys": [{"t": 0.0, "grip": [0.4, 0.2, -1.4], "dir": [0.2, 0.7, -0.7], "ease": "InOut"},
                 {"t": 0.2, "yaw": 30, "grip": [0.9, 1.6, 0.2], "dir": [0.3, 0.6, 0.75], "ease": "In"},
                 {"t": 0.35, "yaw": -30, "grip": [-0.3, -0.4, -2.0], "dir": [-0.5, -0.3, -0.8], "ease": "Out"},
                 {"t": 0.7, "grip": [-0.4, -0.5, -1.6], "dir": [-0.3, -0.4, -0.87], "ease": "InOut"}]}


def _gen(step=None):
    m = json.loads(json.dumps(MOVE))
    if step:
        m["step"] = step
    return S.generate(m)[0]


def test_off_is_unchanged_and_on_holds_poses():
    a, b = _gen(), _gen()
    assert a == b and "stepped" not in a
    c = _gen({"on": 3, "beats": ["strike"]})
    assert c["stepped"] == [[0.2, 0.4, 3]]
    F = c["joints"]["Right Arm"]["frames"]
    i0 = 12
    assert F[i0] == F[i0 + 1] == F[i0 + 2] and F[i0 + 3] != F[i0 + 2]     # held 3 frames, then the snap
    assert c["joints"]["Right Arm"]["frames"][:i0] == a["joints"]["Right Arm"]["frames"][:i0]   # outside: smooth


def test_gates_skip_the_intended_steps_and_destep_restores_the_motion():
    c = _gen({"on": 2, "beats": "all", "imperfection": 1.5})
    assert SN.find(c) == {}
    assert not any("pops" in p for p in C.metrics(c, C.load_rig("r6"))["problems"])
    smooth = _gen()
    d = C.destep(_gen({"on": 2, "beats": "all"}))
    e = np.linalg.norm(np.array(d["sword"]["tip"]) - np.array(smooth["sword"]["tip"]), axis=1)
    # the smooth path back - exact on the samples, close between (an abrupt stop inside a step is lost: the build
    # gate therefore checks the move generated WITHOUT its steps)
    assert np.median(e) < 0.05 and np.percentile(e, 90) < 0.25


def test_imperfection_is_small_and_deterministic():
    a, b = _gen({"on": 2, "beats": "all", "imperfection": 1.5}), _gen({"on": 2, "beats": "all", "imperfection": 1.5})
    assert a == b
    plain = _gen({"on": 2, "beats": "all"})
    qa = np.array(a["joints"]["Head"]["frames"])[:, :4]
    qp = np.array(plain["joints"]["Head"]["frames"])[:, :4]
    ang = np.degrees(2 * np.arccos(np.clip(np.abs((qa * qp).sum(1)), -1, 1)))
    assert 0.1 < ang.max() <= 1.6


def test_review_fixes_hit_on_a_new_pose_caller_untouched_one_run_hands_on_hilt():
    """review 2026-10-18: the Hit landed mid-hold and rewrote the caller's move; touching beats held 7 frames for 5;
    imperfection pulled the hands off the hilt"""
    m = json.loads(json.dumps(MOVE))
    m["events"] = [{"name": "Hit", "t": 0.39}]
    m["step"] = {"on": 5, "windows": [[0.2, 0.4]]}
    c = S.generate(m)[0]
    assert m["events"][0]["t"] == 0.39                                   # the caller's move untouched
    hit = [e["t"] for e in c["events"] if e["name"] == "Hit"][0]
    f = int(round(hit * 60))
    G = c["sword"]["grip_path"]
    assert G[f] != G[f - 1]                                              # a NEW pose on the Hit frame (the blade)
    c2 = _gen({"on": 5, "beats": ["anticipation", "strike"]})
    F2 = c2["sword"]["grip_path"][:25]                                  # the windows: 0 .. 0.4 s (the blade moves)
    runs, r = [], 1
    for i in range(1, len(F2)):
        if F2[i] == F2[i - 1]:
            r += 1
        else:
            runs.append(r)
            r = 1
    assert max(runs[:-1]) <= 5                                           # no hold longer than `on`
    c3 = _gen({"on": 2, "beats": "all", "imperfection": 2.0})
    rig = C.load_rig("r6")
    sp = c3["sword"]["grip"]
    for i, fr in enumerate(C.world_frames(c3, rig)):
        g = np.array(c3["sword"]["grip_path"][i])
        d = np.array(c3["sword"]["tip"][i]) - g
        d /= np.linalg.norm(d)
        assert np.linalg.norm((fr["Right Arm"] @ np.array([0, -1, 0, 1.0]))[:3] - (g + d * sp / 2)) < 0.02
