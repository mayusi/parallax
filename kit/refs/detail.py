"""detail.py — `kit refs detail`: ONE SMALL PART of a reference picture traced at sub-pixel precision — a trigger, a
cog hammer, a screw head, a button, a charm — where the whole-object trace gives it a dozen blocky pixels. The part's
box is cropped, made 4x bigger with real detail (Real-ESRGAN: kit/vision/upscale.py), segmented there (its colour, a
dark / light threshold, or SAM 2.1 from a click), smoothed and traced at that scale, and handed back in the picture's
own millimetres. The owner on Scarborough Fair (2026-10-22): "we need to improve cad and the vision and tracing ...
to handle THE SMALLER details way better".

    lune run kit refs detail <picture> --box x0,y0,x1,y1 --name <name>
        (--hue lo-hi [--sat s] [--val v] | --dark <0-255> | --light <0-255> | --point x,y [--point ..] [--neg x,y ..])
        [--trace <trace.json> --length-mm L | --mm-per-px f] [--x 4] [--fast] [--no-model] [--sigma 1.2] [--eps 0.3]

--point: a click on the part in the PICTURE's pixels (SAM 2.1 on the upscaled crop: for a part the same colour as its
neighbours — a rose trigger on a rose frame); --neg: a click on what is NOT the part (the frame round it). --sigma / --eps: the smoothing and the polygon tolerance, in the
PICTURE's pixels (so 0.3 = a third of a source pixel). --no-model: Lanczos instead of Real-ESRGAN (tests; no GPU).
Writes assets/models/<name>.detail.json (outline + holes, mm, the trace's frame) and build/refs/<name>_detail.png
(the traced outline on the upscaled crop); prints one JSON line (summary / next_action).
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "kit", "vision"))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def enlarge(rgb, x=4, model=True, fast=False):
    """(H, W, 3) uint8 -> (H*x, W*x, 3) uint8: Real-ESRGAN when it loads, else Lanczos (said in the second value)"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    if model:
        try:
            import upscale  # noqa: PLC0415

            out, _how = upscale.upscale(Image.fromarray(rgb), x=x, kind="fast" if fast else "quality")
            arr = np.asarray(out.convert("RGB"))
            if arr.shape[0] == rgb.shape[0] * x:
                return arr, "Real-ESRGAN"
        except Exception:  # noqa: BLE001 — no torch / no weights / no room: Lanczos
            pass
    im = Image.fromarray(rgb).resize((rgb.shape[1] * x, rgb.shape[0] * x), Image.LANCZOS)
    return np.asarray(im), "Lanczos"


def part_mask(big, how, x):
    """the part's mask on the enlarged crop: how = ("hue", lo, hi, sat, val) | ("dark", t) | ("light", t) |
    ("point", [(px, py) in the crop's ENLARGED pixels])"""
    import numpy as np  # noqa: PLC0415

    kind = how[0]
    if kind == "hue":
        import inlays  # noqa: PLC0415

        return inlays.colour_mask(big, (how[1], how[2]), how[3], how[4])
    lum = big.astype(np.float32).mean(axis=2)
    if kind == "dark":
        return lum < how[1]
    if kind == "light":
        return lum > how[1]
    import run as vision  # noqa: PLC0415  (SAM 2.1)

    from PIL import Image  # noqa: PLC0415

    m, _score = vision.mask(Image.fromarray(big), points=how[1], negatives=how[2] if len(how) > 2 else None)
    return np.asarray(m, bool)


