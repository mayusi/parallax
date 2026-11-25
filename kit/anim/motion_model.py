"""motion_model.py — the R6 MOTION DIFFUSION model (plan: MOTION_MODEL_PLAN.md). MDM-style (Tevet et al. 2022): a
transformer encoder predicts the clean motion x0 from a noised one; CondMDM-style inpainting (Cohan et al. 2024): the
observed frames / joints + their mask are part of the input, so keyframes or a fixed body part can be given at sampling.

    python kit/anim/motion_model.py train [--size small|medium] [--steps N] [--version 2]  -> _artifacts/r6model/<name>.pt
    (evaluation: kit/anim/motion_model_eval.py; the overfit check: diagnostics/overfit_test.py)

Data: _artifacts/r6data (kit/anim/motion_dataset.py), GAME-SAFE clips only; 10% of the locomotion source clips (and every
augmented copy) held out. Frame feature: 6 joints x (6D rotation + offset 3) + the Torso offset's velocity 3 = 57
(version 1); version 2 adds 2 foot-contact flags (FK on the R6 rig: the foot within 0.12 studs of the clip's own lowest foot
height) = 59. Normalisation: per-dim mean/std, normalised values CLIPPED to +-8 (a few clips snap the torso in one
frame: up to 182 std, diagnostics/out/model_audit.json).
Losses (version 2): x0 MSE + velocity MSE + POSITION loss (head, hands, feet, torso through a differentiable R6 FK, studs)
+ FOOT-SKATE loss (where the data plants a foot, the predicted foot must move like the data's: R6 clips run in place).
Masks (version 2): keyframes 80% of the time (gaps 10-90 frames), whole joints 10%, none 10%.
Conditions: group, quality = the owner's verdict, measured tags; each dropped 10% (classifier-free guidance).
Version 3 = RESIDUAL in-betweening (owner brief 2026-10-12): the model predicts a correction on top of the fill of the
given frames - x0 = base + delta, base = the given keys joined linearly per feature (lerp of the 6D columns + offsets =
normalised-lerp of the rotations, within a fraction of a degree of slerp; given whole joints copied; nothing given = the
mean) - and sees the base as an input; the output layer starts at zero, so training starts AT the interpolation."""
import json
import math
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

DATA = os.path.join("_artifacts", "r6data")
OUT = os.path.join("_artifacts", "r6model")
JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
CORE = 57
FEAT = 57                      # the active width; set_version() switches it
WIN = 120
T_STEPS = 100
CLIP_Z = 8.0
GROUPS = ["combat", "locomotion", "idle", "dance_emote", "other"]
QUALITY = {"love": 0, "ok": 1, "unrated": 2, "bad": 3, "laggy": 3}
SIZES = {"small": dict(d=256, layers=6, heads=4, ff=1024), "medium": dict(d=384, layers=8, heads=6, ff=1536)}
FLOOR = -3.0                   # the R6 floor: the foot ends 3 studs under the root at rest
VERSION = 1


def set_version(v):
    global FEAT, VERSION
    VERSION = int(v)
    FEAT = CORE + (2 if VERSION >= 2 else 0)


# ---------------------------------------------------------------- R6 forward kinematics (vectorised, matches clip.fk)
def _rig():
    import clip as C
    r = C.load_rig("r6")
    out = {}
    for p in r["order"]:
        j = r["joints"][p]
        out[p] = {"parent": j["parent"], "c0": C.cf(j["c0"]), "c1": C.cf(j["c1"])}
    return r["order"], out


ORDER, RIG = None, None
POINTS = {"Head": (0.0, 0.5, 0.0), "Right Arm": (0.0, -1.0, 0.0), "Left Arm": (0.0, -1.0, 0.0),
          "Right Leg": (0.0, -1.0, 0.0), "Left Leg": (0.0, -1.0, 0.0), "Torso": (0.0, 0.0, 0.0)}


