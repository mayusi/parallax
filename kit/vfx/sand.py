"""sand.py - SAND, SIMULATED AND BAKED (the VFX methods audit, stage 17): a heap of grains as the height of the
sand over the ground. Sand holds a slope up to its angle of repose and no steeper: wherever the heap is steeper, the
grains run downhill until it is not. Baked frame by frame into a mesh sequence the `seq` mesh shape replays.

    lune run kit vfx sand <name> [--mode slump|pour] [--size 8] [--height 4] [--width 2.5] [--repose 34]
                                 [--rate 6] [--settle s] [--frames 40] [--fps 24] [--cols 20] [--rows 20]

  --mode slump   a pillar of sand (--width across, --height tall) let go: it collapses into a heap over --settle
                 seconds (four fifths of the sequence unless said), fast at first and slowing
  --mode pour    sand poured onto the middle of the ground at --rate cubic studs a second: a cone that grows, its
                 sides sliding whenever they pass the angle of repose
  --size s       the square of ground the sand may spread over, in studs (baked at unit size: that square is 1)
  --repose deg   the steepest slope the sand holds (dry sand about 34, gravel 40, wet sand 45, fine ash 25)

The sand is a grid of heights (cols x rows over the ground). Each step, every cell steeper than the angle of repose
against a neighbour gives that neighbour sand; nothing is made or lost. It is the heap's SURFACE that is simulated,
not its grains: no grain flies, bounces or sprays (a swarm does that), and the ground is flat. A slump's SHAPES are
the simulation's; how long it takes is --settle (the slide has no clock of its own here). A pour's clock is real:
--rate cubic studs a second.

Writes assets/effects/seq/<name>.json and a picture of six of its frames. A bake is refused when the sand does not
move (or moves in one jump), sand is made or lost or climbs, the heap is not at rest in its last frame, or it reaches
the edge of its ground.
`check(data)` is that list of checks from a FILE's own frames (the method gate asks it).
"""
import json
import math
import os
import re
import sys

import numpy as np

OUT = os.path.join("assets", "effects", "seq")
LOOK = os.path.join("build", "vfx", "sand")
MODES = ("slump", "pour")
SUB = 6
STILL = 0.012    # the least the surface moves a SECOND, on average, in ground widths
STEEP = 1.5      # the last frame's steepest slope may pass the angle of repose by this many degrees
BUSY = 0.4       # the sand moves in at least this part of the frames (not in one jump and then never)
MASS = 0.03      # sand made or lost, as a part of what there should be
EDGE = 0.002     # the highest the sand may stand on the edge of its ground


NEAR = ((0, 1), (1, 0), (1, 1), (1, -1), (1, 2), (2, 1), (1, -2), (2, -1))  # 16 ways downhill: a round heap, not a square one


def relax(h, limit, share=0.12):
    """one pass: every cell steeper than the sand holds against one of 16 cells round it gives that cell part of
    the excess. limit = (the height difference the sand holds across a cell, along one). What a cell gives the
    other takes: nothing is made or lost."""
    out = h.copy()
    n, m = h.shape
    for dj, di in NEAR:
        reach = math.hypot(dj * limit[1], di * limit[0])
        a = (slice(0, n - dj), slice(max(0, -di), m - max(0, di)))
        b = (slice(dj, n), slice(max(0, di), m - max(0, -di)))
        d = h[a] - h[b]
        move = np.where(np.abs(d) > reach, (d - np.sign(d) * reach) * share * 0.5, 0.0)
        out[a] -= move
        out[b] += move
    return out


