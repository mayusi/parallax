"""sharpen_part.py — the Blender side of SHARPENING a generated part (`lune run kit sharpen <part.glb>`; the
arithmetic and the why: kit/gen/sharpen_math.py). One step per run, all in a work folder:

    blender -b --factory-startup --python-exit-code 2 -P kit/gen/sharpen_part.py -- <step> ...
        fold    <in.glb> <out.glb> [--keep <deg>] [--flare <factor> [--flare-from 0.33] [--flare-to 0.50]]
                [--tail <factor> [--tail-from 0.36] [--tail-to 0.52]]
                [--level <width> [--level-from 0.33] [--level-to 0.50]]
                [--snout <factor>] [--nod <deg>] [--faces <n>] [--drop x0,x1,a0,a1,z0,z1]
                                                         lay a splayed pair of wings straight back; (flare) move
                                                         them out to the width of what they lie on while the head
                                                         keeps its own; (tail) lengthen what lies behind the
                                                         head - a generated head is as long as its wings, a
                                                         carved one much smaller; (level) bring the body behind the head
                                                         to ONE width (a share of its length) - a solid wedge laid
                                                         on flat flanks; (snout) lengthen the muzzle; (nod) pitch
                                                         the head down; (faces) thin it to a triangle budget;
                                                         (drop) FIRST cut a box of it away and cap the cut - a
                                                         stray rod, strut or stand the generator added - in
                                                         fractions of its own box: across x0..x1, along from the
                                                         nose a0..a1, up z0..z1. It
                                                         keeps the part's maps: an already sharpened part can be
                                                         fitted again for a second place on the model
        prep    <in.glb> <work> [--face <yaw>] [--size 4096] [--voxel 0.0042] [--keep-skin]
                [--keep-open x0,y0,z0>x1,y1,z1@w ...]   an OPENING that must stay open (a bore, a strap's slot,
                                                         a sight line): from one point to the other, in fractions
                                                         of the part's own box (x, y, z, Blender's axes), w across
                                                         (a fraction of its longest side) - carved through the new
                                                         skin (a voxel remesh closes what is narrower than about two
                                                         voxels) and looked down: a way still stopped fails prep
        render  <work> <view>                            -> <work>/<view>_in.png + <view>_cam.json
        project <work> <view> <picture> [--match <the first view's picture>]
        final   <work> <out.glb> [--metal gold] [--normal 1.0]

A view is one of sharpen_math.VIEWS (side_left, front, side_right, front_left, front_right, top). `render` shows the
part as it is NOW (with every earlier view's detail), so the redraw of a later view agrees with the earlier ones.
`prep` gives the part a NEW SKIN first: one watertight surface of the same shape (a voxel remesh, the biggest piece
kept, its own UV atlas) with the generator's colour baked across. A generator's skin folds through itself and
pinches (the wolf: 80 edges with 3-4 faces); a build's import then leaves a hole there or winds patches of it
inward - black cracks over the whole part, twice (the old wolf's round 9, and this one's round 3). --keep-skin
skips it (a part that is already one clean surface). `final` writes the part with its game maps: colour (its own,
or carried onto a metal), roughness, a tangent-space normal map, metallic 0.98 said outright (a.import_mesh keeps a
declared metal). Every step ends with one JSON line (summary, next_action).
"""

import json
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sharpen_math as M  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


def opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def load_glb(path):
    """a GLB as ONE object in the scene's own frame (its transform applied) -> the object"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not objs:
        raise SystemExit(f"{path}: no mesh in it")
    bpy.context.view_layer.objects.active = objs[0]
    for o in objs:
        o.select_set(True)
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.data.transform(obj.matrix_world)
    obj.matrix_world.identity()
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def coords(me, what="co"):
    a = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get(what, a)
    return a.reshape(-1, 3)


def pixels(img):
    a = np.zeros(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def save_image(arr, path, data=False):
    """arr (H, W) or (H, W, 3), 0..1, row 0 at the BOTTOM (Blender's order), written as it is (sRGB values for a
    colour, plain values for data)"""
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    h, w = arr.shape[:2]
    img = bpy.data.images.new("out", w, h, alpha=False)
    if data:
        img.colorspace_settings.name = "Non-Color"
    out = np.ones((h, w, 4), dtype=np.float32)
    out[..., :3] = np.clip(arr, 0.0, 1.0)
    img.pixels.foreach_set(out.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def gpu(sc):
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception:  # noqa: BLE001  (no GPU for Cycles: the CPU bakes it, slower)
        pass


def the_part():
    return next(o for o in bpy.context.scene.objects if o.type == "MESH")


def state(work, **new):
    path = os.path.join(work, "state.json")
    data = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    if new:
        data.update(new)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    return data


def weld_seams(me):
    """a GLB's vertices are split along every UV seam: weld them back into ONE surface (the UVs live on the face
    corners and stay) -> the number of OPEN edges left (0 = a closed skin)"""
    import bmesh  # noqa: PLC0415

    bm = bmesh.new()
    bm.from_mesh(me)
    span = max((max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts)) for i in range(3)) if bm.verts else 1.0
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(span, 1e-9) * 1e-6)   # (the kit's own import welds at this)
    left = sum(1 for e in bm.edges if e.is_boundary)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return left


def cap_loops(bm, rim):
    """close every loop of these boundary edges with a fan from its middle - any loop, flat or not, also one that
    touches itself (bmesh's holes_fill left a jagged cut open: 37 edges on the fixture) -> (loops closed, edges of
    loops that do not close, left as they are)"""
    rim = set(rim)
    at = {}
    for e in rim:
        for v in e.verts:
            at.setdefault(v, []).append(e)
    closed = left = 0

    def fan(ring):
        mid = bm.verts.new(sum((p.co for p in ring), ring[0].co * 0.0) / len(ring))
        for i, p in enumerate(ring):
            bm.faces.new((p, ring[(i + 1) % len(ring)], mid))

    while rim:
        first = rim.pop()
        loop, v, walked = [first.verts[0]], first.verts[1], 1
        where = {loop[0]: 0}
        while v is not loop[0]:
            if v in where:                            # the rim touches itself here: that ring is closed on its own
                ring = loop[where[v]:]                # (one fan through a vertex twice pinched 12 edges on the wolf)
                for p in ring[1:]:
                    del where[p]
                del loop[where[v] + 1:]
                if len(ring) >= 3:
                    fan(ring)
                    closed += 1
                else:
                    left += len(ring)
            else:
                where[v] = len(loop)
                loop.append(v)
            nxt = next((e for e in at[v] if e in rim), None)
            if nxt is None:
                break
            rim.discard(nxt)
            walked += 1
            v = nxt.other_vert(v)
        if v is not loop[0] or len(loop) < 3:
            left += len(loop)
            continue
        fan(loop)
        closed += 1
    return closed, left


def keep_biggest(bm):
    """only the biggest connected piece stays (specks inside a hollow, a blob cut loose) -> faces removed"""
    import bmesh  # noqa: PLC0415

    seen, best = set(), []
    for f in bm.faces:
        if f in seen:
            continue
        stack, island = [f], []
        seen.add(f)
        while stack:
            g = stack.pop()
            island.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
        if len(island) > len(best):
            best = island
    keep = set(best)
    gone = [f for f in bm.faces if f not in keep]
    if gone:
        bmesh.ops.delete(bm, geom=gone, context="FACES")
    return len(gone)


def hollow_share(bm, voxel, sample=3000):
    """how much of a closed surface is a THIN WALL with a hollow behind it: the share of (sampled) faces from which
    a ray going inward meets the far side within 4 voxels (or 3% of the part's size, whichever is more). A solid:
    next to none. A generator's crust: nearly all. (A part that is truly a thin plate counts too: shedding takes
    nothing from it, every face of a plate sees out.)"""
    bm.faces.ensure_lookup_table()
    if not len(bm.faces):
        return 0.0
    span = max(max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts) for i in range(3))
    near = max(4.0 * voxel, 0.03 * span)
    tree = BVHTree.FromBMesh(bm)
    thin = met = 0
    for i in range(0, len(bm.faces), max(1, len(bm.faces) // sample)):
        f = bm.faces[i]
        hit = tree.ray_cast(f.calc_center_median() - f.normal * (voxel * 0.25), -f.normal)
        if hit[0] is not None:
            met += 1
            thin += hit[3] < near
    return thin / met if met else 0.0


def shed_inner_wall(bm, voxel, directions=48):
    """a generator's mesh is a thin crust: an outer wall and an inner one a voxel behind it. Where the crust has gaps
    the two are ONE surface, and a new skin kept both: half its triangles and half its colour map on an inside nobody
    sees (the launcher's nose wolf: 446,224 triangles, 98.5% of them a double wall). A face is OUTSIDE when a ray from
    it escapes in some direction; the others go, and every loop that leaves - the crust's gaps among them - is closed
    with a fan -> faces removed"""
    import bmesh  # noqa: PLC0415

    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    k = np.arange(directions) + 0.5                   # (directions spread evenly over the sphere)
    polar, turn = np.arccos(1.0 - 2.0 * k / directions), np.pi * (1.0 + 5.0 ** 0.5) * k
    dirs = np.stack([np.cos(turn) * np.sin(polar), np.sin(turn) * np.sin(polar), np.cos(polar)], axis=1)
    rays = [Vector(d) for d in dirs.tolist()]
    facing = np.array([f.normal[:] for f in bm.faces]) @ dirs.T > 0.15
    doomed = []
    for i, f in enumerate(bm.faces):
        start = f.calc_center_median() + f.normal * (voxel * 0.3)
        if not any(tree.ray_cast(start, rays[j])[0] is None for j in np.flatnonzero(facing[i]).tolist()):
            doomed.append(f)
    if doomed:
        was = {e for e in bm.edges if e.is_boundary}
        bmesh.ops.delete(bm, geom=doomed, context="FACES")
        cap_loops(bm, {e for e in bm.edges if e.is_boundary and e not in was})
        keep_biggest(bm)
    return len(doomed)


def drop_box(me, f):
    """cut a box of the part AWAY and cap what the cut opens -> faces removed. `f` = (x0, x1, a0, a1, z0, z1),
    fractions of the part's own box: across, along from the nose (-Y), up. A stray piece the generator added (the
    heel wolf's rod along its top, read off the picture's back edge): no fit can use it and a new skin keeps it"""
    import bmesh  # noqa: PLC0415

    weld_seams(me)                                    # (a GLB's seams are boundaries too: only the cut is capped)
    bm = bmesh.new()
    bm.from_mesh(me)
    lo = [min(v.co[i] for v in bm.verts) for i in range(3)]
    hi = [max(v.co[i] for v in bm.verts) for i in range(3)]
    b0 = [lo[i] + (hi[i] - lo[i]) * f[2 * i] for i in range(3)]
    b1 = [lo[i] + (hi[i] - lo[i]) * f[2 * i + 1] for i in range(3)]
    was = {e for e in bm.edges if e.is_boundary}
    doomed = [fc for fc in bm.faces if all(b0[i] <= fc.calc_center_median()[i] <= b1[i] for i in range(3))]
    if doomed:
        bmesh.ops.delete(bm, geom=doomed, context="FACES")
        # (the cut's rim is jagged - whole faces went - and can touch itself: each loop gets a fan)
        cap_loops(bm, {e for e in bm.edges if e.is_boundary and e not in was})
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        me.update()
    bm.free()
    return len(doomed)


def step_fold(argv):
    src, dst = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    obj = load_glb(src)
    box, dropped = opt(argv, "--drop", ""), 0
    if box:
        f = [float(v) for v in box.split(",")]
        if len(f) != 6 or not all(0.0 <= f[2 * i] < f[2 * i + 1] <= 1.0 for i in range(3)):
            return emit("fail", f"fold: --drop {box} is not a box (x0,x1,a0,a1,z0,z1: fractions of the part's own box, "
                                "each pair rising within 0..1)", "across x0..x1, along from the nose a0..a1, up z0..z1")
        dropped = drop_box(obj.data, f)
        if not dropped:
            return emit("fail", f"fold: --drop {box} holds no face of {os.path.basename(src)}",
                        "look at the part from above and from the side and give the box of the piece to cut away")
    co = coords(obj.data)
    mid = (co[:, 0].min() + co[:, 0].max()) / 2.0
    along, across = co[:, 1], co[:, 0] - mid          # (nose to -Y, the wings back to +Y, across = X)
    split = M.find_split(along, across)
    if split is None:
        return emit("fail", f"fold: {os.path.basename(src)} has no place where two wings part behind a head",
                    "it is one body: sharpen it as it is (kit sharpen without --fold)")
    wings = M.splay(along, across, split)
    a2, c2 = M.fold(along, across, split, wings, keep=opt(argv, "--keep", 0.0))
    factor = opt(argv, "--flare", 1.0)
    if factor != 1.0:
        c2 = M.flare(a2, c2, factor, opt(argv, "--flare-from", 0.33), opt(argv, "--flare-to", 0.50))
    # the head's fits first (they read the part as it was generated), then the tail, then the level (it reads the
    # final length)
    longer, down = opt(argv, "--snout", 1.0), opt(argv, "--nod", 0.0)
    up = co[:, 2]
    if longer != 1.0:
        a2 = M.snout(a2, longer)
    if down:
        a2, up = M.nod(a2, up, down)
    back = opt(argv, "--tail", 1.0)
    if back != 1.0:
        a2 = M.tail(a2, back, opt(argv, "--tail-from", 0.36), opt(argv, "--tail-to", 0.52))
    even = opt(argv, "--level", 0.0)
    if even:
        c2 = M.level(a2, c2, even, opt(argv, "--level-from", 0.33), opt(argv, "--level-to", 0.50))
    co[:, 1], co[:, 0], co[:, 2] = a2, c2 + mid, up
    obj.data.vertices.foreach_set("co", co.ravel())
    obj.data.update()
    budget = opt(argv, "--faces", 0)
    count = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if budget and count > budget:
        # thinned as a GLB is read (split along every UV seam), the two sides of each seam move apart and the skin
        # opens: the launcher's second wolf came out with 38,201 open edges and failed its build's closed-surface
        # gate. So the seams are welded first; the collapse then keeps the UV islands (its maps still fit)
        was_open = weld_seams(obj.data)
        dec = obj.modifiers.new("Budget", "DECIMATE")
        dec.decimate_type, dec.ratio = "COLLAPSE", max(0.01, float(budget) / count)
        thin = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        obj.modifiers.remove(dec)
        old, obj.data = obj.data, thin
        bpy.data.meshes.remove(old)
        if "custom_normal" in obj.data.attributes:    # (the old surface's normals: the thinned one shades by its own)
            obj.data.attributes.remove(obj.data.attributes["custom_normal"])
        for p in obj.data.polygons:
            p.use_smooth = True
        now_open = weld_seams(obj.data)
        if now_open > was_open:
            return emit("fail", f"fold: thinning {count:,} -> {budget:,} triangles opened the skin ({now_open:,} open "
                                f"edges, {was_open:,} before): a build's closed-surface gate would refuse it",
                        "thin it less (a larger --faces), or leave it whole: the part must stay one closed skin")
    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB")
    before, after = float(across.max() - across.min()), float(c2.max() - c2.min())
    emit("pass", (f"fold: a box of it cut away ({dropped:,} faces) and capped, " if dropped else "fold: ")
                 + f"wings splayed {wings[0][0]:.1f} / {wings[1][0]:.1f} degrees laid straight back"
                 + (f", flared x{factor:g} behind the head" if factor != 1.0 else "")
                 + (f", what lies behind the head x{back:g} as long" if back != 1.0 else "")
                 + (f", its flanks levelled to {even:g} of its length behind the head" if even else "")
                 + (f", muzzle x{longer:g}" if longer != 1.0 else "") + (f", head nodded {down:g} degrees" if down else "")
                 + (f", thinned {count:,} -> {sum(len(p.vertices) - 2 for p in obj.data.polygons):,} triangles"
                    if budget and count > budget else "")
                 + f" - width {before:.3f} -> {after:.3f} of a length {float(a2.max() - a2.min()):.3f}",
         f"LOOK at it from above and from the front beside the reference, then: kit sharpen {dst}",
         out=dst.replace("\\", "/"), splay=[round(w[0], 2) for w in wings])


def new_skin(obj, voxel, solid=True):
    """ONE watertight, outward surface of the same shape, with its own UV atlas -> (the new object, facts). A voxel
    remesh at `voxel` (the part's own units), the biggest piece kept (specks inside a hollow go); and SOLID: where
    more than a fifth of it is a thin wall with a hollow behind (a generator's crust with gaps: its inner wall came
    through the remesh attached), the inner wall is removed and its gaps closed (shed_inner_wall). solid=False keeps
    it as the remesh left it (the fixture's control)"""
    import bmesh  # noqa: PLC0415

    bpy.ops.object.select_all(action="DESELECT")
    skin = obj.copy()
    skin.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(skin)
    skin.data.materials.clear()
    bpy.context.view_layer.objects.active = skin
    skin.select_set(True)
    skin.data.remesh_voxel_size = float(voxel)
    skin.data.remesh_voxel_adaptivity = 0.0
    skin.data.use_remesh_fix_poles = False
    bpy.ops.object.voxel_remesh()
    bm = bmesh.new()
    bm.from_mesh(skin.data)

    def outward():
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if bm.calc_volume(signed=True) < 0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces)

    keep_biggest(bm)
    outward()
    hollow, shed, hollow_now = hollow_share(bm, voxel), 0, None
    if solid and hollow > 0.2:
        shed = shed_inner_wall(bm, voxel)
        outward()
        hollow_now = hollow_share(bm, voxel)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    facts = {"triangles": len(bm.faces), "open_edges": sum(1 for e in bm.edges if e.is_boundary),
             "pinched_edges": sum(1 for e in bm.edges if len(e.link_faces) > 2),
             "opposite_windings": sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous),
             "hollow": round(hollow, 4), "inner_faces_removed": shed,
             "hollow_after": None if hollow_now is None else round(hollow_now, 4)}
    bm.to_mesh(skin.data)
    bm.free()
    for p in skin.data.polygons:
        p.use_smooth = True
    bpy.ops.object.select_all(action="DESELECT")
    skin.select_set(True)
    bpy.context.view_layer.objects.active = skin
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.25, island_margin=0.0015)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.0015)
    bpy.ops.object.mode_set(mode="OBJECT")
    return skin, facts


