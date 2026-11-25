"""aura.py — ki auras and their elements, generated from primitives (numpy only: runs inside Blender's python too).

fxlab recipe "aura" (assets/textures/<name>.json: {"engine": "fx", "recipe": "aura", "frames": 16, "grid": 4,
"cell": 256, "params": {"kind": ..., ...}}) writes frames straight to build/fxlab/<name>/ (no Blender render);
kit/vfx/fxfinish.py finishes them like any other. Every element is WHITE / grey (tint it per form with the sprite's
colour sequence); a two-tone aura is two layers (an outer tinted aura + a smaller inner one near white).

kinds (params):
  body    a full-body aura around a standing figure, looping: an oval hugging the body that rises into a pointed
          crown, its edge broken into flames that stream upward, brighter at the rim and streaked inside.
          style smooth | jagged (spiky, DBZ Super Saiyan 2/3, Kaio-ken) | wisp (layered rippling sheets, Ultra
          Instinct); width 0.55, height 0.85, crown 0.6 (how pointed the top), flames 1.0 (edge amplitude),
          streaks 0.6, rim 0.65, speed 1 (loops per sheet), seed
  lick    one flame tongue rising off the aura and pinching off (one-shot). style smooth | jagged
  spark   ki lightning: a jagged bolt with branches, re-drawn every frame (crackle), flickering (one-shot)
  sparkle a four-point twinkle that blooms and fades (one-shot)
  flash   a power-up flash: a hot core swelling, a ring and radial streaks (one-shot)
  streaks a TILEABLE flame-lick strip for 3D mesh shells (one frame, wraps both ways; tongues point UP, scroll it up
          with uvScroll): staggered bands of tongues, wide and hot at the base, pinching to points. columns 6 (tongues
          across), bands 2 (rows of tongues), sharp 1.0, seed
  rays    a TILEABLE field of fine VERTICAL light streaks on a light floor (one frame, wraps both ways): the striated
          inside of a Dragon Ball aura — never dark (floor 0.45), streaks 24 across, length 3 (rows), seed. Scroll it up
  cells   a TILEABLE field of soft bubbly CELLS (worley noise: light cells, darker seams; one frame, wraps both ways):
          the churning skin of a giant energy ball (Spirit Bomb); cells 7 across, seed. Put it on a sphere, scroll + spin it
  bolt    a TILEABLE lightning strip for beams (one frame, n wide x n/4 tall, wraps along x, dark top and bottom so a
          beam has no hard sides): a zig-zag bolt with a white core and a glow, a thin fork; kinks 14, width 0.035, seed.
          Spec it with "wrap": true, "beam": true; scroll it fast (textureSpeed) and re-spawn the beam to flicker
Rows are written top-first (image order), linear, premultiplied by coverage, values above 1 kept (HDR)."""
import math

import numpy as np

TAU = math.pi * 2


def grid(n):
    v = (np.arange(n) + 0.5) / n * 2 - 1
    x, y = np.meshgrid(v, -v)  # row 0 = top (y = +1)
    return x, y


def _smooth(t):
    return t * t * (3 - 2 * t)


def vnoise(x, y, fx, fy, seed, wrap_y=None):
    """value noise at frequency (fx, fy); wrap_y = integer cells after which it repeats in y (a seamless loop)"""
    rng = np.random.default_rng(seed)
    cx, cy = int(fx * 4) + 8, int(fy * 4) + 8
    if wrap_y:
        cy = int(wrap_y)
    g = rng.random((cy + 1, cx + 1))
    if wrap_y:
        g[cy] = g[0]
    u, v = (x + 1.0) * 0.5 * fx + 2.0, y * fy
    if wrap_y:
        v = np.mod(v, cy)
    else:
        v = v + cy * 0.5
    i0, j0 = np.floor(u).astype(int) % cx, np.floor(v).astype(int) % cy
    i1, j1 = (i0 + 1) % (cx + 1), j0 + 1
    su, sv = _smooth(u - np.floor(u)), _smooth(v - np.floor(v))
    a = g[j0, i0] * (1 - su) + g[j0, i1] * su
    b = g[j1, i0] * (1 - su) + g[j1, i1] * su
    return a * (1 - sv) + b * sv


