"""rbx_round.py — round a part's edges LOCALLY: each hard edge as wide as asked, except where the part is too narrow
there for that round (a notch, a thin web, a thin plate), where it is cut to fit THERE only.

Blender's bevel with clamp_overlap shrinks the WHOLE bevel to fit its tightest spot: one 1 mm notch cut a 2 mm round
to 0.45 mm all round the part (_scratch probe, 2026-10-22) — every traced part with a small hook or notch
(Scarborough Fair's hammer, trigger, frame) got a quarter of its round_mm, and kit look edges measured them sharper
than the art. So the kit measures each edge's room first and bevels in passes, one width class at a time.

    limit = room(bm, want)        a function: a point (bmesh units) -> the widest safe round there
    round_edges(bm, pick, want, room_of)  bevels the picked edges, each min(want(e), room_of(e)), in width classes;
                                  -> [[width, edges, their length]] per pass (the widths actually built)
"""

import heapq
import math

import bmesh
from mathutils import kdtree

CLASSES = (1.0, 0.75, 0.55, 0.4, 0.28, 0.18, 0.1)   # (a pass per fraction of the asked width)
SAFE = 0.45   # (a round may take this much of the room across: two rounds facing each other never meet)
SLOPE = 0.5   # (how fast a round may change along an edge, mm per mm)


def face_widths(hard, idx):
    """{vertex index: the narrowest width across a face beside one of its hard edges} — rays cast in each face's
    plane, perpendicular to the edge, from near both its ends (numpy over the face's boundary segments)"""
    import numpy as np  # noqa: PLC0415

    out = {}
    seg_cache = {}
    for e in hard:
        v0, v1 = e.verts
        d = v1.co - v0.co
        if d.length < 1e-9:
            continue
        d = d.normalized()
        for f in e.link_faces:
            n = f.normal
            if n.length < 1e-9:
                continue
            inward = n.cross(d).normalized()
            mid = (v0.co + v1.co) * 0.5
            if (f.calc_center_median() - mid).dot(inward) < 0:
                inward = -inward
            if f.index not in seg_cache or seg_cache[f.index][0] is not f:
                loops = [(lv.vert, lv.link_loop_next.vert, lv.edge) for lv in f.loops]
                seg_cache[f.index] = (f, loops)
            loops = seg_cache[f.index][1]
            # the face's boundary in (along the edge, inward) coordinates, the edge itself left out
            P = np.array([[(a.co - v0.co).dot(d), (a.co - v0.co).dot(inward)] for a, _b, ed in loops if ed is not e])
            Q = np.array([[(b.co - v0.co).dot(d), (b.co - v0.co).dot(inward)] for _a, b, ed in loops if ed is not e])
            if len(P) == 0:
                continue
            L = (v1.co - v0.co).length
            for frac, vert in ((0.1, v0), (0.9, v1)):
                ox = frac * L
                # the ray x = ox, y > 0: where does it cross a boundary segment?
                x0, y0, x1, y1 = P[:, 0], P[:, 1], Q[:, 0], Q[:, 1]
                dx = x1 - x0
                ok = np.abs(dx) > 1e-12
                t = np.where(ok, (ox - x0) / np.where(ok, dx, 1), -1)
                hit = ok & (t >= 0) & (t <= 1)
                y = y0 + t * (y1 - y0)
                y = y[hit & (y > 1e-6)]
                if len(y):
                    w_ = float(y.min())
                    k = idx[vert]
                    out[k] = min(out.get(k, math.inf), w_)
    return out


