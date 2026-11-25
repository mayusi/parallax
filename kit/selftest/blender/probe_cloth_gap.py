"""probe_cloth_gap.py — runs build_cloth.py (a cover dropped on a table) and measures how far the cover's wall lies
from the table where it rests (card maah: "a cloth at rest is allowed to stand a hair off what it rests on"): the
built mesh's Cover faces against its Table faces. Prints `GAP {json}`: the distance (mm) of the nearest tenth of the
cover's points and of its nearest point, and whether the build exempted the two from the floating check.
Used by kit/test/python/test_cloth_settle.py. Never "fix" this file."""

import json
import os
import runpy
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

g = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_cloth.py"), run_name="__main__")
a = g["a"]
obj = next(o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render and o.get("kit_parts"))
me = obj.data
names = list(obj["kit_parts"])
attr = me.attributes["kit_part"]
ids = np.zeros(len(me.polygons), np.int32)
attr.data.foreach_get("value", ids)
cover = [i for i, n in enumerate(names) if n.split("~")[0] == "Cover"]
table = [i for i, n in enumerate(names) if n.split("~")[0] == "Table"]
tf = [p for p in me.polygons if ids[p.index] in table]
tree = BVHTree.FromPolygons([v.co for v in me.vertices], [tuple(p.vertices) for p in tf])
cv = sorted({v for p in me.polygons if ids[p.index] in cover for v in p.vertices})
mm = float(a.mm_per_stud or 280.0) * obj.matrix_world.to_3x3().median_scale
d = np.array([tree.find_nearest(me.vertices[i].co)[3] for i in cv]) * mm
print("GAP " + json.dumps({"p10_mm": round(float(np.percentile(d, 10)), 3), "min_mm": round(float(d.min()), 3),
                           "settled": (a.design.get("cloth_settled") or {}).get("Cover", 0),
                           "exempt": sorted(set(a.design.get("allow_floating", ())))}))