def bake_across(old, skin, image, voxel, size):
    """the old skin's colour (its own map, on its own UVs) baked onto the new skin's atlas -> pixels (H, W, 4)"""
    sc = bpy.context.scene
    src = bpy.data.materials.new("old_colour")
    src.use_nodes = True
    nt = src.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    emission = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(emission.outputs["Emission"], nt.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    nt.links.new(tex.outputs["Color"], emission.inputs["Color"])
    old.data.materials.clear()
    old.data.materials.append(src)
    dst = bpy.data.materials.new("new_atlas")
    dst.use_nodes = True
    target = dst.node_tree.nodes.new("ShaderNodeTexImage")
    target.image = bpy.data.images.new("across", size, size, alpha=False, float_buffer=True)
    target.image.colorspace_settings.name = "Non-Color"
    dst.node_tree.nodes.active = target
    target.select = True
    skin.data.materials.append(dst)
    gpu(sc)
    sc.cycles.samples = 1
    sc.render.bake.use_selected_to_active = True
    sc.render.bake.cage_extrusion = 3.0 * voxel
    sc.render.bake.max_ray_distance = 8.0 * voxel
    sc.render.bake.margin = 8
    bpy.ops.object.select_all(action="DESELECT")
    old.select_set(True)
    skin.select_set(True)
    bpy.context.view_layer.objects.active = skin
    bpy.ops.object.bake(type="EMIT")
    sc.render.bake.use_selected_to_active = False
    return pixels(target.image)


def parse_keep_open(argv):
    """every --keep-open "x0,y0,z0>x1,y1,z1@w" -> [((x0, y0, z0), (x1, y1, z1), w)] (fractions of the part's box)"""
    out = []
    for i, a in enumerate(argv):
        if a != "--keep-open" or i + 1 >= len(argv):
            continue
        try:
            ends, w = argv[i + 1].split("@")
            p0, p1 = (tuple(float(v) for v in e.split(",")) for e in ends.split(">"))
            if len(p0) != 3 or len(p1) != 3 or not float(w) > 0:
                raise ValueError
        except ValueError:
            raise ValueError(f"sharpen: --keep-open {argv[i + 1]!r} - x0,y0,z0>x1,y1,z1@w (fractions of the part's "
                             "box; w over 0)") from None
        out.append((p0, p1, float(w)))
    return out


KEEP_RINGS = (0.0, 0.4, 0.8)   # the lines of sight down a kept opening: its middle, rings at 0.4 and 0.8 of its half


def ways_clear(obj, ways_world):
    """each way (start, end, width) in world units -> the lines of sight down it that something stops (a count)"""
    bm = bmesh_of(obj)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    stopped = []
    for a, b, w in ways_world:
        a, b = np.asarray(a, float), np.asarray(b, float)
        d = b - a
        length = float(np.linalg.norm(d))
        d /= length
        u = np.cross(d, (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0))
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        n = 0
        for ring in KEEP_RINGS:
            for k in range(1 if ring == 0 else 8):
                t_ = 2 * np.pi * k / 8
                o = a + (u * np.cos(t_) + v * np.sin(t_)) * ring * w / 2
                if tree.ray_cast(Vector(o.tolist()), Vector(d.tolist()), length)[0] is not None:
                    n += 1
        stopped.append(n)
    return stopped


def bmesh_of(obj):
    import bmesh  # noqa: PLC0415

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    return bm


def keep_open(obj, ways, unwrap=False):
    """carve each way (fractions of the part's box) through the part: a cylinder `w` of its longest side across,
    overshooting both ends -> (the ways in world units, how many lines of sight each left stopped). unwrap: the new
    skin's atlas made again with the bore's walls in it (the generator's own map is never re-made: --keep-skin)"""
    co = np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
    lo, hi = co.min(axis=0), co.max(axis=0)
    span = hi - lo
    world = [(lo + span * np.asarray(p0), lo + span * np.asarray(p1), w * float(span.max())) for p0, p1, w in ways]
    for a, b, w in world:
        d = b - a
        length = float(np.linalg.norm(d))
        if length <= 0:
            raise ValueError("sharpen: --keep-open - its two ends are the same point")
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=w / 2.0, depth=length * 1.02,
                                            location=tuple((a + b) / 2.0))
        cut = bpy.context.active_object
        cut.rotation_mode = "QUATERNION"
        cut.rotation_quaternion = Vector((0.0, 0.0, 1.0)).rotation_difference(Vector((d / length).tolist()))
        bpy.context.view_layer.update()
        mod = obj.modifiers.new("KeepOpen", "BOOLEAN")
        mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", cut
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cut, do_unlink=True)
    if unwrap:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=1.25, island_margin=0.0015)
        bpy.ops.uv.pack_islands(rotate=True, margin=0.0015)
        bpy.ops.object.mode_set(mode="OBJECT")
    return world, ways_clear(obj, world)


