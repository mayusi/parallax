"""check_low_round_chains.py — fixture: a.cad on the high-and-low route (Asset(low=...)): the car rim's spoke
(fillet_mm=3) and its LOW's mid-poly rounds. Bevelled in passes of different widths, its arm (3 mm) and flare (2.25,
1.65 mm) edges - one chain - left a 7-cornered face along the whole arm, triangulated into slivers and a 43-75 degree
crease: the bright slit where the spoke meets the lip (rework 6ebz). Prints LOWROUND {json}: the longest low edge
still sharper than 35 degrees (mm), the rounds' passes and segments. Run by kit/test/python/test_low_round_chains.py.
Never "fix" this file."""

import json
import math
import os
import sys

import bmesh

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

SPOKE = '''
with BuildPart() as part:
    with BuildSketch(Plane.XY):
        Polygon((-15, 58), (15, 58), (26, 192), (40, 226), (-40, 226), (-26, 192), align=None)
    extrude(amount=24)
part = part.part.rotate(Axis.X, -14).translate((0, 0, -49.5))
part = part & Cylinder(214, 400)
'''
a = rbx.Asset("_selftest_low_round", tex=256, size=(1.67, 1.67, 0.78), edge_wear=0.0, ao=1.0, edge_radius=0.0,
              low=15000)
a.material("paint", color=(0.66, 0.67, 0.69), metal=1, rough=0.28)
low = a.cad("Spoke", SPOKE, "paint", pos=(0, 233.5 / 280.0, 0), group="face", tol=0.4, angle=18.0, fillet_mm=3)
bm = bmesh.new()
bm.from_mesh(low.data)
mm = 280.0
hard = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35)]
rec = next(c for c in a.design["cad"] if c["part"] == "Spoke")
print("LOWROUND " + json.dumps({"part": low.name, "longest_hard_mm": round(max((e.calc_length() * mm for e in hard),
                                                                            default=0.0), 2),
                                "hard_edges": len(hard), "low_rounds": rec.get("low_rounds"),
                                "segments": rec.get("low_round_segments")}))
bm.free()
