"""rbx_repair.py — a mesh that is not closed, READ: what kind of opening each one is, and what closes it (the
owner's method lists, 2026-11-13: "non-manifold cleanup"; the 3D methods audit, stage M7).

Until now a build closed the tiny tears a boolean leaves and otherwise only COUNTED open edges ("manifold: 14"):
nothing said where they were, what they were or how to close them, and a session's way out was
require_manifold=False. Three different things hide in that number, each with its own repair:

    a SEAM never welded     two edges lying on each other, their points apart by a rounding error: weld them
    a flat HOLE             a missing cap (a tube's end, a cut that took a face with it): cap it flat
    an open RIM             a torn-out patch that is not flat: no flat cap is right - the model has to build
                            that face
    a SHEET's edge          the border of a surface with no thickness (a plane, a flat plate): a cap would lie ON
                            it - the model has to give it thickness

    edge_table(corner, start, total)       every edge: how many faces use it, and whether they run it opposite ways
    faults(table)                          {"open", "fins", "flipped"}
    open_loops(table)                      the open edges chained into loops (vertex ids, in order; their corners)
    face_normals(verts, corner, start, total)   every face's unit normal
    twins(verts, table, tol)               open points lying on another open point: the seam's pairs
    weld_map(pairs)                        {from: to} for a welder
    describe(verts, loop)                  a loop's size, place, flatness, area and KIND (hole / rim / slit /
                                           sheet)
    read(verts, corner, start, total, weld)   all of it for one mesh -> facts, in the order a repair takes them
    said(found)                            ... in plain words

numpy only (a mesh as arrays: `corner` the vertex of every face corner, `start` / `total` each face's corners).
"""

import numpy as np

FLAT = 0.005           # a loop is flat when no point leaves its plane by more than this share of its size (a
#                        real missing cap is flat to rounding; three panels torn from a 16-sided tube leave it by 2%)
SLIT = 2e-3            # a loop that encloses less than this share of its length squared is a slit, not a hole


