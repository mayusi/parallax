"""rbx_uvpack.py - PACK UV ISLANDS BY THEIR REAL SHAPE (the 3D studio route: tighter packing, 2026-11-12).

Why: half of every map the kit baked was empty. Measured on its own built models, the faces of a mesh group cover a
median 0.50 of their map (246 groups, their manifests; 0.55 over the 32 groups of 15 models opened for this). The
pads between islands are not the loss: with every island in its own outline plus half a pad, the same islands would
cover a median 0.93. Nor is a setting: Blender's packer by exact shape gives the same cover with any turn as with
quarter turns (a median 0.001 apart), by boxes a little less. The loss is the PLACING: islands set down in rows,
the holes between the big ones left empty. Published numbers agree: Blender's automatic route covers 0.43 to 0.55,
a packer that places by bitmap (xatlas) 0.56 to 0.67 (PartUV, arXiv 2511.16659, table 6).

What this does: a bitmap packer in plain numpy (Blender's Python has nothing else).
  1. every island is turned onto its smallest bounding rectangle;
  2. at one common scale every island is drawn on a grid CONSERVATIVELY (every cell a triangle touches, row band by
     row band - no sampling) and grown by half a pad;
  3. the largest islands are placed by their exact shape at the first free place from the bottom left (the grid
     against the island as one correlation), turned four ways; the rest are dropped as boxes, largest first, into
     whatever is still free - the holes of a ring, the notch of an L, the gaps beside a curve;
  4. the scale is searched: the largest at which everything still fits the square.
Islands are turned and scaled by ONE factor - never mirrored, never stretched: the texel density stays as even as
the unwrap made it.

Since 2026-11-13 it is the default unwrap's packer, not a second opinion: Blender's packer by exact shape (a median
13 s a group, up to 84 s) no longer runs first - with the diagonal for long islands (DIAG_FROM) and a second
ordering for small sets (pack_best). The numbers of the call the builder makes are in reference/14.

The guarantee, tested from outside with exact geometry (kit/test/python/test_uvpack.py): two islands are never
closer than the pad, none leaves the map. rbx.Asset keeps this layout only where it covers more than Blender's.

    pack(tri, isl, tex, pad_px) -> {"tri": (T,3,2) packed uvs, "cover", ...} or None
    pack_best(...)              -> the fuller of pack()'s layouts by two orderings (a small set: the second is cheap)
    islands(vert, uv)           -> (T,) island ids
    cover(tri)                  -> the share of the map the triangles cover (their area; islands never overlap)
"""
import math
import time

import numpy as np

BIG_N = 48            # islands placed by exact shape (the largest by box)
ROT4 = 16             # the largest of them try four turns; the other big ones two
# A LONG island - a barrel's strip, a blade's flat - can be longer than the map is wide at the scale the rest would
# fit: lying straight it caps everything (the Gjallarhorn's game body: four strips held the map at 0.59 used, where
# Blender's packer, which turns freely, reached 0.68). So an island over DIAG_FROM of the map's side is also drawn
# turned 45 degrees: it fits on the diagonal, and several nest there side by side (that body: 0.70).
DIAG_FROM = 0.7
# AN ISLAND LIES OVER THE TEXEL CENTRES OF ITS OWN BOX. A bake gives a texel to the face that covers its CENTRE; an
# island that starts on a texel's edge and is 0.46 texels thin (a 2 cm seam's wall on a 64 px map, a 1.5 mm lip on a
# game version) covers none, and is drawn in whatever colour the margin of a neighbour left there: a dark seam came
# out grey or dark by the luck of the layout (2026-11-13: a self-test fixture's seam, 20 of its 35 islands without
# one texel of their own). So along each axis an island is laid in the MIDDLE of the texels its box takes - all of
# their centres are under it, a strip thinner than a texel has its one row - where that leaves it at least
# CENTRE_FROM / 2 of a texel beyond the outermost centres; an island just over a whole number of texels stays at
# the edge (it has all but the last centre for sure, where the middle would risk both ends). The cells it takes are
# the same either way (_raster counts them from the island's size, as before): nothing is paid for it.
# What it does NOT do: an island on the diagonal is centred in its turned frame (no help); a thin feature INSIDE a
# larger island lands where the island's middle puts it (as much luck as before); and on a map whose cell is not a
# whole number of texels (a side over 1024 that is no multiple of it) nothing is centred - a cell's corner is no
# texel's corner there.
CENTRE_FROM = 0.2
SMALL_SET = 128       # pack_best: a set of this many islands or fewer is packed by a second ordering too
LADDER = np.unique(np.round(1.19 ** np.arange(0, 48)).astype(np.int64))   # box size classes: 1,2,3,...,8,10,12,14,...


