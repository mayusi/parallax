"""inkgrammar.py — the five SAKUGA VECTOR GRAMMARS of the ink (LIMITATIONS_FIXES_V4 §3.4 step 2, §13.3.2): drawn effect
shapes made from rules a key animator follows, sized and timed by the numbers a scene's trace measured. kit/vfx/ink.py
draws a TRACED scene again; a grammar draws a NEW drawing of the same kind when there is no drawing to trace (or the
traced one is too short to loop).

    lune run kit vfx ink <key> --grammar <name> (--from <trace.json> | --metrics area,speed,cutout)
                               [--frames 64] [--grid 8] [--cell 128] [--rhythm 2] [--seed 1]
    python kit/vfx/ink.py <key> --grammar <name> ...                      (the same, without the runner)
    ink.render_grammar(grammar, contour_metrics, frames=64, grid=8, cell_px=128, rhythm=2) -> (sheet, glow)

The grammars (each a set of drawn rules, never a simulation or a picture):
  flame_tongue    an S-wave centre line (more than one bend: an inflection), the width thinning to a drawn POINT at the
                  tip, two side tongues, tear-drop cut-outs rising inside the body, EMBERS shed from the tip (separate
                  pieces that rise and shrink). Loops: the wave's phase turns a whole number of times over the sheet
  slash_crescent  a crescent between two arcs whose thickness peaks near the LEAD (asymmetric: the razor lead is
                  thick right behind its point, the tail thins slowly), a JAGGED wake (a saw-tooth inner edge in the
                  tail + broken shards left behind), speed-line slits inside. One shot: sweep, then thin out
  sakuga_smoke    one puff of round lobes that grows, rises and breaks up, shaded by HARD shadow shapes bounded by
                  cubic Bezier curves (the Nakamura cut: a flat lit tone, a flat shadow tone, no gradient), holes that
                  open as it dissipates
  kanada_bolt     a Z-forked bolt: straight segments meeting at sharp MITERED corners (never rounded), forks off its
                  corners, and a 1-frame STROBE: every second drawing is the same bolt drawn thin and dim (the flash's
                  off frame), the shape changing each pair
  liquid_splash   a crown sheet with jets whose tips run as streak lines under gravity and pinch into DROPS by the
                  Rayleigh-Plateau rule: the fastest-growing wave of a liquid thread of radius r is 9.01 r long, so the
                  drops are spaced 9.01 r and (volume kept) 1.89 r in radius; holes rupture the crown sheet

What the trace's numbers drive (each grammar's drawn result is MEASURED back and held to them):
  area_frac       how solid the drawing is in its own box (its area over its box's area; from a trace: cover over the
                  box): the grammar's body width is found by bisection until the drawn sheet measures it
  centroid_vel    how fast the drawing's middle travels, in frame widths a second (a trace's `speed`): the flame's wave
                  speed (whole turns per sheet), the slash's front-loading, the smoke's rise, the bolt's root drift,
                  the splash's launch speed (travel is capped to the cell; the summary says when)
  cutout_ratio    the share of the silhouette cut out (a trace's `cutout`): the cut-out size, by bisection. A bolt is a
                  line and has none (said, not faked)

The sheet: frames cells of cell_px (one DRAWING a cell: the flipbook's rate holds it - play at 24 / rhythm fps), every
cell's drawing inside the ink's window (MARGIN of the cell clear on every side; >= GUTTER px of nothing at the cell's
edge), straight RGBA whose see-through pixels carry the NEAREST drawing's colour (mip padding: a smaller mip level
averages colour, never black, into an edge, and never a neighbour's drawing), + <key>_glow.png (luminance x alpha past
a floor: kit/vfx/fxfinish.py's glow mask) + <key>.grammar.json (the numbers, the checks).
"""

import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

GRAMMARS = ("flame_tongue", "slash_crescent", "sakuga_smoke", "kanada_bolt", "liquid_splash")
SS = 4               # drawn this many times larger than the cell, then brought down (anti-aliased, hard edges)
MARGIN = 0.06        # of the cell, clear on every side (ink.MARGIN: mipmaps must not bleed one cell into the next)
GUTTER = 2           # px at a cell's edge that must hold NOTHING (alpha exactly 0)
RP_WAVE = 2.0 * math.pi / 0.697      # Rayleigh-Plateau: the fastest-growing wave is k r = 0.697 -> 9.01 r long
RP_DROP = (0.75 * RP_WAVE) ** (1.0 / 3.0)   # a thread 9.01 r long, pinched into one sphere: 1.89 r in radius
GREYS = [[96, 96, 96], [176, 176, 176], [255, 255, 255]]
TOL_AREA = 0.05      # the measured solidity within this of area_frac (unless the grammar cannot reach it: said)
TOL_CUT = 0.015      # ... and the measured cut-out share within this (or a quarter of cutout_ratio, the larger)
TRAVEL_CAP = 0.30    # a one-shot's travel over the whole sheet, in window units (the cell holds the effect)
COUNTS = {16: (4, 4), 32: (8, 4), 64: (8, 8)}


# ------------------------------------------------------------------ shapes (unit window: x right, y down, 0..1)
def circle(cx, cy, r, n=28):
    a = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    return np.stack([cx + r * np.cos(a), cy + r * np.sin(a)], axis=1)


def ellipse(cx, cy, rx, ry, n=32):
    a = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    return np.stack([cx + rx * np.cos(a), cy + ry * np.sin(a)], axis=1)


