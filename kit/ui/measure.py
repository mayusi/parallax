"""measure.py — a reference still measured by script, not by eye: colour shares, the accent field's region and
the slope of its top edge, the paper and ink masses, the biggest flat regions, text-like bands — into
<still>.layout.json (a screen builder can place from it) and lines for REFS.md.

    python kit/ui/measure.py <still> [--accent #e60012] [--paper #f0f0f0] [--ink #000000] [--tol 60] [--out <json>]
        [--parts "menu item,logo,character"]   (SAM 3 text prompts through kit vision parts, when available)

Everything is in the still's own pixels AND scaled to 1080p (frame height 1080), so numbers from a 720p still and
a 4K still compare. Nothing here is a guess: every number comes from a mask.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def hex_rgb(s):
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def colour_mask(a, rgb, tol):
    d = np.abs(a - np.array(rgb, dtype=np.int32)).sum(axis=2)
    return d <= tol


def bbox(m):
    ys, xs = np.where(m)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def top_edge(m, cols=16):
    """for `cols` columns across the frame, the first row where the mask is true (None where it never is)"""
    h, w = m.shape
    pts = []
    for i in range(cols):
        x = min(w - 1, int((i + 0.5) * w / cols))
        col = m[:, x]
        pts.append([x, int(np.argmax(col)) if col.any() else None])
    return pts


def slope(pts):
    """the top edge's slope (px down per px right) from its first and last measured columns"""
    have = [p for p in pts if p[1] is not None]
    if len(have) < 2:
        return None
    (x0, y0), (x1, y1) = have[0], have[-1]
    return round((y1 - y0) / max(1, x1 - x0), 3)


def masses(m, min_share=0.004):
    """the connected regions of a mask (4-connected flood fill on a downscaled grid), biggest first"""
    h, w = m.shape
    step = max(1, int(max(h, w) / 320))
    small = m[::step, ::step]
    sh, sw = small.shape
    seen = np.zeros_like(small, dtype=bool)
    out = []
    for y in range(sh):
        for x in range(sw):
            if small[y, x] and not seen[y, x]:
                stack = [(y, x)]
                seen[y, x] = True
                px = []
                while stack:
                    cy, cx = stack.pop()
                    px.append((cy, cx))
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < sh and 0 <= nx < sw and small[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                share = len(px) / (sh * sw)
                if share >= min_share:
                    ys = [p[0] for p in px]
                    xs = [p[1] for p in px]
                    out.append({"share": round(share, 3), "box": [min(xs) * step, min(ys) * step, (max(xs) + 1) * step, (max(ys) + 1) * step]})
    out.sort(key=lambda r: -r["share"])
    return out[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("still")
    ap.add_argument("--accent", default="#e60012")
    ap.add_argument("--paper", default="#f0f0f0")
    ap.add_argument("--ink", default="#000000")
    ap.add_argument("--tol", type=int, default=90, help="colour distance (sum of channel differences) that still counts")
    ap.add_argument("--parts", default=None, help="comma-separated things to find with SAM 3 text prompts (kit vision parts)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if not os.path.isfile(a.still):
        return emit("fail", f"measure: no file {a.still}", "give a still (png / jpg / webp)")
    im = Image.open(a.still).convert("RGB")
    W, H = im.size
    arr = np.array(im).astype(np.int32)
    k = 1080.0 / H
    accent = colour_mask(arr, hex_rgb(a.accent), a.tol)
    paper = colour_mask(arr, hex_rgb(a.paper), a.tol)
    ink = (arr.max(axis=2) < 40)
    shares = {"accent": round(float(accent.mean()), 3), "paper": round(float(paper.mean()), 3), "ink": round(float(ink.mean()), 3)}

    def at1080(box):
        return [round(v * k) for v in box] if box else None

    def frac(box):
        return [round(box[0] / W, 3), round(box[1] / H, 3), round(box[2] / W, 3), round(box[3] / H, 3)] if box else None

    acc_box = bbox(accent)
    edge = top_edge(accent)
    layout = {"schema": 1, "still": a.still, "size": [W, H], "to_1080_scale": round(k, 4), "shares": shares,
              "accent": {"box": acc_box, "box_1080": at1080(acc_box), "box_frac": frac(acc_box), "top_edge": edge, "top_edge_slope": slope(edge),
                         "masses": [{**m, "box_1080": at1080(m["box"]), "box_frac": frac(m["box"])} for m in masses(accent)]},
              "paper": {"masses": [{**m, "box_1080": at1080(m["box"]), "box_frac": frac(m["box"])} for m in masses(paper)]},
              "ink": {"masses": [{**m, "box_1080": at1080(m["box"]), "box_frac": frac(m["box"])} for m in masses(ink, 0.02)]},
              "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    # the quadrant census: where each colour lives (top-left / top-right / bottom-left / bottom-right)
    quads = {}
    for name, (y0, y1, x0, x1) in {"tl": (0, H // 2, 0, W // 2), "tr": (0, H // 2, W // 2, W), "bl": (H // 2, H, 0, W // 2), "br": (H // 2, H, W // 2, W)}.items():
        quads[name] = {"accent": round(float(accent[y0:y1, x0:x1].mean()), 3), "paper": round(float(paper[y0:y1, x0:x1].mean()), 3), "ink": round(float(ink[y0:y1, x0:x1].mean()), 3)}
    layout["quadrants"] = quads
    parts_found = []
    if a.parts:
        for thing in [t.strip() for t in a.parts.split(",") if t.strip()]:
            r = subprocess.run(["lune", "run", "kit", "vision", "parts", a.still, "--text", thing], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            line = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("{")), None)
            try:
                res = json.loads(line) if line else {}
            except Exception:  # noqa: BLE001
                res = {}
            parts_found.append({"thing": thing, "result": res.get("summary", (r.stdout or r.stderr or "")[-200:])})
        layout["parts"] = parts_found
    out = a.out or (os.path.splitext(a.still)[0] + ".layout.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(layout, fh, indent=1)
    md = (f"measured by kit ui measure ({W}x{H}, x{k:.3f} to 1080p): accent {shares['accent']:.0%}, paper {shares['paper']:.0%}, ink {shares['ink']:.0%}; "
          f"accent box {at1080(acc_box)} at 1080p ({frac(acc_box)} of the frame), its top edge slope {slope(edge)} (px down per px right); "
          f"quadrants accent tl {quads['tl']['accent']:.0%} tr {quads['tr']['accent']:.0%} bl {quads['bl']['accent']:.0%} br {quads['br']['accent']:.0%}")
    return emit("pass", f"measure: {os.path.basename(a.still)} → {out}", f"paste into REFS.md: {md}", layout=out, refs_line=md)


if __name__ == "__main__":
    raise SystemExit(main())
