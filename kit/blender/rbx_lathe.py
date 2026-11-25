"""rbx_lathe.py — a generated ROUND body made truly round, and its colour bands read from the views (owner 2026-10-16,
batch 2 "still bad": the made extinguisher's red body streaked and its dome chrome, the barrel's hoops only in patches
— a generator's shape of a round object is lumpy, ±5-15% per slice, and its texture smears a hoop into blotches).

true_round(V, up): the mesh cut into height slices; a slice whose outer outline is a circle within the lumps (a barrel,
an extinguisher's body, a lamp's post — never a square lantern, a hexagonal one stays too) is mapped radially onto
its fitted circle: the outer surface lands exactly on r(h), everything inside scales with it (a recessed lid keeps
its depth); parts sticking OUT of the circle (a bracket, a hose, a handle) are left where they are. Pure numpy.

bands(rgba, slices): the view's rows at the slices' heights -> the colour family most of each row is (a hoop's row is
all grey, a lantern's row half panes half frame: no band). Pure numpy.
"""

import numpy as np

SLICES = 80             # height slices (1.25% of the height each: a barrel's hoop is ~3%)
BINS = 48               # angle bins round each slice
ROUND_TOL = 0.06        # a round slice: >= ROUND_SHARE of its bins within ±6% of the fitted circle
ROUND_SHARE = 0.8       #   (a square's bins swing ±17%, a hexagon's ±7%: both stay as they are)
STICK_OUT = 1.12        # a bin beyond 1.12 r is an appendage (a bracket, a hose): never pulled in
BAND_SHARE = 0.6        # a row is a band when >= 60% of its pixels are one colour family


def _circle(x, y):
    """least-squares circle through points (Kasa) -> (cx, cy, r)"""
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x * x + y * y
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    return cx, cy, float(np.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0)))


def _outer(px, py, cx, cy, bins=BINS):
    """the outermost radius in each angle bin round (cx, cy) (NaN: an empty bin)"""
    ang = np.arctan2(py - cy, px - cx)
    rad = np.hypot(px - cx, py - cy)
    k = ((ang + np.pi) / (2 * np.pi) * bins).astype(np.int64) % bins
    out = np.full(bins, np.nan)
    np.fmax.at(out, k, rad)
    return out


