"""curvefit.py — SMOOTH CURVES from a traced pixel outline (plain python + numpy, no bpy).

A traced outline is a staircase of pixels. Simplified to a polygon (Douglas-Peucker) a curved part — a grip, a stock's
sweep, a round guard — becomes facets that follow the stairs. Here the outline becomes what it is: sharp corners kept
exactly, and between them a few cubic Beziers on the TRUE edge (sub-pixel: the staircase averaged out), fitted by
least squares (Schneider, "An Algorithm for Automatically Fitting Digitized Curves", Graphics Gems, 1990). A build then
samples the curves as finely as its triangle budget allows (rbx_trace.smooth).

    pts, corners = subpixel(contour)       # a Moore pixel contour -> points ON the edge (px), corner indices
    curves = fit(pts, corners, tol=0.5)    # [[p0, c1, c2, p3], ...] closed: each segment's p3 is the next one's p0
    poly = sample(curves, flat=1.5)        # a polygon whose every chord is within `flat` of the curve
    flat = outline_flatness(curves, 1.5)   # the sampling a traced outline gets (finer for small shapes)

Pixel convention: a contour point (x, y) is a pixel INDEX; that pixel covers [x, x + 1] x [y, y + 1]. subpixel()
returns continuous coordinates on that grid (the object's edge, not its boundary pixels' corners).
"""

import math

import numpy as np


def _shoelace(a):
    x, y = a[:, 0], a[:, 1]
    return 0.5 * float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum())


def _corners(a, k, corner_deg):
    """indices where the outline turns sharply: the angle between the chords to the k-th neighbour on each side is
    above corner_deg and the largest within k (one corner per bend)"""
    n = len(a)
    prev, nxt = a - np.roll(a, k, 0), np.roll(a, -k, 0) - a
    cos = (prev * nxt).sum(1) / (np.linalg.norm(prev, axis=1) * np.linalg.norm(nxt, axis=1) + 1e-9)
    ang = np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))
    out = []
    for i in range(n):
        if ang[i] <= corner_deg:
            continue
        window = [ang[(i + j) % n] for j in range(-k, k + 1)]
        if ang[i] < max(window):
            continue
        if out and (i - out[-1]) <= k:  # a plateau of equal maxima: one corner
            continue
        out.append(i)
    if len(out) > 1 and (out[0] + n - out[-1]) <= k:
        out.pop()
    return out


def _meet(a, c, corners, reach=10):
    """where the two edges at corner c meet: lines fitted through the points 2..reach steps away on each side (never
    past the neighbouring corners) -> the intersection, or None (too few points, or nearly parallel edges)"""
    n = len(a)
    i = corners.index(c)
    prev_c, next_c = corners[i - 1], corners[(i + 1) % len(corners)]
    lines = []
    for sign, other in ((-1, prev_c), (1, next_c)):
        gap = (c - other) % n if sign < 0 else (other - c) % n
        idx = [(c + sign * j) % n for j in range(2, reach) if gap == 0 or j < gap - 1]
        if len(idx) < 3:
            return None
        pts = a[idx]
        mu = pts.mean(0)
        w, vec = np.linalg.eigh((pts - mu).T @ (pts - mu))
        lines.append((mu, vec[:, int(np.argmax(w))]))
    (p1, d1), (p2, d2) = lines
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < math.sin(math.radians(10)):
        return None
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    return p1 + t * d1


