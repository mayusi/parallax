"""silhouette.py — the effect's OUTLINE as numbers, from the references and from our render, so a mesh's shape params come
from data (owner 2026-10-14: improve "reference understanding" and "mesh making"). For each still: the effect's pixels
(the measured hue band, refs rank), the LARGEST connected piece, then:
  aspect    height / width of that piece (an SSJ aura is a tall flame, a Kamehameha head is round)
  taper     width at 80 % of its height / width at 30 % (1 = a column, < 0.5 = a flame narrowing to its tip)
  tips      flame tongues along the TOP edge (peaks of the top contour with a prominence >= 6 % of the height)
  tip_depth the median prominence of those peaks / height (deep notches = separate tongues; shallow = a wavy rim)
  fill      how much of its bounding box it fills

    lune run kit vfx refs silhouette <set> [--effect <name>] [--view hero] [--times 2.5,4] [--top 16]

Prints the reference medians, our render's (when --effect is given) and what to change in the mesh shapes (flame
shells: height / radius, lobes, tip). Writes refs_measured/<set>.silhouette.json (numbers only).
Only stills whose effect is NOT cut by the picture's top / sides count; under 8 such stills the result is UNTRUSTED.
Known limit: a subject in the effect's own colour (golden hair inside a golden aura) merges with it - read the advice,
do not apply it blindly (2026-10-14: the Saiyan sets measured close-ups; the Spirit Bomb's 20 full shots gave a sphere)."""

import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage

from refkit import MEASURED, REFS, duration_of, effect_mask, frame_of, local_std, out

KEYS = ("aspect", "taper", "tips", "tip_depth", "fill")


def silhouette(img, hue):
    im = img.convert("RGB").resize((240, 180))
    hsv = np.asarray(im.convert("HSV")).astype(float)
    m = effect_mask(hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255, hue, local_std(im))
    m = ndimage.binary_closing(m, iterations=2)
    lab, n = ndimage.label(m)
    if n == 0:
        return None
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    k = int(np.argmax(sizes)) + 1
    if sizes[k - 1] < 300:
        return None
    blob = lab == k
    ys, xs = np.nonzero(blob)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    h, w = y1 - y0 + 1, x1 - x0 + 1
    if w < 8 or h < 8:
        return None
    H, W = blob.shape
    if y0 <= 4 or x0 <= 4 or x1 >= W - 5:  # (closing erodes the border by ~2 px) cut by the picture's top / sides: a close-up, its outline is not the effect's
        return None

    def width_at(frac):  # frac of the height from the BOTTOM
        row = int(y1 - frac * (h - 1))
        return max(1, int(blob[row].sum()))

    # the top contour: for each column, the highest effect pixel (as a height above the blob's bottom)
    top = np.array([(y1 - np.argmax(blob[:, x])) if blob[:, x].any() else 0 for x in range(x0, x1 + 1)], dtype=float)
    top = ndimage.uniform_filter1d(top, 3)
    peaks, prom = [], []
    min_prom = 0.06 * h
    for i in range(1, len(top) - 1):
        if top[i] >= top[i - 1] and top[i] > top[i + 1]:
            left = top[: i + 1][::-1]
            right = top[i:]
            lmin = left[: np.argmax(left > top[i]) if (left > top[i]).any() else len(left)].min()
            rmin = right[: np.argmax(right > top[i]) if (right > top[i]).any() else len(right)].min()
            p = top[i] - max(lmin, rmin)
            if p >= min_prom:
                peaks.append(i)
                prom.append(p / h)
    return {"aspect": round(h / w, 2), "taper": round(width_at(0.8) / width_at(0.3), 2), "tips": len(peaks),
            "tip_depth": round(float(np.median(prom)), 3) if prom else 0.0, "fill": round(float(blob.sum() / (h * w)), 2)}


def summary(rows):
    rows = [r for r in rows if r]
    if not rows:
        return None
    return {k: round(float(np.median([r[k] for r in rows])), 3) for k in KEYS} | {"n": len(rows)}