def simulate(a):
    """a = the checked arguments -> the heights, each (rows + 1, cols + 1), in STUDS"""
    cols, rows, size = a["cols"], a["rows"], a["size"]
    cell = size / min(cols, rows)
    x = (np.arange(cols + 1) / cols - 0.5) * size
    z = (np.arange(rows + 1) / rows - 0.5) * size
    xx, zz = np.meshgrid(x, z)
    r = np.sqrt(xx * xx + zz * zz)
    limit = (math.tan(math.radians(a["repose"])) * size / cols, math.tan(math.radians(a["repose"])) * size / rows)
    area = (size / cols) * (size / rows)
    h = np.zeros((rows + 1, cols + 1))
    spout = np.exp(-(r / (0.06 * size + cell)) ** 2)
    spout = spout / (spout.sum() * area)  # one cubic stud of sand spread under the spout
    if a["mode"] == "slump":
        # the whole slide first (pass after pass until nothing is steeper than the sand holds), then its passes are
        # laid over --settle seconds, fast at first and slowing: sliding sand has no clock of its own here
        h = np.where(r <= a["width"] / 2, a["height"], 0.0).astype(float)
        states = [h]
        while len(states) < 20000:
            nxt = relax(states[-1], limit)
            if float(np.abs(nxt - states[-1]).max()) < 1e-5 * a["height"]:
                break
            states.append(nxt)
        # how far along the slide each pass is, by how much sand has moved so far (the last passes move grains, the
        # first move the heap: laid out by passes, the whole collapse would be over in the first frames)
        done = np.cumsum([0.0] + [float(np.abs(states[k + 1] - states[k]).sum()) for k in range(len(states) - 1)])
        span = max(1.0, a["settle"] * a["fps"])
        out = []
        for f in range(a["frames"]):
            u = min(f / span, 1.0)
            want = done[-1] * (1 - (1 - u) ** 2)
            k = min(int(np.searchsorted(done, want)), len(states) - 1) if u < 1 else len(states) - 1
            if k == 0 or done[k] - done[k - 1] <= 0:
                out.append(states[k].copy())
            else:  # between two passes (the first pass alone moves near half the sand: a frame is a part of the way)
                m = (want - done[k - 1]) / (done[k] - done[k - 1])
                out.append(states[k - 1] * (1 - m) + states[k] * min(max(m, 0.0), 1.0))
        return out
    out = [h.copy()]
    for _ in range(a["frames"] - 1):
        for _ in range(SUB):
            h = h + spout * a["rate"] / (a["fps"] * SUB)
            for _ in range(400):  # (until this step's sand lies at rest: a frame is never a slide cut short)
                nxt = relax(h, limit)
                done = float(np.abs(nxt - h).max()) < 1e-4 * cell
                h = nxt
                if done:
                    break
        out.append(h.copy())
    return out


def to_points(h, size):
    """a frame's heights -> the grid's points (x across, y up, z along), in the heights' own unit"""
    rows, cols = h.shape[0] - 1, h.shape[1] - 1
    x = (np.arange(cols + 1) / cols - 0.5) * size
    z = (np.arange(rows + 1) / rows - 0.5) * size
    xx, zz = np.meshgrid(x, z)
    return np.stack([xx, h, zz], -1)


