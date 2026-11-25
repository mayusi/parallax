"""rbx_denoise.py — a generated hard-surface mesh made clean without melting it (kit-owned code; numpy only: Blender's
python has no scipy). make_clean.py runs it on the candidates of hard-surface objects before the tournament.

A generator's surface is noisy (Pixal3D's Glock: a median 5.1 deg between neighbouring faces, every flat face rippled)
or melted (Hunyuan's: no edge over 45 deg at all). Plain smoothing removes the noise AND the edges. This is GUIDED
normal filtering (Zhang et al. 2015, "Guided Mesh Normal Filtering", simplified): each face takes its guidance from
the most consistent patch around it (the 1-ring of faces whose normals differ least) and averages its neighbours'
normals weighted by how alike their GUIDANCE is — so faces on one side of an edge never average with the other side
— then the vertices move to fit the filtered normals (Sun et al. 2007's update). Measured on Pixal3D's Glock: noise
5.1 -> 1.25 deg, flat faces 34 -> 61 %, its real edges kept (sharp share 0.072). Note: it erases relief finer than a
few faces (tried as a SHARPENER on Hunyuan's melted shape: crisper serrations, but the slide's rear plate outline went).

    V2 = denoise(V, F)                 # V (n, 3) float, F (m, 3) int triangles, welded
    crispness(V, F)                    # {"flat_share", "sharp_share", "noise_deg"} (model_quality.py's measures)
"""

import numpy as np


def scatter(idx, vals, n):
    """sum vals ((k,) or (k, d)) into n bins by idx (np.add.at's result, by bincount: many times faster)"""
    if vals.ndim == 1:
        return np.bincount(idx, vals, minlength=n)
    return np.stack([np.bincount(idx, vals[:, c], minlength=n) for c in range(vals.shape[1])], 1)


def face_geometry(V, F):
    """-> (unit normals (m, 3), areas (m,), centroids (m, 3))"""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    cr = np.cross(b - a, c - a)
    ln = np.linalg.norm(cr, axis=1)
    return cr / np.maximum(ln, 1e-30)[:, None], ln / 2, (a + b + c) / 3


def ring_pairs(F, nv):
    """every ordered pair (i, j), i != j, of faces sharing a vertex (each face's 1-ring) -> (I, J)"""
    fv = F.ravel()
    fi = np.repeat(np.arange(len(F)), 3)
    order = np.argsort(fv, kind="stable")
    fv, fi = fv[order], fi[order]
    starts = np.searchsorted(fv, np.arange(nv))
    deg = np.searchsorted(fv, np.arange(nv), side="right") - starts
    I, J = [np.zeros(0, np.int64)], [np.zeros(0, np.int64)]
    for d in range(2, int(deg.max(initial=0)) + 1):  # the vertices of degree d: all pairs among their d faces
        vs = np.nonzero(deg == d)[0]
        if not len(vs):
            continue
        blocks = fi[starts[vs][:, None] + np.arange(d)[None, :]]
        ii, jj = np.repeat(blocks, d, axis=1).ravel(), np.tile(blocks, (1, d)).ravel()
        keep = ii != jj
        I.append(ii[keep])
        J.append(jj[keep])
    I, J = np.concatenate(I), np.concatenate(J)
    key = np.unique(I * len(F) + J)  # (two faces sharing an edge meet at two vertices: once is enough)
    return key // len(F), key % len(F)


