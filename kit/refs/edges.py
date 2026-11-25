"""edges.py — how ROUND every edge is, MEASURED off a picture (the owner, 2026-10-22: "when I meant details I didn't
only mean the jewel ... the edges etc too, everything on anything we ever work on"). A sharp edge is a step in the
picture one pixel wide; a rounded edge is a ramp as wide as its round seen side-on (the curve turns away from the
light over its radius). So across every strong edge the kit measures the RAMP's width (the 10-90% rise of the
intensity along the gradient), and turns it into a radius in mm with a calibration rendered in Blender on slabs of
known rounds (kit/blender/edge_calibrate.py; CAL below).

    w, m = edge_widths(gray)                 per edge pixel: its ramp width (px) and the edge mask (pure numpy / cv2)
    radius_mm(width_px, mm_per_px)           the calibrated radius
    lune run kit refs edges <picture> --name <asset> (--trace <t> --length-mm L | --mm-per-px f) [--parts <parts.json>]
        [--box x0,y0,x1,y1]
        -> assets/models/<asset>.edges.json: per part (or the whole object) the median radius (+- the
           calibration's error), the share of sharp / soft / round edges, the suggested a.cad round_mm; build/refs/<asset>_edges.png (a heat map:
           blue sharp -> red round)
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# width_mm = alpha x radius + beta x mm_per_px + gamma — fitted by kit/tools/edge_calibrate.py on Blender slabs
# rounded 0 / 0.5 / 1 / 2 / 3 / 4 mm under the kit's ortho studio light, at two scales (the anti-aliasing adds
# ~1.5 px to every edge: beta). Worst error +-0.45 mm at 0.11 mm/px, +-0.8 mm at 0.24 mm/px ("err_mm").
CAL = {"alpha": 0.3704, "beta": 0.066, "gamma": 0.1183, "err_mm": 0.8,
       "source": "kit/tools/edge_calibrate.py 2026-10-22 (defaults)"}
_CAL_FILE = os.path.join(HERE, "edges_cal.json")
if os.path.isfile(_CAL_FILE):
    with open(_CAL_FILE, encoding="utf-8") as _fh:
        CAL = json.load(_fh)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def edge_widths(gray, thresh=None, reach=24, step=4):
    """(H, W) grey -> (widths px (H, W) float, nan off edges; edge mask). An edge pixel = a local maximum of the
    gradient magnitude (Canny); its width = the distance between where the intensity has risen 10% and 90% of the
    way across it, sampled along the gradient +-reach px (sub-pixel, linear interpolation). Every `step`-th edge
    pixel is measured (a map, not a census)."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    g = gray.astype(np.float32)
    gs = cv2.GaussianBlur(g, (0, 0), 0.6)
    gx = cv2.Sobel(gs, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gs, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    if thresh is None:
        thresh = max(20.0, float(np.percentile(mag, 90)))
    u8 = np.clip(gs, 0, 255).astype(np.uint8)
    can = cv2.Canny(u8, thresh * 0.4, thresh) > 0
    H, W = g.shape
    out = np.full((H, W), np.nan, np.float32)
    ys, xs = np.nonzero(can)
    if len(xs) == 0:
        return out, can
    sel = np.arange(0, len(xs), step)
    ts = np.linspace(-reach, reach, 4 * reach + 1)
    for i in sel:
        y, x = ys[i], xs[i]
        m = mag[y, x]
        if m < 1e-3:
            continue
        dx, dy = gx[y, x] / m, gy[y, x] / m
        px, py = x + dx * ts, y + dy * ts
        # (an edge near the picture's border: the border's own value carries on past it)
        prof = cv2.remap(g, px.astype(np.float32)[None, :], py.astype(np.float32)[None, :], cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REPLICATE)[0]
        lo, hi = float(np.median(prof[:reach])), float(np.median(prof[-reach:]))
        span = hi - lo
        if span < 12:  # (a faint edge: no ramp to measure)
            continue
        f = (prof - lo) / span
        mid = 2 * reach  # (the edge pixel itself)
        # walk out from the edge pixel to the first sample under 10% and over 90% (the ramp around THIS edge)
        a = mid
        while a > 0 and f[a] > 0.1:
            a -= 1
        b = mid
        while b < len(f) - 1 and f[b] < 0.9:
            b += 1
        if a == 0 or b == len(f) - 1:
            continue
        ta = ts[a] + (0.1 - f[a]) / max(f[a + 1] - f[a], 1e-6) * (ts[a + 1] - ts[a])
        tb = ts[b - 1] + (0.9 - f[b - 1]) / max(f[b] - f[b - 1], 1e-6) * (ts[b] - ts[b - 1])
        out[y, x] = max(0.0, tb - ta)
    return out, can


def radius_mm(width_px, mm_per_px):
    """a ramp's width -> the round's radius (mm), by the Blender calibration (+- CAL["err_mm"])"""
    return max(0.0, (width_px * mm_per_px - CAL["beta"] * mm_per_px - CAL["gamma"]) / CAL["alpha"])


def summarise(widths, mask, mm_per_px):
    """the measured edges of a region -> median radius, the share sharp (< 0.3 mm) / soft (0.3-1.2) / round (> 1.2)"""
    import numpy as np  # noqa: PLC0415

    w = widths[mask & ~np.isnan(widths)]
    if len(w) < 8:
        return None
    r = np.array([radius_mm(v, mm_per_px) for v in w])
    return {"samples": int(len(r)), "radius_mm": round(float(np.median(r)), 2),
            "p75_mm": round(float(np.percentile(r, 75)), 2),
            "sharp": round(float((r < 0.3).mean()), 2), "soft": round(float(((r >= 0.3) & (r <= 1.2)).mean()), 2),
            "round": round(float((r > 1.2).mean()), 2)}


def heat(rgb, widths, mm_per_px, path):
    """the picture greyed with every measured edge coloured by its radius: blue sharp -> red round"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    base = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB) // 2
    ys, xs = np.nonzero(~np.isnan(widths))
    for y, x in zip(ys, xs):
        r = radius_mm(float(widths[y, x]), mm_per_px)
        t = min(1.0, r / 3.0)
        col = (int(255 * t), int(80 * (1 - abs(t - 0.5) * 2)), int(255 * (1 - t)))
        cv2.circle(base, (int(x), int(y)), 2, col, -1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(base).save(path)


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def _part_masks(argv, shape, mpp, ox, oy):
    """--parts <file>: {"parts": {name: [[x, y] mm ...]}} or a .inlays / .detail / trace file's pieces -> masks"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    if "--parts" not in argv:
        return {}
    with open(_arg(argv, "--parts"), encoding="utf-8") as fh:
        doc = json.load(fh)
    polys = {}
    if isinstance(doc.get("parts"), dict):
        polys = doc["parts"]
    elif isinstance(doc.get("pieces"), list):
        polys = {f"piece{i}": p["outline"] for i, p in enumerate(doc["pieces"])}
    return part_masks(polys, shape, mpp, ox, oy)


def part_masks(polys, shape, mpp, ox, oy):
    """{name: outline | {"outline", "holes"} | [pieces]} in the picture's mm frame (x from ox, y up from oy) -> masks
    (each grown 2 px: its outline's own edge pixels belong to it)"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    def px(pts):
        return np.array([[ox + x / mpp, oy - y / mpp] for x, y in pts], np.int32)
    out = {}
    for name, val in polys.items():
        pieces = val if isinstance(val, list) and val and isinstance(val[0], dict) else [val]
        m = np.zeros(shape, np.uint8)
        for pc in pieces:
            outline = pc.get("outline", []) if isinstance(pc, dict) else pc
            if len(outline) < 3:
                continue
            cv2.fillPoly(m, [px(outline)], 1)
            for h in (pc.get("holes", []) if isinstance(pc, dict) else []):
                if len(h) >= 3:
                    cv2.fillPoly(m, [px(h)], 0)
        if m.any():
            out[name] = cv2.dilate(m, np.ones((5, 5), np.uint8)) > 0
    return out


def main(argv):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    if not argv or argv[0].startswith("--") or "--name" not in argv:
        return emit("fail", "refs edges: needs <picture> --name <asset> (--trace <t> --length-mm L | --mm-per-px f)",
                    "lune run kit refs edges refs/x_side.png --name x --trace assets/models/x_side.trace.json "
                    "--length-mm 280")
    pic, name = argv[0], _arg(argv, "--name")
    if not os.path.isfile(pic):
        return emit("fail", f"refs edges: {pic} not found", "give the picture's path")
    rgb = np.asarray(Image.open(pic).convert("RGB"))
    if "--trace" in argv:
        with open(_arg(argv, "--trace"), encoding="utf-8") as fh:
            fr = json.load(fh)["frame"]
        if "--length-mm" not in argv:
            return emit("fail", "refs edges: --trace needs --length-mm", "add --length-mm <the object's length>")
        mpp, ox, oy = float(_arg(argv, "--length-mm")) / float(fr["length_px"]), float(fr["x0"]), float(fr["y1"])
    else:
        mpp, ox, oy = float(_arg(argv, "--mm-per-px", 0) or 0), 0.0, float(rgb.shape[0])
        if mpp <= 0:
            return emit("fail", "refs edges: give --trace <trace.json> --length-mm L, or --mm-per-px f",
                        "the trace of the same picture gives the mm frame")
    gray = np.asarray(Image.open(pic).convert("L"))
    widths, _can = edge_widths(gray)
    region = np.ones(gray.shape, bool)
    if "--box" in argv:
        x0, y0, x1, y1 = (int(float(v)) for v in _arg(argv, "--box").split(","))
        region[:] = False
        region[y0:y1, x0:x1] = True
    widths[~region] = np.nan
    parts = {"whole": summarise(widths, region, mpp)}
    for pn, m in _part_masks(argv, gray.shape, mpp, ox, oy).items():
        s = summarise(widths, m & region, mpp)
        if s:
            parts[pn] = s
    for s in parts.values():
        if s:  # the suggestion for a.cad: the part's typical round (its median), never under 0.2 mm
            s["round_mm"] = round(max(0.2, s["radius_mm"]), 2)
    dest = _arg(argv, "--out") or os.path.join(REPO, "assets", "models", f"{name}.edges.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump({"source": pic.replace(os.sep, "/"), "mm_per_px": mpp, "calibration": CAL.get("source"),
                   "uncertainty_mm": CAL.get("err_mm"),
                   "parts": parts}, fh, indent=1)
    pv = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", f"{name}_edges.png")
    heat(rgb, widths, mpp, pv)
    rel = lambda p: os.path.relpath(p, REPO).replace(os.sep, "/")  # noqa: E731
    w = parts["whole"] or {}
    return emit("pass", f"refs edges {name}: median round {w.get('radius_mm')} mm over {w.get('samples')} edge "
                f"samples (+-{CAL.get('err_mm')} mm; {w.get('sharp', 0):.0%} sharp, {w.get('soft', 0):.0%} soft, {w.get('round', 0):.0%} round)"
                + (f"; {len(parts) - 1} part(s)" if len(parts) > 1 else ""),
                f"LOOK at {rel(pv)} (blue sharp -> red round); build each part with its round_mm from {rel(dest)}",
                edges=rel(dest), heat=rel(pv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
