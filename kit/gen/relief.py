"""relief.py — a sculpted ornament as a RELIEF from its own reference picture (kit-owned code, plain numpy / scipy).

Code cannot sculpt a wolf's head or a feathered wing; a generator guesses them in 3D and smears the detail. Most
ornaments on a weapon are reliefs — sculpture that rises from a surface and is seen from the front. So the kit takes
the ornament from the reference itself: a surface-normal estimate (MoGe-2) carries the fine sculpting (fur, eyes,
feather ridges), a depth estimate (Depth Anything 3) the big forms, and a least-squares solve turns them into ONE
height field that sits at 0 along the ornament's outline and rises inside it. It matches the picture exactly from the
picture's own view. rbx.Asset.relief() builds it as geometry, at its measured size, on the part it decorates.

    heights = relief_height(normal, depth, mask)        # 0..1 inside the mask, 0 outside
    preview = shade(heights)                            # a lit picture of it, for looking

The solve: minimise  sum |grad h - g|^2 + w * sum (h - d)^2  over the ornament's pixels, h = 0 outside it, where g are
the normal map's slopes (compressed, so a deep step does not swallow the detail: the bas-relief recipe) and d the
depth map scaled to the same range. The sign of "towards the viewer" is checked against the depth map, not assumed.
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


def slopes(normal):
    """surface slopes (dh/dx, dh/dy) from unit normals in camera space (x right, y down, z into the picture): a
    surface facing the camera has n = (0, 0, -1); h grows TOWARD the viewer"""
    nx, ny, nz = normal[..., 0], normal[..., 1], normal[..., 2]
    nz = np.where(np.abs(nz) < 0.05, np.sign(nz + 1e-9) * 0.05, nz)  # (grazing normals: a bounded slope)
    return nx / nz, ny / nz


def compress(gx, gy, alpha=4.0):
    """the bas-relief recipe: big slopes shrink a lot, small ones hardly at all — the detail survives a deep step"""
    mag = np.hypot(gx, gy)
    k = np.log1p(alpha * mag) / (alpha * np.maximum(mag, 1e-9))
    return gx * k, gy * k


def _solve(gx, gy, mask, data=None, w=0.0):
    """least-squares integration of slopes on the mask's pixels, h = 0 outside it (and `w` pulls h toward `data`)"""
    H, W = mask.shape
    idx = -np.ones((H, W), dtype=np.int64)
    ys, xs = np.nonzero(mask)
    n = len(ys)
    idx[ys, xs] = np.arange(n)
    rows, cols, vals, rhs = [], [], [], []
    r = 0
    for dy, dx, g in ((0, 1, gx), (1, 0, gy)):  # forward differences: h[p + d] - h[p] = g[p]
        y2, x2 = ys + dy, xs + dx
        ok = (y2 < H) & (x2 < W)
        a = idx[ys[ok], xs[ok]]
        b = idx[y2[ok], x2[ok]]
        gv = g[ys[ok], xs[ok]]
        m = len(a)
        rr = np.arange(r, r + m)
        inside = b >= 0  # a neighbour outside the mask is the base: h = 0 there
        rows += [rr, rr[inside]]
        cols += [a, b[inside]]
        vals += [-np.ones(m), np.ones(inside.sum())]
        rhs.append(gv)
        r += m
    if w > 0 and data is not None:
        rr = np.arange(r, r + n)
        rows.append(rr)
        cols.append(np.arange(n))
        vals.append(np.full(n, np.sqrt(w)))
        rhs.append(np.sqrt(w) * data[ys, xs])
        r += n
    A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(r, n)).tocsr()
    b = np.concatenate(rhs)
    h = spsolve((A.T @ A).tocsc(), A.T @ b)
    out = np.zeros((H, W))
    out[ys, xs] = h
    return out


def relief_height(normal, depth, mask, depth_weight=0.005, alpha=4.0, detail=1.5, detail_px=3.0):
    """-> heights 0..1 (1 = the part nearest the viewer), 0 outside the mask. `detail` boosts what is finer than
    `detail_px` against the big forms (the relief carver's emphasis: feather ridges, fur, eyes read at game distance)"""
    mask = mask.astype(bool)
    gx, gy = compress(*slopes(normal), alpha=alpha)
    d = np.where(mask, depth, np.nan)
    near = np.nanmax(d) - d  # nearer = higher
    near = np.nan_to_num(near / max(np.nanmax(near), 1e-9))
    best, best_c = None, -2.0
    for sign in (1.0, -1.0):  # which way is "toward the viewer": the one that agrees with the depth map
        h = _solve(sign * gx, sign * gy, mask)
        c = np.corrcoef(h[mask], near[mask])[0, 1] if mask.sum() > 2 else 0.0
        if c > best_c:
            best, best_c = sign, c
    scale = np.ptp(_solve(best * gx, best * gy, mask)[mask]) or 1.0
    h = _solve(best * gx, best * gy, mask, data=near * scale, w=depth_weight)
    h = np.where(mask, h - min(0.0, h[mask].min()), 0.0)
    if detail:
        from scipy.ndimage import gaussian_filter  # noqa: PLC0415

        w = gaussian_filter(mask.astype(float), detail_px)
        low = gaussian_filter(h, detail_px) / np.maximum(w, 1e-6)  # (blur inside the ornament only)
        h = np.where(mask, np.maximum(h + detail * (h - low), 0.0), 0.0)
    top = h.max()
    return h / top if top > 0 else h


def shade(h, light=(-0.6, -0.7, 0.9), relief_depth=0.08):
    """a lit picture of a height field (0..1) for looking: light from the upper left"""
    H, W = h.shape
    s = relief_depth * max(H, W)
    gy, gx = np.gradient(h * s)
    n = np.dstack([-gx, -gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    lv = np.asarray(light, dtype=float)
    lv /= np.linalg.norm(lv)
    return np.clip(n @ lv, 0, 1)
