"""castle_blender.py — modular castle masonry as REAL meshes (AAA gap W3), called by meshes_blender.py for kind "wall".

The look comes from the source's frames (Stormveil, Elden Ring: _artifacts/w3_castle/contact.png), not from a
generic castle: small REGULAR ashlar courses (~1 stud on a 5-stud character) with low-contrast recessed joints,
semicircular arches with a ring of voussoirs and a keystone, a blind arcade, a projecting string course carried on a
corbel arcade (small round arches hung between corbels), a crenellated parapet with coping. Every block is modelled:
a chamfered front (the joint reads by its shadow, not a painted line), its own small offset, and its own tile of the
stone atlas (a trim sheet: 48 stone tones, chamfer-edge tones, mortar, paving), chosen darker near the ground and
streaked under ledges. Modules TILE: every course's joint pattern wraps across the module's ends (a block that
crosses the seam is cut, unchamfered, and continues in the next module), so a run of modules has no seam column.

recipe ("kind": "wall"): length (24), height (19.3), thick (6), seed, stone [r, g, b] (the game's palette),
  bays (blind arches: 2), arch_r (3), open (false: the arches are doorways through the wall), corbels (true),
  parapet (true), back (true: the courtyard face too)
Returns (object, atlas RGBA float image). Geometry is Blender Z-up: x along the wall, -y = the front face, z up.
"""

import math
import random

import numpy as np

TILE_N = 8  # 8 x 8 tiles in the atlas
TILE_WORLD = 4.0  # studs of stone surface one tile holds
STONE_TILES = 48  # 0..47 stone tones (sorted dark -> light), 48..55 chamfer edges, 56..59 mortar, 60..63 paving
EDGE0, MORTAR0, PAVE0 = 48, 56, 60


# ------------------------------------------------------------------ the stone atlas (trim sheet)
def _fbm(shape, rng, scales):
    out = np.zeros(shape)
    for s, w in scales:
        g = rng.random((shape[0] // s + 2, shape[1] // s + 2))
        ys = np.linspace(0, g.shape[0] - 1.001, shape[0])
        xs = np.linspace(0, g.shape[1] - 1.001, shape[1])
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
        fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
        a = g[y0][:, x0] * (1 - fx) + g[y0][:, x0 + 1] * fx
        b = g[y0 + 1][:, x0] * (1 - fx) + g[y0 + 1][:, x0 + 1] * fx
        out += w * (a * (1 - fy) + b * fy)
    return out / sum(w for _, w in scales)


SLATE0 = 40  # with a slate colour: tiles 40..47 are roof slates (towers pick stone below this)


def atlas(stone, size, seed, slate=None):
    """RGBA float [size, size, 4]: limestone tiles from the palette colour, each its own tone / hue / grain;
    `slate` [r, g, b] turns tiles 40..47 into roof slates (split, layered, a paler worn lower edge)"""
    rng = np.random.default_rng(seed)
    t = size // TILE_N
    img = np.zeros((size, size, 4))
    base = np.array(stone, float) / 255.0
    tones = []
    for i in range(STONE_TILES):
        # (the refs: one homogeneous stone, blocks differ by a few percent, not a patchwork of colours)
        tone = 0.86 + 0.2 * (i / (STONE_TILES - 1)) + rng.normal(0, 0.015)
        hue = np.array([1 + rng.normal(0, 0.012), 1 + rng.normal(0, 0.008), 1 + rng.normal(0, 0.014)])
        tones.append((tone, hue))
    for k in range(TILE_N * TILE_N):
        r, c = divmod(k, TILE_N)
        grain = _fbm((t, t), rng, [(32, 0.5), (8, 0.3), (2, 0.2)])
        pits = (rng.random((t, t)) < 0.012) * rng.uniform(0.15, 0.35, (t, t))
        if slate is not None and SLATE0 <= k < STONE_TILES:
            sb = np.array(slate, float) / 255.0
            cleave = _fbm((t, t), rng, [(64, 0.6), (16, 0.4)])  # (slate splits in long thin layers)
            layers = _fbm((t, t), rng, [(2, 1.0)]) * 0.3 + np.repeat(_fbm((t, 1), rng, [(4, 1.0)]), t, 1) * 0.7
            col = sb * rng.uniform(0.8, 1.15) * (0.75 + 0.35 * cleave + 0.2 * layers)[..., None]
            wear = np.linspace(0.0, 1.0, t)[:, None] ** 6  # (the exposed lower edge weathers paler)
            col = col * (1 - 0.35 * wear[..., None]) + base * 0.55 * 0.35 * wear[..., None]
        elif k < STONE_TILES:
            tone, hue = tones[k]
            col = base * hue * tone * (0.86 + 0.28 * grain)[..., None]
            col *= (1 - pits)[..., None]
            if rng.random() < 0.25:  # rain streaks (the tiles chosen under ledges)
                streak = _fbm((t, t), rng, [(4, 1.0)])[:1].repeat(t, 0) * np.linspace(1, 0.4, t)[:, None]
                col *= (1 - 0.18 * streak)[..., None]
            if rng.random() < 0.12:  # a lichen patch (Stormveil's walls are old)
                m = np.clip((_fbm((t, t), rng, [(16, 0.7), (4, 0.3)]) - 0.62) * 6, 0, 1)
                col = col * (1 - m[..., None] * 0.6) + np.array([0.42, 0.44, 0.30]) * m[..., None] * 0.6
        elif k < MORTAR0:  # chamfer edges: worn, darker
            col = base * 0.62 * (0.8 + 0.4 * grain)[..., None] * (1 - pits * 1.5)[..., None]
        elif k < PAVE0:  # mortar: dark, gritty
            col = base * 0.42 * (0.75 + 0.5 * _fbm((t, t), rng, [(2, 1.0)]))[..., None]
        else:  # paving: worn flat tops
            col = base * (0.92 + 0.1 * rng.random()) * (0.85 + 0.3 * grain)[..., None]
        img[r * t : (r + 1) * t, c * t : (c + 1) * t, :3] = np.clip(col, 0, 1)
        img[r * t : (r + 1) * t, c * t : (c + 1) * t, 3] = 1
    return img.astype(np.float32)  # (Blender's pixel buffer takes float32)


# ------------------------------------------------------------------ geometry
class Mesh:
    def __init__(self, rng):
        self.v, self.f, self.uv, self.rng = [], [], [], rng

    def quad_uv(self, pts, uvs):
        """a face with its own UVs (a tiling texture: UVs may run past 1 and wrap)"""
        i0 = len(self.v)
        for p, uv in zip(pts, uvs):
            self.v.append(np.array(p, float))
            self.uv.append((float(uv[0]), float(uv[1])))
        self.f.append(list(range(i0, i0 + len(pts))))

    def quad(self, pts, tile, u_axis, v_axis):
        """a face (3+ points, x/y/z) mapped planar into one atlas tile at a random window"""
        pts = [np.array(p, float) for p in pts]
        us = [float(np.dot(p, u_axis)) for p in pts]
        vs = [float(np.dot(p, v_axis)) for p in pts]
        u0, v0 = min(us), min(vs)
        span = max(max(us) - u0, max(vs) - v0, 1e-6)
        scale = 1.0 / max(TILE_WORLD, span)  # (a face bigger than a tile squeezes in rather than bleeding)
        ou = self.rng.uniform(0, max(0.0, 1 - (max(us) - u0) * scale))
        ov = self.rng.uniform(0, max(0.0, 1 - (max(vs) - v0) * scale))
        r, c = divmod(int(tile), TILE_N)
        pad = 2.0 / 1024
        i0 = len(self.v)
        for p, u, v in zip(pts, us, vs):
            uu = c / TILE_N + pad + (ou + (u - u0) * scale) * (1 / TILE_N - 2 * pad)
            vv = 1 - (r + 1) / TILE_N + pad + (ov + (v - v0) * scale) * (1 / TILE_N - 2 * pad)
            self.v.append(p)
            self.uv.append((uu, vv))
        self.f.append(list(range(i0, i0 + len(pts))))


X, Y, Z = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])


