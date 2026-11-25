"""rbx_mech.py — functional assemblies: parts that MOVE (slide, trigger, hammer, magazine, bolt, lid, wheel).

Declared in the build script (see rbx.Asset.joint): each moving part lives in its own mesh group, and a joint says how
it moves against its parent group — "slide" (translate along an axis) or "hinge" (rotate about an axis through a
pivot), within [min, max] (studs or degrees). In game every joint is a Motor6D (Models.spawn): animate it in the
Animation Editor or drive it from code with Models.pose(model, "Slide", 0.25).

Here, at build time:
  interference(...)  every joint at both ends of its travel: does the moving group run INTO something it did not
                     touch at rest? (BVH triangle overlap, reported with names and how many triangles collide)
  renders(...)       orthographic line-art views for the schematic sheet (Freestyle): side, top, front, a section
                     (cut through the middle: the internals), an exploded view, and one frame per joint at full travel
"""

import json
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import rbx_travel

BL_FROM_RBX = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))  # Roblox (x, y, z) -> Blender (x, -z, y)


def _bl(v):
    return BL_FROM_RBX @ Vector(v)


def pose(joint, value):
    """Blender-space matrix moving a group from rest to `value` along/about its joint."""
    axis = _bl(joint["axis"]).normalized()
    if joint["kind"] == "fixed":
        return Matrix.Identity(4)
    if joint["kind"] == "slide":
        return Matrix.Translation(axis * value)
    pivot = _bl(joint["pivot"])
    return Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(value), 4, axis) @ Matrix.Translation(-pivot)


def _chain(joints, group):
    """the joints from the root down to `group` (a trigger bar riding in the slide moves with the slide)."""
    out, seen = [], set()
    while group in joints and group not in seen:
        seen.add(group)
        out.append(group)
        group = joints[group]["parent"]
    return list(reversed(out))


def followers_of(joints, g, value):
    """the values every joint takes when group g's joint is at `value`: g itself, and each joint that FOLLOWS it
    (a.couple: ratio x driver + offset), and those that follow them -> {group: value}"""
    vals = {g: float(value)}
    by_name = {jj["name"]: gg for gg, jj in joints.items()}
    grew = True
    while grew:
        grew = False
        for gg, jj in joints.items():
            f = jj.get("follows")
            if gg in vals or not f:
                continue
            d = by_name.get(f["joint"])
            if d in vals:
                vals[gg] = float(f["ratio"]) * vals[d] + float(f["offset"])
                grew = True
    return vals


def posed_matrix(joints, k, vals):
    """the matrix that takes group k from rest to where the joints at `vals` put it (each joint of its chain from
    the root down: a part riding on a follower moves with the follower, and with whatever carries it)"""
    m = Matrix.Identity(4)
    for c in _chain(joints, k):
        if c in vals:
            m = m @ pose(joints[c], vals[c])
    return m


def _tree(obj):
    """obj's faces as a BVH tree in WORLD space. (BVHTree.FromObject builds in the object's OWN space: a group moved
    through its travel — matrix_world posed — was tested where it RESTS, so no travel collision was ever caught; a
    lid swinging into a wall read "clear" at 100 degrees. Found by the Gjallarhorn test, 2026-10-06.)"""
    mw = obj.matrix_world
    me = obj.data
    return BVHTree.FromPolygons([mw @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])


def _part_of(obj):
    """face index -> the name of the part it came from (rbx.Asset._join tags every face: "kit_part" + obj["kit_parts"]);
    None for an untagged mesh."""
    attr = obj.data.attributes.get("kit_part")
    names = list(obj.get("kit_parts") or [])
    if attr is None or not names or len(attr.data) != len(obj.data.polygons):
        return None
    vals = [0] * len(attr.data)
    attr.data.foreach_get("value", vals)
    return lambda i: names[vals[i]] if 0 <= i < len(vals) and 0 <= vals[i] < len(names) else "?"


def _pair_parts(pairs, a, b):
    """{(part of a, part of b): colliding triangle pairs} for BVH overlap pairs between a's and b's faces."""
    pa, pb = _part_of(a), _part_of(b)
    out = {}
    if pa is None or pb is None:
        return out
    for i, k in pairs:
        key = (pa(i), pb(k))
        out[key] = out.get(key, 0) + 1
    return out


def soft_part(name):
    """a SPRING compresses: a slide racking into its recoil spring is the mechanism working, not a jam (the take-apart's
    soft rule, rbx_strip.soft, by name). Its overlaps with what moves are not counted; everything else's are."""
    return str(name).split("~")[0].lower().endswith("spring")


def _hard(pairs, a, b):
    """the overlap pairs where neither face is a spring's (untagged meshes: every pair)"""
    pa, pb = _part_of(a), _part_of(b)
    if pa is None or pb is None:
        return pairs
    return [(i, k) for i, k in pairs if not (soft_part(pa(i)) or soft_part(pb(k)))]


