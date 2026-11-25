"""AN OPENING THAT MUST STAY OPEN (the owner's limitations page, 2026-11-15, D-R12: "repair is smarter but does not
know every intended opening ... protect named features through repair and optimization, and prove approved holes,
thin parts and attachments survive").

A bore, a sight line, a slot a strap runs through: the script NAMES it as a straight way from one point to another,
so wide. The build then looks down it - a bundle of lines of sight: the middle, a ring near the rim, a ring half way
in - on the parts as modelled and again on the meshes it exports (after the join and the game version's
reduction): a way that something stops fails the build by the opening's name.
It proves THOSE LINES, not the whole width: a wire thinner than the gap between two lines can pass between them.
Pure Python (the build casts the rays): no Blender."""

import math

RING = 8            # rays round the middle one, near the rim
RING_AT = 0.8       # ... at this share of the opening's half width (the rim itself may graze)
INNER = 6           # a second ring, half way in (a bar across the opening off its middle; a lip is the outer ring's)
INNER_AT = 0.4
LET_BY = 0          # rays that may be stopped: none - an opening is open or it is not


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-12:
        raise ValueError("an opening needs two different points")
    return tuple(c / n for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def rays(start, end, width, ring=RING, ring_at=RING_AT):
    """the bundle looked down: -> [(origin, direction, length)] - the middle line, `ring` lines round it at
    ring_at x half the width and INNER lines at INNER_AT x half the width (turned half a step). start, end: points;
    width: studs across the opening."""
    d = tuple(e - s for s, e in zip(start, end))
    length = math.sqrt(sum(c * c for c in d))
    u = _unit(d)
    side = _unit(_cross(u, (0.0, 1.0, 0.0) if abs(u[1]) < 0.9 else (1.0, 0.0, 0.0)))
    up = _cross(u, side)
    r = 0.5 * float(width) * ring_at
    out = [(tuple(start), u, length)]
    for count, share, turn in ((ring, 1.0, 0.0), (INNER, INNER_AT / ring_at, 0.5)):
        for i in range(count if r > 0 else 0):
            a = 2 * math.pi * (i + turn) / count
            off = tuple(r * share * (math.cos(a) * s + math.sin(a) * w) for s, w in zip(side, up))
            out.append((tuple(p + o for p, o in zip(start, off)), u, length))
    return out


def verdict(name, stopped, total, where=None, whose=None):
    """what the bundle saw -> None when the way is open, else the words"""
    if stopped <= LET_BY:
        return None
    by = f" by {whose}" if whose else ""
    at = f" at ({', '.join(f'{c:g}' for c in where)})" if where else ""
    return f"{name}: {stopped} of its {total} lines of sight are stopped{by}{at}"


def _plane(points):
    """a loop's middle and its plane's unit normal (Newell) -> (centre, normal) or (centre, None)"""
    n = len(points)
    c = tuple(sum(p[i] for p in points) / n for i in range(3))
    nx = ny = nz = 0.0
    for p, q in zip(points, list(points[1:]) + [points[0]]):
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    nn = math.sqrt(nx * nx + ny * ny + nz * nz)
    return c, (None if nn < 1e-18 else (nx / nn, ny / nn, nz / nn))


def pierces(start, end, points):
    """does a way's middle line pass THROUGH an open loop? (his D-R12: a repair must know an intended opening.)
    points: the loop's points, in order. The way passes through it when its middle line, between its two ends,
    CROSSES the loop's own plane INSIDE the loop (the crossing point is inside the loop's outline, laid flat) -
    a way that stops short of the hole, runs along beside it, or passes through the solid wall next to a long
    slot does not."""
    if len(points) < 3:
        return False
    c, normal = _plane(points)
    if normal is None:
        return False
    a = sum((start[i] - c[i]) * normal[i] for i in range(3))
    b = sum((end[i] - c[i]) * normal[i] for i in range(3))
    if a * b > 0 or abs(a - b) < 1e-12:                  # both ends on one side, or the way lies in the plane
        return False
    t = a / (a - b)
    at = tuple(start[i] + (end[i] - start[i]) * t for i in range(3))
    # the loop and the crossing point laid flat in the loop's plane, then: is the point inside the outline?
    u = _unit(_cross(normal, (0.0, 1.0, 0.0) if abs(normal[1]) < 0.9 else (1.0, 0.0, 0.0)))
    v = _cross(normal, u)

    def flat(p):
        d = tuple(p[i] - c[i] for i in range(3))
        return sum(d[i] * u[i] for i in range(3)), sum(d[i] * v[i] for i in range(3))

    x, y = flat(at)
    ring = [flat(p) for p in points]
    inside = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (x1 - x0) * (y - y0) / (y1 - y0):
            inside = not inside
    return inside


def kept(rings, ways):
    """which open loops a named way keeps open -> {index: [the ways' names]}. rings: [[points]]; ways: [(name,
    start, end)]. A way keeps a loop it passes through - but loops in ONE plane are one opening with islands (a
    thick tube's missing end is an outer loop round the bore's inner loop: the missing face is the RING between
    them): a way through an EVEN number of them passes through an island, not the opening, and keeps none."""
    out = {}
    for name, s, e in ways:
        hit = [i for i, r in enumerate(rings) if r and pierces(s, e, r)]
        planes = []      # [(centre, normal, [indices])]
        for i in hit:
            c, n = _plane(rings[i])
            for pc, pn, group in planes:
                same = abs(sum(a_ * b_ for a_, b_ in zip(n, pn))) > 0.999
                level = abs(sum((c[k] - pc[k]) * pn[k] for k in range(3)))
                size = max(math.dist(p, c) for p in rings[i])
                if same and level <= max(1e-5, 1e-3 * size):
                    group.append(i)
                    break
            else:
                planes.append((c, n, [i]))
        for _c, _n, group in planes:
            if len(group) % 2 == 1:
                for i in group:
                    out.setdefault(i, []).append(name)
    return out