def _hull(p):
    p = np.unique(np.round(p, 7), axis=0)
    if len(p) < 3:
        return p
    p = p[np.lexsort((p[:, 1], p[:, 0]))]

    def half(pts):
        h = []
        for q in pts:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h

    lo, up = half(p), half(p[::-1])
    return np.array(lo[:-1] + up[:-1])


HULL_EXACT = 400      # an island with more points than this: its outermost points in 96 directions stand for its hull


def min_rect_angle(p):
    """the turn (radians) that lays an island's smallest bounding rectangle flat, its long side along U (only the
    island's turn hangs on it, never the guarantee: a many-pointed island's hull is taken from its outermost points
    in 96 directions - numpy, no loop over its points)"""
    if len(p) > HULL_EXACT:
        a = np.linspace(0.0, 2 * math.pi, 96, endpoint=False)
        p = p[np.unique(np.argmax(p @ np.stack([np.cos(a), np.sin(a)]), axis=0))]
    h = _hull(p)
    if len(h) < 3:
        d = p.max(0) - p.min(0)
        return 0.0 if d[0] >= d[1] else math.pi / 2
    e = np.roll(h, -1, axis=0) - h
    ang = np.unique(np.round(np.arctan2(e[:, 1], e[:, 0]) % (math.pi / 2), 5))   # the rectangle lies on a hull edge
    if len(ang) > 180:                         # a round island: every half degree is as good as every edge
        ang = ang[np.linspace(0, len(ang) - 1, 180).astype(np.int64)]
    best, ba = None, 0.0
    for a in ang:
        c, s = math.cos(-a), math.sin(-a)
        q = h @ np.array([[c, s], [-s, c]])
        d = q.max(0) - q.min(0)
        if best is None or d[0] * d[1] < best - 1e-12:
            best, ba = d[0] * d[1], (-a if d[0] >= d[1] else -a + math.pi / 2)
    return ba


def _rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return p @ np.array([[c, s], [-s, c]])


