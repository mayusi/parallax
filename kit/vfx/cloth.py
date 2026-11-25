"""cloth.py - CLOTH, SIMULATED AND BAKED (the VFX methods audit, stage 15): a sheet held along an edge, pulled by
gravity and pushed by a gusting wind, baked frame by frame into a mesh sequence the `seq` mesh shape replays (the
game's VfxMesh and the browser player: nothing new runs in either).

    lune run kit vfx cloth <name> [--size 6,4] [--pin top|left|corners] [--wind 0,0,14] [--gust 0.5]
                                  [--gravity 30] [--start hang|flat] [--loop] [--frames 48] [--fps 24]
                                  [--cols 16] [--rows 10] [--seed 1]

  --size w,h     the sheet in studs (it is baked at unit size: its longest side is 1; the layer's scale sizes it)
  --pin          top = the whole top edge held (a banner, a cape's collar) | left = the left edge held (a flag on
                 its pole) | corners = the two top corners held (a sheet on a line)
  --wind x,y,z   studs a second; --gust 0..1 is how much it swells and drops (0 = a steady wind)
  --start        hang = already blowing when the sequence starts | flat = let go flat and still on frame 1 (it unfurls)
  --loop         the wind comes round once a sequence (every gust fits a whole number of times into it) and the sheet
                 is blown six times round before the frames are kept; what is left of a jump (the sheet's own
                 slow swing) is taken out over the last quarter, leaning on the frames one round earlier

The sheet is points that keep their distances (kit/vfx/pbd.py); the wind pushes each point along the sheet's own
normal there, by how fast the air meets it. It does NOT collide with itself, with a character or with the ground.

Writes assets/effects/seq/<name>.json (the mesh sequence format: unit size, cols x rows, frames) and a picture of
six of its frames to look at. A bake is refused when the sheet hangs still, stretches, jumps between frames or its
held edge moves, or its links are not the sheet's. `check(data)` is that list of checks from a FILE's own frames (the method gate asks it).
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
LOOK = os.path.join("build", "vfx", "cloth")
PINS = ("top", "left", "corners")
STRETCH = 1.12  # a link no longer than this many times its rest length, in any frame
STILL = 0.05    # the least a point moves a SECOND, on average, in sheet lengths: under it the sheet hangs still
SHRINK = (0.9, 0.7)  # a frame's links: their mean length, and the shortest, against their rest length
POP = 0.2       # the most any point moves in one frame, in sheet lengths
RATE, ITERS = 192, 12  # the sheet is stepped at least RATE times a second, whatever the bake's fps


def held(cols, rows, pin):
    """which points are held: [(i, j)]"""
    if pin == "top":
        return [(i, 0) for i in range(cols + 1)]
    if pin == "left":
        return [(0, j) for j in range(rows + 1)]
    return [(0, 0), (cols, 0)]


def rest_grid(cols, rows, w, h):
    """the sheet flat, hanging from its top row: x across, y down from 0, z 0 (point j * (cols + 1) + i)"""
    i, j = np.meshgrid(np.arange(cols + 1), np.arange(rows + 1))
    return np.stack([(i / cols - 0.5) * w, -(j / rows) * h, np.zeros_like(i, dtype=float)], -1).reshape(-1, 3).astype(float)


def links(cols, rows, w, h):
    """the sheet's links: along and down it (it does not stretch), across each cell (it does not shear), and two
    apart (it does not fold sharply)"""
    cw, ch, n = w / cols, h / rows, cols + 1
    out = []
    at = lambda i, j: j * n + i  # noqa: E731
    for j in range(rows + 1):
        for i in range(cols + 1):
            if i < cols:
                out.append((at(i, j), at(i + 1, j), cw, 1.0))
            if j < rows:
                out.append((at(i, j), at(i, j + 1), ch, 1.0))
            if i < cols and j < rows:
                d = math.hypot(cw, ch)
                out.append((at(i, j), at(i + 1, j + 1), d, 0.6))
                out.append((at(i + 1, j), at(i, j + 1), d, 0.6))
            if i + 2 <= cols:
                out.append((at(i, j), at(i + 2, j), cw * 2, 0.25))
            if j + 2 <= rows:
                out.append((at(i, j), at(i, j + 2), ch * 2, 0.25))
    return out


def normals(pos, cols, rows):
    g = pos.reshape(rows + 1, cols + 1, 3)
    du = np.empty_like(g)
    dv = np.empty_like(g)
    du[:, 1:-1], du[:, 0], du[:, -1] = g[:, 2:] - g[:, :-2], g[:, 1] - g[:, 0], g[:, -1] - g[:, -2]
    dv[1:-1], dv[0], dv[-1] = g[2:] - g[:-2], g[1] - g[0], g[-1] - g[-2]
    n = np.cross(du, dv)
    length = np.sqrt((n * n).sum(-1, keepdims=True))
    return (n / np.maximum(length, 1e-9)).reshape(-1, 3)


def air(pos, t, wind, gust, seed, period=None):
    """the wind at every point at time t: the wind said, swelling and dropping in waves that travel across the sheet.
    With a `period` (seconds) every wave fits a whole number of times into it: the wind at t + period is the wind at t"""
    speed = float(np.linalg.norm(wind))
    if speed <= 0:
        return np.zeros_like(pos)
    turn = 2 * math.pi / period if period else 0.0
    w = [max(1, round(f / turn)) * turn if period else f for f in (4.1, 7.3, 5.3, 4.9, 6.7)]
    x, y = pos[:, 0], pos[:, 1]
    swell = 1 + gust * (0.6 * np.sin(w[0] * t + 0.9 * x + seed * 1.3) + 0.4 * np.sin(w[1] * t + 1.3 * y + seed * 2.1))
    out = wind[None, :] * swell[:, None]
    push = 0.5 * gust * speed  # air across the wind, in waves that run down and along the sheet: it ripples
    out[:, 0] += push * np.sin(w[2] * t + 2.0 * y + seed * 0.7)
    out[:, 1] += push * np.sin(w[3] * t + 2.0 * x + seed * 1.9)
    out[:, 2] += push * np.cos(w[4] * t + 1.6 * x - 2.2 * y + seed * 0.3)
    return out


def simulate(a):
    """a = the checked arguments -> the frames, each (points, 3), in STUDS"""
    cols, rows, (w, h) = a["cols"], a["rows"], a["size"]
    pos = rest_grid(cols, rows, w, h)
    if a["start"] == "flat":  # let go lying level: what hung down (-y) lies out behind the held edge (+z)
        pos = np.stack([pos[:, 0], np.zeros(len(pos)), -pos[:, 1]], -1)
    prev = pos.copy()
    weight = np.ones(len(pos))
    for i, j in held(cols, rows, a["pin"]):
        weight[j * (cols + 1) + i] = 0.0
    pins = weight == 0
    home = pos[pins].copy()
    sets = pbd.groups(links(cols, rows, w, h), len(pos))
    wind, g = np.array(a["wind"], dtype=float), np.array([0.0, -a["gravity"], 0.0])
    sub = max(1, math.ceil(RATE / a["fps"]))
    dt = 1.0 / (a["fps"] * sub)
    t = 0.0
    period = a["frames"] / a["fps"] if a["loop"] else None  # (a loop: the wind comes round once a sequence)

    def frame():
        nonlocal pos, prev, t
        for _ in range(sub):
            vel = (pos - prev) / dt
            n = normals(pos, cols, rows)
            push = ((air(pos, t, wind, a["gust"], a["seed"], period) - vel) * n).sum(-1, keepdims=True) * n * a["drag"]
            new = pbd.step(pos, prev, g[None, :] + push, dt, a["damp"])
            new[pins] = home
            prev, pos = pos, pbd.solve(new, weight, sets, ITERS)
            pos[pins] = home
            t += dt

    if a["start"] == "hang":
        # unrecorded: three seconds of it, and for a loop at least six times round (a sheet driven by a wind that
        # comes round settles into a motion that comes round with it)
        for _ in range(max(int(a["fps"] * 3), a["frames"] * 6 if a["loop"] else 0)):
            frame()
    n = a["frames"]
    blend = max(2, n // 4) if a["loop"] else 0
    raw = []
    for f in range(n + blend):
        if f > 0 or a["start"] == "hang":
            frame()
        raw.append(pos.copy())
    if not blend:
        return raw
    # the wind has come round, the sheet nearly (its own slow swing is not the wind's): the last frames lean, more and
    # more, on the frames one round earlier - two poses that are close, so no link is shortened by the mixing
    out = []
    for i in range(n):
        k = i - (n - blend)
        if k < 0:
            out.append(raw[i + blend])
        else:
            m = (k + 1) / (blend + 1)
            m = m * m * (3 - 2 * m)
            out.append(raw[i + blend] * (1 - m) + raw[k] * m)
    return out


def check(data, loop=None, play=None):
    """the checks of a cloth FILE, from its own frames (unit size): [{name, ok, value, limit, fix}]. `loop` = the
    layer plays it round (None: as the file was baked); `play` = the frames a second the layer plays it at"""
    a = data.get("args") or {}
    cols, rows, frames = data.get("cols"), data.get("rows"), data.get("frames")
    size = a.get("size")
    sound = (data.get("recipe") == "cloth" and isinstance(cols, int) and isinstance(rows, int) and cols >= 1 and rows >= 1
             and isinstance(frames, list) and len(frames) >= 2 and a.get("pin") in PINS
             and isinstance(size, list) and len(size) == 2 and all(isinstance(s, (int, float)) and not isinstance(s, bool) and s > 0 for s in size))
    if sound:
        try:
            arr = np.array(frames, dtype=float)
            sound = arr.shape == (len(frames), (cols + 1) * (rows + 1) * 3) and bool(np.isfinite(arr).all())
        except (ValueError, TypeError):
            sound = False
    if not sound:
        return [{"name": "a cloth bake", "ok": False, "value": "not one", "limit": "recipe cloth, its grid, its size and pin, every frame whole",
                 "fix": "bake it again: lune run kit vfx cloth <name>"}]
    arr = arr.reshape(len(frames), -1, 3)
    unit = max(size)
    w, h, n = size[0] / unit, size[1] / unit, cols + 1
    g = arr.reshape(len(frames), rows + 1, n, 3)
    along = np.sqrt(((g[:, :, 1:] - g[:, :, :-1]) ** 2).sum(-1)) / (w / cols)
    down = np.sqrt(((g[:, 1:] - g[:, :-1]) ** 2).sum(-1)) / (h / rows)
    stretch = float(max(along.max(), down.max()))
    both = np.concatenate([along.reshape(len(frames), -1), down.reshape(len(frames), -1)], 1)
    slack, short = float(both.mean(1).min()), float(both.min())
    fps = a.get("fps") if isinstance(a.get("fps"), (int, float)) and not isinstance(a.get("fps"), bool) and a.get("fps") > 0 else 24
    pins = [j * n + i for i, j in held(cols, rows, a["pin"])]
    drift = float(np.abs(arr[:, pins] - arr[0:1, pins]).max())
    moves = np.sqrt(((arr[1:] - arr[:-1]) ** 2).sum(-1))  # (frames - 1, points)
    mean, worst = float(moves.mean()), float(moves.max())
    rows_out = [
        {"name": "the sheet moves", "ok": mean * fps >= STILL, "value": f"{mean * fps:.3f} of its length a second", "limit": f"at least {STILL}: under it the sheet hangs still",
         "fix": "more --wind or --gust, or --start flat (it falls open)"},
        {"name": "the cloth does not stretch", "ok": stretch <= STRETCH, "value": f"a link {stretch:.2f} times its length", "limit": f"at most {STRETCH}",
         "fix": "less --wind or --gravity (the links cannot hold it), or --cols / --rows that make its cells nearer square"},
        {"name": "it is a sheet", "ok": slack >= SHRINK[0] and short >= SHRINK[1], "value": f"its links' mean length falls to {slack:.2f} of their own, the shortest to {short:.2f}",
         "limit": f"a mean of at least {SHRINK[0]}, none under {SHRINK[1]} (of the grid its size and cols x rows say)",
         "fix": "less --gust or --wind (the sheet is crumpled), or bake it again: the frames are not this sheet's"},
        {"name": "the held edge stays", "ok": drift <= 0.002, "value": f"moved {drift:.4f}", "limit": "at most 0.002",
         "fix": "bake it again: a held point was moved"},
        {"name": "no jump between frames", "ok": worst <= POP, "value": f"a point moved {worst:.3f} in one frame", "limit": f"at most {POP} of the sheet's length",
         "fix": "more --fps (frames closer together) or less --wind"},
    ]
    if (a.get("loop") is True) if loop is None else loop:
        seam = float(np.sqrt(((arr[0] - arr[-1]) ** 2).sum(-1)).max())
        usual = float(np.percentile(moves.max(1), 75))  # (the largest move of a usual frame: not the seam's own neighbours)
        limit = max(usual * 2.5, 0.01)
        rows_out.append({"name": "the loop's seam", "ok": a.get("loop") is True and seam <= limit, "value": f"a point moves {seam:.3f} from the last frame to the first"
                         + ("" if a.get("loop") is True else " (baked without --loop)"),
                         "limit": f"at most {limit:.3f} (two and a half times a usual frame's largest move), on a bake made with --loop",
                         "fix": "bake it with --loop, or take \"loop\" off the layer"})
    if play is not None and not (0.5 * fps <= play <= 2 * fps):
        rows_out.append({"name": "it is played at its own speed", "ok": False, "value": f"the layer plays {play:g} frames a second, the bake is {fps:g}",
                         "limit": "from half to twice the bake's", "fix": f'"fps": {fps:g} in the params of the layer'})
    return rows_out


def look(frames, cols, rows, path):
    """six frames, each from the front (x, y) and from the side (z, y): the sheet's lines"""
    from PIL import Image, ImageDraw

    cell, pad = 190, 10
    picks = [round(k * (len(frames) - 1) / 5) for k in range(6)]
    img = Image.new("RGB", (pad + 6 * (cell + pad), 34 + 2 * (cell + pad)), (16, 18, 24))
    pen = ImageDraw.Draw(img)
    for col, f in enumerate(picks):
        g = np.asarray(frames[f]).reshape(rows + 1, cols + 1, 3)
        pen.text((pad + col * (cell + pad) + 4, 6), f"frame {f + 1}", fill=(200, 204, 214))
        for row, (ia, name) in enumerate(((0, "front"), (2, "side"))):
            ox, oy = pad + col * (cell + pad), 26 + row * (cell + pad)
            pen.rectangle([ox, oy, ox + cell, oy + cell], outline=(70, 74, 86))
            if col == 0:
                pen.text((ox + 4, oy + cell - 14), name, fill=(120, 126, 140))

            def px(p, ox=ox, oy=oy, ia=ia):
                return ox + cell / 2 + p[ia] * cell * 0.62, oy + cell * 0.12 - p[1] * cell * 0.62

            for j in range(rows + 1):
                pen.line([px(g[j, i]) for i in range(cols + 1)], fill=(230, 196, 120))
            for i in range(cols + 1):
                pen.line([px(g[j, i]) for j in range(rows + 1)], fill=(150, 170, 230))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path)


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


