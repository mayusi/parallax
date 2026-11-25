"""modkit.py - W3, THE MODULAR GOTHIC KIT (LIMITATIONS_FIXES_V4 5.1 / 5.4 step 2 / 13.5: "a 15-20 piece modular PBR
MeshPart kit + <= 3 shared 1024 trims"; smoking gun 1: GothicCourtyard compiles 1,094 plain Parts, 0 MeshParts).

Eighteen pieces a gothic street is built from, each a real mesh (bevelled where an edge catches light) mapped onto
the two shared trim sheets of kit/world/trims.py at 64 px/stud:
  bay pieces (their width a whole number of GRID-stud bays, one storey FLOOR studs tall):
    wall_4, wall_8, lancet_4 (a pointed window, its glass and iron mullion set back in the reveal), twin_lancet_8,
    portal_8 (a pointed doorway 5 wide and 9.6 high to its apex: the owner's R6 rig walks it; oak boards set back)
  bands and edges: plinth_4 (a rusticated base course), string_4 (a moulded band), cornice_4, parapet_4
    (crenellated, coped), quoin (long-and-short corner blocks, one storey), pilaster, buttress (stepped, weathered)
  roof and top: roof_4 (a slate slope), ridge_4, gable_16 (a gable end), dormer, chimney
  ground: cobble_4 (a 4 x 4 sett slab)
Frame: Roblox's (x along the wall from its left end, y up from the storey's floor, z out of the wall toward the
street: the wall's front face at z = 0, its back at z = -WALL). A module is { name, size, grid, kind, sockets,
parts: [{ sheet, verts, faces, uvs }] } - one part a sheet (a MeshPart takes one SurfaceAppearance).
check(kit) is the kit's gate: every face at 35..70 px/stud, every uv inside its strip's rows, at most 3 sheets / 15
maps, every bay piece a whole number of bays, a doorway the R6 rig fits, triangles under MAX_TRIS a piece.
Pure numpy. kit/world/facade_grammar.py puts houses together from it.
Not here: the upload (each part becomes a MeshPart only when uploaded: the owner's), LOD meshes, and collision (the
compiler's invisible hulls stay the collision, as with a skin)."""
import math
import os

import numpy as np

import trims

GRID = 4.0  # studs: a bay
FLOOR = 14.0  # studs floor to floor (the owner's R6 rig: 13 clear under a 1-stud slab)
WALL = 1.2  # studs: a wall's thickness
MAX_TRIS = 4000
DENSITY = (35.0, 70.0)  # px a stud, the V4 bar
DOOR_MIN = (4.5, 8.5)  # studs: the R6 rig's doorway (wide, high)
INSET_PX = 2  # a uv stays this many px inside its strip's rows (no bleed into the next strip at a mip)


