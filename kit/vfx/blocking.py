#!/usr/bin/env python3
"""blocking.py - SOLID BLOCKING FOR THE ANIMATIC (the owner's limitations file, F-R07; the VFX methods audit, stage 29).

The timing animatic (kit/vfx/animatic.py) shows every beat as ONE flat card NEAR the camera, sized to the scene's
share of the screen. A flat card facing one camera cannot say where the effect STANDS, how deep it is, what it
hides, or whether it touches the ground - and from any other angle it is a line.

A chart's beat may now say a SOLID instead:

    "solid": {"form": "ball" | "pillar" | "slab", "size": <studs>, "at": [x, z], "lift": <studs>}

  ball     a sphere `size` across
  pillar   a column `size` tall and a quarter of that across
  slab     a plate `size` across and an eighth of that thick, lying on the ground
  at       where it stands on the ground, from the effect's own place (x right, -z forward); [0, 0] unless said
  lift     how far its underside is above the ground; 0 unless said (0 = it TOUCHES the ground)
  to       [x, z]: where it has GONE by the end of its beat - it moves there evenly over the beat (a wave that runs
           out, a projectile). None unless said: it stands. A chart with a moving solid is checked for FLOW: every
           solid at eleven moments of its beat, from every angle, each other solid where it is at that moment

Such a beat is a real 3D shape in the effect's own place, at the chart's timing, and it is CHECKED from every
gameplay angle the animatic is asked for (--angles, kit/vfx/views.json: `combat` unless said), by geometry alone -
rays from each camera through its picture:

  (a ball is tested as a sphere, a pillar as the upright cylinder it is drawn as, a slab as its box)
  in frame   the part of the solid's outline that is inside the picture (not asked of one that covers over 0.05 of
             the picture: a sky beam, a wide crater)
  share      the part of the picture it covers
  hidden     the part of it that another solid, alive at the same moment and nearer the camera, covers
  grounded   its underside is on the ground
  touches    the other solids it meets

A solid beat that an angle cannot show - most of it outside the picture, a speck, or hidden by another - fails the
animatic, saying which beat, which angle, and what would do.

Solids are "alive at the same moment" only when their beats' stretches overlap - and the animatic ends a beat where the
next one starts, so in practice only beats that START together hide or touch each other.

THE SOLIDS ARE DRAWN HERE, from every angle (`sheet`, `film`): the browser player draws a solid as flat glowing
colour laid over the others (no shading, nothing hidden behind anything: a ball films as a disc), so the player's
film shows no volume and nothing hidden. This file draws them by the same rays its checks use - lit by where a surface
faces, the nearer hiding the farther as in Roblox (where they are opaque), the ground dark under what touches it -
as a sheet of stills (every solid beat from every angle) and a small film of all angles at once on the chart's
clock (the time written on a frame is that of the last frame in which something moved). A
flat card of another beat standing in front of the camera at the same moment is not drawn there and is not counted
as hiding a solid.

WHAT IT IS NOT: three plain forms, upright, on ONE flat ground at height 0, going straight and evenly when they
move. No real silhouette, no bending, no curve, nothing of the scene's own set (a wall, a character) to hide behind
or stand on. Its drawings are of the BLOCKING, not of the effect, and are not the player's film. It says whether a
beat CAN be seen, where it stands and which way it goes; whether it looks right from there is the owner's to judge.
"""
import math

import numpy as np

FORMS = ("ball", "pillar", "slab")
RAYS = (96, 54)     # rays across and down a picture (16:9)
WIDE = 3.0          # the field the outline is looked for in, in pictures (to know what falls outside the frame)
IN_FRAME = 0.5      # the least of a solid's outline an angle must hold
SPECK = 0.002       # the least of the picture a solid must cover
HIDDEN = 0.8        # the most of a solid another may cover
TOUCH = 0.05        # studs: solids this near meet
FILLS = 0.05        # of the picture: a solid that covers this much is seen, however much of it runs out of the frame


