"""inventory.py — `kit refs inventory`: EVERY small detail of a reference picture listed, boxed and graded for how
well the picture shows it — the SHOT LIST an artist writes before modelling (the owner, 2026-10-22: "improve the 3D
models reference collecting and visions and especially for details"). A local vision-language model (Qwen3-VL-4B:
kit/vision/vlm.py) names each detail and boxes it; SAM 2.1 tightens each box to the detail's own mask (--masks); the
picture's mm frame gives each detail its size and the pixels it gets. Run it on every picture of the asset: the
details.json merges them, and a detail no picture shows well enough is a CLOSE-UP to find before modelling.

    lune run kit refs inventory <picture> --name <asset> [--what "a revolver"] [--trace <t> --length-mm L |
        --mm-per-px f] [--n 30] [--passes details] [--parts "hammer,trigger"] [--masks] [--boxes <list.json>] [--bar 2.0] [--min-px 48]

Each detail gets a status: ok (>= --min-px across and >= --bar px/mm: trace it here), upscale (16 px .. --min-px: trace
it with kit refs detail --x 4), close-up (under 16 px, or the picture under the bar: find a sharper picture of it).
Writes assets/models/<asset>.details.json (per picture + the merged shot list) and build/refs/<asset>_inventory.png
(the picture with numbered boxes coloured by status, and every detail's crop); prints one JSON line.
--passes: which lists to ask the VLM for (details, default: decoration, fasteners, text; parts: the pieces a modeller
builds — a 4B model pins the prompt's names on wrong boxes: prefer --parts). --parts "hammer,trigger,chain": NAMED
parts found by SAM 3 from the words (every match, its mask's box). A shared
GPU short of ~10 GB loads the model in 4 bits (KIT_VLM_QUANT=bf16|4bit forces one).
--boxes: a list of {"label", "kind", "box"} instead of the model (a hand list, a test); --out: the details file's path.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "kit", "vision"))

UPSCALE_PX = 16
COLOURS = {"ok": (40, 200, 90), "upscale": (240, 170, 30), "close-up": (230, 50, 60)}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def key(label):
    """a detail's merge key across pictures: lower case, plural / number / punctuation dropped ("Screws #2" = "screw")"""
    k = re.sub(r"[^a-z ]+", " ", label.lower())
    k = " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in k.split())
    return k or "detail"


GENERIC = {"part", "parts", "detail", "details", "object", "other", "component", "piece", "item", "thing"}


def generic(label):
    """a label that names nothing ("part", "other", a bare kind): the model listing its own categories, not a detail"""
    w = label.strip().lower()
    return w in GENERIC or w in {"edge", "texture", "opening", "control", "panel"}


KIND_OF = {"screw": "fastener", "pin": "fastener", "rivet": "fastener", "bolt": "fastener", "gem": "gem",
           "jewel": "gem", "stone": "gem", "sight": "sight", "chain": "chain", "ring": "chain", "charm": "chain",
           "trigger": "control", "hammer": "control", "lever": "control", "button": "control", "safety": "control",
           "grip": "panel", "panel": "panel", "trim": "trim", "logo": "logo", "text": "text", "engraving": "engraving"}


def named_parts(pic, phrases, keep=0.3):
    """SAM 3 (kit trace --part-text's engine, in the TRELLIS.2 environment) -> one row per match of each phrase:
    its mask's box, "hammer", "screw #2" ..."""
    import importlib.util  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("kit_trace", os.path.join(REPO, "kit", "blender", "trace.py"))
    tr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tr)
    out = []
    for ph, matches in tr.text_masks(pic, phrases, keep=keep).items():
        for k, (score, m) in enumerate(matches, 1):
            ys, xs = np.nonzero(m)
            if len(xs) < 9:
                continue
            kind = next((v for w, v in KIND_OF.items() if w in ph.lower()), "other")
            out.append({"label": ph if k == 1 else f"{ph} #{k}", "kind": kind, "pass": "sam3",
                        "box": [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)],
                        "note": f"SAM 3 score {score:.2f}"})
    return out


