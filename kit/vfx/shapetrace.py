"""shapetrace.py — the scene's DRAWN SHAPES as curves: the rotoscope of the VFX lane (the owner's VFX method list,
2026-11-13: "Hand-drawn effects animation", "Frame-by-frame effects", "Masking / rotoscoping"; the VFX studio-route
plan's V3, its trace half).

    lune run kit vfx trace <set> [--beat N] [--tones 3] [--lit 0.6] [--box x0,y0,x1,y1] [--window a,b] [--width 960] [--keep]
    python kit/vfx/shapetrace.py --frames <folder of pictures> --fps 24 --out <folder> [--hue lo,hi] [--tones 3] [--box ...]

Why: an anime effect is drawn shapes - a flame with cut-outs, a crescent that thins from its tail, a puff with a hard
edge - held two frames at a time. The kit read a scene's colours (five numbers) and its timing (V0), and showed its
frames on the chart; nothing carried the DRAWINGS themselves into the effect, so a session typed a look and the
sheets came out as posterised simulations. This reads the drawings as numbers:

  1. the cut-out   every frame of the beat's main shot at the clip's own frame rate; the effect is what the dense read
                   calls the effect (kit/vfx/dense.py: the set's measured hue band, coloured and lit, or white-hot; with
                   no hue, what is brighter than the quiet picture). --box keeps a part of the frame only (a garbage
                   matte, 0..1 from the top left: the session LOOKS at the frames and frames the effect); --lit 0.6
                   keeps only what is that bright (the floor an effect lights is in its hue band too, and dimmer)
  2. the drawings  consecutive frames that show the same shape are ONE drawing, held (on ones, twos, threes: read here
                   from the shapes, the same rule as the dense read); a drawing is taken from all its frames at once
                   (per pixel what most of them show: the clip's compression noise drops out)
  3. the tones     the effect's colours over the whole beat sorted into `--tones` flat tones (a cel has a few flat
                   colours: a rim, a body, a hot core), darkest first, each with its measured colour
  4. the curves    per drawing and tone, the outline of every piece and of every hole in it (the cut-outs), as closed
                   curves: the pixel staircase smoothed away, the sharp points (a flame's tips) kept sharp
  5. the check     every drawing is drawn again from its curves and laid on its cut-out: a trace that covers less than
                   FIT of it is named; a drawing the frame's edge or the --box cuts is SAID (`cut`: the share of its
                   outline that is that straight edge - such an outline is not the drawing's); a cut-out that is a flood (a full-screen flash, a background in the hue band) or
                   a speckle is REFUSED - it is not a drawing, and curves taken from it would look like a result

Kept: curves, colours and timing, never a frame. build/vfx/trace/<set>/beat<k>.json + the LOOK pictures
build/vfx/trace/<set>/beat<k>_d<nn>.png (the scene's frame, the same frame with the trace laid on it, the trace alone;
each 640 px or more: OPEN them - a trace is only as good as its cut-out). --keep also writes
assets/effects/refs_measured/<set>.trace.beat<k>.json (curves beside the beat sheet; only after the owner's yes to
the studio-route plan's decision 2).

Limits, said plainly: it reads COLOUR and LIGHT, so a dark effect (ink, black smoke) is not seen; skin, cloth or
scenery in the set's hue band is traced with the effect unless --box leaves it out; a camera that moves inside the
shot moves the drawings with it (runs ended by such slow drift are SAID, their holds are not the scene's); a soft glow
round a drawing becomes its outermost tone; a shape under 2 px wide is not carried (its fit is named); a drawn point
is told from a tight round end by a narrow rule set on made shapes - a blunt inner corner (a star's, about 70
degrees) can be missed and comes back rounded by a pixel or two.
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dense  # noqa: E402

MEASURED = os.path.join("assets", "effects", "refs_measured")
BUILD = os.path.join("build", "vfx", "trace")

SPECK = 0.0004      # a piece under this share of the frame is noise, not a drawn shape
PINHOLE = 0.00015   # a hole under this share of the frame is noise, not a cut-out
FLOOD = 0.60        # a cut-out covering more of the frame than this is a flash or a background, not a drawing
EDGE = 0.35         # ... and so is one that runs along this share of the frame's border
PIECES = 48         # more pieces than this in one drawing is speckle
CUT = 0.04          # a drawing with more of its outline than this on the frame's or the box's edge is said to be cut
FIT = 0.90          # a drawing's curves, drawn again, must cover this much of its cut-out (intersection over union)
UP = 4              # an outline is read from the cut-out this many times larger (it then lies on the pixels' edges)
SMOOTH = 1.3        # px: the pixel staircase is smoothed over this much of the outline
CORNER = 48.0       # degrees: a turn sharper than this within a few px is a drawn point (a flame's tip), kept sharp
SIMPLIFY = 0.45     # px: an outline's points are thinned while the curve stays within this of the smoothed one
FLAT = 22           # of 255: a 3 x 3 patch whose colours differ by no more than this is one flat tone
LIT = 0.0008        # a frame whose cut-out covers under this share of the frame shows no drawing


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


# ------------------------------------------------------------------ the cut-out
def cut_out(frames, hue=None, box=None, floor=dense.FLOOR, lit=None):
    """(N, H, W, 3) sRGB bytes of ONE shot -> (N, H, W) bool: the effect in every frame (see the head, 1). lit (0..1):
    with a hue, only pixels at least this bright count - the floor and the walls an effect LIGHTS are in its hue band
    too, dimmer than the drawing itself"""
    frames = np.asarray(frames)
    n, h, w = frames.shape[:3]
    mask = np.zeros((n, h, w), dtype=bool)
    if hue is None:
        y = np.stack([dense.luma(frames[a:a + dense.CHUNK]) for a in range(0, n, dense.CHUNK)]) if n <= dense.CHUNK else \
            np.concatenate([dense.luma(frames[a:a + dense.CHUNK]) for a in range(0, n, dense.CHUNK)])
        y = y.reshape(n, h, w)
        mask = (y - dense.quiet(y)[None]) > floor
    else:
        for a in range(0, n, dense.CHUNK):
            m, value = dense.effect_mask(frames[a:a + dense.CHUNK], hue)
            mask[a:a + dense.CHUNK] = m if lit is None else m & (value >= float(lit))
    if box is not None:
        x0, y0, x1, y1 = box
        keep = np.zeros((h, w), dtype=bool)
        keep[int(round(y0 * h)):int(round(y1 * h)), int(round(x0 * w)):int(round(x1 * w))] = True
        mask &= keep[None]
    return mask


def clean(mask, speck=SPECK, pinhole=PINHOLE):
    """one frame's cut-out without its noise: pieces under `speck` of the frame dropped, holes under `pinhole` filled.
    Holes over that stay: a drawn flame's cut-outs are its character"""
    m = np.asarray(mask, dtype=np.uint8)
    area = float(m.size)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] < speck * area:
            m[labels == i] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(1 - m, connectivity=4)
    h, w = m.shape
    for i in range(1, count):
        x, y, bw, bh = (stats[i, k] for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        outside = x == 0 or y == 0 or x + bw == w or y + bh == h      # the picture round the effect, never a hole
        if not outside and stats[i, cv2.CC_STAT_AREA] < pinhole * area:
            m[labels == i] = 1
    return m.astype(bool)


# ------------------------------------------------------------------ the drawings
def drawings(masks, held=dense.HELD, lit=LIT, drift=None):
    """(N, H, W) bool -> [(first, last)]: runs of consecutive frames that show ONE drawing (the covered shapes of two
    neighbours differ by less than `held` of their union: the dense read's rule - AND the frame still differs by less
    than that from the run's FIRST frame: a shape that slides a pixel a frame never changes much from the frame
    before, and sixty such frames came back as one drawing held sixty - a review, 2026-11-13). Frames that show
    nothing end a run and belong to none. drift: a list that gets, per run, whether it was ended by that slow drift
    and not by a new drawing - such a run's length is where the drift passed the rule, not how long a drawing was held"""
    def change(x, y):
        union = np.logical_or(x, y).sum()
        return 1.0 - np.logical_and(x, y).sum() / float(max(union, 1))

    spans, start, before = [], None, None
    for i, m in enumerate(masks):
        if m.mean() < lit:
            if start is not None:
                spans.append((start, i - 1))
            start, before = None, None
            continue
        if start is None:
            start = i
        elif change(m, before) >= held or change(m, masks[start]) >= held:
            spans.append((start, i - 1))
            if drift is not None:
                while len(drift) < len(spans) - 1:
                    drift.append(False)
                drift.append(change(m, before) < held)
            start = i
        before = m
    if start is not None:
        spans.append((start, len(masks) - 1))
    if drift is not None:
        while len(drift) < len(spans):
            drift.append(False)
    return spans


def one_drawing(frames, masks):
    """a held drawing from ALL its frames: per pixel what most of them show (mask) and their middle colour (picture)"""
    if len(frames) == 1:
        return frames[0], masks[0]
    return np.median(frames, axis=0).astype(np.uint8), masks.mean(axis=0) >= 0.5


# ------------------------------------------------------------------ the tones
def palette(pixels, k, seed=7, rounds=16, merge=26.0):
    """(M, 3) effect pixels -> up to k flat tones, darkest first: k-means from a fixed seed (the same frames give the
    same tones), tones closer than `merge` (of 255, straight distance) folded into one - a beat drawn in two colours
    comes back as two, however many were asked for"""
    px = np.asarray(pixels, dtype=np.float32)
    if len(px) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    rng = np.random.default_rng(seed)
    if len(px) > 60000:
        px = px[rng.choice(len(px), 60000, replace=False)]
    k = max(1, min(int(k), len(np.unique(px.astype(np.uint8), axis=0))))
    centres = [px[rng.integers(len(px))]]
    for _ in range(1, k):                                    # k-means++: the next centre far from the ones chosen
        d = np.min([((px - c) ** 2).sum(axis=1) for c in centres], axis=0)
        centres.append(px[rng.choice(len(px), p=d / d.sum())] if d.sum() > 0 else px[rng.integers(len(px))])
    centres = np.array(centres, dtype=np.float32)
    for _ in range(rounds):
        nearest = np.argmin(((px[:, None, :] - centres[None]) ** 2).sum(axis=2), axis=1)
        for j in range(len(centres)):
            if (nearest == j).any():
                centres[j] = np.median(px[nearest == j], axis=0)     # the middle colour: a flat tone, not its glow's mean
    nearest = np.argmin(((px[:, None, :] - centres[None]) ** 2).sum(axis=2), axis=1)
    weight = np.array([(nearest == j).sum() for j in range(len(centres))], dtype=np.float64)
    keep = [j for j in range(len(centres)) if weight[j] > 0]
    centres, weight = centres[keep], weight[keep]
    while len(centres) > 1:                                  # fold the two closest tones while they are one colour
        d = np.sqrt(((centres[:, None] - centres[None]) ** 2).sum(axis=2)) + np.eye(len(centres)) * 1e9
        a, b = np.unravel_index(np.argmin(d), d.shape)
        if d[a, b] >= merge:
            break
        centres[a] = (centres[a] * weight[a] + centres[b] * weight[b]) / (weight[a] + weight[b])
        weight[a] += weight[b]
        centres, weight = np.delete(centres, b, axis=0), np.delete(weight, b)
    luma = centres @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return centres[np.argsort(luma, kind="stable")]


def tone_map(picture, mask, tones):
    """one drawing -> (H, W) int: -1 outside the effect, else the index of its nearest tone; slivers one or two
    pixels wide between two tones (the clip's own anti-aliasing) go to the tone round them"""
    pic = np.asarray(picture, dtype=np.float32)
    d = ((pic[:, :, None, :] - np.asarray(tones, dtype=np.float32)[None, None]) ** 2).sum(axis=3)
    label = np.argmin(d, axis=2).astype(np.uint8)
    label = cv2.medianBlur(label, 5) if min(label.shape) >= 5 else label
    return np.where(mask, label.astype(np.int16), -1)


# ------------------------------------------------------------------ the curves
def _smooth_run(pts, sigma, closed):
    """points about 1 px apart along an outline, smoothed along it; an open run keeps its two ends (they are corners)"""
    n = len(pts)
    if n < 5 or sigma <= 0:
        return pts
    r = max(1, int(math.ceil(sigma * 3)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    if closed:
        pad = np.concatenate([pts[-r:], pts, pts[:r]])
    else:                                                    # reflected through the fixed ends: the ends do not move
        pad = np.concatenate([2 * pts[0] - pts[r:0:-1], pts, 2 * pts[-1] - pts[-2:-r - 2:-1]]) if n > r + 1 else None
        if pad is None:
            return pts
    sm = np.stack([np.convolve(pad[:, 0], k, mode="valid"), np.convolve(pad[:, 1], k, mode="valid")], axis=1)
    if not closed:
        sm[0], sm[-1] = pts[0], pts[-1]
    return sm


def _thin(pts, eps):
    """an open run thinned (Ramer-Douglas-Peucker): its ends kept, every point dropped stays within eps of the line"""
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        seg = pts[b] - pts[a]
        length = float(np.hypot(*seg))
        rel = pts[a + 1:b] - pts[a]
        dist = np.abs(rel[:, 0] * seg[1] - rel[:, 1] * seg[0]) / length if length > 1e-9 else np.hypot(rel[:, 0], rel[:, 1])
        i = int(np.argmax(dist))
        if dist[i] > eps:
            keep[a + 1 + i] = True
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return pts[keep]


def _turn(pts, reach):
    back = pts - np.roll(pts, reach, axis=0)
    ahead = np.roll(pts, -reach, axis=0) - pts
    cross = back[:, 0] * ahead[:, 1] - back[:, 1] * ahead[:, 0]
    return np.degrees(np.abs(np.arctan2(cross, (back * ahead).sum(axis=1))))


def _corners(pts, reach=6, angle=CORNER):
    """indices of the sharp points of a closed outline (points about 1 px apart): where the outline turns more than
    `angle` degrees between the `reach` px before and after, AND turns nearly as much within half that reach, AND
    does not go on turning beyond it. A drawn point turns at ONE place; a tight round end (a small cut-out's) turns
    all the way along: twice the reach out it has turned twice as far. The far look is the steady one (a pixel
    stair shakes a 3 px chord by 18 degrees, a 12 px chord by 5)"""
    n = len(pts)
    if n < 4 * reach:
        return []
    turn = _turn(pts, reach)
    near = _turn(pts, max(2, reach // 2))
    turn = np.where(near > 0.80 * turn, turn, 0.0)
    if n >= 8 * reach:
        turn = np.where(turn > 0.75 * _turn(pts, 2 * reach), turn, 0.0)
    found = []
    sharp = turn > angle
    if not sharp.any():
        return []
    if sharp.all():
        return [int(np.argmax(turn))]
    start = int(np.argmin(sharp))                            # walk from a point that is not sharp: runs do not wrap
    i = 0
    while i < n:
        j = (start + i) % n
        if not sharp[j]:
            i += 1
            continue
        run = []
        while i < n and sharp[(start + i) % n]:
            run.append((start + i) % n)
            i += 1
        found.append(max(run, key=lambda q: turn[q]))
    return sorted(found)


def curve_of(contour, smooth=SMOOTH, simplify=SIMPLIFY):
    """a closed pixel outline (K, 2: x, y) -> (points (M, 2) float px, corner flags (M,) bool): see the head, 4"""
    pts = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 8:
        return pts, np.ones(len(pts), dtype=bool)
    step = np.hypot(*(np.roll(pts, -1, axis=0) - pts).T)      # resampled 1 px apart along the outline
    total = float(step.sum())
    count = max(8, int(round(total)))
    at = np.concatenate([[0.0], np.cumsum(step)])
    ring = np.concatenate([pts, pts[:1]])
    where = np.linspace(0.0, total, count, endpoint=False)
    pts = np.stack([np.interp(where, at, ring[:, 0]), np.interp(where, at, ring[:, 1])], axis=1)
    # a pixel outline turns 90 degrees at every stair: a light smoothing first, so a stair is not taken for a point
    rough = _smooth_run(pts, 0.8, True)
    corners = _corners(rough)
    if not corners:
        sm = _smooth_run(pts, smooth, True)
        far = int(np.argmax(np.hypot(*(sm - sm[0]).T)))      # a closed curve thinned as two runs between far points
        a, b = _thin(sm[:far + 1], simplify), _thin(np.concatenate([sm[far:], sm[:1]]), simplify)
        out_pts = np.concatenate([a[:-1], b[:-1]])
        return out_pts, np.zeros(len(out_pts), dtype=bool)
    out_pts, flags = [], []
    for a, b in zip(corners, corners[1:] + [corners[0] + len(pts)]):
        run = np.array([rough[i % len(pts)] if i in (a, b) else pts[i % len(pts)] for i in range(a, b + 1)])
        run = _thin(_smooth_run(run, smooth, False), simplify)
        out_pts += list(run[:-1])
        flags += [True] + [False] * (len(run) - 2)
    return np.array(out_pts), np.array(flags, dtype=bool)


def shapes_of(mask):
    """a bool picture -> [{"outer": (pts, flags), "holes": [(pts, flags), ...]}], every piece with its holes. Points
    are in px with pixel k covering k .. k + 1 (its centre at k + 0.5), and the curve lies ON the cut-out's edge: an
    outline follows the CENTRES of the boundary pixels, half a pixel inside the edge, so the picture is first made
    UP times larger - the curves came out a pixel thin, and a line 3 px wide covered two thirds of itself (a review,
    2026-11-13)"""
    small = np.asarray(mask, dtype=np.uint8)
    large = cv2.resize(small, (small.shape[1] * UP, small.shape[0] * UP), interpolation=cv2.INTER_NEAREST)
    found, hier = cv2.findContours(large, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]
    edge = lambda c: (np.asarray(c, dtype=np.float64).reshape(-1, 2) + 0.5) / UP  # noqa: E731
    shapes, index = [], {}
    for i, c in enumerate(found):
        if hier[i][3] == -1 and len(c) >= 8:
            index[i] = len(shapes)
            shapes.append({"outer": curve_of(edge(c)), "holes": []})
    for i, c in enumerate(found):
        parent = hier[i][3]
        if parent in index and len(c) >= 8:
            shapes[index[parent]]["holes"].append(curve_of(edge(c)))
    return shapes


# ------------------------------------------------------------------ drawing curves again (the check, the pictures, ink)
def outline(points, corners, per_px=1.0, scale=1.0):
    """a closed curve's points (M, 2) + corner flags -> (a dense polygon (K, 2), the indices in it of the corners): a
    smooth run passes THROUGH its points, a corner breaks it. `scale` multiplies the coordinates; a point is laid
    about every 1 / per_px px. Between two points the curve leaves along the line through its neighbours, but never
    faster than that one step is long: a long straight step beside short ones does not swing the curve out past its
    own points (a plain Catmull-Rom did, by 19 px on a real trace, 2026-11-13)"""
    pts = np.asarray(points, dtype=np.float64) * scale
    n = len(pts)
    if n < 3:
        return pts, [i for i in range(n) if np.asarray(corners, dtype=bool)[i]]
    flags = np.asarray(corners, dtype=bool)
    poly, at = [], []

    def leave(vec, limit):
        length = float(np.hypot(*vec))
        return vec * (limit / length) if length > limit > 0 else vec

    for i in range(n):
        p1, p2 = pts[i], pts[(i + 1) % n]
        if flags[i]:
            at.append(len(poly))
        step = p2 - p1
        length = float(np.hypot(*step))
        m1 = step if flags[i] else leave((p2 - pts[i - 1]) / 2.0, length)          # a corner has no tangent from before it
        m2 = step if flags[(i + 1) % n] else leave((pts[(i + 2) % n] - p1) / 2.0, length)
        steps = max(1, int(math.ceil(length * per_px)))
        t = (np.arange(steps) / steps)[:, None]
        poly.extend((2 * t ** 3 - 3 * t ** 2 + 1) * p1 + (t ** 3 - 2 * t ** 2 + t) * m1
                    + (-2 * t ** 3 + 3 * t ** 2) * p2 + (t ** 3 - t ** 2) * m2)
    return np.array(poly), at


def spline(points, corners, per_px=1.0, scale=1.0):
    """the dense polygon of `outline` alone"""
    return outline(points, corners, per_px, scale)[0]


def fill(shapes, size, scale=1.0, offset=(0.0, 0.0), ss=4):
    """shapes (px curves, pixel k covering k .. k + 1) -> (H, W) float 0..1: their filled coverage, holes cut out,
    edges anti-aliased by drawing `ss` times larger. size = (W, H); a point p lands at (p + offset) * scale"""
    w, h = int(size[0]), int(size[1])
    big = np.zeros((h * ss, w * ss), dtype=np.uint8)
    off = np.asarray(offset, dtype=np.float64)
    for sh in shapes:
        rings = [sh["outer"]] + list(sh["holes"])
        # (the polygon filler counts from pixel centres: the larger picture's pixel k has its centre at k + 0.5)
        polys = [np.rint((spline(p + off, f, per_px=scale * ss, scale=scale * ss) - 0.5) * 16).astype(np.int32) for p, f in rings]
        polys = [p for p in polys if len(p) >= 3]
        if polys:                                             # even-odd over one piece's rings: its holes stay holes
            cv2.fillPoly(big, polys, 255, lineType=cv2.LINE_8, shift=4)
    return cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


# ------------------------------------------------------------------ the trace of one shot
def trace_frames(frames, fps, hue=None, tones=3, box=None, lit=None):
    """(N, H, W, 3) frames of ONE shot -> the trace (see the head): {"size", "fps", "tones", "drawings", "refused"}.
    Curves are in px of the frames; a drawing's layers are CUMULATIVE (layer t = everything in tone t or a lighter
    one), so painting them darkest first gives the drawing back whatever sits inside what"""
    frames = np.asarray(frames)
    n, h, w = frames.shape[:3]
    masks = np.stack([clean(m) for m in cut_out(frames, hue, box, lit=lit)]) if n else np.zeros((0, h, w), dtype=bool)
    drifted = []
    spans = drawings(masks, drift=drifted)
    held = [one_drawing(frames[a:b + 1], masks[a:b + 1]) for a, b in spans]
    held = [(pic, clean(m)) for pic, m in held]
    # sparks just over a speck, each a pixel off from frame to frame: taken together, most of what they show is under a
    # speck and is cleaned away - what is left of such a drawing is nothing, and it is no drawing (it crashed)
    drifted = [x for x, (_, m) in zip(drifted, held) if m.any()]
    spans, held = [sp for sp, (_, m) in zip(spans, held) if m.any()], [(pic, m) for pic, m in held if m.any()]
    # the tones are read from each drawing's INSIDE: its outermost pixels are the clip's own anti-aliasing (the
    # drawing's colour mixed with what is behind it), and would come back as a rim tone no cel was painted with
    # ... and the same inside it, where two tones meet: only FLAT pixels count (a 3 x 3 patch of nearly one colour)
    lit = []
    for pic, m in held:
        if not m.any():
            continue
        inner = cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2).astype(bool)
        spread = (cv2.dilate(pic, np.ones((3, 3), np.uint8)).astype(np.int16) - cv2.erode(pic, np.ones((3, 3), np.uint8))).max(axis=2)
        flat = inner & (spread <= FLAT)
        lit.append(pic[flat if flat.sum() >= 50 else inner if inner.sum() >= 50 else m])
    tone_list = palette(np.concatenate(lit), tones) if lit else np.zeros((0, 3), dtype=np.float32)
    result, refused = [], []
    border = 2.0 * (w + h)
    # the kept part of the frame (the whole frame, or --box): a drawing's pixels on ITS border are a straight cut
    bx0, by0, bx1, by1 = (0, 0, w, h) if box is None else (int(round(box[0] * w)), int(round(box[1] * h)),
                                                             int(round(box[2] * w)), int(round(box[3] * h)))
    for k, ((a, b), (pic, m)) in enumerate(zip(spans, held)):
        cover = float(m.mean())
        on_edge = float(m[0].sum() + m[-1].sum() + m[:, 0].sum() + m[:, -1].sum()) / border
        pieces = cv2.connectedComponents(m.astype(np.uint8), connectivity=8)[0] - 1
        rim = m & ~cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8), borderValue=0).astype(bool)
        part = m[by0:by1, bx0:bx1]
        straight = float(part[0].sum() + part[-1].sum() + part[:, 0].sum() + part[:, -1].sum()) if part.size else 0.0
        cut = min(1.0, straight / float(max(int(rim.sum()), 1)))
        why = None
        if cover > FLOOD:
            why = f"it covers {cover * 100:.0f} % of the frame: a flash or a background, not a drawing"
        elif on_edge > EDGE:
            why = f"it runs along {on_edge * 100:.0f} % of the frame's border: the frame cuts it, its outline is not the drawing's"
        elif pieces > PIECES:
            why = f"{pieces} pieces: speckle, not a drawn shape (the colour band catches noise; --box round the effect)"
        if why:
            refused.append({"frames": [a, b], "why": why})
            continue
        label = tone_map(pic, m, tone_list)
        layers, points, holes, tips = [], 0, 0, 0
        for t in range(len(tone_list)):
            part = clean(label >= t, speck=SPECK / 4, pinhole=PINHOLE / 2) if t else m
            shapes = shapes_of(part)
            if not shapes:
                continue
            layers.append({"tone": t, "shapes": shapes})
            for sh in shapes:
                for p, f in [sh["outer"]] + sh["holes"]:
                    points += len(p)
                if len(layers) == 1:
                    tips += int(sh["outer"][1].sum())                  # the silhouette's own sharp points, not a cut-out's
            if len(layers) == 1:
                holes = sum(len(sh["holes"]) for sh in shapes)
        again = fill(layers[0]["shapes"], (w, h)) > 0.5 if layers else np.zeros_like(m)
        union = np.logical_or(again, m).sum()
        fit = float(np.logical_and(again, m).sum()) / float(max(union, 1))
        ys, xs = np.nonzero(m)
        # the drawing's middle, and how much of its silhouette is cut out (the holes' area over the area its outer
        # outline closes: 0 = solid, a ring is most of it) - the V3 doc, stage C.1: motion and cut-out grammar per drawing
        closed = _closed(m)
        cutout = float((closed & ~m).sum()) / float(max(int(closed.sum()), 1))
        result.append({"frames": [a, b], "hold": b - a + 1, "at": round(a / float(fps), 4), "cover": round(cover, 5),
                       "pieces": int(pieces), "holes": int(holes), "points": int(points), "tips": int(tips),
                       "fit": round(fit, 4), "cut": round(cut, 4), "drift": bool(drifted[k]), "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
                       "centre": [float(xs.mean()), float(ys.mean())], "cutout": round(cutout, 4), "speed": None,
                       "layers": layers})
    # how fast the drawing's middle travels from one drawing to the next, in frame widths a second (the first: None)
    for prev, d in zip(result, result[1:]):
        dt = (d["frames"][0] - prev["frames"][0]) / float(fps)
        if dt > 0:
            dx, dy = d["centre"][0] - prev["centre"][0], d["centre"][1] - prev["centre"][1]
            d["speed"] = round(float(np.hypot(dx, dy)) / float(w) / dt, 4)
    return {"size": [w, h], "fps": float(fps), "frames": int(n), "tones": tone_list, "drawings": result,
            "refused": refused, "by": "the hue band" if hue is not None else "light"}


def _closed(mask):
    """a bool picture with its holes filled: everything its outer outlines close (the background reached from the
    border is all that stays out)"""
    m = mask.astype(np.uint8)
    pad = np.pad(m, 1)
    flood = pad.copy()
    cv2.floodFill(flood, np.zeros((pad.shape[0] + 2, pad.shape[1] + 2), np.uint8), (0, 0), 2)
    return (flood != 2)[1:-1, 1:-1]


def rhythm(trace):
    """how long a drawing usually stays, in 24ths of a second (1 = on ones, 2 = on twos ...): the middle hold of the
    drawings seen whole (the first and the last may be cut by the window); None with fewer than two of them"""
    whole = [d["hold"] for d in trace["drawings"][1:-1] if not d.get("drift")]
    if len(whole) < 2:
        return None
    return max(1, int(round(float(np.median(whole)) * 24.0 / trace["fps"])))


def to_json(trace, digits=5):
    """the trace as plain numbers: curves normalised to the frame (x and y in 0..1 of its width and height), every
    point [x, y, 1 if it is a corner else 0], colours as 0..255"""
    w, h = trace["size"]

    def ring(pf):
        p, f = pf
        return [[round(float(x) / w, digits), round(float(y) / h, digits), int(c)] for (x, y), c in zip(p, f)]

    ds = []
    for d in trace["drawings"]:
        ds.append({**{k: d[k] for k in ("frames", "hold", "at", "cover", "pieces", "holes", "points", "tips", "fit", "cut", "drift",
                                        "cutout", "speed") if k in d},
                   "centre": [round(d["centre"][0] / w, digits), round(d["centre"][1] / h, digits)] if "centre" in d else None,
                   "box": [round(d["box"][0] / w, digits), round(d["box"][1] / h, digits),
                           round(d["box"][2] / w, digits), round(d["box"][3] / h, digits)],
                   "layers": [{"tone": L["tone"], "shapes": [{"outer": ring(s["outer"]), "holes": [ring(x) for x in s["holes"]]}
                                                              for s in L["shapes"]]} for L in d["layers"]]})
    return {"schema": 1, "size": [w, h], "fps": trace["fps"], "frames": trace["frames"], "on": rhythm(trace),
            "tones": [[int(round(float(c))) for c in t] for t in trace["tones"]], "drawings": ds,
            "refused": trace["refused"]}


def from_json(data):
    """a stored trace back as px curves (what fill and ink draw from)"""
    w, h = data["size"]

    def ring(r):
        a = np.asarray(r, dtype=np.float64).reshape(-1, 3)
        return a[:, :2] * np.array([w, h], dtype=np.float64), a[:, 2] > 0.5

    ds = []
    for d in data["drawings"]:
        ds.append({**d, "box": [d["box"][0] * w, d["box"][1] * h, d["box"][2] * w, d["box"][3] * h],
                   **({"centre": [d["centre"][0] * w, d["centre"][1] * h]} if d.get("centre") else {}),
                   "layers": [{"tone": L["tone"], "shapes": [{"outer": ring(s["outer"]), "holes": [ring(x) for x in s["holes"]]}
                                                              for s in L["shapes"]]} for L in d["layers"]]})
    return {**data, "tones": np.asarray(data["tones"], dtype=np.float32), "drawings": ds}


def paint(drawing, tones, size, scale=1.0, offset=(0.0, 0.0), ss=4):
    """one drawing in its flat tones -> (H, W, 4) float 0..1: STRAIGHT colour (the darkest layer's tone everywhere,
    the lighter layers over it) + the coverage. Colour that already carried the coverage, laid over a ground with the
    coverage again, drew a dark fringe round every shape (a review, 2026-11-13)"""
    w, h = int(size[0]), int(size[1])
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    alpha = np.zeros((h, w), dtype=np.float32)
    for k, L in enumerate(drawing["layers"]):
        cov = fill(L["shapes"], (w, h), scale, offset, ss)
        col = np.asarray(tones[L["tone"]], dtype=np.float32) / 255.0
        rgb = rgb + col[None, None] if k == 0 else rgb * (1 - cov[..., None]) + col[None, None] * cov[..., None]
        alpha = np.maximum(alpha, cov)
    return np.dstack([rgb, alpha])


# ------------------------------------------------------------------ the LOOK pictures
def look(trace, frames, out_dir, stem, tile=640, limit=24):
    """per drawing one picture, three panes each `tile` px wide or more: the scene's frame (the part round the beat's
    drawings), the same with the trace's outline laid on it, the trace alone in its tones -> the files written"""
    w, h = trace["size"]
    ds = trace["drawings"]
    if not ds:
        return []
    x0 = min(d["box"][0] for d in ds)
    y0 = min(d["box"][1] for d in ds)
    x1 = max(d["box"][2] for d in ds)
    y1 = max(d["box"][3] for d in ds)
    pad = 0.08 * max(x1 - x0, y1 - y0)
    x0, y0, x1, y1 = (int(max(0, x0 - pad)), int(max(0, y0 - pad)), int(min(w, x1 + pad)), int(min(h, y1 + pad)))
    scale = max(1.0, tile / float(max(1, x1 - x0)))
    pw, ph = int(round((x1 - x0) * scale)), int(round((y1 - y0) * scale))
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.startswith(f"{stem}_d") and f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))
    files = []
    for k, d in enumerate(ds[:limit]):
        a, b = d["frames"]
        scene = Image.fromarray(frames[(a + b) // 2][y0:y1, x0:x1]).resize((pw, ph), Image.LANCZOS)
        over = scene.copy()
        pen = ImageDraw.Draw(over)
        for L in d["layers"]:
            ink = (0, 255, 255) if L["tone"] == 0 else (255, 0, 255)
            for sh in L["shapes"]:
                for p, f in [sh["outer"]] + sh["holes"]:
                    poly = spline(p - np.array([x0, y0]), f, per_px=scale, scale=scale) - 0.5
                    pen.line([tuple(q) for q in poly] + [tuple(poly[0])], fill=ink, width=2)
                    for q in (p[f] - np.array([x0, y0])) * scale - 0.5:  # the points kept sharp
                        pen.ellipse([q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4], outline=(255, 255, 0), width=2)
        alone = paint(d, trace["tones"], (pw, ph), scale, (-x0, -y0))
        back = np.full((ph, pw, 3), 0.16, dtype=np.float32)
        alone = Image.fromarray((np.clip(back * (1 - alone[..., 3:]) + alone[..., :3] * alone[..., 3:], 0, 1) * 255 + 0.5).astype(np.uint8))
        head = 30
        page = Image.new("RGB", (pw * 3 + 16, ph + head), (24, 24, 28))
        for i, im in enumerate((scene, over, alone)):
            page.paste(im, (i * (pw + 8), head))
        ImageDraw.Draw(page).text((6, 8), f"drawing {k + 1} of {len(ds)}: frames {a}-{b} (held {d['hold']}), {d['pieces']} piece(s), "
                                  f"{d['holes']} cut-out(s), {d['tips']} sharp point(s), the curves cover {d['fit'] * 100:.0f} % of the "
                                  f"cut-out{', CUT by the frame or the box' if d.get('cut', 0) > CUT else ''}   |   the scene - the trace on it - the trace alone", fill=(230, 230, 230))
        path = os.path.join(out_dir, f"{stem}_d{k + 1:02d}.png")
        page.save(path)
        files.append(path.replace(os.sep, "/"))
    return files


def report(trace, what):
    """the trace said in one line + whether it is usable (status)"""
    ds, refused = trace["drawings"], trace["refused"]
    if not ds:
        if refused:
            return "fail", f"{what}: nothing to trace - {len(refused)} drawing(s) refused: {refused[0]['why']}"
        if trace.get("by") == "light":
            return "fail", (f"{what}: nothing lit up over the shot's quiet picture - with no measured hue this reads what gets "
                            f"BRIGHTER during the shot: a dark effect is not seen, and neither is one lit in EVERY frame "
                            f"(give its colours: --hue lo,hi)")
        return "fail", f"{what}: nothing lit up - this reads light and the set's colours, not a dark effect"
    loose = [k + 1 for k, d in enumerate(ds) if d["fit"] < FIT]
    on = rhythm(trace)
    said = (f"{what}: {len(ds)} drawing(s) from {trace['frames']} frame(s)"
            + (f", on {'ones twos threes'.split()[on - 1] if on <= 3 else str(on) + 's'}" if on else "")
            + f", {len(trace['tones'])} tone(s), {sum(d['holes'] for d in ds)} cut-out(s), {sum(d['tips'] for d in ds)} sharp point(s)")
    if refused:
        said += f"; {len(refused)} refused ({refused[0]['why']})"
    slow = sum(1 for d in ds if d.get("drift"))
    if slow:
        said += (f"; {slow} of them end by SLOW DRIFT, not by a new drawing (the shape moves a little every frame: a camera "
                 f"move, or motion finer than the held-drawing rule): their holds are not the scene's")
    cut = [d.get("cut", 0.0) for d in ds]
    if max(cut) > CUT:
        said += (f"; the frame or the box CUTS {sum(c > CUT for c in cut)} of them (up to {max(cut) * 100:.0f} % of an outline is "
                 f"its straight edge, not the drawing's)")
    if loose:
        return "fail", said + f"; drawing(s) {', '.join(map(str, loose))}: the curves cover under {FIT * 100:.0f} % of the cut-out"
    return "pass", said


# ------------------------------------------------------------------ the command
def _opts(argv):
    opts, names, i = {}, [], 0
    while i < len(argv):
        if argv[i] in ("--keep", "--track", "--no-track"):
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


def _pair(text, count):
    parts = [float(x) for x in str(text).split(",")]
    if len(parts) != count:
        raise ValueError(f"{text!r}: {count} numbers, comma-separated")
    return parts


def main(argv):
    """the command: ONE JSON line and a code, whatever it is given"""
    try:
        return _main(argv)
    except Exception as e:  # noqa: BLE001 - a frame that is no picture, frames of two sizes, a clip ffmpeg cannot read ...
        return out("fail", f"trace: could not be run ({type(e).__name__}: {str(e)[:200]})",
                   "lune run kit vfx trace <set> [--beat N] [--tones 3] [--lit 0.6] [--box x0,y0,x1,y1] [--window a,b] [--track]")


def _main(argv):
    opts, names = _opts(argv)
    try:
        tones = max(1, min(6, int(opts.get("--tones", 3))))
        box = _pair(opts["--box"], 4) if "--box" in opts else None
        hue = tuple(_pair(opts["--hue"], 2)) if "--hue" in opts else None
        lit = float(opts["--lit"]) if "--lit" in opts else None
    except ValueError as e:
        return out("fail", f"trace: {e}", "lune run kit vfx trace <set> [--beat N] [--tones 3] [--box x0,y0,x1,y1]")
    if box is not None and not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        return out("fail", "trace: --box is x0,y0,x1,y1 in 0..1 from the frame's top left", "e.g. --box 0.2,0.1,0.9,0.8")
    if "--frames" in opts:                                   # any folder of pictures (a fixture, a test)
        folder = opts["--frames"]
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".png", ".jpg"))) if os.path.isdir(folder) else []
        if not files:
            return out("fail", f"trace: no pictures in {folder}", "--frames <a folder of .png frames in order>")
        pictures = [np.asarray(Image.open(os.path.join(folder, f)).convert("RGB")) for f in files]
        if len({pic.shape for pic in pictures}) > 1:
            return out("fail", f"trace: the pictures in {folder} are not all one size", "frames of ONE shot, as the clip gave them")
        frames = np.stack(pictures)
        fps = float(opts.get("--fps", 24))
        if not fps > 0:
            return out("fail", "trace: --fps is the frames a second of the pictures (above 0)", "--fps 24")
        out_dir, stem, what = opts.get("--out", os.path.join(BUILD, "frames")), "trace", f"trace {folder}"
        keep_path = None
    else:
        if not names:
            return out("fail", "trace: needs a scene set", "lune run kit vfx trace <set> [--beat N]")
        name = names[0]
        import breakdown
        import denseclip as DC
        try:
            meta = json.load(open(os.path.join(MEASURED, f"{name}.breakdown.json"), encoding="utf-8"))
        except (OSError, ValueError):
            return out("fail", f"trace {name}: no breakdown to read from", f"lune run kit vfx breakdown {name} --clip <file> first")
        clip = opts.get("--clip") or meta.get("clip")
        if not clip or not os.path.isfile(clip):
            return out("fail", f"trace {name}: the scene's clip is not on this machine ({clip})",
                       f"put the owner-approved clip back under assets/effects/refs/{name}/clip/ or pass --clip <file>")
        beats = breakdown.beat_rows(name)
        if not beats:
            return out("fail", f"trace {name}: no beat with a scene time", f"fill assets/effects/refs_measured/{name}.beats.md first")
        k = int(opts.get("--beat", next((i for i, b in enumerate(beats) if b[3]), 0)))
        if not 0 <= k < len(beats):
            return out("fail", f"trace {name}: no beat {k} (there are {len(beats)})", "name a beat, from 0")
        label, t0, t1, _ = beats[k]
        hue = hue or DC.measured_hue(MEASURED, f"{name}_scene", name)
        info = DC.probe(clip)
        if "--window" in opts:
            a, b = _pair(opts["--window"], 2)
        else:
            read = DC.read_beat(clip, t0, t1, [c["t"] for c in meta.get("cuts", [])], hue, info)
            if read["main"] is None:
                return out("fail", f"trace {name} beat {k}: no shot of this beat could be read",
                           f"lune run kit vfx breakdown {name} --dense --beat {k}, or name the stretch: --window a,b (clip seconds)")
            a, b = read["shots"][read["main"]]["from"], read["shots"][read["main"]]["to"]
        b = min(b, a + 6.0)                                   # a long shot: its first six seconds
        frames = DC.frames(clip, a, b, max(320, int(opts.get("--width", 960))), info)
        fps = info[0]
        out_dir, stem, what = os.path.join(BUILD, name), f"beat{k}", f"trace {name} beat {k} ({label}, {a:.2f}-{b:.2f} s)"
        keep_path = os.path.join(MEASURED, f"{name}.trace.beat{k}.json") if opts.get("--keep") else None
    if len(frames) < 1:
        return out("fail", f"{what}: no frames", "check the window")
    # the CAMERA first (kit/vfx/track.py): a trace compares each frame with the one before, so a camera that moves
    # inside the shot makes every frame a new drawing. A beat whose camera moves is traced only from its stabilised
    # frames (--track), inside the window every frame covers; one whose camera cannot be followed (a flat background)
    # is traced as it is, and says so
    import track as TR
    camera = TR.track(frames, hue) if len(frames) > 1 else None
    tracked = None
    again = "the same command with --track"
    if opts.get("--no-track"):
        # the way out when the camera read is wrong (a large thing that moves on its own can be taken for the camera):
        # traced as the clip has it, and the trace says it was told to
        camera, tracked = None, {"skipped": "--no-track"}
    if camera is not None and camera["known"] and camera["moves"]:
        if not opts.get("--track"):
            return out("fail", f"{what}: {TR.says(camera)} - traced like this every frame would read as a new drawing",
                       f"follow the camera: {again} (lune run kit vfx track <set> --beat N shows what it follows; if what it follows is NOT the camera, --no-track traces the clip as it is)",
                       camera={k: camera[k] for k in ("known", "moves", "pan", "drift", "zoom", "followed")})
        steady, win = TR.stabilise(frames, camera)
        if steady is None or win is None or (win[2] - win[0]) < 0.3 * camera["size"][0] or (win[3] - win[1]) < 0.3 * camera["size"][1]:
            return out("fail", f"{what}: {TR.says(camera)} - so far that its frames share too small a window to trace in",
                       "trace a shorter stretch of it: --window a,b (clip seconds)")
        frames = steady
        tracked = {"window": [int(v) for v in win], "of": camera["size"], "pan": camera["pan"], "drift": camera["drift"], "zoom": camera["zoom"]}
        if box is not None:
            # --box is a share of the FRAME; the trace now runs inside the window: the same region, in the window's shares
            fw, fh = camera["size"]
            ww, wh = float(win[2] - win[0]), float(win[3] - win[1])
            box = [min(1.0, max(0.0, (box[0] * fw - win[0]) / ww)), min(1.0, max(0.0, (box[1] * fh - win[1]) / wh)),
                   min(1.0, max(0.0, (box[2] * fw - win[0]) / ww)), min(1.0, max(0.0, (box[3] * fh - win[1]) / wh))]
            if box[2] - box[0] < 0.02 or box[3] - box[1] < 0.02:
                return out("fail", f"{what}: --box lies outside the window every frame covers ({win[0]},{win[1]}-{win[2]},{win[3]} of the first frame)",
                           "a box inside that window, or a shorter stretch (--window a,b)")
    elif opts.get("--track") and (camera is None or not camera["known"]):
        return out("fail", f"{what}: --track, and {TR.says(camera) if camera else 'one frame has no camera move to follow'}",
                   "trace it without --track (a camera that cannot be followed is not stabilised), or a stretch whose background shows")
    trace = trace_frames(frames, fps, hue, tones, box, lit)
    status, said = report(trace, what)
    os.makedirs(out_dir, exist_ok=True)
    data = to_json(trace)
    if tracked and tracked.get("skipped"):
        data["tracked"] = tracked
        said += "; the camera was NOT read (--no-track)"
    elif tracked:
        data["tracked"] = tracked  # (its curves are in the WINDOW's coordinates: the part of the first frame every frame covers)
        x0, y0, x1, y1 = tracked["window"]
        said += f"; the camera followed ({tracked['pan']:g} px a frame): traced inside the window {x0},{y0}-{x1},{y1} of the first frame"
    elif camera is not None and not camera["known"] and len(trace["drawings"]) > 2 and all(d["hold"] == 1 for d in trace["drawings"]):
        said += "; CAUTION: the camera could not be followed and every drawing lasts one frame - a moving camera reads exactly so"
    store = os.path.join(out_dir, f"{stem}.json")
    with open(store, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, separators=(",", ":"))
    files = look(trace, frames, out_dir, stem, max(320, int(opts.get("--tile", 640))))
    if keep_path and status == "pass":
        with open(keep_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, separators=(",", ":"))
    where = out_dir.replace(os.sep, "/") + "/"
    numbers = {"drawings": len(data["drawings"]), "on": data["on"], "tones": data["tones"],
               "fit": [d["fit"] for d in data["drawings"]], "refused": data["refused"],
               "trace": store.replace(os.sep, "/"), "look": where, "files": files}
    if status != "pass":
        return out("fail", said + (f". LOOK: {where}" if files else ""),
                   "open the pictures: is the cut-out the effect? --box x0,y0,x1,y1 round it, --lit 0.6 to drop what it only lights, --tones for its colours, "
                   "--window a,b for another stretch; a flood or a speckle is not a drawing to take", **numbers)
    return out("pass", said + f". LOOK: {where}",
               f"open {files[0]} onward at full size: does the cyan line sit on the drawing's edge, are the cut-outs and the "
               f"sharp points the scene's? Then the drawings become a sheet: lune run kit vfx ink <key> --from {store.replace(os.sep, '/')}",
               **numbers)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
