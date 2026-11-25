"""photoscan_finish.py - COLMAP's surface made a kit mesh (kit/tools/photoscan.py runs it; his D-R02).

blender -b --factory-startup -P photoscan_finish.py -- <meshed.ply> <cameras.json> <out.glb> <triangle budget>
    [--size <metres> --axis height|length|width]

LEVEL (up: where the cameras' own up points on average), TURN (the longest way across the ground along Blender's
Y, the kit's length), CLEAN (the largest connected piece; a floor the thing stood on cut away), SCALE (a size you
know -> metres, else left and said), PLACE (its base on the ground, its middle on the origin), REDUCE (to the
budget), COLOUR (the points' colours baked into a texture on a fresh unwrap). Prints FINISH {json}."""

import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
PLY, CAMS, GLB, BUDGET = ARGS[0], ARGS[1], ARGS[2], int(ARGS[3])
SIZE = float(ARGS[ARGS.index("--size") + 1]) if "--size" in ARGS else None
AXIS = ARGS[ARGS.index("--axis") + 1] if "--axis" in ARGS else "height"
POINTS = ARGS[ARGS.index("--points") + 1] if "--points" in ARGS else None   # (COLMAP's fused points)
SKIN = 4.0            # point spacings: a face further than this from every point is Poisson's skin, not the thing
FLOOR_SHARE = 0.2     # a flat slab at the bottom holding this share of the points is a floor, not the object
TEX = 2048

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.ply_import(filepath=PLY)
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj
facts = {}

# LEVEL: the cameras' mean up, turned onto Blender's +Z
cams = json.load(open(CAMS, encoding="utf-8"))
up = np.mean([c["up"] for c in cams], axis=0)
up = up / max(np.linalg.norm(up), 1e-12)
facts["up_agreement"] = round(float(np.mean([np.dot(c["up"], up) for c in cams])), 3)   # 1: every camera level
rot = Vector(up.tolist()).rotation_difference(Vector((0, 0, 1))).to_matrix().to_4x4()
obj.data.transform(rot)

