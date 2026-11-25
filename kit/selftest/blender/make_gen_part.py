"""make_gen_part.py — fixture: a GENERATOR-LIKE part as a GLB, made on the spot (no GPU, no weights): what kit gen /
TRELLIS.2 hands the hybrid route - a dense triangle crust (about 40,000 triangles, every face a triangle, slivers
included) with its OWN UV atlas and a painted colour map. A lobed pommel: a turned ball with six lobes and a collar
ring that overlaps it (a generator fuses touching forms into one crust that folds through itself).

    blender -b --factory-startup -P kit/selftest/blender/make_gen_part.py -- <out.glb>

Used by kit/test/python/test_hybrid.py and the hybrid fixtures (build_hybrid_*.py). Never "fix" this file."""

import math
import os
import sys

import bmesh
import bpy
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else "gen_part.glb")

bpy.ops.wm.read_factory_settings(use_empty=True)
# (a regular grid split into triangles pairs back into quads - 0.96 by rbx_quads, where a real TRELLIS.2 crust reads
#  0.39 and the same crust decimated 0.14: so the grid is jittered, split by a random diagonal and collapsed to
#  half by a decimate, as an isosurface's triangles are irregular)
rng = np.random.default_rng(7)
U, V = 300, 150
verts, faces = [], []
for i in range(V + 1):
    for j in range(U):
        th = math.pi * min(max(i + (0.4 * (rng.random() - 0.5) if 0 < i < V else 0.0), 0), V) / V
        ph = 2 * math.pi * (j + 0.4 * (rng.random() - 0.5)) / U
        r = 1.0 + 0.12 * math.sin(6 * ph) * math.sin(th) ** 2 + 0.01 * math.sin(37 * ph + 11 * th)
        verts.append((r * math.sin(th) * math.cos(ph), r * math.sin(th) * math.sin(ph), 1.15 * r * math.cos(th)))
for i in range(V):
    for j in range(U):
        a, b, c, d = i * U + j, i * U + (j + 1) % U, (i + 1) * U + (j + 1) % U, (i + 1) * U + j
        faces += [(a, b, c), (a, c, d)] if rng.random() < 0.5 else [(a, b, d), (b, c, d)]
me = bpy.data.meshes.new("gen")
me.from_pydata(verts, [], faces)
bm = bmesh.new()
bm.from_mesh(me)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
# the collar: a torus crossing the ball's lower half (one crust, folded through itself - as a generator leaves it)
tor = bmesh.ops.create_cone(bm, cap_ends=False, segments=96, radius1=0.95, radius2=0.95, depth=0.25)
for v in tor["verts"]:
    v.co.z -= 0.75
bmesh.ops.triangulate(bm, faces=bm.faces)
bm.to_mesh(me)
bm.free()
obj = bpy.data.objects.new("gen_part", me)
bpy.context.scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
dec = obj.modifiers.new("collapse", "DECIMATE")
dec.ratio = 0.5
bpy.ops.object.modifier_apply(modifier=dec.name)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.1, island_margin=0.003)
bpy.ops.object.mode_set(mode="OBJECT")
# its paint: brass with darker bands by HEIGHT and a red spot - laid by the place on the model (each face's colour
# from its own corners' positions), so the colour is a property of the surface, as a generator's texture is
N = 1024
img = np.zeros((N, N, 4), np.float32)
img[..., 3] = 1.0
uv = np.zeros(len(me.loops) * 2)
me.uv_layers.active.data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
co = np.zeros(len(me.vertices) * 3)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)
lv = np.zeros(len(me.loops), np.int64)
me.loops.foreach_get("vertex_index", lv)
for p in me.polygons:
    ls = list(p.loop_indices)
    u, v = uv[ls], co[lv[ls]]
    z = float(v[:, 2].mean())
    band = 0.55 + 0.45 * (0.5 + 0.5 * math.cos(z * 9.0))
    col = np.array([0.72, 0.52, 0.18]) * band
    if v[:, 0].mean() > 0.6 and abs(v[:, 1].mean()) < 0.35 and abs(z) < 0.35:
        col = np.array([0.6, 0.05, 0.04])
    lo, hi = np.floor(u.min(axis=0) * N).astype(int) - 2, np.ceil(u.max(axis=0) * N).astype(int) + 2
    img[max(lo[1], 0):min(hi[1], N), max(lo[0], 0):min(hi[0], N), :3] = col
im = bpy.data.images.new("gen_colour", N, N, alpha=False)
im.pixels.foreach_set(img.ravel())
im.file_format = "PNG"
im.pack()
mat = bpy.data.materials.new("gen_mat")
mat.use_nodes = True
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = im
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
me.materials.append(mat)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True)
print("MADE", OUT, len(me.polygons))
