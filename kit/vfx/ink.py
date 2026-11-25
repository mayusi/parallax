"""ink.py — traced drawings into a sprite sheet: the drawn effect at the size Roblox shows (the owner's VFX method
list, 2026-11-13: "Hand-drawn effects animation", "Frame-by-frame effects", "SDF effects"; the VFX studio-route plan's
V3, its ink half). The trace (kit/vfx/shapetrace.py) reads a scene's drawings into curves; this draws them again.

    lune run kit vfx ink <key> --from <trace.json> [--drawings 3-9] [--cell 256] [--register beat|drawing]
                                [--between 1] [--loop] [--gray] [--line 2]
    python kit/vfx/ink.py --specs assets/textures --out build/fxlab [name ...]      (the build step: `kit vfx` runs it)
    lune run kit vfx ink <key> --grammar flame_tongue|slash_crescent|sakuga_smoke|kanada_bolt|liquid_splash
                               (--from <trace.json> | --metrics area,speed,cutout) [--frames 64] [--rhythm 2]
                    (a NEW drawing by a sakuga grammar, sized and timed by a trace's numbers: kit/vfx/inkgrammar.py)
    (--specs-dir / --frames-dir / --look-dir / --kept-dir <folder>: other folders than the project's own - a game's, a test's)

What it does:
  1. the window   --register beat (default): ONE square window round all the chosen drawings - every drawing sits
                  where the scene put it, so the motion inside the sheet is the scene's. --register drawing: every
                  drawing centred in its cell at ONE scale (the largest drawing's): for a card the preset moves itself.
                  The window is as small as holds them, so the drawing FILLS its cell (said as `fill`)
  2. the drawing  each drawing's curves drawn at the cell's own size (never a picture scaled up), in the trace's flat
                  tones, darkest first; --gray: the tones as greys, the lightest white (a sheet the preset tints);
                  --line N: an ink line N px wide inside the silhouette's edge
  3. in-betweens  --between N puts N drawings between each two (a plain cross-fade would be two ghosts). When the two
                  drawings are the SAME PIECES (as many pieces, as many cut-outs in each) the in-between is made point
                  to point, the way an animator does it: the outlines are laid out so a sharp point meets a sharp
                  point, every point moves its share of the way, and the shape is grown to the area an in-between
                  should have (it neither swells nor shrinks on the way). When they are not the same pieces it is
                  made from the two drawings' DISTANCE fields (mixed, the outline taken where the area is right):
                  that handles a piece splitting off, and it rounds a drawn point - the summary says how many pairs
                  went that way; two such drawings that barely overlap are refused (a blend, not a drawing)
                  --loop: the last drawing's in-betweens lead back to the first (a sheet that plays round)
  4. the cells    one cell per DRAWING, never per frame (a held drawing is one cell: the flipbook's rate holds it)
                  -> build/fxlab/<key>/NNN.npy, the frames the kit's sheet packer (kit/vfx/fxfinish.py) packs, checks
                  and registers like every other sheet; and the spec assets/textures/<key>.json (recipe "ink").
                  ONLY from a KEPT trace (assets/effects/refs_measured/, shapetrace --keep - after the owner's yes to
                  keeping curves): a spec must be able to ink its sheet again, and build/ is not in the repo. From any
                  other trace this makes the LOOK picture and says so: a look, no texture
  5. the checks   fill (the largest drawing uses at least FILL of its cell), empty (no cell is almost empty), full (as
                  many cells as the sheet has: the engine plays EVERY cell, an empty one is a blank frame - 1, 2, 4, 8,
                  16, 32 or 64), clear (nothing reaches a cell's edge), hard (the edge is a pixel or two wide: a drawn
                  shape, not a soft one), flat (the colours inside are the tones or a mix of two of them), moves (two
                  neighbouring cells are never the same), volume (an in-between has the area it was made for)
  6. LOOK         build/vfx/ink/<key>_strip.png: every cell large over a dark and a light ground, in-betweens marked

Play it as the drawings were held: `"flipbook": {"layout": [cols, rows], "mode": "Loop", "fps": <said in the
summary>, "blend": false}` - with blend on, the engine cross-fades two drawings into a ghost of both; with the mode
left out (OneShot) the engine spreads the cells over the particle's life and the rate means nothing.
Limits, said plainly: a flipbook has ONE rate, so drawings held 2, 2, 1, 3 frames in the scene play evenly at the
middle hold's rate; the sheet is only as good as the trace it is drawn from (LOOK at the trace's pictures first).
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import hashlib
import json
import math
import os
import re
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shapetrace as T  # noqa: E402

SPECS = os.path.join("assets", "textures")
FRAMES = os.path.join("build", "fxlab")
LOOK = os.path.join("build", "vfx", "ink")

MARGIN = 0.06       # of the cell, kept clear on every side (mipmaps must not bleed one cell into the next)
FILL = 0.06         # the largest drawing must cover this share of its cell (the 2026-11-13 flame tongue: 0.02)
OVERLAP = 0.25      # two drawings sharing less than this (intersection over union) are not one shape to in-between
SOFT = 3.0          # half-transparent pixels per pixel of outline: over this the edge is soft, not drawn
SS = 2              # in-betweens are made this many times larger than the cell, then brought down
GROW = (0.8, 1.25)  # a point-to-point in-between that must be grown or shrunk past this has collapsed on its way
EMPTY = 0.003       # a cell whose drawing covers under this share of it is almost empty
KEPT = os.path.join("assets", "effects", "refs_measured")     # where a KEPT trace lives (shapetrace --keep)
COUNTS = (1, 2, 4, 8, 16, 32, 64)                              # the cell counts that fill a sheet
GRIDS = ((1, 1), (2, 1), (2, 2), (4, 2), (4, 4), (8, 4), (8, 8))


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


# ------------------------------------------------------------------ the window
def windows(drawings, cell, register="beat", margin=MARGIN):
    """-> [(scale, (ox, oy))] per drawing: a trace point p lands at (p + offset) * scale in the cell (see the head, 1)"""
    boxes = np.array([d["box"] for d in drawings], dtype=np.float64)
    room = cell * (1.0 - 2.0 * margin)
    if register == "drawing":
        side = float(max((boxes[:, 2] - boxes[:, 0]).max(), (boxes[:, 3] - boxes[:, 1]).max()))
        scale = room / max(side, 1e-6)
        mids = [((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) for b in boxes]
    else:
        x0, y0, x1, y1 = boxes[:, 0].min(), boxes[:, 1].min(), boxes[:, 2].max(), boxes[:, 3].max()
        scale = room / max(x1 - x0, y1 - y0, 1e-6)
        mids = [((x0 + x1) / 2.0, (y0 + y1) / 2.0)] * len(drawings)
    half = cell / 2.0 / scale
    return [(scale, (half - mx, half - my)) for mx, my in mids]


def covers(drawing, tones, size, scale, offset):
    """one drawing -> {tone index: (size, size) coverage 0..1} of its cumulative layers at this size"""
    return {L["tone"]: T.fill(L["shapes"], (size, size), scale, offset) for L in drawing["layers"]
            if 0 <= L["tone"] < len(tones)}


# ------------------------------------------------------------------ in-betweens
def signed(cover):
    """coverage -> signed distance in px: negative inside the shape, positive outside (0 on its edge)"""
    inside = cover >= 0.5
    if not inside.any():
        return np.full(cover.shape, float(max(cover.shape)), dtype=np.float32)
    if inside.all():
        return np.full(cover.shape, -float(max(cover.shape)), dtype=np.float32)
    away = cv2.distanceTransform((~inside).astype(np.uint8), cv2.DIST_L2, 5)
    deep = cv2.distanceTransform(inside.astype(np.uint8), cv2.DIST_L2, 5)
    return (away - deep + np.where(inside, 0.5, -0.5)).astype(np.float32)


def level_for(field, area, rounds=40):
    """the level c at which the shape {field < c} has `area` pixels (the field's outline moved in or out until the
    shape is as large as asked)"""
    lo, hi = float(field.min()) - 1.0, float(field.max()) + 1.0
    for _ in range(rounds):
        mid = (lo + hi) / 2.0
        if float(np.clip(0.5 - (field - mid), 0.0, 1.0).sum()) < area:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def between(a, b, u):
    """two coverages of one layer (at SS times the cell) -> the in-between at u (0 = a, 1 = b): the distance fields
    mixed, the outline put where the shape has the area an in-between should have (see the head, 3)"""
    area = (1.0 - u) * float(a.sum()) + u * float(b.sum())
    if area < 1.0:
        return np.zeros_like(a)
    field = (1.0 - u) * signed(a) + u * signed(b)
    return np.clip(0.5 - (field - level_for(field, area)), 0.0, 1.0).astype(np.float32)


def overlap(a, b):
    a, b = a >= 0.5, b >= 0.5
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum()) / float(union) if union else 1.0


# ... by the CURVES, when the two drawings are the same pieces: point to point, the way an animator in-betweens
RING = 240          # points a matched outline is laid out in


def _dense(ring, scale, offset):
    """a trace ring (points, corner flags) in the cell -> (its outline about 1 px a point, the indices of its corners)"""
    pts, flags = ring
    return T.outline((np.asarray(pts, dtype=np.float64) + np.asarray(offset, dtype=np.float64)) * scale, flags)


def _lay(poly, start, stop, count):
    """`count` points evenly along a closed outline from index start to index stop (going forward, wrapping)"""
    n = len(poly)
    idx = [(start + k) % n for k in range(((stop - start) % n or n) + 1)]
    run = poly[idx]
    step = np.hypot(*(run[1:] - run[:-1]).T)
    at = np.concatenate([[0.0], np.cumsum(step)])
    where = np.linspace(0.0, at[-1], count, endpoint=False)
    return np.stack([np.interp(where, at, run[:, 0]), np.interp(where, at, run[:, 1])], axis=1)


def pair_rings(a, b, scale_a, off_a, scale_b, off_b, count=RING):
    """two outlines of one shape -> (A, B): the same number of points each, laid out so point k of A is point k of B.
    With the same number of sharp points on both, a sharp point meets a sharp point (a tip stays a tip in between);
    else the two are turned against each other until they lie closest"""
    pa, ca = _dense(a, scale_a, off_a)
    pb, cb = _dense(b, scale_b, off_b)
    if _turning(pa) * _turning(pb) < 0:                       # drawn the other way round (a foreign trace): turn it
        b = (np.asarray(b[0])[::-1], np.asarray(b[1])[::-1])
        pb, cb = _dense(b, scale_b, off_b)
    if ca and len(ca) == len(cb):
        k = len(ca)
        ma, mb = pa.mean(axis=0), pb.mean(axis=0)
        best = min(range(k), key=lambda r: sum(float(((pa[ca[j]] - ma - (pb[cb[(j + r) % k]] - mb)) ** 2).sum()) for j in range(k)))
        A, B = [], []
        for j in range(k):
            a0, a1 = ca[j], ca[(j + 1) % k]
            b0, b1 = cb[(j + best) % k], cb[(j + 1 + best) % k]
            la, lb = ((a1 - a0) % len(pa)) or len(pa), ((b1 - b0) % len(pb)) or len(pb)
            m = max(2, int(round(count * (la / float(len(pa)) + lb / float(len(pb))) / 2.0)))
            A.append(_lay(pa, a0, a1, m))
            B.append(_lay(pb, b0, b1, m))
        return np.concatenate(A), np.concatenate(B)
    A = _lay(pa, 0, 0, count)
    B = _lay(pb, 0, 0, count)
    ca0, cb0 = A - A.mean(axis=0), B - B.mean(axis=0)
    shift = min(range(count), key=lambda r: float(((ca0 - np.roll(cb0, -r, axis=0)) ** 2).sum()))
    return A, np.roll(B, -shift, axis=0)


def _mid(ring, scale, offset):
    return ((np.asarray(ring[0], dtype=np.float64) + np.asarray(offset, dtype=np.float64)) * scale).mean(axis=0)


def _match(xs, ys, wa, wb):
    """rings of a and of b paired by the nearest centre -> [(ring a, ring b)] or None when they are not as many"""
    if len(xs) != len(ys):
        return None
    left, pairs = list(range(len(ys))), []
    for x in xs:
        j = min(left, key=lambda q: float(((_mid(x, *wa) - _mid(ys[q], *wb)) ** 2).sum()))
        left.remove(j)
        pairs.append((x, ys[j]))
    return pairs


def pair_shapes(a_shapes, b_shapes, wa, wb):
    """a layer's shapes in two drawings, matched piece to piece and cut-out to cut-out -> [(A outer, B outer,
    [(A hole, B hole), ...])] of paired point lists, or None when the two are not the same pieces (another number of
    pieces, or of cut-outs in a piece): then there is no point-to-point in-between"""
    outers = _match([s["outer"] for s in a_shapes], [s["outer"] for s in b_shapes], wa, wb)
    if outers is None:
        return None
    by_outer = {id(s["outer"]): s for s in list(a_shapes) + list(b_shapes)}
    paired = []
    for oa, ob in outers:
        holes = _match(by_outer[id(oa)]["holes"], by_outer[id(ob)]["holes"], wa, wb)
        if holes is None:
            return None
        paired.append((*pair_rings(oa, ob, *wa, *wb), [pair_rings(ha, hb, *wa, *wb) for ha, hb in holes]))
    return paired


def _turning(poly):
    """a closed outline's area with its sign: which way round it is drawn"""
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum())


