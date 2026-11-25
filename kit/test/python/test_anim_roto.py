"""kit/anim/roto.py - pose by pointing (AAA gaps v2 A3): a known R6 pose seen by a known camera, its joints 'clicked'
(projected), is fitted back - the picture matches and, with the depth signs given, the limbs point the same way"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import roto as R  # noqa: E402


def truth():
    p = np.zeros(R.N)
    p[0:3] = [math.radians(-10), math.radians(150), 0.0]      # a three-quarter view from the front, a little above
    p[3] = math.log(0.09)
    p[4:6] = [0.02, -0.05]
    p[6:9] = [0.1, 0.5, 0.05]                                  # the torso turned
    p[10:13] = [-1.6, 0.2, 0.3]                                # the right arm raised forward (a strike)
    p[13:16] = [-0.9, -0.2, -0.4]
    p[16:19] = [0.5, 0.0, 0.1]
    p[19:22] = [-0.3, 0.0, -0.1]
    return p


def clicks_of(p):
    pts, _ = R.world_points(p)
    return {k: tuple(R.project(p, pts[k])[0]) for k in R.KP}


def test_fit_matches_the_picture_and_the_limbs():
    p = truth()
    clicks = clicks_of(p)
    best, alts = R.fit(clicks, R.depth_signs(p), starts=(150, 180))
    assert best["error"] < 0.004                                 # under half a percent of the picture height
    got, want = R.world_points(best["params"])[0], R.world_points(p)[0]
    for limb, (a, b) in {"Right Arm": ("r_shoulder", "r_hand"), "Left Arm": ("l_shoulder", "l_hand")}.items():
        dg = (got[b] - got[a]) / np.linalg.norm(got[b] - got[a])
        dw = (want[b] - want[a]) / np.linalg.norm(want[b] - want[a])
        dg_c = R.rotvec(best["params"][0:3]) @ dg                # compared in camera space (the camera is fitted too)
        dw_c = R.rotvec(p[0:3]) @ dw
        assert float(dg_c @ dw_c) > 0.95, limb


def test_too_few_clicks_is_refused():
    try:
        R.fit({"neck": (0, 0.1), "pelvis": (0, -0.1)})
        raise AssertionError("expected a refusal")
    except ValueError as exc:
        assert "at least 6" in str(exc)


def test_record_is_clip_format():
    p = truth()
    rec = R.pose_record(p, clicks_of(p), "x.png", "Probe", 0.001)
    assert set(rec["frames"]) == set(R.PARTS) and len(rec["arms_pose"]["Right Arm"]) == 7
    q = np.array(rec["frames"]["Right Arm"][:4])
    assert abs(np.linalg.norm(q) - 1) < 1e-5
