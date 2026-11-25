"""motion_model_gaps.py — in-betweening on HELD-OUT locomotion clips at several keyframe gaps, model vs plain slerp
(owner brief 2026-10-12, step 3):
    python kit/anim/motion_model_gaps.py <model name> [--gaps 20,30,60,90]   -> _artifacts/r6model/gaps_<name>.json
Per gap, over the frames BETWEEN keys (both ends + every gap-th frame are given):
  angle_deg     mean joint angle error vs the real clip
  vel_deg_s     mean |angular speed error| per joint (deg/s), i.e. timing / spacing
  skate_studs_s where the real clip plants a foot (height, kit/anim/motion_model.py contacts), the mean speed of the
                difference between the produced foot and the real foot (studs/s): 0 = the foot moves exactly like the data
  float_studs   where the real foot is planted, how high the produced foot is above the real one (studs, mean)"""
import json
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import motion_model as MM  # noqa: E402


def slerp_fill(f, keys):
    q, p = MM.from_feat(f)
    q, p = q.copy(), p.copy()
    for a, b in zip(keys, keys[1:]):
        for t in range(a + 1, b):
            u = (t - a) / (b - a)
            for j in range(6):
                q[t, j] = C.slerp(q[a, j], q[b, j], u)
                p[t, j] = p[a, j] * (1 - u) + p[b, j] * u
    return q, p


def ang(qa, qb):
    return np.degrees(2 * np.arccos(np.abs(np.sum(qa * qb, -1)).clip(0, 1)))


def speeds(q):
    return ang(q[1:], q[:-1]) * 60.0                      # [T-1, 6] deg/s


def feet(q, p):
    pts = MM.fk_points(torch.tensor(MM.quat_to_mat(q), dtype=torch.float64), torch.tensor(p, dtype=torch.float64))
    return [pts["Right Leg"].numpy(), pts["Left Leg"].numpy()]


def metrics(qm, pm, qt, pt, free, valid):
    fr = [t for t in free if valid[t] > 0]
    out = {"angle_deg": float(ang(qm[fr], qt[fr]).mean())}
    sm, st = speeds(qm), speeds(qt)
    fv = [t for t in fr if t < len(sm)]
    out["vel_deg_s"] = float(np.abs(sm[fv] - st[fv]).mean())
    fm, ft = feet(qm, pm), feet(qt, pt)
    floor = min(f[:, 1].min() for f in ft)
    sk, fl = [], []
    for a, b in zip(fm, ft):
        planted = [t for t in fv if b[t, 1] < floor + 0.12]
        if planted:
            dm, dt = a[1:] - a[:-1], b[1:] - b[:-1]
            sk += list(np.linalg.norm(dm[planted] - dt[planted], axis=1) * 60.0)
            fl += list(a[planted, 1] - b[planted, 1])
    out["skate_studs_s"] = float(np.mean(sk)) if sk else 0.0
    out["float_studs"] = float(np.mean(fl)) if fl else 0.0
    return out


def run(name, gaps=(20, 30, 60, 90), dev="cuda"):
    model, ck = MM.load_model(name, dev)
    _, te, _, _, _ = MM.load_data(0)
    res = {"model": name, "version": MM.VERSION, "held_out_clips": len(te), "gaps": {}}
    for gap in gaps:
        rows = {"model": [], "slerp": []}
        for i, it in enumerate(te):
            x, valid = MM.window(it["x"], it["loop"], np.random.default_rng(0), start=0)
            keys = sorted(set(range(0, MM.WIN, gap)) | {MM.WIN - 1})
            mask = np.zeros((MM.WIN, model.feat), np.float32)
            mask[keys] = 1
            f = MM.sample(model, ck, 1, obs=x, mask=mask, group="locomotion", quality=None, guidance=1.0, seed=i)[0]
            qm, pm = MM.from_feat(f)
            qt, pt = MM.from_feat(x)
            qs, ps = slerp_fill(x, keys)
            free = [t for t in range(MM.WIN) if t not in keys]
            rows["model"].append(metrics(qm, pm, qt, pt, free, valid))
            rows["slerp"].append(metrics(qs, ps, qt, pt, free, valid))
        agg = {k: {m: round(float(np.mean([r[m] for r in v])), 3) for m in v[0]} for k, v in rows.items()}
        agg["model_better_angle_on"] = int(sum(a["angle_deg"] < b["angle_deg"] for a, b in zip(rows["model"], rows["slerp"])))
        res["gaps"][gap] = agg
        print(f"gap {gap}: model {agg['model']}  slerp {agg['slerp']}  (model better on {agg['model_better_angle_on']}/{len(te)})", flush=True)
    os.makedirs(MM.OUT, exist_ok=True)
    json.dump(res, open(os.path.join(MM.OUT, f"gaps_{name}.json"), "w"), indent=1)
    return res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    gaps = tuple(int(g) for g in sys.argv[sys.argv.index("--gaps") + 1].split(",")) if "--gaps" in sys.argv else (20, 30, 60, 90)
    run(sys.argv[1], gaps)