def inset(poly, amounts):
    """a convex polygon (2D, CCW) moved in by a per-edge amount (edge i = poly[i] -> poly[i+1])"""
    n = len(poly)
    lines = []
    for i in range(n):
        a, b = np.array(poly[i]), np.array(poly[(i + 1) % n])
        d = b - a
        d = d / max(np.linalg.norm(d), 1e-9)
        nrm = np.array([-d[1], d[0]])  # (CCW: left = inside)
        lines.append((a + nrm * amounts[i], d))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append(p1 + d1 * t)
    return out


def ccw(poly):
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return poly if area > 0 else poly[::-1]


def block(m, poly_xz, y, ch, tile, edge_tile, cut=None, facing=-1):
    """a chamfered block face on a wall plane: the polygon (x, z) at depth y (front at y, set back by ch at its rim);
    `cut` = edges with no chamfer (a module end). facing -1 = the front (-y), +1 = the back face (+y)"""
    poly = ccw([tuple(p) for p in poly_xz])
    n = len(poly)
    amounts = [0.0 if (cut and cut(poly[i], poly[(i + 1) % n])) else ch for i in range(n)]
    inner = inset(poly, amounts)
    P = lambda q, yy: (q[0], yy, q[1])
    back = y - facing * ch  # (the rim sits ch deeper into the wall)
    front = [P(q, y) for q in inner]
    m.quad(front if facing < 0 else front[::-1], tile, X, Z)
    for i in range(n):
        if amounts[i] == 0:
            continue
        a, b = poly[i], poly[(i + 1) % n]
        ia, ib = inner[i], inner[(i + 1) % n]
        face = [P(a, back), P(b, back), P(ib, y), P(ia, y)]
        d = np.array(b) - np.array(a)
        m.quad(face if facing < 0 else face[::-1], edge_tile, X if abs(d[0]) >= abs(d[1]) else Z, Y)


def courses(h0, h1, seed):
    """course heights between h0 and h1: regular (the refs), 0.9 / 1.1 alternating, the last fitted"""
    zs, z, k = [h0], h0, 0
    while z < h1 - 0.5:
        z = min(h1, z + (1.1 if k % 2 else 0.9))
        if h1 - z < 0.5:
            z = h1
        zs.append(z)
        k += 1
    return zs


def joints(length, rng, lo=1.5, hi=3.0, offset=0.0):
    """joint x positions over one module, periodic: the pattern wraps at the module's length"""
    xs, x = [], offset
    while x < offset + length - lo:
        xs.append(x % length)
        x += rng.uniform(lo, hi)
    # a joint a sliver from the seam would leave a block too thin to keep (a hole at the module's end): the block
    # runs through the seam instead (the same on both sides, so the pattern still wraps)
    return sorted(x for x in xs if 0.3 <= x <= length - 0.3)


