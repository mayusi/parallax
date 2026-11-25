"""rbx_pillow.py — the INFLATE route for sculpted plate parts (a game gun's frame, grips, hammer, trigger; an ornate
housing): a traced outline (holes too) made a solid whose SIDES ARE CONVEX — each face rises off the outline on a
quarter ellipse `edge` mm wide and `h` mm high (vertical where it leaves the side wall, level where it ends) and
crowns `top` mm more toward the middle — so there is no flat slab face and no box edge anywhere, and the side-view
silhouette is exactly the outline. The owner, 2026-10-23: the jewel housing, grips, handle and frame "still have the
straightest edges ON human history ... do not confuse smooth shading with smooth geometry": a fillet on a slab is
still a slab (flat faces, square shoulders); this is the shape itself. (cad_parts.dome did it with OpenCASCADE
offsets + a loft and failed on real traced outlines: offsets that split or vanish in a thin spot, lofts between
wires with different edges — the height here comes from the DISTANCE to the outline, which never fails.)

    bm = pillow_mesh(outline_mm, holes_mm, core_mm, h_mm, edge_mm, top_mm=0.0, side="both", mm=280.0)

The geometry, not the shading: rings of vertices at the profile's own angles (every `rim_deg` of the quarter turn)
follow the outline inward, a grid fills the middle, all triangulated with the outline and holes as constraints; each
vertex's height from its distance to the nearest outline (a part thinner than 2 x edge gets a round top, its ridge
smoothed — never a crease down its middle). side="both": the core is 2 x core_mm thick, a dome on each face (+-Z);
"+" / "-": one dome on that face, the other face flat (a grip panel on the frame). Returns a bmesh in studs.
"""

import math

import bmesh
import numpy as np
from mathutils import Vector
from mathutils import geometry as G
from mathutils.kdtree import KDTree



def _resample(loop, step, corner_deg=35.0):
    """a closed outline at even spacing ~step (N, 2), every corner (a turn over corner_deg) kept as a sample"""
    p = np.asarray([(float(q[0]), float(q[1])) for q in loop], float)
    if len(p) > 2 and np.linalg.norm(p[0] - p[-1]) < 1e-6:
        p = p[:-1]
    a, b = p - np.roll(p, 1, 0), np.roll(p, -1, 0) - p
    turn = np.degrees(np.abs(np.arctan2(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0], (a * b).sum(1))))
    cs = list(np.nonzero(turn > corner_deg)[0]) or [0]
    out = []
    for k, c in enumerate(cs):
        nxt = cs[(k + 1) % len(cs)]
        idx = np.arange(c, (nxt if nxt > c else nxt + len(p)) + 1) % len(p)
        run = p[idx]
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(run, axis=0), axis=1))])
        m = max(1, int(round(cum[-1] / step)))
        t = np.linspace(0.0, cum[-1], m, endpoint=False)
        out.append(np.column_stack([np.interp(t, cum, run[:, 0]), np.interp(t, cum, run[:, 1])]))
    return np.concatenate(out)


def self_crossings(loop):
    """how many times a closed outline crosses itself (segments that are not neighbours) — a redraw that does is
    refused: Scarborough Fair's thin gold arc redrawn crossed itself 3 times and came out with 186 open edges"""
    P = np.asarray([(float(q[0]), float(q[1])) for q in loop], float)
    n = len(P)
    if n < 4:
        return 0
    A, B = P, np.roll(P, -1, 0)
    d = B - A
    cnt = 0
    for i in range(n - 2):
        j = np.arange(i + 2, n if i > 0 else n - 1)
        if not len(j):
            continue
        r, sv = d[i], d[j]
        den = r[0] * sv[:, 1] - r[1] * sv[:, 0]
        ok = np.abs(den) > 1e-12
        qp = A[j] - A[i]
        t = np.where(ok, (qp[:, 0] * sv[:, 1] - qp[:, 1] * sv[:, 0]) / np.where(ok, den, 1), -1)
        u = np.where(ok, (qp[:, 0] * r[1] - qp[:, 1] * r[0]) / np.where(ok, den, 1), -1)
        cnt += int(np.count_nonzero((t > 0) & (t < 1) & (u > 0) & (u < 1)))
    return cnt


