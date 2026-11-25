"""points.py - A POINT CLOUD (the VFX methods audit, stage 18): a shape said as points - sampled from a figure or
from a PICTURE's own bright pixels - that a swarm's particles gather into, each particle drawn to a point of its own.

    lune run kit vfx points <name> [--new ring|disc|sphere|spiral|star] [--picture <png>] [--count 60] [--seed 1]
                                   [--pull 8]

A cloud is a file, assets/effects/points/<name>.json (VfxPresets.points.<name> in the game):
    { "points": [[x, y, z], ...] }     unit size: the farthest point is 1 from the middle; the layer's `size` sizes it
  --new       a starter cloud written to the file (it does not overwrite one): a figure of `--count` points
  --picture   the cloud is sampled from a picture you have (a sigil, a letter, a crest): `--count` points on its
              brightest, most opaque pixels, spread evenly over them, standing upright (x across, y up)
On a swarm layer:   "cloud": { "name": "<name>", "size": 6, "pull": [[0, 0], [0.4, 10], [1, 10]] }
  particle i is drawn to point i (round again when there are more particles than points); `size` is the cloud's
  radius in studs; `pull` (a number, or a curve over the layer's life) is how hard: with a pull of w a particle is
  on its point about 8 / w seconds after it starts a few cloud sizes away. A pull of 0 lets go (the particles scatter by whatever else the layer has).

THE RULE (one arithmetic in three places: here `pull`, the game's `cloudPull` in src/kit/VfxStage.luau, the player's
in kit/vfx/player/player.js; kit/selftest/vfx/points/run.py parity runs all three) - along each axis, for a
particle `d` from its point moving at `v`, pulled at `w` over a step `dt`:
    v' = (v - w*w*d*dt) / (1 + 2*w*dt + w*w*dt*dt)
a critically damped spring, stepped implicitly: it never blows up, whatever the step; a particle that starts at
rest, or moving away, never passes its point (one thrown AT its point faster than w times its distance passes it
once and comes back). The layer applies it LAST in its step, so gravity sags a held particle by gravity / w^2.

The command checks the file, flies a made swarm onto it with THE RULE and says when the shape is whole, and draws
the cloud (from the front and from above) to look at. Nothing here plays in Roblox or in the browser player.
"""
import json
import math
import os
import re
import sys

OUT = os.path.join("assets", "effects", "points")
LOOK = os.path.join("build", "vfx", "points")
LEAST, MOST = 8, 150   # a cloud's points (a swarm is 150 particles at most)
STARTERS = ("ring", "disc", "sphere", "spiral", "star")


def pull(d, v, w, dt):
    """THE RULE: the new speed along one axis"""
    return (v - w * w * d * dt) / (1 + 2 * w * dt + w * w * dt * dt)


def at_curve(curve, u, default):
    """a layer's number at u of its life: a number, or keys [[t, v], ...] / [[t, v, envelope], ...] read straight
    between them (the runtime's numAt), `default` when there is none"""
    if isinstance(curve, bool) or curve is None:
        return default
    if isinstance(curve, (int, float)):
        return float(curve)
    try:
        keys = [(float(k[0]), float(k[1])) for k in curve]
    except (TypeError, ValueError, IndexError):
        return 0.0
    if not keys:
        return default
    if u <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if u <= t1:
            return v0 + (v1 - v0) * ((u - t0) / (t1 - t0) if t1 > t0 else 1.0)
    return keys[-1][1]


def unit(pts):
    """the points about their own middle, the farthest 1 from it"""
    n = len(pts)
    mid = [sum(p[k] for p in pts) / n for k in range(3)]
    far = max(math.sqrt(sum((p[k] - mid[k]) ** 2 for k in range(3))) for p in pts)
    if far <= 1e-9:
        raise ValueError("every point is in one place")
    return [[round((p[k] - mid[k]) / far, 4) for k in range(3)] for p in pts]


def starter(kind, count, seed):
    out = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(count):
        u = (i + 0.5) / count
        if kind == "ring":
            a = 2 * math.pi * i / count
            out.append([math.cos(a), math.sin(a), 0.0])
        elif kind == "disc":
            r, a = math.sqrt(u), golden * i
            out.append([r * math.cos(a), r * math.sin(a), 0.0])
        elif kind == "sphere":
            y = 1 - 2 * u
            r, a = math.sqrt(max(0.0, 1 - y * y)), golden * i
            out.append([r * math.cos(a), y, r * math.sin(a)])
        elif kind == "spiral":
            a = 2 * math.pi * 2.5 * u
            out.append([u * math.cos(a), u * math.sin(a), 0.0])
        else:  # a five-pointed star's outline
            a = 2 * math.pi * i / count + math.pi / 2
            f = (a - math.pi / 2) / (2 * math.pi / 5)
            f = abs(f - math.floor(f) - 0.5) * 2  # 1 at a tip, 0 in a notch
            r = 0.42 + 0.58 * f
            out.append([r * math.cos(a), r * math.sin(a), 0.0])
    return unit(out)


