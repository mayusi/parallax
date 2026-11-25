#!/usr/bin/env python3
"""water.py - WATER AS A HEIGHT FIELD, SIMULATED AND BAKED (the owner's methods list: Wave simulation, Shallow-water
simulation; the VFX methods audit, stage 24). The water is the HEIGHT of its surface over a flat bed, in a square
tank with four walls. Two solvers, both from first principles, both baked frame by frame into a mesh sequence the
`seq` mesh shape replays:

    lune run kit vfx water <name> --recipe drop  [--at x,z] [--width 0.08] [--amount 0.3] [--damp 0.6]
    lune run kit vfx water <name> --recipe rain  [--drops 6] [--seed 1] [--width 0.06] [--amount 0.2] [--damp 0.6]
    lune run kit vfx water <name> --recipe slosh [--mode 1] [--amount 0.3] [--loop]
    lune run kit vfx water <name> --recipe dam   [--at x] [--amount 1.0]
    lune run kit vfx water <name> --recipe surge [--at x,z] [--width 0.12] [--amount 1.5]
                                  [--speed 0.6] [--depth 0.1] [--frames 40] [--fps 24] [--cols 20] [--rows 20]

WAVES (drop, rain, slosh): the wave equation on the height, d2h/dt2 = c2 x laplacian(h) - damp x dh/dt. Small waves
on shallow water: every wave runs at ONE speed c (--speed, in tank widths a second), two waves pass through each
other and add, a wall sends a wave back. `drop`: one drop's crater and rim let go at --at; `rain`: --drops of them at
seeded places and moments; `slosh`: the whole tank rocking in its --mode'th standing wave (with --loop the speed is
moved to the nearest one whose rocking comes round a whole number of times in the sequence; the sequence must be
about a whole rocking long - 2 / (mode x speed) seconds: `--speed 0.75 --frames 64` at 24 frames a second does, the
plain defaults do not and are refused saying so).

SHALLOW WATER (dam, surge): the shallow-water equations (water depth h and its flow h x u, h x v: mass and momentum
kept, gravity g = c2 / depth), solved by a finite-volume scheme (Rusanov fluxes). Here a HIGH wave runs faster than
a low one and its front steepens into a BORE - a wall of water - that the wave equation cannot make. `dam`: the
water --amount x depth deeper on one side of a wall at --at that is gone at the first frame; `surge`: a mound of
water let go.

--depth is the water's depth at rest and --amount a height, both as parts: depth of the tank's width, amount of the
depth. The bake is unit size (the tank is 1 wide), y up, y = 0 the water at rest, the bed at y = -depth.

NEVER MATCHED TO A REAL SCENE: no clip of water was read for this (a download waits on the owner). What the tests
hold is the mathematics - the wave speed, a standing wave's period, two waves adding, the dam-break's bore against
Stoker's exact solution, water neither made nor lost - not that it LOOKS like any water he has in mind.
NOT here: breaking waves (a height has one value a place: nothing curls or falls), spray, foam, splashes, water
running over a sloping or dry bed, anything floating, flow round a thing. The surface is a mesh; what it is drawn
with (colour, shine, see-through) is the layer's own look.

Writes assets/effects/seq/<name>.json and a picture of six of its frames. `check(data)` is the list of checks of a
FILE (the method gate asks it): it SOLVES the file's own asks again and holds the frames to that.
"""
import json
import math
import os
import re
import sys

import numpy as np

OUT = os.path.join("assets", "effects", "seq")
LOOK = os.path.join("build", "vfx", "water")
WAVES = ("drop", "rain", "slosh")   # the wave equation
RAIN_SPAN = 1.15   # seconds the rain's drops are drawn over (0.7 of the default run: 40 frames at 24 a second)
SHALLOW = ("dam", "surge")          # the shallow-water equations
RECIPES = WAVES + SHALLOW
N = 64          # cells across the tank the water is solved on
CFL = 0.4       # of a cell a step, at most, for the fastest wave
STILL = 0.004   # x 10: the least the surface moves a SECOND, on average, as a part of the water's depth
MASS = 0.02     # water made or lost, as a part of (the highest wave x the tank)
SAME = 0.01     # how far a file's frames may lie from what its own asks solve to, as a part of the highest wave (+ the file's rounding)
SEEN = 0.003    # of the tank's width: the least a bake's highest wave (at a scale of 24 studs, under a tenth of a stud is not seen)
STEP = 2.0      # mesh points: the most a bore may run in one frame (the game blends frames: a wall that jumps further fades in place)
QUICK = 1.3     # a place's rise and fall: |second difference| / |first difference| over time, at most (2 = it flickers)


