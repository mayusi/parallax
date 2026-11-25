"""plates.py — B4: the IMPACT PLATES a ScreenGui shows over the whole screen for the frames of a hit (LIMITATIONS_FIXES_V4
§3.4 step 3, §13.3.4: "pre-bake ScreenGui halftone / kanji / drawn impact sheets (1024 x 1024)"). VfxStage's impact
element showed ONE picture; a plate here is a drawn FLIPBOOK (on ones or twos) that src/kit/VfxPlate.luau steps
through, cell by cell, on the 60 fps game clock.

    lune run kit vfx plate <key> --kind halftone|lines|kanji|drawn [--frames 16] [--focus 0.5,0.5] [--seed 1] [--rate 2]
                                 [--char 大|力|十|一]
    python kit/vfx/plates.py --specs assets/effects/plates --out build/textures        (bake every plate spec again)

The kinds (white ink on see-through: the plate is tinted in the game by ImageColor3, black or white or a colour):
  halftone  a manga dot screen bursting out of the hit: dots on a 45-degree screen whose size grows with the distance
            from the focus past a CLEAR middle (the hit itself shows through), its edge a star burst that grows from
            cell to cell
  lines     concentration lines (shuchu-sen): ink wedges from the screen's edge pointing at the focus, ending round a
            clear oval; drawn again every cell (the flicker of lines drawn on ones)
  kanji     a brush-drawn character WRITTEN ON in its stroke order (each stroke pressed in thick, released thin) from the
            kit's own stroke table (STROKES: no font file - a font's glyphs would need its licence vetted), then held
            with a hand-held tremble
  drawn     the hand-drawn impact burst: a jagged star cut out round a clear middle (8-11 big spikes, small ones
            between, every tip leaning off its ray), brush strokes swept out from its edge to a point (harai) and stone
            chips flying out; every cell DRAWN AGAIN from one plan with its points nudged (the line boil of hand-drawn
            animation) while it grows out from the hit
Every plate: frames 1 / 4 / 16 cells on a 1 x 1 / 2 x 2 / 4 x 4 grid of a 1024 x 1024 sheet; a spec beside it
(assets/effects/plates/<key>.plate.json: what VfxPlate reads - layout, frames, rate, focus) that bakes it again; the
plate's own "id" there is empty until the owner uploads build/textures/<key>.png (VfxPlate shows nothing while it is
empty). It is NOT put in assets/effects/_textures.json: that registry's every entry needs a texture spec the fx build
makes (or an uploaded id) - a plate is baked here, not by the fx build.
The checks: full (the cells fill the sheet), moves (no two neighbouring cells the same), ink (hard-edged: a plate is
drawn), clear (halftone / lines / drawn: under 2 % of the oval round the focus is inked - the hit reads through it),
cover (halftone / lines / drawn: 6..60 % of the cell inked - more is a flash, not a plate), written (kanji: the ink
only grows while the strokes are written, and the last cell holds the whole character), boil (drawn: neighbouring
cells share 35..97 % of their ink - the same burst drawn again, neither a new picture nor a held copy), taper (drawn:
the ink's widest line is 3 x its thinnest or more - a brush presses and releases; one width is a ruled vector).
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import json
import math
import os
import re
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

SPECS = os.path.join("assets", "effects", "plates")
OUT = os.path.join("build", "textures")
KINDS = ("halftone", "lines", "kanji", "drawn")
GRIDS = {1: (1, 1), 4: (2, 2), 16: (4, 4)}
SHEET = 1024
SS = 3
CLEAR = 0.02         # the share of the clear oval round the focus that may be inked
COVER = (0.06, 0.60)
BOIL = (0.35, 0.97)  # drawn: the share of ink two neighbouring cells hold in common (redrawn, neither new nor held)
TAPER = 3.0          # drawn: the widest / thinnest of the ink's line (a brush presses and releases)

# the kit's own stroke table: each stroke a polyline in a 0..1 box (x right, y down), in stroke order; drawn by hand
# from the standard forms (no font, no outside data). "w": the brush's width as a share of the box; "end": "tome" (a
# stop: the brush presses then lifts) or "harai" (a sweep: it thins to a point)
STROKES = {
    "一": [{"pts": [[0.12, 0.52], [0.5, 0.49], [0.88, 0.5]], "end": "tome"}],
    "十": [{"pts": [[0.1, 0.42], [0.5, 0.4], [0.9, 0.41]], "end": "tome"},
          {"pts": [[0.5, 0.08], [0.5, 0.5], [0.51, 0.93]], "end": "harai"}],
    "大": [{"pts": [[0.1, 0.36], [0.5, 0.34], [0.9, 0.35]], "end": "tome"},
          {"pts": [[0.52, 0.06], [0.5, 0.36], [0.42, 0.62], [0.26, 0.82], [0.08, 0.94]], "end": "harai"},
          {"pts": [[0.5, 0.38], [0.6, 0.6], [0.76, 0.8], [0.94, 0.92]], "end": "tome"}],
    "力": [{"pts": [[0.16, 0.3], [0.78, 0.28], [0.8, 0.5], [0.74, 0.78], [0.64, 0.92], [0.54, 0.86]], "end": "harai"},
          {"pts": [[0.46, 0.06], [0.45, 0.36], [0.38, 0.62], [0.24, 0.82], [0.08, 0.94]], "end": "harai"}],
}


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def checked(spec):
    """a plate spec -> the same with every field checked; ValueError names the first that is not right"""
    s = dict(spec or {})
    if s.get("kind") not in KINDS:
        raise ValueError(f"kind is one of {', '.join(KINDS)}")
    frames = s.get("frames", 16)
    if frames not in GRIDS:
        raise ValueError("frames is 1, 4 or 16 (a 1 x 1, 2 x 2 or 4 x 4 sheet the engine plays whole)")
    rate = s.get("rate", 2)
    if rate not in (1, 2, 3):
        raise ValueError("rate is 1 (on ones), 2 (on twos) or 3")
    focus = s.get("focus", [0.5, 0.5])
    if not (isinstance(focus, list) and len(focus) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                                and 0.1 <= v <= 0.9 for v in focus)):
        raise ValueError("focus is [x, y], each 0.1..0.9 of the screen")
    seed = s.get("seed", 1)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** 31:
        raise ValueError("seed is a whole number")
    char = s.get("char", "大")
    if s["kind"] == "kanji" and char not in STROKES:
        raise ValueError(f"char is one the kit's stroke table holds: {' '.join(STROKES)}")
    return {"schema": 1, "kind": s["kind"], "frames": frames, "grid": list(GRIDS[frames]), "cell": SHEET // GRIDS[frames][0],
            "rate": rate, "focus": [float(focus[0]), float(focus[1])], "seed": seed,
            "mode": "OneShot", **({"char": char} if s["kind"] == "kanji" else {})}


# ------------------------------------------------------------------ the drawings (one cell -> alpha 0..1)
def halftone(spec, k):
    n = spec["cell"] * SS
    fx, fy = spec["focus"][0] * n, spec["focus"][1] * n
    rng = np.random.default_rng(spec["seed"])
    spikes = rng.uniform(0.75, 1.25, 24)
    u = k / max(spec["frames"] - 1, 1)
    pitch = n / 26.0
    img = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(img)
    reach = 0.26 + 0.46 * (1 - (1 - u) ** 2)               # the burst grows out from the hit
    clear = 0.14 + 0.05 * u
    c, s = math.cos(math.pi / 4), math.sin(math.pi / 4)
    span = int(n * 1.5 / pitch) + 2
    for i in range(-span, span):
        for j in range(-span, span):
            x = fx + (i * c - j * s) * pitch
            y = fy + (i * s + j * c) * pitch
            if not (-pitch < x < n + pitch and -pitch < y < n + pitch):
                continue
            dx, dy = (x - fx) / n, (y - fy) / n
            r = math.hypot(dx, dy)
            ang = (math.atan2(dy, dx) / (2 * math.pi) + 0.5 + 0.02 * k) % 1.0
            edge = reach * spikes[int(ang * len(spikes)) % len(spikes)]
            if r < clear or r > edge:
                continue
            tone = min(1.0, (r - clear) / max(edge - clear, 1e-6) * 1.4)
            rad = pitch * 0.56 * tone
            if rad > 0.6:
                d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=255)
    return np.asarray(img, dtype=np.float32) / 255.0


def lines(spec, k):
    n = spec["cell"] * SS
    fx, fy = spec["focus"][0] * n, spec["focus"][1] * n
    rng = np.random.default_rng(spec["seed"] * 1009 + k)    # drawn again every cell
    img = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(img)
    count = 90
    for i in range(count):
        a = (i + rng.uniform(-0.4, 0.4)) / count * 2 * math.pi
        far = n * 1.2
        base = (fx + math.cos(a) * far, fy + math.sin(a) * far)
        stop = n * (0.2 + rng.uniform(0.0, 0.16)) * (1.25 if abs(math.cos(a)) > 0.7 else 1.0)   # an oval clear middle
        tip = (fx + math.cos(a) * stop, fy + math.sin(a) * stop)
        half = rng.uniform(0.004, 0.016) * 2 * math.pi
        if rng.uniform() < 0.25:
            continue                                        # a gap: the lines are not a fan
        b1 = (fx + math.cos(a - half) * far, fy + math.sin(a - half) * far)
        b2 = (fx + math.cos(a + half) * far, fy + math.sin(a + half) * far)
        d.polygon([b1, tip, b2], fill=255)
        del base
    return np.asarray(img, dtype=np.float32) / 255.0


def _brush(d, pts, w, end, n, upto):
    """a stroke drawn by a brush: pressed in thick, then a tome (stop: a blob, lifted) or a harai (sweep: thinning to
    a point); `upto` 0..1 of its length drawn (the write-on)"""
    p = np.asarray(pts, dtype=np.float64) * n
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    L = float(seg.sum())
    if L <= 0 or upto <= 0:
        return
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    steps = max(8, int(L / 2))
    for s in np.linspace(0.0, min(1.0, upto), steps):
        dist = s * L
        i = min(int(np.searchsorted(cum, dist, side="right")) - 1, len(seg) - 1)
        t = (dist - cum[i]) / max(seg[i], 1e-9)
        x, y = p[i] + (p[i + 1] - p[i]) * t
        press = 1.0 + 0.12 * max(0.0, 1.0 - s / 0.1)          # pressed in (an entry, not a knob)
        if end == "harai":
            width = w * press * max(0.08, 1.0 - max(0.0, s - 0.45) / 0.55)
        else:
            width = w * press * (1.0 + 0.06 * max(0.0, (s - 0.9) / 0.1))
        r = width * n / 2                                     # a flat brush held at 45 degrees: an ellipse
        d.polygon([(x + r * 0.95 * math.cos(a) * math.cos(0.7) - r * 0.6 * math.sin(a) * math.sin(0.7),
                    y + r * 0.95 * math.cos(a) * math.sin(0.7) + r * 0.6 * math.sin(a) * math.cos(0.7))
                   for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)], fill=255)


def kanji(spec, k):
    n = spec["cell"] * SS
    strokes = STROKES[spec["char"]]
    img = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(img)
    done = min(1.0, (k + 1) / max(spec["frames"] * 0.7, 1.0))   # written over the first 70 % of the cells, then held
    per = 1.0 / len(strokes)
    rng = np.random.default_rng(spec["seed"] * 31 + k)
    jitter = (0.0, 0.0) if done < 1.0 else (rng.uniform(-0.006, 0.006), rng.uniform(-0.006, 0.006))
    for i, st in enumerate(strokes):
        upto = (done - i * per) / per
        pts = [[0.12 + 0.76 * (x + jitter[0]), 0.12 + 0.76 * (y + jitter[1])] for x, y in st["pts"]]
        _brush(d, pts, 0.085, st["end"], n, upto)
    return np.asarray(img, dtype=np.float32) / 255.0


def _polygon(cx, cy, pts):
    return [(cx + r * math.cos(a), cy + r * math.sin(a)) for a, r in pts]


def drawn(spec, k):
    """the hand-drawn impact burst: a jagged star cut out round a clear middle (spikes of uneven length, each tip a
    point, the inner edge rough), brush strokes thrown out from the tips (pressed in, swept off to a point: harai),
    stone chips flying out along their rays. Every cell is DRAWN AGAIN from the same plan with its points nudged (the
    line boil of hand-drawn animation) while the burst grows out from the hit and the strokes reach further"""
    n = spec["cell"] * SS
    fx, fy = spec["focus"][0] * n, spec["focus"][1] * n
    plan = np.random.default_rng(spec["seed"] * 7919 + 17)       # the drawing: fixed for every cell
    boil = np.random.default_rng(spec["seed"] * 104729 + k * 31 + 5)   # the hand: different every cell
    u = 1.0 if spec["frames"] == 1 else k / (spec["frames"] - 1)
    grow = 0.58 + 0.42 * (1 - (1 - u) ** 2)
    hole = 0.15 + 0.015 * grow                                     # the clear middle's edge (share of the cell)
    # the spikes: 8-11 big ones, each sector holding one or two small ones off-centre (a drawn burst is never a gear)
    big = int(plan.integers(8, 12))
    sector = 2 * math.pi / big
    base = plan.uniform(0, 2 * math.pi)
    angles, tips = [], []
    for i in range(big):
        a0 = base + i * sector + plan.uniform(-0.12, 0.12) * sector
        angles.append(a0)
        tips.append(plan.uniform(0.2, 0.34) * (1.3 if plan.uniform() < 0.3 else 1.0))
        smalls = 1 if plan.uniform() < 0.6 else 2
        for s in range(smalls):
            angles.append(a0 + sector * (s + 1) / (smalls + 1) + plan.uniform(-0.08, 0.08) * sector)
            tips.append(plan.uniform(0.06, 0.13))
    order = np.argsort(np.mod(np.asarray(angles) - base, 2 * math.pi))
    angles = [angles[i] for i in order]
    tips = [tips[i] for i in order]
    spikes = len(angles)
    step = 2 * math.pi / spikes
    valleys = plan.uniform(0.025, 0.055, spikes)
    lean = plan.uniform(-0.22, 0.22, spikes) * step                # a tip leans off its own ray: drawn, not plotted

    def nudge(r, amount=0.012):
        return r + boil.uniform(-amount, amount) * n

    outer, inner = [], []
    for i in range(spikes):
        a = angles[i]
        nxt = angles[(i + 1) % spikes] + (2 * math.pi if i == spikes - 1 else 0.0)
        outer.append((a + lean[i] + boil.uniform(-0.03, 0.03) * step, nudge((hole + tips[i] * grow) * n, 0.008)))
        outer.append(((a + nxt) / 2 + boil.uniform(-0.05, 0.05) * step, nudge((hole + valleys[i] * grow) * n)))
    for j in range(spikes * 3):
        a = base + j * step / 3
        inner.append((a, nudge(n * hole + n * 0.01 * math.sin(j * 2.3 + spec["seed"]), 0.006)))
    img = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(img)
    d.polygon(_polygon(fx, fy, outer), fill=255)
    d.polygon(_polygon(fx, fy, inner), fill=0)
    # strokes thrown out from the tips: start inside the tip's reach, swept outward with a slight curve, the far ones
    # longer as the cells go on
    for i in range(spikes):
        if plan.uniform() < 0.35:
            continue
        a = angles[i] + (plan.uniform(0.3, 0.6) * step) * (1 if plan.uniform() < 0.5 else -1)   # between two tips
        r0 = hole + (valleys[i] + 0.02) * grow                     # out of the burst's own edge (joined to it)
        reach = (0.12 + 0.2 * plan.uniform()) * (0.45 + 0.55 * u)
        bend = plan.uniform(-0.3, 0.3)
        pts = []
        for s in (0.0, 0.5, 1.0):
            r = r0 + reach * s
            aa = a + bend * reach * s * s
            pts.append([fx / n + r * math.cos(aa) + boil.uniform(-0.002, 0.002), fy / n + r * math.sin(aa) + boil.uniform(-0.002, 0.002)])
        _brush(d, pts, plan.uniform(0.014, 0.028), "harai", n, 1.0)
    # stone chips: small sharp shards out along their rays, turning as they fly
    for c in range(int(plan.integers(9, 15))):
        a = plan.uniform(0, 2 * math.pi)
        r = (hole + (0.2 + 0.14 * plan.uniform()) * grow * (1.0 + 0.4 * u)) * n
        size = (0.008 + 0.012 * plan.uniform()) * n
        spin = plan.uniform(0, 2 * math.pi) + k * plan.uniform(0.3, 0.9)
        cx, cy = fx + r * math.cos(a), fy + r * math.sin(a)
        d.polygon([(cx + size * s * math.cos(spin + t), cy + size * s * math.sin(spin + t))
                   for t, s in ((0.0, 1.3), (2.3, 0.8), (4.1, 1.0))], fill=255)
    return np.asarray(img, dtype=np.float32) / 255.0


DRAW = {"halftone": halftone, "lines": lines, "kanji": kanji, "drawn": drawn}


def bake(spec):
    """a checked spec -> (cells (cell, cell) alpha, the sheet as RGBA uint8, checks)"""
    cells = []
    for k in range(spec["frames"]):
        big = DRAW[spec["kind"]](spec, k)
        cells.append(cv2.resize(big, (spec["cell"], spec["cell"]), interpolation=cv2.INTER_AREA))
    cols, rows = spec["grid"]
    sheet = np.zeros((SHEET, SHEET), np.float32)
    for i, c in enumerate(cells):
        r, q = divmod(i, cols)
        sheet[r * spec["cell"]:(r + 1) * spec["cell"], q * spec["cell"]:(q + 1) * spec["cell"]] = c
    rgba = np.dstack([np.full((SHEET, SHEET), 255, np.uint8)] * 3 + [(sheet * 255 + 0.5).astype(np.uint8)])
    return cells, rgba, checks(spec, cells)


def checks(spec, cells):
    out_ = []

    def add(name, ok, value, limit, fix):
        out_.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": "" if ok else fix})

    cols, rows = spec["grid"]
    add("full", len(cells) == cols * rows, [len(cells), cols * rows], "as many cells as the sheet has",
        "the engine plays every cell of a sheet")
    if len(cells) > 1:
        still = min(float(np.abs(cells[i + 1] - cells[i]).mean()) for i in range(len(cells) - 1))
        add("moves", still > 0.0005 or spec["kind"] == "kanji", round(still, 5), "> 0.0005 between neighbouring cells",
            "two neighbouring cells are the same drawing")
    soft = 0.0
    for a in cells:
        inside = (a > 0.5).astype(np.uint8)
        edge = float(sum(cv2.arcLength(c, True) for c in cv2.findContours(inside, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0]))
        if edge > 0:
            soft = max(soft, float(((a > 0.1) & (a < 0.9)).sum()) / edge)
    add("ink", soft <= 3.0, round(soft, 2), "<= 3 px of soft edge per px of outline", "the plate is soft: a plate is drawn ink")
    n = spec["cell"]
    if spec["kind"] == "drawn":
        # boil: every cell the SAME drawing drawn again - neighbours share most of their ink (not a new picture) and
        # never all of it (not a copy held: a still plate reads as a sticker)
        if len(cells) > 1:
            ious = []
            for i in range(len(cells) - 1):
                a, b = cells[i] > 0.5, cells[i + 1] > 0.5
                ious.append(float((a & b).sum()) / max(float((a | b).sum()), 1.0))
            add("boil", BOIL[0] <= min(ious) and max(ious) <= BOIL[1], [round(min(ious), 3), round(max(ious), 3)],
                f"{BOIL[0]}..{BOIL[1]} of the ink shared by neighbouring cells",
                "each cell is the same burst drawn again: not a new picture, not a held copy")
        # taper: a brush line presses in and sweeps off to a point - the widths along the ink's middle range widely
        # (a ruled, one-width line reads as a vector, not a drawing)
        worst = None
        for a in cells:
            ink = (a > 0.5).astype(np.uint8)
            dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
            ridge = (dist >= cv2.dilate(dist, np.ones((3, 3), np.uint8))) & (dist > 0.5)
            widths = dist[ridge]
            if widths.size >= 20:
                spread = float(np.percentile(widths, 90) / max(np.percentile(widths, 10), 0.5))
                worst = spread if worst is None else min(worst, spread)
        add("taper", worst is not None and worst >= TAPER, round(worst or 0.0, 2), f">= {TAPER}: widest / thinnest of the ink's line",
            "the strokes are one width: a drawn stroke presses in and sweeps off to a point")
    if spec["kind"] in ("halftone", "lines", "drawn"):
        yy, xx = np.mgrid[0:n, 0:n]
        fx, fy = spec["focus"][0] * n, spec["focus"][1] * n
        oval = ((xx - fx) / (0.12 * n)) ** 2 + ((yy - fy) / (0.12 * n)) ** 2 <= 1.0
        worst = max(float((a[oval] > 0.5).mean()) for a in cells)
        add("clear", worst <= CLEAR, round(worst, 4), f"<= {CLEAR} of the oval round the focus inked",
            "the plate covers the hit: its middle must stay clear")
        covers = [float((a > 0.5).mean()) for a in cells]
        add("cover", COVER[0] <= min(covers) and max(covers) <= COVER[1], [round(min(covers), 3), round(max(covers), 3)],
            f"{COVER[0]}..{COVER[1]} of every cell inked", "a plate inks part of the screen (more is a flash, less is nothing)")
    else:
        ink = [float((a > 0.5).mean()) for a in cells]
        grows = all(ink[i + 1] >= ink[i] - 0.002 for i in range(len(ink) - 1) if (i + 1) / max(len(ink) * 0.7, 1) < 1.0)
        whole = DRAW["kanji"]({**spec, "frames": 1}, 0)
        whole = cv2.resize(whole, (n, n), interpolation=cv2.INTER_AREA)
        last = abs(float((cells[-1] > 0.5).mean()) - float((whole > 0.5).mean())) < 0.01
        add("written", grows and last and ink[0] < ink[-1] or len(cells) == 1, [round(x, 3) for x in ink[:3]] + ["..", round(ink[-1], 3)],
            "the ink grows stroke by stroke and the last cell holds the whole character", "the character is not written on")
    return out_


def write(key, spec, rgba, out_dir=OUT, specs_dir=SPECS):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(specs_dir, exist_ok=True)
    png = os.path.join(out_dir, f"{key}.png")
    Image.fromarray(rgba, "RGBA").save(png)
    path = os.path.join(specs_dir, f"{key}.plate.json")
    old_id = ""
    if os.path.isfile(path):                                   # baked again: an uploaded id is kept
        try:
            old_id = json.load(open(path, encoding="utf-8")).get("id", "")
        except (OSError, ValueError, AttributeError):
            old_id = ""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({**spec, "texture": key, "file": png.replace(os.sep, "/"), "id": old_id}, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return png


def look(cells, path, tile=256):
    """the cells side by side over a mid-grey ground (white ink reads on it), for LOOKING"""
    row = Image.new("RGB", (tile * len(cells), tile), (90, 92, 104))
    for i, a in enumerate(cells):
        t = cv2.resize(a, (tile, tile), interpolation=cv2.INTER_AREA)
        ground = np.full((tile, tile, 3), (90, 92, 104), np.float32)
        px = ground * (1 - t[..., None]) + 255.0 * t[..., None]
        row.paste(Image.fromarray(px.astype(np.uint8)), (i * tile, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row.save(path)


def options(argv):
    opts, names, i = {}, [], 0
    while i < len(argv):
        if argv[i].startswith("--"):
            if i + 1 >= len(argv):
                raise ValueError(f"{argv[i]} needs a value")
            opts[argv[i]] = argv[i + 1]
            i += 1
        else:
            names.append(argv[i])
        i += 1
    return opts, names


def build_step(opts):
    specs, out_dir = opts.get("--specs", SPECS), opts.get("--out", OUT)
    done, bad = [], []
    for f in sorted(os.listdir(specs)) if os.path.isdir(specs) else []:
        if not f.endswith(".plate.json"):
            continue
        key = f[:-len(".plate.json")]
        with open(os.path.join(specs, f), encoding="utf-8") as fh:
            spec = checked(json.load(fh))
        cells, rgba, cks = bake(spec)
        if any(not c["ok"] for c in cks):
            bad.append(key)
            continue
        os.makedirs(out_dir, exist_ok=True)
        Image.fromarray(rgba, "RGBA").save(os.path.join(out_dir, f"{key}.png"))
        done.append(key)
    if bad:
        return out("fail", f"plates: {len(bad)} plate(s) fail their checks: {', '.join(bad)}", "lune run kit vfx plate <key> ... names the check")
    return out("pass", f"plates: {len(done)} plate(s) baked again", "none", baked=done)


def main(argv):
    try:
        opts, names = options(argv)
    except ValueError as e:
        return out("fail", f"plate: {e}", "lune run kit vfx plate <key> --kind halftone|lines|kanji|drawn")
    if "--specs" in opts and not names:
        return build_step(opts)
    usage = "lune run kit vfx plate <key> --kind halftone|lines|kanji|drawn [--frames 16] [--focus 0.5,0.5] [--rate 2] [--char 大]"
    if not names:
        return out("fail", "plate: needs a key for the plate", usage)
    key = names[0]
    if not re.fullmatch(r"[a-z0-9_]{1,60}", key):
        return out("fail", f"plate: {key!r} is not a texture key (lower-case letters, digits, _)", usage)
    try:
        raw = {"kind": opts.get("--kind"), "frames": int(opts.get("--frames", 16)), "rate": int(opts.get("--rate", 2)),
               "seed": int(opts.get("--seed", 1)), "char": opts.get("--char", "大")}
        if opts.get("--focus"):
            raw["focus"] = [float(v) for v in str(opts["--focus"]).split(",")]
        spec = checked(raw)
    except (ValueError, TypeError) as e:
        return out("fail", f"plate {key}: {e}", usage)
    cells, rgba, cks = bake(spec)
    bad = [c for c in cks if not c["ok"]]
    if bad:
        return out("fail", f"plate {key}: " + "; ".join(f"{c['name']} {c['value']} (wants {c['limit']}): {c['fix']}" for c in bad),
                   "nothing was written: another --focus / --seed, or the kind named", checks=cks)
    png = write(key, spec, rgba, opts.get("--out", OUT), opts.get("--specs-dir", SPECS))
    strip = os.path.join(opts.get("--look-dir", os.path.join("build", "vfx", "plates")), f"{key}_strip.png")
    look(cells, strip)
    return out("pass", f"plate {key}: {spec['kind']} {spec['frames']} cell(s) ({spec['grid'][0]} x {spec['grid'][1]} of "
                       f"{spec['cell']} px) at {60 // spec['rate']} drawings a second of the 60 fps clock; every check passes",
               f"LOOK at {strip.replace(os.sep, '/')}; then name it in a sequence beat: \"impact_plate\": {{\"plate\": \"{key}\", \"frames\": n}}",
               sheet=png.replace(os.sep, "/"), strip=strip.replace(os.sep, "/"), checks=cks)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