def numbers(text, n, what):
    try:
        v = [float(x) for x in text.split(",")]
    except ValueError:
        v = []
    if len(v) != n or not all(math.isfinite(x) for x in v):
        raise ValueError(f"{what} is {n} numbers with commas between them")
    return v


def arguments(o):
    """the options as text -> the checked arguments (ValueError in words)"""
    def num(key, lo, hi, whole=False):
        try:
            v = float(o[key])
        except ValueError:
            v = float("nan")
        if not (math.isfinite(v) and lo <= v <= hi) or (whole and v != int(v)):
            raise ValueError(f"{key} is {'a whole number' if whole else 'a number'} from {lo:g} to {hi:g}")
        return int(v) if whole else v

    a = {"size": numbers(o["--size"], 2, "--size w,h"), "wind": numbers(o["--wind"], 3, "--wind x,y,z"), "pin": o["--pin"], "start": o["--start"],
         "loop": o["--loop"] is True, "gust": num("--gust", 0, 1), "gravity": num("--gravity", 0, 200), "frames": num("--frames", 2, 64, True),
         "fps": num("--fps", 8, 60, True), "cols": num("--cols", 4, 48, True), "rows": num("--rows", 2, 24, True), "seed": num("--seed", 0, 9999),
         "drag": num("--drag", 0, 4), "damp": num("--damp", 0, 10)}
    if not all(0.2 <= s <= 200 for s in a["size"]):
        raise ValueError("--size is the sheet in studs, each side 0.2 to 200")
    if a["pin"] not in PINS:
        raise ValueError(f"--pin is one of {', '.join(PINS)}")
    if a["start"] not in ("hang", "flat"):
        raise ValueError("--start is hang or flat")
    if a["loop"] and a["start"] == "flat":
        raise ValueError("--loop with --start flat: a sheet that falls open does not come back to flat (take one off)")
    if a["loop"] and a["frames"] / a["fps"] < 1:
        raise ValueError("--loop needs a sequence of at least a second (--frames / --fps): the wind's waves must fit into it")
    if float(np.linalg.norm(a["wind"])) > 120:
        raise ValueError("--wind is at most 120 studs a second")
    return a