def fbm(x, y, fx, fy, seed, octaves=4, wrap_y=None, ridged=False):
    tot, amp, out = 0.0, 1.0, 0.0
    for o in range(octaves):
        k = 2 ** o
        n = vnoise(x, y, fx * k, fy * k, seed + o * 31, wrap_y=None if wrap_y is None else wrap_y * k)
        if ridged:
            n = 1 - np.abs(n * 2 - 1)
        out = out + n * amp
        tot += amp
        amp *= 0.5
    return out / tot


def blur(a, sigma):
    if sigma <= 0.3:
        return a
    r = int(sigma * 3) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    a = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, a)
    return np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, a)


def body(n, k, p):
    """one frame (k in 0..1 across the loop) of a full-body aura: an oval round the figure whose edge breaks into
    flame tongues — longer toward the top, bent upward, streaming up — a bright rim, a see-through body and a soft
    glow round the figure"""
    x, y = grid(n)
    style = p.get("style", "smooth")
    W, H = p.get("width", 0.38), p.get("height", 0.46)
    fl = p.get("flames", 1.0)
    seed = int(p.get("seed", 1))
    loops = int(p.get("speed", 1))
    cx, cy = 0.0, -0.3
    ex = x / W
    ey = (y - cy) / H
    rn = np.sqrt(ex * ex + ey * ey)
    th = np.arctan2(ex, ey)  # 0 straight up, +-pi straight down
    upness = np.clip(np.cos(th), 0, 1)  # 1 at the top .. 0 at the sides and below
    # the tongues: noise around the oval, scrolling up the sides (a seamless loop: an integer number of periods)
    if style == "jagged":
        cells, octv, ridged, sharp = 26, 2, True, 2.6
    elif style == "wisp":
        cells, octv, ridged, sharp = 9, 3, False, 1.0
    else:
        cells, octv, ridged, sharp = 15, 3, False, 2.2
    cells = int(p.get("tongues", cells))
    sharp = float(p.get("sharp", sharp))
    u = (np.abs(th) / math.pi) * cells  # 0 at the top .. cells at the bottom, both sides mirrored-ish
    side = np.sign(ex + 1e-9)
    phase = k * cells * 0.5 * loops
    tong = np.zeros_like(x)
    amp = 0.0
    for o in range(octv):
        f = 2 ** o
        rng = np.random.default_rng(seed + o * 13 + (side > 0) * 0)
        g = rng.random(int(cells * f) + 2)
        uu = (u + phase * f / f) * f
        i0 = np.floor(uu).astype(int)
        t = _smooth(uu - i0)
        nv = g[i0 % (len(g) - 1)] * (1 - t) + g[(i0 + 1) % (len(g) - 1)] * t
        if ridged:
            nv = np.clip(1 - np.abs(nv * 2 - 1), 0, 1)
        tong += nv / f
        amp += 1 / f
    tong = np.clip(tong / amp, 0, 1) ** sharp
    reach = fl * (0.15 + p.get("reach", 1.25) * upness ** 1.1) * (0.25 + 0.75 * tong)
    if style == "wisp":
        reach = fl * (0.18 + 0.6 * upness) * (0.5 + 0.5 * tong)
    R = 1.0 + reach
    inside = np.clip((R - rn) / (0.05 + 0.04 * upness), 0, 1)
    inside *= np.clip((y - (cy - H * 1.02)) / 0.1, 0, 1)  # the feet: soft cut
    # brightest round the figure, fading out into the flames (no outline): the way an anime aura is painted
    q = np.clip(rn / R, 0, 1)
    figure = np.exp(-((x / (W * 0.55)) ** 2 + ((y - cy) / (H * 0.9)) ** 2))
    period = 6
    sy = y * 1.5 - k * period * loops
    streak = fbm(x * 7, sy, 7.0, 1.0, seed + 7, octaves=2, wrap_y=period)
    rimw = 0.22 if style != "wisp" else 0.12
    rim = np.clip(1 - (R - rn) / rimw, 0, 1) ** 2 * p.get("rim", 0.3)
    val = 0.32 + 0.6 * (1 - q) ** 1.6 + 0.35 * figure + rim + p.get("streaks", 0.5) * 0.35 * streak * q * (1 - q) * 2
    if style == "wisp":  # nested rippling sheets: soft contour bands inside the edge
        bands = (0.5 + 0.5 * np.cos(q * 4.0 * TAU - tong * 2 + k * loops * TAU)) ** 3
        val = val * 0.75 + 0.4 * bands * q
    a = np.clip(inside * np.clip(val, 0, 1.4), 0, 1)
    e = (blur(a, n * 0.004) * 0.6 + a * 0.6) * 1.5
    return np.dstack([e, e, e, a])


