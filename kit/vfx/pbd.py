"""pbd.py - the small solver the kit's BAKED simulations share (cloth.py; the VFX methods audit, stage 15 on): points
that keep their distances. Position-based dynamics: every step each point moves by its velocity and the forces on
it, then every link is pulled back toward its rest length, a few times over; a point with weight 0 is held.

    groups(links, n)                 the links sorted into sets no point is in twice (each set is solved in one go)
    step(pos, prev, acc, dt, damp)      one move: returns the new positions (Verlet; `prev` becomes the old ones)
    solve(pos, w, sets, iters)       pull every link toward its rest length, `iters` times

A link is (a, b, rest, stiff): two point numbers, the length it wants, and how much of the error one pass takes out
(0..1). Nothing here knows what the points are a model of.
"""
import numpy as np


def groups(links, n):
    """links [(a, b, rest, stiff)] -> [(a[], b[], rest[], stiff[])]: greedy sets in which no point appears twice, so a
    whole set can be corrected at once without one correction undoing another"""
    sets = []  # [(used: set, rows: list)]
    for a, b, rest, stiff in links:
        for used, rows in sets:
            if a not in used and b not in used:
                used.add(a)
                used.add(b)
                rows.append((a, b, rest, stiff))
                break
        else:
            sets.append(({a, b}, [(a, b, rest, stiff)]))
    out = []
    for _, rows in sets:
        arr = np.array(rows, dtype=float)
        out.append((arr[:, 0].astype(int), arr[:, 1].astype(int), arr[:, 2], arr[:, 3]))
    return out


def step(pos, prev, acc, dt, damp):
    """one Verlet move: the velocity is what the point did last step, less `damp` of it a second"""
    keep = max(0.0, 1.0 - damp * dt)
    return pos + (pos - prev) * keep + acc * (dt * dt)


def solve(pos, w, sets, iters):
    """pull every link toward its rest length; w is each point's weight (0 = held, 1 = free)"""
    for _ in range(iters):
        for a, b, rest, stiff in sets:
            d = pos[b] - pos[a]
            length = np.sqrt((d * d).sum(-1))
            wa, wb = w[a], w[b]
            total = wa + wb
            ok = (length > 1e-9) & (total > 0)
            corr = np.where(ok, stiff * (length - rest) / np.where(ok, length * total, 1.0), 0.0)[:, None] * d
            pos[a] += corr * wa[:, None]
            pos[b] -= corr * wb[:, None]
    return pos
