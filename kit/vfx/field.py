#!/usr/bin/env python3
"""AN AUTHORED VECTOR FIELD (the owner's methods list: Vector field-driven effects; the VFX methods audit, stage 11).

The swarm layer's only field was `curl`: generated noise, the same swirl everywhere. A vector field in a studio is
AUTHORED: someone says where the air goes - a wind, a vortex standing HERE turning about THIS axis, a point that
pushes out or pulls in, a PATH drawn through space that the particles stream along. This is that, as a small file:

    assets/effects/fields/<name>.json   (in the game: VfxPresets.fields.<name>)
    { "schema": 1, "bounds": 10,
      "elements": [ { "kind": "wind",   "dir": [1, 0, 0], "speed": 4 },
                    { "kind": "vortex", "at": [0, 0, 0], "axis": [0, 1, 0], "radius": 4, "speed": 12, "pull": 3, "lift": 2 },
                    { "kind": "point",  "at": [0, 2, 0], "radius": 3, "speed": -8 },
                    { "kind": "path",   "points": [[-6, 0, 0], [0, 4, 0], [6, 0, 0]], "radius": 2, "speed": 10, "pull": 6 } ] }

Places are studs from the swarm layer's `point`, along the WORLD's axes (a field does not turn with the effect).
A swarm layer follows it with `"field": { "name": "<name>", "follow": 6, "gain": 1 }`: each particle's velocity is
drawn toward the field's velocity where it is (`follow` a second: high = it rides the field, low = it drifts into
it); `gain` scales the field. Curl, attract, gravity and drag still add to it.

    lune run kit vfx field <name> --new vortex|wind|fountain|path      a starter to edit
    lune run kit vfx field <name>                                      check it, draw build/vfx/field/<name>.png

THE RULE (`at`; the game's `fieldAt` in src/kit/VfxStage.luau and the player's in kit/vfx/player/player.js are the
same arithmetic, held to it by kit/selftest/vfx/field/run.py parity) - the velocity at a place is the SUM of:
- wind:   its direction (made one long) x speed, everywhere;
- vortex: round the line through `at` along `axis`, with d the distance from that line and f = (d / radius) x
          e^(1 - d / radius) (0 on the line, 1 at `radius`, fading beyond): turning x speed x f, inward x pull x f,
          along the axis x lift x e^-((d / 2 radius)^2);
- point:  away from `at` x speed x e^-((d / radius)^2) x (1 - e^-((d / (radius / 4))^2)): strongest about a third of
          `radius` out, and dying to nothing AT the point (a speck pulled in comes to rest there; it does not shoot
          through and back). A negative speed pulls in;
- path:   with c the nearest place on the drawn line and w = e^-((d / radius)^2): along the line there x speed x w,
          and toward the line (c - place) x (pull / radius) x w.

What the check looks for (a field that fails one is not accepted): `elements` (each kind's own keys, numbers in
range), `moves` (the air moves somewhere inside the bounds), `bounded` (no speed over 400 studs a second),
`carries` (specks let go inside the bounds, and beside each element, GET somewhere: a field that only shivers
carries nothing).

NOT a simulation: nothing in the field is pushed back by the particles or by the world, and it does not change over
time (drive `gain` or the swarm's own keys for that). Not a baked 3D grid (.fga): Roblox has nowhere to read one.
"""
import json
import math
import os
import re
import sys

OUT = os.path.join("assets", "effects", "fields")
LOOK = os.path.join("build", "vfx", "field")
KEYS = {"wind": {"dir", "speed"}, "vortex": {"at", "axis", "radius", "speed", "pull", "lift"}, "point": {"at", "radius", "speed"},
        "path": {"points", "radius", "speed", "pull"}}