def lick(n, k, p):
    """a flame tongue rising, stretching and pinching off (k = 0..1 over the sheet)"""
    x, y = grid(n)
    seed = int(p.get("seed", 3))
    style = p.get("style", "smooth")
    base = -0.85 + 0.85 * k ** 0.9  # the tongue climbs (and stays inside its cell)
    length = 0.45 + 0.45 * math.sin(math.pi * min(1, k * 1.3))
    u = (y - base) / max(length, 1e-3)  # 0 at its root .. 1 at its tip
    w = 0.22 * (1 - k * 0.6) * np.clip(np.sin(np.pi * np.clip(u, 0, 1) ** 0.7), 0, 1) ** (1.6 if style == "jagged" else 1.1)
    wob = (fbm(x * 0 + y * 2.0, y * 3 - k * 4, 1.0, 3.0, seed, octaves=3) - 0.5) * 0.25
    cxl = wob * (0.3 + u)
    if style == "jagged":
        spikes = fbm(x * 5, y * 6 - k * 6, 5.0, 6.0, seed + 9, octaves=2, ridged=True)
        w = w * (0.7 + 0.6 * spikes)
    d = np.abs(x - cxl) / np.maximum(w, 1e-4)
    a = np.clip((1 - d) / 0.12, 0, 1) * (u > 0) * (u < 1)
    a *= 1 - np.clip((k - 0.65) / 0.35, 0, 1)  # it fades as it pinches off
    val = 0.55 + 0.45 * (1 - d)
    e = blur(a * val, n * 0.005) * 1.7
    return np.dstack([e, e, e, a])


def spark(n, k, p, i):
    """a fresh lightning bolt each frame: a jagged walk from one side to the other, with branches"""
    rng = np.random.default_rng(int(p.get("seed", 5)) * 97 + i)
    img = np.zeros((n, n))
    pts = [np.array([rng.uniform(-0.8, -0.4), rng.uniform(-0.6, 0.6)])]
    end = np.array([rng.uniform(0.4, 0.8), rng.uniform(-0.6, 0.6)])
    segs = 14
    for s in range(1, segs + 1):
        t = s / segs
        q = pts[0] * (1 - t) + end * t + rng.normal(0, 0.09, 2) * math.sin(math.pi * t)
        pts.append(q)
    lines = list(zip(pts, pts[1:]))
    for b in range(int(p.get("branches", 3))):  # branches off random joints
        j = rng.integers(2, segs - 2)
        q0 = pts[j]
        ang = rng.uniform(-1.2, 1.2) + (0 if rng.random() > 0.5 else math.pi)
        q = q0
        for _ in range(4):
            q1 = q + np.array([math.cos(ang), math.sin(ang)]) * 0.07 + rng.normal(0, 0.03, 2)
            lines.append((q, q1))
            q = q1
    x, y = grid(n)
    for a0, a1 in lines:
        d = a1 - a0
        L2 = max(float(d @ d), 1e-9)
        t = np.clip(((x - a0[0]) * d[0] + (y - a0[1]) * d[1]) / L2, 0, 1)
        dist = np.hypot(x - (a0[0] + t * d[0]), y - (a0[1] + t * d[1]))
        img = np.maximum(img, np.clip(1 - dist / (3.4 / n), 0, 1))
    flick = 1.0 if (i % 3 != 2) else 0.35
    glow = blur(img, n * 0.014) * 3.0
    e = (img * 3.0 + glow) * flick
    a = np.clip(img + glow * 0.8, 0, 1) * flick
    return np.dstack([e, e, e, a])


def sparkle(n, k, p):
    x, y = grid(n)
    s = math.sin(math.pi * k) ** 0.7
    rot = k * 0.6
    xr, yr = x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)
    star = np.maximum(np.clip(1 - np.abs(xr) / 0.03 - np.abs(yr) / (0.9 * s + 1e-3), 0, 1),
                      np.clip(1 - np.abs(yr) / 0.03 - np.abs(xr) / (0.9 * s + 1e-3), 0, 1))
    core = np.exp(-(x * x + y * y) / (0.02 + 0.03 * s))
    e = (star * 2.0 + core * 1.5) * s
    return np.dstack([e, e, e, np.clip(star + core, 0, 1) * s])


