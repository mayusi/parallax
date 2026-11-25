"""rbx_sweep.py — SWEEP: a section carried along a path, its size and its turn changing on the way (numpy only;
rbx.Asset.sweep makes the part).

A modeller draws a curve and a profile and sweeps one along the other (Blender: a curve with a bevel object, a
taper curve and a tilt per point): a tapering horn, a cable, a tentacle, an ornate handle, a rail, a moulding
round a frame. A build script had `a.tube` only - one round section, one radius, end to end.

    a.sweep("Horn", [(0, 0, 0), (0, 1, 0.2), (0.4, 1.6, 0.3)], 0.2, "bone", scale=[(0, 1), (1, 0)])
    a.sweep("Rail", path, [(-0.1, 0), (0.1, 0), (0.1, 0.05), (0, 0.12), (-0.1, 0.05)], "iron")
    a.sweep("Rope", path, 0.05, "hemp", sides=6, twist=720)

Everything is in ONE frame (studs). The path runs through its points (smooth=True: a centripetal curve through
them, rbx_repeat's; False: straight legs with mitred corners); a path given closed is a loop with no ends.

    section     a radius (a regular polygon of `sides`) or an outline [(x, y), ...], drawn as it is SEEN FROM THE
                PATH'S END LOOKING BACK at its start: x to the right, y to its UP - the direction `up` at the
                path's start (the model's up; a path that starts straight up or down: +Z), carried along the path
                without rolling. (Travelling along the path, the outline's +x is on your left.)
    scale       one number, or [(share of the length, scale), ...] (straight runs between them); a scale of 0 at
                an end is a POINT (a horn's tip); (sx, sy) pairs scale the two ways apart
    twist       degrees turned about the path from start to end (x toward y: counter-clockwise in that same
                view), or [(share, degrees), ...]

    solid(...) -> (vertices (N, 3), faces [[i, ...], ...]) closed, its faces wound outward
"""

import math

import numpy as np

import rbx_repeat

MAX_STATIONS = 2048
MAX_SIDES = 256
TIP = 1e-6            # a scale under this at an end: the section there is one point


def _profile(value, what, pair=False):
    """one number, or [(share, value), ...] -> (shares (K,), values (K,) or (K, 2)), sorted, covering 0..1"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        rows = [(0.0, value), (1.0, value)]
    else:
        try:
            rows = [(float(a), b) for a, b in value]
        except (TypeError, ValueError):
            rows = []
    out = []
    for a, b in rows:
        try:
            v = [float(c) for c in b] if pair and not isinstance(b, (int, float)) else [float(b)] * (2 if pair else 1)
        except (TypeError, ValueError):
            v = []
        if len(v) != (2 if pair else 1) or not (0.0 <= a <= 1.0) or not all(math.isfinite(c) for c in v):
            out = []
            break
        out.append((a, v))
    out.sort(key=lambda r: r[0])
    if len(out) < 2 or any(q[0] - p[0] < 1e-9 for p, q in zip(out, out[1:])):
        raise ValueError(f"sweep: {what}= is one number or two or more (share of the length 0..1, value) pairs, "
                         "no two at the same share")
    xs = np.array([r[0] for r in out])
    ys = np.array([r[1] for r in out])
    return xs, (ys if pair else ys[:, 0])


def _at(xs, ys, t):
    """a profile's value at shares t (M,) -> (M,) or (M, 2): straight runs, its end values held outside them"""
    if ys.ndim == 1:
        return np.interp(t, xs, ys)
    return np.stack([np.interp(t, xs, ys[:, 0]), np.interp(t, xs, ys[:, 1])], axis=1)


