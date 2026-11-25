"""SEAMS THE AUTHOR PLACES (the owner's method lists, 2026-11-13: "seam placement"; the 3D methods audit, stage
S3b: "Seam placement (automatic only)").

The kit cuts a part's UVs where its faces turn (66 degrees) and packs what falls out. A texture artist also says
WHERE a cut goes: down the back of a handle, under a barrel, along the inside of a strap - where nobody looks - so
the part's seen side is ONE piece of the map, with no step in its grain. A placed seam is that: a rule on an edge's
two ends (the model's frame, studs), plus the edges sharper than an angle. The part is then unwrapped along those
cuts and nowhere else; a piece left with no open edge (a tube or a ball nobody cut open) cannot be laid flat and
is said, and how true the pieces lie is the map's own stretch check (rbx_uvcheck.stretch). Pure numpy; no
Blender."""

import numpy as np


def by_rule(points, edges, rule):
    """the edges a rule cuts -> sorted indices. points: (V, 3); edges: (E, 2) vertex indices; rule(a, b) with the
    edge's two ends as (x, y, z) tuples -> true where the seam goes"""
    pts = np.asarray(points, float)
    return sorted(i for i, (a, b) in enumerate(np.asarray(edges, int).reshape(-1, 2))
                  if rule(tuple(pts[a]), tuple(pts[b])))


def by_angle(edge_normals, degrees):
    """the edges sharper than an angle -> sorted indices. edge_normals: {edge index: (n1, n2)} the two faces' unit
    normals (an edge with one face, or more than two, is not asked here)"""
    if degrees is None:
        return []
    bar = float(np.cos(np.radians(float(degrees))))
    return sorted(i for i, (n1, n2) in edge_normals.items() if float(np.dot(n1, n2)) < bar - 1e-9)


def islands(faces, seams):
    """the pieces a mesh falls into when cut along `seams` -> a label per face (0..n-1, in order of first face).
    faces: a list of each face's EDGE indices; two faces are one piece when they share an edge that is not a seam."""
    cut = set(int(s) for s in seams)
    parent = list(range(len(faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first = {}
    for f, es in enumerate(faces):
        for e in es:
            if e in cut:
                continue
            if e in first:
                a, b = find(first[e]), find(f)
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                first[e] = f
    names, out = {}, []
    for f in range(len(faces)):
        out.append(names.setdefault(find(f), len(names)))
    return out


def closed(faces, labels, seams=()):
    """the pieces that have NO open edge left (a tube or a ball nobody cut open: it cannot be laid flat) -> sorted
    labels. An edge is open when it is a seam, or when one face of the piece alone uses it."""
    cut = set(int(s) for s in seams)
    uses = {}
    for f, es in enumerate(faces):
        for e in es:
            uses[(labels[f], e)] = uses.get((labels[f], e), 0) + 1
    has_open = {lab for (lab, e), n in uses.items() if n == 1 or e in cut}
    return sorted(set(labels) - has_open)


def laid(face_corners):
    """the layout that is ON the mesh, read from its corners -> (labels: the piece of each face, cuts: the edges
    that lie in two places of the map, rings: the pieces that are not a disc).
    face_corners: for each face its corners in order, each (vertex, (u, v)) - the place that corner has on the
    map. Two faces are one piece when they share an edge whose two ends have the same places in both. A piece is
    a DISC (it lies flat with no hole and no wrap) when corners - edges + faces == 1, counted on the map: a band
    laid as a ring, a tube laid round on itself or a ball give another number."""
    def key(c):
        return (int(c[0]), round(float(c[1][0]), 5), round(float(c[1][1]), 5))

    faces = [[key(c) for c in f] for f in face_corners]
    edge_faces = {}
    for f, cs in enumerate(faces):
        for i in range(len(cs)):
            a, b = cs[i], cs[(i + 1) % len(cs)]
            edge_faces.setdefault((min(a[0], b[0]), max(a[0], b[0])), []).append((f, frozenset((a, b))))
    parent = list(range(len(faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cuts = []
    for e, uses in sorted(edge_faces.items()):
        if len({u[1] for u in uses}) > 1:
            cuts.append(e)                              # (the same edge of the mesh, in two places of the map)
        seen = {}
        for f, place in uses:
            if place in seen:
                a, b = find(seen[place]), find(f)
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                seen[place] = f
    names, labels = {}, []
    for f in range(len(faces)):
        labels.append(names.setdefault(find(f), len(names)))
    rings = []
    for lab in range(len(names)):
        mine = [cs for f, cs in enumerate(faces) if labels[f] == lab]
        corners = {c for cs in mine for c in cs}
        edges = {frozenset((cs[i], cs[(i + 1) % len(cs)])) for cs in mine for i in range(len(cs))}
        if len(corners) - len(edges) + len(mine) != 1:
            rings.append(lab)
    return labels, cuts, rings