def _area(poly):
    return abs(_turning(poly))


def between_curves(paired, u, size, grow=None):
    """a layer's paired outlines -> (its coverage at u, (the factor it was grown by, the point it was grown about),
    the factor it NEEDED): every point moved the share u of its way. grow: None = find the factor that gives the
    in-between the area between its two drawings' (a shape that turns loses area on a straight way) and grow about the
    layer's own middle; a (factor, point) = use that one (the layers inside the silhouette grow with it, about the
    same point). The factor it needed outside GROW means the shape collapsed on its way (it turned too far)"""
    polys, want, have = [], 0.0, 0.0
    for A, B, holes in paired:
        P = (1.0 - u) * A + u * B
        hs = [(1.0 - u) * ha + u * hb for ha, hb in holes]
        want += (1.0 - u) * (_area(A) - sum(_area(h) for h, _ in holes)) + u * (_area(B) - sum(_area(h) for _, h in holes))
        have += _area(P) - sum(_area(h) for h in hs)
        polys.append((P, hs))
    needed = math.sqrt(want / have) if have > 1e-6 and want > 0 else (1.0 if want <= 0 else float("inf"))
    if grow is None:
        grow = (min(max(needed, GROW[0]), GROW[1]), np.concatenate([p for p, _ in polys]).mean(axis=0))
    factor, middle = grow

    def ring(q):
        return (q - middle) * factor + middle, np.ones(len(q), dtype=bool)

    shapes = [{"outer": ring(P), "holes": [ring(h) for h in hs]} for P, hs in polys]
    return T.fill(shapes, (size, size)), grow, needed


