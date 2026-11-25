"""rbx_profile.py — plain 2D outline operations every traced / measured build needs (rbx.profile; also given to a.cad
code as `profile`). Pure Python (numpy only for smooth_run): runs in Blender, in the cad env and in the tests.

A profile is a list of (u, v) points in millimetres — a side view's (f, h): f along the object (forward), h up — closed
rings for outlines, open lists for paths and sections. Every function returns new points; none edits its input.

Where they came from: the Silverballer's and the Glock's builds (2026-10-07 .. 10), private scripts until the owner's
85/100 on the Glock showed the route works — clip a traced outline to a part's range, read an edge off it as a median
(the trace's pixel noise averaged out), smooth a strap's run, sweep a measured section through its keys without a
crease, cut a U-trough with a round floor.
"""

import json
import math
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def profiles(name):
    """assets/models/<name>.profiles.json (kit refs profiles: a trace's parts as outlines in mm) -> its dict"""
    with open(os.path.join(REPO, "assets", "models", f"{name}.profiles.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _clip(poly, inside, cross):
    """Sutherland-Hodgman against one half-plane: inside(p) -> bool, cross(a, b) -> the point on the boundary"""
    out = []
    for i in range(len(poly)):
        a, b = poly[i - 1], poly[i]
        ia, ib = inside(a), inside(b)
        if ib:
            if not ia:
                out.append(cross(a, b))
            out.append(b)
        elif ia:
            out.append(cross(a, b))
    return out


def clip_h(poly, lo=None, hi=None):
    """the part of a closed polygon with lo <= h <= hi"""
    def at_h(c):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (c - a[1]) / ((b[1] - a[1]) or 1e-12), c)
    out = [tuple(p) for p in poly]
    if hi is not None:
        out = _clip(out, lambda p: p[1] <= hi, at_h(hi))
    if lo is not None and out:
        out = _clip(out, lambda p: p[1] >= lo, at_h(lo))
    return out


def clip_f(poly, lo=None, hi=None):
    """the part of a closed polygon with lo <= f <= hi"""
    def at_f(c):
        return lambda a, b: (c, a[1] + (b[1] - a[1]) * (c - a[0]) / ((b[0] - a[0]) or 1e-12))
    out = [tuple(p) for p in poly]
    if hi is not None:
        out = _clip(out, lambda p: p[0] <= hi, at_f(hi))
    if lo is not None and out:
        out = _clip(out, lambda p: p[0] >= lo, at_f(lo))
    return out


def span_at(poly, h):
    """where a horizontal line at h crosses the polygon -> (f_min, f_max), or None"""
    xs = []
    for i in range(len(poly)):
        (fa, ha), (fb, hb) = poly[i - 1], poly[i]
        if (ha <= h < hb) or (hb <= h < ha):
            xs.append(fa + (fb - fa) * (h - ha) / (hb - ha))
    return (min(xs), max(xs)) if xs else None


def vspan(poly, f):
    """where a vertical line at f crosses the polygon -> (h_min, h_max), or None"""
    ys = []
    for i in range(len(poly)):
        (fa, ha), (fb, hb) = poly[i - 1], poly[i]
        if (fa <= f < fb) or (fb <= f < fa):
            ys.append(ha + (hb - ha) * (f - fa) / (fb - fa))
    return (min(ys), max(ys)) if ys else None


def extents(poly):
    """(f_min, f_max, h_min, h_max)"""
    fs, hs = [p[0] for p in poly], [p[1] for p in poly]
    return min(fs), max(fs), min(hs), max(hs)


def circle(fc, hc, r, n=24):
    return [(fc + r * math.cos(2 * math.pi * i / n), hc + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rounded(poly, nd=2):
    """the points rounded to nd decimals, as lists (a.cad params: JSON, and a stable cache key)"""
    return [[round(p[0], nd), round(p[1], nd)] for p in poly]


def edge(poly, f0, f1, which="lower", step=0.5):
    """the MEDIAN height of a polygon's lower (or upper) edge between f0 and f1 — a measured edge, the trace's pixel
    noise and a part or two in the way (a slide stop under a slide) averaged out"""
    hs = []
    f = f0
    while f <= f1:
        s = vspan(poly, f)
        if s:
            hs.append(s[0] if which == "lower" else s[1])
        f += step
    hs.sort()
    return hs[len(hs) // 2] if hs else None


def rotate(poly, pivot, deg):
    """a profile turned about pivot by deg (counter-clockwise with f right and h up — the kit's +angle about +X)"""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    fp, hp = pivot
    return [(fp + (f - fp) * c - (h - hp) * s, hp + (f - fp) * s + (h - hp) * c) for f, h in poly]


def shift(poly, df=0.0, dh=0.0):
    return [(f + df, h + dh) for f, h in poly]


def rect(f0, f1, h0, h1):
    return [(f0, h0), (f1, h0), (f1, h1), (f0, h1)]


def between(poly, a, b):
    """the run of a closed polygon's points from the one nearest a to the one nearest b (in the ring's own order)"""
    ia = min(range(len(poly)), key=lambda i: (poly[i][0] - a[0]) ** 2 + (poly[i][1] - a[1]) ** 2)
    ib = min(range(len(poly)), key=lambda i: (poly[i][0] - b[0]) ** 2 + (poly[i][1] - b[1]) ** 2)
    return [tuple(poly[(ia + k) % len(poly)]) for k in range((ib - ia) % len(poly) + 1)]


def simplify(poly, tol):
    """Douglas-Peucker on a closed ring (split at its two farthest points): a traced outline with fewer, longer edges
    (a CAD profile offset and filleted cleanly) within tol mm of the trace"""
    if len(poly) < 4:
        return list(poly)

    def dp(pts):
        if len(pts) < 3:
            return pts
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy) or 1e-12
        far, idx = -1.0, 0
        for i in range(1, len(pts) - 1):
            d = abs(dy * (pts[i][0] - x0) - dx * (pts[i][1] - y0)) / ln
            if d > far:
                far, idx = d, i
        return [pts[0], pts[-1]] if far <= tol else dp(pts[: idx + 1])[:-1] + dp(pts[idx:])

    ring = [tuple(p) for p in poly]
    i1 = max(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - ring[0][0], ring[i][1] - ring[0][1]))
    return dp(ring[: i1 + 1])[:-1] + dp(ring[i1:] + ring[:1])[:-1]


def catmull(keys, step=0.25):
    """a smooth path through the keys (Catmull-Rom; its ends' tangents along their first / last legs), points ~step mm
    apart: a MEASURED section swept or cut with no crease past a few degrees. Each key of a plain polyline is a crease
    the bevel check reads as a hard edge, and the eye as a facet (the Glock's dust-cover rail, keyed from the reference
    model's slices every 0.5 mm, 2026-10-10)"""
    keys = [tuple(k) for k in keys]
    if len(keys) < 2:
        return list(keys)
    pts = [keys[0]]
    ext = [keys[0]] + keys + [keys[-1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        n = max(1, int(math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step))
        for k in range(1, n + 1):
            t = k / n
            pts.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t * t
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t ** 3) for j in range(2)))
    return pts


def u_floor(half_w, h_wall, h_floor, n=14):
    """a U's floor: a half-ELLIPSE from (half_w, h_wall) round to (-half_w, h_wall), down to h_floor — a channel's
    rounded bottom (a spring channel, a trough) with no crease past 180/n degrees (n 40 for a long loft: at 14 its
    facets read as ridges)"""
    return [(half_w * math.cos(math.pi * k / n), h_wall - (h_wall - h_floor) * math.sin(math.pi * k / n))
            for k in range(n + 1)]


def u_section(xl, xr, wall_d, floor_d, top, chamfer=0.6, n=12, chamfer_right=True, above=3.0):
    """a U-TROUGH's section [(x, h)] to CUT into a part whose top is at h = top, open above it: straight walls at xl / xr
    down wall_d mm, then a half-ellipse floor down to floor_d (no crease past the 30 deg a hard edge is: a row of
    straight segments reads as sharp edges to the bevel check), each top edge chamfered `chamfer` at 45 deg (a moulded
    edge; chamfer_right=False leaves the right one square where it meets another cut). `above`: how far the cutter
    rises past the top (a clean boolean). The Glock frame's rail troughs, 2026-10-10: the frame is a SHELL — measure it
    against a reference model's slices (kit refs sections), never a solid extrusion"""
    cx, ax, bz = (xl + xr) / 2, (xr - xl) / 2, floor_d - wall_d
    pts = [(xl - chamfer, top + above), (xr + (chamfer if chamfer_right else 0.0), top + above)]
    if chamfer_right:
        pts += [(xr + chamfer, top), (xr, top - chamfer)]
    for k in range(n + 1):
        t = math.pi * k / n   # (from the right wall round the floor to the left)
        pts.append((cx + ax * math.cos(t), top - wall_d - bz * math.sin(t)))
    pts += [(xl, top - chamfer), (xl - chamfer, top)]
    return pts


def smooth_run(pts, h0, h1, near=None, deg=3, step=1.5, tol=3.0):
    """an outline's run between heights h0 > h1 replaced by a smooth fit (a degree-`deg` polynomial f(h), a point every
    `step` mm): a photo trace wiggles 0.1-0.3 mm along a long straight-ish edge, and extruded across a part each wiggle
    reads as a RIDGE (the Glock's front strap: the owner, 'it's supposed to be smooth'). near(h) -> f picks which side
    of the outline (the points within tol mm of it; None: every point in the band). The run must be ONE contiguous run
    of at least 6 points — otherwise the outline comes back as it was (never a guess). Join it where the trace is
    already straight: a kink at a join made a CAD solid whose mesh disagreed with it by 9.5% (open edges on import)."""
    import numpy as np

    side = [i for i, (f, h) in enumerate(pts) if h1 <= h <= h0 and (near is None or abs(f - near(h)) < tol)]
    if len(side) < 6 or side != list(range(side[0], side[-1] + 1)):
        return list(pts)
    hs = np.array([pts[i][1] for i in side])
    fs = np.array([pts[i][0] for i in side])
    c = np.polyfit(hs, fs, deg)
    a, b = pts[side[0]][1], pts[side[-1]][1]
    n = max(4, int(abs(b - a) / step))
    new = [(float(np.polyval(c, a + (b - a) * k / n)), a + (b - a) * k / n) for k in range(n + 1)]
    return list(pts[:side[0]]) + new + list(pts[side[-1] + 1:])