def _where(pairs, b):
    """the middle of b's colliding faces, in Roblox studs (x, y up, z)"""
    mw = b.matrix_world
    polys = b.data.polygons
    pts = [mw @ polys[k].center for _, k in pairs[:400] if k < len(polys)]
    if not pts:
        return None
    mid = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
    return (round(mid[0], 3), round(mid[2], 3), round(-mid[1], 3))


def _island_trees(obj):
    """one BVH tree per connected piece of a joined group, with its world bounds: [(tree, lo, hi)]. Ray parity only
    means something on ONE closed shell — two parts sharing a face exactly (a seam made on one raster:
    rbx_trace.region(minus=...), the kit's own advice) are crossed ONCE where one shell ends and the next begins,
    which flips the parity: a drum sitting in a clear window read as buried in the housing (the Gjallarhorn, 136
    points). The join keeps parts as separate pieces (no vertex merge), so a piece is a part."""
    me = obj.data
    mw = obj.matrix_world
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for poly in me.polygons:
        r0 = find(poly.vertices[0])
        for v in poly.vertices[1:]:
            rv = find(v)
            if rv != r0:
                parent[rv] = r0
    pieces = {}
    for poly in me.polygons:
        pieces.setdefault(find(poly.vertices[0]), []).append(poly)
    out = []
    for polys in pieces.values():
        index = {}
        co = []
        faces = []
        for poly in polys:
            f = []
            for v in poly.vertices:
                if v not in index:
                    index[v] = len(co)
                    co.append(mw @ me.vertices[v].co)
                f.append(index[v])
            faces.append(f)
        lo = Vector([min(p[i] for p in co) for i in range(3)])
        hi = Vector([max(p[i] for p in co) for i in range(3)])
        out.append((BVHTree.FromPolygons(co, faces), lo, hi))
    return out


def _inside_any(pieces, p):
    """p inside any one of the pieces (each tested on its own: shared faces between pieces cannot flip the parity)"""
    for tree, lo, hi in pieces:
        if lo.x <= p.x <= hi.x and lo.y <= p.y <= hi.y and lo.z <= p.z <= hi.z and inside(tree, p):
            return True
    return False


def _samples(obj, spacing):
    """world-space points spread over obj's surface (~one per spacing^2), deterministic."""
    mw = obj.matrix_world
    me = obj.data
    me.calc_loop_triangles()
    vs = [mw @ v.co for v in me.vertices]
    out = []
    for tri in me.loop_triangles:
        a, b, c = (vs[i] for i in tri.vertices)
        area = ((b - a).cross(c - a)).length / 2
        n = max(1, int(area / (spacing * spacing)))
        k = max(1, int(math.sqrt(n * 2)))
        for i in range(k):
            for j in range(k - i):
                u, v = (i + 1 / 3) / k, (j + 1 / 3) / k
                if u + v < 1:
                    out.append(a + (b - a) * u + (c - a) * v)
    return out


def _where_now(obj):
    """an object at its current place — the key of everything built from it (trees, pieces) for one check"""
    return (obj.name, tuple(round(x, 9) for row in obj.matrix_world for x in row))


def _samples_at(obj, spacing, memo):
    """_samples as an (n, 3) array — made once per object and carried along when it only MOVED (a joint's pose is
    rigid: the same points, posed), so the travel's stops do not resample the surface"""
    mw = np.array(obj.matrix_world)
    kept = memo.get(("samples", obj.name, spacing))
    if kept is not None:
        ref, pts = kept
        d = mw @ np.linalg.inv(ref)
        if np.allclose(d[:3, :3] @ d[:3, :3].T, np.eye(3), atol=1e-9):
            return pts @ d[:3, :3].T + d[:3, 3]
    pts = np.array([p[:] for p in _samples(obj, spacing)]).reshape(-1, 3)
    memo[("samples", obj.name, spacing)] = (mw, pts)
    return pts


def penetration(objs, g, skip, spacing, tol, memo=None):
    """how deep is group g INSIDE the other groups' solids: {other group: (points of g's surface deeper than tol, the
    middle of those points — WHERE to look, in studs, WHICH parts: "Bolt in Receiver" or "")}.
    memo: one dict for a whole interference() run — the other groups' trees and pieces are built once per place they
    sit, not again for every stop of every joint (the Silverballer: 54 rebuilds of the whole pistol, 3 minutes)."""
    others = [h for h in objs if h != g and h not in skip]
    if not others:
        return {}
    memo = {} if memo is None else memo
    # the same question asked twice (a joint's travel starts where it rests: its first stop IS the rest pose the
    # check before it tested) -> the same answer, once
    asked = ("asked", _where_now(objs[g]), tuple(_where_now(objs[h]) for h in others), spacing, tol)
    if asked not in memo:
        memo[asked] = _penetration(objs, g, others, spacing, tol, memo)
    return memo[asked]


