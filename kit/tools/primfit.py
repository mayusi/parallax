"""primfit.py — a traced outline REDRAWN from true primitives: straight LINES and circular ARCS, the way a designer
draws a part (and the way the game's artist drew Scarborough Fair). A trace follows its pixels: every edge wobbles a
little and every round is a spline, and the model shows it ("the designs on it look so weird", the owner,
2026-10-22). Fitted to lines + arcs, a 12 mm round is a 12 mm round, a straight edge is straight, and fillets take it.

    prims = fit(points, tol=0.15, corner_deg=35)      [{"type": "line", "a", "b"} | {"type": "arc", "a", "m", "b",
                                                        "c", "r"}] — a closed chain, each primitive's b = the next's a
    prims = fit_mirrored(points, axis="x", at=0.0)    one half fitted, mirrored: a symmetric part exactly symmetric
    pts = sample(prims, step=0.25)                    the redraw as a polyline (preview, area, tests)
    report(points, prims)                             how far the redraw is from the trace (max / mean mm), counts

Pure numpy (kit/test/python/test_primfit.py). cad_parts.redraw() turns the primitives into a build123d Face.
"""

import math

import numpy as np


def _clean(points):
    p = np.asarray(points, float)
    keep = [0]
    for i in range(1, len(p)):
        if np.hypot(*(p[i] - p[keep[-1]])) > 1e-6:
            keep.append(i)
    p = p[keep]
    if len(p) > 2 and np.hypot(*(p[0] - p[-1])) <= 1e-6:
        p = p[:-1]
    return p


def resample(p, step):
    """a closed polyline at even spacing (the fit sees the shape, not the trace's point density)"""
    q = np.vstack([p, p[:1]])
    seg = np.hypot(*np.diff(q, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = max(8, int(s[-1] / step))
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, s, q[:, 0]), np.interp(t, s, q[:, 1])])


def _turns(p, w):
    """the turn (degrees) at each point over +-w points: a corner turns sharply in a short window"""
    n = len(p)
    out = np.zeros(n)
    for i in range(n):
        a, b = p[i] - p[(i - w) % n], p[(i + w) % n] - p[i]
        out[i] = abs(math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a @ b)))
    return out


def corners(p, corner_deg, w=2):
    t = _turns(p, w)
    n, cs = len(p), []
    for i in range(n):
        if t[i] > corner_deg and t[i] >= t[(i - 1) % n] and t[i] > t[(i + 1) % n]:
            cs.append(i)
    return cs


def _line_dev(run):
    a, b = run[0], run[-1]
    ab = b - a
    L = np.hypot(*ab)
    if L < 1e-9:
        return float(np.max(np.hypot(*(run - a).T)))
    return float(np.max(np.abs(ab[0] * (run[:, 1] - a[1]) - ab[1] * (run[:, 0] - a[0])) / L))


def _circle(run):
    """least-squares circle (Kasa) -> centre, radius, max deviation"""
    x, y = run[:, 0], run[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0))
    dev = float(np.max(np.abs(np.hypot(x - cx, y - cy) - r)))
    return np.array([cx, cy]), r, dev


