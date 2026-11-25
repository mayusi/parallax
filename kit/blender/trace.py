"""trace.py — TRACE, don't guess: a reference view -> the exact outline a build extrudes. Plain Python + numpy + Pillow.

    python kit/blender/trace.py <image> --name <outline> [--box x0,y0,x1,y1] [--front left|right] [--bg auto|dark|light]
        [--threshold 28] [--tolerance 1.5] [--min-hole 0.002] [--rotate deg] [--open px]
        [--exclude x0,y0,x1,y1]... [--protect x0,y0,x1,y1]... [--part name=x0,y0,x1,y1]... [--spec refs/<x>.spec.json]
        [--cutout] [--part-point name=x,y[;x,y]]... [--part-box name=x0,y0,x1,y1]... [--part-text name="words"[#k]]...
        [--straighten] [--no-curves] [--ortho] [--organic]

  kit vision (vetted local models, offline — lune run kit vision setup once):
    --cutout                 the object mask from BiRefNet instead of the backdrop colour: photos on a real
                             background (a bench, a table, a field) trace as cleanly as a studio shot
    --part-point name=x,y    ONE part's own outline from a click on it (SAM 2.1): a grip, a trigger guard, a stock —
                             traced as that part's exact shape, not as "everything inside a box". ;x,y adds clicks
                             — QUOTE it then: --part-point "grip=436,261;440,280" (a bare ; ends the shell command)
                             ;!x,y is a click on what is NOT the part (a neighbour SAM keeps swallowing):
                             --part-point "safety=1200,610;1260,580;!1150,700"
    --part-box name=x0,y0,x1,y1   the same from a box around the part (SAM 2.1 picks the part inside it);
                             clicks after it narrow it: --part-box "safety=1100,500,1400,800;1200,610;!1150,700"
    --part-text name="pistol grip"   the same from WORDS (SAM 3, in the TRELLIS.2 environment: a few seconds of GPU):
                             the best match of the phrase; "name=phrase#2" takes the 2nd best (two grips, two claws)

  Every part's mask is JUDGED (trace JSON "part_quality": {name: {"ok", "prompt", "why"}}, the summary names the
  doubtful ones, the preview draws them magenta): a box prompt's mask that fills > 92% of its box (SAM took the
  region), two masks sharing > 30% of the smaller (one area, not two parts), a box-prompted mask that stops well short
  of its box one way while the object runs on as a thin piece (a dropped claw), a plain --part box (not a mask), a
  whole-object mask, an unsure SAM 3 match. `kit refs views` carries the doubts to every spec "ref" link
  (the ref_sizes_doubtful warning): retrace a doubtful part before a build measures against it.

  -> assets/models/<name>.trace.json   {"outline": [[u, h], ...], "holes": [...], "parts": {name: [[u, h], ...]},
     "curves": {"outline": [[p0, c1, c2, p3], ...], "holes": [...], "parts": {...}}, ...}
     SMOOTH CURVES (curvefit.py): the outline is the object's true EDGE (sub-pixel: the pixel staircase averaged out),
     sharp corners kept where two straight edges meet, cubic Beziers between them. "outline" is those curves sampled
     within --tolerance px; a build samples the curves as finely as it wants (rbx_trace.smooth). --no-curves: the
     old pixel-polygon outline (Douglas-Peucker on the staircase).
     u = 0 at the BACK of the object .. 1 at the FRONT (the muzzle), h = height in the same units (fraction of the
     length) measured from the bottom. Use it from a build with rbx_trace (load / clip / offset) and measure the
     result with Asset.trace_match(<name>) (silhouette IoU at build time).
  -> build/renders/<name>_trace.png    the evidence: outline (red), holes (blue), what --exclude REMOVED (red tint),
     protected boxes (green), --part outlines (yellow), spec feature boxes (green ok / red wrong). LOOK at it.

THE REFERENCE MUST BE A TRUE SIDE VIEW. A 3/4 photo shrinks the far end: the trace is then wrong everywhere, and a
model that matches it is wrong too. Best sources, in order: the maker's product side shot (often transparent PNG),
a manual / patent drawing, a blueprint, a museum side photo. The trace warns when the top and bottom edges converge.

Things in front of / attached to the object (a bipod, a scope, a hand): --exclude them, --protect the object's own
pixels so the exclusion can never eat it, and --part them to trace them as their own outlines (to model them too).

The design spec (refs/<name>.spec.json) is the "what IS this object" sheet, written from knowledge + every reference
BEFORE tracing: named features with u/h boxes and solid|gap. The trace is checked against it, so a wrong reference,
a mirrored trace, or an exclusion that ate a real part fails loudly instead of being modelled.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.dirname(KIT)


def game_root():
    """the active game's folder (env KIT_GAME, set by `--game <Name>` > games/.active), else the project root: a
    SampleRegion piece's trace once landed in the root's assets/models, where its build never looked"""
    game = os.environ.get("KIT_GAME")
    act = os.path.join(REPO, "games", ".active")
    if not game and os.path.isfile(act):
        game = open(act, encoding="utf-8").read().strip()
    if game and game.lower() != "none" and os.path.isdir(os.path.join(REPO, "games", game)):
        return os.path.join(REPO, "games", game)
    return REPO
PART_WHOLE = 0.75  # a traced PART this much of the object is the object (SAM's whole-object mask), never a part
CURVE_TOL = 0.9  # px: curve fit tolerance (curvefit._good: rms <= tol / 2, worst point <= 2 tol). Measured: ellipses
# trace within 0.9 px of the truth (the old polygon: 1.7-2.3 px); the M107 photo needs 279 anchors where the old polygon
# had 314 points, at a better fit (IoU 0.987 vs 0.980)


def _out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def _erode(m, r):
    return ~_dilate(~m, r)


def _components(m):
    """label 4-connected components of a boolean mask -> (labels, sizes) (scanline flood fill, no scipy)."""
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    sizes = [0]
    cur = 0
    for y0 in range(h):
        row = m[y0]
        for x0 in np.nonzero(row & (lab[y0] == 0))[0]:
            if lab[y0, x0]:
                continue
            cur += 1
            n = 0
            stack = [(y0, x0)]
            lab[y0, x0] = cur
            while stack:
                y, x = stack.pop()
                n += 1
                for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = cur
                        stack.append((yy, xx))
            sizes.append(n)
    return lab, sizes


def _largest(m):
    lab, sizes = _components(m)
    if len(sizes) < 2:
        return None
    return lab == int(np.argmax(sizes))


def _contour(m):
    """outer boundary of the single blob in m, as an ordered list of (x, y) pixel corners (Moore neighbour trace)."""
    h, w = m.shape
    pad = np.zeros((h + 2, w + 2), bool)
    pad[1:-1, 1:-1] = m
    ys, xs = np.nonzero(pad)
    i = np.lexsort((xs, ys))[0]
    start = (int(xs[i]), int(ys[i]))
    dirs = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    pts = [start]
    cur, back = start, 4  # came from the left
    for _ in range(4 * (h + w) * 8):
        found = False
        for k in range(8):
            d = (back + 1 + k) % 8
            nx, ny = cur[0] + dirs[d][0], cur[1] + dirs[d][1]
            if pad[ny, nx]:
                cur = (nx, ny)
                back = (d + 4) % 8
                found = True
                break
        if not found or cur == start:
            break
        pts.append(cur)
    return [(x - 1, y - 1) for x, y in pts]


def _simplify(pts, tol):
    """Douglas-Peucker on a closed polyline."""
    if len(pts) < 4:
        return pts
    a = np.array(pts, float)

    def rec(lo, hi):
        if hi <= lo + 1:
            return [lo]
        p, q = a[lo], a[hi]
        d = q - p
        n = np.hypot(*d) or 1.0
        seg = a[lo + 1:hi]
        dist = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / n
        k = int(np.argmax(dist))
        if dist[k] > tol:
            return rec(lo, lo + 1 + k) + rec(lo + 1 + k, hi)
        return [lo]

    far = int(np.argmax(np.hypot(*(a - a[0]).T)))
    idx = rec(0, far) + rec(far, len(a) - 1)
    return [tuple(a[i]) for i in idx]


def _curvefit():
    """kit/blender/curvefit.py, found beside this file however trace.py was loaded (lines.py loads it by path)"""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import curvefit  # noqa: PLC0415

    return curvefit


def _boxes_mask(shape, boxes):
    m = np.zeros(shape, bool)
    for x0, y0, x1, y1 in boxes:
        m[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    return m


def _rotate_mask(m, rotate):
    if not rotate:
        return m
    im = Image.fromarray((m * 255).astype(np.uint8)).rotate(rotate, resample=Image.NEAREST, expand=True, fillcolor=0)
    return np.asarray(im) > 127


def _unrotate_mask(m, rotate, shape0):
    """a mask of the --rotate'd picture back in the ORIGINAL picture's pixels (shape0 = (h, w)): turned back, the
    original's frame cut from its centre (rotate(expand=True) keeps the content centred; good to a pixel)"""
    back = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).rotate(-rotate, resample=Image.NEAREST, expand=True,
                                                                          fillcolor=0)) > 127
    h0, w0 = shape0
    y, x = (back.shape[0] - h0) // 2, (back.shape[1] - w0) // 2
    out = np.zeros(shape0, bool)
    part = back[max(y, 0):max(y, 0) + h0, max(x, 0):max(x, 0) + w0]
    out[:part.shape[0], :part.shape[1]] = part
    return out


