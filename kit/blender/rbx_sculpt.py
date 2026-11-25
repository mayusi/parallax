"""rbx_sculpt.py — SCULPTING in code: a clay canvas of signed distances (a.sculpt). Pure numpy for the field (tested in
plain Python); OpenVDB — bundled with Blender 5.x — turns it into a closed mesh (mesh()).

A sculptor adds clay, carves it away, smooths where two masses meet, pulls strokes along a path, presses creases,
inflates a region and roughens a surface. Here each of those is an operation on a SIGNED DISTANCE FIELD: every point
of space knows how far it is from the surface (negative inside). Blending two shapes with a smooth minimum gives the
fillet a sculptor's thumb leaves; noise added to the distance is surface relief at a real size. The result is always
one closed, manifold surface — no booleans to fail, no self-intersections, no holes (the shredded generator meshes and
lofts-with-lumps this replaces).

Units: millimetres throughout (the canvas is the object at its real size; a.sculpt places it in studs). A canvas's
VOXEL is its resolution: a feature thinner than ~1.5 voxels cannot survive the meshing (lost() names it).

    s = Canvas(voxel=0.5, mirror="x")                 # 0.5 mm voxels, every op mirrored across x = 0
    s.ellipsoid((0, 40, 0), (30, 38, 34))            # the skull
    s.ball((0, 10, 22), 14, blend=8)                 # the muzzle, filleted 8 mm into it
    s.stroke([(12, 52, 20), (20, 58, 10)], [5, 3], blend=3)   # a brow ridge, tapering
    s.crease([(8, 25, 33), (16, 22, 30)], 1.2)       # a wrinkle
    s.noise(0.6, 4.0, kind="ridged", where=Ball((0, 50, 0), 25), falloff=8)   # rough skin on the crown
    verts, faces = s.mesh()                          # closed, in mm
"""

import copy
import math
import os

import numpy as np

# ------------------------------------------------------------------------------------------------ noise (seeded)
# Ken Perlin's improved noise: a seeded permutation table (lattice period 256 cells — at a 6 mm scale, 1.5 m) and
# 16 gradients; float32, a few small-table lookups per corner (a 64-bit hash per corner was 6x slower)
_G16 = np.array([(1, 1, 0), (-1, 1, 0), (1, -1, 0), (-1, -1, 0), (1, 0, 1), (-1, 0, 1), (1, 0, -1), (-1, 0, -1),
                 (0, 1, 1), (0, -1, 1), (0, 1, -1), (0, -1, -1), (1, 1, 0), (0, -1, 1), (-1, 1, 0), (0, -1, -1)],
                dtype=np.float32)
_GX, _GY, _GZ = (np.ascontiguousarray(_G16[:, i]) for i in range(3))
_PERMS = {}


def _perm(seed):
    """the seed's permutation of 0..255, twice over (indices up to 511 never wrap)"""
    seed = int(seed) & 0x7FFFFFFF
    if seed not in _PERMS:
        t = np.random.default_rng(seed).permutation(256).astype(np.int32)
        _PERMS[seed] = np.concatenate([t, t])
    return _PERMS[seed]


def perlin(p, seed=0):
    """gradient noise at points p (N, 3) -> (N,) float32, about -1..1, smooth, zero at every lattice point"""
    p = np.asarray(p, dtype=np.float32)
    fl = np.floor(p)
    f = p - fl
    c = fl.astype(np.int64) & 255
    X, Y, Z = c[:, 0], c[:, 1], c[:, 2]
    P = _perm(seed)
    u = f * f * f * (f * (f * 6 - 15) + 10)
    A = P[X] + Y
    B = P[X + 1] + Y
    AA, AB, BA, BB = P[A] + Z, P[A + 1] + Z, P[B] + Z, P[B + 1] + Z
    fx, fy, fz = f[:, 0], f[:, 1], f[:, 2]
    fx1, fy1, fz1 = fx - 1, fy - 1, fz - 1

    def g(h, dx, dy, dz):
        hh = P[h] & 15
        return _GX[hh] * (fx1 if dx else fx) + _GY[hh] * (fy1 if dy else fy) + _GZ[hh] * (fz1 if dz else fz)

    ux, uy, uz = u[:, 0], u[:, 1], u[:, 2]
    x00 = g(AA, 0, 0, 0) + ux * (g(BA, 1, 0, 0) - g(AA, 0, 0, 0))
    x10 = g(AB, 0, 1, 0) + ux * (g(BB, 1, 1, 0) - g(AB, 0, 1, 0))
    x01 = g(AA + 1, 0, 0, 1) + ux * (g(BA + 1, 1, 0, 1) - g(AA + 1, 0, 0, 1))
    x11 = g(AB + 1, 0, 1, 1) + ux * (g(BB + 1, 1, 1, 1) - g(AB + 1, 0, 1, 1))
    y0 = x00 + uy * (x10 - x00)
    y1 = x01 + uy * (x11 - x01)
    return (y0 + uz * (y1 - y0)) * np.float32(1.4)   # (it spans about +-0.7: scaled to about +-1)


def fbm(p, octaves=4, seed=0, lacunarity=2.0, gain=0.5):
    """fractal noise: octaves of perlin, each finer and fainter -> about -1..1"""
    total, amp, norm = np.zeros(len(p), dtype=np.float32), 1.0, 0.0
    q = np.asarray(p, dtype=np.float32)
    for o in range(octaves):
        total += amp * perlin(q, seed + 101 * o)
        norm += amp
        q = q * lacunarity
        amp *= gain
    return total / norm


def ridged(p, octaves=4, seed=0):
    """ridged noise: sharp crests, soft valleys (rock strata, bark, veins, cartilage) -> -1..1"""
    total, amp, norm = np.zeros(len(p), dtype=np.float32), 1.0, 0.0
    q = np.asarray(p, dtype=np.float32)
    for o in range(octaves):
        r = 1.0 - np.abs(np.clip(perlin(q, seed + 211 * o), -1, 1))
        total += amp * r * r
        norm += amp
        q = q * 2.0
        amp *= 0.5
    return total / norm * 2.0 - 1.0


def _worley(p, seed=0):
    """(F1, F2): the distance to the nearest and second-nearest jittered cell point (cells 1 unit wide), float32"""
    p = np.asarray(p, dtype=np.float32)
    c = np.floor(p).astype(np.int64)
    f = p - c
    P0, P1, P2 = _perm(seed), _perm(seed + 7919), _perm(seed + 104729)
    f1 = np.full(len(p), 9.0, dtype=np.float32)
    f2 = np.full(len(p), 9.0, dtype=np.float32)
    for dx in (-1, 0, 1):
        X = (c[:, 0] + dx) & 255
        for dy in (-1, 0, 1):
            Y = (c[:, 1] + dy) & 255
            for dz in (-1, 0, 1):
                Z = (c[:, 2] + dz) & 255
                jx = P0[P0[P0[X] + Y] + Z].astype(np.float32) / 255.0
                jy = P1[P1[P1[X] + Y] + Z].astype(np.float32) / 255.0
                jz = P2[P2[P2[X] + Y] + Z].astype(np.float32) / 255.0
                ex, ey, ez = dx + jx - f[:, 0], dy + jy - f[:, 1], dz + jz - f[:, 2]
                d = np.sqrt(ex * ex + ey * ey + ez * ez)
                f2 = np.where(d < f1, f1, np.minimum(f2, d))
                f1 = np.minimum(f1, d)
    return f1, f2


def cells(p, seed=0):
    """a dome per cell (pebbles, scales seen as bumps, warts, cobbles) -> -1..1: +1 at a cell's point"""
    f1, _f2 = _worley(p, seed)
    return np.clip(1.0 - 2.0 * f1, -1.0, 1.0)


def cracks(p, seed=0):
    """the borders between cells pressed in (scales' outlines, cracked earth, tiles of hide) -> -1 on a border,
    +1 inside a cell"""
    f1, f2 = _worley(p, seed)
    return np.clip((f2 - f1) / 0.25, 0.0, 1.0) * 2.0 - 1.0


NOISES = {"fbm": fbm, "ridged": ridged, "cells": cells, "cracks": cracks, "perlin": perlin}


# ------------------------------------------------------------------------------------------------ smooth blends
def smin(a, b, k):
    """the smooth minimum (a polynomial fillet of radius ~k where a and b meet; k 0: the plain minimum)"""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def cmin(a, b, r):
    """the CHAMFER minimum (hg_sdf fOpUnionChamfer): where a and b meet, a flat 45-degree bevel r wide — a defined
    edge (a rim, a ridge, a plate's lip) where smin's fillet melts it; r 0: the plain minimum"""
    if r <= 0:
        return np.minimum(a, b)
    return np.minimum(np.minimum(a, b), (a + b - r) * math.sqrt(0.5))


def cmax(a, b, r):
    return -cmin(-a, -b, r)


def rmin(a, b, r):
    """the ROUND minimum (hg_sdf fOpUnionRound): where a and b meet square on, a true circular fillet of radius r -
    the radius a pattern-maker leaves in an inside corner (a.cast). smin's k is a width, not a radius: its fillet
    stands about a fifth less far out of a square corner. r 0: the plain minimum"""
    if r <= 0:
        return np.minimum(a, b)
    ua, ub = np.maximum(r - a, 0.0), np.maximum(r - b, 0.0)
    return np.maximum(r, np.minimum(a, b)) - np.sqrt(ua * ua + ub * ub)


def rmax(a, b, r):
    return -rmin(-a, -b, r)


EDGES = ("round", "chamfer", "fillet")   # (a join's profile: round = smin's fillet, chamfer = a flat bevel,
#                                           fillet = a true circular fillet of radius k: rmin)


def _rot(rot):
    """degrees (x, y, z) -> a 3x3 matrix (local -> canvas), the kit's order: CFrame.Angles(rx, ry, rz) = Rx @ Ry @ Rz
    (rbx.py _rot) — the same rot= turns a.box and s.box alike"""
    rx, ry, rz = (math.radians(float(v)) for v in rot)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mx @ my @ mz


# ------------------------------------------------------------------------------------------------ shapes
class Node:
    """a field: d(p) for points p (N, 3) in mm; bounds() its box; feature() its smallest feature (mm). How far it
    can change between two points: |d(p) - d(q)| <= slope() * |p - q| + margin() — slope 1 for a true distance; an
    operation that MOVES the surface by a bounded amount (relief, an inflate, a blend's fillet) adds that amount to
    the margin instead of steepening the slope (the narrow band culls on both, exactly)"""

    def d(self, p):
        raise NotImplementedError

    def bounds(self):
        raise NotImplementedError

    def feature(self):
        return math.inf

    def slope(self):
        return 1.0

    def margin(self):
        return 0.0

    def key(self):
        """what this field IS, as plain values (the sculpt cache's key: the same operations, the same mesh)"""
        return (type(self).__name__,) + tuple((k, _key(v)) for k, v in sorted(vars(self).items()) if k != "cutoff")


