"""WHERE ALONG ITS TRAVEL a moving part is checked (the owner's limitations page, 2026-11-15, D-R05: "ordinary
per-joint clearance checks still sample five fixed stops. Thin obstructions between 0, .25, .5, .75 and 1 can
escape").

The mechanism gate poses a joint at stops of its travel and asks, at each, whether the moving group's surface cuts
another group's. Five stops, however long the travel, let a pin standing between two of them go unseen. Here the
stops are set from HOW FAR the part moves and HOW DEEP it is along the way: between two stops the part moves no
further than half its own depth, so a thing standing ACROSS its path is cut by its surface at one stop at least.
NOT covered: a thing thinner than the path between two stops that the part swallows whole (its faces never cut).
Pure Python: no Blender."""

import math

QUARTERS = (0.0, 0.25, 0.5, 0.75, 1.0)   # the five stops the gate always had: still among the stops, still in the facts
MOST = 48                                # PIECES of one joint's travel, at most (49 stops: each poses the model)
STEP_OF_DEPTH = 0.5                      # between stops the part moves this share of its own smallest depth
STEP_OF_MODEL = 0.02                     # ... and never more than this share of the model's diagonal
STEP_FLOOR = 0.002                       # ... nor less than this share (a hair-thin part would ask for thousands)


def path_length(points_at, lo, hi, pieces=16):
    """how far the fastest corner of the moving group goes over the travel. points_at(value) -> [(x, y, z), ...]
    the group's corners with the joint at that value. The path is walked in `pieces` (a hinge's arc as its
    chords)."""
    prev, far = points_at(lo), None
    total = [0.0] * len(prev)
    for i in range(1, pieces + 1):
        now = points_at(lo + (hi - lo) * i / pieces)
        for k, (p, q) in enumerate(zip(prev, now)):
            total[k] += math.dist(p, q)
        prev = now
    far = max(total) if total else 0.0
    return far


def step_for(depth, diagonal):
    """the furthest the part may move between two stops: half its own smallest depth, within the model's bounds"""
    return max(min(STEP_OF_DEPTH * depth, STEP_OF_MODEL * diagonal), STEP_FLOOR * diagonal, 1e-9)


def stops(lo, hi, length, step, most=MOST):
    """the values of the joint to pose it at -> (values from lo to hi, the path between two of them, coarse).
    Always a multiple of four pieces, so the quarter stops are among them. coarse: the travel is longer than `most`
    stops can cover at `step` - a thing thinner than the path between two stops can still escape, and is said."""
    if hi == lo:
        return [round(lo, 6)], 0.0, False
    n = max(4, int(math.ceil(length / step - 1e-9)))
    n = 4 * int(math.ceil(n / 4))
    coarse = n > most
    if coarse:
        n = most - most % 4
    values = sorted({round(lo + (hi - lo) * i / n, 6) for i in range(n + 1)})
    return values, length / n, coarse


def is_quarter(value, lo, hi):
    """is this stop one of the five the facts always named? (held against the quarter stops as `stops` rounds
    them: a travel of 0.1167 studs has its end at 0.116667, not at a quarter by division)"""
    if hi == lo:
        return True
    return any(abs(value - round(lo + (hi - lo) * q, 6)) < 1e-9 for q in QUARTERS)


POSES = 400                              # poses of one model's action cycles checked, at most


def walk(moves, must, steps, most=POSES):
    """which poses of a timeline to check so that no part moves more than its step unseen. moves: for each pose
    after the first, {group: how far it moved since the pose before}; must: the indices always checked (the first
    and the last are); steps: {group: its step}. -> (indices, scale, coarse). A pose is checked when going on to
    the next without it would carry some group further than its step since the last one checked. When that asks
    for more than `most` poses the steps are widened by `scale` (coarse: a thing thinner than scale x a part's
    step can still pass between two poses - said, never silent)."""
    n = len(moves) + 1
    keep = set(must) | {0, n - 1}

    def run(scale):
        out, acc = [0], {}
        for i in range(1, n):
            for g, d in moves[i - 1].items():
                acc[g] = acc.get(g, 0.0) + d
            ahead = moves[i] if i < n - 1 else {}
            over = any(acc.get(g, 0.0) + d > steps[g] * scale + 1e-12 for g, d in ahead.items() if d > 0)
            if i in keep or over:
                if any(v > 1e-12 for v in acc.values()) or i in keep:
                    out.append(i)
                acc = {}
        return out

    scale, got = 1.0, run(1.0)
    for _ in range(12):
        if len(got) <= most:
            break
        scale *= max(1.25, len(got) / float(most))
        got = run(scale)
    return got, scale, scale > 1.0