def outline(section, sides=12):
    """a section -> (K, 2) float64, counter-clockwise: a radius (a regular polygon, a flat side down) or an
    outline of three or more (x, y) points"""
    if isinstance(section, (int, float)) and not isinstance(section, bool):
        r = float(section)
        try:
            ok = float(sides) == int(sides) and 3 <= int(sides) <= MAX_SIDES
        except (TypeError, ValueError, OverflowError):
            ok = False
        if not (math.isfinite(r) and r > 0) or not ok:
            raise ValueError(f"sweep: a round section is a radius over 0 with sides= 3..{MAX_SIDES} "
                             f"(got {section!r}, sides={sides!r})")
        n = int(sides)
        a = -math.pi / 2 + math.pi / n + 2 * math.pi * np.arange(n) / n
        return np.stack([r * np.cos(a), r * np.sin(a)], axis=1)
    try:
        pts = np.array([[float(c) for c in p] for p in section], np.float64)
    except (TypeError, ValueError):
        pts = np.zeros((0, 2))
    if pts.ndim != 2 or pts.shape[1:] != (2,) or len(pts) < 3 or len(pts) > MAX_SIDES or not np.isfinite(pts).all():
        raise ValueError("sweep: section= is a radius or an outline of three or more (x, y) points")
    if (np.linalg.norm(pts - np.roll(pts, -1, axis=0), axis=1) < 1e-9).any():
        raise ValueError("sweep: section= has two points in the same place (do not repeat the first at the end)")
    area = 0.5 * float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1]))
    if abs(area) < 1e-12:
        raise ValueError("sweep: section= encloses no area")
    return pts if area > 0 else pts[::-1].copy()


def _mitres(before, after):
    """how the section is stretched ACROSS a corner at each station, so the legs on both sides keep their size (a
    picture frame's mitre) -> (M, 3): m * (1 / cos(half the turn) - 1), m the unit direction across the corner;
    zero where the path runs straight"""
    out = np.zeros_like(before)
    for i, (a, b) in enumerate(zip(before, after)):
        way = a + b
        n = float(np.linalg.norm(way))
        cos_half = float(a @ way) / n if n > 1e-9 else 0.0
        if cos_half < math.cos(math.radians(80.0)):
            raise ValueError(f"sweep: the path turns {2 * math.degrees(math.acos(max(-1.0, min(1.0, cos_half)))):.0f} "
                             "degrees at one point - too sharp to carry a section round (give the turn more room, "
                             "or more points round it)")
        m = b - a
        ln = float(np.linalg.norm(m))
        if ln > 1e-9:
            out[i] = (m / ln) * (1.0 / cos_half - 1.0)
    return out


def loops(points, closed=False):
    """is this path a loop: asked closed, or its last point its first"""
    pts = [tuple(float(c) for c in p) for p in points]
    return bool(closed) or (len(pts) > 2 and math.dist(pts[0], pts[-1]) < 1e-9)


def _turns(legs):
    """the angle between each leg and the next, radians (M - 2,)"""
    return np.arccos(np.clip(np.einsum("ij,ij->i", legs[:-1], legs[1:]), -1.0, 1.0))