# CLEAN: only the surface real points stand on. Poisson's surface is closed: where the points are sparse (an
# underside no camera saw, the air round a thin capture) it bulges out as a skin of its own, and its trim leaves
# patches of that skin joined to the real surface (the 24-view trial: an outer shell round the urn). A face whose
# middle is further from every fused point than a few point spacings is skin, and goes.
bm = bmesh.new()
bm.from_mesh(obj.data)
facts["skin_faces_dropped"] = 0
if POINTS:
    from mathutils.kdtree import KDTree

    bpy.ops.wm.ply_import(filepath=POINTS)
    cloud = [o for o in bpy.context.selected_objects if o is not obj][0]
    pts = [rot @ v.co for v in cloud.data.vertices]
    bpy.data.objects.remove(cloud)
    obj.select_set(True)                       # (the import made the cloud the selection; the scan is again)
    bpy.context.view_layer.objects.active = obj
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    step = max(1, len(pts) // 2000)
    gaps = sorted(kd.find_n(pts[i], 2)[1][2] for i in range(0, len(pts), step))
    spacing = gaps[len(gaps) // 2]
    # (point spacings only: a share of the cloud's span grew with every stray point far off - the 24-view trial's
    #  limit came out larger than the shell's distance from the urn, and nothing was dropped)
    reach = SKIN * spacing
    skin = [f for f in bm.faces if kd.find(f.calc_center_median())[2] > reach]
    facts["skin_faces_dropped"] = len(skin)
    facts["point_spacing"] = round(spacing, 6)
    bmesh.ops.delete(bm, geom=skin, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")

# CLEAN: the largest connected piece only
bm.verts.ensure_lookup_table()
bm.verts.index_update()
seen, pieces = set(), []
for v in bm.verts:
    if v.index in seen:
        continue
    stack, piece = [v], []
    seen.add(v.index)
    while stack:
        x = stack.pop()
        piece.append(x)
        for e in x.link_edges:
            y = e.other_vert(x)
            if y.index not in seen:
                seen.add(y.index)
                stack.append(y)
    pieces.append(piece)
pieces.sort(key=len, reverse=True)
facts["pieces_dropped"] = len(pieces) - 1
if len(pieces) > 1:
    bmesh.ops.delete(bm, geom=[v for p in pieces[1:] for v in p], context="VERTS")
# ... and what the skin's removal (or no camera) left open is closed: a game part is a closed solid
rims = [e for e in bm.edges if e.is_boundary]
facts["openings_closed"] = 0
facts["base_filled"] = 0.0
if rims:
    made = bmesh.ops.holes_fill(bm, edges=rims, sides=0).get("faces", [])
    if made:
        made = bmesh.ops.triangulate(bm, faces=made)["faces"]
    facts["openings_closed"] = len(made)
    # how much of the BASE no camera saw: the filled surface in the lowest tenth, against the thing's own footprint
    # (the 24-photo trial: its base unseen, the height it was scaled by was short and it came out 14% too wide)
    zs = [v.co.z for v in bm.verts]
    z0, z1 = min(zs), max(zs)
    low = z0 + 0.1 * (z1 - z0)
    filled_low = sum(f.calc_area() for f in made if f.calc_center_median().z <= low)
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    foot = max((max(xs) - min(xs)) * (max(ys) - min(ys)) * math.pi / 4, 1e-12)
    facts["base_filled"] = round(filled_low / foot, 4)
facts["open_edges_left"] = sum(1 for e in bm.edges if e.is_boundary)

# CLEAN: a floor - a thin flat slab at the very bottom holding a large share of the points - cut away
co = np.array([v.co[:] for v in bm.verts])
h = co[:, 2]
span = float(h.max() - h.min()) or 1.0
slab = h <= h.min() + 0.01 * span
facts["floor_cut"] = False
if slab.mean() > FLOOR_SHARE:
    cut = float(h.min() + 0.015 * span)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, cut),
                           plane_no=(0, 0, 1), clear_inner=True)
    edges = [e for e in bm.edges if e.is_boundary]
    if edges:
        bmesh.ops.holes_fill(bm, edges=edges)
    facts["floor_cut"] = True
bm.to_mesh(obj.data)
bm.free()

# TURN: the longest way across the ground along Y (the kit's length: Roblox Z)
co = np.array([v.co[:] for v in obj.data.vertices])
xy = co[:, :2] - co[:, :2].mean(axis=0)
w, vecs = np.linalg.eigh(xy.T @ xy)
major = vecs[:, int(np.argmax(w))]
turn = math.atan2(major[0], major[1])
obj.data.transform(Matrix.Rotation(turn, 4, "Z"))

# SCALE and PLACE
co = np.array([v.co[:] for v in obj.data.vertices])
lo, hi = co.min(axis=0), co.max(axis=0)
dims = hi - lo
k = 1.0
if SIZE:
    along = {"height": dims[2], "length": dims[1], "width": dims[0]}[AXIS]
    k = SIZE / max(float(along), 1e-12)
facts["scale"] = round(k, 6) if SIZE else None
place = Matrix.Diagonal((k, k, k, 1.0)) @ Matrix.Translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
obj.data.transform(place)
facts["size_m" if SIZE else "size_units"] = [round(float(d * k), 4) for d in dims]
# (the whole move from the cameras' frame to the finished scan: the outline check undoes it)
facts["to_scan"] = [list(r) for r in (place @ Matrix.Rotation(turn, 4, "Z") @ rot)]

# REDUCE
n = len(obj.data.polygons)
if n > BUDGET:
    m = obj.modifiers.new("cut", "DECIMATE")
    m.ratio = BUDGET / n
    m.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier="cut")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode="OBJECT")
obj.data.calc_loop_triangles()
facts["triangles"] = len(obj.data.loop_triangles)

# COLOUR: the points' colours (a colour attribute on the vertices) baked into a texture on a fresh unwrap
colour = obj.data.color_attributes[0].name if len(obj.data.color_attributes) else None
facts["coloured"] = colour is not None
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
bpy.ops.object.mode_set(mode="OBJECT")
img = bpy.data.images.new(os.path.splitext(os.path.basename(GLB))[0] + "_colour", TEX, TEX)
mat = bpy.data.materials.new("scan")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Roughness"].default_value = 0.7
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
obj.data.materials.clear()
obj.data.materials.append(mat)
if colour:
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = colour
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(attr.outputs["Color"], emit.inputs["Color"])
    out = nt.nodes["Material Output"]
    keep = out.inputs["Surface"].links[0].from_socket
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    nt.nodes.active = tex
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.cycles.bake_type = "EMIT"
    sc.render.bake.margin = 8
    bpy.ops.object.bake(type="EMIT")
    nt.links.new(keep, out.inputs["Surface"])
    nt.nodes.remove(emit)
    nt.nodes.remove(attr)
img.pack()
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
# (the colour now lives in the texture: the points' colours go, or the glTF carries both and an importer
#  multiplies them - the kit's bake of the urn trial came out black)
for a_ in list(obj.data.color_attributes):
    obj.data.color_attributes.remove(a_)
os.makedirs(os.path.dirname(os.path.abspath(GLB)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=False, export_yup=True)
print("FINISH " + json.dumps(facts))
