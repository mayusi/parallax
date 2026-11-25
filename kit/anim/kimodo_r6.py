"""kimodo_r6.py — KIMODO-R6: NVIDIA's Kimodo text-to-motion model fine-tuned to generate the R6 rig NATIVELY (owner brief
2026-10-13: "stop translating human motion"). Runs in the Kimodo venv (~/.venvs/kimodo: torch + the kimodo package).

LICENCE  Kimodo-SOMA-RP-v1.1 weights: NVIDIA Open Model License - commercial use, "free to create and distribute
         Derivative Models", the derivative is ours; keep guardrails; attribution notice only if the WEIGHTS are ever
         distributed. Text features come from Llama-3 (LLM2Vec): a model trained with them must be named "Llama 3 ..."
         only if it is distributed. Outputs (animations) are unrestricted. (VETLOG 2026-10-12 / 2026-10-13)

R6 AS A KIMODO SKELETON (Kimodo's own feature layout, KimodoMotionRep, 30 fps, metres = studs x SCALE):
  11 joints: 0 Torso (root = the torso centre: Torso offset + travel), 1 neck, 2 right shoulder, 3 left shoulder,
             4 right hip, 5 left hip (the R6 PIVOTS, limb slides included), 6 head top, 7 / 8 hands, 9 / 10 feet
             (the R6 limb ENDS: hand / foot paths are explicit features); an end's rotation = its part's
  features: smooth_root_pos 3 | global_root_heading 2 | local_joints_positions 11x3 | global_rot_data 11x6 (6D) |
            velocities 11x3 | foot_contacts 2   = 139 numbers a frame
  decode: part rotations -> R6 joint quats (C0r = C1r on every R6 joint, so a joint's quat is its part's turn in
          the parent); pivot positions -> the limb SLIDES and the Torso offset; smooth root -> the clip's root track
MODEL    kimodo.model.twostage_denoiser.TwostageDenoiser built with the R6 rep: NEW input / output projections (both
         stages), everything else - 2 x 16-layer 1024-d transformers, text projection (LLM2Vec 4096 -> 1024), timestep
         and heading embeddings - loaded from Kimodo-SOMA-RP-v1.1. LoRA (rank R) on every attention in-proj / out-proj
         and feed-forward weight; trained: LoRA + the new projections. bf16 autocast, fits 12 GB.
TRAIN    x0-prediction diffusion on Kimodo's 1000-step cosine schedule; text dropped 10% (classifier-free guidance);
         game-safe clips minus the owner's bad / laggy, augmentations included, 30 base clips (+ their copies) held
SAMPLE   DDIM (Kimodo's sampler) 100 steps, text guidance 2
    <kimodo venv> python kit/anim/kimodo_r6.py data              -> _artifacts/kimodo_r6/data.npz (+ stats)
    <kimodo venv> python kit/anim/kimodo_r6.py train [steps] [rank]
    <kimodo venv> python kit/anim/kimodo_r6.py sample "<prompt>" [seconds] [--out clip.json]"""
import json
import math
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.utils.parametrize as P

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
OUT = os.path.join(ROOT, "_artifacts", "kimodo_r6")
DATA = os.path.join(ROOT, "_artifacts", "r6data")
FPS = 30
SCALE = 0.3                    # metres per stud (R6 is 5 studs tall ~ 1.5 m)
MAXF = 150                     # training crop: 5 s
JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
N_J = 11
FEET = (9, 10)
HOLD = 30
DEV = "cuda"


# ---------------------------------------------------------------- R6 kinematics (numpy)
def _rig():
    import clip as C
    r = C.load_rig("r6")
    return {p: (C.cf(r["joints"][p]["c0"]), C.cf(r["joints"][p]["c1"]), r["joints"][p]["parent"]) for p in JOINTS}, r["order"]


RIG, ORDER = None, None


def quat_mat(q):
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