def _penetration(objs, g, others, spacing, tol, memo):
    def built(kind, h, fn):
        key = (kind, _where_now(objs[h]))
        if key not in memo:
            memo[key] = fn(objs[h])
        return memo[key]

    trees = {h: built("tree", h, _tree) for h in others}
    pieces = {h: built("pieces", h, _island_trees) for h in others}
    pts = _samples_at(objs[g], spacing, memo)
    found, first = {}, {}
    for h in others:
        if not pieces[h]:
            continue
        # a point outside h's box (by more than tol) is neither on h's surface nor inside it: the same answer
        # without asking the tree, for most of the points
        lo = np.min([[*lo_] for _t, lo_, _h in pieces[h]], axis=0) - tol
        hi = np.max([[*hi_] for _t, _l, hi_ in pieces[h]], axis=0) + tol
        t = trees[h]
        for i in np.flatnonzero(np.all((pts >= lo) & (pts <= hi), axis=1)):
            p = Vector(pts[i])
            near = t.find_nearest(p)
            if near[0] is None or near[3] < tol:
                continue
            if _inside_any(pieces[h], p):
                found.setdefault(h, []).append(p)
                first.setdefault(h, i)
    found = dict(sorted(found.items(), key=lambda kv: first[kv[0]]))  # (the order the point-by-point walk gave)
    # a real penetration is a CLUSTER of points (a line where a blade crosses a wall, a patch); scattered single
    # points are ray noise from grazing faces. Count the points that have a flagged neighbour within 2.5 spacings.
    from rbx_inspect import dense_clusters  # noqa: PLC0415

    hits = {}
    own, mine = None, _part_of(objs[g])
    for h, pts in found.items():
        dense = dense_clusters(pts, spacing * 2.5, 3)  # itself + 2 flagged neighbours
        theirs, count = _part_of(objs[h]), {}
        if dense and theirs is not None and mine is not None:  # which part of g, inside which part of h
            own = own or _tree(objs[g])
            kept = []
            for p in dense:
                key = (mine(own.find_nearest(p)[2]), theirs(trees[h].find_nearest(p)[2]))
                if soft_part(key[0]) or soft_part(key[1]):
                    continue  # (a spring compresses: not a part driven into another)
                kept.append(p)
                count[key] = count.get(key, 0) + 1
            dense = kept
        if len(dense) >= 3:
            mid = [sum(p[i] for p in dense) / len(dense) for i in range(3)]
            who = ", ".join(f"{a} in {b}" for (a, b), _ in sorted(count.items(), key=lambda t: -t[1])[:3])
            hits[h] = (len(dense), (round(mid[0], 3), round(mid[2], 3), round(-mid[1], 3)), who)  # Roblox studs (x, y up, z)
    return hits


_RAYS = [Vector(v).normalized() for v in ((0.5774, 0.5832, 0.5714), (-0.6123, 0.4871, -0.6229), (0.3011, -0.8934, 0.3335),
                                         (0.8121, 0.1532, -0.5631), (-0.2417, -0.4466, 0.8615))]


def inside(tree, p):
    """p inside the closed surfaces of `tree`? Parity along five rays, majority vote (decided once three agree): real
    boolean geometry has grazing faces (a cutter flush with a face) that fool any single ray."""
    odd = even = 0
    for d in _RAYS:
        n, start = 0, p
        for _ in range(64):
            r = tree.ray_cast(start, d)
            if r[0] is None:
                break
            n += 1
            start = r[0] + d * 1e-5
        odd += n % 2
        even += 1 - n % 2
        if odd >= 3 or even >= 3:  # the vote is decided: the rays left cannot change it
            break
    return odd >= 3


def _carried(joints, t, g, vals):
    """how a follower is named in a travel's line: '' for the joint's own group, else ' (its follower X at v)'"""
    if t == g:
        return ""
    unit = "°" if joints[t]["kind"] == "hinge" else " studs"
    return f" (its follower {joints[t]['name']} at {vals.get(t, 0.0):g}{unit})"


