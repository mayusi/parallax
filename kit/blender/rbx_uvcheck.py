"""rbx_uvcheck.py — a baked group's UVs, CHECKED for what a density number cannot see (the owner's method lists,
2026-11-13: "UV overlap ... stretching checks"; the 3D methods audit, stage M7).

Until now a build measured how MANY texels a face gets (texel density, its spread) and nothing else: two faces
lying on one piece of the map by accident (one of them then shows the other's paint), an unwrap folded over itself
(a mirrored smear) and a texel lying long and thin over the surface (the map coarser one way than its density says)
all passed.

    runs(q, n)                     every face filled onto the map's grid, as runs of texel centres
    overlap(uv, start, total, tri, tri_poly, res, meant)
                                   the texels painted TWICE: under two faces, neither of them one the kit itself
                                   laid on another's place (`meant`: a copy on its original - a.repeat, a.mirror,
                                   a.scatter on the route that unwraps by part)
    stretch(uv_tri, pts)           how far from square a texel lies on the surface, per triangle (1 = square,
                                   2 = twice as long as wide), by the surface it covers

Which faces are a copy on its original is the BUILDER's record, never read off the map: two faces on the very same
place look alike whether the kit stacked them or an unwrap laid a part's front on its back (a leg's 1,329 faces
piled exactly, none of them a copy).

numpy only: arrays in, facts out (the builder reads its mesh into them; the tests write them by hand).
"""

import numpy as np

FLAT = 1e-14           # a UV triangle with less area than this covers no texel (a crushed face: stretch's business)
STRETCHED = 2.0        # a texel twice as long as wide on the surface: the map is twice as coarse that way
# The bars, from built groups measured as they are (2026-11-13, read-only from their .blend; the numbers and the
# models are on board card keak and in the parallax-3d skill's reference/06): a clean map is the rule, the offenders
# are few (15 of 141 groups over the overlap bar, none over 1.2%). ERRORS since 2026-11-17 (the owner's limitations
# review: "promote all 3 to blocking errors"): a build over a bar fails, with the place to fix.
OVERLAP_BAR = 0.001    # more than 0.1% of the map's painted texels under two faces is said
STRETCH_BAR = 0.05     # more than 5% of the surface under texels over STRETCHED x longer than wide is said
CRUSHED_BAR = 0.005    # more than 0.5% of the surface with no room on the map at all is said


def _area2(q):
    """(n, 3, 2) -> (n,) twice the signed area"""
    e1, e2 = q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]
    return e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]


def _expand(start, count):
    """ranges [start, start + count) -> (which range each element is from, the element)"""
    total = int(count.sum())
    if not total:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    which = np.repeat(np.arange(len(count)), count)
    return which, np.repeat(start, count) + np.arange(total) - np.repeat(np.cumsum(count) - count, count)


def runs(q, n, rows=None):
    """triangles (T, 3, 2) on the map -> (triangle, row, first column, end column) of every run of texel
    CENTRES a triangle covers on an n x n grid (a scanline fill: the centres c + 0.5 in [left, right) of the row
    r + 0.5 in [bottom, top)). A triangle thinner than a texel may cover none: it shows no paint either."""
    p = np.asarray(q, np.float64) * n
    p = np.where(np.isfinite(p), p, 0.0)
    x, y = p[:, :, 0], p[:, :, 1]
    r0 = np.clip(np.ceil(y.min(axis=1) - 0.5), 0, n).astype(np.int64)
    r1 = np.clip(np.ceil(y.max(axis=1) - 0.5), 0, n).astype(np.int64)
    if rows is not None:   # (only the rows of this window: a band of overlap()'s)
        r0, r1 = np.maximum(r0, int(rows[0])), np.minimum(r1, int(rows[1]))
    which, row = _expand(r0, np.maximum(r1 - r0, 0))
    yc = row + 0.5
    left, right = np.full(len(which), np.inf), np.full(len(which), -np.inf)
    for i in range(3):                                                     # the edges this row's line crosses
        ya, yb, xa, xb = y[which, i], y[which, (i + 1) % 3], x[which, i], x[which, (i + 1) % 3]
        run = yb - ya
        cross = (np.minimum(ya, yb) <= yc) & (yc <= np.maximum(ya, yb)) & (run != 0)
        xi = xa + (yc - ya) / np.where(run != 0, run, 1.0) * (xb - xa)
        left = np.where(cross, np.minimum(left, xi), left)
        right = np.where(cross, np.maximum(right, xi), right)
    ok = right > left
    which, row = which[ok], row[ok]
    c0 = np.clip(np.ceil(left[ok] - 0.5), 0, n).astype(np.int64)
    c1 = np.clip(np.ceil(right[ok] - 0.5), 0, n).astype(np.int64)
    ok = c1 > c0
    return which[ok], row[ok], c0[ok], c1[ok]


