"""build_project_misaligned.py — NEGATIVE fixture: the block's side picture was changed after it was traced (its
content now sits 40 px further right), so the trace's frame points at the wrong place and the projection would paint
the rear of the block with the backdrop. Must be named: projection_alignment. Never "fix" this file.
The picture (480 x 140 px, white backdrop) and its trace are made at run time in build/selftest/: the block at
x 80..440, y 25..115 (rear half red, front half blue), the trace's frame still at x 40..400 (where it was traced).
Used by `lune run kit selftest`.
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
side = np.ones((140, 480, 4), np.float32)  # sRGB values, top row first
side[25:115, 80:260, :3] = (0.85, 0.12, 0.1)
side[25:115, 260:440, :3] = (0.15, 0.25, 0.8)
png = os.path.join(out, "_project_shifted.png")
rbx_project.save_picture(side, png)
trace = {"name": "_project_shifted", "source": os.path.relpath(png, rbx.REPO).replace("\\", "/"), "front": "right",
         "height_ratio": 0.25, "holes": [], "outline": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.25], [0.0, 0.25]],
         "frame": {"x0": 40.0, "y1": 115.0, "length_px": 360.0}}
path = os.path.join(out, "_project_shifted.trace.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(trace, fh)

a = rbx.Asset("_selftest_project_misaligned", tex=256, size=(0.5, 1.0, 4.0))
a.material("paint", color=(0.5, 0.5, 0.5), rough=0.5)
a.box("Rear", (0.5, 1.0, 2.0), (0, 0.5, 1.0), "paint", bevel=0)
a.box("Front", (0.5, 1.0, 2.0), (0, 0.5, -1.0), "paint", bevel=0)
a.project(path)
a.build()
