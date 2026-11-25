"""probe_shade_angle.py — rbx._angle_held on a 12-sided drum (sides 30 degrees apart, its caps at 90): shaded smooth
everywhere it is NOT held at 45 degrees (its cap edges should be split); shaded by angle at 45 it is. Then a real
build with a.shade("Drum", 45): its facts say every edge held. Prints `SHADE {json}`. Used by
kit/test/python/test_shade_angle.py. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx  # noqa: E402


def drum(smooth_all):
    me = bpy.data.meshes.new("probe_drum")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=1, radius2=1, depth=1)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("probe_drum", me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    if smooth_all:
        bpy.ops.object.shade_smooth()
    else:
        bpy.ops.object.shade_smooth_by_angle(angle=np.radians(45))
    cn = np.empty(len(me.loops) * 3)
    me.corner_normals.foreach_get("vector", cn)
    out = rbx._angle_held(me, cn.reshape(-1, 3), set(range(len(me.polygons))), 45.0)
    bpy.data.objects.remove(obj)
    bpy.data.meshes.remove(me)
    return out


out = {"smooth_all": drum(True), "by_angle": drum(False)}
a = rbx.Asset("_selftest_shade_angle", tex=64, size=(0.6, 0.4, 0.6), ground=True)
a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.4)
a.cylinder("Drum", 0.3, 0.4, (0, 0.2, 0), "steel", axis="Y", segments=12, bevel=0)
a.shade("Drum", 45)
a.build()
print("SHADE " + json.dumps(out))