def lap(e, dx):
    """the laplacian of a field on the tank's cells, walls all round (nine points: a ring stays round)"""
    p = np.pad(e, 1, mode="edge")
    return (4 * (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) + p[:-2, :-2] + p[:-2, 2:] + p[2:, :-2] + p[2:, 2:] - 20 * e) / (6 * dx * dx)


def centres(n):
    return (np.arange(n) + 0.5) / n - 0.5


def stamp(n, x, z, width):
    """one drop's mark on the water: a crater with a rim, of height 1 at its middle, that holds no water in all. The
    shape holds none on an open sea; the walls cut a wide one, and what that leaves over is taken off NEAR the drop
    (it was taken off the whole tank: a wide drop lowered the far water too - a review leftover)"""
    c = centres(n)
    r2 = ((c[None, :] - x) ** 2 + (c[:, None] - z) ** 2) / (width * width)
    s = (1 - r2 / 2) * np.exp(-r2 / 2)
    near = np.exp(-r2 / 8)   # (a soft ring twice the drop's width)
    return s - near * (s.sum() / near.sum())


def rate_of(speed, n):
    """steps a second the waves are solved at: from the wave's speed alone (never from the frames a second)"""
    return max(240, int(math.ceil(speed * n / CFL)))


def slosh_speed(a, n):
    """the speed at which the --mode'th standing wave comes round a whole number of times in the sequence, nearest
    the one asked -> (speed, times round); the solver's own period, not the textbook's (they differ in the fourth digit)"""
    rate = rate_of(a["speed"], n)
    dt, dx = 1.0 / rate, 1.0 / n
    lam = 2 * (1 - math.cos(math.pi * a["mode"] / n)) / (dx * dx)

    def period(c):
        return 2 * math.pi * dt / math.acos(1 - dt * dt * c * c * lam / 2)

    run = a["frames"] / a["fps"]
    times = max(1, int(round(run / period(a["speed"]))))
    theta = 2 * math.pi * times * dt / run
    return math.sqrt(2 * (1 - math.cos(theta)) / (dt * dt * lam)), times


def waves(a, n=N):
    """the wave equation -> the surface at every frame's moment (frame f at f / fps): [n x n heights, in tank widths]"""
    c, depth, amp = a["speed"], a["depth"], a["amount"] * a["depth"]
    rate = rate_of(a["rate_speed"] if "rate_speed" in a else c, n)
    dt, dx = 1.0 / rate, 1.0 / n
    damp = 0.0 if a["recipe"] == "slosh" else a["damp"]
    e = np.zeros((n, n))
    v = np.zeros((n, n))
    falls = []
    if a["recipe"] == "drop":
        e += amp * stamp(n, a["at"][0], a["at"][1], a["width"])
    elif a["recipe"] == "slosh":
        e += amp * np.cos(math.pi * a["mode"] * (centres(n) + 0.5))[None, :] * np.ones((n, 1))
    else:
        rng = np.random.default_rng(int(a["seed"]))
        run = (a["frames"] - 1) / a["fps"]
        # the moments are drawn over a span of the CLOCK (RAIN_SPAN seconds), not of the run: a longer or a shorter run
        # (--frames, --fps) keeps the same rain - it was drawn over 0.7 of the run, so other --frames made other rain.
        # A drop that falls after the run is not in it
        for k in range(int(a["drops"])):
            when = 0.0 if k == 0 else float(rng.uniform(0, RAIN_SPAN))
            x, z = float(rng.uniform(-0.38, 0.38)), float(rng.uniform(-0.38, 0.38))
            if when <= run:
                falls.append((when, x, z))
        falls.sort()
    out, step = [], 0
    prev = e.copy()
    for f in range(a["frames"]):
        t = f / a["fps"]
        while step * dt < t - 1e-12:
            while falls and falls[0][0] <= step * dt + 1e-12:
                _, x, z = falls.pop(0)
                e += amp * stamp(n, x, z, a["width"])
            prev = e.copy()
            v += dt * (c * c * lap(e, dx) - damp * v)
            e = e + dt * v
            step += 1
        while falls and falls[0][0] <= t + 1e-12 and step * dt <= t + 1e-12:   # (a drop that falls on a frame's own moment is in that frame)
            _, x, z = falls.pop(0)
            e += amp * stamp(n, x, z, a["width"])
            prev = e.copy()
        back = (step * dt - t) / dt if step else 0.0
        out.append(e * (1 - back) + prev * back)
    return out


