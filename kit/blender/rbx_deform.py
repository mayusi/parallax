"""rbx_deform.py — DEFORM: bend, twist and taper a part (numpy only; rbx.Asset.bend / twist / taper move the mesh).

A modeller builds a horn, a hook, a fang or a scroll STRAIGHT - a plain tapered bar is easy to get right - and then
bends, twists and tapers it (Blender's Simple Deform modifier: bend, twist, taper; each along one axis, between two
limits). A build script had none of it: curved things were typed as lofts through hand-placed stations, or left
straight.

    a.taper("Horn", along="Z", end=0.15)                 # its far end 15% of its section
    a.twist("Horn", along="Z", angle=90)                 # a quarter turn from one end to the other
    a.bend("Horn", along="Z", toward="Y", angle=70)      # curled 70 degrees toward +Y

Everything works on points (N, 3) in ONE frame: `along` is the part's LENGTH (the deform runs from its low end to
its high end on that axis, or between `start` and `stop`, shares 0..1 of its length), the section is what lies
across it. A deform needs vertices along the length to show: `cuts()` says where to slice the part first.
within=span(...): the stretch measured ONCE on the part and used for other points too (its copies, its detailed
version, a point a hair beside one of its own), so all of them are deformed as one thing.

    bend    the length becomes an arc of `angle` degrees curling toward `toward` (a direction across the length);
            the line through the section's middle keeps its length (the inside shortens, the outside stretches);
            what lies past `stop` goes on straight, turned by the whole angle
    twist   every section turned about the length's axis, from 0 at `start` to `angle` at `stop`
    taper   every section scaled about the axis, from 1 at `start` to `end` at `stop` - or along a profile
            [(share of the length, scale), ...] for a belly, a waist, a flare
    conform every point moved along one direction until the part lies ON another surface (Blender's Shrinkwrap,
            projected): a strap that hugs a body, a plate that follows a hull. It keeps its own thickness.
"""

import math

import numpy as np

AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
MAX_BEND = 360.0     # a full turn: a bar bent into a ring; further and it would lie on itself
MAX_CUTS = 256


def direction(v, what="along"):
    """an axis name ("X", "-Y") or a direction (x, y, z) -> a unit 3-vector"""
    if isinstance(v, str):
        name = v.strip().upper()
        sign = -1.0 if name.startswith("-") else 1.0
        name = name.lstrip("+-")
        if name not in AXES:
            raise ValueError(f'deform: {what}="{v}" - "X", "Y", "Z" (or "-X" ...) or a direction (x, y, z)')
        return sign * np.array(AXES[name])
    try:
        out = np.array([float(c) for c in v], np.float64)
    except (TypeError, ValueError):
        out = np.zeros(0)
    n = float(np.linalg.norm(out)) if out.shape == (3,) else 0.0
    if out.shape != (3,) or not np.isfinite(out).all() or n < 1e-9:
        raise ValueError(f"deform: {what}={v!r} - an axis name or a direction (x, y, z), not zero")
    return out / n


def _share(v, what):
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = float("nan")
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"deform: {what}={v!r} - a share of the part's length, 0..1")
    return v


def span(co, along, start=0.0, stop=1.0, origin=None):
    """where a deform runs on these points -> (o, u, s0, s1): u the unit length axis; o a point on the deform's own
    axis (the middle of the points' box unless `origin` is given); s0 and s1 the positions along u (measured from
    o) where it starts and stops - `start` / `stop` shares of the points' own extent on that axis"""
    co = np.asarray(co, np.float64).reshape(-1, 3)
    if not len(co) or not np.isfinite(co).all():
        raise ValueError("deform: the part has no points to move")
    u = direction(along)
    start, stop = _share(start, "start"), _share(stop, "stop")
    if stop - start < 1e-6:
        raise ValueError(f"deform: start={start} and stop={stop} leave no length to deform")
    o = (co.min(axis=0) + co.max(axis=0)) / 2 if origin is None else np.array([float(c) for c in origin], np.float64)
    s = (co - o) @ u
    lo, hi = float(s.min()), float(s.max())
    if hi - lo < 1e-9:
        raise ValueError(f'deform: the part has no length along "{along}"')
    return o, u, lo + (hi - lo) * start, lo + (hi - lo) * stop