class Mesh:
    def __init__(self):
        self.v, self.f, self.uv = [], [], []

    def poly(self, pts, strip, uaxis, vaxis, flip=False):
        """a planar convex-or-fan polygon (points in order), mapped onto `strip` by planar projection: u along
        `uaxis` at 64 px/stud (wrapping), v along `vaxis` (studs up the strip from the polygon's lowest point);
        a polygon taller than its strip is cut into bands first"""
        pts = [np.asarray(p, float) for p in pts]
        if len(pts) < 3 or np.linalg.norm(sum(np.cross(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))) < 1e-9:
            return  # (a polygon of no area - a panel of no width beside an opening as wide as its module - is no face)
        ua, va = np.asarray(uaxis, float), np.asarray(vaxis, float)
        vs = [float(p @ va) for p in pts]
        lo, hi = min(vs), max(vs)
        sh = trims.strip_studs(strip) - 2 * INSET_PX / trims.PX  # (what of the strip a face may use: inside the inset)
        course = trims.COURSE.get(strip)
        if course:
            sh = math.floor(sh / course + 1e-9) * course  # (whole courses: bands on one grid for every module)
        b = math.floor(lo / sh + 1e-9)
        if hi > (b + 1) * sh + 1e-6:
            # bands on the absolute grid k * sh: clip the polygon between band lines
            k = b
            while k * sh < hi - 1e-9:
                band = _clip(_clip(pts, va, max(lo, k * sh), True), va, min(hi, (k + 1) * sh), False)
                if len(band) >= 3:
                    self.poly(band, strip, ua, va, flip)
                k += 1
            return
        lo = b * sh if course else lo  # (v measured from the band's line: courses line up across modules)
        sheet, top, hpx = trims.STRIPS[strip]
        i0 = len(self.v)
        for p, vv in zip(pts, vs):
            u = float(p @ ua) / trims.SPAN
            row = top + hpx - INSET_PX - (vv - lo) * trims.PX  # (px from the sheet's top)
            row = min(max(row, top + INSET_PX), top + hpx - INSET_PX)
            self.v.append(tuple(float(c) for c in p))
            self.uv.append((u, 1.0 - row / trims.SHEET))
        for j in range(1, len(pts) - 1):
            tri = (i0, i0 + j, i0 + j + 1)
            self.f.append((tri[0], tri[2], tri[1]) if flip else tri)

    def quad(self, a, b, c, d, strip, uaxis, vaxis):
        self.poly([a, b, c, d], strip, uaxis, vaxis)

    def box(self, x0, x1, y0, y1, z0, z1, strip, faces="all", bevel=0.0, top_strip=None):
        """an axis box (bevelled on its front vertical and top edges when bevel > 0), its six faces outward"""
        X, Y, Z = np.eye(3)
        b = bevel
        want = set("lrbtfk") if faces == "all" else set(faces)
        if "f" in want:  # front (+z)
            self.quad((x0 + b, y0, z1), (x1 - b, y0, z1), (x1 - b, y1 - b, z1), (x0 + b, y1 - b, z1), strip, X, Y)
        if "k" in want:  # back (-z)
            self.quad((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), strip, -X, Y)
        if "l" in want:  # left (-x)
            self.quad((x0, y0, z0), (x0, y0, z1 - b), (x0, y1 - b, z1 - b), (x0, y1, z0), strip, Z, Y)
        if "r" in want:
            self.quad((x1, y0, z1 - b), (x1, y0, z0), (x1, y1, z0), (x1, y1 - b, z1 - b), strip, -Z, Y)
        if "t" in want:
            ts = top_strip or strip
            self.quad((x0, y1, z1 - b), (x1, y1, z1 - b), (x1, y1, z0), (x0, y1, z0), ts, X, -Z)
        if "b" in want:
            self.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), strip, X, Z)
        if b > 0:
            s = 1 / math.sqrt(2)
            if "f" in want:
                # the chamfers: front-top, front-left, front-right (45 degrees)
                self.quad((x0 + b, y1 - b, z1), (x1 - b, y1 - b, z1), (x1, y1, z1 - b), (x0, y1, z1 - b), strip, X, np.array([0, s, -s]))
                self.quad((x0, y0, z1 - b), (x0 + b, y0, z1), (x0 + b, y1 - b, z1), (x0, y1, z1 - b), strip, np.array([s, 0, s]), Y)
                self.quad((x1 - b, y0, z1), (x1, y0, z1 - b), (x1, y1, z1 - b), (x1 - b, y1 - b, z1), strip, np.array([s, 0, -s]), Y)

    def tri_area_density(self):
        """per triangle: (world area in square studs, px a stud)"""
        out = []
        V, U = np.array(self.v), np.array(self.uv) * trims.SHEET
        for a, b, c in self.f:
            wa = 0.5 * np.linalg.norm(np.cross(V[b] - V[a], V[c] - V[a]))
            e1, e2 = U[b] - U[a], U[c] - U[a]
            ua = 0.5 * abs(e1[0] * e2[1] - e1[1] * e2[0])
            out.append((wa, math.sqrt(ua / wa) if wa > 1e-9 else 0.0))
        return out