def checked(solid):
    """a chart's "solid" -> {form, size, at: [x, z], lift}; ValueError in words when it is not one"""
    if not isinstance(solid, dict):
        raise ValueError('"solid" is {"form": "ball" | "pillar" | "slab", "size": studs, "at": [x, z], "lift": studs}')
    extra = sorted(set(solid) - {"form", "size", "at", "lift", "to"})
    if extra:
        raise ValueError(f'"solid" has no "{extra[0]}" (form, size, at, lift, to)')

    def num(v, name, lo, hi):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f'the solid\'s "{name}" is a number from {lo:g} to {hi:g}')
        return float(v)

    if solid.get("form") not in FORMS:
        raise ValueError(f'the solid\'s "form" is one of {", ".join(FORMS)}')
    at = solid.get("at", [0, 0])
    if not (isinstance(at, list) and len(at) == 2):
        raise ValueError('the solid\'s "at" is [x, z] on the ground, in studs from the effect\'s place')
    got = {"form": solid["form"], "size": num(solid.get("size"), "size", 0.5, 400), "at": [num(at[0], "at", -500, 500), num(at[1], "at", -500, 500)],
           "lift": num(solid.get("lift", 0), "lift", 0, 400)}
    if "to" in solid:   # (a solid that says none is the solid it always was: the same plan, the same id)
        to = solid["to"]
        if not (isinstance(to, list) and len(to) == 2):
            raise ValueError('the solid\'s "to" is [x, z]: where it has gone by the end of its beat, on the ground')
        got["to"] = [num(to[0], "to", -500, 500), num(to[1], "to", -500, 500)]
    return got


def box_of(solid):
    """-> (the middle [x, y, z], the size [x, y, z]) of a solid at its full size, in the effect's space (y up)"""
    s = solid["size"]
    size = {"ball": [s, s, s], "pillar": [s / 4.0, s, s / 4.0], "slab": [s, s / 8.0, s]}[solid["form"]]
    return [solid["at"][0], solid["lift"] + size[1] / 2.0, solid["at"][1]], size


def rays_of(view, field=1.0, count=RAYS):
    """the rays of a camera through a grid over `field` pictures -> (its place, their directions [rows, cols, 3])"""
    pos, look = np.array(view["pos"], float), np.array(view["look"], float)
    f = look - pos
    if np.linalg.norm(f) < 1e-6:
        raise ValueError("a camera that looks at its own place sees nothing")
    f = f / np.linalg.norm(f)
    r = np.cross(f, [0.0, 1.0, 0.0])
    if np.linalg.norm(r) < 1e-3:
        raise ValueError("a camera that looks straight up or down is not a gameplay angle (its picture has no 'up')")
    r = r / np.linalg.norm(r)
    u = np.cross(r, f)
    t = math.tan(math.radians(view.get("fov", 66)) / 2.0)
    nx, ny = int(round(count[0] * field)), int(round(count[1] * field))
    xs = (np.arange(nx) + 0.5) / nx * 2 - 1
    ys = 1 - (np.arange(ny) + 0.5) / ny * 2
    x, y = np.meshgrid(xs * field * t * 16.0 / 9.0, ys * field * t)
    d = f[None, None, :] + x[..., None] * r[None, None, :] + y[..., None] * u[None, None, :]
    return pos, d / np.linalg.norm(d, axis=-1, keepdims=True)


def holds(solid, place):
    """is a place INSIDE a solid (a camera there sees none of it)"""
    mid, size = box_of(solid)
    d = np.array(place, float) - np.array(mid)
    half = np.array(size) / 2.0
    if solid["form"] == "ball":
        return bool(d @ d < half[0] ** 2)
    if solid["form"] == "pillar":
        return bool(d[0] ** 2 + d[2] ** 2 < half[0] ** 2 and abs(d[1]) < half[1])
    return bool((np.abs(d) < half).all())


def hit(pos, dirs, solid):
    """where each ray meets a solid: its distance along the ray (inf where it does not). A ball is a sphere, a pillar
    an upright cylinder (as both runtimes draw it), a slab its box"""
    mid, size = box_of(solid)
    mid, half = np.array(mid), np.array(size) / 2.0
    if solid["form"] == "pillar":
        # an upright cylinder: its round side (in x, z) between its two ends, and its two end discs
        oc = pos - mid
        a = dirs[..., 0] ** 2 + dirs[..., 2] ** 2
        b = dirs[..., 0] * oc[0] + dirs[..., 2] * oc[2]
        c = oc[0] ** 2 + oc[2] ** 2 - half[0] ** 2
        disc = b * b - a * c
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (-b - np.sqrt(np.maximum(disc, 0.0))) / a
            side = np.where((a > 1e-12) & (disc > 0) & (t > 0) & (np.abs(oc[1] + t * dirs[..., 1]) <= half[1]), t, np.inf)
            best = side
            for end in (half[1], -half[1]):
                te = (end - oc[1]) / dirs[..., 1]
                x, z = oc[0] + te * dirs[..., 0], oc[2] + te * dirs[..., 2]
                best = np.minimum(best, np.where((np.abs(dirs[..., 1]) > 1e-12) & (te > 0) & (x * x + z * z <= half[0] ** 2), te, np.inf))
        return best
    if solid["form"] == "ball":
        oc = pos - mid
        b = (dirs * oc).sum(-1)
        disc = b * b - (oc @ oc - half[0] ** 2)
        t = -b - np.sqrt(np.maximum(disc, 0.0))
        return np.where((disc > 0) & (t > 0), t, np.inf)
    with np.errstate(divide="ignore", invalid="ignore"):
        a = (mid - half - pos) / dirs
        b = (mid + half - pos) / dirs
    near = np.nanmax(np.minimum(a, b), axis=-1)
    far = np.nanmin(np.maximum(a, b), axis=-1)
    return np.where((far >= near) & (far > 0) & (near > 0), near, np.inf)