def step_prep(argv):
    src, work = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    size = opt(argv, "--size", 4096)
    try:
        ways = parse_keep_open(argv)
    except ValueError as e:
        return emit("fail", str(e), "lune run kit sharpen <part.glb> --keep-open 0.5,0,0.5>0.5,1,0.5@0.05")
    os.makedirs(work, exist_ok=True)
    obj = load_glb(src)
    img = None
    for mat in list(obj.data.materials):
        if not (mat and mat.use_nodes):
            continue
        for link in mat.node_tree.links:
            if link.to_socket.name == "Base Color" and link.from_node.type == "TEX_IMAGE" and link.from_node.image:
                img = link.from_node.image
    if img is None or not obj.data.uv_layers:
        return emit("fail", f"sharpen: {os.path.basename(src)} has no colour map of its own (or no UVs) to sharpen",
                    "sharpen a generator's GLB (kit gen writes one with its own map)")
    said, stopped = "its own skin kept", []
    if "--keep-skin" in argv:
        if ways:   # (the generator's own skin: carved as it is)
            _world, stopped = keep_open(obj, ways)
        img.scale(size, size)
        img.filepath_raw = os.path.join(work, "atlas.png")
        img.file_format = "PNG"
        img.save()
    else:
        co = coords(obj.data)
        voxel = float(np.max(co.max(axis=0) - co.min(axis=0))) * opt(argv, "--voxel", 0.0042)
        skin, facts = new_skin(obj, voxel)
        if ways:   # (after the remesh - it closes what is narrower than about two voxels - and BEFORE the colour is
            #        baked across, so the bore's own walls get their UVs and colour like the rest)
            _world, stopped = keep_open(skin, ways, unwrap=True)
        across = bake_across(obj, skin, img, voxel, size)
        save_image(M.linear_to_srgb(across[..., :3]), os.path.join(work, "atlas.png"))
        bpy.data.objects.remove(obj, do_unlink=True)
        obj = skin
        obj.data.materials.clear()
        said = (f"a new skin of {facts['triangles']:,} triangles ({facts['open_edges']} open, {facts['pinched_edges']} "
                f"pinched, {facts['opposite_windings']} wound the other way)")
        if facts["inner_faces_removed"]:
            said += (f", made solid: {facts['hollow']:.0%} of it was a thin wall with a hollow behind (the generator's "
                     f"crust has gaps), its inner wall of {facts['inner_faces_removed']:,} faces removed and the gaps "
                     f"closed - {facts['hollow_after']:.0%} now")
        elif facts["hollow"] > 0.2:
            said += f", HOLLOW: {facts['hollow']:.0%} of it a thin wall (kept: solid=False)"
    if ways:
        said += f"; {len(ways)} opening(s) kept open"
        if any(stopped):
            return emit("fail", f"sharpen prep: an opening is still stopped after it was carved ({stopped} lines of "
                                "sight of each blocked)", "widen it (w) or start and end it outside the part")
    np.save(os.path.join(work, "said.npy"), np.full((size, size), M.OWN_SAY, dtype=np.float32))
    for p in obj.data.polygons:
        p.material_index = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "part.blend"))
    state(work, face=opt(argv, "--face", 0.0), size=size, source=src.replace("\\", "/"), views=[])
    emit("pass", f"sharpen prep: {said}; its colour map at {size} px", "render the first view",
         work=work.replace("\\", "/"))


