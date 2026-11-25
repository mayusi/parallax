"""thin_gen_part.py — fixture: a generated part THINNED the plain way (a collapse decimate to a triangle count, its own
UVs and colour map kept): the triangle soup a decimated generator mesh is - slivers, no loops round the form. The
hybrid route's bad case (build_hybrid.py soup).

    blender -b --factory-startup -P kit/selftest/blender/thin_gen_part.py -- <in.glb> <out.glb> --tris 5000

Never "fix" this file."""

import os
import sys

import bpy

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SRC, DST = os.path.abspath(ARGS[0]), os.path.abspath(ARGS[1])
TRIS = int(ARGS[ARGS.index("--tris") + 1]) if "--tris" in ARGS else 5000
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
obj = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
dec = obj.modifiers.new("thin", "DECIMATE")
dec.ratio = TRIS / max(1, len(obj.data.polygons))
bpy.ops.object.modifier_apply(modifier=dec.name)
bpy.ops.export_scene.gltf(filepath=DST, export_format="GLB", use_selection=True)
print("THIN", DST, len(obj.data.polygons))
