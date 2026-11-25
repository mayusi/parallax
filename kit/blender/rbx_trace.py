"""rbx_trace.py — use a traced reference outline (kit trace) in a build script. Plain Python (no bpy needed).

    import rbx_trace as T
    t = T.load("barrett_side")                    # assets/models/barrett_side.trace.json
    stock = T.clip(t.outline, u0=0.0, u1=0.21)    # the part of the outline inside a band (u: back 0 .. front 1)
    body = T.clip(t.outline, u0=0.2, u1=0.62, h0=0.05)   # ... and above a height
    side = T.studs(stock, length=5.2, origin=(0.33, 0.06))  # -> (u, v) studs for extrude/carve plane="side"
    T.profile(t.outline, 0.4)                     # (bottom, top) of the silhouette at u = 0.4
    grip = T.smooth(t, part="grip", flat=0.0003)  # the SMOOTH curves sampled as finely as you want (a round grip
                                                  # stays round: chords within 0.03% of the length of the true curve)

Design units: u = 0 at the back of the object .. 1 at the front; h = height above the lowest point, in fractions
of the length. `studs` maps them to the side plane: u forward (-Z), v up, relative to an origin (u, h).
"""

import json
import math
import os


class Trace:
    def __init__(self, data):
        self.data = data
        self.outline = [tuple(p) for p in data["outline"]]
        self.holes = [[tuple(p) for p in h] for h in data.get("holes", [])]
        self.height = data.get("height_ratio", 0.0)
        # smooth curves (kit trace since curvefit): {"outline": [[p0, c1, c2, p3], ...], "holes": [...], "parts": {..}}
        self.curves = data.get("curves") or {}


def smooth(t, part=None, hole=None, flat=0.0005):
    """the trace's SMOOTH curves sampled into a polygon whose every chord lies within `flat` (design units: a fraction
    of the object's length — 0.0005 on a 1.45 m rifle = 0.7 mm) of the curve. part="grip": that --part outline;
    hole=0: the first hole; neither: the whole outline. A trace made before curves (or with --no-curves) has none:
    its polygon comes back unchanged."""
    import curvefit  # noqa: PLC0415  (beside this file)

    if part is not None:
        cv, poly = (t.curves.get("parts") or {}).get(part), (t.data.get("parts") or {}).get(part)
    elif hole is not None:
        hs = t.curves.get("holes") or []
        cv, poly = (hs[hole] if hole < len(hs) else None), t.holes[hole]
    else:
        cv, poly = t.curves.get("outline"), t.outline
    if poly is None:
        raise KeyError(f"smooth: no {'part ' + repr(part) if part is not None else 'hole %s' % hole} in this trace")
    if not cv:
        return [tuple(p) for p in poly]
    return curvefit.sample(cv, flat)


def px(t, x, y):
    """a point read off the reference PICTURE (its own pixels, as the trace preview shows them) -> design (u, h): the
    trace records where its frame sits (`frame`). A rotated or straightened trace has no such frame (the warp is not
    a shift): read the point off the trace's preview there."""
    fr = t.data.get("frame")
    if not fr:
        raise ValueError("px: this trace has no picture frame (made before frames, or rotated / straightened) — "
                         "re-run kit trace, or read the point off build/renders/<name>_trace.png")
    u = (x - fr["x0"]) / fr["length_px"]
    return (1.0 - u if t.data.get("front") == "left" else u, (fr["y1"] - y) / fr["length_px"])


