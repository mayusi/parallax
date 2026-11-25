"""vision2.py — the kit's second vision stack (phase B, owner-approved 2026-10-06), run in the TRELLIS.2 environment
(it has the torch + CUDA these models need). `lune run kit vision <command> ...` routes here:

    relief <rgba.png> [-o out.npz] [--detail 1.5]     an ornament's relief from its picture: MoGe-2 normals +
                                                      Depth Anything 3 depth, integrated (kit/gen/relief.py);
                                                      a lit preview beside its picture in build/vision/
    parts <image> --text "<thing>" [--text ...] [-o out.png] [--min 0.5] [--masks out.npz]
                                                      every match of each text prompt as a mask (SAM 3); --masks:
                                                      each match's own mask + score + words (kit trace --part-text)
    albedo <image> [-o out.npz] [--ensemble 1] [--res 768]
                                                      the picture's colour with its lighting taken out, and its
                                                      roughness and metalness (Marigold-IID appearance); a
                                                      cut-out's transparent pixels are left out

Offline: every socket connection raises, Hugging Face is offline, and each weight file is checked against its pin
in kit/vision/models.json (size) before use. Depth Anything 3's package is installed without its dependencies (its
pyproject pulls a web server, video and point-cloud tools); the few optional modules its api imports but depth never
calls (moviepy, pycolmap, evo) are placeholders here.
"""

import json
import os
import socket
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MANIFEST = os.path.join(ROOT, "kit", "vision", "models.json")
BUILD = os.path.join(ROOT, os.environ.get("KIT_BUILD", "build"))
CACHE = os.environ.get("KIT_MODELS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "models")
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")


def _no_network(*_a, **_k):
    raise RuntimeError("kit vision runs offline: a network connection was attempted and blocked")


socket.socket.connect = _no_network
socket.socket.connect_ex = _no_network
socket.socket.sendto = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network


class _Placeholder(types.ModuleType):
    """an optional export / app module of Depth Anything 3 that depth estimation never calls"""
    __path__ = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return type(name, (), {})


for _m in ("moviepy", "moviepy.editor", "pycolmap", "evo", "evo.core", "evo.core.trajectory"):
    sys.modules.setdefault(_m, _Placeholder(_m))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def model_dir(name):
    """the model's folder, every pinned file present at its pinned size (else a clear error)"""
    with open(MANIFEST, encoding="utf-8") as fh:
        m = json.load(fh)["models"][name]
    folder = os.path.join(CACHE, name)
    for f in m["files"]:
        p = os.path.join(folder, f["path"])
        if not os.path.isfile(p) or os.path.getsize(p) != f["size"]:
            raise FileNotFoundError(f"{name}/{f['path']} missing or not its pinned size — lune run kit vision setup {name}")
    return folder


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def _all(argv, flag):
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag and i + 1 < len(argv)]


def normals_and_depth(rgb):
    """MoGe-2 camera-space unit normals (H, W, 3) and Depth Anything 3 relative depth (H, W) of an RGB picture"""
    import torch  # noqa: PLC0415
    from moge.model.v2 import MoGeModel  # noqa: PLC0415

    H, W = rgb.shape[:2]
    moge = MoGeModel.from_pretrained(os.path.join(model_dir("moge-2-vitl-normal"), "model.pt")).cuda()
    moge.train(False)
    with torch.no_grad():
        out = moge.infer(torch.from_numpy(rgb.astype(np.float32) / 255).permute(2, 0, 1).cuda(), apply_mask=False)
    normal = out["normal"].float().cpu().numpy()
    del moge
    torch.cuda.empty_cache()
    from depth_anything_3.api import DepthAnything3  # noqa: PLC0415

    da3 = DepthAnything3.from_pretrained(model_dir("da3-mono-large")).cuda()
    da3.train(False)
    depth = np.asarray(da3.inference([Image.fromarray(rgb)]).depth[0], dtype=np.float32)
    del da3
    torch.cuda.empty_cache()
    if depth.shape != (H, W):
        depth = np.asarray(Image.fromarray(depth).resize((W, H), Image.BILINEAR))
    normal /= np.linalg.norm(normal, axis=2, keepdims=True) + 1e-9
    return normal, depth