def flash(n, k, p):
    x, y = grid(n)
    r = np.hypot(x, y)
    core = np.exp(-(r / (0.12 + 0.5 * k ** 0.5)) ** 2) * (1 - k) * 3
    ring_r = 0.15 + 0.8 * k ** 0.6
    ring = np.exp(-((r - ring_r) / (0.03 + 0.05 * k)) ** 2) * (1 - k) * 1.8
    ang = np.arctan2(y, x)
    rays = (0.5 + 0.5 * np.cos(ang * 18 + 1.3)) ** 8 * np.clip(1 - r / (0.3 + 0.7 * k), 0, 1) * (1 - k) * 1.6
    e = core + ring + rays
    return np.dstack([e, e, e, np.clip(e, 0, 1)])


def pnoise(s, t, cx, cy, seed):
    """periodic value noise on [0,1)^2: cx x cy cells, repeats exactly at s = 1 and t = 1 (a tiling texture)"""
    g = np.random.default_rng(seed).random((cy, cx))
    u, v = s * cx, t * cy
    i0, j0 = np.floor(u).astype(int) % cx, np.floor(v).astype(int) % cy
    i1, j1 = (i0 + 1) % cx, (j0 + 1) % cy
    su, sv = _smooth(u - np.floor(u)), _smooth(v - np.floor(v))
    a = g[j0, i0] * (1 - su) + g[j0, i1] * su
    b = g[j1, i0] * (1 - su) + g[j1, i1] * su
    return a * (1 - sv) + b * sv


def streaks(n, p):
    """one tiling frame: rows of flame tongues (image top = flame tips)"""
    s, t = np.meshgrid((np.arange(n) + 0.5) / n, (np.arange(n) + 0.5) / n)
    up = 1 - t  # 0 at the image bottom .. 1 at the top
    cols, bands, seed = int(p.get("columns", 6)), int(p.get("bands", 2)), int(p.get("seed", 1))
    # each band of tongues starts at a staggered height per column (periodic in s) and rises to points
    stagger = pnoise(s, np.zeros_like(s), cols, 1, seed)
    f = np.mod(up * bands + stagger * 0.9, 1.0)  # 0 at a band's base .. 1 at its top
    # the tongue profile across: |sin| lobes, wobbled by noise so no two are alike
    wob = (pnoise(s, t, cols * 2, bands * 3, seed + 3) - 0.5) * 0.6
    across = np.abs(np.sin(math.pi * (s * cols + wob)))
    width = (1 - f) ** float(p.get("sharp", 1.0))  # wide at the base, a point at the top
    shape = across - (1 - width)
    detail = pnoise(s, t, cols * 4, bands * 6, seed + 7) * 0.25
    a = np.clip((shape + detail - 0.15) / 0.12, 0, 1)
    a *= _smooth(np.clip(f / 0.3, 0, 1))  # a band's base melts into the tips of the band below (no hard edge)
    a *= 0.55 + 0.45 * pnoise(s, t, cols, bands * 2, seed + 11)  # some tongues fainter than others
    hot = np.clip(shape * 1.6 + 0.2, 0, 1.4) * (1 - f) ** 0.5  # hot near each tongue's root and spine
    val = 0.35 + 0.9 * hot
    return np.stack([val, val, val, a], axis=2)


def rays(n, p):
    """one tiling frame of fine vertical light streaks over a light floor"""
    s, t = np.meshgrid((np.arange(n) + 0.5) / n, (np.arange(n) + 0.5) / n)
    cols, rows, seed = int(p.get("streaks", 24)), int(p.get("length", 3)), int(p.get("seed", 1))
    fine = pnoise(s, t, cols, rows, seed)  # tall thin cells: streaks
    finer = pnoise(s, t, cols * 2, rows * 2, seed + 5)
    streak = np.clip((fine * 0.7 + finer * 0.3 - 0.35) / 0.4, 0, 1) ** 1.5
    floor = float(p.get("floor", 0.45))
    a = floor + (1 - floor) * streak
    val = 0.6 + 0.6 * streak
    return np.stack([val, val, val, a], axis=2)