def cuts(co, along, count, start=0.0, stop=1.0, origin=None):
    """where to slice a part so a deform shows -> [(point on the plane (3,), the plane's normal (3,))] * count,
    evenly between the deform's start and stop (the ends themselves are not cut: there is an edge there or none
    is needed)"""
    try:
        ok = float(count) == int(count) and 0 <= int(count) <= MAX_CUTS
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise ValueError(f"deform: cuts={count!r} - a whole number 0..{MAX_CUTS}")
    o, u, s0, s1 = span(co, along, start, stop, origin)
    return [(o + u * (s0 + (s1 - s0) * k / (int(count) + 1)), u) for k in range(1, int(count) + 1)]


def edges(co, along, start=0.0, stop=1.0, origin=None):
    """a slice at each END of a deform's stretch that lies inside the part (start over 0, stop under 1): without
    one the deform has no vertex to start or stop at, and runs on to the part's next vertex instead (a taper
    from half way up a plain bar tapered the whole bar) -> [(point, normal)]"""
    o, u, s0, s1 = span(co, along, start, stop, origin)
    out = []
    if _share(start, "start") > 1e-6:
        out.append((o + u * s0, u))
    if _share(stop, "stop") < 1.0 - 1e-6:
        out.append((o + u * s1, u))
    return out


def _across(u, toward):
    """the direction a bend curls toward, made square to the length u -> (w, v): w across (toward), v = u x w"""
    w = direction(toward, "toward")
    w = w - u * float(w @ u)
    n = float(np.linalg.norm(w))
    if n < 1e-6:
        raise ValueError("deform: toward= must point ACROSS the part's length, not along it")
    w = w / n
    return w, np.cross(u, w)


def bend(co, along, toward, angle, start=0.0, stop=1.0, origin=None, within=None):
    """BEND -> points (N, 3) float64. The stretch between start and stop becomes an arc of `angle` degrees curling
    toward `toward`; before it nothing moves; past it the part goes on straight, turned by the whole angle. The
    line through `origin` along the length (the box's middle by default) keeps its length."""
    co = np.asarray(co, np.float64).reshape(-1, 3)
    try:
        angle = float(angle)
    except (TypeError, ValueError):
        angle = float("nan")
    if not math.isfinite(angle) or abs(angle) > MAX_BEND:
        raise ValueError(f"deform: angle={angle!r} - degrees, at most {MAX_BEND:g} either way")
    o, u, s0, s1 = span(co, along, start, stop, origin) if within is None else within
    if abs(angle) < 1e-9:
        return co.copy()
    w, v = _across(u, toward)
    rel = co - o
    s, h, k = rel @ u, rel @ w, rel @ v
    total = math.radians(angle)
    radius = (s1 - s0) / total                         # of the middle line's arc (negative: curls the other way)
    t = np.clip((s - s0) / (s1 - s0), 0.0, 1.0) * total   # how far round each point's section has gone
    past = np.maximum(s - s1, 0.0)                     # what lies beyond the bend: carried on straight
    r = radius - h
    inside = float((h * np.sign(radius))[s > s0].max(initial=0.0))   # how far the part reaches toward the arc's centre
    if inside >= abs(radius) - 1e-9:   # (the inner side would fold through the arc's centre and out the other side)
        raise ValueError(f"deform: a bend of {angle:g} degrees over {s1 - s0:.3g} studs has a radius of "
                         f"{abs(radius):.3g}, and the part reaches {inside:.3g} toward its inside - it would fold "
                         "through itself (bend less, over a longer stretch, or a thinner part)")
    s_new = np.where(s < s0, s, s0 + r * np.sin(t) + past * np.cos(t))
    h_new = np.where(s < s0, h, radius - r * np.cos(t) + past * np.sin(t))
    out = o + np.outer(s_new, u) + np.outer(h_new, w) + np.outer(k, v)
    out[s <= s0] = co[s <= s0]                         # (what lies before the bend: not moved, not by a rounding)
    return out