def edge_table(corner, start, total):
    """-> {"a", "b": each face corner's edge a -> b; "edge": its edge's id; "count": faces per edge; "net": 0
    where an edge's two faces run it opposite ways (wound alike), "lo", "hi": the edge's vertices}"""
    corner = np.asarray(corner, np.int64)
    start, total = np.asarray(start, np.int64), np.asarray(total, np.int64)
    nxt = np.arange(len(corner), dtype=np.int64) + 1
    nxt[start + total - 1] = start
    a, b = corner, corner[nxt]
    m = int(corner.max()) + 1 if len(corner) else 1
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    uniq, inv, count = np.unique(lo * m + hi, return_inverse=True, return_counts=True)
    net = np.bincount(inv, weights=np.where(a < b, 1.0, -1.0), minlength=len(uniq))
    return {"a": a, "b": b, "edge": inv, "count": count, "net": net, "lo": uniq // m, "hi": uniq % m}


def faults(table):
    """-> {"open": edges with one face, "fins": edges with three or more, "flipped": edges whose two faces are
    wound against each other}"""
    real = table["lo"] != table["hi"]
    c = table["count"]
    return {"open": int(((c == 1) & real).sum()), "fins": int(((c > 2) & real).sum()),
            "flipped": int(((c == 2) & (table["net"] != 0) & real).sum())}


def open_loops(table):
    """the open edges chained head to tail -> [(vertex ids in order, closed, the face corner each edge starts
    at)]. Each open edge is walked the way its one face runs it. A chain that cannot close (a point where three
    open edges meet and one is left over) is returned with closed=False."""
    one = (table["count"][table["edge"]] == 1) & (table["a"] != table["b"])
    a, b = table["a"][one].tolist(), table["b"][one].tolist()
    at = np.nonzero(one)[0].tolist()
    out_of = {}
    for i, v in enumerate(a):
        out_of.setdefault(v, []).append(i)
    used = [False] * len(a)
    loops = []
    for i0 in range(len(a)):
        if used[i0]:
            continue
        chain, i = [a[i0]], i0
        closed, corners = False, []
        while True:
            used[i] = True
            corners.append(at[i])
            v = b[i]
            if v == chain[0]:
                closed = True
                break
            chain.append(v)
            nxt = next((j for j in out_of.get(v, ()) if not used[j]), None)
            if nxt is None:
                break
            i = nxt
        if closed:   # (two holes that share ONE point come back as one chain through it twice: two loops)
            for part, part_corners in _simple(chain, corners):
                loops.append((np.array(part, np.int64), True, np.array(part_corners, np.int64)))
        else:
            loops.append((np.array(chain, np.int64), False, np.array(corners, np.int64)))
    return loops


def _simple(chain, corners):
    """a closed chain that passes a point twice -> the simple loops it is made of (each point once)"""
    out, path, at = [], [], {}
    for v, c in zip(chain, corners, strict=True):
        if v in at:
            k = at[v]
            out.append(([p for p, _c in path[k:]], [c_ for _p, c_ in path[k:]]))
            for p, _c in path[k + 1:]:
                at.pop(p, None)
            path = path[:k]
        at[v] = len(path)
        path.append((v, c))
    if path:
        out.append(([p for p, _c in path], [c_ for _p, c_ in path]))
    return out


def corner_face(start, total, n_corners):
    """-> (L,) the face of every face corner"""
    start, total = np.asarray(start, np.int64), np.asarray(total, np.int64)
    out = np.zeros(n_corners, np.int64)
    idx = np.repeat(start, total) + (np.arange(int(total.sum())) - np.repeat(np.cumsum(total) - total, total))
    out[idx] = np.repeat(np.arange(len(start)), total)
    return out


def face_normals(verts, corner, start, total):
    """every face's unit normal (Newell's sum: right for any polygon) -> (P, 3); a face with no area: zeros"""
    verts = np.asarray(verts, np.float64).reshape(-1, 3)
    corner = np.asarray(corner, np.int64)
    start, total = np.asarray(start, np.int64), np.asarray(total, np.int64)
    nxt = np.arange(len(corner), dtype=np.int64) + 1
    nxt[start + total - 1] = start
    p, q = verts[corner], verts[corner[nxt]]
    n = np.zeros((len(start), 3))
    np.add.at(n, corner_face(start, total, len(corner)), np.cross(p, q))
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-15
    n[ok] /= ln[ok][:, None]
    return n


def twins(verts, table, tol):
    """open points lying on ANOTHER open point within tol, the two not joined by an edge -> (n, 2) vertex ids
    (i < j): a seam that was never welded. tol: a rounding error's size, never a modelling distance."""
    verts = np.asarray(verts, np.float64).reshape(-1, 3)
    one = (table["count"] == 1) & (table["lo"] != table["hi"])
    ids = np.unique(np.concatenate([table["lo"][one], table["hi"][one]]))
    if len(ids) < 2 or tol <= 0:
        return np.zeros((0, 2), np.int64)
    joined = set(zip(table["lo"].tolist(), table["hi"].tolist(), strict=True))
    p = verts[ids]
    cell = np.floor(p / tol).astype(np.int64)
    at = {}
    for k, c in enumerate(map(tuple, cell.tolist())):
        at.setdefault(c, []).append(k)
    near = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
    pairs = set()
    for c, here in at.items():
        for d in near:
            there = at.get((c[0] + d[0], c[1] + d[1], c[2] + d[2]))
            if not there:
                continue
            for i in here:
                for j in there:
                    if i < j and float(np.linalg.norm(p[i] - p[j])) <= tol:
                        u, v = int(ids[i]), int(ids[j])
                        if (min(u, v), max(u, v)) not in joined:
                            pairs.add((min(u, v), max(u, v)))
    return np.array(sorted(pairs), np.int64).reshape(-1, 2)


def weld_map(pairs):
    """twin pairs -> {from: to}: every point of a group of twins goes to the group's smallest id"""
    root = {}

    def find(x):
        while root.get(x, x) != x:
            root[x] = root.get(root[x], root[x])
            x = root[x]
        return x

    for u, v in np.asarray(pairs, np.int64).reshape(-1, 2).tolist():
        ru, rv = find(u), find(v)
        if ru != rv:
            root[max(ru, rv)] = min(ru, rv)
    return {x: find(x) for x in root if find(x) != x}


def welded(corner, mapping):
    """the mesh's corners after a weld (the faces are the same faces; a face that lost an edge keeps its count:
    read it through edge_table, which ignores an edge from a point to itself)"""
    corner = np.asarray(corner, np.int64).copy()
    if mapping:
        lut = np.arange(int(corner.max()) + 1, dtype=np.int64)
        for k, v in mapping.items():
            if k < len(lut):
                lut[k] = v
        corner = lut[corner]
    return corner


def describe(verts, loop, closed=True, beside=None):
    """one open loop -> {"n": its edges, "length", "size": how far across, "centre", "off": how far it
    leaves its own plane, "area": what it encloses, "normal": its plane's, "kind": "hole" (flat: a cap closes
    it) | "rim" (not flat: no flat cap is right) | "slit" (it encloses nothing: two edges nearly on each other,
    their points not matching) | "sheet" (flat, and the faces beside it lie IN its plane: the border of a
    surface with no thickness - a cap would lie on it) | "chain" (it does not close)}.
    beside: (n, 3) the normals of the faces along the loop."""
    p = np.asarray(verts, np.float64).reshape(-1, 3)[np.asarray(loop, np.int64)]
    n = len(p)
    ring = np.vstack([p, p[:1]]) if closed else p
    length = float(np.linalg.norm(np.diff(ring, axis=0), axis=1).sum())
    centre = p.mean(axis=0)
    size = 2.0 * float(np.linalg.norm(p - centre, axis=1).max())          # across: the circle round it
    out = {"n": n if closed else n - 1, "length": round(length, 5), "size": round(size, 5),
           "centre": tuple(round(float(c), 4) for c in centre), "off": 0.0, "area": 0.0, "kind": "chain"}
    if not closed or n < 3:
        return out
    _u, _s, vt = np.linalg.svd(p - centre, full_matrices=False)
    off = float(np.abs((p - centre) @ vt[2]).max())
    q = (p - centre) @ vt[:2].T
    area = abs(float((q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]).sum()) / 2)
    out["off"], out["area"] = round(off, 6), round(area, 6)
    out["normal"] = tuple(round(float(c), 4) for c in vt[2])
    if area < SLIT * length * length:
        out["kind"] = "slit"
    elif off <= max(1e-6, FLAT * size):
        lying = beside is not None and len(beside) and float(np.abs(np.asarray(beside) @ vt[2]).mean()) > 0.9
        out["kind"] = "sheet" if lying else "hole"
    else:
        out["kind"] = "rim"
    return out


