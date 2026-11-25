"""A SURFACE DRAWN BY CONTROL POINTS (the owner's method lists, 2026-11-13: "NURBS"; the 3D methods audit, stage K:
"NURBS (OpenCASCADE lofts are NURBS faces; no control-point surface)").

Some shapes are neither turned nor extruded nor lofted through sections: a car's wing, a saddle, a hull's flare,
a leaf's cup. A modeller makes them from a NET of control points - a grid of points in space the surface is pulled
toward, smooth everywhere, passing through the net's four corners and along its four edges' own curves. This is
that surface: a clamped B-spline over the net (a NURBS with every weight 1), evaluated to a grid of points the
builder turns into a mesh with a wall.
Pure numpy; no Blender."""

import numpy as np


def knots(n, degree):
    """the clamped, evenly spaced knot vector of n control points -> (n + degree + 1,) from 0 to 1 (the curve
    starts ON the first point and ends ON the last)"""
    inner = max(n - degree - 1, 0)
    mid = np.linspace(0.0, 1.0, inner + 2)[1:-1]
    return np.concatenate([np.zeros(degree + 1), mid, np.ones(degree + 1)])


def basis(n, degree, t):
    """every control point's pull at parameters t -> (len(t), n): each row sums to 1 (Cox - de Boor)"""
    t = np.atleast_1d(np.asarray(t, float))
    k = knots(n, degree)
    out = np.zeros((len(t), n + degree))
    for i in range(n + degree):
        out[:, i] = ((t >= k[i]) & (t < k[i + 1])).astype(float) if i + 1 < len(k) else 0.0
    # (the very end belongs to the last span that has any width)
    last = max(i for i in range(n + degree) if k[i] < k[i + 1])
    out[t >= 1.0, :] = 0.0
    out[t >= 1.0, last] = 1.0
    for d in range(1, degree + 1):
        nxt = np.zeros((len(t), n + degree - d))
        for i in range(n + degree - d):
            a = k[i + d] - k[i]
            b = k[i + d + 1] - k[i + 1]
            left = (t - k[i]) / a * out[:, i] if a > 0 else 0.0
            right = (k[i + d + 1] - t) / b * out[:, i + 1] if b > 0 else 0.0
            nxt[:, i] = left + right
        out = nxt
    return out[:, :n]


def surface(net, steps_u=16, steps_v=16, degree=3):
    """the surface a control net draws -> (steps_v + 1, steps_u + 1, 3). net: (rows, columns, 3) control points
    (2 x 2 at least); degree is held to one less than the points along each way (two points draw a straight
    line, three a parabola)."""
    net = np.asarray(net, float)
    if net.ndim != 3 or net.shape[2] != 3 or min(net.shape[:2]) < 2:
        raise ValueError("surface: a net is rows of points (x, y, z) - 2 rows and 2 columns at least")
    if not np.isfinite(net).all():
        raise ValueError("surface: a point of the net is not a number")
    if int(degree) < 1:
        raise ValueError(f"surface: degree={degree!r} - 1 (straight between the points) or more")
    rows, cols = net.shape[:2]
    bu = basis(cols, min(int(degree), cols - 1), np.linspace(0.0, 1.0, int(steps_u) + 1))
    bv = basis(rows, min(int(degree), rows - 1), np.linspace(0.0, 1.0, int(steps_v) + 1))
    return np.einsum("vr,uc,rcx->vux", bv, bu, net)


def normals(grid, joins=None):
    """the surface's own facing at every point of its grid -> (V, U, 3) unit vectors (from the grid's neighbours;
    the way rows x columns turn: reverse the net's rows to face the other way). joins (`seams`): a way closed into a
    RING reads its neighbours across the seam (both edges then face alike and weld); a row gathered into a POLE
    faces the mean of the row beside it (a pole has no way along it: its facing was nothing, its wall no thickness -
    card upjv)"""
    g = np.asarray(grid, float)
    j = joins or {}
    if j.get("ring_u"):   # (the seam's column is the first one again: neighbours read round the ring)
        e = np.concatenate([g[:, -2:-1], g, g[:, 1:2]], axis=1)
        du = (e[:, 2:] - e[:, :-2]) / 2.0
    else:
        du = np.gradient(g, axis=1)
    if j.get("ring_v"):
        e = np.concatenate([g[-2:-1], g, g[1:2]], axis=0)
        dv = (e[2:] - e[:-2]) / 2.0
    else:
        dv = np.gradient(g, axis=0)
    n = np.cross(du, dv)
    length = np.linalg.norm(n, axis=2, keepdims=True)
    n = n / np.maximum(length, 1e-30)
    for key, take, beside in (("pole_v0", (0, slice(None)), (1, slice(None))),
                              ("pole_v1", (-1, slice(None)), (-2, slice(None))),
                              ("pole_u0", (slice(None), 0), (slice(None), 1)),
                              ("pole_u1", (slice(None), -1), (slice(None), -2))):
        if j.get(key):
            m = n[beside].sum(axis=0)
            n[take] = m / max(float(np.linalg.norm(m)), 1e-30)
    return n


