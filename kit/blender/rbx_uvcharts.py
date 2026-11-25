"""rbx_uvcharts.py — UV charts for DENSE organic surfaces (a.sculpt's meshes), plain numpy (kit-owned code).

A smart projection cuts a surface wherever its face normals turn more than an angle. On a sculpt that is everywhere:
its relief (bark fissures, ridges, pores) turns the normal every few faces, so the projection made thousands of
islands and the packing margins between them swallowed the map — the tree stump's 482,876 triangles had 0.11% of their
2048 map (0.05 px per mm: its 6 mm growth rings came out 0.3 px wide, mottled). Here the charts follow the FORM, not
the relief: each face goes to the side (+x, -x, +y, ...) its SMOOTHED normal faces — the area-weighted normal of
everything within a cell of the model's size / 40 — a majority filter over the face neighbours wipes out the
specks, and the seams run only where two charts meet. A conformal unwrap of those few big charts then flattens the
relief inside them (no projection: a fissure's walls get their own texels, nothing folds over).

    labels = charts(verts, faces)          # (N,) 0..5 per face: +x -x +y -y +z -z of its smoothed normal
    seams = seam_edges(faces, labels)      # [(a, b)] vertex pairs where two charts meet
"""

import numpy as np

CELLS = 40          # the smoothing cell: the model's longest side / CELLS (the form, not its relief)
MAJORITY_PASSES = 4  # a face takes its neighbours' most common chart (specks of one or two faces are gone)


def _tris(faces):
    """faces (lists of vertex indices, 3+ each) -> (T, 3) triangles and the face each came from"""
    tri, own = [], []
    for i, f in enumerate(faces):
        for k in range(1, len(f) - 1):
            tri.append((f[0], f[k], f[k + 1]))
            own.append(i)
    return np.asarray(tri, dtype=np.int64).reshape(-1, 3), np.asarray(own, dtype=np.int64)


def face_normals(verts, faces):
    """-> (normals (N, 3) area-weighted, unnormalised: their length is twice the face's area, centres (N, 3))"""
    v = np.asarray(verts, dtype=np.float64)
    tri, own = _tris(faces)
    p = v[tri]
    cross = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n = np.zeros((len(faces), 3))
    np.add.at(n, own, cross)
    c = np.zeros((len(faces), 3))
    np.add.at(c, own, p.mean(axis=1))
    counts = np.bincount(own, minlength=len(faces)).astype(np.float64)
    return n, c / np.maximum(counts, 1.0)[:, None]


def smoothed_normals(verts, faces, cells=CELLS):
    """each face's normal averaged (by area) over the faces in its cell and the 26 around it — the FORM's direction.
    A thin shelf whose two sides cancel in a cell keeps its own normal. -> (N, 3) unit vectors"""
    n, c = face_normals(verts, faces)
    lo, hi = c.min(axis=0), c.max(axis=0)
    size = max(float((hi - lo).max()) / max(1, cells), 1e-9)
    key = np.floor((c - lo) / size).astype(np.int64)
    dims = key.max(axis=0) + 3
    flat = lambda k: ((k[:, 0] + 1) * dims[1] + (k[:, 1] + 1)) * dims[2] + (k[:, 2] + 1)  # noqa: E731
    cell = flat(key)
    uniq, inv = np.unique(cell, return_inverse=True)
    acc = np.zeros((len(uniq), 3))
    np.add.at(acc, inv, n)
    out = np.zeros_like(n)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                k2 = flat(key + np.array([dx, dy, dz]))
                idx = np.minimum(np.searchsorted(uniq, k2), len(uniq) - 1)
                hit = uniq[idx] == k2
                out[hit] += acc[idx[hit]]
    own = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    length = np.linalg.norm(out, axis=1, keepdims=True)
    weak = length[:, 0] < 0.25 * np.linalg.norm(n, axis=1) + 1e-12   # (the two sides of a shelf cancelled)
    out = out / np.maximum(length, 1e-12)
    out[weak] = own[weak]
    return out


