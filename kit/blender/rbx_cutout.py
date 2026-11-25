"""rbx_cutout.py — a part's outline CUT BY ITS MAP (the owner's method lists, 2026-11-13: "alpha clipping",
"opacity"; the 3D methods audit, stage S1, second half): a leaf's edge, a grille's bars, torn paper, a chain-link
fence - shapes far too fine to model - are holes in the colour map's alpha, which Roblox cuts out of the mesh
(SurfaceAppearance.AlphaMode = Transparency with the part's own Transparency 0: a hard cut, sorted by depth).

    texels(uv_tri, pts, n)          the surface point under every texel centre the part's faces cover on an
                                    n x n map -> (row, column, point (K, 3))
    by_rule(points, keep)           keep(point) -> True where the surface stays
    by_picture(points, alpha, frame)   a picture laid flat on the part: where the picture is solid, it stays
    frame_of(points)                the flat frame a sheet's picture is laid in: its own plane, upright
    alpha_map(n, rows, cols, kept)  the map's alpha: 255 everywhere, 0 at the texels cut away
    into_margin(alpha, covered, reach)   ... carried into the margin round the islands (no line when filtered)
    share(kept)                     how much of the part's surface is cut away

numpy only.
"""

import numpy as np

import rbx_uvcheck


def texels(uv_tri, pts, n):
    """triangles on the map (T, 3, 2) and in space (T, 3, 3) -> (row, column, point): every texel centre a
    triangle covers on an n x n map, with the point of the surface under it (the same scanline fill the map's
    own check uses, each centre carried into space by its place in the triangle)"""
    q = np.asarray(uv_tri, np.float64).reshape(-1, 3, 2)
    p = np.asarray(pts, np.float64).reshape(-1, 3, 3)
    which, row, c0, c1 = rbx_uvcheck.runs(q, n)
    if not len(which):
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros((0, 3))
    run, col = rbx_uvcheck._expand(c0, c1 - c0)
    tri, rows = which[run], row[run]
    x, y = (col + 0.5) / n, (rows + 0.5) / n
    a, b, c = q[tri, 0], q[tri, 1], q[tri, 2]
    det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    det = np.where(np.abs(det) < 1e-30, 1e-30, det)
    l1 = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / det
    l2 = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / det
    l3 = 1.0 - l1 - l2
    point = l1[:, None] * p[tri, 0] + l2[:, None] * p[tri, 1] + l3[:, None] * p[tri, 2]
    return rows, col, point


def by_rule(points, keep):
    """keep(point (x, y, z)) -> truthy where the surface STAYS. -> bool per point"""
    return np.fromiter((bool(keep(tuple(float(c) for c in p))) for p in points), bool, len(points))


def frame_of(points):
    """the flat frame a sheet's picture is laid in -> (origin, across, up, width, height): the sheet's own plane
    (the direction its points spread least in is its facing), the picture UPRIGHT in it - its up the model's up
    (+Y) as far as the plane allows (a sheet lying flat: +Z), its bottom left at the origin. A part that is no
    sheet still gets a frame from its thinnest direction: say frame= yourself there."""
    p = np.asarray(points, np.float64).reshape(-1, 3)
    mid = p.mean(axis=0)
    _u, _s, vt = np.linalg.svd(p - mid, full_matrices=False)
    facing = vt[2]
    world_up = np.array([0.0, 1.0, 0.0]) if abs(facing[1]) < 0.9 else np.array([0.0, 0.0, 1.0])
    up = world_up - facing * float(world_up @ facing)
    up /= np.linalg.norm(up)
    # the picture reads RIGHT WAY ROUND from where the model is looked at (the kit's views: its front from -Z,
    # where the model's +X is on the viewer's left; its side from +X; a sheet lying flat from above) - lettering
    # is never mirrored there, whichever way the sheet's faces are wound
    k = int(np.argmax(np.abs(facing)))
    forward = np.array([(-1.0, 0, 0), (0, -1.0, 0), (0, 0, 1.0)][k])     # the way that viewer looks
    across = np.cross(forward, up)
    across /= np.linalg.norm(across)
    a, b = (p - mid) @ across, (p - mid) @ up
    origin = mid + across * a.min() + up * b.min()
    return origin, across, up, float(a.max() - a.min()), float(b.max() - b.min())


def by_picture(points, alpha, frame, level=0.5):
    """a picture laid flat on the part -> bool per point (True where it is solid). alpha (H, W) 0..1, row 0 its
    TOP; frame: frame_of()'s - the picture fills width x height from the origin, its bottom along `across`.
    A point outside the picture is cut away."""
    p = np.asarray(points, np.float64).reshape(-1, 3)
    alpha = np.asarray(alpha, np.float64)
    origin, across, up, width, height = frame
    h, w = alpha.shape
    u = (p - origin) @ np.asarray(across) / max(width, 1e-12)
    v = (p - origin) @ np.asarray(up) / max(height, 1e-12)
    inside = (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)
    col = np.clip((u * w).astype(np.int64), 0, w - 1)
    row = np.clip(((1.0 - v) * h).astype(np.int64), 0, h - 1)
    return inside & (alpha[row, col] >= level)


