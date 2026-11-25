"""THE TOPOLOGY OF A BUILT MODEL, MEASURED (the owner's method lists, 2026-11-13: "edge flow", "polygon
distribution", "internal and hidden faces", "flat shading"; the 3D methods audit, stage T: "polygon distribution
(by tolerance and angle knobs)", "internal and hidden faces (removed on generated shells only)").

A game mesh is paid for by the triangle. Four things a modeller looks for on the finished mesh, each a number here:
  SPENT ON NOTHING  a vertex in the middle of a flat face: every triangle round it lies in one plane, so taking it
                    out changes no shape - two triangles each that buy nothing;
  NEEDLES           a triangle hundreds of times longer than it is wide: its normal is noise, it shades in
                    streaks and bakes badly (a bevel's long strip is not one);
  POLES             a vertex where very many edges meet on a surface that is not flat: the shading pinches there;
  NEVER SEEN        a face no eye outside the model can reach (inside a joint, under a part that sits on it): it
                    is drawn and lit every frame for nothing.
Pure numpy (the rays of NEVER SEEN are the builder's: `directions` gives them); no Blender."""

import numpy as np

FLAT_DEG = 1.0        # triangles round a vertex within this angle of each other lie in one plane
WASTE_BAR = 0.20      # more of a group's triangles than this spent on nothing is said
SLIVER = 500.0       # a triangle this many times longer than wide is a NEEDLE (a bevel's long strip, 20 to
                      # 200 times, is not: 5 to 38% of the built models' triangles are those, and they shade well)
SLIVER_BAR = 0.005    # more of a group's triangles than this (by count) is said
POLE = 16             # edges meeting at one vertex of a curved surface
HIDDEN_SAMPLE = 2000  # the never-seen MEASURE asks this many of a group's triangles at most (a share: its 95% error
#                       at 2000 is under 2 points, against a 30% bar; 8000 cost 5.8 s of an 18 s build at 37k
#                       triangles with a quarter hidden - a hidden one costs every point times every eye). The DROP
#                       (a.drop_hidden) asks every face, as it must
HIDDEN_BAR = 0.30     # more of a group's triangles than this never seen is said (parts sunk into each other,
                      # the kit's way of building, hide 10 to 25% on healthy models: a fact there, not a warning)
NEEDLE_WIDTH = 0.005  # ... and a needle is thinner than this, in studs (1.4 mm): a long bevel is not one


def _normals(points, tris):
    p = np.asarray(points, float)[np.asarray(tris, int).reshape(-1, 3)]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    length = np.linalg.norm(n, axis=1)
    return n / np.maximum(length, 1e-30)[:, None], length / 2.0


def flat_verts(points, tris, keep=None, degrees=FLAT_DEG):
    """the vertices that buy nothing -> a bool per vertex: every triangle round it lies in one plane (within
    `degrees`), it is not on an open edge, and it is not one the caller keeps (`keep`: a bool per vertex - a
    corner of the map, a part's border, a hole's rim)"""
    pts, t = np.asarray(points, float), np.asarray(tris, int).reshape(-1, 3)
    n, area = _normals(pts, t)
    nv = len(pts)
    first = np.full((nv, 3), np.nan)
    ok = np.ones(nv, bool)
    used = np.zeros(nv, bool)
    bar = np.cos(np.radians(degrees))
    for f in np.argsort(-area):                       # (the largest triangle round a vertex sets its plane)
        if area[f] <= 0:
            continue
        for v in t[f]:
            if not used[v]:
                first[v], used[v] = n[f], True
            elif float(first[v] @ n[f]) < bar:
                ok[v] = False
    # an open edge (one triangle alone uses it): its two ends hold the outline
    e = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    uniq, counts = np.unique(e, axis=0, return_counts=True)
    ok[np.unique(uniq[counts != 2])] = False
    # a vertex on the corner of a flat face is needed for its outline: only one the fan goes ALL the way round
    # is free - on a closed fan the edges at the vertex equal its triangles
    tri_at = np.bincount(t.ravel(), minlength=nv)
    edge_at = np.bincount(uniq.ravel(), minlength=nv)
    ok &= used & (tri_at == edge_at) & (tri_at >= 3)
    if keep is not None:
        ok &= ~np.asarray(keep, bool)
    return ok


def waste(points, tris, keep=None, degrees=FLAT_DEG):
    """what a group spends on nothing -> {"verts", "tris": two a vertex, "share": of its triangles}"""
    t = np.asarray(tris, int).reshape(-1, 3)
    free = flat_verts(points, t, keep, degrees)
    n = int(free.sum())
    return {"verts": n, "tris": 2 * n, "share": round(2.0 * n / max(len(t), 1), 4), "mask": free}


