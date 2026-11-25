"""run.py — the kit's local vision models: vetted, pinned (kit/vision/models.json), offline. System python + torch.

    python kit/vision/run.py doctor
    python kit/vision/run.py edges  <image> [-o out.png]          edge map (TEED): white paper, dark lines
    python kit/vision/run.py cutout <image> [-o out.png] [--rgba]  object mask (BiRefNet); --rgba also writes the cut-out
    python kit/vision/run.py mask   <image> --point x,y [--point x,y] [--neg x,y] | --box x0,y0,x1,y1 [-o out.png]
                                                                   ONE part's mask (SAM 2.1) from a click or a box
    python kit/vision/run.py depth  <image> [-o out.png]           relative depth (Depth Anything V2 Small): bright = near
    python kit/vision/run.py similar <a> <b>                        how alike two pictures LOOK (SigLIP 2 cosine, -1..1)
    python kit/vision/run.py view   <image> [--what "a crate"]     which way the photo looks at the object (zero-shot)
    python kit/vision/run.py differ <a> <b> [-o out.png]           WHERE two aligned pictures differ (DINOv2 patches)

Every model file is checked against its pinned hash before its first use (then a stamp of size, mtime, ctime and file
id), the network is switched OFF for the whole process (connect / connect_ex / sendto / DNS all raise), and outputs go
to build/vision/ unless -o.
Importable: edges(img) / cutout(img) / mask(img, points=..., box=...) / depth(img) / embed(imgs) / embed_text(texts) /
zero_shot(img, labels) / view_of(img, what) / patches(img) / differ(a, b) take and return numpy/PIL.
"""

import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")


def _no_network(*_a, **_k):
    raise RuntimeError("kit vision runs offline: a network connection was attempted and blocked")


socket.socket.connect = _no_network  # nothing the models (or a library) do may reach the network
socket.socket.connect_ex = _no_network
socket.socket.sendto = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import setup  # noqa: E402  (the manifest, the cache, the hash check)

_MODELS = {}
EDGE_FLAT = 0.44  # TEED's raw output on ANY flat surface or paper (measured: 0.438-0.441 for grey 60..220 and white)
EDGE_LINE = 0.6  # a line: well above flat, well below the 0.94-0.99 of real edges — a FIXED level, never per image


class ModelMissing(RuntimeError):
    """a vetted model file is not in the cache (kit vision setup not run): optional, so callers skip"""


class PinMismatch(RuntimeError):
    """a model file is there but does not match its vetted pin: never used, callers fail loudly"""


def _manifest():
    with open(setup.MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)["models"]


def ensure(name):
    """the model's folder, every file verified against its pin (full hash once, then size+mtime stamps)"""
    m = _manifest()[name]
    folder = os.path.join(setup.cache_dir(), name)
    stamp_path = os.path.join(folder, ".verified.json")
    try:
        with open(stamp_path, encoding="utf-8") as fh:
            stamps = json.load(fh)
    except (OSError, ValueError):
        stamps = {}
    changed = False
    for f in m["files"]:
        p = os.path.join(folder, f["path"])
        pin = f.get("sha256") or f["git_sha1"]
        if not os.path.isfile(p):
            raise ModelMissing(f"{name}/{f['path']} is not in {setup.cache_dir()} — run: lune run kit vision setup")
        st = os.stat(p)
        stamp = [st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino, pin]  # (a swapped file changes ctime / id)
        if stamps.get(f["path"]) == stamp:
            continue
        if not setup.file_ok(p, f):
            raise PinMismatch(f"{name}/{f['path']} does NOT match its vetted pin (size / hash) — it is never used; "
                              "re-fetch it: lune run kit vision setup")
        stamps[f["path"]] = stamp
        changed = True
    if changed:
        with open(stamp_path, "w", encoding="utf-8") as fh:
            json.dump(stamps, fh)
    return folder


