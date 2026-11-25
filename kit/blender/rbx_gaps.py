"""rbx_gaps.py — where two silhouettes' EDGES disagree, in millimetres (plain numpy: no Blender, unit-tested).

    gaps, marks = edge_gaps(model, ref, per_px=0.4, unit="mm", view="front")
    gaps["worst"]    ["the model is 12 mm too wide at the top left", "the reference has 8 mm more at the ..."]
    gaps["windows"]  3 x 3 windows over both silhouettes: how far the model sticks out / falls short in each
    annotate(diff, marks)                     the 3 x 3 grid, the windows beyond the tolerance and the worst gaps
                                              drawn onto reference_match's diff picture
    regions_in_frame(trace, regions, xf)      refs/<asset>.regions.json boxes -> this frame (a gap per region)

Both masks must already be in ONE frame — rbx_precision._normalise's (cropped to content, the longer side scaled to
n, centred): one pixel is then `per_px` of the MODEL (mm with a.real_scale, else studs). An IoU says how much is
wrong; this says where and by how much. Every pixel on either outline is matched to the nearest pixel on the other
outline (an exact Euclidean distance: the nearest edge pixel in each column first, then a row pass over the edge
pixels only — no scipy in Blender's Python):
  the model's edge OUTSIDE the reference      -> the model sticks out there (extra)
  the reference's edge OUTSIDE the model      -> the reference has more there (missing)
  (and the other two ways round: an edge inside the other silhouette is the other side's excess, seen from inside)
A window's gap is its k-th largest (default 5): a feature must run along a few edge pixels to count, one stray
pixel never does. The direction words come from the line between the two edges (mostly across = wide / long,
mostly up-down = tall).
"""

import numpy as np

K = 5  # a window's gap is its K-th largest edge distance: robust to a stray pixel, still sees a thin claw
# OUTLINES only: holes are filled before the edges are matched. A see-through gap inside one silhouette (a slot between
# a tube and a housing, a thumbhole) has no partner edge in the other's solid area, so its nearest partner was the far
# outline — a 10 mm slot read as a "98 mm" gap on the Gjallarhorn. Openings are counted on their own (`openings`).
CLOSE = 3
# a view's picture axes in words: (horizontal, vertical). side / top traces run back -> front left to right
AXES = {"side": ("long", "tall"), "top": ("long", "wide"), "front": ("wide", "tall"), "back": ("wide", "tall")}
SHORT = {"long": "short", "tall": "short", "wide": "narrow"}
ROWS = ("top", "middle", "bottom")
COLS = {"side": ("back", "middle", "front"), "top": ("back", "middle", "front")}  # front / back views: left .. right


def _grow(m, r):
    """dilate by r pixels (4-neighbour steps), numpy only"""
    m = m.copy()
    for _ in range(int(r)):
        g = m.copy()
        g[1:, :] |= m[:-1, :]
        g[:-1, :] |= m[1:, :]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def enclosed(mask):
    """background pixels shut in on all four sides (left, right, above, below): the silhouette's holes — a notch open
    to one side is not one"""
    m = np.asarray(mask, bool)
    left = np.maximum.accumulate(m, axis=1)
    right = np.maximum.accumulate(m[:, ::-1], axis=1)[:, ::-1]
    up = np.maximum.accumulate(m, axis=0)
    down = np.maximum.accumulate(m[::-1, :], axis=0)[::-1, :]
    return ~m & left & right & up & down


def close(mask, r=CLOSE):
    """morphological closing: slits and notches thinner than 2 r pixels filled, everything wider kept"""
    m = np.asarray(mask, bool)
    if r <= 0:
        return m
    pad = int(r) + 1  # (a frame-edge pad, so a silhouette touching the border is not eaten by the erosion)
    big = np.pad(m, pad)
    closed = ~_grow(~_grow(big, r), r)
    return closed[pad:-pad, pad:-pad] | m


