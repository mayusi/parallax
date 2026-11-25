"""flares.py - the KANADA light flare as a 4x4 flipbook (research 2026-10-23, board/plans/archive/vfx-research-2026-10-23.md):
the straight-line flare of 1980s-to-now anime effects animation (Kanada's "straight speedlines, light flares and
minimalist impact frames"; Demon Slayer announces every sword strike with "a glint on the blade"). Never a soft lens
glow: razor-straight lines through a hot centre - a long cross, short diagonals, each thickest at the centre - and two
ghost rings along the long axis. The sheet SNAPS open (frames 0-3), holds and twinkles (4-9: the diagonals blink on
twos), then draws in (10-15): play it OneShot at ~24 fps for a 0.66 s glint, or let `blade_glint` time it.

    python kit/vfx/flares.py          then: lune run kit vfx (registers + builds it)

  kanada_flare   white on transparent (tint it per layer), 1024 px sheet, 256 px cells
Writes _downloads/kit_generated/textures/<name>.png + assets/textures/<name>.json; prints one JSON line.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

OUT = os.path.join("_downloads", "kit_generated", "textures")
SPECS = os.path.join("assets", "textures")
CELL, GRID = 256, 4


def flare_cell(open_k, twinkle, rot):
    """One cell: open_k 0..1 = how far the lines reach, twinkle 0/1 = the diagonals lit, rot = the cross's tilt."""
    y, x = (np.mgrid[0:CELL, 0:CELL].astype(np.float32) + 0.5) / CELL - 0.5
    a = np.zeros((CELL, CELL), np.float32)
    for k in range(4):
        ang = rot + k * math.pi / 4
        dx, dy = math.cos(ang), math.sin(ang)
        long_ = k % 2 == 0
        if not long_ and not twinkle:
            continue
        length = (0.47 if long_ else 0.2) * open_k
        if length <= 0:
            continue
        along = np.abs(x * dx + y * dy)
        acr = np.abs(x * dy - y * dx)
        width = (0.011 if long_ else 0.007) * np.clip(1 - along / length, 0, 1) + 0.0012  # thickest at the centre
        a = np.maximum(a, np.clip(1 - (acr - width) * CELL, 0, 1) * (along < length))  # 1 px anti-aliased edge
    for k in (1, 2):  # ghost rings along the long axis
        cx, cy = math.cos(rot) * 0.15 * k * open_k, math.sin(rot) * 0.15 * k * open_k
        rr = 0.018 * k * open_k
        if rr > 0.002:
            ring = np.abs(np.hypot(x - cx, y - cy) - rr)
            a = np.maximum(a, np.clip(1 - (ring - 0.002) * CELL, 0, 1) * 0.85)
    core = np.hypot(x, y)
    a = np.maximum(a, np.clip(1 - (core - 0.018 * (0.4 + open_k)) * CELL * 0.6, 0, 1))  # the hot centre
    return np.clip(a, 0, 1)


def sheet(rot=0.3):
    out = np.zeros((CELL * GRID, CELL * GRID), np.float32)
    for f in range(GRID * GRID):
        if f < 4:
            k = (f + 1) / 4  # snaps open
        elif f < 10:
            k = 1.0 - 0.04 * ((f + 1) % 2)  # holds, a little breath (from frame 4: 3 and 4 were identical - fxfinish frames_change)
        else:
            k = 1.0 - (f - 9) / 6  # draws in
        twinkle = 1 if (4 <= f < 10 and (f // 2) % 2 == 0) or f < 4 else 0
        r, c = divmod(f, GRID)
        out[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL] = flare_cell(max(k, 0.0), twinkle, rot)
    return out


FLARES = {"kanada_flare": (sheet, "the Kanada light flare: razor-straight lines through a hot centre (a long cross, short diagonals that blink on twos, two ghost rings), snapping open, holding, drawing in - a sword's glint, a hit's spark; white, tint per layer")}


def main(names):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SPECS, exist_ok=True)
    made = []
    for name in names or list(FLARES):
        fn, about = FLARES[name]
        a = fn()
        rgba = np.dstack([np.full(a.shape + (3,), 255, np.uint8), (a * 255).astype(np.uint8)])
        png = os.path.join(OUT, f"{name}.png")
        Image.fromarray(rgba, "RGBA").save(png)
        spec = {"engine": "fx", "recipe": "import", "about": about + " (kit/vfx/flares.py)", "pack": "kit generated (flares)",
                "source": png.replace(os.sep, "/"), "frames": GRID * GRID, "grid": GRID, "cell": CELL, "premultiply": True,
                "post": {"alpha": "coverage", "tonemap": False}}
        with open(os.path.join(SPECS, f"{name}.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(spec, fh, indent=1)
        made.append({"name": name, "mean_alpha": round(float(a.mean()), 4)})
    print(json.dumps({"status": "pass", "summary": f"flares: {len(made)} flipbook(s) written", "next_action": "lune run kit vfx (registers + builds them)", "flares": made}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
