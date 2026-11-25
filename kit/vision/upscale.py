"""upscale.py — a picture made 2x or 4x bigger with real detail (Real-ESRGAN, BSD-3; weights vetted + pinned in
kit/vision/models.json, loaded weights-only through spandrel). Kit python + torch, offline.

    python kit/vision/upscale.py <image> [--x 2|4] [-o out.png] [--fast] [--tile 384] [--cpu]

--x 4 (default) or 2 (made at x4, then scaled down with Lanczos, as Real-ESRGAN's own --outscale does).
--fast: the small model (realesr-general-x4v3, 1.2M weights) instead of the quality one (RealESRGAN_x4plus, 16.7M).
A transparent picture keeps its alpha: the alpha channel goes through the same model (as Real-ESRGAN does).
Big pictures are done in tiles (--tile px, each read with 16 px of context around it, so no seams). The GPU is used
when it has room (2 GB free), else the CPU (slower, same result); --cpu forces the CPU.
Writes build/vision/<name>_x<n>.png unless -o.

spandrel imports einops for architectures the kit never loads (DAT, HAT, SwinIR-family); the two Real-ESRGAN networks
do not use it, and einops is not on the approved list for the kit python, so a placeholder stands in while it is
missing (a real einops, once installed, is used instead).
"""

import json
import math
import os
import sys
import time
import types

import numpy as np
from PIL import Image

MODELS = {"quality": ("realesrgan-x4plus", "RealESRGAN_x4plus.pth"),
          "fast": ("realesr-general-x4v3", "realesr-general-x4v3.pth")}
ARCHS = {"ESRGAN", "RealESRGAN Compact"}  # spandrel's names for the two networks: anything else is refused
SCALE = 4
PAD = 16  # context read around each tile
GPU_FREE_MB = 2048  # below this much free GPU memory the CPU is used
MAX_SIDE = 8192  # the longest side an output may have


def tiles(w, h, tile, pad=PAD):
    """cover a w x h picture with tiles of at most tile x tile, spread evenly (no sliver at the end); each tile's
    CORE is pasted once, and it is READ with up to `pad` px of context around it, clamped to the picture
    -> [((core x0, y0, x1, y1), (read x0, y0, x1, y1))] in reading order"""
    if tile <= 0:
        tile = max(w, h)

    def cuts(n):
        k = max(1, math.ceil(n / tile))
        return [round(i * n / k) for i in range(k + 1)]

    xs, ys = cuts(w), cuts(h)
    out = []
    for y0, y1 in zip(ys, ys[1:]):
        for x0, x1 in zip(xs, xs[1:]):
            out.append(((x0, y0, x1, y1), (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))))
    return out


def stitch(img, fn, scale, tile, pad=PAD):
    """run fn (an H x W [x C] array -> the same scale-times bigger) tile by tile and paste each tile's core: the
    result equals fn on the whole picture wherever fn sees no further than `pad` px"""
    h, w = img.shape[:2]
    out = None
    for (x0, y0, x1, y1), (rx0, ry0, rx1, ry1) in tiles(w, h, tile, pad):
        part = fn(img[ry0:ry1, rx0:rx1])
        if part.shape[:2] != ((ry1 - ry0) * scale, (rx1 - rx0) * scale):
            raise ValueError(f"the model returned {part.shape[:2]} for a {(ry1 - ry0, rx1 - rx0)} tile, not x{scale}")
        if out is None:
            out = np.zeros((h * scale, w * scale) + part.shape[2:], dtype=part.dtype)
        cy, cx = (y0 - ry0) * scale, (x0 - rx0) * scale
        out[y0 * scale:y1 * scale, x0 * scale:x1 * scale] = part[cy:cy + (y1 - y0) * scale, cx:cx + (x1 - x0) * scale]
    return out


def out_size(w, h, x):
    return w * x, h * x


def _einops_placeholder():
    """spandrel's package imports einops for networks the kit never loads; stand in only while it is missing"""
    try:
        import einops  # noqa: F401, PLC0415

        return
    except ImportError:
        pass

    class _Placeholder(types.ModuleType):
        __path__ = []

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return type(name, (), {})

    for name in ("einops", "einops.layers", "einops.layers.torch"):
        sys.modules.setdefault(name, _Placeholder(name))


def pick_device(force_cpu=False):
    """-> (device, why)"""
    import torch  # noqa: PLC0415

    if force_cpu:
        return "cpu", "CPU (--cpu)"
    if not torch.cuda.is_available():
        return "cpu", "CPU (no CUDA GPU)"
    free_mb = gpu_free_mb()
    if free_mb is None:  # (no nvidia-smi: ask CUDA itself, which costs a context on the GPU)
        free_mb = torch.cuda.mem_get_info()[0] // 2 ** 20
    if free_mb < GPU_FREE_MB:
        return "cpu", f"CPU (the GPU has only {free_mb} MB free)"
    return "cuda", torch.cuda.get_device_name(0)


