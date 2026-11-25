"""soft.py - A SOFT BODY, SIMULATED AND BAKED (the VFX methods audit, stage 16): a ball of jelly that is dropped or
thrown, squashes where it lands, springs back and wobbles - baked frame by frame into a mesh sequence the
`seq` mesh shape replays (the game's VfxMesh and the browser player: nothing new runs in either).

    lune run kit vfx soft <name> [--size 4] [--drop 6] [--throw 0,0,0] [--soft 0.6] [--squash 0.7]
                                 [--gravity 60] [--frames 48] [--fps 24] [--cols 16] [--rows 10]

  --size d       the ball's width in studs (it is baked at unit size: its width is 1; the layer's scale sizes it)
  --drop h       how far its underside starts above the floor, in studs
  --throw x,y,z  the speed it starts with, studs a second
  --soft 0..1    0.1 = a firm rubber ball, 0.8 = a water balloon (the softer it is, the less drop it takes
                 before it is crushed flat and refused)
  --squash 0..0.8  how much of the give is the WHOLE ball flattening and widening against dents where it is
                 touched (0). Over 0.8 nothing pulls the ball back to round and it flies apart: not taken

The floor is y = 0 of the sequence (put the layer's origin on the ground). The ball is points on its skin that keep
their distances and, together, are pulled back to the ball's own shape (shape matching: the
best-fitting turned and stretched copy of the rest shape, its volume kept). It collides with the floor only.

Writes assets/effects/seq/<name>.json (the mesh sequence format) and a picture of six of its frames. A bake is
refused when the ball never deforms, is crushed flat, loses or gains volume, sinks into the floor, cracks open or its skin jumps.
`check(data)` is that list of checks from a FILE's own frames (the method gate asks it).
"""
import json
import math
import os
import re
import sys

import numpy as np

OUT = os.path.join("assets", "effects", "seq")
LOOK = os.path.join("build", "vfx", "soft")
RATE, ITERS = 192, 6   # the ball is stepped at least RATE times a second, whatever the bake's fps
STILL = 0.05           # the least a point moves a SECOND, on average, in ball widths
DEFORM = 0.08          # its height against its width must leave 1 by at least this, in some frame
VOLUME = (0.75, 1.3)   # every frame's volume against the first frame's
FLAT = 0.2             # its height against its width never under this much of what it starts at: under it, a puddle
POP = 0.25             # the most a point of the skin moves in one frame, the ball's own travel taken out
FLOOR = -0.01          # the lowest any point may be


def skin(cols, rows):
    """the ball's own points, radius 1: [bottom pole, the rings bottom to top (cols each), top pole]"""
    pts = [(0.0, -1.0, 0.0)]
    for j in range(1, rows):
        ph = j / rows * math.pi
        for i in range(cols):
            th = i / cols * 2 * math.pi
            pts.append((math.sin(ph) * math.cos(th), -math.cos(ph), math.sin(ph) * math.sin(th)))
    pts.append((0.0, 1.0, 0.0))
    return np.array(pts)


def grid_of(cols, rows):
    """the mesh sequence's grid ((rows + 1) x (cols + 1), the seam column twice, each pole a whole row) -> which of
    the ball's points each grid vertex is"""
    idx = np.empty((rows + 1, cols + 1), dtype=int)
    idx[0, :] = 0
    idx[rows, :] = 1 + (rows - 1) * cols
    for j in range(1, rows):
        for i in range(cols + 1):
            idx[j, i] = 1 + (j - 1) * cols + (i % cols)
    return idx.reshape(-1)


def links(cols, rows, pts):
    at = lambda i, j: 1 + (j - 1) * cols + (i % cols)  # noqa: E731
    top = 1 + (rows - 1) * cols
    pairs = set()
    for j in range(1, rows):
        for i in range(cols):
            pairs.add((at(i, j), at(i + 1, j)))
            if j + 1 < rows:
                pairs.add((at(i, j), at(i, j + 1)))
                pairs.add((at(i, j), at(i + 1, j + 1)))
                pairs.add((at(i + 1, j), at(i, j + 1)))
    for i in range(cols):
        pairs.add((0, at(i, 1)))
        pairs.add((at(i, rows - 1), top))
    return [(a, b, float(np.linalg.norm(pts[a] - pts[b])), 0.5) for a, b in sorted(pairs)]


def relax(pos, a, b, rest, stiff, count, iters):
    """pull every link toward its rest length, ALL AT ONCE (each point takes the mean of what its links ask): no link
    goes before another, so a ball dropped straight stays straight (solved one set after another, the order of the
    sets is a lean, and the shape matching rolls the ball over on it)"""
    for _ in range(iters):
        d = pos[b] - pos[a]
        length = np.sqrt((d * d).sum(-1))
        corr = (stiff * 0.5 * (length - rest) / np.maximum(length, 1e-9))[:, None] * d
        move = np.zeros_like(pos)
        np.add.at(move, a, corr)
        np.add.at(move, b, -corr)
        pos += move / count[:, None]
    return pos


