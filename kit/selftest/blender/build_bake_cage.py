"""build_bake_cage.py — POSITIVE fixture for A BAKE CAGE THE SCRIPT SETS (a.bake_cage, rbx_bakecage; the 3D
methods audit, S3b): two filleted lugs of different shapes side by side (touching; alike, they would share one place of the map) on the high-and-low route (Asset(low=...)), the group's cage set to 2 mm and
the left lug's own to 3 mm. The build must take those depths (the manifest's low facts: cage_mm 2, cage_set), say
them ("cage set: main 2 mm, LugA 3 mm") and pass `bake_cage`. With `shallow` after `--` the left lug's cage is
0.02 mm - under what its rounded high stands off its faceted low (build_bake_cage_shallow.py: the build must FAIL
`bake_cage` and say the depth it needs). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

SHALLOW = "shallow" in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
LUG = """
    part = Box(40, 70, 30)
    part = fillet(part.edges(), 8)
    """

a = rbx.Asset("_selftest_cage_shallow" if SHALLOW else "_selftest_cage", tex=512, size=(0.28, 0.25, 0.11),
              ground=False, low=3000)
a.real_scale(280.0)
a.material("steel", (0.56, 0.57, 0.58), metal=1.0, rough=0.35)
a.cad("LugA", LUG, "steel", pos=(-0.07, 0, 0), tol=0.6, angle=30.0)
a.cad("LugB", LUG.replace("70", "60").replace("8)", "5)"), "steel", pos=(0.07, 0, 0), tol=0.6, angle=30.0)
a.bake_cage(2.0)
a.bake_cage(0.02 if SHALLOW else 3.0, parts=["LugA"])
a.build()

# where the rays missed: the colour map's texels under each lug that came out dark (the steel is light) - a cage
# under the high's surface starts its rays inside it, and they find nothing
import json  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx_cutout  # noqa: E402

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
ids = np.zeros(len(me.polygons), np.int32)
me.attributes["kit_part"].data.foreach_get("value", ids)
names = list(obj["kit_parts"])
out = {}
for i, name in enumerate(names):
    sel = ids[tp] == i
    rows, cols, _pts = rbx_cutout.texels(uv.reshape(-1, 2)[tri.reshape(-1, 3)[sel]],
                                         co.reshape(-1, 3)[tv.reshape(-1, 3)[sel]], n)
    out[name] = {"texels": int(len(rows)), "dark": int((luma[rows, cols] < 0.15).sum())}
out["_names"] = names
print("CAGE " + json.dumps(out))