def fk_points(R, P, xp=torch):
    """R [..., 6, 3, 3] character-space joint rotations, P [..., 6, 3] offsets (JOINTS order) -> {part: [..., 3]} world
    points (head top, hand / foot ends, torso centre) relative to the HumanoidRootPart. Same maths as clip.fk:
    part = parent * C0 * T * C1^-1, T = (C0r^T R C0r, C0r^T p)."""
    global ORDER, RIG
    if RIG is None:
        ORDER, RIG = _rig()
    like = R
    eye = xp.eye(4, dtype=like.dtype, device=like.device) if xp is torch else np.eye(4)
    shape = R.shape[:-3]
    world = {"HumanoidRootPart": eye.expand(*shape, 4, 4) if xp is torch else np.broadcast_to(eye, (*shape, 4, 4))}
    for part in ORDER:
        j = RIG[part]
        k = JOINTS.index(part)
        c0 = xp.tensor(j["c0"], dtype=like.dtype, device=like.device) if xp is torch else j["c0"]
        c1i = xp.tensor(np.linalg.inv(j["c1"]), dtype=like.dtype, device=like.device) if xp is torch else np.linalg.inv(j["c1"])
        c0r = c0[:3, :3]
        Rj = R[..., k, :, :]
        Tr = c0r.T @ Rj @ c0r
        Tp = (c0r.T @ P[..., k, :, None])[..., 0]
        top = xp.cat([Tr, Tp[..., None]], -1) if xp is torch else np.concatenate([Tr, Tp[..., None]], -1)
        bottom = xp.zeros((*shape, 1, 4), dtype=like.dtype, device=like.device) if xp is torch else np.zeros((*shape, 1, 4))
        if xp is torch:
            bottom[..., 0, 3] = 1.0
            T4 = xp.cat([top, bottom], -2)
        else:
            bottom[..., 0, 3] = 1.0
            T4 = np.concatenate([top, bottom], -2)
        world[part] = world[j["parent"]] @ c0 @ T4 @ c1i
    out = {}
    for part, pt in POINTS.items():
        v = xp.tensor([*pt, 1.0], dtype=like.dtype, device=like.device) if xp is torch else np.array([*pt, 1.0])
        out[part] = (world[part] @ v)[..., :3]
    return out


# ---------------------------------------------------------------- features
def quat_to_mat(q):
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


def mat_to_quat(m):
    import clip as C
    return np.array([C.mat_quat(r) for r in m.reshape(-1, 3, 3)]).reshape(*m.shape[:-2], 4)


def contacts(R, P, fps=60):
    """[T, 2] foot-contact flags (right, left): the foot end within 0.12 studs of the CLIP'S OWN lowest foot height.
    R6 clips run IN PLACE (the game moves the root), so a planted foot slides back at ground speed relative to the root -
    a speed test ("slower than 3 studs/s") marked 4.9% of a run's frames as planted; height alone is what is left"""
    pts = fk_points(torch.tensor(R, dtype=torch.float64), torch.tensor(P, dtype=torch.float64))
    feet = [pts[leg].numpy() for leg in ("Right Leg", "Left Leg")]
    floor = min(f[:, 1].min() for f in feet)
    return np.stack([(f[:, 1] < floor + 0.12).astype(np.float32) for f in feet], -1)


def to_feat(rot, pos, root_vel):
    R = quat_to_mat(rot)
    six = np.concatenate([R[..., :, 0], R[..., :, 1]], -1)
    f = np.concatenate([np.concatenate([six, pos], -1).reshape(len(rot), -1), root_vel], -1).astype(np.float32)
    if VERSION >= 2:
        f = np.concatenate([f, contacts(R, pos)], -1)
    return f


def six_to_mat(a, b, xp=np):
    if xp is torch:
        x = a / a.norm(dim=-1, keepdim=True).clamp_min(1e-8)
        y = b - (x * b).sum(-1, keepdim=True) * x
        y = y / y.norm(dim=-1, keepdim=True).clamp_min(1e-8)
        return torch.stack([x, y, torch.cross(x, y, dim=-1)], -1)
    x = a / np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), 1e-8)
    y = b - (x * b).sum(-1, keepdims=True) * x
    y = y / np.maximum(np.linalg.norm(y, axis=-1, keepdims=True), 1e-8)
    return np.stack([x, y, np.cross(x, y)], -1)


def from_feat(f):
    T = len(f)
    j = f[:, :54].reshape(T, 6, 9)
    R = six_to_mat(j[..., 0:3], j[..., 3:6])
    return mat_to_quat(R), j[..., 6:9]


def joint_dims(j):
    return list(range(j * 9, j * 9 + 9))


