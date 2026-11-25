"""labels.py — draw part names onto a preview sheet (system python + PIL; Blender's python has no PIL).

    python kit/blender/labels.py build/renders/<name>.png

Reads build/renders/<name>.labels.json (written by rbx.py: per tile, each part's centre projected to 0..1) and
writes the names with a dot at each part's centre, so "the Guard" in a message and the Guard in the picture are
the same thing. Prints one JSON line: {status, summary, next_action}.
"""

import json
import os
import sys
import time

from PIL import Image, ImageDraw, ImageFont


def save(img, path):
    """Write next to the target, then swap it in — retrying while another process holds the old file (Windows)."""
    tmp = path[:-4] + ".tmp.png"
    img.save(tmp)
    for _ in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.25)
    os.replace(tmp, path)


def font(size):
    for f in ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main(sheet):
    meta = os.path.splitext(sheet)[0] + ".labels.json"
    if not os.path.isfile(meta) or not os.path.isfile(sheet):
        print(json.dumps({"status": "pass", "summary": "no labels to draw", "next_action": "none — proceed"}))
        return 0
    with open(meta, encoding="utf-8") as fh:
        data = json.load(fh)
    im = Image.open(sheet).convert("RGB")
    clean = im.copy()   # (judges and the comparison read the model WITHOUT names: a label reads as a floating defect)
    save(clean, os.path.splitext(sheet)[0] + ".clean.png")
    dr = ImageDraw.Draw(im)
    tw, th = data["tile"]
    cols = data["cols"]
    f = font(12)
    count = 0
    for tile, items in data["tiles"].items():
        r, c = divmod(int(tile), cols)
        placed = []
        for it in items:
            x, y = c * tw + it["u"] * tw, r * th + it["v"] * th
            # nudge labels that would overlap an earlier one downwards
            ty = y - 7
            while any(abs(ty - py) < 13 and abs(x - px) < 60 for px, py in placed):
                ty += 13
            placed.append((x, ty))
            dr.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=(255, 210, 60), outline=(0, 0, 0))
            dr.text((x + 6, ty), it["name"], font=f, fill=(255, 235, 140), stroke_width=2, stroke_fill=(0, 0, 0))
            count += 1
    save(im, sheet)
    compared = _compare(sheet, clean, tw, th)
    print(json.dumps({"status": "pass", "summary": f"{count} part label(s) drawn{compared}", "next_action": "none — proceed"}))
    return 0


def _compare(sheet, im, tw, th):
    """<name>_compare.png: the owner's reference image beside the hero close-up and the side view."""
    name = os.path.splitext(os.path.basename(sheet))[0]
    manifest = os.path.join(os.path.dirname(os.path.dirname(sheet)), "models", f"{name}.manifest.json")
    if not os.path.isfile(manifest):
        return ""
    with open(manifest, encoding="utf-8") as fh:
        ref = json.load(fh).get("reference_image")
    if not ref or not os.path.isfile(ref):
        return ""
    r = Image.open(ref).convert("RGB")
    h = th * 2
    r = r.resize((max(1, int(r.width * h / r.height)), h))
    hero = im.crop((0, 0, tw, th))
    side = im.crop((tw, th, tw * 2, th * 2))
    out = Image.new("RGB", (r.width + tw, h), (24, 24, 28))
    out.paste(r, (0, 0))
    out.paste(hero, (r.width, 0))
    out.paste(side, (r.width, th))
    d = ImageDraw.Draw(out)
    d.text((8, 8), "REFERENCE", font=font(16), fill=(255, 220, 120), stroke_width=2, stroke_fill=(0, 0, 0))
    d.text((r.width + 8, 8), "MODEL", font=font(16), fill=(255, 220, 120), stroke_width=2, stroke_fill=(0, 0, 0))
    path = os.path.join(os.path.dirname(sheet), f"{name}_compare.png")
    save(out, path)
    return f"; reference comparison: {path.replace(os.sep, '/')}"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