def slices(V, up=2, n=SLICES):
    """the mesh's height slices -> [{t0, t1, round, cx, cy, r, outer (BINS,)}] in its own units (up: the up axis)"""
    h = V[:, up]
    lo, hi = float(h.min()), float(h.max())
    span = max(hi - lo, 1e-9)
    ax = [i for i in range(3) if i != up]
    out = []
    for k in range(n):
        t0, t1 = k / n, (k + 1) / n
        m = (h >= lo + t0 * span) & ((h < lo + t1 * span) if k < n - 1 else (h <= hi))
        s = {"t0": t0, "t1": t1, "round": False, "cx": 0.0, "cy": 0.0, "r": 0.0, "outer": np.full(BINS, np.nan)}
        if m.sum() >= BINS:
            px, py = V[m, ax[0]], V[m, ax[1]]
            cx, cy = float(np.median(px)), float(np.median(py))
            for _ in range(3):   # (outer points only: a circle fitted to every vertex finds a lid's centre, not the rim)
                o = _outer(px, py, cx, cy)
                ok = np.isfinite(o)
                if ok.sum() < BINS // 2:
                    break
                med = np.nanmedian(o)
                keep = ok & (o < STICK_OUT * med)   # (an appendage's bins do not pull the circle)
                ang = (np.arange(BINS) + 0.5) / BINS * 2 * np.pi - np.pi
                cx, cy, r = _circle(cx + o[keep] * np.cos(ang[keep]), cy + o[keep] * np.sin(ang[keep]))
            o = _outer(px, py, cx, cy)
            body = np.isfinite(o) & (o < STICK_OUT * r)
            within = body & (np.abs(o - r) <= ROUND_TOL * r)
            s.update(cx=cx, cy=cy, r=r, outer=o,
                     round=bool(r > 0 and body.sum() >= BINS // 2 and within.sum() >= ROUND_SHARE * body.sum()))
        out.append(s)
    return out


def _runs_only(flags, min_run=3):
    """True runs shorter than min_run slices dropped (a lone 'round' slice in a lantern is luck, not a body)"""
    f = np.asarray(flags, bool).copy()
    i = 0
    while i < len(f):
        if f[i]:
            j = i
            while j < len(f) and f[j]:
                j += 1
            if j - i < min_run:
                f[i:j] = False
            i = j
        else:
            i += 1
    return f


def true_round(V, up=2, n=SLICES):
    """V (k,3) -> (V' (k,3), facts): every round slice's vertices mapped radially so its outer outline is the fitted
    circle (a straight axis through the round slices' centres; r(h) their radii, median-smoothed); appendages and the
    slices that are not round untouched, a two-slice ramp between."""
    V = np.asarray(V, np.float64)
    S = slices(V, up, n)
    rnd = _runs_only([s["round"] for s in S])
    facts = {"slices": n, "round_share": round(float(rnd.mean()), 3)}
    if rnd.sum() < 3:
        facts["moved"] = 0
        return V.copy(), facts
    h = V[:, up]
    lo, span = float(h.min()), max(float(np.ptp(h)), 1e-9)
    ax = [i for i in range(3) if i != up]
    tc = np.array([(s["t0"] + s["t1"]) / 2 for s in S])
    # the axis: a straight line through the round slices' centres
    px = np.polyfit(tc[rnd], [S[i]["cx"] for i in np.where(rnd)[0]], 1)
    py = np.polyfit(tc[rnd], [S[i]["cy"] for i in np.where(rnd)[0]], 1)
    # r(h): the round slices' radii, median over 3 (a trace jag goes, a hoop's step stays)
    r = np.array([s["r"] for s in S])
    rs = r.copy()
    for i in np.where(rnd)[0]:
        w = [j for j in (i - 1, i, i + 1) if 0 <= j < n and rnd[j]]
        rs[i] = float(np.median(r[w]))
    # the outer radius per (slice, angle bin) round the AXIS, an appendage's bin filled from its neighbours
    grid = np.full((n, BINS), np.nan)
    for i in np.where(rnd)[0]:
        m = (h >= lo + S[i]["t0"] * span) & (h <= lo + S[i]["t1"] * span)
        cx, cy = np.polyval(px, tc[i]), np.polyval(py, tc[i])
        o = _outer(V[m, ax[0]], V[m, ax[1]], cx, cy)
        o[~(o < STICK_OUT * rs[i])] = np.nan
        if np.isfinite(o).sum() >= 3:   # (circular interpolation over the empty / appendage bins)
            k = np.arange(BINS)
            ok = np.isfinite(o)
            o = np.interp(k, np.concatenate([k[ok] - BINS, k[ok], k[ok] + BINS]), np.tile(o[ok], 3))
            grid[i] = o
    # weight per slice: 1 inside a round run, ramped over two slices at its ends
    wgt = np.zeros(n)
    for i in np.where(rnd)[0]:
        d = min([abs(i - j) for j in range(n) if not rnd[j]] or [n])
        wgt[i] = min(1.0, d / 2.0) if d < 2 else 1.0
    # every vertex: its slice position (fractional), angle bin, outer radius there -> the scale onto r(h)
    t = (h - lo) / span
    f = np.clip(t * n - 0.5, 0, n - 1)
    i0 = np.floor(f).astype(np.int64)
    i1 = np.minimum(i0 + 1, n - 1)
    a = f - i0
    cx = np.polyval(px, t)
    cy = np.polyval(py, t)
    dx, dy = V[:, ax[0]] - cx, V[:, ax[1]] - cy
    rho = np.hypot(dx, dy)
    kb = (((np.arctan2(dy, dx) + np.pi) / (2 * np.pi) * BINS).astype(np.int64)) % BINS
    out = V.copy()
    new_rho = rho.copy()
    for ii, aa in ((i0, 1 - a), (i1, a)):
        g = grid[ii, kb]
        ok = np.isfinite(g) & rnd[ii] & (g > 0)
        gg = np.where(ok, g, 1.0)
        # the outer SKIN (within 15% of the bin's outer radius) lands exactly on r(h) — scaled by its bin's outermost
        # vertex only, the lumps between neighbouring vertices stayed; what lies deeper (a recessed lid) scales with it
        skin = np.clip((rho / gg - 0.85) / 0.1, 0.0, 1.0)
        tgt = (1 - skin) * rho * rs[ii] / gg + skin * rs[ii]
        # (an appendage — beyond the slice's outer body radius — keeps its place)
        tgt = np.where(ok & (rho <= STICK_OUT * rs[ii]), tgt, rho)
        w_k = np.where(ok, wgt[ii], 0.0)
        new_rho += aa * w_k * (tgt - rho)
    scale = np.where(rho > 1e-12, new_rho / np.maximum(rho, 1e-12), 1.0)
    move = np.abs(scale - 1.0) > 1e-6
    out[:, ax[0]] = cx + dx * scale
    out[:, ax[1]] = cy + dy * scale
    out[~move] = V[~move]
    moved = int(move.sum())
    facts.update(moved=moved, axis_tilt=round(float(np.hypot(px[0], py[0]) / span), 4),
                 largest_move=round(float(np.max(np.abs(scale - 1.0) * rho) / span), 4))
    facts["profile"] = [[round(float(tc[i]), 4), round(float(rs[i] / span), 4)] for i in np.where(rnd)[0]]
    return out, facts


NEUTRAL_RATIO = 0.2     # chroma / max channel below this: a neutral (steel, black paint, a white pane) at ANY light


def _kind(rgb):
    """(n,3) sRGB -> (neutral (n,) bool, hue deg (n,), luminance (n,)) — the light-independent part of a colour: the
    concept's barrel is lit from above, its hoops (75,75,73) at the bottom and (189,190,190) at the top, its shadowed
    wood (42,33,23): matched by shade, the bottom hoop went to the wood"""
    rgb = np.asarray(rgb, np.float64).reshape(-1, 3)
    hi, lo = rgb.max(axis=1), rgb.min(axis=1)
    chroma = hi - lo
    neutral = (hi < 25) | (chroma < NEUTRAL_RATIO * np.maximum(hi, 1e-9))
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    c = np.maximum(chroma, 1e-9)
    hue = np.where(hi == r, (60 * (g - b) / c) % 360, np.where(hi == g, 60 * (b - r) / c + 120, 60 * (r - g) / c + 240))
    return neutral, hue, 0.2126 * r + 0.7152 * g + 0.0722 * b


def match_families(rgb, families):
    """each pixel -> the family of ITS KIND nearest it: a neutral pixel to the nearest neutral family by luminance, a
    coloured one to the nearest coloured family by hue; a kind no family has -> the nearest shade (rbx_regions)"""
    import rbx_regions  # noqa: PLC0415

    rgb = np.asarray(rgb, np.float64).reshape(-1, 3)
    fam = []
    for members in families:
        members = np.asarray(members if isinstance(members[0], (list, tuple)) else [members], np.float64)
        n_, h_, l_ = _kind(members)
        neu = n_.mean() >= 0.5
        hh = h_[~n_] if (~n_).any() else h_
        hue = float(np.degrees(np.arctan2(np.sin(np.radians(hh)).mean(), np.cos(np.radians(hh)).mean())) % 360)
        fam.append((neu, hue, float(l_.mean())))
    out = rbx_regions.nearest_family(rgb, families)
    neutral, hue, lum = _kind(rgb)
    neu_f = [i for i, f in enumerate(fam) if f[0]]
    col_f = [i for i, f in enumerate(fam) if not f[0]]
    if neu_f:
        d = np.abs(lum[:, None] - np.array([fam[i][2] for i in neu_f])[None, :])
        out = np.where(neutral, np.asarray(neu_f)[d.argmin(axis=1)], out)
    if col_f:
        dh = np.abs(hue[:, None] - np.array([fam[i][1] for i in col_f])[None, :]) % 360
        dh = np.minimum(dh, 360 - dh)
        out = np.where(~neutral, np.asarray(col_f)[dh.argmin(axis=1)], out)
    return out


def bands(rgba, n=SLICES, families=None, share=BAND_SHARE, core=0.6):
    """the view's object rows at each height slice -> [family index | None] (n,): a row whose middle `core` of its
    width is >= `share` one family (rbx_regions.nearest_family against `families`: lists of sRGB shades) — a barrel's
    hoop row all grey -> the steel, a lantern row half pane half frame -> None (its faces keep their own colour).
    rgba: (h, w, 4) uint8, the cut-out view; slice 0 = the object's BOTTOM."""
    a = rgba[..., 3] > 127
    rows = np.where(a.any(axis=1))[0]
    out = [None] * n
    if len(rows) < n // 4 or not families:
        return out
    top, bot = int(rows.min()), int(rows.max())
    hpx = max(bot - top, 1)
    for k in range(n):
        y0 = int(round(bot - (k + 1) / n * hpx))
        y1 = int(round(bot - k / n * hpx))
        pix = []
        for y in range(max(y0, top), min(y1, bot) + 1):
            cols = np.where(a[y])[0]
            if len(cols) < 4:
                continue
            c0, c1 = cols.min(), cols.max()
            pad = (c1 - c0) * (1 - core) / 2
            sel = cols[(cols >= c0 + pad) & (cols <= c1 - pad)]
            pix.append(rgba[y, sel, :3])
        if not pix:
            continue
        p = np.concatenate(pix).astype(np.float64)
        lab = match_families(p, families)
        cnt = np.bincount(lab, minlength=len(families))
        if cnt.max() >= share * len(lab):
            out[k] = int(cnt.argmax())
    # (a band one slice tall between two others is a highlight or a seam: it takes its neighbours' when they agree)
    for k in range(1, n - 1):
        if out[k - 1] is not None and out[k - 1] == out[k + 1] and out[k] != out[k - 1]:
            out[k] = out[k - 1]
    return out


def staves(V, profile, up=2, n=30, depth=0.006, width=0.006):
    """a ROUND wooden body's staves: shallow grooves pressed into its trued skin at n equal angles (a wine barrel has
    ~30 staves; the made barrel read as one smooth beige drum). Only vertices on the skin of its round slices move
    (within 3% of r(h): a lid, a hoop's inner face stay); each groove a smooth dip `depth` x r deep, `width` x the
    circumference wide each side. profile: true_round's facts["profile"] ([t, r / height] per round slice).
    -> (V', grooved vertex count)"""
    V = np.asarray(V, np.float64)
    if not profile or n < 3:
        return V.copy(), 0
    h = V[:, up]
    lo, span = float(h.min()), max(float(np.ptp(h)), 1e-9)
    t = (h - lo) / span
    tp = np.array([p[0] for p in profile])
    rp = np.array([p[1] for p in profile]) * span
    ax = [i for i in range(3) if i != up]
    # the axis: the round slices' skin centre (true_round left it straight); robustly the bbox centre of the round band
    band = (t >= tp.min()) & (t <= tp.max())
    cx = (V[band, ax[0]].min() + V[band, ax[0]].max()) / 2
    cy = (V[band, ax[1]].min() + V[band, ax[1]].max()) / 2
    dx, dy = V[:, ax[0]] - cx, V[:, ax[1]] - cy
    rho = np.hypot(dx, dy)
    r = np.interp(t, tp, rp)
    gap = np.abs(np.diff(tp)).max() if len(tp) > 1 else 1.0
    near = np.min(np.abs(t[:, None] - tp[None, :]), axis=1) <= max(gap, 1.0 / len(tp))
    skin = band & near & (np.abs(rho - r) <= 0.03 * r)
    ang = np.arctan2(dy, dx)
    step = 2 * np.pi / n
    d = np.abs(((ang + step / 2) % step) - step / 2) / (2 * np.pi)   # (distance to the nearest groove, in turns)
    dip = np.clip(1 - (d / width) ** 2, 0, 1) * depth * r
    k = np.where(skin & (dip > 0), (rho - dip) / np.maximum(rho, 1e-12), 1.0)
    out = V.copy()
    out[:, ax[0]] = cx + dx * k
    out[:, ax[1]] = cy + dy * k
    return out, int((k < 1).sum())