def _one(run, tol):
    """ONE primitive through the run within tol, or None: a line first, else an arc (a sane one: not a near-line of
    huge radius, not a whole circle)"""
    if len(run) <= 2 or _line_dev(run) <= tol:
        return ("line", run[0], run[-1])
    if len(run) >= 4:
        c, r, dev = _circle(run)
        chord = np.hypot(*(run[-1] - run[0]))
        sag = r - math.sqrt(max(r * r - chord * chord / 4, 0.0)) if chord < 2 * r else r
        # (a REAL curve: a near-straight run is never a huge-radius arc, nor an arc far flatter than its chord — a
        # straight edge plus the start of the round after it)
        if dev <= tol and sag >= 1.5 * tol and r <= 4.0 * max(chord, 1e-6):
            ang = np.unwrap(np.arctan2(run[:, 1] - c[1], run[:, 0] - c[0]))
            if abs(ang[-1] - ang[0]) < math.radians(340):
                return ("arc", run[0], run[len(run) // 2], run[-1], c, r)
    return None


def _fit_run(run, tol, out):
    """one corner-to-corner run -> PIECES [(kind "line" | "arc", its trace points)] within tol: from its start, the
    LONGEST primitive that fits (grown, then bisected back), then the next from where it ended; the boundaries then
    slid to where both neighbours fit best — the pieces end at the real line / arc changes"""
    i, n = 0, len(run)
    cuts, kinds = [0], []
    while i < n - 1:
        ll = _reach(run, i, lambda r_: len(r_) <= 2 or _line_dev(r_) <= tol)
        la = _reach(run, i, lambda r_: len(r_) < 4 or _circle_ok(r_, tol))
        # a line unless an arc clearly reaches further (an arc grown over a straight edge + the start of a round
        # passes within tol and bends the edge)
        j = la if (la > i + 3 and (la - i) > 1.5 * (ll - i)) else ll
        if j == la and j != ll:  # (an arc far flatter than its chord is a straight edge plus a round's start: the line)
            _c, r_, _d = _circle(run[i:j + 1])
            if r_ > 4.0 * float(np.hypot(*(run[j] - run[i]))):
                j = ll
        q = _one(run[i:j + 1], tol)
        kinds.append(q[0] if q else "line")
        cuts.append(j)
        i = j
    _refine(run, cuts, kinds)
    for k, kind in enumerate(kinds):
        out.append((kind, run[cuts[k]:cuts[k + 1] + 1]))


def _err(r_, kind):
    """the squared distances of a piece's points to its best line / circle"""
    if kind == "arc" and len(r_) >= 4:
        c, r, _d = _circle(r_)
        return float(np.sum((np.hypot(*(r_ - c).T) - r) ** 2))
    m = r_.mean(axis=0)
    _u, s, _vt = np.linalg.svd(r_ - m, full_matrices=False)
    return float(s[-1] ** 2) if len(s) > 1 else 0.0


def _refine(run, cuts, kinds, reach=8, sweeps=2):
    """each boundary between two pieces slid to where the two fit best: the greedy pass ends a line a little INTO
    the round after it (within tol), which shortens the arc and bends its radius"""
    for _ in range(sweeps):
        for k in range(1, len(cuts) - 1):
            lo, hi = cuts[k - 1] + 3, cuts[k + 1] - 3
            if hi <= lo:
                continue
            best, at = None, cuts[k]
            for c in range(max(lo, cuts[k] - reach), min(hi, cuts[k] + reach) + 1):
                e = _err(run[cuts[k - 1]:c + 1], kinds[k - 1]) + _err(run[c:cuts[k + 1] + 1], kinds[k])
                if best is None or e < best:
                    best, at = e, c
            cuts[k] = at


def _circle_ok(run, tol):
    """a circle passes through the run within tol (a short piece of any curve does: its arc-ness is decided after)"""
    c, r, dev = _circle(run)
    if dev > tol:
        return False
    ang = np.unwrap(np.arctan2(run[:, 1] - c[1], run[:, 0] - c[0]))
    return abs(ang[-1] - ang[0]) < math.radians(340)


def _reach(run, i, ok):
    """the furthest j (> i) with ok(run[i:j+1]): grown by doubling, then bisected"""
    n = len(run)
    lo, hi = i + 1, i + 2
    while hi <= n - 1 and ok(run[i:hi + 1]):
        lo = hi
        if hi == n - 1:
            return lo
        hi = min(n - 1, i + 2 * (hi - i))
    hi = min(hi, n - 1)
    if ok(run[i:hi + 1]):
        return hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ok(run[i:mid + 1]):
            lo = mid
        else:
            hi = mid
    return lo


def _kind(pts, tol):
    """the ONE primitive a piece's points are (a line first; an arc only as a real curve), or None"""
    q = _one(pts, tol)
    return q[0] if q else None


def _merge(pieces, tol, closed=True):
    """neighbours that ONE primitive fits within tol become one — two half arcs of one round, two collinear lines,
    a sliver arc between a line and a round — round the loop's end too (a closed chain's last piece meets its first)"""
    pieces = list(pieces)
    changed = True
    while changed and len(pieces) > 2:
        changed = False
        n = len(pieces)
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            run = np.vstack([pieces[i][1], pieces[j][1][1:]])
            kind = _kind(run, tol)
            if kind is None and "line" in (pieces[i][0], pieces[j][0]) and _line_dev(run) <= 1.25 * tol:
                kind = "line"  # (one straight edge the trace's noise split in two, or a sliver "arc" at its end)
            if kind is None:
                continue
            if j == 0:
                pieces = [(kind, run)] + pieces[1:-1]
            else:
                pieces[i:i + 2] = [(kind, run)]
            changed = True
            break
    # a piece called an arc that is no real curve (its sag under 1.5 tol: a straight edge that took in the start of a
    # round) is a LINE — a huge-radius arc there is a bent edge
    return [("line", pts) if k == "arc" and _sag(pts) < 1.5 * tol else (k, pts) for k, pts in pieces]


def _sag(pts):
    """how far the piece's fitted circle bulges from its chord (mm): a line's is ~0"""
    if len(pts) < 4:
        return 0.0
    _c, r, _d = _circle(pts)
    chord = float(np.hypot(*(pts[-1] - pts[0])))
    return r - math.sqrt(max(r * r - chord * chord / 4, 0.0)) if chord < 2 * r else r


def _geom(kind, pts):
    """a piece's least-squares geometry: ("line", centroid, unit direction) | ("arc", centre, radius)"""
    if kind == "arc" and len(pts) >= 4:
        c, r, _d = _circle(pts)
        return ("arc", c, r)
    m = pts.mean(axis=0)
    _u, _s, vt = np.linalg.svd(pts - m, full_matrices=False)
    return ("line", m, vt[0])


def _project(g, p):
    if g[0] == "arc":
        v = p - g[1]
        return g[1] + v / max(np.hypot(*v), 1e-12) * g[2]
    return g[1] + g[2] * float(np.dot(p - g[1], g[2]))


TAN_DEG = 15.0   # (a joint whose two sides turn less than this is SMOOTH in the design: made truly tangent)


def _perp(v):
    return np.array([-v[1], v[0]])


def _tangent(g, p):
    """the unit direction of primitive g at the point p (a line's direction; a circle's tangent there)"""
    if g[0] == "line":
        return g[2] / max(np.hypot(*g[2]), 1e-12)
    v = p - g[1]
    return _perp(v / max(np.hypot(*v), 1e-12))


def _equalise(geo, rel, tol=math.inf):
    """arcs whose radii are within rel of each other given one radius (their mean) — BEFORE the tangency snap, so
    the equal radii and the smooth joints both hold"""
    arcs = sorted((i for i, g in enumerate(geo) if g[0] == "arc"), key=lambda i: geo[i][2])
    group = []
    for i in arcs + [None]:
        if i is not None and (not group or geo[i][2] <= geo[group[0]][2] * (1 + rel)):
            group.append(i)
            continue
        if len(group) > 1:
            r = float(np.mean([geo[k][2] for k in group]))
            if all(abs(geo[k][2] - r) <= 1.5 * tol for k in group):   # (never pulls an arc off its trace)
                for k in group:
                    geo[k] = ("arc", geo[k][1], r)
        group = [i] if i is not None else []
    return geo


def _snap(geo, i, j, p0, tol=math.inf):
    """make the joint between primitives i and j (near p0) TANGENT by moving an arc's centre (never its radius) —
    only when the tangent point then lands NEAR the real joint (a tangent point is fixed by the geometry: two circles
    touch on the line of their centres, which can lie far round from where the pieces meet: an arc then sweeps the
    long way round) -> True when snapped"""
    keep = (geo[i], geo[j])
    got = _snap_raw(geo, i, j, p0, tol)
    if got and got != "same":
        q = _meet(geo[i], geo[j], p0, True)
        radii = [g[2] for g in (geo[i], geo[j]) if g[0] == "arc"]
        # (a real tangency lands within ~0.8 mm of the joint on a 5 mm round; the wrong one ~12 mm off a 39 mm arc)
        if np.hypot(*(q - p0)) > max(4 * tol, 0.5, 0.2 * min(radii)) if math.isfinite(tol) else False:
            geo[i], geo[j] = keep
            return False
    return got


def _snap_raw(geo, i, j, p0, tol=math.inf):
    gi, gj = geo[i], geo[j]
    if gi[0] == gj[0] == "line":
        return False
    ang = math.degrees(math.acos(min(1.0, abs(float(np.dot(_tangent(gi, p0), _tangent(gj, p0)))))))
    if ang > TAN_DEG:
        return False
    if gi[0] == "line" or gj[0] == "line":
        li, ai = (i, j) if gi[0] == "line" else (j, i)
        _t, m, d = geo[li]
        _t, c, r = geo[ai]
        nrm = _perp(d / max(np.hypot(*d), 1e-12))
        s = float(np.dot(c - m, nrm))
        move = (r if s >= 0 else -r) - s
        if abs(move) > 2 * tol:   # (the art is not smooth here: a real corner, kept)
            return False
        geo[ai] = ("arc", c + nrm * move, r)
        return True
    (_t, c1, r1), (_t2, c2, r2) = gi, gj
    dvec = c2 - c1
    dist = float(np.hypot(*dvec))
    big = max(r1, r2)
    if dist < 0.03 * big and abs(r1 - r2) < 0.03 * big:   # (two pieces of ONE circle: made exactly one)
        geo[j] = ("arc", c1.copy(), r1)
        return "same"
    if dist < 1e-9:
        return False
    target = r1 + r2 if abs(dist - (r1 + r2)) < abs(dist - abs(r1 - r2)) else abs(r1 - r2)
    if abs(target - dist) > 2 * tol:
        return False
    geo[j] = ("arc", c1 + dvec / dist * target, r2)
    return True


def _meet(gi, gj, p0, tangent):
    """the joint where primitives gi and gj meet, nearest p0: exact on BOTH (a tangent point, an intersection), else
    the point both pass nearest"""
    if tangent == "same":   # (one circle: the joint is the trace's own point on it)
        return _project(gi, p0)
    if tangent:
        if gi[0] == "line" or gj[0] == "line":
            (_t, m, d), (_t2, c, _r) = (gi, gj) if gi[0] == "line" else (gj, gi)
            u = d / max(np.hypot(*d), 1e-12)
            return m + u * float(np.dot(c - m, u))
        (_t, c1, r1), (_t2, c2, r2) = gi, gj
        u = (c2 - c1) / max(np.hypot(*(c2 - c1)), 1e-12)
        if abs(np.hypot(*(c2 - c1)) - (r1 + r2)) < 1e-6:
            return c1 + u * r1                                   # (outside each other)
        return c1 + u * r1 if r1 >= r2 else c1 - u * r1          # (one inside the other)
    pts = []
    if gi[0] == gj[0] == "line":
        d1, d2 = gi[2], gj[2]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) > 1e-9:
            w = gj[1] - gi[1]
            t = (w[0] * d2[1] - w[1] * d2[0]) / den
            pts.append(gi[1] + d1 * t)
    elif gi[0] == "line" or gj[0] == "line":
        (_t, m, d), (_t2, c, r) = (gi, gj) if gi[0] == "line" else (gj, gi)
        u = d / max(np.hypot(*d), 1e-12)
        f = m + u * float(np.dot(c - m, u))
        h2 = r * r - float(np.dot(f - c, f - c))
        if h2 >= 0:
            h = math.sqrt(h2)
            pts += [f + u * h, f - u * h]
    else:
        (_t, c1, r1), (_t2, c2, r2) = gi, gj
        dv = c2 - c1
        dd = float(np.hypot(*dv))
        if 1e-9 < dd <= r1 + r2 and dd >= abs(r1 - r2):
            a = (r1 * r1 - r2 * r2 + dd * dd) / (2 * dd)
            h = math.sqrt(max(r1 * r1 - a * a, 0.0))
            base = c1 + dv * (a / dd)
            pts += [base + _perp(dv / dd) * h, base - _perp(dv / dd) * h]
    if pts:
        q = min(pts, key=lambda p_: float(np.hypot(*(p_ - p0))))
        if np.hypot(*(q - p0)) <= 1.0 + 3 * float(np.hypot(*(_project(gi, p0) - p0))):
            return q
    return (_project(gi, p0) + _project(gj, p0)) / 2


def _arc_mid(c, r, a, b, guide):
    """the point of the circle (c, r) half way from a to b, round the way the piece's points (guide) went"""
    ta = math.atan2(a[1] - c[1], a[0] - c[0])
    tb = math.atan2(b[1] - c[1], b[0] - c[0])
    tg = math.atan2(guide[1] - c[1], guide[0] - c[0])
    ccw = (tb - ta) % (2 * math.pi)
    if (tg - ta) % (2 * math.pi) <= ccw:
        tm = ta + ccw / 2
    else:
        tm = ta - ((ta - tb) % (2 * math.pi)) / 2
    return c + r * np.array([math.cos(tm), math.sin(tm)])


def _finish(pieces, tol, closed=True, equal=0.0):
    """pieces -> the closed chain of primitives as a DESIGNER draws it: each piece's own least-squares line / circle
    (near-equal radii made one first, `equal`), every SMOOTH joint (the two sides turning < TAN_DEG) made truly tangent
    (G1: an arc's centre moved, never its radius — what lets OpenCASCADE fillet the part), every joint exactly ON both
    sides (a tangent point, a corner's intersection)"""
    pieces = _merge(pieces, tol, closed)
    n = len(pieces)
    geo = [_geom(k, pts) for k, pts in pieces]
    if equal:
        geo = _equalise(geo, equal, tol)
    near = [(pieces[i][1][-1] + pieces[(i + 1) % n][1][0]) / 2 for i in range(n)]
    fitted = [g for g in geo]   # (each primitive as its points fit it: no snap may drag it far from them)
    tangent = [_snap(geo, i, (i + 1) % n, near[i], tol) for i in range(n)]
    for _ in range(30):  # (an arc between two lines: each snap nudges the other off — repeat until both hold)
        for i in range(n):
            if tangent[i]:
                _snap(geo, i, (i + 1) % n, near[i], tol)
    for i, g in enumerate(geo):   # (an arc a chain of snaps dragged off its points: put back, its joints corners)
        if g[0] == "arc" and np.hypot(*(g[1] - fitted[i][1])) > 2 * tol:
            geo[i] = fitted[i]
            if tangent[i - 1] is not False:
                tangent[i - 1] = False
            tangent[i] = False
    joints = [_meet(geo[i], geo[(i + 1) % n], near[i], tangent[i]) for i in range(n)]
    prims = []
    for i, (kind, pts) in enumerate(pieces):
        a, b = joints[i - 1], joints[i]
        if geo[i][0] == "arc":
            _t, c, r = geo[i]
            m = _arc_mid(c, r, a, b, pts[len(pts) // 2])
            on = abs(np.hypot(*(a - c)) - r) < 1e-6 and abs(np.hypot(*(b - c)) - r) < 1e-6
            # (both ends ON its fitted circle: that exact circle — its radius kept equal to its twins'; else through
            # its ends and middle)
            c3, r3 = ([float(c[0]), float(c[1])], float(r)) if on else _circle3(a, m, b)
            if c3 is not None:
                prims.append({"type": "arc", "a": [float(v) for v in a], "m": [float(v) for v in m],
                              "b": [float(v) for v in b], "c": c3, "r": r3,
                              "g1_in": bool(tangent[i - 1]), "g1_out": bool(tangent[i])})
                continue
        prims.append({"type": "line", "a": [float(v) for v in a], "b": [float(v) for v in b],
                      "g1_in": bool(tangent[i - 1]), "g1_out": bool(tangent[i])})
    return prims


def _circle3(a, m, b):
    (x1, y1), (x2, y2), (x3, y3) = a, m, b
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return None, None
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    return [float(ux), float(uy)], float(math.hypot(x1 - ux, y1 - uy))


def _runs(p, cs):
    n = len(p)
    if not cs:
        t = _turns(p, 2)
        i0 = int(np.argmax(t))
        cs = sorted({i0, (i0 + n // 2) % n})
    out = []
    for k, c in enumerate(cs):
        nxt = cs[(k + 1) % len(cs)]
        idx = [j % n for j in range(c, (nxt if nxt > c else nxt + n) + 1)]
        out.append(p[idx])
    return out


def fit(points, tol=0.15, corner_deg=35.0, step=None, equal=0.0):
    """a closed traced outline (mm) -> a closed chain of lines and arcs within tol mm of it"""
    p = _clean(points)
    if len(p) < 3:
        raise ValueError("primfit: needs 3 or more distinct points")
    per = float(np.sum(np.hypot(*np.diff(np.vstack([p, p[:1]]), axis=0).T)))
    p = resample(p, step or max(per / 600.0, tol / 2))
    cs = corners(p, corner_deg)
    if cs:
        tries = [_runs(p, cs)]
    else:  # a loop with no corner (a rounded rectangle, an oval): it may start anywhere — keep the fewest pieces
        n = len(p)
        tries = [[np.vstack([p[s:], p[:s + 1]])] for s in sorted({int(k * n / 8) for k in range(8)})]
    best = None
    for runs in tries:
        pieces = []
        for run in runs:
            _fit_run(run, tol, pieces)
        pieces = _merge(pieces, tol)
        if best is None or len(pieces) < len(best):
            best = pieces
    return tidy(_finish(best, tol, equal=equal), tol)


def fit_mirrored(points, axis="x", at=0.0, tol=0.15, corner_deg=35.0, equal=0.0):
    """a SYMMETRIC part: the half on the +side of the mirror line (x = at for axis "x": mirrored across a vertical
    line) fitted and mirrored, so both halves are the same primitives"""
    p = _clean(points)
    k = 0 if axis == "x" else 1
    n = len(p)
    s = p[:, k] - at
    cross = [i for i in range(n) if (s[i] >= 0) != (s[(i + 1) % n] >= 0)]
    if len(cross) != 2:
        raise ValueError(f"fit_mirrored: the outline crosses the mirror line {len(cross)} times (needs 2)")

    def on_axis(i):  # (where the edge i -> i+1 meets the mirror line)
        a, b = p[i], p[(i + 1) % n]
        t = (at - a[k]) / (b[k] - a[k])
        q = a + (b - a) * t
        q[k] = at
        return q
    i0, i1 = cross
    if s[(i0 + 1) % n] < 0:  # (walk the + side: from the crossing whose next point is on it)
        i0, i1 = i1, i0
    idx = [j % n for j in range(i0 + 1, (i1 if i1 > i0 else i1 + n) + 1)]
    q = np.vstack([on_axis(i0), p[idx], on_axis(i1)])
    seg = np.hypot(*np.diff(q, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    m_ = max(8, int(cum[-1] / max(cum[-1] / 300.0, tol / 2)))
    t = np.linspace(0, cum[-1], m_ + 1)
    half = np.column_stack([np.interp(t, cum, q[:, 0]), np.interp(t, cum, q[:, 1])])
    tr = _turns(half, 2)
    inner = [i for i in range(3, len(half) - 3) if tr[i] > corner_deg and tr[i] >= tr[i - 1] and tr[i] > tr[i + 1]]
    cuts = [0] + inner + [len(half) - 1]
    side = []
    for a_, b_ in zip(cuts, cuts[1:]):
        _fit_run(half[a_:b_ + 1], tol, side)
    side = _merge(side, tol, closed=False)

    def flip(pts):
        out = pts[::-1].copy()
        out[:, k] = 2 * at - out[:, k]
        return out
    # the other half: the same pieces mirrored, in the loop's order (the mirror line's joints merge across it)
    return tidy(_finish(side + [(kind, flip(pts)) for kind, pts in reversed(side)], tol, equal=equal), tol)


def tidy(prims, tol):
    """two lines in a row that are one straight edge (the mirror line splits the top and bottom edges) become one"""
    out = [dict(q) for q in prims]
    k = 0
    while len(out) > 3 and k < len(out):
        p, q = out[k], out[(k + 1) % len(out)]
        if p["type"] == q["type"] == "line":
            a, b, c = np.array(p["a"]), np.array(p["b"]), np.array(q["b"])
            if _line_dev(np.array([a, b, c])) <= tol / 2:
                p["b"] = q["b"]
                out.pop((k + 1) % len(out))
                continue
        k += 1
    return out


def snap_radii(prims, rel=0.08):
    """arcs whose radii are within rel of each other made EQUAL (their mean): a designer draws one 5 mm round four
    times, a trace gives 4.9 / 5.0 / 5.1 / 5.4. Each arc keeps its ends; its centre moves along their bisector"""
    arcs = sorted((q for q in prims if q["type"] == "arc"), key=lambda q: q["r"])
    groups, cur = [], []
    for q in arcs:
        if cur and q["r"] > cur[0]["r"] * (1 + rel):
            groups.append(cur)
            cur = []
        cur.append(q)
    if cur:
        groups.append(cur)
    for g in groups:
        r = float(np.mean([q["r"] for q in g]))
        for q in g:
            a, b, c0, m0 = (np.array(q[k]) for k in ("a", "b", "c", "m"))
            half = np.hypot(*(b - a)) / 2
            if r <= half + 1e-9:
                continue
            mid, u = (a + b) / 2, (b - a) / max(2 * half, 1e-12)
            nrm = np.array([-u[1], u[0]])
            h = math.sqrt(r * r - half * half)
            c = mid + nrm * h if np.dot(c0 - mid, nrm) >= 0 else mid - nrm * h
            # the arc's middle: the new circle's point on the bisector nearest the old middle (the side it bulged to)
            cand = [c + nrm * r, c - nrm * r]
            m = min(cand, key=lambda v: np.hypot(*(v - m0)))
            q["c"], q["r"], q["m"] = [float(v) for v in c], r, [float(v) for v in m]
    return prims


def sample(prims, step=0.25):
    out = []
    for q in prims:
        a, b = np.array(q["a"]), np.array(q["b"])
        if q["type"] == "line":
            n = max(1, int(np.hypot(*(b - a)) / step))
            out += [a + (b - a) * t for t in np.arange(n) / n]
        else:
            c, r = np.array(q["c"]), q["r"]
            t0 = math.atan2(*(a - c)[::-1])
            tm = math.atan2(*(np.array(q["m"]) - c)[::-1])
            t1 = math.atan2(*(b - c)[::-1])
            sweep = (t1 - t0) % (2 * math.pi)  # counter-clockwise from a to b ...
            if (tm - t0) % (2 * math.pi) > sweep:  # ... unless m is not on that way round: clockwise
                sweep -= 2 * math.pi
            n = max(2, int(abs(sweep) * r / step))
            out += [c + r * np.array([math.cos(t0 + sweep * t), math.sin(t0 + sweep * t)]) for t in np.arange(n) / n]
    return np.array(out)


def report(points, prims):
    """distances between the trace and the redraw BOTH ways (mm: a primitive that runs off — an arc sweeping the long
    way round — shows from the redraw's side) and the primitive counts"""
    p = _clean(points)
    s = sample(prims, step=0.05)
    d = np.array([np.min(np.hypot(*(s - q).T)) for q in p])
    a_, b_ = p, np.roll(p, -1, axis=0)   # (the trace as SEGMENTS: a long straight run has its vertices far apart)
    ab = b_ - a_
    L2 = np.maximum((ab ** 2).sum(axis=1), 1e-12)

    def seg_dist(q):
        t = np.clip(((q - a_) * ab).sum(axis=1) / L2, 0, 1)
        return float(np.min(np.hypot(*(a_ + ab * t[:, None] - q).T)))
    back = np.array([seg_dist(q) for q in s[::4]]) if len(s) else np.zeros(1)
    d = np.concatenate([d, back])
    return {"lines": sum(q["type"] == "line" for q in prims), "arcs": sum(q["type"] == "arc" for q in prims),
            "max_mm": round(float(d.max()), 3), "mean_mm": round(float(d.mean()), 3),
            "radii_mm": sorted(round(q["r"], 2) for q in prims if q["type"] == "arc")}
