"""export_glb.py — one built asset (build/models/<asset>.blend) -> a BLIND GLB for the owner grading page (kit rate):
every visible mesh, its object / mesh / material / image names replaced by the round's label (nothing in the file says
which route or session made it); the baked maps (colour, roughness, metal, normal) go in as glTF PBR.
    blender -b <asset>.blend --factory-startup -P export_glb.py -- <out.glb> <label>"""
import os
import sys

import bpy

out, label = sys.argv[sys.argv.index("--") + 1:][:2]
sc = bpy.context.scene
objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and not o.name.startswith(("R6_", "Preview"))]
for o in list(sc.objects):
    if o not in objs:
        bpy.data.objects.remove(o, do_unlink=True)
for i, o in enumerate(objs):
    o.name = f"{label}_{i}"
    o.data.name = f"{label}_mesh_{i}"
for i, m in enumerate(bpy.data.materials):
    m.name = f"{label}_mat_{i}"
for i, img in enumerate(bpy.data.images):
    img.name = f"{label}_tex_{i}"
for c in bpy.data.collections:
    c.name = f"{label}_set"
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=os.path.abspath(out), export_format="GLB", use_selection=False,
                          export_apply=True, export_yup=True, export_extras=False, export_cameras=False,
                          export_lights=False)
print("EXPORTED", out, len(objs))