def seams(grid, tol=1e-6):
    """how a grid's edges JOIN -> {ring_u, ring_v: its first and last column (row) are one, pole_v0 / pole_v1 /
    pole_u0 / pole_u1: that edge row (column) is gathered into one point}, each True / False (within `tol` of the
    grid's size)"""
    g = np.asarray(grid, float)
    bar = tol * max(float(np.ptp(g.reshape(-1, 3), axis=0).max()), 1e-30)
    same = lambda a, b: float(np.abs(a - b).max()) <= bar   # noqa: E731
    point = lambda r: float(np.ptp(r, axis=0).max()) <= bar  # noqa: E731
    return {"ring_u": same(g[:, 0], g[:, -1]), "ring_v": same(g[0], g[-1]),
            "pole_v0": point(g[0]), "pole_v1": point(g[-1]), "pole_u0": point(g[:, 0]), "pole_u1": point(g[:, -1])}


def cells(grid):
    """each cell's own facing, not yet a unit (its length is twice the cell's area) -> (V - 1, U - 1, 3): its two
    diagonals crossed, turned the way `normals` turns"""
    g = np.asarray(grid, float)
    return np.cross(g[1:, 1:] - g[:-1, :-1], g[1:, :-1] - g[:-1, 1:]) * -1.0


def _against(c, axis, bar):
    """pairs of cells along one way whose facings turn against each other (past 120 degrees): neighbours, and the
    two either side of one cell (the review: a fold lying exactly ON a row of points, or inside one cell, left
    that cell facing neither way between two that faced opposite ways, and nothing was compared)"""
    size = np.linalg.norm(c, axis=2)
    unit = c / np.maximum(size, 1e-30)[..., None]
    live = size > bar
    def take(a, lo, hi):
        return a[:, lo:hi] if axis == 1 else a[lo:hi, :]
    n = c.shape[axis]
    near = ((take(unit, 0, n - 1) * take(unit, 1, n)).sum(axis=2) < -0.5) & take(live, 0, n - 1) & take(live, 1, n)
    hits, pairs = int(near.sum()), near.size
    if n > 2:
        far = ((take(unit, 0, n - 2) * take(unit, 2, n)).sum(axis=2) < -0.5) & take(live, 0, n - 2)             & take(live, 2, n)
        hits += int(far.sum())
    return hits, pairs


def folded(grid):
    """a net that folds its surface over itself: the share of neighbouring cells whose facings turn against each
    other (a smooth surface has none)"""
    c = cells(grid)
    size = np.linalg.norm(c, axis=2)
    bar = 1e-6 * float(np.median(size)) if size.size else 0.0
    a, na = _against(c, 1, bar)
    b, nb = _against(c, 0, bar)
    return float((a + b) / max(na + nb, 1))


def net_folded(net, degree=3, fine=64):
    """does a NET fold its surface? measured on a grid fine enough (64 x 64 at least) that only a fold turns the
    facing past 120 degrees within two cells - a tube most of the way round, drawn in three steps, does not"""
    return folded(surface(net, int(fine), int(fine), degree))


def crossed(front, back):
    """a wall thicker than its surface's tightest bend: the share of the BACK skin's cells that face against the
    front cell they lie behind (the back, pushed in further than the bend's radius, has turned inside out)"""
    f, b = cells(front), cells(back)
    live = (np.linalg.norm(f, axis=2) > 0) & (np.linalg.norm(b, axis=2) > 0)
    return float((((f * b).sum(axis=2) < 0) & live).sum() / max(live.size, 1))


def area(grid):
    """the surface's area (its cells', each as its two diagonals crossed)"""
    return float(np.linalg.norm(cells(grid), axis=2).sum() / 2.0)