FAST = 400.0
STARTERS = {
    "vortex": {"schema": 1, "bounds": 8, "elements": [{"kind": "vortex", "at": [0, 0, 0], "axis": [0, 1, 0], "radius": 4, "speed": 12, "pull": 3, "lift": 2}]},
    "wind": {"schema": 1, "bounds": 8, "elements": [{"kind": "wind", "dir": [1, 0.2, 0], "speed": 6}]},
    "fountain": {"schema": 1, "bounds": 8, "elements": [{"kind": "vortex", "at": [0, 0, 0], "axis": [0, 1, 0], "radius": 3, "speed": 2, "pull": 5, "lift": 14},
                                                         {"kind": "point", "at": [0, 7, 0], "radius": 4, "speed": 9}]},
    "path": {"schema": 1, "bounds": 8, "elements": [{"kind": "path", "points": [[-6, 0, 0], [-2, 4, 2], [2, 4, -2], [6, 0, 0]], "radius": 2.5, "speed": 10, "pull": 8}]},
}


def at(elements, x, y, z):
    """the field's velocity at a place -> [vx, vy, vz]"""
    vx = 0.0
    vy = 0.0
    vz = 0.0
    for e in elements:
        kind = e["kind"]
        if kind == "wind":
            d = e["dir"]
            n = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
            if n > 1e-9:
                s = e["speed"] / n
                vx = vx + d[0] * s
                vy = vy + d[1] * s
                vz = vz + d[2] * s
        elif kind == "vortex":
            a = e["at"]
            ax = e.get("axis")
            if not (isinstance(ax, list) and len(ax) == 3):
                ax = [0, 1, 0]
            n = math.sqrt(ax[0] * ax[0] + ax[1] * ax[1] + ax[2] * ax[2])
            rad = e["radius"]
            if n > 1e-9 and rad > 1e-9:
                nx = ax[0] / n
                ny = ax[1] / n
                nz = ax[2] / n
                rx = x - a[0]
                ry = y - a[1]
                rz = z - a[2]
                h = rx * nx + ry * ny + rz * nz
                px = rx - h * nx
                py = ry - h * ny
                pz = rz - h * nz
                d = math.sqrt(px * px + py * py + pz * pz)
                lift = (e.get("lift") or 0) * math.exp(-((d / (2 * rad)) * (d / (2 * rad))))
                vx = vx + nx * lift
                vy = vy + ny * lift
                vz = vz + nz * lift
                if d > 1e-9:
                    f = (d / rad) * math.exp(1 - d / rad)
                    ux = px / d
                    uy = py / d
                    uz = pz / d
                    turn = e["speed"] * f
                    pull = (e.get("pull") or 0) * f
                    vx = vx + (ny * uz - nz * uy) * turn - ux * pull
                    vy = vy + (nz * ux - nx * uz) * turn - uy * pull
                    vz = vz + (nx * uy - ny * ux) * turn - uz * pull
        elif kind == "point":
            a = e["at"]
            rx = x - a[0]
            ry = y - a[1]
            rz = z - a[2]
            d = math.sqrt(rx * rx + ry * ry + rz * rz)
            rad = e["radius"]
            if d > 1e-9 and rad > 1e-9:
                core = d / (0.25 * rad)
                s = e["speed"] * math.exp(-((d / rad) * (d / rad))) * (1 - math.exp(-(core * core))) / d
                vx = vx + rx * s
                vy = vy + ry * s
                vz = vz + rz * s
        elif kind == "path":
            pts = e["points"]
            best = -1.0
            cx = 0.0
            cy = 0.0
            cz = 0.0
            tx = 0.0
            ty = 0.0
            tz = 0.0
            for i in range(len(pts) - 1):
                p0 = pts[i]
                p1 = pts[i + 1]
                sx = p1[0] - p0[0]
                sy = p1[1] - p0[1]
                sz = p1[2] - p0[2]
                ln = math.sqrt(sx * sx + sy * sy + sz * sz)
                if ln > 1e-9:
                    u = ((x - p0[0]) * sx + (y - p0[1]) * sy + (z - p0[2]) * sz) / (ln * ln)
                    u = max(0, min(1, u))
                    qx = p0[0] + sx * u
                    qy = p0[1] + sy * u
                    qz = p0[2] + sz * u
                    dd = (x - qx) * (x - qx) + (y - qy) * (y - qy) + (z - qz) * (z - qz)
                    if best < 0 or dd < best:
                        best = dd
                        cx = qx
                        cy = qy
                        cz = qz
                        tx = sx / ln
                        ty = sy / ln
                        tz = sz / ln
            rad = e["radius"]
            if best >= 0 and rad > 1e-9:
                w = math.exp(-(best / (rad * rad)))
                along = e["speed"] * w
                pull = (e.get("pull") or 0) / rad * w
                vx = vx + tx * along + (cx - x) * pull
                vy = vy + ty * along + (cy - y) * pull
                vz = vz + tz * along + (cz - z) * pull
    return [vx, vy, vz]