def _area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _inside(pts, loop):
    """even-odd point-in-polygon for many points (N, 2) against one closed loop (M, 2)"""
    x, y = pts[:, 0][:, None], pts[:, 1][:, None]
    ax, ay = loop[:, 0][None, :], loop[:, 1][None, :]
    bx, by = np.roll(loop[:, 0], -1)[None, :], np.roll(loop[:, 1], -1)[None, :]
    crosses = ((ay > y) != (by > y)) & (x < (bx - ax) * (y - ay) / np.where(by == ay, 1e-12, by - ay) + ax)
    return (np.count_nonzero(crosses, axis=1) % 2) == 1


def _material(pts, outer, holes):
    """inside the outline and outside every hole (chunked: the frame's ~40k points x ~1k-point loops)"""
    out = np.zeros(len(pts), bool)
    for s in range(0, len(pts), 4096):
        q = pts[s:s + 4096]
        m = _inside(q, outer)
        for h in holes:
            m &= ~_inside(q, h)
        out[s:s + 4096] = m
    return out


def _tree(pts):
    t = KDTree(len(pts))
    for i, p in enumerate(pts):
        t.insert((float(p[0]), float(p[1]), 0.0), i)
    t.balance()
    return t


def _dist(tree, pts):
    return np.array([tree.find((float(p[0]), float(p[1]), 0.0))[2] for p in pts])


def profile(d, core, h, edge, top, dmax):
    """height over the core at distance d from the outline: a quarter ellipse edge wide x h high (sin of the angle
    whose 1 - cos is d / edge), then a smoothstep crown of `top` toward the deepest point (dmax)"""
    t = np.clip(d / max(edge, 1e-6), 0.0, 1.0)
    z = core + h * np.sqrt(np.clip(1.0 - (1.0 - t) ** 2, 0.0, 1.0))
    if top > 0 and dmax > edge * 1.05:
        c = np.clip((d - edge) / (dmax - edge), 0.0, 1.0)
        z = z + top * c * c * (3.0 - 2.0 * c)
    return z


def core_map(pts, core, zones):
    """the core (half-thickness under the dome, mm) at each point: `core`, or a ZONE's own where a point lies in its
    outline — blended over the zone's `blend` mm across its edge (smoothstep of the signed distance: no step face) —
    the last zone naming a point wins. zones: [{"outline": [(x, y), ...], "core": c, "blend": 2.0}]"""
    c = np.full(len(pts), float(core))
    for z in zones or ():
        loop = _resample(z["outline"], 0.25, corner_deg=181.0)
        inside = _inside(pts, loop)
        dist = _dist(_tree(loop), pts)
        b = max(1e-3, float(z.get("blend", 2.0)))
        t = np.clip((np.where(inside, dist, -dist) + b) / (2 * b), 0.0, 1.0)
        w = t * t * (3 - 2 * t)
        c = c * (1 - w) + float(z["core"]) * w
    return c


