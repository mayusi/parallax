"""rbx_uvparts.py — UVs BY PART (3D crafts S2), for the high-and-low route's game mesh (rbx.Asset(low=...)).

The smart projection the kit used cut every island where a face turned more than 66 degrees and projected it flat:
the car rim's turned bands came out as rings with holes and as slices of a cylinder squashed at their sides, each of
the five identical spokes got a place of its own, and its maps held surface on 28% (barrel), 14% (lip) and 60%
(face). Game studios unwrap by what a part IS:

  - seams on every hard edge (over SEAM_ANGLE, 35: the low's hard edges and its UV splits are one set, Marmoset's rule),
    plus where a strip, a ring or a band has to be cut open; a CLOSED region (a lathe body whose every corner turns
    under the seam angle: chamfered) is opened at its sharpest edges first;
  - a TURNED band (a closed loop of faces round the part, not flat: a lathe's cylinder or cone) is cut across into
    straight STRIPS (no squashed sides), several when it would be too long for the map;
  - a flat face (a cap, a flange) is laid flat as it is, holes and all (the packer fills its holes);
  - IDENTICAL parts share one place (the rim's five spokes, its five threads): copies are found by their shape (a
    rigid turn of one another, vertex for vertex, the same materials and weight) on the faces as the CAD made them
    (rbx.py stashes them before it triangulates), left out of the pack and laid on their original's place after it;
    the bake writes the original only (the copies' UVs are moved off the map while it bakes); never with a stamp, a
    contact, a projection or a texture_from on the asset (those differ copy to copy);
  - an island the unwrap crushed (a tube flattened into the face it hangs from) is projected instead;
  - DENSITY BY WHAT IS SEEN, the builder's word only: `a.texel(part, factor)` (a barrel under a tyre: 0.5; a
    thread looked into: 2). How open each part is (the share of directions its faces see out in) is REPORTED, never
    used: as a weight it gave the rim's threaded lug holes half the texels and turned the threads to blobs (6ebz);
  - a part that brings its own layout (a.mesh(uvs=...): rbx_parts.thread's strips along its helix) keeps it.

    facts = unwrap(obj, tex, pad_px, weights={"Barrel": 0.5}, mm=280.0, others=[...], stack=True)

Pure numpy where it can be (coverage, copies, loops: kit/test/python/test_uvparts.py); bpy only to call Blender's
unwrap and packer.
"""

import math
import os
import time

import numpy as np

SEAM_ANGLE = 35.0      # degrees: an edge sharper than this is a seam AND a hard edge - the low's own smoothing angle
                       # (rbx.py _join): at 66 the low was smoothed across its 40-60 degree turns and the 8-bit normal
                       # map bent the light back by up to 45 degrees - rippled, stepped highlights on the rim's glossy
                       # lip and bore (rework 6ebz: gone with the normal map unlinked)
PLANAR_DEG = 1.5       # every face of a flat island within this of its mean normal
FILL = 0.7             # the map share the packer reaches with strips (sizes the strips' length)
STRIP_TRIES = (0.5, 0.35, 0.25, 0.2)   # a strip is cut in pieces no longer than this share of the packed square's
                                       # side: each tried with the fast box packer, the best TWO packed again by their
                                       # real shape, the fullest map kept (Blender's packer is not monotonic in it: the
                                       # rim's face map 58 / 58 / 65 / 66%, its barrel 78 / 80 / 69 / 80%)
SPREAD_MAX = 75.0      # degrees: a region that is neither flat nor turned whose faces turn further than this from
                       # its mean (a face with tubes hanging from it: the rim hub's seats and lug holes) is cut at
                       # its sharpest edges until it is not (_split_spread)
CRUSH_SHARE = 0.02     # an island with more than this share of its area under CRUSH_DENSITY x its own density ...
CRUSH_DENSITY = 0.5    # ... (or any triangle under a fifth of it) is projected instead (rbx_uvparts._crushed)
SEEN_RAYS = 48         # directions per face for "what is seen" (a hemisphere round its normal)
SEEN_FLOOR = 0.5       # seen_weight(): kept for a builder that asks for it - never applied by default (see above)
SEEN_OPEN = 0.5        # an island whose faces see out in this share of directions (or more) is fully open
SEEN_SHUT = 0.15       # ... and at this share (or fewer) gets SEEN_FLOOR
COPY_TOL = 1e-4        # a copy's vertices land within this share of the part's size of its original's
PACK_SHAPE = "CONCAVE"  # Blender's packer: islands by their real shape
PACK_ROTATE = "ANY"
LATHE_SPREAD = 1.35    # a turned band laid as straight strips when its largest radius is at most this x its smallest
                       # (its texels round the turn then vary by at most +-15%); a wider ring stays flat as it lies


# ---------------------------------------------------------------------------------------------------- pure numpy
def coverage(tris_uv, n):
    """(T, 3, 2) UV triangles -> the share of an n x n map's pixel centres they cover (overlaps once)"""
    tris_uv = np.asarray(tris_uv, np.float64)
    mask = np.zeros((n, n), bool)
    p = tris_uv * n
    for a, b, c in p:
        x0 = int(max(0, math.floor(min(a[0], b[0], c[0]))))
        x1 = int(min(n - 1, math.ceil(max(a[0], b[0], c[0]))))
        y0 = int(max(0, math.floor(min(a[1], b[1], c[1]))))
        y1 = int(min(n - 1, math.ceil(max(a[1], b[1], c[1]))))
        if x1 < x0 or y1 < y0:
            continue
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-14:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (1 - l1 - l2 >= -1e-9)
        mask[y0:y1 + 1, x0:x1 + 1] |= inside
    return float(mask.mean())


def kabsch(a, b):
    """the rigid turn + move taking points a (N, 3) onto b (N, 3) -> (R, t, worst distance); R is a proper turn
    (a mirror image is never a copy here: its normal map would turn the wrong way)"""
    ca, cb = a.mean(0), b.mean(0)
    h = (a - ca).T @ (b - cb)
    u, _s, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    r = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    t = cb - r @ ca
    err = float(np.linalg.norm(a @ r.T + t - b, axis=1).max()) if len(a) else 0.0
    return r, t, err


def copies(co, face_verts, face_part, face_mat=None):
    """IDENTICAL parts: co (V, 3), face_verts [tuple of vertex ids per face], face_part (F,), face_mat (F,) material
    slots -> {copy part: original part} for every part that is a proper rigid turn of an earlier one, vertex for
    vertex (same vertex order, same faces, the same materials on them): a part made by the same code at another angle
    (the rim's spokes) or a duplicate. Mirrors never."""
    co = np.asarray(co, np.float64)
    info = _part_info(face_verts, face_part, face_mat)
    out = {}
    order = sorted(info)
    for i, p in enumerate(order):
        if p in out:
            continue
        for q in order[i + 1:]:
            if q not in out and _same(co, info, q, p):
                out[q] = p
    return out


def keep_copies(co, face_verts, face_part, dup, face_mat=None):
    """the pairs of dup {copy part: original part} that are STILL copies on these faces (copies()' test, pair by pair):
    a triangulation or a clean-up that cut one differently drops it - it unwraps on its own, never laid on UVs that
    do not fit it"""
    co = np.asarray(co, np.float64)
    info = _part_info(face_verts, face_part, face_mat)
    return {q: p for q, p in dup.items() if q in info and p in info and _same(co, info, q, p)}


def _part_info(face_verts, face_part, face_mat):
    """{part: (its vertex ids sorted, its faces in those vertices' order - any face order, any start, each with its
    material)}"""
    face_part = np.asarray(face_part)
    face_mat = np.zeros(len(face_part), np.int64) if face_mat is None else np.asarray(face_mat)
    parts, mats = {}, {}
    for f, p, m_ in zip(face_verts, face_part.tolist(), face_mat.tolist()):
        parts.setdefault(p, []).append(f)
        mats.setdefault(p, []).append(int(m_))
    info = {}
    for p, fs in parts.items():
        vs = sorted({v for f in fs for v in f})
        local = {v: i for i, v in enumerate(vs)}
        shape = tuple(sorted((_cyclic(tuple(local[v] for v in f)), m_) for f, m_ in zip(fs, mats[p])))
        info[p] = (np.array(vs), shape)
    return info