def shallow_step(h, hu, hv, g, dx, dt):
    """one finite-volume step of the shallow-water equations (Rusanov fluxes; walls all round: no water crosses one)"""
    def flux(hl, ql, tl, hr, qr, tr):
        """across a face: q is the flow through it, t the flow along it -> (water, q, t) crossing a second, a width"""
        ul, ur = ql / hl, qr / hr
        a = np.maximum(np.abs(ul) + np.sqrt(g * hl), np.abs(ur) + np.sqrt(g * hr))
        return (0.5 * (ql + qr) - 0.5 * a * (hr - hl),
                0.5 * (ql * ul + 0.5 * g * hl * hl + qr * ur + 0.5 * g * hr * hr) - 0.5 * a * (qr - ql),
                0.5 * (tl * ul + tr * ur) - 0.5 * a * (tr - tl))

    def wall(f, sign, axis):
        p = np.pad(f, 1, mode="edge")
        p = p[1:-1, :] if axis == 1 else p[:, 1:-1]
        if sign < 0:
            if axis == 1:
                p[:, 0], p[:, -1] = -p[:, 0], -p[:, -1]
            else:
                p[0, :], p[-1, :] = -p[0, :], -p[-1, :]
        return p

    H, Q, T = wall(h, 1, 1), wall(hu, -1, 1), wall(hv, 1, 1)                      # across x: the flow through a face is hu
    fh, fq, ft = flux(H[:, :-1], Q[:, :-1], T[:, :-1], H[:, 1:], Q[:, 1:], T[:, 1:])
    H, Q, T = wall(h, 1, 0), wall(hv, -1, 0), wall(hu, 1, 0)                      # across z: it is hv
    gh, gq, gt = flux(H[:-1, :], Q[:-1, :], T[:-1, :], H[1:, :], Q[1:, :], T[1:, :])
    k = dt / dx
    h2 = h - k * (fh[:, 1:] - fh[:, :-1]) - k * (gh[1:, :] - gh[:-1, :])
    hu2 = hu - k * (fq[:, 1:] - fq[:, :-1]) - k * (gt[1:, :] - gt[:-1, :])
    hv2 = hv - k * (ft[:, 1:] - ft[:, :-1]) - k * (gq[1:, :] - gq[:-1, :])
    return np.maximum(h2, 1e-9), hu2, hv2


def shallow(a, n=N):
    """the shallow-water equations -> the surface at every frame's moment, as the height over the water at rest"""
    depth = a["depth"]
    g = a["speed"] ** 2 / depth
    dx = 1.0 / n
    c = centres(n)
    if a["recipe"] == "dam":
        h = np.where(c[None, :] < a["at"][0], depth * (1 + a["amount"]), depth) * np.ones((n, 1))
    else:
        r2 = ((c[None, :] - a["at"][0]) ** 2 + (c[:, None] - a["at"][1]) ** 2) / (a["width"] ** 2)
        h = depth * (1 + a["amount"] * np.exp(-r2 / 2))
    hu, hv = np.zeros((n, n)), np.zeros((n, n))
    out, now = [], 0.0
    for f in range(a["frames"]):
        t = f / a["fps"]
        while now < t - 1e-12:
            fast = float(np.max(np.maximum(np.abs(hu), np.abs(hv)) / h + np.sqrt(g * h)))
            dt = min(CFL * dx / max(fast, 1e-9), t - now)
            h, hu, hv = shallow_step(h, hu, hv, g, dx, dt)
            now += dt
        out.append(h - depth)
    return out


def stoker(deep, low, g):
    """a dam's exact break on a wet bed (Stoker 1957): water `deep` on one side, `low` on the other, both still ->
    (the height of the shelf that runs out behind the bore, its flow speed, the bore's speed)"""
    lo, hi = low, deep
    for _ in range(200):
        hm = 0.5 * (lo + hi)
        um = (hm - low) * math.sqrt(0.5 * g * (hm + low) / (hm * low))
        if um + 2 * math.sqrt(g * hm) > 2 * math.sqrt(g * deep):
            hi = hm
        else:
            lo = hm
    return hm, um, hm * um / (hm - low)