# ------------------------------------------------------------------ a cell
def greys(tones):
    """the tones as greys a preset tints: each tone's brightness over the lightest tone's (the lightest is white)"""
    luma = np.asarray(tones, dtype=np.float32) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    g = luma / max(float(luma.max()), 1e-6) * 255.0
    return np.repeat(g[:, None], 3, axis=1)


def paint(layer_covers, tones, line=0):
    """{tone: coverage} -> (H, W, 4) float 0..1: STRAIGHT colour + coverage. The colour is the darkest layer's tone
    everywhere, the lighter layers laid over it; the coverage is the silhouette's. (Colour that already carries the
    coverage, multiplied by it again when packed, was a dark fringe on every edge - a review, 2026-11-13.) line > 0
    draws an ink line that many px wide inside the silhouette's edge (the darkest tone at a quarter of its brightness)"""
    order = sorted(layer_covers)
    alpha = layer_covers[order[0]].astype(np.float32)
    rgb = np.zeros(alpha.shape + (3,), dtype=np.float32) + (np.asarray(tones[order[0]], dtype=np.float32) / 255.0)[None, None]
    for t in order[1:]:
        cov = layer_covers[t]
        rgb = rgb * (1 - cov[..., None]) + (np.asarray(tones[t], dtype=np.float32) / 255.0)[None, None] * cov[..., None]
        alpha = np.maximum(alpha, cov)
    if line > 0:
        edge = np.clip(-signed(alpha), 0.0, None)                        # px inside the silhouette
        ink_line = np.clip(float(line) + 0.5 - edge, 0.0, 1.0) * (alpha > 0.5)
        dark = np.asarray(tones[order[0]], dtype=np.float32) / 255.0 * 0.25
        rgb = rgb * (1 - ink_line[..., None]) + dark[None, None] * ink_line[..., None]
    return np.dstack([rgb, alpha])