def checked(field):
    """a field file as the rule reads it; raises ValueError saying what is wrong"""
    def num(v, lo, hi):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and lo <= v <= hi

    def vec(v):
        return isinstance(v, list) and len(v) == 3 and all(num(c, -10000, 10000) for c in v)

    if not isinstance(field, dict) or not isinstance(field.get("elements"), list) or not field["elements"]:
        raise ValueError('a field is { "schema": 1, "bounds": 10, "elements": [ ... ] } with one element or more')
    stray = sorted(set(field) - {"schema", "bounds", "elements"})
    if stray:
        raise ValueError(f"a field does not read {', '.join(stray)} at its top (it reads schema, bounds, elements)")
    if field.get("schema", 1) != 1:
        raise ValueError("schema is 1")
    if len(field["elements"]) > 16:
        raise ValueError("a field has 16 elements at most (every particle asks every element every frame)")
    if not num(field.get("bounds", 10), 1, 500):
        raise ValueError("bounds is the half-size of the space the field is made for, 1 to 500 studs")
    for i, e in enumerate(field["elements"]):
        where = f"element {i + 1}"
        if not isinstance(e, dict) or e.get("kind") not in KEYS:
            raise ValueError(f"{where}: kind is wind, vortex, point or path")
        kind = e["kind"]
        unread = sorted(set(e) - KEYS[kind] - {"kind"})
        if unread:
            raise ValueError(f"{where} (a {kind}) does not read {', '.join(unread)} (it reads {', '.join(sorted(KEYS[kind]))})")
        if not num(e.get("speed"), -FAST, FAST):
            raise ValueError(f"{where}: speed is studs a second, {-FAST:g} to {FAST:g}")
        if kind == "wind":
            if not vec(e.get("dir")) or sum(c * c for c in e["dir"]) < 1e-12:
                raise ValueError(f"{where}: dir is [x, y, z], not all 0")
        else:
            if not num(e.get("radius"), 0.05, 1000):
                raise ValueError(f"{where}: radius is 0.05 to 1000 studs")
        if kind in ("vortex", "point") and not vec(e.get("at")):
            raise ValueError(f"{where}: at is [x, y, z], studs from the layer's point")
        if kind == "vortex":
            if "axis" in e and (not vec(e["axis"]) or sum(c * c for c in e["axis"]) < 1e-12):
                raise ValueError(f"{where}: axis is [x, y, z], not all 0")
            for key in ("pull", "lift"):
                if key in e and not num(e[key], -FAST, FAST):
                    raise ValueError(f"{where}: {key} is studs a second, {-FAST:g} to {FAST:g}")
        if kind == "path":
            pts = e.get("points")
            if not (isinstance(pts, list) and 2 <= len(pts) <= 32 and all(vec(q) for q in pts)):
                raise ValueError(f"{where}: points is 2 to 32 places [x, y, z] the flow runs through, in order")
            if all(math.dist(pts[k], pts[k + 1]) < 1e-6 for k in range(len(pts) - 1)):
                raise ValueError(f"{where}: its points are all one place: a path goes somewhere")
            if "pull" in e and not num(e["pull"], 0, FAST):
                raise ValueError(f"{where}: pull is 0 to {FAST:g} (how hard the flow draws specks onto the line)")
    return field