def goals(pos, q, squash):
    """shape matching: where every point would be if the ball were its rest shape `q` (about its own middle), turned
    and - by `squash` - stretched to fit the points best, its volume kept"""
    cm = pos.mean(0)
    p = pos - cm
    apq = p.T @ q
    u, _, vt = np.linalg.svd(apq)
    if np.linalg.det(u @ vt) < 0:
        u[:, -1] *= -1
    rot = u @ vt
    lin = apq @ np.linalg.inv(q.T @ q)
    det = np.linalg.det(lin)
    lin = lin / np.cbrt(det) if det > 1e-9 else rot
    return (q @ (squash * lin + (1 - squash) * rot).T) + cm


def simulate(a):
    """a = the checked arguments -> the frames, each ((rows + 1) * (cols + 1), 3) in the grid's order, in STUDS"""
    cols, rows, r = a["cols"], a["rows"], a["size"] / 2
    q = skin(cols, rows) * r
    q = q - q.mean(0)
    pos = q + np.array([0.0, r + a["drop"], 0.0])
    vel = np.tile(np.array(a["throw"], dtype=float), (len(pos), 1))
    ln = np.array(links(cols, rows, q))
    la, lb, rest, stiff = ln[:, 0].astype(int), ln[:, 1].astype(int), ln[:, 2], ln[:, 3]
    count = np.maximum(np.bincount(np.concatenate([la, lb]), minlength=len(pos)), 1).astype(float)
    order = grid_of(cols, rows)
    sub = max(1, math.ceil(RATE / a["fps"]))
    dt = 1.0 / (a["fps"] * sub)
    per = RATE * dt  # (this step against a step at RATE: what is said "a step" below is said for RATE)
    pull = 1 - (1 - (0.03 + 0.6 * (1 - a["soft"]) ** 2)) ** per  # how much of the way back to its shape one step takes
    grip = 0.4 ** per  # what the floor leaves of a touching point's slide, a step
    g = np.array([0.0, -a["gravity"], 0.0])
    out = [pos[order].copy()]
    vol0 = volume(pos[order].reshape(rows + 1, cols + 1, 3))
    for _ in range(a["frames"] - 1):
        for _ in range(sub):
            vel = vel + g * dt
            new = pos + vel * dt
            new = new + (goals(new, q, a["squash"]) - new) * pull
            relax(new, la, lb, rest, stiff, count, ITERS)
            under = new[:, 1] < 0
            new[under, 1] = 0.0
            # what the floor takes from its height the ball gives to its width (jelly does not shrink): the skin is
            # moved out from the ball's upright axis until the volume inside is the rest shape's again
            vol = volume(new[order].reshape(rows + 1, cols + 1, 3))
            if vol > 1e-9:
                wide = min(max(math.sqrt(vol0 / vol), 0.9 ** per), 1.1 ** per)
                mid = new.mean(0)
                new[:, 0] = mid[0] + (new[:, 0] - mid[0]) * wide
                new[:, 2] = mid[2] + (new[:, 2] - mid[2]) * wide
            new[under, 0] = pos[under, 0] + (new[under, 0] - pos[under, 0]) * grip  # the floor grips what touches it
            new[under, 2] = pos[under, 2] + (new[under, 2] - pos[under, 2]) * grip
            vel = (new - pos) / dt
            going = vel.mean(0)  # the wobble dies down; the ball's own flight does not (it falls as a thing falls)
            vel = going + (vel - going) * (1 - a["damp"] * dt)
            pos = new
        out.append(pos[order].copy())
    return out


def volume(g):
    """the volume inside a closed grid of points (rows + 1, cols + 1, 3)"""
    a, b, c, d = g[:-1, :-1], g[:-1, 1:], g[1:, 1:], g[1:, :-1]
    return abs(float((np.einsum("...i,...i", a, np.cross(b, c)) + np.einsum("...i,...i", a, np.cross(c, d))).sum()) / 6)