def _object_mask(px, alpha, bg, threshold):
    """what is the object: the alpha channel when the picture has real transparency (exact), else the difference
    from the backdrop colour (estimated from the border)."""
    if alpha is not None and (alpha < 16).mean() > 0.05:
        return alpha > 128, "alpha"
    border = np.concatenate([px[0], px[-1], px[:, 0], px[:, -1]])
    if bg == "auto":
        ref = np.median(border, axis=0)
    else:
        ref = np.array([0, 0, 0.0]) if bg == "dark" else np.array([255, 255, 255.0])
    return np.sqrt(((px - ref) ** 2).sum(-1)) > threshold, f"backdrop {ref.round().tolist()}"


def _perspective(filled):
    """in a true side view the long straight edges (barrel, rail, beam, roof line) stay parallel. Fit lines to the
    top and the bottom edge of each half of the silhouette: if they converge, the picture is a perspective / 3/4 view
    and the far end is shrunk."""
    cols = np.nonzero(filled.any(0))[0]
    if len(cols) < 40:
        return {"suspect": False, "convergence": 0.0, "why": "too small to tell"}
    top = np.array([np.argmax(filled[:, c]) for c in cols], float)
    bot = np.array([filled.shape[0] - np.argmax(filled[::-1, c]) for c in cols], float)
    n = len(cols)
    worst = 0.0
    for lo, hi in ((n // 10, n // 2), (n // 2, n - n // 10)):
        xs = np.arange(lo, hi, dtype=float)
        t, b = top[lo:hi], bot[lo:hi]
        # robust: only where the thickness is near this half's median (the straight member, not a magazine/grip)
        th = b - t
        sel = np.abs(th - np.median(th)) < max(2.0, 0.15 * np.median(th))
        if sel.sum() < 0.3 * len(xs):
            continue
        kt = np.polyfit(xs[sel], t[sel], 1)[0]
        kb = np.polyfit(xs[sel], b[sel], 1)[0]
        span = float(xs[sel].max() - xs[sel].min())
        # relative: how much the member's thickness changes along the stretch measured
        worst = max(worst, abs(kt - kb) * span / max(float(np.median(th[sel])), 1.0))
    suspect = worst > 0.12
    return {"suspect": bool(suspect), "convergence": round(float(worst), 4),
            "why": (f"a straight member's thickness changes {worst:.0%} along its length (> 12%)" if suspect
                    else "straight members keep their thickness")}


def _edge_lines(filled):
    """the top and bottom edge lines of the object's STRAIGHT MEMBER — the stretch (40% of the length, slid along it)
    whose thickness stays most constant: a barrel, a rail, a beam, never a stock or a magazine. A whole-length median
    fails on a rifle (stock, grip and barrel all differ). -> ((kt, bt), (kb, bb)) in pixels, or None"""
    cols = np.nonzero(filled.any(0))[0]
    n = len(cols)
    if n < 40:
        return None
    top = np.array([np.argmax(filled[:, c]) for c in cols], float)
    bot = np.array([filled.shape[0] - np.argmax(filled[::-1, c]) for c in cols], float)
    th = bot - top
    win, best = max(20, int(0.4 * n)), None
    for start in range(0, n - win + 1, max(1, n // 20)):
        t = th[start:start + win]
        med = np.median(t)
        keep = np.abs(t - med) < max(2.0, 0.15 * med)
        if best is None or keep.mean() > best[0]:
            best = (keep.mean(), start, keep)
    share, start, keep = best
    if share < 0.5:
        return None
    xs = cols[start:start + win][keep].astype(float)
    return (tuple(np.polyfit(xs, top[start:start + win][keep], 1)),
            tuple(np.polyfit(xs, bot[start:start + win][keep], 1)))


def straighten_homography(filled, max_grow=3.0):
    """the projective transform that undoes a perspective picture's convergence (--straighten): the top and bottom
    edges of the straight member meet at a vanishing point V; the transform sends V to infinity (the edges become
    parallel), keeps vertical lines vertical and the scale at the object's centre (no other information exists —
    the result is right up to a stretch along the length, which the bbox-fitted silhouette check ignores), then
    levels the edges with a shear (verticals stay vertical). Measured (kit/test/python/test_straighten.py): a profile
    photographed by a camera turned 30 / 40 degrees comes back at IoU 0.97 / 0.99 (the exact inverse: 0.975). -> (3x3 H mapping crop pixels to straightened pixels, output size (w, h), V) or None"""
    lines = _edge_lines(filled)
    if lines is None:
        return None
    (kt, bt), (kb, bb) = lines
    if abs(kt - kb) < 1e-5:
        return None  # already parallel
    vx = (bb - bt) / (kt - kb)
    vy = kt * vx + bt
    ys, xs = np.nonzero(filled)
    cx, cy = float(xs.mean()), float(ys.mean())
    dx, dy = vx - cx, vy - cy
    if abs(dx) < 1.5 * (xs.max() - xs.min()) / 2:
        return None  # the vanishing point sits on the object: not a straight member seen in perspective
    to_c = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1]], float)
    proj = np.array([[1, 0, 0], [0, 1, 0], [-1.0 / dx, 0, 1]], float)  # V -> infinity; x = 0 (the centre) untouched
    # the (now parallel) edges run along (dx, dy): level them with a SHEAR, not a rotation — a camera turned about
    # its vertical axis keeps verticals vertical, and a rotation would tilt every one of them
    shear = np.array([[1, 0, 0], [-dy / dx, 1, 0], [0, 0, 1]], float)
    h0 = shear @ proj @ to_c
    hgt, wid = filled.shape
    corners = np.array([[0, 0, 1], [wid, 0, 1], [wid, hgt, 1], [0, hgt, 1]], float) @ h0.T
    if np.any(corners[:, 2] <= 0):
        return None  # the frame would cross the vanishing line: too strong to undo safely
    pts = corners[:, :2] / corners[:, 2:3]
    lo, hi = pts.min(0), pts.max(0)
    size = hi - lo
    if size[0] > max_grow * wid or size[1] > max_grow * hgt:
        return None
    h = np.array([[1, 0, -lo[0]], [0, 1, -lo[1]], [0, 0, 1]], float) @ h0
    return h, (int(np.ceil(size[0])), int(np.ceil(size[1]))), (float(vx), float(vy))


def _warp(img, h, size, nearest=False):
    """apply the 3x3 transform h (input pixels -> output pixels) to a PIL image"""
    hi = np.linalg.inv(h)
    hi = hi / hi[2, 2]
    return img.transform(size, Image.PERSPECTIVE, tuple(hi.flatten()[:8]),
                         resample=Image.NEAREST if nearest else Image.BICUBIC)


def _warp_mask(m, h, size):
    return np.asarray(_warp(Image.fromarray((m * 255).astype(np.uint8)), h, size, nearest=True)) > 127


def _check_spec(spec, filled, x0, y1, length, front):
    """each spec feature is a box in design units (u0, h0, u1, h1); the traced silhouette (`filled`: the outline minus
    the openings the trace keeps — a gap INSIDE the outline, a thumbhole or a trigger guard, is a gap) must be there
    (solid), absent (gap) or partly there (partial)."""
    rows = []
    h, w = filled.shape
    mm = float(spec.get("length_mm") or 0)  # boxes in real millimetres (from the back, from the lowest point)
    for f in spec.get("features", []):
        u0, h0, u1, h1 = [v / mm for v in f["box"]] if mm else f["box"]
        xs = [x0 + (1 - u if front == "left" else u) * length for u in (u0, u1)]
        ys = [y1 - hh * length for hh in (h0, h1)]
        xa, xb = int(max(0, min(xs))), int(min(w, max(xs)))
        ya, yb = int(max(0, min(ys))), int(min(h, max(ys)))
        cov = float(filled[ya:yb, xa:xb].mean()) if xb > xa and yb > ya else 0.0
        want = f.get("expect", "solid")
        lo, hi = {"solid": (0.55, 1.01), "gap": (-0.01, 0.35)}.get(want, (0.15, 0.9))
        rows.append({"name": f["name"], "box": [u0, h0, u1, h1], "expect": want, "coverage": round(cov, 3),
                     "ok": lo <= cov <= hi, "what": f.get("what", "")})
    return rows


def _check_dims(spec, height_ratio):
    """real proportions from published dimensions: a 3/4 photo inflates the height (you see the top) and shortens
    the length — the cheapest, surest perspective check there is."""
    want = spec.get("height_ratio") if spec else None
    if not want:
        return None
    tol = float(spec.get("height_tol", 0.06))
    err = height_ratio / float(want) - 1
    return {"want": want, "got": height_ratio, "error": round(err, 3), "ok": abs(err) <= tol, "tol": tol}


def _vision():
    """kit/vision/run.py (the vetted, offline models), imported on demand"""
    sys.path.insert(0, os.path.join(KIT, "vision"))
    import run  # noqa: PLC0415

    return run


# ---------------------------------------------------------------- is each part's mask worth measuring?
# Measured on a hero asset's side trace (2026-10-06): 5 of 13 SAM part masks were unusable — a box prompt's mask that
# filled its box, a grip and a guard that came back as one area, a crown that dropped a thin claw, a "part" that was a
# plain box. A spec "ref" to such a part measures the mask's mistake, so every part is judged here and the doubts
# travel with it (trace JSON part_quality -> kit refs views -> the ref_sizes check).
BOX_FULL = 0.92  # a box-prompted mask covering more of its box than this took the REGION, not the part
OVERLAP = 0.30  # two part masks sharing more than this of the smaller are one area, not two parts
NESTED = 0.20  # ... unless the smaller is a detail lying inside a part 5x its size (a port on a receiver)
DROP_SPAN, DROP_OTHER = 0.75, 0.70  # a mask spanning < 75% of its box one way while >= 70% the other way ...
DROP_REACH, DROP_FILL = 0.50, 0.60  # ... with the object running on past it >= half-way to the box's edge, thin
TEXT_SURE = 0.5  # SAM 3's own score below this: it was unsure which thing the words meant


def box_fill(mask, box):
    """how much of the prompt box (x0, y0, x1, y1, picture pixels) the mask covers, 0..1"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    h, w = mask.shape
    x0, x1, y0, y1 = max(0, min(x0, x1)), min(w, max(x0, x1)), max(0, min(y0, y1)), min(h, max(y0, y1))
    return float(mask[y0:y1, x0:x1].mean()) if x1 > x0 and y1 > y0 else 0.0


def overlapping(masks):
    """pairs of part masks (one frame) sharing more than OVERLAP of the smaller -> [(a, b, share, iou)]; a small
    detail lying wholly inside a much bigger part (a port on a receiver: < NESTED of its size, 90% inside) is not"""
    names = [n for n in masks if masks[n] is not None and masks[n].any()]
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ma, mb = masks[a], masks[b]
            inter = int(np.logical_and(ma, mb).sum())
            if not inter:
                continue
            sa, sb = int(ma.sum()), int(mb.sum())
            share = inter / min(sa, sb)
            if share <= OVERLAP or (min(sa, sb) < NESTED * max(sa, sb) and share >= 0.9):
                continue
            out.append((a, b, share, inter / (sa + sb - inter)))
    return out


def dropped_piece(mask, whole, box):
    """a box-prompted mask that spans much less of its box one way than the other while the OBJECT runs on past it
    toward the box's edge — as a thin piece, not a wall of the neighbouring body (a crown that dropped its claw; a
    grip box that also caught the receiver is not this). -> None or {"side", "span", "reach", "fill"}"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    h, w = mask.shape
    x0, x1, y0, y1 = max(0, min(x0, x1)), min(w, max(x0, x1)), max(0, min(y0, y1)), min(h, max(y0, y1))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    m, ob = mask[y0:y1, x0:x1], whole[y0:y1, x0:x1] | mask[y0:y1, x0:x1]
    ys, xs = np.nonzero(m)
    if len(xs) < 20:
        return None
    bh, bw = y1 - y0, x1 - x0
    span_x, span_y = (xs.max() - xs.min() + 1) / bw, (ys.max() - ys.min() + 1) / bh
    rest = ob & ~m
    lab, _sizes = _components(rest)
    grown = m.copy()  # (one pixel out, no wrap-around at the box's edges)
    grown[1:] |= m[:-1]
    grown[:-1] |= m[1:]
    grown[:, 1:] |= m[:, :-1]
    grown[:, :-1] |= m[:, 1:]
    touch = grown & rest  # object pixels right beside the mask: where a dropped piece would grow from it
    on = np.isin(lab, list(set(np.unique(lab[touch]).tolist()) - {0}))  # the object running on FROM the mask
    best = None
    for span, other, axis in ((span_x, span_y, 1), (span_y, span_x, 0)):
        if span >= DROP_SPAN or other < DROP_OTHER:
            continue
        lo, hi = (xs.min(), xs.max() + 1) if axis == 1 else (ys.min(), ys.max() + 1)
        size = bw if axis == 1 else bh
        for side, a, b in (("left" if axis == 1 else "top", 0, lo), ("right" if axis == 1 else "bottom", hi, size)):
            if b - a < 0.1 * size:
                continue
            strip = np.zeros_like(m)
            if axis == 1:
                strip[:, a:b] = True
            else:
                strip[a:b, :] = True
            piece = on & strip
            if piece.sum() < max(20, 0.02 * len(xs)):
                continue
            idx = np.nonzero(piece.any(axis=0) if axis == 1 else piece.any(axis=1))[0]
            far = (b - idx.min()) if side in ("left", "top") else (idx.max() + 1 - a)
            reach, fill = far / (b - a), float(piece.sum() / strip.sum())
            if reach >= DROP_REACH and fill < DROP_FILL and (best is None or reach > best["reach"]):
                best = {"side": side, "span": round(float(span), 3), "reach": round(float(reach), 3),
                        "fill": round(fill, 3)}
    return best