def main(argv):
    usage = "lune run kit vfx cloth <name> [--size 6,4] [--pin top|left|corners] [--wind 0,0,14] [--gust 0.5] [--loop]"
    o = {"--size": "6,4", "--pin": "top", "--wind": "0,0,14", "--gust": "0.5", "--gravity": "30", "--start": "hang", "--frames": "48", "--fps": "24",
         "--cols": "16", "--rows": "10", "--seed": "1", "--drag": "0.6", "--damp": "0.6", "--out-dir": OUT, "--look-dir": LOOK, "--loop": False}
    names, i = [], 0
    while i < len(argv):
        if argv[i] == "--loop":
            o["--loop"] = True
            i += 1
        elif argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"cloth: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"cloth: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", names[0]):
        return out("fail", "cloth: name ONE sequence, in lowercase letters, digits and _ (the game finds it by its exact letters)", usage)
    name = names[0]
    try:
        a = arguments(o)
    except ValueError as e:
        return out("fail", f"cloth {name}: {e}", usage)
    frames = simulate(a)
    if not all(np.isfinite(f).all() for f in frames):
        return out("fail", f"cloth {name}: the sheet flew apart (numbers that are not numbers)", "less --wind, less --drag, or more --fps")
    unit = max(a["size"])
    data = {"about": f"a cloth bake (kit/vfx/cloth.py): a {a['size'][0]:g} x {a['size'][1]:g} sheet held at its {a['pin']}, wind {a['wind']}, "
                     f"baked at {a['fps']} frames a second, unit size",
            "recipe": "cloth", "args": a, "cols": a["cols"], "rows": a["rows"],
            "frames": [[round(float(x) / unit, 4) for x in f.reshape(-1)] for f in frames]}
    rows = check(data)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return out("fail", f"cloth {name}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    text = json.dumps(data, separators=(",", ":"))
    kb = len(text.encode("utf-8")) / 1024
    path = os.path.join(o["--out-dir"], f"{name}.json")
    if kb > 600:  # (measured BEFORE anything is written: a refused bake leaves an earlier good one of its name alone)
        return out("fail", f"cloth {name}: {kb:.0f} KB of frames (the data rides into the game: 600 at most)", "fewer --frames, --cols or --rows")
    os.makedirs(o["--out-dir"], exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    picture = os.path.join(o["--look-dir"], f"{name}.png")
    look([np.asarray(f) / unit for f in frames], a["cols"], a["rows"], picture)
    loop = ', "loop": true' if a["loop"] else ""
    return out("pass", f"cloth {name}: {a['frames']} frames of a {a['cols']} x {a['rows']} sheet, {kb:.0f} KB - on a mesh layer: "
               f'"shape": "seq", "pivot": "origin", "params": {{"seq": "{name}", "fps": {a["fps"]}{loop}}}, its scale the sheet\'s longest side ({unit:g} studs)',
               f"OPEN {picture.replace(os.sep, '/')}: does the sheet move as THIS effect's cloth does?", checks=rows, look=picture.replace(os.sep, "/"),
               seq=path.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