def atlas_material(obj, path):
    mat = bpy.data.materials.new("atlas")
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def step_render(argv):
    work, view = os.path.abspath(argv[0]), argv[1]
    spec = next((v for v in M.VIEWS if v[0] == view), None)
    if spec is None:
        return emit("fail", f"sharpen: no view '{view}'", "one of " + ", ".join(v[0] for v in M.VIEWS))
    st = state(work)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(work, "part.blend"))
    sc = bpy.context.scene
    obj = the_part()
    atlas_material(obj, os.path.join(work, "atlas.png"))
    world = bpy.data.worlds.new("w")
    world.color = (0.22, 0.225, 0.235)
    sc.world = world
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    co = coords(obj.data)
    centre = (co.min(axis=0) + co.max(axis=0)) / 2.0
    d = Vector(M.view_direction(float(st.get("face", 0.0)) + spec[1], spec[2]).tolist())
    cam.location = Vector(centre.tolist()) + d * 6.0
    cam.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    bpy.context.view_layer.update()
    inv = np.array(cam.matrix_world.inverted())
    cc = co @ inv[:3, :3].T + inv[:3, 3]
    rx, ry, half_w, half_h = M.frame(cc[:, 0].max() - cc[:, 0].min(), cc[:, 1].max() - cc[:, 1].min())
    cam.location = cam.matrix_world @ Vector(((cc[:, 0].max() + cc[:, 0].min()) / 2.0,
                                              (cc[:, 1].max() + cc[:, 1].min()) / 2.0, 0.0))
    cam_data.ortho_scale = 2.0 * max(half_w, half_h)
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light, sh.color_type = "STUDIO", "TEXTURE"
    sh.show_cavity, sh.cavity_type = True, "BOTH"
    sh.show_shadows = False
    sc.display.render_aa = "16"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = os.path.join(work, f"{view}_in.png")
    bpy.ops.render.render(write_still=True)
    bpy.context.view_layer.update()
    with open(os.path.join(work, f"{view}_cam.json"), "w", encoding="utf-8") as fh:
        json.dump({"matrix": [list(r) for r in cam.matrix_world], "half_w": half_w, "half_h": half_h, "res": [rx, ry]}, fh)
    emit("pass", f"sharpen render {view}: {rx} x {ry}", "redraw it sharp, then project the redraw",
         picture=os.path.join(work, f"{view}_in.png").replace("\\", "/"), seen=spec[3])


