"""motion_fill.py — the HYBRID FILL (owner brief 2026-10-12): the frames at `keys` are kept, every gap between two keys
is filled by length - plain slerp when it is shorter than `short` frames (close keys: human motion is near a straight
interpolation, kit/anim/motion_model_gaps.py), the motion model when it is longer than `long`, a crossfade of the two
in between. k model fills are sampled (seeds) and the best one kept by:
    pops    one-frame joint snaps (a step > 15 deg and 3x its neighbours)                       x 5
    jitter  planted-foot jitter: where a foot sits on the clip's own floor, how much its velocity changes frame to frame
    dtw     DTW (mean over joints, deg) to the nearest LOVED clip of the same group (the held-out combat test clips are
            never used)                                                                          / 10
    from warp.py: {"op": "fill", "keys": [frame, ...] | "keys_s": [s, ...], "model": "medium_v3", "k": 4,
                   "short": 30, "long": 45, "group": "locomotion", "tags": [...]}
SHIPPED FOR LOCOMOTION (owner 2026-10-12): on held-out locomotion the residual model (medium_v3) matches slerp at 20-frame
gaps and beats it at 30+ (MOTION_MODEL_PLAN.md round 3). For COMBAT, plain slerp beat the model on five held-out loved
attacks - a combat fill logs a warning. No model file (it lives in the git-ignored _artifacts/r6model) -> slerp only, said
in the log, never a crash."""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

FPS = 60
_LOVED = {}


def _model(name):
    import motion_model as MM
    if name not in _LOVED.setdefault("_models", {}):
        _LOVED["_models"][name] = MM.load_model(name)
    return _LOVED["_models"][name]


def tensors(c):
    import motion_dataset as MD
    return MD.tensors(c)


def slerp_fill(q, p, keys):
    q, p = q.copy(), p.copy()
    for a, b in zip(keys, keys[1:]):
        for t in range(a + 1, b):
            u = (t - a) / (b - a)
            for j in range(q.shape[1]):
                q[t, j] = C.slerp(q[a, j], q[b, j], u)
                p[t, j] = p[a, j] * (1 - u) + p[b, j] * u
    return q, p


def model_fill(c_rot, c_pos, c_rv, keys, name, seed, group, tags, quality):
    """the model's fill of the whole clip (windows of WIN frames, each starting at a key) -> (q [T,6,4], p [T,6,3])"""
    import motion_model as MM
    model, ck = _model(name)
    x = MM.to_feat(c_rot, c_pos, c_rv)
    T = len(x)
    q_out, p_out = c_rot.copy(), c_pos.copy()
    start = 0
    while start < T - 1:
        end = min(T, start + MM.WIN)
        inner = [k for k in keys if start <= k < end]
        if end < T:                                         # cut the window at the last key inside it
            end = max(k for k in inner if k > start) + 1 if any(k > start for k in inner) else end
        seg = x[start:end]
        n = len(seg)
        obs = np.concatenate([seg, np.repeat(seg[-1:], MM.WIN - n, 0)]) if n < MM.WIN else seg
        mask = np.zeros((MM.WIN, model.feat), np.float32)
        for k in keys:
            if start <= k < end:
                mask[k - start] = 1
        mask[n:] = 1                                        # the padding is "given" (held last frame)
        f = MM.sample(model, ck, 1, obs=obs, mask=mask, group=group, quality=quality, tags=tags, guidance=1.0, seed=seed)[0][:n]
        qm, pm = MM.from_feat(f)
        q_out[start:end], p_out[start:end] = qm, pm
        start = end - 1
    return q_out, p_out


def weight(gap, short, long):
    return 0.0 if gap < short else 1.0 if gap > long else (gap - short) / float(long - short)


def blend(qs, ps, qm, pm, keys, short, long):
    q, p = qs.copy(), ps.copy()
    for a, b in zip(keys, keys[1:]):
        w = weight(b - a, short, long)
        if w <= 0:
            continue
        for t in range(a + 1, b):
            for j in range(q.shape[1]):
                q[t, j] = C.slerp(qs[t, j], qm[t, j], w)
            p[t] = ps[t] * (1 - w) + pm[t] * w
    return q, p


def ang(qa, qb):
    return np.degrees(2 * np.arccos(np.abs(np.sum(qa * qb, -1)).clip(0, 1)))


def pops(q, thresh=15.0):
    step = ang(q[1:], q[:-1])                             # [T-1, 6]
    n = 0
    for i in range(1, len(step) - 1):
        for j in range(step.shape[1]):
            if step[i, j] > thresh and step[i, j] > 3 * max(step[i - 1, j], step[i + 1, j], 1e-6):
                n += 1
    return n


def foot_jitter(q, p):
    import torch
    import motion_model as MM
    pts = MM.fk_points(torch.tensor(MM.quat_to_mat(q), dtype=torch.float64), torch.tensor(p, dtype=torch.float64))
    feet = [pts[l].numpy() for l in ("Right Leg", "Left Leg")]
    floor = min(f[:, 1].min() for f in feet)
    out = []
    for f in feet:
        v = np.diff(f, axis=0) * FPS
        a = np.linalg.norm(np.diff(v, axis=0), axis=1)
        planted = f[1:-1, 1] < floor + 0.12
        if planted.any():
            out.append(float(a[planted].mean()))
    return float(np.mean(out)) if out else 0.0