def object_box(img, tol=30.0):
    """the object's box on its backdrop (pixels away from the border colour), or None on a busy photo"""
    import numpy as np  # noqa: PLC0415

    a = np.asarray(img.convert("RGB")).astype(np.float32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    if float(np.median(np.linalg.norm(border - bg, axis=1))) > tol:  # (no plain backdrop)
        return None
    m = np.linalg.norm(a - bg, axis=2) > tol
    ys, xs = np.nonzero(m)
    if len(xs) < 50:
        return None
    return [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]


def whole(d, obj, what=()):
    """the WHOLE object, not a detail: a box covering most of the object (or 85% of the picture without one), or a
    label that is the object's own name (--what)"""
    x0, y0, x1, y1 = d["box"]
    if what and set(key(d["label"]).split()) & set(what) and obj is not None:
        if (x1 - x0) * (y1 - y0) > 0.3 * (obj[2] - obj[0]) * (obj[3] - obj[1]):
            return True
    if obj is not None:
        ox = max(0.0, min(x1, obj[2]) - max(x0, obj[0]))
        oy = max(0.0, min(y1, obj[3]) - max(y0, obj[1]))
        return ox >= 0.8 * (obj[2] - obj[0]) and oy >= 0.8 * (obj[3] - obj[1])
    return False


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def grade(box, mm_per_px=None, bar=2.0, min_px=48):
    """one detail's px across, size (mm) and status (pure)"""
    w, h = box[2] - box[0], box[3] - box[1]
    across = min(w, h)
    ppm = (1.0 / mm_per_px) if mm_per_px else None
    if across < UPSCALE_PX or (ppm is not None and ppm < bar):
        status = "close-up"
    elif across < min_px:
        status = "upscale"
    else:
        status = "ok"
    row = {"px_across": round(across, 1), "status": status}
    if mm_per_px:
        row.update(size_mm=[round(w * mm_per_px, 2), round(h * mm_per_px, 2)], px_per_mm=round(ppm, 2))
    return row


def merge(shot, source, rows):
    """fold one picture's graded details into the asset's shot list: per detail, its BEST picture"""
    rank = {"close-up": 0, "upscale": 1, "ok": 2}
    for r in rows:
        k = key(r["label"])
        cur = shot.get(k)
        cand = {"label": r["label"], "kind": r["kind"], "status": r["status"], "px_across": r["px_across"],
                "best": source, "box": r["box"]}
        if cur is None or (rank[r["status"]], r["px_across"]) > (rank[cur["status"]], cur["px_across"]):
            cand["seen_in"] = sorted(set((cur or {}).get("seen_in", [])) | {source})
            shot[k] = cand
        else:
            cur["seen_in"] = sorted(set(cur.get("seen_in", [])) | {source})
    return shot


def refine(img, rows):
    """SAM 2.1 on each box: the detail's own mask -> its tight box and its area share of the box"""
    import numpy as np  # noqa: PLC0415

    import run as vision  # noqa: PLC0415

    for r in rows:
        try:
            m, _s = vision.mask(img, box=[int(v) for v in r["box"]])
        except Exception as e:  # noqa: BLE001
            r["mask"] = f"failed: {str(e)[:80]}"
            continue
        m = np.asarray(m, bool)
        ys, xs = np.nonzero(m)
        if len(xs) < 4:
            continue
        x0, y0, x1, y1 = r["box"]
        tight = [float(max(x0, xs.min())), float(max(y0, ys.min())), float(min(x1, xs.max() + 1)),
                 float(min(y1, ys.max() + 1))]
        if (tight[2] - tight[0]) > 2 and (tight[3] - tight[1]) > 2:
            r["box_vlm"], r["box"] = r["box"], [round(v, 1) for v in tight]
    return rows


def sheet(img, rows, path):
    from PIL import Image, ImageDraw  # noqa: PLC0415

    W = 1400
    k = min(1.0, W / img.width)
    top = img.convert("RGB").resize((round(img.width * k), round(img.height * k)))
    dr = ImageDraw.Draw(top)
    for i, r in enumerate(rows, 1):
        b = [v * k for v in r["box"]]
        dr.rectangle(b, outline=COLOURS[r["status"]], width=2)
        dr.text((b[0] + 2, b[1] + 1), str(i), fill=COLOURS[r["status"]])
    cell, cols = 170, max(1, W // 170)
    nrow = (len(rows) + cols - 1) // cols
    out = Image.new("RGB", (max(W, top.width), top.height + nrow * (cell + 18) + 4), (24, 24, 28))
    out.paste(top, (0, 0))
    d2 = ImageDraw.Draw(out)
    for i, r in enumerate(rows):
        x0, y0, x1, y1 = r["box"]
        pad = 0.15 * max(x1 - x0, y1 - y0)
        crop = img.convert("RGB").crop((int(max(0, x0 - pad)), int(max(0, y0 - pad)), int(min(img.width, x1 + pad)),
                                        int(min(img.height, y1 + pad))))
        s = cell / max(crop.size)
        crop = crop.resize((max(1, round(crop.width * s)), max(1, round(crop.height * s))), Image.LANCZOS)
        cx, cy = (i % cols) * cell, top.height + 4 + (i // cols) * (cell + 18)
        out.paste(crop, (cx, cy))
        d2.text((cx + 2, cy + cell + 2), f"{i + 1} {r['label'][:20]} ({r['status']})", fill=COLOURS[r["status"]])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path)


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    from PIL import Image  # noqa: PLC0415

    if not argv or argv[0].startswith("--") or "--name" not in argv:
        return emit("fail", "refs inventory: needs <picture> --name <asset>",
                    'lune run kit refs inventory refs/x_side.png --name x --what "a revolver" '
                    "--trace assets/models/x_side.trace.json --length-mm 280 --masks")
    pic, name = argv[0], _arg(argv, "--name")
    if not os.path.isfile(pic):
        return emit("fail", f"refs inventory: {pic} not found", "give the picture's path")
    img = Image.open(pic).convert("RGB")
    mpp = float(_arg(argv, "--mm-per-px", 0) or 0) or None
    if "--trace" in argv:
        with open(_arg(argv, "--trace"), encoding="utf-8") as fh:
            fr = json.load(fh)["frame"]
        if "--length-mm" not in argv:
            return emit("fail", "refs inventory: --trace needs --length-mm", "add --length-mm <the object's length>")
        mpp = float(_arg(argv, "--length-mm")) / float(fr["length_px"])
    raw = ""
    if "--boxes" in argv:
        with open(_arg(argv, "--boxes"), encoding="utf-8") as fh:
            found = json.load(fh)
        how = "hand list"
    elif _arg(argv, "--passes") == "none":  # (SAM 3 --parts only)
        found, how = [], "no VLM"
    else:
        import vlm  # noqa: PLC0415

        passes_explicit = "--passes" in argv
        if not vlm.installed() and not passes_explicit:
            # VLM not installed and the caller did not force a pass list: skip VLM passes, fall through to --parts /
            # --boxes only.  An explicit --passes still tries and raises (the caller asked for it).
            print(json.dumps({"schema": 1, "status": "warn",
                              "summary": "refs inventory: the vision model (qwen3-vl-4b) is not installed; VLM passes "
                                         "skipped (use --passes to force, or install: lune run kit vision setup qwen3-vl-4b)",
                              "next_action": "continue with --parts or --boxes, or install the VLM"}))
            found, how = [], "no VLM (not installed)"
        else:
            try:
                import time  # noqa: PLC0415

                t0 = time.time()
                found, raw = vlm.details(img, _arg(argv, "--what", "the object"), int(_arg(argv, "--n", 30)),
                                         passes=tuple(_arg(argv, "--passes", "details").split(",")))
                secs = round(time.time() - t0, 1)
                quant = vlm._M.get("quant")
                vlm.free()
            except Exception as e:  # noqa: BLE001
                return emit("fail", f"refs inventory: the vision-language model failed ({str(e)[:200]})",
                            "lune run kit vision setup qwen3-vl-4b; free the GPU (nvidia-smi); or --boxes <list.json>")
            how = f"Qwen3-VL-4B ({quant}, {secs} s)"
    if "--parts" in argv:  # NAMED parts by SAM 3 (words -> masks): far surer than a small VLM naming boxes
        try:
            found = found + named_parts(pic, [w.strip() for w in _arg(argv, "--parts").split(",") if w.strip()])
        except Exception as e:  # noqa: BLE001
            return emit("fail", f"refs inventory: SAM 3 (--parts) failed ({str(e)[:200]})",
                        "check the TRELLIS.2 environment (kit/gen/README.md), or leave --parts out")
        how += " + SAM 3 parts"
    obj = object_box(img)
    what = set(key(_arg(argv, "--what", "")).split())
    rows = []
    for d in found:  # (the VLM's and SAM 3's finds of one detail: the same name over the same place, kept once)
        if generic(d["label"]) or whole(d, obj, what):
            continue
        dup = next((o for o in rows if key(o["label"]) == key(d["label"]) and _iou(o["box"], d["box"]) > 0.6), None)
        if dup is not None:
            if d.get("pass") == "sam3" and dup.get("pass") != "sam3":  # (SAM 3's mask box is the tighter one)
                dup["box"], dup["pass"] = list(d["box"]), "vlm+sam3"
            continue
        rows.append({"label": d["label"], "kind": d.get("kind", "other"), "box": list(d["box"]),
                     "note": d.get("note", ""), **({"pass": d["pass"]} if d.get("pass") else {})})
    if not rows:
        return emit("fail", f"refs inventory {name}: no details found ({how})",
                    "a sharper / bigger picture, or --boxes with a hand list")
    if "--masks" in argv:
        refine(img, rows)
    bar, min_px = float(_arg(argv, "--bar", 2.0)), float(_arg(argv, "--min-px", 48))
    for r in rows:
        r.update(grade(r["box"], mpp, bar, min_px))
        if r["status"] != "close-up":
            b = ",".join(str(int(round(v))) for v in r["box"])
            frame = (f" --trace {_arg(argv, '--trace')} --length-mm {_arg(argv, '--length-mm')}" if "--trace" in argv
                     else (f" --mm-per-px {mpp:g}" if mpp else ""))
            r["trace_cmd"] = (f"lune run kit refs detail {pic} --box {b} --name {name}_{key(r['label']).replace(' ', '_')}"
                              f" --point {int((r['box'][0] + r['box'][2]) / 2)},{int((r['box'][1] + r['box'][3]) / 2)}"
                              f"{frame}")
    dest = _arg(argv, "--out") or os.path.join(REPO, "assets", "models", f"{name}.details.json")
    try:
        with open(dest, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {"schema": 1, "pictures": {}, "shot_list": {}}
    src = pic.replace(os.sep, "/")
    doc["pictures"][src] = {"how": how, "mm_per_px": mpp, "size_px": [img.width, img.height], "details": rows}
    shot = {}
    for s, p in doc["pictures"].items():
        merge(shot, s, p["details"])
    doc["shot_list"] = shot
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    if raw:
        rawp = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", f"{name}_inventory_raw.txt")
        os.makedirs(os.path.dirname(rawp), exist_ok=True)
        with open(rawp, "w", encoding="utf-8") as fh:
            fh.write(raw)
    pv = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", f"{name}_inventory.png")
    sheet(img, rows, pv)
    count = {s: sum(1 for r in shot.values() if r["status"] == s) for s in COLOURS}
    rel = lambda p: os.path.relpath(p, REPO).replace(os.sep, "/")  # noqa: E731
    # (labels came from a model reading a PICTURE: only their letters go into the advice — never raw text)
    need = [key(r["label"]) for r in shot.values() if r["status"] == "close-up"]
    private = "private" in src.lower()
    return emit("pass", f"refs inventory {name}: {len(rows)} details in this picture ({how}); shot list over "
                f"{len(doc['pictures'])} picture(s): {count['ok']} ok, {count['upscale']} upscale, "
                f"{count['close-up']} need a close-up" + (" (PRIVATE source: never commit the details file)"
                                                          if private else ""),
                (f"LOOK at {rel(pv)}; find close-ups of: {', '.join(need[:8])}" if need else
                 f"LOOK at {rel(pv)}; trace each detail with its trace_cmd in {rel(dest)}"),
                sheet=rel(pv), details=rel(dest), counts=count)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