def _clip(pts, axis, at, keep_above):
    """Sutherland-Hodgman: the polygon's part with p . axis >= at (keep_above) or <= at"""
    out = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        fp, fq = float(p @ axis) - at, float(q @ axis) - at
        if not keep_above:
            fp, fq = -fp, -fq
        if fp >= -1e-12:
            out.append(p)
        if (fp >= -1e-12) != (fq >= -1e-12) and abs(fp - fq) > 1e-12:
            t = fp / (fp - fq)
            out.append(p + (q - p) * t)
    return out


def _arch(cx, half, spring, n=8):
    """a POINTED (equilateral) arch's intrados from the left spring to the right one: [(x, y)]"""
    r = 2 * half
    pts = []
    # the left arc is centred on the right spring point and the right arc on the left one
    a_top = math.acos(half / r)  # (60 degrees for an equilateral arch: each arc turns this far from its spring)
    for k in range(n + 1):  # (the left arc: 180 degrees round to 180 - a_top, where it meets the right one at cx)
        a = math.pi - a_top * k / n
        pts.append((cx + half + r * math.cos(a), spring + r * math.sin(a)))
    for k in range(1, n + 1):
        a = a_top - a_top * k / n
        pts.append((cx - half + r * math.cos(a), spring + r * math.sin(a)))
    return pts


def _opening(m, x0, x1, h, cx, half, sill, spring, front_strip="ashlar", reveal_strip="moulding", depth=None):
    """a wall panel x0..x1, 0..h, with a pointed opening (half-width `half`, its sill at `sill`, arch springing at
    `spring`) cut through it: the front and back faces round the hole, the reveal (jambs, sill, soffit). depth: the
    panel's thickness (WALL)"""
    WALL = globals()["WALL"] if depth is None else depth  # noqa: N806
    X, Y, Z = np.eye(3)
    arch = _arch(cx, half, spring)
    apex = max(p[1] for p in arch)
    L, R = cx - half, cx + half
    for z, sign in ((0.0, 1), (-WALL, -1)):
        ua = X if sign > 0 else -X

        def P(x, y):
            return (x, y, z)

        def put(pts):
            pts = pts if sign > 0 else pts[::-1]
            m.poly([P(*q) for q in pts], front_strip, ua, Y)

        put([(x0, 0), (L, 0), (L, spring), (x0, spring)][::1] if False else [(x0, 0), (L, 0), (L, spring), (x0, spring)])
        put([(R, 0), (x1, 0), (x1, spring), (R, spring)])
        if sill > 0:
            put([(L, 0), (R, 0), (R, sill), (L, sill)])
        put([(x0, spring), (L, spring), (L, h), (x0, h)])
        put([(R, spring), (x1, spring), (x1, h), (R, h)])
        put([(L, apex), (R, apex), (R, h), (L, h)])
        # the spandrels between the arch and the apex line: fans from the apex line's ends
        left = [p for p in arch if p[0] <= cx + 1e-9]
        right = [p for p in arch if p[0] >= cx - 1e-9]
        for a, b in zip(left[:-1], left[1:]):
            put([(L, apex), a, b] if sign > 0 else [(L, apex), a, b])
        for a, b in zip(right[:-1], right[1:]):
            put([(R, apex), a, b])
    # the reveal: jambs, the sill, the soffit along the arch (faces looking into the opening)
    ring = [(L, sill)] + arch + [(R, sill)]
    for (ax, ay), (bx, by) in zip(ring[:-1], ring[1:]):
        p0, p1, p2, p3 = (ax, ay, 0.0), (bx, by, 0.0), (bx, by, -WALL), (ax, ay, -WALL)
        d = np.array([bx - ax, by - ay, 0.0])
        ln = np.linalg.norm(d)
        if ln < 1e-9:
            continue
        m.poly([p0, p3, p2, p1], reveal_strip, d / ln, -Z)
    if sill > 0:
        m.poly([(L, sill, 0.0), (R, sill, 0.0), (R, sill, -WALL), (L, sill, -WALL)], reveal_strip, X, -Z)
    return apex