def loved_set(group):
    if group in _LOVED:
        return _LOVED[group]
    import motion_model as MM
    if not (os.path.isfile(os.path.join(MM.DATA, "labels.jsonl")) and os.path.isfile(os.path.join(MM.DATA, "clips.npz"))):
        _LOVED[group] = []                                     # the loved data is git-ignored: a fresh checkout has none -
        return []                                              # the fill still works, it is just not ranked against it
    labels = [json.loads(s) for s in open(os.path.join(MM.DATA, "labels.jsonl"), encoding="utf-8") if '"augmentation": null' in s]
    z = np.load(os.path.join(MM.DATA, "clips.npz"))
    rows = []
    for l in labels:
        if l["owner_verdict"] == "love" and l["licence"] == "game" and l.get("group") == group and l["id"] not in MM.HELD_COMBAT:
            rows.append((l["id"], z[f"{l['id']}/rot"]))
    _LOVED[group] = rows
    return rows


def dtw(a, b):
    cost = ang(a[:, None], b[None])
    n, m = cost.shape
    D = np.full((n + 1, m + 1), np.inf)
    L = np.zeros((n + 1, m + 1))
    D[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            opts = (D[i - 1, j - 1], D[i - 1, j], D[i, j - 1])
            k = int(np.argmin(opts))
            pi, pj = ((i - 1, j - 1), (i - 1, j), (i, j - 1))[k]
            D[i, j] = cost[i - 1, j - 1] + D[pi, pj]
            L[i, j] = L[pi, pj] + 1
    return float(D[n, m] / L[n, m])


def dtw_to_loved(q, group, shortlist=5, step=2):
    rows = loved_set(group)
    if not rows:
        return 0.0, None
    sig = lambda r: np.concatenate([r.mean(0).ravel(), r.std(0).ravel()])  # noqa: E731
    s = sig(q)
    cand = sorted(rows, key=lambda r: float(np.linalg.norm(sig(r[1]) - s)))[:shortlist]
    best = None
    for cid, r in cand:
        d = float(np.mean([dtw(q[::step, j], r[::step, j][:120]) for j in range(6)]))
        if best is None or d < best[0]:
            best = (d, cid)
    return best


def model_available(name):
    import motion_model as MM
    return os.path.isfile(os.path.join(MM.OUT, f"{name}.pt"))


def fill(c, keys, model="medium_v3", k=4, short=30, long=45, group="locomotion", tags=None, quality=0):
    """-> (clip, info): the hybrid fill of clip c (60 fps) keeping the frames at `keys`"""
    import warp as W
    c = W.to60(c)
    T = len(c["times"])
    keys = sorted({int(x) for x in keys if 0 <= int(x) < T} | {0, T - 1})
    rot, pos, _, rv, _ = tensors(c)
    qs, ps = slerp_fill(rot, pos, keys)
    gaps = [b - a for a, b in zip(keys, keys[1:])]
    warnings = []
    need_model = any(weight(g, short, long) > 0 for g in gaps)
    if need_model and not model_available(model):
        warnings.append(f"no model {model}.pt in _artifacts/r6model: every gap filled with slerp")
        need_model = False
    if need_model and group == "combat":
        warnings.append("combat: plain slerp beat the model on five held-out loved attacks (MOTION_MODEL_PLAN.md round 3) - "
                        "check this fill against a slerp one before keeping it")
    cands = []
    if not loved_set(group):
        warnings.append("no loved data (_artifacts/r6data, git-ignored): the fill is not ranked against the loved clips")
    for s in range(k if need_model else 1):
        if need_model:
            qm, pm = model_fill(rot, pos, rv, keys, model, s, group, tags, quality)
            q, p = blend(qs, ps, qm, pm, keys, short, long)
        else:
            q, p = qs, ps
        npop, jit = pops(q), foot_jitter(q, p)
        d, near = dtw_to_loved(q, group)
        cands.append({"seed": s, "pops": npop, "jitter": round(jit, 3), "dtw_loved": round(d, 2), "nearest_loved": near,
                      "score": round(npop * 5 + jit + d / 10.0, 3), "q": q, "p": p})
    best = min(cands, key=lambda x: x["score"])
    out = copy.deepcopy(c)
    for j, name in enumerate(["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]):
        out["joints"][name] = {"frames": [list(map(float, best["q"][i, j])) + list(map(float, best["p"][i, j])) for i in range(T)]}
    info = {"keys": keys, "gaps": gaps, "weights": [round(weight(g, short, long), 2) for g in gaps], "model": model if need_model else None,
            "warnings": warnings,
            "candidates": [{k_: v for k_, v in x.items() if k_ not in ("q", "p")} for x in cands], "picked_seed": best["seed"]}
    return out, info