def bezier_blob(cx, cy, r, rng, lobes=5, wob=0.22, n=10):
    """a closed curve of CUBIC Bezier segments through `lobes` points on a jittered circle (Catmull-Rom tangents):
    the hard shadow shape of a cel-shaded puff"""
    a0 = rng.uniform(0, 2 * math.pi)
    ang = a0 + np.linspace(0.0, 2.0 * math.pi, lobes, endpoint=False) + rng.uniform(-0.25, 0.25, lobes)
    rad = r * (1.0 + rng.uniform(-wob, wob, lobes))
    p = np.stack([cx + rad * np.cos(ang), cy + rad * np.sin(ang)], axis=1)
    p0, p1, p2, p3 = np.roll(p, 1, axis=0), p, np.roll(p, -1, axis=0), np.roll(p, -2, axis=0)
    c1, c2 = p1 + (p2 - p0) / 6.0, p2 - (p3 - p1) / 6.0
    s = np.linspace(0.0, 1.0, n, endpoint=False)[None, :, None]
    q = ((1 - s) ** 3 * p1[:, None] + 3 * (1 - s) ** 2 * s * c1[:, None] + 3 * (1 - s) * s * s * c2[:, None]
         + s ** 3 * p2[:, None])
    return q.reshape(-1, 2)


def ribbon(centre, widths):
    """a centre line + a half-width per point -> items: one quad per segment (+ a disc at each joint wider than a
    hair), unioned when drawn. One closed outline would cross itself where the line bends tighter than its width, and
    a crossed outline fills as a ring"""
    c = np.asarray(centre, dtype=np.float64)
    d = np.gradient(c, axis=0)
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([-d[:, 1], d[:, 0]], axis=1)
    w = np.asarray(widths, dtype=np.float64)
    L, R = c + nrm * w[:, None], c - nrm * w[:, None]
    items = [(np.array([L[i], L[i + 1], R[i + 1], R[i]]), []) for i in range(len(c) - 1)]
    items += [(circle(c[i, 0], c[i, 1], w[i], 10), []) for i in range(1, len(c) - 1) if w[i] > 0.006 and i % 2 == 0]
    return items


def mitered(points, widths, limit=4.0):
    """a polyline drawn as ONE outline whose corners are MITERED (the offset edges meet in a point; past `limit`
    half-widths the corner is cut square) - the Kanada bolt's straight-segment look; a round join would soften it"""
    p = np.asarray(points, dtype=np.float64)
    w = np.asarray(widths, dtype=np.float64)
    n = len(p)
    left, right = [], []
    for i in range(n):
        if i == 0 or i == n - 1:
            d = p[1] - p[0] if i == 0 else p[-1] - p[-2]
            d /= max(np.linalg.norm(d), 1e-9)
            nm = np.array([-d[1], d[0]])
            left.append(p[i] + nm * w[i])
            right.append(p[i] - nm * w[i])
            continue
        d0 = p[i] - p[i - 1]
        d1 = p[i + 1] - p[i]
        d0 /= max(np.linalg.norm(d0), 1e-9)
        d1 /= max(np.linalg.norm(d1), 1e-9)
        n0, n1 = np.array([-d0[1], d0[0]]), np.array([-d1[1], d1[0]])
        m = n0 + n1
        ml = np.linalg.norm(m)
        if ml < 1e-6:
            m, scale = n0, 1.0
        else:
            m /= ml
            scale = 1.0 / max(float(m @ n0), 1e-6)
        if scale <= limit:
            left.append(p[i] + m * w[i] * scale)
            right.append(p[i] - m * w[i] * scale)
        else:                                                  # past the limit: a square cut (two points)
            left += [p[i] + n0 * w[i], p[i] + n1 * w[i]]
            right += [p[i] - n0 * w[i], p[i] - n1 * w[i]]
    return np.concatenate([np.asarray(left), np.asarray(right)[::-1]])


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ the grammars: (k, n, P, seed) -> drawing
# a drawing: {"layers": [{"tone": t, "items": [(outer, [holes])]}], "cuts": [poly], "meta": {...}}; layer 0 is the
# silhouette, lighter layers lie inside it; a cut erases every layer (a cut-out of the silhouette)

def _flame_line(s, ph, amp, base_y, tip_y, lean=0.0, x0=0.5):
    cx = x0 + amp * s ** 1.1 * np.sin(2 * math.pi * 1.15 * s - ph) + lean * s * s
    cy = base_y + (tip_y - base_y) * s
    return np.stack([cx, cy], axis=1)


def flame_tongue(k, n, P, seed):
    t = k / float(n)
    cyc = P["cycles"]
    ph = 2 * math.pi * cyc * t
    s = np.linspace(0.0, 1.0, 56)
    base_y, tip_y = 0.95, 0.34 + 0.05 * math.sin(2 * ph + 1.0)
    amp = 0.085 * (0.75 + 0.25 * math.sin(ph + 0.7))
    W = 0.20 * P["thick"]

    def width(s, w):
        return w * (1 - s) ** 0.85 * (0.45 + 0.55 * np.sqrt(np.minimum(1.0, s / 0.2)))

    main = _flame_line(s, ph, amp, base_y, tip_y)
    items0 = [*ribbon(main, width(s, W)), (circle(main[0, 0], base_y - 0.42 * W, 0.45 * W, 24), [])]
    for side, lag in ((-1, 1.3), (1, 2.4)):                     # two side tongues from the lower body, leaning out
        hs = np.linspace(0.0, 1.0, 32)
        tip2 = base_y - (base_y - tip_y) * (0.48 + 0.06 * math.sin(ph * 2 + lag))
        line = _flame_line(hs, ph + lag, amp * 0.6, base_y - 0.04, tip2, lean=side * 0.13, x0=0.5 + side * 0.05)
        items0 += ribbon(line, width(hs, W * 0.55))
    embers = []
    for j in range(5):                                           # shed from the tip, rising and shrinking
        age = (t * cyc + j / 5.0) % 1.0
        ex = main[-6, 0] + 0.05 * math.sin(2 * math.pi * (age + j * 0.37)) + (j - 2) * 0.012
        ey = tip_y - 0.03 - age * (tip_y - 0.07)
        r = (0.022 * (1 - age) + 0.008) * min(1.0, P["thick"])
        if ey - r > 0.01:
            embers.append((np.array([[ex, ey - 1.6 * r], [ex + r, ey], [ex, ey + 1.6 * r], [ex - r, ey]]), []))
    items0 += embers
    cuts = []
    if P["hole"] > 0:
        for j in range(3):                                       # tear drops rising inside the body
            u = 0.22 + 0.5 * ((j * 0.37 + t * cyc) % 1.0)
            i = int(u * (len(s) - 1))
            r = P["hole"] * float(width(np.array([u]), W)[0]) * 0.75
            if r > 0.004:
                cx, cy = main[i]
                cuts.append(np.array([[cx, cy - 2.2 * r]] + [[cx + r * math.cos(a), cy + r * math.sin(a)]
                                                             for a in np.linspace(-0.3, math.pi + 0.3, 12)]))
    s1 = np.linspace(0.0, 0.82, 48)
    mid = _flame_line(s1, ph, amp, base_y - 0.02, tip_y, x0=0.5)
    core = _flame_line(np.linspace(0.0, 0.55, 36), ph, amp, base_y - 0.04, tip_y)
    return {"layers": [{"tone": 0, "items": items0},
                       {"tone": 1, "items": [*ribbon(mid, width(s1 / 0.82, W * 0.62))]},
                       {"tone": 2, "items": [*ribbon(core, width(np.linspace(0, 1, 36), W * 0.32))]}],
            "cuts": cuts, "meta": {"centre": main, "embers": len(embers)}}