def split_long(bm, want, angle=30.0, piece=2.5):
    """hard edges longer than `piece` x want cut into equal pieces at least that long: a bevel is ONE width per edge,
    so a long straight edge ending at a notch would take the notch's narrow width along its whole length — and never
    shorter: where a bevel chain ENDS, Blender slides its end along the next edge by the full width (a piece under it
    folds over: 528 folded faces on a notched slab with pieces of one width)"""
    longest = piece * want
    hard = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(angle)
            and e.calc_length() > 2 * longest]
    for e in hard:
        cuts = int(e.calc_length() // longest) - 1
        if cuts > 0:
            bmesh.ops.subdivide_edges(bm, edges=[e], cuts=min(cuts, 200), use_grid_fill=False)
    return len(hard)


def room(bm, want, angle=30.0, why=None):
    """-> f(point): how wide a round fits at a point of the part's hard edges: SAFE x the width ACROSS the faces
    beside it (a hook, a web, the plate's thickness), SAFE x a short run between two corners, 0.9 x the radius of the
    curve it runs along — tapered so it never jumps (SLOPE). why: {vertex: the rule that limited it} (a diagnosis)"""
    hard = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(angle)]
    verts = list(dict.fromkeys(v for e in hard for v in e.verts))   # (first-seen order: a set of
    # mesh elements is ordered by memory address - another order every run)
    if not verts:
        return lambda p: want
    idx = {v: i for i, v in enumerate(verts)}
    adj = {i: [] for i in range(len(verts))}
    for e in hard:
        a, b = idx[e.verts[0]], idx[e.verts[1]]
        L = e.calc_length()
        adj[a].append((b, L))
        adj[b].append((a, L))
    tree = kdtree.KDTree(len(verts))
    for v, i in idx.items():
        tree.insert(v.co, i)
    tree.balance()
    limit = [want] * len(verts)
    # ACROSS each face beside a hard edge: a ray from the edge, perpendicular to it in the face's plane, to where it
    # leaves the face — the real local width (a hook, a web; across a wall: the plate's thickness). Two rounds face
    # each other across it: each may take SAFE x it
    for k, w_ in face_widths(hard, idx).items():
        if SAFE * w_ < limit[k]:
            limit[k] = SAFE * w_
            if why is not None:
                why[k] = "across"
    # CORNERS: where the hard edges turn sharply (or meet three ways), a round can take at most SAFE x the shorter
    # straight run beside it (a 1 mm notch wall cannot carry a 2 mm round) — and so can every point within a round's
    # width of that corner (clamp_overlap would otherwise cut the whole pass at that one corner)
    def turn(k):
        if len(adj[k]) != 2:
            return 180.0
        (a, _la), (b, _lb) = adj[k]
        u = verts[k].co - verts[a].co
        w_ = verts[b].co - verts[k].co
        if u.length < 1e-12 or w_.length < 1e-12:
            return 0.0
        return math.degrees(u.angle(w_))
    corner = {k for k in range(len(verts)) if turn(k) > 35.0}
    for c in corner:
        # each RUN from this corner to the next: a round can take at most SAFE x the run's length, along THAT run only
        # (a 1 mm arc between two corners holds a 0.45 mm round; the long edge beside it keeps its own)
        for start, L0 in adj[c]:
            prev, cur, total, steps, members = c, start, L0, 0, [c, start]
            while cur not in corner and steps < 100000:
                nxt = [(j, L) for j, L in adj[cur] if j != prev]
                if not nxt:
                    break
                prev, (cur, L) = cur, nxt[0]
                total += L
                steps += 1
                members.append(cur)
            cap_ = SAFE * total
            if cap_ >= want:
                continue
            for j in members:
                if cap_ < limit[j] and why is not None:
                    why[j] = "short run"
                limit[j] = min(limit[j], cap_)
    # CURVES: a round can never be bigger than the curve it runs along — a 3 mm bevel round a 0.6 mm tip folds over
    # itself (a traced tip is many tiny segments, each turning only ~7 degrees: no corner above sees it). The circle
    # through each rim vertex and its two neighbours gives the curve's radius there
    for k in range(len(verts)):
        if len(adj[k]) != 2 or k in corner:
            continue
        (a, _la), (b, _lb) = adj[k]
        pa, pk, pb = verts[a].co, verts[k].co, verts[b].co
        cross = (pa - pk).cross(pb - pk).length
        if cross < 1e-12:
            continue
        R = (pa - pk).length * (pb - pk).length * (pa - pb).length / (2.0 * cross)
        if 0.9 * R < limit[k]:
            for _co, j, _d in tree.find_range(pk, max(want, 2 * (pa - pk).length)):
                if 0.9 * R < limit[j] and why is not None:
                    why[j] = "curve"
                limit[j] = min(limit[j], 0.9 * R)
    # NO JUMPS: along the edges a round may change by at most SLOPE mm per mm (an abrupt change folds the bevel
    # where the widths meet) — the narrow spots' limits spread to their neighbours, tapering
    for _ in range(64):
        moved = False
        for k in range(len(verts)):
            for j, L in adj[k]:
                cap_ = limit[j] + SLOPE * L
                if cap_ < limit[k] - 1e-9:
                    limit[k] = cap_
                    moved = True
                    if why is not None and k not in why:
                        why[k] = "taper"
        if not moved:
            break
    vtree = tree

    def f(p):
        _co, j, _d = vtree.find(p)
        return limit[j]
    return f