def from_picture(path, count, seed):
    """`count` points on a picture's brightest, most opaque pixels, spread evenly: the best of several random picks
    is taken for each point (the one farthest from the points already there), so the shape is covered, not clumped"""
    import numpy as np
    from PIL import Image

    img = Image.open(path).convert("RGBA")
    img.thumbnail((160, 160))
    a = np.asarray(img, dtype=float) / 255
    w = a[..., :3].max(-1) * a[..., 3]
    if a[..., 3].min() < 0.5:  # a figure on a clear ground: what is opaque is the figure, whatever its colour (black ink too)
        w = a[..., 3]
    elif float(np.median(w)) > 0.5:  # an opaque picture on a light ground: the DARK is the figure
        w = 1 - w
    w = np.where(w >= 0.5 * float(w.max()), w, 0.0) if float(w.max()) > 0 else w
    ys, xs = np.nonzero(w)
    if len(xs) < count:
        raise ValueError(f"the picture has {len(xs)} bright pixels and {count} points were asked: a larger or bolder picture, or a smaller --count")
    rng = np.random.default_rng(int(seed))
    cand = np.stack([xs, ys], -1).astype(float)
    prob = w[ys, xs] / w[ys, xs].sum()
    chosen = [cand[int(rng.choice(len(cand), p=prob))]]
    for _ in range(count - 1):
        picks = cand[rng.choice(len(cand), size=24, p=prob)]
        dist = np.min(((picks[:, None, :] - np.array(chosen)[None, :, :]) ** 2).sum(-1), axis=1)
        chosen.append(picks[int(np.argmax(dist))])
    return unit([[float(x), float(-y), 0.0] for x, y in chosen])


def checked(data):
    """a cloud file's content -> its points (ValueError in words)"""
    if not isinstance(data, dict) or not isinstance(data.get("points"), list):
        raise ValueError('a cloud file is { "points": [[x, y, z], ...] }')
    for key in data:
        if key not in ("about", "points", "from"):
            raise ValueError(f"a cloud file does not read {key}")
    pts = data["points"]
    if not LEAST <= len(pts) <= MOST:
        raise ValueError(f"a cloud is {LEAST} to {MOST} points ({len(pts)} here)")
    for p in pts:
        if not (isinstance(p, list) and len(p) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in p)):
            raise ValueError("every point is [x, y, z], three numbers")
    return [[float(x) for x in p] for p in pts]


def check(pts):
    """[{name, ok, value, limit, fix}] of a cloud's points"""
    n = len(pts)
    far = max(math.sqrt(sum(x * x for x in p)) for p in pts)
    mid = math.sqrt(sum((sum(p[k] for p in pts) / n) ** 2 for k in range(3)))
    near = sorted(min(math.dist(p, q) for j, q in enumerate(pts) if j != i) for i, p in enumerate(pts))
    usual = near[n // 2]
    twins = sum(1 for d in near if d < 1e-3)
    ext = sorted(max(p[k] for p in pts) - min(p[k] for p in pts) for k in range(3))
    return [
        {"name": "unit size", "ok": 0.9 <= far <= 1.001 and mid <= 0.35, "value": f"the farthest point {far:.2f} from the middle, the middle {mid:.2f} off its points' own",
         "limit": "the farthest 0.9 to 1 away, the points' middle within 0.35 of the origin", "fix": "run the command on it (--picture or --new write it at unit size)"},
        {"name": "a shape, not a clump", "ok": ext[2] >= 0.8 and ext[1] >= 0.15, "value": f"{ext[2]:.2f} long, {ext[1]:.2f} wide", "limit": "at least 0.8 long and 0.15 wide",
         "fix": "points spread over the figure"},
        {"name": "no two particles on one point", "ok": twins == 0, "value": f"{twins} point(s) on top of another", "limit": "none", "fix": "take the doubled points out (from a picture: a smaller --count, or another --seed)"},
        {"name": "the points cover the shape evenly", "ok": near[-1] <= 6 * max(usual, 1e-6), "value": f"the loneliest point {near[-1]:.3f} from its nearest, the usual {usual:.3f}",
         "limit": "at most 6 times the usual", "fix": "more --count, or take the stray point out"},
    ]


def gather(pts, w, size=1.0, dt=1 / 60, seed=1, spread=3.0, limit=20.0):
    """a made swarm flown onto the cloud by THE RULE: every particle starts still, scattered `spread` cloud sizes
    round the middle -> the seconds until every one is within 0.02 of the cloud's size of its point (None: never)"""
    import random

    rng = random.Random(seed)
    pos = [[rng.uniform(-spread, spread) * size for _ in range(3)] for _ in pts]
    vel = [[0.0, 0.0, 0.0] for _ in pts]
    t = 0.0
    while t < limit:
        worst = 0.0
        for i, p in enumerate(pts):
            for k in range(3):
                vel[i][k] = pull(pos[i][k] - p[k] * size, vel[i][k], w, dt)
                pos[i][k] += vel[i][k] * dt
            worst = max(worst, math.dist(pos[i], [x * size for x in p]))
        t += dt
        if worst <= 0.02 * size:
            return t
    return None


def look(pts, path):
    from PIL import Image, ImageDraw

    size = 360
    img = Image.new("RGB", (size * 2 + 30, size + 40), (16, 18, 24))
    pen = ImageDraw.Draw(img)
    for col, (name, ia, ib) in enumerate((("from the front (x, y)", 0, 1), ("from above (x, z)", 0, 2))):
        ox = 10 + col * (size + 10)
        pen.rectangle([ox, 30, ox + size, 30 + size], outline=(70, 74, 86))
        pen.text((ox + 4, 8), name, fill=(200, 204, 214))
        for i, p in enumerate(pts):
            x, y = ox + (p[ia] * 0.46 + 0.5) * size, 30 + (0.5 - p[ib] * 0.46) * size
            c = int(120 + 135 * i / max(len(pts) - 1, 1))  # (the first particle's point dim, the last bright)
            pen.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(c, int(c * 0.86), int(c * 0.5)))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path)


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


