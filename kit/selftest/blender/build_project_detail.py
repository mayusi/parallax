"""build_project_detail.py — POSITIVE fixture: a block in two materials (bronze rear, blue front) given the FINE
STRUCTURE of a studio-lit side picture (a.project(..., detail=1.0, bump=1.0)). Must NOT be named: projection_
(detail, match, coverage, alignment).
The picture is made at run time in build/selftest/ (440 x 140 px, black backdrop, the block at x 40..400, y 25..115):
a warm grey surface under a strong left-to-right light (x0.25 .. x1.0) with a big soft shadow, cut by fine engraving
lines (2 px, 30% albedo) every 24 px and one along the middle. Its colour, its light and its shadow must NOT reach the
model (each material's mean colour within 4/255: projection_detail), its lines must (contrast transferred, and seen
from the side camera the model's fine structure follows the picture's: projection_match). Painting the same picture in
colour mode moved the bronze by -37/255 (luma) and turned the blue warm grey (measured 2026-10-07: it becomes the lit
picture's colour). Used by `lune run kit selftest`.
"""

import json
import os
import sys

import numpy as np

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_project  # noqa: E402

out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
H, W = 140, 440
yy, xx = np.mgrid[0:H, 0:W] + 0.5
albedo = np.zeros((H, W, 3))
albedo[25:115, 40:400] = (0.62, 0.55, 0.45)  # a warm grey: not the model's bronze / blue
lines = np.zeros((H, W), bool)
for x in range(52, 400, 24):
    lines[35:105, x:x + 2] = True
lines[69:71, 50:390] = True
albedo[lines] *= 0.3
light = 0.25 + 0.75 * np.clip((xx - 40) / 360, 0, 1)  # the studio light: strong left-to-right
shadow = 1 - 0.55 * np.clip((34 - np.hypot(xx - 300, yy - 72)) / 10, 0, 1)  # a big soft shadow
lin = albedo * (light * shadow)[..., None]
pic = np.zeros((H, W, 4), np.float32)
pic[..., :3] = rbx_project.linear_to_srgb(lin)
pic[..., 3] = 1
png = os.path.join(out, "_project_detail.png")
rbx_project.save_picture(pic, png)
trace = {"name": "_project_detail", "source": os.path.relpath(png, rbx.REPO).replace("\\", "/"), "front": "right",
         "height_ratio": 0.25, "holes": [], "outline": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.25], [0.0, 0.25]],
         "frame": {"x0": 40.0, "y1": 115.0, "length_px": 360.0}, "mask": "backdrop [0, 0, 0]", "bg": "auto"}
path = os.path.join(out, "_project_detail.trace.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(trace, fh)

a = rbx.Asset("_selftest_project_detail", tex=512, size=(0.5, 1.0, 4.0))
a.material("bronze", color=(0.55, 0.36, 0.2), metal=0.9, rough=0.35)
a.material("paint", color=(0.2, 0.3, 0.6), rough=0.5)
a.box("Rear", (0.5, 1.0, 2.0), (0, 0.5, 1.0), "bronze", bevel=0)
a.box("Front", (0.5, 1.0, 2.0), (0, 0.5, -1.0), "paint", bevel=0)
a.trace_match(path)
a.project(path, detail=1.0, bump=1.0)
a.build()
