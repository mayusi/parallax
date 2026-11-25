"""rbx_garment.py — CLOTHES that hang like cloth: a garment's panel or tube made as a sheet, DRAPED by Blender's own
cloth simulation on the body (collision with the body parts, its top pinned, its ends pulled into place so the extra
length bunches into folds), then given a real wall (thickness) and a LINING of its own colour inside.

Typed shells round a body read as inflated boxes (the R6 Hero, 2026-10-12: "looks really bad"); a draped sheet has the
folds, the hang and the bunching of real cloth, because physics put them there.

    import rbx_garment as G
    G.tube(a, "LeftSleeve", "coat", centre=(-1.5, 0, 0), half=(0.58, 0.58), y_top=4.04, y_bottom=2.62, slack=1.4,
           group="LeftArm")
    G.drape(a, "LeftSleeve", colliders=["R6LeftArm"], pin_top=True, pull_end=True)   # bunches at the cuff
    G.finish(a, "LeftSleeve", thickness_mm=10, lining="lining")                      # a wall + its lining part

Units: studs (Roblox space: y up, -z front), like every a.* call; a garment's resolution is its sheet's.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import rbx

RBX_FROM_BL = rbx.BL_FROM_RBX.inverted()


def _ring(half, p, n, centre=(0.0, 0.0), t0=0.0, t1=2 * math.pi, closed=True):
    """points of a superellipse (|x/hx|^p + |z/hz|^p = 1: p 2 an ellipse, 4+ a rounded box — a garment round an R6
    block) from angle t0 to t1, t measured from +z (the back) toward -x (the left side)"""
    hx, hz = half
    pts = []
    count = n if closed else n + 1
    for i in range(count):
        t = t0 + (t1 - t0) * i / n
        s, c = math.sin(t), math.cos(t)
        x = -math.copysign(abs(s) ** (2.0 / p), s) * hx
        z = math.copysign(abs(c) ** (2.0 / p), c) * hz
        pts.append((centre[0] + x, centre[1] + z))
    return pts


def sheet(a, name, mat, rows, group="main", closed=True):
    """a garment sheet from rows of points (each row: [(x, y, z)] studs, top row first) -> the part (open: no wall
    yet; finish() gives it one)"""
    n = len(rows[0])
    verts = [v for row in rows for v in row]
    faces = []
    span = n if closed else n - 1
    for j in range(len(rows) - 1):
        for i in range(span):
            i2 = (i + 1) % n
            faces.append((j * n + i, j * n + i2, (j + 1) * n + i2, (j + 1) * n + i))
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in verts]
    for f in faces:
        bm.faces.new([vs[k] for k in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return a._emit(name, bm, mat, group, (0, 0, 0), (0, 0, 0)) or _part(a, name)


def tube(a, name, mat, centre, half, y_top, y_bottom, slack=1.0, flare=1.0, p=4.0, around=48, along=None,
         group="main", t0=0.0, t1=2 * math.pi, closed=True, half_bottom=None, centre_bottom=None):
    """a tube (a sleeve, a trouser leg) or, with t0..t1 and closed=False, a panel round part of a body (a coat's
    skirt): rings of half-size `half` (x, z) about centre (x, z) from y_top down `slack` times the length it covers
    (the extra bunches when drape(pull_end=True) lifts its end to y_bottom), flaring to half_bottom (or half * flare)
    and its centre moving to centre_bottom (a trouser leg fitted at the hip, baggy at the boot, its inner side kept flat
    on the leg's inner face)"""
    length = (y_top - y_bottom) * slack
    along = along or max(12, int(length / 0.03))
    hb = half_bottom or (half[0] * flare, half[1] * flare)
    rows = []
    for j in range(along + 1):
        f = j / along
        h = (half[0] + (hb[0] - half[0]) * f, half[1] + (hb[1] - half[1]) * f)
        y = y_top - length * f
        cb = centre_bottom or centre
        c = (centre[0] + (cb[0] - centre[0]) * f, centre[2] + (cb[2] - centre[2]) * f)
        rows.append([(x, y, z) for x, z in _ring(h, p, around, c, t0, t1, closed)])
    return sheet(a, name, mat, rows, group=group, closed=closed)


def _part(a, name):
    for o, _g in a.parts:
        if o.name == name:
            return o
    raise ValueError(f'garment: no part "{name}"')


def _rbx(o, co):
    return RBX_FROM_BL @ o.matrix_world @ co


def drape(a, name, colliders, pin_top=True, pull_end=False, pin=None, frames=60, mass=0.3, stiffness=15.0,
          bending=0.5, gravity=1.0, thickness_out=0.015, quality=8, end_y=None):
    """drape part `name` (a sheet) by Blender's cloth simulation: `colliders` (part names: the body) push it out,
    pin_top holds its top row, pull_end lifts its bottom row up to y `end_y` (default: what the tube was made to
    cover) so the slack bunches; pin(x, y, z) -> True holds any other vertex. bending: low = soft folds, high = stiff
    leather. The result replaces the part's mesh (no modifiers left). -> facts {seconds, moved_max, folds}"""
    import time  # noqa: PLC0415

    t = time.time()
    o = _part(a, name)
    sc = bpy.context.scene
    me = o.data
    ys = [_rbx(o, v.co).y for v in me.vertices]
    top, bottom = max(ys), min(ys)
    eps = (top - bottom) * 0.004 + 1e-4
    pinned = [v.index for v, y in zip(me.vertices, ys) if pin_top and y > top - eps]
    if pin is not None:
        pinned += [v.index for v in me.vertices if pin(*_rbx(o, v.co))]
    end = [v.index for v, y in zip(me.vertices, ys) if y < bottom + eps] if pull_end else []
    vg = o.vertex_groups.new(name="kit_pin")
    if pinned or end:
        vg.add(sorted(set(pinned + end)), 1.0, "REPLACE")
    hook_obj = None
    if end:
        lift = (end_y if end_y is not None else o.get("kit_cover_bottom", bottom)) - bottom
        hook_obj = bpy.data.objects.new(f"{name}_hook", None)
        sc.collection.objects.link(hook_obj)
        # (parented to the garment: it moves in the garment's own frame — Roblox space. Unparented, its world frame
        #  differs from the part's by BL_FROM_RBX's quarter turn, and the hook TURNED the end ring and flung it)
        hook_obj.parent = o
        hm = o.modifiers.new("kit_hook", "HOOK")
        hm.object = hook_obj
        hm.vertex_indices_set(end)
        hook_obj.location = (0, 0, 0)
        hook_obj.keyframe_insert("location", frame=1)
        hook_obj.location = (0, lift, 0)
        hook_obj.keyframe_insert("location", frame=max(2, int(frames * 0.6)))
        sc.frame_set(1)
        hm.matrix_inverse = (o.matrix_world.inverted() @ hook_obj.matrix_world).inverted()
    cols = []
    for cn in colliders:
        c = _part(a, cn)
        m = c.modifiers.new("kit_collision", "COLLISION")
        c.collision.thickness_outer = thickness_out
        cols.append((c, m))
    cl = o.modifiers.new("kit_cloth", "CLOTH")
    s = cl.settings
    s.quality = int(quality)
    s.mass = float(mass)
    s.tension_stiffness = s.compression_stiffness = float(stiffness)
    s.bending_stiffness = float(bending)
    s.vertex_group_mass = "kit_pin"
    s.effector_weights.gravity = float(gravity)
    cs = cl.collision_settings
    cs.use_collision = True
    cs.distance_min = 0.01
    cs.use_self_collision = True
    cs.self_distance_min = 0.008
    cl.point_cache.frame_start, cl.point_cache.frame_end = 1, int(frames)
    before = [v.co.copy() for v in me.vertices]
    sc.frame_start = 1
    for f in range(1, int(frames) + 1):
        sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    new = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    for m in list(o.modifiers):
        o.modifiers.remove(m)
    o.vertex_groups.clear()
    old = o.data
    o.data = new
    new.name = name
    bpy.data.meshes.remove(old)
    for c, m in cols:
        c.modifiers.remove(m)
    if hook_obj is not None:
        bpy.data.objects.remove(hook_obj, do_unlink=True)
    sc.frame_set(1)
    moved = max(((v.co - b).length for v, b in zip(new.vertices, before)), default=0.0)
    ys2 = [v.co.y for v in new.vertices]
    return {"seconds": round(time.time() - t, 1), "moved_max": round(moved, 3),
            "y": [round(min(ys2), 3), round(max(ys2), 3)], "y_before": [round(bottom, 3), round(top, 3)]}


def finish(a, name, thickness_mm, lining=None, lining_mm=1.5, smooth=1):
    """give a draped sheet its WALL (thickness_mm, outward: the body stays clear) and, with lining=<material>, a lining
    part <name>Lining inside it (the coat's dark inside, seen at the open front and the hems). smooth: subdivision
    levels (a sheet's polygons smoothed before the wall)"""
    o = _part(a, name)
    mm = float(a.mm_per_stud or 280.0)
    if smooth:
        sub = o.modifiers.new("kit_sub", "SUBSURF")
        sub.levels = sub.render_levels = int(smooth)
    group = next(g for p, g in a.parts if p is o)
    if lining:
        dg = bpy.context.evaluated_depsgraph_get()
        src = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        verts = [tuple(v.co) for v in src.vertices]
        faces = [list(p.vertices) for p in src.polygons]
        bpy.data.meshes.remove(src)
        bm = bmesh.new()
        vs = [bm.verts.new(v) for v in verts]
        for f in faces:
            bm.faces.new([vs[k] for k in f])
        a._emit(f"{name}Lining", bm, lining, group, (0, 0, 0), (0, 0, 0))
        lo = _part(a, f"{name}Lining")
        lo.matrix_world = o.matrix_world.copy()
        so = lo.modifiers.new("kit_wall", "SOLIDIFY")
        so.thickness = float(lining_mm) / mm
        so.offset = -1.0          # inside the sheet
        so.use_even_offset = False   # (even thickness divides by a fold's angle: a tight bunch flung a sleeve 88 studs)
        so.use_quality_normals = True
        _apply(lo)
    so = o.modifiers.new("kit_wall", "SOLIDIFY")
    so.thickness = float(thickness_mm) / mm
    so.offset = 1.0 if not lining else 1.0
    so.use_even_offset = False   # (even thickness divides by a fold's angle: a tight bunch flung a sleeve 88 studs)
    so.use_quality_normals = True
    so.use_rim = True
    _apply(o)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def _apply(o):
    dg = bpy.context.evaluated_depsgraph_get()
    new = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    for m in list(o.modifiers):
        o.modifiers.remove(m)
    old = o.data
    mats = list(old.materials)
    o.data = new
    for m in mats:
        if m.name not in [x.name for x in new.materials if x]:
            new.materials.append(m)
    bpy.data.meshes.remove(old)
    for p in new.polygons:
        p.use_smooth = True


# ---- does it clip when the body MOVES? ------------------------------------------------------------------------------
# R6's joints (Roblox space, the character at rest: the HumanoidRootPart at y 3): every limb swings about an axis along
# x — the arms through y 3.5 (the shoulders), the legs through y 2 (the hips)
R6_PIVOTS = {"LeftArm": (3.5, 0.0), "RightArm": (3.5, 0.0), "LeftLeg": (2.0, 0.0), "RightLeg": (2.0, 0.0), "Torso": None}
R6_WALK = {"stride": {"LeftLeg": 35, "RightLeg": -35, "LeftArm": -40, "RightArm": 40},
           "stride_back": {"LeftLeg": -35, "RightLeg": 35, "LeftArm": 40, "RightArm": -40},
           "arms_up": {"LeftArm": 90, "RightArm": 90}}


def _swing(p, deg, pivot):
    """p (x, y, z) turned `deg` about the x axis through (y, z) = pivot (positive: the limb swings FORWARD, to -z)"""
    if not deg or pivot is None:
        return p
    a = math.radians(deg)
    y, z = p[1] - pivot[0], p[2] - pivot[1]
    return (p[0], pivot[0] + y * math.cos(a) + z * math.sin(a), pivot[1] - y * math.sin(a) + z * math.cos(a))


def clip_check(a, body, poses=None, pivots=None, tol_mm=2.0, step=3):
    """swing the body and its clothes through `poses` ({pose: {group: degrees}}, default R6_WALK) and measure how far
    each clothing group cuts INTO the body parts it is not worn on. body: {group: mannequin part name} (the R6 box each
    group rides). -> {pose: {group: {"into": part, "share": fraction of its vertices inside, "depth_mm": deepest}}} —
    only what clips more than tol_mm. A skirt that swings into the other leg, a sleeve into the torso: found here, by
    numbers, before a playtest"""
    poses = poses or R6_WALK
    pivots = pivots or R6_PIVOTS
    mm = float(a.mm_per_stud or 280.0)
    boxes = {}
    for g, pname in body.items():
        o = _part(a, pname)
        pts = [_rbx(o, Vector(c)) for c in o.bound_box]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        boxes[g] = (lo, hi)
    cloth = {}
    for o, g in a.parts:
        if g in body and o.name not in body.values():
            vs = o.data.vertices
            cloth.setdefault(g, []).extend((tuple(_rbx(o, vs[i].co)), o.name) for i in range(0, len(vs), step))
    out = {}
    for pose, angles in poses.items():
        res = {}
        for g, pts in cloth.items():
            names = [n for _p, n in pts]
            moved = [_swing(p, angles.get(g, 0), pivots.get(g)) for p, _n in pts]
            for other, (lo, hi) in boxes.items():
                if other == g:
                    continue
                deg = angles.get(other, 0)
                piv = pivots.get(other)
                # into the OTHER part's own frame (undo its swing), then a box test
                local = [_swing(p, -deg, piv) for p in moved]
                deep = []
                for p, n in zip(local, names):
                    d = min(p[0] - lo[0], hi[0] - p[0], p[1] - lo[1], hi[1] - p[1], p[2] - lo[2], hi[2] - p[2]) * mm
                    if d > tol_mm:
                        deep.append((d, n))
                if deep:
                    worst = max(deep)
                    prev = res.get(g)
                    if prev is None or worst[0] > prev["depth_mm"]:
                        res[g] = {"into": body[other], "share": round(len(deep) / len(local), 4),
                                  "depth_mm": round(worst[0], 1), "part": worst[1]}
        if res:
            out[pose] = res
    return out



def pose(a, angles, pivots=None):
    """PREVIEW a pose: every part of each group (its body block and its clothes) swung by angles {group: degrees}
    about its joint (R6_PIVOTS) — the render then shows the outfit mid-stride (a skirt half riding its leg, a sleeve
    on a raised arm). Preview only: build the game version unposed."""
    pivots = pivots or R6_PIVOTS
    for o, g in a.parts:
        if g not in angles and o.name.startswith("R6"):
            g = o.name[2:]                       # (the preview body's blocks, R6<Group>, move with their group)
        deg = angles.get(g, 0)
        if not deg:
            continue
        inv = o.matrix_world.inverted() @ rbx.BL_FROM_RBX
        for v in o.data.vertices:
            v.co = inv @ Vector(_swing(tuple(_rbx(o, v.co)), deg, pivots.get(g)))
        o.data.update()


def coverage(a, body, step=0.05, reach_mm=60.0, faces=("front", "back", "left", "right")):
    """how much of each body block's FACES its own clothes cover (the clothes in its group — the ones that move with
    it): rays cast outward from a grid of points on each face; a face share under 1 is bare body showing (an R6
    leg's grey inner face mid-stride, a gap at a cuff). -> {group: {face: share}} and the worst bare spots"""
    from mathutils.bvhtree import BVHTree  # noqa: PLC0415

    mm = float(a.mm_per_stud or 280.0)
    out, bare = {}, {}
    for g, pname in body.items():
        o = _part(a, pname)
        pts = [_rbx(o, Vector(c)) for c in o.bound_box]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        verts, polys = [], []
        for o2, g2 in a.parts:
            if g2 != g or o2.name in body.values():
                continue
            base = len(verts)
            verts += [tuple(_rbx(o2, v.co)) for v in o2.data.vertices]
            polys += [tuple(base + i for i in p.vertices) for p in o2.data.polygons]
        if not polys:
            out[g] = {f: 0.0 for f in faces}
            continue
        tree = BVHTree.FromPolygons(verts, polys)
        spec = {"front": (2, -1), "back": (2, 1), "left": (0, -1), "right": (0, 1)}   # (axis, sign): -z is the front
        res = {}
        for f in faces:
            ax, sg = spec[f]
            u_ax, v_ax = [i for i in range(3) if i != ax]
            n = Vector([0, 0, 0])
            n[ax] = sg
            hits = total = 0
            u = lo[u_ax] + step / 2
            while u < hi[u_ax]:
                v = lo[v_ax] + step / 2
                while v < hi[v_ax]:
                    p = [0.0, 0.0, 0.0]
                    p[ax] = hi[ax] if sg > 0 else lo[ax]
                    p[u_ax], p[v_ax] = u, v
                    total += 1
                    hit = tree.ray_cast(Vector(p) - n * 0.002, n, 1.0)
                    # covered: clothing within reach outside the face — or the face point already INSIDE clothing
                    # (the ray leaves a solid: a boot's sole round a foot), which a short ray never sees
                    if hit[0] is not None and (hit[3] <= reach_mm / mm or hit[1].dot(n) > 0):
                        hits += 1
                    else:
                        bare.setdefault(f"{g}.{f}", []).append(tuple(round(x, 2) for x in p))
                    v += step
                u += step
            res[f] = round(hits / max(1, total), 3)
        out[g] = res
    def bands(pts):   # bare points by height, 0.1 stud bands: where on the face the body shows
        h = {}
        for p in pts:
            k = round(int(p[1] / 0.1) * 0.1, 1)
            h[k] = h.get(k, 0) + 1
        return dict(sorted(h.items()))
    return out, {k: {"points": len(v), "by_height": bands(v)} for k, v in bare.items()}