def twist(co, along, angle, start=0.0, stop=1.0, origin=None, within=None):
    """TWIST -> points (N, 3): every section turned about the length's axis (through `origin`), from nothing at
    start to `angle` degrees at stop (right-handed about `along`); past stop the whole angle"""
    co = np.asarray(co, np.float64).reshape(-1, 3)
    try:
        angle = float(angle)
    except (TypeError, ValueError):
        angle = float("nan")
    if not math.isfinite(angle) or abs(angle) > 3600.0:
        raise ValueError(f"deform: angle={angle!r} - degrees (ten turns at most)")
    o, u, s0, s1 = span(co, along, start, stop, origin) if within is None else within
    rel = co - o
    s = rel @ u
    t = np.clip((s - s0) / (s1 - s0), 0.0, 1.0) * math.radians(angle)
    side = rel - np.outer(s, u)                        # each point's place across the axis
    turned = side * np.cos(t)[:, None] + np.cross(u, side) * np.sin(t)[:, None]
    out = o + np.outer(s, u) + turned
    out[t == 0.0] = co[t == 0.0]                       # (what is not turned: not moved, not by a rounding)
    return out


def profile_at(profile, t):
    """a taper's scale at shares t (N,) of the length -> (N,): straight lines between the profile's points, its end
    values held outside them"""
    try:
        pts = sorted((float(a), float(b)) for a, b in profile)
    except (TypeError, ValueError):
        pts = []
    if len(pts) < 2 or any(not (0.0 <= a <= 1.0) or not (b > 0.0 and math.isfinite(b)) for a, b in pts):
        raise ValueError("deform: profile= is two or more (share of the length 0..1, scale over 0) pairs")
    xs, ys = np.array([a for a, _b in pts]), np.array([b for _a, b in pts])
    if (np.diff(xs) < 1e-9).any():
        raise ValueError("deform: profile= has two points at the same share of the length")
    return np.interp(t, xs, ys)


def taper(co, along, end=None, start=0.0, stop=1.0, origin=None, profile=None, keep=None, within=None):
    """TAPER -> points (N, 3): every section scaled about the length's axis (through `origin`) - from 1 at start
    to `end` at stop, or by `profile` [(share, scale), ...] over that stretch. keep: a direction across the length
    that is NOT scaled (a blade tapers in width and keeps its thickness)"""
    co = np.asarray(co, np.float64).reshape(-1, 3)
    if (end is None) == (profile is None):
        raise ValueError("deform: taper needs end= (the far end's scale) or profile=[(share, scale), ...]")
    o, u, s0, s1 = span(co, along, start, stop, origin) if within is None else within
    rel = co - o
    s = rel @ u
    t = np.clip((s - s0) / (s1 - s0), 0.0, 1.0)
    if profile is not None:
        scale = profile_at(profile, t)
    else:
        try:
            end = float(end)
        except (TypeError, ValueError):
            end = float("nan")
        if not (math.isfinite(end) and 0.0 < end <= 20.0):
            raise ValueError(f"deform: end={end!r} - the far end's scale, over 0 (1 = no taper)")
        scale = 1.0 + (end - 1.0) * t
    side = rel - np.outer(s, u)
    if keep is None:
        out = o + np.outer(s, u) + side * scale[:, None]
    else:
        w, _v = _across(u, keep)
        held = np.outer(side @ w, w)                   # the part of each point's place that is not scaled
        out = o + np.outer(s, u) + held + (side - held) * scale[:, None]
    out[scale == 1.0] = co[scale == 1.0]               # (what is not scaled: not moved, not by a rounding)
    return out


