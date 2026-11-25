"""omni_run.py — a picture + a SHAPE CONTROL -> a mesh (GLB) with Hunyuan3D-Omni, on this PC, offline.

Hunyuan3D-Omni (Tencent, Sept 2025: Hunyuan3D 2.1's 3.3B shape model + a control encoder) makes the shape the picture
shows, held to a control: a point cloud, voxels or a bounding box. The kit's main use: STEER generation with a
code-built blockout (kit gen omni <name> --image <pic> --from-asset <asset>) — the blockout fixes proportions and
placement, the picture brings the detail. Its own environment: ~/.cache/roblox-kit/envs/hunyuan3d-omni (torch 2.10 +
CUDA 13; kit/gen/README.md). The kit calls it; by hand:

    <envs/hunyuan3d-omni>/Scripts/python.exe kit/gen/omni_run.py <cutout_rgba.png> <out.glb>
        (--blockout <npz> [--control point|voxel|bbox] | --points <file> | --voxels <file> | --bbox x,y,z)
        [--seed N] [--steps N] [--guidance F] [--octree N]

Controls are in ROBLOX SPACE (x right, y up, -Z front), any unit (a blockout: studs): --blockout is the npz
kit/gen/omni_blockout.py exports from a kit build; --points / --voxels take a .npz (points, or verts + faces), .ply,
.obj or .glb (a mesh is sampled on its surface); --bbox is the three side lengths.

The frame (measured on the repo's own demo: the picture's silhouette matches its cloud seen from +Z, IoU 0.80 vs
0.63 mirrored): Omni's object faces +Z (its camera), y up — Roblox's faces -Z. So a cloud goes in turned half a
turn about Y, centred, its longest side scaled to 2 x 0.98 (inference.py's normalize_mesh); the mesh comes back
through the exact inverse: the GLB is in the control's own frame, units and place (a blockout's: studs, where the
asset stands). `<out minus .glb>.json` records it all, plus the numbers for a.import_mesh and how well the result
agrees with the control (each axis's size; Chamfer distance).

What it guards:
- offline: every socket connection raises; Hugging Face runs offline. Weights: the verified local copies
  (~/.cache/roblox-kit/models/hunyuan3d-omni, sizes checked against pins.json — fetched with the Hub's sha256), the
  .bin files read with torch.load(weights_only=True, mmap=True) only.
- 12 GB: fp16, and each network on the GPU only while it runs (image + control encoder, then the 3.3B DiT — streamed
  from disk straight to the GPU in fp16 — then the shape decoder).
- dependencies: pytorch-lightning, diffusers and torchdiffeq are imported by the repo for one base class, one random
  helper and one fixed-step Euler loop — small exact stand-ins below, so none of them is installed; pymeshlab
  (GPL-3.0) is not used (floaters removed with trimesh); RMBG never loads (the picture comes cut out by BiRefNet).
"""

import hashlib
import json
import os
import socket
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CACHE = os.path.join(HOME, ".cache", "roblox-kit")
MODELS = os.environ.get("KIT_MODELS") or os.path.join(CACHE, "models")
WEIGHTS = os.path.join(MODELS, "hunyuan3d-omni")
SRC = os.environ.get("KIT_OMNI_SRC") or os.path.join(CACHE, "src", "Hunyuan3D-Omni")
DINO = os.environ.get("KIT_OMNI_DINO") or os.path.join(WEIGHTS, "dinov2-large")
COND = os.path.join(WEIGHTS, "cond_encoder", "pytorch_model.bin")

os.environ.update(
    HF_HUB_OFFLINE="1",
    TRANSFORMERS_OFFLINE="1",
    HF_HUB_DISABLE_TELEMETRY="1",
    PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True",
)


def _no_network(*_a, **_k):
    raise RuntimeError("kit gen runs offline: a network connection was attempted and blocked")


socket.socket.connect = _no_network
socket.socket.connect_ex = _no_network
socket.socket.sendto = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network