def check(data, loop=None, play=None):
    """the checks of a sand FILE, from its own frames (unit size: its ground is 1 wide): [{name, ok, value, limit, fix}]"""
    a = data.get("args") if isinstance(data.get("args"), dict) else {}
    cols, rows, frames = data.get("cols"), data.get("rows"), data.get("frames")
    repose, mode = a.get("repose"), a.get("mode")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)  # noqa: E731
    sound = (data.get("recipe") == "sand" and isinstance(cols, int) and isinstance(rows, int) and not isinstance(cols, bool) and not isinstance(rows, bool)
             and cols >= 4 and rows == cols and isinstance(frames, list) and len(frames) >= 2 and mode in MODES and num(repose) and 5 <= repose <= 60
             and num(a.get("size")) and a["size"] > 0 and num(a.get("fps")) and a["fps"] > 0 and (mode != "pour" or (num(a.get("rate")) and a["rate"] > 0)))
    if sound:
        try:
            arr = np.array(frames, dtype=float)
            sound = arr.shape == (len(frames), (cols + 1) * (rows + 1) * 3) and bool(np.isfinite(arr).all())
        except (ValueError, TypeError):
            sound = False
    if sound:
        g = arr.reshape(len(frames), rows + 1, cols + 1, 3)
        flat = to_points(np.zeros((rows + 1, cols + 1)), 1.0)
        sound = bool(np.abs(g[..., 0] - flat[..., 0]).max() <= 2e-4 and np.abs(g[..., 2] - flat[..., 2]).max() <= 2e-4)  # a height over each place of the ground
    if not sound:
        return [{"name": "a sand bake", "ok": False, "value": "not one", "limit": "recipe sand, its grid over the ground, its mode and angle, every frame whole",
                 "fix": "bake it again: lune run kit vfx sand <name>"}]
    h = g[..., 1]
    cw, ch = 1.0 / cols, 1.0 / rows
    vol = h.sum((1, 2)) * cw * ch
    if mode == "pour":
        t = np.arange(len(frames)) / a["fps"]
        want = a["rate"] * t / a["size"] ** 3
        off = float(np.abs(vol[1:] - want[1:]).max() / max(want[-1], 1e-12))
        mass = f"within {off:.3f} of what was poured"
    else:
        off = float(np.abs(vol - vol[0]).max() / max(vol[0], 1e-12))
        mass = f"within {off:.3f} of the pillar's"
    last = h[-1]
    slope = max(float(np.abs(np.diff(last, axis=1)).max() / cw), float(np.abs(np.diff(last, axis=0)).max() / ch))
    steep = math.degrees(math.atan(slope))
    held = (h.max(0) > 1e-4)  # the ground the sand ever lies on: bare ground does not count as sand that is still
    moved = float(np.abs(h[1:] - h[:-1])[:, held].mean()) if held.any() else 0.0
    rim = float(max(h[:, 0].max(), h[:, -1].max(), h[:, :, 0].max(), h[:, :, -1].max()))
    low = float(h.min())
    spread = float((last > 0.02 * max(float(last.max()), 1e-9)).mean())
    lim = math.tan(math.radians(repose))
    slid = float(np.abs(relax(last, (lim * cw, lim * ch)) - last).max())  # what one more pass would still move (all 16 ways)
    rest = max(0.02 * float(last.max()), 3e-4)
    busy = float((np.abs(h[1:] - h[:-1]).max((1, 2)) > 1e-4).mean())
    energy = (h * h).sum((1, 2))
    climbs = float((energy[1:] - energy[:-1]).max() / max(float(energy[0]), 1e-12))
    rows_out = [
        {"name": "the sand moves", "ok": moved * a["fps"] >= STILL, "value": f"{moved * a['fps']:.4f} of its ground's width a second", "limit": f"at least {STILL}, where the sand lies",
         "fix": "a taller or narrower pillar, more --rate, or a lower --repose"},
        {"name": "no sand is made or lost", "ok": off <= MASS, "value": mass, "limit": f"within {MASS}", "fix": "bake it again: the heights were changed"},
        {"name": "the heap holds no slope steeper than its sand", "ok": steep <= repose + STEEP, "value": f"its steepest slope ends at {steep:.0f} degrees",
         "limit": f"at most {repose:g} + {STEEP:g} degrees (its angle of repose)", "fix": "more --frames (it was still sliding), or a lower pillar"},
        {"name": "the heap has come to rest", "ok": slid <= rest, "value": f"one more pass would still move a place by {slid:.4f}",
         "limit": f"at most {rest:.4f} (a fiftieth of its height): the last frame is held, it must not be a slide cut short",
         "fix": "a --settle no longer than the sequence, more --frames, or less --rate"},
        {"name": "the sand keeps moving", "ok": busy >= BUSY, "value": f"it moves in {busy:.2f} of its frames", "limit": f"at least {BUSY} of them",
         "fix": "a longer --settle (the slide is over in the first frames), or fewer --frames"},
        {"name": "it is a heap", "ok": float(last.max()) > 0.02 and spread >= 0.03, "value": f"{last.max():.3f} high over {spread:.2f} of its ground",
         "limit": "over 0.02 high, over at least 0.03 of its ground", "fix": "more sand: a taller pillar, more --rate or more --frames"},
        {"name": "the sand stays on its ground", "ok": rim <= EDGE and low >= -1e-4, "value": f"{rim:.4f} high at the edge, its lowest {low:.4f}",
         "limit": f"at most {EDGE} at the edge (it would be cut off there), none under the ground", "fix": "a larger --size, or less sand"},
    ]
    if mode == "slump":
        rows_out.append({"name": "sand only runs downhill", "ok": climbs <= 1e-3, "value": f"its sand climbs by {max(climbs, 0):.4f} between two frames",
                         "limit": "never (a slide only lowers the heap)", "fix": "bake it again: the frames are out of order or not a slide"})
    if loop:
        rows_out.append({"name": "it is played once", "ok": False, "value": "the layer loops it", "limit": "a heap does not stand back up",
                         "fix": 'take "loop" off the layer'})
    fps = a["fps"]
    if play is not None and not (0.5 * fps <= play <= 2 * fps):
        rows_out.append({"name": "it is played at its own speed", "ok": False, "value": f"the layer plays {play:g} frames a second, the bake is {fps:g}",
                         "limit": "from half to twice the bake's", "fix": f'"fps": {fps:g} in the params of the layer'})
    return rows_out