def _module(name, kind, size, grid, parts, sockets=None, extra=None):
    out = {"name": name, "kind": kind, "size": [float(s) for s in size], "grid": grid, "parts": [], "sockets": sockets or {}}
    for sheet, m in parts:
        out["parts"].append({"sheet": sheet, "verts": m.v, "faces": m.f, "uvs": m.uv})
    if extra:
        out.update(extra)
    return out


def _bay_sockets(w):
    return {"left": [0.0, 0.0, 0.0], "right": [w, 0.0, 0.0], "up": [0.0, FLOOR, 0.0]}


def wall(w):
    m = Mesh()
    m.box(0, w, 0, FLOOR, -WALL, 0, "ashlar", faces="fk")
    m.box(0, w, 0, FLOOR, -WALL, 0, "moulding", faces="t")
    return _module(f"wall_{int(w)}", "bay", (w, FLOOR, WALL), int(w / GRID), [("stone", m)], _bay_sockets(w))


def lancet(w=4.0, twin=False):
    stone, glass = Mesh(), Mesh()
    X, Y = np.eye(3)[0], np.eye(3)[1]
    centres = [w / 4, 3 * w / 4] if twin else [w / 2]
    half, sill, spring = 1.1, 3.5, 9.0
    # (one hole a panel: a twin lancet is two panels side by side, each with its own opening)
    seg = w / len(centres)
    for k, cx in enumerate(centres):
        apex = _opening(stone, k * seg, (k + 1) * seg, FLOOR, cx, half, sill, spring)
        # the glass set back in the reveal, the iron mullion and transom in front of it
        zg = -WALL * 0.6
        ring = [(cx - half, sill)] + _arch(cx, half, spring) + [(cx + half, sill)]
        glass.poly([(x, y, zg) for x, y in ring[::-1]][::-1], "glass", X, Y)
        glass.box(cx - 0.08, cx + 0.08, sill, apex - 0.4, zg, zg + 0.16, "iron")
        glass.box(cx - half, cx + half, spring - 0.08, spring + 0.08, zg, zg + 0.16, "iron")
    stone.box(0, w, 0, FLOOR, -WALL, 0, "moulding", faces="t")
    name = "twin_lancet_8" if twin else "lancet_4"
    return _module(name, "bay", (w, FLOOR, WALL), int(w / GRID), [("stone", stone), ("roof", glass)], _bay_sockets(w),
                   {"opening": {"width": 2 * half, "sill": sill, "apex": round(spring + 2 * half * math.sin(math.radians(60)), 3)}})


def portal(w=8.0):
    stone, wood = Mesh(), Mesh()
    X, Y = np.eye(3)[0], np.eye(3)[1]
    half, spring = 2.5, 5.3
    apex = _opening(stone, 0, w, FLOOR, w / 2, half, 0.0, spring, reveal_strip="quoin")
    # the oak door in two leaves set back, iron straps across it
    zd = -WALL + 0.25
    ring = [(w / 2 - half, 0)] + _arch(w / 2, half, spring) + [(w / 2 + half, 0)]
    wood.poly([(x, y, zd) for x, y in ring], "oak", X, Y)
    for y in (1.5, 4.0):
        wood.box(w / 2 - half, w / 2 + half, y, y + 0.25, zd, zd + 0.1, "iron")
    # the hood moulding over the arch: a drip stone between two arches (0.1 and 0.7 outside the opening's), standing
    # 0.35 proud, its outer edge closed
    inner, outer = _arch(w / 2, half + 0.1, spring), _arch(w / 2, half + 0.7, spring)
    Z = np.array([0, 0, 1.0])
    for (a, b), (c, d) in zip(zip(inner[:-1], inner[1:]), zip(outer[:-1], outer[1:])):
        a0, b0 = np.array([a[0], a[1], 0.35]), np.array([b[0], b[1], 0.35])
        c0, d0 = np.array([c[0], c[1], 0.35]), np.array([d[0], d[1], 0.35])
        t = b0 - a0
        t /= np.linalg.norm(t)
        out = np.array([-t[1], t[0], 0.0])
        if out @ (c0 - a0) < 0:
            out = -out
        stone.poly([a0, b0, d0, c0] if np.cross(b0 - a0, c0 - a0)[2] > 0 else [a0, c0, d0, b0], "moulding", t, out)
        stone.poly([c0, d0, d0 - Z * 0.35, c0 - Z * 0.35] if out @ np.cross(d0 - c0, -Z) > 0 else [c0, c0 - Z * 0.35, d0 - Z * 0.35, d0], "moulding", t, -Z)
    stone.box(0, w, 0, FLOOR, -WALL, 0, "moulding", faces="t")
    return _module("portal_8", "bay", (w, FLOOR, WALL), 2, [("stone", stone), ("roof", wood)], _bay_sockets(w),
                   {"opening": {"width": 2 * half, "sill": 0.0, "apex": round(apex, 3)}})


