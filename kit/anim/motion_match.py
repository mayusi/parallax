"""motion_match.py — NEW moves built from short HUMAN MOTION WINDOWS (owner-approved plan v3, idea 3, 2026-10-12).

Measured first (kit/anim/pose_space.py): single frames of my rejected moves sit as close to the loved pose space as
loved attacks do - the failure is the MOTION between poses, not the poses. So a move is assembled from windows of real
loved motion (each ~0.17 s, poses AND their velocities), chosen so the sequence follows an intent and each window
continues the last one smoothly; consecutive windows are blended over their overlap.

    db = build_db(kinds=("attack", "m1/combo", "dash"))          # windows of every loved clip of those kinds (+ mirrored)
    clip = synthesize(db, intent, rng)                            # intent: a list of target keys (time, pose features)

The database row = [pose (54) | velocity (54)] at the window's first frame, plus the window's frames. The search is a
greedy beam over windows: cost = distance to the intent's pose at that time + the transition cost (pose + velocity
mismatch with where the previous window ended). Randomness (rng) picks among the near-best, so one intent gives MANY
different candidates (idea 5: generate many, filter, show the best; idea 1: the owner picks)."""
import copy
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import derive as D  # noqa: E402
import pose_space as PS  # noqa: E402

LIB = os.path.join("_artifacts", "r6lib")
WIN = 10          # frames per window at 60 fps (~0.17 s)
HOP = 5           # windows start every 5 frames; consecutive windows overlap by WIN - HOP when stitched


def resample60(c):
    if int(round(float(c.get("fps") or 30))) != 60:
        c = copy.deepcopy(c)
        D.op_retime(c, duration=float(c["times"][-1]), fps=60)
    return c


def build_db(kinds=("attack", "m1/combo", "dash", "ability", "other"), mirror=True):
    picks = json.load(open(os.path.join("assets", "animations", "library", "owner_picks.json"), encoding="utf-8"))["picks"]
    rows, wins, src = [], [], []
    for r in picks:
        if r["verdict"] != "love" or r["laggy"] or r["kind"] not in kinds:
            continue
        p = os.path.join(LIB, "clips", f"{r['id']}.clip.json")
        if not os.path.isfile(p):
            continue
        c = resample60(json.load(open(p, encoding="utf-8")))
        if not all(j in c["joints"] for j in PS.JOINTS):
            continue
        for tag, cc in (("", c), ("m", D.op_mirror(copy.deepcopy(c)) if mirror else None)):
            if cc is None:
                continue
            V = PS.clip_vectors(cc)
            for s in range(0, len(V) - WIN, HOP):
                vel = (V[s + 1] - V[s]) * 60
                rows.append(np.concatenate([V[s], vel * 0.05]))
                wins.append(V[s:s + WIN])
                src.append(f"{r['id']}{tag}@{s}")
    return {"rows": np.array(rows), "wins": np.array(wins), "src": src}