def shrink(cover, k):
    """a coverage made k times larger, brought down to the cell (area average)"""
    return cover if k == 1 else cv2.resize(cover, (cover.shape[1] // k, cover.shape[0] // k), interpolation=cv2.INTER_AREA)


# ------------------------------------------------------------------ the sheet
def grid_for(count, cell):
    """the smallest sheet layout that holds `count` cells with both sides a power of two and at most 1024 px ->
    ((cols, rows), cell) - the cell made smaller when the sheet would be too large; None when nothing holds them"""
    for cols, rows in GRIDS:
        if cols * rows >= count:
            c = cell
            while c * cols > 1024 and c > 32:
                c //= 2
            return ((cols, rows), c) if c * cols <= 1024 else None
    return None


def ink(trace, cell=256, register="beat", n_between=0, gray=False, line=0, pick=None, loop=False):
    """a trace (shapetrace.from_json's) -> {"cells": [(H, W, 4) straight RGBA], "kinds": ["drawing" | "between"],
    "grid", "cell", "checks", "fill", "tones", "holds", "by_field", "refused"}: see the head. pick = (first, last)
    drawings, counted from 1; loop: the last drawing's in-betweens lead back to the first"""
    tones = np.asarray(trace["tones"], dtype=np.float32).reshape(-1, 3)
    ds = list(trace["drawings"])
    if pick:
        if pick[1] > len(ds):
            return {"refused": f"--drawings {pick[0]}-{pick[1]}: the trace holds {len(ds)} drawing(s)"}
        ds = ds[pick[0] - 1:pick[1]]
    ds = [d for d in ds if any(0 <= L["tone"] < len(tones) and L["shapes"] for L in d["layers"])]
    if not ds:
        return {"refused": "no drawings to ink (the trace holds none, or none with a tone)"}
    pairs = {}
    if n_between:
        pairs = {i: i + 1 for i in range(len(ds) - 1)}
        if loop and len(ds) > 1:
            pairs[len(ds) - 1] = 0
    count = len(ds) + n_between * len(pairs)
    fit = grid_for(count, int(cell))
    if fit is None:
        return {"refused": f"{count} cells do not fit a sheet of 64 cells: fewer drawings (--drawings a-b) or fewer in-betweens"}
    grid, cell = fit
    wins = windows(ds, cell, register)
    paint_tones = greys(tones) if gray else tones
    big = [covers(d, tones, cell * SS, s * SS, off) for d, (s, off) in zip(ds, wins)] if pairs else None
    zero = np.zeros((cell * SS, cell * SS), dtype=np.float32)
    cells, kinds, areas, loose, by_field = [], [], [], [], 0
    for i, (d, (s, off)) in enumerate(zip(ds, wins)):
        cells.append(paint(covers(d, tones, cell, s, off), paint_tones, line))
        kinds.append("drawing")
        areas.append(None)
        if i not in pairs:
            continue
        j = pairs[i]
        a, b = big[i], big[j]
        la = {L["tone"]: L["shapes"] for L in d["layers"] if L["tone"] in a}
        lb = {L["tone"]: L["shapes"] for L in ds[j]["layers"] if L["tone"] in b}
        wa, wb = wins[i], wins[j]
        base_a, base_b = min(a), min(b)
        # point to point when the two drawings are the same pieces AND the shape does not collapse on its way (it
        # turned too far: the middle in-between would have to be grown past GROW); else by distance fields
        paired = {t: pair_shapes(la[t], lb[t], wa, wb) for t in sorted(set(la) & set(lb))}
        curves = base_a == base_b and paired.get(base_a) is not None
        if curves:
            needed = between_curves(paired[base_a], 0.5, cell)[2]
            curves = GROW[0] <= needed <= GROW[1]
        every = sorted(set(a) | set(b))
        if not curves or any(paired.get(t) is None for t in every):
            by_field += 1
        if not curves:
            share = overlap(a[base_a], b[base_b])
            if share < OVERLAP:
                loose.append((i + 1, j + 1, share))
        for step in range(1, n_between + 1):
            u = step / float(n_between + 1)
            mixed, grow = {}, None
            for t in every:
                if curves and paired.get(t) is not None:
                    mixed[t], g, _ = between_curves(paired[t], u, cell, grow)
                    grow = g if grow is None else grow
                else:
                    mixed[t] = shrink(between(a.get(t, zero), b.get(t, zero), u), SS)
            outer = mixed[every[0]]
            for t in every[1:]:                                  # a tone inside never pokes out of the silhouette
                mixed[t] = np.minimum(mixed[t], outer)
            cells.append(paint(mixed, paint_tones, line))
            kinds.append("between")
            areas.append(((1 - u) * float(a[base_a].sum()) + u * float(b[base_b].sum())) / (SS * SS))
    if loose:
        i, j, share = loose[0]
        return {"refused": f"drawings {i} and {j} are not the same pieces and barely overlap ({share * 100:.0f} % shared): an "
                           f"in-between of them is a blend, not a drawing (no --between there: --drawings a-b)"}
    checks, fill = check(cells, kinds, areas, paint_tones, cell, grid, line)
    return {"cells": cells, "kinds": kinds, "grid": grid, "cell": cell, "checks": checks, "fill": fill,
            "tones": [[int(round(float(c))) for c in t] for t in paint_tones], "holds": [int(d.get("hold", 1)) for d in ds],
            "drawings": len(ds), "by_field": by_field, "cut": [float(d.get("cut", 0.0)) for d in ds], "refused": None}


def off_tones(pixels, tones):
    """(M, 3) colours -> how far each is (of 255) from the nearest tone OR the nearest mix of two tones: where two
    tones meet, the pixel between them is a mix of the two (anti-aliasing), and that is not a foreign colour"""
    px = np.asarray(pixels, dtype=np.float32)
    ts = np.asarray(tones, dtype=np.float32)
    best = np.abs(px[:, None, :] - ts[None]).max(axis=2).min(axis=1)
    for i in range(len(ts)):
        for j in range(i + 1, len(ts)):
            span = ts[j] - ts[i]
            t = np.clip(((px - ts[i]) @ span) / max(float(span @ span), 1e-6), 0.0, 1.0)
            best = np.minimum(best, np.abs(px - (ts[i] + t[:, None] * span)).max(axis=1))
    return best


def check(cells, kinds, areas, tones, cell, grid, line=0):
    """the sheet's own checks (see the head, 5) -> ([{name, ok, value, limit, fix}], fill)"""
    checks = []

    def add(name, ok, value, limit, fix):
        checks.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": "" if ok else fix})

    alphas = [c[..., 3] for c in cells]
    fills = [float((a > 0.5).mean()) for a in alphas]
    fill = max(fills)
    add("fill", fill >= FILL, round(fill, 3), f">= {FILL}",
        "the largest drawing uses almost none of its cell: trace ONE element (--box), or --register drawing")
    add("empty", min(fills) >= EMPTY, [fills.index(min(fills)) + 1, round(min(fills), 4)], f"every cell >= {EMPTY}",
        "a cell is almost empty (its number is given): leave that drawing out (--drawings a-b)")
    add("full", len(cells) == grid[0] * grid[1], [len(cells), grid[0] * grid[1]], "as many cells as the sheet has",
        "the engine plays EVERY cell of a sheet: the empty ones are blank frames. A sheet holds 1, 2, 4, 8, 16, 32 or 64 "
        "cells: choose --drawings a-b; with --between the count fills a sheet only when it loops (--loop)")
    rim = max(1, int(round(cell * 0.02)))
    edge = max(float(max(a[:rim].max(), a[-rim:].max(), a[:, :rim].max(), a[:, -rim:].max())) for a in alphas)
    add("clear", edge <= 0.02, round(edge, 3), "<= 0.02", "a drawing reaches its cell's edge and would be cut there")
    soft = 0.0
    for a in alphas:
        inside = (a > 0.5).astype(np.uint8)
        outline = float(sum(cv2.arcLength(c, True) for c in cv2.findContours(inside, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0]))
        if outline > 0:
            soft = max(soft, float(((a > 0.1) & (a < 0.9)).sum()) / outline)
    add("hard", soft <= SOFT, round(soft, 2), f"<= {SOFT} px of soft edge", "the edge is soft: a drawn shape has a hard one")
    if line <= 0:
        off = 0.0
        for c in cells:
            solid = c[..., 3] > 0.98
            if solid.any():
                off = max(off, float((off_tones(c[solid][:, :3] * 255.0, tones) > 8.0).mean()))
        add("flat", off <= 0.05, round(off, 3), "<= 0.05 of the inside off the tones",
            "colours that are not the trace's tones: a tone edge is soft, or the tones are too many for the drawing")
    if len(cells) > 1:
        still = min(float(np.abs(alphas[i + 1] - alphas[i]).mean()) for i in range(len(cells) - 1))
        add("moves", still > 0.0008, round(still, 5), "> 0.0008", "two neighbouring cells are the same drawing: a sheet "
            "holds each drawing ONCE (the flipbook's rate holds it)")
    drift = 0.0
    for a, want in zip(alphas, areas):
        if want:
            drift = max(drift, abs(float(a.sum()) - want) / want)
    if any(areas):
        add("volume", drift <= 0.04, round(drift, 3), "<= 0.04", "an in-between is not the size it was made for")
    return checks, fill


def premultiplied(cellpx):
    """straight RGBA -> what the sheet packer reads: colour times coverage"""
    px = cellpx.astype(np.float32).copy()
    px[..., :3] *= px[..., 3:4]
    return px


def trace_id(path):
    """a trace file's content as a short id: a sheet inked from it is stale once the trace was made again"""
    with open(path, "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()[:16]


def write_frames(frames_dir, key, cells, spec_path, trace_path):
    fdir = os.path.join(frames_dir, key)
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".npy"):
            os.remove(os.path.join(fdir, f))
    for i, c in enumerate(cells):
        np.save(os.path.join(fdir, f"{i:03d}.npy"), premultiplied(c).astype(np.float16))
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": len(cells), "spec_mtime": os.path.getmtime(spec_path), "engine": "ink",
                   "trace": trace_id(trace_path)}, fh)