# Roblox (x right, y up, front -Z) -> Omni (front +Z): a half turn about Y. A proper rotation (no mirror: windings
# and handedness survive) and its own inverse.
OMNI_FROM_RBX = ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))
SPAN = 0.98  # a cloud's longest side fills [-0.98, 0.98] (inference.py: normalize_mesh(mesh, scale=0.98))
N_POINTS = 2048  # the point control's size (the repo's demo clouds: 2048 points)
N_VOXEL_SAMPLES = 16384  # surface samples for the voxel control (the encoder snaps them to its 16^3 grid)
N_MEASURE = 20000  # samples per surface when measuring agreement
NEEDS_GB = 7.5  # free GPU memory a run needs (the DiT is 6.1 GB in fp16, plus working memory)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def _arg(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------- geometry (numpy only)
def sample_surface(verts, faces, n, seed):
    """n points spread over a triangle mesh by area (seeded: the same blockout gives the same cloud)"""
    import numpy as np  # noqa: PLC0415

    v, f = np.asarray(verts, np.float64), np.asarray(faces, np.int64)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if not area.sum() > 0:
        raise ValueError("the mesh has no area to sample")
    rng = np.random.default_rng(seed)
    tri = rng.choice(len(f), size=n, p=area / area.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    return a[tri] * (1 - s)[:, None] + b[tri] * (s * (1 - r2))[:, None] + c[tri] * (s * r2)[:, None]


def load_surface(path):
    """a control file -> (verts, faces or None): .npz (verts + faces, or points), .ply / .obj / .glb (trimesh)"""
    import numpy as np  # noqa: PLC0415

    if path.lower().endswith(".npz"):
        z = np.load(path)
        if "verts" in z and "faces" in z:
            return z["verts"].astype(np.float64), z["faces"].astype(np.int64)
        key = "points" if "points" in z else z.files[0]
        return z[key][:, :3].astype(np.float64), None
    import trimesh  # noqa: PLC0415

    m = trimesh.load(path) if path.lower().endswith(".ply") else trimesh.load(path, force="mesh", process=False)
    if isinstance(m, trimesh.PointCloud) or not len(getattr(m, "faces", [])):
        return np.asarray(m.vertices, np.float64), None
    return np.asarray(m.vertices, np.float64), np.asarray(m.faces, np.int64)


def cloud(verts, faces, n, seed):
    """n control points: sampled on the surface, or (a bare cloud) drawn from its points"""
    import numpy as np  # noqa: PLC0415

    if faces is not None:
        return sample_surface(verts, faces, n, seed)
    rng = np.random.default_rng(seed)
    return verts[rng.choice(len(verts), size=n, replace=len(verts) < n)]


def normaliser(pts):
    """-> (centre, k): the cloud's box centred on the origin, its longest side 2 x SPAN"""
    lo, hi = pts.min(0), pts.max(0)
    return (lo + hi) / 2, 2 * SPAN / max(float((hi - lo).max()), 1e-9)


def to_omni(pts, centre, k):
    import numpy as np  # noqa: PLC0415

    return ((np.asarray(pts, np.float64) - centre) * k) @ np.array(OMNI_FROM_RBX).T


def to_asset(pts, centre, k):
    """the exact inverse of to_omni"""
    import numpy as np  # noqa: PLC0415

    return (np.asarray(pts, np.float64) @ np.array(OMNI_FROM_RBX)) / k + centre


def chamfer(a, b):
    """symmetric mean nearest-neighbour distance between two point sets"""
    from scipy.spatial import cKDTree  # noqa: PLC0415

    return float((cKDTree(b).query(a)[0].mean() + cKDTree(a).query(b)[0].mean()) / 2)


def agreement(gen, ref):
    """two point sets (the result and the control's surface, same frame) -> how well they agree: each axis's size
    ratio, Chamfer in place (/ the control's longest side) and after normalising each to its own box"""
    import numpy as np  # noqa: PLC0415

    ge, rext = np.ptp(gen, 0), np.ptp(ref, 0)
    long = float(rext.max())

    def unit(p):
        lo, hi = p.min(0), p.max(0)
        return (p - (lo + hi) / 2) / max(float((hi - lo).max()), 1e-9)

    shift = (gen.min(0) + gen.max(0)) / 2 - (ref.min(0) + ref.max(0)) / 2
    return {
        "size_ratio_xyz": [round(float(g / max(r, 1e-9)), 3) for g, r in zip(ge, rext)],
        "chamfer_placed": round(chamfer(gen, ref) / long, 4),
        "chamfer_normalised": round(chamfer(unit(gen), unit(ref)), 4),
        "centre_offset": round(float(np.linalg.norm(shift)) / long, 4),
    }


def clean(mesh):
    """the repo's FloaterRemover + DegenerateFaceRemover, on trimesh (pymeshlab is GPL-3.0): pieces under 0.5% of
    the faces go (meshlab's nbfaceratio=0.005), degenerate faces and unused vertices go"""
    import trimesh  # noqa: PLC0415

    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        mesh = trimesh.util.concatenate([p for p in parts if len(p.faces) >= 0.005 * len(mesh.faces)])
    return mesh


# ---------------------------------------------------------------------------------- the repo's imports, satisfied
def install_stubs():
    """exact stand-ins for the little the repo takes from three libraries (none of them is installed):
    pytorch_lightning (the shape decoder's base class), diffusers (randn_tensor for the starting noise; FeedForward,
    the MoE experts' MLP — same parameter names, so the DiT's weights load into it with nothing missing) and
    torchdiffeq's odeint (the repo samples with fixed-grid Euler: y += dt * f(t, y) at each grid time, t cast to y's
    dtype like torchdiffeq's _PerturbFunc)"""
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415

    class LightningModule(nn.Module):
        _trainer = None

        def save_hyperparameters(self, *_a, **_k):
            pass

    pl = types.ModuleType("pytorch_lightning")
    pl.LightningModule = LightningModule
    utl = types.ModuleType("pytorch_lightning.utilities")
    utl.rank_zero_info = lambda *_a, **_k: None
    utl.rank_zero_only = lambda fn: fn
    pl.utilities = utl

    def randn_tensor(shape, generator=None, device=None, dtype=None, layout=None):
        if isinstance(generator, list):
            raise NotImplementedError("kit omni: one generator")
        where = generator.device if generator is not None else device
        return torch.randn(shape, generator=generator, device=where, dtype=dtype,
                           layout=layout or torch.strided).to(device)

    class GELU(nn.Module):  # diffusers 0.41 models/activations.py GELU: same layout (proj), same maths
        def __init__(self, dim_in, dim_out, approximate="none", bias=True):
            super().__init__()
            self.proj = nn.Linear(dim_in, dim_out, bias=bias)
            self.approximate = approximate

        def forward(self, x):
            return nn.functional.gelu(self.proj(x), approximate=self.approximate)

    class FeedForward(nn.Module):  # diffusers 0.41 models/attention.py FeedForward, the GELU kinds the MoE uses
        def __init__(self, dim, dim_out=None, mult=4, dropout=0.0, activation_fn="geglu", final_dropout=False,
                     inner_dim=None, bias=True):
            super().__init__()
            inner_dim = inner_dim if inner_dim is not None else int(dim * mult)
            if activation_fn not in ("gelu", "gelu-approximate"):
                raise NotImplementedError(f"kit omni: FeedForward({activation_fn})")
            act = GELU(dim, inner_dim, approximate="tanh" if activation_fn == "gelu-approximate" else "none",
                       bias=bias)
            self.net = nn.ModuleList([act, nn.Dropout(dropout), nn.Linear(inner_dim, dim_out or dim, bias=bias)])
            if final_dropout:
                self.net.append(nn.Dropout(dropout))

        def forward(self, hidden_states, *_a, **_k):
            for module in self.net:
                hidden_states = module(hidden_states)
            return hidden_states

    names = ("diffusers", "diffusers.utils", "diffusers.utils.torch_utils", "diffusers.models",
             "diffusers.models.attention")
    dif, dif_u, dif_t, dif_m, dif_a = (types.ModuleType(n) for n in names)
    dif_t.randn_tensor = randn_tensor
    dif_a.FeedForward = FeedForward
    dif.utils, dif_u.torch_utils, dif.models, dif_m.attention = dif_u, dif_t, dif_m, dif_a

    def odeint(func, y0, t, method="euler", **_k):
        if method != "euler":
            raise NotImplementedError(f"kit omni: only the Euler sampler (asked for {method})")
        ys, y = [y0], y0
        for t0, t1 in zip(t[:-1], t[1:]):
            y = y + (t1 - t0) * func(t0.to(y.dtype), y)
            ys.append(y)
        return torch.stack(ys)

    ode = types.ModuleType("torchdiffeq")
    ode.odeint = odeint
    sys.modules.update({"pytorch_lightning": pl, "pytorch_lightning.utilities": utl, "torchdiffeq": ode,
                        **dict(zip(names, (dif, dif_u, dif_t, dif_m, dif_a)))})


def install_stand_in():
    """--stand-in: no image encoder (the machinery check only — zeros where DINOv2's features go, so the shape is
    meaningless; it measures loading, memory and time)"""
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    from hy3dshape.models.conditioners import omni_encoder as oe  # noqa: PLC0415

    class ZeroImageEncoder(nn.Module):
        def __init__(self, image_size=518, **_k):
            super().__init__()
            self.anchor = nn.Parameter(torch.zeros(1), requires_grad=False)
            self.tokens = (image_size // 14) ** 2 + 1

        def setup_transform(self, image_size):
            self.tokens = (image_size // 14) ** 2 + 1

        def forward(self, image, **_k):
            z = torch.zeros(len(image), self.tokens, 1024, device=image.device, dtype=image.dtype)
            return {"dino": {"last_hidden_state": z}}

        def unconditional_embedding(self, batch_size):
            a = self.anchor
            return {"dino": {"last_hidden_state": torch.zeros(batch_size, self.tokens, 1024, device=a.device,
                                                              dtype=a.dtype)}}

    oe.DinoImageEncoder = ZeroImageEncoder


# ------------------------------------------------------------------------------------------------- weights + models
def check_weights(stand_in):
    """every pinned file is there at its pinned size, plus the two the control needs -> list of problems"""
    pins_path = os.path.join(WEIGHTS, "pins.json")
    if not os.path.isfile(pins_path):
        return [f"no {pins_path} — the Hunyuan3D-Omni weights were never fetched (python kit/gen/fetch.py --omni)"]
    with open(pins_path, encoding="utf-8") as fh:
        pins = json.load(fh)
    problems = []
    for key, pin in pins.items():
        rel = key.split("/")[2:]
        path = os.path.join(WEIGHTS, *rel) if key.startswith("tencent/") else os.path.join(DINO, *rel)
        if not os.path.isfile(path):
            problems.append(f"missing {path}")
        elif os.path.getsize(path) != pin["size"]:
            problems.append(f"{path} is {os.path.getsize(path)} bytes, pinned {pin['size']}")
    if not stand_in:
        later = "python kit/gen/fetch.py --omni-encoders, once the owner approves it"
        if not os.path.isfile(COND):
            problems.append(f"missing {COND} (the control encoder, 465 KB, same repo: {later})")
        if not os.path.isfile(os.path.join(DINO, "model.safetensors")):
            problems.append(f"missing {DINO} (the image encoder facebook/dinov2-large, Apache-2.0, 1.22 GB: {later})")
    return problems


def _cfg(name):
    from hy3dshape.models.utils.misc import get_config_from_file  # noqa: PLC0415

    return get_config_from_file(os.path.join(WEIGHTS, name, "config.json"))


def _state(name):
    import torch  # noqa: PLC0415

    return torch.load(os.path.join(WEIGHTS, name, "pytorch_model.bin"), map_location="cpu", mmap=True,
                      weights_only=True)


def load_cond_encoder(stand_in, dtype):
    """the image encoder (DINOv2-large, from its local copy) + the control encoder (its 465 KB of weights)"""
    import torch  # noqa: PLC0415
    from hy3dshape.models.utils.misc import instantiate_from_config  # noqa: PLC0415

    cfg = _cfg("cond_encoder")
    cfg.params.image_encoder.params.version = DINO.replace("\\", "/")
    enc = instantiate_from_config(cfg)
    if not stand_in:
        missing, unexpected = enc.load_state_dict(torch.load(COND, map_location="cpu", weights_only=True),
                                                  strict=False)
        stray = [k for k in missing if not k.startswith("image_encoder.")]
        if stray or unexpected:
            raise RuntimeError(f"control encoder weights do not fit: missing {stray[:3]}, unexpected {unexpected[:3]}")
    enc.disable_drop = True
    return enc.to(dtype=dtype).train(False)


def load_dit(dtype):
    """the 3.3B DiT built empty (meta device), its fp32 weights streamed from the memory-mapped file straight to the
    GPU in fp16 — never a 12 GB copy in RAM"""
    import torch  # noqa: PLC0415
    from hy3dshape.models.utils.misc import instantiate_from_config  # noqa: PLC0415

    with torch.device("meta"):
        dit = instantiate_from_config(_cfg("model"))
    state = {k: v.to(device="cuda", dtype=dtype) for k, v in _state("model").items()}
    missing, unexpected = dit.load_state_dict(state, strict=False, assign=True)
    unset = [n for n, t in list(dit.named_parameters()) + list(dit.named_buffers()) if t.is_meta]
    if missing or unexpected or unset:
        raise RuntimeError(f"DiT weights do not fit: missing {missing[:3]}, unexpected {unexpected[:3]}, "
                           f"unset {unset[:3]}")
    return dit.train(False)


def load_vae(dtype):
    from hy3dshape.models.utils.misc import instantiate_from_config  # noqa: PLC0415

    cfg = _cfg("vae")
    vae = instantiate_from_config(cfg)
    missing, unexpected = vae.load_state_dict(_state("vae"), strict=False)
    if missing or unexpected:
        raise RuntimeError(f"shape decoder weights do not fit: missing {missing[:3]}, unexpected {unexpected[:3]}")
    return vae.to(dtype=dtype).train(False), float(cfg["scale_factor"])


def _free(*mods):
    import gc  # noqa: PLC0415

    import torch  # noqa: PLC0415

    for m in mods:
        m.to("meta")
    gc.collect()
    torch.cuda.empty_cache()


# -------------------------------------------------------------------------------------------------------- the run
def parse_control(argv, seed):
    """-> dict: kind, the encoder's input (Omni frame), the reference surface for measuring, the way back"""
    import numpy as np  # noqa: PLC0415

    if "--bbox" in argv:
        size = np.array([float(x) for x in (_arg(argv, "--bbox") or "").replace("x", ",").split(",")], np.float64)
        if size.shape != (3,) or (size <= 0).any():
            raise ValueError("--bbox takes three positive side lengths: x,y,z")
        return {"kind": "bbox", "size": size, "omni": (size / size.max())[None, :]}
    for flag, kind in (("--blockout", None), ("--points", "point"), ("--voxels", "voxel")):
        path = _arg(argv, flag)
        if not path:
            continue
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{flag} {path}: no such file")
        kind = kind or _arg(argv, "--control") or "point"
        if kind not in ("point", "voxel", "bbox"):
            raise ValueError(f"--control {kind}: point, voxel or bbox")
        verts, faces = load_surface(path)
        ref = cloud(verts, faces, N_MEASURE, seed + 1)
        centre, k = normaliser(verts if faces is None else ref)
        out = {"kind": kind, "source": path, "centre": centre, "k": k, "ref": ref}
        if kind == "bbox":
            size = np.ptp(ref, 0)
            out.update(size=size, omni=(size / size.max())[None, :])
        else:
            out["omni"] = to_omni(cloud(verts, faces, N_POINTS if kind == "point" else N_VOXEL_SAMPLES, seed),
                                  centre, k)
        return out
    raise ValueError("no control: --blockout <npz>, --points <file>, --voxels <file> or --bbox x,y,z")


def back_to_asset(verts, ctrl):
    """the generated mesh (Omni frame) -> the control's frame, units and place"""
    import numpy as np  # noqa: PLC0415

    if ctrl["kind"] != "bbox":
        return to_asset(verts, ctrl["centre"], ctrl["k"])
    v = np.asarray(verts, np.float64) @ np.array(OMNI_FROM_RBX)
    v = v * (float(ctrl["size"].max()) / max(float(np.ptp(v, 0).max()), 1e-9))  # its longest side to the box's
    if "ref" in ctrl:  # a box measured from a blockout: on the blockout's centre
        return v + (ctrl["ref"].min(0) + ctrl["ref"].max(0)) / 2 - (v.min(0) + v.max(0)) / 2
    return v - [(v[:, 0].min() + v[:, 0].max()) / 2, v[:, 1].min(), (v[:, 2].min() + v[:, 2].max()) / 2]  # on y=0


def main(argv):
    if len(argv) < 2 or not os.path.isfile(argv[0]):
        return emit("fail", "omni: usage: omni_run.py <cutout_rgba.png> <out.glb> (--blockout <npz> | --points <f> "
                            "| --voxels <f> | --bbox x,y,z) [--seed N]",
                    "lune run kit gen omni <name> --image <picture> --from-asset <asset>")
    src, out = argv[0], argv[1]
    seed, steps = _opt(argv, "--seed", 1234), _opt(argv, "--steps", 50)
    guidance, octree = _opt(argv, "--guidance", 4.5), _opt(argv, "--octree", 384)
    stand_in = "--stand-in" in argv
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    img = Image.open(src)
    if img.mode != "RGBA" or np.all(np.asarray(img)[:, :, 3] == 255):
        return emit("fail", f"omni: {src} has no cut-out (no transparent background)",
                    f"lune run kit vision cutout {src} --rgba, then pass its _rgba.png")
    try:
        ctrl = parse_control(argv, seed)
    except (ValueError, FileNotFoundError) as e:
        return emit("fail", f"omni: {e}", "lune run kit gen omni <name> --image <picture> --from-asset <asset>")
    problems = check_weights(stand_in)
    if problems:
        return emit("fail", f"omni: weights not ready — {problems[0]}",
                    "fetch them: kit/gen/README.md (Hunyuan3D-Omni)", problems=problems)
    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        return emit("fail", "omni: no CUDA GPU visible", "check the NVIDIA driver (nvidia-smi)")
    free = torch.cuda.mem_get_info()[0] / 2**30
    if free < NEEDS_GB:
        return emit("fail", f"omni: the GPU is busy — {free:.1f} GB free, a run needs {NEEDS_GB} GB",
                    "wait for the other GPU job to finish (nvidia-smi), then run the same command again")
    sys.path.insert(0, SRC)
    install_stubs()
    if stand_in:
        install_stand_in()
    from hy3dshape.models.utils.misc import instantiate_from_config  # noqa: PLC0415
    from hy3dshape.pipelines import Hunyuan3DOmniSiTFlowMatchingPipeline as Pipe  # noqa: PLC0415
    from hy3dshape.pipelines.utils import export_to_trimesh  # noqa: PLC0415

    dtype, dev = torch.float16, torch.device("cuda")
    t0 = time.time()
    torch.cuda.reset_peak_memory_stats()
    root = _cfg("")  # the pipeline's own settings (box_v, num_chunks)
    sched = _cfg("scheduler")
    scheduler = instantiate_from_config(sched.sampler, transport=instantiate_from_config(sched.transport))
    vae, scale_factor = load_vae(dtype)  # waits on the CPU until the decode
    enc = load_cond_encoder(stand_in, dtype).to(dev)
    pipe = Pipe(vae=vae, model=None, scheduler=scheduler, cond_encoder=enc,
                image_processor=instantiate_from_config(_cfg("image_processor")), scale_factor=scale_factor,
                device="cuda", dtype=dtype)
    t_load = time.time()
    # 1. the picture + the control -> the condition tokens (the pipeline's own encode_cond)
    with torch.no_grad():
        image, _mask = pipe.prepare_image(img, None)
        signal = torch.as_tensor(ctrl["omni"], dtype=dtype, device=dev)[None]
        pick = {k: (signal if ctrl["kind"] == k else None) for k in ("bbox", "point", "voxel")}
        cond, _ = pipe.encode_cond(image, None, None, pick["bbox"], pick["point"], pick["voxel"], guidance >= 0)
    _free(enc)
    pipe.cond_encoder = None
    t_enc = time.time()
    # 2. the DiT: flow matching, classifier-free guidance on the picture (the pipeline's __call__, step by step)
    dit = load_dit(dtype)
    t_dit = time.time()
    with torch.no_grad():
        latents = pipe.prepare_latents(None, 1, dtype, dev, torch.Generator("cuda").manual_seed(seed))
        sample = scheduler.sample_ode(num_steps=steps, sampling_method="euler")

        def denoise(x, ts, contexts):
            pred = dit(x, ts, contexts, guidance=None)
            if guidance >= 0:
                c, u = pred.chunk(2)
                pred = u + guidance * (c - u)
                return torch.cat([pred, pred], dim=0)
            return pred

        if guidance >= 0:
            latents = torch.cat([latents, latents])
        latents = sample(latents, denoise, contexts=cond)[-1]
        latents = latents.chunk(2)[0] if guidance >= 0 else latents
    _free(dit)
    t_den = time.time()
    # 3. the shape decoder: the surface of the latent field (marching cubes at --octree)
    vae.to(dev)
    with torch.no_grad():
        box = float(root.params.box_v)
        shapes = vae.decode(latents / scale_factor, octree_depth=8, bounds=[-box] * 3 + [box] * 3, mc_level=0.0,
                            num_chunks=int(root.params.num_chunks), octree_resolution=octree, mc_mode="mc")
    peak = torch.cuda.max_memory_allocated() / 2**30
    _free(vae)
    if not shapes or shapes[0] is None:
        return emit("fail", "omni: the decoder found no surface (the latent field is empty)",
                    "try another --seed; check the picture is a clean cut-out of ONE object",
                    seconds=round(time.time() - t0, 1), peak_vram_gb=round(peak, 2))
    mesh = clean(export_to_trimesh(shapes)[0])
    t_dec = time.time()
    # 4. back to the control's frame, units and place
    v = back_to_asset(mesh.vertices, ctrl)
    mesh.vertices = v
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    mesh.export(out)
    lo, hi = v.min(0), v.max(0)
    gen = np.asarray(mesh.sample(N_MEASURE, seed=seed), np.float64)
    if "ref" in ctrl:
        agree = agreement(gen, ctrl["ref"])
    else:
        agree = {"size_ratio_xyz": [round(float(g / s), 3) for g, s in zip(np.ptp(v, 0), ctrl["size"])]}
    with open(os.path.join(WEIGHTS, "pins.json"), encoding="utf-8") as fh:
        pins = json.load(fh)
    rel = os.path.relpath(out).replace("\\", "/")
    cx, cz, h = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2, hi[1] - lo[1]
    record = {
        "engine": "hunyuan3d-omni", "model": "tencent/Hunyuan3D-Omni @ 70e803b",
        # the owner's rule (2026-10-07): the licence's s.5(c) forbids displaying outputs outside its territory (the
        # EU, UK, South Korea excluded) — a public Roblox game would — so its meshes live in PRIVATE assets only
        "private_only": True,
        "licence": "Tencent Hunyuan 3D Omni Community License (owner accepted 2026-10-06; no military use; "
                   ">1M MAU needs Tencent's licence; outputs never train other models)",
        "image_encoder": "STAND-IN (zeros: machinery check only)" if stand_in else "facebook/dinov2-large",
        "control": ctrl["kind"], "control_source": ctrl.get("source"), "seed": seed, "steps": steps,
        "guidance": guidance, "octree": octree, "faces": int(len(mesh.faces)),
        "input": os.path.basename(src), "input_sha256": sha256(src),
        "weights": {k.split("/", 2)[2]: p["sha256"][:16] for k, p in pins.items()
                    if k.endswith((".bin", ".safetensors"))},
        "frame": "Roblox (x right, y up, -Z front) in the control's units; Omni's = a half turn about Y, undone",
        # Omni makes the SHAPE only (no textures): mat= is a kit material the build script defines ("body": rename)
        "import": {"height": round(float(h), 4),
                   "pos": [round(float(cx), 4), round(float(lo[1]), 4), round(float(cz), 4)],
                   "line": f'a.import_mesh("Body", "{rel}", height={h:.3f}, pos=({cx:.3f}, {lo[1]:.3f}, '
                           f'{cz:.3f}), mat="body")'},
        "agreement": agree,
        "seconds": round(time.time() - t0, 1), "seconds_load": round(t_load - t0 + t_dit - t_enc, 1),
        "seconds_encode": round(t_enc - t_load, 1), "seconds_denoise": round(t_den - t_dit, 1),
        "seconds_decode": round(t_dec - t_den, 1), "peak_vram_gb": round(peak, 2),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    ratios = agree["size_ratio_xyz"]
    off = [abs(r - 1) for r in ratios]
    if max(off) > 0.15:
        nxt = (f"improve: the result is {max(off):.0%} off the control on {'xyz'[off.index(max(off))]} — try "
               "another --seed, or --control voxel")
    else:
        nxt = f"import it in a MASTER build script: {record['import']['line']}"
    return emit("pass", f"omni: {out} in {record['seconds']} s (peak {record['peak_vram_gb']} GB on the GPU; "
                        f"{record['faces']} faces; size vs control x/y/z {ratios})", nxt, out=out, record=record)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