def seen(view, solid, others=()):
    """one solid from one camera -> {in_frame, share, hidden, by}: by = the index in `others` of what hides it most"""
    pos, wide = rays_of(view, WIDE)
    out_of = int(np.isfinite(hit(pos, wide, solid)).sum())
    pos, dirs = rays_of(view)
    own = hit(pos, dirs, solid)
    mine = np.isfinite(own)
    inside = int(mine.sum())
    covered, worst, by = np.zeros(mine.shape, bool), 0, None
    for k, other in enumerate(others):
        nearer = mine & (hit(pos, dirs, other) < own)
        covered |= nearer
        if int(nearer.sum()) > worst:
            worst, by = int(nearer.sum()), k
    # is its middle in the picture (a solid too small for any ray to meet is a speck there, not a solid outside it)
    mid = np.array(box_of(solid)[0]) - pos
    toward = dirs[dirs.shape[0] // 2, dirs.shape[1] // 2]
    depth = float(mid @ toward)
    middle = False
    if depth > 0:
        near = np.abs((dirs * (mid / np.linalg.norm(mid))).sum(-1) - 1.0)
        j, i = np.unravel_index(int(np.argmin(near)), near.shape)
        middle = bool(near[j, i] < 1e-4) or (0 < j < dirs.shape[0] - 1 and 0 < i < dirs.shape[1] - 1)
    # the wide field has WIDE x WIDE as many rays over WIDE x WIDE as much: one ray weighs the same in both
    return {"middle": middle, "in_frame": round(min(1.0, inside / out_of), 3) if out_of else 0.0, "share": round(inside / mine.size, 4),
            "hidden": round(int(covered.sum()) / inside, 3) if inside else 0.0, "by": by}


def touching(a, b):
    """do two solids meet (their boxes within TOUCH of each other)"""
    (ma, sa), (mb, sb) = box_of(a), box_of(b)
    return all(abs(ma[k] - mb[k]) <= (sa[k] + sb[k]) / 2.0 + TOUCH for k in range(3))


def placed(solid, u):
    """a solid where it is at `u` of its beat's life (0 at its start .. 1 at its end): on its way from "at" to "to".
    One that says no "to" stands where it stands"""
    to = solid.get("to")
    if not to:
        return solid
    u = min(max(float(u), 0.0), 1.0)
    there = dict(solid)
    there["at"] = [solid["at"][0] + (to[0] - solid["at"][0]) * u, solid["at"][1] + (to[1] - solid["at"][1]) * u]
    return there


def travel(solid):
    """how far a solid goes over its beat, in studs (0 for one that stands)"""
    to = solid.get("to")
    return math.hypot(to[0] - solid["at"][0], to[1] - solid["at"][1]) if to else 0.0


def project(view, point):
    """where a place is in a camera's picture -> [x, y], each -1 .. 1 across the picture (x right, y up; outside
    that = outside the picture), or None for a place behind the camera"""
    pos, look = np.array(view["pos"], float), np.array(view["look"], float)
    f = (look - pos) / np.linalg.norm(look - pos)
    r = np.cross(f, [0.0, 1.0, 0.0])
    r = r / np.linalg.norm(r)
    u = np.cross(r, f)
    d = np.array(point, float) - pos
    depth = float(d @ f)
    if depth <= 1e-6:
        return None
    t = math.tan(math.radians(view.get("fov", 66)) / 2.0)
    return [round(float(d @ r) / depth / (t * 16.0 / 9.0), 3), round(float(d @ u) / depth / t, 3)]


# where in its life a moving solid is looked at: eleven moments, evenly, from its start to its end (three - start,
# middle, end - let a ball pass behind a pillar, and touch it, between two looks: a review)
MOMENTS = tuple((round(0.02 + 0.096 * k, 3), {0: "at its start", 5: "at its middle", 10: "at its end"}.get(k, f"{int(round((0.02 + 0.096 * k) * 100))} % of its way along"))
                for k in range(11))


def fault(got, solid, view, what, by):
    """what an angle cannot show of a solid, in words - or None"""
    if holds(solid, view["pos"]):
        return f"{what}: the camera is INSIDE it (a smaller size, or an \"at\" away from the camera)"
    if got["share"] == 0 and got["middle"]:
        return f"{what}: it is too small to see from there, a speck (under {SPECK} of the picture: a larger size)"
    if got["share"] == 0 and got["in_frame"] == 0:
        return f"{what}: none of it is in the picture (move its \"at\", or name another angle)"
    if got["in_frame"] < IN_FRAME and got["share"] < FILLS:   # (a sky beam, a wide crater: most of it is outside and it still fills the picture)
        return f"{what}: only {got['in_frame']:.2f} of it is in the picture, under {IN_FRAME} (a smaller size, or an \"at\" nearer the middle)"
    if got["share"] < SPECK:
        return f"{what}: it covers {got['share']:.4f} of the picture, a speck (under {SPECK}: a larger size)"
    if got["hidden"] > HIDDEN:
        return f"{what}: {got['hidden']:.2f} of it is hidden behind beat {by} (over {HIDDEN}: move one of them, or stagger their times)"
    return None


def angles(rows, views):
    """every solid beat from every angle. rows: the animatic's rows ({"index", "beat", "t", "life", "solid"?});
    views: {name: {"pos", "look", "fov"}} -> ({angle: [{beat, index, in_frame, share, hidden, by, grounded, touches}]},
    the problems in words).
    FLOW (a chart in which a solid says "to": it MOVES over its beat): every solid is then looked at at eleven moments
    of its beat, from its start to its end, with every other solid where IT is at that very moment. What the row
    says is the worst of them, and it gains "flow": how far the solid goes, where its middle is in the picture at
    its start and at its end (so the way it crosses the frame can be read), the most of the picture it covers on
    the way, and every look. A solid an angle loses at one of those moments stops the run, saying at which; what
    happens BETWEEN two looks (under a tenth of the beat) is not seen. A chart in which nothing moves is checked as
    it always was"""
    solids = [r for r in rows if r.get("solid")]
    moving = any(r["solid"].get("to") for r in solids)
    report, problems = {}, []
    for name, view in views.items():
        report[name] = []
        try:
            rays_of(view)
        except ValueError as e:
            problems.append(f"the {name} angle: {e}")
            continue
        for r in solids:
            what = f"beat {r['beat']} (a {r['solid']['form']} of {r['solid']['size']:g} studs) from the {name} angle"
            if not moving:
                # what is alive at the same moment (their stretches of the chart overlap)
                live = [o for o in solids if o is not r and o["t"] < r["t"] + r["life"] and r["t"] < o["t"] + o["life"]]
                got = seen(view, r["solid"], [o["solid"] for o in live])
                by = live[got["by"]] if got["by"] is not None else None
                row = {"beat": r["beat"], "index": r["index"], "in_frame": got["in_frame"], "share": got["share"], "hidden": got["hidden"],
                       "by": by["beat"] if by else None, "grounded": r["solid"]["lift"] == 0,
                       "touches": [o["beat"] for o in live if touching(r["solid"], o["solid"])]}
                report[name].append(row)
                said = fault(got, r["solid"], view, what, row["by"])
                if said:
                    problems.append(said)
                continue
            looks, touches, said = [], [], None
            for u, moment in MOMENTS:
                now = r["t"] + u * r["life"]
                live = [o for o in solids if o is not r and o["t"] <= now < o["t"] + o["life"]]
                theirs = [placed(o["solid"], (now - o["t"]) / o["life"]) for o in live]
                mine = placed(r["solid"], u)
                got = seen(view, mine, theirs)
                by = live[got["by"]]["beat"] if got["by"] is not None else None
                looks.append({"at": moment, "in_frame": got["in_frame"], "share": got["share"], "hidden": got["hidden"], "by": by})
                for o, s in zip(live, theirs):
                    if touching(mine, s) and o["beat"] not in touches:
                        touches.append(o["beat"])
                said = said or fault(got, mine, view, f"{what}, {moment}", by)
            worst = max(looks, key=lambda g: g["hidden"])
            row = {"beat": r["beat"], "index": r["index"], "in_frame": min(g["in_frame"] for g in looks), "share": min(g["share"] for g in looks),
                   "hidden": worst["hidden"], "by": worst["by"], "grounded": r["solid"]["lift"] == 0, "touches": touches,
                   "flow": {"travel": round(travel(r["solid"]), 3), "from": project(view, box_of(placed(r["solid"], 0))[0]),
                            "to": project(view, box_of(placed(r["solid"], 1))[0]), "most": max(g["share"] for g in looks), "looks": looks}}
            report[name].append(row)
            if said:
                problems.append(said)
    return report, problems


# ---------------------------------------------------------------------------------------------- the solids, DRAWN
# The film of an animatic is the browser player's, and the player draws a solid as flat glowing colour: no volume, and
# nothing hidden behind anything. So the solids are drawn HERE, by the same rays the checks use: each ray takes the
# nearest thing it meets - what is behind is hidden, as in Roblox, where they are opaque - a surface is lit by where it
# faces, and the ground under a solid that touches it is dark. From ANY camera: the animatic's own view and every
# gameplay angle, as stills (`sheet`) and in motion (`film`). It is a drawing of the BLOCKING - three plain forms on a
# flat ground - not of the effect.
LIGHT = np.array([-0.45, 0.8, 0.4]) / np.linalg.norm([-0.45, 0.8, 0.4])
PALETTE = ((255, 150, 60), (90, 170, 255), (120, 220, 130), (235, 100, 180), (240, 220, 90), (170, 130, 255))


def normals(pos, dirs, t, solid):
    """the way the surface faces where each ray meets a solid ([rows, cols, 3]; anything where it does not)"""
    mid, size = box_of(solid)
    mid, half = np.array(mid), np.array(size) / 2.0
    with np.errstate(invalid="ignore"):
        d = pos + dirs * np.where(np.isfinite(t), t, 0.0)[..., None] - mid
    if solid["form"] == "ball":
        return d / max(half[0], 1e-9)
    if solid["form"] == "pillar":
        cap = np.abs(np.abs(d[..., 1]) - half[1]) < 1e-4 * max(1.0, half[1])
        side = np.stack([d[..., 0], np.zeros_like(d[..., 0]), d[..., 2]], -1) / max(half[0], 1e-9)
        ends = np.stack([np.zeros_like(d[..., 0]), np.sign(d[..., 1]), np.zeros_like(d[..., 0])], -1)
        return np.where(cap[..., None], ends, side)
    rel = np.abs(d) / np.maximum(half, 1e-9)
    axis = np.argmax(rel, -1)
    n = np.zeros_like(d)
    for k in range(3):
        n[..., k] = np.where(axis == k, np.sign(d[..., k]), 0.0)
    return n


def picture(view, solids, colours=None, size=(480, 270)):
    """the solids from one camera, as a picture [h, w, 3] uint8: lit, the nearer hiding the farther, on the ground"""
    pos, dirs = rays_of(view, 1.0, size)
    h, w = dirs.shape[:2]
    up = np.clip(dirs[..., 1], -1, 1)
    img = np.stack([20 + 26 * (up + 1) / 2, 24 + 34 * (up + 1) / 2, 34 + 52 * (up + 1) / 2], -1)   # the sky: darker low
    with np.errstate(divide="ignore", invalid="ignore"):
        tg = np.where(dirs[..., 1] < -1e-6, -pos[1] / dirs[..., 1], np.inf)
    on = np.isfinite(tg) & (tg > 0)
    gp = pos + dirs * np.where(on, tg, 0.0)[..., None]
    check = (np.floor(gp[..., 0] / 4.0) + np.floor(gp[..., 2] / 4.0)) % 2
    fade = 1.0 / (1.0 + np.where(on, tg, 0.0) / 160.0)
    shade = np.ones((h, w))
    for s in solids:                                   # the ground is dark under what stands on it (its contact)
        mid, sz = box_of(s)
        reach = max(sz[0], sz[2]) / 2.0
        dist = np.hypot(gp[..., 0] - mid[0], gp[..., 2] - mid[2]) / max(reach, 1e-9)
        shade = np.minimum(shade, 1.0 - 0.6 * np.clip(1.6 - dist, 0, 1) / (1.0 + s["lift"] / max(reach, 1e-9) * 2.0))
    ground = (46 + 16 * check) * fade * shade
    img = np.where(on[..., None], np.stack([ground * 0.92, ground * 0.96, ground * 1.08], -1), img)
    depth = np.where(on, tg, np.inf)
    for k, s in enumerate(solids):
        t = hit(pos, dirs, s)
        nearer = t < depth
        if not nearer.any():
            continue
        n = normals(pos, dirs, t, s)
        lit = 0.32 + 0.68 * np.clip((n * LIGHT).sum(-1), 0, 1)
        rim = 0.18 * np.clip(1.0 + (n * dirs).sum(-1), 0, 1) ** 2          # a little light at the edge: the form reads
        colour = np.array((colours or {}).get(k, PALETTE[k % len(PALETTE)]), float)
        img = np.where(nearer[..., None], np.clip(colour[None, None, :] * lit[..., None] + 255 * rim[..., None], 0, 255), img)
        depth = np.where(nearer, t, depth)
    return np.clip(img, 0, 255).astype(np.uint8)


def alive(rows, now):
    """the solids that stand at a moment of the chart, each where it is then -> [(row, its solid placed)]"""
    out = []
    for r in rows:
        if r.get("solid") and r["t"] <= now < r["t"] + r["life"]:
            out.append((r, placed(r["solid"], (now - r["t"]) / r["life"])))
    return out


def tile(view, name, rows, now, colours, size, note=""):
    """one camera at one moment, with its name and the moment written on it -> a PIL image"""
    from PIL import Image, ImageDraw
    live = alive(rows, now)
    img = Image.fromarray(picture(view, [s for _, s in live], {k: colours.get(r["index"]) or PALETTE[r["index"] % len(PALETTE)]
                                                             for k, (r, _) in enumerate(live)}, size))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size[0], 15], fill=(0, 0, 0))
    draw.text((4, 2), f"{name} | {now:.2f} s | {note}"[: size[0] // 6], fill=(235, 235, 235))
    return img


def sheet(rows, views, dest, colours=None, size=(480, 270)):
    """every solid beat (down) from every angle (across), at the middle of its beat, with what stands beside it then:
    its volume, what hides it, where it touches the ground -> the PNG's path, or None when there is no solid beat"""
    from PIL import Image
    solids = [r for r in rows if r.get("solid")]
    if not solids or not views:
        return None
    names = list(views)
    out = Image.new("RGB", (size[0] * len(names), size[1] * len(solids)), (0, 0, 0))
    for j, r in enumerate(solids):
        now = r["t"] + r["life"] / 2.0
        for i, n in enumerate(names):
            out.paste(tile(views[n], n, rows, now, colours or {}, size, f"beat {r['beat']}"), (i * size[0], j * size[1]))
    out.save(dest)
    return dest


def film(rows, views, dest, duration, colours=None, fps=8, size=(320, 180)):
    """the solids IN MOTION from every angle at once (the angles side by side, two a row), on the chart's own clock:
    each stands for its beat's stretch and goes its way -> whether the video was written (ffmpeg)"""
    import shutil
    import subprocess
    from PIL import Image
    names = list(views)
    if not names or not any(r.get("solid") for r in rows) or not shutil.which("ffmpeg"):
        return False
    cols = 1 if len(names) == 1 else 2
    lines = (len(names) + cols - 1) // cols
    w, h = size[0] * cols, size[1] * lines
    pipe = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", dest],
                            stdin=subprocess.PIPE)
    try:
        last, held = None, None
        for f in range(max(1, int(round(duration * fps)))):
            now = f / fps
            # (a frame in which nothing stands where it did not a frame ago is the frame before, with its clock: a still
            # scene is not drawn again - one picture is over half a second of rays)
            state = [(r["index"], s["at"]) for r, s in alive(rows, now)]
            if state != last or held is None:
                last, held = state, [tile(views[n], n, rows, now, colours or {}, size) for n in names]
            frame = Image.new("RGB", (w, h), (0, 0, 0))
            for k, n in enumerate(names):
                frame.paste(held[k], ((k % cols) * size[0], (k // cols) * size[1]))
            pipe.stdin.write(frame.tobytes())
        pipe.stdin.close()
        pipe.wait(timeout=600)
    except BaseException:
        pipe.kill()
        pipe.wait()
        raise
    import os
    return pipe.returncode == 0 and os.path.isfile(dest)
