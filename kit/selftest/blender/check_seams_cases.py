"""check_seams_cases.py — fixture: the build's SEAM CHECK (`seams`, rbx_seams) on a REAL baked model. A ball on a slab
is built (a real unwrap, a real bake); one line `SEAMS {json}`, read by kit/test/python/test_seams_build.py:
  built    what the build itself said of the ball's map: seams on smooth surface were judged, none shows a step,
           no `seams` warning
  damaged  the same mesh held against a DAMAGED copy of its colour map (every texel left of the map's middle made
           redder: an island there no longer matches its neighbour across the seam) - the check must fail and say
           where
  crate    a box's seams all lie on sharp edges: cut, but none judged
Never "fix" this file."""

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

a = rbx.Asset("_selftest_seams", size=(6.0, 5.0, 6.0), ground=True)
a.material("stone", color=(0.5, 0.5, 0.48), rough=0.8)
a.material("wood", color=(0.42, 0.3, 0.18), rough=0.7)
a.box("Slab", (6.0, 1.0, 6.0), (0, 0.5, 0), "wood", bevel=0)
a.sphere("Ball", 2.0, (0, 3.0, 0), "stone", group="ball", segments=24, rings=12)
a.build()

manifest = json.load(open(os.path.join(rbx.BUILD, "models", "_selftest_seams.manifest.json"), encoding="utf-8"))
out = {"built": dict(a._seams)}
ball = bpy.data.objects["_selftest_seams_ball"]
color = manifest["groups"]["ball"]["textures"]["color"]
path = color if os.path.isabs(color) else os.path.join(rbx.REPO, color)
img = bpy.data.images.load(path, check_existing=False)
w, h = img.size
px = np.empty(w * h * 4, np.float32)
img.pixels.foreach_get(px)
px = px.reshape(h, w, 4)
px[:, : w // 2, 0] = np.clip(px[:, : w // 2, 0] + 0.25, 0, 1)
bad = bpy.data.images.new("_selftest_seams_damaged", w, h, alpha=True)
bad.pixels.foreach_set(px.ravel())
bad.filepath_raw = os.path.join(rbx.RENDERS, "_selftest_seams_damaged.png")
bad.file_format = "PNG"
os.makedirs(rbx.RENDERS, exist_ok=True)
bad.save()
facts, checks = a._seam_check(ball, "ball", {"color": bad.filepath_raw})
out["damaged"] = {"facts": facts, "checks": [{k: c.get(k) for k in ("name", "ok", "severity", "fix")} for c in checks]}
facts, checks = a._seam_check(ball, "ball", {"color": path})
out["again"] = {"share": facts["share"], "ok": all(c.get("ok") for c in checks)}
print("SEAMS " + json.dumps(out))