def load(name, root=None):
    """the trace written by `kit trace <image> --name <name>` (assets/models/<name>.trace.json)."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = root or os.path.abspath(os.path.join(here, "..", ".."))
    with open(os.path.join(root, "assets", "models", f"{name}.trace.json"), encoding="utf-8") as fh:
        return Trace(json.load(fh))


def _clip_edge(poly, inside, cut):
    out = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(cut(prev, cur))
            out.append(cur)
        elif inside(prev):
            out.append(cut(prev, cur))
    return out


def clip(poly, u0=None, u1=None, h0=None, h1=None):
    """Sutherland-Hodgman: the polygon inside the axis-aligned band(s). Works on any traced outline (concave ok
    for convex clip windows). Returns [] when nothing is inside."""
    pts = list(poly)

    def cut_u(u):
        return lambda a, b: (u, a[1] + (b[1] - a[1]) * (u - a[0]) / ((b[0] - a[0]) or 1e-12))

    def cut_h(h):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (h - a[1]) / ((b[1] - a[1]) or 1e-12), h)

    for bound, inside, cut in (
        (u0, lambda p: p[0] >= u0, cut_u(u0) if u0 is not None else None),
        (u1, lambda p: p[0] <= u1, cut_u(u1) if u1 is not None else None),
        (h0, lambda p: p[1] >= h0, cut_h(h0) if h0 is not None else None),
        (h1, lambda p: p[1] <= h1, cut_h(h1) if h1 is not None else None),
    ):
        if bound is None or not pts:
            continue
        pts = _clip_edge(pts, inside, cut)
    return _dedupe(pts)


def _dedupe(pts, eps=1e-6):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < eps and abs(out[0][1] - out[-1][1]) < eps:
        out.pop()
    return out


def studs(poly, length, origin=(0.0, 0.0)):
    """design (u, h) -> side-plane studs (u forward, v up) for an object `length` studs long, origin at (u, h)."""
    ou, oh = origin
    return [((u - ou) * length, (h - oh) * length) for u, h in poly]


def profile(poly, u):
    """(bottom, top) heights of the outline at position u (the extreme crossings), or None."""
    hs = []
    n = len(poly)
    for i in range(n):
        (u0, h0), (u1, h1) = poly[i - 1], poly[i]
        if (u0 - u) * (u1 - u) <= 0 and u0 != u1:
            hs.append(h0 + (h1 - h0) * (u - u0) / (u1 - u0))
    return (min(hs), max(hs)) if hs else None


def bounds(poly):
    us = [p[0] for p in poly]
    hs = [p[1] for p in poly]
    return min(us), min(hs), max(us), max(hs)


def offset(poly, d):
    """grow (d > 0) or shrink (d < 0) a polygon by d (same units), mitered corners — clearance gaps between a part
    and the notch it sits in (a magazine in its well, a grip on its frame)."""
    import math

    n = len(poly)
    area = sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(n)) / -2
    sign = 1 if area > 0 else -1  # outward normals for either winding
    out = []
    for i in range(n):
        (x0, y0), (x1, y1), (x2, y2) = poly[i - 1], poly[i], poly[(i + 1) % n]

        def normal(ax, ay, bx, by):
            dx, dy = bx - ax, by - ay
            ln = math.hypot(dx, dy) or 1.0
            return (dy / ln * sign, -dx / ln * sign)

        n0, n1 = normal(x0, y0, x1, y1), normal(x1, y1, x2, y2)
        mx, my = n0[0] + n1[0], n0[1] + n1[1]
        ml = math.hypot(mx, my) or 1.0
        mx, my = mx / ml, my / ml
        cosh = max(0.3, mx * n1[0] + my * n1[1])  # cap the miter at sharp corners
        out.append((x1 + mx * d / cosh, y1 + my * d / cosh))
    return out


def clean(poly, tol):
    """remove the pixel STAIRCASE a traced edge carries (a slanted edge traced from pixels is a run of tiny steps;
    cut into a part, it reads as a jagged saw edge). Douglas-Peucker in design units: every point that lies within
    `tol` of the straight line through its neighbours goes. Use tol ~ 1 mm real: clean(poly, 1.0 / length_mm)."""
    pts = list(poly)
    if len(pts) < 5:
        return pts

    def dist(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1e-12
        return abs(dx * (p[1] - a[1]) - dy * (p[0] - a[0])) / n

    def rec(seq):
        if len(seq) < 3:
            return seq
        a, b = seq[0], seq[-1]
        k, dk = 0, -1.0
        for i in range(1, len(seq) - 1):
            d = dist(seq[i], a, b)
            if d > dk:
                k, dk = i, d
        if dk > tol:
            return rec(seq[: k + 1])[:-1] + rec(seq[k:])
        return [a, b]

    # split the closed loop at its two farthest-apart points
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    first = rec(pts[: far + 1])
    second = rec(pts[far:] + [pts[0]])
    return first[:-1] + second[:-1]


def _raster(rings, u0, h0, step, w, h):
    """even-odd scanline fill of polygon rings (design units) on a w x h grid of `step` cells from (u0, h0)."""
    import numpy as np

    edges = []
    for ring in rings:
        pts = [((p[0] - u0) / step + 1, (p[1] - h0) / step + 1) for p in ring]
        edges += [(pts[i - 1], pts[i]) for i in range(len(pts))]
    mask = np.zeros((h, w), bool)
    if not edges:
        return mask
    e = np.array(edges, float)
    ex0, ey0, ex1, ey1 = e[:, 0, 0], e[:, 0, 1], e[:, 1, 0], e[:, 1, 1]
    xs = np.arange(w) + 0.5
    for row in range(1, h - 1):
        yc = row + 0.5
        hit = (ey0 <= yc) != (ey1 <= yc)
        if hit.any():
            xc = np.sort(ex0[hit] + (yc - ey0[hit]) * (ex1[hit] - ex0[hit]) / (ey1[hit] - ey0[hit]))
            mask[row] = (np.searchsorted(xc, xs) % 2) == 1
    return mask


def _grow(mask, r):
    import numpy as np

    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def region(poly, u0=None, u1=None, h0=None, h1=None, length_mm=None, res_mm=0.5, holes=(), every=False, clean_mm=1.0,
           minus=(), min_mm=1.5, round_mm=0.0):
    """the traced silhouette inside a box, as CLEAN polygon(s) — rasterised, masked, contoured. Unlike clip(), a
    concave outline that crosses the box edge several times (a skeleton stock, a trigger guard) never produces the
    zero-width "bridges" that make an extrusion collapse. -> the largest piece (or every piece, every=True).
    res_mm / length_mm: raster resolution (0.5 mm on a 1448 mm rifle); without length_mm, 1/2000 of the length.
    minus: [(polygon, gap_mm), ...] taken out BEFORE contouring — split one traced shape into pieces (a receiver minus
    its magazine and grip) on ONE raster, so the pieces share their boundary exactly (gap_mm = the seam between them).
    Cutting a piece out with a separately simplified outline instead leaves slivers wherever the two simplifications
    disagree (measured: ~1 mm shelves under a grip and a magazine).
    round_mm: fillet every corner (a closing fills inside corners, an opening rounds outside ones) — a traced outline
    has hard pixel corners and a subtraction can leave a pointed shard; machined / moulded parts have radii."""
    import numpy as np

    step = (res_mm / length_mm) if length_mm else 0.0005
    b = bounds(poly)
    u0 = b[0] if u0 is None else max(u0, b[0])
    u1 = b[2] if u1 is None else min(u1, b[2])
    h0 = b[1] if h0 is None else max(h0, b[1])
    h1 = b[3] if h1 is None else min(h1, b[3])
    if u1 <= u0 or h1 <= h0:
        return [] if every else None
    w = int((u1 - u0) / step) + 3
    h = int((h1 - h0) / step) + 3
    mask = _raster([poly, *holes], u0, h0, step, w, h)
    rr = max(1, int(round(round_mm / res_mm))) if (round_mm and length_mm) else 0
    if rr:  # the outer shape gets its fillets BEFORE the mating cuts (those must stay exact)
        pad = rr + 2
        big = np.pad(mask, pad)
        big = ~_grow(~_grow(big, rr), rr)  # closing: inside corners filleted
        big = _grow(~_grow(~big, rr), rr)  # opening: outside corners rounded
        mask = big[pad:-pad, pad:-pad]
    for other, gap_mm in minus:
        cut = _raster([other], u0, h0, step, w, h)
        r = int(round((gap_mm / length_mm) / step)) if (length_mm and gap_mm) else 0
        mask &= ~(_grow(cut, r) if r > 0 else cut)
    # a wall thinner than min_mm left between two subtractions is a sliver, not a part: open it away
    if minus and length_mm:
        r = max(1, int(math.ceil(min_mm / res_mm / 2)))
        thin = ~_grow(~mask, r)
        mask = _grow(thin, r) & mask
    if rr and minus:  # shards a subtraction left (two cuts converging to a point): opening only, mating corners stay
        pad = rr + 2
        big = np.pad(mask, pad)
        big = _grow(~_grow(~big, rr), rr)
        mask = big[pad:-pad, pad:-pad]
    mask[:, :1] = mask[:, -1:] = False
    mask[:1, :] = mask[-1:, :] = False
    # components (4-connected), biggest first
    lab = np.zeros(mask.shape, np.int32)
    comps = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n = len(comps) + 1
        stack, size = [(y0, x0)], 0
        lab[y0, x0] = n
        while stack:
            y, x = stack.pop()
            size += 1
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if mask[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    stack.append((yy, xx))
        comps.append((size, n))
    comps.sort(reverse=True)
    out = []
    for size, n in comps if every else comps[:1]:
        if size < 20:
            continue
        m = lab == n
        # outer boundary (Moore neighbour trace)
        ys, xs_ = np.nonzero(m)
        i = np.lexsort((xs_, ys))[0]
        start = (int(xs_[i]), int(ys[i]))
        dirs = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
        pts, cur, back = [start], start, 4
        for _ in range(8 * (h + w) * 4):
            found = False
            for k in range(8):
                d = (back + 1 + k) % 8
                nx, ny = cur[0] + dirs[d][0], cur[1] + dirs[d][1]
                if 0 <= ny < h and 0 <= nx < w and m[ny, nx]:
                    cur, back, found = (nx, ny), (d + 4) % 8, True
                    break
            if not found or cur == start:
                break
            pts.append(cur)
        poly_out = [(u0 + (x + 0.5 - 1) * step, h0 + (y + 0.5 - 1) * step) for x, y in pts]
        # pixel centres -> the true edge; then clean at the SOURCE photo's pixel size (~1 mm), not the raster's:
        # a staircase left from the photo reads as a jagged saw edge on the model
        tol = (clean_mm / length_mm) if length_mm else step * 2
        out.append(clean(offset(poly_out, step * 0.5), max(step * 0.8, tol)))
    if every:
        return out
    return out[0] if out else None


def hull(poly):
    """convex hull (monotone chain) — an opening traced AROUND something solid in the photo (a trigger guard with
    the trigger in it, a window with a figure behind) becomes the whole opening."""
    pts = sorted(set(map(tuple, poly)))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def measure(name, root=None):
    """refs/<name>.measure.json — a 3D reference measured by `kit refs measure` (real millimetres)"""
    here = os.path.dirname(os.path.abspath(__file__))
    root = root or os.path.abspath(os.path.join(here, "..", ".."))
    with open(os.path.join(root, "refs", f"{name}.measure.json"), encoding="utf-8") as fh:
        return json.load(fh)


def loft_stations(m, length_studs, ends=True):
    """a measured reference's cross-sections as stations for a.loft(name, stations, mat, axis="Z"), scaled so the
    whole object is `length_studs` long: (along, rx, ry, (off_width, off_height), squareness) in studs — `along` from
    -length/2 (the back, u = 0) to +length/2 (the front, u = 1), heights above the object's lowest point. ends=True
    adds a closing station at each end (a quarter of the first / last section), so the loft does not end in a flat cut.
    (Roblox's front is -Z: put the loft at rot=(0, 180, 0) or mirror `along` when the front must face -Z.)"""
    length_mm = float(m["size_mm"][2])
    k = length_studs / length_mm
    out = []
    for s in m["stations"]:
        along = (s["u"] - 0.5) * length_studs
        out.append((along, s["rx_mm"] * k, s["ry_mm"] * k, (s["off_mm"][0] * k, s["off_mm"][1] * k), s["squareness"]))
    if ends and out:
        first, last = out[0], out[-1]
        out.insert(0, (-length_studs / 2, first[1] * 0.25, first[2] * 0.25, first[3], first[4]))
        out.append((length_studs / 2, last[1] * 0.25, last[2] * 0.25, last[3], last[4]))
    return out