def stations(points, smooth=True, closed=False, extra=()):
    """the path -> (places (M, 3), ways (M, 3) unit: the way the path runs AT each station, shares (M,) of its
    length, closed, mitres (M, 3), legs: the unit direction from each station to the next (M - 1; a closed path:
    M, the last back to the first)). A curve gets a station wherever it has turned about 10 degrees since the
    last, at every point given and at every share in `extra` (where a profile has a point). A closed path's last
    station is NOT its first again."""
    try:
        pts = np.array([[float(c) for c in p] for p in points], np.float64)
    except (TypeError, ValueError):
        pts = np.zeros((0, 3))
    if pts.ndim != 2 or pts.shape[1:] != (3,) or len(pts) < 2 or not np.isfinite(pts).all():
        raise ValueError("sweep: the path is two or more points (x, y, z) in studs")
    if closed and float(np.linalg.norm(pts[-1] - pts[0])) > 1e-9:
        pts = np.vstack([pts, pts[0]])
    closed = bool(closed) or (len(pts) > 2 and float(np.linalg.norm(pts[-1] - pts[0])) < 1e-9)
    if closed and len(pts) < 4:
        raise ValueError("sweep: a closed path needs three or more different points")
    if (np.linalg.norm(np.diff(pts, axis=0), axis=1) < 1e-9).any():
        raise ValueError("sweep: the path has two points in the same place")
    rounded = bool(smooth) and len(pts) > 2
    fine = pts
    for per in (48, 192) if rounded else ():           # (drawn finer where one piece of it still turns too far)
        fine = rbx_repeat._smooth(pts, closed, per)
        seg = np.linalg.norm(np.diff(fine, axis=0), axis=1)
        fine = fine[np.concatenate([[True], seg > 1e-12])]
        seg = np.linalg.norm(np.diff(fine, axis=0), axis=1)
        if float(_turns(np.diff(fine, axis=0) / seg[:, None]).max(initial=0.0)) <= math.radians(5.0):
            break
    seg = np.linalg.norm(np.diff(fine, axis=0), axis=1)
    at = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(at[-1])
    shares = at / total
    if rounded:   # a station where the curve has turned 10 degrees since the last, and at every point given
        turn = _turns(np.diff(fine, axis=0) / seg[:, None])
        given = {int(np.argmin(np.linalg.norm(fine - p, axis=1))) for p in pts}
        keep, turned = [0], 0.0
        for j in range(1, len(fine) - 1):
            turned += float(turn[j - 1])
            if turned >= math.radians(10.0) - 1e-9 or j in given:
                keep.append(j)
                turned = 0.0
        keep.append(len(fine) - 1)
        fixed = [j in given or j in (0, len(fine) - 1) for j in keep]
        shares = shares[keep]
    else:
        fixed = [True] * len(shares)
    # a station wherever a profile has a point. On a curve, one of the curve's OWN stations that would then sit
    # right beside it makes way (two stations a hair apart on a bend pinch the part between them)
    rows = sorted(zip(shares.tolist(), fixed))
    for t in sorted({float(t) for t in extra}):
        if not 1e-5 < t < 1.0 - 1e-5 or min(abs(t - r[0]) for r in rows) <= 1e-5:
            continue
        i = next(k for k, r in enumerate(rows) if r[0] > t)
        lo, hi = rows[i - 1], rows[i]
        gap = hi[0] - lo[0]
        rows.insert(i, (t, True))
        if not hi[1] and hi[0] - t < 0.4 * gap:
            rows.pop(i + 1)
        if not lo[1] and t - lo[0] < 0.4 * gap:
            rows.pop(i - 1)
    shares = np.array([r[0] for r in rows])
    if len(shares) > MAX_STATIONS:
        raise ValueError(f"sweep: {len(shares)} stations along the path - at most {MAX_STATIONS} (a shorter twist, "
                         "fewer points)")
    place = np.stack([np.interp(shares * total, at, fine[:, i]) for i in range(3)], axis=1)
    chords = np.diff(place, axis=0)
    chords /= np.linalg.norm(chords, axis=1)[:, None]
    if closed:      # the way AT each station: between the legs that meet there (a mitre), round the join too
        ways = np.array([rbx_repeat._unit(chords[-1] + chords[0], chords[0])]
                        + [rbx_repeat._unit(chords[j - 1] + chords[j], chords[j]) for j in range(1, len(chords))])
        return place[:-1], ways, shares[:-1], True, _mitres(np.roll(chords, 1, axis=0), chords), chords
    ways = np.array([chords[0]] + [rbx_repeat._unit(chords[j - 1] + chords[j], chords[j])
                                   for j in range(1, len(chords))] + [chords[-1]])
    mitres = _mitres(np.vstack([chords[:1], chords]), np.vstack([chords, chords[-1:]]))
    return place, ways, shares, False, mitres, chords


def _carry(v, a, b):
    """direction v, square to a, carried to be square to b by the smallest turn from a to b"""
    out = rbx_repeat._align(a, b)[:3, :3] @ v
    out = out - b * float(out @ b)                     # (kept square, against rounding over many steps)
    return out / np.linalg.norm(out)