def slivers(points, tris, ratio=SLIVER, width=None):
    """the triangles many times longer than wide -> {"count", "share": by count, "worst", "mask"}. A triangle's
    length over its width is its longest edge over the height on it; one with no surface at all is not counted
    here (the validator's degenerate faces)."""
    pts, t = np.asarray(points, float), np.asarray(tris, int).reshape(-1, 3)
    p = pts[t]
    edges = np.stack([np.linalg.norm(p[:, 1] - p[:, 0], axis=1), np.linalg.norm(p[:, 2] - p[:, 1], axis=1),
                      np.linalg.norm(p[:, 0] - p[:, 2], axis=1)], axis=1)
    longest = edges.max(axis=1)
    area = _normals(pts, t)[1]
    real = area > 1e-14
    aspect = np.ones(len(t))
    aspect[real] = longest[real] ** 2 / (2.0 * area[real])
    thin = real & (aspect > ratio)
    if width is not None:   # (thin in studs too: its height on its longest edge)
        thin &= (2.0 * area / np.maximum(longest, 1e-30)) < float(width)
    return {"count": int(thin.sum()), "share": round(float(thin.sum()) / max(int(real.sum()), 1), 4),
            "worst": round(float(aspect.max()) if len(aspect) else 1.0, 1), "mask": thin}


def poles(points, tris, limit=POLE, degrees=FLAT_DEG):
    """the vertices where more than `limit` edges meet on a surface that is not flat there -> sorted indices
    (the middle of a flat fan - a cap's centre - pinches nothing and is not one)"""
    pts, t = np.asarray(points, float), np.asarray(tris, int).reshape(-1, 3)
    e = np.unique(np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1), axis=0)
    valence = np.bincount(e.ravel(), minlength=len(pts))
    n, area = _normals(pts, t)
    bar = np.cos(np.radians(degrees))
    out = []
    for v in np.nonzero(valence > limit)[0]:
        mine = n[(t == v).any(axis=1) & (area > 0)]
        if len(mine) and float((mine @ mine[0]).min()) < bar:
            out.append(int(v))
    return out


def directions(normal, count=24, grazing=0):
    """the ways an eye could look at a face from outside: `count` directions spread over the half of space its
    normal points into (deterministic) -> (count, 3) unit vectors, none flatter than about 10 degrees to the face;
    grazing: that many more in a ring 4 degrees off the face (a.drop_hidden asks them: a face seen only at a glance
    is kept - card fw6p)"""
    n = np.asarray(normal, float)
    n = n / max(np.linalg.norm(n), 1e-30)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    i = np.arange(count) + 0.5
    up = 0.17 + (1.0 - 0.17) * (i / count)            # (sin 10 degrees .. 1: from grazing to straight on)
    turn = i * 2.399963229728653                      # (the golden angle: an even spread)
    if grazing:
        up = np.r_[up, np.full(int(grazing), np.sin(np.radians(4.0)))]
        turn = np.r_[turn, np.arange(int(grazing)) * 2 * np.pi / int(grazing)]
    flat = np.sqrt(np.maximum(1.0 - up * up, 0.0))
    return n[None, :] * up[:, None] + (u[None, :] * np.cos(turn)[:, None] + v[None, :] * np.sin(turn)[:, None]) * flat[:, None]


def waste_problem(group, w, bar=WASTE_BAR):
    if w["share"] <= bar:
        return None
    return (f"{group}: {w['share']:.0%} of its triangles are spent on nothing ({w['verts']} vertices in the middle "
            f"of flat faces: about {w['tris']} triangles) - build that face coarser (fewer segments, a plain box)")


def sliver_problem(group, s, bar=SLIVER_BAR):
    if s["share"] <= bar:
        return None
    return (f"{group}: {s['share']:.0%} of its triangles are needles (over {SLIVER:g} times longer than wide; the "
            f"worst {s['worst']:g}) - they shade in streaks: weld the points that nearly meet, or cut that face again")


def hidden_problem(group, share, count, where, bar=HIDDEN_BAR):
    if share <= bar:
        return None
    on = f" (most on {', '.join(where[:3])})" if where else ""
    return (f"{group}: {share:.0%} of its triangles ({count}) can never be seen from outside{on} - drawn every "
            "frame for nothing: a.drop_hidden() takes them out")


def pole_problem(group, found, names=()):
    if not found:
        return None
    on = f" (on {', '.join(names[:3])})" if names else ""
    return (f"{group}: {len(found)} point(s) where more than {POLE} edges meet on a curved surface{on} - the "
            "shading pinches there: end the fan on a small flat cap, or use fewer segments round it")


def shaded(corner_normals, face_normals, degrees=2.0):
    """how much of a part is shaded FLAT -> the share of its corners whose normal is its own face's (within
    `degrees`). 1.0 = every face flat; a smooth part is far below. (N, 3) each, one row a corner."""
    c, f = np.asarray(corner_normals, float).reshape(-1, 3), np.asarray(face_normals, float).reshape(-1, 3)
    if not len(c):
        return 1.0
    c = c / np.maximum(np.linalg.norm(c, axis=1, keepdims=True), 1e-30)
    f = f / np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-30)
    return float(((c * f).sum(axis=1) >= np.cos(np.radians(degrees))).mean())


def shade_problem(part, asked, flat_share):
    """a part's shading as exported against what its script asked -> a sentence, or None"""
    if asked == "flat" and flat_share < 0.99:
        return (f"{part}: asked flat, and {1 - flat_share:.0%} of its corners are shaded round (their normal is "
                "not their face's)")
    if asked == "smooth" and flat_share > 0.9:
        return f"{part}: asked smooth, and {flat_share:.0%} of its corners are shaded flat"
    return None