def slash_crescent(k, n, P, seed):
    t = k / float(max(n - 1, 1))
    pw = P["ease"]

    def ease(x):
        x = min(max(x, 0.0), 1.0)
        return 1 - (1 - x) ** pw

    a_from, a_to = math.radians(165), math.radians(375)          # screen angles (y down): a sweep OVER the top
    lead_u = 0.14 + 0.86 * ease(t / 0.55)                                      # the lead sweeps in the first 55 % of the life
    tail_u = 0.8 * min(1.0, max(0.0, t - 0.18) / 0.82) ** 1.3        # the tail follows late and never quite arrives
    lead = a_from + (a_to - a_from) * lead_u
    tail = a_from + (a_to - a_from) * min(tail_u, lead_u - 0.04)
    span = lead - tail
    cx, cy, R = 0.5, 0.55, 0.4
    env = 0.35 + 0.65 * math.sin(math.pi * min(1.0, 0.12 + t * 0.95)) ** 0.5
    th = 0.16 * P["thick"] * env
    u = np.linspace(0.0, 1.0, 120)
    f = u ** 2.2 * (1 - u) ** 0.75                                  # the weight right behind a drawn point (razor lead)
    f /= f.max()
    wake = 0.34 * np.clip(u / 0.1, 0.0, 1.0) * np.clip((0.55 - u) / 0.25, 0.0, 1.0)
    saw = np.abs(((u * 15.0) % 1.0) * 2 - 1)                       # the jagged wake: a saw-toothed tail band
    teeth = np.where(u < 0.55, 1 - 0.7 * saw, 1.0)
    thick = th * np.maximum(f, wake * teeth)
    ang = tail + span * u
    out_r, in_r = R + 0.3 * thick, R - 0.7 * thick

    def arc(rr, aa):
        return np.stack([cx + rr * np.cos(aa), cy + rr * np.sin(aa)], axis=1)

    outer, inner = arc(out_r, ang), arc(in_r, ang)
    items0 = [(np.concatenate([outer, inner[::-1]]), [])]
    shards = 0
    for j in range(4):                                             # the wake: thin broken slivers left behind the tail
        a = tail - 0.1 - (j + 1) * 0.13 * (1 + 0.3 * j)
        if a < a_from - 0.05:
            continue
        size = th * 0.5 * (1 - 0.18 * j)
        if size < 0.006:
            continue
        rr = R + 0.12 * th * (-1) ** j
        p = np.array([cx + rr * math.cos(a), cy + rr * math.sin(a)])
        tang = np.array([-math.sin(a), math.cos(a)])
        nrm = np.array([math.cos(a), math.sin(a)])
        items0.append((np.array([p + tang * size * 1.8, p + nrm * size * 0.3, p - tang * size * 1.2, p - nrm * size * 0.25]), []))
        shards += 1
    cuts = []
    if P["hole"] > 0 and th > 0.01:
        for j, uc in enumerate((0.5, 0.66, 0.8)):                 # speed-line slits along the band
            i = int(uc * (len(u) - 1))
            if thick[i] < 0.012:
                continue
            half = abs(span) * 0.18 * P["hole"]
            w = 0.17 * thick[i] * P["hole"]
            aa = np.linspace(ang[i] - half, ang[i] + half, 16)
            lens = w * np.sin(np.linspace(0, math.pi, 16))
            rr = R - 0.2 * thick[i] + (j - 1) * 0.06 * thick[i]
            cuts.append(np.concatenate([arc(rr + lens, aa), arc(rr - lens, aa)[::-1]]))
    mid_in = arc(out_r - thick * 0.5, ang)
    core_in = arc(out_r - thick * np.where(u > 0.45, 0.2, 0.0), ang)
    return {"layers": [{"tone": 0, "items": items0},
                       {"tone": 1, "items": [(np.concatenate([outer, mid_in[::-1]]), [])]},
                       {"tone": 2, "items": [(np.concatenate([outer, core_in[::-1]]), [])]}],
            "cuts": cuts, "meta": {"centre_xy": (cx, cy), "lead": lead, "tail": tail, "span": span, "shards": shards,
                                   "thick": thick}}


