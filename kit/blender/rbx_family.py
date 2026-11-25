"""A FAMILY OF MODULES THAT SNAP (the owner's method lists: "modular snapping", "kitbashing as a library"; the 3D
methods audit's PARTLY: "a family of parts that snap to each other (dovetail joints, hallway tiles) is not built").

`a.module(grid, family=...)` holds one asset to a kit grid. A FAMILY is many such assets - a hall's straight, its
corner, its doorway, its end - that must meet without a seam: where two modules stand side by side, the shape the
one leaves on its side must be the shape the other leaves on its. The kit measures that shape: every gridded side
of a module is cut a hair inside it, and the cut (the module's cross-section there) is filled into a raster, one
per grid cell of the side, looked at FROM OUTSIDE the side (u to the right, v up). Two sides that face each other
see their shared plane mirrored left to right, so side A fits side B when A's raster is B's flipped across - on
any two sides of any two modules, so a module turned to face another way is matched too.
EVERY CELL IS ITS OWN WINDOW, the same size on every module: a grid cell, or - along an axis the grid leaves free
(a wall's own depth) - FREE_WINDOW studs centred on the side's middle, where the game lines two sides up. So two
modules' cells always compare pixel for pixel (review 2026-11-17: one raster split by integer division drifted off
its cells, and a free depth of 4.0 against 4.2 compared as "different", never as the seam it is).
  fits  - the two cuts are one shape: whatever differs is no wider than raster jitter (STEP_PX)
  seam  - related shapes (IoU >= NEAR) with a misfit at least STEP_PX + 1 raster cells wide anywhere - a lip, a step,
          a wall a little thicker: the seam a player sees, judged by its WIDTH, never by the share of the area
          (a 0.1 stud step on a big side passed an area test)
  other - different shapes (a doorway beside a wall): different connectors, never put side by side
A CONNECTOR is a shape: cut cells alike with EVERY other member (never a chain of near-alikes). Two cells meet
when they fit face to face. A seam between two DIFFERENT connectors fails the family; a connector against its own
mirror (a one-sided hall turned 180 degrees onto itself) is only said.
Pure numpy; rbx measures the cuts."""

import numpy as np

RES = 0.025        # studs a raster cell (a 4-stud cell: 160 px a side)
STEP_PX = 1        # a misfit this many raster cells wide is jitter; one wider is a step a player sees (0.075 studs)
NEAR = 0.6         # IoU under which two cuts are different connectors, never a seam
EMPTY = 0.002      # a cell filled less than this is open (nothing to meet: a doorway's gap, an open end)
FREE_WINDOW = 8.0  # studs: a cell's window along an axis the grid leaves free, centred on the side's middle


def fill(loops, lo, size, res=RES):
    """closed loops [[(u, v), ...], ...] (a cut through a solid) filled even-odd into a raster over the rectangle
    lo (u0, v0) .. lo + size, cell centres every `res` -> bool (rows v, cols u)"""
    segs = []
    for loop in loops:
        p = np.asarray(loop, float).reshape(-1, 2)
        if len(p) >= 3:
            segs += [(tuple(p[k]), tuple(p[(k + 1) % len(p)])) for k in range(len(p))]
    return fill_segments(segs, lo, size, res)


def fill_segments(segs, lo, size, res=RES):
    """a cut through ONE closed solid given as its loose edges (S, 2, 2) - (u, v) ends, in any order (a bisect's
    cut) - filled even-odd into a raster over lo .. lo + size (one solid at a time: two overlapping would cancel)"""
    nu, nv = max(1, int(round(size[0] / res))), max(1, int(round(size[1] / res)))
    us = lo[0] + (np.arange(nu) + 0.5) * size[0] / nu
    vs = lo[1] + (np.arange(nv) + 0.5) * size[1] / nv
    sg = np.asarray(segs, float).reshape(-1, 2, 2)
    inside = np.zeros((nv, nu), bool)
    if not len(sg):
        return inside
    a, b = sg[:, 0], sg[:, 1]
    for j, v in enumerate(vs):
        cross = (a[:, 1] <= v) != (b[:, 1] <= v)
        if not cross.any():
            continue
        x = a[cross, 0] + (v - a[cross, 1]) * (b[cross, 0] - a[cross, 0]) / (b[cross, 1] - a[cross, 1])
        inside[j] = ((x[None, :] > us[:, None]).sum(axis=1) % 2) == 1
    return inside