def subpixel(contour, sigma=1.2, k=6, corner_deg=50.0, meet_px=1.5):
    """a closed Moore contour (pixel indices, in order) -> (points ON the object's edge, corner indices). The outline
    is smoothed along its length by a Gaussian that never reaches across a corner (corners stay sharp), then every
    point moves half a pixel outward: a boundary pixel's centre lies half a pixel inside the edge."""
    a = np.asarray(contour, float) + 0.5  # pixel centres
    keep = np.r_[True, np.any(np.diff(a, axis=0) != 0, axis=1)]
    a = a[keep]
    n = len(a)
    if n < 8:
        return a, []
    # a CORNER has straight sides that meet ON the outline; a tight bend (an ellipse's end, a small round) turns as
    # sharply but its side lines meet 2-3 px out in the air (measured): it is a curve, smoothed like one
    cands = _corners(a, k, corner_deg)
    corners = []
    for c in cands:
        x = _meet(a, c, cands)
        if x is not None and float(np.min(np.hypot(*(a - x).T))) <= meet_px:
            corners.append(c)
    r = max(1, int(math.ceil(3 * sigma)))
    w = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    sm = a.copy()
    if not corners:
        sm = sum(w[j + r] * np.roll(a, -j, 0) for j in range(-r, r + 1)) / w.sum()
    else:
        for ci, c0 in enumerate(corners):
            c1 = corners[(ci + 1) % len(corners)]
            span = (c1 - c0) % n or n
            idx = [(c0 + t) % n for t in range(span + 1)]
            seg = a[idx]
            for t in range(1, span):  # the window is cut at the span's ends: never across a corner
                lo, hi = max(0, t - r), min(span, t + r)
                ww = w[lo - t + r:hi - t + r + 1]
                sm[idx[t]] = (seg[lo:hi + 1] * ww[:, None]).sum(0) / ww.sum()
    tang = np.roll(sm, -1, 0) - np.roll(sm, 1, 0)
    nrm = np.stack([tang[:, 1], -tang[:, 0]], 1)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    if _shoelace(sm) < 0:
        nrm = -nrm  # (ty, -tx) points outward on a positive-area loop, inward on a negative one
    e = sm + 0.5 * nrm
    # the corner point itself: where its two edges MEET (the pixel at the bend is a staircase step)
    for c in corners:
        x = _meet(e, c, corners)
        if x is not None and float(np.linalg.norm(x - e[c])) <= 3.0:
            e[c] = x
    return e, corners


def _bez(b, u):
    u = np.asarray(u, float)[..., None]
    v = 1 - u
    return v ** 3 * b[0] + 3 * v * v * u * b[1] + 3 * v * u * u * b[2] + u ** 3 * b[3]


def _bez1(b, u):
    u = np.asarray(u, float)[..., None]
    v = 1 - u
    return 3 * (v * v * (b[1] - b[0]) + 2 * v * u * (b[2] - b[1]) + u * u * (b[3] - b[2]))


def _bez2(b, u):
    u = np.asarray(u, float)[..., None]
    return 6 * ((1 - u) * (b[2] - 2 * b[1] + b[0]) + u * (b[3] - 2 * b[2] + b[1]))


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else np.array([1.0, 0.0])


def _generate(d, u, t1, t2):
    """least-squares control points along the end tangents (t1 forward from d[0], t2 backward from d[-1])"""
    p0, p3 = d[0], d[-1]
    uu = u[:, None]
    b0, b1, b2, b3 = (1 - uu) ** 3, 3 * uu * (1 - uu) ** 2, 3 * uu * uu * (1 - uu), uu ** 3
    a1, a2 = t1 * b1, t2 * b2
    c = np.array([[(a1 * a1).sum(), (a1 * a2).sum()], [(a1 * a2).sum(), (a2 * a2).sum()]])
    tmp = d - (p0 * (b0 + b1) + p3 * (b2 + b3))
    x = np.array([(a1 * tmp).sum(), (a2 * tmp).sum()])
    det = c[0, 0] * c[1, 1] - c[0, 1] * c[1, 0]
    seg = float(np.linalg.norm(p3 - p0))
    al1 = al2 = 0.0
    if abs(det) > 1e-12:
        al1 = (x[0] * c[1, 1] - x[1] * c[0, 1]) / det
        al2 = (c[0, 0] * x[1] - c[1, 0] * x[0]) / det
    if al1 < 1e-6 * seg or al2 < 1e-6 * seg:
        al1 = al2 = seg / 3  # (the Wu / Barsky heuristic when least squares degenerates)
    return np.array([p0, p0 + t1 * al1, p3 + t2 * al2, p3])


def _reparam(d, u, b):
    """one Newton step per point toward its nearest spot on the curve"""
    diff = _bez(b, u) - d
    d1, d2 = _bez1(b, u), _bez2(b, u)
    num = (diff * d1).sum(1)
    den = (d1 * d1).sum(1) + (diff * d2).sum(1)
    out = np.where(np.abs(den) > 1e-12, u - num / np.where(np.abs(den) > 1e-12, den, 1), u)
    return np.clip(out, 0.0, 1.0)


def _good(err, tol):
    """a segment fits when its typical error is small (rms <= tol / 2: a smooth miss like an arc's) and no point is far
    off (max <= 2 tol: a photo's few noisy edge pixels are not shape) — following every noisy pixel to a max of tol
    tripled the segments on a photographed rifle, while a pure max of 2 tol let an ellipse drift past a pixel"""
    return float(np.sqrt((err ** 2).mean())) <= tol / 2 and float(err.max()) <= 2 * tol


