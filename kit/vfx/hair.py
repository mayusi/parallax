"""hair.py - HAIR AND FUR, SIMULATED AND BAKED (the VFX methods audit, stage 19): strands rooted on a head or along
a line, each a chain that keeps its length, with a little stiffness, in gravity and wind, swung by what it is
rooted on - it lags the turn, overshoots and settles. Baked as RIBBONS (one strip a strand) into a mesh sequence
the `seq` mesh shape replays (the sequence's `strips`: separate grids no face joins).

    lune run kit vfx hair <name> [--root cap|line] [--strands 16] [--length 3] [--width 0.25] [--head 1.2]
                                 [--move toss|sway|none] [--amount 0.8] [--wind 0,0,0] [--gust 0.5]
                                 [--stiff 0.15] [--gravity 40] [--loop] [--frames 48] [--fps 24] [--segments 8]

  --root cap     strands grow out of the top of a head (a ball `--head` studs across; the hair lies over it and does
                 not go through it) | line = strands hang from a row `--head` studs long (a mane, a tassel, a fringe)
  --length l     a strand's length in studs (the bake is unit size: a strand is 1 long; the layer's scale sizes it)
  --move         toss = the root turns left and right (`--amount` radians each way) | sway = it slides side to side
                 (`--amount` studs each way) | none = only the wind moves the hair
  --stiff 0..1   0 = wet string, 0.15 = hair, 0.6 = bristles (fur: short --length, more --stiff, more --strands)
  --loop         the root's move and the wind come round once a sequence; the hair is swung six times round before
                 the frames are kept, the remainder taken out over the last quarter

A strand is points a segment apart (kit/vfx/pbd.py: points that keep their distances): every step each point
falls and is blown, then the segments are pulled back to their length, each point a little toward straight on from
the two before it (`--stiff`), and out of the head. Strands do not collide with one another.

Writes assets/effects/seq/<name>.json (the mesh sequence format, with "strips": one a strand, 2 points wide) and a
picture of six of its frames. A bake is refused when the hair does not move, a strand stretches, the roots come
apart, the hair moves as one stiff piece, a ribbon turns over, or it jumps. `check(data)` is that list from a FILE's own frames.
"""
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbd  # noqa: E402

OUT = os.path.join("assets", "effects", "seq")
LOOK = os.path.join("build", "vfx", "hair")
ROOTS, MOVES = ("cap", "line"), ("toss", "sway", "none")
RATE, ITERS = 240, 16  # the strands are stepped RATE times a second, whatever the bake's fps
STILL = 0.05    # the least a strand's tip moves a SECOND, on average, in strand lengths
LENGTH = (0.9, 1.1)  # a strand's length along its middle, against 1, in every frame
POP = 0.35      # the most a tip moves in one frame, in strand lengths
LIMP = 0.02     # how far some point must be off the best rigid move of the whole first frame (a strand length = 1)


def roots(a):
    """the strands' roots and the way each grows, on the body at rest: (strands, 3) each"""
    n, r = a["strands"], a["head"] / 2
    if a["root"] == "line":
        x = (np.arange(n) + 0.5) / n - 0.5
        pos = np.stack([x * a["head"], np.zeros(n), np.zeros(n)], -1)
        out = np.tile(np.array([0.0, -1.0, 0.0]), (n, 1))  # a fringe hangs
        return pos, out
    k = np.arange(n) + 0.5
    polar = np.arccos(1 - 0.9 * k / n)  # the top of the ball, down to a little past half way
    turn = k * math.pi * (3 - math.sqrt(5))
    out = np.stack([np.sin(polar) * np.cos(turn), np.cos(polar), np.sin(polar) * np.sin(turn)], -1)
    return out * r, out


def body(a, t, period):
    """where the body is at time t: (the angle it is turned about y, how far it has slid along x)"""
    if a["move"] == "none":
        return 0.0, 0.0
    swing = math.sin(2 * math.pi * t / period)
    return (a["amount"] * swing, 0.0) if a["move"] == "toss" else (0.0, a["amount"] * swing)


