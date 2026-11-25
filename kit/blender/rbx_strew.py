"""rbx_strew.py — SCATTER: where pieces go when they are spread over a surface (numpy only; rbx.Asset.scatter
makes the copies).

A modeller does not place two hundred scales, shingles, rivets or barnacles: he models ONE and scatters it over
the surface (Blender: Geometry Nodes' Distribute Points on Faces + Instance on Points, aligned to the normal). A
build script had none of it: one kind of grip stud was built in, everything else was left off or painted on.

    with a.scatter("Roof", pitch=0.25, facing=(0, -1, 0)):        # shingles, all pointing down the slope
        a.box("Shingle", (0.22, 0.02, 0.3), (0, 0.01, 0), "slate")
    with a.scatter("Hull", count=40, where=lambda c, n: c[1] < 0.5, vary={"size": 0.3}):
        a.sphere("Barnacle", 0.05, (0, 0, 0), "shell")             # only below the waterline, each its own size

The piece is modelled AT THE ORIGIN, standing on y = 0 with +Y its up: each copy stands on the surface with its
up along the surface's own direction there.

    triangles(verts, faces)        a mesh as triangles (T, 3, 3)
    sample(tris, count / pitch, where, seed)   points on them: spread by AREA (a big face gets more), never two
                                   closer than `pitch` (blue noise: no clumps, no rows) -> (points, normals)
    placements(points, normals, facing, spin, seed)   a 4 x 4 for each: +Y to the normal, then either spun about it
                                   at random (stones, barnacles) or turned so the piece's +Z runs along `facing`
                                   laid onto the surface (shingles, scales, fur: a nap)
"""

import math
import zlib

import numpy as np

import rbx_repeat

MAX_POINTS = 512          # (rbx_repeat.MAX_COPIES: every copy is real triangles)
CANDIDATES = 60000


def triangles(verts, faces):
    """a mesh -> its triangles (T, 3, 3) float64 (a face of more than three corners: a fan from its first)"""
    v = np.asarray(verts, np.float64).reshape(-1, 3)
    out = []
    for f in faces:
        for a, b in zip(f[1:], f[2:]):
            out.append((v[f[0]], v[a], v[b]))
    return np.array(out, np.float64).reshape(-1, 3, 3)


def _rng(seed):
    return np.random.default_rng(zlib.crc32(str(seed).encode()))


def _border(tris):
    """the edges only ONE of these triangles has: the picked surface's own border -> (E, 2, 3)"""
    seen = {}
    for t in tris:
        for i, j in ((0, 1), (1, 2), (2, 0)):
            ka, kb = tuple(np.round(t[i], 6).tolist()), tuple(np.round(t[j], 6).tolist())
            seen.setdefault((ka, kb) if ka <= kb else (kb, ka), []).append((t[i], t[j]))
    return np.array([v[0] for v in seen.values() if len(v) == 1], np.float64).reshape(-1, 2, 3)


def _off_border(pts, edges, margin):
    """which points are at least `margin` from every border edge -> bool (N,)"""
    keep = np.ones(len(pts), bool)
    if not len(edges):
        return keep
    a, d = edges[:, 0], edges[:, 1] - edges[:, 0]
    dd = np.maximum((d * d).sum(axis=1), 1e-300)
    for i in range(0, len(pts), 1024):                  # (in pieces: every point against every border edge)
        rel = pts[i:i + 1024, None, :] - a[None, :, :]
        t = np.clip((rel * d[None, :, :]).sum(axis=2) / dd[None, :], 0.0, 1.0)
        gap = np.linalg.norm(rel - t[:, :, None] * d[None, :, :], axis=2).min(axis=1)
        keep[i:i + 1024] = gap >= margin
    return keep