def gpu_free_mb():
    """the first GPU's free memory from nvidia-smi (MB), or None — asked without touching the GPU"""
    import subprocess  # noqa: PLC0415

    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", "-i", "0"],
                           capture_output=True, text=True, timeout=20)
        return int(r.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def load(kind, device):
    """the pinned weights, checked against their pin (kit/vision/run.py ensure), loaded weights-only"""
    import torch  # noqa: PLC0415

    import run  # noqa: PLC0415  (the pin check; importing it also switches the network off)

    name, fname = MODELS[kind]
    path = os.path.join(run.ensure(name), fname)
    _einops_placeholder()
    import spandrel  # noqa: PLC0415

    state = torch.load(path, map_location="cpu", weights_only=True)
    model = spandrel.ModelLoader().load_from_state_dict(spandrel.canonicalize_state_dict(state))
    if model.architecture.name not in ARCHS or model.scale != SCALE:
        raise RuntimeError(f"{name}: spandrel read it as {model.architecture.name} x{model.scale}, "
                           "not a Real-ESRGAN x4")
    model.model.train(False)
    model.to(device)
    half = device == "cuda" and model.supports_half
    if half:
        model.model.half()
    return model, half


def runner(model, device, half):
    """an H x W x 3 float32 0..1 array -> 4x bigger, through the model"""
    import torch  # noqa: PLC0415

    def fn(arr):
        t = torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1)))[None].to(device)
        with torch.inference_mode():
            y = model(t.half() if half else t).float().clamp(0, 1)
        return y[0].cpu().numpy().transpose(1, 2, 0)

    return fn


def upscale(img, x=4, kind="quality", tile=384, force_cpu=False):
    """a PIL picture -> (the picture x times bigger, how it ran). RGBA keeps its alpha; other modes come back RGB."""
    alpha = None
    if img.mode in ("RGBA", "LA", "P", "PA"):
        rgba = np.asarray(img.convert("RGBA"))
        if (rgba[..., 3] < 255).any():
            alpha = rgba[..., 3].astype(np.float32) / 255
        rgb = rgba[..., :3]
    else:
        rgb = np.asarray(img.convert("RGB"))
    rgb = rgb.astype(np.float32) / 255

    def run_on(device):
        model, half = load(kind, device)
        fn = runner(model, device, half)
        big = stitch(rgb, fn, SCALE, tile)
        if alpha is None:
            return big, None, half
        return big, stitch(np.repeat(alpha[..., None], 3, axis=2), fn, SCALE, tile).mean(axis=2), half

    device, why = pick_device(force_cpu)
    try:
        big, big_a, half = run_on(device)
    except RuntimeError as e:  # (torch.cuda.OutOfMemoryError is one): the CPU always has room
        if device != "cuda" or "out of memory" not in str(e).lower():
            raise
        import torch  # noqa: PLC0415

        torch.cuda.empty_cache()
        device, why = "cpu", "CPU (the GPU ran out of memory)"
        big, big_a, half = run_on(device)
    out = Image.fromarray((big * 255).round().clip(0, 255).astype(np.uint8), "RGB")
    if big_a is not None:
        out.putalpha(Image.fromarray((big_a * 255).round().clip(0, 255).astype(np.uint8), "L"))
    if x != SCALE:
        w, h = img.size
        out = out.resize(out_size(w, h, x), Image.LANCZOS)
    return out, {"device": device, "why": why, "half": half, "model": MODELS[kind][0], "alpha": alpha is not None}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def main(argv):
    if not argv or not os.path.isfile(argv[0]):
        return emit("fail", "vision upscale: give a picture file",
                    "lune run kit vision upscale refs/<picture>.png [--x 2]")
    src = argv[0]
    x = int(argv[argv.index("--x") + 1]) if "--x" in argv else 4
    if x not in (2, 4):
        return emit("fail", f"vision upscale: --x is 2 or 4, not {x}", "lune run kit vision upscale <picture> --x 2")
    tile = int(argv[argv.index("--tile") + 1]) if "--tile" in argv else 384
    img = Image.open(src)
    w, h = img.size
    if max(w, h) * x > MAX_SIDE:
        return emit("fail", f"vision upscale: {w} x {h} px x{x} would be {w * x} x {h * x} px (the limit is "
                            f"{MAX_SIDE} px a side)", "use --x 2, or crop the picture to the part you need first")
    import run  # noqa: PLC0415  (offline from here on: run.py switches the network off)

    t0 = time.time()
    try:
        out_img, how = upscale(img, x=x, kind="fast" if "--fast" in argv else "quality", tile=tile,
                               force_cpu="--cpu" in argv)
    except (run.ModelMissing, run.PinMismatch) as e:
        return emit("fail", f"vision upscale: {e}", "lune run kit vision setup realesrgan-x4plus realesr-general-x4v3")
    if "-o" in argv:
        out = argv[argv.index("-o") + 1]
    else:
        out = os.path.join("build", "vision", f"{os.path.splitext(os.path.basename(src))[0]}_x{x}.png")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    out_img.save(out)
    took = time.time() - t0
    return emit("pass", f"vision upscale: {out} ({w} x {h} -> {out_img.size[0]} x {out_img.size[1]} px, {how['model']} "
                        f"on {how['why']}{', fp16' if how['half'] else ''}{', alpha kept' if how['alpha'] else ''}, "
                        f"{took:.1f} s)", f"look at {out}", out=out.replace("\\", "/"), seconds=round(took, 2), **how)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
