"""curve.py - a smooth line THROUGH typed points, the Python twin of kit/lib/worldcurve.luau (the owner's method list,
2026-11-13: "Spline-based rivers"; the compiler's roads, fences and rows use the Luau one).

A centripetal Catmull-Rom spline (Barry and Goldman's form): it passes through every typed point and makes no loop or
cusp inside a span. Handed on as a polyline, cut so no joint turns more than `max_turn` degrees and no piece is longer
than `step` studs - never closer than `least` to the last cut or to a typed point. Both files are held to one table of
cases: kit/test/fixtures/curve_cases.json (kit/test/python/test_world_curve.py, kit/test/spec/worldcurve.spec.luau).
"""

import math

DEFAULTS = {"step": 12.0, "max_turn": 6.0, "least": 1.0, "fine": 64}
FLOOR = {"step": 0.5, "least": 0.25, "fine": 1024}  # (what an option may be asked down to)


def _number(v):
    """an option typed as a positive number (True is no number: Python would read it as 1)"""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def _dist(a, b):
    n = max(len(a), len(b))
    return math.sqrt(sum(((b[i] if i < len(b) else 0.0) - (a[i] if i < len(a) else 0.0)) ** 2 for i in range(n)))


def _lerp(a, b, wa, wb):
    return [a[i] * wa + (b[i] if i < len(b) else 0.0) * wb for i in range(len(a))]


def distinct(points):
    """the typed points with repeats dropped"""
    out = []
    for p in points:
        if not out or _dist(out[-1], p) > 1e-6:
            out.append(list(p))
    return out


def span(p0, p1, p2, p3, u):
    """one span p1 -> p2 of the centripetal spline through p0 p1 p2 p3, at u in 0..1"""
    t0 = 0.0
    t1 = t0 + math.sqrt(_dist(p0, p1))
    t2 = t1 + math.sqrt(_dist(p1, p2))
    t3 = t2 + math.sqrt(_dist(p2, p3))
    t = t1 + (t2 - t1) * u
    a1 = _lerp(p0, p1, (t1 - t) / (t1 - t0), (t - t0) / (t1 - t0))
    a2 = _lerp(p1, p2, (t2 - t) / (t2 - t1), (t - t1) / (t2 - t1))
    a3 = _lerp(p2, p3, (t3 - t) / (t3 - t2), (t - t2) / (t3 - t2))
    b1 = _lerp(a1, a2, (t2 - t) / (t2 - t0), (t - t0) / (t2 - t0))
    b2 = _lerp(a2, a3, (t3 - t) / (t3 - t1), (t - t1) / (t3 - t1))
    return _lerp(b1, b2, (t2 - t) / (t2 - t1), (t - t1) / (t2 - t1))


def turn(a, b, c):
    """the angle (degrees) between the directions a -> b and b -> c"""
    la, lb = _dist(a, b), _dist(b, c)
    if la < 1e-9 or lb < 1e-9:
        return 0.0
    n = max(len(a), len(b), len(c))
    g = lambda p, i: p[i] if i < len(p) else 0.0  # noqa: E731
    dot = sum((g(b, i) - g(a, i)) * (g(c, i) - g(b, i)) for i in range(n))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / (la * lb)))))


def sharpest(points):
    """the sharpest corner of a line of points, in degrees (0 = straight)"""
    pts = distinct(points)
    return max([turn(pts[i - 1], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)] or [0.0])


def length(points):
    return sum(_dist(points[i - 1], points[i]) for i in range(1, len(points)))


def through(points, step=None, max_turn=None, least=None, closed=False):
    """the smooth line through `points` as a polyline: every typed point is on it, in order"""
    step = step if _number(step) else DEFAULTS["step"]
    max_turn = max_turn if _number(max_turn) else DEFAULTS["max_turn"]
    least = least if _number(least) else DEFAULTS["least"]
    step = max(step, FLOOR["step"])
    least = max(FLOOR["least"], min(least, step / 2))  # (a least longer than the step would overrule it)
    pts = distinct(points)
    if closed and len(pts) > 2 and _dist(pts[0], pts[-1]) <= 1e-6:
        pts.pop()
    n = len(pts)
    if n < 3:
        return pts

    def at(i):  # (0-based)
        if closed:
            return pts[i % n]
        if i < 0:
            return _lerp(pts[0], pts[1], 2.0, -1.0)
        if i > n - 1:
            return _lerp(pts[n - 1], pts[n - 2], 2.0, -1.0)
        return pts[i]

    out = [pts[0]]
    for i in range(n if closed else n - 1):
        p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
        fine = max(DEFAULTS["fine"], min(FLOOR["fine"], math.ceil(_dist(p1, p2) / (least / 2))))
        samples = [span(p0, p1, p2, p3, k / fine) for k in range(fine + 1)]
        total = length(samples)
        run = turned = walked = 0.0
        for k in range(1, fine):
            d = _dist(samples[k - 1], samples[k])
            run += d
            walked += d
            turned += turn(samples[k - 1], samples[k], samples[k + 1])
            due_turn = turned >= max_turn * 0.75
            # (a cut may not fall within `least` of the span's end, so the last piece can run `least` over: cut early)
            due_run = run + _dist(samples[k], samples[k + 1]) > max(step - least, least)
            if (due_turn or due_run) and run >= least and total - walked >= least:
                out.append(samples[k])
                run = turned = 0.0
        if not (closed and i == n - 1):
            out.append(p2)
    if closed:
        out.append(pts[0])
    return out
