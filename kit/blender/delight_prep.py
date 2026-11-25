"""delight_prep.py - a finished scan put back where its cameras saw it, for kit/tools/delight.py (his D-R03).

blender -b --factory-startup -P delight_prep.py -- <scan.glb> <to_scan.json> <out.obj>

The scan (kit/tools/photoscan.py's GLB, in the kit's frame) moved back into COLMAP's frame (to_scan undone, as
photoscan_outline.py does), triangulated and written as an OBJ with its UVs, for Mitsuba."""

import json
import os
import sys

import bpy
from mathutils import Matrix

ARGS = sys.argv[sys.argv.index("--") + 1:]
GLB, SPEC, OUT = (os.path.abspath(a) for a in ARGS[:3])
back = Matrix(json.load(open(SPEC, encoding="utf-8"))["to_scan"]).inverted()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
objs = [o for o in bpy.data.objects if o.type == "MESH"]
for o in objs:
    o.data.transform(o.matrix_world)
    o.matrix_world = Matrix.Identity(4)
    o.data.transform(back)
    m = o.modifiers.new("tri", "TRIANGULATE")
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.modifier_apply(modifier="tri")
bpy.ops.wm.obj_export(filepath=OUT, export_selected_objects=False, export_materials=False, export_uv=True,
                      export_normals=True, forward_axis="Y", up_axis="Z", apply_modifiers=True)

# the way the surface faces at every texel of the colour texture (the cameras' frame), for the solve's shading
# model: written as RGB = (n + 1) / 2; a texel no face covers stays black
size = int(ARGS[3]) if len(ARGS) > 3 else 1024
img = bpy.data.images.new("facing", size, size, float_buffer=False)
img.colorspace_settings.name = "Non-Color"
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 1
sc.render.bake.margin = 4
sc.render.bake.normal_space = "OBJECT"
for o in objs:
    for slot in o.material_slots:
        if slot.material is None:
            continue
        nt = slot.material.node_tree
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        nt.nodes.active = node
    if not o.material_slots:
        m = bpy.data.materials.new("bake")
        m.use_nodes = True
        node = m.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        m.node_tree.nodes.active = node
        o.data.materials.append(m)
bpy.ops.object.select_all(action="SELECT")
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.bake(type="NORMAL", normal_space="OBJECT", margin=4)
img.filepath_raw = os.path.splitext(OUT)[0] + "_facing.png"
img.file_format = "PNG"
img.save()
print("PREP " + json.dumps({"objects": len(objs), "triangles": sum(len(o.data.polygons) for o in objs),
                            "facing": img.filepath_raw}))
