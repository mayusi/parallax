"""A PART BROKEN BEFOREHAND (the owner's method lists, 2026-11-13: "destructible preparation"; the 3D methods audit,
stage O: missing).

A thing that breaks in a game is not cut at the moment it is hit: it is MODELLED broken - its pieces made
beforehand, fitted together so it looks whole, each its own mesh - and the game lets them go. `a.fracture` cuts
one closed part into pieces that way: points are scattered inside its box, and each piece is the part of it nearer
to one point than to any other (the cells a crack pattern makes). Here: where the points go, the planes that bound
one piece, and how the pieces are held to the whole (their volumes add up to the part's).
Pure numpy (the cutting is the builder's, in Blender); no Blender."""

import numpy as np

PIECES = (2, 24)     # how many pieces a part may be broken into
VOLUME_TOL = 0.02    # the pieces' volumes may differ from the whole part's by this share


def seeds(lo, hi, count, seed=1):
    """`count` points inside a box, spread (never two in one spot), the same for the same seed -> (count, 3).
    Each point is the best of several tries: the one furthest from the points already placed."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    rng = np.random.default_rng(int(seed))
    size = np.maximum(hi - lo, 1e-9)
    out = [lo + size * rng.random(3)]
    for _ in range(int(count) - 1):
        tries = lo + size * rng.random((24, 3))
        far = np.min(np.linalg.norm((tries[:, None, :] - np.array(out)[None, :, :]) / size, axis=2), axis=1)
        out.append(tries[int(np.argmax(far))])
    return np.array(out)


def planes(points, i):
    """the planes that bound piece i: for every other point, the plane halfway to it -> [(point on it, normal)].
    The normal points AWAY from point i: what lies on that side belongs to the other piece and is cut off."""
    pts = np.asarray(points, float)
    out = []
    for j in range(len(pts)):
        if j == i:
            continue
        n = pts[j] - pts[i]
        length = float(np.linalg.norm(n))
        if length < 1e-12:
            continue
        out.append(((pts[i] + pts[j]) / 2.0, n / length))
    return out


def volume(points, tris):
    """the volume a closed triangle mesh holds (signed: positive when its faces look outward)"""
    p = np.asarray(points, float)[np.asarray(tris, int).reshape(-1, 3)]
    return float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6.0)


def problem(part, whole, pieces, tol=VOLUME_TOL):
    """the pieces against the part they were cut from -> a sentence, or None. whole: the part's volume;
    pieces: each piece's volume"""
    pieces = [float(v) for v in pieces]
    if any(v <= 1e-9 for v in pieces):
        return f"{part}: {sum(1 for v in pieces if v <= 1e-9)} of its {len(pieces)} pieces came out empty or open"
    got = sum(pieces)
    if abs(got - whole) > tol * abs(whole):
        return (f"{part}: its {len(pieces)} pieces hold {got / whole:.0%} of the part they were cut from - a "
                "piece is missing or doubled (the part must be one closed solid)")
    return None


def burst(centre, at, speed):
    """the push a piece gets when the whole lets go: away from the whole's centre, `speed` studs a second; a
    piece AT the centre goes straight up -> (x, y, z)"""
    d = np.asarray(at, float) - np.asarray(centre, float)
    length = float(np.linalg.norm(d))
    if length < 1e-6:
        return (0.0, float(speed), 0.0)
    d = d / length * float(speed)
    return (float(d[0]), float(d[1]), float(d[2]))
