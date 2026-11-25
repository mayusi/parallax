"""frame_labels.py - draws a direction frame's plain-word labels onto its render (kit world frame runs it).

    python kit/world/frame_labels.py <frame.png> <frame.labels.json>

The owner on an unlabelled test frame (GothicCourtyard, 2026-11-11): "I don't know what I'm exactly looking at". A
direction must read at a glance, so every label the scene names ("labels" in the .frame.json; frame_blender.py projects
them) is drawn: a dot on the thing, a leader line, the words on a dark tag above it, tags never overlapping and never
off the picture; what the camera cannot see (behind it, off the edges, behind a wall) is listed in a strip along the
bottom ("Not in this view: ..."). The render without labels is kept beside it as <frame>.raw.png.
Prints one JSON line: {status, summary, next_action, out, raw, drawn, not_in_view}.
"""

import hashlib
import json
import os
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf")


def font(size):
    for f in FONTS:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def overlaps(a, b, pad=6):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def place(boxes, w, h, px, py, tw, th, strip_top):
    """a tag of tw x th near the point (px, py), inside the picture and above the strip, clear of every placed tag:
    above first, then above to either side, then further up, and only then below (a tag below a figure covers it)"""
    pad, rise = 10, max(28.0, h / 11.0)
    bw, bh = tw + 2 * pad, th + 2 * pad
    box = None
    for sign in (1, -1):
        for k in range(10):
            for dx in (0.0, bw / 2 + 30, -(bw / 2 + 30), bw + 40, -(bw + 40)):
                gap = rise + k * (th + 8)
                y0 = py - gap - bh if sign > 0 else py + gap  # (above the point, or below it)
                x0 = min(max(8.0, px + dx - bw / 2), w - bw - 8.0)
                y0 = min(max(8.0, y0), strip_top - bh - 8.0)
                box = (x0, y0, x0 + bw, y0 + bh)
                if not any(overlaps(box, b) for b in boxes):
                    return box
    return box


def strip_text(d, unseen, size, max_w):
    """the bottom strip's one line inside max_w: the type shrinks to 60 % of the labels' size; a list still too long
    names as many as fit and counts the rest ("+2 more") - it ran off the right edge mid-word (a world with nine
    labels, seven of them out of an establishing shot: "... lamp 1: the stair's f") -> (text, font)"""
    head = "Not in this view: "
    text, s = head + "; ".join(unseen), size
    f = font(s)
    while s > max(12, int(size * 0.6)) and d.textlength(text, font=f) > max_w:
        s -= 1
        f = font(s)
    shown = list(unseen)
    while len(shown) > 1 and d.textlength(text, font=f) > max_w:
        shown.pop()
        text = head + "; ".join(shown) + f"; +{len(unseen) - len(shown)} more"
    return text, f


def draw(png, labels_path):
    with open(labels_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    raw = os.path.splitext(png)[0] + ".raw.png"
    with open(png, "rb") as fh:
        shown = hashlib.sha1(fh.read()).hexdigest()
    if not os.path.isfile(raw) or spec.get("labelled_sha1") != shown:
        shutil.copyfile(png, raw)  # (a fresh render - its labels file has no hash yet: keep it unlabelled beside)
    img = Image.open(raw).convert("RGBA")
    w, h = img.size
    size = max(16, w // 58)
    f = font(size)
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    labels = spec.get("labels", [])
    seen = [lb for lb in labels if lb.get("seen")]
    unseen = [lb["text"] for lb in labels if not lb.get("seen")]
    strip_h = int(size * 2.2) if unseen else 0
    strip_top = h - strip_h
    boxes, drawn = [], []
    for lb in sorted(seen, key=lambda lb: lb["px"][1]):  # (top first: the sky's tags take the high places)
        px, py = lb["px"]
        l, t, r, b = d.textbbox((0, 0), lb["text"], font=f)
        box = place(boxes, w, h, px, py, r - l, b - t, strip_top)
        boxes.append(box)
        cx = min(max(px, box[0] + 12), box[2] - 12)
        cy = box[3] if box[3] <= py else box[1]
        d.line([(px, py), (cx, cy)], fill=(255, 255, 255, 230), width=max(2, size // 12))
        rr = max(4, size // 5)
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255),
                  width=2)
        d.rounded_rectangle(box, radius=8, fill=(10, 10, 14, 200))
        d.text((box[0] + 10 - l, box[1] + 10 - t), lb["text"], font=f, fill=(255, 255, 255, 255))
        drawn.append({"text": lb["text"], "box": [round(v, 1) for v in box]})
    if unseen:
        d.rectangle([0, strip_top, w, h], fill=(10, 10, 14, 215))
        text, fs = strip_text(d, unseen, size, w - 28)
        d.text((14, strip_top + strip_h / 2), text, font=fs, fill=(235, 235, 240, 255), anchor="lm")
    Image.alpha_composite(img, over).convert("RGB").save(png)
    with open(png, "rb") as fh:
        spec["labelled_sha1"] = hashlib.sha1(fh.read()).hexdigest()  # (a re-run draws on the raw again, once)
    with open(labels_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)
    return {"drawn": drawn, "not_in_view": unseen, "size": [w, h], "raw": raw}


def main(argv):
    png, labels_path = argv[0], argv[1]
    r = draw(png, labels_path)
    print(json.dumps({"status": "pass",
                      "summary": f"{len(r['drawn'])} label(s) drawn" + (f", {len(r['not_in_view'])} not in view ("
                                                                        + "; ".join(r["not_in_view"]) + ")"
                                                                        if r["not_in_view"] else ""),
                      "next_action": f"LOOK at {png} (unlabelled: {r['raw']})", "out": png, "raw": r["raw"],
                      "drawn": len(r["drawn"]), "not_in_view": r["not_in_view"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