def wall_mesh(rec):
    """the module's faces (Mesh: v, f, uv), pure (no Blender)"""
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))
    L = float(rec.get("length", 24))
    T = float(rec.get("thick", 6))
    bays = int(rec.get("bays", 2))
    ar = float(rec.get("arch_r", 3.0))
    ring = 0.9
    plinth_top, slope_top = 2.8, 3.3
    string_z, string_h = 14.0, 0.85
    breast, merlon_h, cope = 1.6, 2.4, 0.4
    top = string_z + string_h
    para_t = 1.3
    J = 0.07  # joint chamfer (the shadow line between blocks)
    arch_cx = [L * (i + 0.5) / bays for i in range(bays)]
    open_ = bool(rec.get("open"))
    ground = rec.get("open") == "ground"  # (a gate: the doorway runs down to the ground, no plinth or step across it)

    def across(a, b):
        """[a, b] minus every ground doorway's width (the plinth and its slope stop at a gate)"""
        segs = [(a, b)]
        if ground:
            for cx in arch_cx:
                segs = [p for s0, s1 in segs for p in ((s0, min(s1, cx - ar)), (max(s0, cx + ar), s1)) if p[1] - p[0] > 0.05]
        return segs
    spring = 8.0

    def pick(z, under_ledge=False):
        """darker tiles low (splash, damp), mid tones up the wall, streaked tiles right under a ledge"""
        t = min(1.0, max(0.0, (z - 0.5) / 12.0))
        if under_ledge:
            t *= 0.6
        k = int(np.clip(rng.gauss(6 + t * 34, 6), 0, STONE_TILES - 1))
        return k

    edge = lambda: EDGE0 + rng.randrange(8)
    ruin = float(rec.get("ruin", 0.0))
    roots = [np.array(r["path"], float) for r in rec.get("roots", [])]
    root_r = [float(r.get("r", 1.2)) for r in rec.get("roots", [])]
    breach_x = float(rec.get("breach_x", L * 0.62))
    drng = random.Random(seed * 13 + 1)

    def root_dist(x, z):
        """(distance to the nearest root path on the front face, that root's radius)"""
        best = (1e9, 1.0)
        for path, r in zip(roots, root_r):
            for a, b in zip(path[:-1], path[1:]):
                ab, ap = b - a, np.array([x, z]) - a
                t = float(np.clip(np.dot(ap, ab) / max(np.dot(ab, ab), 1e-9), 0, 1))
                d = float(np.linalg.norm(ap - ab * t))
                if d < best[0]:
                    best = (d, r)
        return best

    def breached(x, z):
        """the V of a breach (ruin >= 0.5): wider toward the top, down to below the string course"""
        if ruin < 0.5:
            return False
        w = (z - (string_z - 5.5)) * 0.7
        return w > 0 and abs(x - breach_x) < w

    def disturb(poly, y, facing):
        """a front block near a root is lifted, pushed out and turned; one on the root's path or in a breach is
        gone; ruin knocks out a few up high. Returns (poly, y) or None (no block)."""
        if facing > 0:
            return poly, y
        cx = sum(p[0] for p in poly) / len(poly)
        cz = sum(p[1] for p in poly) / len(poly)
        if breached(cx, cz):
            return None
        if ruin > 0 and cz > string_z - 2 and drng.random() < ruin * 0.18:
            return None
        if roots:
            d, r = root_dist(cx, cz)
            if d < r:
                return None
            reach = r * 2.4
            if d < reach:
                k = 1 - (d - r) / (reach - r)
                ang = math.radians(drng.uniform(-9, 9) * k)
                ca, sa = math.cos(ang), math.sin(ang)
                lift = 0.25 * k
                poly = [(cx + (px - cx) * ca - (pz - cz) * sa, cz + lift + (px - cx) * sa + (pz - cz) * ca) for px, pz in poly]
                y = y - 0.45 * k * drng.uniform(0.5, 1.0)
        return poly, y
    seam = lambda a, b: (abs(a[0] - b[0]) < 1e-6 and (abs(a[0]) < 1e-6 or abs(a[0] - L) < 1e-6))

    def arch_gap(z0, z1, cx, r_out):
        """the x-interval a course must leave free for an arch of outer radius r_out springing at `spring`"""
        if z1 <= spring:
            return cx - r_out, cx + r_out, None
        if z0 >= spring + r_out:
            return None
        return cx - r_out, cx + r_out, r_out

    def fill(y, z0, z1, xa, xb, facing, holes, offset_seed, ring_w=None):
        """one course of ashlar between z0..z1 over [xa, xb] (the module), leaving holes (arches; ring_w: the width of
        their voussoir ring on this face - 0 on a face with no ring, the back of a doorway)"""
        rw = ring if ring_w is None else ring_w
        rrow = random.Random(offset_seed)
        js = joints(L, rrow, offset=rrow.uniform(0, 3))
        if not js or js[0] > 1e-6:
            js = [0.0] + js
        edges = sorted(set([0.0] + js + [L]))
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a < 0.25:
                continue
            segs = [(a, b)]
            for cx, r_out in holes:
                nxt = []
                for s0, s1 in segs:
                    # the arch's x-extent across this course: its widest point in the course (a circle trims later)
                    zz = max(z0, spring)
                    if z0 >= spring + r_out:
                        nxt.append((s0, s1))
                        continue
                    half = (r_out - rw) if z0 < spring else math.sqrt(max(0.0, r_out * r_out - (zz - spring) ** 2))
                    lo, hi = cx - half, cx + half
                    if s1 <= lo or s0 >= hi:
                        nxt.append((s0, s1))
                        continue
                    if s0 < lo:
                        nxt.append((s0, lo))
                    if s1 > hi:
                        nxt.append((hi, s1))
                segs = nxt
            for s0, s1 in segs:
                if s1 - s0 < 0.2:
                    continue
                poly = [(s0, z0), (s1, z0), (s1, z1), (s0, z1)]
                # a block beside an arch above the springing: its arch-side top corner follows the circle
                for cx, r_out in holes:
                    if z0 < spring + r_out and z1 > spring:
                        top_half = math.sqrt(max(0.0, r_out * r_out - (max(z1, spring) - spring) ** 2))
                        low_half = (r_out - rw) if z0 <= spring else math.sqrt(max(0.0, r_out * r_out - (z0 - spring) ** 2))
                        if abs(s1 - (cx - low_half)) < 1e-6 and top_half < low_half:
                            poly[2] = (cx - top_half, z1)
                        if abs(s0 - (cx + low_half)) < 1e-6 and top_half < low_half:
                            poly[3] = (cx + top_half, z1)
                jit = rng.uniform(-0.03, 0.03)
                got = disturb(poly, y + jit * -facing, facing)
                if got is None:
                    continue
                block(m, got[0], got[1], J, pick(z0, under_ledge=z1 > string_z - 1.2), edge(), cut=seam, facing=facing)

    # --- the front face: plinth, body courses round the blind arches, then the parapet above the string course
    holes = [(cx, ar + ring) for cx in arch_cx]
    for i, (z0, z1) in enumerate(zip([0.0, 1.4], [1.4, plinth_top])):
        rp = random.Random(seed * 31 + i)
        js = sorted(set([0.0] + joints(L, rp, 2.6, 3.6, rp.uniform(0, 3)) + [L]))
        for a0_, b0_ in zip(js[:-1], js[1:]):
            for a, b in across(a0_, b0_):
                if b - a > 0.3:
                    block(m, [(a, z0), (b, z0), (b, z1), (a, z1)], -0.5, J * 1.4, pick(z0), edge(), cut=seam)
    # the plinth's sloped weathering top
    for a0_ in np.arange(0, L, 3.0):
        for a, b in across(a0_, min(L, a0_ + 3.0)):
            m.quad([(a, -0.5, plinth_top), (b, -0.5, plinth_top), (b, 0.0, slope_top), (a, 0.0, slope_top)], PAVE0 + rng.randrange(4), X, Y)
    zs = courses(slope_top, string_z, seed)
    for i, (z0, z1) in enumerate(zip(zs[:-1], zs[1:])):
        fill(0.0, z0, z1, 0, L, -1, holes if z0 < spring + ar + ring else [], seed * 101 + i)

    # --- blind arches: recess back wall, jambs, soffit, voussoir ring with a keystone; "open": a real DOORWAY (the
    # reveal and soffit run through the wall's thickness, no back wall: a tomb's mouth, a gate)
    depth = T if open_ else 0.6
    floor_z = 0.0 if ground else slope_top
    for cx in arch_cx:
        rz = [slope_top] if open_ else courses(slope_top, spring + ar, seed + 7)
        for i, (z0, z1) in enumerate(zip(rz[:-1], rz[1:])):
            rrow = random.Random(seed * 7 + i)
            xs = [cx - ar]
            while xs[-1] < cx + ar - 1.2:
                xs.append(min(cx + ar, xs[-1] + rrow.uniform(1.2, 2.2)))
            if xs[-1] < cx + ar:
                xs[-1] = cx + ar
            for a, b in zip(xs[:-1], xs[1:]):
                if z0 >= spring:  # trim to the arch's circle
                    ha = math.sqrt(max(0.0, ar * ar - (z0 - spring) ** 2))
                    hb = math.sqrt(max(0.0, ar * ar - (z1 - spring) ** 2))
                    a0, b0 = max(a, cx - ha), min(b, cx + ha)
                    a1, b1 = max(a, cx - hb), min(b, cx + hb)
                    if b0 - a0 < 0.15:
                        continue
                    poly = [(a0, z0), (b0, z0), (max(b1, a1), z1), (a1, z1)] if b1 > a1 else [(a0, z0), (b0, z0), ((a0 + b0) / 2, z1)]
                else:
                    poly = [(a, z0), (b, z0), (b, z1), (a, z1)]
                block(m, poly, depth, J, pick(z0) // 2, edge())
        for sx in (-1, 1):  # jambs (the reveal)
            x = cx + sx * ar
            pts = [(x, 0.0, floor_z), (x, depth, floor_z), (x, depth, spring), (x, 0.0, spring)]
            m.quad(pts if sx > 0 else pts[::-1], pick(5), Y, Z)
        seg = 16
        for k in range(seg):  # soffit (the arch's underside)
            a0, a1 = math.pi * k / seg, math.pi * (k + 1) / seg
            p = lambda a, yy: (cx + ar * math.cos(a), yy, spring + ar * math.sin(a))
            m.quad([p(a0, 0.0), p(a1, 0.0), p(a1, depth), p(a0, depth)], pick(6), X, Y)
        nv = 13  # voussoirs (odd: a keystone at the crown)
        for k in range(nv):
            a0, a1 = math.pi * k / nv, math.pi * (k + 1) / nv
            key = k == nv // 2
            ro = ar + ring + (0.25 if key else 0.0)
            poly = [(cx + ar * math.cos(a1), spring + ar * math.sin(a1)), (cx + ar * math.cos(a0), spring + ar * math.sin(a0)),
                    (cx + ro * math.cos(a0), spring + ro * math.sin(a0)), (cx + ro * math.cos(a1), spring + ro * math.sin(a1))]
            block(m, poly, -0.12 - (0.1 if key else 0.0), J * 1.2, pick(9), edge())

    # --- corbel arcade under the string course (small round arches hung between corbels)
    if rec.get("corbels", True):
        sp, cw, ch_, proj = 2.0, 0.6, 1.0, 0.6
        cz1 = string_z
        for i in range(int(L / sp)):
            x = sp * (i + 0.5)
            x0, x1 = x - cw / 2, x + cw / 2
            z0 = cz1 - ch_
            # a corbel: front, sides, and a sloped underside (tapers back to the wall)
            m.quad([(x0, -proj, z0 + 0.35), (x1, -proj, z0 + 0.35), (x1, -proj, cz1), (x0, -proj, cz1)], pick(20), X, Z)
            m.quad([(x0, 0, z0), (x1, 0, z0), (x1, -proj, z0 + 0.35), (x0, -proj, z0 + 0.35)], EDGE0 + rng.randrange(8), X, Y)
            for sx, xx in ((-1, x0), (1, x1)):
                pts = [(xx, 0, z0), (xx, -proj, z0 + 0.35), (xx, -proj, cz1), (xx, 0, cz1)]
                m.quad(pts if sx > 0 else pts[::-1], EDGE0 + rng.randrange(8), Y, Z)
            # the small arch to the next corbel (wraps over the module's seam)
            ax0, ax1 = x1, x1 + sp - cw
            acx, r = (ax0 + ax1) / 2, (ax1 - ax0) / 2
            sz = cz1 - 0.25 - r
            n = 6
            for k in range(n):
                a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
                # a wedge of the spandrel band: from the arch's edge straight up to the ledge
                inner = [(acx + r * math.cos(a), sz + r * math.sin(a)) for a in (a1, a0)]
                poly = [inner[0], inner[1], (inner[1][0], cz1), (inner[0][0], cz1)]
                shift = L if min(px for px, _ in poly) >= L - 1e-6 else 0.0  # (the last arch wraps into this module's start)
                if max(px for px, _ in poly) > L + 1e-6 and shift == 0.0:
                    continue  # (straddles the seam: the neighbouring module's first wedges draw it)
                pts = [(px - shift, -0.35, pz) for px, pz in poly]
                m.quad(pts[::-1], pick(18, True), X, Z)
                # its underside (the small arch's soffit back to the wall): without it the band read as a dark gap
                (ia, za), (ib, zb) = inner[0], inner[1]
                m.quad([(ib - shift, -0.35, zb), (ia - shift, -0.35, za), (ia - shift, 0.0, za), (ib - shift, 0.0, zb)], EDGE0 + rng.randrange(8), X, Y)

    # --- string course: a moulded ledge in stone segments
    prof = [(0.0, string_z), (-0.35, string_z + 0.08), (-0.55, string_z + 0.35), (-0.65, string_z + 0.55),
            (-0.65, string_z + string_h - 0.12), (-0.55, top), (0.0, top)]
    xs = [0.0]
    while xs[-1] < L - 0.5:
        xs.append(min(L, xs[-1] + rng.uniform(2.4, 3.4)))
    xs[-1] = L
    for a, b in zip(xs[:-1], xs[1:]):
        g = 0.03 if a > 0 else 0.0
        a2, b2 = a + g, b - (0.03 if b < L else 0.0)
        tile = pick(28)
        for (y0, z0), (y1, z1) in zip(prof[:-1], prof[1:]):
            m.quad([(a2, y0, z0), (b2, y0, z0), (b2, y1, z1), (a2, y1, z1)], tile, X, Z if abs(z1 - z0) > abs(y1 - y0) else Y)
        for xx, s in ((a2, -1), (b2, 1)):
            if 0 < xx < L:
                pts = [(xx, y, z) for y, z in prof]
                m.quad(pts if s > 0 else pts[::-1], tile, Y, Z)

    # --- parapet: breastwork + merlons (front and walkway faces), embrasure cheeks, coping; the walkway paving
    if rec.get("parapet", True):
        b0, b1 = top, top + breast
        bz = courses(b0, b1, seed + 3)
        for face_y, facing in ((0.0, -1), (para_t, 1)):
            for i, (z0, z1) in enumerate(zip(bz[:-1], bz[1:])):
                fill(face_y, z0, z1, 0, L, facing, [], seed * 211 + i + (50 if facing > 0 else 0))
        mw, gw = 2.5, 1.5
        unit = mw + gw
        for i in range(int(L / unit)):
            x0 = gw / 2 + i * unit
            x1 = x0 + mw
            mc = (x0 + x1) / 2
            if breached(mc, b1) or (roots and root_dist(mc, b1 + 1)[0] < root_dist(mc, b1 + 1)[1] * 1.6):
                continue
            if ruin > 0 and drng.random() < ruin * 0.45:
                continue  # (fallen: the embrasure gap simply widens)
            mz = courses(b1, b1 + merlon_h, seed + 5)
            for face_y, facing in ((0.0, -1), (para_t, 1)):
                for k, (z0, z1) in enumerate(zip(mz[:-1], mz[1:])):
                    mid = rng.uniform(x0 + 0.8, x1 - 0.8)
                    for a, b in ((x0, mid), (mid, x1)):
                        block(m, [(a, z0), (b, z0), (b, z1), (a, z1)], face_y, J, pick(z0), edge(), facing=facing)
            for xx, s in ((x0, -1), (x1, 1)):  # embrasure cheeks
                pts = [(xx, 0.0, b1), (xx, para_t, b1), (xx, para_t, b1 + merlon_h), (xx, 0.0, b1 + merlon_h)]
                m.quad(pts if s > 0 else pts[::-1], pick(24), Y, Z)
            # coping cap (projects a little, chamfered top)
            c0, c1, zt = x0 - 0.12, x1 + 0.12, b1 + merlon_h
            yy0, yy1 = -0.15, para_t + 0.15
            capt = pick(30)
            m.quad([(c0, yy0, zt), (c1, yy0, zt), (c1, yy0, zt + cope * 0.6), (c0, yy0, zt + cope * 0.6)], capt, X, Z)
            m.quad([(c1, yy1, zt), (c0, yy1, zt), (c0, yy1, zt + cope * 0.6), (c1, yy1, zt + cope * 0.6)], capt, X, Z)
            m.quad([(c0, yy0, zt + cope * 0.6), (c1, yy0, zt + cope * 0.6), (c1 - 0.1, yy0 + 0.25, zt + cope), (c0 + 0.1, yy0 + 0.25, zt + cope)], EDGE0 + rng.randrange(8), X, Y)
            m.quad([(c1, yy1, zt + cope * 0.6), (c0, yy1, zt + cope * 0.6), (c0 + 0.1, yy1 - 0.25, zt + cope), (c1 - 0.1, yy1 - 0.25, zt + cope)], EDGE0 + rng.randrange(8), X, Y)
            m.quad([(c0 + 0.1, yy0 + 0.25, zt + cope), (c1 - 0.1, yy0 + 0.25, zt + cope), (c1 - 0.1, yy1 - 0.25, zt + cope), (c0 + 0.1, yy1 - 0.25, zt + cope)], PAVE0 + rng.randrange(4), X, Y)
            for xx, s in ((c0, -1), (c1, 1)):
                pts = [(xx, yy0, zt), (xx, yy1, zt), (xx, yy1, zt + cope * 0.6), (xx, yy0, zt + cope * 0.6)]
                m.quad(pts if s > 0 else pts[::-1], capt, Y, Z)
        # the breastwork's top: one continuous capped course over the whole module (sills in the embrasures, the
        # ledge left where a merlon fell; under a standing merlon it is hidden) + the walkway
        for g0 in np.arange(0.0, L, 2.0):
            g1 = min(L, g0 + 2.0)
            m.quad([(g0, 0.0, b1), (g1, 0.0, b1), (g1, para_t, b1), (g0, para_t, b1)], PAVE0 + rng.randrange(4), X, Y)
        for a in np.arange(0, L, 3.0):
            for c in np.arange(para_t, T, 2.4):
                b, d = min(L, a + 3.0), min(T, c + 2.4)
                m.quad([(a + 0.03, c + 0.03, top), (b - 0.03, c + 0.03, top), (b - 0.03, d - 0.03, top), (a + 0.03, d - 0.03, top)], PAVE0 + rng.randrange(4), X, Y)
        for a in np.arange(0, L, 4.0):  # the mortar under the paving joints
            b = min(L, a + 4.0)
            m.quad([(a, para_t, top - 0.05), (b, para_t, top - 0.05), (b, T, top - 0.05), (a, T, top - 0.05)], MORTAR0 + rng.randrange(4), X, Y)

    # --- the courtyard (back) face: plain ashlar up to the walkway
    if rec.get("back", True):
        bzs = courses(0.0, top, seed + 11)
        for i, (z0, z1) in enumerate(zip(bzs[:-1], bzs[1:])):
            fill(T, z0, z1, 0, L, 1, [(cx, ar) for cx in arch_cx] if open_ else [], seed * 307 + i, ring_w=0.0)

    # --- mortar cores behind every face (seen only through the joints)
    def in_opening(x, z):
        for cx in arch_cx:
            if z >= floor_z - 1e-6 and ((z <= spring and abs(x - cx) < ar) or math.hypot(x - cx, z - spring) < ar):
                return True
        return False

    for y, zz0, zz1, facing, step, holes_ in ((J, slope_top, string_z, -1, 0.5, True), (T - J, 0.0, top, 1, 0.5 if open_ else 4.0, open_),
                                             (J - 0.5, 0.0, plinth_top, -1, 0.5 if ground else 4.0, ground)):
        for a in np.arange(0, L, step):
            for z in np.arange(zz0, zz1, step):
                b, z2 = min(L, a + step), min(zz1, z + step)
                if holes_ and any(in_opening(px, pz) for px in (a, b) for pz in (z, z2)):
                    continue  # (the front core must not close the blind arches)
                pts = [(a, y, z), (b, y, z), (b, y, z2), (a, y, z2)]
                m.quad(pts if facing < 0 else pts[::-1], MORTAR0 + rng.randrange(4), X, Z)
    for cx in ([] if open_ else arch_cx):  # the recesses' own core (a doorway has none)
        for a in np.arange(cx - ar, cx + ar, 2.0):
            for z in np.arange(slope_top, spring + ar, 2.0):
                b, z2 = min(cx + ar, a + 2.0), min(spring + ar, z + 2.0)
                m.quad([(a, depth + J, z), (b, depth + J, z), (b, depth + J, z2), (a, depth + J, z2)], MORTAR0 + rng.randrange(4), X, Z)

    return m


# ------------------------------------------------------------------ round towers + their slate roofs
def arc_block(m, R, a0, a1, z0, z1, ch, tile, edge_tile, nseg=2):
    """a chamfered block curved round a tower of radius R (angles a0..a1, heights z0..z1): its face at R, the
    rim (joint) set ch deeper; the joint reads by its shadow as on the wall"""
    da = ch / R
    P = lambda r, a, z: (r * math.cos(a), r * math.sin(a), z)
    angs = [a0 + da + (a1 - a0 - 2 * da) * k / nseg for k in range(nseg + 1)]
    zi0, zi1, rr = z0 + ch, z1 - ch, R - ch
    tan = lambda a: np.array([-math.sin(a), math.cos(a), 0.0])
    for a, b in zip(angs[:-1], angs[1:]):
        mid = (a + b) / 2
        m.quad([P(R, a, zi0), P(R, b, zi0), P(R, b, zi1), P(R, a, zi1)], tile, tan(mid), Z)
        m.quad([P(rr, a - (da if a == angs[0] else 0), z0), P(rr, b + (da if b == angs[-1] else 0), z0), P(R, b, zi0), P(R, a, zi0)],
               edge_tile, tan(mid), Z)
        m.quad([P(R, a, zi1), P(R, b, zi1), P(rr, b + (da if b == angs[-1] else 0), z1), P(rr, a - (da if a == angs[0] else 0), z1)],
               edge_tile, tan(mid), Z)
    m.quad([P(rr, a0, z0), P(R, angs[0], zi0), P(R, angs[0], zi1), P(rr, a0, z1)], edge_tile, Z, np.array([math.cos(a0), math.sin(a0), 0.0]))
    m.quad([P(R, angs[-1], zi0), P(rr, a1, z0), P(rr, a1, z1), P(R, angs[-1], zi1)], edge_tile, Z, np.array([math.cos(a1), math.sin(a1), 0.0]))


def ring(m, prof, segs, tile_fn, a0=0.0, a1=2 * math.pi):
    """a moulding turned round the tower: prof = [(radius, z), ...] from bottom to top, outward faces"""
    for k in range(segs):
        a, b = a0 + (a1 - a0) * k / segs, a0 + (a1 - a0) * (k + 1) / segs
        t = tile_fn()
        for (r0, z0), (r1, z1) in zip(prof[:-1], prof[1:]):
            pts = [(r0 * math.cos(a), r0 * math.sin(a), z0), (r0 * math.cos(b), r0 * math.sin(b), z0),
                   (r1 * math.cos(b), r1 * math.sin(b), z1), (r1 * math.cos(a), r1 * math.sin(a), z1)]
            m.quad(pts, t, np.array([-math.sin(a), math.cos(a), 0.0]), Z if abs(z1 - z0) >= abs(r1 - r0) else np.array([math.cos(a), math.sin(a), 0.0]))


def tower_mesh(rec):
    """a round tower (Stormveil / Carcassonne): a battered base, regular ashlar courses curved round it, arrow slits,
    a moulded string course, machicolation corbels carrying a crenellated parapet ring, the fighting top paved.
    recipe ("kind": "tower"): radius (6.5), height (30: the parapet's top), seed, stone, slits (5), ruin (0..1),
    door ({angle (deg, 0 = local +X), width, height}: a doorway at the foot),
    waterline (z: the stone below is dark and wet) + rings (tide rings above it), cracked (0..1: blocks out of true)"""
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))
    R = float(rec.get("radius", 6.5))
    H = float(rec.get("height", 30.0))
    ruin = float(rec.get("ruin", 0.0))
    J = 0.07
    batter_top, string_z = 3.6, H - 7.5
    mach_z = H - 5.2  # machicolations: the parapet ring rides out on corbels from here
    para_r = R + 0.75
    edge = lambda: EDGE0 + rng.randrange(8)

    water = rec.get("waterline")
    rings = int(rec.get("rings", 0))
    cracked = float(rec.get("cracked", 0.0))

    def pick(z):
        # the lake keeps the record: below the waterline the stone is dark and wet; above it, one dark tide ring per
        # year the water stood there (rings 1.1 studs apart, fading upward)
        if water is not None:
            if z < water:
                return int(np.clip(rng.gauss(2, 1.5), 0, 6))
            for k in range(rings):
                zr = water + 0.55 + 1.1 * k
                if abs(z - zr) < 0.45:
                    return int(np.clip(rng.gauss(3 + 2.5 * k, 1.5), 0, SLATE0 - 1))
        t = min(1.0, max(0.0, (z - 0.5) / (H * 0.6)))
        return int(np.clip(rng.gauss(4 + t * 30, 5), 0, SLATE0 - 1))

    slits = [(2 * math.pi * k / max(1, int(rec.get("slits", 5))) + rng.uniform(-0.2, 0.2), rng.uniform(7, string_z - 5))
             for k in range(int(rec.get("slits", 5)))]
    slit_w, slit_h = 0.55, 3.0
    # every opening in the shaft: (angle, bottom, height, width, kind) - the slits, and a DOOR at ground level when the
    # recipe has one (angle in degrees, 0 = local +X: the world compiler turns the tower so it faces its door)
    openings = [(sa, sz, slit_h, slit_w, "slit") for sa, sz in slits]
    door = rec.get("door")
    if isinstance(door, dict):
        openings.append((math.radians(float(door.get("angle", 0))), 0.0, float(door.get("height", 7.0)), float(door.get("width", 4.0)), "door"))

    def in_slit(a, b, z0, z1):
        for sa, sz, oh, ow, _ in openings:
            w = (ow / 2 + 0.25) / R
            d = (sa - (a + b) / 2 + math.pi) % (2 * math.pi) - math.pi
            if abs(d) < (b - a) / 2 + w and z1 > sz - 0.3 and z0 < sz + oh + 0.3:
                return True
        return False

    # the shaft: courses of curved ashlar (the base courses step out: a batter)
    zs = courses(0.0, mach_z, seed)
    for i, (z0, z1) in enumerate(zip(zs[:-1], zs[1:])):
        r_here = R + max(0.0, (batter_top - z0) / batter_top) * 0.9
        circ = 2 * math.pi * r_here
        n = max(8, int(circ / (rng.uniform(2.4, 3.0) * max(1.0, R / 6.5))))  # (a bigger tower: longer blocks, one budget)
        off = rng.uniform(0, 2 * math.pi / n)
        cuts = sorted([off + 2 * math.pi * k / n + rng.uniform(-0.25, 0.25) / r_here for k in range(n)])
        cuts.append(cuts[0] + 2 * math.pi)
        for a, b in zip(cuts[:-1], cuts[1:]):
            if z0 >= string_z and z0 < string_z + 0.85:
                continue
            if in_slit(a, b, z0, z1):
                # the block beside a slit is split: keep the parts clear of the slit
                keep = [(a, b)]
                for sa, sz, oh, ow, _ in openings:
                    if not (z1 > sz and z0 < sz + oh):
                        continue
                    w = (ow / 2) / r_here
                    d = (sa - (a + b) / 2 + math.pi) % (2 * math.pi) - math.pi + (a + b) / 2  # (the slit's angle near this block)
                    nxt = []
                    for k0, k1 in keep:
                        if k1 <= d - w or k0 >= d + w:
                            nxt.append((k0, k1))
                            continue
                        if d - w - k0 > 0.04:
                            nxt.append((k0, d - w))
                        if k1 - (d + w) > 0.04:
                            nxt.append((d + w, k1))
                    keep = nxt
                for k0, k1 in keep:
                    arc_block(m, r_here, k0, k1, z0, z1, J, pick(z0), edge(), 1 if k1 - k0 < 0.3 else 2)
                continue
            if ruin > 0 and z0 > mach_z - 6 and rng.random() < ruin * 0.25:
                continue
            # a cracked tower: blocks above the water pushed out of true (the shaft is moving)
            push = rng.uniform(0, 0.22) * cracked if (water is None or z0 > water) else 0.0
            arc_block(m, r_here + push, a, b, z0, z1, J, pick(z0), edge(), 2 if b - a > 0.3 else 1)
    # arrow slits: the reveal (dark inside) + a splayed sill
    for sa, sz, slit_h, ow, okind in openings:
        w, dep = ow / 2, (2.4 if okind == "door" else 1.2)
        ca, sa_ = math.cos(sa), math.sin(sa)
        tx, ty = -sa_, ca
        def p(u, r, z):
            return (ca * r + tx * u, sa_ * r + ty * u, z)
        dark = MORTAR0 + rng.randrange(4)
        if okind != "door":  # (a slit is closed behind by the dark; a door opens into the tower's own walls)
            m.quad([p(-w, R - dep, sz), p(w, R - dep, sz), p(w, R - dep, sz + slit_h), p(-w, R - dep, sz + slit_h)], dark, np.array([tx, ty, 0.0]), Z)
        m.quad([p(-w, R, sz), p(-w, R - dep, sz), p(-w, R - dep, sz + slit_h), p(-w, R, sz + slit_h)], pick(sz), np.array([ca, sa_, 0.0]), Z)
        m.quad([p(w, R - dep, sz), p(w, R, sz), p(w, R, sz + slit_h), p(w, R - dep, sz + slit_h)], pick(sz), np.array([ca, sa_, 0.0]), Z)
        m.quad([p(-w, R, sz + slit_h), p(-w, R - dep, sz + slit_h), p(w, R - dep, sz + slit_h), p(w, R, sz + slit_h)], edge(), np.array([tx, ty, 0.0]), np.array([ca, sa_, 0.0]))
        if okind != "door":  # (a door's sill is the ground)
            m.quad([p(-w - 0.15, R + 0.05, sz - 0.05), p(w + 0.15, R + 0.05, sz - 0.05), p(w, R - dep, sz), p(-w, R - dep, sz)], PAVE0 + rng.randrange(4),
                   np.array([tx, ty, 0.0]), np.array([ca, sa_, 0.0]))
    # the batter's sloped top + a moulded string course
    # (a door leaves its gap in the rings that run round the foot of the shaft)
    da = [o for o in openings if o[4] == "door"]
    arc0, arc1 = (da[0][0] + (da[0][3] / 2 + 0.3) / R, da[0][0] + 2 * math.pi - (da[0][3] / 2 + 0.3) / R) if da else (0.0, 2 * math.pi)
    ring(m, [(R + 0.9, 0.9), (R + 0.9, 1.0), (R, batter_top)], 32, lambda: PAVE0 + rng.randrange(4), arc0, arc1)
    ring(m, [(R, string_z), (R + 0.35, string_z + 0.1), (R + 0.5, string_z + 0.4), (R + 0.5, string_z + 0.7), (R, string_z + 0.85)], 40, lambda: pick(H))
    # machicolations: corbels round the top, the parapet ring carried out on them (with drop holes between)
    nc = int(2 * math.pi * R / (1.8 * max(1.0, R / 6.5)))
    for k in range(nc):
        a = 2 * math.pi * k / nc
        w = 0.32 / R
        for zb, out in ((mach_z - 1.2, 0.35), (mach_z - 0.6, 0.6)):
            arc_block(m, R + out, a - w, a + w, zb, zb + 0.6, 0.04, pick(H - 3), edge(), 1)
    ring(m, [(para_r, mach_z), (para_r, mach_z + 0.05)], 48, edge)
    pz = courses(mach_z, H - 2.3, seed + 4)
    for z0, z1 in zip(pz[:-1], pz[1:]):
        n = max(8, int(2 * math.pi * para_r / (2.8 * max(1.0, R / 6.5))))
        off = rng.uniform(0, 1)
        for k in range(n):
            a, b = off + 2 * math.pi * k / n, off + 2 * math.pi * (k + 1) / n
            arc_block(m, para_r, a, b, z0, z1, J, pick(z0), edge(), 2)
    nm = max(8, int(2 * math.pi * para_r / 3.6))
    for k in range(nm):
        a0 = 2 * math.pi * k / nm
        a1 = a0 + 2 * math.pi / nm * 0.6
        if ruin > 0 and rng.random() < ruin * 0.45:
            continue
        for z0, z1 in ((H - 2.3, H - 1.15), (H - 1.15, H)):
            arc_block(m, para_r, a0, a1, z0, z1, J, pick(z0), edge(), 2)
        # cheeks + coping
        for a, s in ((a0, -1), (a1, 1)):
            ca, sa_ = math.cos(a), math.sin(a)
            pts = [(ca * (para_r - 1.1), sa_ * (para_r - 1.1), H - 2.3), (ca * para_r, sa_ * para_r, H - 2.3),
                   (ca * para_r, sa_ * para_r, H), (ca * (para_r - 1.1), sa_ * (para_r - 1.1), H)]
            m.quad(pts if s > 0 else pts[::-1], pick(H), np.array([ca, sa_, 0.0]), Z)
        ring(m, [(para_r + 0.12, H), (para_r + 0.12, H + 0.22), (para_r - 0.4, H + 0.38), (para_r - 1.1, H + 0.3)], 3, lambda: PAVE0 + rng.randrange(4), a0, a1)
        ring(m, [(para_r - 1.1, H), (para_r - 1.1, H - 2.3)], 3, lambda: pick(H), a0, a1)  # (the merlon's inner face)
    # the inner face of the parapet + the fighting top's paving
    ring(m, [(para_r - 1.1, H - 2.3), (para_r - 1.1, mach_z + 0.4)], 40, lambda: pick(H))  # (the breastwork, all round)
    ring(m, [(para_r - 1.1, H - 2.3), (0.05, H - 2.3)], 24, lambda: PAVE0 + rng.randrange(4))
    # mortar core behind the joints
    ring(m, [(R - J, mach_z), (R - J, 0.0)], 48, lambda: MORTAR0 + rng.randrange(4), arc0, arc1)
    return m


