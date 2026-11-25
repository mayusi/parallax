"""sections_cut.py — Blender side of `kit refs sections`: cut a model with planes and write the cut lines (mm).

    blender -b [file.blend] --factory-startup -P kit/refs/sections_cut.py -- <model.glb or -> <out.json>
        [--only a,b] [--hide a,b] [--mm-per-unit K | --match-length L_mm] [--at d1,d2,..] [--along x1,x2,..]
        [--flip] [--kit]

CROSS sections (--at): planes square to the model's length axis, d mm BEHIND ITS FRONT-MOST POINT; ALONG sections
(--along): planes through the length axis and up, x mm off the model's centre line. Every visible mesh is cut (or
--only / --hide by object-name substrings); each cut edge -> [[u, h], [u, h], object] in mm (cross: u = across; along:
u = mm behind the front). --kit: a kit build (.blend, Blender +y = the front, z up, studs: --mm-per-unit the
manifest's mm_per_stud); else the length axis is the longer horizontal one, its front at the max end (--flip: the min).
--match-length: the scale that makes this model as long as L mm (a reference model in its own units, scaled to ours).
"""

import json
import sys

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def _opt(flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _nums(flag):
    v = _opt(flag)
    return [float(t) for t in v.split(",") if t.strip()] if v else []


src, out = argv[0], argv[1]
only = [s.strip().lower() for s in (_opt("--only") or "").split(",") if s.strip()]
hide = [s.strip().lower() for s in (_opt("--hide") or "").split(",") if s.strip()]
kit_build, flip = "--kit" in argv, "--flip" in argv
if src != "-":
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    low = src.lower()
    if low.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=src)
    elif low.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=src)
    elif low.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=src)
    else:
        raise SystemExit(f"sections_cut: cannot read {src}")
objs = []
for o in bpy.data.objects:
    nm = o.name.lower()
    if o.type != "MESH" or o.hide_render or nm.startswith(("ground", "studio")):
        continue
    if (only and not any(s in nm for s in only)) or any(s in nm for s in hide):
        continue
    objs.append(o)
if not objs:
    print(json.dumps({"error": "no mesh left to cut (check --only / --hide)"}))
    raise SystemExit(0)
dg = bpy.context.evaluated_depsgraph_get()
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)])
hi = Vector([max(p[i] for p in pts) for i in range(3)])
ext = hi - lo
ax = 1 if kit_build else (0 if ext.x >= ext.y else 1)
across = 1 - ax
front_max = kit_build or not flip
front = hi[ax] if front_max else lo[ax]
mid = (lo[across] + hi[across]) / 2
mmpu = float(_opt("--mm-per-unit", "0") or 0)
if _opt("--match-length"):
    mmpu = float(_opt("--match-length")) / max(ext[ax], 1e-9)
if mmpu <= 0:
    mmpu = 1.0


def _behind(v):
    """mm behind the front-most point"""
    return ((front - v[ax]) if front_max else (v[ax] - front)) * mmpu


def _cut(no, co, uv):
    segs = []
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(o.matrix_world)
        r = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-7, plane_co=co,
                                   plane_no=no)
        for e in [g for g in r["geom_cut"] if isinstance(g, bmesh.types.BMEdge)]:
            a, b = e.verts[0].co, e.verts[1].co
            segs.append([uv(a), uv(b), o.name])
        bm.free()
        o.evaluated_get(dg).to_mesh_clear()
    return segs


n_len = Vector((1, 0, 0)) if ax == 0 else Vector((0, 1, 0))
n_across = Vector((1, 0, 0)) if across == 0 else Vector((0, 1, 0))
sign = 1.0 if front_max else -1.0
res = {"length_mm": ext[ax] * mmpu, "mm_per_unit": mmpu, "objects": [o.name for o in objs], "cross": [], "along": []}
for d in _nums("--at"):
    c = front - sign * d / mmpu
    res["cross"].append({"d": d, "segs": _cut(n_len, n_len * c, lambda v: [(v[across] - mid) * mmpu, v.z * mmpu])})
for x in _nums("--along"):
    c = mid + x / mmpu
    res["along"].append({"x": x, "segs": _cut(n_across, n_across * c, lambda v: [_behind(v), v.z * mmpu])})
with open(out, "w", encoding="utf-8") as fh:
    json.dump(res, fh)
print(json.dumps({"cut": out, "objects": len(objs), "length_mm": round(res["length_mm"], 2),
                  "cross": [len(s["segs"]) for s in res["cross"]], "along": [len(s["segs"]) for s in res["along"]]}))