def interference(objs, joints):
    """objs: {group: joined object}; joints: {group: joint}. -> (problems list, facts dict).
    A pair of groups that already overlaps at rest (seated parts, a slide on its rails) only counts when the
    overlap GROWS by more than a third at a travel end — that is a part driving into another one. A SPRING's faces
    never count (soft_part: it compresses — a pistol's slide racks back into its recoil spring by design)."""
    rest = {g: o.matrix_world.copy() for g, o in objs.items()}
    trees = {g: _tree(o) for g, o in objs.items()}
    base, base_parts = {}, {}
    for g in joints:
        for h in objs:
            if h != g and g in trees and h in trees:
                pairs = _hard(trees[g].overlap(trees[h]), objs[g], objs[h])
                base[(g, h)] = len(pairs)
                base_parts[(g, h)] = _pair_parts(pairs, objs[g], objs[h])
    problems, facts = [], {}
    # parts that MOVE must not sit inside other parts at rest (the face-pair count above cannot tell touching from
    # passing through: a barrel through a wall, a bolt inside a receiver wall). Sample the surface, test depth.
    diag = max((o.dimensions.length for o in objs.values()), default=1.0)
    spacing, tol = diag * 0.0025, diag * 0.0012
    memo = {}  # trees / pieces / samples, built once per place a group sits (penetration)
    for g, j in joints.items():
        if g not in objs or j["kind"] == "fixed":
            continue
        skip = set(_chain(joints, g)) | {k for k in objs if g in _chain(joints, k)}
        for h, (n, mid, who) in sorted(penetration(objs, g, skip, spacing, tol, memo).items(), key=lambda t: -t[1][0]):
            if n >= 3:
                problems.append(f"{j['name']} ('{g}') sits INSIDE '{h}' at rest ({n} surface points deeper than "
                                f"{tol:.3f} studs, around {mid}{': ' + who if who else ''}) — cut clearance in '{h}' "
                                "(a bore, a slot, a pocket) or move the part")
    for g, j in joints.items():
        if g not in objs:
            problems.append(f"joint {j['name']}: group '{g}' has no mesh")
            continue
        if j["kind"] == "fixed":
            continue
        drv_ = (j.get("follows") or {}).get("joint")
        if drv_ and any(jj["name"] == drv_ for jj in joints.values()):
            # (a FOLLOWER never moves alone - posing its driver poses it: it is swept with its driver's travel,
            #  below; swept alone it was tested at places the model can never take - card ver5)
            facts[f"{j['name']}@follows"] = drv_
            continue
        at0_ = followers_of(joints, g, 0.0)
        followers_ = [gg for gg in at0_ if gg != g and gg in objs]
        # g, everything riding on it, and every follower of it with what rides on them (card ver5: a follower's
        # travel was never checked together with its driver's)
        moving = [k for k in objs if any(c in at0_ for c in _chain(joints, k))]
        # SEQUENCE (a.joint(after={"Lid": "max"})): the joints that move first are posed for this travel
        by_name = {jj["name"]: (gg, jj) for gg, jj in joints.items()}
        staged = []
        for nm, val in (j.get("after") or {}).items():
            if nm not in by_name:
                problems.append(f"joint {j['name']}: after= names no joint '{nm}' (joints: {', '.join(sorted(by_name))})")
                continue
            gg, jj = by_name[nm]
            v = jj["max"] if val == "max" else jj["min"] if val == "min" else float(val)
            for k in objs:
                if gg in _chain(joints, k) and k not in moving and k not in staged:
                    objs[k].matrix_world = pose(jj, v) @ rest[k]
                    staged.append(k)
        staged_trees = {}
        if staged:
            bpy.context.view_layer.update()
            staged_trees = {k: _tree(objs[k]) for k in staged}
            here = _tree(objs[g])
            for k in staged:
                pairs = _hard(here.overlap(staged_trees[k]), objs[g], objs[k])
                base[(g, k)] = len(pairs)
                base_parts[(g, k)] = _pair_parts(pairs, objs[g], objs[k])
        # the whole TRAVEL, not only its two ends: a part can pass through something and come out clear at the end
        # (a shell lifted through a closed cover; a lid sweeping through a strap). The stops are set from how far
        # the group moves and how deep it is (rbx_travel): five stops whatever the travel let a pin standing
        # between two of them go unseen (the owner's limitations page, D-R05). The depth is the whole group's
        # smallest: a thin member of a bulky group gets the bulky group's step
        testers = [g] + followers_   # (the groups whose surfaces are tested at each stop)
        length = 0.0
        for t_ in testers:   # (the stops from the group that moves FURTHEST: a follower geared up runs further)
            corners = [rest[t_] @ Vector(c) for c in objs[t_].bound_box]

            def corners_at(value, _t=t_, _back=rest[t_].inverted(), _corners=corners):
                m = posed_matrix(joints, _t, followers_of(joints, g, value)) @ rest[_t] @ _back
                return [tuple(m @ c) for c in _corners]

            length = max(length, rbx_travel.path_length(corners_at, j["min"], j["max"]))
        depth = min((d for t_ in testers for d in objs[t_].dimensions if d > 1e-6), default=diag)
        stops, gap, coarse = rbx_travel.stops(j["min"], j["max"], length, rbx_travel.step_for(depth, diag))
        facts[f"{j['name']}@stops"] = len(stops)
        if coarse:   # (said, never silent: a thing thinner than the path between two stops can still escape)
            facts[f"{j['name']}@coarse"] = round(gap, 4)
        runs = []  # [line in problems, the last stop of the stretch | None]: one line a STRETCH of travel
        open_run = {}  # other group -> (its run, the index of the stop it was last driven into at)

        def say(h, si, end, text):
            """one line for a stretch of stops in a row that drive into h; a later, separate stretch its own"""
            was_ = open_run.get(h)
            if was_ is not None and was_[1] == si - 1:
                was_[0][1] = end
                open_run[h] = (was_[0], si)
                return
            run_ = [len(problems), None]
            runs.append(run_)
            open_run[h] = (run_, si)
            problems.append(text)

        for si, end in enumerate(stops):
            vals_ = followers_of(joints, g, end)
            for k in moving:
                objs[k].matrix_world = posed_matrix(joints, k, vals_) @ rest[k]
            bpy.context.view_layer.update()
            unit = "°" if j["kind"] == "hinge" else " studs"
            hit = False
            touched = False   # (some surface of the group cuts another's here that did not at rest)
            for t_, h, o in [(t_, h, o) for t_ in testers for h, o in objs.items() if h not in moving]:
                moved = _tree(objs[t_])
                pairs = _hard(moved.overlap(staged_trees.get(h) or trees[h]), objs[t_], o)
                n = len(pairs)
                b = base.get((t_, h), 0)
                # NEWLY touched: some pair of PARTS cuts each other more than at rest. (The group's total says
                # nothing: a runner that left the seats it rested on and now cuts a pin of the same body has FEWER
                # pairs than at rest - the review's find.)
                was = base_parts.get((t_, h), {})
                now_parts = _pair_parts(pairs, objs[t_], o) if n else {}
                touched = touched or (any(c > was.get(key, 0) for key, c in now_parts.items()) if now_parts
                                      else n > b)
                if n > max(8, b * 1.34):
                    # WHICH parts (the pairs that grew since rest) and WHERE: "drives into 'main'" names nothing to fix
                    grew = sorted(((c - was.get(key, 0), key) for key, c in now_parts.items()), reverse=True)
                    who = ", ".join(f"{a} into {z} +{d}" for d, (a, z) in grew[:3] if d > 0)
                    at = _where(pairs, o)
                    say((t_, h), si, end, f"{j['name']} at {end:g}{unit}{_carried(joints, t_, g, vals_)} drives "
                                          f"into '{h}' ({n} colliding triangle pairs, {b} at rest"
                                          f"{': ' + who if who else ''}{f'; around {at}' if at else ''})")
                    hit = True
            # the same depth test the rest pose gets (surface samples inside each part of the others): a few big
            # triangles never make 8 colliding pairs, and a lid swinging through a wall read "clear"
            # (the depth test is the dear one - a pistol's eight joints took 173 s at every stop, 74 s this way:
            # between the five quarter stops it runs only where two parts newly touch. NOT seen by either test: a
            # thing thinner than the path between two stops that the group swallows whole, its faces never cut -
            # the depth test asks whether the GROUP's surface is inside another, not the other way round)
            skip = set(_chain(joints, g)) | set(moving)
            for t_ in testers:
                deep = {} if not (touched or rbx_travel.is_quarter(end, j["min"], j["max"])) else penetration(
                    objs, t_, skip, spacing, tol, memo if t_ == g else {})
                for h, (n, mid, who) in sorted(deep.items(), key=lambda t: -t[1][0]):
                    if n >= 3 and not hit:
                        say((t_, h), si, end, f"{j['name']} at {end:g}{unit}{_carried(joints, t_, g, vals_)} drives "
                                              f"into '{h}' ({n} surface points inside it, around {mid}"
                                              f"{': ' + who if who else ''})")
                        hit = True
            if hit or rbx_travel.is_quarter(end, j["min"], j["max"]):   # (the five named stops, and every hit)
                facts[f"{j['name']}@{end:g}"] = "drives in" if hit else "clear"
            for k in moving:
                objs[k].matrix_world = rest[k]
        for line_, last_ in runs:   # (a part driven into over a stretch of the travel: say the stretch, once)
            if last_ is not None:
                unit = "°" if j["kind"] == "hinge" else " studs"
                problems[line_] += f" - and on to {last_:g}{unit}"
        for k in staged:  # (the sequence's earlier joints back to rest)
            objs[k].matrix_world = rest[k]
        bpy.context.view_layer.update()
    return problems, facts


