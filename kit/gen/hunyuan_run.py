"""hunyuan_run.py — Tencent Hunyuan3D-2 on this PC: a shape from 4 views (2mv turbo) and a texture for a mesh (Paint).

Runs in its own environment, ~/.cache/roblox-kit/envs/hunyuan3d2 (torch 2.10 + CUDA 13, Hunyuan3D-2's code at a
pinned commit in ~/.cache/roblox-kit/src/Hunyuan3D-2, its rasterizer compiled on this PC — kit/gen/README.md). The
kit calls it (`lune run kit gen mv-shape | paint`); by hand:

    <envs/hunyuan3d2>/Scripts/python.exe kit/gen/hunyuan_run.py shape <out.glb> --front <rgba> [--left <rgba>]
        [--back <rgba>] [--right <rgba>] [--seed N] [--steps 5] [--octree 380] [--guidance 5]
    <envs/hunyuan3d2>/Scripts/python.exe kit/gen/hunyuan_run.py paint <mesh.glb> <picture_rgba.png> <out.glb>
        [--seed N] [--texture 2048] [--sheet <views.png>]
    python kit/gen/hunyuan_run.py fetch     (the weights the owner approved, each checked against the Hub's sha256)

Frames. Every GLB here is in ROBLOX space: x right, y up, the FRONT faces -Z (a GLB's coordinates are Roblox's, as
a.import_mesh reads them). Hunyuan works in the glTF habit (front faces +Z, its x = the object's left); the runner
turns half a turn about y on the way in and out. The 4 views are pictures OF the object, level, from:
    front = the camera in front of it (on Roblox -Z), looking at its front     (kit camfit yaw 0)
    left  = the camera on its LEFT side (Roblox -X), looking toward +X         (yaw +90)
    back  = the camera behind it (+Z)                                           (yaw 180)
    right = the camera on its RIGHT side (+X), looking toward -X               (yaw -90)
`paint` returns the input mesh, unchanged in place and frame, with a new UV layout and a base-colour texture.

What it guards:
- offline: every socket connection raises; Hugging Face runs offline; each weight file's size is checked against
  pins.json (written at fetch with the Hub's sha256). Any torch.load is forced to weights_only=True.
- licences: rembg (BRIA, non-commercial), pymeshlab (GPL), xatlas and pygltflib are never imported (placeholders
  stand in for modules that import them at the top but are never called); nvdiffrast is not used by Paint.
- 12 GB shared: shape moves one network at a time to the GPU (conditioner -> DiT -> VAE); paint loads Delight, frees
  it, then the multiview network, then frees it before baking. A run checks the GPU has room first.
Tencent Hunyuan 3D 2.0 Community License: not for use in the EU, UK or South Korea; no military use; >1M monthly
users needs Tencent's licence; outputs may not train other AI models (kit/gen/README.md). The owner's rule
(2026-10-07): Hunyuan outputs are PRIVATE EXPERIMENTS ONLY — a public game would display them outside the licence's
territory (s.5(c)) — so every record says "private_only": true and a.import_mesh refuses it in a public asset.
"""

import gc
import hashlib
import importlib.util
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
WEIGHTS = os.path.join(MODELS, "hunyuan3d-2")
SRC = os.environ.get("KIT_HUNYUAN_SRC") or os.path.join(CACHE, "src", "Hunyuan3D-2")
LICENCE = "Tencent Hunyuan 3D 2.0 Community License"

_TOKENIZER = [f"tokenizer/{n}" for n in ("merges.txt", "special_tokens_map.json", "tokenizer_config.json",
                                         "vocab.json")]
_PAINT = "hunyuan3d-paint-v2-0-turbo"
_DELIGHT = "hunyuan3d-delight-v2-0"
_SHAPE = "hunyuan3d-dit-v2-mv-turbo"
_SHAPE_FULL = "hunyuan3d-dit-v2-mv"   # (the base model the turbo was step-distilled from: 50 steps; VETLOG 2026-10-09)
SHAPE_DIR = os.path.join(WEIGHTS, "Hunyuan3D-2mv", _SHAPE)
PAINT_DIR = os.path.join(WEIGHTS, "Hunyuan3D-2", _PAINT)
DELIGHT_DIR = os.path.join(WEIGHTS, "Hunyuan3D-2", _DELIGHT)
# the exact files the owner approved (2026-10-06), at pinned commits: no unet .bin (7.3 GB), no .ckpt duplicates
FILES = {
    ("tencent/Hunyuan3D-2mv", "3a761b539b29fe4ff64714813aa9560fd66f5de0"): [
        f"{_SHAPE}/config.yaml", f"{_SHAPE}/model.fp16.safetensors",
        f"{_SHAPE_FULL}/config.yaml", f"{_SHAPE_FULL}/model.fp16.safetensors"],
    ("tencent/Hunyuan3D-2", "9cd649ba6913f7a852e3286bad86bfa9a2d83dcf"): [
        f"{_PAINT}/{n}" for n in ["model_index.json", "feature_extractor/preprocessor_config.json",
                                  "image_encoder/config.json", "image_encoder/model.safetensors",
                                  "image_encoder/preprocessor_config.json", "scheduler/scheduler_config.json",
                                  "text_encoder/config.json", "text_encoder/pytorch_model.bin", *_TOKENIZER,
                                  "unet/config.json", "unet/diffusion_pytorch_model.safetensors", "vae/config.json",
                                  "vae/diffusion_pytorch_model.bin"]
    ] + [
        f"{_DELIGHT}/{n}" for n in ["model_index.json", "feature_extractor/preprocessor_config.json",
                                    "scheduler/scheduler_config.json", "text_encoder/config.json",
                                    "text_encoder/model.safetensors", *_TOKENIZER, "unet/config.json",
                                    "unet/diffusion_pytorch_model.safetensors", "vae/config.json",
                                    "vae/diffusion_pytorch_model.safetensors"]
    ],
}
VIEWS = ("front", "left", "back", "right")
NEED_GB = {"shape": 3.5, "paint": 5.5}  # free GPU memory a run needs: measured peaks 2.46 / 4.26 GB + headroom


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ fetch (the only networked step)
def fetch():
    """download the approved files at their pinned commits; each LFS file must match the Hub's sha256 and size ->
    pins.json (the runner checks every pinned size before a run)"""
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import HfApi, hf_hub_download  # noqa: PLC0415

    pins_path = os.path.join(WEIGHTS, "pins.json")
    pins = json.load(open(pins_path, encoding="utf-8")) if os.path.isfile(pins_path) else {}
    api, bad = HfApi(), 0
    for (repo, rev), names in FILES.items():
        info = api.model_info(repo, revision=rev, files_metadata=True)
        meta = {s.rfilename: s for s in info.siblings}
        for name in names:
            s = meta[name]
            local = hf_hub_download(repo, name, revision=rev, local_dir=os.path.join(WEIGHTS, repo.split("/")[1]))
            size, digest = os.path.getsize(local), sha256(local)
            lfs_ok = s.lfs is None or (digest == s.lfs.sha256 and size == s.lfs.size)
            ok = (s.size is None or size == s.size) and lfs_ok
            bad += not ok
            pins[f"{repo}/{name}"] = {"commit": rev, "size": size, "sha256": digest}
            print(("OK  " if ok else "BAD ") + f"{repo}/{name} {size} bytes", flush=True)
            os.makedirs(WEIGHTS, exist_ok=True)
            with open(pins_path, "w", encoding="utf-8") as fh:
                json.dump(pins, fh, indent=1)
    return emit("pass" if not bad else "fail",
                f"hunyuan fetch: {'every file verified' if not bad else f'{bad} file(s) failed the check'} ({WEIGHTS})",
                "lune run kit gen mv-shape <name> --front ... (kit/gen/README.md)")


# ------------------------------------------------------------------ guards + shims
def _no_network(*_a, **_k):
    raise RuntimeError("kit gen runs offline: a network connection was attempted and blocked")


class _Placeholder(types.ModuleType):
    """a module Hunyuan3D-2 imports at the top of a file whose functions the kit never calls"""

    __path__ = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def never(*_a, **_k):
            raise RuntimeError(f"kit gen: {self.__name__}.{name} is not installed on purpose (kit/gen/README.md)")

        return never


def install_guards():
    """offline, weights-only loading, and the Hunyuan3D-2 packages without their demo/GPL imports"""
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      DIFFUSERS_OFFLINE="1")
    socket.socket.connect = _no_network
    socket.socket.connect_ex = _no_network
    socket.socket.sendto = _no_network
    socket.create_connection = _no_network
    socket.getaddrinfo = _no_network
    import torch  # noqa: PLC0415

    _load = torch.load

    def weights_only_load(*a, **k):
        k["weights_only"] = True
        return _load(*a, **k)

    torch.load = weights_only_load
    sys.path.insert(0, SRC)
    # the packages' __init__ files import everything (pymeshlab, xatlas, rembg ...): register the packages bare, so
    # only the modules the kit uses load
    for pkg in ("hy3dgen", "hy3dgen.shapegen", "hy3dgen.texgen"):
        mod = types.ModuleType(pkg)
        mod.__path__ = [os.path.join(SRC, *pkg.split("."))]
        sys.modules[pkg] = mod
    for name in ("pymeshlab", "xatlas", "pygltflib"):
        sys.modules.setdefault(name, _Placeholder(name))
    # the compiled rasterizer's python side, without its package __init__ (a GLB reader that needs pygltflib)
    spec = importlib.util.spec_from_file_location(
        "custom_rasterizer", os.path.join(SRC, "hy3dgen", "texgen", "custom_rasterizer", "custom_rasterizer",
                                          "render.py"))
    cr = importlib.util.module_from_spec(spec)
    sys.modules["custom_rasterizer"] = cr
    spec.loader.exec_module(cr)
    return torch


def check_weights(prefixes):
    """the pinned files under these folders are all there at their pinned sizes -> list of problems"""
    pins_path = os.path.join(WEIGHTS, "pins.json")
    if not os.path.isfile(pins_path):
        return [f"no {pins_path} — the Hunyuan3D-2 weights were never fetched"]
    with open(pins_path, encoding="utf-8") as fh:
        pins = json.load(fh)
    problems, seen = [], 0
    for key, pin in pins.items():
        repo, rel = key.split("/", 2)[1], key.split("/", 2)[2]
        if not rel.startswith(tuple(prefixes)):
            continue
        seen += 1
        path = os.path.join(WEIGHTS, repo, *rel.split("/"))
        if not os.path.isfile(path):
            problems.append(f"missing {path}")
        elif os.path.getsize(path) != pin["size"]:
            problems.append(f"{path} is {os.path.getsize(path)} bytes, pinned {pin['size']}")
    if not seen:
        problems.append(f"pins.json has no {prefixes[0]} files")
    return problems


def gpu_room(torch, mode):
    """None, or why the GPU cannot take this run now (it is shared: other programs may be using it)"""
    if not torch.cuda.is_available():
        return "no CUDA GPU visible (check the NVIDIA driver: nvidia-smi)"
    free, total = torch.cuda.mem_get_info()
    if free / 2**30 < NEED_GB[mode]:
        return (f"the GPU has {free / 2**30:.1f} GB free of {total / 2**30:.1f} GB; {mode} needs about "
                f"{NEED_GB[mode]} GB")
    return None


def rgba_cutout(path):
    """the picture as RGBA with a real transparent background, else None"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    img = Image.open(path)
    if img.mode != "RGBA":
        return None
    a = np.asarray(img)[:, :, 3]
    if np.all(a == 255) or not np.any(a > 127):
        return None
    return img


def to_roblox(v):
    """Hunyuan's frame (front +Z, x = the object's left) <-> Roblox's (front -Z, x = its right): half a turn about y
    (its own inverse)"""
    import numpy as np  # noqa: PLC0415

    v = np.array(v, dtype=np.float64, copy=True)
    v[:, 0] *= -1.0
    v[:, 2] *= -1.0
    return v


def write_record(out, record):
    """<output stem>.json beside the GLB (x.gen.glb -> x.gen.json, x.paint.glb -> x.paint.json): a.import_mesh reads
    it, and refuses a "private_only" mesh in a public asset (the owner's rule for Hunyuan outputs, 2026-10-07)"""
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)


UNUSED = ("text_encoder/pytorch_model.bin", "image_encoder/")  # paint turbo: fetched with its folder, never loaded


def _pins(prefix):
    """the weight files this run actually loaded -> their pinned sha256 (first 16)"""
    with open(os.path.join(WEIGHTS, "pins.json"), encoding="utf-8") as fh:
        pins = json.load(fh)
    return {k.split("/", 2)[2]: v["sha256"][:16] for k, v in pins.items()
            if prefix in k and k.endswith((".safetensors", ".bin"))
            and not (prefix == _PAINT and any(u in k for u in UNUSED))}


class no_init:
    """build a network without filling it with random numbers first (its weights are copied in right after; the
    networks are big: ~10 s and gigabytes of churn saved). Anything the checkpoint lacks is reported by
    load_streaming, never used silently."""

    NAMES = ("uniform_", "normal_", "trunc_normal_", "kaiming_uniform_", "kaiming_normal_", "xavier_uniform_",
             "xavier_normal_", "orthogonal_")

    def __init__(self, torch, dtype):
        self.torch, self.dtype, self.saved = torch, dtype, {}

    def __enter__(self):
        init = self.torch.nn.init
        for n in self.NAMES:
            self.saved[n] = getattr(init, n)
            setattr(init, n, lambda t, *a, **k: t)
        self.torch.set_default_dtype(self.dtype)

    def __exit__(self, *exc):
        for n, fn in self.saved.items():
            setattr(self.torch.nn.init, n, fn)
        self.torch.set_default_dtype(self.torch.float32)