def part_quality(prompts, masks, raw=None, whole=None, share=None, scores=None):
    """every traced part judged -> {name: {"ok", "prompt", "why": [...]}}.
    prompts: {name: {"kind": "plain" | "box" | "points" | "text", "box": picture px (plain / box)}};
    masks: the part masks as traced (one frame, the trace's); raw: the prompt's own masks in the PICTURE's pixels (box
    prompts), whole: the object mask in the picture's pixels; share: each part's share of the object; scores: SAM's."""
    raw, share, scores = raw or {}, share or {}, scores or {}
    out = {n: {"ok": True, "prompt": p["kind"], "why": []} for n, p in prompts.items()}
    for n, p in prompts.items():
        why = out[n]["why"]
        if masks.get(n) is None or not masks[n].any():
            why.append("empty: no part found there — prompt it again")
            continue
        if p["kind"] == "plain":
            why.append("a plain box (--part), not a mask: its outline is everything of the object inside the box you "
                       "drew — trace the part itself (--part-point, --part-box or --part-text)")
        if share.get(n, 0.0) >= PART_WHOLE:
            why.append(f"covers {share[n]:.0%} of the object: SAM's whole-object mask, not the part")
        if p["kind"] == "box" and n in raw:
            f = box_fill(raw[n], p["box"])
            if f > BOX_FULL:
                why.append(f"fills its box ({f:.0%}): SAM likely took the region, not the part")
            if whole is not None:
                d = dropped_piece(raw[n], whole, p["box"])
                if d:
                    why.append(f"possible dropped piece: the mask spans {d['span']:.0%} of its box and the object "
                               f"runs on {d['reach']:.0%} of the way to the box's {d['side']} edge outside it (a thin "
                               "claw, a tip?) — add a click on it")
        if p["kind"] == "text" and n in scores and scores[n] < TEXT_SURE:
            why.append(f"SAM 3 was unsure (score {scores[n]:.2f}): the words may mean another thing")
    mask_parts = {n: masks.get(n) for n, p in prompts.items() if p["kind"] != "plain"}
    for a, b, sh, iou in overlapping(mask_parts):
        said = (f"'{a}' and '{b}' are one area ({iou:.0%} the same)" if iou >= 0.8 else
                f"'{a}' and '{b}' overlap ({sh:.0%} of the smaller): one area, not two parts")
        out[a]["why"].append(said)
        out[b]["why"].append(said)
    for q in out.values():
        q["ok"] = not q["why"]
    return out