def step_project(argv):
    work, view, picture = os.path.abspath(argv[0]), argv[1], os.path.abspath(argv[2])
    first = os.path.abspath(opt(argv, "--match", "")) if "--match" in argv else ""   # (Blender reads no relative path)
    st = state(work)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(work, "part.blend"))
    sc = bpy.context.scene
    obj = the_part()
    me = obj.data
    with open(os.path.join(work, f"{view}_cam.json"), encoding="utf-8") as fh:
        cam = json.load(fh)
    co, no = coords(me), coords(me, "normal")
    toward = M.toward_camera(cam["matrix"])
    uv = M.ortho_uv(co, cam["matrix"], cam["half_w"], cam["half_h"])
    bvh = BVHTree.FromPolygons([tuple(v) for v in co], [tuple(p.vertices) for p in me.polygons])
    eps = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0))) * 2e-3
    d = Vector(toward.tolist())
    seen = np.zeros(len(co))
    for i in np.nonzero(no @ toward > 0.02)[0]:
        if bvh.ray_cast(Vector((co[i] + no[i] * eps).tolist()), d)[0] is None:
            seen[i] = 1.0
    weight = M.view_weight(no, toward, seen)
    me.attributes.new("pj_uv", "FLOAT2", "POINT").data.foreach_set("vector", uv.astype(np.float32).ravel())
    me.attributes.new("pj_w", "FLOAT", "POINT").data.foreach_set("value", weight.astype(np.float32))
    src = bpy.data.images.load(picture)
    if first and os.path.isfile(first) and os.path.abspath(first) != picture:
        a = pixels(src)
        a[..., :3] = M.match_colour(a[..., :3], pixels(bpy.data.images.load(first))[..., :3])
        src.pixels.foreach_set(a.ravel())
    size = int(st["size"])
    gpu(sc)
    sc.cycles.samples = 1
    sc.render.bake.margin = 6
    baked = {}
    for what in ("colour", "weight"):
        mat = bpy.data.materials.new(what)
        mat.use_nodes = True
        nt = mat.node_tree
        for node in list(nt.nodes):
            nt.nodes.remove(node)
        emission = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(emission.outputs["Emission"], nt.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
        attr = nt.nodes.new("ShaderNodeAttribute")
        if what == "colour":
            attr.attribute_name = "pj_uv"
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image, tex.extension = src, "EXTEND"
            nt.links.new(attr.outputs["Vector"], tex.inputs["Vector"])
            nt.links.new(tex.outputs["Color"], emission.inputs["Color"])
        else:
            attr.attribute_name = "pj_w"
            nt.links.new(attr.outputs["Fac"], emission.inputs["Color"])
        target = nt.nodes.new("ShaderNodeTexImage")
        target.image = bpy.data.images.new(f"bake_{what}", size, size, alpha=False, float_buffer=True)
        target.image.colorspace_settings.name = "Non-Color"   # (the float bake as it is: linear values)
        nt.nodes.active = target
        target.select = True
        me.materials.clear()
        me.materials.append(mat)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.bake(type="EMIT")
        baked[what] = pixels(target.image)
    weight_map = np.clip(baked["weight"][..., 0], 0.0, 1.0)
    old = M.srgb_to_linear(pixels(bpy.data.images.load(os.path.join(work, "atlas.png")))[..., :3])
    said = np.load(os.path.join(work, "said.npy"))
    new, total = M.blend(old, said, baked["colour"][..., :3], weight_map)
    save_image(M.linear_to_srgb(new), os.path.join(work, "atlas.png"))
    np.save(os.path.join(work, "said.npy"), total.astype(np.float32))
    state(work, views=[*st.get("views", []), view])
    emit("pass", f"sharpen project {view}: this view sees {float(seen.mean()):.0%} of the part's points and drew on "
                 f"{float((weight_map > 0.05).mean()):.0%} of its colour map", "the next view, or final",
         leads=round(float((weight_map > said).mean()), 3))


def close_skin(obj):
    """a generator's GLB as one skin -> (open edges before, after, pinched edges left):
    - weld its UV seams (a GLB is split along them);
    - take out its MEMBRANES: a triangle with one free edge whose other edges already carry two faces;
    - fill what small holes are left; a patch takes the colour of the skin beside it (its neighbours' UVs).
    PINCHED edges (three or four faces on one edge, where two sheets of the skin touch) are counted and LEFT: cutting
    them out and patching was tried on the wolf (80 such edges) and left more open edges than it closed. A build's
    import deletes the smallest faces on a pinch and can leave a small hole there (gate `manifold`): a part that must
    pass that gate is given a new skin first (a voxel remesh, its maps baked across) - not built here yet."""
    import bmesh  # noqa: PLC0415

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    before = sum(1 for e in bm.edges if e.is_boundary)
    for _ in range(8):
        junk = [f for f in bm.faces if any(e.is_boundary for e in f.edges)
                and any(len(e.link_faces) > 2 for e in f.edges)]
        if not junk:
            break
        bmesh.ops.delete(bm, geom=junk, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    left = [e for e in bm.edges if e.is_boundary]
    if left and len(left) <= 400:   # (pinholes; hundreds of open edges is an open shell: left as it is)
        old = set(bm.faces)
        bmesh.ops.holes_fill(bm, edges=left, sides=0)
        uv = bm.loops.layers.uv.active
        if uv is not None:
            for f in [f for f in bm.faces if f not in old]:
                for loop in f.loops:
                    near = [l2 for l2 in loop.vert.link_loops if l2.face in old]
                    if near:
                        loop[uv].uv = near[0][uv].uv
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    after = sum(1 for e in bm.edges if e.is_boundary)
    pinched = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bm.to_mesh(obj.data)
    bm.free()
    return before, after, pinched


def step_final(argv):
    work, dst = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    metal = opt(argv, "--metal", "")
    if metal and metal != "gold":
        return emit("fail", f"sharpen: no metal '{metal}'", "--metal gold, or none (the part keeps its own colour)")
    st = state(work)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(work, "part.blend"))
    obj = the_part()
    atlas = pixels(bpy.data.images.load(os.path.join(work, "atlas.png")))[::-1, :, :3]   # (row 0 at the top)
    said = np.load(os.path.join(work, "said.npy"))[::-1]
    colour, rough, normal = M.maps(atlas, metal_ramp=M.GOLD if metal == "gold" else None,
                                   normal_strength=opt(argv, "--normal", 1.0))
    files = {"colour": os.path.join(work, "colour.png"), "rough": os.path.join(work, "rough.png"),
             "normal": os.path.join(work, "normal.png")}
    save_image(colour[::-1], files["colour"])
    save_image(rough[::-1], files["rough"], data=True)
    save_image(normal[::-1], files["normal"], data=True)
    mat = bpy.data.materials.new("sharpened")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    col = nt.nodes.new("ShaderNodeTexImage")
    col.image = bpy.data.images.load(files["colour"])
    nt.links.new(col.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.98
    r = nt.nodes.new("ShaderNodeTexImage")
    r.image = bpy.data.images.load(files["rough"])
    r.image.colorspace_settings.name = "Non-Color"
    nt.links.new(r.outputs["Color"], bsdf.inputs["Roughness"])
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(files["normal"])
    n.image.colorspace_settings.name = "Non-Color"
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(n.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    before, after, pinched = close_skin(obj)
    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB")
    drawn = float((said > 2.0 * M.OWN_SAY).mean())
    emit("pass", f"sharpen: {dst.replace(chr(92), '/')} - {len(st.get('views', []))} view(s) drew on {drawn:.0%} of "
                 f"its colour map; colour{' on ' + metal if metal else ''}, roughness and normal maps; open edges "
                 f"{before} -> {after}"
                 + (f"; {pinched} pinched edge(s) left (a build's manifold gate may open a small hole there)"
                    if pinched else ""),
         "look at it lit, beside what it was and beside its reference, from every view - then a.import_mesh(...) "
         "with no mat= keeps these maps", out=dst.replace("\\", "/"), views=st.get("views", []), open_edges=after)


STEPS = {"fold": step_fold, "prep": step_prep, "render": step_render, "project": step_project, "final": step_final}

if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not args or args[0] not in STEPS:
        raise SystemExit("sharpen_part: a step - " + ", ".join(STEPS))
    STEPS[args[0]](args[1:])
