"""outline_dump.py — run by kit/refs/outline.py inside Blender: a model's parts as world-space triangles (one npz).

    blender -b --factory-startup -P kit/refs/outline_dump.py -- <model.glb|fbx|obj> <out.npz>
"""

import os
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = os.path.abspath(argv[0]), os.path.abspath(argv[1])
bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(src)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=src)
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=src)
else:
    bpy.ops.wm.obj_import(filepath=src)
data, names = {}, []
for o in bpy.context.scene.objects:
    if o.type != "MESH" or not o.data.polygons:
        continue
    me = o.data
    me.calc_loop_triangles()
    M = np.array(o.matrix_world)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    V = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    T = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", T)
    key = f"p{len(names)}"
    data[key + "__V"] = V.astype(np.float32)
    data[key + "__T"] = T.reshape(-1, 3)
    names.append(o.name)
data["__names"] = np.array(names)
np.savez_compressed(out, **data)
print("OUTLINE_DUMP", len(names))
