"""A BAKE CAGE THE AUTHOR SETS (the owner's method lists, 2026-11-13: "bake cages"; the 3D methods audit, stage S3b:
"Bake cages (computed, never authored)").

On the high-and-low route the detail of the HIGH is baked onto the game mesh: from every texel a ray starts a
little way above the low's surface - the cage - and looks back for the high. The kit measures how far the high
stands off the low and sets one depth for the group. An artist also sets it by hand, part by part: deeper where a
boss stands proud, shallower in a narrow gap where a deep cage reaches the next part and bakes ITS detail on.
`a.bake_cage(mm, parts=...)` is that, and it is held: a cage UNDER what the high needs starts its rays inside the
detail and misses it (an error); one far deeper than it needs is said (it may reach a neighbour).

HOW BLENDER'S BAKE CASTS (measured 2026-11-17: a plane low with one extra high plane - _scratch/bake_ray_rule.py -
and a block with two slots either side of a leaning fin, its baked map replayed texel by texel): each texel's ray
starts one depth out along the texel's own normal (or at the cage's point over it) and takes the NEAREST face
ahead of it either way round - a face met from BEHIND is baked too, a flipped normal; nothing behind the start is
ever seen. The kit's calm_normals then overwrites a texel tilted past LOW_NORMAL_Z_MIN with its neighbours' mean:
a flipped wall can come out looking flat (a 4.4 mm depth on that block: 45,510 texels calmed), so a check of the
bake reads its RAYS, never the calmed map.

THE FITTED CAGE (`a.bake_cage("fit")`; the audit's PARTLY: "a hand-sculpted cage around a complex part"): what an
artist sculpts by hand, solved. Every point of the high lies over a triangle of the low; the cage over it - its
corners pushed along their own normals, the depths shared by place in the triangle - must clear it (x FIT_MARGIN,
+ FIT_PAD_MM): `fit_solve` raises the corners until every point is cleared, never past GAP_SHARE of the room in
front of a corner (a slot's far wall). A cage never steps under FIT_RATIO of its neighbour (a sharp step folds).
Where the room stops a corner short of its points they are UNMET - said, with the part: no cage bakes that whole;
bake that part apart, or bring the high closer to the low.

THE WRONG SURFACE (any cage; `column_truth` against `bake_hit`): along the texel's ray, the surface it should
bake is the high's outer face over it - the face nearest the texel, then on through any body that sits on it
(a dome on a plate) to its far side. The bake's own pick is the nearest face ahead of its start, either way round. Where the
two are more than WRONG_MM apart the texel baked the wrong surface: inside a proud detail (a cage too shallow),
the back of the far wall of a slot it started behind, or a thin fin beside it (too deep). A hole the low leaves out on purpose is the surface over its texel:
never this.
Pure numpy; no Blender."""

import numpy as np

MISSES = 0.01     # more of a group's map than this left unbaked (its rays found no high) is said
SHARE = 0.99      # a part's need: the distance 99% of its high lies within
TOO_DEEP = 6.0    # a cage this many times what its part needs (and over FLOOR_MM) is said
FLOOR_MM = 1.0    # ... a need under this is taken as this: a cage of a millimetre is never "too deep"
FIT_MARGIN = 1.25  # the fitted cage: this much over what the high stands off the low ...
FIT_PAD_MM = 0.1   # ... and this
FIT_FLOOR_MM = 0.25  # ... and never under this
FIT_RATIO = 0.6    # a fitted corner is never under this share of its neighbour's depth (a sharp step folds the cage)
GAP_SHARE = 0.45   # ... and never past this share of the room in front of it (the next surface along its normal)
STACK_MM = 0.15    # a body entered this near where the last one was left sits ON it (a dome on its plate)
WRONG_MM = 0.25    # a texel's bake landed this far from the surface it should bake: the wrong surface
CROSS = 0.01       # more of a group's map than this baked from the wrong surface is said