BAND = 256   # rows of the grid counted at a time (a 4096 grid whole: ~67 MB an array, several at once; a band: ~1 MB)


def overlap(uv, start, total, tri, tri_poly, res=2048, meant=None, band=BAND):
    """a mesh's UV map -> what lies on what BY ACCIDENT, counted on the map's own grid: every face is filled
    onto a res x res grid of texel centres, and a centre under two faces is painted twice (one of the two faces
    shows the other's paint there). Counted where that is at least three grid texels wide each way, so the
    number is the patch's INSIDE: a strip two texels wide counts nothing, a patch eight wide three quarters of
    itself. Counting on the grid costs what the map costs, whatever the faces look like (a counter top of long
    slivers cost minutes when its triangles were met pair by pair).
    uv (L, 2): every loop's place; start / total (P,): each polygon's loops; tri (T, 3): each triangle's loops;
    tri_poly (T,): its polygon; res: the grid (twice the map's side sees a texel and a half); meant (P,) bool:
    the faces the BUILDER laid on another face's place - they are left off the grid (their original stands for
    them). Nothing else is taken for a copy: two faces on the very same place count like any other two.
    -> {"share": the twice-painted share of the map's painted texels, "texels": how many, "polys": the faces
        that have some, "stacked": the faces left off as copies, "at": [(u, v, texels)] the three faces with the
        most, "mask": bool per polygon}"""
    uv = np.asarray(uv, np.float64).reshape(-1, 2)
    start, total = np.asarray(start, np.int64), np.asarray(total, np.int64)
    tri, tri_poly = np.asarray(tri, np.int64).reshape(-1, 3), np.asarray(tri_poly, np.int64)
    n = int(res)
    off = np.zeros(len(start), bool) if meant is None else np.asarray(meant, bool)
    live = np.nonzero(~off[tri_poly])[0]
    mask = np.zeros(len(start), bool)
    out = {"share": 0.0, "texels": 0, "polys": 0, "stacked": int(off.sum()), "at": [], "mask": mask}
    if len(live) < 2:
        return out
    q = uv[tri[live]]
    w = n + 1
    # counted BAND rows at a time (each band with a row either side: "wide" asks a texel's eight neighbours), each
    # band from only the triangles that reach it - the same numbers as the whole grid at a fraction of its memory
    # (card keak: a 4096 map's grid)
    yv = np.where(np.isfinite(q[:, :, 1]), q[:, :, 1], 0.0) * n
    t_lo = np.clip(np.ceil(yv.min(axis=1) - 0.5), 0, n).astype(np.int64)
    t_hi = np.clip(np.ceil(yv.max(axis=1) - 0.5), 0, n).astype(np.int64)
    per_poly = np.zeros(len(start), np.float64)
    poly_of = tri_poly[live]
    n_twice = 0
    painted = 0
    for b0 in range(0, n, int(band)):
        b1 = min(n, b0 + int(band))
        r0, r1 = max(0, b0 - 1), min(n, b1 + 1)                      # (the band and a row round it)
        reach = np.nonzero((t_hi > r0) & (t_lo < r1))[0]
        if not len(reach):
            continue
        which, row, c0, c1 = runs(q[reach], n, rows=(r0, r1))
        if not len(which):
            continue
        rr = row - r0
        h = r1 - r0
        count = np.bincount(rr * w + c0, minlength=h * w).astype(np.int32)
        count -= np.bincount(rr * w + c1, minlength=h * w).astype(np.int32)
        count = np.cumsum(count.reshape(h, w), axis=1, dtype=np.int32)[:, :n]
        twice = count >= 2
        across = twice.copy()
        across[:, 1:] &= twice[:, :-1]
        across[:, :-1] &= twice[:, 1:]
        wide = across.copy()
        wide[1:] &= across[:-1]
        wide[:-1] &= across[1:]
        if r0 == 0:
            wide[0] = False
        if r1 == n:
            wide[-1] = False
        wide[:, 0] = wide[:, -1] = False
        own = slice(b0 - r0, b1 - r0)                                 # (the band's own rows: each counted once)
        n_twice += int(wide[own].sum())
        painted += int((count[own] >= 1).sum())
        upto = np.zeros((h, w), np.int32)
        np.cumsum(wide, axis=1, dtype=np.int32, out=upto[:, 1:])
        mine = (row >= b0) & (row < b1)
        hit = (upto[rr[mine], c1[mine]] - upto[rr[mine], c0[mine]]).astype(np.float64)
        per_poly += np.bincount(poly_of[reach[which[mine]]], weights=hit, minlength=len(start))
    if not n_twice:
        return out
    mask |= per_poly > 0
    out["share"] = n_twice / max(painted, 1)
    out["texels"], out["polys"] = n_twice, int(mask.sum())
    for p in np.argsort(-per_poly)[:3]:
        if per_poly[p] > 0:
            c = uv[start[p]:start[p] + total[p]].mean(axis=0)
            out["at"].append((round(float(c[0]), 3), round(float(c[1]), 3), int(per_poly[p])))
    return out