def load_streaming(torch, module, f, prefix="", convert=None):
    """copy a safetensors checkpoint (an open safe_open) into a built module one tensor at a time — peak memory is
    the module plus one tensor, not two copies of it. convert(name) -> [(name in the module, half or None)] renames
    a checkpoint entry (half 0/1: that half of it along dim 0). -> (missing names, unexpected names)"""
    own = module.state_dict(keep_vars=True)
    targets = {}
    for key in f.keys():
        if key.startswith(prefix):
            for name, half in (convert(key[len(prefix):]) if convert else [(key[len(prefix):], None)]):
                targets[name] = (key, half)
    with torch.no_grad():
        for name, (key, half) in targets.items():
            if name in own:
                t = f.get_tensor(key)
                if half is not None:
                    t = t.chunk(2, dim=0)[half]
                if tuple(own[name].shape) != tuple(t.shape):
                    raise ValueError(f"{prefix}{name}: checkpoint {tuple(t.shape)} vs network {tuple(own[name].shape)}")
                own[name].data.copy_(t)
    return sorted(set(own) - set(targets)), sorted(set(targets) - set(own))


_DINOV2_TF5 = (("attention.attention.query", "attention.q_proj"), ("attention.attention.key", "attention.k_proj"),
               ("attention.attention.value", "attention.v_proj"), ("attention.output.dense", "attention.o_proj"),
               ("mlp.weights_out", "mlp.down_proj"))


def dinov2_tf5(name):
    """transformers 5 renamed DINOv2's layers and split its SwiGLU input projection in two (gate = the first half:
    the old forward was silu(x1) * x2). Its own conversion_mapping.py does exactly this on from_pretrained; Hunyuan
    loads a state dict directly, so the runner does it. Same weights, nothing computed differently."""
    for old, new in _DINOV2_TF5:
        if old in name:
            return [(name.replace(old, new), None)]
    if "mlp.weights_in." in name:
        return [(name.replace("mlp.weights_in.", "mlp.gate_proj."), 0),
                (name.replace("mlp.weights_in.", "mlp.up_proj."), 1)]
    return [(name, None)]


# ------------------------------------------------------------------ shape: 1-4 views -> mesh
def shape_pipeline(torch, shape_dir=SHAPE_DIR):
    """Hunyuan3DDiTFlowMatchingPipeline.from_single_file, network by network (the checkpoint holds the DiT, the
    shape VAE's decoder and the DINOv2-giant image encoder): built in half precision without random init, weights
    streamed in, every DiT / encoder weight present (strict), the VAE missing only its encoder (unused here)"""
    import yaml  # noqa: PLC0415
    from hy3dgen.shapegen.pipelines import Hunyuan3DDiTFlowMatchingPipeline, instantiate_from_config  # noqa: PLC0415
    from safetensors import safe_open  # noqa: PLC0415

    with open(os.path.join(shape_dir, "config.yaml"), encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    parts = {}
    with safe_open(os.path.join(shape_dir, "model.fp16.safetensors"), "pt", device="cpu") as f:
        for name in ("model", "vae", "conditioner"):
            with no_init(torch, torch.float16):
                net = instantiate_from_config(cfg[name])
            new_dino = name == "conditioner" and not any(".attention.attention.query" in k for k in net.state_dict())
            missing, unexpected = load_streaming(torch, net, f, prefix=name + ".",
                                                 convert=dinov2_tf5 if new_dino else None)
            # (the VAE's ENCODING half — point cloud -> latents — is not shipped and never runs here)
            stray = [m for m in missing if not (name == "vae" and m.startswith(("encoder.", "pre_kl.")))]
            if stray or unexpected:
                raise RuntimeError(f"hunyuan shape: the {name} checkpoint does not fit the code: missing {stray[:3]}, "
                                   f"unexpected {unexpected[:3]}")
            parts[name] = net.to(torch.float16).train(False).requires_grad_(False)
    return Hunyuan3DDiTFlowMatchingPipeline(
        vae=parts["vae"], model=parts["model"], conditioner=parts["conditioner"],
        scheduler=instantiate_from_config(cfg["scheduler"]), image_processor=instantiate_from_config(
            cfg["image_processor"]), device="cpu", dtype=torch.float16)


def offload_one_at_a_time(torch, modules):
    """each network moves to the GPU when it runs and the others leave it (what accelerate's model offload does,
    without accelerate): the shape stage's peak is its biggest network, not all three"""
    def hook_for(name):
        def pre(module, _args):
            if next(module.parameters()).device.type == "cuda":
                return
            for other, m in modules.items():
                if other != name and next(m.parameters()).device.type == "cuda":
                    m.to("cpu")
            torch.cuda.empty_cache()
            module.to("cuda")
        return pre

    for name, m in modules.items():
        m.register_forward_pre_hook(hook_for(name))


def clean_shape(mesh):
    """Hunyuan's own clean-up without pymeshlab: drop specks (connected pieces under 0.5% of the faces, its
    FloaterRemover's ratio), degenerate faces and unused vertices"""
    import numpy as np  # noqa: PLC0415
    import trimesh  # noqa: PLC0415

    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    labels = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(mesh.faces))
    counts = np.bincount(labels)
    small = counts < max(1, int(0.005 * len(mesh.faces)))
    dropped = int(small.sum())
    mesh.update_faces(~small[labels])
    mesh.remove_unreferenced_vertices()
    return mesh, dropped


