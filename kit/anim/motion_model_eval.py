"""motion_model_eval.py — the smoke-test evaluation of kit/anim/motion_model.py (owner brief 2026-10-12):
    python kit/anim/motion_model_eval.py [--size small]   -> _artifacts/r6model/eval/ (report.json, 12 sample gifs + sheet)
1. in-betweening on HELD-OUT locomotion clips (keyframes every 20 frames) vs plain slerp between the same keyframes
2. the body filled around GsRunV4c's right arm (the arm given every frame)
3. 12 samples: 10 by condition (group + tags, quality = loved, guidance 2) + 2 of the fixed-arm bodies, rendered
4. memorisation: each sample's DTW (deg, per joint, mean) to its nearest TRAINING clip; the yardstick = held-out real
   clips' DTW to their nearest training clip (a sample far below that is likely a near-copy)"""
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
import motion_model as MM  # noqa: E402
from blender_path import find_blender  # noqa: E402

OUT = os.path.join(MM.OUT, "eval")
WIN, FEAT = MM.WIN, MM.FEAT


def quat_err(a, b):
    d = np.abs(np.sum(a * b, -1)).clip(0, 1)
    return np.degrees(2 * np.arccos(d))


def slerp_baseline(q, p, keys):
    import clip as C
    out_q, out_p = q.copy(), p.copy()
    for a, b in zip(keys, keys[1:]):
        for t in range(a + 1, b):
            u = (t - a) / (b - a)
            for j in range(6):
                out_q[t, j] = C.slerp(q[a, j], q[b, j], u)
                out_p[t, j] = p[a, j] * (1 - u) + p[b, j] * u
    return out_q, out_p


def dtw(a, b):
    cost = quat_err(a[:, None], b[None])
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


def signature(x):
    return np.concatenate([x[:, :54].mean(0), x[:, :54].std(0)])


def nearest_train(f, train_orig, k=10, step=2, exclude=None):
    s = signature(f)
    pool = [it for it in train_orig if it["id"] != exclude]
    cand = sorted(pool, key=lambda it: float(np.linalg.norm(signature(it["x"]) - s)))[:k]
    q, _ = MM.from_feat(f[::step])
    best = None
    for it in cand:
        qt, _ = MM.from_feat(it["x"][::step][:240])
        per = [dtw(q[:, j], qt[:, j]) for j in range(6)]
        m = float(np.mean(per))
        if best is None or m < best[0]:
            best = (m, it["id"], [round(v, 1) for v in per])
    return best


