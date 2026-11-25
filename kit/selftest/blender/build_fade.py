"""build_fade.py — fixtures for SEE-THROUGH BY DEGREES (a.fade, rbx_cutout; the 3D methods audit, stage X). By the
word after `--`:
  (none)   a post and, in a group of its own, a pane that fades from clear at its foot to solid at its top (a rule
           on the point): the pane's colour map must carry the degrees in its alpha, the manifest must mark the
           group `alpha_mode: Transparency` and `alpha_soft`. After the build `FADE {json}`: the alpha read from
           the written file low and high on the pane, and how many degrees it holds.
  solid    the pane "faded" by a rule that says solid everywhere: `cutout` must FAIL (build_fade_solid.py).
  master   the same model as a MASTER (build_fade_master.py): `kit optimize` builds its game version from it - the
           faded pane's colour must come through as it is, not darkened by its own alpha (`game_fidelity` holds).
Used by `lune run kit selftest`. Never "fix" this file."""

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

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SOLID = "solid" in ARGS
MASTER = "master" in ARGS

a = rbx.Asset("_selftest_fade_solid" if SOLID else "_selftest_fade_master" if MASTER else "_selftest_fade", tex=256,
              size=(3.0, 3.0, 1.0), ground=True, **({"stage": "master"} if MASTER else {}))
a.material("stone", color=(0.6, 0.6, 0.58), rough=0.8)
a.material("glass", color=(0.7, 0.85, 0.9), rough=0.2)
a.box("Post", (0.5, 3.0, 1.0), (-1.25, 1.5, 0), "stone", bevel=0)
a.box("Pane", (2.5, 3.0, 0.1), (0.25, 1.5, 0), "glass", bevel=0, group="pane")
a.fade("Pane", keep=(lambda p: 1.0) if SOLID else (lambda p: p[1] / 3.0))
a.build()


def read_back():
    """what the finished build wrote, read here and printed for the build test"""
    manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
    grp = manifest["groups"]["pane"]
    obj = bpy.data.objects[a.name + "_pane"]
    rel = grp["textures"]["color"]
    img = bpy.data.images.load(rel if os.path.isabs(rel) else os.path.join(rbx.REPO, rel), check_existing=False)
    n = img.size[0]
    px = np.empty(n * n * 4, np.float32)
    img.pixels.foreach_get(px)
    alpha = px.reshape(n, n, 4)[..., 3]
    me = obj.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    uv = np.empty(len(me.loops) * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    tri, tv = np.empty(nt * 3, np.int64), np.empty(nt * 3, np.int64)
    me.loop_triangles.foreach_get("loops", tri)
    me.loop_triangles.foreach_get("vertices", tv)
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(rbx.BL_FROM_RBX.inverted() @ obj.matrix_world, np.float64)
    co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    rows, cols, pts = rbx_cutout.texels(uv.reshape(-1, 2)[tri.reshape(-1, 3)], co[tv.reshape(-1, 3)], n)
    y = pts[:, 1]
    got = alpha[rows, cols]
    print("FADE " + json.dumps({
        "file": os.path.basename(rel), "alpha_mode": grp.get("alpha_mode"), "alpha_soft": grp.get("alpha_soft"),
        "post_alpha_mode": manifest["groups"]["main"].get("alpha_mode"),
        "low": round(float(got[(y > 0.2) & (y < 0.6)].mean()), 3), "mid": round(float(got[(y > 1.3) & (y < 1.7)].mean()), 3),
        "high": round(float(got[(y > 2.4) & (y < 2.8)].mean()), 3),
        "degrees": int(len(np.unique(np.round(got * 255))))}))


if not (SOLID or MASTER):
    read_back()