def _torch():
    import torch

    # KIT_FORCE_CPU=1 skips the CUDA probe itself: with a faulted driver `torch.cuda.is_available()` crashes the whole
    # process (a segfault, 2026-10-14), and a machine without a GPU never needs to ask
    if os.environ.get("KIT_FORCE_CPU") == "1":
        torch.cuda.is_available = lambda: False  # (transformers asks CUDA on its own — stream capture — and crashed too)
        torch.cuda.is_current_stream_capturing = lambda: False
        torch.cuda.graphs.is_current_stream_capturing = lambda: False
        return torch, "cpu"
    return torch, ("cuda" if torch.cuda.is_available() else "cpu")


def _teed():
    if "teed" not in _MODELS:
        torch, dev = _torch()
        from teed import TED

        net = TED()
        sd = torch.load(os.path.join(ensure("teed"), "5_model.pth"), map_location="cpu", weights_only=True)
        net.load_state_dict(sd, strict=True)
        _MODELS["teed"] = net.to(dev).train(False)
    return _MODELS["teed"]


def _birefnet():
    if "birefnet" not in _MODELS:
        torch, dev = _torch()
        from safetensors.torch import load_file

        from birefnet import BiRefNet, BiRefNetConfig

        net = BiRefNet(config=BiRefNetConfig(bb_pretrained=False))
        missing, unexpected = net.load_state_dict(load_file(os.path.join(ensure("birefnet"), "model.safetensors")),
                                                  strict=False)
        if missing or unexpected:
            raise RuntimeError(f"birefnet weights do not fit the vendored network: {missing[:3]} {unexpected[:3]}")
        net = net.to(dev).train(False)
        _MODELS["birefnet"] = net.half() if dev == "cuda" else net
    return _MODELS["birefnet"]


def _sam():
    if "sam" not in _MODELS:
        _torch_, dev = _torch()
        from transformers import Sam2Model, Sam2Processor
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()  # (the checkpoint is typed sam2_video; the image model is a subset of it)
        folder = ensure("sam2.1-hiera-small")
        model = Sam2Model.from_pretrained(folder, local_files_only=True).to(dev).train(False)
        _MODELS["sam"] = (model, Sam2Processor.from_pretrained(folder, local_files_only=True))
    return _MODELS["sam"]


def _depth():
    if "depth" not in _MODELS:
        _torch_, dev = _torch()
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        folder = ensure("depth-anything-v2-small")
        model = AutoModelForDepthEstimation.from_pretrained(folder, local_files_only=True).to(dev).train(False)
        _MODELS["depth"] = (model, AutoImageProcessor.from_pretrained(folder, local_files_only=True))
    return _MODELS["depth"]


def _siglip():
    if "siglip" not in _MODELS:
        _torch_, dev = _torch()
        from transformers import AutoProcessor, SiglipModel

        folder = ensure("siglip2-base")
        # the fixed-resolution SigLIP 2 checkpoints are SigLIP-architecture weights (config model_type "siglip");
        # Siglip2Model is the NaFlex variant's class and does not fit them
        model = SiglipModel.from_pretrained(folder, local_files_only=True).to(dev).train(False)
        _MODELS["siglip"] = (model, AutoProcessor.from_pretrained(folder, local_files_only=True))
    return _MODELS["siglip"]


def _dino():
    if "dino" not in _MODELS:
        _torch_, dev = _torch()
        from transformers import AutoImageProcessor, Dinov2WithRegistersModel

        folder = ensure("dinov2-reg-small")
        model = Dinov2WithRegistersModel.from_pretrained(folder, local_files_only=True).to(dev).train(False)
        _MODELS["dino"] = (model, AutoImageProcessor.from_pretrained(folder, local_files_only=True))
    return _MODELS["dino"]


def _rgb(img):
    if isinstance(img, str):
        img = Image.open(img)
    if img.mode in ("RGBA", "LA", "P"):  # a transparent background reads as white paper, as on a product page
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    return img.convert("RGB")