def need(dists_mm, part_of, n_parts, share=SHARE):
    """what each part's cage must reach: the high's distance over the low, by the low's part nearest each point
    -> [mm for part 0..n-1] (0.0 for a part no point of the high lies nearest)"""
    d, p = np.asarray(dists_mm, float), np.asarray(part_of, int)
    out = []
    for i in range(int(n_parts)):
        mine = np.sort(d[p == i])
        out.append(0.0 if not len(mine) else float(mine[min(len(mine) - 1, int(share * len(mine)))]))
    return out


def problem(part, asked_mm, need_mm):
    """a cage under what its part's high needs -> a sentence, or None"""
    if asked_mm + 1e-6 >= need_mm:
        return None
    return (f"{part}: its cage is {asked_mm:g} mm and its high stands {need_mm:.2f} mm off the game mesh - the "
            f"rays start inside the detail and miss it: at least {np.ceil(need_mm * 10) / 10:g} mm")


def deep(part, asked_mm, need_mm):
    """a cage far deeper than its part needs -> a sentence, or None"""
    if asked_mm <= TOO_DEEP * max(need_mm, FLOOR_MM):
        return None
    return (f"{part}: its cage is {asked_mm:g} mm and its high needs {max(need_mm, 0.01):.2f} - that deep a ray "
            "can land on the part beside it and bake that part's detail here")


def offsets(vert_faces, face_mm):
    """how far each vertex of the cage is pushed out: the deepest cage among the faces that meet at it
    -> (V,) mm. vert_faces: for each vertex, the indices of its faces; face_mm: (F,) each face's cage"""
    f = np.asarray(face_mm, float)
    return np.array([float(f[list(fs)].max()) if len(fs) else 0.0 for fs in vert_faces])


def miss_problem(group, share, where):
    """rays that found no high under their cage -> a sentence, or None. where: the parts they are on, worst first"""
    if share <= MISSES:
        return None
    on = f" (most on {', '.join(where[:3])})" if where else ""
    return (f"{group}: {share:.1%} of its map's texels found no high under their cage{on} - they bake as black "
            "patches or take their neighbour's colour: a deeper cage there (a.bake_cage), or the high is missing "
            "under that part")


def fit_solve(corners, place, along, need_mm, n_verts, cap_mm, floor_mm=FIT_FLOOR_MM, iters=400, ceiling=None):
    """THE FITTED CAGE, SOLVED: S points of the high, each over a triangle of the low.
    corners (S, 3): its triangle's vertices; place (S, 3): where it lies in the triangle (weights summing to 1);
    along (S, 3): how much of each corner's push is along the triangle's normal (1 on a flat face);
    need_mm (S,): how far the cage must clear the low there; cap_mm (V,): the most each vertex may take (the room).
    ceiling: (corners, place, along, most_mm) - points ACROSS the low's faces where the cage may rise no higher (the
    room in front of the face there x GAP_SHARE): a corner whose own normal looks over a wall is still held by the
    face it lifts (the fin's top corner: 10.66 mm, past the 2.3 mm gap its face's rays crossed)
    -> ((V,) depths mm, (S,) unmet: points the cage could not clear, (V,) the caps as the faces tightened them -
    give THESE to taper, or it lifts a corner a face held down)"""
    v = np.asarray(corners, int).reshape(-1, 3)
    a = np.asarray(place, float).reshape(-1, 3) * np.clip(np.asarray(along, float).reshape(-1, 3), 0.2, 1.0)
    need = np.asarray(need_mm, float)
    cap = np.asarray(cap_mm, float)
    h = np.minimum(np.full(int(n_verts), float(floor_mm)), cap)
    if ceiling is not None:
        cv = np.asarray(ceiling[0], int).reshape(-1, 3)
        ca = np.asarray(ceiling[1], float).reshape(-1, 3) * np.clip(np.asarray(ceiling[2], float).reshape(-1, 3),
                                                                     0.2, 1.0)
        most = np.asarray(ceiling[3], float)
    for _ in range(iters):
        moved = False
        short = need - (a * h[v]).sum(axis=1)
        bad = short > 1e-4
        if bad.any():
            free = (h[v[bad]] < cap[v[bad]] - 1e-9)                 # (a corner at its room takes no more)
            aa = a[bad] * free
            den = (aa ** 2).sum(axis=1)
            ok = den > 1e-12
            if ok.any():
                step = aa[ok] * (short[bad][ok] / den[ok])[:, None]  # (each point alone: the least that clears it)
                up = np.zeros(len(h))
                np.maximum.at(up, v[bad][ok].ravel(), step.ravel())
                nxt = np.minimum(h + up, cap)
                moved = not np.allclose(nxt, h)
                h = nxt
        if ceiling is not None:
            over = (ca * h[cv]).sum(axis=1) - most
            hi = over > 1e-4
            if hi.any():
                den = (ca[hi] ** 2).sum(axis=1)
                step = ca[hi] * (over[hi] / np.maximum(den, 1e-12))[:, None]
                down = np.zeros(len(h))
                np.maximum.at(down, cv[hi].ravel(), step.ravel())
                nxt = np.maximum(h - down, 0.0)
                moved = moved or not np.allclose(nxt, h)
                cap = np.minimum(cap, np.where(down > 0, nxt, cap))   # (a corner a face held down rises no more)
                h = nxt
        if not moved:
            break
    return h, need - (a * h[v]).sum(axis=1) > 1e-3, cap