def look(frames, path):
    """six frames: the heap cut through its middle (its outline, the angle of repose drawn beside it) and from above"""
    from PIL import Image, ImageDraw

    cell, pad = 190, 10
    picks = [round(k * (len(frames) - 1) / 5) for k in range(6)]
    top = max(float(np.max(frames[0])), float(np.max(frames[-1])), 1e-6)
    img = Image.new("RGB", (pad + 6 * (cell + pad), 34 + 2 * (cell + pad)), (16, 18, 24))
    pen = ImageDraw.Draw(img)
    for col, f in enumerate(picks):
        h = np.asarray(frames[f])
        ox = pad + col * (cell + pad)
        pen.text((ox + 4, 6), f"frame {f + 1}", fill=(200, 204, 214))
        oy = 26
        pen.rectangle([ox, oy, ox + cell, oy + cell], outline=(70, 74, 86))
        mid = h[h.shape[0] // 2]
        scale = cell * 0.9  # one ground width across the cell, heights at the same scale
        line = [(ox + cell * 0.05 + i / (len(mid) - 1) * scale, oy + cell - 8 - mid[i] * scale) for i in range(len(mid))]
        pen.line(line, fill=(230, 196, 120), width=2)
        pen.line([ox, oy + cell - 8, ox + cell, oy + cell - 8], fill=(110, 116, 130))
        oy = 26 + cell + pad
        img.paste(Image.fromarray((np.clip(h / top, 0, 1) * 235 + 20).astype(np.uint8)).resize((cell, cell)), (ox, oy))
        pen.rectangle([ox, oy, ox + cell, oy + cell], outline=(70, 74, 86))
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

    a = {"mode": o["--mode"], "size": num("--size", 0.5, 400), "height": num("--height", 0.05, 400), "width": num("--width", 0.05, 400),
         "repose": num("--repose", 5, 60), "rate": num("--rate", 0.001, 100000), "frames": num("--frames", 2, 64, True), "fps": num("--fps", 8, 60, True),
         "cols": num("--cols", 8, 24, True), "rows": num("--rows", 8, 24, True)}
    if a["cols"] != a["rows"]:
        raise ValueError("--cols and --rows are the same number (the ground is a square: on cells that are not, the heap comes out wider one way)")
    a["settle"] = num("--settle", 0.1, 8) if o["--settle"] else round(0.8 * (a["frames"] - 1) / a["fps"], 3)
    if a["mode"] == "slump" and a["settle"] * a["fps"] > a["frames"] - 1:
        raise ValueError(f"--settle {a['settle']:g} is longer than the sequence ({(a['frames'] - 1) / a['fps']:.2f} s): the heap would be cut off still sliding")
    if a["mode"] not in MODES:
        raise ValueError(f"--mode is one of {', '.join(MODES)}")
    if a["mode"] == "slump" and a["width"] < 3 * a["size"] / min(a["cols"], a["rows"]):
        raise ValueError("--width is under three cells of the grid: the pillar is too thin to stand on it (a larger --width, a smaller --size, more --cols / --rows)")
    return a


def main(argv):
    usage = "lune run kit vfx sand <name> [--mode slump|pour] [--size 8] [--height 4] [--width 2.5] [--repose 34] [--rate 6]"
    o = {"--mode": "slump", "--size": "8", "--height": "4", "--width": "2.5", "--repose": "34", "--rate": "6", "--frames": "40", "--fps": "24",
         "--cols": "20", "--rows": "20", "--settle": "", "--out-dir": OUT, "--look-dir": LOOK}
    names, i = [], 0
    while i < len(argv):
        if argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"sand: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"sand: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", names[0]):
        return out("fail", "sand: name ONE sequence, in lowercase letters, digits and _ (the game finds it by its exact letters)", usage)
    name = names[0]
    try:
        a = arguments(o)
    except ValueError as e:
        return out("fail", f"sand {name}: {e}", usage)
    heights = simulate(a)
    unit = a["size"]
    data = {"about": f"a sand bake (kit/vfx/sand.py): {a['mode']}, angle of repose {a['repose']:g} degrees, on {a['size']:g} studs of ground, "
                     f"baked at {a['fps']} frames a second, unit size, the ground at y = 0",
            "recipe": "sand", "args": a, "cols": a["cols"], "rows": a["rows"],
            "frames": [[round(float(x), 4) for x in to_points(h / unit, 1.0).reshape(-1)] for h in heights]}
    rows = check(data)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return out("fail", f"sand {name}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    text = json.dumps(data, separators=(",", ":"))
    kb = len(text.encode("utf-8")) / 1024
    path = os.path.join(o["--out-dir"], f"{name}.json")
    if kb > 600:  # (measured BEFORE anything is written: a refused bake leaves an earlier good one of its name alone)
        return out("fail", f"sand {name}: {kb:.0f} KB of frames (the data rides into the game: 600 at most)", "fewer --frames, --cols or --rows")
    os.makedirs(o["--out-dir"], exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    picture = os.path.join(o["--look-dir"], f"{name}.png")
    look([h / unit for h in heights], picture)
    return out("pass", f"sand {name}: {a['frames']} frames of a {a['cols']} x {a['rows']} heap, {kb:.0f} KB - on a mesh layer: "
               f'"shape": "seq", "pivot": "origin", "params": {{"seq": "{name}", "fps": {a["fps"]}}}, its scale the ground\'s width ({unit:g} studs), its origin on the ground',
               f"OPEN {picture.replace(os.sep, '/')}: does the heap slide and settle as THIS effect's sand does?", checks=rows,
               look=picture.replace(os.sep, "/"), seq=path.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