def near(field):
    """places beside each element that lie inside the bounds: a small element in a big space is looked at where it is"""
    b, out = field.get("bounds", 10), []
    for e in field["elements"]:
        r = e.get("radius", 1)
        spots = []
        if "at" in e:  # six specks round it, where a point is strongest and a vortex well under way
            for axis in range(3):
                for side in (-0.4, 0.4):
                    q = list(e["at"])
                    q[axis] += r * side
                    spots.append(q)
        pts = e.get("points") or []
        spots += [[q[0], q[1] + r * 0.3, q[2]] for q in pts]
        for a, c in zip(pts, pts[1:]):  # and three along every stretch of a path, just off its line
            spots += [[a[0] + (c[0] - a[0]) * u, a[1] + (c[1] - a[1]) * u + r * 0.3, a[2] + (c[2] - a[2]) * u] for u in (0.25, 0.5, 0.75)]
        out += [p for p in spots if all(abs(c) <= b for c in p)]
    return out


def seeds(bounds, n=64, seed=7):
    """n places inside the bounds, the same every run (a small generator of our own: no library's stream)"""
    out, s = [], seed
    for _ in range(n):
        p = []
        for _ in range(3):
            s = (s * 1103515245 + 12345) % 2147483648
            p.append((s / 2147483648 * 2 - 1) * bounds * 0.8)
        out.append(p)
    return out


def trails(field, seconds=3.0, fps=60):
    """64 specks let go in the bounds, and one beside each element, each riding the field -> [[place, ...], ...]"""
    els, dt = field["elements"], 1.0 / fps
    out = []
    for p in seeds(field.get("bounds", 10)) + near(field):
        trail = [list(p)]
        for _ in range(int(seconds * fps)):
            v = at(els, p[0], p[1], p[2])
            p = [p[0] + v[0] * dt, p[1] + v[1] * dt, p[2] + v[2] * dt]
            trail.append(p)
        out.append(trail)
    return out


def check(field, flown=None):
    rows = []

    def add(name, ok, value, limit, fix):
        rows.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": fix})

    els, b = field["elements"], field.get("bounds", 10)
    n = 7
    speeds = []
    for i in range(n):
        for j in range(n):
            for k in range(n):
                v = at(els, (i / (n - 1) * 2 - 1) * b, (j / (n - 1) * 2 - 1) * b, (k / (n - 1) * 2 - 1) * b)
                speeds.append(math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]))
    for p in seeds(b) + near(field):  # (a coarse grid alone misses a thin path or a small vortex in a big space)
        v = at(els, p[0], p[1], p[2])
        speeds.append(math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]))
    speeds.sort()
    add("moves", speeds[-1] > 0.2, round(speeds[-1], 3), "somewhere inside the bounds the air moves at over 0.2 studs a second",
        "the air stands still inside the bounds: the elements sit outside them (at, points, bounds) or their speeds are next to 0")
    add("bounded", speeds[-1] <= FAST, round(speeds[-1], 1), f"no speed over {FAST:g} studs a second", "elements stacked on one place add up: lower their speeds")
    flown = flown if flown is not None else trails(field)
    # how far a speck GETS from where it was let go (a speck that shivers on the spot has a long path and gets nowhere)
    reach = sorted(max(math.dist(t[0], q) for q in t) for t in flown)
    gone = sum(1 for r in reach if r > 1.0)
    add("carries", gone >= 4, gone, "4 specks or more get over a stud from where they were let go in 3 s",
        "the field carries nothing: its elements do not reach where the specks are (radius, at, bounds)")
    return rows


