"""vectorize.py — a picture's lines or shapes as SVG curves (vtracer, MIT; vetted + pinned). Kit python, no model.

    python kit/vision/vectorize.py <image> [-o out.svg] [--binary | --color] [--speckle 4] [--threshold auto|0-255]
                                   [--invert] [--colors 6] [--corner 60] [--polygon]

--binary (the default): lines, engraving, a stencil -> filled curves of one colour. The picture is read as dark ink
  on light paper (a transparent background is paper); --threshold is the grey level below which a pixel is ink
  (auto: Otsu's level, picked from the picture); --invert for light lines on a dark ground. The ink it traced is saved
  beside the SVG as <name>_ink.png — what to look at when the curves miss a line.
--color: every colour region becomes a filled curve, stacked; --colors = bits kept per colour channel (1-8, fewer =
  fewer regions); transparent pixels are left out.
--speckle N: drop specks smaller than N x N pixels (noise, dust, paper grain).
--polygon: straight segments instead of curves (crisp hard-surface outlines).
Writes build/vision/<name>.svg unless -o. Blender reads it as curves (File > Import > Scalable Vector Graphics):
extrude or bevel them into an engraving, a stencil, an outline to build from.
"""

import io
import json
import os
import re
import sys
import time

import numpy as np
from PIL import Image

MANY_PATHS = 3000  # more than this is slow to import and usually traced noise


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def otsu(gray):
    """Otsu's threshold of a uint8 grey picture: the level that best splits it into two groups (ink, paper)"""
    hist = np.bincount(np.asarray(gray, np.uint8).ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 128
    levels = np.arange(256)
    w0 = np.cumsum(hist)
    m0 = np.cumsum(hist * levels)
    w1 = total - w0
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (m0[-1] * w0 / total - m0) ** 2 / (w0 * w1 / total)
    between[(w0 == 0) | (w1 == 0)] = -1
    best = int(np.argmax(between))
    return best + 1 if between[best] > 0 else 128  # (a flat picture has no split: the middle level)


def ink(img, threshold="auto", invert=False):
    """-> (an L picture: black ink on white paper, the threshold used). Transparent pixels are paper; a grey level
    BELOW the threshold is ink (with --invert: above it)."""
    rgba = np.asarray(img.convert("RGBA"), dtype=np.float32)
    gray = rgba[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    paper = 0.0 if invert else 255.0
    a = rgba[..., 3] / 255.0
    gray = (gray * a + paper * (1 - a)).clip(0, 255).astype(np.uint8)  # (transparent -> paper)
    level = otsu(gray) if threshold == "auto" else int(threshold)
    is_ink = gray > level if invert else gray < level
    return Image.fromarray(np.where(is_ink, 0, 255).astype(np.uint8), "L"), level


def svg_stats(svg):
    """what vtracer wrote: path count, curve / line segments, the canvas size"""
    paths = re.findall(r"<path\b[^>]*\bd=\"([^\"]*)\"", svg)
    segments = sum(len(re.findall(r"[CLQ]", d)) for d in paths)
    m = re.search(r"<svg\b[^>]*\bwidth=\"(\d+)\"[^>]*\bheight=\"(\d+)\"", svg)
    return {"paths": len(paths), "segments": segments,
            "width": int(m.group(1)) if m else None, "height": int(m.group(2)) if m else None}


def vectorize(img, binary=True, speckle=4, threshold="auto", invert=False, colors=6, corner=60, polygon=False):
    """-> (svg text, the ink picture or None, the threshold used or None)"""
    import vtracer  # noqa: PLC0415

    ink_img, level = (ink(img, threshold, invert) if binary else (img.convert("RGBA"), None))
    buf = io.BytesIO()
    ink_img.save(buf, format="PNG")
    svg = vtracer.convert_raw_image_to_svg(
        buf.getvalue(), img_format="png", colormode="binary" if binary else "color", hierarchical="stacked",
        mode="polygon" if polygon else "spline", filter_speckle=int(speckle), color_precision=int(colors),
        layer_difference=16, corner_threshold=int(corner), length_threshold=4.0, max_iterations=10,
        splice_threshold=45, path_precision=3)
    return svg, (ink_img if binary else None), level


def main(argv):
    if not argv or not os.path.isfile(argv[0]):
        return emit("fail", "vision vectorize: give a picture file (lines on paper work best)",
                    "lune run kit vision vectorize refs/<picture>.png [--color] [--speckle 4]")
    src, t0 = argv[0], time.time()
    binary = "--color" not in argv
    threshold = argv[argv.index("--threshold") + 1] if "--threshold" in argv else "auto"
    if threshold != "auto" and not (threshold.isdigit() and 0 <= int(threshold) <= 255):
        return emit("fail", f"vision vectorize: --threshold is auto or a grey level 0-255, not {threshold}",
                    "lune run kit vision vectorize <picture> --threshold 128")
    colors = _opt(argv, "--colors", 6)
    if not 1 <= colors <= 8:
        return emit("fail", f"vision vectorize: --colors is 1-8 bits per channel, not {colors}",
                    "lune run kit vision vectorize <picture> --color --colors 4")
    img = Image.open(src)
    svg, ink_img, level = vectorize(img, binary=binary, speckle=_opt(argv, "--speckle", 4), threshold=threshold,
                                    invert="--invert" in argv, colors=colors, corner=_opt(argv, "--corner", 60),
                                    polygon="--polygon" in argv)
    if "-o" in argv:
        out = argv[argv.index("-o") + 1]
    else:
        out = os.path.join("build", "vision", os.path.splitext(os.path.basename(src))[0] + ".svg")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    stats = svg_stats(svg)
    extra = {"out": out.replace("\\", "/"), **stats}
    how = "binary" if binary else f"colour ({colors} bits)"
    if ink_img is not None:
        ink_path = os.path.splitext(out)[0] + "_ink.png"
        ink_img.save(ink_path)
        extra.update(ink=ink_path.replace("\\", "/"), threshold=level)
        how += f", ink below grey {level}" if "--invert" not in argv else f", ink above grey {level}"
        share = float((np.asarray(ink_img) == 0).mean())
        extra["ink_share"] = round(share, 4)
        if stats["paths"] == 0 or share == 0:
            return emit("fail", f"vision vectorize: no ink traced in {src} ({how}) — the picture has nothing darker "
                                f"than grey {level}",
                        "light lines on a dark ground? add --invert; or set --threshold 0-255", **extra)
    summary = (f"vision vectorize: {out} ({stats['paths']} paths, {stats['segments']} segments, "
               f"{len(svg.encode()) / 1024:.1f} KB; {how}; {time.time() - t0:.1f} s)")
    if stats["paths"] > MANY_PATHS:
        return emit("pass", summary, f"improve: {stats['paths']} paths is mostly specks — raise --speckle "
                                     f"(now {_opt(argv, '--speckle', 4)})" + ("" if binary else " or lower --colors"),
                    **extra)
    look = f"look at {out} (open it in a browser)" + (f" beside {extra['ink']} (what was traced)" if binary else "")
    return emit("pass", summary, look, **extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
