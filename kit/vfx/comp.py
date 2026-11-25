"""comp.py - SURFACE LOOKS IN SECONDS: a short stack - a shape, a noise that pans, a distortion, an erosion, a colour
ramp - evaluated straight into a sprite sheet.

    lune run kit vfx comp <key>                    bake assets/textures/<key>.json (its "comp" block) now: frames, the
                                                   LOOK strip, how long it took
    lune run kit vfx comp <key> --new ring|skin|blobs|branches|map|graph
                                                   write a starter spec of that kind first (never over an existing one)
    python kit/vfx/comp.py --specs <dir> --out <frames dir> --plain
    python kit/vfx/comp.py --specs <dir> --out <frames dir> --textures-dir <built> --mapped --pack <packer>
                                                   the build steps: every stale recipe "comp" spec - the plain stacks
                                                   before the kit's packer runs, the ones that map a "source" after
                                                   it (their source is then the one of this run), packed by the step

Why: Roblox has no custom shaders, so what a shader artist does live - scroll a noise through a shape, bend the
lookup, erode by a threshold, map grey to colour - is baked into a sheet. The kit's Blender recipes do it in minutes
a round; this does the 2D part in about a second or less (a 16-frame, 256 px sheet: 0.3-0.7 s), so a look can be
TRIED. Blender stays for what needs real light or a simulation.

A spec (assets/textures/<key>.json):
    {"engine": "fx", "recipe": "comp", "frames": 16, "grid": 4, "cell": 256,
     "comp": {
       "loop": true,                     the frames loop (every "pan" is in whole patterns a loop); false = one shot
       "tile": false,                    the frame wraps (a skin a shell or a beam scrolls); no shape then
       "shape": {"sdf": "ring", "radius": 0.34, "width": 0.07, "soft": 0.02, "falloff": 0.0},
                                         a SIGNED DISTANCE shape: ring | disc | box | streak | star | blobs (smooth
                                         union of discs: metaballs) | branches (a trunk that forks and forks again,
                                         each fork shorter and thinner: lightning, cracks, veins; "trunks": 5 = cracks
                                         round a point). falloff > 0 = a gradient inwards, for the ramp
       "source": {"texture": "<key>"},   instead of a shape: a built texture's luminance x alpha (gradient mapping)
       "noise": {"scale": 4, "octaves": 3, "pan": [1, 0], "seed": 3, "contrast": 1.4, "mix": 1.0},
                                         tiling noise multiplied in, panning `pan` whole patterns a loop
                                         "kind": "voronoi" = CELLS (each pixel's distance to the nearest of a
                                         tiling scatter of points: cracked ground, scales, foam) in place of the soft
                                         fbm; "polar": true = the noise read round the cell's middle (angle across,
                                         distance out): a pan [1, 0] turns it round, [0, 1] runs it outward (a ring of
                                         energy, a portal) - not on a tile
       "warp": {"scale": 3, "amount": 0.05, "pan": [0, 1], "seed": 11},
                                         UV distortion: every lookup above is bent by a second, panning noise
       "twirl": {"amount": 4, "radius": 0.45, "centre": [0.5, 0.5]},
                                         a SWIRL: every lookup turned round "centre" by "amount" radians at the middle,
                                         less and less out to "radius" (nothing beyond): a vortex, a twister - not on
                                         a tile
       "rim": {"width": 0.02, "color": [255, 250, 220], "mix": 1.0},
                                         a HOT EDGE: the band of the picture's own alpha "width" of the cell in from its
                                         border, coloured "color" ("mix" of it): it rides an erosion's front (a burn
                                         edge), a shape's outline, a noise's islands
       "shock": {"from": 0.08, "to": 0.45, "width": 0.07, "amount": 0.02, "centre": [0.5, 0.5]},
                                         SHOCKWAVE DISTORTION, baked: a ring that runs out from "centre" (radius from ->
                                         to over the frames, in cells) and BENDS the picture where it is, as a lens
                                         does - pushed outward just outside its line, pulled in just inside, by
                                         "amount" of the cell at most (three tenths of its width at most: over that the
                                         picture smears into streaks; nothing is bent at the very centre); nothing changes over 3 widths from the line. A
                                         one-shot ("loop": false), not on a tile, not with erode or halftone; it
                                         starts a width or more from its centre. It bends THIS sheet's picture (the
                                         shape and noise, or a source - which is read as a GREY mask, luminance x
                                         alpha, and must fade to clear before the cell's edge) - not the live scene
                                         behind the sheet
       "erode": {"from": 0.15, "to": 1, "soft": 0.04},   the SHARE of the look cut away, its faintest parts first
                                         (0 = nothing, 1 = all of it): one number "at", or from -> to over the frames
                                         of a one-shot - every frame then removes an even share of the area, and
                                         "to": 1 empties exactly the last frame
       "ramp": [[0, [40, 6, 2]], [0.5, [255, 96, 20]], [1, [255, 240, 200]]], "bands": 0,
                                         grey -> colour: the value through a colour ramp; bands > 1 = flat steps
       "halftone": {"dot": 8, "angle": 45}
                                         the alpha as a printed screen: dots `dot` px apart whose size is the alpha
       "graph": {"nodes": {...}, "value": "<node>", "alpha": "<node>"}
                                         NODE-BASED COMPOSITING, instead of shape / source / noise / warp: the look is
                                         a GRAPH of named nodes, each reading others by name - several shapes and
                                         noises joined, one masking another, a bend of anything by anything.
                                         A node is {"op": ...}: sources "shape" (the keys of "shape" above), "noise"
                                         (scale, octaves, pan, seed, contrast), "value" {"is": 0-1}; joins "add" |
                                         "sub" | "mul" | "max" | "min" | "screen" {"a", "b"} and "mix" {"a", "b",
                                         "by"} (a, b, by: a node's name or a number); "invert" {"of"}; "levels"
                                         {"of", "low", "high", "gamma"}; "warp" {"of", "by", "amount"} (the node
                                         "of" read at places bent by how far the node "by" is from its own mean). "value" names the node the
                                         picture is read from (the ramp colours it, an erosion cuts it); "alpha",
                                         when said, the node that is its alpha. 3 to 24 nodes. Refused: a name that
                                         names no node, a ring, a node no output reads, a graph in which no node
                                         joins two others or with under two shapes / noises (that is the stack),
                                         and a node that DOES nothing - halved, what the sheet shows must change
     },
     "post": {"alpha": "coverage", "tonemap": false, "border": 0}}

Its checks (a sheet that fails one writes NO frames): fills (the fullest frame covers 6 % of its cell or more), moves
(no two neighbouring frames show the same picture), packs (every frame's ALPHA changes enough for the kit's packer,
which reads alpha alone: an opaque look whose colours alone move is ONE frame, scrolled by the layer), loops (a
loop's last frame steps into its first no harder than 1.5 times its hardest ordinary step), clear (a shape: nothing
touches the cell's edge) or tiles (a tile: every frame wraps), ends (a one-shot that erodes ends empty). Writes build/fxlab/<key>/NNN.npy and build/vfx/comp/<key>_strip.png: every frame over a dark and a
light ground. OPEN it. `lune run kit vfx` packs, checks and registers the sheet like every other.
Prints one JSON line {schema, status, summary, next_action, seconds, ...}.
"""

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

SPECS = os.path.join("assets", "textures")
FRAMES = os.path.join("build", "fxlab")
BUILT = os.path.join("build", "textures")
LOOK = os.path.join("build", "vfx", "comp")
FILL = 0.06
SEAM = 1.5
EDGE = 0.02
PACK = 0.001       # the least mean alpha every frame must change by (the packer refuses a sheet below 0.0008)
FOOT = 0.04        # under an erosion, a value below this fades to nothing (the shape's own soft rim stays soft)
TWIGS = 600        # the most segments a branches shape may have
BLOCKS = {"shape": {"sdf", "soft", "falloff", "radius", "width", "size", "round", "length", "angle", "points", "inner", "outer", "sharp",
                    "count", "spread", "k", "seed", "origin", "trunks", "depth", "forks", "shrink"},
          "source": {"texture"}, "noise": {"scale", "octaves", "pan", "seed", "contrast", "mix"}, "warp": {"scale", "amount", "pan", "seed"},
          "erode": {"at", "from", "to", "soft"}, "halftone": {"dot", "angle"}, "shock": {"from", "to", "width", "amount", "centre"},
          "twirl": {"amount", "radius", "centre"}, "rim": {"width", "color", "mix"}}
BLOCKS["noise"] = BLOCKS["noise"] | {"kind", "polar"}
NOISES = ("fbm", "voronoi")
SHOCK_SEEN = 0.012   # the least the picture changes (mean of a colour, where the ring is) for a shock to count as bending it
SHOCK_REACH = 3.0    # widths from the ring beyond which a shock bends nothing at all
SHAPES = ("ring", "disc", "box", "streak", "star", "blobs", "branches")
POST = {"alpha": "coverage", "tonemap": False, "border": 0}


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status in ("pass", "warn") else 1


# ---------------------------------------------------------------------------------------------------------------
# fields


def periodic(n, scale, seed):
    """smooth noise in 0-1 that TILES, about `scale` patterns across (low-passed white noise in frequency space)"""
    rng = np.random.default_rng(int(seed))
    fy, fx = np.fft.fftfreq(n)[:, None] * n, np.fft.fftfreq(n)[None, :] * n
    f = np.sqrt(fx * fx + fy * fy)
    amp = np.exp(-(f / max(float(scale), 0.5)) ** 2)
    amp[0, 0] = 0
    v = np.real(np.fft.ifft2((rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))) * amp))
    return (v - v.min()) / max(float(v.max() - v.min()), 1e-9)