def round_edges(bm, pick, want, room_of, segments=5, clamp=False):
    """bevel the hard edges pick(e) selects, each to min(want(e), room_of(e)), one width class per pass (the widest
    first; each pass picks its edges afresh, never an edge an earlier pass rounded) -> [[width, n edges, length]]"""
    done = bm.faces.layers.int.get("kit_round") or bm.faces.layers.int.new("kit_round")
    passes = []

    def target(e):
        w = want(e)
        if w <= 0:
            return 0.0
        r = min(w, room_of(e.verts[0].co), room_of(e.verts[1].co))   # (the tighter end: one width per edge)
        cls = next((c for c in CLASSES if r >= c * w - 1e-9), CLASSES[-1])
        return round(cls * w, 6)
    widths = sorted({target(e) for e in bm.edges if pick(e)} - {0.0}, reverse=True)

    def select():
        bm.edges.ensure_lookup_table()
        return [e for e in bm.edges if pick(e) and not all(f[done] for f in e.link_faces) and abs(target(e) - w) < 1e-6]
    for w in widths:
        sel = select()
        if not sel:
            continue
        # (no Blender clamp: it also weighs the short unbevelled edges where a chain ENDS and shrinks the whole
        # pass — a full 2 mm class 3.4 mm from a notch came out 0.05 mm; the room above is the per-edge limit) —
        # CHECKED: a pass whose new faces cut through the rest of the part is undone and done again clamped
        length = sum(e.calc_length() for e in sel)   # (before the bevel replaces them)
        keep = _snapshot(bm)
        res = bmesh.ops.bevel(bm, geom=sel, offset=w, segments=segments, profile=0.5, affect="EDGES",
                              clamp_overlap=clamp)
        clamped = False
        if not clamp and _crosses(bm, res.get("faces", [])):
            _restore(bm, keep)
            done = bm.faces.layers.int.get("kit_round")
            sel = select()
            res = bmesh.ops.bevel(bm, geom=sel, offset=w, segments=segments, profile=0.5, affect="EDGES",
                                  clamp_overlap=True)
            clamped = True
        _free(keep)
        for f in res.get("faces", []):
            f[done] = 1
        passes.append([w, len(sel), length] + (["clamped"] if clamped else []))
    bm.faces.layers.int.remove(done)
    return passes


def _crosses(bm, new_faces, eps=1e-9):
    """do the pass's NEW faces cut through faces they do not touch (overlapping bevels: what clamp_overlap
    prevents)? A BVH overlap of the whole part, pairs sharing a vertex ignored, degenerate new faces counted"""
    from mathutils.bvhtree import BVHTree  # noqa: PLC0415

    bm.verts.index_update()   # (indices go stale through bmesh operations: refreshed, or shared vertices look apart)
    bm.faces.index_update()
    bm.faces.ensure_lookup_table()
    new = {f.index for f in new_faces if f.is_valid}
    if not new:
        return False
    if any(bm.faces[i].calc_area() < eps for i in new):
        return True
    tree = BVHTree.FromBMesh(bm, epsilon=0.0)
    for i, j in tree.overlap(tree):
        if i == j or (i not in new and j not in new):
            continue
        a, b = bm.faces[i], bm.faces[j]
        if {v.index for v in a.verts} & {v.index for v in b.verts}:
            continue
        return True
    return False


def _snapshot(bm):
    import bpy  # noqa: PLC0415

    me = bpy.data.meshes.new("_kit_round_keep")
    bm.to_mesh(me)
    return me


def _restore(bm, me):
    bm.clear()
    bm.from_mesh(me)


def _free(me):
    import bpy  # noqa: PLC0415

    bpy.data.meshes.remove(me)