def simulate(a, n=N):
    return waves(a, n) if a["recipe"] in WAVES else shallow(a, n)


def to_points(e, cols, rows):
    """the solved surface -> the mesh's points (x across, y up, z along; rows of columns), the tank 1 wide"""
    n = e.shape[0]
    c = centres(n)
    x = np.arange(cols + 1) / cols - 0.5
    z = np.arange(rows + 1) / rows - 0.5
    along = np.stack([np.interp(x, c, row) for row in e])                 # n x (cols + 1)
    y = np.stack([np.interp(z, c, along[:, k]) for k in range(cols + 1)], axis=1)   # (rows + 1) x (cols + 1)
    xx, zz = np.meshgrid(x, z)
    return np.stack([xx, y, zz], -1)


def volume(y):
    """the water over the rest level in a grid of point heights (the tank is 1 x 1), each point weighing its share"""
    w = np.ones(y.shape[-2:])
    w[0, :] *= 0.5
    w[-1, :] *= 0.5
    w[:, 0] *= 0.5
    w[:, -1] *= 0.5
    return (y * w).sum((-2, -1)) / w.sum()


def check(data, loop=None, play=None):
    """the checks of a water FILE, from its own frames: [{name, ok, value, limit, fix}]"""
    a = data.get("args") if isinstance(data.get("args"), dict) else {}
    cols, rows, frames = data.get("cols"), data.get("rows"), data.get("frames")
    whole = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
    sound = data.get("recipe") == "water" and whole(cols) and whole(rows) and isinstance(frames, list) and len(frames) >= 2 and "strips" not in data
    if sound:
        try:   # the asks the file says it was baked with, worked out again: they are its numbers
            asks = data.get("asks")
            sound = (isinstance(asks, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in asks.items()) and set(asks) <= set(DEFAULTS)
                     and arguments(asks) == a and a["cols"] == cols and a["rows"] == rows and a["frames"] == len(frames))
        except (ValueError, KeyError, TypeError):
            sound = False
    if sound:
        try:
            arr = np.array(frames, dtype=float)
            sound = arr.shape == (len(frames), (cols + 1) * (rows + 1) * 3) and bool(np.isfinite(arr).all())
        except (ValueError, TypeError):
            sound = False
    if sound:
        g = arr.reshape(len(frames), rows + 1, cols + 1, 3)
        flat = to_points(np.zeros((N, N)), cols, rows)
        sound = bool(np.abs(g[..., 0] - flat[..., 0]).max() <= 2e-4 and np.abs(g[..., 2] - flat[..., 2]).max() <= 2e-4)
    if not sound:
        return [{"name": "a water bake", "ok": False, "value": "not one", "limit": "recipe water, the asks it was baked with, a height over each place of its tank, every frame whole",
                 "fix": "bake it again: lune run kit vfx water <name> --recipe ..."}]
    y = g[..., 1]
    fps, depth = a["fps"], a["depth"]
    if not all(type(v) in (int, float) for f in frames for v in f):   # (a number written as text is not a number to the game)
        return [{"name": "a water bake", "ok": False, "value": "a height that is not a number", "limit": "every height a number", "fix": "bake it again: lune run kit vfx water <name>"}]
    cells = simulate(a)
    solved = np.stack([to_points(e, cols, rows)[..., 1] for e in cells])
    high = max(float(np.abs(solved).max()), 1e-9)
    off = float(np.abs(y - solved).max())
    same = SAME * high + 1e-4
    moved = float(np.abs(y[1:] - y[:-1]).mean()) * fps / depth
    lost = max(abs(float(e.mean() - cells[0].mean())) for e in cells) / high   # (on the solver's own cells: a coarse mesh cannot weigh a sharp step)
    d1 = np.abs(y[1:] - y[:-1])
    d2 = np.abs(y[2:] - 2 * y[1:-1] + y[:-2]) if len(frames) > 2 else np.zeros((1,) + y.shape[1:])
    quick = float(d2.mean() / max(float(d1.mean()), 1e-12))
    low = float(y.min())
    out = [
        {"name": "the frames are what its asks solve to", "ok": off <= same, "value": f"{off:.5f} of the tank's width off, at the worst place",
         "limit": f"at most {same:.5f} (a hundredth of its highest wave: the file's own recipe and numbers, solved again)",
         "fix": "bake it again: the frames were changed by hand, or are another bake's"},
        {"name": "the waves are high enough to see", "ok": high >= SEEN, "value": f"the highest is {high:.4f} of the tank's width", "limit": f"at least {SEEN}",
         "fix": "more --amount or more --depth"},
        {"name": "the water moves", "ok": moved >= STILL * 10, "value": f"{moved:.3f} of its depth a second, on average", "limit": f"at least {STILL * 10:g}",
         "fix": "more --amount, more --speed, less --damp, or fewer --frames (it has died down for most of them)"},
        {"name": "no water is made or lost", "ok": lost <= 1e-6, "value": f"{lost:.2e} of (its highest wave x the tank), on the solver's cells", "limit": "at most 1e-6",
         "fix": "a fault in the solver (kit/vfx/water.py)"},
        {"name": "the water stays over its bed", "ok": low > -depth * 0.98, "value": f"its lowest place is {-low / depth:.2f} of the depth under the rest level",
         "limit": "under 0.98 of it (the bed is not laid bare)", "fix": "less --amount"},
        {"name": "a place rises and falls over several frames", "ok": quick <= QUICK, "value": f"{quick:.2f} (2 = every place flips each frame)", "limit": f"at most {QUICK}",
         "fix": "less --speed, more --fps, a wider --width or a lower --mode: the waves pass a place faster than the frames can show"},
    ]
    if loop:
        if a["recipe"] == "slosh" and a.get("loop") is True:
            steps = np.abs(y[1:] - y[:-1]).max((1, 2))
            seam = float(np.abs(y[0] - y[-1]).max())
            out.append({"name": "the loop's seam", "ok": seam <= 1.5 * float(steps.max()), "value": f"{seam:.4f} from the last frame to the first, its largest step is {steps.max():.4f}",
                        "limit": "no more than one and a half of its largest step", "fix": "bake it again with --loop"})
        else:
            out.append({"name": "the loop's seam", "ok": False, "value": "the layer loops a bake that does not come round", "limit": "a slosh baked with --loop",
                        "fix": 'take "loop" off the layer, or bake a slosh with --loop'})
    if play is not None and not (0.5 * fps <= play <= 2 * fps):
        out.append({"name": "it is played at its own speed", "ok": False, "value": f"the layer plays {play:g} frames a second, the bake is {fps:g}",
                    "limit": "from half to twice the bake's", "fix": f'"fps": {fps:g} in the params of the layer'})
    return out