def edge(mask):
    """the mask's outer pixels: in the mask, with a 4-neighbour outside it (or on the frame's border)"""
    m = np.asarray(mask, bool)
    inner = m.copy()
    inner[1:, :] &= m[:-1, :]
    inner[:-1, :] &= m[1:, :]
    inner[:, 1:] &= m[:, :-1]
    inner[:, :-1] &= m[:, 1:]
    inner[0, :] = inner[-1, :] = False
    inner[:, 0] = inner[:, -1] = False
    return m & ~inner


def _column_nearest(feat):
    """for every pixel: the distance to the nearest feature pixel in its own COLUMN, and that pixel's row"""
    h, w = feat.shape
    rows = np.broadcast_to(np.arange(h)[:, None], (h, w))
    big = 4 * (h + w)
    above = np.maximum.accumulate(np.where(feat, rows, -big), axis=0)  # the last feature row at or above
    below = np.minimum.accumulate(np.where(feat, rows, 2 * big)[::-1], axis=0)[::-1]  # the first at or below
    da, db = rows - above, below - rows
    return np.minimum(da, db), np.where(da <= db, above, below)


def nearest(feat, ys, xs, chunk=2048):
    """exact Euclidean distance from each point (ys[i], xs[i]) to the nearest True pixel of `feat`
    -> (distance px, its row, its column); all inf / -1 when feat is empty"""
    n = len(ys)
    d = np.full(n, np.inf, np.float64)
    qy, qx = np.full(n, -1, np.int64), np.full(n, -1, np.int64)
    if not np.any(feat) or n == 0:
        return d, qy, qx
    g, near = _column_nearest(feat)
    g2 = g.astype(np.float64) ** 2
    cols = np.arange(feat.shape[1], dtype=np.float64)
    for s in range(0, n, chunk):
        yy, xx = ys[s:s + chunk], xs[s:s + chunk]
        cost = (xx[:, None].astype(np.float64) - cols[None, :]) ** 2 + g2[yy]
        j = np.argmin(cost, axis=1)
        d[s:s + chunk] = np.sqrt(cost[np.arange(len(j)), j])
        qx[s:s + chunk] = j
        qy[s:s + chunk] = near[yy, j]
    return d, qy, qx


def _fmt(v, unit):
    if unit == "mm":
        return f"{v:.0f} mm" if round(v, 1) >= 10 else f"{v:.1f} mm"
    return f"{v:.2f} studs"


def place(i, j, view):
    """a 3 x 3 window's name: 'top left', 'bottom front', 'centre'; i or j None = a whole column / row"""
    cols = COLS.get(view, ("left", "centre", "right"))
    if i is None:
        return f"{cols[j]} (top to bottom)"
    if j is None:
        return f"{ROWS[i]} ({cols[0]} to {cols[2]})"
    if i == 1 and j == 1:
        return "centre"
    return f"{ROWS[i]} {cols[j]}"


def _merge(entries):
    """windows of one kind and direction along a WHOLE column (or row) are said once: 'too wide at the left (top to
    bottom)' instead of three windows. entries: [{kind, across, i, j, gap, ...}] -> the same, merged"""
    out, used = [], set()
    for axis in ("j", "i"):  # whole columns first: a front view too wide shows as its left and right columns
        other = "i" if axis == "j" else "j"
        for key in sorted({(e["kind"], e["across"], e[axis]) for e in entries}):
            group = [e for e in entries if (e["kind"], e["across"], e[axis]) == key and id(e) not in used]
            if len({e[other] for e in group}) == 3:
                used.update(id(e) for e in group)
                top = max(group, key=lambda e: e["gap"])
                out.append({**top, other: None})
    return out + [e for e in entries if id(e) not in used]


def words(kind, gap, where, across, view, unit):
    """'the model is 12 mm too wide at the top left' / 'the reference has 8 mm more at the bottom centre (...)'"""
    adj = AXES.get(view, ("wide", "tall"))[0 if across else 1]
    if kind == "extra":
        return f"the model is {_fmt(gap, unit)} too {adj} at the {where}"
    return f"the reference has {_fmt(gap, unit)} more at the {where} (the model is too {SHORT[adj]} there)"


