"""preview.py — top-down map of a compiled world (build/worlds/<name>.json, written by `kit world`) -> <name>.png.

Footprints are drawn lowest-first so taller geometry sits on top; brightness encodes height (darker = lower).
Spawn pads are green rings. One image per world: the evidence a model looks at after `lune run kit world`.
Usage: python kit/world/preview.py build/worlds/<name>.json
"""

import json
import math
import os
import sys

from PIL import Image, ImageDraw

SIZE = 1024
PAD = 40


def corners(p):
    sx, sz = p["size"][0] / 2, p["size"][2] / 2
    r = p["rot"]
    out = []
    for lx, lz in ((-sx, -sz), (sx, -sz), (sx, sz), (-sx, sz)):
        # world = R * local (x, 0, z) + pos  (rows of r are the matrix rows)
        wx = r[0][0] * lx + r[0][2] * lz + p["pos"][0]
        wz = r[2][0] * lx + r[2][2] * lz + p["pos"][2]
        out.append((wx, wz))
    return out


def main(path):
    data = json.load(open(path, encoding="utf-8"))
    # backdrop scenery (distant ranges, a colossus beyond the edge) is not the map
    parts = [p for p in data["parts"] if not p.get("backdrop")]
    if not parts:
        print(json.dumps({"status": "fail", "summary": "no parts to draw"}))
        return 1
    pts = [c for p in parts for c in corners(p)]
    minx, maxx = min(x for x, _ in pts), max(x for x, _ in pts)
    minz, maxz = min(z for _, z in pts), max(z for _, z in pts)
    span = max(maxx - minx, maxz - minz, 1)
    scale = (SIZE - 2 * PAD) / span

    def px(x, z):
        return (PAD + (x - minx) * scale, PAD + (z - minz) * scale)

    tops = [p["pos"][1] + p["size"][1] / 2 for p in parts]
    lo, hi = min(tops), max(tops)
    img = Image.new("RGB", (SIZE, SIZE), (18, 20, 26))
    draw = ImageDraw.Draw(img, "RGBA")
    for p, top in sorted(zip(parts, tops), key=lambda t: t[1]):
        shade = 0.45 + 0.55 * ((top - lo) / (hi - lo) if hi > lo else 1)
        r, g, b = (int(c * shade) for c in p["color"])
        alpha = int(255 * (1 - min(p["transparency"], 0.85)))
        poly = [px(x, z) for x, z in corners(p)]
        if p.get("shape") == "Ball" or (p.get("shape") == "Cylinder" and p["size"][0] >= p["size"][2]):
            cx, cz = px(p["pos"][0], p["pos"][2])
            rad = max(p["size"][0], p["size"][2]) / 2 * scale
            draw.ellipse([cx - rad, cz - rad, cx + rad, cz + rad], fill=(r, g, b, alpha), outline=(0, 0, 0, 90))
        else:
            draw.polygon(poly, fill=(r, g, b, alpha), outline=(0, 0, 0, 90))
    for p in parts:
        if p.get("spawn"):
            cx, cz = px(p["pos"][0], p["pos"][2])
            draw.ellipse([cx - 9, cz - 9, cx + 9, cz + 9], outline=(80, 255, 120, 255), width=3)
    # scale bar: 50 studs
    bar = 50 * scale
    draw.line([PAD, SIZE - 18, PAD + bar, SIZE - 18], fill=(230, 230, 230), width=3)
    draw.text((PAD + bar + 8, SIZE - 26), "50 studs  (top-down, +X right, +Z down; brighter = taller)", fill=(200, 200, 200))
    out = os.path.splitext(path)[0] + ".png"
    img.save(out)
    print(json.dumps({"status": "pass", "summary": f"map {out} ({len(parts)} parts, {round(span)} studs across)", "file": out.replace(chr(92), "/")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