def band(name, h, out, strip, w=GRID, step=None):
    """a horizontal band across a bay (a plinth, a string course, a cornice): a bevelled box standing `out` proud"""
    m = Mesh()
    m.box(0, w, 0, h, -WALL, out, strip, faces="ftb", bevel=min(0.15, h / 4))
    if step:  # a cornice's second, deeper course on top
        m.box(0, w, h, h + step[0], -WALL, out + step[1], strip, faces="ftb", bevel=0.1)
    return _module(name, "band", (w, h + (step[0] if step else 0), WALL + out + (step[1] if step else 0)), 1, [("stone", m)],
                   {"left": [0.0, 0.0, 0.0], "right": [w, 0.0, 0.0]})


def parapet(w=GRID):
    m = Mesh()
    m.box(0, w, 0, 1.6, -WALL, 0, "ashlar", faces="fkt", top_strip="moulding")
    # one merlon a bay: 2 studs of wall, 2 of crenel
    m.box(0, 2, 1.6, 3.6, -WALL, 0, "ashlar", faces="fkt", top_strip="moulding")
    m.box(0, 2, 1.6, 3.6, -WALL, 0, "ashlar", faces="lr")
    return _module("parapet_4", "top", (w, 3.6, WALL), 1, [("stone", m)], {"left": [0.0, 0.0, 0.0], "right": [w, 0.0, 0.0]})


def quoin():
    """long-and-short blocks up a corner, one storey: alternately 2.6 along the wall and 1.6, standing 0.15 proud,
    wrapping round the corner (x = 0 is the corner, the return face runs back along -z)"""
    m = Mesh()
    y, k = 0.0, 0
    while y < FLOOR - 1e-6:
        h = min(2.0, FLOOR - y)
        a = 2.6 if k % 2 == 0 else 1.6
        b = 1.6 if k % 2 == 0 else 2.6
        m.box(-0.15, a, y, y + h - 0.08, -0.6, 0.15, "quoin", faces="ftb", bevel=0.08)
        m.box(-0.15, 0.6, y, y + h - 0.08, -b, 0.15, "quoin", faces="lb", bevel=0.0)
        y += h
        k += 1
    return _module("quoin", "corner", (2.75, FLOOR, 2.75), 0, [("stone", m)], {"corner": [0.0, 0.0, 0.0]})


def pilaster():
    m = Mesh()
    m.box(0, 1.2, 0, FLOOR, -WALL, 0.4, "quoin", faces="flrt", bevel=0.1)
    return _module("pilaster", "edge", (1.2, FLOOR, WALL + 0.4), 0, [("stone", m)], {"foot": [0.6, 0.0, 0.0]})