def sakuga_smoke(k, n, P, seed):
    t = k / float(max(n - 1, 1))
    rng = np.random.default_rng(seed)
    lobes = 6
    R = 0.11 + 0.13 * (1 - (1 - t) ** 2)
    rise = P["travel"] * t
    cx, cy = 0.5, 0.66 - rise
    base_ang = rng.uniform(0, 2 * math.pi, lobes)
    base_off = rng.uniform(0.35, 0.75, lobes)
    base_r = rng.uniform(0.5, 0.85, lobes)
    spread = 1.0 + 0.35 * max(0.0, t - 0.55) / 0.45                 # breaking up: the lobes drift apart
    shrink = 1.0 - 0.45 * max(0.0, t - 0.6) / 0.4
    items0, items1, items2, cuts = [], [], [], []
    for j in range(lobes):
        pack = 1.3 - 0.4 * (P["thick"] - 0.4)                    # thick: how tightly the lobes pack (solid vs lumpy)
        lx = cx + math.cos(base_ang[j]) * base_off[j] * R * spread * pack
        ly = cy + math.sin(base_ang[j]) * base_off[j] * R * 0.8 * spread * pack
        lr = base_r[j] * R * shrink
        lrng = np.random.default_rng(seed * 101 + j)
        items0.append((circle(lx, ly, lr, 40), []))
        # the lit side: the lobe less a cubic-Bezier shadow bite from its lower right (hard edged)
        bite = bezier_blob(lx + 0.5 * lr, ly + 0.55 * lr, 0.78 * lr, lrng, lobes=5, wob=0.18)
        items1.append((circle(lx, ly, lr * 0.97, 40), [bite]))
        if lr > 0.05:
            items2.append((bezier_blob(lx - 0.38 * lr, ly - 0.4 * lr, 0.26 * lr, lrng, lobes=4, wob=0.2), []))
        if P["hole"] > 0 and t > 0.3:                           # dissipation holes opening inside the lobes
            hr = P["hole"] * lr * 0.55 * smoothstep((t - 0.3) / 0.5)
            if hr > 0.004:
                cuts.append(bezier_blob(lx + 0.1 * lr, ly - 0.05 * lr, hr, lrng, lobes=4, wob=0.15))
    return {"layers": [{"tone": 0, "items": items0}, {"tone": 1, "items": items1}, {"tone": 2, "items": items2}],
            "cuts": cuts, "meta": {"centre": (cx, cy)}}


def _zig(rng, start, end, steps, amp):
    pts = [np.asarray(start, dtype=np.float64)]
    d = np.asarray(end, dtype=np.float64) - pts[0]
    nrm = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-9)
    for i in range(1, steps):
        side = 1 if i % 2 else -1
        pts.append(pts[0] + d * (i / steps + rng.uniform(-0.03, 0.03)) + nrm * side * amp * rng.uniform(0.6, 1.0))
    pts.append(np.asarray(end, dtype=np.float64))
    return np.asarray(pts)