def _kth(vals, k):
    """the k-th largest (the smallest when there are fewer than k): its index into vals"""
    order = np.argsort(vals)[::-1]
    return int(order[min(k, len(order)) - 1])


def _summarise(sel, gap, kind, across, k):
    """the K-th largest gap of one kind among the selected samples -> (gap px, index of that sample, across?)"""
    idx = np.nonzero(sel & (kind > 0))[0], np.nonzero(sel & (kind < 0))[0]
    out = []
    for ix in idx:
        if not len(ix):
            out.append((0.0, -1, True))
            continue
        top = ix[np.argsort(gap[ix])[::-1][:k]]
        j = ix[_kth(gap[ix], k)]
        out.append((float(gap[j]), int(j), bool(np.mean(across[top]) >= 0.5)))
    return out


def edge_gaps(model, ref, per_px, unit="mm", view="side", tol=None, regions=(), k=K):
    """-> (facts dict, marks for annotate). per_px: the model's size of one pixel of this frame (mm or studs).
    tol: beyond it a window is named (default: 3 mm or 2% of the view's size, whichever is bigger; in studs, 2%).
    regions: [{"name": ..., "box": [row0, col0, row1, col1]}] in this frame's pixels — each gets its own gap."""
    model, ref = close(np.asarray(model, bool)), close(np.asarray(ref, bool))
    # the openings, before the holes are filled: see-through on one side, solid on the other
    hm, hr_ = enclosed(model), enclosed(ref)
    open_extra, open_missing = hm & ref, hr_ & model  # (the model's holes where the reference is solid, and back)
    model, ref = model | hm, ref | hr_
    em, er = edge(model), edge(ref)
    my, mx = np.nonzero(em)
    ry, rx = np.nonzero(er)
    dm, qmy, qmx = nearest(er, my, mx)  # each model-edge pixel -> the nearest reference-edge pixel
    dr, qry, qrx = nearest(em, ry, rx)  # each reference-edge pixel -> the nearest model-edge pixel
    # +1: the model has shape there the reference does not (extra); -1: the reference has more (missing)
    km = np.where(ref[my, mx], -1, 1)
    kr = np.where(model[ry, rx], 1, -1)
    ys, xs = np.concatenate([my, ry]), np.concatenate([mx, rx])
    gap = np.concatenate([dm, dr])
    kind = np.concatenate([km, kr])
    # the points on each side: the model's edge point and the reference's
    mpy, mpx = np.concatenate([my, qry]), np.concatenate([mx, qrx])
    rpy, rpx = np.concatenate([qmy, ry]), np.concatenate([qmx, rx])
    finite = np.isfinite(gap)
    gap = np.where(finite, gap, 0.0)
    across = np.abs(mpx - rpx) >= np.abs(mpy - rpy)  # the gap runs mostly across the picture (wide / long)
    both = model | ref
    if not both.any():
        return {"unit": unit, "note": "both silhouettes are empty", "tolerance": 0.0, "mean": 0.0, "max": 0.0,
                "windows": [], "worst": []}, []
    by, bx = np.nonzero(both)
    y0, y1, x0, x1 = by.min(), by.max() + 1, bx.min(), bx.max() + 1
    size = max(y1 - y0, x1 - x0) * per_px
    if tol is None:
        tol = max(3.0 if unit == "mm" else 0.0, 0.02 * size)
    wi = np.clip((ys - y0) * 3 // max(1, y1 - y0), 0, 2)
    wj = np.clip((xs - x0) * 3 // max(1, x1 - x0), 0, 2)
    windows, entries = [], []
    for i in range(3):
        for j in range(3):
            sel = (wi == i) & (wj == j) & finite
            if not sel.any():
                continue
            (ge, je, ae), (gm, jm, am) = _summarise(sel, gap, kind, across, k)
            row = {"place": place(i, j, view), "extra": round(ge * per_px, 1 if unit == "mm" else 3),
                   "missing": round(gm * per_px, 1 if unit == "mm" else 3), "edge_px": int(sel.sum())}
            windows.append(row)
            for g_, j_, a_, kind_ in ((ge, je, ae, "extra"), (gm, jm, am, "missing")):
                if j_ >= 0 and g_ * per_px > tol:
                    entries.append({"kind": kind_, "across": a_, "i": i, "j": j, "gap": g_ * per_px, "at": j_})
    worst, marks = [], []
    for e in sorted(_merge(entries), key=lambda e: -e["gap"]):
        worst.append(words(e["kind"], e["gap"], place(e["i"], e["j"], view), e["across"], view, unit))
        j_ = e["at"]
        marks.append({"m": (int(mpy[j_]), int(mpx[j_])), "r": (int(rpy[j_]), int(rpx[j_])), "kind": e["kind"],
                      "window": (e["i"], e["j"]), "box": (int(y0), int(y1), int(x0), int(x1))})
    reg_rows = []
    for reg in regions or ():
        r0, c0, r1, c1 = reg["box"]
        sel = (ys >= r0) & (ys < r1) & (xs >= c0) & (xs < c1) & finite
        if not sel.any():
            reg_rows.append({"region": reg["name"], "note": "no edge of either silhouette in it"})
            continue
        (ge, je, ae), (gm, jm, am) = _summarise(sel, gap, kind, across, k)
        row = {"region": reg["name"], "extra": round(ge * per_px, 1 if unit == "mm" else 3),
               "missing": round(gm * per_px, 1 if unit == "mm" else 3)}
        said = [words(kn, g_ * per_px, f"region '{reg['name']}'", a_, view, unit)
                for g_, j_, a_, kn in ((ge, je, ae, "extra"), (gm, jm, am, "missing")) if j_ >= 0 and g_ * per_px > tol]
        row["ok"] = not said
        if said:
            row["how"] = said
        reg_rows.append(row)
    seen = gap[finite] * per_px
    facts = {"unit": unit, "per_px": round(float(per_px), 5), "view_size": round(float(size), 1),
             "tolerance": round(float(tol), 2), "mean": round(float(seen.mean()), 2) if len(seen) else 0.0,
             "p95": round(float(np.percentile(seen, 95)), 2) if len(seen) else 0.0,
             "max": round(max((max(w["extra"], w["missing"]) for w in windows), default=0.0), 2),
             "windows": windows, "worst": worst}
    if reg_rows:
        facts["regions"] = reg_rows
    # openings, window by window, in area (mm2 or studs2): a see-through slot the reference does not have (extra), or
    # one it has that the model filled (missing) — the IoU and the inside-lines check judge them; listed here for where
    oy, ox = np.nonzero(open_extra | open_missing)
    if len(oy):
        area = float(per_px) ** 2
        ops = []
        for i in range(3):
            for j in range(3):
                win = np.zeros_like(open_extra)
                win[y0 + (y1 - y0) * i // 3: y0 + (y1 - y0) * (i + 1) // 3, x0 + (x1 - x0) * j // 3:
                    x0 + (x1 - x0) * (j + 1) // 3] = True
                e_, m_ = int((open_extra & win).sum()), int((open_missing & win).sum())
                if e_ or m_:
                    ops.append({"place": place(i, j, view), "extra_area": round(e_ * area, 1),
                                "missing_area": round(m_ * area, 1)})
        facts["openings"] = ops
    return facts, marks


def regions_in_frame(trace, regions, xf, px=2048):
    """refs/<asset>.regions.json boxes (pixels of the traced picture) -> [{"name", "box": [row0, col0, row1, col1]}]
    in the normalised frame of the trace's mask: rbx_precision.trace_mask(trace, px) normalised with transform xf =
    (row0, col0, scale, y0, x0) (rbx_precision._normalise_xf). The picture -> design units step is colour_match's
    (the trace's frame: x0, y1, length_px, front). -> (boxes, note: why there are none, or None)"""
    fr, src = trace.get("frame") or {}, (trace.get("source") or "").replace("\\", "/")
    if regions.get("image", "").replace("\\", "/") != src or not {"x0", "y1", "length_px"} <= set(fr):
        return [], f"the regions are drawn on {regions.get('image')}, this view's trace on {src}: not one picture"
    hr = max(float(trace.get("height_ratio", 0.3)), 0.01)
    hpx = max(8, int(px * hr))  # (trace_mask's rows)
    L, x0, y1 = float(fr["length_px"]), float(fr["x0"]), float(fr["y1"])
    row0, col0, s, oy, ox = xf
    out = []
    for reg in regions.get("regions", []):
        bx0, by0, bx1, by1 = reg["box"]
        us = sorted(((1 - (b - x0) / L) if trace.get("front") == "left" else (b - x0) / L) for b in (bx0, bx1))
        hs = sorted((y1 - b) / L for b in (by0, by1))
        rows = [((1 + (hr - h) / hr * hpx) - row0) * s + oy for h in (hs[1], hs[0])]
        cols = [((1 + u * px) - col0) * s + ox for u in us]
        out.append({"name": reg["name"], "box": [int(rows[0]), int(cols[0]), int(rows[1]) + 1, int(cols[1]) + 1]})
    return out, None


def _line(img, a, b, colour, width=2):
    n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
    yy = np.linspace(a[0], b[0], n).round().astype(int)
    xx = np.linspace(a[1], b[1], n).round().astype(int)
    h, w = img.shape[:2]
    for dy in range(-(width // 2), width - width // 2):
        for dx in range(-(width // 2), width - width // 2):
            ok = (yy + dy >= 0) & (yy + dy < h) & (xx + dx >= 0) & (xx + dx < w)
            img[yy[ok] + dy, xx[ok] + dx, :3] = colour


def annotate(diff, marks, box=None, flagged_only=False):
    """draw onto reference_match's diff picture (n x n x 4, top row first): the 3 x 3 windows (thin grey), each
    window beyond the tolerance framed in yellow, and each named gap as a yellow line from one edge to the other
    with a white dot where the model's edge is"""
    if box is None and marks:
        box = marks[0]["box"]
    if box is None:
        return diff
    y0, y1, x0, x1 = box
    grey, yellow, white = (0.42, 0.42, 0.45), (1.0, 0.85, 0.1), (1.0, 1.0, 1.0)
    if not flagged_only:
        for t in range(4):
            yl = int(y0 + t * (y1 - y0) / 3)
            xl = int(x0 + t * (x1 - x0) / 3)
            _line(diff, (min(yl, diff.shape[0] - 1), x0), (min(yl, diff.shape[0] - 1), x1 - 1), grey, 1)
            _line(diff, (y0, min(xl, diff.shape[1] - 1)), (y1 - 1, min(xl, diff.shape[1] - 1)), grey, 1)
    for mk in marks:
        i, j = mk["window"]  # (None: a whole column / row)
        ia, ib = (0, 3) if i is None else (i, i + 1)
        ja, jb = (0, 3) if j is None else (j, j + 1)
        a0, a1 = int(y0 + ia * (y1 - y0) / 3), int(y0 + ib * (y1 - y0) / 3) - 1
        b0, b1 = int(x0 + ja * (x1 - x0) / 3), int(x0 + jb * (x1 - x0) / 3) - 1
        for p, q in (((a0, b0), (a0, b1)), ((a1, b0), (a1, b1)), ((a0, b0), (a1, b0)), ((a0, b1), (a1, b1))):
            _line(diff, p, q, yellow, 3)
        _line(diff, mk["m"], mk["r"], yellow, 3)
        cy, cx = mk["m"]
        diff[max(cy - 4, 0):cy + 5, max(cx - 4, 0):cx + 5, :3] = white
    return diff