def _same(co, info, q, p):
    """part q is a rigid turn of part p, vertex for vertex, face for face"""
    vp, sp = info[p]
    vq, sq = info[q]
    if len(vq) != len(vp) or sq != sp:
        return False
    size = float(np.ptp(co[vp], axis=0).max()) or 1.0
    return kabsch(co[vq], co[vp])[2] <= COPY_TOL * size


def triangulate_like(bm, dup, kp):
    """every n-gon (more than 4 corners) of bm (a bmesh) as triangles, BEAUTY - and each copy's (dup {copy part:
    original part}, as copies() found them on these very faces; kp: the kit_part face layer) cut along its ORIGINAL's
    diagonals, so a copy's triangles are its original's turned: the UVs laid from the original fit it, and its shading
    and bake match. BEAUTY picks diagonals by shape, and a turned copy's float noise flips its ties - the car rim's
    Spoke2 took 54 corners from other islands: a striped blotch (rework 6ebz). -> the copy parts it could not cut so
    (cut BEAUTY; the caller stops stacking them)"""
    import bmesh  # noqa: PLC0415

    big = [f for f in bm.faces if len(f.verts) > 4]
    if not big:
        return set()
    if not dup or kp is None:
        bmesh.ops.triangulate(bm, faces=big, quad_method="BEAUTY", ngon_method="BEAUTY")
        return set()
    # (a new layer first: adding one invalidates the faces fetched before it - and the kit_part layer re-fetched)
    name = kp.name
    src = bm.faces.layers.int.new("kit_tri_src")   # (each triangle remembers the n-gon it was cut from)
    kp = bm.faces.layers.int.get(name)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.faces.index_update()
    bm.verts.index_update()
    big = [f for f in bm.faces if len(f.verts) > 4]
    fverts = [tuple(v.index for v in f.verts) for f in bm.faces]
    fpart = np.array([f[kp] for f in bm.faces], np.int64)
    vmap = _vertex_maps(None, fverts, fpart, dup)
    for f in bm.faces:
        f[src] = f.index
    origs = set(dup.values())
    key_of = {(int(fpart[f.index]), frozenset(fverts[f.index])): f.index for f in big if int(fpart[f.index]) in origs}
    mine = [f for f in big if int(fpart[f.index]) in dup]
    bmesh.ops.triangulate(bm, faces=[f for f in big if int(fpart[f.index]) not in dup], quad_method="BEAUTY",
                          ngon_method="BEAUTY")
    want = set(key_of.values())
    tris = {}
    for f in bm.faces:
        if f[src] in want:
            tris.setdefault(f[src], []).append(tuple(v.index for v in f.verts))
    failed = set()
    for f in mine:
        q = int(f[kp])
        if q in failed or not f.is_valid:
            continue
        ring = fverts[f[src]]
        try:
            vm = vmap[q]
            i = key_of[(dup[q], frozenset(vm[v] for v in ring))]
            inv = {o: c for c, o in vm.items()}
            rim = {frozenset((ring[k], ring[(k + 1) % len(ring)])) for k in range(len(ring))}
            diag = []
            for t in tris[i]:
                t_ = [inv[o] for o in t]
                for k in range(3):
                    e = frozenset((t_[k], t_[(k + 1) % 3]))
                    if e not in rim and e not in diag:
                        diag.append(e)
            pieces = [f]
            for e in diag:
                a_, b_ = (bm.verts[v] for v in e)
                host = next((g for g in pieces if g.is_valid and a_ in g.verts and b_ in g.verts), None)
                made = bmesh.utils.face_split(host, a_, b_) if host is not None else None
                new_f = made[0] if isinstance(made, tuple) else made
                if new_f is None:
                    raise ValueError("no piece holds this diagonal")
                pieces.append(new_f)
            if any(len(g.verts) != 3 for g in pieces if g.is_valid):
                raise ValueError("not all triangles")
        except (KeyError, ValueError, RuntimeError, TypeError):
            failed.add(q)
    rest = [f for f in bm.faces if len(f.verts) > 4]   # (a failed copy's n-gons, any piece left over)
    if rest:
        bmesh.ops.triangulate(bm, faces=rest, quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.faces.layers.int.remove(src)
    return failed


def _cyclic(f):
    """a face's corners from its smallest one, its winding kept"""
    i = f.index(min(f))
    return f[i:] + f[:i]


def loops_of(edges):
    """boundary edges [(a, b)] -> closed loops [[v0, v1, ...]] (an open chain is returned as it is)"""
    nbr = {}
    for a, b in edges:
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    seen_e = set()
    out = []
    for a, b in edges:
        k = (min(a, b), max(a, b))
        if k in seen_e:
            continue
        seen_e.add(k)
        loop = [a, b]
        prev, cur = a, b
        while True:
            nxt = None
            for c in nbr.get(cur, ()):
                kk = (min(cur, c), max(cur, c))
                if kk not in seen_e:
                    nxt = c
                    seen_e.add(kk)
                    break
            if nxt is None or nxt == loop[0]:
                break
            loop.append(nxt)
            prev, cur = cur, nxt
        out.append(loop)
    return out


def circle3(pts):
    """points (N, 3) round a loop -> (centre, unit normal, radius, worst distance off the circle) or None"""
    pts = np.asarray(pts, np.float64)
    if len(pts) < 5:
        return None
    c0 = pts.mean(0)
    _u, _s, vt = np.linalg.svd(pts - c0)
    n = vt[2]
    e1, e2 = vt[0], vt[1]
    x, y = (pts - c0) @ e1, (pts - c0) @ e2
    a = np.stack([x, y, np.ones_like(x)], 1)
    sol, *_ = np.linalg.lstsq(a, x * x + y * y, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0))
    if r <= 0:
        return None
    off = np.abs(np.hypot(x - cx, y - cy) - r).max()
    plane = np.abs((pts - c0) @ n).max()
    return c0 + cx * e1 + cy * e2, n, r, float(max(off, plane))


def lathe_axis(loop_a, loop_b, tol):
    """two boundary loops' points -> (origin, unit axis) when both are circles round one axis (a turned band: a
    lathe's cylinder, cone or flat ring), else None"""
    ca, cb = circle3(loop_a), circle3(loop_b)
    if ca is None or cb is None or ca[3] > tol or cb[3] > tol:
        return None
    (pa, na, _ra, _), (pb, nb, _rb, _) = ca, cb
    if abs(float(na @ nb)) < 0.999:
        return None
    d = pb - pa
    if np.linalg.norm(d - (d @ na) * na) > tol:
        return None
    return pa, na