def mat_quat(m):
    import clip as C
    return np.array([C.mat_quat(r) for r in m.reshape(-1, 3, 3)]).reshape(*m.shape[:-2], 4)


def r6_world(rot, pos):
    """rot [T,6,4], pos [T,6,3] (character space, JOINTS order) -> part world 4x4 {part: [T,4,4]} + pivot world 4x4"""
    global RIG, ORDER
    if RIG is None:
        RIG, ORDER = _rig()
    T = len(rot)
    world = {"HumanoidRootPart": np.broadcast_to(np.eye(4), (T, 4, 4))}
    pivots = {}
    for part in ORDER:
        c0, c1, parent = RIG[part]
        k = JOINTS.index(part)
        c0r = c0[:3, :3]
        T4 = np.zeros((T, 4, 4))
        T4[:, :3, :3] = c0r.T @ quat_mat(rot[:, k]) @ c0r
        T4[:, :3, 3] = (c0r.T @ pos[:, k, :, None])[..., 0]
        T4[:, 3, 3] = 1
        pv = world[parent] @ c0 @ T4
        pivots[part] = pv
        world[part] = pv @ np.linalg.inv(c1)
    return world, pivots


def joint_frames(rot, pos):
    """-> positions [T,11,3] (studs) + rotations [T,11,3,3] of the R6 'Kimodo skeleton' joints"""
    world, piv = r6_world(rot, pos)
    pt = lambda m, v: (m @ np.array([*v, 1.0]))[..., :3]  # noqa: E731
    P_ = [world["Torso"][:, :3, 3], piv["Head"][:, :3, 3], piv["Right Arm"][:, :3, 3], piv["Left Arm"][:, :3, 3],
          piv["Right Leg"][:, :3, 3], piv["Left Leg"][:, :3, 3], pt(world["Head"], (0, 0.5, 0)),
          pt(world["Right Arm"], (0, -1, 0)), pt(world["Left Arm"], (0, -1, 0)), pt(world["Right Leg"], (0, -1, 0)), pt(world["Left Leg"], (0, -1, 0))]
    src = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
    R_ = [world[s][:, :3, :3] for s in src]
    return np.stack(P_, 1), np.stack(R_, 1)


def heading_of(R_torso):
    """torso facing (-Z of the part) on the floor -> angle about +Y (0 = facing -Z)"""
    f = -R_torso[..., :, 2]
    return np.arctan2(-f[..., 0], -f[..., 2])


