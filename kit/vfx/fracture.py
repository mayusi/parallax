"""fracture.py - AN OBJECT BROKEN INTO ITS OWN PIECES: a slab (a ground plate, a pane, a sheet of ice) cut into the
pieces it breaks into, each with the push the blow gives it.

    lune run kit vfx fracture <name> --size w,d[,h] [--shape slab|disc] [--pieces 14] [--impact x,z] [--focus 0.6]
                              [--speed 30] [--lift 0.6] [--wave 60] [--seed 3]

Why: the kit's `debris` layer throws generic rock chunks from one point. Nothing BREAKS: a ground slab that heaves, a
pane that shatters, are the object's own surface coming apart - pieces that fit together until the blow, small and
fast where it lands, large and slow at the rim. This tool makes that plan; the `debris` layer flies it
(`"pieces": "<name>"`: every piece starts where it sat in the slab and leaves when the blow's wave reaches it).

  --size     the slab: width and depth in studs (and thickness, default a tenth of the smaller side)
  --shape    slab = that rectangle; disc = a round plate of that width
  --pieces   how many it breaks into (4-64)
  --impact   where the blow lands, in the slab's own plane from its centre (default: the centre)
  --focus    0 = pieces of even size; towards 1 = small pieces round the impact, large ones at the rim
  --speed    studs a second of the piece nearest the impact; a piece further out is slower
  --lift     how far the push is turned upward (0 = flat along the ground, 1 = straight up)
  --wave     studs a second the break travels outward: a piece leaves after its distance / wave

The cut is a Voronoi cut clipped to the slab: every piece is CONVEX and the pieces tile the slab exactly. Its own
checks (a plan that fails one is not written): count (as many pieces as asked), tiles (the pieces' areas add up to
the slab's, to a thousandth), convex, slivers (no piece under a twentieth of the mean area, none thinner than a
fifth of its length), focus (with a focus, the pieces near the impact are smaller than the far ones), outward (every
push points away from the impact and up).
Writes assets/effects/fractures/<name>.json and the LOOK picture build/vfx/fracture/<name>.png: the cut seen from
above with the impact marked (left), and the pieces a quarter of a second after the blow by the debris layer's own
flight (right). OPEN it.
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.join("assets", "effects", "fractures")
LOOK = os.path.join("build", "vfx", "fracture")
TILES = 0.001      # the pieces' areas against the slab's, as a share
SLIVER = 0.05      # a piece under this share of the mean area is a sliver
THIN = 0.2         # ... and so is one whose width is under this share of its length
MEET_WIDE = 0.05   # studs: no piece narrower (kit/vfx/settle.py SKIN is 0.02: pieces that meet are parted only when they
                   # lie deeper in each other than that - a piece thinner than it could lie wholly inside another, unparted,
                   # and a piece of no width - three points on a line - is 'under' every place on its line: a review leftover)
DEFAULTS = {"shape": "slab", "pieces": 14, "impact": [0.0, 0.0], "focus": 0.6, "speed": 30.0, "lift": 0.6, "wave": 60.0, "seed": 3}


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status in ("pass", "warn") else 1


def area(poly):
    """a polygon's signed area (positive when its points run counter-clockwise, x to the right and z up the page)"""
    p = np.asarray(poly, dtype=np.float64)
    if len(p) < 3:
        return 0.0
    x, z = p[:, 0], p[:, 1]
    return float(0.5 * np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z))


def centroid(poly):
    p = np.asarray(poly, dtype=np.float64)
    x, z = p[:, 0], p[:, 1]
    cross = x * np.roll(z, -1) - np.roll(x, -1) * z
    a = 0.5 * np.sum(cross)
    if abs(a) < 1e-12:
        return [float(x.mean()), float(z.mean())]
    return [float(np.sum((x + np.roll(x, -1)) * cross) / (6 * a)), float(np.sum((z + np.roll(z, -1)) * cross) / (6 * a))]


def clip(poly, point, normal):
    """the part of a convex polygon on the side of the line through `point` that `normal` points AWAY from
    (Sutherland-Hodgman, one edge)"""
    out_pts = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        da = (a[0] - point[0]) * normal[0] + (a[1] - point[1]) * normal[1]
        db = (b[0] - point[0]) * normal[0] + (b[1] - point[1]) * normal[1]
        if da <= 0:
            out_pts.append(a)
        if (da < 0 < db) or (db < 0 < da):
            t = da / (da - db)
            out_pts.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
    return out_pts