def _fit_cubic(d, t1, t2, tol, depth=0):
    if len(d) == 2:
        dist = float(np.linalg.norm(d[1] - d[0])) / 3
        return [np.array([d[0], d[0] + t1 * dist, d[1] + t2 * dist, d[1]])]
    cl = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(d, axis=0), axis=1))]
    u = cl / cl[-1] if cl[-1] > 0 else np.linspace(0, 1, len(d))
    b = _generate(d, u, t1, t2)
    err = np.linalg.norm(_bez(b, u) - d, axis=1)
    if _good(err, tol):
        return [b]
    if err.max() <= 8 * tol:
        for _ in range(20):
            u = _reparam(d, u, b)
            b = _generate(d, u, t1, t2)
            err = np.linalg.norm(_bez(b, u) - d, axis=1)
            if _good(err, tol):
                return [b]
    split = int(np.argmax(err[1:-1])) + 1 if len(d) > 2 else len(d) // 2
    if depth > 40 or len(d) < 4:
        return [b]
    tc = _unit(d[split - 1] - d[split + 1])
    return _fit_cubic(d[:split + 1], t1, tc, tol, depth + 1) + _fit_cubic(d[split:], -tc, t2, tol, depth + 1)


def _end_tangent(d, m=5):
    """the direction a span leaves its first point: the least-squares line through its first m points"""
    pts = d[: max(2, min(m, len(d)))]
    v = pts[-1] - pts[0]
    if len(pts) > 2:
        c = pts - pts.mean(0)
        w, vec = np.linalg.eigh(c.T @ c)
        axis = vec[:, int(np.argmax(w))]
        v = axis if float(axis @ v) >= 0 else -axis
    return _unit(v)


def fit(points, corners, tol=0.5):
    """closed smoothed outline + its corners -> closed list of cubic Beziers (np arrays [p0, c1, c2, p3]): rms error
    within tol / 2 px and no point further than 2 tol (see _good), tangent-continuous except at the corners"""
    a = np.asarray(points, float)
    n = len(a)
    if n < 4:
        return [np.array([a[i], a[i], a[(i + 1) % n], a[(i + 1) % n]]) for i in range(n)]
    if corners:
        cs, smooth_ends = list(corners), False
    else:  # a closed smooth loop: two halves joined with matching tangents
        cs, smooth_ends = [0, n // 2], True
    out = []
    for ci, c0 in enumerate(cs):
        c1 = cs[(ci + 1) % len(cs)]
        span = (c1 - c0) % n or n
        d = a[[(c0 + t) % n for t in range(span + 1)]]
        if smooth_ends:
            t1 = _unit(a[(c0 + 1) % n] - a[(c0 - 1) % n])
            t2 = -_unit(a[(c1 + 1) % n] - a[(c1 - 1) % n])
        else:
            t1, t2 = _end_tangent(d), _end_tangent(d[::-1])
        out += _fit_cubic(d, t1, t2, tol)
    return out


def outline_flatness(curves, tolerance=1.5):
    """how closely an outline's polygon should follow its curves (px): `tolerance`, but never coarser than 2% of the
    shape's smaller side — a 24 px part sampled at 1.5 px loses its roundness (and fits worse than the staircase did)"""
    pts = np.array([b[i] for b in curves for i in (0, 3)], float)
    side = float(min(pts.max(0) - pts.min(0))) if len(pts) else 0.0
    return min(tolerance, max(0.3, 0.02 * side))


def sample(curves, flat=1.5):
    """closed polygon from the curves: each cubic split in half until its control points lie within `flat` of its
    chord (a chord then never strays further than `flat` from the curve). Corners and joins are vertices."""
    out = []

    def rec(b, depth):
        p0, c1, c2, p3 = b
        ch = p3 - p0
        ln = float(np.linalg.norm(ch))
        if ln > 1e-12:
            dist = max(abs(float(ch[0] * (c[1] - p0[1]) - ch[1] * (c[0] - p0[0]))) / ln for c in (c1, c2))
        else:
            dist = max(float(np.linalg.norm(c1 - p0)), float(np.linalg.norm(c2 - p0)))
        if 0.75 * dist <= flat or depth > 16:  # a cubic strays at most 3/4 of its control points' distance
            out.append(p0)
            return
        m01, m12, m23 = (p0 + c1) / 2, (c1 + c2) / 2, (c2 + p3) / 2
        m012, m123 = (m01 + m12) / 2, (m12 + m23) / 2
        mid = (m012 + m123) / 2
        rec((p0, m01, m012, mid), depth + 1)
        rec((mid, m123, m23, p3), depth + 1)

    for b in curves:
        rec(tuple(np.asarray(b, float)), 0)
    return [(float(p[0]), float(p[1])) for p in out]