def render(clip_path, out_dir, name, size=300):
    subprocess.run([find_blender() or "blender", "-b", os.environ.get("PARALLAX_R6_RIG") or "assets/rigs/R6_IK.blend", "--disable-autoexec",
                    "--python-exit-code", "2", "-P", "kit/anim/look_r6.py", "--", f"{name}.r6", "--clip", clip_path, "--out", out_dir,
                    "--size", str(size), "--views", "2"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    subprocess.run([sys.executable, "kit/anim/look_sheet.py", os.path.join(out_dir, f"{name}.r6.look")], capture_output=True)
    return os.path.join(out_dir, f"{name}.r6.look.gif")


def evaluate(size="small", dev="cuda"):
    global OUT
    OUT = os.path.join(MM.OUT, "eval" if size == "small" else f"eval_{size}")
    os.makedirs(OUT, exist_ok=True)
    model, ck = MM.load_model(size, dev)
    global FEAT
    FEAT = MM.FEAT                                         # the checkpoint's width (57 for v1, 59 for v2)
    tr, te, _, _, _ = MM.load_data(0)
    train_orig = [it for it in tr if it["id"] == it["src"]]
    rep = {"size": size, "steps": ck["steps"], "train_items": ck["train_items"], "held_out_locomotion_clips": len(te)}
    # 1. in-betweening
    em, eb = [], []
    for i, it in enumerate(te):
        x, valid = MM.window(it["x"], it["loop"], np.random.default_rng(0))
        keys = list(range(0, WIN, 20)) + [WIN - 1]
        mask = np.zeros((WIN, FEAT), np.float32)
        mask[keys] = 1
        f = MM.sample(model, ck, 1, obs=x, mask=mask, group="locomotion", quality=None, guidance=1.0, seed=i)[0]
        qm, _ = MM.from_feat(f)
        qt, pt = MM.from_feat(x)
        qb, _ = slerp_baseline(qt, pt, keys)
        free = [t for t in range(WIN) if t not in keys and valid[t] > 0]
        em.append(float(quat_err(qm[free], qt[free]).mean()))
        eb.append(float(quat_err(qb[free], qt[free]).mean()))
    rep["inbetween"] = {"clips": len(te), "keys_every_frames": 20, "model_mean_err_deg": round(float(np.mean(em)), 2),
                        "slerp_mean_err_deg": round(float(np.mean(eb)), 2), "model_better_on": int(sum(a < b for a, b in zip(em, eb))),
                        "per_clip": [{"id": it["id"], "model": round(a, 2), "slerp": round(b, 2)} for it, a, b in zip(te, em, eb)]}
    # 2. the body around GsRunV4c's right arm
    import motion_dataset as MD
    import warp as W
    gc = W.to60(json.load(open(os.path.join("build", "animations", "GsRunV4c.clip.json"), encoding="utf-8")))
    rot, pos, _, rv, _ = MD.tensors(gc)
    arm = MM.to_feat(rot, pos, rv)
    reps = int(math.ceil(WIN / (len(arm) - 1)))
    arm = np.concatenate([arm[:-1]] * reps + [arm[-1:]])[:WIN]
    amask = np.zeros((WIN, FEAT), np.float32)
    amask[:, MM.joint_dims(2)] = 1                       # joint 2 = Right Arm
    arm_s = MM.sample(model, ck, 3, obs=arm, mask=amask, group="locomotion", quality=0, tags=["stride", "loop"], guidance=2.0, seed=7)
    qa, _ = MM.from_feat(arm)
    rep["fixed_arm"] = {"source": "build/animations/GsRunV4c.clip.json Right Arm, tiled to 2 s; group locomotion, tags stride+loop, quality loved",
                        "arm_kept_err_deg": [round(float(quat_err(MM.from_feat(s)[0][:, 2], qa[:, 2]).mean()), 3) for s in arm_s]}
    # 3. samples
    conds = [("locomotion", ["stride", "loop"]), ("locomotion", ["stride", "loop"]), ("locomotion", ["stride", "fast"]),
             ("combat", ["strike", "fast"]), ("combat", ["strike", "heavy", "lunge"]), ("combat", ["strike", "spin"]),
             ("idle", ["loop", "holds"]), ("idle", ["loop", "slow"]), ("dance_emote", ["loop"]), ("dance_emote", ["botharms"])]
    samples = []
    for i, (g, tg) in enumerate(conds):
        f = MM.sample(model, ck, 1, group=g, quality=0, tags=tg, guidance=2.0, seed=100 + i)[0]
        samples.append((f"S{i + 1:02d}_{g}", f, g, tg))
    samples += [("S11_fixed_arm", arm_s[0], "locomotion", ["fixed GsRunV4c arm"]), ("S12_fixed_arm", arm_s[1], "locomotion", ["fixed GsRunV4c arm"])]
    # 4. memorisation
    mem = []
    for name, f, g, tg in samples:
        d, cid, per = nearest_train(f, train_orig)
        mem.append({"sample": name, "group": g, "tags": tg, "nearest_train": cid, "dtw_deg": round(d, 2), "per_joint": per})
    real = []
    for it in te[:8]:
        d, cid, _ = nearest_train(it["x"][:WIN], train_orig)
        real.append({"held_out": it["id"], "nearest_train": cid, "dtw_deg": round(d, 2)})
    rep["memorisation"] = {"samples": mem, "held_out_real_clips": real}
    # renders
    jobs = []
    for name, f, g, _ in samples:
        p = os.path.join(OUT, f"{name}.clip.json")
        json.dump(MM.to_clip(f, name, g in ("locomotion", "idle")), open(p, "w", encoding="utf-8"))
        jobs.append((p, name))
    with ThreadPoolExecutor(3) as ex:
        rep["gifs"] = list(ex.map(lambda j: render(j[0], OUT, j[1]), jobs))
    json.dump(rep, open(os.path.join(OUT, "report.json"), "w", encoding="utf-8"), indent=1)
    return rep


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    size = sys.argv[sys.argv.index("--name") + 1] if "--name" in sys.argv else (sys.argv[sys.argv.index("--size") + 1] if "--size" in sys.argv else "small")
    r = evaluate(size)
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"eval {size}: in-between model {r['inbetween']['model_mean_err_deg']} deg vs slerp {r['inbetween']['slerp_mean_err_deg']} deg "
                                 f"(better on {r['inbetween']['model_better_on']}/{r['inbetween']['clips']}); fixed arm kept within {r['fixed_arm']['arm_kept_err_deg']} deg",
                      "next_action": "read _artifacts/r6model/eval/report.json"}))