def _key(v):
    if isinstance(v, Node):
        return v.key()
    if isinstance(v, np.ndarray):
        if v.size > 64:   # (a sampled grid: its bytes' digest)
            import hashlib  # noqa: PLC0415

            return ("array", v.shape, hashlib.sha1(np.ascontiguousarray(v).tobytes()).hexdigest())
        return tuple(round(float(x), 6) for x in v.ravel())
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (list, tuple)):
        return tuple(_key(x) for x in v)
    return v


class Ball(Node):
    def __init__(self, c, r):
        self.c, self.r = np.asarray(c, dtype=np.float64), float(r)

    def d(self, p):
        return np.linalg.norm(p - self.c, axis=1) - self.r

    def bounds(self):
        return self.c - self.r, self.c + self.r

    def feature(self):
        return self.r


class Ellipsoid(Node):
    """radii (rx, ry, rz) about c, turned by rot (degrees): a bound on the true distance, exact on the surface"""

    def __init__(self, c, radii, rot=(0, 0, 0)):
        self.c, self.r, self.m = np.asarray(c, dtype=np.float64), np.asarray(radii, dtype=np.float64), _rot(rot)

    def d(self, p):
        q = (p - self.c) @ self.m   # (canvas -> local: m is orthonormal)
        k0 = np.linalg.norm(q / self.r, axis=1)
        k1 = np.linalg.norm(q / (self.r * self.r), axis=1)
        outside = k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)
        # inside, the outside bound's slope runs to hundreds near the long axis (a 40 x 4.5 x 4.5 limb culled into a
        # box, the review 2026-10-10): (k0 - 1) x the shortest radius — 0 on the surface, never steeper than 1, never
        # farther than the true distance
        return np.where(k0 >= 1.0, outside, (k0 - 1.0) * float(self.r.min()))

    def bounds(self):
        ext = np.abs(self.m) @ self.r
        return self.c - ext, self.c + ext

    def feature(self):
        return float(self.r.min())


class Capsule(Node):
    """a round cone from a (radius ra) to b (radius rb): a limb, a horn, a finger, a stroke's segment (exact)"""

    def __init__(self, a, b, ra, rb=None):
        self.a, self.b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
        self.ra, self.rb = float(ra), float(ra if rb is None else rb)

    def d(self, p):
        ba = self.b - self.a
        l2 = float(ba @ ba)
        if l2 < 1e-12:
            return np.linalg.norm(p - self.a, axis=1) - max(self.ra, self.rb)
        rr = self.ra - self.rb
        a2 = l2 - rr * rr
        if a2 <= 1e-12:   # (one end's ball swallows the other: just the bigger ball)
            big = (self.a, self.ra) if self.ra >= self.rb else (self.b, self.rb)
            return np.linalg.norm(p - big[0], axis=1) - big[1]
        il2 = 1.0 / l2
        pa = p - self.a
        y = pa @ ba
        z = y - l2
        x = pa * l2 - y[:, None] * ba
        x2 = np.einsum("ij,ij->i", x, x)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        out = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - self.ra   # (Inigo Quilez's exact round cone: the side,
        out = np.where(np.sign(y) * a2 * y2 < k, np.sqrt(x2 + y2) * il2 - self.ra, out)   # the a cap,
        out = np.where(np.sign(z) * a2 * z2 > k, np.sqrt(x2 + z2) * il2 - self.rb, out)   # the b cap: tested first
        return out

    def bounds(self):
        r = max(self.ra, self.rb)
        return np.minimum(self.a, self.b) - r, np.maximum(self.a, self.b) + r

    def feature(self):
        return min(self.ra, self.rb)


class Box(Node):
    """a box of size (sx, sy, sz) about c, its edges rounded `round` mm, turned by rot (degrees)"""

    def __init__(self, c, size, round=0.0, rot=(0, 0, 0)):
        self.c, self.h = np.asarray(c, dtype=np.float64), np.asarray(size, dtype=np.float64) / 2.0
        self.round, self.m = min(float(round), float(self.h.min())), _rot(rot)

    def d(self, p):
        q = np.abs((p - self.c) @ self.m) - (self.h - self.round)
        out = np.linalg.norm(np.maximum(q, 0.0), axis=1) + np.minimum(q.max(axis=1), 0.0)
        return out - self.round

    def bounds(self):
        ext = np.abs(self.m) @ self.h
        return self.c - ext, self.c + ext

    def feature(self):
        return float(self.h.min())


class Torus(Node):
    """a ring of radius R (to the tube's centre) and tube radius r about c, its axis local y, turned by rot"""

    def __init__(self, c, R, r, rot=(0, 0, 0)):
        self.c, self.R, self.r, self.m = np.asarray(c, dtype=np.float64), float(R), float(r), _rot(rot)

    def d(self, p):
        q = (p - self.c) @ self.m
        return np.hypot(np.hypot(q[:, 0], q[:, 2]) - self.R, q[:, 1]) - self.r

    def bounds(self):
        ext = np.abs(self.m) @ np.array([self.R + self.r, self.r, self.R + self.r])
        return self.c - ext, self.c + ext

    def feature(self):
        return self.r


class Grid(Node):
    """a sampled field (a mesh turned into distances: from_mesh): trilinear inside its box, the box's distance plus
    its band outside. Its distances are TRUE only within its band (band x voxel from the surface) — a blend wider than
    that near it fillets against a clamped value (too much clay): from_mesh's band grows with the blend it is added
    with"""

    def __init__(self, values, lo, voxel, band):
        self.v, self.lo, self.vox, self.band = np.asarray(values, dtype=np.float32), np.asarray(lo, dtype=np.float64), \
            float(voxel), float(band)
        self.hi = self.lo + (np.array(self.v.shape) - 1) * self.vox

    def d(self, p):
        g = (p - self.lo) / self.vox
        n = np.array(self.v.shape) - 1
        gc = np.clip(g, 0, n - 1e-6)
        i = np.floor(gc).astype(np.int64)
        f = gc - i
        out = np.zeros(len(p))
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                    out += w * self.v[i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz]
        outside = np.linalg.norm(np.maximum(np.maximum(self.lo - p, p - self.hi), 0.0), axis=1)
        return np.where(outside > 0, np.maximum(out, 0.0) + outside, out)

    def bounds(self):
        return self.lo, self.hi


# ------------------------------------------------------------------------------------------------ operations
class Union(Node):
    edge = "round"   # (set on the instance only when chamfer: every round join's cache key unchanged)

    def __init__(self, a, b, k=0.0, edge="round"):
        self.a, self.b, self.k = a, b, float(k)
        if edge != "round":
            self.edge = edge

    def d(self, p):
        if self.edge == "chamfer":
            return cmin(self.a.d(p), self.b.d(p), self.k)
        if self.edge == "fillet":
            return rmin(self.a.d(p), self.b.d(p), self.k)
        return smin(self.a.d(p), self.b.d(p), self.k)

    def bounds(self):
        (la, ha), (lb, hb) = self.a.bounds(), self.b.bounds()
        return np.minimum(la, lb), np.maximum(ha, hb)

    def feature(self):
        return min(self.a.feature(), self.b.feature())

    def slope(self):
        return max(self.a.slope(), self.b.slope())

    def margin(self):   # (the fillet lies at most k / 4 under the plain minimum; a round one r (sqrt 2 - 1))
        return max(self.a.margin(), self.b.margin()) + self.k * (0.42 if self.edge == "fillet" else 0.25)


class Subtract(Node):
    """a with b carved out of it, the edge filleted k"""

    edge = "round"

    def __init__(self, a, b, k=0.0, edge="round"):
        self.a, self.b, self.k = a, b, float(k)
        if edge != "round":
            self.edge = edge

    def d(self, p):
        if self.edge == "chamfer":
            return cmax(self.a.d(p), -self.b.d(p), self.k)
        if self.edge == "fillet":
            return rmax(self.a.d(p), -self.b.d(p), self.k)
        return smax(self.a.d(p), -self.b.d(p), self.k)

    def bounds(self):
        return self.a.bounds()

    def feature(self):
        return min(self.a.feature(), self.b.feature())

    def slope(self):
        return max(self.a.slope(), self.b.slope())

    def margin(self):
        return max(self.a.margin(), self.b.margin()) + self.k / 4.0


class Intersect(Node):
    edge = "round"

    def __init__(self, a, b, k=0.0, edge="round"):
        self.a, self.b, self.k = a, b, float(k)
        if edge != "round":
            self.edge = edge

    def d(self, p):
        if self.edge == "chamfer":
            return cmax(self.a.d(p), self.b.d(p), self.k)
        if self.edge == "fillet":
            return rmax(self.a.d(p), self.b.d(p), self.k)
        return smax(self.a.d(p), self.b.d(p), self.k)

    def bounds(self):
        (la, ha), (lb, hb) = self.a.bounds(), self.b.bounds()
        return np.maximum(la, lb), np.minimum(ha, hb)

    def feature(self):
        return min(self.a.feature(), self.b.feature())

    def slope(self):
        return max(self.a.slope(), self.b.slope())

    def margin(self):
        return max(self.a.margin(), self.b.margin()) + self.k / 4.0


