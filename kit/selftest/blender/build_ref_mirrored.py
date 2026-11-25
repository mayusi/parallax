"""build_ref_mirrored.py — NEGATIVE fixture: the same model as build_view_gaps_ok.py (a lug on its RIGHT side), but its
FRONT and TOP traces are drawn as mirror images (the lug on the left) — the way a downloaded reference chart can be.
Must be named: reference_front_mirrored and reference_top_mirrored (no shape change fixes a flipped chart).
Never "fix" this file. Used by `lune run kit selftest`.
"""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

# the parts (Roblox studs: x right, y up, z back): body x -0.5..0.5, y 0..1, z -2..2; grip x -0.3..0.3, y -1.2..0,
# z 0.4..1.2; lug x 0.5..0.8, y 0.4..0.7, z -1.5..-0.5. Overall x -0.5..0.8, y -1.2..1.0, z -2..2
W, H, L = 1.3, 2.2, 4.0
side = [[0, 0.3], [0.2, 0.3], [0.2, 0], [0.4, 0], [0.4, 0.3], [1, 0.3], [1, 0.55], [0, 0.55]]  # u = (2 - z) / L
# front: u = (0.8 - x) / W (seen from the front, the model's right side +X is on the picture's left), h = (y + 1.2) / W
front = [[0.5 / W, 0], [1.1 / W, 0], [1.1 / W, 1.2 / W], [1, 1.2 / W], [1, H / W], [0.3 / W, H / W],
         [0.3 / W, 1.9 / W], [0, 1.9 / W], [0, 1.6 / W], [0.3 / W, 1.6 / W], [0.3 / W, 1.2 / W], [0.5 / W, 1.2 / W]]
back = [[1 - u, h] for u, h in front]  # seen from behind: +X on the right
front = [[1 - u, h] for u, h in front]  # MIRRORED: the chart drawn flipped (the lug on the picture's right)
top = [[0, 0.075], [0.625, 0.075], [0.625, 0], [0.875, 0], [0.875, 0.075], [1, 0.075], [1, 0.325], [0, 0.325]]
top = [[u, round(0.325 - h, 6)] for u, h in top]  # MIRRORED: the lug on the other side of the length
out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
paths = {}
for view, outline in (("side", side), ("front", front), ("back", back), ("top", top)):
    t = {"name": f"_view_gaps_{view}", "source": f"kit/selftest/refs/_view_gaps_{view}.png", "front": "right",
         "height_ratio": round(max(h for _u, h in outline), 6), "holes": [], "outline": outline}
    paths[view] = os.path.join(out, f"_ref_mirrored_{view}.trace.json")
    with open(paths[view], "w", encoding="utf-8") as fh:
        json.dump(t, fh)

a = rbx.Asset("_selftest_ref_mirrored", tex=64, size=(W, H, L))
a.real_scale(100.0)  # 1 stud = 100 mm: the gaps are said in millimetres
a.material("body", color=(0.5, 0.5, 0.52))
a.box("Body", (1.0, 1.0, 4.0), (0, 0.5, 0), "body", bevel=0)
a.box("Grip", (0.6, 1.2, 0.8), (0, -0.6, 0.8), "body", bevel=0)
a.box("Lug", (0.3, 0.3, 1.0), (0.65, 0.55, -1.0), "body", bevel=0)
for view, path in paths.items():
    a.trace_match(path, view=view)
a.build()