def trace(mask, x, sigma=1.2, eps=0.3, keep="largest"):
    """the enlarged mask -> [{"outline": [[x, y]...], "holes": [...]}] in SOURCE-picture pixels (sub-pixel): holes
    under a source pixel's worth filled, smoothed by sigma source px, simplified to eps source px (pure: test_detail.py)"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    m = mask.astype(np.uint8)
    n_, lab_, st_, _c = cv2.connectedComponentsWithStats((1 - m).astype(np.uint8), connectivity=4)
    for k in range(1, n_):
        if st_[k, cv2.CC_STAT_AREA] < x * x * 2:
            m[lab_ == k] = 1
    if sigma > 0:
        m = (cv2.GaussianBlur(m.astype(np.float32), (0, 0), sigma * x) > 0.5).astype(np.uint8)
    cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return []
    outers = [i for i in range(len(cs)) if hier[0][i][3] == -1]
    if keep == "largest":
        outers = [max(outers, key=lambda i: cv2.contourArea(cs[i]))]
    out = []
    for i in outers:
        if cv2.contourArea(cs[i]) < x * x * 4:
            continue
        o = cv2.approxPolyDP(cs[i], eps * x, True)[:, 0, :].astype(float) / x
        hs = [cv2.approxPolyDP(cs[j], eps * x, True)[:, 0, :].astype(float) / x for j in range(len(cs))
              if hier[0][j][3] == i and cv2.contourArea(cs[j]) > x * x * 4]
        out.append({"outline": o.tolist(), "holes": [h.tolist() for h in hs if len(h) >= 3]})
    return out


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageDraw  # noqa: PLC0415

    if not argv or argv[0].startswith("--") or "--box" not in argv or "--name" not in argv:
        return emit("fail", "refs detail: needs <picture> --box x0,y0,x1,y1 --name <name> and --hue / --dark / --light / "
                    "--point", "lune run kit refs detail refs/x/side.png --box 1870,850,2000,1070 --name x_trigger "
                    "--point 1930,960 --trace assets/models/x_side.trace.json --length-mm 280")
    pic, name = argv[0], _arg(argv, "--name")
    if not os.path.isfile(pic):
        return emit("fail", f"refs detail: {pic} not found", "give the picture's path")
    src = np.asarray(Image.open(pic).convert("RGB"))
    x0, y0, x1, y1 = (int(float(v)) for v in _arg(argv, "--box").split(","))
    pad = 6
    cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
    crop = src[cy0:min(src.shape[0], y1 + pad), cx0:min(src.shape[1], x1 + pad)]
    x = int(_arg(argv, "--x", 4))
    big, how_up = enlarge(crop, x, model="--no-model" not in argv, fast="--fast" in argv)
    if "--hue" in argv:
        lo, hi = (float(v) for v in _arg(argv, "--hue").split("-"))
        how = ("hue", lo, hi, float(_arg(argv, "--sat", 0.25)), float(_arg(argv, "--val", 0.25)))
    elif "--dark" in argv:
        how = ("dark", float(_arg(argv, "--dark")))
    elif "--light" in argv:
        how = ("light", float(_arg(argv, "--light")))
    elif "--point" in argv:
        pts = [argv[i + 1] for i, a in enumerate(argv) if a == "--point"]
        negs = [argv[i + 1] for i, a in enumerate(argv) if a == "--neg"]
        to_big = lambda q: ((float(q.split(",")[0]) - cx0) * x, (float(q.split(",")[1]) - cy0) * x)  # noqa: E731
        how = ("point", [to_big(p) for p in pts], [to_big(q) for q in negs] or None)
    else:
        return emit("fail", "refs detail: say how to find the part: --hue lo-hi | --dark t | --light t | --point x,y",
                    "a part the same colour as its neighbours: --point on it (SAM 2.1)")
    try:
        mask = part_mask(big, how, x)
    except Exception as e:  # noqa: BLE001
        return emit("fail", f"refs detail: the mask failed ({str(e)[:160]})", "try --hue / --dark instead of --point")
    pieces = trace(mask, x, float(_arg(argv, "--sigma", 1.2)), float(_arg(argv, "--eps", 0.3)),
                   "all" if "--all" in argv else "largest")
    if not pieces:
        return emit("fail", f"refs detail {name}: nothing traced in the box", "check the box / the colour / the click")
    if "--trace" in argv:
        with open(_arg(argv, "--trace"), encoding="utf-8") as fh:
            fr = json.load(fh)["frame"]
        if "--length-mm" not in argv:
            return emit("fail", "refs detail: --trace needs --length-mm", "add --length-mm <the object's length>")
        mpp, ox, oy = float(_arg(argv, "--length-mm")) / float(fr["length_px"]), float(fr["x0"]), float(fr["y1"])
    else:
        mpp, ox, oy = float(_arg(argv, "--mm-per-px", 0) or 0), float(x0), float(y1)
        if mpp <= 0:
            return emit("fail", "refs detail: give --trace <trace.json> --length-mm L, or --mm-per-px f",
                        "the trace of the same picture gives the mm frame")

    def mm(pts):
        return [[round((px + cx0 - ox) * mpp, 4), round((oy - (py + cy0)) * mpp, 4)] for px, py in pts]

    out = [{"outline": mm(p["outline"]), "holes": [mm(h) for h in p["holes"]]} for p in pieces]
    dest = os.path.join(REPO, "assets", "models", f"{name}.detail.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump({"source": pic.replace(os.sep, "/"), "box": [x0, y0, x1, y1], "upscale": f"{how_up} x{x}",
                   "mm_per_px": mpp, "frame": "x mm from the frame's left (the trace's x0), y mm up from its bottom",
                   "pieces": out}, fh)
    prev = Image.fromarray(big).convert("RGB")
    dr = ImageDraw.Draw(prev)
    for p in pieces:
        dr.line([(px * x, py * x) for px, py in p["outline"]] + [(p["outline"][0][0] * x, p["outline"][0][1] * x)],
                fill=(0, 255, 255), width=2)
    pv = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", f"{name}_detail.png")
    os.makedirs(os.path.dirname(pv), exist_ok=True)
    prev.save(pv)
    rel = lambda p: os.path.relpath(p, REPO).replace(os.sep, "/")  # noqa: E731
    npts = sum(len(p["outline"]) for p in out)
    return emit("pass", f"refs detail {name}: {len(out)} piece(s), {npts} points at 1/{x} px ({how_up}) -> {rel(dest)}",
                f"LOOK at {rel(pv)}; build it: a.cad with cad_parts.outline() on the outline, round_mm= for soft edges",
                preview=rel(pv), upscale=how_up)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