def outline(shape, w, d):
    """the slab's own outline, counter-clockwise, centred on its middle"""
    if shape == "disc":
        r = w / 2.0
        return [[r * math.cos(2 * math.pi * k / 40), r * math.sin(2 * math.pi * k / 40)] for k in range(40)]
    return [[-w / 2.0, -d / 2.0], [w / 2.0, -d / 2.0], [w / 2.0, d / 2.0], [-w / 2.0, d / 2.0]]


def inside(poly, p):
    return all((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9 for a, b in zip(poly, poly[1:] + poly[:1]))


def seeds(o, rim, rng):
    """where the pieces' middles lie: drawn round the impact, closer together the higher the focus, and spread out
    (a new point too near another is drawn again) so that no two pieces are slivers of each other"""
    w, d = o["size"][0], o["size"][1]
    reach = math.hypot(w, d)
    ix, iz = o["impact"]
    count = int(o["pieces"])
    apart = 0.45 * math.sqrt(abs(area(rim)) / count)
    pts, tries = [], 0
    while len(pts) < count and tries < 20000:
        tries += 1
        if rng.random() < 0.25:                       # a quarter are spread over the whole slab: its far corners break too
            p = [rng.uniform(-w / 2, w / 2), rng.uniform(-d / 2, d / 2)]
        else:
            r = reach * rng.random() ** (1.0 + 2.5 * o["focus"])
            a = rng.uniform(0, 2 * math.pi)
            p = [ix + r * math.cos(a), iz + r * math.sin(a)]
        if not inside(rim, p):
            continue
        # nearer the impact the pieces may sit closer (that is the focus); a floor keeps them from touching
        near = math.hypot(p[0] - ix, p[1] - iz) / reach
        gap = apart * (1 - 0.75 * o["focus"] * math.exp(-near * 4)) * (0.6 if tries > 6000 else 1.0)
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= gap for q in pts):
            pts.append(p)
    return pts