def read(verts, corner, start, total, weld=1e-5):
    """one mesh -> {"faults": before anything, "twins": seam points a weld joins, "weld": {from: to},
    "after_weld": the faults left once they are welded, "loops": [describe()... + "verts"] of what is still open
    then, the largest first}"""
    table = edge_table(corner, start, total)
    before = faults(table)
    pairs = twins(verts, table, weld) if before["open"] else np.zeros((0, 2), np.int64)
    mapping = weld_map(pairs)
    if mapping:
        table = edge_table(welded(corner, mapping), start, total)
    after = faults(table)
    loops = []
    if after["open"]:
        normals = face_normals(verts, corner, start, total)
        face = corner_face(start, total, len(np.asarray(corner)))
        for loop, closed, corners in open_loops(table):
            d = describe(verts, loop, closed, normals[face[corners]])
            d["verts"] = loop
            loops.append(d)
    loops.sort(key=lambda d: -d["size"])
    return {"faults": before, "twins": int(len(pairs)), "weld": mapping, "after_weld": after, "loops": loops}


def _sizes(rows):
    s = sorted((r["size"] for r in rows), reverse=True)
    return ", ".join(f"{x:.3g}" for x in s[:3]) + (" ..." if len(s) > 3 else "")


def said(found):
    """read()'s facts in plain words, e.g. "a seam of 12 points never welded; 2 flat holes (0.4, 0.4 studs
    across); 1 open rim (3.2 studs across)". "" when the mesh is closed."""
    parts = []
    if found["twins"]:
        parts.append(f"a seam of {found['twins']} point pair{'s' if found['twins'] != 1 else ''} never welded")
    for kind, one, many in (("hole", "flat hole", "flat holes"), ("rim", "open rim", "open rims"),
                            ("sheet", "border of a surface with no thickness", "borders of surfaces with no thickness"),
                            ("slit", "slit", "slits"), ("chain", "open chain", "open chains")):
        rows = [r for r in found["loops"] if r["kind"] == kind]
        if rows:
            parts.append(f"{len(rows)} {one if len(rows) == 1 else many} ({_sizes(rows)} studs across)")
    left = found["after_weld"]
    if left["fins"]:
        parts.append(f"{left['fins']} edge{'s' if left['fins'] != 1 else ''} shared by three or more faces")
    if left["flipped"]:
        parts.append(f"{left['flipped']} edge{'s' if left['flipped'] != 1 else ''} between faces wound against each other")
    return "; ".join(parts)