# each side seen FROM OUTSIDE: (its outward axis, sign) -> (right, up) unit axes; right = forward x up with forward
# the way the viewer looks (into the side). Facing sides (+X/-X, +Z/-Z, +Y/-Y) see their shared plane mirrored left
# to right with the same up - what `meet` flips - and a quarter turn about up carries one wall side's frame onto
# another's (test_family: every turn of every wall side)
FRAMES = {"+X": ((0, 0, -1), (0, 1, 0)), "-X": ((0, 0, 1), (0, 1, 0)),
          "+Z": ((1, 0, 0), (0, 1, 0)), "-Z": ((-1, 0, 0), (0, 1, 0)),
          "+Y": ((1, 0, 0), (0, 0, -1)), "-Y": ((-1, 0, 0), (0, 0, -1))}


def windows(lo_uv, hi_uv, grid_u, grid_v):
    """a side's cells as windows: [(v, u, (lo_u, lo_v), (size_u, size_v), (centre_u, centre_v))] - on a gridded axis
    one a grid cell, exactly; on a free axis (grid 0) one window FREE_WINDOW wide centred on the side's middle"""
    out = []

    def spans(lo, hi, g):
        if g > 0:
            n = max(1, int(round((hi - lo) / g)))
            return [(lo + i * g, g) for i in range(n)]
        mid = (lo + hi) / 2.0
        return [(mid - FREE_WINDOW / 2.0, FREE_WINDOW)]
    for j, (v0, sv) in enumerate(spans(lo_uv[1], hi_uv[1], grid_v)):
        for i, (u0, su) in enumerate(spans(lo_uv[0], hi_uv[0], grid_u)):
            out.append((j, i, (u0, v0), (su, sv), (u0 + su / 2.0, v0 + sv / 2.0)))
    return out


def _erode(m):
    """one 4-neighbour erosion (a pixel stays where it and its four neighbours are all set)"""
    e = m.copy()
    e[1:, :] &= m[:-1, :]
    e[:-1, :] &= m[1:, :]
    e[:, 1:] &= m[:, :-1]
    e[:, :-1] &= m[:, 1:]
    e[0, :] = e[-1, :] = False
    e[:, 0] = e[:, -1] = False
    return e


def misfit(a, b, step=STEP_PX):
    """where two cuts differ, is any of it WIDER than jitter: the XOR eroded `step` times, anything left -> bool"""
    x = np.asarray(a, bool) ^ np.asarray(b, bool)
    for _ in range(int(step)):
        x = _erode(x)
    return bool(x.any())