def look(heights, depth, path):
    """six frames: the water cut through its middle (its bed drawn under it, heights three times as tall) and from above"""
    from PIL import Image, ImageDraw

    cell, pad = 190, 10
    picks = [round(k * (len(heights) - 1) / 5) for k in range(6)]
    top = max(max(float(np.abs(h).max()) for h in heights), 1e-6)
    img = Image.new("RGB", (pad + 6 * (cell + pad), 34 + 2 * (cell + pad)), (16, 18, 24))
    pen = ImageDraw.Draw(img)
    for col, f in enumerate(picks):
        h = np.asarray(heights[f])
        ox = pad + col * (cell + pad)
        pen.text((ox + 4, 6), f"frame {f + 1}", fill=(200, 204, 214))
        oy = 26
        pen.rectangle([ox, oy, ox + cell, oy + cell], outline=(70, 74, 86))
        mid = h[h.shape[0] // 2]
        zero = oy + cell * 0.55
        tall = 3.0 * cell * 0.9
        bed = zero + depth * tall
        pen.line([ox, bed, ox + cell, bed], fill=(110, 116, 130))
        pen.line([ox, zero, ox + cell, zero], fill=(50, 56, 70))
        pen.line([(ox + cell * 0.05 + i / (len(mid) - 1) * cell * 0.9, zero - mid[i] * tall) for i in range(len(mid))], fill=(120, 190, 240), width=2)
        oy = 26 + cell + pad
        img.paste(Image.fromarray((np.clip(0.5 + 0.5 * h / top, 0, 1) * 235 + 20).astype(np.uint8)).resize((cell, cell)), (ox, oy))
        pen.rectangle([ox, oy, ox + cell, oy + cell], outline=(70, 74, 86))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path)


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


