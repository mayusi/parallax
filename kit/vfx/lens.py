"""lens.py - the LENS textures (board/plans/archive/aaa-vfx-research.md, camera and screen): the camera's own marks a huge hit leaves,
drawn as full-screen images because Roblox has no lens post effects. The `lens` layer (VfxStage builders.lens, the
player's LensLayer) stretches them over the screen and fades them by curves.

    python kit/vfx/lens.py            then: lune run kit vfx (registers + builds them)

  lens_vignette  black, clear in the middle, closing in at the corners (focus, weight)
  lens_fringe    a thin white ring hugging the screen edge: the `lens` layer draws it twice, tinted red and cyan at two
                 sizes - the colour split at the frame's edge that chromatic aberration makes (Roblox cannot split a
                 rendered frame's channels: this is the honest stand-in)
  lens_dirt      soft smudges and hexagonal bokeh specks (the dirty lens a flash lights up)
  lens_zoom      radial speed streaks, clear in the centre (the zoom-blur rush of an anime / ZZZ impact)
  lens_streaks   parallel speed lines (research 2026-10-23: directional speed lines / motion streaks), turned by the layer
Writes _downloads/kit_generated/textures/<name>.png + assets/textures/<name>.json; prints one JSON line.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

N = 1024
OUT = os.path.join("_downloads", "kit_generated", "textures")
SPECS = os.path.join("assets", "textures")


def radius():
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float64)
    x, y = (xx + 0.5) / N * 2 - 1, (yy + 0.5) / N * 2 - 1
    return x, y, np.sqrt(x * x + y * y) / math.sqrt(2)  # 0 centre .. 1 corner


def smooth(e0, e1, v):
    t = np.clip((v - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def vignette():
    _, _, r = radius()
    a = smooth(0.42, 1.0, r) ** 1.3
    return np.zeros((N, N, 3)), a


def fringe():
    x, y, _ = radius()
    edge = np.maximum(np.abs(x), np.abs(y))  # 0 centre .. 1 at the screen's edge (a rounded box, not a circle)
    soft = (np.abs(x) ** 4 + np.abs(y) ** 4) ** (1 / 4)  # a rounded box: the corners bend like a lens
    d = np.minimum(edge, soft)
    a = smooth(0.90, 0.985, d) * 0.55 * (0.6 + 0.4 * smooth(0.5, 1.0, np.sqrt(x * x + y * y) / math.sqrt(2)))
    return np.ones((N, N, 3)), a


def dirt():
    rng = np.random.default_rng(1337)
    img = Image.new("L", (N, N), 0)
    g = ImageDraw.Draw(img)
    for _ in range(26):  # smudges: big soft blobs
        cx, cy, rr = rng.uniform(0, N), rng.uniform(0, N), rng.uniform(60, 220)
        g.ellipse((cx - rr, cy - rr * rng.uniform(0.5, 1), cx + rr, cy + rr), fill=int(rng.uniform(25, 70)))
    img = img.filter(ImageFilter.GaussianBlur(40))
    spots = Image.new("L", (N, N), 0)
    s = ImageDraw.Draw(spots)
    for _ in range(90):  # bokeh: small hexagons, a bright rim
        cx, cy, rr = rng.uniform(0, N), rng.uniform(0, N), rng.uniform(6, 26)
        rot = rng.uniform(0, math.pi / 3)
        pts = [(cx + rr * math.cos(rot + k * math.pi / 3), cy + rr * math.sin(rot + k * math.pi / 3)) for k in range(6)]
        s.polygon(pts, fill=int(rng.uniform(50, 140)), outline=int(rng.uniform(140, 220)))
    spots = spots.filter(ImageFilter.GaussianBlur(1.6))
    a = np.clip((np.asarray(img, np.float64) + np.asarray(spots, np.float64)) / 255.0, 0, 1)
    return np.ones((N, N, 3)), a


def zoom():
    x, y, r = radius()
    ang = np.arctan2(y, x)
    rng = np.random.default_rng(77)
    k = 220
    phases = rng.uniform(0, 1, k)
    widths = rng.uniform(0.15, 0.6, k)
    starts = rng.uniform(0.25, 0.55, k)
    idx = ((ang + math.pi) / (2 * math.pi) * k).astype(int) % k
    frac = ((ang + math.pi) / (2 * math.pi) * k) % 1.0
    line = np.clip(1 - np.abs(frac - phases[idx]) / (widths[idx] * 0.5), 0, 1) ** 2
    a = line * smooth(starts[idx], starts[idx] + 0.25, r)
    return np.ones((N, N, 3)), np.clip(a, 0, 1)


def streaks():
    """parallel speed lines along X, SEAMLESS in X with TWO periods across the sheet (the lens layer shows half of it and
    scrolls along x, so the lines move along their own length and never snap back - review 3, 2026-10-23): ~150 rows,
    each its own weight, start, length and taper; the middle band (where the action is) kept sparse"""
    x, y, _ = radius()
    rng = np.random.default_rng(91)
    a = np.zeros((N, N))
    xp = (x + 1) / 2 % 0.5  # 0..0.5, two periods across the sheet
    for ry in rng.uniform(-1, 1, 150):
        if abs(ry) < 0.22 and rng.random() < 0.8:  # keep the centre band clear
            continue
        w = rng.uniform(0.0015, 0.007) * (0.6 + abs(ry))
        x0, ln = rng.uniform(0, 0.5), rng.uniform(0.08, 0.3)
        t = ((xp - x0) % 0.5) / ln  # wraps at the period: seamless
        prof = np.sin(np.pi * np.clip(t, 0, 1)) * (t < 1)
        line = np.clip(1 - np.abs(y - ry) / (w * prof + 1e-6), 0, 1) * (prof > 0.02)
        a = np.maximum(a, line * rng.uniform(0.5, 1.0))
    return np.ones((N, N, 3)), np.clip(a, 0, 1)


def soft(n=512):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    x, y = (xx + 0.5) / n * 2 - 1, (yy + 0.5) / n * 2 - 1
    return x, y, np.sqrt(x * x + y * y)  # 0 centre .. 1 the picture's edge (the middle of a side)


def glow():
    """a flare's glow: a hot core falling away to nothing well inside the picture's edge"""
    _, _, r = soft()
    a = np.clip(1 - r, 0, 1) ** 2.2 * 0.75 + np.exp(-(r / 0.12) ** 2) * 0.6
    return np.ones(a.shape + (3,)), np.clip(a, 0, 1)


def ghost():
    """a flare's ghost: a faint disc with a brighter rim (the iris seen out of focus), clear outside it"""
    _, _, r = soft()
    a = (0.28 + 0.5 * np.exp(-((r - 0.84) / 0.05) ** 2)) * (1 - smooth(0.88, 0.96, r))
    return np.ones(a.shape + (3,)), np.clip(a, 0, 1)