def denoise(V, F, iters=8, sigma_r=0.3, v_iters=15):
    """the guided filter (module doc) -> new vertex positions (n, 3). sigma_r: how alike two guidance normals must be
    to average (|g_i - g_j|, 0.3 ~ 17 deg): smaller keeps more edges and more noise"""
    V = np.asarray(V, np.float64).copy()
    F = np.asarray(F, np.int64)
    m = len(F)
    if m == 0:
        return V
    I, J = ring_pairs(F, len(V))
    vi = F.ravel()
    cnt = np.maximum(np.bincount(vi, minlength=len(V)), 1)[:, None]
    for _ in range(int(iters)):
        N, A, _C = face_geometry(V, F)
        # each patch's consistency: the largest normal difference between its face and the faces round it
        H = np.zeros(m)
        np.maximum.at(H, I, np.linalg.norm(N[I] - N[J], axis=1))
        # each face's guide: the most consistent patch among its own and its ring's
        Hmin = H.copy()
        np.minimum.at(Hmin, I, H[J])
        best = np.arange(m)
        pick = H[J] == Hmin[I]
        best[I[pick]] = J[pick]
        own = H <= Hmin
        best[own] = np.nonzero(own)[0]
        pm = scatter(I, N[J] * A[J][:, None], m) + N * A[:, None]
        pm /= np.maximum(np.linalg.norm(pm, axis=1, keepdims=True), 1e-30)
        G = pm[best]
        # the joint bilateral filter: a neighbour counts by its area and how alike its guide is
        w = A[J] * np.exp(-np.sum((G[I] - G[J]) ** 2, axis=1) / (2 * sigma_r * sigma_r))
        Nf = N * A[:, None] + scatter(I, N[J] * w[:, None], m)
        Nf /= np.maximum(np.linalg.norm(Nf, axis=1, keepdims=True), 1e-30)
        Nr = np.repeat(Nf, 3, axis=0)
        for _ in range(int(v_iters)):  # each vertex onto the planes of its faces' filtered normals
            _N, _A, C = face_geometry(V, F)
            d = np.sum(Nr * (np.repeat(C, 3, axis=0) - V[vi]), axis=1)
            V += scatter(vi, Nr * d[:, None], len(V)) / cnt
    return V


def edge_pairs(F):
    """the pairs of faces sharing an edge -> (I, J), each pair once"""
    F = np.asarray(F, np.int64)
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    fid = np.tile(np.arange(len(F)), 3)
    key = e[:, 0] * (int(e.max(initial=0)) + 1) + e[:, 1]
    order = np.argsort(key, kind="stable")
    key, fid = key[order], fid[order]
    pair = np.nonzero(key[1:] == key[:-1])[0]
    return fid[pair], fid[pair + 1]


def components(mask, I, J):
    """connected components of the masked faces over the pairs (I, J) -> labels (m,), -1 where not masked"""
    lab = np.where(mask, np.arange(len(mask)), -1)
    keep = mask[I] & mask[J]
    a, b = I[keep], J[keep]
    while True:
        low = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, low)
        np.minimum.at(new, b, low)
        new[mask] = new[new[mask]]  # (pointer jumping: a label takes its label's label)
        if np.array_equal(new, lab):
            return lab
        lab = new