def look(field, flown, path, size=420):
    """the specks' trails from above (x, z) and from the side (x, y), brighter where they are faster"""
    from PIL import Image, ImageDraw
    b = field.get("bounds", 10) * 1.3
    img = Image.new("RGB", (size * 2 + 30, size + 40), (16, 18, 24))
    pen = ImageDraw.Draw(img)
    for col, (name, ia, ib, flip) in enumerate((("from above (x, z)", 0, 2, False), ("from the side (x, y)", 0, 1, True))):
        ox = 10 + col * (size + 10)
        pen.rectangle([ox, 30, ox + size, 30 + size], outline=(70, 74, 86))
        pen.text((ox + 4, 8), name, fill=(200, 204, 214))

        def px(p, ox=ox, ia=ia, ib=ib, flip=flip):
            u = (p[ia] / b + 1) / 2
            v = (p[ib] / b + 1) / 2
            return ox + u * size, 30 + ((1 - v) if flip else v) * size

        for t in flown:
            for k in range(0, len(t) - 3, 3):
                sp = math.dist(t[k], t[k + 3]) * 20
                c = int(max(60, min(255, 60 + sp * 14)))
                a0, a1 = px(t[k]), px(t[k + 3])
                if all(ox <= q[0] <= ox + size and 30 <= q[1] <= 30 + size for q in (a0, a1)):
                    pen.line([a0, a1], fill=(c, int(c * 0.85), int(c * 0.55)))
            s = px(t[0])
            if ox <= s[0] <= ox + size and 30 <= s[1] <= 30 + size:
                pen.ellipse([s[0] - 2, s[1] - 2, s[0] + 2, s[1] + 2], fill=(110, 190, 255))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path)


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


def main(argv):
    usage = "lune run kit vfx field <name> [--new vortex|wind|fountain|path]"
    o = {"--new": "", "--out-dir": OUT, "--look-dir": LOOK}
    names, i = [], 0
    while i < len(argv):
        if argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"field: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"field: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", names[0]):  # (the validator's and the gate's own rule)
        return out("fail", "field: name ONE field, in lowercase letters, digits and _ (the game finds it by its exact letters)", usage)
    name = names[0]
    path = os.path.join(o["--out-dir"], f"{name}.json")
    if o["--new"]:
        if o["--new"] not in STARTERS:
            return out("fail", f"field: --new is one of {', '.join(sorted(STARTERS))}", usage)
        if os.path.exists(path):
            return out("fail", f"field {name}: {path.replace(os.sep, '/')} is already there (a starter does not overwrite a field)", f"edit it, then: lune run kit vfx field {name}")
        os.makedirs(o["--out-dir"], exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(STARTERS[o["--new"]], fh, indent=1)
            fh.write("\n")
    try:
        with open(path, encoding="utf-8") as fh:
            field = checked(json.load(fh))
    except OSError:
        return out("fail", f"field {name}: no field {path.replace(os.sep, '/')}", f"lune run kit vfx field {name} --new vortex")
    except ValueError as e:
        return out("fail", f"field {name}: {e}", "kit/vfx/field.py (its head) says what a field file holds")
    flown = trails(field)
    rows = check(field, flown)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        # (the summary leads with what is WRONG in words - "the air stands still inside the bounds" - then the numbers)
        return out("fail", f"field {name}: {failed[0]['fix'].split(':')[0]} - " + "; ".join(f"{c['name']} = {c['value']} (needs {c['limit']})" for c in failed),
                   failed[0]["fix"], checks=rows)
    picture = os.path.join(o["--look-dir"], f"{name}.png")
    look(field, flown, picture)
    kinds = ", ".join(e["kind"] for e in field["elements"])
    return out("pass", f"field {name}: {len(field['elements'])} element(s) ({kinds}) in bounds of {field.get('bounds', 10):g} studs - on a swarm layer: "
               f'"field": {{"name": "{name}"}}',
               f"OPEN {picture.replace(os.sep, '/')}: do the specks go where THIS effect's air goes?", checks=rows, look=picture.replace(os.sep, "/"),
               field=path.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