DEFAULTS = {"--recipe": "drop", "--speed": "0.6", "--depth": "0.1", "--amount": "", "--width": "", "--at": "", "--drops": "6", "--seed": "1", "--damp": "0.6",
            "--mode": "1", "--frames": "40", "--fps": "24", "--cols": "20", "--rows": "20", "--loop": ""}
AMOUNT = {"drop": 0.3, "rain": 0.2, "slosh": 0.3, "dam": 1.0, "surge": 1.5}
WIDTH = {"drop": 0.08, "rain": 0.06, "surge": 0.12}


def arguments(given):
    """the asks, checked -> the numbers a bake is made from (and its file says); ValueError in words when one cannot work"""
    o = dict(DEFAULTS, **given)

    def num(key, lo, hi, whole=False):
        try:
            v = float(o[key])
        except (ValueError, TypeError):
            v = float("nan")
        if not (math.isfinite(v) and lo <= v <= hi) or (whole and v != int(v)):
            raise ValueError(f"{key} is {'a whole number' if whole else 'a number'} from {lo:g} to {hi:g}")
        return int(v) if whole else v

    recipe = o["--recipe"]
    if recipe not in RECIPES:
        raise ValueError(f"--recipe is one of {', '.join(RECIPES)}")
    a = {"recipe": recipe, "speed": num("--speed", 0.1, 4), "depth": num("--depth", 0.02, 0.5), "frames": num("--frames", 2, 64, True), "fps": num("--fps", 8, 60, True),
         "cols": num("--cols", 8, 24, True), "rows": num("--rows", 8, 24, True), "loop": o["--loop"] in ("1", True)}
    o["--amount"] = o["--amount"] if o["--amount"] not in ("", None) else str(AMOUNT[recipe])
    a["amount"] = num("--amount", 0.02, 0.9) if recipe in WAVES else num("--amount", 0.05, 4)
    least = min(a["cols"], a["rows"])
    if recipe in WIDTH:
        o["--width"] = o["--width"] if o["--width"] not in ("", None) else str(WIDTH[recipe])
        a["width"] = num("--width", 0.03, 0.3)
        if a["width"] < 1.0 / least:
            raise ValueError(f"--width {a['width']:g} is under one cell of the mesh ({1.0 / least:.3f}): its waves would fall between the points (a wider --width, more --cols / --rows)")
        if a["speed"] / a["fps"] > 0.9 * a["width"]:
            raise ValueError(f"--speed {a['speed']:g} at {a['fps']} frames a second moves a wave {a['speed'] / a['fps']:.3f} of the tank a frame, over 0.9 of its --width "
                             f"{a['width']:g}: a place would flip from frame to frame (less --speed, more --fps, a wider --width)")
    if recipe in ("drop", "surge", "dam"):
        text = o["--at"] if o["--at"] not in ("", None) else "0,0"
        try:
            at = [float(x) for x in str(text).split(",")]
        except ValueError:
            at = []
        if recipe == "dam" and len(at) == 1:
            at = [at[0], 0.0]
        if len(at) != 2 or not all(math.isfinite(x) and -0.4 <= x <= 0.4 for x in at):
            raise ValueError("--at is x,z in the tank, each from -0.4 to 0.4 (its middle is 0,0; a dam takes its x)")
        a["at"] = at
    if recipe in SHALLOW:   # a bore runs FASTER than the speed said (that is small waves'): held to the mesh it is shown on
        g = a["speed"] ** 2 / a["depth"]
        bore = stoker(a["depth"] * (1 + a["amount"]), a["depth"], g)[2] if recipe == "dam" else a["speed"] * math.sqrt(1 + a["amount"])
        if bore / a["fps"] > STEP / least:
            raise ValueError(f"the bore runs {bore:.2f} tank widths a second: {bore / a['fps'] * least:.1f} points of the mesh a frame, over {STEP:g} "
                             f"(the wall of water would fade from place to place, not travel: less --speed or --amount, more --fps)")
    if recipe == "rain":
        a["drops"], a["seed"] = num("--drops", 2, 24, True), num("--seed", 0, 99999, True)
    if recipe in ("drop", "rain"):
        a["damp"] = num("--damp", 0, 5)
    if recipe == "slosh":
        a["mode"] = num("--mode", 1, 4, True)
        if a["mode"] > least / 6:
            raise ValueError(f"--mode {a['mode']} is under 12 points a wave on {least} cells: a lower --mode or more --cols / --rows")
        if a["loop"]:
            a["rate_speed"] = a["speed"]
            sp, times = slosh_speed(a, N)
            if abs(sp - a["speed"]) > 0.25 * a["speed"]:
                raise ValueError(f"--loop: the nearest speed whose rocking comes round in {a['frames']} frames is {sp:.3g}, far from the {a['speed']:g} asked "
                                 f"(more --frames, or a --speed near {sp:.3g})")
            a["speed"], a["times"] = round(sp, 9), times
        period = 2.0 / (a["mode"] * a["speed"]) * a["fps"]
        if period < 8:
            raise ValueError(f"the rocking comes round every {period:.1f} frames, under 8: less --speed, more --fps or a lower --mode")
    elif a["loop"]:
        raise ValueError("--loop is for a slosh (a drop, rain, a dam and a surge do not come round)")
    return a