def buttress():
    m = Mesh()
    m.box(0, 2, 0, 8, -WALL, 3.0, "ashlar", faces="flrt", bevel=0.12, top_strip="moulding")
    m.box(0.25, 1.75, 8, FLOOR, -WALL, 1.5, "ashlar", faces="flr", bevel=0.1)
    # the weathering: a slope shedding water off the lower stage, a cap on the upper
    X, Y, Z = np.eye(3)
    s = 1 / math.sqrt(2)
    m.poly([(0, 8, 3.0), (2, 8, 3.0), (2, 9.5, 1.5), (0, 9.5, 1.5)], "moulding", X, np.array([0, s, -s]))
    m.box(0.25, 1.75, FLOOR, FLOOR + 0.6, -WALL, 1.8, "moulding", faces="flrt", bevel=0.1)
    return _module("buttress", "edge", (2.0, FLOOR + 0.6, WALL + 3.0), 0, [("stone", m)], {"foot": [1.0, 0.0, 0.0]})


def roof(w=GRID, run=10.0, pitch=45.0):
    """a slate slope a bay wide: from the eaves (z = 0.8 out, y = 0) up to the ridge, 0.5 thick"""
    m = Mesh()
    X = np.eye(3)[0]
    c, s = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    rise = run * math.tan(math.radians(pitch))
    up = np.array([0, s, -c])  # along the slope toward the ridge
    nrm = np.array([0, c, s])
    e0 = np.array([0, 0, 0.8])
    e1 = e0 + up * (run + 0.8) / c
    for o, strip in ((0.5, "slate"), (0.0, "slate")):
        off = nrm * o
        pts = [e0 + off, e0 + [w, 0, 0] + off, e1 + [w, 0, 0] + off, e1 + off]
        m.poly(pts if o > 0 else pts[::-1], strip, X, up if o > 0 else up)
    m.poly([e0, e0 + [w, 0, 0], e0 + [w, 0, 0] + nrm * 0.5, e0 + nrm * 0.5], "beam", X, nrm)  # (the eaves' edge)
    return _module("roof_4", "roof", (w, rise + 1, run + 0.8), 1, [("roof", m)], {"left": [0.0, 0.0, 0.0], "right": [w, 0.0, 0.0]},
                   {"rise": round(rise, 3), "run": run})


def ridge(w=GRID):
    m = Mesh()
    X = np.eye(3)[0]
    s = 1 / math.sqrt(2)
    m.poly([(0, 0, 0.6), (w, 0, 0.6), (w, 0.6, 0), (0, 0.6, 0)], "iron", X, np.array([0, s, -s]))
    m.poly([(0, 0.6, 0), (w, 0.6, 0), (w, 0, -0.6), (0, 0, -0.6)], "iron", X, np.array([0, -s, -s]))
    return _module("ridge_4", "roof", (w, 0.6, 1.2), 1, [("roof", m)], {"left": [0.0, 0.0, 0.0], "right": [w, 0.0, 0.0]})


def gable(span=16.0, rise=8.0):
    m = Mesh()
    X, Y = np.eye(3)[0], np.eye(3)[1]
    m.poly([(0, 0, 0), (span, 0, 0), (span / 2, rise, 0)], "ashlar", X, Y)
    m.poly([(span, 0, -WALL), (0, 0, -WALL), (span / 2, rise, -WALL)], "ashlar", -X, Y)
    # the coping along both rakes
    for a, b in (((0, 0), (span / 2, rise)), ((span / 2, rise), (span, 0))):
        d = np.array([b[0] - a[0], b[1] - a[1], 0.0])
        d /= np.linalg.norm(d)
        p, q = np.array([a[0], a[1], 0.3]), np.array([b[0], b[1], 0.3])
        m.poly([p, q, q + [0, 0.5, 0], p + [0, 0.5, 0]], "moulding", d, Y)
        m.poly([p + [0, 0.5, 0], q + [0, 0.5, 0], q + [0, 0.5, -WALL - 0.6], p + [0, 0.5, -WALL - 0.6]], "moulding", d, np.array([0, 0, -1.0]))
    return _module("gable_16", "gable", (span, rise + 0.5, WALL + 0.3), 4, [("stone", m)], {"left": [0.0, 0.0, 0.0], "right": [span, 0.0, 0.0]})


