"""strike.py blade_edges: the sword's EDGE per frame (owner 2026-10-18: the sword 'not properly animated in alot of the
poses') - across the blade, leading the cut, never twisting faster than the hands can roll it, carried across seams"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import strike as S    # noqa: E402

MOVE = {"name": "EdgeProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "events": [{"name": "Hit", "t": 0.3}],
        "keys": [{"t": 0.0, "pitch": 0, "yaw": 0, "grip": [0.4, 0.2, -1.4], "dir": [0.2, 0.7, -0.7], "ease": "InOut"},
                 {"t": 0.15, "pitch": 0, "yaw": 30, "grip": [0.9, 1.6, 0.2], "dir": [0.3, 0.6, 0.75], "ease": "In"},
                 {"t": 0.3, "pitch": 10, "yaw": -30, "grip": [-0.3, -0.4, -2.0], "dir": [-0.5, -0.3, -0.8], "ease": "Out"},
                 {"t": 0.6, "pitch": 0, "yaw": 0, "grip": [-0.4, -0.5, -1.6], "dir": [-0.3, -0.4, -0.87], "ease": "InOut"}]}


def _clip(**extra):
    m = json.loads(json.dumps(MOVE))
    m.update(extra)
    return S.generate(m)


def _parts(c):
    sw = c["sword"]
    E, T, G = (np.asarray(sw[k], dtype=float) for k in ("edge", "tip", "grip_path"))
    D = (T - G) / np.linalg.norm(T - G, axis=1)[:, None]
    return E, T, D


def test_edge_is_across_the_blade_and_leads_the_cut():
    c, _ = _clip()
    assert c["sword"]["kind"] == "katana"                                   # renders as a katana
    E, T, D = _parts(c)
    assert np.abs((E * D).sum(1)).max() < 1e-3
    assert np.allclose(np.linalg.norm(E, axis=1), 1.0, atol=1e-3)
    sp = np.linalg.norm(T[2:] - T[:-2], axis=1)
    k = int(np.argmax(sp)) + 1                                              # the fastest frame: the cut
    v = (T[k + 1] - T[k - 1]) / np.linalg.norm(T[k + 1] - T[k - 1])
    assert E[k] @ v > 0.9


def test_edge_twists_no_faster_than_the_hands_and_carries_a_seam():
    start = [0.0, 0.0, 1.0]
    for c, _ in (_clip(), _clip(edge_start=start)):
        E, _, D = _parts(c)
        cap = math.radians(S.TWIST_MAX) / 60 + 1e-3
        for i in range(len(E) - 1):
            a = E[i] - (E[i] @ D[i + 1]) * D[i + 1]
            a /= np.linalg.norm(a)
            assert math.acos(min(1.0, float(a @ E[i + 1]))) <= cap * 1.05
    c, info = _clip(edge_start=start)
    E, _, D = _parts(c)
    s = np.asarray(start) - (np.asarray(start) @ D[0]) * D[0]
    assert E[0] @ (s / np.linalg.norm(s)) > 0.999                          # the seam frame is the last clip's edge
    assert info["edge_end"] == c["sword"]["edge"][-1]


def test_dossier_measures_the_hands_and_the_edge():
    """proc_dossier sword measures (the katana underhip dossier, 2026-10-18): the hands' side, the bottom pause, the
    finish height over the shoulders, the edge at the start and at the Hit"""
    import proc_dossier as PD
    c, _ = _clip()
    fns, _ = PD.sword_measures(c, {})
    for k in ("hands_side_max_studs", "bottom_pause_s", "finish_hands_over_shoulders_studs", "edge_up_at_start",
              "edge_up_at_hit"):
        assert k in fns and np.isfinite(fns[k]({})), k
    assert fns["bottom_pause_s"]({}) > 0
    assert -1.0 <= fns["edge_up_at_hit"]({}) <= 1.0