def cut(rim, pts):
    """the slab cut into one convex piece a seed: each seed keeps what is nearer to it than to any other"""
    pieces = []
    for i, p in enumerate(pts):
        poly = [list(v) for v in rim]
        for j, q in enumerate(pts):
            if i == j or len(poly) < 3:
                continue
            mid = [(p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0]
            poly = clip(poly, mid, [q[0] - p[0], q[1] - p[1]])
        pieces.append(poly)
    return pieces


def hull(points):
    """the convex hull of 2D points, counter-clockwise (Andrew's chain); fewer than three = a point or a line"""
    pts = sorted(set((float(q[0]), float(q[1])) for q in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 1e-12:
            lower.pop()
        lower.append(q)
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 1e-12:
            upper.pop()
        upper.append(q)
    return lower[:-1] + upper[:-1]


def measure(poly):
    """(length, width) of a piece: its longest extent in any direction, and its NARROWEST - exactly: for each edge of
    its hull, the farthest point from that edge's line, the least of those (a splinter is long one way and thin the
    other, whichever way it lies; sampling 72 ways let a thin one between two of them pass: a review). Points on a
    line have no width"""
    p = np.asarray(poly, dtype=np.float64)
    spans = []
    for a in np.linspace(0, math.pi, 72, endpoint=False):
        along = p @ np.array([math.cos(a), math.sin(a)])
        spans.append(float(along.max() - along.min()))
    h = hull(poly)
    if len(h) < 3:
        return max(spans), 0.0
    narrow = math.inf
    for i in range(len(h)):
        a, b = h[i], h[(i + 1) % len(h)]
        ex, ez = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ez)
        if ln < 1e-12:
            continue
        far = max(abs((q[0] - a[0]) * ez - (q[1] - a[1]) * ex) / ln for q in h)
        narrow = min(narrow, far)
    return max(spans), (0.0 if narrow == math.inf else narrow)


def launch(o, centre, size_of, rng):
    """the push the blow gives a piece: away from the impact and up, slower the further out it sits; a spin that a
    smaller piece takes faster; and the moment the break reaches it"""
    w, d = o["size"][0], o["size"][1]
    reach = math.hypot(w, d) / 2.0
    dx, dz = centre[0] - o["impact"][0], centre[1] - o["impact"][1]
    dist = math.hypot(dx, dz)
    if dist < 1e-6:
        a = rng.uniform(0, 2 * math.pi)
        dx, dz, far = math.cos(a), math.sin(a), 0.0
    else:
        dx, dz, far = dx / dist, dz / dist, dist / max(reach, 1e-6)
    speed = o["speed"] * (0.3 + 0.7 * math.exp(-2.2 * far)) * rng.uniform(0.85, 1.15)
    lift = min(max(o["lift"], 0.0), 1.0) * (math.pi / 2)
    flat, up = math.cos(lift), math.sin(lift)
    vel = [speed * flat * dx, speed * max(up, 0.08), speed * flat * dz]
    turn = min(9.0, 0.35 * speed / max(size_of, 0.2))
    spin = [float(rng.uniform(-1, 1) * turn) for _ in range(3)]
    return [round(v, 4) for v in vel], [round(s, 4) for s in spin], round(dist / max(o["wave"], 1e-6), 4)


def plan(o):
    """the options -> the fracture plan (a table that goes to a file as it is)"""
    rng = np.random.default_rng(int(o["seed"]))
    w, d, h = o["size"]
    rim = outline(o["shape"], w, d)
    polys = cut(rim, seeds(o, rim, rng))
    pieces = []
    for poly in polys:
        if len(poly) < 3 or abs(area(poly)) < 1e-9:
            continue
        if area(poly) < 0:
            poly = poly[::-1]
        c = centroid(poly)
        ln, wd = measure(poly)
        vel, spin, delay = launch(o, c, ln, rng)
        pieces.append({"points": [[round(x - c[0], 4), round(z - c[1], 4)] for x, z in poly], "centre": [round(c[0], 4), round(c[1], 4)],
                       "area": round(area(poly), 5), "length": round(ln, 4), "width": round(wd, 4), "vel": vel, "spin": spin, "delay": delay})
    pieces.sort(key=lambda p: p["delay"])
    return {"schema": 1, "shape": o["shape"], "size": [w, d, h], "impact": [float(o["impact"][0]), float(o["impact"][1])],
            "area": round(abs(area(rim)), 5), "made": {k: o[k] for k in ("pieces", "focus", "speed", "lift", "wave", "seed")}, "pieces": pieces}


def check(p, o):
    checks = []

    def add(name, ok, value, limit, fix):
        checks.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": fix})

    pieces = p["pieces"]
    add("count", len(pieces) == int(o["pieces"]), len(pieces), f"{int(o['pieces'])} pieces", "fewer pieces, or another --seed: some seeds could not be placed apart")
    if not pieces:
        return checks
    total = sum(pc["area"] for pc in pieces)
    off = abs(total - p["area"]) / max(p["area"], 1e-9)
    add("tiles", off <= TILES, round(off, 5), f"the pieces' areas within {TILES} of the slab's", "the pieces do not make up the slab: a fault in the cut")

    def convex(pts):
        n = len(pts)
        return all((pts[(i + 1) % n][0] - pts[i][0]) * (pts[(i + 2) % n][1] - pts[(i + 1) % n][1])
                   - (pts[(i + 1) % n][1] - pts[i][1]) * (pts[(i + 2) % n][0] - pts[(i + 1) % n][0]) >= -1e-6 for i in range(n))

    add("convex", all(convex(pc["points"]) for pc in pieces), sum(1 for pc in pieces if not convex(pc["points"])), "0 pieces with a dent",
        "a piece with a dent cannot be built as one solid: a fault in the cut")
    mean = total / len(pieces)
    small = min(pc["area"] for pc in pieces) / mean
    short = min(p["size"][0], p["size"][1])  # (a plank's pieces are as wide as the plank: that is no splinter)
    thin = min(pc["width"] / max(min(pc["length"], short), 1e-9) for pc in pieces)
    add("slivers", small >= SLIVER and thin >= THIN, [round(small, 3), round(thin, 3)],
        f"the smallest piece >= {SLIVER} of the mean area, the thinnest >= {THIN} as wide as it is long", "a splinter reads as a fault, not a piece: another --seed, or fewer pieces")
    narrow = min(measure(pc["points"])[1] for pc in pieces)
    add("meets", narrow >= MEET_WIDE, round(narrow, 4), f"every piece {MEET_WIDE} studs wide or more",
        "a piece this thin cannot be met by another (it lies inside it unparted): a bigger slab, or fewer pieces")
    if o["focus"] >= 0.3 and len(pieces) >= 8:
        far = sorted(pieces, key=lambda pc: math.hypot(pc["centre"][0] - p["impact"][0], pc["centre"][1] - p["impact"][1]))
        half = len(far) // 2
        near_a, far_a = float(np.median([pc["area"] for pc in far[:half]])), float(np.median([pc["area"] for pc in far[half:]]))
        add("focus", near_a < far_a, [round(near_a, 3), round(far_a, 3)], "the pieces near the impact smaller than the far ones",
            "the blow does not read in the cut: a higher --focus, or another --seed")
    ok = True
    for pc in pieces:
        dx, dz = pc["centre"][0] - p["impact"][0], pc["centre"][1] - p["impact"][1]
        if math.hypot(dx, dz) > 1e-3 and pc["vel"][0] * dx + pc["vel"][2] * dz < -1e-6:
            ok = False
        if pc["vel"][1] <= 0:
            ok = False
    add("outward", ok, None, "every push points away from the impact, and up", "a piece pushed toward the blow: a fault in the launch")
    return checks


def fly(piece, t, gravity=120.0, floor=0.0, thick=0.0):
    """where a piece is `t` seconds after the blow, by the debris layer's own flight: it waits for the break to reach
    it, then rises and falls under gravity, and on the ground it loses half its speed and a quarter of its bounce.
    -> (x, y, z) of its middle. (A reading for the LOOK picture and the tests: the game and the player fly it.)"""
    x, z = piece["centre"]
    y = floor + thick / 2.0
    vx, vy, vz = piece["vel"]
    left = t - piece["delay"]
    if left <= 0:
        return x, y, z
    dt = 1.0 / 240.0
    while left > 1e-9:
        step = min(dt, left)
        vy -= gravity * step
        x, y, z = x + vx * step, y + vy * step, z + vz * step
        if y < floor + thick / 2.0:
            y = floor + thick / 2.0
            vx, vy, vz = vx * 0.5, -vy * 0.25, vz * 0.5
        left -= step
    return x, y, z


def look(p, path, tile=520):
    """the LOOK picture: the cut from above with the impact marked (left); the pieces 0.25 s after the blow (right)"""
    w, d, h = p["size"]
    span = max(w, d) * 1.9
    page = Image.new("RGB", (2 * tile + 18, tile + 34), (20, 20, 24))
    pen = ImageDraw.Draw(page)

    def to_px(x, z, ox):
        return (ox + tile / 2.0 + x / span * tile, 28 + tile / 2.0 - z / span * tile)

    last = max(pc["delay"] for pc in p["pieces"]) or 1.0
    for col, (title, when) in enumerate((("the cut (the blow marked; darker = leaves later)", 0.0), ("0.25 s after the blow, from above", 0.25))):
        ox = 6 + col * (tile + 6)
        pen.text((ox + 2, 6), title, fill=(225, 225, 225))
        for pc in p["pieces"]:
            x, y, z = fly(pc, when, thick=h)
            shade = int(215 - 110 * pc["delay"] / last)
            lifted = min(1.0, max(0.0, (y - h / 2.0) / max(span * 0.25, 1e-6)))
            fill = (shade, int(shade * (1 - 0.35 * lifted)), int(shade * (1 - 0.7 * lifted)))
            pen.polygon([to_px(x + px, z + pz, ox) for px, pz in pc["points"]], fill=fill, outline=(30, 30, 36))
        ix, iz = to_px(p["impact"][0], p["impact"][1], ox)
        pen.line([ix - 7, iz, ix + 7, iz], fill=(255, 80, 60), width=2)
        pen.line([ix, iz - 7, ix, iz + 7], fill=(255, 80, 60), width=2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.save(path)


def checked(block):
    """the command's options as a plan can be made from; raises ValueError saying what is wrong"""
    o = dict(DEFAULTS)
    o.update({k: v for k, v in block.items() if k in o or k == "size"})

    def num(v, name, lo, hi):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"{name} is a number from {lo:g} to {hi:g}")
        return float(v)

    size = o.get("size")
    if not (isinstance(size, (list, tuple)) and len(size) in (2, 3)):
        raise ValueError("--size is width,depth[,thickness] in studs")
    w, d = num(size[0], "the width", 0.5, 200), num(size[1], "the depth", 0.5, 200)
    h = num(size[2], "the thickness", 0.02, 50) if len(size) == 3 else round(min(w, d) / 10.0, 4)
    if o["shape"] not in ("slab", "disc"):
        raise ValueError("--shape is slab or disc")
    if o["shape"] == "disc":
        d = w
    o["size"] = [w, d, h]
    o["pieces"] = int(num(o["pieces"], "--pieces", 4, 64))
    imp = o["impact"]
    if not (isinstance(imp, (list, tuple)) and len(imp) == 2):
        raise ValueError("--impact is x,z from the slab's centre")
    o["impact"] = [num(imp[0], "the impact's x", -200, 200), num(imp[1], "the impact's z", -200, 200)]
    if not inside(outline(o["shape"], w, d), o["impact"]):
        raise ValueError("--impact lies outside the slab: it is x,z from the slab's centre, inside it")
    o["focus"], o["speed"] = num(o["focus"], "--focus", 0, 1), num(o["speed"], "--speed", 1, 400)
    o["lift"], o["wave"] = num(o["lift"], "--lift", 0, 1), num(o["wave"], "--wave", 1, 2000)
    o["seed"] = int(num(o["seed"], "--seed", 0, 1e9))
    return o


FLAGS = {"--size": "size", "--shape": "shape", "--pieces": "pieces", "--impact": "impact", "--focus": "focus", "--speed": "speed",
         "--lift": "lift", "--wave": "wave", "--seed": "seed"}
DIRS = ("--out-dir", "--look-dir")


def _main(argv):
    usage = "lune run kit vfx fracture <name> --size w,d[,h] [--shape slab|disc] [--pieces 14] [--impact x,z] [--focus 0.6] [--seed 3]"
    if not argv or argv[0].startswith("--"):
        return out("fail", "fracture: needs the plan's name", usage)
    name, rest = argv[0], argv[1:]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        return out("fail", f'fracture: "{name}" is not a name (lower-case letters, digits, _)', usage)
    block, dirs, i = {}, {}, 0
    while i < len(rest):
        a = rest[i]
        if a not in FLAGS and a not in DIRS:
            return out("fail", f"fracture: {a} is not one of its options", usage)
        if i + 1 >= len(rest):
            return out("fail", f"fracture: {a} needs a value", usage)
        v = rest[i + 1]
        if a in DIRS:
            dirs[a] = v
        elif a == "--shape":
            block["shape"] = v
        elif a in ("--size", "--impact"):
            try:
                block[FLAGS[a]] = [float(x) for x in v.split(",")]
            except ValueError:
                return out("fail", f"fracture: {a} is numbers, comma-separated", usage)
        else:
            try:
                block[FLAGS[a]] = float(v)
            except ValueError:
                return out("fail", f"fracture: {a} needs a number", usage)
        i += 2
    if "size" not in block:
        return out("fail", "fracture: needs --size w,d[,h] (the slab, in studs)", usage)
    try:
        o = checked(block)
    except ValueError as e:
        return out("fail", f"fracture {name}: {e}", usage)
    p = plan(o)
    checks = check(p, o)
    failed = [c for c in checks if not c["ok"]]
    picture = os.path.join(dirs.get("--look-dir", LOOK), f"{name}.png")
    if p["pieces"] and not failed:  # (a refused cut does not overwrite the picture of the plan that stays)
        look(p, picture)
    extra = {"checks": checks, "look": picture.replace(os.sep, "/"), "pieces": len(p["pieces"])}
    store = os.path.join(dirs.get("--out-dir", OUT), f"{name}.json")
    if failed:
        said = "; ".join(f"{c['name']} = {c['value']} (needs {c['limit']}): {c['fix']}" for c in failed)
        return out("fail", f"fracture {name}: {said}" + (" - the plan of that name stays as it was" if os.path.isfile(store) else " - nothing written"),
                   failed[0]["fix"], **extra)
    os.makedirs(os.path.dirname(store), exist_ok=True)
    with open(store, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(p, fh, separators=(",", ":"))
        fh.write("\n")
    w, d, h = p["size"]
    return out("pass", f"fracture {name}: a {p['shape']} of {w:g} x {d:g} x {h:g} studs in {len(p['pieces'])} pieces, the blow at {p['impact'][0]:g},{p['impact'][1]:g} "
               f"- on a debris layer: \"pieces\": \"{name}\"",
               f"OPEN {extra['look']}: do the pieces read as THIS object breaking (small at the blow, large at the rim)?", plan=store.replace(os.sep, "/"), **extra)


def main(argv):
    try:
        return _main(argv)
    except Exception as e:  # noqa: BLE001 - a command answers in one line, never with a traceback
        return out("fail", f"fracture: {type(e).__name__}: {e}", "lune run kit vfx fracture <name> --size w,d[,h]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