def alpha_map(n, rows, cols, kept):
    """-> (n, n) uint8, row 0 the map's v = 0: 255 everywhere, 0 at the texels cut away (a texel no face of the
    part covers keeps 255: the margin round an island, the other parts of the group)"""
    out = np.full((n, n), 255, np.uint8)
    out[np.asarray(rows)[~np.asarray(kept, bool)], np.asarray(cols)[~np.asarray(kept, bool)]] = 0
    return out


def into_margin(alpha, covered, reach):
    """the cut carried into the MARGIN round the islands: a texel no face covers takes the alpha of the covered
    texel it lies beside, `reach` texels deep (the way a bake pads its colour). Left at 255, the margin bleeds
    into the cut texels along an island's border when the map is filtered or shrunk - a faint line round the
    part, the ghost of the square round a round sign. alpha (n, n) uint8, covered (n, n) bool -> (n, n) uint8"""
    out, known = np.asarray(alpha, np.uint8).copy(), np.asarray(covered, bool).copy()
    for _ in range(int(reach)):
        grown = np.zeros_like(known)
        least = np.full(out.shape, 255, np.uint8)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src_k = np.zeros_like(known)
            src_a = np.full(out.shape, 255, np.uint8)
            ys = slice(max(dy, 0), out.shape[0] + min(dy, 0))
            yd = slice(max(-dy, 0), out.shape[0] + min(-dy, 0))
            xs = slice(max(dx, 0), out.shape[1] + min(dx, 0))
            xd = slice(max(-dx, 0), out.shape[1] + min(-dx, 0))
            src_k[yd, xd] = known[ys, xs]
            src_a[yd, xd] = out[ys, xs]
            grown |= src_k
            least = np.where(src_k, np.minimum(least, src_a), least)
        new = grown & ~known
        if not new.any():
            break
        out[new] = least[new]
        known |= new
    return out


def share(kept):
    """how much of the part's covered map is cut away, 0..1"""
    kept = np.asarray(kept, bool)
    return float((~kept).mean()) if len(kept) else 0.0


# SEE-THROUGH BY DEGREES (a.fade; the owner's method lists: transparency). A cut is all or nothing; a FADE gives
# every point how solid it is, 0..1 - a pane clear at its foot and frosted at its top, smoke's edge, a ghost.

def grade_by_rule(points, keep):
    """keep(point (x, y, z)) -> how SOLID the surface is there: a number 0..1 (True / False are 1 / 0).
    -> float per point, held to 0..1"""
    got = np.fromiter((float(keep(tuple(float(c) for c in p))) for p in points), float, len(points))
    return np.clip(np.nan_to_num(got, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)


def grade_by_picture(points, alpha, frame):
    """a picture laid flat on the part -> how solid each point is: the picture's own value there (its alpha, or
    how dark it is), 0 outside it. alpha (H, W) 0..1, row 0 its TOP; frame: frame_of()'s."""
    p = np.asarray(points, np.float64).reshape(-1, 3)
    alpha = np.asarray(alpha, np.float64)
    origin, across, up, width, height = frame
    h, w = alpha.shape
    u = (p - origin) @ np.asarray(across) / max(width, 1e-12)
    v = (p - origin) @ np.asarray(up) / max(height, 1e-12)
    inside = (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)
    col = np.clip((u * w).astype(np.int64), 0, w - 1)
    row = np.clip(((1.0 - v) * h).astype(np.int64), 0, h - 1)
    return np.where(inside, np.clip(alpha[row, col], 0.0, 1.0), 0.0)


def alpha_graded(n, rows, cols, solid):
    """-> (n, n) uint8, row 0 the map's v = 0: 255 everywhere, each covered texel its own share of 255"""
    out = np.full((n, n), 255, np.uint8)
    out[np.asarray(rows), np.asarray(cols)] = np.round(np.asarray(solid, float) * 255.0).astype(np.uint8)
    return out


def clear(solid):
    """how see-through a faded part is over all: 0 = solid everywhere, 1 = nothing left of it"""
    solid = np.asarray(solid, float)
    return float(1.0 - solid.mean()) if len(solid) else 0.0


def fade_kind(solid):
    """what a fade amounts to -> "fade" (three degrees or more), "cut" (only clear and solid: a.cutout does that
    with a hard edge), "even" (one degree everywhere: that is a part's own transparency) or "steps" (two degrees,
    neither clear nor solid - a fade, coarse)"""
    solid = np.asarray(solid, float)
    levels = np.unique(np.round(solid * 255.0)) if len(solid) else np.zeros(0)
    if len(levels) >= 3:
        return "fade"
    if len(levels) <= 1:
        return "even"
    return "cut" if levels[0] == 0 and levels[-1] == 255 else "steps"


def grades(solid):
    """how many different degrees a fade holds (of 255) - one or two is a cut, not a fade"""
    solid = np.asarray(solid, float)
    return int(len(np.unique(np.round(solid * 255.0)))) if len(solid) else 0
