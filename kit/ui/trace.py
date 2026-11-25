"""trace.py — a UI piece TRACED from a reference picture: crop at 1:1, upscale (Real-ESRGAN), cut out (BiRefNet),
and for a gauge plate: find the green cells, blank them to empty wells and write their anchors. The reference's
own pixels are the art — that is how a replica is 1:1. A repaint (Qwen-Image-Edit) is an optional pass on top.

    python kit/ui/trace.py <identity>/<piece> --from <picture> --box x,y,w,h [--x 4] [--cutout] [--gauge]
                           [--pad 2] [--repaint "<instruction>"] [--art assets/ui/art]

Writes assets/ui/art/<identity>/<piece>.png (+ <piece>.anchors.json for --gauge) and <piece>.trace.json (the
source, the box, the scale: provenance, and what kit ui gauge lays the other pieces out from).
"""
import argparse
import json
import os
import subprocess
import sys

from PIL import Image

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KIT)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def green_mask(im):
    """the lit green cells of a character-action-style gauge: saturated green, not the plate's grey-green"""
    px = im.convert("RGB").load()
    w, h = im.size
    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if g > 120 and g > r + 50 and g > b + 50:
                mp[x, y] = 255
    return mask


def cells_from_mask(mask, min_w=6, min_h=3, gap=2):
    """connected green runs -> rows of cell rectangles (left to right, top to bottom). Thin dark seams between
    cells blur shut after an upscale: the mask is eroded sideways by `gap` px first so every seam opens, and the
    cells are widened back by the same amount."""
    from PIL import ImageChops
    w, h = mask.size
    if gap > 0:
        left = ImageChops.offset(mask, -gap, 0)
        right = ImageChops.offset(mask, gap, 0)
        mask = ImageChops.multiply(ImageChops.multiply(mask, left), right)
    mp = mask.load()
    # row bands: y ranges with any green
    ys = [y for y in range(h) if any(mp[x, y] for x in range(w))]
    bands, s, p = [], None, None
    for y in ys:
        if s is None:
            s = p = y
        elif y - p > 2:
            bands.append((s, p))
            s = p = y
        else:
            p = y
    if s is not None:
        bands.append((s, p))
    rows = []
    for (y0, y1) in bands:
        if y1 - y0 + 1 < min_h:
            continue
        xs = [x for x in range(w) if any(mp[x, y] for y in range(y0, y1 + 1))]
        cells, cs, cp = [], None, None
        for x in xs:
            if cs is None:
                cs = cp = x
            elif x - cp > 2:
                cells.append((cs, cp))
                cs = cp = x
            else:
                cp = x
        if cs is not None:
            cells.append((cs, cp))
        rects = []
        for (x0, x1) in cells:
            if x1 - x0 + 1 < min_w:
                continue
            # the cell's own vertical extent (rows lean: measure per cell)
            cy = [y for y in range(y0, y1 + 1) if any(mp[x, y] for x in range(x0, x1 + 1))]
            rects.append({"x": x0, "y": min(cy), "w": x1 - x0 + 1, "h": max(cy) - min(cy) + 1})
        if rects:
            # slivers at a row's end (a cap's green glint, a cut cell) are not wells: keep cells near the median width
            widths = sorted(r["w"] for r in rects)
            med = widths[len(widths) // 2]
            rects = [r for r in rects if r["w"] >= med * 0.55 and r["h"] >= 3]
            for r in rects:
                r["x"], r["w"] = max(0, r["x"] - gap), r["w"] + 2 * gap
            if rects:
                rows.append(rects)
    return rows


def blank_cells(im, rows, ring=3):
    """paint each green cell with the dark well colour sampled just outside it (the plate's own trough)"""
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    for rects in rows:
        for c in rects:
            samples = []
            for y in range(max(0, c["y"] - ring), min(h, c["y"] + c["h"] + ring)):
                for x in range(max(0, c["x"] - ring), min(w, c["x"] + c["w"] + ring)):
                    inside = c["x"] <= x < c["x"] + c["w"] and c["y"] <= y < c["y"] + c["h"]
                    if not inside:
                        r, g, b, a = px[x, y]
                        if a > 200 and not (g > 120 and g > r + 50 and g > b + 50):
                            samples.append((r, g, b))
            if samples:
                samples.sort(key=lambda t: sum(t))
                med = samples[len(samples) // 4]  # the darker quartile: the well floor, not the rim
            else:
                med = (8, 10, 8)
            for y in range(c["y"], c["y"] + c["h"]):
                for x in range(c["x"], c["x"] + c["w"]):
                    px[x, y] = (med[0] // 2, med[1] // 2, med[2] // 2, 255)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--box", required=True, help="x,y,w,h in the picture's pixels")
    ap.add_argument("--x", type=int, default=4)
    ap.add_argument("--pad", type=int, default=2)
    ap.add_argument("--cutout", action="store_true")
    ap.add_argument("--gauge", action="store_true")
    ap.add_argument("--repaint", default=None)
    ap.add_argument("--gap", type=int, default=3, help="px of sideways erosion that opens the seams between cells")
    ap.add_argument("--sharpen", type=float, default=0.8, help="unsharp amount after the upscale (0 = none)")
    ap.add_argument("--lift", type=float, default=0.0, help="levels stretch + mid-tone lift for a piece that reads muddy at HUD size (1 = full)")
    ap.add_argument("--art", default="assets/ui/art")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "/" not in a.target:
        return emit("fail", "name the piece as <identity>/<piece>", "python kit/ui/trace.py action/emblem_gear --from ... --box ...")
    ident, piece = a.target.split("/", 1)
    if not os.path.isfile(a.src):
        return emit("fail", f"no picture at {a.src}", "point --from at the reference picture")
    x, y, w, h = (int(v) for v in a.box.split(","))
    src = Image.open(a.src).convert("RGB")
    x0, y0 = max(0, x - a.pad), max(0, y - a.pad)
    x1, y1 = min(src.width, x + w + a.pad), min(src.height, y + h + a.pad)
    crop = src.crop((x0, y0, x1, y1))
    work = os.path.join(ROOT, "build", "vision", "trace")
    os.makedirs(work, exist_ok=True)
    crop_path = os.path.join(work, f"{ident}_{piece}_crop.png")
    crop.save(crop_path)
    up_path = crop_path
    scale = 1
    if a.x > 1:
        up_path = os.path.join(work, f"{ident}_{piece}_x{a.x}.png")
        code, out = run([sys.executable, os.path.join(KIT, "vision", "upscale.py"), crop_path, "--x", str(a.x), "-o", up_path])
        if code != 0 or not os.path.isfile(up_path):
            return emit("fail", f"upscale failed: {out[-300:]}", "lune run kit vision setup realesrgan-x4plus")
        scale = a.x
    if a.repaint:
        rp_path = os.path.join(work, f"{ident}_{piece}_repaint.png")
        code, out = run(["lune", "run", "kit", "vision", "edit", up_path, "--prompt", a.repaint, "-o", rp_path])
        if code == 0 and os.path.isfile(rp_path):
            up_path = rp_path
        else:
            return emit("fail", f"repaint failed: {out[-300:]}", "lune run kit vision setup qwen-image-edit sd-cpp, or drop --repaint")
    im = Image.open(up_path).convert("RGBA")
    if a.x > 1 and not a.repaint:
        # the upscaler drifts colour and crushes contrast (a blood-red gem came back magenta, steel rims went grey):
        # match each channel's mean and spread back to the 1:1 crop's
        import numpy as np
        src_a = np.asarray(crop.convert("RGB")).astype(float)
        up_a = np.asarray(im.convert("RGB")).astype(float)
        out = np.empty_like(up_a)
        for ch in range(3):
            m0, s0 = src_a[..., ch].mean(), src_a[..., ch].std() + 1e-6
            m1, s1 = up_a[..., ch].mean(), up_a[..., ch].std() + 1e-6
            out[..., ch] = np.clip((up_a[..., ch] - m1) * (s0 / s1) + m0, 0, 255)
        matched = Image.fromarray(out.astype("uint8"), "RGB")
        matched.putalpha(im.getchannel("A"))
        im = matched
    if a.lift > 0:
        # a crest traced from a zoomed sheet reads muddy at in-game size: stretch the levels (cut the darkest and
        # lightest 0.5 percent) and lift the mid-tones a little, colour only
        from PIL import ImageOps, ImageEnhance
        rgb = ImageOps.autocontrast(im.convert("RGB"), cutoff=0.5)
        rgb = ImageEnhance.Brightness(rgb).enhance(1.0 + 0.12 * a.lift)
        rgb = ImageEnhance.Contrast(rgb).enhance(1.0 + 0.15 * a.lift)
        rgb.putalpha(im.getchannel("A"))
        im = rgb
    if a.sharpen > 0:
        # an x4 upscale is soft beside crisp live cells: a mild unsharp mask on the colour, never on the alpha
        from PIL import ImageFilter
        rgb = im.convert("RGB").filter(ImageFilter.UnsharpMask(radius=2, percent=int(100 * a.sharpen), threshold=2))
        rgb.putalpha(im.getchannel("A"))
        im = rgb
    if a.cutout:
        cut_path = os.path.join(work, f"{ident}_{piece}_cut.png")
        code, out = run(["lune", "run", "kit", "vision", "cutout", up_path, "--rgba", "-o", cut_path])
        rgba = cut_path[:-4] + "_rgba.png"
        if code != 0 or not os.path.isfile(rgba):
            return emit("fail", f"cutout failed: {out[-300:]}", "lune run kit vision setup birefnet, or drop --cutout")
        im = Image.open(rgba).convert("RGBA")
    anchors = None
    if a.gauge:
        mask = green_mask(im)
        rows = cells_from_mask(mask, gap=a.gap)
        if not rows:
            return emit("fail", "no green cells found in the crop", "widen --box to include the lit cells (saturated green)")
        # the reference's own lit cell becomes the live cell's art (the first, cleanest cell of row 1, padded by
        # its frame): kit ui gauge draws every lit cell with it, so the cells are 1:1 too
        c0 = rows[0][0]
        fr = max(2, round(c0["h"] * 0.18))
        cell_img = im.crop((max(0, c0["x"] - fr), max(0, c0["y"] - fr), min(im.width, c0["x"] + c0["w"] + fr), min(im.height, c0["y"] + c0["h"] + fr)))
        im = blank_cells(im, rows)
        anchors = {"schema": 1, "size": list(im.size), "traced": True, "cell_frame_px": fr,
                   "rows": [{"row": i, "cells": r, "lean_px": 0} for i, r in enumerate(rows)]}
    out_dir = os.path.join(ROOT, a.art, ident)
    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, f"{piece}.png")
    im.save(out_png)
    if anchors:
        with open(os.path.join(out_dir, f"{piece}.anchors.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(anchors, fh, indent=1)
        cell_img.save(os.path.join(out_dir, f"{piece}_cell.png"))
    with open(os.path.join(out_dir, f"{piece}.trace.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"schema": 1, "from": os.path.relpath(a.src, ROOT).replace("\\", "/"), "box": [x0, y0, x1 - x0, y1 - y0],
                   "scale": scale, "cutout": a.cutout, "gauge": a.gauge, "repaint": a.repaint, "size": list(im.size)}, fh, indent=1)
    cells = sum(len(r) for r in anchors["rows"]) if anchors else 0
    return emit("pass", f"{ident}/{piece}: traced {w}x{h} px at x{scale}" + (f", {cells} wells in {len(anchors['rows'])} rows blanked + anchored" if anchors else "") + (", cut out" if a.cutout else ""),
                f"LOOK at {os.path.relpath(out_png, ROOT)}; the screen shows it as art:{ident}/{piece}" + (" (kit ui gauge lays live cells over its wells)" if anchors else ""))


if __name__ == "__main__":
    raise SystemExit(main())
