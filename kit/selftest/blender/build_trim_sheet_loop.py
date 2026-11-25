"""build_trim_sheet_loop.py — fixture for A TRIM SHEET WHOSE NOISE IS ON A LOOP (card fczy; rbx_wear.wrap_x): the
trim sheet fixture's bands and finishes with noise_3d on - every noise field drawn on a loop the sheet's width
long, so the sheet repeats along its length AS BAKED: no cross-fade at its ends (facts.trim_sheet.faded false,
trim_fade not named), and the rows no band lies on hold their nearest band's colour, not black.
After the build `LOOP {json}`: the colour map's darkest row outside the bands and the darkest inside them.
Used by kit/test/python/test_trim_sheet_left.py. Never "fix" this file."""

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

a = rbx.Asset("_selftest_trim_sheet_loop", tex=512, size=(8.0, 0, 8.5), ground=True, noise_3d=True,
              spec_occlusion=0.0)
a.material("planks", color=(0.42, 0.3, 0.18), rough=0.7, wear=0.6, grime=0.4)
a.material("stone", color=(0.5, 0.5, 0.48), rough=0.8, wear=0.5)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5, wear=0.5)
a.trim_sheet([("planks", "planks", 4.0), ("stone", "stone", 1.5), ("edge", "iron", 1.0), ("rivets", "iron", 0.5)],
             studs=8.0)
a.build()
man = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
color = next(v for k, v in man["groups"]["main"]["textures"].items() if k == "color")
img = bpy.data.images.load(color if os.path.isabs(color) else os.path.join(rbx.REPO, color), check_existing=False)
w, h = img.size
px = np.empty(w * h * 4, np.float32)
img.pixels.foreach_get(px)
px = px.reshape(h, w, 4)[..., :3].mean(axis=2)
yc = (np.arange(h) + 0.5) / h
on = np.zeros(h, bool)
for b in man["trim_sheet"]["bands"].values():
    on |= (yc >= b["v0"]) & (yc <= b["v1"])
print("LOOP " + json.dumps({"off_band_darkest": round(float(px[~on].mean(axis=1).min()), 4) if (~on).any() else None,
                            "on_band_darkest": round(float(px[on].mean(axis=1).min()), 4)}))