# ---------------------------------------------------------------- data
# five LOVED sword / weapon attacks, one per pack, kept out of training (and every augmented copy) for the combat
# in-betweening test (owner brief 2026-10-12): Sword Fox 'Slash 1', BEST R6 'Slash2(IDK)', CHAIN 'Swing 3',
# Free Friday 'Swing1', Mace 'Strike'. Models trained before this list existed (small, medium_v2) did see them.
HELD_COMBAT = {"s12510269939_2", "s91857791404560_1", "s17666652767_6", "d4555875_19_3", "s15605359138_5"}
COMBAT_TEST = []


def load_data(seed=0, ids=None):
    COMBAT_TEST.clear()
    labels =[json.loads(s) for s in open(os.path.join(DATA, "labels.jsonl"), encoding="utf-8")]
    labels = [l for l in labels if l["licence"] == "game"]
    if ids is not None:
        labels = [l for l in labels if l["id"] in ids]
    tags = sorted({t for l in labels for t in l.get("tags", [])})
    rng = np.random.default_rng(seed)
    loco = sorted({l["id"] for l in labels if l["augmentation"] is None and l.get("group") == "locomotion"})
    held = set() if ids is not None else set(rng.choice(loco, size=max(5, len(loco) // 10), replace=False).tolist())
    zc, za = np.load(os.path.join(DATA, "clips.npz")), np.load(os.path.join(DATA, "aug.npz"))
    train, test = [], []
    for l in labels:
        src = l.get("source_id") or l["id"]
        z = zc if l["augmentation"] is None else za
        f = to_feat(z[f"{l['id']}/rot"], z[f"{l['id']}/pos"], z[f"{l['id']}/root_vel"])
        item = {"id": l["id"], "src": src, "x": f, "group": GROUPS.index(l.get("group", "other")),
                "quality": QUALITY.get(l["owner_verdict"], 2), "loop": l["loop"],
                "tags": np.array([t in l.get("tags", []) for t in tags], np.float32)}
        if src in HELD_COMBAT:                             # the combat test's attacks: never trained on
            if l["augmentation"] is None:
                COMBAT_TEST.append(item)
        elif src in held:
            if l["augmentation"] is None:                  # a held-out clip is tested once, as recorded
                test.append(item)
        else:
            train.append(item)
    allx = np.concatenate([it["x"] for it in train])
    mean, std = allx.mean(0), np.maximum(allx.std(0), 1e-3)
    if VERSION >= 2:
        mean[CORE:], std[CORE:] = 0.5, 0.5                 # contacts are 0 / 1: map them to -1 / +1
    return train, test, tags, mean.astype(np.float32), std.astype(np.float32)


def window(x, loop, rng, n=WIN, start=None):
    T = len(x)
    valid = np.ones(n, np.float32)
    if T >= n:
        s = int(rng.integers(0, T - n + 1)) if start is None else min(start, T - n)
        return x[s:s + n], valid
    if loop:
        reps = int(math.ceil(n / max(1, T - 1)))
        return np.concatenate([x[:-1]] * reps + [x[-1:]])[:n], valid
    valid[T:] = 0.0
    return np.concatenate([x, np.repeat(x[-1:], n - T, 0)]), valid


def mask_v1(rng, n=WIN):
    m = np.zeros((n, FEAT), np.float32)
    r = rng.random()
    if r < 0.3:
        return m
    if r < 0.55:
        k = int(rng.integers(2, 8))
        m[sorted(set(rng.choice(n, size=k, replace=False).tolist()) | {0, n - 1})] = 1
    elif r < 0.8:
        for j in rng.choice(6, size=int(rng.integers(1, 4)), replace=False):
            m[:, joint_dims(int(j))] = 1
    else:
        a, b = int(rng.integers(5, 30)), int(rng.integers(5, 30))
        m[:a] = 1
        m[n - b:] = 1
    return m


def mask_v2(rng, n=WIN):
    """keyframes 80% (a regular gap of 10-90 frames, a random phase, both ends), whole joints 10%, none 10%"""
    m = np.zeros((n, FEAT), np.float32)
    r = rng.random()
    if r < 0.8:
        gap = int(rng.integers(10, 91))
        keys = set(range(int(rng.integers(0, gap)), n, gap)) | {0, n - 1}
        m[sorted(keys)] = 1
    elif r < 0.9:
        for j in rng.choice(6, size=int(rng.integers(1, 4)), replace=False):
            m[:, joint_dims(int(j))] = 1
    return m


def base_fill(xn, mask):
    """the residual's base for ONE example (normalised [T, F], mask [T, F]): every feature column joined linearly
    between the frames where it is given (held before the first / after the last); a column given nowhere = 0 (the mean)"""
    T, F = xn.shape
    out = np.zeros_like(xn)
    t = np.arange(T)
    for f in range(F):
        given = np.where(mask[:, f] > 0.5)[0]
        if len(given) == 0:
            continue
        out[:, f] = np.interp(t, given, xn[given, f])
    return out


# ---------------------------------------------------------------- model
class MotionDiffusion(nn.Module):
    def __init__(self, n_tags, feat=57, d=256, layers=6, heads=4, ff=1024, max_len=WIN, residual=False):
        super().__init__()
        self.feat = feat
        self.residual = residual
        self.inp = nn.Linear(feat * (4 if residual else 3), d)
        self.step = nn.Sequential(nn.Linear(d, d), nn.SiLU(), nn.Linear(d, d))
        self.group = nn.Embedding(len(GROUPS) + 1, d)
        self.quality = nn.Embedding(5, d)
        self.tags = nn.Linear(n_tags, d)
        self.pos = nn.Parameter(torch.zeros(1, max_len + 2, d))
        layer = nn.TransformerEncoderLayer(d, heads, ff, dropout=0.1, activation="gelu", batch_first=True, norm_first=True)
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.out = nn.Linear(d, feat)
        if residual:                                       # start exactly at the interpolation
            nn.init.zeros_(self.out.weight)
            nn.init.zeros_(self.out.bias)
        self.d = d

    def step_embed(self, t):
        half = self.d // 2
        f = torch.exp(-torch.arange(half, device=t.device) * (math.log(10000.0) / half))
        a = t[:, None].float() * f[None]
        return self.step(torch.cat([a.sin(), a.cos()], -1))

    def forward(self, xt, obs, mask, t, group, quality, tags, base=None):
        parts = [xt, obs * mask, mask] + ([base] if self.residual else [])
        h = self.inp(torch.cat(parts, -1))
        cond = (self.group(group) + self.quality(quality) + self.tags(tags))[:, None]
        tok = torch.cat([self.step_embed(t)[:, None], cond, h], 1) + self.pos[:, : h.shape[1] + 2]
        out = self.out(self.enc(tok)[:, 2:])
        return base + out if self.residual else out


def schedule(T=T_STEPS):
    s = 0.008
    t = np.linspace(0, T, T + 1) / T
    ac = np.cos((t + s) / (1 + s) * math.pi / 2) ** 2
    ac = ac / ac[0]
    betas = np.clip(1 - ac[1:] / ac[:-1], 1e-5, 0.999)
    return torch.tensor(betas, dtype=torch.float32), torch.tensor(np.cumprod(1 - betas), dtype=torch.float32)


# ---------------------------------------------------------------- train
def batch(items, rng, mean, std, bs, dev, mask_fn, cond_drop=0.1):
    idx = rng.integers(0, len(items), bs)
    X, V, M, G, Q, TG, BS = [], [], [], [], [], [], []
    for i in idx:
        it = items[i]
        x, v = window(it["x"], it["loop"], rng)
        xn = np.clip((x - mean) / std, -CLIP_Z, CLIP_Z)
        m = mask_fn(rng)
        X.append(xn)
        V.append(v)
        M.append(m)
        BS.append(base_fill(xn, m) if VERSION >= 3 else np.zeros_like(xn))
        G.append(it["group"] if rng.random() > cond_drop else len(GROUPS))
        Q.append(it["quality"] if rng.random() > cond_drop else 4)
        TG.append(it["tags"] if rng.random() > cond_drop else np.zeros_like(it["tags"]))
    t = lambda a, dt=torch.float32: torch.tensor(np.array(a), dtype=dt, device=dev)  # noqa: E731
    return t(X), t(V), t(M), t(G, torch.long), t(Q, torch.long), t(TG), t(BS)


def decode_torch(xn, mean, std):
    """normalised features [B, T, F] -> (R [B,T,6,3,3], P [B,T,6,3]) in raw units"""
    x = xn * std + mean
    B, T = x.shape[:2]
    j = x[..., :54].reshape(B, T, 6, 9)
    return six_to_mat(j[..., 0:3], j[..., 3:6], torch), j[..., 6:9]


def fit(items, tags, mean, std, size="small", steps=40000, bs=64, lr=2e-4, seed=0, mask_fn=None, cond_drop=0.1,
        w_pos=1.0, w_skate=0.5, log_every=1000, dev="cuda", init=None):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    mask_fn = mask_fn or (mask_v2 if VERSION >= 2 else mask_v1)
    model = MotionDiffusion(len(tags), FEAT, **SIZES[size], residual=VERSION >= 3).to(dev)
    if init is not None:                                   # a fine-tune continues a trained model
        model.load_state_dict(init)
    opt = torch.optim.AdamW(model.parameters(), lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, lr, total_steps=steps, pct_start=0.05)
    _, abar = schedule()
    abar = abar.to(dev)
    mean_t, std_t = torch.tensor(mean, device=dev), torch.tensor(std, device=dev)
    log, t0 = [], time.time()
    for step in range(1, steps + 1):
        x0, valid, mask, g, q, tg, base = batch(items, rng, mean, std, bs, dev, mask_fn, cond_drop)
        t = torch.randint(0, T_STEPS, (bs,), device=dev)
        a = abar[t][:, None, None]
        xt = a.sqrt() * x0 + (1 - a).sqrt() * torch.randn_like(x0)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            pred = model(xt, x0, mask, t, g, q, tg, base)
        pred = pred.float()
        w = valid[..., None]
        rec = (((pred - x0) ** 2) * w).sum() / (w.sum() * FEAT)
        vel = ((((pred[:, 1:] - pred[:, :-1]) - (x0[:, 1:] - x0[:, :-1])) ** 2) * w[:, 1:]).sum() / (w[:, 1:].sum() * FEAT)
        loss = rec + 0.5 * vel
        parts = {"rec": float(rec), "vel": float(vel)}
        if VERSION >= 2:
            Rp, Pp = decode_torch(pred, mean_t, std_t)
            Rg, Pg = decode_torch(x0, mean_t, std_t)
            fp, fg = fk_points(Rp, Pp), fk_points(Rg, Pg)
            pos = sum(((fp[k] - fg[k]) ** 2).sum(-1) for k in fp) / len(fp)
            pos = (pos * valid).sum() / valid.sum()
            contact = (x0[..., CORE:] * std_t[CORE:] + mean_t[CORE:]) > 0.5          # the data's planted feet
            sk = 0.0
            for i_, leg in enumerate(("Right Leg", "Left Leg")):
                # planted feet move like the DATA's (in place: back at ground speed), not just "do not move"
                dp = fp[leg][:, 1:] - fp[leg][:, :-1]
                dg = fg[leg][:, 1:] - fg[leg][:, :-1]
                c = contact[:, 1:, i_].float() * valid[:, 1:]
                sk = sk + ((dp - dg).pow(2).sum(-1) * c).sum() / c.sum().clamp_min(1.0)
            loss = loss + w_pos * pos + w_skate * sk * 60.0
            parts.update(pos=float(pos), skate=float(sk))
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        if step % log_every == 0 or step == 1:
            log.append({"step": step, "loss": round(float(loss), 5), **{k: round(v, 5) for k, v in parts.items()},
                        "minutes": round((time.time() - t0) / 60, 2)})
            print(json.dumps(log[-1]), flush=True)
    return model, log


def save(model, log, name, size, tags, mean, std, steps, n_train, n_test):
    os.makedirs(OUT, exist_ok=True)
    torch.save({"model": model.state_dict(), "size": size, "version": VERSION, "feat": FEAT, "tags": list(tags),
                "mean": torch.tensor(mean), "std": torch.tensor(std), "steps": steps, "train_items": n_train,
                "test_items": n_test, "log": log}, os.path.join(OUT, f"{name}.pt"))


# ---------------------------------------------------------------- sample
def load_model(name="small", dev="cuda"):
    ck = torch.load(os.path.join(OUT, f"{name}.pt"), map_location=dev, weights_only=True)   # tensors + plain data only
    set_version(ck.get("version", 1))
    ck["mean"], ck["std"] = ck["mean"].cpu().numpy(), ck["std"].cpu().numpy()
    m = MotionDiffusion(len(ck["tags"]), ck.get("feat", 57), **SIZES[ck["size"]], residual=ck.get("version", 1) >= 3).to(dev)
    m.load_state_dict(ck["model"])
    m.eval()
    return m, ck


@torch.no_grad()
def sample(model, ck, n=1, obs=None, mask=None, group=None, quality=0, tags=None, guidance=2.0, seed=0, dev="cuda"):
    """obs [WIN, F] RAW units, mask [WIN, F] (1 = given); -> [n, WIN, F] raw"""
    F_ = model.feat
    g_ = torch.Generator(device=dev).manual_seed(seed)
    mean, std = torch.tensor(ck["mean"], device=dev), torch.tensor(ck["std"], device=dev)
    obs_n = torch.zeros(n, WIN, F_, device=dev) if obs is None else ((torch.tensor(obs, device=dev) - mean) / std).clamp(-CLIP_Z, CLIP_Z)[None].repeat(n, 1, 1)
    msk = torch.zeros(n, WIN, F_, device=dev) if mask is None else torch.tensor(mask, device=dev)[None].repeat(n, 1, 1)
    base = None
    if model.residual:
        b = base_fill(obs_n[0].cpu().numpy(), msk[0].cpu().numpy()) if obs is not None and mask is not None else np.zeros((WIN, F_), np.float32)
        base = torch.tensor(b, device=dev, dtype=torch.float32)[None].repeat(n, 1, 1)
    gi = torch.full((n,), len(GROUPS) if group is None else GROUPS.index(group), device=dev, dtype=torch.long)
    qi = torch.full((n,), 4 if quality is None else quality, device=dev, dtype=torch.long)
    tg = torch.zeros(n, len(ck["tags"]), device=dev)
    for t_ in tags or []:
        if t_ in ck["tags"]:
            tg[:, ck["tags"].index(t_)] = 1
    betas, abar = schedule()
    betas, abar = betas.to(dev), abar.to(dev)
    x = torch.randn(n, WIN, F_, device=dev, generator=g_)
    for t in reversed(range(T_STEPS)):
        tt = torch.full((n,), t, device=dev, dtype=torch.long)
        x0c = model(x, obs_n, msk, tt, gi, qi, tg, base)
        if guidance and guidance != 1.0:
            x0u = model(x, obs_n, msk, tt, torch.full_like(gi, len(GROUPS)), torch.full_like(qi, 4), torch.zeros_like(tg), base)
            x0 = x0u + guidance * (x0c - x0u)
        else:
            x0 = x0c
        x0 = x0 * (1 - msk) + obs_n * msk
        if t == 0:
            x = x0
            break
        a_t, a_prev = abar[t], abar[t - 1]
        mu = betas[t] * a_prev.sqrt() / (1 - a_t) * x0 + (1 - a_prev) * (1 - betas[t]).sqrt() / (1 - a_t) * x
        x = mu + (betas[t] * (1 - a_prev) / (1 - a_t)).sqrt() * torch.randn(x.shape, device=dev, generator=g_)
    return (x * std + mean).cpu().numpy()


def to_clip(f, name, loop=False):
    q, p = from_feat(f)
    return {"schema": 1, "name": name, "rig": "R6", "fps": 60, "loop": loop, "priority": "Action",
            "times": [round(i / 60, 6) for i in range(len(f))], "events": [],
            "joints": {j: {"frames": [list(map(float, q[i, k])) + list(map(float, p[i, k])) for i in range(len(f))]}
                       for k, j in enumerate(JOINTS)}}


def main(argv):
    size = argv[argv.index("--size") + 1] if "--size" in argv else "small"
    if argv[:1] == ["train"]:
        steps = int(argv[argv.index("--steps") + 1]) if "--steps" in argv else 40000
        set_version(int(argv[argv.index("--version") + 1]) if "--version" in argv else 1)
        name = argv[argv.index("--name") + 1] if "--name" in argv else size
        tr, te, tags, mean, std = load_data(0)
        model, log = fit(tr, tags, mean, std, size, steps)
        save(model, log, name, size, tags, mean, std, steps, len(tr), len(te))
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"trained {name} ({size}, v{VERSION}) for {steps} steps: last {log[-1]}",
                          "next_action": f"python kit/anim/motion_model_eval.py --name {name}"}))
        return 0
    if argv[:1] == ["finetune"]:
        # continue a trained model on ONE group (owner brief 2026-10-12: 30k steps on combat, game-safe) - the base's
        # normalisation and tag list are kept so the fine-tune reads the same features; HELD_COMBAT stays out
        base = argv[argv.index("--from") + 1] if "--from" in argv else "medium_v3"
        group = argv[argv.index("--group") + 1] if "--group" in argv else "combat"
        steps = int(argv[argv.index("--steps") + 1]) if "--steps" in argv else 30000
        name = argv[argv.index("--name") + 1] if "--name" in argv else f"{base}_{group}"
        _, ck = load_model(base, "cpu")
        tr, te, tags, _, _ = load_data(0)
        assert list(tags) == list(ck["tags"]), "the tag list changed since the base model was trained"
        items = [it for it in tr if GROUPS[it["group"]] == group]
        model, log = fit(items, tags, ck["mean"], ck["std"], ck["size"], steps, lr=5e-5, init=ck["model"])
        save(model, log, name, ck["size"], tags, ck["mean"], ck["std"], steps, len(items), len(te))
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"fine-tuned {base} -> {name} on {group} ({len(items)} items incl. augmented) for {steps} steps: last {log[-1]}",
                          "next_action": f"python diagnostics/combat_fill_test.py {name}"}))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))