def kanada_bolt(k, n, P, seed):
    pair, off = k // 2, k % 2                                   # the strobe: a flash drawing, then its thin off frame
    pairs = max(1, n // 2)
    rng = np.random.default_rng(seed * 7919 + pair)
    x0 = 0.3 + P["drift"] * math.sin(2 * math.pi * pair / pairs)      # a diagonal strike uses its square cell
    x1 = 0.72 + rng.uniform(-0.1, 0.1)
    main = _zig(rng, (x0, 0.04), (x1, 0.96), int(rng.integers(6, 9)), 0.1)
    main[:, 0] = np.clip(main[:, 0], 0.06, 0.94)
    W = 0.034 * P["thick"]
    taper = np.linspace(1.0, 0.45, len(main))
    paths = [(main, taper)]
    if not off:
        for f in range(int(rng.integers(2, 4))):                # forks from the bolt's corners
            i = int(rng.integers(1, len(main) - 2))
            side = rng.choice([-1, 1])
            start = main[i]
            end = start + np.array([side * rng.uniform(0.16, 0.3), rng.uniform(0.14, 0.3)])
            end = np.clip(end, 0.05, 0.95)
            fz = _zig(rng, start, end, int(rng.integers(3, 5)), 0.05)
            paths.append((fz, np.linspace(taper[i] * 0.6, 0.2, len(fz))))
    scale = 0.45 if off else 1.0
    layers = [{"tone": 0, "items": [(mitered(p, W * scale * tw), []) for p, tw in paths]}]
    if not off:
        layers.append({"tone": 1, "items": [(mitered(p, W * 0.58 * tw), []) for p, tw in paths]})
        layers.append({"tone": 2, "items": [(mitered(main, W * 0.26 * taper), [])]})
    return {"layers": layers, "cuts": [], "meta": {"off": bool(off), "root": x0, "corners": len(main) - 2}}


def liquid_splash(k, n, P, seed):
    t = k / float(max(n - 1, 1))
    rng = np.random.default_rng(seed)
    tau = t
    r = 0.012                                                  # a jet's thread radius where it thins out
    w_root = 0.05 * P["thick"]                                 # ... and its width where it leaves the mound (thick)
    lam, rd = RP_WAVE * r, RP_DROP * r
    g = np.array([0.0, 0.95])
    s0 = P["launch"]
    floor_y = 0.92
    rise = math.sin(math.pi * min(1.0, t * 1.5)) ** 0.6         # the mound swells, then falls back into the pool
    wb = 0.11 + 0.1 * t                                           # the ring spreads over the pool
    hm = 0.07 * rise + 0.012
    xs = np.linspace(-1.0, 1.0, 48)
    mound = np.concatenate([np.stack([0.5 + wb * xs, floor_y - hm * np.sqrt(np.clip(1 - xs ** 2, 0, 1))], 1),
                            np.array([[0.5 + wb, floor_y + 0.02], [0.5 - wb, floor_y + 0.02]])])
    items0, items1, items2, cuts = [(mound, [])], [], [], []
    if hm > 0.03:
        items1.append((ellipse(0.5, floor_y - hm * 0.35, wb * 0.75, hm * 0.4), []))
    drops, threads = 0, 0
    age_break, emit_end = 0.3, 0.45
    jets = 7
    for j in range(jets):
        u = -1.0 + 2.0 * j / (jets - 1)
        ang = math.radians(90 - 26 * u + rng.uniform(-4, 4))     # fanning OUT from the mound
        d = np.array([math.cos(ang), -math.sin(ang)])
        p0 = np.array([0.5 + wb * 0.85 * u, floor_y - hm * math.sqrt(max(0.0, 1 - (0.85 * u) ** 2)) + 0.01])
        sp = s0 * rng.uniform(0.85, 1.1) * (1.0 - 0.3 * abs(u))
        if tau <= 0.0:
            continue
        # the spike: the streak of the parcels younger than the break age (root -> tip), wide at the root, a thread
        # at the tip; older parcels have pinched into drops one Rayleigh-Plateau wave (9.01 r) apart, 1.89 r round
        te = np.linspace(max(0.0, tau - age_break), min(tau, emit_end), 22)
        if te[-1] > te[0]:
            age = tau - te
            line = (p0 + sp * d * age[:, None] + 0.5 * g * age[:, None] ** 2)[::-1]
            if np.all((line > 0.02) & (line < 0.98)):
                sfrac = np.linspace(0.0, 1.0, len(line))
                root = 1.0 if te[-1] >= tau - 1e-9 else 0.0       # still joined to the mound: wide at the root
                wv = r + (w_root - r) * root * (1 - sfrac) ** 1.6
                items0 += ribbon(line, wv)
                items1 += ribbon(line, wv * 0.42)
                threads += 1
        step = lam / max(sp, 1e-6)
        for te_i in np.arange(step * 0.5, min(tau, emit_end), step):
            a = tau - te_i
            if a < age_break:
                continue
            q = p0 + sp * d * a + 0.5 * g * a * a
            if q[1] + rd > floor_y + 0.02 or not (0.02 + rd < q[0] < 0.98 - rd and 0.02 + rd < q[1]):
                continue
            items0.append((circle(q[0], q[1], rd, 20), []))
            items2.append((circle(q[0] - 0.35 * rd, q[1] - 0.35 * rd, 0.38 * rd, 12), []))
            drops += 1
    if P["hole"] > 0 and hm > 0.03:                             # the mound's sheet ruptures
        for j in range(3):
            x = 0.5 + wb * (-0.5 + 0.5 * j)
            hr = P["hole"] * hm * 0.42 * (0.8 + 0.2 * j)
            if hr > 0.003:
                cuts.append(ellipse(x, floor_y - hm * 0.45, hr * 1.4, hr))
    return {"layers": [{"tone": 0, "items": items0}, {"tone": 1, "items": items1}, {"tone": 2, "items": items2}],
            "cuts": cuts, "meta": {"drops": drops, "threads": threads, "r": r, "lam": lam, "rd": rd}}


DRAW = {"flame_tongue": flame_tongue, "slash_crescent": slash_crescent, "sakuga_smoke": sakuga_smoke,
        "kanada_bolt": kanada_bolt, "liquid_splash": liquid_splash}
HAS_HOLES = {"flame_tongue": True, "slash_crescent": True, "sakuga_smoke": True, "kanada_bolt": False,
             "liquid_splash": True}
LOOPS = {"flame_tongue": True, "kanada_bolt": True}
HOLE_MAX = {"slash_crescent": 0.7}
SAMPLE = {"liquid_splash": (0.15, 0.45)}
# the body width a grammar is drawn at, at most: past it the grammar's own look breaks (a bolt's corners fill in,
# a flame's bend is lost in its width) - numbers asking for more are drawn at the edge and SAID
THICK = {"kanada_bolt": (0.4, 1.2), "flame_tongue": (0.4, 1.4)}   # a splash's shape is its crown: after it the pool is a sliver     # past this the slits open through the band's edge (notches, not cut-outs)


# ------------------------------------------------------------------ drawing to pixels
def window(drawings):
    """ONE square window round every drawing of the sheet (ink's --register beat): each drawing sits where the
    grammar put it, so the motion inside the sheet is the grammar's, and the window is as small as holds them all
    (the drawing fills its cell) -> (x0, y0, size) in the grammar's units"""
    pts = [np.asarray(o, dtype=np.float64) for d in drawings for L in d["layers"] for o, _ in L["items"]]
    if not pts:
        return (0.0, 0.0, 1.0)
    p = np.concatenate(pts)
    lo, hi = p.min(axis=0), p.max(axis=0)
    size = float(max(hi - lo)) * 1.02 + 1e-6
    mid = (lo + hi) / 2.0
    return (float(mid[0] - size / 2), float(mid[1] - size / 2), size)


def raster(drawing, cell, ss=SS, win=(0.0, 0.0, 1.0)):
    """a drawing -> {tone: coverage (cell, cell) float 0..1}: every layer drawn ss times larger, its items unioned
    (each item its outer less its own holes), clipped to the silhouette, the cuts taken out of every layer. `win`
    (x0, y0, size) is the part of the grammar's plane the cell's inside (all but MARGIN) shows"""
    big = cell * ss
    lo, span = MARGIN * big, (1 - 2 * MARGIN) * big
    origin, size = np.array(win[:2], dtype=np.float64), float(win[2])

    def px(poly):
        p = (np.asarray(poly, dtype=np.float64) - origin) / size
        return [tuple(v) for v in (lo + p * span)]

    cut = Image.new("L", (big, big), 0)
    dc = ImageDraw.Draw(cut)
    for c in drawing["cuts"]:
        dc.polygon(px(c), fill=255)
    cutm = np.asarray(cut) > 0
    covers, sil = {}, None
    for L in drawing["layers"]:
        solid = Image.new("L", (big, big), 0)                   # items with no holes of their own: one picture
        ds = ImageDraw.Draw(solid)
        m = None
        for outer, holes in L["items"]:
            if not holes:
                ds.polygon(px(outer), fill=255)
                continue
            im = Image.new("L", (big, big), 0)
            d = ImageDraw.Draw(im)
            d.polygon(px(outer), fill=255)
            for h in holes:
                d.polygon(px(h), fill=0)
            m = (np.asarray(im) > 0) if m is None else (m | (np.asarray(im) > 0))
        m = (np.asarray(solid) > 0) if m is None else (m | (np.asarray(solid) > 0))
        m &= ~cutm
        if sil is None:
            sil = m
        else:
            m &= sil
        cov = cv2.resize(m.astype(np.float32), (cell, cell), interpolation=cv2.INTER_AREA) if ss > 1 else m.astype(np.float32)
        covers[L["tone"]] = np.maximum(covers.get(L["tone"], 0.0), cov)
    return covers


def paint(covers, tones):
    """{tone: coverage} -> straight RGBA float (ink.paint's rule: darkest tone everywhere, lighter ones laid over)"""
    order = sorted(covers)
    alpha = covers[order[0]].astype(np.float32)
    rgb = np.zeros(alpha.shape + (3,), np.float32) + (np.asarray(tones[min(order[0], len(tones) - 1)], np.float32) / 255.0)
    for t in order[1:]:
        c = covers[t][..., None]
        rgb = rgb * (1 - c) + (np.asarray(tones[min(t, len(tones) - 1)], np.float32) / 255.0) * c
        alpha = np.maximum(alpha, covers[t])
    return np.dstack([rgb, alpha])


def mip_pad(cellpx):
    """the see-through pixels take the colour of the NEAREST drawn pixel of the same cell (alpha untouched): a smaller
    mip level then averages the drawing's own colour into its edge, never black (a dark fringe)"""
    a = cellpx[..., 3]
    drawn = a > 0
    if not drawn.any() or drawn.all():
        return cellpx
    src = (~drawn).astype(np.uint8)                             # zeros = the drawn pixels (the labels' seeds)
    _, labels = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    seeds = np.argwhere(src == 0)
    near = seeds[labels - 1]
    out = cellpx.copy()
    out[..., :3] = cellpx[near[..., 0], near[..., 1], :3]
    out[drawn, :3] = cellpx[drawn, :3]
    return out


# ------------------------------------------------------------------ measuring a drawn cell
def solidity(alpha):
    """how solid the drawing's MAIN piece is in its own box (its area over its box's area): an ember or a drop off to
    the side would stretch the box of the whole drawing and say nothing about the shape"""
    m = (alpha > 0.5).astype(np.uint8)
    cnt, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if cnt <= 1:
        return 0.0
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = stats[i]
    return float(area) / float(w * h)


def closed_of(mask):
    m = np.pad(mask.astype(np.uint8), 1)
    flood = m.copy()
    cv2.floodFill(flood, np.zeros((m.shape[0] + 2, m.shape[1] + 2), np.uint8), (0, 0), 2)
    return (flood != 2)[1:-1, 1:-1]


def cutout_of(alpha):
    m = alpha > 0.5
    c = closed_of(m)
    return float((c & ~m).sum()) / float(max(int(c.sum()), 1))


def pieces(alpha):
    return cv2.connectedComponents((alpha > 0.5).astype(np.uint8), connectivity=8)[0] - 1


# ------------------------------------------------------------------ the numbers -> the grammar's parameters
def metrics_from_trace(trace):
    """a trace (shapetrace's json, normalised) -> {"area_frac", "centroid_vel", "cutout_ratio", "drawings"}: the
    medians over its drawings. area_frac = the main piece's area (less its holes) over its box (how solid the shape is
    in its own box: a number that carries from a camera frame to a cell); centroid_vel = the trace's speed (frame widths a second; the first drawing
    has none); cutout_ratio = its cutout"""
    ds = trace.get("drawings") or []
    solid, vel, cut = [], [], []
    w, h = (trace.get("size") or [1, 1])[:2]

    def shoelace(ring):
        p = np.asarray(ring, dtype=np.float64).reshape(-1, 3)[:, :2] * np.array([w, h], dtype=np.float64)
        return 0.5 * abs(float(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))), p

    for d in ds:
        shapes = (d.get("layers") or [{}])[0].get("shapes") or []
        best = None
        for sh in shapes:
            area, p = shoelace(sh["outer"])
            if best is None or area > best[0]:
                holes = sum(shoelace(x)[0] for x in sh.get("holes") or [])
                box = float(np.ptp(p[:, 0]) * np.ptp(p[:, 1]))
                best = (area, (area - holes) / max(box, 1e-9))
        if best is not None and best[0] > 0:
            solid.append(min(1.0, best[1]))
        if d.get("speed") is not None:
            vel.append(float(d["speed"]))
        if d.get("cutout") is not None:
            cut.append(float(d["cutout"]))
    if not solid:
        raise ValueError("the trace has no drawings to measure")
    return {"area_frac": round(float(np.median(solid)), 4), "centroid_vel": round(float(np.median(vel)) if vel else 0.0, 4),
            "cutout_ratio": round(float(np.median(cut)) if cut else 0.0, 4), "drawings": len(ds)}