def advice(ref, got):
    tips = []
    if got["aspect"] < ref["aspect"] * 0.85:
        tips.append(f"TALLER: aspect {got['aspect']} vs {ref['aspect']} - raise the flame shells' height / radius by x{ref['aspect'] / max(0.01, got['aspect']):.2f}")
    elif got["aspect"] > ref["aspect"] * 1.15:
        tips.append(f"WIDER: aspect {got['aspect']} vs {ref['aspect']} - widen the shells (radius x{got['aspect'] / max(0.01, ref['aspect']):.2f})")
    if got["taper"] > ref["taper"] + 0.12:
        tips.append(f"NARROW the top: taper {got['taper']} vs {ref['taper']} - a smaller 'tip' param / more flame tongues leaning in")
    elif got["taper"] < ref["taper"] - 0.12:
        tips.append(f"FULLER top: taper {got['taper']} vs {ref['taper']} - a bigger 'tip' / 'base' param")
    if got["tips"] + 1 < ref["tips"]:
        tips.append(f"MORE TONGUES on the rim: {got['tips']} vs {ref['tips']} - raise 'lobes' or add tongue layers")
    elif got["tips"] > ref["tips"] + 2:
        tips.append(f"FEWER tongues: {got['tips']} vs {ref['tips']} - lower 'lobes'")
    if got["tip_depth"] < ref["tip_depth"] * 0.6:
        tips.append(f"DEEPER notches: tip_depth {got['tip_depth']} vs {ref['tip_depth']} - raise 'lobe' (lobe depth) / tongue height spread")
    return tips


def cmd_silhouette(preset, opts):
    rk = os.path.join(REFS, preset, "ranks.json")
    if not os.path.isfile(rk):
        return out("fail", f"refs silhouette {preset}: no ranks yet", f"lune run kit vfx refs rank {preset}")
    r = json.load(open(rk, encoding="utf-8"))
    hue = tuple(r["hue"])
    # the FULL shots refs rank found (the whole effect in frame) — close-ups rank first by coverage but show no outline
    picks = r.get("full_shots") or [f for _, f in r["ranks"]]
    picks = picks[: int(opts.get("--top", 24))]
    ref_rows = [silhouette(Image.open(os.path.join(REFS, preset, f)), hue) for f in picks]
    ref = summary(ref_rows)
    if not ref:
        return out("fail", f"refs silhouette {preset}: no effect outline in the top stills", "check the rank sheet / --hue")
    res = {"preset": preset, "hue": list(hue), "reference": ref}
    weak = ref["n"] < 8  # wiki stills are mostly close-ups (cut by the frame) or the subject shares the effect's colour (golden hair)
    if weak:
        res["trust"] = f"only {ref['n']} uncut stills - too few to shape a mesh by; gather full shots (refs wiki --only <shot words>) first"
    msg = f"refs silhouette {preset}: reference (n {ref['n']}) aspect {ref['aspect']}, taper {ref['taper']}, tips {ref['tips']}, tip_depth {ref['tip_depth']}, fill {ref['fill']}"
    tips = []
    eff = opts.get("--effect")
    if eff:
        view = opts.get("--view", "hero")
        video = os.path.join("build", "vfx", "booth", f"{eff}_play_{view}.mp4")
        if not os.path.isfile(video):
            return out("fail", f"refs silhouette: no recording {video}", f"python kit/vfx/autorec.py {eff}")
        dur = duration_of(video)
        times = [float(t) for t in opts["--times"].split(",")] if "--times" in opts else [dur * 0.4, dur * 0.65]
        got = summary([silhouette(frame_of(video, t), hue) for t in times])
        if not got:
            return out("warn", msg + f"; {eff}: no outline in the effect's hue at {times}", "pass --times inside the effect / check the hue")
        res["render"] = dict(got, effect=eff, view=view, times=times)
        tips = advice(ref, got)
        res["advice"] = tips
        msg += f"; {eff}: aspect {got['aspect']}, taper {got['taper']}, tips {got['tips']}, tip_depth {got['tip_depth']}, fill {got['fill']}"
    os.makedirs(MEASURED, exist_ok=True)
    json.dump(res, open(os.path.join(MEASURED, f"{preset}.silhouette.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    if weak:
        return out("warn", msg + f" — UNTRUSTED: {res['trust']}", res["trust"], silhouette=res)
    return out("warn" if tips else "pass", msg, "; ".join(tips) if tips else ("the outline matches the references" if eff else f"compare a render: --effect <name>"),
               silhouette=res)