def check(data, loop=None, play=None):
    """the checks of a soft-body FILE, from its own frames (unit size): [{name, ok, value, limit, fix}]. `loop` = the
    layer plays it round (a drop does not come back to where it started: refused)"""
    a = data.get("args") if isinstance(data.get("args"), dict) else {}
    fps = a.get("fps") if isinstance(a.get("fps"), (int, float)) and not isinstance(a.get("fps"), bool) and a.get("fps") > 0 else 24
    cols, rows, frames = data.get("cols"), data.get("rows"), data.get("frames")
    sound = (data.get("recipe") == "soft" and isinstance(cols, int) and isinstance(rows, int) and not isinstance(cols, bool) and not isinstance(rows, bool)
             and cols >= 3 and rows >= 2 and isinstance(frames, list) and len(frames) >= 2)
    if sound:
        try:
            arr = np.array(frames, dtype=float)
            sound = arr.shape == (len(frames), (cols + 1) * (rows + 1) * 3) and bool(np.isfinite(arr).all())
        except (ValueError, TypeError):
            sound = False
    if not sound:
        return [{"name": "a soft-body bake", "ok": False, "value": "not one", "limit": "recipe soft, its grid, every frame whole",
                 "fix": "bake it again: lune run kit vfx soft <name>"}]
    g = arr.reshape(len(frames), rows + 1, cols + 1, 3)
    crack = float(max(np.abs(g[:, :, 0] - g[:, :, -1]).max(), np.abs(g[:, 0] - g[:, 0, :1]).max(), np.abs(g[:, -1] - g[:, -1, :1]).max()))
    pts = arr.reshape(len(frames), -1, 3)
    mean = float(np.sqrt(((pts[1:] - pts[:-1]) ** 2).sum(-1)).mean())
    own = pts - pts.mean(1, keepdims=True)  # each frame about its own middle: the skin's move, not the ball's travel
    pop = float(np.sqrt(((own[1:] - own[:-1]) ** 2).sum(-1)).max())
    ext = pts.max(1) - pts.min(1)
    ratio = ext[:, 1] / np.maximum((ext[:, 0] + ext[:, 2]) / 2, 1e-9)
    ratio = ratio / ratio[0]
    most = float(ratio[np.argmax(np.abs(ratio - 1))])
    gives = int((np.abs(ratio - 1) >= DEFORM).sum())
    vols = np.array([volume(f) for f in g])
    rel = vols / max(vols[0], 1e-12)
    low = float(pts[..., 1].min())
    rows_out = [
        {"name": "the ball moves", "ok": mean * fps >= STILL, "value": f"{mean * fps:.3f} of its width a second", "limit": f"at least {STILL}: under it the ball sits still",
         "fix": "more --drop or a --throw"},
        {"name": "it is soft", "ok": gives >= 2, "value": f"its height against its width goes to {most:.2f} of what it starts at ({gives} frame(s) out of shape)",
         "limit": f"under {1 - DEFORM:.2f} or over {1 + DEFORM:.2f} in at least 2 frames: a ball that keeps its shape is a rigid ball",
         "fix": "more --soft, more --drop, or more --frames (it had not landed yet)"},
        {"name": "it is not crushed flat", "ok": float(ratio.min()) >= FLAT, "value": f"its height against its width falls to {ratio.min():.2f} of what it starts at",
         "limit": f"not under {FLAT}: under it the ball is a puddle", "fix": "less --soft, less --drop or less --gravity"},
        {"name": "it keeps its volume", "ok": VOLUME[0] <= float(rel.min()) and float(rel.max()) <= VOLUME[1],
         "value": f"{rel.min():.2f} to {rel.max():.2f} of the first frame's", "limit": f"{VOLUME[0]} to {VOLUME[1]}",
         "fix": "less --soft or less --drop (it is crushed flat)"},
        {"name": "it stays on the floor", "ok": low >= FLOOR, "value": f"its lowest point at {low:.3f}", "limit": f"not under {FLOOR} (the floor is y = 0)",
         "fix": "bake it again: a point was moved under the floor"},
        {"name": "its skin is closed", "ok": crack <= 1e-3, "value": f"its seam or a pole open by {crack:.4f}", "limit": "at most 0.001",
         "fix": "bake it again: the seam's two columns or a pole's row came apart"},
        {"name": "no jump in its skin", "ok": pop <= POP, "value": f"a point moved {pop:.3f} in one frame (the ball's travel taken out)", "limit": f"at most {POP} of its width",
         "fix": "more --fps, less --throw (it spins or lands too hard for the frames to follow)"},
    ]
    if loop:
        rows_out.append({"name": "it is played once", "ok": False, "value": "the layer loops it", "limit": "a dropped ball does not come back to where it started",
                         "fix": 'take "loop" off the layer'})
    if play is not None and not (0.5 * fps <= play <= 2 * fps):
        rows_out.append({"name": "it is played at its own speed", "ok": False, "value": f"the layer plays {play:g} frames a second, the bake is {fps:g}",
                         "limit": "from half to twice the bake's", "fix": f'"fps": {fps:g} in the params of the layer'})
    return rows_out