def checked_metrics(m):
    out = {}
    for name, lo, hi in (("area_frac", 0.01, 1.0), ("centroid_vel", 0.0, 20.0), ("cutout_ratio", 0.0, 0.9)):
        v = m.get(name) if isinstance(m, dict) else None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"contour_metrics.{name} is a number from {lo} to {hi} (got {v!r})")
        out[name] = float(v)
    return out


def drive(grammar, metrics, frames, rhythm):
    """the speed-driven parameters (before the bisections fit thick and hole)"""
    v, dt = metrics["centroid_vel"], rhythm / 24.0
    travel = v * dt * (frames - 1)
    P = {"thick": 1.0, "hole": 0.0, "cycles": 1, "ease": 2.0, "travel": 0.0, "drift": 0.0, "launch": 0.5}
    said = []
    if grammar == "flame_tongue":
        P["cycles"] = max(1, int(round(v * dt * frames / 0.5)))           # the wave's turns over the loop
    elif grammar == "slash_crescent":
        P["ease"] = min(4.0, max(1.5, 1.0 + 2.0 * v))                    # faster = more of the sweep up front
    elif grammar == "sakuga_smoke":
        # a soft cap: the cell holds the puff, so the rise eases toward TRAVEL_CAP (faster still rises further)
        P["travel"] = TRAVEL_CAP * (1.0 - math.exp(-travel / TRAVEL_CAP))
        if travel > TRAVEL_CAP:
            said.append(f"the smoke's rise eases toward {TRAVEL_CAP} of the cell (the speed asks {travel:.2f}; drawn {P['travel']:.2f})")
    elif grammar == "kanada_bolt":
        P["drift"] = min(0.18, max(0.02, v * dt * frames / (2 * math.pi)))
    elif grammar == "liquid_splash":
        P["launch"] = min(1.05, max(0.5, 0.55 + 0.5 * v))
        if 0.55 + 0.5 * v > 1.05:
            said.append("the splash's launch speed is capped at 1.05 (its drops would leave the cell)")
    return P, said