def pillow_mesh(outline, holes=(), core=1.0, h=2.0, edge=2.0, top=0.0, side="both", mm=280.0, step=None,
                rim_deg=7.5, smooth=24, zones=()):
    if side not in ("both", "+", "-"):
        raise ValueError(f'pillow: side="{side}" — "both", "+" or "-"')
    if h <= 0 or edge <= 0 or core < 0 or any(float(z_["core"]) < 0 for z_ in zones or ()):
        raise ValueError(f"pillow: h={h} and edge={edge} must be > 0, core={core} >= 0")
    step = float(step or max(0.35, min(0.6, edge / 4.0)))   # (along the outline: its own curves, not the rim's)
    loops = [_resample(outline, step)]
    for hl in holes or ():
        loops.append(_resample(hl, step))
    for k, lp in enumerate(loops):   # outer counter-clockwise, holes clockwise (the walls' winding below)
        if (_area(lp) > 0) != (k == 0):
            loops[k] = lp[::-1].copy()
    outer, hls = loops[0], loops[1:]
    bnd = np.concatenate(loops)
    # the distance field: a dense sampling of every loop (step / 4) in a KD tree
    dense = np.concatenate([_resample(lp, step / 4.0, corner_deg=181.0)
                            for lp in loops])
    tree = _tree(dense)
    # RINGS at the profile's own angles: each outline sample moved inward d_k along its normal, kept only where its
    # true distance to the outline is d_k (past the middle of a thin spot it is not), thinned where rings bunch up
    # (inside a concave corner)
    n_rim = max(4, min(int(round(90.0 / rim_deg)), int(round(edge / 0.12))))   # (a 1 mm rim needs fewer rings)
    ring_d = [edge * (1.0 - math.cos(math.radians(90.0 * k / n_rim))) for k in range(1, n_rim + 1)]
    normals = []
    for lp in loops:
        tng = np.roll(lp, -1, 0) - np.roll(lp, 1, 0)
        tng /= np.maximum(np.linalg.norm(tng, axis=1), 1e-12)[:, None]
        normals.append(np.stack([-tng[:, 1], tng[:, 0]], 1))   # (left of the walk: inward for ccw outer + cw holes)
    nrm = np.concatenate(normals)
    pts = [bnd]
    for dk in ring_d:
        cand = bnd + nrm * dk
        ok = _material(cand, outer, hls)
        cand = cand[ok]
        if not len(cand):
            break
        dd = _dist(tree, cand)
        cand = cand[np.abs(dd - dk) <= 0.2 * dk + 0.02]
        keep = _thin(cand, 0.45 * step)
        if keep:
            pts.append(np.asarray(keep))
    # the MIDDLE: a triangular grid (finer where the part is thin), kept clear of the rings
    lo, hi = bnd.min(0), bnd.max(0)
    have = np.concatenate(pts)
    near = _tree(have)
    inner = max(step, 1.2 if top <= 0 else min(1.2, max(0.5, edge / 4.0)))   # (a flat middle needs no fine grid; a crowned one
    #                                                         keeps its curve)
    for sp, beyond in ((inner, edge), (step, 0.0)):
        ys = np.arange(lo[1], hi[1] + sp, sp * math.sqrt(3) / 2)
        grid = np.array([(x + (0.5 * sp if j % 2 else 0.0), y) for j, y in enumerate(ys)
                         for x in np.arange(lo[0], hi[0] + sp, sp)])
        grid = grid[_material(grid, outer, hls)]
        if not len(grid):
            continue
        dd = _dist(tree, grid)
        fine = sp < inner   # (the fine pass only fills GAPS the rings and the middle grid left — a thin part's
        #                    ridge — never the whole middle again: a jewel boss came out 120k faces a side)
        grid = grid[(dd > max(beyond, ring_d[0]) + 0.5 * sp) & ((dd < edge + inner) if fine else True)]
        if not len(grid):
            continue
        gap = _dist(near, grid)
        grid = grid[gap > 0.5 * (inner if fine else sp)]
        if len(grid):
            pts.append(grid)
            have = np.concatenate(pts)
            near = _tree(have)
    allp = np.concatenate(pts)
    nb = len(bnd)
    edges, start = [], 0
    for lp in loops:
        n = len(lp)
        edges += [(start + i, start + (i + 1) % n) for i in range(n)]
        start += n
    vin = [Vector((float(x), float(y))) for x, y in allp]
    out = G.delaunay_2d_cdt(vin, edges, [], 0, 1e-5)
    ov, of, orig = np.array([(v.x, v.y) for v in out[0]]), out[2], out[3]
    # each output vertex: which outline sample it is (the walls), its distance -> its height
    bidx = {}
    for o, ids in enumerate(orig):
        for i in ids:
            if i < nb:
                bidx[i] = o
    if len(bidx) < nb or len(set(bidx.values())) < nb:
        raise RuntimeError(f"pillow: the triangulation merged outline samples ({len(set(bidx.values()))} of {nb} "
                           "kept) — a self-touching outline?")
    of = _inside_faces(of, ov, {(bidx[a_], bidx[b_]) for a_, b_ in edges}, outer, hls)
    is_b = np.zeros(len(ov), bool)
    is_b[list(bidx.values())] = True
    d = _dist(tree, ov)
    d[is_b] = 0.0
    z = profile(d, 0.0, h, edge, top, float(d.max()))
    # a thin part's RIDGE (no flat top: two rims meet) — smoothed, the rims and the outline held
    if smooth:
        nbr = [[] for _ in ov]
        for f in of:
            for a_, b_ in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                nbr[a_].append(b_)
                nbr[b_].append(a_)
        tt = np.clip((d / edge - 0.35) / 0.5, 0.0, 1.0)
        alpha = tt * tt * (3 - 2 * tt)
        alpha[is_b] = 0.0
        act = np.nonzero(alpha > 0)[0]
        for _ in range(int(smooth)):
            zn = z.copy()
            for i in act:
                zn[i] = (1 - alpha[i]) * z[i] + alpha[i] * z[nbr[i]].mean()
            z = zn
    bm = bmesh.new()
    s = 1.0 / float(mm)
    sides = {"both": (1, -1), "+": (1,), "-": (-1,)}[side]
    cv = core_map(ov, core, zones)   # (per vertex: a zone thickens or thins the part where it lies)
    sheets = {}
    for sg in sides:
        vs = [bm.verts.new((x * s, y * s, sg * (cc + zz) * s)) for (x, y), zz, cc in zip(ov, z, cv)]
        sheets[sg] = vs
        for f in of:
            try:
                bm.faces.new([vs[i] for i in (f if sg > 0 else f[::-1])])
            except ValueError:
                pass
    if side != "both":   # the flat back: the outline alone, triangulated, at z = 0
        sg = -sides[0]
        flat = G.delaunay_2d_cdt([Vector((float(x), float(y))) for x, y in bnd], edges, [], 0, 1e-5)
        fv, ff = np.array([(v.x, v.y) for v in flat[0]]), flat[2]
        back = {}
        for o, ids in enumerate(flat[3]):
            for i in ids:
                back[i] = o
        bvs = [bm.verts.new((x * s, y * s, 0.0)) for x, y in fv]
        # (the same exact winding rule as the face: a thin trim is ALL outline samples, where a centroid test
        # guesses — Scarborough Fair's frame trim came out with 5 open edges)
        for f in _inside_faces(ff, fv, {(back[a_], back[b_]) for a_, b_ in edges}, outer, hls):
            try:
                bm.faces.new([bvs[i] for i in (f if sg > 0 else f[::-1])])
            except ValueError:
                pass
        lower = {i: bvs[back[i]] for i in range(nb)}
    else:
        lower = {i: sheets[-1][bidx[i]] for i in range(nb)}
    upper = {i: sheets[sides[0]][bidx[i]] for i in range(nb)}
    # the side WALL between the two faces along every loop (none when the core is 0: the rims meet, welded below)
    start = 0
    for lp in loops:
        n = len(lp)
        for i in range(n):
            a_, b_ = start + i, start + (i + 1) % n
            quad = [lower[a_], lower[b_], upper[b_], upper[a_]]
            if len({v.co.to_tuple(7) for v in quad}) == 4:
                try:
                    bm.faces.new(quad)
                except ValueError:
                    pass
        start += n
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5 * s)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    return bm