def face_neighbours(faces):
    """-> (pairs (E, 2) of faces that share an edge)"""
    a, b, own = [], [], []
    for i, f in enumerate(faces):
        for k in range(len(f)):
            x, y = f[k], f[(k + 1) % len(f)]
            a.append(min(x, y))
            b.append(max(x, y))
            own.append(i)
    e = np.stack([np.asarray(a), np.asarray(b)], axis=1)
    own = np.asarray(own)
    order = np.lexsort((e[:, 1], e[:, 0]))
    e, own = e[order], own[order]
    same = np.all(e[1:] == e[:-1], axis=1)
    return np.stack([own[:-1][same], own[1:][same]], axis=1)


def side(normals):
    """(N, 3) -> (N,) 0..5: +x -x +y -y +z -z, the axis each normal faces most"""
    n = np.asarray(normals, dtype=np.float64)
    ax = np.abs(n).argmax(axis=1)
    return ax * 2 + (n[np.arange(len(n)), ax] < 0)


def pieces_of(n_faces, pairs):
    """-> (N,) the connected piece of every face (faces joined by a shared edge)"""
    parent = list(range(n_faces))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs.tolist():
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(n_faces)], dtype=np.int64)


def charts(verts, faces, cells=CELLS, passes=MAJORITY_PASSES, parts=None):
    """-> (N,) chart per face, 0..5 = +x -x +y -y +z -z of its smoothed normal, specks voted away.
    parts: (N,) a part id per face — each part smoothed at its OWN scale (a 40 mm fungus on a 1 m stump gets its own
    sides; smoothed at the stump's 100 mm cells it was one chart). A closed piece left in ONE chart (no seam: a
    conformal unwrap collapses it — two of the stump's fungi came out with no UV area) takes its faces' own sides."""
    n = len(faces)
    parts = np.zeros(n, dtype=np.int64) if parts is None else np.asarray(parts)
    sn = np.zeros((n, 3))
    for p in np.unique(parts):
        idx = np.flatnonzero(parts == p)
        sn[idx] = smoothed_normals(verts, [faces[i] for i in idx], cells)
    lab = side(sn)
    pairs = face_neighbours(faces)
    for _ in range(passes):
        votes = np.zeros((len(lab), 6))
        np.add.at(votes, (pairs[:, 0], lab[pairs[:, 1]]), 1.0)
        np.add.at(votes, (pairs[:, 1], lab[pairs[:, 0]]), 1.0)
        votes[np.arange(len(lab)), lab] += 0.5   # (a tie keeps the face's own chart)
        new = votes.argmax(axis=1)
        if np.array_equal(new, lab):
            break
        lab = new
    return split_closed(verts, faces, lab, pairs)


def split_closed(verts, faces, labels, pairs=None):
    """every connected piece that sits in ONE chart (a closed surface without a seam) takes its faces' own sides
    -> new labels"""
    lab = np.asarray(labels).copy()
    pairs = face_neighbours(faces) if pairs is None else pairs
    _uniq, inv = np.unique(pieces_of(len(faces), pairs), return_inverse=True)
    lo, hi = np.full(len(_uniq), 99), np.full(len(_uniq), -1)
    np.minimum.at(lo, inv, lab)
    np.maximum.at(hi, inv, lab)
    closed = ((lo == hi) & (np.bincount(inv) > 1))[inv]
    if closed.any():
        lab[closed] = side(face_normals(verts, faces)[0])[closed]
    return lab


def seam_edges(faces, labels):
    """-> set of (a, b) vertex pairs (a < b) on the border of two charts"""
    out = set()
    edge_lab = {}
    for i, f in enumerate(faces):
        for k in range(len(f)):
            x, y = f[k], f[(k + 1) % len(f)]
            e = (min(x, y), max(x, y))
            if e in edge_lab and edge_lab[e] != labels[i]:
                out.add(e)
            edge_lab.setdefault(e, labels[i])
    return out