def polar(co, axis):
    """points (N, 3) -> (angle round the axis, radius from it)"""
    o, a = axis
    a = a / np.linalg.norm(a)
    e1 = np.cross(a, [1.0, 0.0, 0.0])
    if np.linalg.norm(e1) < 0.1:
        e1 = np.cross(a, [0.0, 1.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    d = np.asarray(co, np.float64) - o
    rad = d - (d @ a)[:, None] * a
    return np.arctan2(rad @ e2, rad @ e1), np.linalg.norm(rad, axis=1)


def lathe_rings(co, axis, ring_tol, edges=None, start=None):
    """vertices (N, 3) of a turned band and its axis -> (theta, r, z per vertex; ring_of: each vertex's ring or -1;
    order: the rings along the profile; pts: each ring's (r, z)), or None (fewer than two rings). A ring = the
    vertices sharing one radius and height (3 or more); the profile runs ring to ring along the mesh's own edges
    from the ring of `start` (by distance a profile that folds back near itself jumps across: the lip's front face
    beside its inner wall)"""
    o, a = axis
    a = a / np.linalg.norm(a)
    e1 = np.cross(a, [1.0, 0.0, 0.0])
    if np.linalg.norm(e1) < 0.1:
        e1 = np.cross(a, [0.0, 1.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    d = np.asarray(co, np.float64) - o
    z = d @ a
    rad = d - z[:, None] * a
    r = np.linalg.norm(rad, axis=1)
    th = np.arctan2(rad @ e2, rad @ e1)
    key = np.round(np.stack([r, z], 1) / ring_tol).astype(np.int64)
    rings = {}
    for i, k in enumerate(map(tuple, key)):
        rings.setdefault(k, []).append(i)
    big = [v for v in rings.values() if len(v) >= 3]
    if len(big) < 2:
        return None
    pts = np.array([[r[v].mean(), z[v].mean()] for v in big])
    ring_of = np.full(len(r), -1, np.int64)
    for k_, v in enumerate(big):
        ring_of[v] = k_
    order = None
    if edges is not None and start is not None and ring_of[start] >= 0:
        nbr = {}
        for a_, b_ in edges:
            ra, rb = ring_of[a_], ring_of[b_]
            if ra >= 0 and rb >= 0 and ra != rb:
                nbr.setdefault(ra, set()).add(rb)
                nbr.setdefault(rb, set()).add(ra)
        order = [int(ring_of[start])]
        while True:
            nxt = [q for q in nbr.get(order[-1], ()) if q not in order]
            if not nxt:
                break
            order.append(min(nxt, key=lambda q: float(np.linalg.norm(pts[q] - pts[order[-1]]))))
        if len(order) != len(big):
            order = None
    if order is None:   # (no edges given, or a profile that branches: nearest-next from the farthest ring)
        mid = pts.mean(0)
        order = [int(np.argmax(np.linalg.norm(pts - mid, axis=1)))]
        left = set(range(len(pts))) - set(order)
        while left:
            last = pts[order[-1]]
            nxt = min(left, key=lambda j: float(np.linalg.norm(pts[j] - last)))
            order.append(nxt)
            left.discard(nxt)
    return th, r, z, ring_of, order, pts


def best_split(radii):
    """the profile's ring radii in order -> the interior ring to cut a too-wide turned band at: the one leaving
    both sides' largest / smallest radius lowest (each side then a strip or a flat ring of its own)"""
    radii = np.asarray(radii, np.float64)
    best, at = None, None
    for k in range(1, len(radii) - 1):
        lo, hi = radii[:k + 1], radii[k:]
        worst = max(lo.max() / max(lo.min(), 1e-12), hi.max() / max(hi.min(), 1e-12))
        if best is None or worst < best - 1e-9:
            best, at = worst, k
    return at


def lathe_uv(co, axis, ring_tol, edges=None, start=None):
    """vertices (N, 3) of a turned band and its axis -> (theta (N,), s (N,), r (N,)): the angle round the axis, the
    length along the profile (lathe_rings' order) and the radius, or None"""
    got = lathe_rings(co, axis, ring_tol, edges, start)
    if got is None:
        return None
    th, r, z, _ring_of, order, pts = got
    poly = pts[order]
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    # every vertex's s: its nearest point on the profile polyline
    q = np.stack([r, z], 1)
    best = np.full(len(q), np.inf)
    s = np.zeros(len(q))
    for i in range(len(poly) - 1):
        p0, p1 = poly[i], poly[i + 1]
        dv = p1 - p0
        ll = float(dv @ dv)
        t = np.clip(((q - p0) @ dv) / ll, 0.0, 1.0) if ll > 0 else np.zeros(len(q))
        dist = np.linalg.norm(q - (p0 + t[:, None] * dv), axis=1)
        better = dist < best
        best[better] = dist[better]
        s[better] = cum[i] + t[better] * math.sqrt(ll)
    return th, s, r


def seen_weight(open_share):
    """the share of directions a face sees out in -> its island's density weight (SEEN_FLOOR .. 1)"""
    s = (float(open_share) - SEEN_SHUT) / max(SEEN_OPEN - SEEN_SHUT, 1e-9)
    return float(SEEN_FLOOR + (1.0 - SEEN_FLOOR) * min(1.0, max(0.0, s)))


def hemisphere(n=SEEN_RAYS):
    """n directions spread over the +z hemisphere (a Fibonacci spiral, cosine-weighted: what a surface sees)"""
    i = np.arange(n) + 0.5
    r = np.sqrt(i / n)
    phi = i * math.pi * (3.0 - math.sqrt(5.0))
    z = np.sqrt(np.maximum(0.0, 1.0 - r * r))
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], 1)


# ------------------------------------------------------------------------------------------------------- Blender
def _regions(bm, seam):
    """faces joined across every edge that is not a seam -> (F,) region id"""
    parent = list(range(len(bm.faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for e in bm.edges:
        if seam[e.index] or len(e.link_faces) != 2:
            continue
        a, b = (f.index for f in e.link_faces)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    roots = [find(i) for i in range(len(bm.faces))]
    ids = {r: k for k, r in enumerate(sorted(set(roots)))}
    return np.array([ids[r] for r in roots], np.int64)


def _shortest(bm, starts, goals, blocked):
    """Dijkstra over the mesh's edges from any vertex in starts to the nearest in goals, never along a blocked edge
    -> [edge index, ...] (empty: none)"""
    import heapq  # noqa: PLC0415

    goals = set(goals)
    dist = {v: 0.0 for v in starts}
    back = {}
    heap = [(0.0, v) for v in starts]
    heapq.heapify(heap)
    vs = bm.verts
    while heap:
        d, v = heapq.heappop(heap)
        if v in goals:
            path = []
            while v in back:
                v, e = back[v]
                path.append(e)
            return path
        if d > dist.get(v, 1e30):
            continue
        for e in vs[v].link_edges:
            if blocked(e):
                continue
            w = e.other_vert(vs[v]).index
            nd = d + e.calc_length()
            if nd < dist.get(w, 1e30):
                dist[w] = nd
                back[w] = (v, e.index)
                heapq.heappush(heap, (nd, w))
    return []


def _open_share(obj, faces, dirs, others=()):
    """the share of directions round each face's normal that see out past the object and everything else of the
    asset (others: its other meshes, world space) -> (F,)"""
    from mathutils import Vector  # noqa: PLC0415
    from mathutils.bvhtree import BVHTree  # noqa: PLC0415

    verts, polys = [], []
    for o in (obj, *others):
        mw = o.matrix_world
        base = len(verts)
        verts += [mw @ v.co for v in o.data.vertices]
        polys += [tuple(base + i for i in p.vertices) for p in o.data.polygons]
    tree = BVHTree.FromPolygons(verts, polys)
    mw = obj.matrix_world
    nm = mw.to_3x3().inverted_safe().transposed()
    size = max(obj.dimensions) or 1.0
    eps = 1e-4 * size
    out = np.ones(len(faces))
    for k, f in enumerate(faces):
        n = (nm @ f.normal).normalized()
        if n.length < 0.5:
            continue
        rot = Vector((0, 0, 1)).rotation_difference(n).to_matrix()
        c = mw @ (f.center if hasattr(f, "center") else f.calc_center_median()) + n * eps
        hits = 0
        for d in dirs:
            dv = rot @ Vector(d)
            if tree.ray_cast(c, dv, 4.0 * size)[0] is not None:
                hits += 1
        out[k] = 1.0 - hits / len(dirs)
    return out


def weight_of(weights, name):
    """a.texel's factor for a joined part name: its own, else the part it is a copy of ("Spoke~m1", "Spoke~r3" ->
    "Spoke": a copy takes its part's density - it did not, card nrey), else 1"""
    if name in weights:
        return weights[name]
    return weights.get(str(name).split("~")[0], 1.0)


def unwrap(obj, tex, pad_px, weights=None, mm=280.0, seam_angle=SEAM_ANGLE, others=(), stack=True):
    """UVs BY PART on obj (a joined group of the high-and-low route, OBJECT mode, kit_part face attribute + the
    kit_parts names; others: the asset's other meshes, for the "seen" report; stack=False: no copy shares a place)
    -> facts {"route", "flat", "strips", "bands", "patches", "fallback", "given", "cuts", "islands", "stacked", "use",
       "crushed" / "folded" (faces re-projected: an island the unwrap crushed, or laid over itself),
    "strip_max", "tries", "seconds", "parts": {name: {"tx_per_mm", "islands", "seen", "weight", "shares"}}}. The strips
    are cut at each STRIP_TRIES length and packed by their boxes (fast); the best two are packed again by their
    real shape, and the fullest map is kept."""
    import bmesh  # noqa: PLC0415
    import bpy  # noqa: PLC0415

    weights = dict(weights or {})
    ts = bpy.context.tool_settings
    was = (ts.use_uv_select_sync, tuple(ts.mesh_select_mode))
    t0 = time.time()
    try:
        me = obj.data
        names = [str(n) for n in (obj.get("kit_parts") or [])]
        if not me.uv_layers:
            me.uv_layers.new(name="UVMap")
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        kp0 = bm.faces.layers.int.get("kit_part")
        stash = obj.get("kit_copies")
        if not stack:
            dup = {}
        elif stash is not None:   # (found by rbx.py on the faces as the CAD made them, before it triangulated)
            flat = [int(x) for x in stash]
            dup = {flat[i]: flat[i + 1] for i in range(0, len(flat) - 1, 2)}
        else:
            dup = copies(np.array([v.co[:] for v in bm.verts], np.float64),
                         [tuple(v.index for v in f.verts) for f in bm.faces],
                         np.array([f[kp0] if kp0 is not None else 0 for f in bm.faces], np.int64),
                         [f.material_index for f in bm.faces])

        def name_of(p):
            return names[p] if p < len(names) else ""
        dup = {q: p for q, p in dup.items() if weight_of(weights, name_of(q)) == weight_of(weights, name_of(p))}
        # (a part that laid its own UVs - a.mesh(uvs=), placed seams - is never stacked on another or under one: a
        # copy takes its original's layout and drops its own; review 2026-11-17: a spoke's placed seams were replaced
        # by its twin's automatic strips)
        kg0 = bm.faces.layers.int.get("kit_uv_given")
        if kg0 is not None and kp0 is not None:
            own = {f[kp0] for f in bm.faces if f[kg0]}
            dup = {q: p for q, p in dup.items() if q not in own and p not in own}
        # every n-gon as its triangles (the same triangles the game mesh exports; rbx.py has done it already on the
        # high-and-low route): a flat ring merged into two half-circle n-gons cannot be laid along a strip. A copy is
        # cut like its original (triangulate_like), and every pair is checked again on the triangles: one that no
        # longer matches unwraps on its own
        failed = triangulate_like(bm, dup, kp0)
        dup = {q: p for q, p in dup.items() if q not in failed}
        bm.to_mesh(me)
        bm.free()
        me.update()
        if dup:
            n_ = len(me.vertices)
            co_ = np.empty(n_ * 3, np.float64)
            me.vertices.foreach_get("co", co_)
            fp_ = np.zeros(len(me.polygons), np.int64)
            if me.attributes.get("kit_part") is not None:
                me.attributes["kit_part"].data.foreach_get("value", fp_)
            mt_ = np.empty(len(me.polygons), np.int64)
            me.polygons.foreach_get("material_index", mt_)
            kept = keep_copies(co_.reshape(-1, 3), [tuple(p.vertices) for p in me.polygons], fp_, dup, mt_)
            dropped = sorted(name_of(q) for q in dup if q not in kept)
            dup = kept
        else:
            dropped = []
        dropped += [str(n) for n in (obj.get("kit_copies_dropped") or [])]   # (rbx.py's check after its clean-up)
        seen = _open_share(obj, list(me.polygons), hemisphere(), others)
        t_prep = round(time.time() - t0, 2)
        boxes = {}
        for sm in STRIP_TRIES:   # (ranked by the box packer: a hundredth of a second, where the shape packer takes 20)
            boxes[str(sm)] = _unwrap(obj, tex, pad_px, weights, mm, seam_angle, dup, sm, seen, "AABB")["use"]
        best, shaped = None, {}
        for sm in sorted(STRIP_TRIES, key=lambda x: -boxes[str(x)])[:2]:
            facts = _unwrap(obj, tex, pad_px, weights, mm, seam_angle, dup, sm, seen, PACK_SHAPE)
            shaped[str(sm)] = facts["use"]
            if best is None or facts["use"] > best[0]["use"] + 1e-4:
                n = len(me.loops)
                uv = np.empty(n * 2, np.float64)
                me.uv_layers.active.data.foreach_get("uv", uv)
                best = (facts, uv, sm)
        facts, uv, sm = best
        me.uv_layers.active.data.foreach_set("uv", uv)
        _seams_from_splits(me)   # (the mesh's seams = where its UVs split: copies' cuts, strips' closing edges too)
        for coll in (me.polygons, me.edges, me.vertices):   # (nothing left selected in the saved file)
            coll.foreach_set("select", [False] * len(coll))
        me.update()
        facts["strip_max"] = sm
        if dropped:   # (copies found on the n-gons whose triangles came out different: unwrapped on their own)
            facts["copies_dropped"] = dropped
        facts["tries"] = {"boxes": boxes, PACK_SHAPE.lower(): shaped}
        facts["seconds"] = {"prepare": t_prep, "all": round(time.time() - t0, 2)}
        return facts
    finally:
        ts.use_uv_select_sync, ts.mesh_select_mode = was[0], was[1]
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")


def _seams_from_splits(me):
    """every edge's seam flag = whether its two faces' UVs part there (or it is open)"""
    import bmesh  # noqa: PLC0415

    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    for e in bm.edges:
        if len(e.link_faces) != 2:
            e.seam = True
            continue
        fa, fb = e.link_faces
        split = False
        for v in e.verts:
            la = next(lp for lp in fa.loops if lp.vert == v)
            lb = next(lp for lp in fb.loops if lp.vert == v)
            if (la[uvl].uv - lb[uvl].uv).length > 1e-7:
                split = True
                break
        e.seam = split
    bm.to_mesh(me)
    bm.free()


FOLD_RES = 256   # a.k.a. the grid an island is checked on for lying over itself, its own box scaled to it


def _folded(me, mask):
    """the islands (of the faces in mask) that lie over THEMSELVES: each island on its own grid (rbx_uvcheck.overlap,
    its box scaled to FOLD_RES), a patch three cells wide under two of its faces -> (F,) bool. Its own faces only:
    islands placed on each other are the packer's to keep apart"""
    import bmesh  # noqa: PLC0415
    import rbx_uvcheck  # noqa: PLC0415

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    isl = _islands(bm, bm.loops.layers.uv.active)
    bm.free()
    mask = np.asarray(mask)
    out = np.zeros(len(mask), bool)
    if not len(me.polygons) or not me.uv_layers:
        return out
    me.calc_loop_triangles()
    uv = np.empty(len(me.loops) * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    start = np.empty(len(me.polygons), np.int64)
    total = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", start)
    me.polygons.foreach_get("loop_total", total)
    tri = np.array([t.loops for t in me.loop_triangles], np.int64).reshape(-1, 3)
    tp = np.array([t.polygon_index for t in me.loop_triangles], np.int64)
    for i in sorted(set(isl[mask].tolist())):
        polys = np.nonzero((isl == i) & mask)[0]
        if len(polys) < 4:
            continue
        loops = np.concatenate([np.arange(start[p], start[p] + total[p]) for p in polys])
        lo, hi = uv[loops].min(0), uv[loops].max(0)
        span = float(max(hi - lo))
        if span <= 0:
            continue
        others = np.ones(len(start), bool)
        others[polys] = False
        r = rbx_uvcheck.overlap(((uv - lo) / span).ravel(), start, total, tri, tp, res=FOLD_RES, meant=others)
        if r["texels"] > 0:
            out[polys] = True
    return out


def _crushed(me, mask):
    """the islands (of the faces in mask) the unwrap crushed: more than CRUSH_SHARE of their area under
    CRUSH_DENSITY x their own density, or a triangle under a fifth of it -> (F,) bool"""
    import bmesh  # noqa: PLC0415

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    isl = _islands(bm, bm.loops.layers.uv.active)
    bm.free()
    tri_uv, pidx, a3 = uv_tris(me)
    e1, e2 = tri_uv[:, 1] - tri_uv[:, 0], tri_uv[:, 2] - tri_uv[:, 0]
    a_uv = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    mask = np.asarray(mask)
    out = np.zeros(len(mask), bool)
    ti = isl[pidx]
    for i in set(ti[mask[pidx]].tolist()):
        sel = (ti == i) & mask[pidx]
        tot3, totuv = a3[sel].sum(), a_uv[sel].sum()
        if tot3 <= 0 or totuv <= 0:
            continue
        rel = np.sqrt((a_uv[sel] / totuv) / np.maximum(a3[sel] / tot3, 1e-30))
        low = a3[sel][rel < CRUSH_DENSITY].sum() / tot3
        if low > CRUSH_SHARE or rel.min() < 0.2:
            out[isl == i] = True
    return out & mask


def _unwrap(obj, tex, pad_px, weights, mm, seam_angle, dup, strip_max, seen, shape):
    """one try: seams, strips cut at strip_max of the packed square's side, Blender's unwrap, weights, the pack
    (`shape`: Blender's packer's shape method)"""
    import bmesh  # noqa: PLC0415
    import bpy  # noqa: PLC0415

    me = obj.data
    names = [str(n) for n in (obj.get("kit_parts") or [])]
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    kp = bm.faces.layers.int.get("kit_part")
    fpart = np.array([f[kp] if kp is not None else 0 for f in bm.faces], np.int64)
    co = np.array([v.co[:] for v in bm.verts], np.float64)
    fverts = [tuple(v.index for v in f.verts) for f in bm.faces]

    # 2. seams: every edge sharper than the angle, every open edge
    lim = math.radians(seam_angle)
    seam = np.zeros(len(bm.edges), bool)
    for e in bm.edges:
        if len(e.link_faces) != 2 or e.calc_face_angle(math.pi) > lim:
            seam[e.index] = True

    # 2a. where a part that laid its own UVs meets one that did not (welded, fused): a seam - a region is all of one or
    #     the other, so the given faces are never laid again with their neighbours (review 2026-11-17)
    kgb = bm.faces.layers.int.get("kit_uv_given")
    if kgb is not None:
        for e in bm.edges:
            lf = e.link_faces
            if len(lf) == 2 and bool(lf[0][kgb]) != bool(lf[1][kgb]):
                seam[e.index] = True

    # 2b. a TURNED region whose radius spreads too far (a flange's flat ring turned into its wall under 66 degrees):
    #     cut at the ring that leaves both sides narrowest, until each is a strip or a flat ring of its own
    size = float(np.ptp(co, axis=0).max()) or 1.0
    for _ in range(8):
        if not _split_wide(bm, seam, co, size):
            break
    # 2c. a CLOSED region (no boundary: a lathe body whose every corner turns under the seam angle - the rim's barrel
    #     and lip once their 90-degree corners were chamfered) is opened at its sharpest edges, then split as above
    for _ in range(6):
        if not _open_closed(bm, seam):
            break
        for _k in range(8):
            if not _split_wide(bm, seam, co, size):
                break
    # 2d. a region neither flat nor turned that faces every way (tubes hanging from a face: the unwrap crushed them
    #     into it) is cut at its sharpest edges until each piece is a strip, a flat face or a gentle patch
    kg_ = bm.faces.layers.int.get("kit_uv_given")
    given_ = np.array([bool(f[kg_]) for f in bm.faces]) if kg_ is not None else np.zeros(len(bm.faces), bool)
    for _ in range(6):
        if not _split_spread(bm, seam, co, size, given_):
            break

    # 3. islands of one surface each; a flat one stays as it is, a closed band is cut into strips
    reg = _regions(bm, seam)
    nreg = int(reg.max()) + 1 if len(reg) else 0
    area = np.array([f.calc_area() for f in bm.faces])
    nrm = np.array([f.normal[:] for f in bm.faces])
    total = float(sum(area[fpart == p].sum() for p in set(fpart.tolist()) if p not in dup))
    side = math.sqrt(max(total, 1e-12) / FILL)   # the packed square's side, in the mesh's units
    kinds = {"flat": 0, "strips": 0, "bands": 0, "patches": 0, "fallback": 0, "given": 0}
    cuts = 0
    fallback = np.zeros(len(bm.faces), bool)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    lathe = np.zeros(len(bm.faces), bool)
    kg = bm.faces.layers.int.get("kit_uv_given")   # (a part that laid its own UVs: kept, only scaled and packed)
    given = np.array([bool(f[kg]) for f in bm.faces]) if kg is not None else np.zeros(len(bm.faces), bool)
    lathe |= given
    for r in range(nreg):
        fs = np.nonzero(reg == r)[0]
        if fpart[fs[0]] in dup:
            continue   # (a copy: its original's UVs are laid on it)
        if given[fs].all():
            kinds["given"] += 1
            continue
        mean = (nrm[fs] * area[fs, None]).sum(0)
        mlen = float(np.linalg.norm(mean))
        flat = mlen > 1e-12 and (nrm[fs] @ (mean / mlen)).min() >= math.cos(math.radians(PLANAR_DEG))
        fset = set(fs.tolist())
        loops, genus = _region_loops(bm, fs)
        b = len(loops)
        if b >= 2 and genus == 0:   # a TURNED band (a lathe's cylinder, cone or narrow flat ring): straight strips
            k_ = _strips(bm, uvl, fs, loops, co, area, size, side * strip_max)
            if k_:
                k_, cut_ = k_
                lathe[fs] = True
                kinds["strips"] += 1
                cuts += k_
                for ei in cut_:
                    seam[ei] = True
                continue
        if flat:
            kinds["flat"] += 1
            continue
        if b == 0 or genus != 0:
            kinds["fallback"] += 1
            fallback[fs] = True
            continue
        if b == 1:
            kinds["patches"] += 1
            continue
        # a band (not turned): cut across between its two longest loops, in pieces no longer than strip_max x side
        def length(lp):
            return sum((bm.verts[lp[i]].co - bm.verts[lp[i - 1]].co).length for i in range(len(lp)))
        loops.sort(key=length, reverse=True)
        la, lb = loops[0], loops[1]
        circ = 0.5 * (length(la) + length(lb))
        k = max(1, int(math.ceil(circ / max(strip_max * side, 1e-9))))
        # k start points evenly along loop A (by length)
        acc = [0.0]
        for i in range(1, len(la)):
            acc.append(acc[-1] + (bm.verts[la[i]].co - bm.verts[la[i - 1]].co).length)
        tot = acc[-1] + (bm.verts[la[0]].co - bm.verts[la[-1]].co).length
        starts = []
        for j in range(k):
            want = j * tot / k
            starts.append(la[int(np.argmin([abs(a_ - want) for a_ in acc]))])
        starts = list(dict.fromkeys(starts))
        cut_edges = set()

        def blocked(e, fset=fset, cut_edges=cut_edges):
            if e.index in cut_edges or seam[e.index]:
                return True
            return not any(g.index in fset for g in e.link_faces)
        made = 0
        for s in starts:
            path = _shortest(bm, [s], lb, blocked)
            if path:
                cut_edges.update(path)
                made += 1
        for ei in cut_edges:
            seam[ei] = True
        cuts += made
        kinds["bands"] += 1

    # 4. Blender's unwrap on the seams (angle based: a band cut across unrolls straight, a flat face as it lies) —
    #    never on the turned strips (laid above) nor the copies (laid on their original below) — then the fallback
    #    faces by the smart projection, then every island at its real size
    for e in bm.edges:
        e.seam = bool(seam[e.index])
    bm.to_mesh(me)
    bm.free()
    copy_f = np.isin(fpart, list(dup)) if dup else np.zeros(len(fpart), bool)
    _edit_select(obj, ~fallback & ~lathe & ~copy_f)
    bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, margin=0.0)
    # 4b. an island the unwrap crushed (the rim's lug-hole walls flattened into the face round them: triangles at a
    #     hundredth of their island's density) is projected instead, with the fallback faces
    bpy.ops.object.mode_set(mode="OBJECT")
    bad = _crushed(me, ~fallback & ~lathe & ~copy_f)
    if bad.any():
        kinds["crushed"] = int(bad.sum())
        fallback |= bad
    # 4c. an island laid over ITSELF (a long band unrolled into a curve that coils back across itself: the karambit's
    #     screws, 1.05% of their map painted twice with no face flipped - card keak) is projected instead too
    folded = (_folded(me, ~fallback & ~lathe & ~copy_f) if os.environ.get("KIT_UV_FOLD", "1") != "0"
              else np.zeros(len(fallback), bool))   # (KIT_UV_FOLD=0: off - the test's way to see the fold it catches)
    if folded.any():
        kinds["folded"] = int(folded.sum())
        fallback |= folded
    if fallback.any():
        _edit_select(obj, fallback & ~copy_f)
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.001)
    _edit_select(obj, ~copy_f)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")

    # 5. density by what is seen (+ the builder's weight per part), island by island; copies take their original's
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    isl = _islands(bm, uvl)
    nisl = int(isl.max()) + 1 if len(isl) else 0
    fw = np.ones(len(fpart))   # the density weight each face's island got (seen x the builder's)
    for i in range(nisl):
        fs = np.nonzero(isl == i)[0]
        p = int(fpart[fs[0]])
        if p in dup:
            continue
        w = min(4.0, max(0.25, float(weight_of(weights, names[p] if p < len(names) else ""))))
        fw[fs] = w
        if abs(w - 1.0) < 1e-6:
            continue
        pts = [lp[uvl].uv for fi in fs for lp in bm.faces[fi].loops]
        cx = sum(u.x for u in pts) / len(pts)
        cy = sum(u.y for u in pts) / len(pts)
        for fi in fs:
            for lp in bm.faces[fi].loops:
                u = lp[uvl].uv
                lp[uvl].uv = (cx + (u.x - cx) * w, cy + (u.y - cy) * w)
    bm.to_mesh(me)
    bm.free()

    # 6. pack the originals' islands (a copy takes no room: it is laid on its original afterwards — one place)
    if dup:   # (the copies off the map while the originals pack: never in their way)
        _shift(me, copy_f, 10.0)
    _edit_select(obj, ~copy_f)
    _pack(pad_px / float(tex), shape)
    bpy.ops.object.mode_set(mode="OBJECT")
    missed = _lay_copies(me, co, fverts, fpart, dup) if dup else 0
    for q, p in dup.items():   # (a copy is drawn at its original's weight)
        fw[fpart == q] = float(np.average(fw[fpart == p], weights=area[fpart == p]))
    out = _facts(obj, tex, names, fpart, dup, kinds, cuts, seen, area, fw, mm, seam_angle)
    if missed:
        out["copy_corners_guessed"] = int(missed)
    return out


def _region_loops(bm, fs):
    """a region's faces -> (its boundary loops (3+ vertices), its genus: 0 = a disk or a band, -1 = closed)"""
    fset = set(int(f) for f in fs)
    border, inner, verts = [], set(), set()
    for fi in sorted(fset):   # (in face order: the loops' first vertex sets where a strip starts - kept stable)
        f = bm.faces[fi]
        for e in f.edges:
            if sum(1 for g in e.link_faces if g.index in fset) == 1:
                border.append((e.verts[0].index, e.verts[1].index))
            else:
                inner.add(e.index)
        verts.update(v.index for v in f.verts)
    loops = [lp for lp in loops_of(border) if len(lp) >= 3]
    chi = len(verts) - (len(inner) + len(border)) + len(fset)
    b = len(loops)
    return loops, ((2 - chi - b) // 2 if b else -1)


def _split_wide(bm, seam, co, size):
    """one pass: every turned region whose radius spreads past LATHE_SPREAD gets a seam round its best ring
    (best_split) -> True when a seam was added"""
    reg = _regions(bm, seam)
    added = False
    for r in range(int(reg.max()) + 1 if len(reg) else 0):
        fs = np.nonzero(reg == r)[0]
        loops, genus = _region_loops(bm, fs)
        if len(loops) < 2 or genus != 0:
            continue

        def length(lp):
            return sum(float(np.linalg.norm(co[lp[i]] - co[lp[i - 1]])) for i in range(len(lp)))
        loops.sort(key=length, reverse=True)
        ax = lathe_axis(co[loops[0]], co[loops[1]], 1e-3 * size)
        if ax is None:
            continue
        verts = sorted({v.index for fi in fs for v in bm.faces[fi].verts})
        vid = {v: i for i, v in enumerate(verts)}
        edges = {(vid[e.verts[0].index], vid[e.verts[1].index]) for fi in fs for e in bm.faces[fi].edges}
        got = lathe_rings(co[verts], ax, 1e-4 * size, edges=edges, start=vid[loops[0][0]])
        if got is None:
            continue
        _th, rv, _z, ring_of, order, pts = got
        if rv.min() <= 0 or rv.max() / rv.min() <= LATHE_SPREAD or len(order) < 3:
            continue
        k = best_split([pts[q][0] for q in order])
        if k is None:
            continue
        ring = order[k]
        for fi in fs:
            for e in bm.faces[fi].edges:
                a_, b_ = vid.get(e.verts[0].index), vid.get(e.verts[1].index)
                if a_ is not None and b_ is not None and ring_of[a_] == ring and ring_of[b_] == ring \
                        and not seam[e.index]:
                    seam[e.index] = True
                    added = True
    return added


def _open_closed(bm, seam):
    """one pass: every CLOSED region (no boundary, or with handles) gets seams on its sharpest edges (within 2 degrees
    of its sharpest; a smooth closed surface - under 5 degrees - is left to the smart projection) -> True when a seam
    was added"""
    reg = _regions(bm, seam)
    added = False
    for r in range(int(reg.max()) + 1 if len(reg) else 0):
        fs = np.nonzero(reg == r)[0]
        loops, genus = _region_loops(bm, fs)
        if loops and genus == 0:
            continue
        fset = set(fs.tolist())
        cand = []
        for fi in fs:
            for e in bm.faces[fi].edges:
                if seam[e.index] or len(e.link_faces) != 2:
                    continue
                if all(g.index in fset for g in e.link_faces):
                    cand.append((e.calc_face_angle(0.0), e.index))
        if not cand:
            continue
        top = max(a_ for a_, _ in cand)
        if top < math.radians(5):
            continue
        for a_, ei in cand:
            if a_ >= top - math.radians(2) and not seam[ei]:
                seam[ei] = True
                added = True
    return added


def _split_spread(bm, seam, co, size, given):
    """one pass: every region that is not flat, not a turned band and not a part's own layout, whose faces turn more
    than SPREAD_MAX from its mean normal, gets seams on its sharpest edges (within 2 degrees of its sharpest)
    -> True when a seam was added"""
    reg = _regions(bm, seam)
    added = False
    for r in range(int(reg.max()) + 1 if len(reg) else 0):
        fs = np.nonzero(reg == r)[0]
        if given[fs].any():
            continue
        nrm = np.array([bm.faces[fi].normal[:] for fi in fs])
        area = np.array([bm.faces[fi].calc_area() for fi in fs])
        mean = (nrm * area[:, None]).sum(0)
        ml = float(np.linalg.norm(mean))
        if ml < 1e-12:
            spread = 180.0
        else:
            spread = math.degrees(math.acos(max(-1.0, min(1.0, float((nrm @ (mean / ml)).min())))))
        if spread <= SPREAD_MAX:
            continue
        loops, genus = _region_loops(bm, fs)
        if len(loops) >= 2 and genus == 0:   # (a turned band within the spread: _strips lays it straight)
            def length(lp):
                return sum(float(np.linalg.norm(co[lp[i]] - co[lp[i - 1]])) for i in range(len(lp)))
            ls = sorted(loops, key=length, reverse=True)
            ax = lathe_axis(co[ls[0]], co[ls[1]], 1e-3 * size)
            if ax is not None:
                _th, rv = polar(co[sorted({v.index for fi in fs for v in bm.faces[fi].verts})], ax)
                if rv.min() > 0 and rv.max() / rv.min() <= LATHE_SPREAD:
                    continue
        fset = set(fs.tolist())
        cand = []
        for fi in fs:
            for e in bm.faces[fi].edges:
                if seam[e.index] or len(e.link_faces) != 2:
                    continue
                if all(g.index in fset for g in e.link_faces):
                    cand.append((e.calc_face_angle(0.0), e.index))
        if not cand:
            continue
        top = max(a_ for a_, _ in cand)
        if top < math.radians(5):
            continue
        for a_, ei in cand:
            if a_ >= top - math.radians(2) and not seam[ei]:
                seam[ei] = True
                added = True
    return added


def _strips(bm, uvl, fs, loops, co, area, size, longest):
    """a band whose two longest loops are circles round one axis, its radius spread at most LATHE_SPREAD: every face
    of it laid as k straight strips (u = the angle x its mean radius, v = the length along the profile), each a
    piece of the turn no longer than `longest` (mesh units), cut along a column of its vertices
    -> (k, the edges where two pieces meet), or 0 (not a turned band: left to the other routes)"""
    def length(lp):
        return sum(float(np.linalg.norm(co[lp[i]] - co[lp[i - 1]])) for i in range(len(lp)))
    loops = sorted(loops, key=length, reverse=True)
    la, lb = loops[0], loops[1]
    ax = lathe_axis(co[la], co[lb], 1e-3 * size)
    if ax is None:
        return 0
    verts = sorted({v.index for fi in fs for v in bm.faces[fi].verts})
    vid = {v: i for i, v in enumerate(verts)}
    edges = {(vid[e.verts[0].index], vid[e.verts[1].index]) for fi in fs for e in bm.faces[fi].edges}
    got = lathe_uv(co[verts], ax, 1e-4 * size, edges=edges, start=vid[la[0]])
    if got is None:
        return 0
    th, sv, rv = got
    if rv.min() <= 0 or rv.max() / rv.min() > LATHE_SPREAD:
        return 0
    cen = np.array([np.mean([co[v.index] for v in bm.faces[fi].verts], 0) for fi in fs])
    fth, rf = polar(cen, ax)
    rref = float((rf * area[fs]).sum() / max(area[fs].sum(), 1e-12))
    k = max(1, int(math.ceil(2 * math.pi * rref / max(longest, 1e-9))))
    th0 = float(th[vid[la[0]]])
    col = np.sort(np.mod(th[[vid[v] for v in la]] - th0, 2 * math.pi))   # loop A's columns (relative angles)
    bounds = [0.0]
    for j in range(1, k):
        want = j * 2 * math.pi / k
        bounds.append(float(col[int(np.argmin(np.abs(col - want)))]))
    bounds = sorted(set(bounds)) + [2 * math.pi]
    signed = 0.0
    placed = []
    piece = {}
    for n_, fi in enumerate(fs):
        f = bm.faces[fi]
        rel = float(np.mod(fth[n_] - th0, 2 * math.pi))
        j = max(i for i in range(len(bounds) - 1) if bounds[i] <= rel + 1e-9)
        piece[fi] = j
        uvs = []
        for lp in f.loops:
            i = vid[lp.vert.index]
            dth = (th[i] - fth[n_] + math.pi) % (2 * math.pi) - math.pi
            uvs.append(((rel + dth - bounds[j]) * rref, float(sv[i])))
        placed.append((f, uvs))
        for q in range(1, len(uvs) - 1):
            (x0, y0), (x1, y1), (x2, y2) = uvs[0], uvs[q], uvs[q + 1]
            signed += (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
    flip = signed < 0   # (never a mirrored island: its normal map would turn the wrong way)
    for f, uvs in placed:
        for lp, (u, v) in zip(f.loops, uvs):
            lp[uvl].uv = (-u if flip else u, v)
    cut = set()   # (where two pieces meet: a seam)
    for fi, j in piece.items():
        for e in bm.faces[fi].edges:
            if len(e.link_faces) == 2:
                g = [x.index for x in e.link_faces if x.index != fi][0]
                if g in piece and piece[g] != j:
                    cut.add(e.index)
    return len(bounds) - 1, cut


def _edit_select(obj, mask):
    """obj in EDIT mode, FACE select mode, exactly the faces in mask selected (and all their UVs)"""
    import bmesh  # noqa: PLC0415
    import bpy  # noqa: PLC0415

    if bpy.context.object is not obj or obj.mode != "EDIT":
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    # UV sync selection ON: every UV operator then acts on exactly the selected faces (Blender 5.2's default; with
    # it off, uv.select_all would have to pick the UVs too). Never uv.select_all with it on: that selects the MESH,
    # all of it (the copies and the strips were unwrapped again over their own UVs)
    bpy.context.tool_settings.use_uv_select_sync = True
    bm = bmesh.from_edit_mesh(obj.data)
    bm.select_mode = {"FACE"}
    bm.faces.index_update()   # (an edit mesh's indices can be stale: f.index = the mesh polygon's, as mask is)
    bm.faces.ensure_lookup_table()
    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = bool(mask[f.index])
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)


def _shift(me, mask, du):
    """every corner of the faces in mask moved du along U (off the map and back: a copy while the bake runs)"""
    n = len(me.loops)
    uv = np.empty(n * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    starts = np.empty(len(me.polygons), np.int64)
    totals = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    sel = np.nonzero(np.asarray(mask))[0]
    if len(sel):
        idx = np.concatenate([np.arange(starts[i], starts[i] + totals[i]) for i in sel])
        uv[idx, 0] += du
    me.uv_layers.active.data.foreach_set("uv", uv.ravel())


def _pack(margin, shape):
    """Blender's packer on the selected islands: by `shape` (CONCAVE: their real shape; AABB: their boxes), any
    rotation, a pad round each"""
    import bpy  # noqa: PLC0415

    bpy.ops.uv.pack_islands(rotate=True, rotate_method=PACK_ROTATE, scale=True, merge_overlap=False,
                            margin_method="FRACTION", margin=margin, shape_method=shape)


def _lay_copies(me, co, fverts, fpart, dup):
    """every corner of a copy takes its original's UV at the matching vertex (copies() matched them in order), in
    the island of the original's face that lies under this face (a vertex on a seam has a UV in each island; two
    copies' n-gons can split into other triangles, so faces are matched by where they lie, not by their vertices)"""
    import bmesh  # noqa: PLC0415
    from mathutils import Vector  # noqa: PLC0415
    from mathutils.bvhtree import BVHTree  # noqa: PLC0415

    vmap = _vertex_maps(co, fverts, fpart, dup)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    isl = _islands(bm, uvl)
    fp = np.asarray(fpart)
    store = {}   # original's vertex -> {island: uv}
    near = {}    # original's vertex -> [(its face's centre, uv)]: the fallback
    trees = {}
    exact = {}   # (original part, a face's corners) -> that face: a copy cut like its original finds its very face
    for p in set(dup.values()):
        own = [f for f in bm.faces if fp[f.index] == p]
        trees[p] = (BVHTree.FromPolygons([v.co for v in bm.verts], [tuple(v.index for v in f.verts) for f in own]),
                    [f.index for f in own])
        for f in own:
            exact[(p, frozenset(v.index for v in f.verts))] = f.index
            c_ = np.mean([v.co[:] for v in f.verts], 0)
            for lp in f.loops:
                store.setdefault(lp.vert.index, {})[int(isl[f.index])] = lp[uvl].uv.copy()
                near.setdefault(lp.vert.index, []).append((c_, lp[uvl].uv.copy()))
    missed = 0
    for q, p in dup.items():
        vq = sorted(vmap[q])
        r, t, _err = kabsch(co[vq], co[[vmap[q][v] for v in vq]])
        tree, own = trees[p]
        for f in bm.faces:
            if fp[f.index] != q:
                continue
            c = r @ np.mean([v.co[:] for v in f.verts], 0) + t
            j = exact.get((p, frozenset(vmap[q].get(v.index, -1) for v in f.verts)))
            if j is not None:
                i = int(isl[j])
            else:   # (the face under it: a copy whose n-gons were cut otherwise - keep_copies normally drops those)
                hit = tree.find_nearest(Vector(c.tolist()))
                if hit[2] is None:
                    continue
                i = int(isl[own[hit[2]]])
            for lp in f.loops:
                m_ = vmap[q][lp.vert.index]
                uv = store.get(m_, {}).get(i)
                if uv is None:   # (never seen on the rim: a corner outside the island under it - nearest face)
                    missed += 1
                    opts = near.get(m_)
                    if opts:
                        uv = min(opts, key=lambda o: float(np.linalg.norm(o[0] - c)))[1]
                if uv is not None:
                    lp[uvl].uv = uv
    bm.to_mesh(me)
    bm.free()
    return missed


def uv_tris(me):
    """the mesh's UV triangles (Blender's own triangulation) -> (T, 3, 2) uv, (T,) polygon index, (T,) 3D area"""
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    lidx = np.empty(nt * 3, np.int64)
    vidx = np.empty(nt * 3, np.int64)
    pidx = np.empty(nt, np.int64)
    me.loop_triangles.foreach_get("loops", lidx)
    me.loop_triangles.foreach_get("vertices", vidx)
    me.loop_triangles.foreach_get("polygon_index", pidx)
    uv = np.empty(len(me.loops) * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    pt = co.reshape(-1, 3)[vidx.reshape(-1, 3)]
    a3 = np.linalg.norm(np.cross(pt[:, 1] - pt[:, 0], pt[:, 2] - pt[:, 0]), axis=1) / 2
    return uv.reshape(-1, 2)[lidx.reshape(-1, 3)], pidx, a3


def _facts(obj, tex, names, fpart, dup, kinds, cuts, seen, area, fw, mm, seam_angle):
    import bmesh  # noqa: PLC0415

    me = obj.data
    tri_uv, pidx, a3 = uv_tris(me)
    e1, e2 = tri_uv[:, 1] - tri_uv[:, 0], tri_uv[:, 2] - tri_uv[:, 0]
    a_uv = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    a_mm = a3 * mm * mm
    dens = np.sqrt(a_uv * tex * tex / np.maximum(a_mm, 1e-12))
    tpart = fpart[pidx]
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    isl = _islands(bm, bm.loops.layers.uv.active)
    bm.free()
    parts = {}
    for p in sorted(set(fpart.tolist())):
        sel = tpart == p
        d, w = dens[sel], a_mm[sel]
        order = np.argsort(d)
        cum = np.cumsum(w[order]) / max(w.sum(), 1e-12)
        med = float(d[order][min(len(d) - 1, int(np.searchsorted(cum, 0.5)))]) if len(d) else 0.0
        fs = fpart == p
        name = names[p] if p < len(names) else str(p)
        parts[name] = {"tx_per_mm": round(med, 3), "islands": int(len(set(isl[fs].tolist()))),
                       "seen": round(float((seen[fs] * area[fs]).sum() / max(area[fs].sum(), 1e-12)), 3),
                       "weight": round(float(np.average(fw[fs], weights=area[fs])), 3),
                       **({"shares": names[dup[p]] if dup[p] < len(names) else str(dup[p])} if p in dup else {})}
    own = ~np.isin(fpart, list(dup)) if dup else np.ones(len(fpart), bool)
    return {"route": "by part", "seam_angle": float(seam_angle), **kinds, "cuts": int(cuts),
            "islands": int(len(set(isl[own].tolist()))), "stacked": len(dup),
            "use": round(coverage(tri_uv, int(tex)), 3), "parts": parts, "copy_ids": sorted(int(q) for q in dup)}


def _islands(bm, uvl):
    """faces joined where an edge's two corners carry the same UVs on both sides -> (F,) island id"""
    parent = list(range(len(bm.faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        fa, fb = e.link_faces
        same = True
        for v in e.verts:
            la = next(lp for lp in fa.loops if lp.vert == v)
            lb = next(lp for lp in fb.loops if lp.vert == v)
            if (la[uvl].uv - lb[uvl].uv).length > 1e-7:
                same = False
                break
        if same:
            ra, rb = find(fa.index), find(fb.index)
            if ra != rb:
                parent[ra] = rb
    roots = [find(i) for i in range(len(bm.faces))]
    ids = {r: k for k, r in enumerate(sorted(set(roots)))}
    return np.array([ids[r] for r in roots], np.int64)


def _vertex_maps(co, fverts, fpart, dup):
    """{copy part: {its vertex: the original's vertex}} by order (copies() matched them so)"""
    parts = {}
    for f, p in zip(fverts, np.asarray(fpart).tolist()):
        parts.setdefault(p, set()).update(f)
    out = {}
    for q, p in dup.items():
        vq, vp = sorted(parts[q]), sorted(parts[p])
        out[q] = dict(zip(vq, vp))
    return out


def match_density(me, mask):
    """the islands of the faces in `mask` scaled, each about its own middle, to the texel density of the faces NOT
    in it (their area-weighted median of map area over surface area) - the rest of the map untouched. A mesh whose
    faces are all in mask: every island to their own median (as average_islands_scale would) -> islands scaled"""
    import bmesh  # noqa: PLC0415

    mask = np.asarray(mask, bool)
    if not mask.any() or not me.uv_layers:
        return 0
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    isl = _islands(bm, uvl)
    a3 = np.array([f.calc_area() for f in bm.faces])
    auv = np.zeros(len(bm.faces))
    for f in bm.faces:
        u = [lp[uvl].uv for lp in f.loops]
        s_ = 0.0
        for i in range(1, len(u) - 1):
            s_ += (u[i].x - u[0].x) * (u[i + 1].y - u[0].y) - (u[i].y - u[0].y) * (u[i + 1].x - u[0].x)
        auv[f.index] = abs(s_) / 2
    ref = ~mask if (~mask).any() else mask
    good = ref & (a3 > 0) & (auv > 0)
    if not good.any():
        bm.free()
        return 0
    dens = np.sqrt(auv[good] / a3[good])
    order = np.argsort(dens)
    cum = np.cumsum(a3[good][order])
    target = float(dens[order][int(np.searchsorted(cum, cum[-1] / 2))])
    done = 0
    for i in sorted(set(isl[mask].tolist())):
        fs = np.nonzero((isl == i) & mask)[0]
        tot3, totuv = float(a3[fs].sum()), float(auv[fs].sum())
        if tot3 <= 0 or totuv <= 0:
            continue
        k = target / np.sqrt(totuv / tot3)
        loops = [lp for f in fs for lp in bm.faces[int(f)].loops]
        c = sum((lp[uvl].uv for lp in loops), loops[0][uvl].uv * 0) / len(loops)
        for lp in loops:
            lp[uvl].uv = c + (lp[uvl].uv - c) * k
        done += 1
    bm.to_mesh(me)
    bm.free()
    return done
