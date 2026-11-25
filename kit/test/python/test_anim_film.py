"""kit/anim/film_keys.py (AAA gaps v2 A2): an R6 pose seen from the front, turned into MediaPipe-style world landmarks,
is fitted back near-exactly with MediaPipe's depth choosing each limb's side; key frames pick the pauses + the strike"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import film_keys as F  # noqa: E402
import roto as R       # noqa: E402

IDX = {"head": 0, "l_shoulder": 11, "r_shoulder": 12, "l_hand": 15, "r_hand": 16, "l_hip": 23, "r_hip": 24,
       "l_foot": 27, "r_foot": 28}


def landmarks_of(p):
    pts, _ = R.world_points(p)
    out = [[0.0, 0.0, 0.0] for _ in range(33)]
    Rc = R.rotvec(p[0:3])
    for k, i in IDX.items():
        c = Rc @ pts[k]
        out[i] = [float(c[0]), float(c[1]), float(-c[2])]   # MediaPipe: z smaller = nearer the camera
    return out


def pose(arm):
    p = np.zeros(R.N)
    p[0:3] = [0.0, math.radians(180), 0.0]
    p[3] = 0.0
    p[10:13] = [arm, 0.1, 0.2]
    p[13:16] = [-0.5, 0.0, -0.2]
    return p


def test_a_front_pose_fits_back():
    """(MediaPipe's neck / pelvis are the shoulder / hip midpoints, ~0.2-0.3 studs off R6's torso ends - real footage
    has that gap too: the fit is judged on the limbs' directions)"""
    truth = pose(-1.4)
    lm = landmarks_of(truth)
    best, _ = R.fit(F.clicks_of(lm), F.flips_of(lm))
    assert best["error"] < 0.1
    got, want = R.world_points(best["params"])[0], R.world_points(truth)[0]
    for a, b in (("r_shoulder", "r_hand"), ("l_shoulder", "l_hand")):
        dg = R.rotvec(best["params"][0:3]) @ (got[b] - got[a])
        dw = R.rotvec(truth[0:3]) @ (want[b] - want[a])
        assert float(dg @ dw) / (np.linalg.norm(dg) * np.linalg.norm(dw)) > 0.9, a


def test_key_frames_find_the_pauses_and_the_strike():
    frames = []
    for i in range(60):                                         # hold, swing fast, hold
        a = -0.2 if i < 20 else (-0.2 - 1.6 * (i - 20) / 10 if i < 30 else -1.8)
        frames.append(landmarks_of(pose(a)))
    keys = F.key_frames(frames, 30, 4)
    assert keys[0] == 0 and keys[-1] == 59 and any(20 <= k <= 30 for k in keys)