def roof_mesh(rec):
    """a conical roof of SLATES (each its own quad and slate tile, row over row, each row stepping out over the one
    below), an eave, a finial. recipe ("kind": "roof"): radius (7.4), height (17), seed, stone, slate [r, g, b]"""
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))
    R = float(rec.get("radius", 7.4))
    H = float(rec.get("height", 17.0))
    slant = math.hypot(R, H)
    row = 0.62
    nrow = int(slant / row)
    for i in range(nrow):
        t0, t1 = i / nrow, (i + 1.6) / nrow  # (a slate is longer than its row: it laps over the next)
        r0, r1 = R * (1 - t0), max(0.05, R * (1 - min(t1, 1.0)))
        z0, z1 = H * t0, H * min(t1, 1.0)
        circ = 2 * math.pi * max(r0, 0.3)
        n = max(6, int(circ / rng.uniform(0.85, 1.05)))
        off = rng.uniform(0, 2 * math.pi / n) + (math.pi / n if i % 2 else 0)
        lift = 0.07  # (the lower edge stands proud of the row below: the courses read)
        for k in range(n):
            a = off + 2 * math.pi * k / n
            b = a + 2 * math.pi / n * rng.uniform(0.9, 0.98)
            jz = rng.uniform(-0.04, 0.04)
            tilt = rng.uniform(-0.03, 0.03)
            P = lambda r, ang, z: (r * math.cos(ang), r * math.sin(ang), z)
            pts = [P(r0 + lift, a, z0 + jz), P(r0 + lift + tilt, b, z0 + jz), P(r1, b, z1), P(r1, a, z1)]
            mid = (a + b) / 2
            m.quad(pts, SLATE0 + rng.randrange(8), np.array([-math.sin(mid), math.cos(mid), 0.0]),
                   np.array([-math.cos(mid) * R, -math.sin(mid) * R, H]) / slant)
            if i == 0:  # the eave: the slate's thickness seen from below
                m.quad([P(r0 + lift, b, z0 + jz), P(r0 + lift, a, z0 + jz), P(r0 + lift - 0.05, a, z0 + jz - 0.12), P(r0 + lift - 0.05, b, z0 + jz - 0.12)],
                       EDGE0 + rng.randrange(8), np.array([-math.sin(mid), math.cos(mid), 0.0]), Z)
    # underside (seen from the parapet walk) + the finial: a lead spike on a ball
    for k in range(16):
        a, b = 2 * math.pi * k / 16, 2 * math.pi * (k + 1) / 16
        m.quad([(0, 0, H * 0.25), (R * math.cos(b), R * math.sin(b), 0), (R * math.cos(a), R * math.sin(a), 0)], MORTAR0, X, Y)
    ring(m, [(0.35, H - 0.2), (0.45, H + 0.3), (0.32, H + 0.8), (0.1, H + 1.0), (0.06, H + 3.2), (0.0, H + 3.6)], 10, lambda: SLATE0 + 7)
    return m