def edges(img):
    """edge probability map (TEED, as its own test pipeline: BGR minus the BIPED mean, small images x1.5, sizes rounded
    up to a multiple of 8, the fused output) -> float32 HxW: the RAW sigmoid — flat surfaces sit at EDGE_FLAT (~0.44),
    lines above EDGE_LINE (0.6). (TEED's own saver min-max normalises per image: on a flat picture that stretches
    0.003 of noise into "lines everywhere", so it is NOT done here.)"""
    torch, dev = _torch()
    img = _rgb(img)
    w0, h0 = img.size
    x = np.asarray(img).astype(np.float32)[..., ::-1] - np.array([104.007, 116.669, 122.679], np.float32)
    s = 1.5 if (h0 < 512 or w0 < 512) else 1.0
    h8, w8 = -(-int(h0 * s) // 8) * 8, -(-int(w0 * s) // 8) * 8
    t = torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1)))[None].to(dev)
    t = torch.nn.functional.interpolate(t, size=(h8, w8), mode="bilinear", align_corners=False)
    with torch.no_grad():
        e = torch.sigmoid(_teed()(t)[-1])
        e = torch.nn.functional.interpolate(e, size=(h0, w0), mode="bilinear", align_corners=False)
    return e[0, 0].float().cpu().numpy()


def cutout(img):
    """object (foreground) mask (BiRefNet at 1024 px, ImageNet normalisation, as its model card) -> float32 HxW 0..1"""
    torch, dev = _torch()
    img = _rgb(img)
    w0, h0 = img.size
    x = np.asarray(img.resize((1024, 1024), Image.BILINEAR)).astype(np.float32) / 255
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    t = torch.from_numpy(x.transpose(2, 0, 1).copy())[None].to(dev)
    with torch.no_grad():
        p = _birefnet()(t.half() if dev == "cuda" else t)[-1].sigmoid().float()
        p = torch.nn.functional.interpolate(p, size=(h0, w0), mode="bilinear", align_corners=False)
    return p[0, 0].cpu().numpy()


def mask(img, points=None, negatives=None, box=None):
    """ONE part's mask (SAM 2.1): points = [(x, y)] on the part (negatives: on what is NOT the part), and/or box =
    (x0, y0, x1, y1) around it (a box with clicks: the box bounds it, the clicks say which piece and which not)
    -> (bool HxW, score 0..1)"""
    torch, dev = _torch()
    img = _rgb(img)
    model, proc = _sam()
    kw = {}
    if points or negatives:
        pts = [[list(p) for p in (points or [])] + [list(p) for p in (negatives or [])]]
        kw["input_points"] = [pts]
        kw["input_labels"] = [[[1] * len(points or []) + [0] * len(negatives or [])]]
    if box:
        kw["input_boxes"] = [[list(box)]]
    inp = proc(images=img, return_tensors="pt", **kw).to(dev)
    with torch.no_grad():
        out = model(**inp, multimask_output=False)
    m = proc.post_process_masks(out.pred_masks.cpu(), inp["original_sizes"].cpu())[0][0, 0].numpy().astype(bool)
    return m, float(out.iou_scores.flatten()[0])


def depth(img):
    """relative depth (Depth Anything V2 Small; bright = near) -> float32 HxW 0..1"""
    torch, dev = _torch()
    img = _rgb(img)
    w0, h0 = img.size
    model, proc = _depth()
    inp = proc(images=img, return_tensors="pt").to(dev)
    with torch.no_grad():
        d = model(**inp).predicted_depth
        d = torch.nn.functional.interpolate(d[:, None], size=(h0, w0), mode="bicubic", align_corners=False)[0, 0]
    d = d.float().cpu().numpy()
    return (d - d.min()) / max(1e-6, float(d.max() - d.min()))


def embed(images):
    """SigLIP 2 image embeddings, L2-normalised -> float32 (n, d). Cosine of two = how alike they LOOK (content,
    style, finish) — the perceptual judge's eye. Takes paths / PIL images."""
    torch, dev = _torch()
    model, proc = _siglip()
    imgs = [_rgb(i) for i in images]
    with torch.no_grad():
        inp = proc(images=imgs, return_tensors="pt").to(dev)
        e = model.get_image_features(**inp)
        e = e.pooler_output if hasattr(e, "pooler_output") else e
        e = torch.nn.functional.normalize(e.float(), dim=-1)
    return e.cpu().numpy()