def shape(argv):
    if len(argv) < 2 or "--front" not in argv:
        return emit("fail", "hunyuan shape: usage: shape <out.glb> --front <rgba> [--left] [--back] [--right]",
                    "lune run kit gen mv-shape <name> --front <pic> --left <pic> --back <pic> --right <pic>")
    out = argv[1]
    views = {}
    for v in VIEWS:
        if f"--{v}" in argv:
            path = argv[argv.index(f"--{v}") + 1]
            img = rgba_cutout(path) if os.path.isfile(path) else None
            if img is None:
                return emit("fail", f"hunyuan shape: the {v} view {path} is missing or has no cut-out (transparent "
                                    "background)", f"lune run kit vision cutout {path} --rgba, then pass its _rgba.png")
            views[v] = (path, img)
    full = _opt(argv, "--model", "turbo") == "full"   # (the base model: 50 steps, finer than its distillation?)
    shape_name = _SHAPE_FULL if full else _SHAPE
    seed, steps = _opt(argv, "--seed", 1), _opt(argv, "--steps", 50 if full else 5)
    octree, guidance = _opt(argv, "--octree", 380), _opt(argv, "--guidance", 5.0)
    chunks = _opt(argv, "--chunks", 20000)
    problems = check_weights([shape_name])
    if problems:
        return emit("fail", f"hunyuan shape: weights not ready — {problems[0]}",
                    "fetch them: python kit/gen/hunyuan_run.py fetch (kit/gen/README.md)")
    torch = install_guards()
    busy = gpu_room(torch, "shape")
    if busy:
        return emit("fail", f"hunyuan shape: {busy}", "wait until the GPU is free (nvidia-smi), then run it again")
    t0 = time.time()
    pipe = shape_pipeline(torch, os.path.join(WEIGHTS, "Hunyuan3D-2mv", shape_name))
    pipe.device = torch.device("cuda")
    offload_one_at_a_time(torch, {"conditioner": pipe.conditioner, "model": pipe.model, "vae": pipe.vae})
    t_load = time.time() - t0
    torch.cuda.reset_peak_memory_stats()
    t1 = time.time()
    result = pipe(image={v: img for v, (_p, img) in views.items()}, num_inference_steps=steps,
                  guidance_scale=guidance, octree_resolution=octree, num_chunks=chunks,
                  generator=torch.manual_seed(seed), output_type="trimesh", enable_pbar=False)[0]
    peak = torch.cuda.max_memory_allocated() / 2**30
    t_gen = time.time() - t1
    pipe.vae.to("cpu")
    if result is None:
        return emit("fail", "hunyuan shape: no surface came out (the decoder found nothing inside the box)",
                    "check the views are cut out and show one object; try another --seed")
    mesh, dropped = clean_shape(result)
    import trimesh  # noqa: PLC0415

    glb = trimesh.Trimesh(to_roblox(mesh.vertices), mesh.faces, process=False)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    glb.export(out)
    ext = (glb.vertices.max(0) - glb.vertices.min(0)).round(4).tolist()
    record = {
        "engine": "hunyuan3d-2mv", "private_only": True, "model": f"tencent/Hunyuan3D-2mv/{shape_name}",
        "licence": LICENCE,
        "frame": "roblox: x right, y up, front -Z (unit box, as generated)",
        "views": {v: {"input": os.path.basename(p), "sha256": sha256(p)} for v, (p, _i) in views.items()},
        "seed": seed, "steps": steps, "octree": octree, "guidance": guidance,
        "vertices": len(glb.vertices), "faces": len(glb.faces), "extents": ext, "specks_dropped": dropped,
        "watertight": bool(glb.is_watertight), "weights": _pins(shape_name),
        "seconds": round(time.time() - t0, 1), "seconds_load": round(t_load, 1), "seconds_generate": round(t_gen, 1),
        "peak_vram_gb": round(peak, 2), "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_record(out, record)
    return emit("pass", f"hunyuan shape: {out} — {len(glb.faces)} faces from {len(views)} view(s) in "
                        f"{record['seconds']} s (peak {record['peak_vram_gb']} GB on the GPU)",
                "import it: a.import_mesh(...) in a MASTER build script, then lune run kit asset <name>", out=out,
                record=record)


# ------------------------------------------------------------------ paint: mesh + picture -> textured mesh
def paint_pipeline(torch):
    """Paint turbo's multiview network, assembled from the vetted GitHub code and the safetensors weights: the
    repo's unet/modules.py is never run, the unet .bin never fetched, and the text encoder (its prompt is a learned
    embedding inside the unet) never loaded"""
    from diffusers import AutoencoderKL, DDIMScheduler, LCMScheduler  # noqa: PLC0415
    from diffusers.models import UNet2DConditionModel  # noqa: PLC0415
    from hy3dgen.texgen.hunyuanpaint.pipeline import HunyuanPaintPipeline  # noqa: PLC0415
    from hy3dgen.texgen.hunyuanpaint.unet.modules import UNet2p5DConditionModel  # noqa: PLC0415
    from safetensors import safe_open  # noqa: PLC0415
    from transformers import CLIPImageProcessor, CLIPTokenizer  # noqa: PLC0415

    with open(os.path.join(PAINT_DIR, "unet", "config.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    with no_init(torch, torch.float16):
        unet = UNet2p5DConditionModel(UNet2DConditionModel(**cfg))
    with safe_open(os.path.join(PAINT_DIR, "unet", "diffusion_pytorch_model.safetensors"), "pt", device="cpu") as f:
        missing, unexpected = load_streaming(torch, unet, f)
    # the safetensors also carries an image-prompt adapter (attn2.to_k_ip / to_v_ip + unet.image_proj_model: 36
    # tensors) that neither the GitHub code nor the repo's own unet/modules.py (functionally identical, compared
    # 2026-10-06) ever builds — so upstream never runs it either: left out
    unexpected = [k for k in unexpected if ".attn2.to_k_ip." not in k and ".attn2.to_v_ip." not in k
                  and not k.startswith("unet.image_proj_model.")]
    if missing or unexpected:
        raise RuntimeError(f"hunyuan paint: the unet checkpoint does not fit the code: missing {missing[:3]}, "
                           f"unexpected {unexpected[:3]}")
    unet = unet.to(torch.float16).requires_grad_(False)
    vae = AutoencoderKL.from_pretrained(os.path.join(PAINT_DIR, "vae"), torch_dtype=torch.float16)
    sched = DDIMScheduler.from_pretrained(os.path.join(PAINT_DIR, "scheduler"))  # (as the repo's model_index)
    pipe = HunyuanPaintPipeline(
        vae=vae, text_encoder=None, tokenizer=CLIPTokenizer.from_pretrained(os.path.join(PAINT_DIR, "tokenizer")),
        unet=unet, scheduler=sched,
        feature_extractor=CLIPImageProcessor.from_pretrained(os.path.join(PAINT_DIR, "feature_extractor")))
    pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")  # turbo
    pipe.set_turbo(True)
    pipe.set_progress_bar_config(disable=True)
    pipe.vae.enable_slicing()
    return pipe.to("cuda")


def multiview(torch, pipe, image, controls, camera_info, seed):
    """Multiview_Diffusion_Net.__call__ (hy3dgen/texgen/utils/multiview_utils.py) with the seed passed in"""
    import random  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    size = 512
    controls = [c.resize((size, size)) for c in controls]
    n = len(controls) // 2
    kwargs = dict(generator=torch.Generator(device="cuda").manual_seed(seed), width=size, height=size,
                  num_in_batch=n, camera_info_gen=[camera_info], camera_info_ref=[[0]],
                  normal_imgs=[controls[:n]], position_imgs=[controls[n:]])
    return pipe([image.resize((size, size))], num_inference_steps=30, **kwargs).images


def vertex_fill(texture, mask, vtx_pos, vtx_uv, pos_idx, uv_idx):
    """Hunyuan's meshVerticeInpaint (texgen/differentiable_renderer/mesh_processor.py) as sparse-matrix passes: every
    vertex no view saw takes the inverse-square-distance mean colour of its coloured neighbours along the mesh, pass
    after pass, until no more can be reached; each such vertex's colour is written at its texels (the seeds the image
    inpaint grows from). The same rule — its python loop swept every uncoloured vertex once per pass, so a big unseen
    region (a chair's underside) took 146 s of a 168 s paint. -> (texture, mask) as the original returns them"""
    import numpy as np  # noqa: PLC0415
    import scipy.sparse as sp  # noqa: PLC0415

    h, w = texture.shape[:2]
    cols = np.rint(vtx_uv[uv_idx][..., 0] * (w - 1)).astype(np.int64).ravel()
    rows = np.rint((1.0 - vtx_uv[uv_idx][..., 1]) * (h - 1)).astype(np.int64).ravel()
    vi = pos_idx.ravel()
    seen = mask[rows, cols] > 0
    n = len(vtx_pos)
    known = np.zeros(n, bool)
    color = np.zeros((n, texture.shape[2]), np.float64)
    color[vi[seen]] = texture[rows[seen], cols[seen]]
    known[vi[seen]] = True
    a, b = pos_idx.ravel(), np.roll(pos_idx, -1, axis=1).ravel()   # (the original's G[a] holds b)
    wt = 1.0 / np.maximum(np.linalg.norm(vtx_pos[a] - vtx_pos[b], axis=1), 1e-4) ** 2
    adj = sp.csr_matrix((wt, (a, b)), shape=(n, n))
    filled = np.zeros(n, bool)
    while True:
        k = known.astype(np.float64)
        tot = adj @ k
        new = ~known & (tot > 0)
        if not new.any():
            break
        acc = adj @ (color * k[:, None])
        color[new] = acc[new] / tot[new, None]
        known |= new
        filled |= new
    out, out_mask = texture.copy(), mask.copy()
    put = filled[vi]
    out[rows[put], cols[put]] = color[vi[put]]
    out_mask[rows[put], cols[put]] = 255
    return out, out_mask


def uv_fill(render, texture, mask_np):
    """MeshRender.uv_inpaint with the fast vertex_fill, then the same OpenCV inpaint -> a float texture tensor"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    import torch  # noqa: PLC0415

    vtx_pos, pos_idx, vtx_uv, uv_idx = render.get_mesh()
    tex, m = vertex_fill(texture.cpu().numpy(), mask_np, vtx_pos, vtx_uv, pos_idx, uv_idx)
    tex = cv2.inpaint((tex * 255).astype(np.uint8), 255 - m, 3, cv2.INPAINT_NS)
    return torch.tensor(tex / 255).float().to(texture.device)


def sheet(path, images, size=256):
    from PIL import Image  # noqa: PLC0415

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    canvas = Image.new("RGB", (size * 4, size * 2), (128, 128, 128))
    for i, im in enumerate(images[:8]):
        canvas.paste(im.convert("RGB").resize((size, size)), ((i % 4) * size, (i // 4) * size))
    canvas.save(path)


def paint(argv):
    if len(argv) < 4:
        return emit("fail", "hunyuan paint: usage: paint <mesh.glb> <picture_rgba.png> <out.glb> [--seed N]",
                    "lune run kit gen paint <asset-or-mesh> --image <picture>")
    src, pic, out = argv[1], argv[2], argv[3]
    seed, tex = _opt(argv, "--seed", 0), _opt(argv, "--texture", 2048)
    sheet_path = argv[argv.index("--sheet") + 1] if "--sheet" in argv else None
    image = rgba_cutout(pic) if os.path.isfile(pic) else None
    if image is None:
        return emit("fail", f"hunyuan paint: {pic} is missing or has no cut-out (transparent background)",
                    f"lune run kit vision cutout {pic} --rgba, then pass its _rgba.png")
    if not os.path.isfile(src):
        return emit("fail", f"hunyuan paint: no mesh at {src}", "lune run kit gen paint <asset-or-mesh> ...")
    problems = check_weights([_PAINT, _DELIGHT])
    if problems:
        return emit("fail", f"hunyuan paint: weights not ready — {problems[0]}",
                    "fetch them: python kit/gen/hunyuan_run.py fetch (kit/gen/README.md)")
    torch = install_guards()
    busy = gpu_room(torch, "paint")
    if busy:
        return emit("fail", f"hunyuan paint: {busy}", "wait until the GPU is free (nvidia-smi), then run it again")
    import numpy as np  # noqa: PLC0415
    import trimesh  # noqa: PLC0415

    mesh = trimesh.load(src, force="mesh", process=False)
    uv = getattr(mesh.visual, "uv", None)
    if uv is None or len(uv) != len(mesh.vertices):
        return emit("fail", f"hunyuan paint: {src} has no UV layout",
                    "let the kit unwrap it: lune run kit gen paint <asset-or-mesh> --image <picture>")
    if len(mesh.faces) > 500000:
        return emit("fail", f"hunyuan paint: {len(mesh.faces)} faces is too many to paint",
                    "lune run kit gen paint ... --faces 100000 (the kit reduces it first)")
    t0 = time.time()
    from hy3dgen.texgen.differentiable_renderer.mesh_render import MeshRender  # noqa: PLC0415
    from hy3dgen.texgen.pipelines import Hunyuan3DPaintPipeline, Hunyuan3DTexGenConfig  # noqa: PLC0415
    from hy3dgen.texgen.utils.dehighlight_utils import Light_Shadow_Remover  # noqa: PLC0415

    cfg = Hunyuan3DTexGenConfig(DELIGHT_DIR, PAINT_DIR, _PAINT)
    cfg.texture_size = tex
    hp = Hunyuan3DPaintPipeline.__new__(Hunyuan3DPaintPipeline)  # its methods, not its all-at-once loading
    hp.config, hp.models = cfg, {}
    hp.render = MeshRender(default_resolution=cfg.render_size, texture_size=cfg.texture_size)
    torch.cuda.reset_peak_memory_stats()
    # 1. Delight: the picture's lighting and shadows taken out
    prompt = hp.recenter_image(image)
    delight = Light_Shadow_Remover(cfg)
    lit_free = delight(prompt)
    del delight
    gc.collect()
    torch.cuda.empty_cache()
    t_delight = time.time() - t0
    # 2. the mesh, turned into Hunyuan's frame, seen from the 6 views the network was trained on
    steps_s = {}
    t_ = time.time()
    mesh.vertices = to_roblox(mesh.vertices)
    hp.render.load_mesh(mesh)
    elevs, azims, weights = cfg.candidate_camera_elevs, cfg.candidate_camera_azims, cfg.candidate_view_weights
    normals = hp.render_normal_multiview(elevs, azims, use_abs_coor=True)
    positions = hp.render_position_multiview(elevs, azims)
    camera_info = [(((a // 30) + 9) % 12) // {-20: 1, 0: 1, 20: 1, -90: 3, 90: 3}[e]
                   + {-20: 0, 0: 12, 20: 24, -90: 36, 90: 40}[e] for a, e in zip(azims, elevs)]
    steps_s["render_views"] = round(time.time() - t_, 1)
    # 3. Paint: 6 consistent views of the object, painted like the picture
    t1 = time.time()
    pipe = paint_pipeline(torch)
    views = multiview(torch, pipe, lit_free, normals + positions, camera_info, seed)
    del pipe
    gc.collect()
    torch.cuda.empty_cache()
    t_paint = time.time() - t1
    if sheet_path:
        sheet(sheet_path, [prompt, lit_free] + list(views))
    # 4. bake the views into the UV layout, fill what no view saw
    views = [v.resize((cfg.render_size, cfg.render_size)) for v in views]
    t_ = time.time()
    texture, mask = hp.bake_from_multiview(views, elevs, azims, weights, method=cfg.merge_method)
    steps_s["bake"] = round(time.time() - t_, 1)
    used = hp.render.uv_feature_map(torch.ones_like(hp.render.vtx_pos[:, :1]))[..., 0] > 0
    seen = mask.squeeze(-1) & used
    coverage = float(seen.sum()) / max(1.0, float(used.sum()))
    mask_np = (mask.squeeze(-1).cpu().numpy() * 255).astype(np.uint8)
    t_ = time.time()
    texture = uv_fill(hp.render, texture, mask_np)   # (hp.texture_inpaint, its vertex pass vectorised)
    steps_s["inpaint"] = round(time.time() - t_, 1)
    t_ = time.time()
    hp.render.set_texture(texture)
    painted = hp.render.save_mesh()
    painted.vertices = to_roblox(painted.vertices)  # back to the input's own frame
    peak = torch.cuda.max_memory_allocated() / 2**30
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    painted.export(out)
    steps_s["save"] = round(time.time() - t_, 1)
    record = {
        "engine": "hunyuan3d-paint", "private_only": True, "model": f"tencent/Hunyuan3D-2/{_PAINT} + {_DELIGHT}",
        "licence": LICENCE,
        "frame": "the input mesh's own (roblox: x right, y up, front -Z); geometry unchanged, a base-colour texture",
        "input_mesh": os.path.basename(src), "input_mesh_sha256": sha256(src), "picture": os.path.basename(pic),
        "picture_sha256": sha256(pic), "seed": seed, "texture": tex, "faces": len(painted.faces),
        "coverage": round(coverage, 4), "weights": {**_pins(_PAINT), **_pins(_DELIGHT)},
        "seconds": round(time.time() - t0, 1), "seconds_delight": round(t_delight, 1),
        "seconds_paint": round(t_paint, 1), "seconds_steps": steps_s, "peak_vram_gb": round(peak, 2), "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_record(out, record)
    hint = (f"look at {sheet_path} (the picture, without its lighting, and the 6 painted views)" if sheet_path
            else "transfer it onto the kit's atlas in the build script")
    return emit("pass", f"hunyuan paint: {out} — {round(coverage * 100, 1)}% of the surface seen by a view, the rest "
                        f"filled; {record['seconds']} s, peak {record['peak_vram_gb']} GB", hint, out=out,
                record=record)


def main(argv):
    if argv[:1] == ["fetch"]:
        return fetch()
    if argv[:1] == ["shape"]:
        return shape(argv)
    if argv[:1] == ["paint"]:
        return paint(argv)
    return emit("fail", "hunyuan: usage: hunyuan_run.py fetch | shape <out.glb> --front ... | paint <mesh> <pic> <out>",
                "see kit/gen/README.md")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
