"""build_view_gaps_front.py — NEGATIVE fixture: the model is 25% too WIDE for its front view (its side view matches).
Must be named: view_gaps_front. Never "fix" this file.
Only the side view used to be scored edge by edge in practice: a front / back / top view could be wrong unnoticed. The
traces are made at run time in build/selftest/: the same model as build_view_gaps_ok.py (a 4-stud body, a grip, a lug
on its right side), its front trace drawn 0.8x as wide — every width in it is 80% of the model's. Used by
`lune run kit selftest`.
"""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

W, H, L = 1.3, 2.2, 4.0
side = [[0, 0.3], [0.2, 0.3], [0.2, 0], [0.4, 0], [0.4, 0.3], [1, 0.3], [1, 0.55], [0, 0.55]]
front = [[0.5 / W, 0], [1.1 / W, 0], [1.1 / W, 1.2 / W], [1, 1.2 / W], [1, H / W], [0.3 / W, H / W],
         [0.3 / W, 1.9 / W], [0, 1.9 / W], [0, 1.6 / W], [0.3 / W, 1.6 / W], [0.3 / W, 1.2 / W], [0.5 / W, 1.2 / W]]
# 0.8x as wide: a trace's units are its own width, so the heights grow by 1 / 0.8 (the outline keeps u 0..1)
front = [[u, h / 0.8] for u, h in front]
out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
paths = {}
for view, outline in (("side", side), ("front", front)):
    t = {"name": f"_view_gaps_{view}", "source": f"kit/selftest/refs/_view_gaps_{view}.png", "front": "right",
         "height_ratio": round(max(h for _u, h in outline), 6), "holes": [], "outline": outline}
    paths[view] = os.path.join(out, f"_view_gaps_front_{view}.trace.json")
    with open(paths[view], "w", encoding="utf-8") as fh:
        json.dump(t, fh)

a = rbx.Asset("_selftest_view_gaps_front", tex=64, size=(W, H, L))
a.real_scale(100.0)  # 1 stud = 100 mm: 130 mm wide where the reference is 104 mm
a.material("body", color=(0.5, 0.5, 0.52))
a.box("Body", (1.0, 1.0, 4.0), (0, 0.5, 0), "body", bevel=0)
a.box("Grip", (0.6, 1.2, 0.8), (0, -0.6, 0.8), "body", bevel=0)
a.box("Lug", (0.3, 0.3, 1.0), (0.65, 0.55, -1.0), "body", bevel=0)
for view, path in paths.items():
    a.trace_match(path, view=view)
a.build()