def placed(v, angle, slide):
    c, s = math.cos(angle), math.sin(angle)
    return np.stack([v[..., 0] * c + v[..., 2] * s + slide, v[..., 1], -v[..., 0] * s + v[..., 2] * c], -1)


def air(pos, t, wind, gust, period):
    speed = float(np.linalg.norm(wind))
    if speed <= 0:
        return np.zeros_like(pos)
    turn = 2 * math.pi / period
    w = [max(1, round(f / turn)) * turn for f in (3.7, 6.1)]
    swell = 1 + gust * (0.6 * np.sin(w[0] * t + 0.8 * pos[..., 0]) + 0.4 * np.sin(w[1] * t + 1.1 * pos[..., 1]))
    return wind * swell[..., None]


def simulate(a):
    """a = the checked arguments -> the frames, each (strands, points, 3): the strands' middles, in STUDS; and the
    body's (angle, slide) of each frame"""
    n, pts, seg = a["strands"], a["segments"] + 1, a["length"] / a["segments"]
    period = a["frames"] / a["fps"] if a["loop"] else 2.0
    dt = 1.0 / RATE  # (one step for every bake: the same hair at any --fps; a frame is read between two steps)
    r0, n0 = roots(a)
    # every strand's points, then one held point a segment BEHIND each root (what the first segment is kept straight
    # on from: the way the strand grows out of its body)
    at = lambda st, k: st * pts + k  # noqa: E731
    behind = lambda st: n * pts + st  # noqa: E731
    links = []
    for st in range(n):
        for k in range(pts - 1):
            links.append((at(st, k), at(st, k + 1), seg, 1.0))
        if a["stiff"] > 0:
            links.append((behind(st), at(st, 1), 2 * seg, a["stiff"]))
            for k in range(pts - 2):
                links.append((at(st, k), at(st, k + 2), 2 * seg, a["stiff"]))
    sets = pbd.groups(links, n * pts + n)
    weight = np.ones(n * pts + n)
    held = np.array([at(st, 0) for st in range(n)] + [behind(st) for st in range(n)])
    weight[held] = 0.0
    pos = np.concatenate([(r0[:, None, :] + n0[:, None, :] * (np.arange(pts) * seg)[None, :, None]).reshape(-1, 3), r0 - n0 * seg])
    prev = pos.copy()
    g = np.array([0.0, -a["gravity"], 0.0])
    wind = np.array(a["wind"], dtype=float)
    head = a["head"] / 2 * 1.04 if a["root"] == "cap" else 0.0
    t = 0.0

    def step():
        nonlocal pos, prev, t
        t += dt
        angle, slide = body(a, t, period)
        root, grow = placed(r0, angle, slide), placed(n0, angle, 0.0)
        vel = (pos - prev) / dt
        acc = g + (air(pos, t, wind, a["gust"], period) - vel) * a["drag"]
        new = pbd.step(pos, prev, acc, dt, a["damp"])
        new[held] = np.concatenate([root, root - grow * seg])
        old = pos
        for _ in range(ITERS):
            pbd.solve(new, weight, sets, 1)
            if head:
                centre = np.array([slide, 0.0, 0.0])
                off = new[: n * pts] - centre
                far = np.linalg.norm(off, axis=-1, keepdims=True)
                inside = (far < head)[:, 0] & (weight[: n * pts] > 0)
                new[: n * pts][inside] = (centre + off / np.maximum(far, 1e-9) * head)[inside]
                old[: n * pts][inside] += (new[: n * pts][inside] - old[: n * pts][inside]) * 0.3  # the head rubs: hair lying on it does not skate
        prev, pos = old, new

    last = pos.copy()

    def upto(target):
        """step until `target` seconds, and say where the points are AT it (between the last two steps)"""
        nonlocal last
        while t < target - 1e-12:
            last = pos.copy()
            step()
        m = min(max((target - (t - dt)) / dt, 0.0), 1.0)
        return (last + (pos - last) * m)[: n * pts].reshape(n, pts, 3)

    n_out = a["frames"]
    warm = max(3.0, 6 * n_out / a["fps"] if a["loop"] else 0.0)
    upto(warm)
    blend = max(2, n_out // 4) if a["loop"] else 0
    raw, where = [], []
    for f in range(n_out + blend):
        at_t = warm + (f + 1) / a["fps"]
        raw.append(upto(at_t))
        where.append(body(a, at_t, period))
    if not blend:
        return raw, where
    out = []
    for i in range(n_out):
        k = i - (n_out - blend)
        if k < 0:
            out.append(raw[i + blend])
        else:
            m = (k + 1) / (blend + 1)
            m = m * m * (3 - 2 * m)
            out.append(raw[i + blend] * (1 - m) + raw[k] * m)
    return out, where[blend:]


def ribbons(mid, a, where):
    """a frame's strand middles (strands, points, 3) and its body's (angle, slide) -> its ribbons' points, strip after
    strip, each strip row by row (root to tip), 2 points a row: (strands * points * 2, 3).
    A ribbon's flat side starts as its root's own (fixed on the body: across the way the strand grows) and is CARRIED
    down the strand, at each point only what its direction makes it turn: it cannot flip over from one row to the
    next or from one frame to the next (a side worked out afresh at each point did, wherever a strand pointed at
    its head's middle)"""
    angle = where[0]
    pts = mid.shape[1]
    tan = np.gradient(mid, axis=1)
    tan = tan / np.maximum(np.linalg.norm(tan, axis=-1, keepdims=True), 1e-9)
    grow = roots(a)[1]
    side = np.cross(grow, np.array([0.0, 1.0, 0.0]))
    thin = np.linalg.norm(side, axis=-1, keepdims=True) < 1e-6  # (a strand that grows straight up or down: across is x)
    side = placed(np.where(thin, np.array([1.0, 0.0, 0.0]), side), angle, 0.0)
    side = side / np.maximum(np.linalg.norm(side, axis=-1, keepdims=True), 1e-9)
    sides = []
    for k in range(pts):
        flat = side - (side * tan[:, k]).sum(-1, keepdims=True) * tan[:, k]
        size = np.linalg.norm(flat, axis=-1, keepdims=True)
        side = np.where(size > 1e-6, flat / np.maximum(size, 1e-9), side)
        sides.append(side)
    side = np.stack(sides, 1)
    taper = a["width"] / 2 * (1 - 0.85 * (np.arange(pts) / (pts - 1)) ** 1.5)
    left, right = mid - side * taper[None, :, None], mid + side * taper[None, :, None]
    return np.stack([left, right], 2).reshape(-1, 3)  # strand, row, across


def fit(first, now):
    """the turn (3 x 3) that best lays the points `first` onto `now`, each about its own middle (Kabsch)"""
    p, q = first - first.mean(0), now - now.mean(0)
    u, _, vt = np.linalg.svd(p.T @ q)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    return vt.T @ np.diag([1.0, 1.0, d]) @ u.T


def check(data, loop=None, play=None):
    """the checks of a hair FILE, from its own frames (unit size: a strand is 1 long): [{name, ok, value, limit, fix}]"""
    a = data.get("args") if isinstance(data.get("args"), dict) else {}
    cols, rows, strips, frames = data.get("cols"), data.get("rows"), data.get("strips"), data.get("frames")
    whole = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
    sound = (data.get("recipe") == "hair" and cols == 1 and whole(rows) and rows >= 2 and whole(strips) and 2 <= strips <= 64
             and isinstance(frames, list) and len(frames) >= 2)
    if sound:
        try:
            arr = np.array(frames, dtype=float)
            sound = arr.shape == (len(frames), strips * (rows + 1) * 2 * 3) and bool(np.isfinite(arr).all())
        except (ValueError, TypeError):
            sound = False
    if not sound:
        return [{"name": "a hair bake", "ok": False, "value": "not one", "limit": "recipe hair, its strips (2 points wide), every frame whole",
                 "fix": "bake it again: lune run kit vfx hair <name>"}]
    fps = a.get("fps") if isinstance(a.get("fps"), (int, float)) and not isinstance(a.get("fps"), bool) and a.get("fps") > 0 else 24
    g = arr.reshape(len(frames), strips, rows + 1, 2, 3)
    mid = g.mean(3)  # (frames, strands, points, 3)
    segs = np.linalg.norm(mid[:, :, 1:] - mid[:, :, :-1], axis=-1)
    length = segs.sum(-1)
    even = float((segs.max(-1) / np.maximum(segs.min(-1), 1e-9)).max())
    root, tip = mid[:, :, 0], mid[:, :, -1]
    apart = np.linalg.norm(root[:, :, None] - root[:, None, :], axis=-1)
    rigid = float(np.abs(apart - apart[0:1]).max())
    tips = np.linalg.norm(tip[1:] - tip[:-1], axis=-1)
    moved = float(tips.mean())
    # is it hair, or one stiff piece? The whole head of hair against ITSELF: laid by its best rigid move (any turn,
    # any slide) onto its shape in the first frame, how far a point of it is still off. A stiff piece riding its
    # body, turned or tilted about any axis, leaves nothing; hair that lags, swings or bends does
    hang = tip - root
    first = mid[0].reshape(-1, 3)
    bend = 0.0
    for f in range(1, len(frames)):
        now = mid[f].reshape(-1, 3)
        bend = max(bend, float(np.linalg.norm((first - first.mean(0)) @ fit(first, now).T - (now - now.mean(0)), axis=-1).max()))
    own = hang[1:] - hang[:-1]  # a tip's move with its own root's taken out
    worst = float(np.linalg.norm(own, axis=-1).max())
    across = g[:, :, :, 1] - g[:, :, :, 0]
    across = across / np.maximum(np.linalg.norm(across, axis=-1, keepdims=True), 1e-9)
    turned = min(float((across[:, :, 1:] * across[:, :, :-1]).sum(-1).min()), float((across[1:] * across[:-1]).sum(-1).min()))
    width = np.linalg.norm(g[:, :, :, 1] - g[:, :, :, 0], axis=-1)
    rows_out = [
        {"name": "the hair moves", "ok": moved * fps >= STILL, "value": f"its tips {moved * fps:.3f} of a strand a second", "limit": f"at least {STILL}",
         "fix": "a --move (toss, sway) or some --wind"},
        {"name": "no strand stretches", "ok": LENGTH[0] <= float(length.min()) and float(length.max()) <= LENGTH[1] and even <= 1.5,
         "value": f"a strand {length.min():.2f} to {length.max():.2f} long, its longest segment {even:.2f} times its shortest",
         "limit": f"{LENGTH[0]} to {LENGTH[1]} of its length, segments within 1.5 of each other", "fix": "bake it again: the strands were pulled"},
        {"name": "the roots stay on one body", "ok": rigid <= 0.01, "value": f"two roots {rigid:.4f} nearer or farther than they started", "limit": "at most 0.01",
         "fix": "bake it again: a root was moved"},
        {"name": "the hair moves on its body", "ok": bend >= LIMP, "value": f"a point of it is {bend:.3f} of a strand off where one stiff piece would have it",
         "limit": f"at least {LIMP:g}: under it the hair rides its body as one stiff piece (or is too heavy to swing)",
         "fix": "less --stiff, less --gravity, more --amount or --wind, or a longer --length"},
        {"name": "no jump", "ok": worst <= POP, "value": f"a tip moved {worst:.3f} in one frame, its root's own move taken out", "limit": f"at most {POP} of a strand",
         "fix": "more --fps, less --amount"},
        {"name": "no ribbon turns over", "ok": turned > 0, "value": f"a ribbon's flat side turns {math.degrees(math.acos(max(-1.0, min(1.0, turned)))):.0f} degrees from one row or frame to the next",
         "limit": "under 90", "fix": "bake it again: a ribbon was turned over (it pinches to nothing between two frames)"},
        {"name": "the strands are ribbons", "ok": float(width[:, :, 0].min()) > 1e-3 and float(width.max()) <= 0.5,
         "value": f"{width[:, :, 0].min():.3f} wide at the thinnest root, {width.max():.3f} at the widest place", "limit": "over 0.001 at every root, at most 0.5 of a strand's length anywhere",
         "fix": "a --width from 0.004 to 0.45 of the --length"},
    ]
    if (a.get("loop") is True) if loop is None else loop:
        seam = float(np.linalg.norm(tip[0] - tip[-1], axis=-1).max())
        limit = max(float(np.percentile(tips.max(1), 75)) * 2.5, 0.01)
        rows_out.append({"name": "the loop's seam", "ok": a.get("loop") is True and seam <= limit,
                         "value": f"a tip moves {seam:.3f} from the last frame to the first" + ("" if a.get("loop") is True else " (baked without --loop)"),
                         "limit": f"at most {limit:.3f} (two and a half times a usual frame's largest move), on a bake made with --loop",
                         "fix": 'bake it with --loop, or take "loop" off the layer'})
    if play is not None and not (0.5 * fps <= play <= 2 * fps):
        rows_out.append({"name": "it is played at its own speed", "ok": False, "value": f"the layer plays {play:g} frames a second, the bake is {fps:g}",
                         "limit": "from half to twice the bake's", "fix": f'"fps": {fps:g} in the params of the layer'})
    return rows_out


def look(frames, strips, rows, path):
    """six frames from the front (x, y) and from above (x, z): each strand's middle line"""
    from PIL import Image, ImageDraw

    cell, pad = 190, 10
    picks = [round(k * (len(frames) - 1) / 5) for k in range(6)]
    allp = np.asarray(frames).reshape(len(frames), strips, rows + 1, 2, 3).mean(3)
    span = float(np.abs(allp).max()) * 2.2
    img = Image.new("RGB", (pad + 6 * (cell + pad), 34 + 2 * (cell + pad)), (16, 18, 24))
    pen = ImageDraw.Draw(img)
    for col, f in enumerate(picks):
        pen.text((pad + col * (cell + pad) + 4, 6), f"frame {f + 1}", fill=(200, 204, 214))
        for row, (ib, name, flip) in enumerate(((1, "front", -1), (2, "above", 1))):
            ox, oy = pad + col * (cell + pad), 26 + row * (cell + pad)
            pen.rectangle([ox, oy, ox + cell, oy + cell], outline=(70, 74, 86))
            if col == 0:
                pen.text((ox + 4, oy + cell - 14), name, fill=(120, 126, 140))
            for s in range(strips):
                line = [(ox + cell / 2 + p[0] / span * cell, oy + cell / 2 + flip * p[ib] / span * cell) for p in allp[f, s]]
                pen.line(line, fill=(230, 196, 120))
                pen.ellipse([line[0][0] - 2, line[0][1] - 2, line[0][0] + 2, line[0][1] + 2], fill=(150, 170, 230))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path)


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


