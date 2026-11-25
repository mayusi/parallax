"""build_paint.py — POSITIVE fixture for VERTEX PAINT (a.vertex_paint, rbx_paint; the 3D methods audit, S4): a pale
post painted by a rule on the point - dark at its foot, as it is at its top (a grey ramp over its height) - with a
cap on it that nobody painted. The build must multiply the paint into the colour map (the post's foot far darker
than its top, the cap untouched), write it into the mesh's vertex colours, find it again in the exported file
(`export_read_back` passes) and say it ("painted: main (Post: ..."). After the build one line `PAINT {json}` for
kit/test/python/test_paint_build.py: the baked colour's brightness low and high on the post and on the cap, and
the vertex colours read from the exported FBX by a fresh import. Used by `lune run kit selftest`. Never "fix"
this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx  # noqa: E402
import rbx_cutout  # noqa: E402

a = rbx.Asset("_selftest_paint", tex=256, size=(1.2, 3.4, 1.2), ground=True)
a.material("stone", color=(0.7, 0.68, 0.62), rough=0.8)
a.box("Post", (1.0, 3.0, 1.0), (0, 1.5, 0), "stone", bevel=0)
a.box("Cap", (1.2, 0.4, 1.2), (0, 3.2, 0), "stone", bevel=0)
a.vertex_paint(lambda p: 0.25 + 0.75 * min(max(p[1] / 3.0, 0.0), 1.0), parts=["Post"])
a.build()

manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
obj = bpy.data.objects[a.name]
color = manifest["groups"]["main"]["textures"]["color"]
img = bpy.data.images.load(color if os.path.isabs(color) else os.path.join(rbx.REPO, color), check_existing=False)
n = img.size[0]
tex = np.empty(n * n * 4, np.float32)
img.pixels.foreach_get(tex)
luma = tex.reshape(n, n, 4)[..., :3].mean(axis=2)
me = obj.data
me.calc_loop_triangles()
nt = len(me.loop_triangles)
uv = np.empty(len(me.loops) * 2, np.float64)
me.uv_layers.active.data.foreach_get("uv", uv)
tri, tv, tp = np.empty(nt * 3, np.int64), np.empty(nt * 3, np.int64), np.empty(nt, np.int64)
me.loop_triangles.foreach_get("loops", tri)
me.loop_triangles.foreach_get("vertices", tv)
me.loop_triangles.foreach_get("polygon_index", tp)
co = np.empty(len(me.vertices) * 3, np.float64)
me.vertices.foreach_get("co", co)
m = np.array(rbx.BL_FROM_RBX.inverted() @ obj.matrix_world, np.float64)
co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
ids = np.zeros(len(me.polygons), np.int32)
me.attributes["kit_part"].data.foreach_get("value", ids)
names = list(obj["kit_parts"])
out = {}
for i, name in enumerate(names):
    sel = ids[tp] == i
    rows, cols, pts = rbx_cutout.texels(uv.reshape(-1, 2)[tri.reshape(-1, 3)[sel]], co[tv.reshape(-1, 3)[sel]], n)
    # (its upright sides alone, away from where the cap sits on the post: the occlusion darkens those)
    reach = np.abs(pts[:, [0, 2]]).max(axis=1)
    side = reach > 0.98 * reach.max()
    y = (pts[:, 1] - pts[:, 1].min()) / (pts[:, 1].max() - pts[:, 1].min())
    lo, hi = side & (y > 0.10) & (y < 0.30), side & (y > 0.65) & (y < 0.85)
    out[name] = {"low": round(float(luma[rows[lo], cols[lo]].mean()), 3),
                 "high": round(float(luma[rows[hi], cols[hi]].mean()), 3)}

# the exported file, read by a fresh import: its vertex colours by height
fbx = manifest["groups"]["main"]["fbx"]
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=fbx if os.path.isabs(fbx) else os.path.join(rbx.REPO, fbx))
got = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
cols = got.data.color_attributes
if len(cols):
    px = np.empty(len(cols[0].data) * 4, np.float64)
    cols[0].data.foreach_get("color", px)
    px = px.reshape(-1, 4)[:, :3].mean(axis=1)
    out["file"] = {"darkest": round(float(px.min()), 3), "lightest": round(float(px.max()), 3),
                   "white_share": round(float((px > 0.98).mean()), 3)}
else:
    out["file"] = None
print("PAINT " + json.dumps(out))
