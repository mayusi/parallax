"""mod_gate.py - the image half of the kit's MODERATION GATE (kit/lib/moderation.luau holds the words half).

Why it exists: Roblox moderates the account that uploads blood or gore (pools and splats included): Open Cloud then
answers 403 'User is moderated' to every call. An uploaded image is judged on its own - a game's age label does not
cover it. So before anything is sent, every image is measured here and one that
reads as blood is held back.

What it measures, per PNG (pixels with alpha >= 0.5 are "shown"):
  crimson  - the share of shown pixels in blood's colour: hue within 20 degrees of red (340..12), saturation
             >= 0.45, value 0.10..0.85 (dark to mid red; fire's bright orange-yellow core and a pure glow at full
             value are NOT blood's colour). Blood on a decal is most of what the decal shows.
  blobs    - how many separate crimson patches (8-connected, >= 0.02% of the image each) - a splatter is many.
  flagged  - crimson >= HOLD_SHARE, or crimson >= SPLAT_SHARE with >= SPLAT_BLOBS patches.
The thresholds were set on the kit's own built textures (fire, auras, UI art, model maps: none flagged, the
highest crimson share measured is kept in the selftest note) and the selftest's drawn pool and splatter (both
flagged). A flagged image is never "probably fine": the owner clears it by name (kit moderation clear), or it
stays home.

Usage: python -I kit/tools/mod_gate.py <png> [<png> ...]   -> one JSON line: {"images": [...], "flagged": n}
Exit 0 always when it could read the files (the verdict is in the JSON); 2 when a file cannot be read.
"""

import json
import sys

import numpy as np
from PIL import Image

HOLD_SHARE = 0.30     # most of what the image shows is blood-red: a pool, a smear, a red decal
SPLAT_SHARE = 0.08    # a fair part of it, in many separate drops: a splatter
SPLAT_BLOBS = 6
BLOB_MIN = 0.0002     # a patch smaller than this share of the image is noise, not a drop


def crimson_mask(rgba):
    a = rgba[..., 3].astype(np.float32) / 255.0
    rgb = rgba[..., :3].astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    d = mx - mn
    sat = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.0)
    # hue in degrees (red at 0)
    hue = np.zeros_like(mx)
    m = d > 1e-6
    rr = m & (mx == r)
    gg = m & (mx == g) & ~rr
    bb = m & ~rr & ~gg
    hue[rr] = (60.0 * ((g[rr] - b[rr]) / d[rr])) % 360.0
    hue[gg] = 60.0 * ((b[gg] - r[gg]) / d[gg]) + 120.0
    hue[bb] = 60.0 * ((r[bb] - g[bb]) / d[bb]) + 240.0
    red_hue = (hue >= 340.0) | (hue <= 12.0)
    shown = a >= 0.5
    crim = shown & m & red_hue & (sat >= 0.45) & (mx >= 0.10) & (mx <= 0.85)
    return crim, shown


def blobs(mask, min_px):
    """8-connected patches of the mask of at least min_px pixels (an iterative fill: no scipy needed)."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    count = 0
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if seen[y0, x0]:
            continue
        stack = [(y0, x0)]
        seen[y0, x0] = True
        size = 0
        while stack:
            y, x = stack.pop()
            size += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if size >= min_px:
            count += 1
    return count


def measure(path):
    im = Image.open(path).convert("RGBA")
    # measured at up to 512 px on the long side: the share does not change, the patch count barely does
    scale = 512.0 / max(im.size)
    if scale < 1.0:
        im = im.resize((max(1, round(im.size[0] * scale)), max(1, round(im.size[1] * scale))), Image.NEAREST)
    rgba = np.asarray(im)
    crim, shown = crimson_mask(rgba)
    n_shown = int(shown.sum())
    share = float(crim.sum()) / n_shown if n_shown else 0.0
    patches = blobs(crim, max(2, int(BLOB_MIN * crim.size))) if share >= SPLAT_SHARE else 0
    flagged = share >= HOLD_SHARE or (share >= SPLAT_SHARE and patches >= SPLAT_BLOBS)
    why = ""
    if share >= HOLD_SHARE:
        why = f"{share:.0%} of what it shows is blood-red"
    elif flagged:
        why = f"{share:.0%} blood-red in {patches} separate patches (a splatter)"
    return {"file": path, "crimson": round(share, 4), "patches": patches, "shown": n_shown,
            "flagged": bool(flagged), "why": why}


def main(argv):
    out, bad = [], []
    for p in argv:
        try:
            out.append(measure(p))
        except Exception as e:  # a file that cannot be read is reported, never skipped
            bad.append({"file": p, "error": str(e)[:200]})
    print(json.dumps({"images": out, "unreadable": bad, "flagged": sum(1 for r in out if r["flagged"])}))
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