def cells(n, p):
    """one tiling frame of worley cells: bright cell middles, dark seams, periodic in both axes"""
    k, seed = int(p.get("cells", 7)), int(p.get("seed", 1))
    rng = np.random.default_rng(seed)
    pts = rng.random((k * k, 2))
    s, t = np.meshgrid((np.arange(n) + 0.5) / n, (np.arange(n) + 0.5) / n)
    d1 = np.full((n, n), 9.0)
    d2 = np.full((n, n), 9.0)
    for px, py in pts:
        for ox in (-1, 0, 1):  # the 3x3 tiled copies make it wrap
            for oy in (-1, 0, 1):
                d = np.sqrt((s - px - ox) ** 2 + (t - py - oy) ** 2) * k
                nd1 = np.minimum(d1, d)
                d2 = np.where(d < d1, d1, np.minimum(d2, d))
                d1 = nd1
    edge = np.clip((d2 - d1) / 0.35, 0, 1)  # 0 on a seam .. 1 inside a cell
    centre = np.clip(1 - d1 / 0.8, 0, 1)
    val = 0.35 + 0.45 * edge + 0.5 * centre ** 2
    a = 0.45 + 0.55 * edge
    return np.stack([val, val, val, a], axis=2)


def bolt(n, p):
    """one tiling frame of lightning along x (n wide, n/4 tall)"""
    h = max(8, n // 4)
    rng = np.random.default_rng(int(p.get("seed", 1)))
    kinks = int(p.get("kinks", 14))
    xs = np.linspace(0, 1, kinks + 1)
    ys = rng.uniform(-0.55, 0.55, kinks + 1)
    ys[-1] = ys[0]  # periodic: the bolt leaves the right edge where it entered the left
    x = (np.arange(n) + 0.5) / n
    y = (np.arange(h) + 0.5) / h * 2 - 1  # -1 .. 1 across the strip
    path = np.interp(x, xs, ys)
    fork = np.interp(x, xs, np.roll(ys, 3) * 0.8)
    fork_on = (np.sin(x * math.pi * 2 * 3 + rng.uniform(0, 6)) > 0.35).astype(float)
    w = float(p.get("width", 0.035)) * 3  # the core's half-width across the strip (-1 .. 1)
    d = np.abs(y[:, None] - path[None, :])
    d2 = np.abs(y[:, None] - fork[None, :])
    core = np.exp(-((d / max(w, 1e-3)) ** 2)) + 0.55 * fork_on[None, :] * np.exp(-((d2 / max(w * 0.6, 1e-3)) ** 2))
    glow = np.exp(-d / (w * 5)) * 0.45 + 0.25 * fork_on[None, :] * np.exp(-d2 / (w * 4))
    side = 1 - _smooth(np.clip((np.abs(y) - 0.7) / 0.3, 0, 1))  # dark top and bottom
    val = (core * 1.6 + glow) * side[:, None]
    a = np.clip(val, 0, 1)
    return np.stack([val, val, val, a], axis=2)


def frames(spec):
    p = spec.get("params", {})
    n = int(spec.get("cell", 256))
    count = int(spec.get("frames", 16))
    kind = p.get("kind", "body")
    out = []
    for i in range(count):
        k = i / count if kind == "body" else i / max(1, count - 1)  # a loop stops one step short of the start
        if kind == "body":
            f = body(n, k, p)
        elif kind == "lick":
            f = lick(n, k, p)
        elif kind == "spark":
            f = spark(n, k, p, i)
        elif kind == "sparkle":
            f = sparkle(n, k, p)
        elif kind == "flash":
            f = flash(n, k, p)
        elif kind == "streaks":
            f = streaks(n, p)
        elif kind == "bolt":
            f = bolt(n, p)
        elif kind == "rays":
            f = rays(n, p)
        elif kind == "cells":
            f = cells(n, p)
        else:
            raise ValueError(f"aura kind: body | lick | spark | sparkle | flash | streaks | bolt | rays | cells (got {kind})")
        a = f[..., 3:4]
        out.append(np.concatenate([f[..., :3] * np.clip(a, 0, 1), a], axis=2).astype(np.float32))  # premultiplied
    return out
