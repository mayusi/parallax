"""build_project_ok.py — POSITIVE fixture: a grey 4 x 1 x 0.5 stud block painted with its side picture (a.project) and
a decal straightened out of its top picture (a.decal). Must NOT be named: projection_ (alignment, coverage, match,
decal).
The pictures and their traces are made at run time in build/selftest/: the side picture (440 x 140 px, white
backdrop) holds the block at x 40..400, y 25..115 — the rear half red / dark red stripes, the front half blue under a
yellow band along its top (a mirrored or upside-down projection shows at once); the top picture (440 x 100) holds it
at x 40..400, y 25..70 in grey with an orange marking drawn as a slanted quad. Seen from the side camera, the baked
model must show its picture cell by cell (projection_match); the decal must land on the top face. Used by
`lune run kit selftest`.
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

side = np.ones((140, 440, 4), np.float32)  # sRGB values, top row first
for k, x in enumerate(range(40, 220, 30)):
    side[25:115, x:x + 30, :3] = (0.85, 0.12, 0.1) if k % 2 == 0 else (0.45, 0.05, 0.08)
side[25:115, 220:400, :3] = (0.15, 0.25, 0.8)
side[25:40, 220:400, :3] = (0.95, 0.85, 0.1)
side_png = os.path.join(out, "_project_side.png")
rbx_project.save_picture(side, side_png)
top = np.ones((100, 440, 4), np.float32)
top[25:70, 40:400, :3] = 0.5
QUAD = [(250, 35), (300, 38), (296, 60), (246, 57)]  # the marking, photographed at a slant
top[rbx_project.fill_rings([QUAD], 440, 100)] = (0.95, 0.55, 0.1, 1.0)
top_png = os.path.join(out, "_project_top.png")
rbx_project.save_picture(top, top_png)


def trace(name, png, hr, y1):
    t = {"name": name, "source": os.path.relpath(png, rbx.REPO).replace("\\", "/"), "front": "right",
         "height_ratio": hr, "holes": [], "outline": [[0.0, 0.0], [1.0, 0.0], [1.0, hr], [0.0, hr]],
         "frame": {"x0": 40.0, "y1": y1, "length_px": 360.0}}
    path = os.path.join(out, f"{name}.trace.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(t, fh)
    return path


side_trace = trace("_project_side", side_png, 0.25, 115.0)
top_trace = trace("_project_top", top_png, 0.125, 70.0)

a = rbx.Asset("_selftest_project_ok", tex=512, size=(0.5, 1.0, 4.0))
a.material("paint", color=(0.5, 0.5, 0.5), rough=0.5)
a.box("Rear", (0.5, 1.0, 2.0), (0, 0.5, 1.0), "paint", bevel=0)
a.box("Front", (0.5, 1.0, 2.0), (0, 0.5, -1.0), "paint", bevel=0)
a.trace_match(side_trace)
a.project(side_trace)
a.decal("badge", top_trace, box=QUAD, view="top")
a.build()