def _sample_k(grammar, frames):
    # the drawings the fit measures: across the whole sheet, for a one-shot its readable middle (not the first
    # spark or the last wisp)
    if LOOPS.get(grammar):
        ks = np.linspace(0, frames - 1, 8).astype(int)
        return [int(k) - int(k) % 2 for k in ks] if grammar == "kanada_bolt" else [int(k) for k in ks]
    lo, hi = SAMPLE.get(grammar, (0.25, 0.75))
    return [int(k) for k in np.linspace(frames * lo, frames * hi, 8)]


def measure(grammar, P, frames, cell, seed, ks):
    """the sampled drawings drawn as the sheet will draw them (its window, its supersampling: a thin slit measures
    differently at another size) -> (mean solidity, mean cut-out share)"""
    win = window([DRAW[grammar](k, frames, P, seed) for k in sorted(set(list(range(0, frames, 4)) + [frames - 1] + list(ks)))])
    sol, cut = [], []
    for k in ks:
        a = raster(DRAW[grammar](k, frames, P, seed), cell, win=win)[0]
        if (a > 0.5).any():
            sol.append(solidity(a))
            cut.append(cutout_of(a))
    return (float(np.mean(sol)) if sol else 0.0, float(np.mean(cut)) if cut else 0.0)


def _bisect(fn, target, lo, hi, rounds=8, grid=7):
    """the argument whose value is nearest the target -> (argument, (lowest, highest) value seen, past reach?). fn is
    scanned on a coarse grid first (a grammar's response need not be monotone: a fat flame's main piece can get LESS
    solid), then bisected inside the first bracket that holds the target"""
    xs = np.linspace(lo, hi, grid)
    fs = [fn(x) for x in xs]
    reach = (min(fs), max(fs))
    for i in range(grid - 1):
        if min(fs[i], fs[i + 1]) <= target <= max(fs[i], fs[i + 1]):
            a, b, rising = xs[i], xs[i + 1], fs[i + 1] >= fs[i]
            for _ in range(rounds):
                mid = 0.5 * (a + b)
                if (fn(mid) < target) == rising:
                    a = mid
                else:
                    b = mid
            return 0.5 * (a + b), reach, False
    j = int(np.argmin([abs(f - target) for f in fs]))
    return float(xs[j]), reach, True


def fit(grammar, metrics, frames, cell, seed, rhythm):
    """the grammar's parameters for these numbers: speed by rule, thick and hole by bisection on the DRAWN cells"""
    P, said = drive(grammar, metrics, frames, rhythm)
    ks = _sample_k(grammar, frames)
    clamped = {}
    for _ in range(3):
        P["thick"], reach, cl = _bisect(lambda x: measure(grammar, {**P, "thick": x}, frames, cell, seed, ks)[0],
                                        metrics["area_frac"], *THICK.get(grammar, (0.4, 1.8)))
        clamped["area_frac"] = [round(reach[0], 3), round(reach[1], 3)] if cl else None
        if HAS_HOLES[grammar] and metrics["cutout_ratio"] > 0:
            P["hole"], reach, cl = _bisect(lambda x: measure(grammar, {**P, "hole": x}, frames, cell, seed, ks)[1],
                                           metrics["cutout_ratio"], 0.0, HOLE_MAX.get(grammar, 1.0))
            clamped["cutout_ratio"] = [round(reach[0], 3), round(reach[1], 3)] if cl else None
        else:
            P["hole"] = 0.0
            break
    if not HAS_HOLES[grammar] and metrics["cutout_ratio"] > 0:
        said.append(f"a {grammar} is a line: it has no cut-outs (cutout_ratio {metrics['cutout_ratio']} is not used)")
    for name, reach in clamped.items():
        if reach:
            said.append(f"{name} {metrics[name]} is past what a {grammar} can be ({reach[0]}..{reach[1]}): drawn at the nearest")
    return P, said, clamped, ks


# ------------------------------------------------------------------ the grammar's own checks (from the pixels)
def tone_masks(cellpx, tones):
    """which cumulative tone layer each drawn pixel shows (nearest tone by its colour) -> {t: bool mask of tone >= t}"""
    a = cellpx[..., 3] > 0.5
    ts = np.asarray(tones, np.float32)[:3] / 255.0
    d = np.abs(cellpx[..., None, :3] - ts[None, None]).sum(axis=3)
    lab = np.argmin(d, axis=2)
    return {t: a & (lab >= t) for t in range(len(ts))}


