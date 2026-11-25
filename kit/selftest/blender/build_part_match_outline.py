"""build_part_match_outline.py — POSITIVE fixture for an OUTLINE-ONLY part ("<part>!"): the model's handle is a frame
of four bars round a big window (a design detail the picture's part does not have — the Silverballer's three-hole
trigger against the Hardballer's windowed one); its OUTLINE is exactly the traced handle's. Compared as "handle!",
both are filled and match. (As a plain "handle" the window alone would take a quarter of its area: IoU 0.75.)
Must NOT be named: part_match_side. Used by `lune run kit selftest`. Never "fix" this file."""

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
TRACE = {"name": "_part_match_ol", "front": "right", "height_ratio": 0.55, "holes": [],
         "outline": [[0, 0.3], [0.125, 0.3], [0.125, 0.0], [0.275, 0.0], [0.275, 0.3], [1, 0.3], [1, 0.55], [0, 0.55]],
         "parts": {"handle": [[0.125, 0.0], [0.275, 0.0], [0.275, 0.3], [0.125, 0.3]]}}
trace = os.path.join(out, "_part_match_ol.trace.json")
with open(trace, "w", encoding="utf-8") as fh:
    json.dump(TRACE, fh)

a = rbx.Asset("_selftest_part_match_outline", tex=64, size=(0.5, 2.2, 4.0), ground=False)
a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
a.material("grip", (0.1, 0.1, 0.1), rough=0.7)
a.box("Body", (0.5, 1.0, 4.0), (0, 0, 0), "steel", bevel=0)
# the handle (0.6 along z, 1.2 tall, under the body's rear: z 0.9 .. 1.5, y -1.7 .. -0.5) as four bars round a window
a.box("HandleBack", (0.4, 1.2, 0.15), (0, -1.1, 1.425), "grip", bevel=0)
a.box("HandleFront", (0.4, 1.2, 0.15), (0, -1.1, 0.975), "grip", bevel=0)
a.box("HandleTop", (0.4, 0.2, 0.3), (0, -0.6, 1.2), "grip", bevel=0)
a.box("HandleBottom", (0.4, 0.2, 0.3), (0, -1.6, 1.2), "grip", bevel=0)
a.trace_match(trace, bar=0.5, parts={"handle!": ["HandleBack", "HandleFront", "HandleTop", "HandleBottom"]})
a.build()