def cmd_relief(argv):
    src = argv[0]
    rgba = Image.open(src).convert("RGBA")
    a = np.asarray(rgba)
    mask = a[:, :, 3] > 127
    if mask.all() or not mask.any():
        return emit("fail", f"vision relief: {src} needs a cut-out (a transparent background around the ornament)",
                    "cut it out first: lune run kit vision parts <picture> --text \"<ornament>\" or vision cutout")
    rgb = a[:, :, :3].copy()
    t0 = time.time()
    normal, depth = normals_and_depth(rgb)
    import relief as R  # noqa: PLC0415

    h = R.relief_height(normal, depth, mask, detail=_opt(argv, "--detail", 1.5))
    out = argv[argv.index("-o") + 1] if "-o" in argv else os.path.splitext(src)[0] + ".relief.npz"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    np.savez_compressed(out, height=h.astype(np.float32), mask=mask, rgb=rgb,
                        meta=json.dumps({"source": src.replace("\\", "/"), "px": [int(mask.shape[1]), int(mask.shape[0])],
                                         "models": ["moge-2-vitl-normal", "da3-mono-large"]}))
    H, W = mask.shape
    sh = (R.shade(h, relief_depth=0.05) * 230 * mask + 40 * ~mask).astype(np.uint8)
    prev = Image.new("RGB", (W * 2, H), (20, 20, 20))
    bg = Image.new("RGBA", (W, H), (60, 60, 64, 255))
    bg.alpha_composite(rgba)
    prev.paste(bg.convert("RGB"), (0, 0))
    prev.paste(Image.fromarray(sh).convert("RGB"), (W, 0))
    preview = os.path.join(BUILD, "vision", os.path.splitext(os.path.basename(out))[0] + "_preview.png")
    os.makedirs(os.path.dirname(preview), exist_ok=True)  # (a generated picture: build/, never beside the input)
    prev.save(preview)
    return emit("pass", f"vision relief: {out} ({W} x {H} px ornament, {int(mask.sum())} px, {time.time() - t0:.1f} s) — "
                        f"LOOK at {preview} (the picture beside its lit relief)",
                f'build it: a.relief("<Name>", "{out}", "<material>", width=<studs>, depth=<studs>, pos=..., rot=...)',
                out=out.replace("\\", "/"), preview=preview.replace("\\", "/"))


def cmd_parts(argv):
    import torch  # noqa: PLC0415
    from transformers import Sam3Model, Sam3Processor  # noqa: PLC0415

    src = argv[0]
    texts = _all(argv, "--text")
    if not texts:
        return emit("fail", "vision parts: needs --text \"<thing>\" (e.g. --text screw --text trigger)",
                    "lune run kit vision parts <picture> --text \"<thing>\"")
    image = Image.open(src).convert("RGB")
    folder = model_dir("sam3")
    t0 = time.time()
    proc = Sam3Processor.from_pretrained(folder)
    model = Sam3Model.from_pretrained(folder, torch_dtype=torch.float16).cuda()
    model.train(False)
    keep = _opt(argv, "--min", 0.5)
    found = {}
    W, H = image.size
    label = np.zeros((H, W), dtype=np.uint16)
    k = 0
    every = []  # (mask, score, text) of every match: --masks keeps them whole (the label image loses overlaps)
    for text in texts:
        inputs = proc(images=image, text=text, return_tensors="pt").to("cuda")
        inputs = {n: (v.half() if v.is_floating_point() else v) for n, v in inputs.items()}
        with torch.no_grad():
            outputs = model(**inputs)
        res = proc.post_process_instance_segmentation(outputs, threshold=keep, mask_threshold=0.5,
                                                      target_sizes=[(H, W)])[0]
        boxes = []
        for m, s, b in zip(res["masks"], res["scores"], res["boxes"]):
            k += 1
            mb = m.cpu().numpy().astype(bool)
            label[mb] = k
            every.append((mb, float(s), text))
            boxes.append({"id": k, "score": round(float(s), 3), "box": [round(float(x)) for x in b.tolist()]})
        found[text] = boxes
    if "--masks" in argv:  # every match's own mask, its score and its words (kit trace --part-text reads these)
        mpath = argv[argv.index("--masks") + 1]
        os.makedirs(os.path.dirname(os.path.abspath(mpath)), exist_ok=True)
        np.savez_compressed(mpath, masks=np.stack([e[0] for e in every]) if every else np.zeros((0, H, W), bool),
                            scores=np.array([e[1] for e in every], np.float32), texts=np.array([e[2] for e in every]))
    out = argv[argv.index("-o") + 1] if "-o" in argv else os.path.splitext(src)[0] + ".parts.png"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    Image.fromarray(label).save(out)
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump({"source": src.replace("\\", "/"), "label_image": out.replace("\\", "/"), "found": found}, fh, indent=1)
    counts = ", ".join(f"{t}: {len(b)}" for t, b in found.items())
    return emit("pass", f"vision parts: {counts} in {time.time() - t0:.1f} s -> {out} (+ .json: each mask's id, score, box)",
                "use a mask: kit vision relief on its cut-out, or its boxes as part positions", out=out.replace("\\", "/"),
                found=found)