def embed_text(texts):
    """SigLIP 2 text embeddings, L2-normalised -> float32 (n, d) (padded to 64 tokens, as SigLIP was trained)"""
    torch, dev = _torch()
    model, proc = _siglip()
    with torch.no_grad():
        inp = proc(text=list(texts), padding="max_length", max_length=64, truncation=True, return_tensors="pt").to(dev)
        e = model.get_text_features(**inp)
        e = e.pooler_output if hasattr(e, "pooler_output") else e
        e = torch.nn.functional.normalize(e.float(), dim=-1)
    return e.cpu().numpy()


def zero_shot(image, labels):
    """SigLIP's own probability that each label describes the image (independent sigmoids, not a softmax) -> list"""
    torch, _dev = _torch()
    model, _proc = _siglip()
    img, txt = embed([image])[0], embed_text(labels)
    logits = txt @ img * float(model.logit_scale.exp()) + float(model.logit_bias)
    return [float(1 / (1 + np.exp(-v))) for v in logits]


VIEWS = {"side": "a side view of {}", "front": "a front view of {}", "top": "a top-down view of {}",
         "three-quarter": "a three-quarter view of {}", "back": "a view of the back of {}"}


def view_of(image, what="the object"):
    """which way a photo looks at the object (zero-shot) -> (best view, {view: p})"""
    ps = zero_shot(image, [t.format(what) for t in VIEWS.values()])
    out = dict(zip(VIEWS, ps))
    return max(out, key=out.get), out


def patches(img, size=448):
    """DINOv2 (with registers) per-patch features, L2-normalised -> float32 (h, w, d) on a size x size square
    (14 px patches: 448 -> 32 x 32). The CLS and register tokens are dropped: only the image grid remains."""
    torch, dev = _torch()
    model, proc = _dino()
    img = _rgb(img).resize((size, size), Image.BICUBIC)
    inp = proc(images=img, return_tensors="pt", do_resize=False, do_center_crop=False).to(dev)
    with torch.no_grad():
        h = model(**inp).last_hidden_state[0]
    n = size // 14
    grid = h[1 + model.config.num_register_tokens:][: n * n].float()
    grid = torch.nn.functional.normalize(grid, dim=-1).reshape(n, n, -1)
    return grid.cpu().numpy()


def differ(a, b, size=448):
    """WHERE two pictures of the same thing differ (DINOv2 patch features, same framing): 1 - cosine per patch ->
    float32 (h, w), 0 = alike. Meaningful on aligned pairs (a render vs its reference in the same frame)."""
    pa, pb = patches(a, size), patches(b, size)
    return np.clip(1.0 - (pa * pb).sum(-1), 0, 2).astype(np.float32)


NOT_SINK = 0.15   # a picture that is one of the --not terms keeps this share of its score: last, never deleted


def not_of(title, terms, probs=None, what_p=None):
    """which --not term a picture IS -> the term, or None: its own title names it (a whole word, any case), or the
    vision model's probability for the term beats its probability for the object (probs: one per term)"""
    import re  # noqa: PLC0415

    low = str(title or "").lower().replace("_", " ")
    for term in terms:
        words = [w for w in term.lower().split() if w]
        if words and all(re.search(rf"\b{re.escape(w)}\b", low) for w in words):
            return term
    if probs is not None and what_p is not None:
        for term, p in zip(terms, probs):
            if p > what_p:
                return term
    return None


