"""build_part_match_ok.py — POSITIVE fixture for the per-part check: a 4-stud body with a handle under its rear, measured
against a trace (written at run time in build/selftest/) whose outline is the pair and whose PART "handle" is the
handle's own outline, exactly where the model has it. Must NOT be named: part_match_side. The negative twin
(build_part_match_off.py) builds the same body with the handle misplaced and short. Used by `lune run kit selftest`.
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
# design units: u = (2 - z) / 4 (the back z = +2 -> 0, the front z = -2 -> 1), v = (y + 1.7) / 4; height 2.2 / 4
TRACE = {"name": "_part_match", "front": "right", "height_ratio": 0.55, "holes": [],
         "outline": [[0, 0.3], [0.125, 0.3], [0.125, 0.0], [0.275, 0.0], [0.275, 0.3], [1, 0.3], [1, 0.55], [0, 0.55]],
         "parts": {"handle": [[0.125, 0.0], [0.275, 0.0], [0.275, 0.3], [0.125, 0.3]]}}
trace = os.path.join(out, "_part_match.trace.json")
with open(trace, "w", encoding="utf-8") as fh:
    json.dump(TRACE, fh)

HANDLE = {"pos": (0, -1.1, 1.2), "size": (0.4, 1.2, 0.6)}  # (the twin overrides it)
HANDLE.update(json.loads(os.environ.get("KIT_PART_MATCH_HANDLE", "{}")))
a = rbx.Asset(os.environ.get("KIT_PART_MATCH_NAME", "_selftest_part_match_ok"), tex=64, size=(0.5, 2.2, 4.0),
              ground=False)
a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
a.material("grip", (0.1, 0.1, 0.1), rough=0.7)
a.box("Body", (0.5, 1.0, 4.0), (0, 0, 0), "steel", bevel=0)
a.box("Handle", tuple(HANDLE["size"]), tuple(HANDLE["pos"]), "grip", bevel=0)
a.trace_match(trace, bar=0.5, parts={"handle": ["Handle"]})
if os.environ.get("KIT_PART_MATCH_DEPTH"):  # (the depth16 twin: an earlier render left this output behind)
    a.scene.render.image_settings.file_format = "PNG"
    a.scene.render.image_settings.color_depth = os.environ["KIT_PART_MATCH_DEPTH"]
a.build()