def synthesize(db, intent, rng, beam_pick=6, w_intent=1.0, w_trans=3.0, total=None):
    """intent: [(frame, pose_vec or None)] sorted - where the move should be at those frames (None = free); the
    result: a clip of stitched windows (60 fps), starting from the first intent pose"""
    rows, wins = db["rows"], db["wins"]
    total = total or intent[-1][0] + WIN
    cur = intent[0][1]
    out = [cur]
    t = 0
    used = []
    prev_end, prev_vel = cur, np.zeros_like(cur)
    while t < total - 1:
        # the intent target nearest after this window
        tgt = None
        for f, pv in intent:
            if f >= t + HOP and pv is not None:
                tgt = (f, pv)
                break
        trans = np.linalg.norm(rows[:, :54] - prev_end, axis=1) + 0.5 * np.linalg.norm(rows[:, 54:] - prev_vel * 0.05, axis=1)
        cost = w_trans * trans
        if tgt is not None:
            steps = max(1, (tgt[0] - t) // HOP)
            # the window's END should head toward the target, more strongly as it nears
            # where the window would END once shifted to start at prev_end (the shift is applied below) - comparing the
            # unshifted end aimed with the wrong numbers (2026-10-12: the key-pose error did not move with the weight)
            land = prev_end + (wins[:, HOP] - wins[:, 0])
            cost = cost + w_intent * np.linalg.norm(land - (prev_end + (tgt[1] - prev_end) / steps), axis=1)
        best = np.argsort(cost)[:beam_pick]
        k = int(rng.choice(best))
        used.append(db["src"][k])
        W = wins[k] + (prev_end - wins[k][0])               # shift the window to start where the last one ended
        n_new = min(HOP, total - 1 - t)
        for i in range(1, n_new + 1):
            out.append(W[i])
        prev_vel = (W[n_new] - W[n_new - 1]) * 60
        prev_end = W[n_new]
        t += n_new
    return np.array(out), used


def to_clip(V, name, base=None):
    """pose vectors (60 fps) -> a kit R6 clip (joint frames re-orthonormalised by the pose space's decoder)"""
    frames = [PS.from_vec(v) for v in V]
    c = {"schema": 1, "name": name, "rig": "R6", "fps": 60, "loop": False, "priority": "Action",
         "times": [round(i / 60, 6) for i in range(len(frames))], "events": [],
         "joints": {j: {"frames": [fr[j] for fr in frames]} for j in PS.JOINTS}}
    if base:
        for k in ("gate",):
            if k in base:
                c[k] = base[k]
    return c


def features(V):
    """the few things an intent asks for, from pose vectors (n x 54): the torso's turn (deg) and lean, and each arm's
    direction in the torso's frame (unit 3-vectors) -> n x 8 (turn / 90, lean / 45, right arm xyz, left arm xyz)"""
    V = np.atleast_2d(V)
    def col(j, k):
        return V[:, j * 9 + k * 3: j * 9 + k * 3 + 3]
    tx, ty = col(0, 0), col(0, 1)
    tz = np.cross(tx, ty)
    fwd = -tz
    turn = np.degrees(np.arctan2(-fwd[:, 0], -fwd[:, 2])) * -1
    lean = np.degrees(np.arcsin(np.clip(-fwd[:, 1], -1, 1)))
    ra = -col(2, 1)
    la = -col(3, 1)
    norm = lambda a: a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)
    return np.hstack([turn[:, None] / 90.0, lean[:, None] / 45.0, norm(ra), norm(la)])


def synthesize_features(db, intent, rng, beam_pick=6, w_intent=4.0, w_trans=1.0, total=None):
    """like synthesize(), but the intent is FEATURE targets [(frame, 8-vector or None)] (see features()) - what the move
    should DO (turn, lean, where the arms point), not exact poses the library may never contain"""
    rows, wins = db["rows"], db["wins"]
    total = total or intent[-1][0] + WIN
    start = intent[0][1]
    cur = start if start is not None and np.size(start) == 54 else wins[int(rng.integers(len(wins)))][0]
    out, used, t = [cur], [], 0
    prev_end, prev_vel = cur, np.zeros_like(cur)
    targets = [(f, v) for f, v in intent[1:] if v is not None]
    while t < total - 1:
        tgt = next(((f, v) for f, v in targets if f >= t + HOP), None)
        trans = 0.5 * np.linalg.norm(rows[:, 54:] - prev_vel * 0.05, axis=1)
        cost = w_trans * trans
        if tgt is not None:
            steps = max(1, (tgt[0] - t) // HOP)
            land = prev_end + (wins[:, HOP] - wins[:, 0])
            fl, f0 = features(land), features(prev_end)[0]
            want = f0 + (np.asarray(tgt[1]) - f0) / steps
            cost = cost + w_intent * np.linalg.norm(fl - want, axis=1)
        k = int(rng.choice(np.argsort(cost)[:beam_pick]))
        used.append(db["src"][k])
        W = wins[k] + (prev_end - wins[k][0])
        n_new = min(HOP, total - 1 - t)
        for i in range(1, n_new + 1):
            out.append(W[i])
        prev_vel = (W[n_new] - W[n_new - 1]) * 60
        prev_end = W[n_new]
        t += n_new
    return np.array(out), used
