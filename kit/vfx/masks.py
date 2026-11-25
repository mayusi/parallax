"""masks.py - the VFX MASK LIBRARY (board/plans/archive/aaa-vfx-research.md: pros keep named, reusable erosion / flow / noise
masks; Simon Truempler, "How to (Not) Create Textures for VFX", GDC 2022). Every mask TILES seamlessly (built from
periodic noise: FFT-filtered random fields and wrap-around cell patterns), is white with the pattern in its ALPHA (the
preset's colour tints it), and is registered as a texture spec, so a mesh shell can scroll it (uvScroll) and a sprite
can wear it.

    python kit/vfx/masks.py [name ...]        (no names: all)   then: lune run kit vfx (registers + builds them)

  mask_fbm       soft cloudy noise: smoke shells, heat, generic breakup
  mask_cells     rounded cells (Voronoi F1): dissolve into blobs, scales, boiling plasma
  mask_cracks    thin cell edges (Voronoi F2 - F1): cracked ground, ice, shattering energy
  mask_streaks   noise stretched along V (the axis a Roblox beam runs along): wind-torn, speed, smears
  mask_caustics  bright warped ridges: water light, magic shimmer
  mask_electric  thin ridged filaments: electricity, veins of energy
  mask_swirl     noise advected round a curl field: vortex, portal, liquid swirl
  mask_heat      soft vertical wave bands: heat shimmer over fire
  mask_sparkle   sparse sharp dots: glitter, stars, ki dust
Writes _downloads/kit_generated/textures/<name>.png + assets/textures/<name>.json; prints one JSON line.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

N = 512
OUT = os.path.join("_downloads", "kit_generated", "textures")
SPECS = os.path.join("assets", "textures")


def field(beta, seed, n=N, aniso=(1.0, 1.0)):
    """a periodic gaussian random field with a 1/f^beta spectrum (tiles exactly: it lives on a torus), 0..1"""
    rng = np.random.default_rng(seed)
    fy = np.fft.fftfreq(n)[:, None] * aniso[1]
    fx = np.fft.fftfreq(n)[None, :] * aniso[0]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1
    amp = 1.0 / f ** beta
    amp[0, 0] = 0
    spec = (rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))) * amp
    v = np.real(np.fft.ifft2(spec))
    v -= v.min()
    return v / max(v.max(), 1e-9)


def voronoi(cells, seed, n=N):
    """F1 and F2 distances to points on a torus (wrap-around), normalised"""
    rng = np.random.default_rng(seed)
    pts = rng.random((cells, 2)) * n
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    f1 = np.full((n, n), 1e9, np.float32)
    f2 = np.full((n, n), 1e9, np.float32)
    for px, py in pts:
        dx = np.abs(xx - px)
        dx = np.minimum(dx, n - dx)
        dy = np.abs(yy - py)
        dy = np.minimum(dy, n - dy)
        d = np.sqrt(dx * dx + dy * dy)
        f2 = np.where(d < f1, f1, np.minimum(f2, d))
        f1 = np.minimum(f1, d)
    scale = n / np.sqrt(cells)
    return f1 / scale, f2 / scale


def warp(img, dx, dy):
    """sample img at (x + dx, y + dy) with wrap-around (bilinear)"""
    n = img.shape[0]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    x = (xx + dx) % n
    y = (yy + dy) % n
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    x1, y1 = (x0 + 1) % n, (y0 + 1) % n
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy)
            + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def norm(v, lo=1.0, hi=99.0):
    a, b = np.percentile(v, lo), np.percentile(v, hi)
    return np.clip((v - a) / max(b - a, 1e-9), 0, 1)


def m_fbm():
    return norm(field(1.6, 11))


def m_cells():
    f1, _ = voronoi(48, 21)
    return norm(1 - np.clip(f1 * 1.4, 0, 1) ** 1.5)


def m_cracks():
    f1, f2 = voronoi(40, 31)
    edge = np.clip((f2 - f1) * 7.0, 0, 1)
    jitter = field(1.4, 32) * 0.35
    return norm(np.clip(1 - edge - jitter * (1 - edge), 0, 1) ** 3)


def m_streaks():
    return norm(field(1.4, 41, aniso=(0.12, 1.0)))


def m_caustics():
    # the web of bright curved lines light makes through water: cell EDGES (F2 - F1) on smoothly warped coordinates, glowing
    f1, f2 = voronoi(28, 51)
    web = np.exp(-(f2 - f1) * 9.0)
    w = warp(web, (field(2.4, 52) - 0.5) * 70, (field(2.4, 53) - 0.5) * 70)
    return norm(w ** 1.4, 1, 99.7)


def m_electric():
    # thin filaments: the iso-lines of a SMOOTH field (one bright line where it crosses 0.5), a finer field branching off
    a = field(2.7, 61)
    b = field(2.2, 62)
    line = np.exp(-np.abs(a - 0.5) * 70) + 0.55 * np.exp(-np.abs(b - 0.5) * 110)
    return norm(np.clip(line, 0, 1.2), 1, 99.8)


def m_swirl():
    # noise dragged round the vortices of a divergence-free (curl) field: each step moves the pattern ~2 px
    psi = field(2.6, 71)
    vx = (np.roll(psi, -1, 0) - np.roll(psi, 1, 0))
    vy = -(np.roll(psi, -1, 1) - np.roll(psi, 1, 1))
    k = 2.0 / max(np.abs(vx).max(), np.abs(vy).max(), 1e-9)
    vx, vy = vx * k, vy * k
    img = field(1.2, 72)
    for _ in range(40):
        img = warp(img, -vx, -vy)
    return norm(img)


def m_heat():
    # a few soft, slowly wavering vertical bands (shimmer rises: scroll it up the column)
    xx = np.mgrid[0:N, 0:N][1] / N
    v = field(2.4, 81, aniso=(1.0, 0.35))
    bands = 0.5 + 0.5 * np.sin(xx * 2 * np.pi * 4 + (v - 0.5) * 5)
    return norm(bands ** 1.5 * 0.8 + field(1.8, 82) * 0.2)


def m_sparkle():
    rng = np.random.default_rng(91)
    img = np.zeros((N, N))
    for _ in range(140):
        x, y, r = rng.integers(0, N), rng.integers(0, N), rng.uniform(1.0, 3.2)
        yy, xx = np.mgrid[-8:9, -8:9]
        d = np.sqrt(xx * xx + yy * yy)
        dot = np.clip(1 - d / r, 0, 1) ** 2 + np.clip(1 - (np.minimum(np.abs(xx), np.abs(yy)) / 0.7), 0, 1) * np.clip(1 - d / (r * 2.5), 0, 1) * 0.6
        ys, xs = (np.arange(-8, 9) + y) % N, (np.arange(-8, 9) + x) % N
        img[np.ix_(ys, xs)] = np.maximum(img[np.ix_(ys, xs)], dot)
    return np.clip(img, 0, 1)


MASKS = {
    "mask_fbm": (m_fbm, "soft cloudy tileable noise: smoke shells, heat, generic breakup"),
    "mask_cells": (m_cells, "rounded tileable cells (Voronoi F1): dissolve into blobs, scales, boiling plasma"),
    "mask_cracks": (m_cracks, "thin tileable cell edges (Voronoi F2 - F1): cracked ground, ice, shattering energy"),
    "mask_streaks": (m_streaks, "tileable noise stretched along V (a beam's length axis): wind-torn, speed, smears"),
    "mask_caustics": (m_caustics, "bright warped tileable ridges: water light, magic shimmer"),
    "mask_electric": (m_electric, "thin ridged tileable filaments: electricity, energy veins"),
    "mask_swirl": (m_swirl, "tileable noise advected round a curl field: vortex, portal, liquid swirl"),
    "mask_heat": (m_heat, "soft wavy tileable bands: heat shimmer over fire"),
    "mask_sparkle": (m_sparkle, "sparse sharp tileable dots with tiny crosses: glitter, stars, ki dust"),
}


def seam_error(a):
    """how far the mask is from tiling: the jump across each wrap edge vs the jump between neighbours inside"""
    inner = np.mean(np.abs(np.diff(a, axis=1))) + np.mean(np.abs(np.diff(a, axis=0)))
    edge = np.mean(np.abs(a[:, 0] - a[:, -1])) + np.mean(np.abs(a[0, :] - a[-1, :]))
    return float(edge / max(inner, 1e-9))


def main(names):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SPECS, exist_ok=True)
    made, bad = [], []
    for name in names or list(MASKS):
        if name not in MASKS:
            bad.append(f"{name}: unknown mask ({', '.join(MASKS)})")
            continue
        fn, about = MASKS[name]
        a = fn().astype(np.float64)
        seam = seam_error(a)
        if seam > 1.6:
            bad.append(f"{name}: does not tile (seam {seam:.2f}x the inner step)")
        rgba = np.dstack([np.full((N, N), 255, np.uint8)] * 3 + [(a * 255).astype(np.uint8)])
        png = os.path.join(OUT, f"{name}.png")
        Image.fromarray(rgba, "RGBA").save(png)
        spec = {"engine": "fx", "recipe": "import", "about": about + " (kit/vfx/masks.py)", "pack": "kit generated (procedural, tileable)",
                "source": png.replace(os.sep, "/"), "frames": 1, "grid": 1, "cell": 0, "premultiply": False,
                "post": {"alpha": "coverage", "tonemap": False, "border": 0}}
        with open(os.path.join(SPECS, f"{name}.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(spec, fh, indent=1)
        made.append({"name": name, "seam": round(seam, 2), "mean": round(float(a.mean()), 3)})
    status = "fail" if bad else "pass"
    print(json.dumps({"status": status, "summary": f"masks: {len(made)} tileable mask(s) written" + (f"; {'; '.join(bad)}" if bad else ""),
                      "next_action": "lune run kit vfx (registers + builds them), then LOOK at build/textures/_fx_review.png" if not bad else "fix the mask generator",
                      "masks": made}))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