@torch.no_grad()
def sdedit(model, ck, x_raw, t_start, seed=0, group=None, quality=0, tags=None, guidance=2.0, dev="cuda"):
    """SDEdit (Meng et al. 2022): noise a motion [WIN, F] (raw units) to step t_start, then denoise it back with the
    model - nothing given (no keys), so the model may move every frame; small t keeps the input, large t re-imagines it"""
    F_ = model.feat
    g_ = torch.Generator(device=dev).manual_seed(seed)
    mean, std = torch.tensor(ck["mean"], device=dev), torch.tensor(ck["std"], device=dev)
    x0 = ((torch.tensor(x_raw, device=dev, dtype=torch.float32) - mean) / std).clamp(-CLIP_Z, CLIP_Z)[None]
    betas, abar = schedule()
    betas, abar = betas.to(dev), abar.to(dev)
    t_start = int(min(T_STEPS - 1, max(0, t_start)))
    x = abar[t_start].sqrt() * x0 + (1 - abar[t_start]).sqrt() * torch.randn(x0.shape, device=dev, generator=g_)
    obs = torch.zeros_like(x0)
    msk = torch.zeros_like(x0)
    base = torch.zeros_like(x0) if model.residual else None
    gi = torch.full((1,), len(GROUPS) if group is None else GROUPS.index(group), device=dev, dtype=torch.long)
    qi = torch.full((1,), 4 if quality is None else quality, device=dev, dtype=torch.long)
    tg = torch.zeros(1, len(ck["tags"]), device=dev)
    for t_ in tags or []:
        if t_ in ck["tags"]:
            tg[:, ck["tags"].index(t_)] = 1
    for t in reversed(range(t_start + 1)):
        tt = torch.full((1,), t, device=dev, dtype=torch.long)
        x0c = model(x, obs, msk, tt, gi, qi, tg, base) if model.residual else model(x, obs, msk, tt, gi, qi, tg)
        if guidance and guidance != 1.0:
            un = (x, obs, msk, tt, torch.full_like(gi, len(GROUPS)), torch.full_like(qi, 4), torch.zeros_like(tg))
            x0u = model(*un, base) if model.residual else model(*un)
            x0p = x0u + guidance * (x0c - x0u)
        else:
            x0p = x0c
        if t == 0:
            x = x0p
            break
        a_t, a_prev = abar[t], abar[t - 1]
        mu = betas[t] * a_prev.sqrt() / (1 - a_t) * x0p + (1 - a_prev) * (1 - betas[t]).sqrt() / (1 - a_t) * x
        x = mu + (betas[t] * (1 - a_prev) / (1 - a_t)).sqrt() * torch.randn(x.shape, device=dev, generator=g_)
    return (x[0] * std + mean).cpu().numpy()