# ------------------------------------------------------------------ roots (Stormhold direction C: the Erdtree's root)
def _periodic_noise(shape, rng, cells):
    """smooth value noise that TILES (the grid wraps): a texture that repeats without a seam"""
    g = rng.random((cells[0], cells[1]))
    ys = np.linspace(0, cells[0], shape[0], endpoint=False)
    xs = np.linspace(0, cells[1], shape[1], endpoint=False)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    y1, x1 = (y0 + 1) % cells[0], (x0 + 1) % cells[1]
    a = g[y0][:, x0] * (1 - fx) + g[y0][:, x1] * fx
    b = g[y1][:, x0] * (1 - fx) + g[y1][:, x1] * fx
    return a * (1 - fy) + b * fy


def bark_texture(color, size, seed):
    """ONE tiling bark image: fibre bundles running along v (the root's length), deep dark furrows between them,
    knots of cross-grain; UVs on the root run around (u) and along (v) and wrap"""
    rng = np.random.default_rng(seed)
    base = np.array(color, float) / 255.0
    fib = (0.55 * _periodic_noise((size, size), rng, (3, 24)) + 0.3 * _periodic_noise((size, size), rng, (6, 64))
           + 0.15 * _periodic_noise((size, size), rng, (24, 128)))
    furrow = np.clip((0.36 - fib) * 7, 0, 1)
    knot = np.clip((_periodic_noise((size, size), rng, (6, 6)) - 0.72) * 5, 0, 1)
    tone = 0.62 + 0.7 * fib - 0.25 * knot
    col = base[None, None, :] * tone[..., None] * (1 - 0.8 * furrow)[..., None]
    img = np.ones((size, size, 4), np.float32)
    img[..., :3] = np.clip(col, 0, 1)
    return img