def dormer():
    stone, slate = Mesh(), Mesh()
    X, Y, Z = np.eye(3)
    _opening(stone, 0, 4, 5.0, 2.0, 0.9, 0.6, 2.6)
    for x in (0.0, 4.0):  # the cheeks in oak
        slate.poly([(x, 0, 0), (x, 0, -3), (x, 5, -3), (x, 5, 0)] if x == 0 else [(x, 0, -3), (x, 0, 0), (x, 5, 0), (x, 5, -3)], "oak", -Z if x == 0 else Z, Y)
    s = 1 / math.sqrt(2)
    slate.poly([(-0.3, 5, 0.4), (2, 7.3, 0.4), (2, 7.3, -3), (-0.3, 5, -3)], "slate", np.array([s, s, 0]), -Z)
    slate.poly([(2, 7.3, 0.4), (4.3, 5, 0.4), (4.3, 5, -3), (2, 7.3, -3)], "slate", np.array([s, -s, 0]), -Z)
    return _module("dormer", "roof", (4.6, 7.3, 3.4), 1, [("stone", stone), ("roof", slate)], {"foot": [2.0, 0.0, 0.0]})


def chimney():
    m = Mesh()
    m.box(0, 2.4, 0, 6, -2.4, 0, "ashlar", faces="fklr", bevel=0.0)
    m.box(-0.3, 2.7, 6, 6.8, -2.7, 0.3, "moulding", faces="fklrt", bevel=0.1)
    return _module("chimney", "roof", (3.0, 6.8, 3.0), 0, [("stone", m)], {"foot": [1.2, 0.0, -1.2]})


def cobble():
    m = Mesh()
    m.box(0, GRID, -0.3, 0, -GRID, 0, "cobble", faces="tf", bevel=0.0)
    return _module("cobble_4", "ground", (GRID, 0.3, GRID), 1, [("stone", m)], {"left": [0.0, 0.0, 0.0], "right": [GRID, 0.0, 0.0]})


def build_kit():
    """the eighteen modules by name"""
    mods = [
        wall(4.0), wall(8.0), lancet(4.0), lancet(8.0, twin=True), portal(8.0),
        band("plinth_4", 2.0, 0.4, "plinth"), band("string_4", 0.8, 0.3, "moulding"),
        band("cornice_4", 1.0, 0.5, "moulding", step=(0.6, 0.9)), parapet(), quoin(), pilaster(), buttress(),
        roof(), ridge(), gable(), dormer(), chimney(), cobble(),
    ]
    return {m["name"]: m for m in mods}


