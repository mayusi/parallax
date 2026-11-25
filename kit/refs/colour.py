"""colour.py — is a REFERENCE PICTURE colour-graded? Before a colour is sampled from a photo or a render, its tint is
measured on a surface known to be NEUTRAL (black rubber, grey steel, white paper: --neutral x0,y0,x1,y1) or, without
one, on the picture's least colourful mid-tones; the picture is BALANCED so that surface reads grey again, and every
sample is given raw and balanced. Why (kit lesson, 2026-10-07): a colour-graded render read black rubber as navy.

    python kit/refs/colour.py <picture> [--neutral x0,y0,x1,y1] [--sample name=x0,y0,x1,y1 ...] [--out <png>]

  -> one JSON line: the cast (its chroma in CIELAB and its hue in words: "blue", "orange"...; under 4 = neutral),
     the white-balance gains, each sample's colour raw and balanced (sRGB hex + Lab), and the balanced picture
     (build/refs/colour/<picture>_balanced.png) to sample from.
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "kit", "blender"))
import rbx_colour  # noqa: E402  (CIELAB, hue names)

TINTED = 4.0  # chroma (CIELAB) of a supposedly neutral surface above which the picture counts as colour-graded


def to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def _box(text):
    x0, y0, x1, y1 = (int(float(v)) for v in text.split(","))
    return x0, y0, x1, y1


def _hex(srgb):
    return "#" + "".join(f"{int(round(min(1, max(0, v)) * 255)):02x}" for v in srgb)


def neutral_mean(lin, box=None):
    """the mean LINEAR colour of the neutral surface: the box, or the least colourful mid-tones (luminance 8..85%,
    the 15% with the least saturation) -> (rgb, where)"""
    if box:
        x0, y0, x1, y1 = box
        return lin[y0:y1, x0:x1].reshape(-1, 3).mean(0), "the neutral box"
    flat = lin.reshape(-1, 3)
    lum = flat @ np.array([0.2126, 0.7152, 0.0722])
    mx, mn = flat.max(1), flat.min(1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    mid = (lum > 0.008) & (lum < 0.7)  # (linear: about 8..85% in sRGB)
    if mid.sum() < 50:
        return flat.mean(0), "the whole picture"
    cut = np.quantile(sat[mid], 0.15)
    pick = mid & (sat <= cut)
    return flat[pick].mean(0), "the least colourful mid-tones"


def measure(path, neutral=None, samples=(), out=None):
    img = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
    lin = to_linear(img)
    mean, where = neutral_mean(lin, neutral)
    lab = rbx_colour.srgb_to_lab(to_srgb(mean))
    chroma = float(math.hypot(lab[1], lab[2]))
    hue = rbx_colour.hue_name(math.degrees(math.atan2(lab[2], lab[1])) % 360)
    gains = float(mean.mean()) / np.maximum(mean, 1e-6)  # von Kries: the neutral surface made grey, its brightness kept
    balanced = lin * gains
    res = {"cast": {"chroma": round(chroma, 2), "hue": hue, "graded": chroma >= TINTED, "measured_on": where,
                    "neutral_srgb": _hex(to_srgb(mean))},
           "gains": [round(float(g), 4) for g in gains], "samples": []}
    for name, (x0, y0, x1, y1) in samples:
        raw = lin[y0:y1, x0:x1].reshape(-1, 3).mean(0)
        bal = raw * gains
        raw_s, bal_s = to_srgb(raw), to_srgb(bal)
        raw_lab, bal_lab = rbx_colour.srgb_to_lab(raw_s), rbx_colour.srgb_to_lab(bal_s)
        res["samples"].append({"name": name, "raw": _hex(raw_s), "balanced": _hex(bal_s),
                               "balanced_linear": [round(float(v), 4) for v in np.clip(bal, 0, 1)],
                               "raw_lab": [round(float(v), 1) for v in raw_lab],
                               "balanced_lab": [round(float(v), 1) for v in bal_lab],
                               "grading_did": rbx_colour.colour_words(raw_lab, bal_lab)})
    if out is None:
        stem = os.path.splitext(os.path.basename(path))[0]
        out = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", "colour", f"{stem}_balanced.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    Image.fromarray((to_srgb(balanced) * 255).round().astype(np.uint8)).save(out)
    res["balanced_picture"] = out
    return res


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "refs colour: give a picture",
                          "next_action": "lune run kit refs colour <picture> --neutral x0,y0,x1,y1 --sample grip=..."}))
        return 1
    neutral = _box(argv[argv.index("--neutral") + 1]) if "--neutral" in argv else None
    samples = []
    for i, a in enumerate(argv):
        if a == "--sample" and i + 1 < len(argv) and "=" in argv[i + 1]:
            name, box = argv[i + 1].split("=", 1)
            samples.append((name, _box(box)))
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    res = measure(argv[0], neutral, samples, out)
    c = res["cast"]
    rows = [f"  {s['name']:<16} raw {s['raw']}  balanced {s['balanced']}  (the grading made it {s['grading_did']})"
            for s in res["samples"]]
    verdict = (f"COLOUR-GRADED: a {c['hue']} cast of chroma {c['chroma']:g} on {c['measured_on']}" if c["graded"]
               else f"neutral (chroma {c['chroma']:g} on {c['measured_on']})")
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"refs colour {os.path.basename(argv[0])}: {verdict}",
                      "next_action": ("sample from the BALANCED colours (or the balanced picture): "
                                      f"{res['balanced_picture']}" if c["graded"] else
                                      "its colours can be sampled as they are") +
                      ("" if neutral else " — give --neutral x0,y0,x1,y1 on a surface you know is grey / black / "
                       "white for a sure answer"), "rows": rows, **res}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
