"""sdf.py - LAND AS A SIGNED DISTANCE, read by kit world check (the owner's method list: "Signed distance field / SDF
terrain"). The same rules as src/kit/SdfRules.luau, which the game and the compiler read: every shape says how far a
point is from its surface (below 0 = inside), shapes are joined or cut out of each other in order, with a blend that
rounds the seam. The two files are held to the same numbers by one table of points in both tests
(kit/test/python/test_world_sdf.py, kit/test/spec/worldsdf.spec.luau).
Pure (no numpy): a shape is {"ball": {"center", "radius"}} | {"box": {"center", "size", "round"?}} |
{"capsule": {"from", "to", "radius"}}, with "cut": true and "blend": studs."""
import math

FAR = 1e9


def shape(s, x, y, z):
    """how far a point is from ONE shape's surface (below 0 = inside it)"""
    if "ball" in s:
        c = s["ball"]["center"]
        return math.sqrt((x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2) - s["ball"]["radius"]
    if "box" in s:
        c, size, r = s["box"]["center"], s["box"]["size"], s["box"].get("round") or 0
        qx = abs(x - c[0]) - (size[0] / 2 - r)
        qy = abs(y - c[1]) - (size[1] / 2 - r)
        qz = abs(z - c[2]) - (size[2] / 2 - r)
        out = math.sqrt(max(qx, 0) ** 2 + max(qy, 0) ** 2 + max(qz, 0) ** 2)
        return out + min(max(qx, qy, qz), 0) - r
    a, b = s["capsule"]["from"], s["capsule"]["to"]
    bx, by, bz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    px, py, pz = x - a[0], y - a[1], z - a[2]
    len2 = bx * bx + by * by + bz * bz
    t = min(1.0, max(0.0, (px * bx + py * by + pz * bz) / len2)) if len2 > 0 else 0.0
    return math.sqrt((px - bx * t) ** 2 + (py - by * t) ** 2 + (pz - bz * t) ** 2) - s["capsule"]["radius"]


def smin(a, b, k):
    """the least of two distances, the seam rounded over k studs (k = 0: a sharp seam)"""
    if k <= 0:
        return min(a, b)
    h = max(k - abs(a - b), 0) / k
    return min(a, b) - h * h * k / 4


def at(spec, x, y, z):
    """THE LAND'S DISTANCE at a point, and the CUT's -> (d, cut): d below 0 = inside what this op makes; cut below 0 =
    inside a cutting shape. The land that was there before the op is taken out where cut is below 0 and the op's own
    land does not stand (d not below 0)"""
    d, cut = FAR, FAR
    for s in spec["shapes"]:
        di = shape(s, x, y, z)
        k = s.get("blend") or 0
        if s.get("cut"):
            d = -smin(-d, di, k)
            cut = smin(cut, di, k)  # (the cuts together: where two meet, the seam is rounded)
        else:
            d = smin(d, di, k)
    return d, cut


def bounds(spec):
    """the box its shapes lie in (each shape's own box, a blend's reach and a cell wider) -> (lo, hi)"""
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for s in spec["shapes"]:
        pad = (s.get("blend") or 0) + 4
        if "ball" in s:
            c, r = s["ball"]["center"], s["ball"]["radius"]
            a, b = [c[i] - r for i in range(3)], [c[i] + r for i in range(3)]
        elif "box" in s:
            c, size = s["box"]["center"], s["box"]["size"]
            a, b = [c[i] - size[i] / 2 for i in range(3)], [c[i] + size[i] / 2 for i in range(3)]
        else:
            f, t, r = s["capsule"]["from"], s["capsule"]["to"], s["capsule"]["radius"]
            a, b = [min(f[i], t[i]) - r for i in range(3)], [max(f[i], t[i]) + r for i in range(3)]
        for i in range(3):
            lo[i] = min(lo[i], a[i] - pad)
            hi[i] = max(hi[i], b[i] + pad)
    return lo, hi


def cell(d, cut):
    """WHAT A 4-STUD CELL BECOMES -> (fill 0..1: how full of the op's material, clear 0..1: how much of what was there
    is taken out). Half a cell inside is full, half a cell outside is empty."""
    fill = min(1.0, max(0.0, 0.5 - d / 4))
    clear = min(1.0, max(0.0, 0.5 - cut / 4)) if cut < FAR / 2 else 0.0
    return fill, clear


def at_many(spec, pts):
    """the land's distance and the cut's at MANY points (an N x 3 numpy array) -> (d, cut) arrays: the same numbers as
    `at`, one point at a time (held together by a test)"""
    import numpy as np

    pts = np.asarray(pts, dtype=float)
    d = np.full(len(pts), FAR)
    cut = np.full(len(pts), FAR)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    for s in spec["shapes"]:
        if "ball" in s:
            c = s["ball"]["center"]
            di = np.sqrt((x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2) - s["ball"]["radius"]
        elif "box" in s:
            c, size, r = s["box"]["center"], s["box"]["size"], s["box"].get("round") or 0
            qx = np.abs(x - c[0]) - (size[0] / 2 - r)
            qy = np.abs(y - c[1]) - (size[1] / 2 - r)
            qz = np.abs(z - c[2]) - (size[2] / 2 - r)
            out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
            di = out + np.minimum(np.maximum(np.maximum(qx, qy), qz), 0) - r
        else:
            a, b = s["capsule"]["from"], s["capsule"]["to"]
            bx, by, bz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            px, py, pz = x - a[0], y - a[1], z - a[2]
            len2 = bx * bx + by * by + bz * bz
            t = np.clip((px * bx + py * by + pz * bz) / len2, 0, 1) if len2 > 0 else np.zeros(len(pts))
            di = np.sqrt((px - bx * t) ** 2 + (py - by * t) ** 2 + (pz - bz * t) ** 2) - s["capsule"]["radius"]
        k = s.get("blend") or 0

        def least(a_, b_):
            if k <= 0:
                return np.minimum(a_, b_)
            h = np.maximum(k - np.abs(a_ - b_), 0) / k
            return np.minimum(a_, b_) - h * h * k / 4

        if s.get("cut"):
            d = -least(-d, di)
            cut = least(cut, di)
        else:
            d = least(d, di)
    return d, cut


def solid(spec, x, y, z):
    """is the point inside the land this op makes -> True | False; and is it CUT OUT (inside a cutting shape and not
    inside what the op makes) -> True | False"""
    d, cut = at(spec, x, y, z)
    return d < 0, (cut < 0 and d >= 0)