def frames(ways, up=None, closed=False, legs=None):
    """the section's own (side, up) at every station -> (sides (M, 3), ups (M, 3)): `up` at the first, carried
    along the path without rolling; side x up = the way the path runs. It is carried from a station ONTO the leg
    that leaves it and from the leg onto the next station (legs given): along a straight leg the section then
    does not turn at all, however the path bends out of its plane at the leg's ends. A closed path's frame meets
    itself: what the loop turned it by is taken back out evenly along it."""
    t0 = ways[0]
    if up is None:
        up = (0.0, 1.0, 0.0) if abs(t0[1]) < 0.99 else (0.0, 0.0, 1.0)
    try:
        u = np.array([float(c) for c in up], np.float64)
    except (TypeError, ValueError):
        u = np.zeros(0)
    if u.shape != (3,) or not np.isfinite(u).all():
        raise ValueError(f"sweep: up={up!r} - a direction (x, y, z)")
    u = u - t0 * float(u @ t0)
    if float(np.linalg.norm(u)) < 1e-6:
        raise ValueError("sweep: up= points along the path's start - give a direction across it")
    u /= np.linalg.norm(u)

    def step(v, i, j):                                 # from station i to station j, by the leg between them
        if legs is None:
            return _carry(v, ways[i], ways[j])
        return _carry(_carry(v, ways[i], legs[i]), legs[i], ways[j])

    ups = [u]
    for i in range(len(ways) - 1):
        ups.append(step(ups[-1], i, i + 1))
    ups = np.array(ups)
    if closed and len(ways) > 2:
        back = step(ups[-1], len(ways) - 1, 0)
        off = math.atan2(float(np.cross(ups[0], back) @ ways[0]), float(ups[0] @ back))   # what the loop turned it by
        for i in range(len(ups)):
            ups[i] = rbx_repeat.rotation(ways[i], -math.degrees(off) * i / len(ups))[:3, :3] @ ups[i]
    sides = np.cross(ups, ways)
    return sides, ups