def rank(folder, what="the object", nots=()):
    """rank downloaded reference candidates (kit refs find) for TRACING: which way each looks at the object (SigLIP
    zero-shot), how cleanly the object stands out (BiRefNet: a whole object, not cut by the frame, not a speck),
    resolution. nots: what the pictures must NOT be ("museum piece", "votive copy", "antique", "car" - the car rim's
    first search put museum objects first, lesson L-3d-aab91e): a picture whose title names one, or that the model
    reads as one more than as the object, sinks to the bottom (NOT_SINK of its score), marked with the term.
    -> list of dicts, best first; writes <folder>/index.json + <folder>/contact.png (numbered thumbnails)"""
    nots = [n.strip() for n in nots if n and n.strip()]
    from PIL import ImageDraw

    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                   and not f.startswith("contact"))
    rows = []
    for f in files:
        path = os.path.join(folder, f)
        try:
            img = _rgb(path)
        except Exception:  # noqa: BLE001 — a broken download is skipped, never fatal
            continue
        w, h = img.size
        best, ps = view_of(img, what)
        m = cutout(img) > 0.5
        cover = float(m.mean())
        ys, xs = np.nonzero(m)
        edge = bool(len(xs)) and bool(xs.min() <= 1 or ys.min() <= 1 or xs.max() >= w - 2 or ys.max() >= h - 2)
        clean = 0.0 if not len(xs) else (1.0 if 0.08 <= cover <= 0.85 else 0.4) * (0.6 if edge else 1.0)
        # one object, not a collage or a shelf of them: separate pieces at least a quarter the size of the biggest
        from scipy.ndimage import label as _label  # noqa: PLC0415

        lab, n_ = _label(m)
        sizes = np.bincount(lab.ravel())[1:] if n_ else np.array([0])
        objects = int((sizes >= 0.25 * sizes.max()).sum()) if n_ else 0
        if objects > 1:
            clean *= 0.35
        # printed text (a patent's front page, a poster, a document) is not a picture of the object: measured on a
        # design patent's pieces, "text" outscored "object" on every text block and on no drawing
        p_text, p_obj = zero_shot(img, ["a page of printed text", "a drawing or photograph of an object"])
        is_text = p_text > p_obj
        if is_text:
            clean = 0.0
        meta = {}
        if os.path.isfile(path + ".json"):
            with open(path + ".json", encoding="utf-8") as fh:
                meta = json.load(fh)
        is_not = None
        if nots:
            is_not = not_of(meta.get("title", ""), nots)
            if is_not is None:
                probs = zero_shot(img, [f"a photograph of {what}"] + [f"a photograph of {n}" for n in nots])
                is_not = not_of("", nots, probs[1:], probs[0])
        rows.append({"file": f, "view": best, "view_p": round(ps[best], 3), "views": {k: round(v, 3) for k, v in ps.items()},
                     "object_share": round(cover, 3), "objects": objects, "text": is_text, "cut_by_frame": edge,
                     "w": w, "h": h, "not": is_not,
                     "score": round(ps[best] * clean * min(1.0, min(w, h) / 800) * (NOT_SINK if is_not else 1.0), 4),
                     "license": meta.get("license"), "title": meta.get("title", "")[:80]})
    rows.sort(key=lambda r: -r["score"])
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"what": what, "ranked": rows}, fh, indent=1, ensure_ascii=False)
    # contact sheet: what the builder LOOKS at before picking (rank, view, licence on each)
    tw, th, cols = 260, 200, 4
    sheet = Image.new("RGB", (cols * tw, max(1, (len(rows) + cols - 1) // cols) * (th + 22)), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    for k, r in enumerate(rows):
        im = _rgb(os.path.join(folder, r["file"]))
        im.thumbnail((tw - 8, th - 8))
        x, y = (k % cols) * tw, (k // cols) * (th + 22)
        sheet.paste(im, (x + (tw - im.width) // 2, y + 4))
        d.text((x + 6, y + th + 2), ("TEXT | " if r["text"] else f"NOT {r['not']} | " if r.get("not") else
                                    f"#{k + 1} {r['view']} {r['view_p']:.2f} | ")
               + f"{r['license']} | {r['file'][:16]}", fill=(20, 20, 20))
    sheet.save(os.path.join(folder, "contact.png"))
    return rows


# ---------------------------------------------------------------------------------------------------------------- CLI
def _pairs(argv, flag):
    out = []
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            out.append(tuple(float(v) for v in argv[i + 1].split(",")))
    return out


def _out(argv, image, kind):
    if "-o" in argv:
        return argv[argv.index("-o") + 1]
    os.makedirs(os.path.join("build", "vision"), exist_ok=True)
    return os.path.join("build", "vision", f"{os.path.splitext(os.path.basename(image))[0]}_{kind}.png")


def _emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def doctor():
    torch, dev = _torch()
    rows, t_all = [], time.time()
    probe = Image.new("RGB", (96, 96), (240, 240, 240))
    probe.paste((30, 30, 30), (24, 24, 72, 72))
    for name, fn in (("teed", lambda: edges(probe)), ("birefnet", lambda: cutout(probe)),
                     ("sam2.1-hiera-small", lambda: mask(probe, points=[(48, 48)])),
                     ("depth-anything-v2-small", lambda: depth(probe)),
                     ("siglip2-base", lambda: zero_shot(probe, ["a dark square", "a red circle"])),
                     ("dinov2-reg-small", lambda: differ(probe, probe))):
        t0 = time.time()
        try:
            fn()
            rows.append(f"{name} ok ({time.time() - t0:.1f} s)")
        except Exception as e:  # noqa: BLE001 — the doctor reports, it never hides
            rows.append(f"{name} FAILED: {e}")
    bad = [r for r in rows if "FAILED" in r]
    gpu = torch.cuda.get_device_name(0) if dev == "cuda" else "no CUDA GPU (CPU: slower, same results)"
    return _emit("fail" if bad else "pass",
                 f"vision: torch {torch.__version__} on {gpu}; " + "; ".join(rows) + f" — {time.time() - t_all:.1f} s",
                 bad[0] if bad else "none — proceed (kit vision edges|cutout|mask|depth|similar|view|differ)", models=rows)


def main(argv):
    if not argv or argv[0] not in ("doctor", "edges", "cutout", "mask", "depth", "similar", "view", "differ", "rank",
                                   "alike", "taste", "relevance"):
        return _emit("fail", "vision: needs doctor | edges | cutout | mask | depth | similar | view | differ | rank | alike | taste | relevance",
                     "lune run kit vision doctor")
    cmd = argv[0]
    if cmd == "doctor":
        return doctor()
    if cmd == "relevance":  # yes/no scores for text prompts (kit/tools/parts_rerank.py): {"prompts": [...]} in a file
        if len(argv) < 2 or not os.path.isfile(argv[1]):
            return _emit("fail", "vision relevance: give the request file ({\"prompts\": [...]})",
                         "python kit/vision/run.py relevance <request.json>")
        import vlm  # noqa: PLC0415  (the model stays loaded in a warm worker: vlm's own cache)

        with open(argv[1], encoding="utf-8") as f:
            prompts = [str(p) for p in json.load(f).get("prompts", [])]
        return _emit("pass", f"vision relevance: {len(prompts)} prompt(s) scored", "none", scores=vlm.yes_scores(prompts))
    if cmd == "alike":  # search by look (kit/vision/alike.py), with this process's embed: the warm worker's loaded model
        import alike  # noqa: PLC0415

        return alike.main(argv[1:], embed=embed)
    if cmd == "taste":  # the taste model per lane (kit/vision/taste.py), on the same look index
        import taste  # noqa: PLC0415

        return taste.main(argv[1:], embed=embed)
    if cmd == "rank":
        if len(argv) < 2 or not os.path.isdir(argv[1]):
            return _emit("fail", "vision rank: give the folder kit refs find filled", "lune run kit refs rank build/refs/<slug>")
        what = argv[argv.index("--what") + 1] if "--what" in argv else "the object"
        nots = (argv[argv.index("--not") + 1] if "--not" in argv and argv.index("--not") + 1 < len(argv) else "").split(",")
        t0 = time.time()
        rows = rank(argv[1], what, nots)
        if not rows:
            return _emit("fail", f"vision rank: no pictures in {argv[1]}", "lune run kit refs find \"<object>\" first")
        top = ", ".join(f"#{k + 1} {r['view']} ({r['file'][:14]})" for k, r in enumerate(rows[:3]))
        sunk = sum(1 for r in rows if r.get("not"))
        return _emit("pass", f"refs rank: {len(rows)} picture(s) ranked for tracing — best: {top}"
                     + (f"; {sunk} sunk as --not" if sunk else "") + f" ({time.time() - t0:.1f} s)",
                     f"LOOK at {argv[1]}/contact.png, then: lune run kit refs pick {argv[1]} <#> --as <asset>_<view>",
                     out=os.path.join(argv[1], "contact.png").replace("\\", "/"), ranked=rows[:8])
    if len(argv) < 2 or not os.path.isfile(argv[1]):
        return _emit("fail", f"vision {cmd}: give an image file", f"lune run kit vision {cmd} refs/<photo>.png")
    image, t0 = argv[1], time.time()
    if cmd in ("similar", "differ") and (len(argv) < 3 or not os.path.isfile(argv[2])):
        return _emit("fail", f"vision {cmd}: give two image files", f"lune run kit vision {cmd} <a.png> <b.png>")
    if cmd == "similar":
        e = embed([image, argv[2]])
        sim = float(e[0] @ e[1])
        return _emit("pass", f"vision similar: {sim:.3f} (1 = the same look; unrelated pictures sit near 0)",
                     "none — proceed", similarity=round(sim, 4))
    if cmd == "view":
        what = argv[argv.index("--what") + 1] if "--what" in argv else "the object"
        best, ps = view_of(image, what)
        return _emit("pass", f"vision view: {best} (" + ", ".join(f"{k} {v:.2f}" for k, v in ps.items()) + ")",
                     "none — proceed", view=best, views={k: round(v, 4) for k, v in ps.items()})
    out = _out(argv, image, cmd)
    if cmd == "differ":
        d = differ(image, argv[2])
        heat = (np.clip(d / 0.6, 0, 1) * 255).astype(np.uint8)  # a fixed scale: 0.6 = completely different content
        Image.fromarray(heat).resize(_rgb(image).size, Image.NEAREST).save(out)
        return _emit("pass", f"vision differ: {out} (mean {d.mean():.3f}, worst patch {d.max():.3f}; bright = differs)",
                     f"look at {out}", out=out.replace("\\", "/"), mean=round(float(d.mean()), 4))
    if cmd == "edges":
        e = edges(image)
        v = np.clip((e - EDGE_FLAT) / (1 - EDGE_FLAT), 0, 1)  # a fixed mapping: paper white, lines dark
        Image.fromarray((255 * (1 - v)).astype(np.uint8)).save(out)
        info = f"{(e > EDGE_LINE).mean():.1%} of the image is line"
    elif cmd == "cutout":
        a = cutout(image)
        Image.fromarray((255 * a).clip(0, 255).astype(np.uint8)).save(out)
        if "--rgba" in argv:
            rgba = _rgb(image).convert("RGBA")
            rgba.putalpha(Image.fromarray((255 * a).clip(0, 255).astype(np.uint8)))
            rgba.save(out[:-4] + "_rgba.png")
        info = f"object = {(a > 0.5).mean():.1%} of the image"
    elif cmd == "mask":
        pts, neg, box = _pairs(argv, "--point"), _pairs(argv, "--neg"), _pairs(argv, "--box")
        if not pts and not box:
            return _emit("fail", "vision mask: needs --point x,y or --box x0,y0,x1,y1", "click ON the part: --point x,y")
        m, score = mask(image, points=pts or None, negatives=neg or None, box=box[0] if box else None)
        Image.fromarray(m.astype(np.uint8) * 255).save(out)
        ys, xs = np.nonzero(m)
        info = (f"part = {m.mean():.2%} of the image, score {score:.2f}"
                + (f", bbox x {xs.min()}-{xs.max()} y {ys.min()}-{ys.max()}" if len(xs) else ", EMPTY"))
    else:
        d = depth(image)
        Image.fromarray((255 * d).astype(np.uint8)).save(out)
        info = "bright = near"
    return _emit("pass", f"vision {cmd}: {out} ({info}, {time.time() - t0:.1f} s)",
                 f"look at {out}", out=out.replace("\\", "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