def main(argv):
    usage = ("lune run kit vfx water <name> --recipe drop|rain|slosh|dam|surge [--speed 0.6] [--depth 0.1] [--amount a] [--width w] [--at x,z] [--frames 40] [--fps 24] "
             "(a slosh's --loop needs a sequence a whole rocking long: --speed 0.75 --frames 64 at 24 frames a second)")
    o = dict(DEFAULTS, **{"--out-dir": OUT, "--look-dir": LOOK})
    names, i = [], 0
    while i < len(argv):
        if argv[i] == "--loop":
            o["--loop"] = "1"
            i += 1
        elif argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"water: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"water: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", names[0]):
        return out("fail", "water: name ONE sequence, in lowercase letters, digits and _ (the game finds it by its exact letters)", usage)
    name = names[0]
    try:
        a = arguments({k: v for k, v in o.items() if k in DEFAULTS})
    except ValueError as e:
        return out("fail", f"water {name}: {e}", usage)
    heights = simulate(a)
    kind = "the wave equation" if a["recipe"] in WAVES else "the shallow-water equations"
    data = {"about": f"a water bake (kit/vfx/water.py): {a['recipe']}, {kind}, small waves at {a['speed']:g} tank widths a second on water {a['depth']:g} of the tank deep, "
                     f"baked at {a['fps']} frames a second, unit size (the tank is 1 wide), y = 0 the water at rest. Never matched to a real scene",
            "recipe": "water", "asks": {k: v for k, v in o.items() if k in DEFAULTS}, "args": a, "cols": a["cols"], "rows": a["rows"],
            "frames": [[round(float(x), 4) for x in to_points(e, a["cols"], a["rows"]).reshape(-1)] for e in heights]}
    rows = check(data, loop=a["loop"] or None)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return out("fail", f"water {name}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    text = json.dumps(data, separators=(",", ":"))
    kb = len(text.encode("utf-8")) / 1024
    path = os.path.join(o["--out-dir"], f"{name}.json")
    if kb > 600:  # (measured BEFORE anything is written: a refused bake leaves an earlier good one of its name alone)
        return out("fail", f"water {name}: {kb:.0f} KB of frames (the data rides into the game: 600 at most)", "fewer --frames, --cols or --rows")
    os.makedirs(o["--out-dir"], exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    picture = os.path.join(o["--look-dir"], f"{name}.png")
    look(heights, a["depth"], picture)
    least = min(a["cols"], a["rows"])
    coarse = (f" - COARSE: a drop {a['width'] * least:.1f} points of the mesh wide draws its rings with about four points each "
              f"(a --width of {2.0 / least:.2f} or more, or more --cols / --rows)") if "width" in a and a["width"] * least < 2 else ""
    loop = ', "loop": true' if a["loop"] else ""
    return out("pass", f"water {name}: {a['frames']} frames of a {a['cols']} x {a['rows']} surface ({kind}), {kb:.0f} KB{coarse} - on a mesh layer: "
               f'"shape": "seq", "pivot": "origin", "params": {{"seq": "{name}", "fps": {a["fps"]}{loop}}}, its scale the tank\'s width in studs (with that pivot y = 0, the water at rest, is on the layer\'s point)',
               f"OPEN {picture.replace(os.sep, '/')}: do the waves run as THIS effect's water does? (never matched to a real scene)", checks=rows,
               look=picture.replace(os.sep, "/"), seq=path.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