def solid(points, section, scale=1.0, twist=0.0, smooth=True, closed=False, up=None, sides=12, strip=False):
    """the swept part -> (vertices (N, 3) float64, faces [[i, ...], ...]): closed (capped at both ends, a point where
    the scale is 0, or a loop), every face wound outward, no edge of it running BACK along the path.
    strip=True: also -> (..., face_st, length, perimeter): for each face {vertex: (s, t)} - s the studs along the
    path's own length to its station, t the share of the way round the section (0..1) - or None for an end cap;
    a face that closes a loop (the last station back to the first, the section's last side back to its first)
    reads s = the whole length and t = 1 there, so a strip laid by them runs on without a jump"""
    ring = outline(section, sides)
    sx, sy = _profile(scale, "scale", pair=True)
    tx, ty = _profile(twist if not isinstance(twist, (int, float)) or isinstance(twist, bool)
                      else [(0.0, 0.0), (1.0, twist)], "twist")
    if (sy < 0).any():
        raise ValueError("sweep: scale= cannot be under 0")
    if float(np.abs(np.diff(ty)).sum()) > 18000:
        raise ValueError("sweep: twist= of more than fifty turns is a typing mistake")
    flat = (sy.min(axis=1) < TIP) & (sy.max(axis=1) >= TIP)
    if flat.any():
        raise ValueError("sweep: a scale of 0 one way only is a flat end with no thickness - give 0 both ways (a "
                         "point) or neither")
    inner = ((sx > 1e-9) & (sx < 1 - 1e-9))
    if inner.any() and (sy[inner].max(axis=1) < TIP).any():
        raise ValueError("sweep: a scale of 0 is a point, and only an END of the path can be one")
    if float(sy.max()) < TIP:
        raise ValueError("sweep: scale= is 0 everywhere - there is no part")
    # a station wherever a profile has a point, and enough along a twist that it reads as a turn (every 10 degrees)
    extra = list(sx) + list(tx)
    for (a0, d0), (a1, d1) in zip(zip(tx, ty), zip(tx[1:], ty[1:])):
        n = int(math.ceil(abs(d1 - d0) / 10.0 - 1e-9))
        extra += [a0 + (a1 - a0) * k / n for k in range(1, n)]
    place, ways, shares, loop, mitres, legs = stations(points, smooth, closed, extra)
    side_, up_ = frames(ways, up, loop, legs)
    sc = _at(sx, sy, shares)
    tw = np.radians(_at(tx, ty, shares))
    if loop and float(sy.min()) < TIP:
        raise ValueError("sweep: a closed path has no end for a point (a scale of 0)")
    turns = abs(float(ty[-1] - ty[0])) / 360.0
    if loop and (abs(turns - round(turns)) > 1e-6 or not np.allclose(sy[0], sy[-1])):
        raise ValueError("sweep: on a closed path the twist must come back to where it started (a whole number of "
                         "turns) and the scale must end as it began")
    verts, rings = [], []
    k = len(ring)
    for i in range(len(place)):
        c, s = math.cos(tw[i]), math.sin(tw[i])
        x = ring[:, 0] * sc[i, 0]
        y = ring[:, 1] * sc[i, 1]
        xr, yr = x * c - y * s, x * s + y * c          # turned about the path (x toward y)
        end = (not loop) and i in (0, len(place) - 1)
        if end and float(sc[i].max()) < TIP:           # a point
            rings.append([len(verts)])
            verts.append(place[i])
            continue
        off = np.outer(xr, side_[i]) + np.outer(yr, up_[i])
        stretch = float(np.linalg.norm(mitres[i]))
        if stretch > 1e-12:                            # a corner: the section stretched across it (a mitre)
            off = off + np.outer(off @ (mitres[i] / stretch), mitres[i])
        rings.append(list(range(len(verts), len(verts) + k)))
        verts += list(place[i] + off)
    verts = np.array(verts, np.float64)
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if loop else [])
    # folding, on the part as it is made: between two stations every edge must run ON along the path. One that
    # runs back means the section reaches further toward the inside of a turn than the turn has room for
    # (a bend too tight for it, or a leg too short for its mitres)
    reach = float(np.linalg.norm(ring, axis=1).max())
    for i, (r0, r1) in enumerate(pairs):
        if len(r0) == 1 or len(r1) == 1:
            continue
        on = (verts[r1] - verts[r0]) @ legs[i]
        if float(on.min()) <= 1e-7:
            j = (i + 1) % len(place)
            raise ValueError(f"sweep: at {shares[i]:.0%} of the path the part would fold through itself - its "
                             f"section reaches {reach * float(max(sc[i].max(), sc[j].max())):.3g} from the path and "
                             f"the path turns within {float(np.linalg.norm(place[j] - place[i])):.3g} studs (a "
                             "gentler turn, a longer leg, or a smaller section)")
    faces = []
    # (the strip: studs along the path to each station, the share round the section to each of its points)
    run = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(np.asarray(place, np.float64), axis=0), axis=1))]
    length = float(run[-1] + (np.linalg.norm(np.asarray(place[0]) - np.asarray(place[-1])) if loop else 0.0))
    side_len = np.linalg.norm(np.roll(ring, -1, axis=0) - ring, axis=1)
    perimeter = float(side_len.sum())
    round_ = np.r_[0.0, np.cumsum(side_len)[:-1]] / max(perimeter, 1e-12)
    face_st = []
    for n_, (r0, r1) in enumerate(pairs):
        s0 = float(run[n_])
        s1 = length if (loop and n_ == len(pairs) - 1) else float(run[n_ + 1])
        for a in range(k):
            b = (a + 1) % k
            ta, tb = float(round_[a]), (1.0 if b == 0 else float(round_[b]))
            if len(r0) == 1 and len(r1) == 1:
                continue
            if len(r0) == 1:
                faces.append([r0[0], r1[b], r1[a]])
                face_st.append({r0[0]: (s0, (ta + tb) / 2), r1[b]: (s1, tb), r1[a]: (s1, ta)})
            elif len(r1) == 1:
                faces.append([r0[a], r0[b], r1[0]])
                face_st.append({r0[a]: (s0, ta), r0[b]: (s0, tb), r1[0]: (s1, (ta + tb) / 2)})
            else:
                faces.append([r0[a], r0[b], r1[b], r1[a]])
                face_st.append({r0[a]: (s0, ta), r0[b]: (s0, tb), r1[b]: (s1, tb), r1[a]: (s1, ta)})
    if not loop:
        if len(rings[0]) > 1:
            faces.append(list(reversed(rings[0])))
            face_st.append(None)
        if len(rings[-1]) > 1:
            faces.append(list(rings[-1]))
            face_st.append(None)
    if strip:
        return verts, faces, face_st, length, perimeter * float(np.abs(sc).max())
    return verts, faces


def volume(verts, faces):
    """a closed mesh's signed volume (positive: its faces wound outward)"""
    v = 0.0
    for f in faces:
        p0 = verts[f[0]]
        for a, b in zip(f[1:], f[2:]):
            v += float(np.dot(p0, np.cross(verts[a], verts[b]))) / 6.0
    return v
