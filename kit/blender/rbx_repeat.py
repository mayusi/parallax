"""rbx_repeat.py — REPEAT: where the copies of a part go (numpy only; rbx.Asset.repeat makes the copies).

A modeller does not build twelve teeth, eight spokes or forty chain links: he builds ONE and repeats it - Blender's
Array modifier (a count and an offset), an array round an empty (a ring), an array along a curve. A build script had
none of it: a row was typed part by part, so rows were short, rings were left out and chains were faked.

    with a.repeat(12, step=(0, 0, 0.3)):                      # a ROW: each copy `step` from the last
        a.box("Tooth", ...)
    with a.repeat(8, around="Y", centre=(0, 1, 0)):           # a RING: turned about an axis through a point
        a.cylinder("Spoke", ...)
    with a.repeat(20, along=[(0, 0, 0), (1, 0.5, 0), ...]):   # ALONG A PATH: evenly spaced, turned to follow it
        a.cad("Link", ...)

Everything is in ONE frame (studs; x across, y up, z along): the a.frame open where the block is opened, which
rbx.Asset.repeat turns into the model's. This module only says WHERE: a list of 4 x 4 matrices, the first always
the identity (the part where its script put it).

    row(count, step)                      every copy `step` further on
    ring(count, around, centre, angle, rise)   a full turn by default (the copies evenly round it, none on the first);
                                          angle < 360: an ARC with a copy at each end; rise: a helix (stairs, a
                                          spring; more than a full turn only with a rise)
    path(points, count / spacing, follow, smooth)   along a polyline (smooth=True: through the points, rounded - a
                                          centripetal curve, which never runs backwards between uneven points);
                                          the part is modelled at the path's START, facing along its first leg;
                                          follow turns each copy to the path's direction there without rolling it
                                          (parallel transport); a path that ends where it starts is a LOOP
    places(points)                        at given places (the first: where the part is modelled); moved, not turned
    varied(count, vary, seed)             a copy is not a stamp: a small size, turn and shift of its own, about the
                                          part's own centre - the same on every build
"""

import math
import zlib

import numpy as np

MAX_COPIES = 512     # more than this in one block is a typing mistake (or scattering: another tool)
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
VARY_KEYS = ("size", "turn", "shift")


def _count(count):
    try:
        ok = float(count) == int(count) and 1 <= int(count) <= MAX_COPIES
    except (TypeError, ValueError, OverflowError):
        ok = False
    if not ok:
        raise ValueError(f"repeat: count={count!r} - a whole number 1..{MAX_COPIES} (the part itself counts as one)")
    return int(count)


def _vec(v, what):
    try:
        out = np.array([float(c) for c in v], np.float64)
    except (TypeError, ValueError):
        out = np.zeros(0)
    if out.shape != (3,) or not np.isfinite(out).all():
        raise ValueError(f"repeat: {what}={v!r} - three numbers (x, y, z) in studs")
    return out


def translation(t):
    m = np.eye(4)
    m[:3, 3] = t
    return m


def rotation(axis, degrees):
    """a turn of `degrees` about `axis` (a unit 3-vector) through the origin, right-handed -> 4 x 4"""
    x, y, z = axis
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    k = 1.0 - c
    m = np.eye(4)
    m[:3, :3] = [[c + x * x * k, x * y * k - z * s, x * z * k + y * s],
                 [y * x * k + z * s, c + y * y * k, y * z * k - x * s],
                 [z * x * k - y * s, z * y * k + x * s, c + z * z * k]]
    return m


def about(point, m):
    """the transform m done about `point` instead of the origin"""
    return translation(point) @ m @ translation(-np.asarray(point, np.float64))


def row(count, step):
    """a ROW -> [4 x 4] * count: copy k is k * step from the part"""
    count, step = _count(count), _vec(step, "step")
    return [translation(step * k) for k in range(count)]


def _axis(around):
    if isinstance(around, str):
        if around.upper() not in AXES:
            raise ValueError(f'repeat: around="{around}" - "X", "Y", "Z" or a direction (x, y, z)')
        return np.array(AXES[around.upper()])
    v = _vec(around, "around")
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        raise ValueError("repeat: around=(0, 0, 0) is no direction")
    return v / n