def strip(result, path, tile=320):
    """the LOOK picture: every cell `tile` px or more, over a dark ground (top) and a light one (bottom), in order;
    an in-between is marked"""
    cells = result["cells"]
    per_row = min(len(cells), 6)
    rows = int(math.ceil(len(cells) / float(per_row)))
    head = 22
    page = Image.new("RGB", (per_row * (tile + 6) + 6, rows * (2 * tile + head + 10) + 6), (20, 20, 24))
    pen = ImageDraw.Draw(page)
    for i, c in enumerate(cells):
        r, col = divmod(i, per_row)
        x, y = 6 + col * (tile + 6), 6 + r * (2 * tile + head + 10)
        kind = result["kinds"][i]
        pen.text((x + 2, y + 4), f"cell {i + 1}" + ("  (in-between)" if kind == "between" else ""),
                 fill=(255, 190, 90) if kind == "between" else (225, 225, 225))
        px = cv2.resize(c, (tile, tile), interpolation=cv2.INTER_NEAREST if tile % c.shape[0] == 0 else cv2.INTER_LINEAR)
        for k, ground in enumerate((0.10, 0.82)):
            over = ground * (1 - px[..., 3:]) + px[..., :3] * px[..., 3:]
            page.paste(Image.fromarray((np.clip(over, 0, 1) * 255 + 0.5).astype(np.uint8)), (x, y + head + k * (tile + 4)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.save(path)
    return path.replace(os.sep, "/")


def play_rate(trace, holds, n_between):
    """-> (drawings a second so the sheet plays as the scene held its drawings - the middle hold, in-betweens sharing
    it -, the rate that would really need when the engine's 30 a second cut it, else None)"""
    whole = holds[1:-1] if len(holds) > 3 else holds
    hold = float(np.median(whole)) if whole else 1.0
    real = round(float(trace["fps"]) / max(hold, 1.0) * (n_between + 1), 2)
    return (30.0, real) if real > 30.0 else (real, None)


# ------------------------------------------------------------------ the command
FLAGS = ("--gray", "--loop")


def options(argv):
    opts, names, i = {}, [], 0
    while i < len(argv):
        if argv[i] in FLAGS:
            opts[argv[i]] = True
        elif argv[i].startswith("--"):
            if i + 1 >= len(argv):
                raise ValueError(f"{argv[i]} needs a value")
            opts[argv[i]] = argv[i + 1]
            i += 1
        else:
            names.append(argv[i])
        i += 1
    return opts, names


def checked(block):
    """a spec's "ink" block (or the command's options as one) -> the same block with every field of the kind and
    range the ink takes; ValueError names the first that is not"""
    b = dict(block or {})

    def whole(name, default, low, high):
        v = b.get(name, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or not low <= int(v) <= high:
            raise ValueError(f"{name} is a whole number from {low} to {high}")
        return int(v)

    cell = whole("cell", 256, 32, 1024)
    if cell & (cell - 1):
        raise ValueError("cell is a power of two from 32 to 1024")
    register = b.get("register", "beat")
    if register not in ("beat", "drawing"):
        raise ValueError("register is beat or drawing")
    line = b.get("line", 0)
    if isinstance(line, bool) or not isinstance(line, (int, float)) or not 0 <= line <= 12:
        raise ValueError("line is 0 to 12 px")
    for flag in ("gray", "loop"):
        if not isinstance(b.get(flag, False), bool):
            raise ValueError(f"{flag} is true or false")
    pick = b.get("drawings")
    if pick is not None and not (isinstance(pick, (list, tuple)) and len(pick) == 2
                                 and all(isinstance(x, int) and not isinstance(x, bool) for x in pick) and 1 <= pick[0] <= pick[1]):
        raise ValueError("drawings is [first, last], counted from 1")
    return {"cell": cell, "register": register, "between": whole("between", 0, 0, 3), "gray": bool(b.get("gray", False)),
            "line": float(line), "drawings": list(pick) if pick is not None else None, "loop": bool(b.get("loop", False))}


def settings(opts):
    """the command's options -> the spec's "ink" block (what the build step inks again from)"""
    pick = None
    if opts.get("--drawings"):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", str(opts["--drawings"]))
        if not m:
            raise ValueError("--drawings is a-b, counted from 1 (e.g. 3-9)")
        pick = [int(m.group(1)), int(m.group(2) or m.group(1))]

    def number(name, default, kind):
        try:
            return kind(opts.get(name, default))
        except (TypeError, ValueError):
            raise ValueError(f"{name} is a number") from None

    return checked({"cell": number("--cell", 256, int), "register": str(opts.get("--register", "beat")),
                    "between": number("--between", 0, int), "gray": bool(opts.get("--gray")), "line": number("--line", 0, float),
                    "drawings": pick, "loop": bool(opts.get("--loop"))})


def kept(trace_path, kept_dir=KEPT):
    """is this trace one that was KEPT (it lies in the folder kept traces live in)? Only such a trace can make a
    texture spec: a spec must be able to ink its sheet again, and build/ is not in the repo"""
    try:
        return os.path.commonpath([os.path.abspath(trace_path), os.path.abspath(kept_dir)]) == os.path.abspath(kept_dir)
    except ValueError:
        return False


def run(key, trace_path, s, specs=SPECS, frames_dir=FRAMES, look_dir=LOOK, write_spec=True, kept_dir=KEPT):
    """ink one sheet -> (status, summary, next_action, extra)"""
    try:
        with open(trace_path, encoding="utf-8") as fh:
            trace = T.from_json(json.load(fh))
        float(trace["fps"])
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
        return ("fail", f"ink {key}: its trace is not on this machine or is not a trace ({trace_path}: {type(e).__name__})",
                "lune run kit vfx trace <set> --beat N first (its last line names the file), or keep the curves: --keep", {})
    try:
        result = ink(trace, s["cell"], s["register"], s["between"], s["gray"], s["line"], s["drawings"], s["loop"])
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
        return ("fail", f"ink {key}: {trace_path} is not a trace this can draw ({type(e).__name__}: {e})",
                "trace it again: lune run kit vfx trace <set> --beat N", {})
    if result.get("refused"):
        return "fail", f"ink {key}: {result['refused']}", "see the summary; the trace's own pictures show its drawings", {}
    cols, rows = result["grid"]
    fps, real = play_rate(trace, result["holds"], s["between"])
    spec_path = os.path.join(specs, f"{key}.json")
    shown = spec_path.replace(os.sep, "/")
    play = f'"flipbook": {{"layout": [{cols}, {rows}], "mode": "Loop", "fps": {fps:g}, "blend": false}}'
    spec = {"engine": "fx", "recipe": "ink",
            "about": f"drawn from the trace {trace_path.replace(os.sep, '/')} (kit/vfx/ink.py): {result['drawings']} drawing(s)"
                     + (f" + {s['between']} in-between(s) each" if s["between"] else "") + f"; play with {play}",
            "frames": len(result["cells"]), "grid": [cols, rows] if cols != rows else cols, "cell": result["cell"],
            "from": trace_path.replace(os.sep, "/"), "ink": s, "play": {"mode": "Loop", "fps": fps, "blend": False},
            "post": {"alpha": "coverage", "tonemap": False, "border": 0}}
    import fxfinish  # (a line or a fringe added to this sheet by hand is kept when the tool runs again)
    spec["post"].update(fxfinish.last_looks(spec_path))
    look = strip(result, os.path.join(look_dir, f"{key}_strip.png"))
    bad = [c for c in result["checks"] if not c["ok"]]
    earlier = os.path.isfile(spec_path)
    is_kept = kept(trace_path, kept_dir)
    wrote = False
    if not bad and is_kept:                                   # a sheet that failed its checks leaves no spec and no frames
        if write_spec:
            os.makedirs(specs, exist_ok=True)
            with open(spec_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(spec, fh, indent=1)
        write_frames(frames_dir, key, result["cells"], spec_path, trace_path)
        wrote = True
    holds = result["holds"]
    uneven = len(set(holds[1:-1] if len(holds) > 3 else holds)) > 1
    said = (f"ink {key}: {result['drawings']} drawing(s)" + (f" + {len(result['cells']) - result['drawings']} in-between(s)" if s["between"] else "")
            + f" in a {cols} x {rows} sheet of {result['cell']} px cells"
            + (f" (asked for {s['cell']} px: the sheet would pass 1024)" if result["cell"] != s["cell"] else "")
            + f", {len(result['tones'])} tone(s), the largest fills {result['fill'] * 100:.0f} % of its cell; plays at {fps:g} drawings a second"
            + (f" - the engine's most: as the scene held them it would need {real:g}, so it plays {real / fps:.1f} times too slow" if real else "")
            + (f" (the scene holds them {', '.join(map(str, holds))} frames: a flipbook has one rate)" if uneven else "")
            + (f"; {result['by_field']} pair(s) of drawings are not the same pieces (or turn too far): their in-betweens are made "
               f"from distance fields, which round a drawn point" if result.get("by_field") else "")
            + (f"; the frame or the box CUT {sum(c > T.CUT for c in result['cut'])} of these drawings (up to {max(result['cut']) * 100:.0f} % "
               f"of an outline is that straight edge, not the scene's drawing)" if max(result["cut"]) > T.CUT else ""))
    extra = {"cells": len(result["cells"]), "grid": [cols, rows], "cell": result["cell"], "fill": round(result["fill"], 4),
             "fps": fps, "tones": result["tones"], "checks": result["checks"], "look": look, "spec": shown if wrote else None}
    if bad:
        return ("fail", said + "; NOT a sheet to use - " + "; ".join(f"{c['name']}: {c['fix']} ({c['value']}, wants {c['limit']})" for c in bad)
                + (f"; the EARLIER sheet of this key ({shown}) is unchanged" if earlier else "") + f". LOOK: {look}",
                "fix what the summary names, then ink it again", extra)
    if not is_kept:
        return ("pass", said + f". A LOOK ONLY, no texture: its trace is not a kept one ({kept_dir.replace(os.sep, '/')}/), and a "
                f"texture spec must be able to ink its sheet again. LOOK: {look}",
                f"open {look} at full size (dark ground above, light below): are these the scene's drawings? For a texture - after "
                f"the owner's yes to keeping curves - trace with --keep and ink --from the kept file", extra)
    return ("pass", said + f". LOOK: {look}",
            f"open {look} at full size (dark ground above, light below): are these the scene's drawings? Then lune run kit vfx "
            f"(packs and registers {key}); in the preset: {play} (Loop plays {fps:g} cells a second; with OneShot the engine "
            f"spreads the cells over the particle's life instead: a life of {len(result['cells']) / fps:.2f} s is the same timing)", extra)


def build_step(argv):
    """the build step: every recipe "ink" spec whose frames are missing, older than its spec, or drawn from a trace
    that was made again since, is inked again from the trace and the options the spec names"""
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else d  # noqa: E731
    specs, frames_dir = opt("--specs", SPECS), opt("--out", FRAMES)
    kept_dir = opt("--kept-dir", KEPT)
    names = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--specs", "--out", "--kept-dir"))]
    done, errors = [], []
    for f in sorted(os.listdir(specs)) if os.path.isdir(specs) else []:
        if not f.endswith(".json") or (names and f[:-5] not in names):
            continue
        path = os.path.join(specs, f)
        try:
            with open(path, encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(spec, dict) or spec.get("engine") != "fx" or spec.get("recipe") != "ink":
            continue
        key = f[:-5]
        source = str(spec.get("from", ""))
        try:
            with open(os.path.join(frames_dir, key, "frames.json"), encoding="utf-8") as fh:
                meta = json.load(fh)
            fresh = meta.get("spec_mtime") == os.path.getmtime(path) and meta.get("trace") == trace_id(source)
        except (OSError, ValueError, AttributeError):
            fresh = False
        if fresh and "--force" not in argv:
            continue
        try:
            status, said, _, _ = run(key, source, checked(spec.get("ink")), specs, frames_dir, write_spec=False, kept_dir=kept_dir)
        except ValueError as e:
            status, said = "fail", f"ink {key}: its spec's \"ink\" block is not one ({e})"
        except Exception as e:  # noqa: BLE001 - one broken spec must not stop the others, nor print a traceback
            status, said = "fail", f"ink {key}: could not be inked again ({type(e).__name__}: {e})"
        (done if status == "pass" else errors).append(said)
    if errors:
        return out("fail", "ink: " + "; ".join(errors), "ink it again from its trace: lune run kit vfx ink <key> --from <trace.json>",
                   inked=done)
    return out("pass", f"ink: {len(done)} sheet(s) inked again" if done else "ink: every ink sheet's frames are current", "none", inked=done)


# ------------------------------------------------------------------ the sakuga grammars (kit/vfx/inkgrammar.py)
class GrammarRefused(ValueError):
    """a grammar sheet that failed its checks: .checks says which (nothing was written)"""

    def __init__(self, message, checks):
        super().__init__(message)
        self.checks = checks


def sheet_checks(cells, tones, cols, rows, cell_px):
    """a grammar sheet's packing checks -> (checks, the sheet (H, W, 4), the deepest clean mip level): the GUTTER (>= 2
    px of nothing at every cell's edge), the MIP PADDING (no see-through pixel left black: a smaller mip level would
    average black into the edge) and the deepest mip level at which no cell touches its neighbour"""
    import inkgrammar as G
    checks = []

    def add(name, ok, value, limit, fix):
        checks.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": "" if ok else fix})

    g = G.GUTTER
    ring = max(float(max(c[:g, :, 3].max(), c[-g:, :, 3].max(), c[:, :g, 3].max(), c[:, -g:, 3].max())) for c in cells)
    add("gutter", ring == 0.0, ring, f"alpha 0 in the outer {g} px of every cell", "a drawing reaches into the cell's gutter")
    drawn = [c for c in cells if (c[..., 3] > 0).any()]
    black = max([float(((c[..., 3] == 0) & (c[..., :3].sum(axis=2) == 0)).mean()) for c in drawn] or [0.0])
    add("mip_padded", black == 0.0 or min(min(t) for t in tones) == 0, round(black, 4),
        "no see-through pixel left black", "the see-through pixels are black: a mip level draws a dark fringe")
    sheet = np.zeros((rows * cell_px, cols * cell_px, 4), np.float32)
    for i, c in enumerate(cells):
        r, q = divmod(i, cols)
        sheet[r * cell_px:(r + 1) * cell_px, q * cell_px:(q + 1) * cell_px] = c
    level, size = 0, cell_px
    while size >= 8:                                            # the deepest mip level at which no cell bleeds
        f = 2 ** (level + 1)
        a = cv2.resize(sheet[..., 3], (sheet.shape[1] // f, sheet.shape[0] // f), interpolation=cv2.INTER_AREA)
        cs = cell_px // f
        edge = max(float(max(a[r * cs, :].max(), a[(r + 1) * cs - 1, :].max())) for r in range(rows))
        edge = max(edge, max(float(max(a[:, q * cs].max(), a[:, (q + 1) * cs - 1].max())) for q in range(cols)))
        if edge > 0.0:
            break
        level, size = level + 1, size // 2
    add("mip_clean", level >= 1, level, ">= 1 mip level with no cell touching its neighbour",
        "the drawings sit so close to the cell's edge that the first mip level already bleeds")
    return checks, sheet, level


def grammar_sheet(grammar, contour_metrics, frames=64, grid=8, cell_px=128, rhythm=2, seed=1, tones=None):
    """draw a grammar's sheet in memory -> {cells, sheet (H, W, 4) straight float, checks, params, said, measured,
    play}. Raises ValueError on input it does not take"""
    import inkgrammar as G
    if grammar not in G.GRAMMARS:
        raise ValueError(f"grammar is one of {', '.join(G.GRAMMARS)} (got {grammar!r})")
    m = G.checked_metrics(contour_metrics)
    if frames not in G.COUNTS:
        raise ValueError(f"frames is 16, 32 or 64 (a sheet the engine plays whole; got {frames!r})")
    cols, rows = G.COUNTS[frames]
    if grid != cols:
        raise ValueError(f"{frames} frames lie {cols} x {rows}: grid is {cols} (got {grid!r})")
    if cell_px not in (64, 128, 256):
        raise ValueError(f"cell_px is 64, 128 or 256 (got {cell_px!r})")
    if rhythm not in (1, 2, 3):
        raise ValueError(f"rhythm is 1 (on ones), 2 (on twos) or 3 (got {rhythm!r})")
    tones = [list(t) for t in (tones if tones is not None and len(tones) else G.GREYS)]
    while len(tones) < 3:
        tones.append(tones[-1])
    tones = sorted(tones[:3], key=lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
    P, said, clamped, ks = G.fit(grammar, m, frames, cell_px, seed, rhythm)
    drawings = [G.DRAW[grammar](k, frames, P, seed) for k in range(frames)]
    win = G.window(drawings)
    cells = [G.mip_pad(G.paint(G.raster(d, cell_px, win=win), tones)) for d in drawings]
    checks, _ = check(cells, ["drawing"] * frames, [0] * frames, np.asarray(tones, np.float32), cell_px, (cols, rows))

    def add(name, ok, value, limit, fix):
        checks.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": "" if ok else fix})

    # the numbers the sheet was driven by, measured back on the very drawings the fit sampled
    sol = float(np.mean([G.solidity(cells[k][..., 3]) for k in ks]))
    cut = float(np.mean([G.cutout_of(cells[k][..., 3]) for k in ks]))
    add("area_frac", clamped.get("area_frac") is not None or abs(sol - m["area_frac"]) <= G.TOL_AREA, round(sol, 3),
        f"{m['area_frac']} +- {G.TOL_AREA}" + (f" (unreachable: drawn at the nearest of {clamped['area_frac']})"
                                              if clamped.get("area_frac") else ""),
        "the drawn sheet is not as solid as its numbers say")
    if G.HAS_HOLES[grammar]:
        tol = max(G.TOL_CUT, 0.25 * m["cutout_ratio"])
        add("cutout_ratio", clamped.get("cutout_ratio") is not None or abs(cut - m["cutout_ratio"]) <= tol, round(cut, 3),
            f"{m['cutout_ratio']} +- {round(tol, 3)}" + (f" (unreachable: nearest of {clamped['cutout_ratio']})"
                                                    if clamped.get("cutout_ratio") else ""),
            "the drawn cut-outs are not the share its numbers say")
    more, sheet, level = sheet_checks(cells, tones, cols, rows, cell_px)
    checks += more
    checks += G.signature(grammar, cells, drawings, tones, cell_px, win)
    return {"cells": cells, "sheet": sheet, "checks": checks, "params": {k: (round(v, 4) if isinstance(v, float) else v)
                                                                      for k, v in P.items()},
            "said": said, "metrics": m, "measured": {"area_frac": round(sol, 4), "cutout_ratio": round(cut, 4), "mip_clean": level},
            "window": [round(x, 4) for x in win],
            "play": {"layout": [cols, rows], "fps": round(24.0 / rhythm, 3), "mode": "Loop" if G.LOOPS.get(grammar) else "OneShot",
                     "blend": False}, "tones": tones}


def render_grammar(grammar, contour_metrics, frames=64, grid=8, cell_px=128, rhythm=2, seed=1, tones=None, key=None,
                   out_dir=LOOK):
    """LIMITATIONS_FIXES_V4 §13.3.2: a sakuga grammar's sheet -> (sheet png, glow png). The sheet is
    (frames / grid) x grid cells of cell_px (8 x 8 x 128 = 1024 x 1024), straight RGBA, mip-padded; the glow is
    luminance x alpha past a floor (fxfinish's mask). Raises GrammarRefused (nothing written) when a check fails"""
    import fxfinish as F
    res = grammar_sheet(grammar, contour_metrics, frames, grid, cell_px, rhythm, seed, tones)
    bad = [c for c in res["checks"] if not c["ok"]]
    if bad:
        raise GrammarRefused(f"{grammar}: " + "; ".join(f"{c['name']} {c['value']} (wants {c['limit']}): {c['fix']}" for c in bad),
                             res["checks"])
    key = key or grammar
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, f"{key}.png")
    glow_path = os.path.join(out_dir, f"{key}_glow.png")
    img = Image.fromarray((np.clip(res["sheet"], 0, 1) * 255.0 + 0.5).astype(np.uint8), "RGBA")
    img.save(sheet_path)
    glow, share = F.glow_mask(img, {"floor": 0.6, "soft": 0.12})
    glow.save(glow_path)
    with open(os.path.join(out_dir, f"{key}.grammar.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "grammar": grammar, "metrics": res["metrics"], "measured": res["measured"],
                   "params": res["params"], "said": res["said"], "play": res["play"], "glow_share": round(share, 4),
                   "frames": frames, "cell": cell_px, "rhythm": rhythm, "seed": seed, "tones": res["tones"],
                   "checks": res["checks"]}, fh, indent=1)
    return sheet_path, glow_path


def grammar_main(opts, names):
    import inkgrammar as G
    usage = ("lune run kit vfx ink <key> --grammar " + "|".join(G.GRAMMARS)
             + " (--from <trace.json> | --metrics area,speed,cutout) [--frames 64] [--grid 8] [--cell 128] [--rhythm 2] [--seed 1]")
    if not names:
        return out("fail", "ink: needs a key for the grammar's sheet", usage)
    key = names[0]
    if not re.fullmatch(r"[a-z0-9_]{1,60}", key):
        return out("fail", f"ink: {key!r} is not a texture key (lower-case letters, digits, _)", usage)
    tones = None
    try:
        if opts.get("--from"):
            with open(opts["--from"], encoding="utf-8") as fh:
                trace = json.load(fh)
            metrics = G.metrics_from_trace(trace)
            tones = trace.get("tones") or None
        elif opts.get("--metrics"):
            a, v, c = (float(x) for x in str(opts["--metrics"]).split(","))
            metrics = {"area_frac": a, "centroid_vel": v, "cutout_ratio": c}
        else:
            return out("fail", f"ink {key}: a grammar is driven by numbers: --from <trace.json> or --metrics area,speed,cutout", usage)
        num = {name: int(opts.get(flag, dflt)) for name, flag, dflt in
               (("frames", "--frames", 64), ("grid", "--grid", 8), ("cell_px", "--cell", 128), ("rhythm", "--rhythm", 2),
                ("seed", "--seed", 1))}
        if "--grid" not in opts and num["frames"] in G.COUNTS:
            num["grid"] = G.COUNTS[num["frames"]][0]
        if "--cell" not in opts:
            num["cell_px"] = 128
    except (OSError, ValueError, TypeError, KeyError) as e:
        return out("fail", f"ink {key}: {e}", usage)
    look = opts.get("--look-dir", LOOK)
    try:
        sheet, glow = render_grammar(opts["--grammar"], metrics, tones=tones, key=key, out_dir=look, **num)
    except GrammarRefused as e:
        return out("fail", f"ink {key}: the {opts['--grammar']} sheet failed its checks - {e}",
                   "the numbers ask for a drawing the grammar cannot make: see the check named; nothing was written",
                   checks=e.checks)
    except ValueError as e:
        return out("fail", f"ink {key}: {e}", usage)
    with open(os.path.join(look, f"{key}.grammar.json"), encoding="utf-8") as fh:
        rep = json.load(fh)
    said = (" " + " ".join(rep["said"])) if rep["said"] else ""
    return out("pass", f"ink {key}: {rep['grammar']} {rep['frames']} drawings ({rep['play']['layout'][0]} x {rep['play']['layout'][1]}"
                       f" x {rep['cell']} px) from area {rep['metrics']['area_frac']} / speed {rep['metrics']['centroid_vel']} / "
                       f"cutout {rep['metrics']['cutout_ratio']}, measured back {rep['measured']['area_frac']} / "
                       f"{rep['measured']['cutout_ratio']}; every check passes; glow {rep['glow_share'] * 100:.1f} % of the sheet."
                       f" Play: flipbook {rep['play']}" + said,
               f"LOOK at {sheet.replace(os.sep, '/')} (and its _glow) before it goes anywhere",
               sheet=sheet.replace(os.sep, "/"), glow=glow.replace(os.sep, "/"))


def main(argv):
    if "--grammar" in argv:
        try:
            opts, names = options(argv)
        except ValueError as e:
            return out("fail", f"ink: {e}", "lune run kit vfx ink <key> --grammar <name> --metrics area,speed,cutout")
        return grammar_main(opts, names)
    if "--specs" in argv and "--from" not in argv:
        return build_step(argv)
    usage = "lune run kit vfx ink <key> --from <trace.json> [--drawings a-b] [--cell 256] [--between 1] [--loop] [--register beat|drawing]"
    try:
        opts, names = options(argv)
    except ValueError as e:
        return out("fail", f"ink: {e}", usage)
    if not names or "--from" not in opts:
        return out("fail", "ink: needs a key for the new sheet and the trace to draw it from",
                   "lune run kit vfx ink <key> --from build/vfx/trace/<set>/beat<k>.json")
    key = names[0]
    if not re.fullmatch(r"[a-z0-9_]{1,60}", key):
        return out("fail", f"ink: {key!r} is not a texture key (lower-case letters, digits, _)", "name it like hk_lick_ink")
    try:
        s = settings(opts)
    except ValueError as e:
        return out("fail", f"ink {key}: {e}", usage)
    specs = opts.get("--specs-dir", SPECS)
    spec_path = os.path.join(specs, f"{key}.json")
    if os.path.isfile(spec_path):
        try:
            with open(spec_path, encoding="utf-8") as fh:
                other = json.load(fh).get("recipe")
        except (OSError, ValueError, AttributeError):
            other = "?"
        if other != "ink":
            return out("fail", f"ink {key}: {spec_path.replace(os.sep, '/')} is another texture's spec (recipe {other})",
                       "pick a new key: a sheet that exists is never overwritten by another kind")
    status, said, nxt, extra = run(key, opts["--from"], s, specs, opts.get("--frames-dir", FRAMES), opts.get("--look-dir", LOOK),
                                   kept_dir=opts.get("--kept-dir", KEPT))
    return out(status, said, nxt, **extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