def iou(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    union = (a | b).sum()
    return float((a & b).sum() / union) if union else 1.0


def meet(a, b):
    """two cell cuts, each seen from outside its own side, standing face to face -> (verdict, IoU):
    fits / seam / other / open (both empty)"""
    a, b = np.asarray(a, bool), np.fliplr(np.asarray(b, bool))
    if a.shape != b.shape:   # (every window is the same size: only a different grid, never a different module)
        return "other", 0.0
    if a.mean() < EMPTY and b.mean() < EMPTY:
        return "open", 1.0
    q = iou(a, b)
    if not misfit(a, b):
        return "fits", q
    return ("seam", q) if q >= NEAR else ("other", q)


def same(a, b):
    """two cell cuts alike (both seen from outside their sides): no misfit wider than jitter -> bool"""
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    return a.shape == b.shape and not misfit(a, b)


def pack(r):
    """a raster as text rows ('#' filled, '.' empty) - the manifest's form, readable as a picture"""
    return ["".join("#" if x else "." for x in row) for row in np.asarray(r, bool)[::-1]]


def unpack(rows):
    return np.array([[c == "#" for c in row] for row in rows], bool)[::-1] if rows else np.zeros((0, 0), bool)


def facing(side):
    """the sides a side can stand face to face with: a wall side (X or Z, a module turns about its up) any wall
    side; a top only a bottom, a bottom only a top -> a kind: wall, +Y or -Y"""
    return "wall" if side[-1] in "XZ" else side


def faces(kind_a, kind_b):
    return (kind_a == kind_b == "wall") or {kind_a, kind_b} == {"+Y", "-Y"}


def family(modules):
    """modules {name: {side: [[cell rows (pack) for u] for v]}} -> {
      "connectors": {id: [(module, side, v, u)]}, "mates": {id: [ids it meets face to face]},
      "sides": {module: {side: [[id per cell]]}},
      "seams": [(module, side, v, u, module, side, v, u, IoU)] - two DIFFERENT shapes that almost meet: fails,
      "turned": [... the same] - a shape against its own mirror (met only turned 180 degrees onto itself): said,
      "whole": {"module.side": ["module.side" whose every cell meets it, cell u against cell n_u - 1 - u]}}"""
    flat = []
    for m, sides in sorted(modules.items()):
        for s, grid in sorted(sides.items()):
            for v, row in enumerate(grid):
                for u, rows in enumerate(row):
                    flat.append(((m, s, v, u), unpack(rows)))
    ids, groups = {}, []   # groups: (id, facing kind, [member rasters])
    for key, r in flat:
        if r.size == 0 or r.mean() < EMPTY:
            ids[key] = "open"
            continue
        got = next((cid for cid, kind, members in groups
                    if kind == facing(key[1]) and all(same(r, x) for x in members)), None)
        if got is None:
            got = f"C{len(groups) + 1}"
            groups.append((got, facing(key[1]), []))
        next(g for g in groups if g[0] == got)[2].append(r)
        ids[key] = got
    live = [(k, r) for k, r in flat if ids[k] != "open"]
    fits_pairs, seams, turned = {}, [], []
    for i, (ka, ra) in enumerate(live):
        for kb, rb in live[i:]:
            if not faces(facing(ka[1]), facing(kb[1])):
                continue
            verdict, q = meet(ra, rb)
            ca, cb = ids[ka], ids[kb]
            if verdict == "fits":
                fits_pairs.setdefault(ca, set()).add(cb)
                fits_pairs.setdefault(cb, set()).add(ca)
            elif verdict == "seam":
                (turned if ca == cb else seams).append((*ka, *kb, round(q, 3)))
    out_sides, conns = {}, {}
    for (m, s, v, u), cid in ids.items():
        out_sides.setdefault(m, {}).setdefault(s, {}).setdefault(v, {})[u] = cid
        conns.setdefault(cid, []).append((m, s, v, u))
    sides = {m: {s: [[g[v][u] for u in sorted(g[v])] for v in sorted(g)] for s, g in ss.items()}
             for m, ss in out_sides.items()}
    mates = {cid: sorted(fits_pairs.get(cid, set())) for cid, _k, _m in groups}
    whole = {}
    flat_sides = [(m, s, grid) for m, ss in sides.items() for s, grid in ss.items()]
    for ma, sa, ga in flat_sides:
        for mb, sb, gb in flat_sides:
            if not faces(facing(sa), facing(sb)) or len(ga) != len(gb) or any(len(x) != len(y) for x, y in zip(ga, gb)):
                continue
            ok = all((ga[v][u] == "open" and gb[v][len(gb[v]) - 1 - u] == "open")
                     or gb[v][len(gb[v]) - 1 - u] in mates.get(ga[v][u], [])
                     for v in range(len(ga)) for u in range(len(ga[v])))
            if ok:
                whole.setdefault(f"{ma}.{sa}", []).append(f"{mb}.{sb}")
    return {"connectors": conns, "mates": mates, "sides": sides, "seams": seams, "turned": turned, "whole": whole}