def _weight(where, falloff, p):
    """1 inside the region, easing to 0 over `falloff` mm outside it (smoothstep); None: 1 everywhere"""
    if where is None:
        return 1.0
    dist = where.d(p)
    if falloff <= 0:
        return (dist <= 0).astype(np.float64)
    t = np.clip(1.0 - dist / falloff, 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Offset(Node):
    """the surface pushed out (amount > 0: inflate) or in (< 0: deflate), in a region or everywhere"""

    def __init__(self, a, amount, where=None, falloff=0.0):
        self.a, self.amount, self.where, self.falloff = a, float(amount), where, float(falloff)

    def d(self, p):
        return self.a.d(p) - self.amount * _weight(self.where, self.falloff, p)

    def bounds(self):
        lo, hi = self.a.bounds()
        e = max(self.amount, 0.0)
        return lo - e, hi + e

    def feature(self):
        return self.a.feature()

    def slope(self):
        return self.a.slope()

    def margin(self):   # (the surface moves by at most |amount| anywhere — a hard-edged region's step included)
        return self.a.margin() + abs(self.amount)


class Displace(Node):
    """surface relief: the distance moved by amp x noise(p / scale) — about +-amp mm, features ~scale mm apart.
    scale (sx, sy, sz): stretched along an axis — bark and muscle fibre run up a form, rock strata lie flat"""

    def __init__(self, a, amp, scale, kind="fbm", octaves=4, seed=0, where=None, falloff=0.0):
        if kind not in NOISES:
            raise ValueError(f'noise kind "{kind}" — use one of {", ".join(NOISES)}')
        sc = np.broadcast_to(np.asarray(scale, dtype=np.float64), (3,)).copy()
        if np.any(sc <= 0):
            raise ValueError(f"noise scale must be > 0 (mm): {scale}")
        self.a, self.amp, self.scale, self.kind = a, float(amp), sc, kind
        self.octaves, self.seed, self.where, self.falloff = int(octaves), int(seed), where, float(falloff)

    cutoff = math.inf   # (Canvas.sample sets its band here: farther from the surface than amp + band, the noise
    #   cannot change what the mesher sees — the field there is clamped to the band anyway)

    def d(self, p):
        base = self.a.d(p)
        w = _weight(self.where, self.falloff, p)
        if np.isscalar(w):
            w = np.full(len(p), float(w))
        idx = np.nonzero((np.abs(base) <= abs(self.amp) * 1.3 + self.cutoff) & (w > 0))[0]
        if not len(idx):
            return base
        fn = NOISES[self.kind]
        q = p[idx] / self.scale
        n = fn(q, seed=self.seed) if self.kind in ("cells", "cracks", "perlin") else fn(q, self.octaves, self.seed)
        out = base.copy()
        out[idx] -= self.amp * n * w[idx]
        return out

    def bounds(self):
        lo, hi = self.a.bounds()
        return lo - abs(self.amp), hi + abs(self.amp)

    def feature(self):
        return min(self.a.feature(), float(self.scale.min()) / 2.0)

    def slope(self):
        return self.a.slope()

    def margin(self):   # (the noise spans about +-1.25: the surface moves by at most 1.25 |amp| either way)
        return self.a.margin() + 2.5 * abs(self.amp)


class Stamp(Displace):
    """surface relief from a REAL SCAN's height map (a CC0 ambientCG displacement — bone, rock, bark, plaster) at its
    real size: tile_mm per repeat, depth mm, projected three ways (triplanar about `centre`, weighted by the surface's
    direction from it — a rounded organic form). Noise is a guess at a surface; a scan is one"""

    def __init__(self, a, height, tile_mm, depth, centre=(0, 0, 0), where=None, falloff=0.0):
        h = np.asarray(height, dtype=np.float32)
        if h.ndim != 2 or min(h.shape) < 4:
            raise ValueError("stamp: a 2D height map")
        if tile_mm <= 0:
            raise ValueError("stamp: tile_mm must be > 0")
        h = h - float(h.mean())
        s_ = float(np.abs(h).max()) or 1.0
        self.a, self.amp, self.scale, self.kind = a, float(depth), np.full(3, float(tile_mm)), "stamp"
        self.octaves, self.seed, self.where, self.falloff = 0, 0, where, float(falloff)
        self.height = (h / s_).astype(np.float32)          # (-1..1, mean 0: the surface moves both ways)
        self.centre = np.asarray(centre, dtype=np.float64)

    def _sample(self, u, v):
        h = self.height
        n0, n1 = h.shape
        fu, fv = (u * n0) % n0, (v * n1) % n1
        i, j = np.floor(fu).astype(np.int64) % n0, np.floor(fv).astype(np.int64) % n1
        a, b = fu - np.floor(fu), fv - np.floor(fv)
        i1, j1 = (i + 1) % n0, (j + 1) % n1
        return (h[i, j] * (1 - a) * (1 - b) + h[i1, j] * a * (1 - b) + h[i, j1] * (1 - a) * b + h[i1, j1] * a * b)

    def d(self, p):
        base = self.a.d(p)
        w = _weight(self.where, self.falloff, p)
        if np.isscalar(w):
            w = np.full(len(p), float(w))
        idx = np.nonzero((np.abs(base) <= abs(self.amp) * 1.3 + self.cutoff) & (w > 0))[0]
        if not len(idx):
            return base
        q = p[idx] / self.scale[0]
        dirn = np.abs(p[idx] - self.centre) ** 4
        dirn /= np.maximum(dirn.sum(axis=1, keepdims=True), 1e-12)
        val = (dirn[:, 0] * self._sample(q[:, 1], q[:, 2]) + dirn[:, 1] * self._sample(q[:, 0], q[:, 2])
               + dirn[:, 2] * self._sample(q[:, 0], q[:, 1]))
        out = base.copy()
        out[idx] -= self.amp * val * w[idx]
        return out

    def margin(self):   # (the map spans -1..1: the surface moves by at most |depth| either way)
        return self.a.margin() + abs(self.amp)


def load_height(path, size=512):
    """a scan's displacement image -> a size x size float32 height map 0..1, cached beside it as .npy (PIL outside
    Blender, Blender's own image loader inside it — the build has no PIL)"""
    path = os.path.expanduser(str(path))
    cache = os.path.splitext(path)[0] + f"_h{int(size)}.npy"
    if os.path.isfile(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
        return np.load(cache)
    try:
        from PIL import Image  # noqa: PLC0415

        im = Image.open(path).convert("L").resize((int(size), int(size)))
        h = np.asarray(im, dtype=np.float32) / 255.0
    except ImportError:
        import bpy  # noqa: PLC0415

        img = bpy.data.images.load(path, check_existing=True)
        img.scale(int(size), int(size))
        px = np.empty(int(size) * int(size) * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        h = px.reshape(int(size), int(size), 4)[:, :, :3].mean(axis=2)
        bpy.data.images.remove(img)
    try:
        np.save(cache, h)
    except OSError:
        pass
    return h


class Mirror(Node):
    """a made symmetric across the plane axis = 0: a and its reflection together (a shape on either side gets its
    twin — folding with |x| emptied anything authored on the - side, the review 2026-10-10)"""

    def __init__(self, a, axis=0):
        self.a, self.axis = a, int(axis)

    def d(self, p):
        q = p.copy()
        q[:, self.axis] = -q[:, self.axis]
        return np.minimum(self.a.d(p), self.a.d(q))

    def bounds(self):
        lo, hi = self.a.bounds()
        m = max(abs(lo[self.axis]), abs(hi[self.axis]))
        lo, hi = lo.copy(), hi.copy()
        lo[self.axis], hi[self.axis] = -m, m
        return lo, hi

    def feature(self):
        return self.a.feature()

    def slope(self):
        return self.a.slope()

    def margin(self):
        return self.a.margin()


class Reflect(Node):
    """a mirrored across the plane axis = 0 — its reflection ALONE (Mirror is a with its reflection, together)"""

    def __init__(self, a, axis=0):
        self.a, self.axis = a, int(axis)

    def d(self, p):
        q = np.asarray(p, dtype=np.float64).copy()
        q[:, self.axis] = -q[:, self.axis]
        return self.a.d(q)

    def bounds(self):
        lo, hi = self.a.bounds()
        lo, hi = lo.copy(), hi.copy()
        lo[self.axis], hi[self.axis] = -hi[self.axis], -lo[self.axis]
        return lo, hi

    def feature(self):
        return self.a.feature()

    def slope(self):
        return self.a.slope()

    def margin(self):
        return self.a.margin()


def sdf2d(rings, pts, chunk=20000):
    """the exact signed distance (2D, mm) from points (N, 2) to a traced outline and its holes: rings [outline,
    hole, ...] of (u, v) points; inside (even-odd) negative"""
    pts = np.asarray(pts, dtype=np.float64)
    segs = []
    for ring in rings:
        r = np.asarray(ring, dtype=np.float64)
        if len(r) >= 3:
            segs.append(np.concatenate([r, np.roll(r, -1, axis=0)], axis=1))   # (x0, y0, x1, y1)
    seg = np.concatenate(segs) if segs else np.zeros((0, 4))
    out = np.empty(len(pts))
    for s_ in range(0, len(pts), chunk):
        q = pts[s_:s_ + chunk]
        x, y = q[:, :1], q[:, 1:2]
        x0, y0, x1, y1 = seg[:, 0], seg[:, 1], seg[:, 2], seg[:, 3]
        ex, ey = x1 - x0, y1 - y0
        ll = np.maximum(ex * ex + ey * ey, 1e-18)
        t = np.clip(((x - x0) * ex + (y - y0) * ey) / ll, 0.0, 1.0)
        dx, dy = x - (x0 + t * ex), y - (y0 + t * ey)
        dist = np.sqrt((dx * dx + dy * dy).min(axis=1))
        crosses = ((y0 > y) != (y1 > y)) & (x < x0 + (y - y0) * ex / np.where(np.abs(ey) > 1e-18, ey, 1e-18))
        inside = (crosses.sum(axis=1) % 2) == 1
        out[s_:s_ + chunk] = np.where(inside, -dist, dist)
    return out


class Silhouette(Node):
    """a TRACED VIEW's outline (+ its holes), mm, extruded through the object along its view axis: plane "side" —
    (u forward = -z, v up = y), extruded along x; "front" — (u = x, v = y), extruded along z. Its exact 2D distance
    is rastered once at `res` mm and sampled bilinearly (a voxel's accuracy at corners). Alone it is a prism; two of
    them intersected are the photos' visual hull (Canvas.views)"""

    EXTENT = 1.0e4   # (mm: how far the prism runs along its axis — the other view, or the clay, bounds it)

    def __init__(self, rings, plane, res, min_mm=0.0):
        """min_mm > 0: the outline's features thinner than min_mm dropped — islands and spurs opened away, slits
        closed (a keep trim through a thin island leaves a FIN in the clay: a skull's styloid seen side-on did)"""
        if plane not in ("side", "front"):
            raise ValueError(f'silhouette plane "{plane}" — "side" or "front"')
        pts = np.concatenate([np.asarray(r, dtype=np.float64) for r in rings if len(r) >= 3])
        self.plane, self.res = plane, float(res)
        pad = 8 * self.res + max(0.0, float(min_mm))
        self.lo2 = pts.min(axis=0) - pad
        n = np.ceil((pts.max(axis=0) + pad - self.lo2) / self.res).astype(int) + 1
        gu, gv = np.meshgrid(np.arange(n[0]) * self.res + self.lo2[0], np.arange(n[1]) * self.res + self.lo2[1],
                             indexing="ij")
        self.v = sdf2d(rings, np.stack([gu.ravel(), gv.ravel()], axis=1)).reshape(n).astype(np.float32)
        self.hi2 = self.lo2 + (n - 1) * self.res
        if min_mm > 0:
            self.min_mm = float(min_mm)   # (set only when used: the cache keys of every other silhouette unchanged)
            self.v = _reopened(self.v, self.res, self.min_mm)

    @classmethod
    def from_mask(cls, mask, lo, res, plane, min_mm=0.0):
        """a silhouette from a RASTER — rbx_refmesh.outline(ref, view): the exact outline of a reference mesh, no
        picture traced (a traced outline put a skull's crown 7 mm off) -> Silhouette"""
        if plane not in ("side", "front"):
            raise ValueError(f'silhouette plane "{plane}" — "side" or "front"')
        self = cls.__new__(cls)
        self.plane, self.res = plane, float(res)
        self.lo2 = np.asarray(lo, dtype=np.float64)
        # (a raster's distance is a STAIRCASE of pixel steps: swept through the object as a prism, every step became
        #  a horizontal ridge across a skull's forehead and occiput — blurred over ~2 px it is a smooth edge again)
        self.v = smooth_grid(sdf_from_mask(mask, self.res), passes=4)
        self.hi2 = self.lo2 + (np.array(self.v.shape) - 1) * self.res
        if min_mm > 0:
            self.min_mm = float(min_mm)
            self.v = _reopened(self.v, self.res, self.min_mm)
        return self

    def thin(self, min_mm):
        """where the outline has features thinner than min_mm (islands, spurs, slits) -> [(u, v) mm, ...] one per
        feature, biggest first"""
        k = max(1, int(round(min_mm / 2.0 / self.res)))
        mask = self.v < 0
        changed = _clean(mask, k) != mask
        return [(float(self.lo2[0] + cu * self.res), float(self.lo2[1] + cv * self.res))
                for cu, cv in _blob_centres(changed)]

    def _uv(self, p):
        return np.stack([-p[:, 2], p[:, 1]], axis=1) if self.plane == "side" else p[:, :2]

    def d(self, p):
        q = self._uv(np.asarray(p, dtype=np.float64))
        g = (q - self.lo2) / self.res
        n = np.array(self.v.shape) - 1
        gc = np.clip(g, 0, n - 1e-6)
        i = np.floor(gc).astype(np.int64)
        f = gc - i
        out = np.zeros(len(q))
        for du in (0, 1):
            for dv in (0, 1):
                w = (f[:, 0] if du else 1 - f[:, 0]) * (f[:, 1] if dv else 1 - f[:, 1])
                out += w * self.v[i[:, 0] + du, i[:, 1] + dv]
        outside = np.linalg.norm(np.maximum(np.maximum(self.lo2 - q, q - self.hi2), 0.0), axis=1)
        return np.where(outside > 0, np.maximum(out, 0.0) + outside, out)

    def bounds(self):
        e = self.EXTENT
        if self.plane == "side":   # (u = -z, v = y; any x)
            return np.array([-e, self.lo2[1], -self.hi2[0]]), np.array([e, self.hi2[1], -self.lo2[0]])
        return np.array([self.lo2[0], self.lo2[1], -e]), np.array([self.hi2[0], self.hi2[1], e])

    def margin(self):
        return self.res   # (bilinear between exact samples: within about a pixel at a corner)


def _morph(mask, k, erode):
    """a 2D mask eroded (erode=True) or dilated by a disk of k px (outside the grid counts as outside)"""
    h, w = mask.shape
    p = np.pad(mask, k, constant_values=False)
    out = np.ones_like(mask) if erode else np.zeros_like(mask)
    for du in range(-k, k + 1):
        for dv in range(-k, k + 1):
            if du * du + dv * dv <= k * k:
                s = p[k + du:k + du + h, k + dv:k + dv + w]
                out = (out & s) if erode else (out | s)
    return out


def _grow(mask, r):
    """a 2D mask dilated by a square of r px — doubling shifts, cheap for a wide r"""
    out = mask.copy()
    for axis in (0, 1):
        done, step = 0, 1
        while done < r:
            s = min(step, r - done)
            grown = out.copy()
            if axis == 0:
                grown[s:] |= out[:-s]
                grown[:-s] |= out[s:]
            else:
                grown[:, s:] |= out[:, :-s]
                grown[:, :-s] |= out[:, s:]
            out, done, step = grown, done + s, step * 2
    return out


def _clean(mask, k):
    """features thinner than 2k px gone: an opening (islands, spurs) then a closing (slits, pinholes)"""
    opened = _morph(_morph(mask, k, True), k, False)
    return _morph(_morph(opened, k, False), k, True)


def _reopened(v, res, min_mm, chunk=4096):
    """a rastered 2D distance field with its features thinner than min_mm dropped: the mask cleaned, the distance
    re-measured near what changed (to the nearest pixel of the other side, less half a pixel) and kept exact
    everywhere else"""
    k = max(1, int(round(min_mm / 2.0 / res)))
    mask = v < 0
    clean = _clean(mask, k)
    changed = clean != mask
    if not changed.any():
        return v
    near = _grow(changed, 2 * k + int(np.ceil(2.0 * min_mm / res)) + 2)
    # the cleaned outline as sub-pixel points: between every two neighbouring pixels on either side of it — at the
    # ORIGINAL field's zero crossing where neither pixel changed (exact there), half-way where one did
    edge = []
    for axis in (0, 1):
        sl_a = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        sl_b = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        cross = clean[sl_a] != clean[sl_b]
        idx = np.argwhere(cross).astype(np.float64)
        va, vb = v[sl_a][cross].astype(np.float64), v[sl_b][cross].astype(np.float64)
        same = ~changed[sl_a][cross] & ~changed[sl_b][cross]
        t = np.where(same, va / np.where(same, va - vb, 1.0), 0.5)
        idx[:, axis] += np.clip(t, 0.0, 1.0)
        edge.append(idx)
    edge = np.concatenate(edge)
    out = v.copy()
    q_all = np.argwhere(near)
    if not len(q_all) or not len(edge):
        return out
    best = np.full(len(q_all), np.inf)
    for i in range(0, len(q_all), chunk):
        q = q_all[i:i + chunk].astype(np.float64)
        for j in range(0, len(edge), chunk):
            d2 = ((q[:, None, :] - edge[None, j:j + chunk, :]) ** 2).sum(axis=2).min(axis=1)
            best[i:i + chunk] = np.minimum(best[i:i + chunk], d2)
    dist = np.sqrt(best) * res
    out[q_all[:, 0], q_all[:, 1]] = np.where(clean[q_all[:, 0], q_all[:, 1]], -dist, dist)
    return out


def _blob_centres(mask):
    """the connected blobs of a 2D mask (4-neighbour) -> [(i, j) centre px], biggest first"""
    seen = np.zeros_like(mask)
    blobs = []
    for start in map(tuple, np.argwhere(mask)):
        if seen[start]:
            continue
        stack, cells = [start], []
        seen[start] = True
        while stack:
            i, j = stack.pop()
            cells.append((i, j))
            for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a < mask.shape[0] and 0 <= b < mask.shape[1] and mask[a, b] and not seen[a, b]:
                    seen[a, b] = True
                    stack.append((a, b))
        blobs.append((len(cells), np.mean(cells, axis=0)))
    return [tuple(c) for _n, c in sorted(blobs, key=lambda b: -b[0])]


def sdf_from_mask(mask, res, reach=15.0, chunk=2048):
    """a raster mask's signed distance (mm, inside negative), exact within `reach` mm of its edge and clamped beyond:
    each pixel against the pixels on the other side of the edge (brute force over the edge's pixels, chunked)"""
    m = np.asarray(mask, dtype=bool)
    inner = m & ~_morph(m, 1, True)
    outer = ~m & _morph(m, 1, False)
    out = np.where(m, -reach, reach).astype(np.float32)
    r_px = reach / res
    for side, edge in ((True, outer), (False, inner)):
        e = np.argwhere(edge).astype(np.float32)
        if not len(e):
            continue
        near = _grow(edge, int(np.ceil(r_px)) + 1) & (m == side)
        q = np.argwhere(near)
        best = np.full(len(q), np.inf, dtype=np.float32)
        for i in range(0, len(q), chunk):
            qi = q[i:i + chunk].astype(np.float32)
            for j in range(0, len(e), chunk * 4):
                ej = e[j:j + chunk * 4]
                d2 = (qi[:, None, 0] - ej[None, :, 0]) ** 2 + (qi[:, None, 1] - ej[None, :, 1]) ** 2
                best[i:i + chunk] = np.minimum(best[i:i + chunk], d2.min(axis=1))
        dist = np.minimum((np.sqrt(best) - 0.5) * res, reach)
        out[q[:, 0], q[:, 1]] = np.where(side, -dist, dist)
    return out


def smooth_grid(g, passes=4):
    """a 2D distance grid blurred by `passes` 3x3 box filters (edges clamped): a raster's stair-steps gone, the zero
    line where it was to within a fraction of a pixel (a box blur of a signed distance keeps its straight runs)"""
    out = np.asarray(g, dtype=np.float32).copy()
    for _ in range(int(passes)):
        p = np.pad(out, 1, mode="edge")
        out = sum(p[1 + di:1 + di + out.shape[0], 1 + dj:1 + dj + out.shape[1]]
                  for di in (-1, 0, 1) for dj in (-1, 0, 1)) / 9.0
    return out.astype(np.float32)


def _bilinear(grid, lo, res, u, v):
    """sample a 2D grid (cell (0, 0) at lo, res apart) at (u, v) arrays; outside it: its edge value plus the way out"""
    n = np.array(grid.shape) - 1
    gu, gv = (u - lo[0]) / res, (v - lo[1]) / res
    cu, cv = np.clip(gu, 0, n[0] - 1e-6), np.clip(gv, 0, n[1] - 1e-6)
    i, j = np.floor(cu).astype(np.int64), np.floor(cv).astype(np.int64)
    fu, fv = cu - i, cv - j
    val = (grid[i, j] * (1 - fu) * (1 - fv) + grid[i + 1, j] * fu * (1 - fv) + grid[i, j + 1] * (1 - fu) * fv
           + grid[i + 1, j + 1] * fu * fv)
    away = np.hypot(np.maximum(np.maximum(-gu, gu - n[0]), 0), np.maximum(np.maximum(-gv, gv - n[1]), 0)) * res
    return np.where(away > 0, np.maximum(val, 0) + away, val)


class SliceStack(Node):
    """a LOFT through measured horizontal sections: levels [(y mm, mask (nx, nz) bool, (x0, z0), res mm)] — e.g. one
    bone's pieces of a reference's slices (rbx_refmesh.slice_pieces) — each section's 2D distance, blended level to
    level by height, capped flat at the first and last. A form built from the real object's own sections, not from
    ellipsoids placed by eye"""

    def __init__(self, levels):
        if len(levels) < 2:
            raise ValueError("a slice stack needs 2+ levels")
        levels = sorted(levels, key=lambda lv: lv[0])
        self.ys = np.array([float(lv[0]) for lv in levels])
        self.grids = [smooth_grid(sdf_from_mask(lv[1], float(lv[3])), passes=4) for lv in levels]   # (no stair-steps)
        self.los = [tuple(float(x) for x in lv[2]) for lv in levels]
        self.res = [float(lv[3]) for lv in levels]
        self.box = (np.array([min(lo[0] for lo in self.los), self.ys[0], min(lo[1] for lo in self.los)]),
                    np.array([max(lo[0] + (g.shape[0] - 1) * r for lo, g, r in zip(self.los, self.grids, self.res)),
                              self.ys[-1],
                              max(lo[1] + (g.shape[1] - 1) * r for lo, g, r in zip(self.los, self.grids, self.res))]))

    def d(self, p):
        p = np.asarray(p, dtype=np.float64)
        y = p[:, 1]
        k = np.clip(np.searchsorted(self.ys, y) - 1, 0, len(self.ys) - 2)
        out = np.empty(len(p))
        for i in np.unique(k):
            sel = k == i
            a = _bilinear(self.grids[i], self.los[i], self.res[i], p[sel, 0], p[sel, 2])
            b = _bilinear(self.grids[i + 1], self.los[i + 1], self.res[i + 1], p[sel, 0], p[sel, 2])
            t = np.clip((y[sel] - self.ys[i]) / max(self.ys[i + 1] - self.ys[i], 1e-9), 0.0, 1.0)
            out[sel] = a * (1 - t) + b * t
        cap = np.maximum(self.ys[0] - y, y - self.ys[-1])   # (above the top level / below the bottom: flat caps)
        return np.where(cap > 0, np.where(out > 0, np.hypot(np.maximum(out, 0), cap), cap), out)

    def bounds(self):
        return self.box

    def slope(self):
        return 1.5   # (a blend between two sections leans: conservative for the band's culling)


def trace_rings(side=None, front=None, length=None, width=None):
    """traced views (kit trace's design units) -> mm rings for Canvas.views. side: (outline, holes, height_ratio) —
    u 0 back .. 1 front over `length` mm, h up in lengths -> (forward, up) centred on the side's middle; front:
    (outline, holes, height_ratio) — u across the picture (the model's right on its LEFT), h up in widths -> (x, up);
    its width from the side's height over its own ratio (the same height seen from the front), else `width`"""
    side_rings = front_rings = None
    if side is not None:
        if not length:
            raise ValueError("trace_rings: the side's real length (mm)")
        outline, holes, _hr = side
        side_rings = [[((u - 0.5) * length, h * length) for u, h in ring] for ring in [outline] + list(holes)]
    if front is not None:
        outline, holes, hr_front = front
        if side is not None and side[2] and hr_front:
            width = side[2] * length / hr_front
        if not width:
            raise ValueError("trace_rings: the front's real width (mm) — give a side trace, or width=")
        front_rings = [[((0.5 - u) * width, h * width) for u, h in ring] for ring in [outline] + list(holes)]
    return side_rings, front_rings


def _spine(root):
    """a canvas's operations, newest first: the left spine of add / carve / keep / relief / inflate — each link's
    `a` is everything before it; the last entry is the first clay"""
    out, n = [], root
    while isinstance(n, (Union, Subtract, Intersect, Displace, Offset)):
        out.append(n)
        n = n.a
    return out + [n]


def prune_masks(root, centers, reach, band):
    """which operations can touch the band in each block -> (spine, keep (len(spine), len(centers)) bool): an add /
    carve whose shape is, by its slope bound, farther than band + its blend from every point within `reach` of the
    block's centre leaves the clipped field unchanged (smin / smax are exact once two values differ by the blend);
    a keep (intersect) the block lies deep inside likewise. Reliefs, inflates and the first clay always stay"""
    spine = _spine(root)
    c = np.asarray(centers, dtype=np.float64)
    keep = np.ones((len(spine), len(c)), dtype=bool)
    for i, n in enumerate(spine[:-1]):
        if isinstance(n, (Union, Subtract, Intersect)):
            db = n.b.d(c)
            slack = reach * n.b.slope() + n.b.margin()
            if isinstance(n, Intersect):
                keep[i] = db + slack >= -(band + n.k)
            else:
                keep[i] = db - slack <= band + n.k
    return spine, keep


def pruned(spine, mask):
    """the tree with only the operations `mask` keeps (copies of the links: the canvas's own tree is untouched)"""
    node = spine[-1]
    for n, k in zip(reversed(spine[:-1]), reversed(list(mask[:-1]))):
        if k:
            n2 = copy.copy(n)
            n2.a = node
            node = n2
    return node


def strap_node(points, height, thickness, round=None):
    """a flat plate along a path: one rounded Box per span, turned so its z runs along the span (rot x, y from the
    span's direction, as Canvas.strap documents), each overlapping the next by its thickness and joined with a
    fillet of half its thickness so the turns read as one plate"""
    pts = [np.asarray(q, dtype=np.float64) for q in points]
    if len(pts) < 2:
        raise ValueError("a strap needs 2+ points")
    hs = [float(height)] * len(pts) if np.isscalar(height) else [float(h) for h in height]
    ts = [float(thickness)] * len(pts) if np.isscalar(thickness) else [float(t) for t in thickness]
    if len(hs) != len(pts) or len(ts) != len(pts):
        raise ValueError(f"a strap's heights / thicknesses: one per point ({len(pts)}), or one for all")
    node = None
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = b - a
        length = float(np.linalg.norm(d))
        if length < 1e-9:
            continue
        u = d / length
        rot = (math.degrees(math.atan2(-u[1], u[2])), math.degrees(math.asin(max(-1.0, min(1.0, u[0])))), 0.0)
        t, h = (ts[i] + ts[i + 1]) / 2.0, (hs[i] + hs[i + 1]) / 2.0
        r = min(t, h) * 0.3 if round is None else min(float(round), min(t, h) / 2.0 - 1e-6)
        # (overlapping its neighbour by t / 2 at an INNER joint only: past the path's two ends that overlap stood out
        #  as a square block — "a white cube clipping at its root", a judge)
        lo = t / 2.0 if i > 0 else 0.0
        hi = t / 2.0 if i < len(pts) - 2 else 0.0
        mid = (a + b) / 2.0 + u * (hi - lo) / 2.0
        seg = Box(tuple(mid), (t, h, length + lo + hi), round=r, rot=rot)
        node = seg if node is None else Union(node, seg, t * 0.5)
    if node is None:
        raise ValueError("a strap's points are all one point")
    return node


def stroke_node(points, radius):
    """a chain of round cones through the points, the radius per point (or one for all): one clay stroke"""
    pts = [np.asarray(q, dtype=np.float64) for q in points]
    if len(pts) < 2:
        raise ValueError("a stroke needs 2+ points")
    rs = [float(radius)] * len(pts) if np.isscalar(radius) else [float(r) for r in radius]
    if len(rs) != len(pts):
        raise ValueError(f"a stroke's radii: one per point ({len(pts)}), or one for all")
    node = Capsule(pts[0], pts[1], rs[0], rs[1])
    for i in range(1, len(pts) - 1):
        node = Union(node, Capsule(pts[i], pts[i + 1], rs[i], rs[i + 1]))
    return node


# ------------------------------------------------------------------------------------------------ the canvas
AXES = {"x": 0, "y": 1, "z": 2}


class Canvas:
    """a sculpt: operations in order on one field. Every add / carve / keep takes blend= (mm): the fillet where the
    new clay meets the old. mirror="x": every operation from here on is mirrored across x = 0."""

    def __init__(self, voxel=0.5, mirror=None):
        if voxel <= 0:
            raise ValueError("voxel must be > 0 (mm)")
        self.voxel = float(voxel)
        self.root = None
        self.mirror_axis = AXES[mirror] if mirror else None
        self.log = []   # [(op, what, its smallest feature mm)] — lost() reads it
        self.on_done = None   # (a.sculpt sets it: done() builds the part)
        self.stats = {}
        self.warnings = []   # (a.sculpt reports them with the part: a crease that never met the surface)
        self.prune = True    # (sample(): each block's own tree — exact after the band's clip; False: the whole tree)
        self.threads = None  # (sample()'s worker threads: None = every core, 1 = one)
        self.brushes = []    # (s.brush: sculpt brushes on the meshed surface, in order — rbx_brushes)
        self.fit = None      # (s.fit_to: a stiff fit toward a reference surface after meshing — fit_field)

    def _sym(self, node):
        return Mirror(node, self.mirror_axis) if self.mirror_axis is not None else node

    def _note(self, op, what, feature):
        self.log.append((op, what, float(feature)))

    # -- clay
    def add(self, node, blend=0.0, what="shape", edge="round"):
        if edge not in EDGES:
            raise ValueError(f'edge "{edge}": one of {", ".join(EDGES)}')
        node = self._sym(node)
        self.root = node if self.root is None else Union(self.root, node, blend, edge)
        self._note("add", what, node.feature())
        return self

    def carve(self, node, blend=0.0, what="shape", edge="round"):
        if self.root is None:
            raise ValueError("carve: nothing to carve yet — add clay first")
        if edge not in EDGES:
            raise ValueError(f'edge "{edge}": one of {", ".join(EDGES)}')
        self.root = Subtract(self.root, self._sym(node), blend, edge)
        self._note("carve", what, node.feature())
        return self

    def keep(self, node, blend=0.0, what="shape", edge="round"):
        if self.root is None:
            raise ValueError("keep: nothing to trim yet — add clay first")
        if edge not in EDGES:
            raise ValueError(f'edge "{edge}": one of {", ".join(EDGES)}')
        # (mirrored, a keep is the shape's keep AND its reflection's, one after the other — as an add adds both and
        #  a carve carves both. The union of the two kept nearly everything: a sword's lens section, its second cone
        #  mirrored, left the blade 100 mm thick)
        self.root = Intersect(self.root, node, blend, edge)
        if self.mirror_axis is not None:
            self.root = Intersect(self.root, Reflect(node, self.mirror_axis), blend, edge)
        self._note("keep", what, node.feature())
        return self

    def ball(self, c, r, blend=0.0, carve=False, edge="round"):
        return (self.carve if carve else self.add)(Ball(c, r), blend, "ball", edge)

    def ellipsoid(self, c, radii, rot=(0, 0, 0), blend=0.0, carve=False, edge="round"):
        return (self.carve if carve else self.add)(Ellipsoid(c, radii, rot), blend, "ellipsoid", edge)

    def capsule(self, a, b, ra, rb=None, blend=0.0, carve=False, edge="round"):
        return (self.carve if carve else self.add)(Capsule(a, b, ra, rb), blend, "capsule", edge)

    def box(self, c, size, round=0.0, rot=(0, 0, 0), blend=0.0, carve=False, edge="round"):
        return (self.carve if carve else self.add)(Box(c, size, round, rot), blend, "box", edge)

    def torus(self, c, R, r, rot=(0, 0, 0), blend=0.0, carve=False, edge="round"):
        return (self.carve if carve else self.add)(Torus(c, R, r, rot), blend, "torus", edge)

    def stroke(self, points, radius, blend=0.0, carve=False, edge="round"):
        """clay pulled along a path (a brow, a tendon, a root, a horn's ridge): radius per point tapers it"""
        return (self.carve if carve else self.add)(stroke_node(points, radius), blend, "stroke", edge)

    def strap(self, points, height, thickness, round=None, blend=0.0, carve=False):
        """a FLAT PLATE swept along a path (a jaw's rising branch, a cheekbone's arch, a rib, a strap, a rim): rounded
        boxes `thickness` across the path and `height` in the plane through it and the vertical (along z when the path
        is vertical) — one value or one per point; edges rounded `round` mm (default 0.3 x the thinner side). A chain
        of ellipsoids (a stroke, the old plate helper) has a ROUND section: bone built that way read as tubes and
        slabs ("a round tube on the side", "melted" — fresh judges, 2026-10-11)"""
        node = strap_node(points, height, thickness, round)
        return (self.carve if carve else self.add)(node, blend, "strap")

    def crease(self, points, width, blend=None, snap=False):
        """a line pressed in (a wrinkle, an eyelid, a seam between plates): a stroke of width / 2 carved, its edge
        softened by blend (default a third of the width). snap=True: the path laid ON the surface first (on_surface)
        — a path drawn by eye floats over a dome or sinks under it, and a crease that never meets the surface cuts
        nothing (a skull's sutures, 4 mm above its vault, were 'entirely absent' — a judge, 2026-10-11): warned"""
        r = float(width) / 2.0
        if snap:
            points = self._lay_on(points, r)
        elif self.root is not None:
            off = self._off_surface(points, r)
            if off is not None:
                self.warnings.append(f"a crease floats {off:+.1f} mm off the surface over most of its path (cuts "
                                     f"little or nothing) — crease(..., snap=True) lays it on")
        return self.carve(stroke_node(points, r), r * 0.66 if blend is None else blend, "crease")

    def on_surface(self, points, depth=0.0, steps=10):
        """points moved onto the clay's surface as it stands NOW, each along the field's gradient (a suture, a seam, a
        vein drawn by eye) — depth mm under it (negative: above it) -> [(x, y, z)]"""
        if self.root is None:
            raise ValueError("on_surface: no surface yet — add clay first")
        p = np.asarray(points, dtype=np.float64).reshape(-1, 3).copy()
        h = max(self.voxel * 0.5, 1e-3)
        for _ in range(steps):
            d = self.root.d(p) + depth
            g = np.stack([(self.root.d(p + e) - self.root.d(p - e)) / (2 * h) for e in np.eye(3) * h], axis=1)
            n = np.linalg.norm(g, axis=1)
            n[n < 1e-9] = 1.0
            step = np.clip(d / n, -20.0, 20.0)   # (a field that is not exact — smooth unions, relief: small steps)
            p -= (step / n)[:, None] * g
            if np.max(np.abs(d)) < 0.01:
                break
        return [tuple(float(c) for c in q) for q in p]

    def _lay_on(self, points, r, passes=6):
        """a path laid on the surface with as FEW points as keep it there: its points snapped, then a point added only
        where a span's chord sinks or lifts more than r / 4 off the surface (two snapped ends alone span a chord that
        sinks into a dome). Few: a stroke is one capsule per span, and every capsule is evaluated at every voxel — a
        point every 1.5 mm made four skull sutures 280 capsules and doubled a 25-minute mesh"""
        pts = [np.asarray(q, dtype=np.float64) for q in self.on_surface(points)]
        for _ in range(passes):
            mids = [(a + b) / 2.0 for a, b in zip(pts, pts[1:])]
            off = np.abs(self.root.d(np.asarray(mids))) > r * 0.25
            if not off.any():
                break
            fixed = iter(self.on_surface([m for m, o in zip(mids, off) if o]))
            out = [pts[0]]
            for b, o in zip(pts[1:], off):
                if o:
                    out.append(np.asarray(next(fixed)))
                out.append(b)
            pts = out
        return [tuple(float(c) for c in q) for q in pts]

    def _off_surface(self, points, r):
        """how far a path sits off the surface (mm, + = in the air) when over half of it is farther than r from it
        (a tube of radius r there meets nothing) — else None"""
        pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        if len(pts) < 2:
            return None
        samples = []
        for a, b in zip(pts, pts[1:]):
            n = max(2, int(np.linalg.norm(b - a) / self.voxel))
            samples.append(a + (b - a) * np.linspace(0.0, 1.0, n, endpoint=False)[:, None])
        d = self.root.d(np.concatenate(samples + [pts[-1:]]))
        far = np.abs(d) > r
        return float(np.median(d[far])) if far.mean() > 0.5 else None

    # -- surface
    THIN_MM = 4.0   # (a keep trim warns of outline features thinner than this: each leaves a fin in the clay)

    def views(self, side=None, front=None, blend=0.0, mode="add", min_mm=0.0):
        """the REFERENCE'S silhouette (traced views, as mm rings — rbx's s.views(...) reads them from kit trace): side
        [outline, holes ...] in (forward, up), front in (x, up). mode="add": the clay STARTS as the photos' visual hull
        (both views needed: the side alone is an endless prism); mode="keep": whatever was sculpted is trimmed back to
        the photographed silhouette (a nose, an ear, a root that grew past the picture). blend: its edges rounded.
        min_mm: the outline's features thinner than this dropped first (islands, spurs, slits — a keep trim runs
        through the whole object, and a thin island in the outline leaves a thin FIN of clay: warned when unset)"""
        if mode not in ("add", "keep"):
            raise ValueError('views: mode "add" or "keep"')
        res = self.voxel
        nodes = [Silhouette(r, plane, res, min_mm) for r, plane in ((side, "side"), (front, "front")) if r]
        if mode == "keep" and not min_mm:
            for n in nodes:
                spots = n.thin(self.THIN_MM)
                if spots:
                    where = ", ".join(f"({u:.0f}, {v:.0f})" for u, v in spots[:3])
                    self.warnings.append(f"the traced {n.plane} outline has {len(spots)} feature(s) thinner than "
                                         f"{self.THIN_MM:g} mm (u, v mm: {where}) — a keep trim leaves fins there; "
                                         f"min_mm={self.THIN_MM:g} drops them")
        if not nodes:
            raise ValueError("views: give side= and / or front= (traced outlines)")
        if mode == "add" and len(nodes) < 2:
            raise ValueError("views(mode='add'): needs BOTH side and front — one view alone is an endless prism "
                             "(mode='keep' trims existing clay with one)")
        hull = nodes[0] if len(nodes) == 1 else Intersect(nodes[0], nodes[1], blend)
        if mode == "add":
            self.add(hull, 0.0, "views")
        else:
            self.keep(hull, blend, "views")
        return self

    def loft_slices(self, levels, blend=0.0, carve=False, edge="round"):
        """clay LOFTED through measured horizontal sections (SliceStack): levels [(y, mask, (x0, z0), res)] —
        rbx_refmesh.slice_pieces(ref, y) gives each slice's pieces with their masks. The form comes from the real
        object's own sections instead of ellipsoids placed by eye (its vault matched within 2-5%, its face did not)"""
        node = SliceStack(levels)
        return (self.carve if carve else self.add)(node, blend, "slices", edge)

    def trim_to(self, outline, view, blend=0.0, min_mm=0.0):
        """trimmed to a reference mesh's EXACT silhouette: outline = rbx_refmesh.outline(ref, view) ({"mask", "lo",
        "res"}), view "side" or "front" — a prism through the object, as views(mode="keep"); min_mm drops its thin
        features first (Canvas.views)"""
        sil = Silhouette.from_mask(outline["mask"], outline["lo"], outline["res"], view, min_mm)
        if not min_mm:
            spots = sil.thin(self.THIN_MM)
            if spots:
                self.warnings.append(f"the {view} outline has {len(spots)} feature(s) thinner than {self.THIN_MM:g} mm "
                                     f"— a keep trim leaves fins there; min_mm={self.THIN_MM:g} drops them")
        return self.keep(sil, blend, "outline")

    def inflate(self, amount, where=None, falloff=0.0):
        """push the surface out by amount mm (negative: in) — everywhere, or in a region (a Node) easing out over
        falloff mm: swell a cheek, deflate a hollow"""
        if self.root is None:
            raise ValueError("inflate: nothing to inflate yet")
        self.root = Offset(self.root, amount, self._sym(where) if where is not None else None, falloff)
        self._note("inflate", "inflate", math.inf)   # (a sub-voxel offset survives: the mesher interpolates it)
        return self

    def noise(self, amp, scale, kind="fbm", octaves=4, seed=0, where=None, falloff=0.0):
        """relief over the surface: about +-amp mm, features ~scale mm apart (fbm: lumps, ridged: crests — rock,
        bark, cells: domes — scales, warts, cracks: borders pressed in — hide plates, cracked earth). scale (sx, sy,
        sz): stretched — scale=(4, 30, 4) runs bark's ridges up a trunk"""
        if self.root is None:
            raise ValueError("noise: no surface yet")
        self.root = Displace(self.root, amp, scale, kind, octaves, seed,
                             self._sym(where) if where is not None else None, falloff)
        self._note("noise", f"{kind} noise", min(float(np.min(scale)) / 2.0, 2.0 * abs(amp)))
        return self

    def stamp(self, scan, tile_mm, depth, centre=None, where=None, falloff=0.0, size=512):
        """relief from a REAL SCAN's height map (Stamp): scan = an ambientCG id cached by `kit materials --fetch`
        ("Rock064", "Concrete034" ...) or a height image's path; tile_mm: its real size per repeat; depth: mm;
        centre: the triplanar projection's centre (default: the canvas's middle)"""
        if self.root is None:
            raise ValueError("stamp: no surface yet")
        path = str(scan)
        if not os.path.isfile(os.path.expanduser(path)):
            root = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "materials", path)
            hits = [f for f in (os.listdir(root) if os.path.isdir(root) else []) if f.endswith("_Displacement.jpg")]
            if not hits:
                raise ValueError(f'stamp: no height map for "{scan}" (a path, or a scan cached by kit materials --fetch)')
            path = os.path.join(root, hits[0])
        h = load_height(path, size)
        if centre is None:
            lo, hi = self.root.bounds()
            centre = (np.asarray(lo) + np.asarray(hi)) / 2.0
        self.root = Stamp(self.root, h, tile_mm, depth, centre, self._sym(where) if where is not None else None,
                          falloff)
        self._note("stamp", f"{os.path.basename(path)} stamp", min(float(tile_mm) / 64.0, 2.0 * abs(depth)))
        return self

    def done(self, **kw):
        """build it (a.sculpt's part: rbx.Asset._sculpt_done) -> the part"""
        if self.on_done is None:
            raise ValueError("done(): this canvas is not an a.sculpt part — call mesh() for the raw surface")
        if self.root is None:
            raise ValueError("done(): an empty canvas — add clay first")
        return self.on_done(self, **kw)

    def key(self):
        k = (self.voxel, self.mirror_axis, self.root.key() if self.root is not None else None)
        if self.brushes:
            k += (tuple(repr(sorted(b.items())) for b in self.brushes),)
        if self.fit is not None:
            k += (_key(self.fit["target"]), self.fit["strength"], self.fit["max_mm"], self.fit["smooth_mm"])
        return k

    def fit_to(self, ref, strength=0.7, max_mm=6.0, smooth_mm=15.0, points=300000):
        """a STIFF FIT toward a reference model after meshing (fit_field): ref = rbx_refmesh.load(...) in this
        canvas's frame (mm). A smooth correction of the large forms toward the real object — the sculpt's own
        detail stays; the reference is never taken in. Order: mesh -> sharpen -> FIT -> brushes -> smooth"""
        import rbx_refmesh  # noqa: PLC0415

        self.fit = {"target": rbx_refmesh.surface_points(ref, int(points)), "strength": float(strength),
                    "max_mm": float(max_mm), "smooth_mm": float(smooth_mm)}
        return self

    def brush(self, kind, path, radius, strength=0.5):
        """a SCULPT BRUSH on the meshed surface (rbx_brushes): "pinch" (a sharp ridge / rim along the path), "flatten"
        (a plane under it), "inflate" (mm along the normal; negative presses in), "crease" (a groove with crisp
        walls) — radius mm, Blender's smooth falloff; path: points (one for a dab). The second pass every sculptor
        makes: forms out of balls and blends read "melted" until rims are pinched and planes flattened"""
        import rbx_brushes  # noqa: PLC0415

        if kind not in rbx_brushes.KINDS:
            raise ValueError(f'brush "{kind}": one of {", ".join(rbx_brushes.KINDS)}')
        pts = [tuple(float(c) for c in p) for p in np.asarray(path, dtype=np.float64).reshape(-1, 3)]
        self.brushes.append({"kind": kind, "path": pts, "radius": float(radius), "strength": float(strength)})
        self._note("brush", f"{kind} brush", float(radius))
        return self

    # -- reading it
    def bounds(self, pad=None):
        if self.root is None:
            raise ValueError("an empty canvas")
        lo, hi = self.root.bounds()
        pad = 3.0 * self.voxel if pad is None else pad
        return np.asarray(lo, dtype=np.float64) - pad, np.asarray(hi, dtype=np.float64) + pad

    def lost(self, min_voxels=1.5):
        """the operations whose smallest feature is under min_voxels voxels: the meshing cannot keep them"""
        return [(op, what, f) for op, what, f in self.log if f < min_voxels * self.voxel]

    def d(self, p):
        return self.root.d(np.asarray(p, dtype=np.float64))

    def _cutoff(self, band_mm, exact=False):
        """tell every relief how far from ITS surface its noise can still matter: the band, plus how far every
        operation above it can still move the surface (a later inflate, a later relief, a blend's fillet) — measured
        from its own surface alone, a later inflate(4) erased a relief entirely (the review 2026-10-10). Reliefs
        inside a region (where=) and exact=True: never skipped"""
        stack = [(self.root, 0.0)]
        while stack:
            n, slack = stack.pop()
            if isinstance(n, Displace):
                n.cutoff = math.inf if exact else band_mm + slack
                stack.append((n.a, slack + 1.25 * abs(n.amp)))
            elif isinstance(n, Offset):
                stack.append((n.a, slack + abs(n.amount)))
            elif isinstance(n, (Union, Subtract, Intersect)):
                stack += [(n.a, slack + n.k / 4.0), (n.b, slack + n.k / 4.0)]
            elif isinstance(n, Mirror):
                stack.append((n.a, slack))
            if getattr(n, "where", None) is not None:
                stack.append((n.where, math.inf))

    def _near(self, lo, cells, size, band):
        """which cubes of `size` voxels (their corner indices `cells`) the surface can pass through -> (near mask,
        their centre values)"""
        v = self.voxel
        dc = self.root.d(lo + (cells + (size - 1) / 2.0) * v)
        reach = math.sqrt(3) * (size - 1) / 2.0 * v * self.root.slope() + self.root.margin() + band * v
        return np.abs(dc) <= reach, dc

    def sample(self, block=16, band=3.0, chunk=1_500_000, sub=8):
        """the field on the voxel grid, only where the surface can be (a narrow band of `band` voxels): blocks of
        block^3 voxels farther from the surface than the field's slope allows are skipped — inside ones reported as
        solid — and each near block is culled again in sub^3 pieces before its voxels are evaluated.
        -> (lo, shape, [(ijk, values (block,)*3 float32)], [ijk of solid blocks])"""
        lo, hi = self.bounds()
        v = self.voxel
        bw = band * v
        self._cutoff(bw)
        shape = np.maximum(np.ceil((hi - lo) / v).astype(np.int64) + 1, 2)
        nb = -(-shape // block)
        bi = np.stack(np.meshgrid(*[np.arange(n) for n in nb], indexing="ij"), axis=-1).reshape(-1, 3) * block
        near, dc = self._near(lo, bi, block, band)
        solid = bi[(~near) & (dc < 0)]
        todo = bi[near]
        sub = sub if (sub and block % sub == 0 and sub < block) else block
        k = block // sub
        soffs = np.stack(np.meshgrid(*[np.arange(k)] * 3, indexing="ij"), axis=-1).reshape(-1, 3) * sub
        subs = (todo[:, None, :] + soffs[None, :, :]).reshape(-1, 3)
        snear, sdc = self._near(lo, subs, sub, band)
        offs = np.stack(np.meshgrid(*[np.arange(sub)] * 3, indexing="ij"), axis=-1).reshape(-1, 3)
        vals = np.empty((len(subs), sub, sub, sub), dtype=np.float32)
        vals[~snear] = np.where(sdc[~snear] < 0, -bw, bw).astype(np.float32)[:, None, None, None]
        idx = np.nonzero(snear)[0]
        per = max(1, chunk // len(offs))
        # PER-BLOCK PRUNING: an operation whose shape stays farther than the band + its blend from a block (its own
        # slope bound, from one value at the block's centre) cannot change any value there after the band's clip —
        # dropped from that block's tree. Blocks with the same surviving operations share one evaluation. (Every
        # operation at every voxel made a 144-operation skull 25-55 minutes; most blocks need a handful.)
        spine, keep = prune_masks(self.root, lo + (todo + (block - 1) / 2.0) * v,
                                  math.sqrt(3) * (block - 1) / 2.0 * v, bw) if self.prune else (None, None)
        groups = {}
        for i in idx:
            b_ = i // (k * k * k)
            groups.setdefault(keep[:, b_].tobytes() if keep is not None else b"", []).append(i)
        # (on every core: numpy releases the interpreter lock inside its array work — Blender used one of 16; the
        #  chunk is SHARED across the workers: 16 full chunks at once ran a 1.5M-point tree each, out of memory)
        workers = max(1, self.threads or (os.cpu_count() or 1))
        per = max(1, (chunk // workers) // len(offs))
        jobs = []
        for key, members in groups.items():
            tree = pruned(spine, np.frombuffer(key, dtype=bool)) if keep is not None else self.root
            members = np.asarray(members)
            jobs += [(tree, members[s_:s_ + per]) for s_ in range(0, len(members), per)]
        trees = len(groups)

        def run(job):
            tree, group = job
            ijk = (subs[group][:, None, :] + offs[None, :, :]).reshape(-1, 3)
            got = tree.d(lo + ijk * v).astype(np.float32)
            np.clip(got, -bw, bw, out=got)
            vals[group] = got.reshape(len(group), sub, sub, sub)   # (each job its own sub-blocks: no two collide)

        workers = max(1, min(workers, len(jobs)))
        if workers == 1:
            for job in jobs:
                run(job)
        else:
            from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(run, jobs))
        vals = vals.reshape(len(todo), k, k, k, sub, sub, sub).transpose(0, 1, 4, 2, 5, 3, 6)
        vals = vals.reshape(len(todo), block, block, block)
        self.stats = {"blocks": int(len(todo)), "solid_blocks": int(len(solid)), "voxels_evaluated":
                      int(len(idx) * len(offs)), "grid": [int(x) for x in shape], "trees": trees,
                      "operations": int(len(spine) if spine else 0),
                      "kept_per_block": round(float(keep.sum(axis=0).mean()), 1) if keep is not None else None}
        return lo, shape, [(t, vals[i]) for i, t in enumerate(todo)], list(solid)

    def dense(self, band=3.0, exact=False):
        """the whole field on the voxel grid (tests and small canvases) -> (lo, values); exact=True: every relief
        evaluated everywhere (the truth the band is checked against)"""
        self._cutoff(band * self.voxel, exact)
        lo, hi = self.bounds()
        shape = np.maximum(np.ceil((hi - lo) / self.voxel).astype(np.int64) + 1, 2)
        ijk = np.stack(np.meshgrid(*[np.arange(n) for n in shape], indexing="ij"), axis=-1).reshape(-1, 3)
        return lo, self.root.d(lo + ijk * self.voxel).reshape(tuple(shape))

    def mesh(self, adaptivity=0.0, block=16, band=3.0, smooth=0, smooth_where=None, smooth_falloff=0.0, sharp=False):
        """the closed surface -> (verts (N, 3) mm, faces [quads and triangles as index lists]). Needs OpenVDB
        (Blender 5.x's bundled `openvdb`). smooth: Taubin passes over the mesh (a sculptor's smooth brush: the
        voxels' faint stair-steps, a relief too sharp) — everywhere, or only in a region (smooth_where, a Node, easing
        out over smooth_falloff mm); Taubin's shrink-and-swell keeps the volume (a plain Laplacian shrinks it)"""
        import openvdb   # noqa: PLC0415  (Blender's own; the field above is plain numpy)

        lo, shape, blocks, solid = self.sample(block, band)
        bw = band * self.voxel
        grid = openvdb.FloatGrid(background=bw)
        for ijk, vals in blocks:
            grid.copyFromArray(np.ascontiguousarray(vals), ijk=tuple(int(x) for x in ijk), tolerance=0.0)
        for ijk in solid:   # (deep inside: an inactive tile of "solid", no voxels stored)
            a = tuple(int(x) for x in ijk)
            grid.fill(min=a, max=tuple(x + block - 1 for x in a), value=-bw, active=False)
        pts, tris, quads = grid.convertToPolygons(isovalue=0.0, adaptivity=float(adaptivity))
        verts = lo + np.asarray(pts, dtype=np.float64) * self.voxel
        verts, quads, tris, specks = drop_specks(verts, np.asarray(quads, dtype=np.int64).reshape(-1, 4),
                                                 np.asarray(tris, dtype=np.int64).reshape(-1, 3), 3.0 * self.voxel)
        self.stats["specks"] = specks
        if sharp:   # (corners and rims onto the field's own planes: see sharpen; before any smoothing)
            idx = feature_verts(verts, quads, tris)
            verts = sharpen(self.d, verts, idx, self.voxel)
            self.stats["sharpened"] = int(len(idx))
        if self.fit is not None:   # (a smooth correction toward the reference: before the brushes, after sharpening)
            f = self.fit
            verts = fit_field(verts, quads, tris, f["target"], f["strength"], f["max_mm"], f["smooth_mm"])
        if self.brushes:   # (the sculptor's second pass, in order: rbx_brushes)
            import rbx_brushes  # noqa: PLC0415

            faces_ = [list(map(int, q)) for q in quads] + [list(map(int, t)) for t in tris]
            for b in self.brushes:
                verts = rbx_brushes.apply(verts, faces_, b, mirror_axis=self.mirror_axis)
        if smooth:
            w = None if smooth_where is None else _weight(smooth_where, float(smooth_falloff), verts)
            verts = taubin(verts, quads, tris, int(smooth), weight=w)
        faces = [list(map(int, q)) for q in quads] + [list(map(int, t)) for t in tris]
        return verts, faces


def _grad(field, p, h):
    """the field's gradient by central differences -> (N, 3)"""
    g = np.empty_like(p)
    for i in range(3):
        e = np.zeros(3)
        e[i] = h
        g[:, i] = (field(p + e) - field(p - e)) / (2 * h)
    return g


def feature_verts(verts, quads, tris, turn=0.05):
    """the vertices where the surface turns sharply: 1 - |mean of the unit normals of the faces around them| above
    `turn` (0.05: ~18 degrees between neighbours) -> indices"""
    v = np.asarray(verts, dtype=np.float64)
    acc = np.zeros_like(v)
    cnt = np.zeros(len(v))
    for f in (np.asarray(quads, dtype=np.int64).reshape(-1, 4), np.asarray(tris, dtype=np.int64).reshape(-1, 3)):
        if not len(f):
            continue
        nrm = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        for j in range(f.shape[1]):
            np.add.at(acc, f[:, j], nrm)
            np.add.at(cnt, f[:, j], 1.0)
    spread = 1.0 - np.linalg.norm(acc, axis=1) / np.maximum(cnt, 1.0)
    return np.nonzero((cnt > 0) & (spread > turn))[0]


def sharpen(field, verts, idx, voxel, samples=10, reg=0.05, seed=0):
    """SHARP FEATURES the way dual contouring keeps them: each vertex in `idx` moved to the point that best meets the
    tangent planes of the exact field around it (samples on a voxel-wide sphere projected onto the surface, a QEF
    solved with a small pull toward where it was) — a mesher that averages edge crossings rounds every corner and
    rim by about a voxel. Moves are capped at one voxel -> the new vertices"""
    v = np.asarray(verts, dtype=np.float64).copy()
    if not len(idx):
        return v
    rng = np.random.default_rng(seed)
    dirs = rng.normal(size=(samples, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    c = v[idx]
    p = (c[:, None, :] + dirs[None, :, :] * voxel).reshape(-1, 3)
    h = voxel * 0.25
    for _ in range(4):   # (Newton onto the zero set: p -= d * g / |g|^2)
        d = field(p)
        g = _grad(field, p, h)
        p -= (d / np.maximum((g * g).sum(axis=1), 1e-9))[:, None] * g
    g = _grad(field, p, h)
    n = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    n = n.reshape(len(idx), samples, 3)
    p = p.reshape(len(idx), samples, 3)
    ata = np.einsum("ksi,ksj->kij", n, n) + reg * np.eye(3)[None]
    atb = np.einsum("ksi,ks->ki", n, (n * p).sum(axis=2)) + reg * c
    x = np.linalg.solve(ata, atb[:, :, None])[:, :, 0]
    move = x - c
    m = np.linalg.norm(move, axis=1, keepdims=True)
    x = c + move * np.minimum(1.0, voxel / np.maximum(m, 1e-12))
    ok = np.isfinite(x).all(axis=1)
    v[idx[ok]] = x[ok]
    return v


def nearest(points, queries, chunk=2048):
    """for each query its nearest point (indices into points): Blender's KD-tree inside Blender, scipy's outside it,
    brute force (chunked) without either"""
    P = np.asarray(points, dtype=np.float64)
    Q = np.asarray(queries, dtype=np.float64)
    try:
        import mathutils.kdtree as kd  # noqa: PLC0415

        tree = kd.KDTree(len(P))
        for i, p in enumerate(P):
            tree.insert(p, i)
        tree.balance()
        return np.array([tree.find(q)[1] for q in Q], dtype=np.int64)
    except ImportError:
        pass
    try:
        from scipy.spatial import cKDTree  # noqa: PLC0415

        return cKDTree(P).query(Q)[1]
    except ImportError:
        pass
    out = np.empty(len(Q), dtype=np.int64)
    pp = (P * P).sum(axis=1)
    for i in range(0, len(Q), chunk):
        q = Q[i:i + chunk]
        out[i:i + chunk] = np.argmin(pp[None, :] - 2.0 * q @ P.T, axis=1)
    return out


def fit_field(verts, quads, tris, target, strength=0.7, max_mm=6.0, smooth_mm=15.0, rounds=3):
    """a STIFF FIT toward a reference surface (`target`: dense points on it, mm): each vertex's offset to its nearest
    target point, capped at max_mm, then smoothed over the mesh across smooth_mm (in MILLIMETRES: a fixed pass count
    smoothed a 0.45 mm sculpt over ~5 mm and copied the scan's own ripples onto it) — only the large-scale
    correction survives (a cheek too low, a vault too long), the sculpt's own creases, rims and brushes stay its own —
    applied at `strength`, `rounds` times. The reference is never taken in: what moves is our surface, by a smooth
    field -> new vertices"""
    v = np.asarray(verts, dtype=np.float64).copy()
    e = [np.stack([f[:, i], f[:, (i + 1) % f.shape[1]]], axis=1)
         for f in (np.asarray(quads, dtype=np.int64).reshape(-1, 4), np.asarray(tris, dtype=np.int64).reshape(-1, 3))
         if len(f) for i in range(f.shape[1])]
    edges = np.unique(np.sort(np.concatenate(e), axis=1), axis=0)
    a, b = edges[:, 0], edges[:, 1]
    deg = np.bincount(np.concatenate([a, b]), minlength=len(v)).astype(np.float64)
    deg[deg == 0] = 1.0
    T = np.asarray(target, dtype=np.float64)
    edge = float(np.linalg.norm(v[a] - v[b], axis=1).mean()) or 1.0
    passes = int(min(4000, max(1, 2.0 * (float(smooth_mm) / edge) ** 2)))   # (a lazy walk spreads ~edge*sqrt(n/2))
    for _ in range(int(rounds)):
        u = T[nearest(T, v)] - v
        m = np.linalg.norm(u, axis=1, keepdims=True)
        u *= np.minimum(1.0, max_mm / np.maximum(m, 1e-12))
        for _p in range(passes):
            acc = np.zeros_like(u)
            np.add.at(acc, a, u[b])
            np.add.at(acc, b, u[a])
            u = 0.5 * u + 0.5 * acc / deg[:, None]
        v += float(strength) * u
    return v


def taubin(verts, quads, tris, passes, lam=0.5, mu=-0.53, weight=None):
    """Taubin smoothing (a shrink step lam, a swell step mu, `passes` times) of a mesh's vertices -> new vertices:
    noise and stair-steps relax while the volume stays (a plain Laplacian loses a sphere's volume pass by pass).
    weight (N,) 0..1: how much each vertex moves (a region's smoothing); None: all of them"""
    v = np.asarray(verts, dtype=np.float64).copy()
    e = [np.stack([f[:, i], f[:, (i + 1) % f.shape[1]]], axis=1) for f in (np.asarray(quads), np.asarray(tris))
         if len(f) for i in range(f.shape[1])]
    if not e:
        return v
    edges = np.unique(np.sort(np.concatenate(e), axis=1), axis=0)
    a, b = edges[:, 0], edges[:, 1]
    deg = np.bincount(np.concatenate([a, b]), minlength=len(v)).astype(np.float64)
    deg[deg == 0] = 1.0
    w = 1.0 if weight is None else np.clip(np.asarray(weight, dtype=np.float64), 0.0, 1.0)[:, None]
    for _ in range(int(passes)):
        for f in (lam, mu):
            acc = np.zeros_like(v)
            np.add.at(acc, a, v[b])
            np.add.at(acc, b, v[a])
            v = v + f * w * (acc / deg[:, None] - v)
    return v


def pieces(n_verts, edges):
    """connected pieces of a mesh: (n_verts,) labels from its edges (E, 2) — min-label propagation with pointer
    jumping, numpy only (Blender's python has no scipy)"""
    lab = np.arange(n_verts)
    if not len(edges):
        return lab
    e0, e1 = edges[:, 0], edges[:, 1]
    while True:
        m = np.minimum(lab[e0], lab[e1])
        new = lab.copy()
        np.minimum.at(new, e0, m)
        np.minimum.at(new, e1, m)
        for _ in range(4):
            new = new[new]
        if np.array_equal(new, lab):
            return lab
        lab = new


def drop_specks(verts, quads, tris, min_extent):
    """the closed pieces narrower than min_extent (mm) dropped: pockets the voxels cannot resolve — fine ridged
    relief pinched off 31 specks under 7 mm round a stump (2026-10-10), each read as a sliver. Canvas.mesh drops
    under 3 voxels across: what lost() already names (a feature under 1.5 voxels of radius) -> (verts, quads, tris,
    how many pieces were dropped)"""
    if not len(verts):
        return verts, quads, tris, 0
    edges = np.concatenate([np.stack([f[:, i], f[:, (i + 1) % f.shape[1]]], axis=1)
                            for f in (quads, tris) if len(f) for i in range(f.shape[1])] or [np.zeros((0, 2), int)])
    lab = pieces(len(verts), edges)
    uniq, inv = np.unique(lab, return_inverse=True)
    lo = np.full((len(uniq), 3), np.inf)
    hi = np.full((len(uniq), 3), -np.inf)
    np.minimum.at(lo, inv, verts)
    np.maximum.at(hi, inv, verts)
    keep_piece = (hi - lo).max(axis=1) >= min_extent
    if keep_piece.all() or not keep_piece.any():
        return verts, quads, tris, 0
    keep_v = keep_piece[inv]
    remap = np.cumsum(keep_v) - 1
    q = quads[keep_v[quads].all(axis=1)] if len(quads) else quads
    t = tris[keep_v[tris].all(axis=1)] if len(tris) else tris
    return verts[keep_v], remap[q], remap[t], int((~keep_piece).sum())


MAX_GRID_VOXELS = 150_000_000   # (600 MB of float32: a 1 m mesh at 1 mm is 1 billion — refused, said)


def mesh_volume(verts, faces):
    """a mesh's enclosed volume (the divergence theorem; mm3), any polygon fanned"""
    v = np.asarray(verts, dtype=np.float64)
    vol = 0.0
    for f in faces:
        a = v[f[0]]
        for i in range(1, len(f) - 1):
            vol += float(np.dot(a, np.cross(v[f[i]], v[f[i + 1]]))) / 6.0
    return abs(vol)


def from_mesh(verts, tris, voxel, band=4.0):
    """a CLOSED mesh (mm) -> a Grid field (a generated mesh, an earlier part: re-sculpted and remeshed as one
    surface). An OPEN mesh comes back closed but not whole — a cube missing a face kept a fifth of its volume (the
    review 2026-10-10): the Grid's clay_ratio (its clay's volume / the mesh's) says so; close it first (kit make's
    clean). band: how many voxels out its distances stay true (raise it for wide blends). Needs OpenVDB."""
    import openvdb   # noqa: PLC0415

    v = np.asarray(verts, dtype=np.float64)
    if len(v):
        cells = np.prod((v.max(axis=0) - v.min(axis=0)) / float(voxel) + 2 * band + 1)
        if cells > MAX_GRID_VOXELS:
            raise ValueError(f"from_mesh: {cells / 1e6:.0f} M voxels at {voxel:g} mm — over {MAX_GRID_VOXELS / 1e6:.0f} "
                             f"M: a coarser voxel_mm for this sculpt")
    xf = openvdb.createLinearTransform(voxelSize=float(voxel))
    tri = np.asarray([t for t in tris if len(t) == 3], dtype=np.uint32).reshape(-1, 3)
    quad = np.asarray([q for q in tris if len(q) == 4], dtype=np.uint32).reshape(-1, 4)
    g = openvdb.FloatGrid.createLevelSetFromPolygons(v.astype(np.float32), triangles=tri,
                                                      quads=quad, transform=xf, halfWidth=float(band))
    (i0, j0, k0), (i1, j1, k1) = g.evalActiveVoxelBoundingBox()
    arr = np.full((i1 - i0 + 1, j1 - j0 + 1, k1 - k0 + 1), band * voxel, dtype=np.float32)
    g.copyToArray(arr, ijk=(i0, j0, k0))
    grid = Grid(arr, np.array([i0, j0, k0], dtype=np.float64) * voxel, voxel, band * voxel)
    want = mesh_volume(v, tris)
    grid.clay_ratio = float((arr < 0).sum()) * float(voxel) ** 3 / want if want > 0 else 0.0
    return grid
