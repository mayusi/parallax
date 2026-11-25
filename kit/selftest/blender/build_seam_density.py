"""build_seam_density.py — fixture for PLACED SEAMS AND THE REST OF THE MAP (card xxp7): a handle laid along the
author's seams (a.seams) beside a plain Block that has none. The handle's islands are brought to the Block's texel
density and the Block keeps its own (average_islands_scale moved every island a few percent), and the saved mesh
carries no seam flags. After the build `DENS {json}`: each part's texel density (the square root of its map area
over its surface area) and how many edges still carry a seam flag. Used by kit/test/python/test_seam_left.py.
Never "fix" this file."""

import json
import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import rbx  # noqa: E402

a = rbx.Asset("_selftest_seam_density", tex=256, size=(2.2, 3.0, 1.0), ground=True)
a.material("wood", color=(0.45, 0.3, 0.18), rough=0.7)
a.cylinder("Handle", 0.5, 3.0, (0, 1.5, 0), "wood", axis="Y", segments=16, bevel=0)
a.seams("Handle", cut=lambda p, q: p[2] > 0.49 and q[2] > 0.49, sharp=60)
a.box("Block", (0.8, 0.8, 0.8), (0.9, 0.4, 0.0), "wood", bevel=0)
a.build()

obj = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("_selftest_seam_density"))
me = obj.data
names, attr = list(obj.get("kit_parts") or []), me.attributes.get("kit_part")
bm = bmesh.new()
bm.from_mesh(me)
uvl = bm.loops.layers.uv.active
area3, areauv = {}, {}
for f in bm.faces:
    part = names[attr.data[f.index].value].split("~")[0]
    u = [lp[uvl].uv for lp in f.loops]
    s_ = sum((u[i].x - u[0].x) * (u[i + 1].y - u[0].y) - (u[i].y - u[0].y) * (u[i + 1].x - u[0].x)
             for i in range(1, len(u) - 1))
    area3[part] = area3.get(part, 0.0) + f.calc_area()
    areauv[part] = areauv.get(part, 0.0) + abs(s_) / 2
bm.free()
print("DENS " + json.dumps({"density": {p: round(math.sqrt(areauv[p] / area3[p]), 5) for p in area3},
                            "seam_edges": sum(1 for e in me.edges if e.use_seam)}))