def arguments(o):
    def num(key, lo, hi, whole=False):
        try:
            v = float(o[key])
        except ValueError:
            v = float("nan")
        if not (math.isfinite(v) and lo <= v <= hi) or (whole and v != int(v)):
            raise ValueError(f"{key} is {'a whole number' if whole else 'a number'} from {lo:g} to {hi:g}")
        return int(v) if whole else v

    try:
        wind = [float(x) for x in o["--wind"].split(",")]
    except ValueError:
        wind = []
    if len(wind) != 3 or not all(math.isfinite(x) for x in wind) or math.sqrt(sum(x * x for x in wind)) > 120:
        raise ValueError("--wind x,y,z is 3 numbers with commas between them, 120 studs a second at most")
    a = {"root": o["--root"], "move": o["--move"], "loop": o["--loop"] is True, "wind": wind, "strands": num("--strands", 2, 64, True),
         "length": num("--length", 0.2, 100), "width": num("--width", 0.01, 20), "head": num("--head", 0.2, 100), "amount": num("--amount", 0, 20),
         "gust": num("--gust", 0, 1), "stiff": num("--stiff", 0, 0.9), "gravity": num("--gravity", 0, 400), "frames": num("--frames", 2, 64, True),
         "fps": num("--fps", 8, 60, True), "segments": num("--segments", 3, 16, True), "drag": num("--drag", 0, 20), "damp": num("--damp", 0, 20)}
    if a["root"] not in ROOTS:
        raise ValueError(f"--root is one of {', '.join(ROOTS)}")
    if a["move"] not in MOVES:
        raise ValueError(f"--move is one of {', '.join(MOVES)}")
    if not 0.004 * a["length"] <= a["width"] <= 0.45 * a["length"]:
        raise ValueError("--width is from 0.004 to 0.45 of the --length (a strand is a ribbon: not a thread too thin to draw, not a sheet)")
    if a["move"] == "toss" and a["amount"] > math.pi:
        raise ValueError("--amount for a toss is radians each way, 3.14 at most")
    if a["loop"] and a["frames"] / a["fps"] < 1:
        raise ValueError("--loop needs a sequence of at least a second (--frames / --fps): the move and the wind must fit into it")
    return a