def hold_down(depth_mm, ceiling, iters=200):
    """the ceiling again (fit_solve's), after the taper: never above the room across a face -> (V,) mm"""
    h = np.asarray(depth_mm, float).copy()
    if ceiling is None or not len(ceiling[3]):
        return h
    cv = np.asarray(ceiling[0], int).reshape(-1, 3)
    ca = np.asarray(ceiling[1], float).reshape(-1, 3) * np.clip(np.asarray(ceiling[2], float).reshape(-1, 3), 0.2, 1.0)
    most = np.asarray(ceiling[3], float)
    for _ in range(iters):
        over = (ca * h[cv]).sum(axis=1) - most
        hi = over > 1e-4
        if not hi.any():
            break
        den = (ca[hi] ** 2).sum(axis=1)
        step = ca[hi] * (over[hi] / np.maximum(den, 1e-12))[:, None]
        down = np.zeros(len(h))
        np.maximum.at(down, cv[hi].ravel(), step.ravel())
        h = np.maximum(h - down, 0.0)
    return h


def short_of(corners, place, along, stand_mm, depth_mm, tol=0.02):
    """the points the cage passes under: the cage's height over each (as fit_solve reckons it) short of where the
    high stands there by more than `tol` mm -> (S,) bool"""
    v = np.asarray(corners, int).reshape(-1, 3)
    a = np.asarray(place, float).reshape(-1, 3) * np.clip(np.asarray(along, float).reshape(-1, 3), 0.2, 1.0)
    return (a * np.asarray(depth_mm, float)[v]).sum(axis=1) + tol < np.asarray(stand_mm, float)


def taper(depth_mm, vert_nbrs, cap_mm, ratio=FIT_RATIO):
    """never under `ratio` of a neighbour's depth (a sharp step folds the cage), never past the room -> (V,) mm.
    vert_nbrs: each vertex's neighbours, or an (E, 2) array of edges"""
    h = np.asarray(depth_mm, float).copy()
    cap = np.asarray(cap_mm, float)
    if isinstance(vert_nbrs, np.ndarray) and vert_nbrs.ndim == 2:
        e = vert_nbrs.astype(int)
    else:
        e = np.array([(x, y) for x, ns in enumerate(vert_nbrs) for y in ns], int).reshape(-1, 2)
    if not len(e):
        return h
    a_, b_ = np.concatenate([e[:, 0], e[:, 1]]), np.concatenate([e[:, 1], e[:, 0]])
    for _ in range(64):
        nb = np.zeros(len(h))
        np.maximum.at(nb, a_, ratio * h[b_])
        nxt = np.minimum(np.maximum(h, nb), np.maximum(cap, h))   # (a step never pushes one past its room)
        if np.allclose(nxt, h):
            break
        h = nxt
    return h


