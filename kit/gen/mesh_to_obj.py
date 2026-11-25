"""mesh_to_obj.py — a built game mesh (.fbx / .glb) as one OBJ of its triangles, in the file's own frame (for CoACD:
kit/gen/hulls.py; kit/gen/hybrid_fabricate.py --hulls).

    blender -b --factory-startup --python-exit-code 2 -P kit/gen/mesh_to_obj.py -- <in.fbx|.glb> <out.obj>"""

import os
import sys

import bmesh
import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
src, dst = os.path.abspath(args[0]), os.path.abspath(args[1])
bpy.ops.wm.read_factory_settings(use_empty=True)
if src.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=src)
else:
    bpy.ops.import_scene.gltf(filepath=src)
verts, tris = [], []
for o in [x for x in bpy.context.scene.objects if x.type == "MESH"]:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)   # (one surface: split at UV seams for the file only)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    # (one winding, outward: a game file's faces can come wound both ways - the H9 blade's read back as half its
    #  volume, its signed tetrahedra cancelling - and CoACD and the hull judge both read the winding)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bm.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    base = len(verts)
    verts += [v.co[:] for v in bm.verts]
    bm.verts.index_update()
    tris += [tuple(base + v.index for v in f.verts) for f in bm.faces]
    bm.free()
if not tris:
    raise SystemExit(f"{src}: no faces")
with open(dst, "w", encoding="ascii") as f:
    for v in verts:
        f.write("v %.6f %.6f %.6f\n" % v)
    for t in tris:
        f.write("f %d %d %d\n" % (t[0] + 1, t[1] + 1, t[2] + 1))
print("OBJ", dst, len(verts), len(tris))