def cmd_albedo(argv):
    import torch  # noqa: PLC0415
    from diffusers import MarigoldIntrinsicsPipeline  # noqa: PLC0415

    src = argv[0]
    a = np.asarray(Image.open(src).convert("RGBA"))
    mask = a[:, :, 3] > 127
    t0 = time.time()
    pipe = MarigoldIntrinsicsPipeline.from_pretrained(model_dir("marigold-iid-appearance"), variant="fp16",
                                                      torch_dtype=torch.float16).to("cuda")
    pipe.set_progress_bar_config(disable=True)
    res = pipe(Image.fromarray(a[:, :, :3]), ensemble_size=_opt(argv, "--ensemble", 1),
               processing_resolution=_opt(argv, "--res", 768),
               generator=torch.Generator("cuda").manual_seed(_opt(argv, "--seed", 1)))
    pred = np.asarray(res.prediction, dtype=np.float32)  # (2, H, W, 3): albedo (sRGB), then roughness / metalness
    del pipe
    torch.cuda.empty_cache()
    albedo, rough, metal = pred[0], pred[1][..., 0], pred[1][..., 1]
    out = argv[argv.index("-o") + 1] if "-o" in argv else os.path.splitext(src)[0] + ".albedo.npz"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    np.savez_compressed(out, albedo=albedo.astype(np.float16), rough=rough.astype(np.float16),
                        metal=metal.astype(np.float16), mask=mask,
                        meta=json.dumps({"source": src.replace("\\", "/"), "albedo_space": "srgb",
                                         "model": "marigold-iid-appearance"}))
    H, W = mask.shape
    sheet = Image.new("RGB", (W * 4, H), (20, 20, 20))
    for k, im in enumerate((a[:, :, :3], albedo * 255, np.dstack([rough] * 3) * 255, np.dstack([metal] * 3) * 255)):
        sheet.paste(Image.fromarray(np.clip(im, 0, 255).astype(np.uint8)), (k * W, 0))
    preview = os.path.join(BUILD, "vision", os.path.splitext(os.path.basename(out))[0] + "_preview.png")
    os.makedirs(os.path.dirname(preview), exist_ok=True)
    sheet.save(preview)
    sel = mask if (mask.any() and not mask.all()) else np.ones_like(mask)
    med = [round(float(v), 3) for v in np.median(albedo[sel], axis=0)]
    return emit("pass", f"vision albedo: {out} ({W} x {H} px, {time.time() - t0:.1f} s; median colour {med} sRGB, "
                        f"roughness {float(np.median(rough[sel])):.2f}, metalness {float(np.median(metal[sel])):.2f})"
                        f" — LOOK at {preview} (the picture, its colour, roughness, metalness)",
                "use it: a region's median colour is its material's colour with the light taken out",
                out=out.replace("\\", "/"), preview=preview.replace("\\", "/"), median_srgb=med)


def main(argv):
    cmds = {"relief": cmd_relief, "parts": cmd_parts, "albedo": cmd_albedo}
    if not argv or argv[0] not in cmds or len(argv) < 2 or not os.path.isfile(argv[1]):
        return emit("fail", f"vision2: usage: {' | '.join(cmds)} <image> ...", "lune run kit vision relief <cut-out.png>")
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
