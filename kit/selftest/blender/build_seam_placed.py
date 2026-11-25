"""build_seam_placed.py — POSITIVE fixture for SEAMS THE AUTHOR PLACES (a.seams, rbx_seamplace; the 3D methods
audit, S3b): a round handle standing up, its UVs cut by the author - one cut down its BACK (a rule on an edge's two
ends: both at the back, z > 0.49) and its two caps cut off (sharp=60). The build must lay the side as ONE strip
whose only cut is at the back, say so ("placed seams: Handle 3 piece(s)") and pass `seam_placed`. After the build
one line `SEAMS {json}` for kit/test/python/test_seam_placed_build.py: how many places on the map the side's
vertices have down the front (one each) and down the back (two each). With `uncut` after `--` the side is never
cut open (build_seam_placed_uncut.py: the build must FAIL `seam_placed`); with `nowhere` the rule cuts no edge
(build_seam_placed_nowhere.py: the build must STOP and say so). Used by `lune run kit selftest`. Never "fix" this
file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = "uncut" if "uncut" in ARGS else "nowhere" if "nowhere" in ARGS else "placed"

a = rbx.Asset("_selftest_seam_" + HOW, tex=256, size=(1.0, 3.0, 1.0), ground=True)
a.material("wood", color=(0.45, 0.3, 0.18), rough=0.7)
a.cylinder("Handle", 0.5, 3.0, (0, 1.5, 0), "wood", axis="Y", segments=16, bevel=0)
if HOW == "placed":
    a.seams("Handle", cut=lambda p, q: p[2] > 0.49 and q[2] > 0.49, sharp=60)
elif HOW == "uncut":
    a.seams("Handle", sharp=60)                       # the caps come off; nobody cuts the tube open
else:
    a.seams("Handle", cut=lambda p, q: p[2] > 5.0 and q[2] > 5.0)
a.build()

obj = bpy.data.objects[a.name]
back = rbx.BL_FROM_RBX.inverted() @ obj.matrix_world
uv = obj.data.uv_layers.active.data
places = {"front": {}, "back": {}}
for poly in obj.data.polygons:
    if abs((back.to_3x3() @ poly.normal)[1]) > 0.5:
        continue                                      # (a cap)
    for li in poly.loop_indices:
        p = back @ obj.data.vertices[obj.data.loops[li].vertex_index].co
        side = "front" if p[2] < -0.49 else "back" if p[2] > 0.49 else None
        if side:
            places[side].setdefault(round(p[1], 3), set()).add((round(uv[li].uv[0], 4), round(uv[li].uv[1], 4)))
print("SEAMS " + json.dumps({k: sorted(len(v) for v in d.values()) for k, d in places.items()}))