def ring(count, around="Y", centre=(0.0, 0.0, 0.0), angle=360.0, rise=0.0):
    """a RING -> [4 x 4] * count: turned about the axis `around` through `centre`. A full turn (angle 360) spaces the
    copies evenly and puts none on the first; a smaller angle is an ARC with a copy at each end. rise: how far the
    last copy has moved along the axis (a helix: a spiral stair, a spring's coils; on a full turn, the pitch). More
    than a full turn needs a rise (two turns of a spring: angle=720, rise=...): without one its copies would land
    on each other."""
    count, axis, centre = _count(count), _axis(around), _vec(centre, "centre")
    try:
        angle, rise = float(angle), float(rise)
    except (TypeError, ValueError):
        raise ValueError(f"repeat: angle={angle!r}, rise={rise!r} - numbers (degrees, studs)") from None
    if not (math.isfinite(angle) and math.isfinite(rise)) or abs(angle) < 1e-9:
        raise ValueError(f"repeat: angle={angle!r} - degrees, not 0 (rise={rise!r})")
    whole = abs(abs(angle) - 360.0) < 1e-6
    if abs(angle) > 360.0 + 1e-6 and abs(rise) < 1e-9:
        raise ValueError(f"repeat: angle={angle:g} is more than a full turn - its copies would land on each other "
                         "(a helix: give rise= too)")
    steps = count if whole else max(count - 1, 1)
    return [about(centre, translation(axis * (rise * k / steps)) @ rotation(axis, angle * k / steps))
            for k in range(count)]


