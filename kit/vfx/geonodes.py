"""geonodes.py - GEOMETRY NODES, BAKED (the VFX methods audit, stage 22): a mesh that Blender's Geometry Nodes build
and move - a node tree, not a script that moves vertices - read frame by frame and baked into a mesh sequence the
`seq` mesh shape replays (the game's VfxMesh and the browser player: nothing new runs in either).

    lune run kit vfx geonodes <name> --recipe ripple  [--waves 3] [--speed 1.5] [--amount 0.08] [--cols 20] [--rows 20] [--loop]
    lune run kit vfx geonodes <name> --recipe scatter [--count 24] [--seed 1] [--size 0.08] [--speed 0.5] [--rise 0.2] [--spin 2]
                                     [--frames 32] [--fps 24] [--blender <blender.exe>]

  ripple   a Grid whose points a Set Position node lifts by rings that run out from the middle with the Scene Time
           and die at the rim: `--waves` rings across the radius, `--speed` rings a second passing a place,
           `--amount` their height (the ground is 1 wide). `--loop`: the rings come round once a sequence
  scatter  points Distributed on the Faces of a disc, a small quad Instanced on each (`--size`, of the ground),
           every instance growing (from a fiftieth of its size) as a front that runs out from the middle at
           `--speed` (ground widths a second) reaches it - over `--rise` of a width - and turning at `--spin` radians a second; Realized, so every
           quad is its own strip of the mesh. The points' number is what the tree gives for about `--count`

Blender does the work (kit/vfx/geonodes_bake.py runs inside it, headless): it is found as --blender, else as every kit
tool finds it (kit/blender_path.py: KIT_BLENDER / BLENDER, the OS's install folders newest first, then the PATH).

Writes assets/effects/seq/<name>.json (unit size: the ground is 1 wide, y up) and a picture of six of its frames.
A bake is refused when nothing moves, the mesh jumps, a ripple's grid slides sideways, its rim lifts or its rings
run inward, a
scatter's quads are not square, lift off the ground, wander or shrink. `check(data)` is that list from a FILE's own
frames (the method gate asks it).
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_KIT = os.path.abspath(os.path.join(_HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

OUT = os.path.join("assets", "effects", "seq")
LOOK = os.path.join("build", "vfx", "geonodes")
BAKE = os.path.join(_HERE, "geonodes_bake.py")
RECIPES = ("ripple", "scatter")
STILL = 0.01   # the least a point moves a SECOND, on average over the points that move at all, in ground widths
POP = 0.25     # the most a point moves in one frame


def blender(asked=None):
    """the Blender to run, or None"""
    if asked:  # (a Blender that was NAMED and is not there is not swapped for another)
        return asked if os.path.isfile(asked) else None
    return find_blender()


def bake(a, exe):
    """the asks -> what the tree gave (the dict geonodes_bake.py writes); raises RuntimeError saying what Blender said"""
    tmp = tempfile.mkdtemp(prefix="kit_geonodes_")
    try:
        asks, got = os.path.join(tmp, "asks.json"), os.path.join(tmp, "out.json")
        with open(asks, "w", encoding="utf-8") as fh:
            json.dump(a, fh)
        r = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "2", "-P", BAKE, "--", asks, got],
                           capture_output=True, text=True, timeout=600, check=False)
        if r.returncode != 0 or not os.path.isfile(got):
            tail = [ln for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()][-3:]
            raise RuntimeError(" | ".join(tail)[:400] or f"Blender ended with {r.returncode}")
        with open(got, encoding="utf-8") as fh:
            return json.load(fh)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check(data, loop=None, play=None):
    """the checks of a geometry-nodes FILE, from its own frames (unit size): [{name, ok, value, limit, fix}]"""
    a = data.get("args") if isinstance(data.get("args"), dict) else {}
    cols, rows, strips, frames = data.get("cols"), data.get("rows"), data.get("strips", 1), data.get("frames")
    whole = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
    recipe = a.get("recipe")
    sound = (data.get("recipe") == "geonodes" and recipe in RECIPES and whole(cols) and whole(rows) and whole(strips) and cols >= 1 and rows >= 1
             and strips >= 1 and isinstance(frames, list) and len(frames) >= 2 and isinstance(data.get("nodes"), list)
             and any(isinstance(n, str) and n.startswith("GeometryNode") for n in data["nodes"])
             and (recipe != "scatter" or (cols == 1 and rows == 1 and strips >= 2)) and (recipe != "ripple" or strips == 1))
    if sound:
        try:
            arr = np.array(frames, dtype=float)
            sound = arr.shape == (len(frames), strips * (cols + 1) * (rows + 1) * 3) and bool(np.isfinite(arr).all())
        except (ValueError, TypeError):
            sound = False
    if not sound:
        return [{"name": "a geometry-nodes bake", "ok": False, "value": "not one", "limit": "recipe geonodes, its tree's nodes, its grid or strips, every frame whole",
                 "fix": "bake it again: lune run kit vfx geonodes <name> --recipe ripple|scatter"}]
    fps = a.get("fps") if isinstance(a.get("fps"), (int, float)) and not isinstance(a.get("fps"), bool) and a.get("fps") > 0 else 24
    pts = arr.reshape(len(frames), -1, 3)
    steps = np.linalg.norm(pts[1:] - pts[:-1], axis=-1)
    busy = steps.max(0) > 1e-4
    moved = float(steps[:, busy].mean()) * fps if busy.any() else 0.0
    worst = float(steps.max())
    out = [
        {"name": "the mesh moves", "ok": moved >= STILL and float(busy.mean()) >= 0.2, "value": f"{moved:.3f} of the ground a second, {busy.mean():.2f} of its points",
         "limit": f"at least {STILL}, and a fifth of the points", "fix": "more --speed or --amount (a ripple), more --speed or --frames (a scatter: the front had not come)"},
        {"name": "no jump", "ok": worst <= POP, "value": f"a point moved {worst:.3f} in one frame", "limit": f"at most {POP} of the ground", "fix": "more --fps, less --speed"},
    ]
    if recipe == "ripple":
        g = arr.reshape(len(frames), rows + 1, cols + 1, 3)
        slide = float(max(np.abs(g[..., 0] - g[0:1, ..., 0]).max(), np.abs(g[..., 2] - g[0:1, ..., 2]).max()))
        wide = float(max(np.ptp(g[0, ..., 0]), np.ptp(g[0, ..., 2])))
        r = np.hypot(g[0, ..., 0], g[0, ..., 2])
        rim = float(np.abs(g[..., 1])[:, r >= 0.5 - 1e-6].max()) if (r >= 0.5 - 1e-6).any() else 0.0
        high = float(np.abs(g[..., 1]).max())
        mid = g[:, rows // 2, :, 1]  # the heights along the middle row
        lit = np.where(np.abs(mid) >= 0.02 * max(high, 1e-9), mid, 0.0)  # (a height rounded to nothing is no side of the ground)
        turns = int((lit[:, 1:] * lit[:, :-1] < 0).sum(1).max()) if high > 0 else 0
        half = g[:, rows // 2, cols // 2:, 1]  # the middle row, from the middle out: do the rings run OUT?
        outward = float((half[1:, 1:] * half[:-1, :-1]).sum())   # this frame, one point further out, against the last frame
        inward = float((half[1:, :-1] * half[:-1, 1:]).sum())
        out += [
            {"name": "the grid stays where it is", "ok": slide <= 1e-3 and abs(wide - 1) <= 0.01, "value": f"a point slid {slide:.4f} sideways; the ground is {wide:.2f} wide",
             "limit": "no slide (the tree lifts, it does not push), the ground 1 wide", "fix": "bake it again: the frames are not this grid's"},
            {"name": "rings that die at the rim", "ok": rim <= 0.02 * max(high, 1e-9) + 1e-3 and high >= 0.005 and turns >= 1,
             "value": f"{high:.3f} high at the most, {rim:.4f} at the rim, the middle row crosses the ground {turns} time(s)",
             "limit": "over 0.005 high, flat at the rim, up AND down across the middle", "fix": "more --amount or --waves"},
            {"name": "the rings run out", "ok": outward > inward, "value": f"a frame is like the last one moved OUT by {outward:.4f}, moved IN by {inward:.4f}",
             "limit": "more like it moved out", "fix": "less --speed for its --fps (over a quarter of a ring a frame the rings seem to run back in), or bake it again"},
        ]
        if (a.get("loop") is True) if loop is None else loop:
            seam = float(np.linalg.norm(pts[0] - pts[-1], axis=-1).max())
            limit = max(float(np.percentile(steps.max(1), 75)) * 2.5, 0.002)
            out.append({"name": "the loop's seam", "ok": a.get("loop") is True and seam <= limit,
                        "value": f"a point moves {seam:.4f} from the last frame to the first" + ("" if a.get("loop") is True else " (baked without --loop)"),
                        "limit": f"at most {limit:.4f}, on a bake made with --loop", "fix": 'bake it with --loop, or take "loop" off the layer'})
    else:
        q = arr.reshape(len(frames), strips, 4, 3)  # a quad: (row 0: col 0, col 1), (row 1: col 0, col 1)
        e = np.stack([np.linalg.norm(q[:, :, 1] - q[:, :, 0], axis=-1), np.linalg.norm(q[:, :, 3] - q[:, :, 2], axis=-1),
                      np.linalg.norm(q[:, :, 2] - q[:, :, 0], axis=-1), np.linalg.norm(q[:, :, 3] - q[:, :, 1], axis=-1)], -1)
        size = e.mean(-1)
        skew = float((e.max(-1) - e.min(-1)).max())
        diag = float(np.abs(np.linalg.norm(q[:, :, 3] - q[:, :, 0], axis=-1) - size * math.sqrt(2)).max())
        lift = float(np.abs(q[..., 1]).max())
        centre = q.mean(2)
        wander = float(np.linalg.norm(centre - centre[0:1], axis=-1).max())
        reach = float(np.linalg.norm(centre[0][:, [0, 2]], axis=-1).max())
        shrink = float((size[:-1] - size[1:]).max())
        come = float((size[-1] > 0.5 * max(float(size.max()), 1e-9)).mean())
        late = np.argmax(size > 0.5 * np.maximum(size.max(0, keepdims=True), 1e-9), axis=0)  # the frame each quad is half grown
        rad = np.linalg.norm(centre[0][:, [0, 2]], axis=-1)
        grown = size.max(0) > 1e-4
        order = float(np.corrcoef(rad[grown], late[grown])[0, 1]) if grown.sum() >= 4 and np.ptp(late[grown]) > 0 and np.ptp(rad[grown]) > 0 else 0.0
        out += [
            {"name": "every strip is a square on the ground", "ok": skew <= 2e-3 and diag <= 3e-3 and lift <= 1e-3,
             "value": f"sides {skew:.4f} apart, a diagonal {diag:.4f} off a square's, {lift:.4f} off the ground", "limit": "a square, flat on y = 0, in every frame",
             "fix": "bake it again: the frames are not instanced quads"},
            {"name": "the instances keep their places", "ok": wander <= 1e-3 and reach <= 0.5 + 1e-3, "value": f"a middle moved {wander:.4f}; the farthest is {reach:.2f} from the middle",
             "limit": "no middle moves, all within the disc (0.5)", "fix": "bake it again: an instance was moved"},
            {"name": "a front that runs out", "ok": shrink <= 1e-3 and come >= 0.5 and order >= 0.6,
             "value": f"{come:.2f} of the quads grown by the last frame; nearer the middle grows sooner: {order:.2f}; a quad shrank by {max(shrink, 0):.4f}",
             "limit": "at least half grown, growth in order of distance (0.6 or more), none shrinking", "fix": "more --frames or --speed (the front had not come)"},
        ]
        if loop:
            out.append({"name": "it is played once", "ok": False, "value": "the layer loops it", "limit": "what has grown does not go back", "fix": 'take "loop" off the layer'})
    if play is not None and not (0.5 * fps <= play <= 2 * fps):
        out.append({"name": "it is played at its own speed", "ok": False, "value": f"the layer plays {play:g} frames a second, the bake is {fps:g}",
                    "limit": "from half to twice the bake's", "fix": f'"fps": {fps:g} in the params of the layer'})
    return out


def look(data, path):
    """six frames from the front (x, y: heights three times as tall) and from above (x, z)"""
    from PIL import Image, ImageDraw

    cols, rows, strips = data["cols"], data["rows"], data.get("strips", 1)
    g = np.array(data["frames"]).reshape(len(data["frames"]), strips, rows + 1, cols + 1, 3)
    cell, pad = 190, 10
    picks = [round(k * (len(g) - 1) / 5) for k in range(6)]
    img = Image.new("RGB", (pad + 6 * (cell + pad), 34 + 2 * (cell + pad)), (16, 18, 24))
    pen = ImageDraw.Draw(img)
    for col, f in enumerate(picks):
        pen.text((pad + col * (cell + pad) + 4, 6), f"frame {f + 1}", fill=(200, 204, 214))
        for row, (ib, name, k) in enumerate(((1, "front", -3.0), (2, "above", 1.0))):
            ox, oy = pad + col * (cell + pad), 26 + row * (cell + pad)
            pen.rectangle([ox, oy, ox + cell, oy + cell], outline=(70, 74, 86))
            if col == 0:
                pen.text((ox + 4, oy + cell - 14), name, fill=(120, 126, 140))

            def px(p, ox=ox, oy=oy, ib=ib, k=k):
                return ox + cell / 2 + p[0] * cell * 0.9, oy + cell / 2 + k * p[ib] * cell * 0.9

            for s in range(strips):
                for j in range(rows + 1):
                    pen.line([px(g[f, s, j, i]) for i in range(cols + 1)], fill=(230, 196, 120))
                for i in range(cols + 1):
                    pen.line([px(g[f, s, j, i]) for j in range(rows + 1)], fill=(150, 170, 230))
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

    if o["--recipe"] not in RECIPES:
        raise ValueError(f"--recipe is one of {', '.join(RECIPES)}")
    a = {"recipe": o["--recipe"], "frames": num("--frames", 2, 64, True), "fps": num("--fps", 8, 60, True), "loop": o["--loop"] is True}
    if a["recipe"] == "ripple":
        a.update(cols=num("--cols", 4, 48, True), rows=num("--rows", 4, 24, True), waves=num("--waves", 0.5, 12), speed=num("--speed", 0.1, 20),
                 amount=num("--amount", 0.005, 0.5))
        if a["waves"] > min(a["cols"], a["rows"]) / 5:
            raise ValueError(f"--waves {a['waves']:g} on {a['cols']} x {a['rows']} points is under 5 points a ring (the rings would be jagged or false): "
                             f"at most {min(a['cols'], a['rows']) / 5:g}, or more --cols / --rows")
        if a["loop"]:  # the rings come round a whole number of times in the sequence
            asked = a["speed"]
            turns = max(1, round(asked * a["frames"] / a["fps"]))
            a["speed"] = turns * a["fps"] / a["frames"]
            if abs(a["speed"] - asked) > 0.25 * asked:
                raise ValueError(f"--loop: the nearest speed whose rings come round in {a['frames']} frames at {a['fps']} a second is {a['speed']:g}, "
                                 f"far from the {asked:g} asked: more --frames, or that --speed")
        if a["speed"] / a["fps"] > 0.25:
            raise ValueError(f"--speed {a['speed']:g} at {a['fps']} frames a second is over a quarter of a ring a frame (the rings would seem to stand or run "
                             f"back in): at most {0.25 * a['fps']:g}, or more --fps")
    else:
        if a["loop"]:
            raise ValueError("--loop is for a ripple: a scatter's quads grow and do not go back")
        a.update(count=num("--count", 8, 64, True), seed=num("--seed", 0, 9999, True), size=num("--size", 0.01, 0.4), speed=num("--speed", 0.02, 10),
                 rise=num("--rise", 0.01, 1), spin=num("--spin", -20, 20))
    return a


def main(argv):
    usage = "lune run kit vfx geonodes <name> --recipe ripple|scatter [--frames 32] [--fps 24] (ripple: --waves --speed --amount --loop; scatter: --count --size --speed --rise --spin)"
    o = {"--recipe": "ripple", "--frames": "32", "--fps": "24", "--cols": "20", "--rows": "20", "--waves": "3", "--speed": "", "--amount": "0.08", "--count": "24",
         "--seed": "1", "--size": "0.08", "--rise": "0.2", "--spin": "2", "--blender": "", "--out-dir": OUT, "--look-dir": LOOK, "--loop": False}
    names, i = [], 0
    while i < len(argv):
        if argv[i] == "--loop":
            o["--loop"] = True
            i += 1
        elif argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"geonodes: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"geonodes: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", names[0]):
        return out("fail", "geonodes: name ONE sequence, in lowercase letters, digits and _ (the game finds it by its exact letters)", usage)
    name = names[0]
    if not o["--speed"]:
        o["--speed"] = "1.5" if o["--recipe"] == "ripple" else "0.5"
    try:
        a = arguments(o)
    except ValueError as e:
        return out("fail", f"geonodes {name}: {e}", usage)
    exe = blender(o["--blender"])
    if not exe:
        if o["--blender"]:
            return out("fail", f"geonodes {name}: no Blender at {o['--blender']}", usage)
        return out("fail", f"geonodes {name}: no Blender to run the tree in (--blender <blender.exe>, or KIT_BLENDER, or blender on the PATH)", usage)
    try:
        got = bake(a, exe)
    except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError) as e:
        return out("fail", f"geonodes {name}: Blender did not bake it: {e}", "kit/vfx/geonodes_bake.py (the tree) - or another --blender")
    data = {"about": f"a Geometry Nodes bake (kit/vfx/geonodes.py, Blender {got.get('blender')}): {a['recipe']}, baked at {a['fps']} frames a second, unit size "
                     "(the ground is 1 wide)",
            "recipe": "geonodes", "args": a, "blender": got.get("blender"), "nodes": got.get("nodes"), "cols": got.get("cols"), "rows": got.get("rows"),
            "frames": got.get("frames")}
    if a["recipe"] == "scatter" and (not isinstance(got.get("strips"), int) or got["strips"] < 4):
        return out("fail", f"geonodes {name}: the tree gave {got.get('strips')} quad(s) for a count of about {a['count']}: too few to be a scatter",
                   "more --count, or another --seed")
    if isinstance(got.get("strips"), int) and got["strips"] > 1:
        data["strips"] = got["strips"]
    rows = check(data)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return out("fail", f"geonodes {name}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    text = json.dumps(data, separators=(",", ":"))
    kb = len(text.encode("utf-8")) / 1024
    path = os.path.join(o["--out-dir"], f"{name}.json")
    if kb > 600:  # (measured BEFORE anything is written: a refused bake leaves an earlier good one of its name alone)
        return out("fail", f"geonodes {name}: {kb:.0f} KB of frames (the data rides into the game: 600 at most)", "fewer --frames, --cols / --rows or --count")
    os.makedirs(o["--out-dir"], exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    picture = os.path.join(o["--look-dir"], f"{name}.png")
    look(data, picture)
    loop = ', "loop": true' if a["loop"] else ""
    what = f"a {data['cols']} x {data['rows']} grid" if a["recipe"] == "ripple" else f"{data.get('strips')} quads"
    if a["recipe"] == "ripple" and a["loop"]:
        what += f" (its rings at {a['speed']:g} a second, so that they come round)"
    return out("pass", f"geonodes {name}: {a['frames']} frames of {what} from a tree of {len(data['nodes'])} kinds of node (Blender {data['blender']}), {kb:.0f} KB - "
               f'on a mesh layer: "shape": "seq", "pivot": "origin", "params": {{"seq": "{name}", "fps": {a["fps"]}{loop}}}, its scale the ground\'s width in studs',
               f"OPEN {picture.replace(os.sep, '/')}: does the mesh move as THIS effect's does?", checks=rows, look=picture.replace(os.sep, "/"),
               seq=path.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
