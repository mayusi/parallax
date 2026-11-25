"""rbx_quads.py — IS A MESH QUADS, OR TRIANGLE SOUP? Pure numpy (no Blender): unit-tested in
kit/test/python/test_quads.py.

A game file is triangles (FBX / GLB triangulate every quad), so a quad mesh arrives as PAIRS of triangles: two
triangles sharing the quad's diagonal - the longest edge of both - that together make a flat, convex four-sided face
with corners near square. A decimated generator mesh or a voxel remesh is triangles that pair like that only by
chance: slivers, fans, corners of 20 and 150 degrees.

    quad_share(tris, co)            -> the share of triangles that pair into a good quad (0..1)
    polygon_share(polys, co)        -> the same for a mesh that still has its polygons (each fanned into
                                       triangles and judged the same: a four-sided face is not taken on trust)

What a GOOD quad is here (field-aligned retopology, a modelled loop): the two triangles share an edge that is the
longest of each (the diagonal), they turn under PLANAR_DEG from each other, and every corner of the four-sided
face lies within CORNER_DEG of a right angle. Measured: an Instant Meshes quad remesh of a lobed ball triangulated
for export 0.9+, the same ball decimated to the same count ~0.1-0.2 (test_quads)."""

import numpy as np

PLANAR_DEG = 25.0   # the two triangles of a quad turn no more than this from each other
CORNER_DEG = 40.0   # every corner of the quad within this of 90 degrees


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-20)


def pairs(tris, co, planar_deg=PLANAR_DEG, corner_deg=CORNER_DEG):
    """-> (T,) bool: each triangle pairs into a good quad with the neighbour across its longest edge"""
    tris, co = np.asarray(tris, np.int64).reshape(-1, 3), np.asarray(co, float).reshape(-1, 3)
    t = len(tris)
    if not t:
        return np.zeros(0, bool)
    p = co[tris]
    edge_len = np.stack([np.linalg.norm(p[:, (k + 1) % 3] - p[:, k], axis=1) for k in range(3)], axis=1)
    longest = edge_len.argmax(axis=1)   # edge k joins corners k and k+1
    a = tris[np.arange(t), longest]
    b = tris[np.arange(t), (longest + 1) % 3]
    c = tris[np.arange(t), (longest + 2) % 3]   # the corner opposite the diagonal
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    key = lo * (len(co) + 1) + hi
    order = np.argsort(key, kind="stable")
    ks = key[order]
    same = np.flatnonzero(ks[1:] == ks[:-1])
    # (an edge three triangles share as their longest pairs nothing: crowded)
    three = set(ks[np.flatnonzero(ks[2:] == ks[:-2])].tolist()) if len(ks) > 2 else set()
    out = np.zeros(t, bool)
    if not len(same):
        return out
    i, j = order[same], order[same + 1]
    ok = np.array([k not in three for k in ks[same].tolist()], bool)
    n = _unit(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]))
    ok &= (n[i] * n[j]).sum(axis=1) >= np.cos(np.radians(planar_deg))
    # the quad's corners in order: a, c_i, b, c_j (c_i and c_j on the two sides of the diagonal a-b)
    qa, qb, ci, cj = co[a[i]], co[b[i]], co[c[i]], co[c[j]]
    ring = np.stack([qa, ci, qb, cj], axis=1)
    cos_lim = np.cos(np.radians(90.0 - corner_deg))
    for k in range(4):
        prv, cur, nxt = ring[:, (k - 1) % 4], ring[:, k], ring[:, (k + 1) % 4]
        cosang = (_unit(prv - cur) * _unit(nxt - cur)).sum(axis=1)
        ok &= np.abs(cosang) <= cos_lim
    out[i[ok]] = True
    out[j[ok]] = True
    return out


def quad_share(tris, co, **kw):
    """the share of triangles that pair into a good quad"""
    pr = pairs(tris, co, **kw)
    return float(pr.mean()) if len(pr) else 0.0


def polygon_share(polys, co, **kw):
    """polys: a list of vertex-id lists (a Blender mesh's polygons). -> (share of the mesh's TRIANGLES (as the game
    counts them) in good quads, triangles). Every polygon is fanned into triangles first and judged like the rest:
    a four-sided face is not taken on trust - the kit's import joins a soup's triangles into "quads" (Blender's
    join-triangles: a decimated generator mesh came in 80% four-sided, corners of 20 and 150 degrees), and a
    skewed quad is no loop round the form either."""
    tris = [(p[0], p[k], p[k + 1]) for p in polys for k in range(1, len(p) - 1)]
    if not tris:
        return 0.0, 0
    return quad_share(np.array(tris, np.int64), co, **kw), len(tris)