def _smooth(pts, closed=False, per=48):
    """a polyline through its points, rounded: a CENTRIPETAL Catmull-Rom curve (it never loops or runs backwards
    between points of uneven spacing, as the uniform one does), `per` pieces a span. An open path's ends are met
    along its first and last legs (a point mirrored past each end); a closed one (its last point its first) is
    rounded through the join too."""
    if closed:
        ring_ = pts[:-1]
        p = np.vstack([ring_[-1], ring_, ring_[0], ring_[1]])
    else:
        p = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        t0 = 0.0
        t1 = t0 + math.sqrt(float(np.linalg.norm(p1 - p0)))
        t2 = t1 + math.sqrt(float(np.linalg.norm(p2 - p1)))
        t3 = t2 + math.sqrt(float(np.linalg.norm(p3 - p2)))
        if min(t1 - t0, t3 - t2) < 1e-9:              # (a closed path of two legs: its neighbour is the point itself)
            out += [p1 + (p2 - p1) * k / per for k in range(per)]
            continue
        for t in np.linspace(t1, t2, per, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(pts[-1])
    return np.array(out)


def _align(a, b):
    """the smallest turn that takes direction a to direction b (unit 3-vectors) -> 4 x 4 (no roll about either). A
    path straight back on itself: turned round about the model's UP (a copy on the ground stays on its feet)"""
    v = np.cross(a, b)
    s, c = float(np.linalg.norm(v)), float(np.dot(a, b))
    if s < 1e-12:
        if c > 0:
            return np.eye(4)
        up = np.array([0.0, 1.0, 0.0]) if abs(a[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        axis = up - a * float(up @ a)
        return rotation(axis / np.linalg.norm(axis), 180.0)
    return rotation(v / s, math.degrees(math.atan2(s, c)))


def _unit(v, fallback):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else fallback


def path(points, count=None, spacing=None, follow=True, smooth=True):
    """ALONG A PATH -> [4 x 4] * n: the copies evenly spaced by the path's own length from its first point (where
    the part is modelled, facing along the path's first leg) to its last - `count` of them, or one every `spacing`
    studs. A CLOSED path (its last point its first) is a loop: `count` copies evenly round it, none on the first
    again. follow: each copy is turned to the path's direction there, carried along it without rolling; False: only
    moved. A part modelled BESIDE the path's start keeps that offset, carried round with the path."""
    try:
        pts = np.array([[float(c) for c in p] for p in points], np.float64)
    except (TypeError, ValueError):
        pts = np.zeros((0, 3))
    if pts.ndim != 2 or pts.shape[1:] != (3,) or len(pts) < 2 or not np.isfinite(pts).all():
        raise ValueError("repeat: along= is a path of two or more points (x, y, z) in studs")
    if (np.linalg.norm(np.diff(pts, axis=0), axis=1) < 1e-9).any():
        raise ValueError("repeat: along= has two points in the same place")
    closed = len(pts) > 2 and float(np.linalg.norm(pts[-1] - pts[0])) < 1e-9
    rounded = bool(smooth) and len(pts) > 2
    fine = _smooth(pts, closed) if rounded else pts
    seg = np.linalg.norm(np.diff(fine, axis=0), axis=1)
    fine = fine[np.concatenate([[True], seg > 1e-12])]   # (a curve's piece of no length: dropped)
    seg = np.linalg.norm(np.diff(fine, axis=0), axis=1)
    at = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(at[-1])
    if (count is None) == (spacing is None):
        raise ValueError("repeat: along= needs count= (so many, end to end) or spacing= (one every so many studs)")
    if spacing is not None:
        try:
            spacing = float(spacing)
        except (TypeError, ValueError):
            spacing = 0.0
        if not (math.isfinite(spacing) and spacing > 1e-6):
            raise ValueError(f"repeat: spacing={spacing!r} - studs between copies, over 0")
        n = int(math.floor(total / spacing + 1e-9)) + 1
        if closed and n > 1 and abs(spacing * (n - 1) - total) < 1e-6 * max(total, 1.0):
            n -= 1                                     # (the last would land on the first)
        if n > MAX_COPIES:
            raise ValueError(f"repeat: spacing={spacing:g} on a path {total:.3g} studs long is {n} copies - at most "
                             f"{MAX_COPIES}")
        stops = [spacing * k for k in range(n)]
    else:
        count = _count(count)
        stops = [total * k / (count if closed else max(count - 1, 1)) for k in range(count)]
    chords = np.diff(fine, axis=0) / seg[:, None]
    if rounded:   # a curve: the direction AT each of its points (between them it turns evenly), its ends the legs'
        first = _unit(pts[1] - pts[0], chords[0])
        last = _unit(pts[-1] - pts[-2], chords[-1])
        if closed:
            first = last = _unit(chords[0] + chords[-1], chords[0])
        knots = np.vstack([first, [_unit(chords[j - 1] + chords[j], chords[j]) for j in range(1, len(chords))], last])
    else:         # straight legs: a copy on a leg faces along that leg, to the corner
        knots = chords

    def where(s):
        i = int(min(max(np.searchsorted(at, s, side="right") - 1, 0), len(seg) - 1))
        f = min(max((s - at[i]) / seg[i], 0.0), 1.0)
        facing = _unit(knots[i] * (1.0 - f) + knots[i + 1] * f, chords[i]) if rounded else chords[i]
        return fine[i] + chords[i] * (s - at[i]), i, facing

    out, turn, last_i, heading = [], np.eye(4), 0, knots[0]
    for s in stops:
        p, i, facing = where(s)
        for j in range(last_i + 1, i + 1):            # carried along: a small turn at every bend passed
            turn, heading = _align(heading, knots[j]) @ turn, knots[j]
        turn, heading, last_i = _align(heading, facing) @ turn, facing, i
        out.append(translation(p) @ (turn if follow else np.eye(4)) @ translation(-pts[0]))
    return out


def varied(count, vary, seed):
    """each copy's OWN small difference -> [4 x 4] * count, the first the identity, to be done about the part's own
    centre. vary: {"size": 0.1 (each copy 90% .. 110% of the part), "turn": 15 (degrees about a random axis),
    "shift": 0.02 (studs, any direction)}. seed: a name - the same copies on every build (crc32, never hash())"""
    count = _count(count)
    vary = dict(vary or {})
    bad = sorted(set(vary) - set(VARY_KEYS))
    if bad:
        raise ValueError(f"repeat: vary has no {', '.join(bad)} - it has {', '.join(VARY_KEYS)}")
    try:
        size, turn, shift = (float(vary.get(k, 0.0)) for k in VARY_KEYS)
    except (TypeError, ValueError):
        raise ValueError(f"repeat: vary={vary!r} - numbers (size a share, turn degrees, shift studs)") from None
    if not (0.0 <= size < 1.0 and 0.0 <= turn <= 180.0 and 0.0 <= shift and math.isfinite(shift)):
        raise ValueError(f"repeat: vary={vary!r} - size 0..1 (a share), turn 0..180 degrees, shift 0 or more studs")
    rng = np.random.default_rng(zlib.crc32(str(seed).encode()))
    out = [np.eye(4)]
    for _ in range(count - 1):
        u = rng.uniform(-1.0, 1.0, 8)                 # (always the same draws: turning one knob moves no other)
        m = np.eye(4)
        m[:3, :3] *= 1.0 + size * u[0]
        axis = u[1:4] / (np.linalg.norm(u[1:4]) + 1e-12)
        m = rotation(axis, turn * u[4]) @ m
        m[:3, 3] = shift * u[5:8]
        out.append(m)
    return out


def places(points):
    """AT GIVEN PLACES -> [4 x 4] * n: the part is modelled at the first point; a copy stands at each of the
    others, moved only (screws at uneven spots, four feet, the pegs of a board: neither a row nor a ring)"""
    try:
        pts = np.array([[float(c) for c in p] for p in points], np.float64)
    except (TypeError, ValueError):
        pts = np.zeros((0, 3))
    if pts.ndim != 2 or pts.shape[1:] != (3,) or len(pts) < 2 or not np.isfinite(pts).all():
        raise ValueError("repeat: at= is two or more places (x, y, z) in studs, the first where the part is modelled")
    if len(pts) > MAX_COPIES:
        raise ValueError(f"repeat: at= has {len(pts)} places - at most {MAX_COPIES}")
    gaps = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2) + np.eye(len(pts))
    if float(gaps.min()) < 1e-9:
        raise ValueError("repeat: at= has two places in the same spot")
    return [translation(p - pts[0]) for p in pts]


OPTIONS = {"row": (), "ring": ("centre", "angle", "rise"), "path": ("spacing", "follow", "smooth"), "places": ()}
SAID_BY = {"row": "step=", "ring": "around=", "path": "along=", "places": "at="}


def resolve(count=None, step=None, around=None, along=None, centre=None, angle=None, rise=None, spacing=None,
            follow=None, smooth=None, at=None):
    """a.repeat's arguments -> (kind: "row" | "ring" | "path" | "places", the placements). Exactly one of step /
    around / along / at says which; an option of another kind (a row with angle=, a ring with spacing=) is
    refused, never silently dropped."""
    if at is not None and not isinstance(at, (str, bytes)):
        try:
            at = list(at)   # (read ONCE: a generator is used up by the first look)
        except TypeError:
            pass
    given = [k for k, v in (("step", step), ("around", around), ("along", along), ("at", at)) if v is not None]
    if len(given) != 1:
        raise ValueError("repeat: say ONE of step=(x, y, z) (a row), around='Y' (a ring), along=[points] (a path) "
                         f"or at=[places] - got {', '.join(given) or 'none'}")
    kind = {"step": "row", "around": "ring", "along": "path", "at": "places"}[given[0]]
    opts = {"centre": centre, "angle": angle, "rise": rise, "spacing": spacing, "follow": follow, "smooth": smooth}
    wrong = [k for k, v in opts.items() if v is not None and k not in OPTIONS[kind]]
    if wrong:
        raise ValueError(f"repeat: {', '.join(k + '=' for k in wrong)} - not an option of a {kind} ({SAID_BY[kind]}); "
                         f"a {kind} takes {', '.join(k + '=' for k in ('count',) + OPTIONS[kind])}")
    if kind == "places":
        if count is not None and isinstance(at, list) and count != len(at):
            raise ValueError(f"repeat: at= has {len(at)} places and count={count!r} - leave count out")
        return kind, places(at)
    if kind == "row":
        return kind, row(count, step)
    if kind == "ring":
        return kind, ring(count, around, (0.0, 0.0, 0.0) if centre is None else centre,
                          360.0 if angle is None else angle, 0.0 if rise is None else rise)
    return kind, path(along, count, spacing, True if follow is None else follow, True if smooth is None else smooth)
