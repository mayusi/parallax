"""studio_pack.py - a built model's meshes written for ROBLOX STUDIO to load with no upload (kit/tools/studio_model.py).

blender -b <asset>.blend --factory-startup --python-exit-code 2 -P studio_pack.py -- <manifest.json> <out dir>

Every group of the manifest is the object its .fbx was exported from (the .fbx is named after it). Its triangles are
written in ROBLOX's axes (the build's own BL_FROM_RBX: the same turn an uploaded .fbx comes out with, the export
pre-turning the file for the importer) with Roblox's UV (v from the TOP of the image: VfxMesh's Vector2.new(u, 1 - v))
and its split normals, as <out>/mesh_<group>.json:
    {"group", "object", "verts": [[x, y, z]], "uvs": [[u, v]], "normals": [[x, y, z]],
     "tris": [[v1, v2, v3, uv1, uv2, uv3, n1, n2, n3]] (0-based), "bounds": [[lo], [hi]]}
Studio builds an EditableMesh from it (kit/studio/model_load.luau). Prints PACK {json}."""

import json
import os
import sys

import bpy
from mathutils import Matrix

ARGS = sys.argv[sys.argv.index("--") + 1:]
MANIFEST, OUT = ARGS[0], ARGS[1]
# rbx.BL_FROM_RBX (kit/blender/rbx.py): Roblox (x, y, z) -> Blender (x, -z, y); its inverse takes Blender to Roblox
BL_FROM_RBX = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
RBX = BL_FROM_RBX.inverted()
ROUND = 6

with open(MANIFEST, encoding="utf-8") as fh:
    manifest = json.load(fh)
os.makedirs(OUT, exist_ok=True)
done, missing = {}, []
for group, entry in sorted(manifest.get("groups", {}).items()):
    name = os.path.splitext(os.path.basename(entry.get("fbx") or ""))[0]
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH":
        missing.append(group)
        continue
    dg = bpy.context.evaluated_depsgraph_get()
    me = obj.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    to_rbx = RBX @ obj.matrix_world
    turn = to_rbx.to_3x3().inverted().transposed()          # (normals: the inverse transpose)
    uv_layer = me.uv_layers.active
    verts = [[round(c, ROUND) for c in (to_rbx @ v.co)] for v in me.vertices]
    uvs, uv_at, normals, n_at, tris = [], {}, [], {}, []

    def index(table, at, value):
        key = tuple(value)
        if key not in at:
            at[key] = len(table)
            table.append(list(value))
        return at[key]

    for t in me.loop_triangles:
        row_v, row_uv, row_n = [], [], []
        for li, vi in zip(t.loops, t.vertices):
            uv = uv_layer.data[li].uv if uv_layer else (0.0, 0.0)
            row_v.append(vi)
            row_uv.append(index(uvs, uv_at, (round(uv[0], ROUND), round(1.0 - uv[1], ROUND))))
            n = (turn @ me.corner_normals[li].vector).normalized()
            row_n.append(index(normals, n_at, (round(n.x, ROUND), round(n.y, ROUND), round(n.z, ROUND))))
        tris.append(row_v + row_uv + row_n)
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    # an uploaded mesh is centred on its bounds by Roblox's importer; a MeshPart made from an EditableMesh keeps the
    # vertices where they are given (measured 2026-11-18: a box built round (10, 10, 10) on a part at (0, 50, 0)
    # was hit by a ray at (10, 60, 11)) - so every group is written centred, as the upload would stand it
    mid = [(a + b) / 2.0 for a, b in zip(lo, hi)]
    verts = [[round(v[i] - mid[i], ROUND) for i in range(3)] for v in verts]
    with open(os.path.join(OUT, f"mesh_{group}.json"), "w", encoding="utf-8") as fh:
        json.dump({"group": group, "object": name, "verts": verts, "uvs": uvs, "normals": normals, "tris": tris,
                   "bounds": [lo, hi]}, fh, separators=(",", ":"))
    done[group] = {"tris": len(tris), "verts": len(verts), "bounds": [lo, hi]}
    obj.evaluated_get(dg).to_mesh_clear()
print("PACK " + json.dumps({"groups": done, "missing": missing}))
sys.exit(1 if missing or not done else 0)