def look(frames, cols, rows, path):
    """six frames from the side (x, y), the floor drawn"""
    from PIL import Image, ImageDraw

    cell, pad = 190, 10
    picks = [round(k * (len(frames) - 1) / 5) for k in range(6)]
    allp = np.asarray(frames)
    span = max(float(allp[..., 1].max()), float(np.abs(allp[..., 0]).max()) * 2, 1.0) * 1.1
    img = Image.new("RGB", (pad + 6 * (cell + pad), 34 + cell + pad), (16, 18, 24))
    pen = ImageDraw.Draw(img)
    for col, f in enumerate(picks):
        g = np.asarray(frames[f]).reshape(rows + 1, cols + 1, 3)
        ox, oy = pad + col * (cell + pad), 26
        pen.text((ox + 4, 6), f"frame {f + 1}", fill=(200, 204, 214))
        pen.rectangle([ox, oy, ox + cell, oy + cell], outline=(70, 74, 86))

        def px(p, ox=ox, oy=oy):
            return ox + cell / 2 + p[0] / span * cell, oy + cell - 8 - p[1] / span * (cell - 16)

        pen.line([ox, oy + cell - 8, ox + cell, oy + cell - 8], fill=(110, 116, 130))
        for j in range(rows + 1):
            pen.line([px(g[j, i]) for i in range(cols + 1)], fill=(230, 196, 120))
        for i in range(cols + 1):
            pen.line([px(g[j, i]) for j in range(rows + 1)], fill=(150, 170, 230))
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
        throw = [float(x) for x in o["--throw"].split(",")]
    except ValueError:
        throw = []
    if len(throw) != 3 or not all(math.isfinite(x) for x in throw) or math.sqrt(sum(x * x for x in throw)) > 200:
        raise ValueError("--throw x,y,z is 3 numbers with commas between them, 200 studs a second at most")
    return {"size": num("--size", 0.2, 200), "drop": num("--drop", 0, 400), "throw": throw, "soft": num("--soft", 0.05, 0.95), "squash": num("--squash", 0, 0.8),
            "gravity": num("--gravity", 0, 400), "frames": num("--frames", 2, 64, True), "fps": num("--fps", 8, 60, True), "cols": num("--cols", 6, 48, True),
            "rows": num("--rows", 4, 24, True), "damp": num("--damp", 0, 10)}


def main(argv):
    usage = "lune run kit vfx soft <name> [--size 4] [--drop 6] [--throw 0,0,0] [--soft 0.6] [--squash 0.7] [--gravity 60]"
    o = {"--size": "4", "--drop": "6", "--throw": "0,0,0", "--soft": "0.6", "--squash": "0.7", "--gravity": "60", "--frames": "48", "--fps": "24",
         "--cols": "16", "--rows": "10", "--damp": "1.5", "--out-dir": OUT, "--look-dir": LOOK}
    names, i = [], 0
    while i < len(argv):
        if argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"soft: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"soft: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", names[0]):
        return out("fail", "soft: name ONE sequence, in lowercase letters, digits and _ (the game finds it by its exact letters)", usage)
    name = names[0]
    try:
        a = arguments(o)
    except ValueError as e:
        return out("fail", f"soft {name}: {e}", usage)
    frames = simulate(a)
    if not all(np.isfinite(f).all() for f in frames):
        return out("fail", f"soft {name}: the ball flew apart (numbers that are not numbers)", "less --throw, less --soft, or more --fps")
    unit = a["size"]
    data = {"about": f"a soft-body bake (kit/vfx/soft.py): a ball {a['size']:g} studs wide dropped {a['drop']:g} studs, thrown at {a['throw']}, "
                     f"baked at {a['fps']} frames a second, unit size, the floor at y = 0",
            "recipe": "soft", "args": a, "cols": a["cols"], "rows": a["rows"],
            "frames": [[round(float(x) / unit, 4) for x in f.reshape(-1)] for f in frames]}
    rows = check(data)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return out("fail", f"soft {name}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    text = json.dumps(data, separators=(",", ":"))
    kb = len(text.encode("utf-8")) / 1024
    path = os.path.join(o["--out-dir"], f"{name}.json")
    if kb > 600:  # (measured BEFORE anything is written: a refused bake leaves an earlier good one of its name alone)
        return out("fail", f"soft {name}: {kb:.0f} KB of frames (the data rides into the game: 600 at most)", "fewer --frames, --cols or --rows")
    os.makedirs(o["--out-dir"], exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    picture = os.path.join(o["--look-dir"], f"{name}.png")
    look([np.asarray(f) / unit for f in frames], a["cols"], a["rows"], picture)
    return out("pass", f"soft {name}: {a['frames']} frames of a {a['cols']} x {a['rows']} ball, {kb:.0f} KB - on a mesh layer: "
               f'"shape": "seq", "pivot": "origin", "params": {{"seq": "{name}", "fps": {a["fps"]}}}, its scale the ball\'s width ({unit:g} studs), its origin on the ground',
               f"OPEN {picture.replace(os.sep, '/')}: does the ball give and spring back as THIS effect's body does?", checks=rows,
               look=picture.replace(os.sep, "/"), seq=path.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
