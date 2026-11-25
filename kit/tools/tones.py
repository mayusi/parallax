"""tones.py — a material's COLOURS measured from a real photo, not guessed: the object's pixels (a cutout's alpha, or
every pixel) in LINEAR light -> its base (median), its cavity tone (the darkest tenth: what settles in recesses) and
its edge tone (the lightest tenth: worn, bleached, polished) -> a.material(color=...) and the grime tone to use.

    python kit/tools/tones.py <photo | albedo.npz> [--mask <cutout.png>] [--json out.json]

Best on an ALBEDO (`kit vision albedo`: lighting taken out); on a plain photo the cavity tone includes shadow.
"""

import argparse
import json
import sys

import numpy as np


def to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def tones(rgb, alpha=None):
    """rgb (H, W, 3) 0..1 sRGB, alpha (H, W) 0..1 or None -> {"base", "cavity", "edge"} linear RGB, "spread" (the
    luminance's 10-90% range over the median: how much the colour varies), "pixels"; and the grime tone it suggests"""
    lin = to_linear(np.asarray(rgb, dtype=np.float64)[..., :3]).reshape(-1, 3)
    if alpha is not None:
        lin = lin[np.asarray(alpha).reshape(-1) > 0.5]
    if len(lin) < 50:
        raise ValueError("tones: fewer than 50 object pixels — a cutout mask with the object in it")
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    lo, mid, hi = np.percentile(lum, [10, 50, 90])
    pick = lambda m: [round(float(x), 4) for x in lin[m].mean(axis=0)]  # noqa: E731
    base = pick(np.abs(lum - mid) <= max((hi - lo) * 0.1, 1e-4))
    cavity, edge = pick(lum <= lo), pick(lum >= hi)
    warm = cavity[0] > cavity[2] * 1.6     # (a cavity red over blue: a warm ochre-brown — stain, not dirt)
    light = mid > 0.25
    grime = "stain" if (warm and light) else ("dust" if mid < 0.08 else "dirt")
    return {"base": base, "cavity": cavity, "edge": edge, "spread": round(float((hi - lo) / max(mid, 1e-6)), 3),
            "pixels": int(len(lin)), "grime_tone": grime}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("--mask")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    from PIL import Image  # noqa: PLC0415

    if a.photo.endswith(".npz"):   # (kit vision albedo's output: the colour with the light taken out, and its mask)
        d = np.load(a.photo)
        rgb = np.asarray(d["albedo"], dtype=np.float64)
        alpha = np.asarray(d["mask"], dtype=np.float64) if "mask" in d.files else np.ones(rgb.shape[:2])
        im = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    else:
        im = Image.open(a.photo).convert("RGBA")
        rgb = np.asarray(im, dtype=np.float64)[..., :3] / 255.0
        alpha = np.asarray(im, dtype=np.float64)[..., 3] / 255.0
    if a.mask:
        m = Image.open(a.mask).convert("RGBA").resize(im.size)
        alpha = np.asarray(m, dtype=np.float64)[..., 3] / 255.0
    if alpha.min() > 0.99:
        alpha = None
    try:
        t = tones(rgb, alpha)
    except ValueError as e:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"materials --tones: {e}",
                          "next_action": "give a cutout (kit vision cutout) whose alpha holds the object"}))
        return 1
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(t, fh, indent=2)
    print(json.dumps({"schema": 1, "status": "pass", "tones": t,
                      "summary": f"tones of {a.photo}: base {t['base']} (linear), cavity {t['cavity']}, edge "
                                 f"{t['edge']}, spread {t['spread']}, grime_tone {t['grime_tone']}",
                      "next_action": f"a.material(..., **rbx.look(..., color={tuple(t['base'])}), grime_tone="
                                     f"\"{t['grime_tone']}\") — then look at the render beside the photo"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