def _inside_faces(faces, ov, walk, outer, holes):
    """the triangulation's faces inside the material. A face on the outline decides by its winding (the CDT's faces
    are counter-clockwise; every loop walks with the material on its left, so a face holding a loop edge in the
    loop's own direction is inside, reversed outside) — exact even for the sliver ears three nearly collinear
    outline samples make, where a centroid test guesses; the rest by their centroid"""
    keep, test = [], []
    for f in faces:
        es = [(f[k], f[(k + 1) % len(f)]) for k in range(len(f))]
        if any(e in walk for e in es):
            keep.append(f)
        elif not any((b, a) in walk for a, b in es):
            test.append(f)
    if test:
        cen = np.array([ov[f].mean(0) for f in test])
        keep += [f for f, ok in zip(test, _material(cen, outer, holes)) if ok]
    return keep


def _thin(pts, r):
    """greedy: never two points closer than r (a spatial hash of r-cells)"""
    cells, keep = {}, []
    for p in pts:
        cx, cy = int(math.floor(p[0] / r)), int(math.floor(p[1] / r))
        if any(math.dist(p, q) < r for i in (-1, 0, 1) for j in (-1, 0, 1) for q in cells.get((cx + i, cy + j), ())):
            continue
        cells.setdefault((cx, cy), []).append((float(p[0]), float(p[1])))
        keep.append(p)
    return keep