def stretch(uv_tri, pts, limit=STRETCHED):
    """how far from SQUARE a texel lies on the surface. uv_tri (T, 3, 2), pts (T, 3, 3) the same corners in
    space -> {"p50", "p90", "max": the ratio of a texel's long side to its short one (by surface), "share": the
    surface whose texels are longer than limit x their width, "crushed": the surface with no room on the map at
    all (counted there, not in the share), "at": [(u, v, ratio)] the worst five, "ratio": per triangle (inf
    where crushed)}. A triangle with no surface counts for nothing."""
    q = np.asarray(uv_tri, np.float64).reshape(-1, 3, 2)
    p = np.asarray(pts, np.float64).reshape(-1, 3, 3)
    d1, d2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    w = np.linalg.norm(np.cross(d1, d2), axis=1) / 2                       # the surface each stands for
    e1, e2 = q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    real = w > 1e-14
    flat = real & ~(np.abs(det) > 2 * FLAT)
    good = real & ~flat
    ratio = np.full(len(q), np.inf)
    ratio[~real] = 1.0
    if good.any():
        inv = 1.0 / det[good]
        # the map's two directions carried onto the surface: J = [d1 d2] . inv([e1 e2])
        ju = (d1[good] * e2[good, 1][:, None] - d2[good] * e1[good, 1][:, None]) * inv[:, None]
        jv = (d2[good] * e1[good, 0][:, None] - d1[good] * e2[good, 0][:, None]) * inv[:, None]
        a, b, c = (ju * ju).sum(axis=1), (ju * jv).sum(axis=1), (jv * jv).sum(axis=1)
        mid, off = (a + c) / 2, np.sqrt(((a - c) / 2) ** 2 + b * b)
        ratio[good] = np.sqrt((mid + off) / np.maximum(mid - off, 1e-30))
    total = float(w[real].sum())
    out = {"p50": 1.0, "p90": 1.0, "max": 1.0, "share": 0.0, "crushed": 0.0, "at": [], "ratio": ratio}
    if total <= 0:
        return out
    order = np.argsort(ratio[good])
    cum = np.cumsum(w[good][order]) / max(float(w[good].sum()), 1e-30)
    if len(order):
        r = ratio[good][order]
        out["p50"] = round(float(r[min(np.searchsorted(cum, 0.5), len(r) - 1)]), 3)
        out["p90"] = round(float(r[min(np.searchsorted(cum, 0.9), len(r) - 1)]), 3)
        out["max"] = round(float(r[-1]), 3)
    out["crushed"] = round(float(w[flat].sum() / total), 5)
    out["share"] = round(float(w[good & (ratio > limit)].sum() / total), 5)
    worst = np.nonzero(good & (ratio > limit))[0]
    for j in worst[np.argsort(-(ratio[worst] * w[worst]))[:5]]:
        c = q[j].mean(axis=0)
        out["at"].append((round(float(c[0]), 3), round(float(c[1]), 3), round(float(ratio[j]), 2)))
    return out