def streak():
    """a flare's anamorphic streak: a thin level line, hot in the middle, thinning to both ends"""
    x, y, _ = soft()
    along = np.clip(1 - np.abs(x), 0, 1) ** 1.6
    a = along * np.exp(-(y / (0.02 + 0.05 * along)) ** 2)
    return np.ones(a.shape + (3,)), np.clip(a, 0, 1)


LENS = {
    "lens_glow": (glow, "a soft round glow, hot in the middle: a lens flare's light (the lens layer's `flare`)"),
    "lens_ghost": (ghost, "a faint disc with a brighter rim: a lens flare's ghost (the lens layer's `flare`)"),
    "lens_streak": (streak, "a thin level line of light, hot in the middle: a lens flare's anamorphic streak (the lens layer's `flare`)"),
    "lens_vignette": (vignette, "black, clear in the middle, closing in at the corners: the lens layer's vignette"),
    "lens_fringe": (fringe, "a thin white ring at the screen edge: drawn twice (red / cyan, two sizes) = the lens layer's colour fringe (chromatic aberration stand-in)"),
    "lens_dirt": (dirt, "soft smudges + hexagonal bokeh specks: the lens layer's dirty lens lit by a flash"),
    "lens_zoom": (zoom, "radial speed streaks, clear centre: the lens layer's zoom-blur rush"),
    "lens_streaks": (streaks, "parallel speed lines across the screen, sparse in the middle band: the lens layer's directional motion streaks (turned by streakAngle)"),
}


def main(names):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SPECS, exist_ok=True)
    made = []
    for name in names or list(LENS):
        fn, about = LENS[name]
        rgb, a = fn()
        rgba = np.dstack([(rgb * 255).astype(np.uint8), (np.clip(a, 0, 1) * 255).astype(np.uint8)])
        png = os.path.join(OUT, f"{name}.png")
        Image.fromarray(rgba, "RGBA").save(png)
        spec = {"engine": "fx", "recipe": "import", "about": about + " (kit/vfx/lens.py)", "pack": "kit generated (lens)",
                "source": png.replace(os.sep, "/"), "frames": 1, "grid": 1, "cell": 0, "premultiply": False,
                "post": {"alpha": "coverage", "tonemap": False, "border": 0}}
        with open(os.path.join(SPECS, f"{name}.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(spec, fh, indent=1)
        made.append({"name": name, "mean_alpha": round(float(a.mean()), 3), "centre_alpha": round(float(a[a.shape[0] // 2, a.shape[1] // 2]), 3)})
    print(json.dumps({"status": "pass", "summary": f"lens: {len(made)} texture(s) written", "next_action": "lune run kit vfx (registers + builds them)", "lens": made}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