# ---------------------------------------------------------------- line-art renders (the schematic's views)
NOT_PARTS = ("glass", "marks")  # mesh groups that are not parts of their own (lenses, markings ride on parts)


def _white_material():
    white = bpy.data.materials.new("_LineArtWhite")
    white.use_nodes = True
    nt = white.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1, 1, 1, 1)
    nt.links.new(em.outputs["Emission"], nt.nodes.get("Material Output").inputs["Surface"])
    return white


def _backface_material():
    """white where the first surface seen is a FRONT face, red where it is a BACK face: with a section clip
    plane, back faces are exactly where the plane cuts through solid material (the hatched area)."""
    m = bpy.data.materials.new("_SectionMask")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (1, 1, 1, 1)
    mix.inputs["B"].default_value = (1, 0, 0, 1)
    nt.links.new(geo.outputs["Backfacing"], mix.inputs["Factor"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(mix.outputs["Result"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], nt.nodes.get("Material Output").inputs["Surface"])
    return m


def _freestyle(sc, hidden=True):
    """ISO 128-ish line work: visible edges black + thick; hidden edges grey, thin, dashed."""
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"
    vl = bpy.context.view_layer
    fs = vl.freestyle_settings
    fs.crease_angle = math.radians(140)
    while len(fs.linesets) > 0:
        fs.linesets.remove(fs.linesets[0])

    def lineset(name, visibility, color, thickness, dashed):
        ls = fs.linesets.new(name)
        ls.select_by_visibility = True
        ls.visibility = visibility
        ls.select_silhouette = ls.select_border = ls.select_crease = True
        ls.select_external_contour = True
        ls.linestyle = bpy.data.linestyles.new(f"Kit{name}")
        ls.linestyle.color = color
        ls.linestyle.thickness = thickness
        ls.linestyle.use_dashed_line = dashed
        if dashed:
            ls.linestyle.dash1, ls.linestyle.gap1 = 7, 5
        return ls

    lineset("Visible", "VISIBLE", (0, 0, 0), 2.0, False)
    if hidden:
        lineset("Hidden", "HIDDEN", (0.72, 0.72, 0.72), 0.9, True)
    vl.material_override = _white_material()
    world = bpy.data.worlds.new("_LineArtWorld")
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs[0].default_value = (1, 1, 1, 1)
    sc.world = world
    sc.render.engine = "CYCLES"
    from rbx import cycles_device  # noqa: PLC0415  (rbx imports this module: import at call time)

    cycles_device(sc)
    sc.cycles.samples = 1
    sc.cycles.use_denoising = False
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0  # (a studio render before this must not leave its exposure)


def _bounds(objs):
    cs = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    return (Vector([min(c[i] for c in cs) for i in range(3)]), Vector([max(c[i] for c in cs) for i in range(3)]))


def _project(sc, cam, objs):
    """per group: projected centre + projected bounds (0..1, v from the top) — callouts and part dimensions."""
    from bpy_extras.object_utils import world_to_camera_view

    out = []
    for g, o in sorted(objs.items()):
        cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
        ps = [world_to_camera_view(sc, cam, c) for c in cs]
        c = world_to_camera_view(sc, cam, sum(cs, Vector()) / len(cs))
        out.append({"name": g, "u": round(c.x, 4), "v": round(1 - c.y, 4),
                    "box": [round(min(p.x for p in ps), 4), round(1 - max(p.y for p in ps), 4),
                            round(max(p.x for p in ps), 4), round(1 - min(p.y for p in ps), 4)]})
    return out


def views_waiting(renders_dir, name, key, why=None):
    """this build did NOT render the schematic's views (they are asked for: `kit asset <name> --schematic`) -> what
    the build says about it. A set kept from an older build is marked stale as soon as what it shows has changed
    (its key), so `kit schematic` never draws an old model as today's."""
    import time  # noqa: PLC0415

    meta_path = os.path.join(renders_dir, f"{name}_schematic.json")
    ask = f"lune run kit asset {name} --schematic"
    head = f"skipped ({why})" if why else "not rendered (they are asked for)"
    try:
        with open(meta_path, encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        return f"{head}: the clearance check ran — its sheets: {ask}"
    if not isinstance(old, dict):
        return f"{head}: the clearance check ran — its sheets: {ask}"
    same = old.get("key") == key
    if same != (not old.get("stale")):  # (marked once when the model moves on; cleared if it comes back)
        if same:
            old.pop("stale", None)
        else:
            old["stale"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(old, fh, indent=1)
    if same:
        return f"{head}: the kept views still show this build (lune run kit schematic {name})"
    return f"{head}: the kept views show an OLDER build (stale since {old['stale']}) — {ask}"


def renders(asset, objs, joints, renders_dir, explode=None, key=None, force=False):
    """build/renders/<name>_s_<view>.png + <name>_schematic.json for the schematic composer (kit schematic):
    presentation renders (studio light), then line art at ONE common scale: side / top / front with hidden lines,
    a section (clip plane + back-face mask for hatching), an exploded view and every joint at full travel.
    ON DEMAND: `key` fingerprints everything they show (geometry, baked maps, joints, this code); while it matches
    the last run's and its files exist, nothing is rendered again (-> that meta, with "reused": True); force
    (--rebake) renders anyway."""
    meta_path = os.path.join(renders_dir, f"{asset.name}_schematic.json")
    if key and not force:
        try:
            with open(meta_path, encoding="utf-8") as fh:
                old = json.load(fh)
            files = list(old["present"].values())
            for v in old["views"].values():
                files += [v["file"]] + ([v["mask"]] if "mask" in v else [])
            if old.get("key") == key and all(os.path.isfile(os.path.join(renders_dir, f)) for f in files):
                if old.pop("stale", None):  # (views_waiting marked them; the model is back at what they show)
                    with open(meta_path, "w", encoding="utf-8") as fh:
                        json.dump(old, fh, indent=1)
                return {**old, "reused": True}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
    sc = bpy.context.scene
    keep = set(objs.values())
    hidden_objs = []
    for o in sc.objects:
        if o.type == "MESH" and o not in keep and not o.hide_render:
            o.hide_render = True
            hidden_objs.append(o)
    rest = {g: o.matrix_world.copy() for g, o in objs.items()}
    lo, hi = _bounds(objs.values())
    center, ext = (lo + hi) / 2, hi - lo
    cam = bpy.data.objects.new("SchematicCam", bpy.data.cameras.new("SchematicCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    views = {}

    def aim(direction, focus, persp=False, dist=None, roll_top=False):
        cam.location = focus + direction * (dist or (max(ext) * 4 + 5))
        cam.rotation_euler = (focus - cam.location).to_track_quat("-Z", "Y").to_euler()
        if roll_top:
            cam.rotation_euler = (0, 0, -math.pi / 2)  # muzzle left like the side view; the left side at the bottom
        cam.data.clip_end = max(ext) * 20 + 50

    # ---- presentation (the model sheet): studio light, product shots + the magazine on its own
    present = {}
    asset._studio(list(objs.values()), (0.16, 0.165, 0.18))
    sc.render.engine = "CYCLES"
    from rbx import cycles_device  # noqa: PLC0415

    cycles_device(sc)
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.denoising_use_gpu = sc.cycles.device == "GPU"  # same denoiser (OIDN) on the GPU: 4.8 -> 1.0 s a shot, within 1/255 of the CPU (= a CPU rerun)
    sc.render.film_transparent = False
    shots = [("side", Vector((-1, 0, 0)), True), ("three_quarter", (BL_FROM_RBX @ Vector((-0.75, 0.45, -0.55))).normalized(), False),
             ("rear_quarter", (BL_FROM_RBX @ Vector((0.7, 0.4, 0.65))).normalized(), False)]
    for name, d, ortho in shots:
        cam.data.type = "ORTHO" if ortho else "PERSP"
        cam.data.lens = 70
        sc.render.resolution_x, sc.render.resolution_y = (1800, 900) if name == "side" else (1100, 800)
        if ortho:
            cam.data.ortho_scale = max(ext.y, ext.z * 2) * 1.12
            aim(d, center)
        else:
            rad = ext.length / 2
            aim(d, center, dist=rad / math.tan(math.atan(18 / 70)) * 1.08)
        path = os.path.join(renders_dir, f"{asset.name}_p_{name}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        present[name] = os.path.basename(path)
    slides = [(j["max"] - j["min"], g) for g, j in joints.items() if j["kind"] == "slide"]
    mag_groups = [max(slides)[1]] if slides else []
    if mag_groups:  # one removable part shown on its own (a magazine, a battery, a cartridge...)
        solo = set(mag_groups) | {k for k in objs if any(m in _chain(joints, k) for m in mag_groups)}
        for g, o in objs.items():
            o.hide_render = g not in solo
        mlo, mhi = _bounds([objs[g] for g in solo])
        cam.data.type = "PERSP"
        sc.render.resolution_x, sc.render.resolution_y = 700, 1000
        aim((BL_FROM_RBX @ Vector((-0.8, 0.25, -0.5))).normalized(), (mlo + mhi) / 2, dist=(mhi - mlo).length * 2.1)
        path = os.path.join(renders_dir, f"{asset.name}_p_part.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        present["part"] = os.path.basename(path)
        for o in objs.values():
            o.hide_render = False
    soft = bpy.data.objects.get("StudioSoftbox")
    if soft:
        soft.hide_render = True
    for o in sc.objects:
        if o.type == "LIGHT":
            o.hide_render = True

    # ---- line art at ONE scale (pixels per stud), views aligned by the composer
    _freestyle(sc)
    cam.data.type = "ORTHO"
    pps = min(1900 / (ext.y * 1.08), 1050 / (ext.z * 1.08))

    def shoot(view, direction, w, h, focus=None, clip=None, roll_top=False, hidden=True, mask=False):
        focus = focus if focus is not None else center
        rx, ry = max(64, int(w * 1.08 * pps)), max(64, int(h * 1.08 * pps))
        sc.render.resolution_x, sc.render.resolution_y = rx, ry
        cam.data.ortho_scale = max(w, h) * 1.08
        aim(Vector(direction).normalized(), focus, roll_top=roll_top)
        cam.data.clip_start = (cam.location - focus).length - clip if clip is not None else 0.01
        fs = bpy.context.view_layer.freestyle_settings
        if len(fs.linesets) > 1:
            fs.linesets[1].show_render = hidden
        path = os.path.join(renders_dir, f"{asset.name}_s_{view}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        views[view] = {"file": os.path.basename(path), "res": [rx, ry], "pps": pps, "callouts": _project(sc, cam, objs)}
        if mask:  # the hatching mask: back faces behind the clip plane = cut material
            sc.render.use_freestyle = False
            bpy.context.view_layer.material_override = _backface_material()
            mpath = os.path.join(renders_dir, f"{asset.name}_s_{view}_mask.png")
            sc.render.filepath = mpath
            bpy.ops.render.render(write_still=True)
            views[view]["mask"] = os.path.basename(mpath)
            sc.render.use_freestyle = True
            bpy.context.view_layer.material_override = _white_material()

    shoot("side", (-1, 0, 0), ext.y, ext.z)
    shoot("top", (0, 0, 1), ext.y, ext.x, roll_top=True)
    shoot("front", (0, 1, 0.0001), ext.x, ext.z)
    shoot("section", (1, 0, 0), ext.y, ext.z, clip=0.0, hidden=False, mask=True)
    # exploded: each moving group pushed out along its joint (children follow their parent)
    main_c = sum((objs["main"].matrix_world @ Vector(c) for c in objs["main"].bound_box), Vector()) / 8 if "main" in objs else center
    big = max(ext)
    for g, j in joints.items():
        if g not in objs or j["kind"] == "fixed":
            continue
        travel = (explode or {}).get(g)
        span_ = (j["max"] - j["min"]) if j["kind"] == "slide" else 0.0
        if j.get("explode_axis"):
            direction = _bl(j["explode_axis"]).normalized()
        elif j["kind"] == "slide" and span_ * 1.6 >= big * 0.15:
            direction = _bl(j["axis"]).normalized()
        else:  # short travel or a hinge: out of the frame, away from its centre (in the side plane)
            gc = sum((objs[g].matrix_world @ Vector(c) for c in objs[g].bound_box), Vector()) / 8
            direction = Vector((0, gc.y - main_c.y, gc.z - main_c.z))
            direction = direction.normalized() if direction.length > 1e-4 else _bl(j["axis"]).normalized()
        if travel is None:
            travel = min(max(span_ * 1.6, big * 0.15), big * 0.32)
        m = Matrix.Translation(direction * travel)
        for k in objs:
            if g in _chain(joints, k):
                objs[k].matrix_world = m @ objs[k].matrix_world
    bpy.context.view_layer.update()
    elo, ehi = _bounds(objs.values())
    eext = ehi - elo
    shoot("exploded", (-1, 0, 0), eext.y, eext.z, focus=(elo + ehi) / 2, hidden=False)
    for g, o in objs.items():
        o.matrix_world = rest[g]
    moving_col = bpy.data.collections.new("_Moving")
    sc.collection.children.link(moving_col)
    fs = bpy.context.view_layer.freestyle_settings
    vis = fs.linesets[0]
    vis.select_by_collection = True
    vis.collection = moving_col
    vis.collection_negation = "EXCLUSIVE"
    mv = fs.linesets.new("Moving")
    mv.select_by_visibility = True
    mv.visibility = "VISIBLE"
    mv.select_silhouette = mv.select_border = mv.select_crease = mv.select_external_contour = True
    mv.select_by_collection = True
    mv.collection = moving_col
    mv.linestyle = bpy.data.linestyles.new("KitMoving")
    mv.linestyle.color = (1, 0, 0)
    mv.linestyle.thickness = 2.6
    for g, j in joints.items():
        if g not in objs or j["kind"] == "fixed":
            continue
        for k in objs:
            if g in _chain(joints, k):
                moving_col.objects.link(objs[k])
        m = pose(j, j["max"])
        for k in objs:
            if g in _chain(joints, k):
                objs[k].matrix_world = m @ rest[k]
        bpy.context.view_layer.update()
        mlo, mhi = _bounds(objs.values())
        mext = mhi - mlo
        shoot(f"motion_{j['name']}", (-1, 0, 0), mext.y, mext.z, focus=(mlo + mhi) / 2, hidden=False)
        for k, o in objs.items():
            o.matrix_world = rest[k]
        for o in list(moving_col.objects):
            moving_col.objects.unlink(o)
    bpy.data.collections.remove(moving_col)
    bpy.data.objects.remove(cam)
    bpy.context.view_layer.material_override = None
    sc.render.use_freestyle = False
    for o in hidden_objs:
        o.hide_render = False
    for o in sc.objects:
        if o.type == "LIGHT" and o.name != "StudioSoftbox":
            o.hide_render = False
    size = [round(v, 4) for v in (ext.x, ext.z, ext.y)]  # Roblox x, y, z
    meta = {"asset": asset.name, "size_studs": size, "views": views, "present": present,
            "joints": {g: dict(j) for g, j in joints.items()}, "real_mm_per_stud": getattr(asset, "mm_per_stud", None),
            "groups": sorted(objs), "parts": [g for g in sorted(objs) if not any(t in g for t in NOT_PARTS)],
            "key": key}
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta
