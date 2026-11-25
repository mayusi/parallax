"""model_quality.py — how sound a downloaded reference model is, before anything uses it (`kit make`'s intake):

    blender -b --factory-startup -P kit/blender/model_quality.py -- <model.glb> <out.json>

The old intake checked size and proportions only, so a 1.17M-face photogrammetry scan full of holes and noise passed
as a "reference". This measures what makes a model a mess:
  open_share   open (boundary) edges / all edges — torn, unclosed surfaces (a clean model is ~0; a raw scan is not)
  speck_share  faces in islands under 1% of the model's size — floating scan debris
  noise        the median angle between neighbouring faces' normals, in degrees, over the surface: a modelled
               surface is flat or smoothly curved (a few degrees), a raw scan's is jagged everywhere
  faces, islands, size (x, y, z in its own units: its proportions), materials, textured
Prints one JSON line; writes the same to <out.json>.
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = os.path.abspath(argv[0]), os.path.abspath(argv[1])
bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(src)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=src)
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=src)
else:
    bpy.ops.import_scene.fbx(filepath=src)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bm = bmesh.new()
mats, textured = set(), False
for o in objs:
    me = o.data.copy()
    me.transform(o.matrix_world)
    bm.from_mesh(me)
    for m in o.data.materials:
        if m:
            mats.add(m.name)
            if m.use_nodes and any(n.type == "TEX_IMAGE" and n.image for n in m.node_tree.nodes):
                textured = True
    bpy.data.meshes.remove(me)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
bm.faces.ensure_lookup_table()
pts = [v.co for v in bm.verts]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
size = hi - lo
big = max(size)

edges = len(bm.edges) or 1
open_share = sum(1 for e in bm.edges if e.is_boundary) / edges

# islands (face connectivity) and their extents
seen = set()
speck_faces, islands = 0, 0
for f in bm.faces:
    if f.index in seen:
        continue
    islands += 1
    stack, isl = [f], []
    seen.add(f.index)
    while stack:
        g = stack.pop()
        isl.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen:
                    seen.add(h.index)
                    stack.append(h)
    vs = {v for g in isl for v in g.verts}
    ext3 = max(max(v.co[i] for v in vs) - min(v.co[i] for v in vs) for i in range(3))
    if ext3 < big * 0.01:
        speck_faces += len(isl)
speck_share = speck_faces / max(1, len(bm.faces))

# surface noise: the angle between neighbouring faces, sampled over up to 60k interior edges
step = max(1, len(bm.edges) // 60000)
angles = []
for i, e in enumerate(bm.edges):
    if i % step or len(e.link_faces) != 2:
        continue
    a, b = e.link_faces
    if a.normal.length < 0.5 or b.normal.length < 0.5:
        continue
    angles.append(math.degrees(a.normal.angle(b.normal, 0.0)))
angles.sort()
noise = angles[len(angles) // 2] if angles else 0.0
p90 = angles[int(len(angles) * 0.9)] if angles else 0.0
# a MODELLED hard surface is flat faces and real edges (two peaks: ~0 deg and sharp); a raw SCAN is jagged everywhere
# at a moderate angle and has almost no flat run and no clean edge (the 1.17M-face Glock scan: flat 0.10, sharp 0.035; modelled ones 0.30-0.40, 0.17-0.28)
flat_share = sum(1 for x in angles if x < 2.0) / max(1, len(angles))
sharp_share = sum(1 for x in angles if x > 45.0) / max(1, len(angles))

out = {"schema": 1, "status": "pass", "summary": f"model_quality: {os.path.basename(src)}", "next_action": "none",
       "faces": len(bm.faces), "islands": islands, "open_share": round(open_share, 4),
       "speck_share": round(speck_share, 4), "noise_deg": round(noise, 2), "noise_p90_deg": round(p90, 2),
       "flat_share": round(flat_share, 4), "sharp_share": round(sharp_share, 4),
       "size": [round(v, 5) for v in size], "materials": len(mats), "textured": textured}
bm.free()
with open(dst, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps(out))
