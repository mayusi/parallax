"""depth_relief.py — the RELIEF inside a view, picture against model: what neither an outline nor the openings see (a
recess, a step between slide and frame, a fuller down a blade, a raised panel) - his V3 list, 3D stage A.3 "depth
cavities".

A photo has no metric depth; a monocular depth model (Depth Anything V2 Small, kit/vision: vetted, offline) gives a
RELATIVE one. So the two are compared as RELIEF - each depth less its own local average inside the object (the big
curvature and the camera's tilt cancel out) - and the photo's relief is scaled to the model's by least squares (the
one number a relative depth leaves free). Then:
    corr       how alike the two reliefs run (Pearson, -1..1; 1 = every step and recess where the picture has it)
    windows    along the view's length and height: where the picture is recessed and the model is not ("missing":
               a cavity or a step not cut) and where the model is recessed and the picture is not ("extra")

    compare(photo_near, photo_mask, model_near, model_mask, width=384, blur=None) -> dict
photo_near / model_near: HxW, larger = NEARER the viewer (a model's depth along the view, negated); masks: the
object. Both are cut to their masks' boxes and laid on one grid (as the silhouette check fits them), the model's
mirror image tried too (a side view's front may face either way) and kept only when its outline fits clearly better. Plain numpy: Blender's python runs it.
"""

import numpy as np

COLS, ROWS = 8, 3          # the windows the worst places are named by
RECESS_SIGMA = 1.5         # a window is "missing" / "extra" past this many of the relief's own spreads
MIN_INNER = 400            # pixels both reliefs must share inside, else nothing is said


def crop(a, mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None, None
    sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
    return a[sl], mask[sl]


def resize(a, w, h):
    """nearest-neighbour resize -> h x w (plain numpy)"""
    ys = np.minimum((np.arange(h) + 0.5) * a.shape[0] / h, a.shape[0] - 1).astype(int)
    xs = np.minimum((np.arange(w) + 0.5) * a.shape[1] / w, a.shape[1] - 1).astype(int)
    return a[np.ix_(ys, xs)]


def _box(a, r):
    """a box filter of radius r (summed-area table), edges clamped"""
    if r < 1:
        return a.copy()
    p = np.pad(a, r + 1, mode="edge").astype(float)
    s = p.cumsum(0).cumsum(1)
    k = 2 * r + 1
    out = s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k]
    return out[: a.shape[0], : a.shape[1]] / float(k * k)


def erode(m, n):
    m = m.copy()
    for _ in range(int(n)):
        e = m.copy()
        e[1:] &= m[:-1]
        e[:-1] &= m[1:]
        e[:, 1:] &= m[:, :-1]
        e[:, :-1] &= m[:, 1:]
        m = e
    return m


def relief(near, mask, r):
    """the depth less its local average INSIDE the object (three box passes ~ a gaussian of radius r)"""
    d = np.where(mask, near, 0.0).astype(float)
    w = mask.astype(float)
    sd, sw = d, w
    for _ in range(3):
        sd, sw = _box(sd, r), _box(sw, r)
    return np.where(mask, d - sd / np.maximum(sw, 1e-9), 0.0)


def _norm(x, inner):
    v = x[inner]
    s = float(v.std())
    return (x - float(v.mean())) / s if s > 1e-12 else None


def compare(photo_near, photo_mask, model_near, model_mask, width=384, blur=None):
    pn, pm = crop(np.nan_to_num(photo_near), photo_mask)
    mn, mm = crop(np.nan_to_num(model_near), model_mask)
    if pn is None or mn is None:
        return None
    w = int(width)
    h = max(16, int(round(w * pn.shape[0] / pn.shape[1])))
    pn, pm = resize(pn, w, h), resize(pm, w, h)
    r = int(blur or max(3, w // 24))
    rp = relief(pn, pm, r)
    best = None
    for flip in (False, True):
        mn_, mm_ = (mn[:, ::-1], mm[:, ::-1]) if flip else (mn, mm)
        mn_, mm_ = resize(mn_, w, h), resize(mm_, w, h)
        inner = erode(pm & mm_, max(2, r // 2))   # (the outline itself is the silhouette's: well inside it)
        if inner.sum() < MIN_INNER:
            continue
        rm = relief(mn_, mm_, r)
        zp, zm = _norm(rp, inner), _norm(rm, inner)
        if zp is None or zm is None:
            corr = 0.0
        else:
            corr = float(np.mean(zp[inner] * zm[inner]))
        iou = float((pm & mm_).sum() / max(1, (pm | mm_).sum()))
        # the mirror image only when its OUTLINE fits clearly better - never because its relief happens to: on a
        # symmetric outline that would line a recess cut at the wrong end up with the picture's (the tests found it)
        if best is None or iou > best["outline_iou"] + 0.02:
            best = {"corr": round(corr, 3), "outline_iou": round(iou, 3), "mirrored": flip, "_zp": zp, "_zm": zm,
                    "_inner": inner, "_rp": rp, "_rm": rm}
    if best is None:
        return None
    zp, zm, inner = best.pop("_zp"), best.pop("_zm"), best.pop("_inner")
    rp_, rm_ = best.pop("_rp"), best.pop("_rm")
    # the photo's relief in the MODEL's units: least squares rp ~ a * rm (a relative depth's one free number)
    v = float((rm_[inner] ** 2).sum())
    a = float((rp_[inner] * rm_[inner]).sum() / v) if v > 0 else 0.0
    best["scale"] = round(a, 6)
    windows = []
    if zp is not None and zm is not None:
        k = max(0.0, float((zp[inner] * zm[inner]).sum() / max((zm[inner] ** 2).sum(), 1e-12)))
        for i in range(ROWS):
            for j in range(COLS):
                sl = (slice(i * h // ROWS, (i + 1) * h // ROWS), slice(j * w // COLS, (j + 1) * w // COLS))
                cell = inner[sl]
                if cell.sum() < MIN_INNER // (COLS * ROWS) + 1:
                    continue
                # (the model's relief scaled to the picture's by least squares - never blown up to a unit spread:
                #  a flat model would turn its noise into "extra" relief)
                gap = float((zp[sl][cell] - k * zm[sl][cell]).mean())   # < 0: the picture deeper there
                if abs(gap) >= RECESS_SIGMA * 0.5:
                    windows.append({"kind": "missing" if gap < 0 else "extra", "gap": round(gap, 2),
                                    "across": [round(100 * j / COLS), round(100 * (j + 1) / COLS)],
                                    "up": [round(100 * (ROWS - 1 - i) / ROWS), round(100 * (ROWS - i) / ROWS)]})
    best["windows"] = sorted(windows, key=lambda x: -abs(x["gap"]))[:6]
    best["pixels"] = int(inner.sum())
    return best