def needed(angle, per=10.0):
    """how many slices a bend or a twist of `angle` degrees needs to read as a curve and not as a kink: one every
    `per` degrees (a 90 degree bend: 8 slices, nine pieces of 10 degrees)"""
    try:
        n = int(math.ceil(abs(float(angle)) / float(per) - 1e-9)) - 1
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(MAX_CUTS, n))


def profile_cuts(co, along, profile, start=0.0, stop=1.0, origin=None):
    """where a profile taper needs a slice: at each of the profile's own points inside the stretch (between them
    the scale runs straight, which a straight edge already is) -> [(point, normal)]"""
    profile_at(profile, np.zeros(1))                   # (a bad profile is said here)
    o, u, s0, s1 = span(co, along, start, stop, origin)
    return [(o + u * (s0 + (s1 - s0) * float(a)), u) for a in sorted({float(a) for a, _b in profile})
            if 1e-6 < float(a) < 1.0 - 1e-6]


def grid(co, toward, pitch):
    """planes that slice a part into pieces at most `pitch` studs wide, both ways ACROSS `toward` (so a flat plate
    can follow a curved surface) -> [(point, normal)]"""
    co = np.asarray(co, np.float64).reshape(-1, 3)
    d = direction(toward, "toward")
    try:
        pitch = float(pitch)
    except (TypeError, ValueError):
        pitch = 0.0
    if not (math.isfinite(pitch) and pitch > 1e-6):
        raise ValueError(f"deform: pitch={pitch!r} - studs between slices, over 0")
    first = np.array(AXES["X"]) if abs(d[0]) < 0.9 else np.array(AXES["Y"])
    w = first - d * float(first @ d)
    w /= np.linalg.norm(w)
    out = []
    for axis in (w, np.cross(d, w)):
        s = co @ axis
        lo, hi = float(s.min()), float(s.max())
        n = min(MAX_CUTS, max(0, int(math.ceil((hi - lo) / pitch - 1e-9)) - 1))
        out += [(axis * (lo + (hi - lo) * k / (n + 1)), axis) for k in range(1, n + 1)]
    return out


def conform(co, toward, reach, gap=0.0, lead=None):
    """CONFORM -> (points (N, 3), the share of the points whose ray met nothing). Every point moves along `toward`
    until the part's LEADING side (the side that faces the way it travels) lies on the surface, `gap` studs off
    it; the part keeps its own thickness and its own profile (a point that lies 0.05 behind the leading side ends
    0.05 behind it). reach (N,): how far each point's own ray along `toward` goes before it meets the surface,
    nan where it meets nothing - such a point moves as the nearest point that did (measured across `toward`), so
    an overhang carries on level instead of dropping off the edge. lead: where the leading side is along `toward`
    (the points' own furthest by default; given, another set of points - the part's detailed version, a copy -
    is laid down exactly as the part is)."""
    co = np.asarray(co, np.float64).reshape(-1, 3)
    d = direction(toward, "toward")
    reach = np.asarray(reach, np.float64).reshape(-1)
    try:
        gap = float(gap)
    except (TypeError, ValueError):
        gap = float("nan")
    if len(reach) != len(co) or not math.isfinite(gap):
        raise ValueError("deform: conform needs one reach per point and a gap in studs")
    hit = np.isfinite(reach)
    if not hit.any():
        raise ValueError("deform: nothing of the part is over the surface along toward= (it would not move)")
    s = co @ d
    lead = float(s.max()) if lead is None else float(lead)
    move = reach - (lead - s) - gap                    # (its ray's length, less how far behind the leading side it is)
    if not hit.all():
        flat = co - np.outer(s, d)                     # the points seen along `toward`
        src, miss = flat[hit], np.flatnonzero(~hit)
        for i in range(0, len(miss), 2048):            # (in pieces: every missed point against every one that hit)
            part = miss[i:i + 2048]
            near = np.argmin(((flat[part][:, None, :] - src[None, :, :]) ** 2).sum(axis=2), axis=1)
            move[part] = move[hit][near]
    return co + np.outer(move, d), float((~hit).mean())