def _spline(pts, n):
    """Catmull-Rom through pts -> n points"""
    P = [np.array(p, float) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    segs = len(P) - 3
    for i in range(n):
        u = i / (n - 1) * segs
        k = min(int(u), segs - 1)
        t = u - k
        p0, p1, p2, p3 = P[k], P[k + 1], P[k + 2], P[k + 3]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.array(out)


def root_mesh(rec):
    """a root of the Erdtree: `strands` braided tubes twisting round a path (Blender Z-up points), thick where it
    comes from the tree, thin where it digs in; returns (bark Mesh, glow Mesh): the glow is thin fissure ribbons
    on the strands (Neon in Roblox, emissive in the frames: the light lives only in the cracks).
    recipe ("kind": "root"): path [[x, y, z], ...], radius [start, end] (3.2, 0.9), strands (5), twist (turns, 2.5),
    glow (fissures per strand, 2), seed"""
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    bark, glow = Mesh(random.Random(seed + 1)), Mesh(random.Random(seed + 2))
    path = _spline(rec["path"], int(rec.get("samples", 90)))
    r0, r1 = rec.get("radius", [3.2, 0.9])
    ns, turns, sides = int(rec.get("strands", 5)), float(rec.get("twist", 2.5)), 8
    # parallel-transport frames along the path
    tang = np.gradient(path, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
    nrm = np.cross(tang[0], [0, 0, 1.0] if abs(tang[0][2]) < 0.9 else [1.0, 0, 0])
    nrm /= np.linalg.norm(nrm)
    frames = []
    for t in tang:
        nrm = nrm - t * np.dot(nrm, t)
        nrm /= np.linalg.norm(nrm) + 1e-9
        frames.append((nrm.copy(), np.cross(t, nrm)))
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    n = len(path)
    for s in range(ns):
        ph = 2 * math.pi * s / ns + rng.uniform(-0.3, 0.3)
        sr = rng.uniform(0.85, 1.1)
        rings = []
        for i in range(n):
            u = i / (n - 1)
            R = r0 + (r1 - r0) * u
            a = ph + u * turns * 2 * math.pi
            nn, bb = frames[i]
            c = path[i] + (nn * math.cos(a) + bb * math.sin(a)) * R * 0.5
            rs = R * 0.5 * sr * (1 + 0.12 * math.sin(u * 23 + s))
            ring_pts = [c + (nn * math.cos(2 * math.pi * k / sides) + bb * math.sin(2 * math.pi * k / sides)) * rs for k in range(sides)]
            rings.append((c, rs, ring_pts))
        vs = [rng.uniform(0, 1)]
        for i in range(n - 1):  # (one texture repeat per local circumference along: a running sum, not total / local)
            seg = float(np.linalg.norm(rings[i + 1][0] - rings[i][0]))
            circ = 2 * math.pi * max((rings[i][1] + rings[i + 1][1]) / 2, 0.2)
            vs.append(vs[-1] + seg / circ)
        for i in range(n - 1):
            v0, v1 = vs[i], vs[i + 1]
            for k in range(sides):
                p = [rings[i][2][k], rings[i][2][(k + 1) % sides], rings[i + 1][2][(k + 1) % sides], rings[i + 1][2][k]]
                u0, u1 = k / sides, (k + 1) / sides
                bark.quad_uv(p, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        # fissures: ribbons laid on the strand, a little proud of the bark, over part of its length
        for g in range(int(rec.get("glow", 2))):
            k0 = rng.uniform(0, 2 * math.pi)
            i0 = rng.randrange(2, max(3, n // 2))
            i1 = min(n - 2, i0 + rng.randrange(n // 5, n // 2))
            for i in range(i0, i1):
                pts = []
                for j in (i, i + 1):
                    c, rs, _ = rings[j]
                    nn, bb = frames[j]
                    wob = k0 + 0.4 * math.sin(j * 0.35 + g)
                    out = nn * math.cos(wob) + bb * math.sin(wob)
                    side = np.cross(tang[j], out)
                    w = 0.09 * (1 - abs((j - i0) / max(1, i1 - i0) - 0.5) * 1.6)
                    pts.append((c + out * (rs + 0.03) - side * w, c + out * (rs + 0.03) + side * w))
                glow.quad([pts[0][0], pts[0][1], pts[1][1], pts[1][0]], 0, X, Y)
    return bark, glow


def _ico():
    """a unit icosahedron subdivided once (42 verts, 80 faces)"""
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    v = [np.array(p, float) / np.linalg.norm(p) for p in v]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
         (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    cache = {}

    def mid(a, b):
        key = (min(a, b), max(a, b))
        if key not in cache:
            p = v[a] + v[b]
            v.append(p / np.linalg.norm(p))
            cache[key] = len(v) - 1
        return cache[key]
    nf = []
    for a, b, c in f:
        ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
        nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
    return v, nf


def cairn_mesh(rec):
    """a CAIRN: flat field stones stacked by travellers, each a squashed, lumpy, slightly tilted stone smaller than
    the one under it (the Site of Grace's field: one stone left by every traveller who woke there).
    recipe ("kind": "cairn"): stones (3..9), base (radius of the bottom stone, 0.9), seed, stone [r, g, b]"""
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))
    v0, faces = _ico()
    n = int(rec.get("stones", rng.randint(3, 7)))
    r = float(rec.get("base", 0.9))
    z = 0.0
    cx = cy = 0.0
    for k in range(n):
        h = r * rng.uniform(0.32, 0.5)
        sx, sy = r * rng.uniform(0.9, 1.15), r * rng.uniform(0.75, 1.0)
        rot = rng.uniform(0, math.pi)
        tilt = (rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08))
        tile = rng.randrange(STONE_TILES)
        lumps = [rng.uniform(0.85, 1.12) for _ in v0]
        pts = []
        for p, l in zip(v0, lumps):
            x, y, zz = p[0] * sx * l, p[1] * sy * l, p[2] * h * 0.5 * l
            x, y = x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)
            zz += x * tilt[0] + y * tilt[1]
            pts.append((cx + x, cy + y, z + h * 0.5 + zz))
        for a, b, c in faces:
            pa, pb, pc = np.array(pts[a]), np.array(pts[b]), np.array(pts[c])
            nrm = np.cross(pb - pa, pc - pa)
            nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
            m.quad([pts[a], pts[b], pts[c]], tile, X if abs(nrm[2]) > 0.5 else Z, Y if abs(nrm[2]) > 0.5 else X)
        z += h * 0.82
        cx += rng.uniform(-0.08, 0.08) * r
        cy += rng.uniform(-0.08, 0.08) * r
        r *= rng.uniform(0.7, 0.86)
    return m


def _to_object(m, rec, img):
    import bpy  # (here, not at the top: the geometry + atlas are testable without Blender)

    me = bpy.data.meshes.new(rec["name"])
    me.from_pydata([tuple(p) for p in m.v], [], m.f)
    me.update()
    uvl = me.uv_layers.new(name="UV")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = m.uv[me.loops[li].vertex_index]
        poly.use_smooth = False
    obj = bpy.data.objects.new(rec["name"], me)
    bpy.context.collection.objects.link(obj)
    return obj, img


def build_piece(rec):
    """kind wall | tower | roof | cairn -> (Blender object, atlas image)"""
    kind = rec.get("kind", "wall")
    seed = int(rec.get("seed", 1))
    m = {"wall": wall_mesh, "tower": tower_mesh, "roof": roof_mesh, "cairn": cairn_mesh}[kind](rec)
    slate = rec.get("slate", [52, 58, 68]) if kind in ("tower", "roof") else None
    return _to_object(m, rec, atlas(rec.get("stone", [138, 131, 120]), 1024, seed, slate=slate))


def build_root(rec):
    """(bark object, bark atlas, glow object): the glow is emissive here, Neon in Roblox"""
    import bpy

    bark, glow = root_mesh(rec)
    obj, img = _to_object(bark, rec, bark_texture(rec.get("bark", [118, 92, 52]), 512, int(rec.get("seed", 1))))
    gobj, _ = _to_object(glow, dict(rec, name=rec["name"] + "_glow"), None)
    mat = bpy.data.materials.new(rec["name"] + "_glowmat")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    col = [c / 255 for c in rec.get("glow_color", [255, 178, 72])]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Emission Color"].default_value = (*col, 1)
    b.inputs["Emission Strength"].default_value = float(rec.get("glow_strength", 12.0))
    gobj.data.materials.append(mat)
    return obj, img, gobj


def build_wall(rec):
    """(Blender object, atlas image)"""
    import bpy  # (here, not at the top: the geometry + atlas are testable without Blender)

    m = wall_mesh(rec)
    seed = int(rec.get("seed", 1))
    me = bpy.data.meshes.new(rec["name"])
    me.from_pydata([tuple(p) for p in m.v], [], m.f)
    me.update()
    uvl = me.uv_layers.new(name="UV")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = m.uv[me.loops[li].vertex_index]
        poly.use_smooth = False
    obj = bpy.data.objects.new(rec["name"], me)
    bpy.context.collection.objects.link(obj)
    return obj, atlas(rec.get("stone", [138, 131, 120]), 1024, seed)
