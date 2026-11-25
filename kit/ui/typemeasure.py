"""typemeasure.py — reference understanding for TYPE: the lettering in a crop measured, so `kit ui letter` starts from the
reference's own proportions instead of a guess.

    python kit/ui/read.py type <crop.png>            (lune run kit ui read type <crop>; crops: kit ui read <still> --crops)

The text is split from its ground (the side of an Otsu threshold the border is NOT on), its glyphs found as connected
pieces, and measured: cap height (the median height of the tall glyphs), stroke weight (twice the median distance to the
edge inside the strokes, as a share of the cap height), slant (the shear that makes the vertical strokes most upright),
tracking (the median gap between glyphs, as a share of the cap height), the fill colour, and an outline (a dark ring
hugging light letters, or a light ring hugging dark ones). -> <crop>.type.json with the `kit ui letter` flags to try.
"""
import json
import os

import numpy as np
from PIL import Image


def otsu(v):
    hist, edges = np.histogram(v, bins=64, range=(0, 255))
    total, sum_all = v.size, (hist * edges[:-1]).sum()
    best, thr, wb, sb = -1.0, 128.0, 0, 0.0
    for i in range(64):
        wb += hist[i]
        if wb == 0 or wb == total:
            continue
        sb += hist[i] * edges[i]
        mb, mf = sb / wb, (sum_all - sb) / (total - wb)
        var = wb * (total - wb) * (mb - mf) ** 2
        if var > best:
            best, thr = var, edges[i + 1]
    return thr


def text_mask(gray):
    """True on the letters: the side of the threshold the crop's border is NOT on"""
    thr = otsu(gray)
    border = np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])
    light_ground = (border > thr).mean() > 0.5
    return gray < thr if light_ground else gray > thr


def slant_of(mask, angles=np.linspace(-0.45, 0.45, 37)):
    """the shear (x per y, + = leaning right) under which the strokes stand most upright: the column profile is sharpest"""
    ys, xs = np.nonzero(mask)
    if len(xs) < 20:
        return 0.0
    yc = ys - ys.mean()
    best, best_a = -1.0, 0.0
    for a in angles:
        x = np.round(xs + a * yc).astype(int)  # undo a lean of a: x' = x + a * (y - yc), y grows downward
        prof = np.bincount(x - x.min())
        score = float((prof.astype(np.float64) ** 2).sum())
        if score > best:
            best, best_a = score, a
    return round(float(best_a), 3)


def measure(img):
    from scipy import ndimage as ndi
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    gray = rgb.mean(axis=2)
    m = text_mask(gray)
    lab, n = ndi.label(m)
    if n == 0:
        return None
    sl = ndi.find_objects(lab)
    hs = np.array([s[0].stop - s[0].start for s in sl])
    ws = np.array([s[1].stop - s[1].start for s in sl])
    areas = np.bincount(lab.ravel())[1:]
    keep = (areas > 0.002 * m.size) | (hs > 0.25 * m.shape[0])  # glyphs, not specks
    if not keep.any():
        return None
    cap = float(np.median(hs[keep][hs[keep] >= 0.6 * hs[keep].max()]))
    dist = ndi.distance_transform_edt(m)
    ridge = dist[(dist > 0) & (dist >= ndi.maximum_filter(dist, size=3))]
    stroke = 2 * float(np.median(ridge)) if ridge.size else 0.0
    boxes = sorted((s[1].start, s[1].stop) for s, k in zip(sl, keep) if k)
    gaps = [b[0] - a[1] for a, b in zip(boxes, boxes[1:]) if b[0] - a[1] > 0]
    track = float(np.median(gaps)) / cap if gaps else 0.0
    fill = rgb[m].mean(axis=0)
    ring = ndi.binary_dilation(m, iterations=2) & ~m  # (an outline hugs the edge: a wide ring averaged it with the ground)
    ring_l = float(rgb[ring].mean()) if ring.any() else 0.0
    # the open ground = the crop's own border (letters often fill a tight crop: a ground 'far from the letters' was empty)
    edge = np.zeros(m.shape, bool)
    edge[:2, :] = edge[-2:, :] = edge[:, :2] = edge[:, -2:] = True
    near = ndi.binary_dilation(m, iterations=6)
    ground = edge & ~near
    ground_l = float(rgb[ground].mean()) if ground.any() else float(rgb[edge].mean())
    fill_l = float(fill.mean())
    # an outline: the ring hugging the letters is darker (or lighter) than both the letters and the open ground
    outline = bool((ring_l < fill_l - 40 and ring_l < ground_l - 15) or (ring_l > fill_l + 40 and ring_l > ground_l + 15))
    return {"cap_px": round(cap, 1), "stroke_px": round(stroke, 2), "weight": round(stroke / cap, 3) if cap else 0.0,
            "slant": slant_of(m), "track": round(track, 3), "fill": "#%02x%02x%02x" % tuple(int(v) for v in fill),
            "outline": outline, "glyphs": int(keep.sum())}


def letter_flags(t):
    """the measures -> kit ui letter flags (cap height ~0.7 of the size; weight 0.10 regular .. 0.20+ black)"""
    w = t["weight"]
    weight = 400 if w < 0.11 else 600 if w < 0.15 else 800 if w < 0.2 else 900
    # (an UPRIGHT face, so the shear IS the slant: letter's default Bangers already leans +0.2 and doubled an italic)
    flags = ["--font", "oswald", "--size", str(int(round(t["cap_px"] / 0.7))), "--weight", str(weight), "--lean", "0", "--shear", f"{t['slant']:.2f}",
             "--track", f"{max(0.0, t['track'] - 0.08):.2f}", "--fill", t["fill"]]
    if t["outline"]:
        flags += ["--outline", "0.03"]
    return flags


def cmd_type(a):
    def emit(status, summary, next_action, **extra):
        print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
        return 0 if status == "pass" else 1

    if not os.path.isfile(a.crop):
        return emit("fail", f"type: no crop at {a.crop}", "kit ui read <still> --crops makes them")
    t = measure(Image.open(a.crop))
    if t is None:
        return emit("fail", f"type: no lettering found in {a.crop}", "crop tighter around the words")
    t["letter_flags"] = letter_flags(t)
    out = os.path.splitext(a.crop)[0] + ".type.json"
    with open(out, "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump({"schema": 1, "crop": a.crop, **t}, fh, indent=1)
    lean = "upright" if abs(t["slant"]) < 0.04 else f"leans {'right' if t['slant'] > 0 else 'left'} {abs(t['slant']):.2f}"
    return emit("pass", f"type: {os.path.basename(a.crop)} — cap {t['cap_px']} px, stroke {t['weight']:.2f} of the cap, {lean}, "
                f"track {t['track']:.2f}, fill {t['fill']}{', outlined' if t['outline'] else ''} ({t['glyphs']} glyphs)",
                "letter it: lune run kit ui letter <id>/<piece> --text \"...\" " + " ".join(t["letter_flags"]), type=out)
