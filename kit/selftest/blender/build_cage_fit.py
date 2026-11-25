"""build_cage_fit.py - fixture for THE FITTED BAKE CAGE and THE WRONG SURFACE (a.bake_cage("fit"), rbx_bakecage; the
3D methods audit's PARTLY "a hand-sculpted cage around a complex part", card urp5).

One part no single depth bakes: a block with two slots either side of a fin leaning 8 deg (the far wall of the
second slot 0.61 mm from the fin's foot), and a dome 3 mm proud that lives on the high only. After `--`:
  fit   a.bake_cage("fit")   - must bake the dome AND the walls right; bake_cross / bake_cage_pinch / bake_misses pass
  one   a.bake_cage(1.0)     - one shallow depth: the dome is lost; bake_cage FAILS (it needs 2.7 mm) and so does
                               bake_cross (an error: the script set the cage)
  none  the kit's own depth  - 4.4 mm, deep enough for the dome: its rays start past the fin and the far walls -
                               bake_cross WARNS (the kit set it), and calm_normals hides most of it in the map
  parts a.bake_cage("fit", parts=["Body"]) beside a second part, a plain peg, at the kit's own depth: two parts,
                               so the bake explodes them apart (bake groups); the body must still bake right and its
                               bake_cross is an ERROR check while the peg's is a warning
Prints CAGEFIT {...}: the baked normal map read against the truth - on the slot walls the share of texels more than
5 deg off the true face (measured against the low's own shading normal), on the dome the error against the
sphere's own tilt. Used by kit/test/python/test_cage_fit_build.py. Never "fix" this file."""

import json
import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = next((a_ for a_ in args if a_ in ("fit", "one", "none", "parts")), "fit")
R, CY = 12.1667, 2.8333   # the dome: a sphere of R mm about (-15, CY, 0), cut at y = 12 (3 mm tall, 8 mm across)
BODY = """
    outline = [(-30, -12), (30, -12), (30, 12), (12.75, 12), (12.75, 0), (12.14, 0), (10.46, 12), (9.86, 12),
               (11.54, 0), (9.25, 0), (9.25, 12), (-30, 12)]
    part = extrude(Polygon(*outline, align=None), amount=20, both=True)
    """
DOME = f"""
    part = Pos(-15, {CY}, 0) * Sphere({R})
    part &= Pos(-15, 13.5, 0) * Box(30, 3, 30)
    """

a = rbx.Asset(f"_selftest_cagefit_{MODE}", tex=512, size=(0.25, 0.096, 0.143) if MODE == "parts" else
              (0.214, 0.096, 0.143), ground=False, low=4000)
a.real_scale(280.0)
a.material("steel", (0.56, 0.57, 0.58), metal=1.0, rough=0.35)
a.cad("Body", BODY, "steel", tol=0.3, angle=20.0)
a.cad("Dome", DOME, "steel", tol=0.1, angle=10.0, low=False)
if MODE == "parts":   # (a plain peg against the body's right end, 10 mm cube)
    a.cad("Peg", """
    part = Box(10, 10, 10)
    """, "steel", pos=(35.0 / 280.0, 0, 0), tol=0.3, angle=20.0)
    a.bake_cage("fit", parts=["Body"])
elif MODE == "one":
    a.bake_cage(1.0)
elif MODE == "fit":
    a.bake_cage("fit")
a.build()

import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx_cutout  # noqa: E402

man = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
obj = bpy.data.objects[a.name]
nm = man["groups"]["main"]["textures"]["normal"]
img = bpy.data.images.load(nm if os.path.isabs(nm) else os.path.join(rbx.REPO, nm), check_existing=False)
img.colorspace_settings.name = "Non-Color"
n = img.size[0]
px = np.empty(n * n * 4, np.float32)
img.pixels.foreach_get(px)
me = obj.data
me.calc_loop_triangles()
nt = len(me.loop_triangles)
uv = np.empty(len(me.loops) * 2, np.float64)
me.uv_layers.active.data.foreach_get("uv", uv)
tri, tv, tp = np.empty(nt * 3, np.int64), np.empty(nt * 3, np.int64), np.empty(nt, np.int64)
me.loop_triangles.foreach_get("loops", tri)
me.loop_triangles.foreach_get("vertices", tv)
me.loop_triangles.foreach_get("polygon_index", tp)
mw = np.array(obj.matrix_world)
inv = np.linalg.inv(mw[:3, :3])
co = np.empty(len(me.vertices) * 3, np.float64)
me.vertices.foreach_get("co", co)
co = (co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]) * 280.0     # mm, the world (Blender: Z up)
fn = np.empty(len(me.polygons) * 3, np.float64)
me.polygons.foreach_get("normal", fn)
fn = fn.reshape(-1, 3) @ inv
fn /= np.linalg.norm(fn, axis=1, keepdims=True)
cn = np.empty(len(me.loops) * 3, np.float64)
me.corner_normals.foreach_get("vector", cn)
cn = cn.reshape(-1, 3) @ inv
cn /= np.linalg.norm(cn, axis=1, keepdims=True)
uvt = uv.reshape(-1, 2)[tri.reshape(-1, 3)]
rows, cols, pts = rbx_cutout.texels(uvt, co[tv.reshape(-1, 3)], n)
_r, _c, nrm = rbx_cutout.texels(uvt, np.repeat(fn[tp][:, None, :], 3, axis=1), n)
_r, _c, shade = rbx_cutout.texels(uvt, cn[tri.reshape(-1, 3)], n)
shade /= np.linalg.norm(shade, axis=1, keepdims=True)
ts = px.reshape(n, n, 4)[rows, cols, :3] * 2.0 - 1.0
tilt = np.degrees(np.arccos(np.clip(ts[:, 2] / np.maximum(np.linalg.norm(ts, axis=1), 1e-9), -1, 1)))
# (the body's own middle: the peg, when there, sits past its right end)
mid = (co.min(axis=0) + np.array([min(co[:, 0].max(), co[:, 0].min() + 60.0), co[:, 1].max(), co[:, 2].max()])) / 2.0
sx = pts[:, 0] - mid[0]
# the slot walls (x 9.25 facing +x, x 12.75 facing -x): their true face against the low's shading normal
wall = ((nrm[:, 0] > 0.99) & (np.abs(sx - 9.25) < 0.2)) | ((nrm[:, 0] < -0.99) & (np.abs(sx - 12.75) < 0.2))
want_wall = np.degrees(np.arccos(np.clip((shade * nrm).sum(axis=1), -1, 1)))
# the dome: texels of the top face within 7 mm of its axis; the truth is the sphere's own tilt
top = (nrm[:, 2] > 0.99) & (pts[:, 2] > mid[2] + 11.9)
r_ = np.hypot(pts[:, 0] - (mid[0] - 15.0), pts[:, 1] - mid[1])
dome = top & (r_ < 7.0)
want_dome = np.degrees(np.arcsin(np.clip(r_ / R, 0, 1)))
out = {"mode": MODE,
       "wall_texels": int(wall.sum()),
       "wall_wrong": round(float((np.abs(tilt - want_wall)[wall] > 5.0).mean()), 4) if wall.any() else None,
       "dome_texels": int(dome.sum()),
       "dome_err_p50": round(float(np.median(np.abs(tilt - want_dome)[dome])), 2) if dome.any() else None,
       "dome_err_p90": round(float(np.percentile(np.abs(tilt - want_dome)[dome], 90)), 2) if dome.any() else None}
print("CAGEFIT " + json.dumps(out))