def yaw_mat(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


# ---------------------------------------------------------------- R6 motion rep (Kimodo layout)
def make_rep(stats=None):
    from kimodo.motion_rep.reps.base import MotionRepBase
    from kimodo.motion_rep.stats import Stats

    class Skel:
        nbjoints = N_J
        root_idx = 0

    class R6Rep(MotionRepBase):
        def __init__(self):
            self.size_dict = {"smooth_root_pos": torch.Size([3]), "global_root_heading": torch.Size([2]),
                              "local_joints_positions": torch.Size([N_J, 3]), "global_rot_data": torch.Size([N_J, 6]),
                              "velocities": torch.Size([N_J, 3]), "foot_contacts": torch.Size([2])}
            self.last_root_feature = "global_root_heading"
            self.local_root_size_dict = {"local_root_rot_vel": torch.Size([1]), "local_root_vel": torch.Size([2]),
                                         "global_root_y": torch.Size([1])}
            super().__init__(Skel(), FPS, None)

        def set_stats(self, mean, std, lmean, lstd):
            g = self.global_root_dim
            self.global_root_stats = Stats(load=False)
            self.global_root_stats.register_from_tensors(torch.tensor(mean[:g]), torch.tensor(std[:g]))
            self.body_stats = Stats(load=False)
            self.body_stats.register_from_tensors(torch.tensor(mean[g:]), torch.tensor(std[g:]))
            self.local_root_stats = Stats(load=False)
            self.local_root_stats.register_from_tensors(torch.tensor(lmean), torch.tensor(lstd))
            self.stats = Stats(load=False)
            self.stats.register_from_tensors(torch.tensor(mean), torch.tensor(std))

        def to(self, dev):
            for s in (self.global_root_stats, self.body_stats, self.local_root_stats, self.stats):
                s.to(dev)
            return self

    rep = R6Rep()
    if stats is not None:
        rep.set_stats(*stats)
    return rep


def features(rot60, pos60, root60=None):
    """an R6 clip at 60 fps -> [T30, 139] features (canonicalised: frame 0 faces -Z, root xz at 0)"""
    from kimodo.geometry import matrix_to_cont6d
    from kimodo.motion_rep.smooth_root import get_smooth_root_pos
    rot, pos = rot60[::2], pos60[::2]
    Pj, Rj = joint_frames(rot, pos)
    if root60 is not None:
        Pj = Pj + root60[::2, None, :]
    Pj = Pj * SCALE
    # canonicalise: turn so the first frame faces -Z, move so the first torso is at x = z = 0
    a0 = heading_of(Rj[0, 0])
    Ry = yaw_mat(-a0)
    Pj = (Pj - np.array([Pj[0, 0, 0], 0.0, Pj[0, 0, 2]])) @ Ry.T
    Rj = np.einsum("ab,tjbc->tjac", Ry, Rj)
    root = torch.tensor(Pj[None, :, 0], dtype=torch.float32)
    try:
        smooth = get_smooth_root_pos(root)[0].numpy()
    except RuntimeError:                                   # Kimodo's spline solve is singular on some short clips
        r = Pj[:, 0]
        k = max(1, min(15, len(r) // 2 * 2 - 1))
        pad = np.pad(r, ((k // 2, k // 2), (0, 0)), mode="edge")
        smooth = np.stack([np.convolve(pad[:, a], np.ones(k) / k, "valid") for a in range(3)], 1)
        smooth[:, 1] = r[:, 1]
    head = heading_of(Rj[:, 0])
    local = Pj.copy()
    local[..., 0] -= smooth[:, None, 0]
    local[..., 2] -= smooth[:, None, 2]
    rot6 = matrix_to_cont6d(torch.tensor(Rj, dtype=torch.float32)).numpy()
    vel = np.gradient(Pj, axis=0) * FPS if len(Pj) > 1 else np.zeros_like(Pj)
    feet = Pj[:, FEET]
    sp = np.linalg.norm(vel[:, FEET], axis=-1)
    floor = -3.0 * SCALE
    contact = ((feet[..., 1] < floor + 0.06) & (sp < 0.6)).astype(np.float32)
    f = np.concatenate([smooth, np.stack([np.cos(head), np.sin(head)], -1), local.reshape(len(Pj), -1),
                        rot6.reshape(len(Pj), -1), vel.reshape(len(Pj), -1), contact], 1)
    return f.astype(np.float32)


def decode(feat, name="kimodo_r6"):
    """[T, 139] unnormalised features -> an R6 clip (60 fps, slerp-upsampled from 30) with a root track"""
    import clip as C
    from kimodo.geometry import cont6d_to_matrix
    import warp as W
    global RIG, ORDER
    if RIG is None:
        RIG, ORDER = _rig()
    T = len(feat)
    smooth = feat[:, 0:3]
    head = np.arctan2(feat[:, 4], feat[:, 3])
    local = feat[:, 5:5 + 33].reshape(T, N_J, 3)
    R = cont6d_to_matrix(torch.tensor(feat[:, 38:38 + 66].reshape(T, N_J, 6))).numpy()
    Pw = local.copy()
    Pw[..., 0] += smooth[:, None, 0]
    Pw[..., 2] += smooth[:, None, 2]
    Pw = Pw / SCALE                                        # world studs
    root, frames = [], {j: [] for j in JOINTS}
    for t in range(T):
        Ry = yaw_mat(head[t])
        trav = np.array([smooth[t, 0] / SCALE, 0.0, smooth[t, 2] / SCALE])
        root.append(list(C.mat_quat(Ry)) + list(map(float, trav)))
        Rt = Ry.T @ R[t, 0]                                # the torso in the character frame
        tp = Ry.T @ (Pw[t, 0] - trav)
        frames["Torso"].append(list(C.mat_quat(Rt)) + list(map(float, tp)))
        for k, part in ((1, "Head"), (2, "Right Arm"), (3, "Left Arm"), (4, "Right Leg"), (5, "Left Leg")):
            c0 = RIG[part][0]
            q = Rt.T @ (Ry.T @ R[t, k])                    # the part's turn in the torso (C0r = C1r)
            piv_c = Ry.T @ (Pw[t, k] - trav)               # the pivot, character frame
            slide = Rt.T @ (piv_c - tp) - c0[:3, 3]        # how far the pivot left its rest place, torso frame
            if part == "Head":
                slide = np.zeros(3)
            frames[part].append(list(C.mat_quat(q)) + list(map(float, slide)))
    clip = {"schema": 1, "name": name, "rig": "R6", "fps": FPS, "loop": False, "priority": "Action",
            "times": [round(i / FPS, 6) for i in range(T)], "events": [], "root": root,
            "joints": {j: {"frames": frames[j]} for j in JOINTS}, "source": {"kind": "kimodo_r6"}}
    c60 = W.to60(clip)
    R0 = np.array(root)
    c60["root"] = [list(R0[min(T - 1, int(round(i / 2)))]) for i in range(len(c60["times"]))]
    return c60


# ---------------------------------------------------------------- data
def build_data():
    texts = json.load(open(os.path.join(OUT, "texts.json"), encoding="utf-8"))
    z = np.load(os.path.join(DATA, "clips.npz"))
    za = np.load(os.path.join(DATA, "aug.npz"))
    labels = {json.loads(s)["id"]: json.loads(s) for s in open(os.path.join(DATA, "labels.jsonl"), encoding="utf-8")}
    bases = sorted({v["source"] for v in texts.values()})
    rng = np.random.default_rng(0)
    held = set(rng.choice(bases, HOLD, replace=False).tolist())
    feats, ids, srcs = [], [], []
    for cid, v in texts.items():
        src = z if labels[cid]["augmentation"] is None else za
        rot, pos = src[f"{cid}/rot"], src[f"{cid}/pos"]
        rp = src[f"{cid}/root_pos"] if f"{cid}/root_pos" in src.files else None
        if len(rot) < 8:
            continue
        f = features(rot, pos, rp)
        feats.append(f)
        ids.append(cid)
        srcs.append(v["source"])
    tr = [f for f, s in zip(feats, srcs) if s not in held]
    allf = np.concatenate(tr)
    mean, std = allf.mean(0), np.maximum(allf.std(0), 1e-3)
    rep = make_rep()
    lr_all = []
    for f in tr[::3]:
        lr_all.append(rep.global_root_to_local_root(torch.tensor(f[None, :, :5]), normalized=False, lengths=torch.tensor([len(f)]))[0].numpy())
    lr_all = np.concatenate(lr_all)
    lmean, lstd = lr_all.mean(0), np.maximum(lr_all.std(0), 1e-3)
    np.savez(os.path.join(OUT, "data.npz"), **{f"f{i}": f for i, f in enumerate(feats)})
    json.dump({"ids": ids, "sources": srcs, "held": sorted(held), "mean": mean.tolist(), "std": std.tolist(),
               "lmean": lmean.tolist(), "lstd": lstd.tolist()}, open(os.path.join(OUT, "data.json"), "w"))
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"{len(feats)} clips -> features ({sum(len(f) for f in feats)} frames at 30 fps, "
                      f"dim {feats[0].shape[1]}); {HOLD} base clips held out ({sum(1 for s in srcs if s in held)} with copies)",
                      "next_action": "python kit/anim/kimodo_r6.py train"}))


# ---------------------------------------------------------------- model
class LoRA(nn.Module):
    def __init__(self, out_f, in_f, r, alpha):
        super().__init__()
        self.A = nn.Parameter(torch.randn(r, in_f) / math.sqrt(in_f))
        self.B = nn.Parameter(torch.zeros(out_f, r))
        self.s = alpha / r

    def forward(self, W):
        return W + (self.B @ self.A) * self.s


def build_model(rank=16, alpha=16, stats=None):
    from kimodo.model.twostage_denoiser import TwostageDenoiser
    from kimodo.model.loading import load_checkpoint_state_dict
    import glob
    rep = make_rep(stats)
    kw = dict(llm_shape=[1, 4096], use_text_mask=False, latent_dim=1024, ff_size=2048, num_layers=16, num_heads=8,
              activation="gelu", dropout=0.0, pe_dropout=0.0, norm_first=False, num_text_tokens_override=50,
              input_first_heading_angle=True)
    model = TwostageDenoiser(rep, "concat", None, **kw)
    ck = glob.glob(os.path.expanduser("~/.cache/huggingface/hub/models--nvidia--Kimodo-SOMA-RP-v1.1/snapshots/*/model.safetensors"))[0]
    sd = {k.replace("denoiser.backbone.", ""): v for k, v in load_checkpoint_state_dict(ck).items()}
    own = model.state_dict()
    keep = {k: v for k, v in sd.items() if k in own and own[k].shape == v.shape}
    fresh = sorted(k for k in own if k not in keep)
    model.load_state_dict(keep, strict=False)
    for p in model.parameters():
        p.requires_grad = False
    for stage in (model.root_model, model.body_model):
        for lin in (stage.input_linear, stage.output_linear):
            for p in lin.parameters():
                p.requires_grad = True
        if rank:
            for layer in stage.seqTransEncoder.layers:
                for mod, name in ((layer.self_attn, "in_proj_weight"), (layer.self_attn.out_proj, "weight"),
                                  (layer.linear1, "weight"), (layer.linear2, "weight")):
                    W = getattr(mod, name)
                    P.register_parametrization(mod, name, LoRA(W.shape[0], W.shape[1], rank, alpha))
    return model, rep, fresh


def lora_state(model):
    return {k: v for k, v in model.state_dict().items() if ".parametrizations." in k and (k.endswith(".A") or k.endswith(".B"))
            or "input_linear" in k or "output_linear" in k}


# ---------------------------------------------------------------- train
def train(steps=20000, rank=16, bs=32, lr=2e-4, sample_every=2500):
    from kimodo.model.diffusion import Diffusion
    meta = json.load(open(os.path.join(OUT, "data.json")))
    z = np.load(os.path.join(OUT, "data.npz"))
    feats = [z[f"f{i}"] for i in range(len(meta["ids"]))]
    stats = tuple(np.array(meta[k], np.float32) for k in ("mean", "std", "lmean", "lstd"))
    held = set(meta["held"])
    texts = json.load(open(os.path.join(OUT, "texts.json"), encoding="utf-8"))
    emb_keys = json.load(open(os.path.join(OUT, "text_emb.npz.keys.json"), encoding="utf-8"))
    ez = np.load(os.path.join(OUT, "text_emb.npz"))
    emb = {k: ez[str(i)].astype(np.float32) for i, k in enumerate(emb_keys)}
    items = [(f, [emb[t] for t in texts[cid]["texts"] if t in emb]) for f, cid, s in zip(feats, meta["ids"], meta["sources"]) if s not in held]
    items = [it for it in items if it[1]]
    test = [(f, [emb[t] for t in texts[cid]["texts"] if t in emb]) for f, cid, s in zip(feats, meta["ids"], meta["sources"])
            if s in held and "|" not in cid]
    test = [it for it in test if it[1]][:64]
    model, rep, fresh = build_model(rank, stats=stats)
    model.to(DEV)
    rep.to(DEV)
    mean, std = torch.tensor(stats[0], device=DEV), torch.tensor(stats[1], device=DEV)
    diff = Diffusion(1000).to(DEV)
    groups = [{"params": [p for n, p in model.named_parameters() if p.requires_grad and ("input_linear" in n or "output_linear" in n)], "lr": lr * 2.5},
              {"params": [p for n, p in model.named_parameters() if p.requires_grad and "parametrizations" in n], "lr": lr}]
    opt = torch.optim.AdamW(groups, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, [lr * 2.5, lr], total_steps=steps, pct_start=0.03)
    n_tr = sum(p.numel() for g in groups for p in g["params"])
    print(json.dumps({"trainable_params": n_tr, "fresh_layers": fresh, "train_items": len(items), "test_items": len(test)}), flush=True)
    rng = np.random.default_rng(0)
    log, t0 = [], time.time()

    def batch(pool, n):
        idx = rng.integers(0, len(pool), n)
        L = [min(len(pool[i][0]), MAXF) for i in idx]
        Tm = max(L)
        X = np.zeros((n, Tm, pool[0][0].shape[1]), np.float32)
        M = np.zeros((n, Tm), bool)
        E = np.zeros((n, 1, 4096), np.float32)
        for b, (i, l) in enumerate(zip(idx, L)):
            f = pool[i][0]
            s = int(rng.integers(0, len(f) - l + 1))
            X[b, :l] = f[s: s + l]
            M[b, :l] = True
            E[b, 0] = pool[i][1][int(rng.integers(0, len(pool[i][1])))]
        return torch.tensor(X, device=DEV), torch.tensor(M, device=DEV), torch.tensor(E, device=DEV)

    def loss_of(X, M, E, train_mode=True):
        x0 = (X - mean) / std
        x0 = x0 * M[..., None]
        t = torch.randint(0, 1000, (len(X),), device=DEV)
        xt = diff.q_sample(x0, t)
        if train_mode:
            drop = (torch.rand(len(X), 1, 1, device=DEV) < 0.1).float()
            E = E * (1 - drop)
        tmask = torch.ones(len(X), 1, dtype=torch.bool, device=DEV)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            pred = model(xt, M, E, tmask, t, first_heading_angle=torch.zeros(len(X), device=DEV))
        w = M[..., None].float()
        return (((pred.float() - x0) ** 2) * w).sum() / (w.sum() * x0.shape[-1])

    model.train()
    for step in range(1, steps + 1):
        X, M, E = batch(items, bs)
        loss = loss_of(X, M, E)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_([p for g in groups for p in g["params"]], 1.0)
        opt.step()
        sched.step()
        if step % 250 == 0 or step == 1:
            model.eval()
            with torch.no_grad():
                Xt, Mt, Et = batch(test, min(32, len(test)))
                tl = float(loss_of(Xt, Mt, Et, False))
            model.train()
            log.append({"step": step, "loss": round(float(loss), 5), "held_loss": round(tl, 5), "minutes": round((time.time() - t0) / 60, 2),
                        "gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2)})
            print(json.dumps(log[-1]), flush=True)
        if step % sample_every == 0 or step == steps:
            ck = {"lora": lora_state(model), "rank": rank, "stats": [s.tolist() for s in stats], "step": step, "log": log}
            torch.save(ck, os.path.join(OUT, f"kimodo_r6_r{rank}.pt"))                 # the latest
            torch.save(ck, os.path.join(OUT, f"kimodo_r6_r{rank}_step{step}.pt"))      # every checkpoint is kept
            # (the first run overwrote one file: steps 2,500-12,500 were lost - only their samples survived)
            try:
                model.eval()
                c = sample(model, rep, stats, "boxer throws a jab and cross", 3.0)
                import motion_fill as MF
                q = np.array([[f[:4] for f in c["joints"][j]["frames"]] for j in JOINTS]).transpose(1, 0, 2)
                print(json.dumps({"step": step, "sample": "boxer", "frames": len(q), "pops": MF.pops(q)}), flush=True)
                json.dump(c, open(os.path.join(OUT, f"sample_step{step}.clip.json"), "w"))
            except Exception as e:                         # a sample must never kill a long run
                print("sample failed:", repr(e)[:200], flush=True)
            model.train()


# ---------------------------------------------------------------- sample
def text_embed(prompt):
    keys = json.load(open(os.path.join(OUT, "text_emb.npz.keys.json"), encoding="utf-8"))
    if prompt in keys:
        return np.load(os.path.join(OUT, "text_emb.npz"))[str(keys.index(prompt))].astype(np.float32)
    from kimodo.model.llm2vec.llm2vec_wrapper import LLM2VecEncoder
    enc = LLM2VecEncoder("McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp", "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised",
                         "bfloat16", 4096, device="cpu")
    e, _ = enc([prompt])
    return e[0, 0].float().cpu().numpy()


@torch.no_grad()
def sample(model, rep, stats, prompt, seconds=3.0, steps=100, cfg=2.0, seed=0, name=None):
    from kimodo.model.diffusion import Diffusion, DDIMSampler
    T = int(round(seconds * FPS))
    g = torch.Generator(device=DEV).manual_seed(seed)
    mean, std = torch.tensor(stats[0], device=DEV), torch.tensor(stats[1], device=DEV)
    e = torch.tensor(text_embed(prompt), device=DEV)[None, None]
    diff = Diffusion(1000).to(DEV)
    sampler = DDIMSampler(diff)
    use_t, _ = diff.space_timesteps(steps)
    diff.calc_diffusion_vars(use_t)
    x = torch.randn((1, T, rep.motion_rep_dim), device=DEV, generator=g)
    M = torch.ones(1, T, dtype=torch.bool, device=DEV)
    tm = torch.ones(1, 1, dtype=torch.bool, device=DEV)
    h0 = torch.zeros(1, device=DEV)
    for i in reversed(range(steps)):
        t = torch.full((1,), i, device=DEV, dtype=torch.long)
        tb = torch.full((1,), int(use_t[i]), device=DEV, dtype=torch.long)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            pc = model(x, M, e, tm, tb, first_heading_angle=h0)
            pu = model(x, M, e * 0, tm, tb, first_heading_angle=h0)
        x0 = (pu + cfg * (pc - pu)).float()
        x = x0 if i == 0 else sampler(use_t, x, x0, t)
    feat = (x[0] * std + mean).cpu().numpy()
    return decode(feat, name or "kimodo_r6")


def load(rank=16, path=None):
    ck = torch.load(path or os.path.join(OUT, f"kimodo_r6_r{rank}.pt"), map_location="cpu", weights_only=True)
    stats = tuple(np.array(s, np.float32) for s in ck["stats"])
    model, rep, _ = build_model(ck["rank"], stats=stats)
    model.load_state_dict(ck["lora"], strict=False)
    model.to(DEV).eval()
    rep.to(DEV)
    return model, rep, stats


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "data":
        build_data()
    elif cmd == "train":
        train(int(sys.argv[2]) if len(sys.argv) > 2 else 20000, int(sys.argv[3]) if len(sys.argv) > 3 else 16)
    elif cmd == "sample":
        m, r, s = load()
        sec = float(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else 3.0
        c = sample(m, r, s, sys.argv[2], sec)
        out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(OUT, "sample.clip.json")
        json.dump(c, open(out, "w"))
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"sampled '{sys.argv[2]}' -> {out}", "next_action": "render it"}))
    else:
        print(__doc__)
