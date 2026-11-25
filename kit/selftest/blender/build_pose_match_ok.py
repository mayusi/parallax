"""build_pose_match_ok.py — POSITIVE fixture for trace_match(pose=): the picture shows a lid OPEN (standing up at the
body's front), the model rests with it shut (lying on the body). Measured with pose={"Lid": "min"} the lid is moved
where the picture has it and the outlines match. Must NOT be named: reference_side. Its negative twin
(build_pose_match_off.py) measures the same model without the pose. Used by `lune run kit selftest`.
Never "fix" this file."""

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
# design units: u = (2 - z) / 4, v = (y + 0.5) / 4. The body: z -2 .. 2, y -0.5 .. 0.5 (v 0 .. 0.25). The lid OPEN:
# z -2 .. -1.8 (u 0.95 .. 1), y 0.5 .. 2.1 (v 0.25 .. 0.65)
TRACE = {"name": "_pose_match", "front": "right", "height_ratio": 0.65, "holes": [],
         "outline": [[0, 0], [1, 0], [1, 0.65], [0.95, 0.65], [0.95, 0.25], [0, 0.25]]}
trace = os.path.join(out, "_pose_match.trace.json")
with open(trace, "w", encoding="utf-8") as fh:
    json.dump(TRACE, fh)

a = rbx.Asset(os.environ.get("KIT_POSE_MATCH_NAME", "_selftest_pose_match_ok"), tex=64, size=(0.5, 1.2, 4.0),
              ground=False)
a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
a.material("lid", (0.2, 0.3, 0.6), rough=0.5)
a.box("Body", (0.5, 1.0, 4.0), (0, 0, 0), "steel", bevel=0)
a.box("Lid", (0.5, 0.2, 1.6), (0, 0.6, -1.0), "lid", group="lid", bevel=0)  # shut: lying on the body's front half
# hinged at its front end on the body's top (z -1.8, y 0.5): -90 degrees about +X swings it up to stand at the front
a.joint("Lid", "lid", "hinge", axis=(1, 0, 0), pivot=(0, 0.5, -1.8), min=-90, max=0)
pose = None if os.environ.get("KIT_POSE_MATCH_NONE") else {"Lid": "min"}
a.trace_match(trace, bar=0.95, pose=pose)
a.build()