def signature(grammar, cells, drawings, tones, cell, win=(0.0, 0.0, 1.0)):
    """the grammar's defining features, measured on the drawn cells -> [{name, ok, value, limit, fix}]"""
    out = []

    def add(name, ok, value, limit, fix):
        out.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": "" if ok else fix})

    n = len(cells)
    if grammar == "flame_tongue":
        bends, sheds = 0, 0
        for c in cells:
            m = tone_masks(c, tones)[1]
            rows = [(y, np.nonzero(m[y])[0]) for y in range(m.shape[0])]
            mid = np.array([xs.mean() for y, xs in rows if len(xs) >= 2])
            if len(mid) > 12:
                sm = np.convolve(mid, np.ones(5) / 5.0, mode="valid")
                dd = np.diff(sm)
                sgn = np.sign(dd[np.abs(dd) > 0.05])
                if len(sgn) and np.count_nonzero(np.diff(sgn)) >= 1 and np.ptp(sm) >= 1.5:
                    bends += 1
            if pieces(c[..., 3]) >= 2:
                sheds += 1
        add("s_wave", bends >= 0.6 * n, f"{bends}/{n}", ">= 60 % of drawings bend both ways",
            "the centre line does not bend both ways: an S-wave flame, not a straight cone")
        add("embers", sheds >= 0.5 * n, f"{sheds}/{n}", ">= half the drawings shed an ember (a separate piece)",
            "no embers come off the tip")
    elif grammar == "slash_crescent":
        heavy, seen, broken, moved = 0, 0, 0, 0
        for c, d in zip(cells, drawings):
            meta = d["meta"]
            if meta["span"] < math.radians(30):
                continue
            seen += 1
            a = c[..., 3] > 0.5
            ys, xs = np.nonzero(a)
            lo, sp = MARGIN * cell, (1 - 2 * MARGIN) * cell
            cx = lo + (meta["centre_xy"][0] - win[0]) / win[2] * sp
            cy = lo + (meta["centre_xy"][1] - win[1]) / win[2] * sp
            ang = np.arctan2(ys + 0.5 - cy, xs + 0.5 - cx)
            midang = meta["tail"] + 0.5 * meta["span"]
            rel = (ang - midang + math.pi) % (2 * math.pi) - math.pi
            lead_side = (rel < 0) if meta["span"] < 0 else (rel > 0)
            within = np.abs(rel) <= abs(meta["span"]) * 0.5 + 0.05
            lead_mass, tail_mass = int((lead_side & within).sum()), int((~lead_side & within).sum())
            if lead_mass > 1.3 * max(tail_mass, 1):
                heavy += 1
            if meta["tail"] > math.radians(165) + 0.2:
                moved += 1
                if pieces(c[..., 3]) >= 2:
                    broken += 1
        add("razor_lead", seen and heavy >= 0.7 * seen, f"{heavy}/{seen}", ">= 70 % lead-heavy (lead half > 1.3 x tail half)",
            "the crescent is not asymmetric: its weight should sit right behind the lead")
        add("jagged_wake", moved and broken >= 0.7 * moved, f"{broken}/{moved}",
            ">= 70 % of the drawings whose tail has left its start leave shards behind",
            "no broken wake behind the tail")
    elif grammar == "sakuga_smoke":
        shares = []
        for c in cells:
            tm = tone_masks(c, tones)
            sil = tm[0].sum()
            if sil > 50:
                shares.append(float((tm[0] & ~tm[1]).sum()) / float(sil))
        good = sum(1 for s in shares if 0.12 <= s <= 0.65)
        add("hard_shadow", shares and good >= 0.8 * len(shares), f"{good}/{len(shares)}",
            ">= 80 % with 12..65 % of the puff in the flat shadow tone", "the shadow shapes are missing or swallow the puff")
    elif grammar == "kanada_bolt":
        lum = [float((c[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32) * c[..., 3]).sum()) for c in cells]
        steps = np.sign(np.diff(lum))
        alt = int(np.count_nonzero(steps[1:] != steps[:-1])) if len(steps) > 1 else 0
        add("strobe", len(steps) > 1 and alt >= 0.9 * (len(steps) - 1), f"{alt}/{max(len(steps) - 1, 0)}",
            ">= 90 % of steps flip bright/dim (a 1-frame strobe)", "the bolt does not strobe frame by frame")
        sharp = []
        for c in cells[0::2]:
            m = (c[..., 3] > 0.5).astype(np.uint8)
            cs = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
            count = 0
            for cnt in cs:
                ap = cv2.approxPolyDP(cnt, 1.2, True).reshape(-1, 2).astype(np.float64)
                for i in range(len(ap)):
                    a0, a1, a2 = ap[i - 1], ap[i], ap[(i + 1) % len(ap)]
                    v1, v2 = a0 - a1, a2 - a1
                    if np.linalg.norm(v1) > 3 and np.linalg.norm(v2) > 3:
                        cosv = v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2))
                        if cosv > math.cos(math.radians(110)):
                            count += 1
            sharp.append(count)
        add("mitered", sharp and float(np.median(sharp)) >= 6, float(np.median(sharp)) if sharp else 0,
            ">= 6 outline corners of 110 degrees or sharper a flash drawing (a round join leaves none)",
            "the bolt's corners are rounded: mitered joins")
    elif grammar == "liquid_splash":
        late = [(c, d) for c, d in zip(cells, drawings) if d["meta"]["drops"] > 0]
        many = sum(1 for c, d in late if pieces(c[..., 3]) >= 6)
        add("drops", late and many >= 0.6 * len(late), f"{many}/{len(late)}", ">= 60 % of the drawings with drops show >= 6 pieces",
            "the threads do not break into drops")
        radii = []
        for c, d in late:
            want = d["meta"]["rd"] / win[2] * (1 - 2 * MARGIN) * cell
            cnt, lab, stats, _ = cv2.connectedComponentsWithStats((c[..., 3] > 0.5).astype(np.uint8), connectivity=8)
            for st in stats[1:]:                                  # round, lone pieces only (a thread or two drops
                bw, bh, area = st[cv2.CC_STAT_WIDTH], st[cv2.CC_STAT_HEIGHT], st[cv2.CC_STAT_AREA]   # touching is not one drop)
                if area < (3 * want) ** 2 and max(bw, bh) <= 1.5 * min(bw, bh) and area >= 0.6 * bw * bh:
                    radii.append(math.sqrt(area / math.pi) / want)
        med = float(np.median(radii)) if radii else 0.0
        add("rayleigh_plateau", 0.75 <= med <= 1.3, round(med, 3), "drop radius 0.75..1.3 x 1.89 r",
            "the drops are not the size the thread pinches into")
    return out