def border_ease(F, region, vs, rings):
    """per vertex of `vs` (the region's, sorted): 0 on the region's border (a vertex also on a face outside it),
    rising by 1 / rings per vertex ring inward, 1 from `rings` rings in"""
    inside = np.zeros(int(F.max(initial=0)) + 1, bool)
    inside[F[region].ravel()] = True
    outside = np.zeros_like(inside)
    outside[F[~region].ravel()] = True
    ring = np.full(len(inside), -1)
    ring[inside & outside] = 0
    e = np.concatenate([F[region][:, [0, 1]], F[region][:, [1, 2]], F[region][:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    for k in range(1, rings + 1):
        nxt = e[(ring[e[:, 0]] == k - 1) & (ring[e[:, 1]] < 0), 1]
        ring[nxt] = k
    r = ring[vs].astype(np.float64)
    return np.where(r < 0, 1.0, np.minimum(r / rings, 1.0))


def planarize(V, F, angle=6.0, min_share=0.01, tol=0.004, rings=4):
    """the FLAT faces of a hard surface made dead flat: the area-weighted normal directions that hold at least
    `min_share` of the surface, each one's connected regions of faces within `angle` degrees of it, and each region
    whose vertices all lie within `tol` x the object's size of its best plane (it is flat already, only wavy: a
    generated slide flank) moved onto that plane. A curve never qualifies (its faces fall outside the angle, or its
    region off its plane). -> (new vertices, [{normal, area_share, max_move} per region])"""
    V = np.asarray(V, np.float64).copy()
    F = np.asarray(F, np.int64)
    N, A, _C = face_geometry(V, F)
    total = float(A.sum()) or 1.0
    size = float((V.max(0) - V.min(0)).max()) or 1.0
    I, J = edge_pairs(F)
    # the dominant directions: normals binned on a cube map (64 x 64 a side), the bins holding min_share of the area
    ax = np.argmax(np.abs(N), axis=1)
    sgn = np.sign(N[np.arange(len(N)), ax]).astype(np.int64)
    uv = np.take_along_axis(N, np.array([[1, 2], [0, 2], [0, 1]])[ax], axis=1)
    uv = uv / np.maximum(np.abs(N[np.arange(len(N)), ax]), 1e-9)[:, None]
    cell = np.clip(((uv + 1) / 2 * 64).astype(np.int64), 0, 63)
    bins = ((ax * 2 + (sgn > 0)) * 64 + cell[:, 0]) * 64 + cell[:, 1]
    area_bin = np.bincount(bins, A)
    taken = np.zeros(len(F), bool)
    cos_a = np.cos(np.radians(angle))
    done = []
    for b in np.argsort(area_bin)[::-1]:
        if area_bin[b] < min_share * total:
            break
        sel = (bins == b) & ~taken
        if not sel.any():
            continue
        d = (N[sel] * A[sel][:, None]).sum(0)
        d /= max(np.linalg.norm(d), 1e-12)
        near = (N @ d >= cos_a) & ~taken
        lab = components(near, I, J)
        ids, cnt = np.unique(lab[lab >= 0], return_counts=True)
        for k in ids:
            region = lab == k
            if A[region].sum() < min_share * total:
                continue
            taken |= region
            vs = np.unique(F[region])
            P = V[vs]
            c = P.mean(0)
            w, vec = np.linalg.eigh((P - c).T @ (P - c))
            n = vec[:, 0] * (1 if vec[:, 0] @ d >= 0 else -1)
            dist = (P - c) @ n
            if np.abs(dist).max() > tol * size:
                continue
            # eased in from the region's border over `rings` vertex rings: moved whole up to its edge, a region
            # left a step where it met its unflattened neighbours (bands on the Glock's frame flank)
            V[vs] = P - np.outer(dist * border_ease(F, region, vs, rings), n)
            done.append({"normal": [round(float(x), 3) for x in n], "area_share": round(float(A[region].sum() / total), 4),
                         "max_move": round(float(np.abs(dist).max() / size), 5)})
    return V, done


def crispness(V, F):
    """the dihedral angles between edge-neighbouring faces: {flat_share (< 2 deg), sharp_share (> 45 deg), noise_deg
    (the median)} — a modelled hard surface is flat faces and real edges (0.3-0.4 / 0.17-0.28); a melted generated one
    has no edge (sharp ~0); a noisy one little flat (model_quality.py measures the same over a whole file)"""
    F = np.asarray(F, np.int64)
    N, _A, _C = face_geometry(np.asarray(V, np.float64), F)
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    fid = np.tile(np.arange(len(F)), 3)
    key = e[:, 0] * (int(e.max(initial=0)) + 1) + e[:, 1]
    order = np.argsort(key, kind="stable")
    key, fid = key[order], fid[order]
    pair = np.nonzero(key[1:] == key[:-1])[0]
    if not len(pair):
        return {"flat_share": 0.0, "sharp_share": 0.0, "noise_deg": 0.0}
    cosang = np.clip(np.sum(N[fid[pair]] * N[fid[pair + 1]], axis=1), -1, 1)
    ang = np.degrees(np.arccos(cosang))
    return {"flat_share": round(float((ang < 2).mean()), 4), "sharp_share": round(float((ang > 45).mean()), 4),
            "noise_deg": round(float(np.median(ang)), 2)}
