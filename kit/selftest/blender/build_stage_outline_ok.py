"""build_stage_outline_ok.py — POSITIVE fixture: the same HERO block, its side silhouette AT its reference (a plain
4 x 1 stud block against a plain traced block: IoU ~1.0 >= 0.9). The stage gate must NOT name it: past the blockout,
detail work is judged as usual. Never "fix" this file.
The reference is made at run time in build/selftest/. Used by `lune run kit selftest`. A hero build writes its
part review to assets/models/: removed again after.
"""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
trace = {"name": "_stage_block_side", "source": "kit/selftest/refs/_stage_block.png", "front": "right",
         "height_ratio": 0.25, "holes": [], "outline": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.25], [0.0, 0.25]]}
with open(os.path.join(out, "_stage_block_side.trace.json"), "w", encoding="utf-8") as fh:
    json.dump(trace, fh)

a = rbx.Asset("_selftest_stage_outline_ok", tex=64, size=(0.5, 1.0, 4.0), quality="hero")
a.material("body", color=(0.55, 0.56, 0.6))
a.box("Body", (0.5, 1.0, 4.0), (0, 0.5, 0), "body", bevel=0)
a.trace_match(os.path.join(out, "_stage_block_side.trace.json"))
try:
    a.build()
finally:
    review = os.path.join(rbx.REPO, "assets", "models", f"{a.name}.parts.md")
    if os.path.isfile(review):
        os.remove(review)
