"""make_sculpt_hull.py — a REAL object's shape SCULPTED from its traced photos (`kit make`'s sculpted_hull candidate):

    blender -b --factory-startup -P kit/blender/make_sculpt_hull.py -- <side.trace.json> <front.trace.json> <out.glb>
        [--blend 0.012]

The same visual hull as make_hull.py (the side outline x the front outline: the photographed silhouette) built as a
SCULPT (rbx_sculpt: the two views' exact 2D distances intersected, meshed by OpenVDB) — always one closed surface
(no boolean to fail on a complex outline), its edges rounded by `blend` (a fraction of its length: 0.012 = 12 mm on a
metre) the way a moulded or worn object's are, its flats flat. Written like make_hull's (glTF: y up, the front toward
-Z, its length 1) so the tournament, the clean-up, the paint and the build take it as one more candidate. One JSON
line.
"""

import json
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rbx_sculpt as S  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
side_path, front_path, out = (os.path.abspath(a) for a in argv[:3])
blend_frac = float(argv[argv.index("--blend") + 1]) if "--blend" in argv else 0.012
side, front = (json.load(open(p, encoding="utf-8")) for p in (side_path, front_path))
L = 1000.0   # (sculpted in millimetres at a 1 m length; written at length 1 like every candidate)


def rings(t):
    return t["outline"], [h for h in t.get("holes", []) if len(h) >= 3], float(t.get("height_ratio", 0.0))


side_rings, front_rings = S.trace_rings(rings(side), rings(front), length=L)
c = S.Canvas(voxel=L / 400.0).views(side=side_rings, front=front_rings, blend=blend_frac * L)
verts, faces = c.mesh(adaptivity=0.15)
bpy.ops.wm.read_factory_settings(use_empty=True)
v = np.asarray(verts, dtype=np.float64) / L
# the canvas is Roblox's axes (x right, y up, z back: the front at -z) -> make_hull's Blender frame (x right, y the
# FRONT, z up): (x, y, z) -> (x, -z, y)
me = bpy.data.meshes.new("sculpted_hull")
me.from_pydata([(float(x), float(-z), float(y)) for x, y, z in v], [], faces)
me.validate()
ob = bpy.data.objects.new("sculpted_hull", me)
bpy.context.scene.collection.objects.link(ob)
for p in me.polygons:
    p.use_smooth = True
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True)
xs = np.array([(vv.co.x, vv.co.y, vv.co.z) for vv in me.vertices]) if len(me.vertices) else np.zeros((1, 3))
size = (xs.max(axis=0) - xs.min(axis=0)).tolist()
print(json.dumps({"schema": 1, "status": "pass" if len(me.polygons) else "fail",
                  "summary": f"make_sculpt_hull: {os.path.basename(out)} — {len(me.polygons)} faces, {size[0]:.3f} x "
                             f"{size[1]:.3f} x {size[2]:.3f} (x width, y length, z height), edges rounded "
                             f"{blend_frac * 100:.1f}% of its length",
                  "next_action": "none", "faces": len(me.polygons), "size": [round(x, 4) for x in size],
                  "specks_dropped": c.stats.get("specks", 0)}))