def voronoi(n, scale, seed):
    """CELLS that TILE: every pixel's distance to the nearest of one random point per square of a `scale` x `scale`
    grid (wrapped), back in 0-1 - 0 on a point, 1 farthest from any"""
    k = max(1, int(round(float(scale))))
    pts = np.random.default_rng(int(seed)).random((k, k, 2))
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    gx, gy = (xx + 0.5) / n * k, (yy + 0.5) / n * k
    cx, cy = np.floor(gx).astype(np.int64), np.floor(gy).astype(np.int64)
    best = np.full((n, n), np.inf)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ix, iy = cx + dx, cy + dy
            p = pts[iy % k, ix % k]
            best = np.minimum(best, np.hypot(gx - (ix + p[..., 0]), gy - (iy + p[..., 1])))
    return (best - best.min()) / max(float(best.max() - best.min()), 1e-9)


def fbm(n, scale, octaves, seed, kind="fbm"):
    """`octaves` layers of tiling noise (soft "fbm", or "voronoi" cells), each twice as fine and half as strong,
    back in 0-1"""
    layer = voronoi if kind == "voronoi" else periodic
    total, amp, acc = 0.0, 1.0, np.zeros((n, n))
    for k in range(max(1, int(octaves))):
        acc += amp * layer(n, float(scale) * (2 ** k), int(seed) * 31 + k)
        total += amp
        amp *= 0.5
    acc /= total
    return (acc - acc.min()) / max(float(acc.max() - acc.min()), 1e-9)


def sample(field, x, y, wrap=True):
    """the field at pixel coordinates (x, y), bilinear; wrapping, or held at its edge"""
    h, w = field.shape[:2]
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    if field.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]

    def at(yy, xx):
        if wrap:
            return field[yy % h, xx % w]
        return field[np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)]

    top = at(y0, x0) * (1 - fx) + at(y0, x0 + 1) * fx
    bot = at(y0 + 1, x0) * (1 - fx) + at(y0 + 1, x0 + 1) * fx
    return top * (1 - fy) + bot * fy