def sample(tris, count=None, pitch=None, where=None, seed="scatter", margin=0.0):
    """points spread over triangles -> (points (N, 3), normals (N, 3) unit, pitch used). count: so many (fewer if
    the surface cannot hold them `pitch` apart - never silently: the caller compares); pitch: none closer than
    this (studs), as many as fit, or with count the least distance between them. Two points on faces that look
    opposite ways (the two sides of a sail, a blade, a wing) do not count as close. where(center, normal) -> bool
    picks the faces (both in the triangles' own frame). margin: no point nearer than this to the BORDER of the
    picked faces (a piece then does not hang over a roof's edge). The same points for the same seed."""
    tris = np.asarray(tris, np.float64).reshape(-1, 3, 3)
    if count is None and pitch is None:
        raise ValueError("scatter: say count= (so many) or pitch= (none closer than this, as many as fit)")
    if count is not None:
        try:
            ok = float(count) == int(count) and 1 <= int(count) <= MAX_POINTS
        except (TypeError, ValueError, OverflowError):
            ok = False
        if not ok:
            raise ValueError(f"scatter: count={count!r} - a whole number 1..{MAX_POINTS}")
        count = int(count)
    if pitch is not None:
        try:
            pitch = float(pitch)
        except (TypeError, ValueError):
            pitch = float("nan")
        if not (math.isfinite(pitch) and pitch > 1e-6):
            raise ValueError(f"scatter: pitch={pitch!r} - studs between pieces, over 0")
    try:
        margin = float(margin)
    except (TypeError, ValueError):
        margin = float("nan")
    if not (math.isfinite(margin) and margin >= 0.0):
        raise ValueError(f"scatter: margin={margin!r} - studs kept from the picked surface's border, 0 or more")
    cross = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    area = np.linalg.norm(cross, axis=1) / 2
    keep = area > 1e-12
    if where is not None:
        mid = tris.mean(axis=1)
        nrm = cross / np.maximum(np.linalg.norm(cross, axis=1), 1e-300)[:, None]
        try:
            keep &= np.array([bool(where(tuple(c), tuple(n))) for c, n in zip(mid.tolist(), nrm.tolist())])
        except ValueError:
            raise ValueError("scatter: where(center, normal) must answer True or False for one face") from None
    tris, cross, area = tris[keep], cross[keep], area[keep]
    total = float(area.sum())
    if not len(tris) or total < 1e-12:
        raise ValueError("scatter: no surface to scatter on (where= picked no face, or the part has no area)")
    unit = cross / np.linalg.norm(cross, axis=1)[:, None]
    edges = _border(tris) if margin > 0 else np.zeros((0, 2, 3))
    flat = tris.reshape(-1, 3)
    across = float(np.linalg.norm(flat.max(axis=0) - flat.min(axis=0)))   # (a long thin strip: its length counts)
    rng = _rng(seed)
    least = pitch if pitch is not None else 0.7 * math.sqrt(total / count)     # (a spread that fits with room)
    while True:
        n = int(min(CANDIDATES, max(64, 40 * total / (least * least), 30 * across / least)))
        pick = rng.choice(len(tris), size=n, p=area / total)
        u, v = rng.random(n), rng.random(n)
        flip = u + v > 1
        u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
        t = tris[pick]
        pts = t[:, 0] + (t[:, 1] - t[:, 0]) * u[:, None] + (t[:, 2] - t[:, 0]) * v[:, None]
        ok = _off_border(pts, edges, margin) if margin > 0 else np.ones(n, bool)
        if margin > 0 and not ok.any():
            raise ValueError(f"scatter: margin={margin:g} leaves no room on the picked surface")
        got, cells = [], {}
        for i in np.flatnonzero(ok):                    # (in the order drawn: the first to come keeps its place)
            p, face = pts[i], unit[pick[i]]
            key = tuple(np.floor(p / least).astype(int).tolist())
            near = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for j in cells.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                            # (close, and not on a face that looks the opposite way)
                            if float(((pts[j] - p) ** 2).sum()) < least * least and float(unit[pick[j]] @ face) > -0.5:
                                near = True
                                break
                        if near:
                            break
                    if near:
                        break
                if near:
                    break
            if near:
                continue
            cells.setdefault(key, []).append(int(i))
            got.append(int(i))
            if len(got) >= (count or MAX_POINTS + 1):
                break
        if count is None or len(got) >= count or pitch is not None:
            break
        least *= 0.85                                   # (so many do not fit this far apart: closer)
    if count is None and len(got) > MAX_POINTS:
        raise ValueError(f"scatter: pitch={pitch:g} on {total:.3g} square studs is more than {MAX_POINTS} pieces - "
                         "a wider pitch, or count=")
    got = np.array(got, int)
    return pts[got], unit[pick[got]], least


def placements(points, normals, facing=None, spin=True, seed="scatter"):
    """where each piece stands -> [4 x 4] * N: the piece's +Y to the surface's normal at its point, then turned
    about it - at random (spin=True), or so its +Z runs along `facing` laid onto the surface (a nap: shingles
    down a roof, scales down a tail); where `facing` stands straight off the surface the piece is left as it fell"""
    pts = np.asarray(points, np.float64).reshape(-1, 3)
    nrm = np.asarray(normals, np.float64).reshape(-1, 3)
    if len(pts) != len(nrm):
        raise ValueError("scatter: one normal per point")
    lay = None
    if facing is not None:
        try:
            lay = np.array([float(c) for c in facing], np.float64)
        except (TypeError, ValueError):
            lay = np.zeros(0)
        if lay.shape != (3,) or not np.isfinite(lay).all() or float(np.linalg.norm(lay)) < 1e-9:
            raise ValueError(f"scatter: facing={facing!r} - a direction (x, y, z)")
        lay = lay / np.linalg.norm(lay)
    rng = _rng(f"{seed}/spin")
    y, z = np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])
    out = []
    for p, n in zip(pts, nrm):
        m = rbx_repeat._align(y, n)
        turn = rng.uniform(0.0, 360.0)                  # (always drawn: a nap on one build moves no other piece)
        if lay is not None:
            want = lay - n * float(lay @ n)             # `facing`, laid onto the surface here
            if float(np.linalg.norm(want)) > 1e-6:
                want /= np.linalg.norm(want)
                has = m[:3, :3] @ z
                turn = math.degrees(math.atan2(float(np.cross(has, want) @ n), float(has @ want)))
            else:
                turn = 0.0
        elif not spin:
            turn = 0.0
        out.append(rbx_repeat.translation(p) @ rbx_repeat.rotation(n, turn) @ m)
    return out