def main(argv):
    usage = "lune run kit vfx points <name> [--new ring|disc|sphere|spiral|star] [--picture <png>] [--count 60] [--pull 8]"
    o = {"--new": "", "--picture": "", "--count": "60", "--seed": "1", "--pull": "8", "--out-dir": OUT, "--look-dir": LOOK}
    names, i = [], 0
    while i < len(argv):
        if argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"points: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"points: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", names[0]):
        return out("fail", "points: name ONE cloud, in lowercase letters, digits and _ (the game finds it by its exact letters)", usage)
    name = names[0]
    try:
        count, seed, w = int(o["--count"]), int(o["--seed"]), float(o["--pull"])
    except ValueError:
        return out("fail", f"points {name}: --count and --seed are whole numbers, --pull a number", usage)
    if not (LEAST <= count <= MOST) or not (0.5 <= w <= 60):
        return out("fail", f"points {name}: --count is {LEAST} to {MOST}, --pull 0.5 to 60", usage)
    path = os.path.join(o["--out-dir"], f"{name}.json")
    made = None
    if o["--new"] and o["--picture"]:
        return out("fail", f"points {name}: --new or --picture, not both", usage)
    if o["--new"] or o["--picture"]:
        if os.path.exists(path):
            return out("fail", f"points {name}: {path.replace(os.sep, '/')} is already there (a cloud is not overwritten)", f"another name, or edit it, then: lune run kit vfx points {name}")
        try:
            if o["--new"]:
                if o["--new"] not in STARTERS:
                    return out("fail", f"points {name}: --new is one of {', '.join(STARTERS)}", usage)
                made = {"about": f"a {o['--new']} of {count} points (kit vfx points --new)", "from": o["--new"], "points": starter(o["--new"], count, seed)}
            else:
                made = {"about": f"{count} points on a picture's bright pixels (kit vfx points --picture)", "from": os.path.basename(o["--picture"]),
                        "points": from_picture(o["--picture"], count, seed)}
        except (OSError, ValueError) as e:
            return out("fail", f"points {name}: {e}", usage)
    try:
        if made is None:
            with open(path, encoding="utf-8") as fh:
                made_now = json.load(fh)
        pts = checked(made if made is not None else made_now)
    except OSError:
        return out("fail", f"points {name}: no cloud {path.replace(os.sep, '/')}", f"lune run kit vfx points {name} --new ring   (or --picture <png>)")
    except ValueError as e:
        return out("fail", f"points {name}: {e}", "kit/vfx/points.py (its head) says what a cloud file holds")
    rows = check(pts)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return out("fail", f"points {name}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    if made is not None:
        os.makedirs(o["--out-dir"], exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(made, fh, separators=(",", ":"))
            fh.write("\n")
    whole = gather(pts, w)
    picture = os.path.join(o["--look-dir"], f"{name}.png")
    look(pts, picture)
    return out("pass", f"points {name}: {len(pts)} points - on a swarm layer of {len(pts)} particles or more (fewer draw part of it): "
               f'"cloud": {{"name": "{name}", "size": 6, "pull": {w:g}}}; scattered particles are on their points after {whole:.2f} s at that pull',
               f"OPEN {picture.replace(os.sep, '/')}: do the points say THIS effect's shape?", checks=rows, look=picture.replace(os.sep, "/"),
               cloud=path.replace(os.sep, "/"), gathered=round(whole, 3))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
