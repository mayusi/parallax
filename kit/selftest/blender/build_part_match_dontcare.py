"""build_part_match_dontcare.py — POSITIVE fixture: a don't-care box must not STEER the fit. The same body and handle as
build_part_match_ok.py (the handle exactly where the trace has it), plus a tall FIN on the body's front top that the
trace does not have — boxed out with dont_care=. Both outlines are fitted by their bounding boxes; before the fix the
fin made the model's box taller, the frame shifted by half the fin, and the handle (which IS right) read as misplaced.
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
# design units: u = (2 - z) / 4 (the back z = +2 -> 0, the front z = -2 -> 1), v = (y + 1.7) / 4; height 2.2 / 4
TRACE = {"name": "_part_match_dc", "front": "right", "height_ratio": 0.55, "holes": [],
         "outline": [[0, 0.3], [0.125, 0.3], [0.125, 0.0], [0.275, 0.0], [0.275, 0.3], [1, 0.3], [1, 0.55], [0, 0.55]],
         "parts": {"handle": [[0.125, 0.0], [0.275, 0.0], [0.275, 0.3], [0.125, 0.3]]}}
trace = os.path.join(out, "_part_match_dc.trace.json")
with open(trace, "w", encoding="utf-8") as fh:
    json.dump(TRACE, fh)

a = rbx.Asset("_selftest_part_match_dontcare", tex=64, size=(0.5, 3.0, 4.0), ground=False)
a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
a.material("grip", (0.1, 0.1, 0.1), rough=0.7)
a.box("Body", (0.5, 1.0, 4.0), (0, 0, 0), "steel", bevel=0)
a.box("Handle", (0.4, 1.2, 0.6), (0, -1.1, 1.2), "grip", bevel=0)
a.box("Fin", (0.2, 0.8, 0.8), (0, 0.9, -1.2), "steel", bevel=0)  # (not in the picture: on purpose)
# the fin's box in the trace's units: u 0.6 .. 0.9 (z -0.4 .. -1.6), v from just under the body's top to above the fin
a.trace_match(trace, bar=0.5, dont_care=[(0.6, 0.5, 0.9, 0.8)], parts={"handle": ["Handle"]})
a.build()