def _raster_sheet(q, isl_local, H, Wd):
    """q: (T,3,2) triangles in CELLS, island-local (min corner 0,0); isl_local: (T,) 0..n-1; H: (n,) rows per
    island. -> bool sheet (sum H, Wd): island i's rows start at cumsum(H)[i-1]. Every cell a triangle TOUCHES is set:
    row by row, the triangle's extent inside that row's band."""
    off = np.concatenate([[0], np.cumsum(H)])
    rows = int(off[-1])
    plus, minus = [], []
    y = q[..., 1]
    j0 = np.floor(y.min(axis=1)).astype(np.int64)
    j1 = np.floor(y.max(axis=1)).astype(np.int64)
    j1 = np.minimum(j1, H[isl_local] - 1)
    span = j1 - j0 + 1
    R = 1
    todo = np.arange(len(q))
    while len(todo):
        m = todo[span[todo] <= R]
        todo = todo[span[todo] > R]
        step = max(1, 2_000_000 // R)
        for s0 in range(0, len(m), step):
            mm = m[s0:s0 + step]
            jj = j0[mm][:, None] + np.arange(R)[None, :]
            xl = np.full(jj.shape, np.inf)
            xr = np.full(jj.shape, -np.inf)
            for a, b in ((0, 1), (1, 2), (2, 0)):
                xa, ya, xb, yb = q[mm, a, 0][:, None], q[mm, a, 1][:, None], q[mm, b, 0][:, None], q[mm, b, 1][:, None]
                ylo, yhi = np.minimum(ya, yb), np.maximum(ya, yb)
                over = (ylo <= jj + 1) & (yhi >= jj)
                dy = yb - ya
                flat = dy == 0
                slope = (xb - xa) / np.where(flat, 1.0, dy)
                x0 = xa + (np.clip(jj, ylo, yhi) - ya) * slope
                x1 = xa + (np.clip(jj + 1, ylo, yhi) - ya) * slope
                lo_e = np.where(flat, np.minimum(xa, xb), np.minimum(x0, x1))
                hi_e = np.where(flat, np.maximum(xa, xb), np.maximum(x0, x1))
                xl = np.where(over, np.minimum(xl, lo_e), xl)
                xr = np.where(over, np.maximum(xr, hi_e), xr)
            ok = (jj <= j1[mm][:, None]) & (xr >= xl)
            cl = np.clip(np.floor(xl[ok]), 0, Wd - 2).astype(np.int64)
            cr = np.clip(np.floor(xr[ok]), 0, Wd - 2).astype(np.int64)
            rg = (off[isl_local[mm]][:, None] + jj)[ok]
            plus.append(rg * Wd + cl)
            minus.append(rg * Wd + cr + 1)
        R *= 2
    n = rows * Wd
    diff = np.bincount(np.concatenate(plus), minlength=n).astype(np.int32)
    diff -= np.bincount(np.concatenate(minus), minlength=n).astype(np.int32)
    return np.cumsum(diff.reshape(rows, Wd), axis=1) > 0, off


def _centred(ext, cell=1.0):
    """ext: (k, 2) the islands' box sizes in CELLS, cell: texels a cell -> (k, 2) how far from its cells' corner
    each island starts, in cells, so that it lies over the texel centres of its box (CENTRE_FROM)"""
    e = np.asarray(ext, np.float64) * cell                  # texels
    if abs(cell - round(cell)) > 1e-9:                      # (a cell that is no whole number of texels: see above)
        return np.zeros_like(e)
    spare = np.clip(np.ceil(e - 1e-9) - e, 0.0, 1.0)        # what is left of the last texel its box takes
    # (a spare of a millionth of a texel is rounding, not room: such an island stays where it is)
    mid = ((e < 1.0) | (spare <= 1.0 - CENTRE_FROM)) & (spare > 1e-6)
    return np.where(mid, spare / 2.0, 0.0) / cell


def _raster(tri_cells, cut, cell=1.0):
    """every island's cells, island by island -> (list of bool masks (h, w); lo (k,2): what to take off an island's
    points to have it in its own cells - its min corner, less the start that lays it over its texels' centres
    (_centred)). tri_cells: (T,3,2) in cells, sorted by island; cut: (k+1,) slices; cell: texels a cell"""
    k = len(cut) - 1
    lo = np.array([tri_cells[cut[i]:cut[i + 1]].reshape(-1, 2).min(axis=0) for i in range(k)])
    top = np.array([tri_cells[cut[i]:cut[i + 1]].reshape(-1, 2).max(axis=0) for i in range(k)])
    hi = top - lo                              # the island's size: its cells are counted from THIS, centred or not
    W = np.floor(hi[:, 0]).astype(np.int64) + 1
    H = np.floor(hi[:, 1]).astype(np.int64) + 1
    lo = lo - _centred(hi, cell)
    isl = np.repeat(np.arange(k), np.diff(cut))
    q = tri_cells - lo[isl][:, None, :]
    masks = [None] * k
    edges = [0, 16, 64, 256, 1 << 30]          # islands of a like width share a sheet (a narrow one wastes none)
    for a, b in zip(edges[:-1], edges[1:]):
        ids = np.flatnonzero((W > a) & (W <= b))
        if not len(ids):
            continue
        local = np.full(k, -1, np.int64)
        local[ids] = np.arange(len(ids))
        tm = local[isl] >= 0
        sheet, off = _raster_sheet(q[tm], local[isl][tm], H[ids], int(W[ids].max()) + 2)
        for n, i in enumerate(ids):
            masks[i] = sheet[off[n]:off[n + 1], :W[i]].copy()
    return masks, lo


def _dilate(m, r):
    h, w = m.shape
    out = np.zeros((h + 2 * r, w + 2 * r), bool)
    row = np.zeros((h, w + 2 * r), bool)
    for dx in range(2 * r + 1):
        row[:, dx:dx + w] |= m
    for dy in range(2 * r + 1):
        out[dy:dy + h] |= row
    return out


def _up(v):
    return int(LADDER[min(np.searchsorted(LADDER, v), len(LADDER) - 1)]) if v <= LADDER[-1] else int(v)


def _place_small(occ, items):
    """items: [(island, h, w)] sorted by box, largest first; each is a BOX. Class by class (boxes of a like size share
    one map of the free places, made fresh for the class), each box at the first free place from the bottom left,
    lying or standing. -> {island: (y, x, quarter turns)} or None"""
    g = occ.shape[0]
    out = {}
    classes, seen = [], {}
    for it in items:
        key = (_up(it[1]), _up(it[2]))
        if key not in seen:
            seen[key] = len(classes)
            classes.append((key, []))
        classes[seen[key]][1].append(it)
    for (Hc, Wc), members in classes:
        S = np.zeros((g + 1, g + 1), np.int32)
        np.cumsum(occ, axis=0, dtype=np.int32, out=S[1:, 1:])
        np.cumsum(S[1:, 1:], axis=1, out=S[1:, 1:])
        cand = []
        for hh, ww in ((Hc, Wc), (Wc, Hc)) if Hc != Wc else ((Hc, Wc),):
            if hh > g or ww > g:
                cand.append((np.zeros(0, np.int64), 1))
                continue
            free = (S[hh:, ww:] - S[:-hh, ww:] - S[hh:, :-ww] + S[:-hh, :-ww]) == 0
            cand.append((np.flatnonzero(free.ravel()), free.shape[1]))
        ptr = [0] * len(cand)
        for i, h, w in members:
            best = None
            for o, (idx, fw) in enumerate(cand):
                bh, bw = (h, w) if o == 0 else (w, h)
                p = ptr[o]
                while p < len(idx):
                    y, x = divmod(int(idx[p]), fw)
                    if not occ[y:y + bh, x:x + bw].any():
                        break
                    row = occ[y, x:x + 4 * bw + 8]             # taken: jump past what blocks this row here
                    run = int(np.argmin(row)) if not row.all() else len(row)
                    p = int(np.searchsorted(idx, y * fw + x + max(run, 1))) if run > 1 else p + 1
                ptr[o] = p
                if p < len(idx):
                    y, x = divmod(int(idx[p]), fw)
                    score = (y + bh, x)
                    if best is None or score < best[0]:
                        best = (score, y, x, o, bh, bw)
            if best is None:
                return None
            _s, y, x, o, bh, bw = best
            occ[y:y + bh, x:x + bw] = True
            out[i] = (y, x, o)
    return out


def _place(masks, g, pool, order_by="box", diag=None):
    """masks: every island's cells grown by half a pad; order_by: largest first by its box ("box") or by the cells
    it covers ("cells"); diag: {island: its mask turned 45 degrees} for the long ones.
    -> ([(y, x, turn)] per island or None, the grid). turn: 0..3 quarter turns; 4, 5: on a diagonal"""
    k = len(masks)
    occ = np.zeros((g, g), bool)
    diag = diag or {}
    box = np.array([m.shape[0] * m.shape[1] for m in masks])
    key = box if order_by == "box" else np.array([int(m.sum()) for m in masks])
    order = np.argsort(-key, kind="stable")
    # by exact shape: the largest, and every long island (it may lie straight or on a diagonal) - in that order
    big = [int(i) for n_, i in enumerate(order)
           if int(i) in diag or (n_ < BIG_N and (min(masks[i].shape) >= 6 * pool or k <= 8))]
    isbig = set(big)
    out = [None] * k
    top = 0
    P = pool
    for n, i in enumerate(big):
        m0 = masks[i]
        best = None
        rows = min(g, -(-(top + max(m0.shape) + 2) // P) * P)
        oc = occ[:rows].reshape(rows // P, P, g // P, P).any(axis=(1, 3))
        F = np.fft.rfft2(oc.astype(np.float64))
        cands = [(t, np.rot90(m0, t)) for t in ((0, 1, 2, 3) if n < ROT4 else (0, 1))]
        if i in diag:   # (turned 45 degrees, and that turned a quarter: the other diagonal)
            cands += [(4, diag[i]), (5, np.rot90(diag[i], 1))]
        for t, m in cands:
            h, w = m.shape
            hc, wc = -(-h // P), -(-w // P)
            if hc > oc.shape[0] or wc > oc.shape[1]:
                continue
            mp = np.zeros((hc * P, wc * P), bool)
            mp[:h, :w] = m
            pad = np.zeros(oc.shape, np.float64)
            pad[:hc, :wc] = mp.reshape(hc, P, wc, P).any(axis=(1, 3))
            corr = np.fft.irfft2(F * np.conj(np.fft.rfft2(pad)), s=oc.shape)
            valid = corr[:oc.shape[0] - hc + 1, :oc.shape[1] - wc + 1] < 0.5
            flat = np.flatnonzero(valid.ravel())
            if not len(flat):
                continue
            y, x = divmod(int(flat[0]), valid.shape[1])
            y, x = y * P, x * P
            if y + h > g or x + w > g:
                continue
            score = (y + h, x + w)
            if best is None or score < best[0]:
                best = (score, y, x, t, m)
        if best is None:
            return None, occ
        _s, y, x, t, m = best
        occ[y:y + m.shape[0], x:x + m.shape[1]] |= m
        top = max(top, y + m.shape[0])
        out[i] = (y, x, t)
    small = [(int(i), masks[i].shape[0], masks[i].shape[1]) for i in order if int(i) not in isbig]
    got = _place_small(occ, small)
    if got is None:
        return None, occ
    for i, v in got.items():
        out[i] = v
    return out, occ


def cover(tri):
    """(T,3,2) uv triangles -> their summed area: the share of the map they cover when none overlaps"""
    tri = np.asarray(tri, np.float64)
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    return float((np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2).sum())


def pack_best(tri, isl, tex, pad_px=4.0, budget_s=None, at_least=None, log=None):
    """pack() with the islands ordered by their boxes, and - for a small set, where it costs under a second - by the
    cells they cover as well (a few odd shapes pack differently: the Gjallarhorn's trigger, 12 islands, 0.61 -> 0.70).
    The second only searches above the first. -> the fuller layout ("secs": both), or None"""
    t0 = time.time()
    best = pack(tri, isl, tex, pad_px, budget_s=budget_s, at_least=at_least, log=log)
    if len(isl) and len(np.unique(isl)) <= SMALL_SET:
        left = None if budget_s is None else max(1.0, budget_s - (time.time() - t0))
        more = pack(tri, isl, tex, pad_px, budget_s=left, log=log, order_by="cells",
                    at_least=best["cover"] * 1.005 if best else at_least)
        if more is not None and (best is None or more["cover"] > best["cover"]):
            best = more
    if best is not None:
        best["secs"] = time.time() - t0
    return best


def pack(tri, isl, tex, pad_px=4.0, cell=None, tries=14, pool=None, log=None, budget_s=None, at_least=None,
         order_by="box"):
    """tri: (T,3,2) uv triangles (any layout: only the islands' shapes and relative sizes are used), isl: (T,) the
    island of each, tex: the map's side in texels, pad_px: the least distance between two islands in texels.
    budget_s: stop searching a larger scale after this many seconds (the best layout so far is returned).
    at_least: the cover a layout must reach to be of use (another packer's, times the gain asked): the search never
    goes under it, and gives up when even that does not fit. Until something fits the scale comes down faster and
    faster (a map of thousands of islands fits at a tenth of the map, not at the 62% the search starts from);
    once the scale is bracketed it is halved to within 0.4% for a small set (two fits a hair apart differ by a
    whole island's place), 0.6% for a large one.
    -> {"tri": packed uvs in 0..1 (same order), "cover", "scale", "secs", "grid", "islands", ...}, or None when
    nothing was packed (no area, or not even the first try fitted in time)"""
    t0 = time.time()
    tri = np.asarray(tri, np.float64)
    if not len(tri) or not np.isfinite(tri).all():
        return None
    _ids, isl = np.unique(np.asarray(isl, np.int64), return_inverse=True)   # (any ids: numbered 0..k-1 here)
    k = int(isl.max()) + 1
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    A = float((np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2).sum())
    if A <= 1e-12:                             # (no area, or only rounding noise: no scale to speak of)
        return None
    cell = float(cell or (1.0 if tex <= 1024 else tex / 1024.0))     # texels a cell
    g = int(round(tex / cell))
    r = int(math.ceil(pad_px / (2.0 * cell) - 1e-9))
    # the big islands' grid: 4 x 4 cells pooled (measured on five real sets: within 0.02 of 2 x 2, two to three
    # times faster)
    pool = pool or (4 if g % 4 == 0 and g >= 512 else (2 if g % 2 == 0 and g >= 128 else 1))
    by = np.argsort(isl, kind="stable")
    tri, isl = tri[by], isl[by]
    cut = np.searchsorted(isl, np.arange(k + 1))
    flat = np.empty_like(tri)
    for i in range(k):                          # every island laid flat on its smallest rectangle
        p = tri[cut[i]:cut[i + 1]].reshape(-1, 2)
        flat[cut[i]:cut[i + 1]] = _rot(p, min_rect_angle(p)).reshape(-1, 3, 2)
    lo_s, hi_s, got = None, None, None
    fails, close = 0, (1.004 if k <= SMALL_SET else 1.006)
    s_min = math.sqrt(at_least / A) if at_least else 0.0
    s = max(math.sqrt(0.62 / A), s_min)        # start: 62% of the map (or what the layout must reach)
    ext2 = np.array([np.ptp(flat[cut[i]:cut[i + 1]].reshape(-1, 2), axis=0) for i in range(k)])   # (long, short)
    ext = ext2.max(axis=1)
    # the least square side an island needs: lying straight, or on the diagonal ((long + short) / sqrt 2)
    need = np.minimum(ext, ext2.sum(axis=1) / math.sqrt(2.0))
    for n in range(tries):
        sc = s * tex / cell
        if float(need.max()) * sc + 2 * r + 1 > g:     # an island that fits the map neither way: nothing to draw
            spots, occ, masks, lo, dg = None, np.zeros((1, 1), bool), None, None, {}
        else:
            masks, lo = _raster(flat * sc, cut, cell)
            dg = {}   # the long islands, drawn turned 45 degrees as well (DIAG_FROM)
            for i in np.flatnonzero(ext * sc + 2 * r + 1 > DIAG_FROM * g):
                t45 = _rot(flat[cut[i]:cut[i + 1]].reshape(-1, 2), math.pi / 4).reshape(-1, 3, 2) * sc
                m45, lo45 = _raster(t45, np.array([0, len(t45)]), cell)
                dg[int(i)] = (m45[0], lo45[0])
            spots, occ = _place([_dilate(m, r) for m in masks], g, pool, order_by,
                                {i: _dilate(m, r) for i, (m, _l) in dg.items()})
        ok = spots is not None
        if log:
            log(f"  try {n}: cover {s * s * A:.3f} -> {'fits' if ok else 'does not fit'} ({time.time() - t0:.1f} s)")
        if ok:
            lo_s, got = s, (masks, lo, spots, s, dg)
            used = np.flatnonzero(occ.any(1))
            free_rows = 1.0 - (int(used[-1]) + 1) / g if len(used) else 0.5
            nxt = s * math.sqrt(1.0 / max(1.0 - free_rows, 0.5)) * 0.99 if free_rows > 0.03 else s * 1.03
            s = min(nxt, (s + hi_s) / 2) if hi_s else nxt
        else:
            hi_s = s
            if not lo_s and s <= s_min * 1.0001:
                break                          # even the least useful scale does not fit
            if lo_s:
                s = (lo_s + s) / 2
            else:                              # nothing fits yet: down by 8%, 15%, 28%, 49%, then by half each try
                fails += 1
                s = max(s * max(0.92 ** (2 ** (fails - 1)), 0.5), s_min)
        if lo_s and hi_s and hi_s / lo_s < close:
            break
        if budget_s and time.time() - t0 > budget_s:              # (the setup above counts too)
            break
    if got is None:
        return None
    masks, lo, spots, s, dg = got
    q = flat * (s * tex / cell)
    out = np.empty_like(q)
    for i in range(k):
        m = slice(cut[i], cut[i + 1])
        y, x, t = spots[i]
        if t >= 4:                                  # on a diagonal: the island turned 45 degrees first
            h, w = dg[i][0].shape
            p = _rot(q[m].reshape(-1, 2), math.pi / 4).reshape(-1, 3, 2) - dg[i][1]
            t -= 4
        else:
            h, w = masks[i].shape                   # the island's own cells (not grown)
            p = q[m] - lo[i]                        # island-local, in cells, inside [0,w] x [0,h]
        for _ in range(t):                          # np.rot90: cell (y, x) -> (w - 1 - x, y)
            p = np.stack([p[..., 1], w - p[..., 0]], axis=-1)
            h, w = w, h
        out[m] = (p + (x + r, y + r)) * cell
    back = np.empty_like(out)
    back[by] = out
    return {"tri": back / tex, "cover": s * s * A, "scale": s, "secs": time.time() - t0, "grid": g, "cell": cell,
            "dilate": r, "islands": k, "pool": pool}


def islands(vert, uv):
    """the UV islands of a triangle list: two triangles are one island when they share a mesh vertex AT the same uv.
    vert: (T,3) the mesh vertex of every corner, uv: (T,3,2) -> (T,) island ids 0..k-1. numpy only: every round the
    ROOT labels of a triangle's three corners are joined to the smallest of them and every chain is shortened to its
    root - a few rounds whatever order the vertex ids are in (joining the corners themselves moved a label one
    triangle a round: minutes on a long strip with shuffled ids)"""
    vert = np.asarray(vert, np.int64).reshape(-1)
    q = np.round(np.asarray(uv, np.float64).reshape(-1, 2) * 1e5).astype(np.int64)
    key = np.column_stack([vert, q])
    _u, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.reshape(-1, 3)
    lab = np.arange(int(inv.max()) + 1)
    while True:
        r = lab[inv]                                   # every corner's root (the chains are flat here)
        m = np.repeat(r.min(axis=1), 3)
        new = lab.copy()
        np.minimum.at(new, r.ravel(), m)               # a root takes the smallest root it shares a triangle with
        while True:                                    # ... and every chain is shortened to its root
            nn = new[new]
            if np.array_equal(nn, new):
                break
            new = nn
        if np.array_equal(new, lab):
            break
        lab = new
    _r, out = np.unique(lab[inv[:, 0]], return_inverse=True)
    return out