def _trellis_python():
    """the TRELLIS.2 environment's python (as kit/lib/run.luau Run.tool("trellis2") finds it), or None"""
    env = os.environ.get("TRELLIS2")
    if env:
        return env
    home = os.path.expanduser("~")
    for c in (os.path.join(home, ".cache", "roblox-kit", "envs", "trellis2", "Scripts", "python.exe"),
              os.path.join(home, ".cache", "roblox-kit", "envs", "trellis2", "bin", "python")):
        if os.path.isfile(c):
            return c
    return None


class PromptError(Exception):
    """a part prompt that cannot be traced: (summary, next_action) said plainly, the trace stops"""


def parse_text(arg):
    """--part-text 'name=the phrase' | 'name=the phrase#2' (the 2nd best match) -> (name, phrase, k)"""
    name, _, rest = arg.partition("=")
    rest = rest.strip()
    k = 1
    head, hash_, tail = rest.rpartition("#")
    if hash_ and tail.strip().isdigit():
        rest, k = head, max(1, int(tail))
    return name.strip(), rest.strip().strip("\"'").strip(), k


def text_masks(image, phrases, keep=0.3):
    """SAM 3 by words (kit/gen/vision2.py parts, run in the TRELLIS.2 environment: its torch + CUDA) ->
    {phrase: [(score, bool H x W mask in the picture's pixels), ...] best first}"""
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    py = _trellis_python()
    where = "~/.cache/roblox-kit/envs/trellis2" + ("" if not py else f", TRELLIS2={py}")
    missing = (f"trace: --part-text needs SAM 3, which runs in the TRELLIS.2 environment ({where}) — it is not "
               "installed here",
               "install it (kit/gen/README.md, 'Reinstall from scratch'; the weights: lune run kit vision setup sam3, "
               "with the owner's HF_TOKEN set), or prompt the part without words: --part-point name=x,y or --part-box "
               "name=x0,y0,x1,y1 (SAM 2.1)")
    if not py:
        raise PromptError(*missing)
    tmp = tempfile.mkdtemp(prefix="kit_sam3_")
    try:
        npz = os.path.join(tmp, "masks.npz")
        cmd = [py, os.path.join(KIT, "gen", "vision2.py"), "parts", os.path.abspath(image)]
        for p in phrases:
            cmd += ["--text", p]
        cmd += ["-o", os.path.join(tmp, "parts.png"), "--min", str(keep), "--masks", npz]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, timeout=1800)
        except OSError:  # (TRELLIS2 set to a python that is not there)
            raise PromptError(*missing) from None
        said = None
        for line in reversed((r.stdout or "").splitlines()):
            if line.startswith("{"):
                try:
                    said = json.loads(line)
                    break
                except ValueError:
                    pass
        if r.returncode != 0 or not os.path.isfile(npz):
            tail = (said or {}).get("summary") or (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["?"]
            raise PromptError(f"trace: SAM 3 (--part-text) stopped: {tail if isinstance(tail, str) else tail[0]}",
                              (said or {}).get("next_action") or "read the error above; prompt the part with "
                              "--part-point / --part-box meanwhile")
        z = np.load(npz)
        out = {p: [] for p in phrases}
        for m, s, t in zip(z["masks"], z["scores"], z["texts"]):
            out.setdefault(str(t), []).append((float(s), m.astype(bool)))
        for p in out:
            out[p].sort(key=lambda sm: -sm[0])
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _prompt(entry, kind):
    """a --part-point (name, clicks[, not-clicks]) or --part-box (name, box[, clicks, not-clicks]) -> (name, SAM prompt)"""
    if kind == "points":
        pn, pts, *rest = entry
        negs = rest[0] if rest else []
        return pn, {"points": pts, **({"negatives": negs} if negs else {})}
    pn, pb, *rest = entry
    pts, negs = (list(rest) + [[], []])[:2]
    return pn, {"box": pb, **({"points": pts} if pts else {}), **({"negatives": negs} if negs else {})}


def _clicks(text):
    """"x,y;!x,y;..." -> ([(x, y)] on the part, [(x, y)] NOT on it)"""
    pos, neg = [], []
    for xy in (c.strip() for c in text.split(";") if c.strip()):
        (neg if xy.startswith("!") else pos).append(tuple(float(v) for v in xy.lstrip("!").split(",")))
    return pos, neg


def trace(image, box, name, front="right", bg="auto", threshold=28.0, tolerance=1.5, min_hole=0.002, rotate=0.0,
          exclude=(), open_px=0, protect=(), parts=(), spec=None, cutout=False, part_points=(), part_boxes=(),
          straighten=False, curves=True, ortho=False, part_texts=(), organic=False):
    src = Image.open(image)
    has_alpha = src.mode in ("RGBA", "LA", "PA") or "transparency" in src.info
    rgba = src.convert("RGBA")
    if rotate:
        # level the object (a photo is rarely square-on): rotate about the centre, the new area is backdrop
        rgba = rgba.rotate(rotate, resample=Image.BICUBIC, expand=True, fillcolor=rgba.getpixel((2, 2)))
    full = np.asarray(rgba, np.float32)
    whole, how = _object_mask(full[..., :3], full[..., 3] if has_alpha else None, bg, threshold)
    if cutout:  # a learned object mask (BiRefNet): a real background no longer bleeds into the outline
        whole, how = _vision().cutout(rgba) > 0.5, "BiRefNet cutout (kit vision)"
    # --exclude / --protect / --part boxes are in the ORIGINAL picture's pixels (what you see when you open it);
    # a protected box always wins, so a coarse exclusion can never eat the object itself
    shape0 = (src.size[1], src.size[0])
    ex = _rotate_mask(_boxes_mask(shape0, exclude), rotate)
    keep = _rotate_mask(_boxes_mask(shape0, protect), rotate)
    removed = whole & ex & ~keep
    part_masks = {pn: whole & _rotate_mask(_boxes_mask(shape0, [pb]), rotate) for pn, pb in parts}
    part_scores = {}
    # a click that lands on the BACKDROP is a misread coordinate (a grid read at the wrong scale): SAM then returns the
    # backdrop — with a high score — and the part comes back as a speck of the object. Said here, plainly
    off_object = [f"{pn} click ({int(x)}, {int(y)})" for pn, pts, *_neg in part_points for x, y in pts
                  if not (0 <= int(y) < whole.shape[0] and 0 <= int(x) < whole.shape[1]) or not whole[int(y), int(x)]]
    # how each part was asked for, and the box prompts' own masks in the picture's pixels: their quality is judged
    # against the box (part_quality)
    prompts = {pn: {"kind": "plain", "box": list(pb)} for pn, pb in parts}
    raw = {}
    for pn, prompt in [*(_prompt(e, "points") for e in part_points), *(_prompt(e, "box") for e in part_boxes)]:
        # SAM 2.1 on the ORIGINAL picture (the clicks / boxes are in its pixels), then rotated like every other mask
        pm, part_scores[pn] = _vision().mask(src, **prompt)
        part_masks[pn] = whole & _rotate_mask(pm, rotate)
        prompts[pn] = {"kind": "box", "box": list(prompt["box"])} if "box" in prompt else {"kind": "points"}
        if "box" in prompt:
            raw[pn] = pm
    part_text = {}
    if part_texts:
        # SAM 3 by WORDS ("the pistol grip"): every match of the phrase, the best one taken (or the k-th: name=phrase#k)
        try:
            found = text_masks(image, sorted({ph for _pn, ph, _k in part_texts}))
        except PromptError as e:
            return _out("fail", e.args[0], e.args[1])
        for pn, ph, k in part_texts:
            got = found.get(ph, [])
            if len(got) < k:
                return _out("fail", f'trace: SAM 3 found {len(got)} match(es) of "{ph}" in the picture'
                            + (f", not a #{k}" if got else ""),
                            f'take one of #1..#{len(got)} (--part-text "{pn}={ph}#1")' if got else
                            'say what the part IS in plain words ("pistol grip", "trigger guard", "scope") or prompt '
                            f"it without words: --part-point {pn}=x,y or --part-box {pn}=x0,y0,x1,y1")
            sc_, pm = got[k - 1]
            if pm.shape != shape0:
                return _out("fail", f'trace: SAM 3\'s mask for "{ph}" is {pm.shape[1]} x {pm.shape[0]} px, the '
                            f"picture {shape0[1]} x {shape0[0]}", "read kit/gen/vision2.py parts: its masks must be "
                            "the picture's size (target_sizes)")
            part_masks[pn] = whole & _rotate_mask(pm, rotate)
            part_scores[pn] = sc_
            prompts[pn] = {"kind": "text"}
            part_text[pn] = {"phrase": ph, "pick": k, "matches": len(got), "score": round(sc_, 3)}
    x_off, y_off = (box[0], box[1]) if box else (0, 0)
    sl = (slice(box[1], box[3]), slice(box[0], box[2])) if box else (slice(None), slice(None))
    crop = rgba.crop(tuple(box)) if box else rgba
    m = (whole & ~removed)[sl]
    if open_px:
        # opening: drop anything thinner than ~2 x open_px (a sling, a cable, a strap) and keep the real forms
        m = _dilate(_erode(m, open_px), open_px)
    m = _erode(_dilate(m, 2), 2)  # close hairline gaps along the outline
    rem = removed[sl]
    part_masks = {pn: pm[sl] for pn, pm in part_masks.items()}  # (from here on, everything is in the crop's pixels)

    def shape(mask):
        """the body, its holes (backdrop fully enclosed: trigger guard, ejection port) and the body with holes filled"""
        body_ = _largest(mask)
        if body_ is None:
            return None
        lab, sizes = _components(~body_)
        edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
        holes_ = [i for i in range(1, len(sizes)) if i not in edge and sizes[i] > body_.sum() * min_hole]
        filled_ = body_.copy()
        for i in range(1, len(sizes)):
            if i not in edge:
                filled_ |= lab == i
        return body_, lab, holes_, filled_

    got = shape(m)
    if got is None:
        return _out("fail", f"trace: nothing found in the box ({how})",
                    "check --box, or raise/lower --threshold, or set --bg dark|light")
    body, lab_bg, holes_px, filled = got
    straightened = None
    if straighten:
        # undo a perspective picture's convergence BEFORE the outline is taken: the picture and every mask go
        # through the same transform (see straighten_homography)
        before = _perspective(filled)
        hv = straighten_homography(filled)
        if hv is not None:
            h, size, vp = hv
            crop = _warp(crop, h, size)
            m = _warp_mask(m, h, size)
            rem = _warp_mask(rem, h, size)
            part_masks = {pn: _warp_mask(pm, h, size) for pn, pm in part_masks.items()}
            got = shape(m)
            if got is not None:
                body, lab_bg, holes_px, filled = got
                # the transform itself is kept: every later reader of this photo (the lines and perceptual checks)
                # cuts it exactly as the trace did — box, rotation, THEN this warp
                straightened = {"vanishing_point": [round(vp[0], 1), round(vp[1], 1)],
                                "convergence_before": before["convergence"],
                                "homography": [float(x) for x in np.asarray(h, float).ravel()],
                                "size": [int(size[0]), int(size[1])]}
        if straightened is None:
            straightened = {"skipped": "no straight member to read the perspective from, or none to undo",
                            "convergence_before": before["convergence"]}
    def outline_of(mask):
        """-> (polygon in px, Bezier curves in px or None): the curve-sampled true edge, or the staircase polygon"""
        contour = _contour(mask)
        if not curves:
            return _simplify(contour, tolerance), None
        cf = _curvefit()
        cv = cf.fit(*cf.subpixel(contour), tol=CURVE_TOL)
        return cf.sample(cv, cf.outline_flatness(cv, tolerance)), cv

    outer, outer_cv = outline_of(filled)
    hole_fits = [outline_of(lab_bg == i) for i in holes_px]
    holes = [h for h, _cv in hole_fits]
    ys, xs = np.nonzero(filled)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    length = float(x1 - x0)

    def design(pts):
        out = []
        for x, y in pts:
            u = (x - x0) / length
            if front == "left":
                u = 1 - u
            out.append([round(float(u), 5), round(float((y1 - y) / length), 5)])
        return out

    def design_cv(cv):  # (the design map is affine: a Bezier maps through its control points)
        return [design(b) for b in cv] if cv is not None else None

    part_fits, part_share, part_final = {}, {}, {}
    for pn, pm in part_masks.items():
        pb = _largest(_erode(_dilate(pm, 2), 2))
        part_final[pn] = pb
        if pb is not None:
            part_fits[pn] = outline_of(pb)
            part_share[pn] = float(pb.sum() / max(1, filled.sum()))
    part_out = {pn: design(poly) for pn, (poly, _cv) in part_fits.items() if poly}
    # is each part's mask worth measuring? (a box-filling mask, two parts as one area, a dropped claw, a plain box)
    whole0 = whole if not rotate else _unrotate_mask(whole, rotate, shape0)  # (the box prompts' own pixels)
    quality = part_quality(prompts, part_final, raw, whole0, part_share, part_scores) if prompts else {}
    persp = _perspective(filled)
    traced = filled.copy()  # the silhouette this trace WRITES: the outline minus the openings it keeps
    for i in holes_px:
        traced &= lab_bg != i
    spec_rows = _check_spec(spec, traced, x0, y1, length, front) if spec else []
    dims = _check_dims(spec, round(float((y1 - y0) / length), 5))
    result = {"name": name, "source": os.path.relpath(os.path.abspath(image), REPO).replace("\\", "/"), "box": box,
              "rotate": rotate, "exclude": [list(e) for e in exclude], "protect": [list(p) for p in protect],
              "front": front, "pixels_per_length": length, "height_ratio": round(float((y1 - y0) / length), 5),
              "mask": how, "bg": bg, "threshold": threshold, "open": open_px, "perspective": persp,
              "outline": design(outer), "holes": [design(h) for h in holes], "parts": part_out,
              **({"organic": True} if organic else {})}
    if outer_cv is not None:
        result["curves"] = {"outline": design_cv(outer_cv), "holes": [design_cv(cv) for _h, cv in hole_fits],
                            "parts": {pn: design_cv(cv) for pn, (_p, cv) in part_fits.items() if pn in part_out},
                            "tolerance_px": CURVE_TOL}
    if straightened is not None:
        result["straighten"] = straightened
    # where the design frame sits in the PICTURE (its own pixels, as the preview shows them): a point read off the
    # reference maps to design units exactly (rbx_trace.px) — not after a rotation or a straightening warp
    result["frame"] = None if (rotate or (straightened or {}).get("homography")) else {
        "x0": float(x0 + x_off), "y1": float(y1 + y_off), "length_px": length}
    if part_scores:
        result["part_scores"] = {k: round(v, 3) for k, v in part_scores.items()}  # SAM's own confidence per part
    if quality:
        result["part_quality"] = quality  # {name: {ok, prompt, why}}: kit refs views carries it to every ref link
    if part_text:
        result["part_text"] = part_text  # the words, which match was taken, of how many
    if spec_rows:
        result["spec"] = spec_rows
    if dims:
        result["dims"] = dims
    os.makedirs(os.path.join(game_root(), "assets", "models"), exist_ok=True)
    path = os.path.join(game_root(), "assets", "models", f"{name}.trace.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)

    # the evidence: the crop on white, what the exclusions REMOVED tinted red, outline + holes + parts + spec boxes
    preview = Image.alpha_composite(Image.new("RGBA", crop.size, (255, 255, 255, 255)), crop).convert("RGB")
    px = np.asarray(preview).copy()
    px[rem] = (px[rem] * 0.35 + np.array([255, 40, 40]) * 0.65).astype(np.uint8)
    preview = Image.fromarray(px)
    d = ImageDraw.Draw(preview)
    lw = max(2, int(max(preview.size) / 600))  # readable at any image size
    for pb in protect if not (straightened and "vanishing_point" in straightened) else ():  # (boxes are pre-warp)
        d.rectangle((pb[0] - x_off, pb[1] - y_off, pb[2] - x_off, pb[3] - y_off), outline=(40, 200, 80), width=lw)
    d.line(outer + [outer[0]], fill=(255, 60, 60), width=lw)
    for h in holes:
        d.line(h + [h[0]], fill=(60, 220, 255), width=lw)
    for x, y in ([tuple(b[0]) for b in outer_cv] if outer_cv is not None else outer):  # curve anchors / vertices
        d.ellipse((x - lw, y - lw, x + lw, y + lw), fill=(255, 220, 60))

    def to_px(p):
        u = 1 - p[0] if front == "left" else p[0]
        return (x0 + u * length, y1 - p[1] * length)

    for pn, poly in part_out.items():
        pts = [to_px(p) for p in poly]
        doubt = not quality.get(pn, {"ok": True})["ok"]  # a doubtful mask in magenta, its name with a "?"
        d.line(pts + [pts[0]], fill=(220, 40, 200) if doubt else (230, 170, 0), width=lw)
        d.text((pts[0][0] + 4, pts[0][1] + 4), pn + ("?" if doubt else ""),
               fill=(160, 0, 140) if doubt else (150, 100, 0))
    for row in spec_rows:
        pa, pb2 = to_px(row["box"][:2]), to_px(row["box"][2:])
        col = (30, 150, 60) if row["ok"] else (230, 30, 30)
        bx = (min(pa[0], pb2[0]), min(pa[1], pb2[1]), max(pa[0], pb2[0]), max(pa[1], pb2[1]))
        d.rectangle(bx, outline=col, width=max(1, lw // 2))
        d.text((bx[0] + 3, bx[1] + 2), row["name"], fill=col)
    os.makedirs(os.path.join(game_root(), "build", "renders"), exist_ok=True)
    ppath = os.path.join(game_root(), "build", "renders", f"{name}_trace.png")
    preview.save(ppath)

    rel = lambda p: os.path.relpath(p, REPO).replace("\\", "/")  # noqa: E731
    bad = [r for r in spec_rows if not r["ok"]]
    warn = []
    # (--ortho: a render / drawing known to be orthographic — a taper is real; --organic: a curved organic form — a
    #  skull, a creature, a rock — has no straight member whose thickness should hold: the check is for a barrel)
    if persp["suspect"] and not ortho and not organic:
        warn.append(f"PERSPECTIVE: {persp['why']} — a non-orthographic picture gives a WRONG outline; use a true side "
                    "view (the maker's product shot, a manual drawing, a blueprint)"
                    + ("" if straighten else ", or add --straighten to undo the convergence"))
    if dims and not dims["ok"]:
        warn.append(f"PROPORTIONS: traced height/length {dims['got']} vs the real {dims['want']} ({dims['error']:+.0%}) — "
                    "a perspective / 3/4 picture, or parts still attached that the spec's height leaves out")
    if bad:
        warn.append("spec features wrong: " + ", ".join(f"{r['name']} (want {r['expect']}, coverage {r['coverage']})"
                                                       for r in bad[:6])
                    + " — an exclusion ate a real part, the reference is wrong, or the spec box is off")
    if off_object:
        warn.append("PART CLICK OFF THE OBJECT: " + ", ".join(off_object) + " is on the backdrop, not the object — "
                    "read the click off the ORIGINAL picture's pixels (a grid drawn on a resized copy is at its scale)")
    whole = sorted((pn for pn, s in part_share.items() if s >= PART_WHOLE), key=lambda pn: -part_share[pn])
    if whole:
        # one click on a big structure gives SAM's WHOLE-OBJECT mask (a stock clicked on the Gjallarhorn came back as
        # the whole launcher): a model built from that "part" would be the whole silhouette again
        warn.append("PART = WHOLE OBJECT: " + ", ".join(f"{pn} covers {part_share[pn]:.0%} of the object" for pn in whole)
                    + " — that is the object, not the part: prompt it with a box around just the part "
                    "(--part-box name=x0,y0,x1,y1) or more clicks on it (--part-point \"name=x,y;x,y\")")
    doubtful = [pn for pn, q in quality.items() if not q["ok"]]
    summary = (f"trace {name}: outline {len(outer)} points, {len(holes)} hole(s), {len(part_out)} part(s), mask from "
               f"{how}, height/length {result['height_ratio']}"
               + (f", spec {len(spec_rows) - len(bad)}/{len(spec_rows)} features ok" if spec_rows else "")
               + (f"; {len(doubtful)} DOUBTFUL part mask(s): "
                  + "; ".join(f"{pn} ({quality[pn]['why'][0].split(':')[0]})" for pn in doubtful) if doubtful else "")
               + f" -> {rel(path)}")
    look = (f"LOOK at {rel(ppath)}: red line = outline (must hug the object), blue = holes, red TINT = what --exclude "
            "removed (only what you meant to drop), green = protected, yellow = --part outlines (magenta = doubtful), "
            "boxes = spec features")
    retrace = ("doubtful part masks — " + "; ".join(f"{pn}: {', '.join(quality[pn]['why'])}" for pn in doubtful)
               + " — retrace each with clicks on it (--part-point \"name=x,y;x,y\") or by words (--part-text "
               "name=\"what it is\") before a spec \"ref\" measures it" if doubtful else "")
    if warn:
        return _out("fail", summary, "; ".join(warn + ([retrace] if retrace else [])) + " · " + look, trace=rel(path),
                    preview=rel(ppath), part_quality=quality)
    if retrace:
        return _out("pass", summary, retrace + " · " + look, trace=rel(path), preview=rel(ppath), part_quality=quality)
    return _out("pass", summary, look + ("" if spec_rows else " · write refs/<name>.spec.json (what each feature IS, "
                                         "where) and re-run with --spec so the trace is CHECKED"),
                trace=rel(path), preview=rel(ppath))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--box", default=None)
    ap.add_argument("--name", required=True)
    ap.add_argument("--front", default="right", choices=("left", "right"))
    ap.add_argument("--bg", default="auto", choices=("auto", "dark", "light"))
    ap.add_argument("--threshold", type=float, default=28.0)
    ap.add_argument("--tolerance", type=float, default=1.5)
    ap.add_argument("--min-hole", type=float, default=0.002)
    ap.add_argument("--rotate", type=float, default=0.0, help="degrees counter-clockwise, applied first (level the object)")
    ap.add_argument("--exclude", action="append", default=[], help="x0,y0,x1,y1 removed (original picture pixels)")
    ap.add_argument("--protect", action="append", default=[], help="x0,y0,x1,y1 never removed by --exclude")
    ap.add_argument("--part", action="append", default=[],
                    help="name=x0,y0,x1,y1: trace that box as its own outline (a bipod you also --exclude)")
    ap.add_argument("--open", type=int, default=0, help="remove features thinner than ~2x this many pixels (cables, straps)")
    ap.add_argument("--spec", default=None, help="design spec json: features (u0,h0,u1,h1 boxes, solid|gap|partial)")
    ap.add_argument("--cutout", action="store_true", help="object mask from BiRefNet (kit vision) instead of the backdrop")
    ap.add_argument("--part-point", action="append", default=[], help="name=x,y[;x,y]: that part's outline from clicks (SAM 2.1)")
    ap.add_argument("--part-box", action="append", default=[], help="name=x0,y0,x1,y1: that part's outline from a box (SAM 2.1)")
    ap.add_argument("--part-text", action="append", default=[],
                    help='name="what it is"[#k]: that part\'s outline from WORDS (SAM 3, the TRELLIS.2 environment): '
                         "the best match, or the k-th")
    ap.add_argument("--straighten", action="store_true",
                    help="undo a perspective picture's convergence (the long straight edges made parallel) before tracing")
    ap.add_argument("--no-curves", action="store_true",
                    help="the old outline: Douglas-Peucker on the pixel staircase, no smooth curves")
    ap.add_argument("--organic", action="store_true",
                    help="a curved ORGANIC form (a skull, a creature, a rock, a tree): its tapers are its shape — the "
                         "perspective check (straight members keep their thickness) is skipped")
    ap.add_argument("--ortho", action="store_true",
                    help="the picture IS orthographic (an orthographic render, a technical drawing): a member that "
                         "tapers is real, not perspective — skip the perspective check")
    a = ap.parse_args()
    box = [int(v) for v in a.box.split(",")] if a.box else None
    ex = [[int(v) for v in e.split(",")] for e in a.exclude]
    pr = [[int(v) for v in e.split(",")] for e in a.protect]
    pt = [(p.split("=")[0], [int(v) for v in p.split("=")[1].split(",")]) for p in a.part]
    spec = None
    if a.spec:
        with open(a.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    pp = [(p.split("=")[0], *_clicks(p.split("=", 1)[1])) for p in a.part_point]
    pbx = [(p.split("=")[0], [float(v) for v in p.split("=", 1)[1].split(";")[0].split(",")],
            *_clicks(";".join(p.split("=", 1)[1].split(";")[1:]))) for p in a.part_box]
    ptx = [parse_text(p) for p in a.part_text]
    if any(not n or not ph for n, ph, _k in ptx):
        sys.exit(_out("fail", "trace: --part-text needs name=\"what it is\" (e.g. --part-text grip=\"pistol grip\")",
                      'lune run kit trace <picture> --name <outline> --part-text grip="pistol grip"'))
    sys.exit(trace(a.image, box, a.name, a.front, a.bg, a.threshold, a.tolerance, a.min_hole, a.rotate, ex, a.open,
                   pr, pt, spec, a.cutout, pp, pbx, a.straighten, not a.no_curves, a.ortho, ptx, a.organic))