def smooth(edge0, edge1, x):
    t = np.clip((x - edge0) / np.maximum(edge1 - edge0, 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def sdf(shape, u, v):
    """the signed distance (in cells, negative inside) from each (u, v) to the shape, centred on the cell"""
    kind = shape["sdf"]
    px, py = u - 0.5, v - 0.5
    r = np.sqrt(px * px + py * py)
    if kind == "disc":
        return r - shape["radius"]
    if kind == "ring":
        return np.abs(r - shape["radius"]) - shape["width"] * 0.5
    if kind == "box":
        w, h = shape["size"]
        rd = min(shape.get("round", 0.0), w * 0.5, h * 0.5)  # (a corner cannot be rounder than half its side)
        qx, qy = np.abs(px) - (w * 0.5 - rd), np.abs(py) - (h * 0.5 - rd)
        return np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - rd
    if kind == "streak":  # a capsule: a line of `length` at `angle` degrees, `width` thick
        a = math.radians(shape.get("angle", 0.0))
        ax, ay = math.cos(a), -math.sin(a)
        half = shape["length"] * 0.5
        t = np.clip(px * ax + py * ay, -half, half)
        return np.sqrt((px - t * ax) ** 2 + (py - t * ay) ** 2) - shape["width"] * 0.5
    if kind == "star":  # a radius that swings between inner and outer `points` times round (inside or outside is
        # exact; the distance is along the ray from the centre, not the nearest: a star's soft edge is a little
        # wider between its points)
        ang = np.arctan2(-py, px)
        k = 0.5 + 0.5 * np.cos(int(shape["points"]) * (ang - math.radians(shape.get("angle", 0.0))))
        sharp = k ** float(shape.get("sharp", 2.0))
        return r - (shape["inner"] + (shape["outer"] - shape["inner"]) * sharp)
    if kind == "blobs":  # metaballs: discs joined by a smooth minimum (k = how far they reach for each other)
        rng = np.random.default_rng(int(shape.get("seed", 1)))
        k = max(float(shape.get("k", 0.08)), 1e-4)
        acc = np.zeros_like(u)
        for _ in range(int(shape["count"])):
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(0, shape.get("spread", 0.2))
            rad = shape["radius"] * rng.uniform(0.6, 1.0)
            dist = np.sqrt((px - d * math.cos(a)) ** 2 + (py - d * math.sin(a)) ** 2) - rad
            acc += np.exp(-dist / k)
        return -k * np.log(np.maximum(acc, 1e-300))
    if kind == "branches":
        best = np.full(u.shape, np.inf)
        for (x0, y0, x1, y1, w) in branch_segments(shape):
            ax, ay = x1 - x0, y1 - y0
            t = np.clip(((u - x0) * ax + (v - y0) * ay) / max(ax * ax + ay * ay, 1e-12), 0, 1)
            best = np.minimum(best, np.sqrt((u - (x0 + t * ax)) ** 2 + (v - (y0 + t * ay)) ** 2) - w * 0.5)
        return best
    raise ValueError(f"shape: sdf is one of {', '.join(SHAPES)}")


def branch_segments(shape):
    """a branching shape as line segments [(u0, v0, u1, v1, width)] in cell units: `trunks` trunks leave `origin`
    (spread evenly round it when there are several, else along `angle`, 90 = up the cell); every segment ends in
    `forks` children turned by up to `spread` degrees, `shrink` times as long and as thick, `depth` times over"""
    rng = np.random.default_rng(int(shape.get("seed", 1)))
    ox, oy = shape.get("origin", [0.5, 0.5])
    trunks = int(shape.get("trunks", 1))
    segs = []

    def grow(x, y, ang, length, width, depth):
        x1, y1 = x + length * math.cos(ang), y - length * math.sin(ang)  # (v runs down the picture)
        segs.append((x, y, x1, y1, width))
        if depth <= 1:
            return
        forks = int(shape.get("forks", 2))
        spread = math.radians(shape.get("spread", 35.0))
        for k in range(forks):
            side = (k / (forks - 1) * 2 - 1) if forks > 1 else 0.0
            turn = side * spread * rng.uniform(0.55, 1.0) + rng.uniform(-0.12, 0.12) * spread
            grow(x1, y1, ang + turn, length * shape.get("shrink", 0.7) * rng.uniform(0.85, 1.0), width * shape.get("shrink", 0.7), depth - 1)

    for i in range(trunks):
        base = math.radians(shape.get("angle", 90.0)) + (2 * math.pi * i / trunks if trunks > 1 else 0.0)
        grow(ox, oy, base, shape["length"], shape["width"], int(shape.get("depth", 4)))
    return segs


def ramp_of(stops, bands=0):
    """value 0-1 -> colour, through the ramp's stops (linear between them); bands > 1 = that many flat steps"""
    pos = np.array([s[0] for s in stops], dtype=np.float64)
    col = np.array([s[1] for s in stops], dtype=np.float64)

    def apply(value):
        x = np.clip(value, 0, 1)
        if bands and bands > 1:
            x = np.minimum(np.floor(x * bands), bands - 1) / (bands - 1)
        return np.dstack([np.interp(x, pos, col[:, c]) for c in range(3)])

    return apply


# ---------------------------------------------------------------------------------------------------------------
# a spec's "comp" block


def number(v, name, lo, hi):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(f"{name} is a number from {lo:g} to {hi:g}")
    return float(v)


def pair(v, name, whole):
    if not (isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
        raise ValueError(f"{name} is [u, v]")
    if whole and any(float(x) != int(x) for x in v):
        raise ValueError(f"{name} is in WHOLE patterns a loop (a looping sheet must come back to where it began)")
    return [float(v[0]), float(v[1])]


def colour(c, name):
    """[r, g, b] in 0-255, as every colour of the kit's specs is written ([1, 1, 1] is near black, not white)"""
    if not (isinstance(c, (list, tuple)) and len(c) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 255 for x in c)):
        raise ValueError(f"{name} is [r, g, b], each 0-255")
    return [float(x) / 255.0 for x in c]


def checked(spec):
    """a spec as options that can be baked; raises ValueError saying what is wrong"""
    if not isinstance(spec, dict) or not isinstance(spec.get("comp"), dict):
        raise ValueError('the spec needs a "comp" block')
    c = spec["comp"]
    known = {"loop", "tile", "shape", "source", "noise", "warp", "erode", "ramp", "bands", "halftone", "graph", "shock", "twirl", "rim"}
    odd = sorted(set(c) - known)
    if odd:
        raise ValueError(f'"comp" does not read {", ".join(odd)} (it reads: {", ".join(sorted(known))})')
    for name, reads in BLOCKS.items():  # a key a block does not read is a typo that would be baked as its default
        block = c.get(name)
        if isinstance(block, dict):
            stray = sorted(set(block) - reads)
            if stray:
                raise ValueError(f'"{name}" does not read {", ".join(stray)} (it reads: {", ".join(sorted(reads))})')
    for name in ("loop", "tile"):
        if name in c and not isinstance(c[name], bool):
            raise ValueError(f'"{name}" is true or false')
    # (the looks drawn on a FINISHED cell - a line where the picture steps, a colour fringe - change nothing of the
    # strip below them: a comp sheet may ask for them; it was refused with every other finish)
    post = spec.get("post")
    if not isinstance(post, dict) or {k: v for k, v in post.items() if k not in ("edges", "aberration", "emissive")} != POST:
        raise ValueError(f'a comp sheet\'s colours and alpha are final: its "post" must be {json.dumps(POST)} plus, if wanted, "edges", "aberration" and "emissive" (a glow mask beside it; any other finish - a tone curve, an edge fade - '
                         f"would pack another picture than the strip shows)")
    frames, cell = spec.get("frames", 16), spec.get("cell", 256)
    grid = spec.get("grid", 4)
    cols, rows = (grid, grid) if isinstance(grid, int) else (grid[0], grid[1]) if isinstance(grid, list) and len(grid) == 2 else (0, 0)
    if not (isinstance(frames, int) and isinstance(cell, int) and isinstance(cols, int) and isinstance(rows, int)) or frames < 1 or frames != cols * rows:
        raise ValueError('"frames" must fill the "grid" exactly (the engine plays every cell of a sheet)')
    if cols not in (1, 2, 4, 8) or rows not in (1, 2, 4, 8):
        raise ValueError('"grid" is 1, 2, 4 or 8 cells a side (or [columns, rows] of those): a sheet\'s sides are powers of two')
    if cell not in (64, 128, 256, 512) or cell * max(cols, rows) > 1024:
        raise ValueError('"cell" is 64, 128, 256 or 512 and the sheet at most 1024 px on a side')
    o = {"frames": frames, "cell": cell, "loop": c.get("loop", True), "tile": c.get("tile", False), "bands": 0}
    whole = o["loop"]
    if c.get("shape") is not None and c.get("source") is not None:
        raise ValueError('"shape" or "source", not both')
    if c.get("shape") is not None:
        if o["tile"]:
            raise ValueError('a "tile" has no shape: it fills its cell and wraps')
        s = c["shape"]
        if not isinstance(s, dict) or s.get("sdf") not in SHAPES:
            raise ValueError(f'shape: "sdf" is one of {", ".join(SHAPES)}')
        sh = {"sdf": s["sdf"], "soft": number(s.get("soft", 0.02), "shape.soft", 0, 0.5), "falloff": number(s.get("falloff", 0.0), "shape.falloff", 0, 1)}
        need = {"ring": ("radius", "width"), "disc": ("radius",), "box": (), "streak": ("length", "width"), "star": ("inner", "outer"), "blobs": ("radius",),
                "branches": ("length", "width")}[s["sdf"]]
        for k in need:
            sh[k] = number(s.get(k), f"shape.{k}", 0.001, 1)
        if s["sdf"] == "box":
            sh["size"] = pair(s.get("size"), "shape.size", False)
            if min(sh["size"]) <= 0 or max(sh["size"]) > 1:
                raise ValueError("shape.size is [width, height], each above 0 and at most 1 (of the cell)")
            sh["round"] = number(s.get("round", 0.0), "shape.round", 0, 0.5)
        if s["sdf"] in ("streak", "star"):
            sh["angle"] = number(s.get("angle", 0.0), "shape.angle", -360, 360)
        if s["sdf"] == "branches":
            sh["angle"] = number(s.get("angle", 90.0), "shape.angle", -360, 360)
            sh["origin"] = pair(s.get("origin", [0.5, 0.5]), "shape.origin", False)
            sh["trunks"] = int(number(s.get("trunks", 1), "shape.trunks", 1, 16))
            sh["depth"] = int(number(s.get("depth", 4), "shape.depth", 1, 6))
            sh["forks"] = int(number(s.get("forks", 2), "shape.forks", 1, 3))
            sh["spread"] = number(s.get("spread", 35.0), "shape.spread", 0, 120)
            sh["shrink"] = number(s.get("shrink", 0.7), "shape.shrink", 0.3, 0.95)
            sh["seed"] = int(number(s.get("seed", 1), "shape.seed", 0, 1e9))
            twigs = sh["trunks"] * sum(sh["forks"] ** k for k in range(sh["depth"]))
            if twigs > TWIGS:
                raise ValueError(f"shape: {sh['trunks']} trunk(s), {sh['forks']} forks, {sh['depth']} deep make {twigs} segments (at most {TWIGS}): fewer of one of them")
        if s["sdf"] == "star":
            sh["points"] = int(number(s.get("points", 5), "shape.points", 2, 64))
            sh["sharp"] = number(s.get("sharp", 2.0), "shape.sharp", 0.2, 16)
        if s["sdf"] == "blobs":
            sh["count"] = int(number(s.get("count", 5), "shape.count", 1, 64))
            sh["spread"] = number(s.get("spread", 0.2), "shape.spread", 0, 0.5)
            sh["k"] = number(s.get("k", 0.08), "shape.k", 0.001, 0.5)
            sh["seed"] = int(number(s.get("seed", 1), "shape.seed", 0, 1e9))
        o["shape"] = sh
    if c.get("source") is not None:
        s = c["source"]
        if not isinstance(s, dict) or not isinstance(s.get("texture"), str) or not re.fullmatch(r"[A-Za-z0-9_.\-]+", s["texture"]):
            raise ValueError('source: {"texture": "<a built texture key>"}')
        o["source"] = s["texture"]
    for name in ("noise", "warp"):
        if c.get(name) is None:
            continue
        n = c[name]
        if not isinstance(n, dict):
            raise ValueError(f'"{name}" is a table')
        got = {"scale": number(n.get("scale", 4), f"{name}.scale", 0.5, 64), "pan": pair(n.get("pan", [0, 0]), f"{name}.pan", whole),
               "seed": int(number(n.get("seed", 1), f"{name}.seed", 0, 1e9))}
        if name == "noise":
            got["octaves"] = int(number(n.get("octaves", 3), "noise.octaves", 1, 6))
            got["contrast"] = number(n.get("contrast", 1.0), "noise.contrast", 0.1, 8)
            got["mix"] = number(n.get("mix", 1.0), "noise.mix", 0, 1)
            got["kind"] = n.get("kind", "fbm")
            if got["kind"] not in NOISES:
                raise ValueError(f'noise.kind is one of {", ".join(NOISES)}')
            got["polar"] = n.get("polar", False)
            if not isinstance(got["polar"], bool):
                raise ValueError("noise.polar is true or false")
            if got["polar"] and o["tile"]:
                raise ValueError('a "polar" noise turns round the cell\'s middle: not on a "tile" (its frame wraps, it has no middle)')
        else:
            got["amount"] = number(n.get("amount", 0.05), "warp.amount", 0, 0.5)
        o[name] = got
    if c.get("shock") is not None:
        # SHOCKWAVE DISTORTION, baked (the VFX methods audit, stage 30): a ring that runs out from a point and BENDS
        # the picture it passes over, as a lens does
        s = c["shock"]
        if not isinstance(s, dict):
            raise ValueError('"shock" is {"from", "to", "width", "amount", "centre"}')
        if o["loop"]:
            raise ValueError('a "shock" is a one-shot: "loop": false (a ring that has run out does not come back)')
        if o["tile"]:
            raise ValueError('a "shock" runs out from a point: not on a "tile"')
        centre = s.get("centre", [0.5, 0.5])
        if not (isinstance(centre, list) and len(centre) == 2):
            raise ValueError('shock.centre is [x, y] in the cell, 0-1 each')
        got = {"from": number(s.get("from", 0.05), "shock.from", 0, 0.6), "to": number(s.get("to", 0.45), "shock.to", 0.05, 0.9),
               "width": number(s.get("width", 0.07), "shock.width", 0.02, 0.3), "amount": number(s.get("amount", 0.02), "shock.amount", 0, 0.09),
               "centre": [number(centre[0], "shock.centre", 0, 1), number(centre[1], "shock.centre", 0, 1)]}
        if got["to"] <= got["from"]:
            raise ValueError('a shock runs OUT: "to" is larger than "from"')
        if got["amount"] <= 0:
            raise ValueError('shock.amount is 0: a shock that bends nothing is no shock (leave the "shock" out, or give it an amount)')
        if got["from"] < got["width"]:
            raise ValueError(f'shock.from {got["from"]:g} is under its "width" {got["width"]:g}: the ring would start on its own centre, where the picture is '
                             f"stretched many times over (start it a width out or more)")
        for other, why in (("erode", "an erosion cuts the faintest SHARE of the whole picture, so a ring bending one place moves the cut everywhere"),
                           ("halftone", "a printed screen's dots stand still on the cell: the ring would change their sizes, not bend them")):
            if c.get(other) is not None:
                raise ValueError(f'a "shock" does not go with "{other}" ({why})')
        if got["amount"] > 0.3 * got["width"] + 1e-9:
            raise ValueError(f'shock.amount {got["amount"]:g} is over three tenths of its "width" {got["width"]:g}: the picture would be stretched to over twice its length at the line of the ring '
                             f"and smear into streaks (less amount, or a wider ring)")
        if 0 < got["amount"] * cell < 1.0:
            raise ValueError(f'shock.amount {got["amount"]:g} moves the picture by {got["amount"] * cell:.2f} px, under a pixel: nothing would be seen to bend (more amount)')
        if frames < 4:
            raise ValueError('a shock needs 4 frames or more (a ring seen in one or two places does not travel)')
        if (got["to"] - got["from"]) / (frames - 1) > 1.5 * got["width"]:
            raise ValueError(f'the ring runs {(got["to"] - got["from"]) / (frames - 1):.3f} of the cell a frame, over one and a half of its "width" {got["width"]:g}: '
                             f"it would jump from place to place (more frames, a wider ring, or a shorter run)")
        o["shock"] = got
    if c.get("twirl") is not None:
        tw = c["twirl"]
        if not isinstance(tw, dict):
            raise ValueError('"twirl" is {"amount": radians, "radius": 0-1, "centre": [x, y]}')
        if o["tile"]:
            raise ValueError('a "twirl" turns round a point: not on a "tile"')
        centre = tw.get("centre", [0.5, 0.5])
        if not (isinstance(centre, list) and len(centre) == 2):
            raise ValueError("twirl.centre is [x, y] in the cell, 0-1 each")
        got = {"amount": number(tw.get("amount", 3.0), "twirl.amount", -12, 12), "radius": number(tw.get("radius", 0.45), "twirl.radius", 0.05, 1),
               "centre": [number(centre[0], "twirl.centre", 0, 1), number(centre[1], "twirl.centre", 0, 1)]}
        if abs(got["amount"]) < 0.05:
            raise ValueError("twirl.amount is (near) 0: a twirl that turns nothing is no twirl (leave it out, or give it an amount)")
        o["twirl"] = got
    if c.get("rim") is not None:
        rm = c["rim"]
        if not isinstance(rm, dict):
            raise ValueError('"rim" is {"width": 0-0.2 of the cell, "color": [r, g, b], "mix": 0-1}')
        got = {"width": number(rm.get("width", 0.02), "rim.width", 0.002, 0.2),
               "color": colour(rm.get("color", [255, 250, 220]), "rim.color"), "mix": number(rm.get("mix", 1.0), "rim.mix", 0.05, 1)}
        if got["width"] * cell < 1.0:
            raise ValueError(f"rim.width {got['width']:g} is {got['width'] * cell:.2f} px of a {cell} px cell: under a pixel, no edge would show (wider)")
        o["rim"] = got
    if c.get("erode") is not None:
        e = c["erode"]
        if not isinstance(e, dict):
            raise ValueError('"erode" is {"at": x} or {"from": a, "to": b}, with "soft"')
        er = {"soft": number(e.get("soft", 0.04), "erode.soft", 0, 0.5)}
        if "at" in e and ("from" in e or "to" in e):
            raise ValueError('"erode" is ONE share ("at") or a share that grows ("from", "to"), not both')
        if "at" in e:
            er["from"] = er["to"] = number(e["at"], "erode.at", 0, 1)
        else:
            er["from"], er["to"] = number(e.get("from", 0.0), "erode.from", 0, 1), number(e.get("to", 1.0), "erode.to", 0, 1)
            if er["to"] <= er["from"]:
                raise ValueError('"erode": "to" must be above "from" (the share cut away grows over the frames)')
            if er["from"] != er["to"] and o["loop"]:
                raise ValueError('an erosion that changes over the frames needs "loop": false (it does not come back)')
        o["erode"] = er
    if c.get("ramp") is not None:
        r = c["ramp"]
        if not (isinstance(r, list) and len(r) >= 2 and all(isinstance(s, list) and len(s) == 2 for s in r)):
            raise ValueError('"ramp" is [[position 0-1, [r, g, b]], ...], two stops or more')
        stops = [[number(s[0], "a ramp position", 0, 1), colour(s[1], "a ramp colour")] for s in r]
        if any(stops[i][0] >= stops[i + 1][0] for i in range(len(stops) - 1)):
            raise ValueError('"ramp" positions must rise')
        o["ramp"] = stops
        o["bands"] = int(number(c.get("bands", 0), "bands", 0, 16))
    elif c.get("bands") is not None:
        raise ValueError('"bands" are the steps of a "ramp": there is no ramp')
    if c.get("halftone") is not None:
        h = c["halftone"]
        if not isinstance(h, dict):
            raise ValueError('"halftone" is {"dot": px, "angle": degrees}')
        o["halftone"] = {"dot": number(h.get("dot", 8), "halftone.dot", 3, 64), "angle": number(h.get("angle", 45.0), "halftone.angle", -180, 180)}
        if o["tile"] and (o["halftone"]["angle"] % 90 != 0 or o["halftone"]["dot"] != int(o["halftone"]["dot"]) or cell % int(o["halftone"]["dot"]) != 0):
            raise ValueError('a halftone screen on a "tile" wraps only when it stands square ("angle": 0 or 90) and a whole number of its dots '
                             f'fits the cell ("dot" dividing {cell}): turned or cut dots show a seam')
    if c.get("graph") is not None:
        mixed = [k for k in ("shape", "source", "noise", "warp", "shock", "twirl") if k in o]
        if mixed:
            raise ValueError(f'"graph" stands in place of {", ".join(mixed)}: say them as nodes of the graph, or drop the graph')
        o["graph"] = graph_checked(c["graph"], spec, o["tile"], whole)
        idle = graph_idle(o)
        if idle:
            raise ValueError("graph: " + ", ".join(f'"{n}"' for n, _ in idle) + " do nothing (halved, what the sheet shows changes by "
                             + ", ".join(str(v) for _, v in idle) + f"; needs {NODE_MATTERS}): a node multiplied by nothing, hidden under a max, flat, or feeding a value no "
                             'colour reads (an "alpha" node with no ramp, or a ramp of one colour) - wire it so that it shows, or take it out; a constant '
                             "0 or 1 is written as a number in the join, not as a node")
    if not any(k in o for k in ("shape", "source", "noise", "graph")):
        raise ValueError('"comp" needs something to show: a "shape", a "source", a "noise" or a "graph"')
    if o["tile"] and "noise" not in o and "source" not in o and "graph" not in o:
        raise ValueError('a "tile" needs a "noise" (or a "source") to fill it')
    return o


# ---------------------------------------------------------------------------------------------------------------
# the bake


def source_value(key, built, specs, cell):
    """(a built FX texture's luminance x alpha at cell x cell, the file it came from). The kit packs fx textures
    before it bakes a mapped stack; a texture of another engine, or a dissolve sheet (packed later), is refused"""
    its_path = os.path.join(specs, f"{key}.json")
    if os.path.isfile(its_path):
        try:
            its = json.load(open(its_path, encoding="utf-8"))
        except (OSError, ValueError):
            its = None
        if isinstance(its, dict) and its.get("engine") != "fx":
            raise ValueError(f'source "{key}" is not an fx texture ("engine": "{its.get("engine")}")')
        if isinstance(its, dict) and (its.get("recipe") == "dissolve" or (its.get("recipe") == "comp" and isinstance(its.get("comp"), dict) and its["comp"].get("source") is not None)):
            raise ValueError(f'source "{key}" is itself baked from another texture: map the texture it came from')
    path = os.path.join(built, f"{key}.png")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    img = Image.open(path).convert("RGBA")
    cols = rows = 1
    spec_path = os.path.join(specs, f"{key}.json")
    if os.path.isfile(spec_path):
        try:
            g = json.load(open(spec_path, encoding="utf-8")).get("grid", 1)
        except (OSError, ValueError, AttributeError):
            g = 1
        cols, rows = (g, g) if isinstance(g, int) and g >= 1 else (int(g[0]), int(g[1])) if isinstance(g, list) and len(g) == 2 else (1, 1)
    if cols > 1 or rows > 1:
        img = img.crop((0, 0, img.width // cols, img.height // rows))
    px = np.asarray(img.resize((cell, cell), Image.LANCZOS), dtype=np.float64) / 255.0
    return (px[..., :3] * np.array([0.3, 0.55, 0.15])).sum(axis=2) * px[..., 3], path


def halftone(alpha, dot, angle):
    """the alpha as a printed screen: a grid of dots `dot` px apart, turned by `angle`; each dot covers its square by
    the alpha AT ITS CENTRE (a dot of radius r covers pi r^2 of a unit square, so full alpha joins the dots up)"""
    n = alpha.shape[0]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    a = math.radians(angle)
    gx, gy = (xx * math.cos(a) + yy * math.sin(a)) / dot, (-xx * math.sin(a) + yy * math.cos(a)) / dot
    cx, cy = np.floor(gx) + 0.5, np.floor(gy) + 0.5                      # each pixel's dot centre, in grid units
    px = (cx * math.cos(a) - cy * math.sin(a)) * dot                      # ... and where that is in the picture
    py = (cx * math.sin(a) + cy * math.cos(a)) * dot
    at_centre = np.clip(sample(alpha, px - 0.5, py - 0.5, wrap=False), 0, 1)
    # a dot of radius r covers pi r^2 of its square while it stays inside it (r <= 0.5, alpha <= 0.785); past that the
    # dots run into each other, and the radius goes on to the square's corner (0.707) so that alpha 1 closes the screen
    free = np.sqrt(np.minimum(at_centre, 0.7) / math.pi)
    radius = np.where(at_centre <= 0.7, free, free + (at_centre - 0.7) / 0.3 * (0.7072 - math.sqrt(0.7 / math.pi)))
    dist = np.sqrt((gx - cx) ** 2 + (gy - cy) ** 2)
    edge = 0.75 / dot                                                     # a pixel and a half of soft edge
    return np.clip((radius - dist) / edge + 0.5, 0, 1) * (at_centre > 0.004)


def ranks(value):
    """each covered pixel's place among the covered pixels, 0-1 (the faintest lowest; equal values share one place):
    a threshold that rises evenly over these removes an even share of the AREA each step"""
    from scipy.stats import rankdata
    r = np.zeros(value.shape)
    covered = value > 1e-6
    if covered.any():
        r[covered] = rankdata(value[covered], method="average") / float(covered.sum())
    return r


# ---------------------------------------------------------------------------------------------------------------
# the node graph ("comp": {"graph": {...}}): the same sources and looks as the stack, wired by name

NODE_OPS = {"shape": None, "noise": {"scale", "octaves", "pan", "seed", "contrast"}, "value": {"is"},
            "add": {"a", "b"}, "sub": {"a", "b"}, "mul": {"a", "b"}, "max": {"a", "b"}, "min": {"a", "b"}, "screen": {"a", "b"},
            "mix": {"a", "b", "by"}, "invert": {"of"}, "levels": {"of", "low", "high", "gamma"}, "warp": {"of", "by", "amount"}}
NODE_INPUTS = {"add": ("a", "b"), "sub": ("a", "b"), "mul": ("a", "b"), "max": ("a", "b"), "min": ("a", "b"), "screen": ("a", "b"), "mix": ("a", "b", "by"),
               "invert": ("of",), "levels": ("of",), "warp": ("of", "by")}
NODES_MOST = 24
NODE_MATTERS = 0.002  # a node HALVED must change what the sheet shows by this much (mean, 0-1) ...
NODE_SPOT, NODE_SPOT_PX = 0.2, 6  # ... or by this much in this many pixels of a 128 px cell (a spark, a thin line)


def graph_checked(g, spec, tile, whole):
    """a spec's comp.graph as options; raises ValueError saying what is wrong"""
    if not isinstance(g, dict) or not isinstance(g.get("nodes"), dict):
        raise ValueError('"graph" is {"nodes": {"<name>": {"op": ...}, ...}, "value": "<a node>", "alpha": "<a node>" (optional)}')
    odd = sorted(set(g) - {"nodes", "value", "alpha"})
    if odd:
        raise ValueError(f'"graph" does not read {", ".join(odd)} (it reads: nodes, value, alpha)')
    raw = g["nodes"]
    if not 3 <= len(raw) <= NODES_MOST:
        raise ValueError(f"a graph is 3 to {NODES_MOST} nodes ({len(raw)} here): one or two are the stack's own blocks")
    nodes = {}
    for name, node in raw.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f'a node\'s name is lowercase letters, digits and _ ("{name}")')
        if not isinstance(node, dict) or node.get("op") not in NODE_OPS:
            raise ValueError(f'node "{name}": "op" is one of {", ".join(sorted(NODE_OPS))}')
        op = node["op"]
        mini = {"engine": "fx", "recipe": "comp", "frames": spec.get("frames", 16), "grid": spec.get("grid", 4), "cell": spec.get("cell", 256), "post": dict(POST)}
        if op == "shape":
            if tile:
                raise ValueError(f'node "{name}": a "tile" has no shape (it fills its cell and wraps)')
            try:
                got = checked(dict(mini, comp={"loop": whole, "shape": {k: v for k, v in node.items() if k != "op"}}))["shape"]
            except ValueError as e:
                raise ValueError(f'node "{name}": {e}') from None
        elif op == "noise":
            stray = sorted(set(node) - NODE_OPS[op] - {"op"})
            if stray:
                raise ValueError(f'node "{name}" (noise) does not read {", ".join(stray)} (it reads: {", ".join(sorted(NODE_OPS[op]))})')
            try:
                got = checked(dict(mini, comp={"loop": whole, "tile": tile, "noise": {k: v for k, v in node.items() if k != "op"}}))["noise"]
            except ValueError as e:
                raise ValueError(f'node "{name}": {e}') from None
        else:
            stray = sorted(set(node) - NODE_OPS[op] - {"op"})
            if stray:
                raise ValueError(f'node "{name}" ({op}) does not read {", ".join(stray)} (it reads: {", ".join(sorted(NODE_OPS[op]))})')
            got = {}
            if op == "value":
                got["is"] = number(node.get("is"), f"{name}.is", 0, 1)
            for key in NODE_INPUTS.get(op, ()):
                v = node.get(key)
                if isinstance(v, str):
                    if v not in raw:
                        raise ValueError(f'node "{name}": "{key}" names no node ("{v}")')
                    got[key] = v
                elif key in ("a", "b", "by") and op != "warp" and isinstance(v, (int, float)) and not isinstance(v, bool):
                    got[key] = number(v, f"{name}.{key}", 0, 1)
                else:
                    raise ValueError(f'node "{name}": "{key}" is a node\'s name' + ("" if op == "warp" or key == "of" else " or a number 0-1"))
            if op in ("add", "sub", "mul", "max", "min", "screen", "mix") and not any(isinstance(got[k], str) for k in NODE_INPUTS[op]):
                raise ValueError(f'node "{name}": no input of it is a node (numbers alone are one number: a "value")')
            if op == "levels":
                got["low"], got["high"] = number(node.get("low", 0.0), f"{name}.low", 0, 1), number(node.get("high", 1.0), f"{name}.high", 0, 1)
                got["gamma"] = number(node.get("gamma", 1.0), f"{name}.gamma", 0.1, 8)
                if got["high"] <= got["low"]:
                    raise ValueError(f'node "{name}": "high" must be above "low"')
            if op == "warp":
                got["amount"] = number(node.get("amount", 0.05), f"{name}.amount", 0.001, 0.5)
        nodes[name] = dict(got, op=op)
    outs = {}
    for key in ("value", "alpha"):
        if key in g:
            if not isinstance(g[key], str) or g[key] not in nodes:
                raise ValueError(f'graph: "{key}" names no node')
            outs[key] = g[key]
    if "value" not in outs:
        raise ValueError('graph: "value" names the node the picture is read from')

    def inputs(name):
        return [nodes[name][k] for k in NODE_INPUTS.get(nodes[name]["op"], ()) if isinstance(nodes[name].get(k), str)]

    state, used = {}, set()

    def walk(name, path):  # (a node that reads itself, however far round, has no value)
        if state.get(name) == 1:
            raise ValueError("graph: " + " -> ".join(path + [name]) + " goes round in a ring")
        if state.get(name) == 2:
            return
        state[name] = 1
        used.add(name)
        for nxt in inputs(name):
            walk(nxt, path + [name])
        state[name] = 2

    for start in outs.values():
        walk(start, [])
    idle = sorted(set(nodes) - used)
    if idle:
        raise ValueError(f'graph: {", ".join(idle)} feed nothing (a node no output reads is a typo or left over: wire it or take it out)')
    if not any(len(set(inputs(n))) >= 2 for n in nodes):
        raise ValueError("graph: no node joins two others (a chain of single steps is the stack: use its blocks)")
    if sum(1 for n in nodes.values() if n["op"] in ("shape", "noise")) < 2:
        raise ValueError("graph: it has under two shapes or noises (one source and numbers is the stack: use its blocks)")
    return {"nodes": nodes, "value": outs["value"], "alpha": outs.get("alpha"), "order": sorted(nodes)}


def graph_fields(o):
    """what each source node is on the plain grid, worked out once: {name: field}"""
    n = o["cell"]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    base = {}
    for name, node in o["graph"]["nodes"].items():
        if node["op"] == "shape":
            base[name] = sdf(node, (xx + 0.5) / n, (yy + 0.5) / n)
        elif node["op"] == "noise":
            base[name] = fbm(n, node["scale"], node["octaves"], node["seed"])
    return base


def graph_at(o, base, t, held=None):
    """the graph at time t (0-1 of the frames) -> (value, alpha or None). `held` = {node: share}: that node gives
    only that share of itself (how much a node matters is measured by halving it)"""
    n, g, wrap = o["cell"], o["graph"], o["tile"]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    memo, keep = {}, []
    held = held or {}

    def at(ref, x, y):
        if not isinstance(ref, str):
            return np.full((n, n), float(ref))
        key = (ref, id(x), id(y))
        if key in memo:
            return memo[key]
        node = g["nodes"][ref]
        op = node["op"]
        if op == "value":
            out = np.full((n, n), node["is"])
        elif op == "shape":
            d = base[ref] if x is xx and y is yy else sample(base[ref], x, y, wrap=False)
            soft = node["soft"]
            inside = 1 - smooth(-soft, soft, d) if soft > 0 else (d < 0).astype(np.float64)
            out = inside * (np.clip(-d / node["falloff"], 0, 1) if node["falloff"] > 0 else 1.0)
        elif op == "noise":
            nz = sample(base[ref], x - node["pan"][0] * t * n, y - node["pan"][1] * t * n)
            out = np.clip((nz - 0.5) * node["contrast"] + 0.5, 0, 1)
        elif op == "warp":
            # the bending node is worked out ONCE, on the plain grid, and READ at two places (as the stack's warp reads
            # its noise): asked for again at every bent place, a warp bent by a warp doubled its cost at each level
            # (twelve deep: a minute and a half a frame). It bends by how far it is from its OWN mean, so a mask that
            # is 0 nearly everywhere bends where it is and does not slide the whole picture
            amt = node["amount"] * n
            field = at(node["by"], xx, yy)
            field = field - float(field.mean())
            bx = x + sample(field, x, y) * 2 * amt
            by = y + sample(field, x + n * 0.37, y + n * 0.61) * 2 * amt  # (down the cell: the same node, read elsewhere)
            keep.extend([bx, by])
            out = at(node["of"], bx, by)
        else:
            a = at(node["a"], x, y) if "a" in node else None
            b = at(node["b"], x, y) if "b" in node else None
            if op == "add":
                out = a + b
            elif op == "sub":
                out = a - b
            elif op == "mul":
                out = a * b
            elif op == "max":
                out = np.maximum(a, b)
            elif op == "min":
                out = np.minimum(a, b)
            elif op == "screen":
                out = 1 - (1 - a) * (1 - b)
            elif op == "mix":
                m = at(node["by"], x, y)
                out = a * (1 - m) + b * m
            elif op == "invert":
                out = 1 - at(node["of"], x, y)
            else:  # levels
                v = np.clip((at(node["of"], x, y) - node["low"]) / (node["high"] - node["low"]), 0, 1)
                out = v ** node["gamma"]
            out = np.clip(out, 0, 1)
        if ref in held:
            out = out * held[ref]
        memo[key] = out
        return out

    value = at(g["value"], xx, yy)
    alpha = at(g["alpha"], xx, yy) if g["alpha"] else None
    return value, alpha


def graph_seen(o, base, t, held=None):
    """what the SHEET shows of the graph at time t (premultiplied RGBA): the value through the ramp, under the alpha
    (the alpha node, else the value). A value no colour reads - under an alpha node, with no ramp or a ramp of one
    colour - shows nothing, and so do the nodes that only feed it"""
    value, alpha = graph_at(o, base, t, held)
    cover = np.clip(alpha if alpha is not None else value, 0, 1)
    rgb = ramp_of(o["ramp"], o["bands"])(value) if "ramp" in o else np.ones(value.shape + (3,))
    return np.dstack([rgb * cover[..., None], cover])


def graph_idle(o):
    """the nodes that do nothing: HALVED (at three moments of the sheet), each must change what the sheet SHOWS - by
    NODE_MATTERS on average, or strongly in a small place (a spark, a thin line). A node times nothing, one hidden
    under a max, one that is 0 everywhere, one that only feeds a value no colour reads: halving it changes nothing.
    Measured at 128 px (the look is the same at any size; a 24-node graph at 512 took most of a minute).
    -> [(name, how much)]"""
    small = dict(o, cell=min(o["cell"], 128))
    base = graph_fields(small)
    g = o["graph"]
    moments = (0.0, 0.37, 0.71)
    plain = [graph_seen(small, base, t) for t in moments]
    idle = []
    for name in g["order"]:
        if name in (g["value"], g["alpha"]):
            continue  # (an output IS the picture)
        most, spot = 0.0, 0
        for t, seen in zip(moments, plain):
            change = np.abs(graph_seen(small, base, t, held={name: 0.5}) - seen).max(-1)
            most, spot = max(most, float(change.mean())), max(spot, int((change >= NODE_SPOT).sum()))
        if most < NODE_MATTERS and spot < NODE_SPOT_PX:
            idle.append((name, round(most, 5)))
    return idle


def _node_alone(o, base, t, name):
    """one node's own field at time t (read as if it were the graph's value)"""
    sub = dict(o, graph=dict(o["graph"], value=name, alpha=None))
    return graph_at(sub, base, t)[0]


def shock_at(s, x, y, t, n):
    """SHOCKWAVE DISTORTION: where the picture is READ once a ring of radius from -> to (at time t of 0-1) bends it.
    A lens: just outside the ring's line the picture is read from nearer the centre (it is pushed outward), just
    inside from further out (it is pulled in) - the most a width from the line, nothing at all beyond SHOCK_REACH
    widths. -> (x, y, how far each place is from the ring's line in widths)"""
    cx, cy = s["centre"][0] * n, s["centre"][1] * n
    dx, dy = x - cx, y - cy
    r = np.hypot(dx, dy)
    q = (r / n - (s["from"] + (s["to"] - s["from"]) * t)) / s["width"]
    # 1 at a width out, -1 at a width in; taken down to nothing between 2.2 and SHOCK_REACH widths by a curve with no
    # corner (a window that ended in a corner left a faint crease ring there)
    fade = np.clip((SHOCK_REACH - np.abs(q)) / (SHOCK_REACH - 2.2), 0.0, 1.0)
    lens = q * np.exp(0.5 - q * q / 2.0) * fade * fade * (3.0 - 2.0 * fade)
    # nothing at the very centre (every way is "out" there: the picture would pinwheel) - by a curve with no corner
    # (a ramp that stopped at one width left a crease ring that stood still while the shock ran out)
    lens = lens * (1.0 - np.exp(-(r / (s["width"] * n)) ** 2))
    push = s["amount"] * n * lens / np.maximum(r, 1e-6)
    return x - dx * push, y - dy * push, q


def frames_of(o, source=None, shock=True):
    """the stack evaluated for every frame -> [frame] (straight RGBA, 0-1). shock=False: the same frames with the
    shock left out (what its ring is measured against)"""
    n, count = o["cell"], o["frames"]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    wrap = o["tile"]
    noise = fbm(n, o["noise"]["scale"], o["noise"]["octaves"], o["noise"]["seed"], o["noise"].get("kind", "fbm")) if "noise" in o else None
    if "warp" in o:
        wx, wy = periodic(n, o["warp"]["scale"], o["warp"]["seed"]), periodic(n, o["warp"]["scale"], o["warp"]["seed"] + 977)
    paint = ramp_of(o["ramp"], o["bands"]) if "ramp" in o else None
    # the shape's distance is worked out ONCE, on the plain grid; a warp then reads it at the bent coordinates (a
    # branching shape of hundreds of segments, measured again on every frame, took seconds)
    dist = sdf(o["shape"], (xx + 0.5) / n, (yy + 0.5) / n) if "shape" in o else None
    base = graph_fields(o) if "graph" in o else None
    frames = []
    for i in range(count):
        t = i / float(count) if o["loop"] else (i / float(count - 1) if count > 1 else 0.0)
        x, y = xx, yy
        if "warp" in o and o["warp"]["amount"] > 0:
            px, py = o["warp"]["pan"][0] * t * n, o["warp"]["pan"][1] * t * n
            amt = o["warp"]["amount"] * n
            x = xx + (sample(wx, xx - px, yy - py) - 0.5) * 2 * amt
            y = yy + (sample(wy, xx - px, yy - py) - 0.5) * 2 * amt
        if shock and "shock" in o and o["shock"]["amount"] > 0:
            sx, sy, _ = shock_at(o["shock"], xx, yy, t, n)
            x, y = x + (sx - xx), y + (sy - yy)
        if "twirl" in o:
            x, y = twirled(o["twirl"], x, y, n)
        value = np.ones((n, n))
        if dist is not None:
            d = dist if x is xx else sample(dist, x, y, wrap=False)
            soft = o["shape"]["soft"]
            inside = 1 - smooth(-soft, soft, d) if soft > 0 else (d < 0).astype(np.float64)
            value = inside * (np.clip(-d / o["shape"]["falloff"], 0, 1) if o["shape"]["falloff"] > 0 else 1.0)
        elif source is not None:
            value = sample(source, x, y, wrap=wrap)
        if noise is not None:
            px, py = o["noise"]["pan"][0] * t * n, o["noise"]["pan"][1] * t * n
            if o["noise"].get("polar"):
                # round the cell's middle: across = the angle (one turn = the noise's width, so it closes without a
                # seam), out = the distance; a pan [1, 0] turns it, [0, 1] runs it outward
                ang = np.arctan2(y + 0.5 - n * 0.5, x + 0.5 - n * 0.5)
                nz = sample(noise, (ang / (2 * math.pi) % 1.0) * n - px, np.hypot(x + 0.5 - n * 0.5, y + 0.5 - n * 0.5) - py)
            else:
                nz = sample(noise, x - px, y - py)
            nz = np.clip((nz - 0.5) * o["noise"]["contrast"] + 0.5, 0, 1)
            value = value * (1 - o["noise"]["mix"] + o["noise"]["mix"] * nz)
        own_alpha = None
        if base is not None:  # the node graph: the value (and its own alpha, when it names one) come from its nodes
            value, own_alpha = graph_at(o, base, t)
        if "erode" in o:
            # the SHARE of the look cut away, faintest first: a pixel's place among the covered pixels against a line
            # that rises from "from" to "to" - every frame of a one-shot removes an even share of the area, however
            # the values are spread (measured against the value itself, the last frames held a few pixels and the
            # packer refused the sheet as "not moving"). At 1 nothing is left, by rule; at 0 nothing is cut
            q = o["erode"]["from"] + (o["erode"]["to"] - o["erode"]["from"]) * t
            soft = o["erode"]["soft"]
            foot = np.clip(value / FOOT, 0, 1)
            if q >= 1:
                keep = np.zeros((n, n))
            elif q <= 0:
                keep = np.ones((n, n))
            else:
                r = ranks(value)
                keep = np.clip((r - (q - soft * 0.5)) / soft, 0, 1) if soft > 0 else (r > q).astype(np.float64)
            alpha = keep * foot
        else:
            alpha = value
        if own_alpha is not None:  # (an erosion still cuts: what is left of the graph's alpha)
            alpha = alpha * own_alpha if "erode" in o else own_alpha
        if "halftone" in o:
            alpha = halftone(np.clip(alpha, 0, 1), o["halftone"]["dot"], o["halftone"]["angle"])
        rgb = paint(value) if paint else np.ones((n, n, 3))
        if "rim" in o:
            band = rim_band(np.clip(alpha, 0, 1), max(1, int(round(o["rim"]["width"] * n))), wrap)
            k = (band * o["rim"]["mix"])[..., None]
            rgb = rgb * (1 - k) + np.asarray(o["rim"]["color"], dtype=np.float64)[None, None, :] * k  # (colour() is 0-1 already)
        frames.append(np.dstack([rgb, np.clip(alpha, 0, 1)]))
    return frames


def twirled(tw, x, y, n):
    """lookups turned round the twirl's centre: by its amount at the middle, falling to nothing at its radius"""
    cx, cy = tw["centre"][0] * n - 0.5, tw["centre"][1] * n - 0.5
    dx, dy = x - cx, y - cy
    r = np.hypot(dx, dy) / (tw["radius"] * n)
    ang = tw["amount"] * np.clip(1 - r, 0, 1) ** 2
    ca, sa = np.cos(ang), np.sin(ang)
    return cx + dx * ca - dy * sa, cy + dx * sa + dy * ca


def rim_band(alpha, px, wrap):
    """the band of alpha `px` pixels in from its border: alpha less alpha worn down by `px` (a min over a square)"""
    inner = alpha
    for _ in range(px):
        if wrap:
            nb = [np.roll(inner, (dy, dx), (0, 1)) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
        else:
            pad = np.pad(inner, 1, mode="constant")
            h, w = inner.shape
            nb = [pad[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
        inner = np.minimum.reduce(nb)
    return np.clip(alpha - inner, 0, 1)


def premultiplied(frame):
    f = frame.astype(np.float64).copy()
    f[..., :3] *= f[..., 3:]
    return f


def check(frames, o, plain=None):
    """plain: the same frames with no shock (a spec with a "shock": what its ring is measured against)"""
    checks = []

    def add(name, ok, value, limit, fix):
        checks.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": fix})

    cover = [float((f[..., 3] > 0.02).mean()) for f in frames]
    add("fills", max(cover) >= FILL, round(max(cover), 3), f">= {FILL} of the cell covered in the fullest frame",
        "the look is a speck in its cell: a larger shape, a lower erosion threshold or more noise")
    if len(frames) > 1:
        seen = [premultiplied(f) for f in frames]  # (what is SEEN: a colour under no alpha changes nothing)
        steps = [float(np.abs(seen[i + 1] - seen[i]).mean()) for i in range(len(seen) - 1)]
        add("moves", min(steps) > 1e-5, round(min(steps), 6), "every frame differs from the one before",
            'two frames show the same picture: give the noise or the warp a "pan"; a one-shot that erodes: "to": 1 (higher empties it before its last frame)')
        if o["loop"]:
            seam = float(np.abs(seen[0] - seen[-1]).mean())
            hard = float(max(steps))
            add("loops", seam <= SEAM * hard + 1e-6, round(seam / max(hard, 1e-9), 2), f"the last frame into the first <= {SEAM} times the hardest ordinary step",
                "the loop pops at its seam: every pan in whole patterns a loop")
    if len(frames) > 1:
        change = min(float(np.abs(frames[i + 1][..., 3] - frames[i][..., 3]).mean()) for i in range(len(frames) - 1))
        add("packs", change >= PACK, round(change, 5), f">= {PACK} mean ALPHA changed between every two frames (the kit's packer reads alpha alone)",
            "the packer would refuse this sheet as \"not moving\": a look whose colours alone move is ONE frame scrolled by its layer (\"frames\": 1, \"grid\": 1, then uvScroll / textureSpeed); "
            "a look that changes too little a frame needs fewer frames or a fuller shape")
    if o["tile"]:
        # every frame must WRAP, in colour and in alpha. Read low-passed (a fine grain steps as hard between any two
        # columns as across a seam and hid a real one): the step across each seam against the step between
        # neighbouring columns / rows. A halftone tile is held to its own rule in the spec (its dots fit the cell)
        from scipy.ndimage import gaussian_filter
        worst = 0.0
        if "halftone" not in o:
            for f in frames:
                low = gaussian_filter(premultiplied(f), sigma=(3, 3, 0), mode="wrap")
                for seam, inside in ((np.abs(low[:, 0] - low[:, -1]).mean(), np.abs(low[:, 1:] - low[:, :-1]).mean()),
                                     (np.abs(low[0, :] - low[-1, :]).mean(), np.abs(low[1:, :] - low[:-1, :]).mean())):
                    worst = max(worst, float(seam) - 2 * float(inside))
        add("tiles", worst <= 0.01, round(worst, 4), "the smoothed picture's step across each seam <= twice its step between neighbours + 0.01",
            "a tile must wrap: a source texture that does not tile cannot make one")
    else:
        edge = max(float(max(f[0, :, 3].max(), f[-1, :, 3].max(), f[:, 0, 3].max(), f[:, -1, 3].max())) for f in frames)
        add("clear", edge <= EDGE, round(edge, 3), f"<= {EDGE} alpha on the cell's edge",
            "the source reaches the cell's edge: a sheet that is not a tile must fade to clear before it (a source that fades out at its rim; a full plate cannot be one)"
            if "source" in o else "the shape is cut by its cell: make it smaller or warp it less")
    if "shock" in o:
        n, count, s = o["cell"], len(frames), o["shock"]
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
        bent, stray, radius = [], 0.0, []
        for i, f in enumerate(frames):
            t = i / float(count - 1) if count > 1 else 0.0
            _, _, q = shock_at(s, xx, yy, t, n)
            diff = np.abs(premultiplied(f) - premultiplied(plain[i])).mean(-1) if plain is not None else np.zeros((n, n))
            band = np.abs(q) < SHOCK_REACH
            bent.append(float(diff[band].mean()) if band.any() else 0.0)
            stray = max(stray, float(diff[np.abs(q) > SHOCK_REACH + 0.2].max()) if (np.abs(q) > SHOCK_REACH + 0.2).any() else 0.0)
            r = np.hypot(xx - s["centre"][0] * n, yy - s["centre"][1] * n) / n
            radius.append(float((r * diff).sum() / diff.sum()) if diff.sum() > 1e-9 else None)
        seen = sum(1 for b in bent if b >= SHOCK_SEEN) / float(count)
        add("bends", seen >= 0.75, round(seen, 2), f"the ring changes the picture where it is by {SHOCK_SEEN} or more (mean) in three frames of four",
            'the shock bends nothing you can see: more "amount", or a picture with more in it for the ring to bend (a flat fill has nothing to move)')
        add("bends only at its ring", stray <= 1e-6, round(stray, 6), f"nothing changes further than {SHOCK_REACH:g} widths from the ring's line",
            "a fault in the shock (kit/vfx/comp.py shock_at)")
        known = [(i, r) for i, r in enumerate(radius) if r is not None]
        ran = (known[-1][1] - known[0][1]) if len(known) >= 2 else 0.0
        add("runs out", ran >= 0.5 * (s["to"] - s["from"]), round(ran, 3), f"what it bends is {0.5 * (s['to'] - s['from']):.3f} of the cell further out at the end than at the start",
            'the ring does not travel over the picture: a picture that reaches as far as the ring\'s "to", or a "to" inside the picture')
    if "erode" in o and not o["loop"] and o["erode"]["to"] > o["erode"]["from"]:
        last = float((frames[-1][..., 3] > 0.02).mean())
        add("ends", last <= 0.01, round(last, 3), "<= 0.01 of the cell still covered in the last frame",
            'a one-shot that erodes must end empty (its last frame is held): "to": 1 clears exactly on the last frame')
    return checks


def file_id(path):
    if path is None:
        return "none"
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return None


def write_frames(frames_dir, key, frames, spec_path, src_id):
    fdir = os.path.join(frames_dir, key)
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".npy"):
            os.remove(os.path.join(fdir, f))
    for i, c in enumerate(frames):
        np.save(os.path.join(fdir, f"{i:03d}.npy"), premultiplied(c).astype(np.float16))
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": len(frames), "spec_mtime": os.path.getmtime(spec_path), "engine": "comp", "source": src_id}, fh)


def strip(frames, path, tile=200):
    per_row = min(len(frames), 8)
    rows = int(math.ceil(len(frames) / float(per_row)))
    head = 20
    page = Image.new("RGB", (per_row * (tile + 6) + 6, rows * (2 * tile + head + 10) + 6), (20, 20, 24))
    pen = ImageDraw.Draw(page)
    for i, c in enumerate(frames):
        r, col = divmod(i, per_row)
        x, y = 6 + col * (tile + 6), 6 + r * (2 * tile + head + 10)
        pen.text((x + 2, y + 3), f"frame {i}", fill=(225, 225, 225))
        px = np.asarray(Image.fromarray((np.clip(c, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").resize((tile, tile), Image.LANCZOS), dtype=np.float64) / 255.0
        for k, ground in enumerate((0.10, 0.82)):
            over = ground * (1 - px[..., 3:]) + px[..., :3] * px[..., 3:]
            page.paste(Image.fromarray((np.clip(over, 0, 1) * 255 + 0.5).astype(np.uint8)), (x, y + head + k * (tile + 4)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.save(path)


def bake(key, spec, spec_path, built, specs, frames_dir, look_dir=None):
    """one sheet -> (status, summary, next_action, extra). Frames are written only when every check passes"""
    t0 = time.perf_counter()
    o = checked(spec)
    source, src_path = None, None
    if "source" in o:
        try:
            source, src_path = source_value(o["source"], built, specs, o["cell"])
        except FileNotFoundError as e:
            return ("fail", f"comp {key}: no built texture {str(e).replace(os.sep, '/')}", "build the source texture first (lune run kit vfx)", {})
    frames = frames_of(o, source)
    checks = check(frames, o, frames_of(o, source, shock=False) if "shock" in o else None)
    seconds = round(time.perf_counter() - t0, 3)
    failed = [c for c in checks if not c["ok"]]
    look = None
    if look_dir:
        look = os.path.join(look_dir, f"{key}_strip.png")
        strip(frames, look)
    extra = {"checks": checks, "look": look.replace(os.sep, "/") if look else None, "seconds": seconds}
    if failed:
        said = "; ".join(f"{c['name']} = {c['value']} (needs {c['limit']}): {c['fix']}" for c in failed)
        return ("fail", f"comp {key}: {said} - no frames written", failed[0]["fix"], extra)
    write_frames(frames_dir, key, frames, spec_path, file_id(src_path))
    parts = [k for k in ("shape", "source", "noise", "warp", "shock", "erode", "ramp", "halftone") if k in o]
    if "graph" in o:
        parts.insert(0, f"a graph of {len(o['graph']['nodes'])} nodes")
    how = "Loop" if o["loop"] else "OneShot"
    return ("pass", f"comp {key}: {o['frames']} frames of {o['cell']} px in {seconds:g} s ({' + '.join(parts)}"
            + (", a tile" if o["tile"] else "") + f") - play it as a {how} flipbook",
            (f"OPEN {extra['look']}; " if look else "") + "edit the spec and run it again, then lune run kit vfx packs and registers it", extra)


TEMPLATES = {
    "ring": {"loop": True, "shape": {"sdf": "ring", "radius": 0.34, "width": 0.09, "soft": 0.02},
             "noise": {"scale": 5, "octaves": 3, "pan": [1, 0], "seed": 3, "contrast": 1.6, "mix": 0.8},
             "warp": {"scale": 3, "amount": 0.03, "pan": [0, 1], "seed": 11},
             "erode": {"at": 0.22, "soft": 0.05},
             "ramp": [[0, [255, 255, 255]], [1, [255, 255, 255]]]},
    "skin": {"loop": True, "tile": True,
             "noise": {"scale": 4, "octaves": 4, "pan": [1, 0], "seed": 5, "contrast": 1.8, "mix": 1.0},
             "warp": {"scale": 2, "amount": 0.06, "pan": [0, 1], "seed": 13},
             "erode": {"at": 0.35, "soft": 0.08},
             "ramp": [[0, [255, 255, 255]], [1, [255, 255, 255]]]},
    "blobs": {"loop": True, "shape": {"sdf": "blobs", "count": 6, "radius": 0.11, "spread": 0.2, "k": 0.06, "seed": 2, "soft": 0.015, "falloff": 0.12},
              "warp": {"scale": 3, "amount": 0.025, "pan": [1, 0], "seed": 7},
              "ramp": [[0, [255, 255, 255]], [1, [255, 255, 255]]], "bands": 3},
    "branches": {"loop": True, "shape": {"sdf": "branches", "origin": [0.5, 0.86], "angle": 90, "length": 0.26, "width": 0.035, "depth": 5,
                                         "forks": 2, "spread": 34, "shrink": 0.72, "seed": 4, "soft": 0.006},
                 "warp": {"scale": 4, "amount": 0.012, "pan": [1, 0], "seed": 5},
                 "ramp": [[0, [255, 255, 255]], [1, [255, 255, 255]]]},
    "graph": {"loop": True,
              "graph": {"nodes": {"core": {"op": "shape", "sdf": "disc", "radius": 0.16, "soft": 0.03, "falloff": 0.16},
                                  "halo": {"op": "shape", "sdf": "ring", "radius": 0.33, "width": 0.05, "soft": 0.02},
                                  "clouds": {"op": "noise", "scale": 5, "octaves": 3, "pan": [1, 0], "seed": 3, "contrast": 1.6},
                                  "drift": {"op": "noise", "scale": 3, "octaves": 2, "pan": [0, 1], "seed": 11, "contrast": 1.0},
                                  "torn": {"op": "mul", "a": "halo", "b": "clouds"},
                                  "bent": {"op": "warp", "of": "torn", "by": "drift", "amount": 0.03},
                                  "both": {"op": "max", "a": "core", "b": "bent"}},
                        "value": "both"},
              "ramp": [[0, [255, 255, 255]], [1, [255, 255, 255]]]},
    # (a mottled disc for the ring to bend, so the starter bakes as it is: a "source" may stand in place of the shape
    # and the noise - a built texture that fades to clear at its rim, read as a grey mask)
    "shock": {"loop": False, "shape": {"sdf": "disc", "radius": 0.4, "soft": 0.03},
              "noise": {"scale": 6, "octaves": 3, "pan": [0, 0], "seed": 5, "contrast": 2.2, "mix": 0.8},
              "shock": {"from": 0.08, "to": 0.38, "width": 0.07, "amount": 0.02, "centre": [0.5, 0.5]},
              "ramp": [[0, [0, 0, 0]], [0.5, [128, 128, 128]], [1, [255, 255, 255]]]},
    "map": {"loop": True, "source": {"texture": "<a built grey texture>"},
            "warp": {"scale": 3, "amount": 0.02, "pan": [1, 0], "seed": 9},
            "ramp": [[0, [0, 0, 0]], [0.5, [128, 128, 128]], [1, [255, 255, 255]]]},
}


def new_spec(kind):
    return {"engine": "fx", "recipe": "comp",
            "about": f"a {kind} look (kit/vfx/comp.py): EDIT the \"comp\" block - its ramp is white on purpose: put the scene's measured colours in it",
            "frames": 16, "grid": 4, "cell": 256, "comp": json.loads(json.dumps(TEMPLATES[kind])), "post": dict(POST)}


def build_step(argv):
    """every recipe "comp" spec whose frames are missing, older than its spec, or made from a source texture that
    changed, is baked again. --plain: only the stacks with no source (kit vfx runs this BEFORE its packer, which
    packs them like every sheet). --mapped: only the ones that map a "source" (run AFTER the packer, so the source is
    this run's); with --pack <packer> those are then packed and registered by this step"""
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else d  # noqa: E731
    specs, frames_dir, built = opt("--specs", SPECS), opt("--out", FRAMES), opt("--textures-dir", BUILT)
    done, errors, keys = [], [], []
    for f in sorted(os.listdir(specs)) if os.path.isdir(specs) else []:
        if not f.endswith(".json"):
            continue
        path = os.path.join(specs, f)
        try:
            with open(path, encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(spec, dict) or spec.get("engine") != "fx" or spec.get("recipe") != "comp":
            continue
        key = f[:-5]
        block = spec.get("comp") if isinstance(spec.get("comp"), dict) else {}
        mapped = block.get("source") is not None
        if ("--plain" in argv and mapped) or ("--mapped" in argv and not mapped):
            continue
        src = block["source"].get("texture") if isinstance(block.get("source"), dict) else None
        src_path = os.path.join(built, f"{src}.png") if isinstance(src, str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*", src) and ".." not in src else None
        try:
            with open(os.path.join(frames_dir, key, "frames.json"), encoding="utf-8") as fh:
                meta = json.load(fh)
            fresh = meta.get("spec_mtime") == os.path.getmtime(path) and meta.get("source") == file_id(src_path) and meta.get("source") is not None
        except (OSError, ValueError, AttributeError):
            fresh = False
        if fresh and "--force" not in argv:
            keys.append(key)
            continue
        try:
            status, said, _, _ = bake(key, spec, path, built, specs, frames_dir)
        except ValueError as e:
            status, said = "fail", f"comp {key}: {e}"
        except Exception as e:  # noqa: BLE001 - one broken spec must not stop the others, nor print a traceback
            status, said = "fail", f"comp {key}: could not be baked ({type(e).__name__}: {e})"
        if status == "pass":
            done.append(said)
            keys.append(key)
        else:
            errors.append(said)
    packed = None
    if keys and "--pack" in argv:
        r = subprocess.run([sys.executable, opt("--pack", ""), "--specs", specs, "--frames", frames_dir, "--out", built,
                            "--registry", opt("--registry", os.path.join("assets", "effects", "_textures.json")), "--no-review", *keys],
                           capture_output=True, text=True, check=False)
        try:
            packed = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            packed = {"status": "fail", "summary": (r.stderr.strip().splitlines() or ["the packer printed nothing"])[-1]}
        if packed.get("status") != "pass":
            errors.append(f"the packer: {packed.get('summary')}")
    if errors:
        return out("fail", "comp: " + "; ".join(errors), "fix the spec, then: lune run kit vfx comp <key>", baked=done)
    tail = f", {len(keys)} packed" if packed else ""
    return out("pass", (f"comp: {len(done)} sheet(s) baked" if done else "comp: every comp sheet's frames are current") + tail, "none", baked=done, packed=keys if packed else [])


DIRS = ("--textures-dir", "--specs-dir", "--frames-dir", "--look-dir")


def _main(argv):
    if "--specs" in argv:
        return build_step(argv)
    usage = "lune run kit vfx comp <key> [--new ring|skin|blobs|branches|map|graph|shock]"
    if not argv or argv[0].startswith("--"):
        return out("fail", "comp: needs a texture key", usage)
    key, rest = argv[0], argv[1:]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        return out("fail", f'comp: "{key}" is not a texture key (lower-case letters, digits, _)', usage)
    opts, i = {}, 0
    while i < len(rest):
        if rest[i] not in DIRS and rest[i] != "--new":
            return out("fail", f"comp: {rest[i]} is not one of its options", usage)
        if i + 1 >= len(rest):
            return out("fail", f"comp: {rest[i]} needs a value", usage)
        opts[rest[i]] = rest[i + 1]
        i += 2
    specs = opts.get("--specs-dir", SPECS)
    path = os.path.join(specs, f"{key}.json")
    if "--new" in opts:
        if opts["--new"] not in TEMPLATES:
            return out("fail", f"comp: --new is one of {', '.join(TEMPLATES)}", usage)
        if os.path.exists(path):
            return out("fail", f"comp {key}: {path.replace(os.sep, '/')} is there already - a new look gets a new key", usage)
        os.makedirs(specs, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(new_spec(opts["--new"]), fh, indent=1)
            fh.write("\n")
        if opts["--new"] == "map":
            return out("pass", f"comp {key}: a starter spec written ({path.replace(os.sep, '/')})",
                       'name the built grey texture in "comp.source.texture" and put the colours in its ramp, then: lune run kit vfx comp ' + key)
    if not os.path.isfile(path):
        return out("fail", f"comp {key}: no spec {path.replace(os.sep, '/')}", f"lune run kit vfx comp {key} --new ring|skin|blobs|branches|map|graph")
    try:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, ValueError) as e:
        return out("fail", f"comp {key}: its spec cannot be read ({type(e).__name__})", "fix the JSON")
    if not isinstance(spec, dict) or spec.get("engine") != "fx" or spec.get("recipe") != "comp":
        return out("fail", f'comp {key}: its spec is not a comp recipe ("engine": "fx", "recipe": "comp")', usage)
    try:
        status, said, nxt, extra = bake(key, spec, path, opts.get("--textures-dir", BUILT), specs, opts.get("--frames-dir", FRAMES), opts.get("--look-dir", LOOK))
    except ValueError as e:
        return out("fail", f"comp {key}: {e}", "fix the spec's \"comp\" block")
    return out(status, said, nxt, **extra)


def main(argv):
    try:
        return _main(argv)
    except Exception as e:  # noqa: BLE001 - a command answers in one line, never with a traceback
        return out("fail", f"comp: {type(e).__name__}: {e}", "lune run kit vfx comp <key> [--new ring|skin|blobs|branches|map|graph|shock]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