def main(argv):
    usage = "lune run kit vfx hair <name> [--root cap|line] [--strands 16] [--length 3] [--move toss|sway|none] [--amount 0.8] [--wind x,y,z] [--loop]"
    o = {"--root": "cap", "--strands": "16", "--length": "3", "--width": "0.25", "--head": "1.2", "--move": "toss", "--amount": "0.8", "--wind": "0,0,0",
         "--gust": "0.5", "--stiff": "0.15", "--gravity": "40", "--frames": "48", "--fps": "24", "--segments": "8", "--drag": "1.5", "--damp": "1.0",
         "--out-dir": OUT, "--look-dir": LOOK, "--loop": False}
    names, i = [], 0
    while i < len(argv):
        if argv[i] == "--loop":
            o["--loop"] = True
            i += 1
        elif argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"hair: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"hair: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", names[0]):
        return out("fail", "hair: name ONE sequence, in lowercase letters, digits and _ (the game finds it by its exact letters)", usage)
    name = names[0]
    try:
        a = arguments(o)
    except ValueError as e:
        return out("fail", f"hair {name}: {e}", usage)
    mids, where = simulate(a)
    if not all(np.isfinite(m).all() for m in mids):
        return out("fail", f"hair {name}: the strands flew apart (numbers that are not numbers)", "less --wind, less --amount, or more --fps")
    unit = a["length"]
    data = {"about": f"a hair bake (kit/vfx/hair.py): {a['strands']} strands {a['length']:g} studs long rooted on a {a['root']}, move {a['move']}, "
                     f"baked at {a['fps']} frames a second, unit size (a strand is 1 long), one strip a strand",
            "recipe": "hair", "args": a, "cols": 1, "rows": a["segments"], "strips": a["strands"],
            "frames": [[round(float(x) / unit, 4) for x in ribbons(m, a, w).reshape(-1)] for m, w in zip(mids, where)]}
    rows = check(data)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return out("fail", f"hair {name}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    text = json.dumps(data, separators=(",", ":"))
    kb = len(text.encode("utf-8")) / 1024
    path = os.path.join(o["--out-dir"], f"{name}.json")
    if kb > 600:  # (measured BEFORE anything is written: a refused bake leaves an earlier good one of its name alone)
        return out("fail", f"hair {name}: {kb:.0f} KB of frames (the data rides into the game: 600 at most)", "fewer --frames, --strands or --segments")
    os.makedirs(o["--out-dir"], exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    picture = os.path.join(o["--look-dir"], f"{name}.png")
    look(data["frames"], a["strands"], a["segments"], picture)
    loop = ', "loop": true' if a["loop"] else ""
    return out("pass", f"hair {name}: {a['frames']} frames of {a['strands']} strands, {kb:.0f} KB - on a mesh layer: "
               f'"shape": "seq", "pivot": "origin", "params": {{"seq": "{name}", "fps": {a["fps"]}{loop}}}, its scale a strand\'s length ({unit:g} studs)',
               f"OPEN {picture.replace(os.sep, '/')}: does the hair swing and settle as THIS effect's does?", checks=rows, look=picture.replace(os.sep, "/"),
               seq=path.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