def check(kit):
    """the kit's gate -> (errors, stats)"""
    errors = []
    sheets = set()
    worst_lo, worst_hi = 1e9, 0.0
    tris_total = 0
    for name, m in kit.items():
        tris = 0
        for part in m["parts"]:
            sheets.add(part["sheet"])
            mesh = Mesh()
            mesh.v, mesh.f, mesh.uv = part["verts"], part["faces"], part["uvs"]
            tris += len(mesh.f)
            for (wa, d) in mesh.tri_area_density():
                if wa < 0.02:  # (a sliver of a bevel's corner: too small to read at any distance)
                    continue
                worst_lo, worst_hi = min(worst_lo, d), max(worst_hi, d)
                if not (DENSITY[0] - 1e-6 <= d <= DENSITY[1] + 1e-6):
                    errors.append(f"{name}: a face at {d:.0f} px/stud (the bar {DENSITY[0]:.0f}..{DENSITY[1]:.0f})")
                    break
            # every uv inside one strip's rows of its own sheet
            rows = [(t, h) for s, (sh, t, h) in trims.STRIPS.items() if sh == part["sheet"]]  # (top, height) px
            for a, b, c in part["faces"]:
                vs = [(1 - part["uvs"][i][1]) * trims.SHEET for i in (a, b, c)]
                if not any(all(t + INSET_PX - 1e-3 <= v <= t + h - INSET_PX + 1e-3 for v in vs) for t, h in rows):
                    errors.append(f"{name}: a face's uvs leave its strip (rows {min(vs):.0f}..{max(vs):.0f} px)")
                    break
        if tris > MAX_TRIS:
            errors.append(f"{name}: {tris} triangles (at most {MAX_TRIS})")
        tris_total += tris
        if m["kind"] == "bay" and abs(m["size"][0] / GRID - round(m["size"][0] / GRID)) > 1e-6:
            errors.append(f"{name}: {m['size'][0]} studs wide is not a whole number of {GRID:.0f}-stud bays")
        if name.startswith("portal"):
            op = m.get("opening") or {}
            if op.get("width", 0) < DOOR_MIN[0] or op.get("apex", 0) < DOOR_MIN[1]:
                errors.append(f"{name}: a doorway {op.get('width')} x {op.get('apex')} - the R6 rig needs {DOOR_MIN[0]} x {DOOR_MIN[1]}")
    maps = len(sheets) * len(trims.MAPS)
    if len(sheets) > 3:
        errors.append(f"{len(sheets)} sheets (at most 3)")
    if maps > 15:
        errors.append(f"{maps} maps (at most 15)")
    if not (15 <= len(kit) <= 20):
        errors.append(f"{len(kit)} modules (a kit is 15..20)")
    return errors, {"modules": len(kit), "sheets": sorted(sheets), "maps": maps, "tris": tris_total,
                    "density": [round(worst_lo, 1), round(worst_hi, 1)]}


def write_obj(path, part, name):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# {name} ({part['sheet']} sheet) - kit/world/modkit.py; Roblox axes, studs\n")
        for x, y, z in part["verts"]:
            fh.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
        for u, v in part["uvs"]:
            fh.write(f"vt {u:.5f} {v:.5f}\n")
        for a, b, c in part["faces"]:
            fh.write(f"f {a + 1}/{a + 1} {b + 1}/{b + 1} {c + 1}/{c + 1}\n")


def write(kit, out):
    """one .obj a module part + kit.json (sizes, sockets, sheets, openings) -> kit.json's path"""
    import json

    os.makedirs(out, exist_ok=True)
    reg = {}
    for name, m in kit.items():
        files = []
        for k, part in enumerate(m["parts"]):
            fn = f"{name}_{part['sheet']}.obj"
            write_obj(os.path.join(out, fn), part, name)
            files.append({"sheet": part["sheet"], "obj": fn, "tris": len(part["faces"])})
        reg[name] = {k: v for k, v in m.items() if k != "parts"}
        reg[name]["parts"] = files
    path = os.path.join(out, "kit.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"grid": GRID, "floor": FLOOR, "wall": WALL, "sheets": list(trims.SHEETS), "maps": list(trims.MAPS),
                   "modules": reg}, fh, indent=1)
    return path


def main(argv):
    """python kit/world/modkit.py [<out dir>] -> the kit's .obj parts, kit.json and the trim sheets' maps; one JSON line"""
    import json

    out = argv[0] if argv else os.path.join("build", "worlds", "kits", "gothic")
    kit = build_kit()
    errors, stats = check(kit)
    path = write(kit, out)
    trims.write(out)
    print(json.dumps({"status": "fail" if errors else "pass",
                      "summary": f"{stats['modules']} modules on {len(stats['sheets'])} trim sheets ({stats['maps']} maps), "
                                 f"{stats['tris']} tris, {stats['density'][0]}..{stats['density'][1]} px/stud -> {path}"
                                 + (f"; {len(errors)} problem(s): {errors[0]}" if errors else ""),
                      "next_action": errors[0] if errors else
                      f"LOOK: blender -b --factory-startup -P kit/world/modkit_blender.py -- {out} --world assets/worlds/GothicCourtyard.json"}))
    return 1 if errors else 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