def pinch_problem(group, count, total, where):
    """points of the high the room stops the fitted cage short of -> a sentence, or None"""
    if not count:
        return None
    on = f" (on {', '.join(where[:3])})" if where else ""
    return (f"{group}: {count} of {total} points of the high{on} stand farther off the game mesh than the room in "
            "front of it allows (a slot or an inside corner narrower than the detail is deep): no cage bakes them "
            "whole - bake that part apart (its own group), or bring the high closer to the low")


def column_truth(t, out, tol=STACK_MM, sits=None):
    """the surface a texel should bake, along its ray: t - each crossing of the high, mm out from the texel;
    out - True where the ray leaves solid material there, going out -> t, or None: the face nearest the texel, then
    on through any body entered within `tol` of it (a dome on a plate) to that body's far face. Two faces left with
    no entry between them: the body was entered right AT the first (a foot lying on its plate, which one cast of
    the ray cannot see twice) - on to the second. sits: True on a face of a part of the high ONLY (a thread, a
    lettering, a dome the low leaves out): it is baked onto the surface under it however far it stands off"""
    t, out = np.asarray(t, float), np.asarray(out, bool)
    order = np.argsort(t, kind="stable")
    t, out = t[order], out[order]
    sits = np.zeros(len(t), bool) if sits is None else np.asarray(sits, bool)[order]
    if not out.any():
        return None
    i = int(np.flatnonzero(out)[np.argmin(np.abs(t[out]))])
    cur = float(t[i])
    for k in range(i + 1, len(t)):
        if out[k]:
            cur = float(t[k])
        elif t[k] - cur > tol and not sits[k]:
            break
    return cur


def repair_column(t, out, inside):
    """one cast of a ray sees ONE of two faces lying on each other (a dome's foot on its plate's top): an entry met
    while already inside (`inside`: the line starts in solid material) is a face left right there that the cast
    dropped - put back. (A face left while outside is column_truth's: a body entered right at the last face.)
    -> (t, out) in order"""
    t, out = np.asarray(t, float), np.asarray(out, bool)
    order = np.argsort(t, kind="stable")
    rt, ro, state = [], [], bool(inside)
    for t_, o_ in zip(t[order], out[order]):
        if not o_ and state:
            rt.append(float(t_))
            ro.append(True)
        rt.append(float(t_))
        ro.append(bool(o_))
        state = not o_
    return np.array(rt), np.array(ro, bool)


def bake_hit(t, out, t_from, reach):
    """where the bake's ray lands (measured on Blender 5.2, kit/selftest note in rbx_bakecage's header): from t_from
    (the start, mm out along the ray) back toward the texel and on, the NEAREST face either way round - one met from
    behind is baked too (a flipped normal) - within reach; never one behind the start -> t, or None"""
    t = np.asarray(t, float)
    got = t[(t <= t_from + 1e-9) & (t >= t_from - reach)]
    return float(got.max()) if len(got) else None


def wrong(truth, hit, tol=WRONG_MM):
    """the bake landed on another surface than the one over its texel (a miss is bake_misses', never this)"""
    return truth is not None and hit is not None and abs(hit - truth) > tol


def cross_problem(group, share, where):
    """texels baked from the wrong surface -> a sentence, or None. where: the parts they are on, worst first"""
    if share <= CROSS:
        return None
    on = f" (most on {', '.join(where[:3])})" if where else ""
    return (f"{group}: {share:.1%} of its map's texels baked another surface than the one over them{on} - the "
            "cage starts their rays inside a proud detail (too shallow there) or past a thin wall (too deep): "
            'a.bake_cage("fit") follows the high and stops short of the next wall')
