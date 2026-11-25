"""build_zone_split.py — POSITIVE fixture: a sphere whose grip-like zone is cut along planes that pass a hair (1e-5
studs) beside its poles, where a fan of thin triangles meets (a CAD mesh is full of them; planes placed from measured
photo numbers graze them). Each such plane cuts a speck off the tip of every triangle in the fan: zero-area slivers
(60 here before a.zone collapsed them as a clamped bevel's are; the Glock 17's grip split left 35 and failed
degenerate_faces, 2026-10-08). Must NOT be flagged: degenerate_faces, manifold.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_zone_split", tex=64, size=(0.6, 0.6, 0.6), ground=False)
a.material("polymer", **rbx.finish("polymer"))
a.material("grip", **rbx.finish("polymer"), pattern="pyramids", pattern_mm=2.0)
a.sphere("Knob", 0.3, (0, 0, 0), "polymer", segments=32, rings=16)

# the knob's poles: fans of thin triangles meeting in one vertex (a CAD mesh is full of them). Planes a hair (1e-5
# studs) beside a pole cut a speck off the tip of every triangle in the fan: zero-area slivers
obj = next(o for o, _g in a.parts if o.name == "Knob")
to_rbx = rbx.BL_FROM_RBX.inverted()
vs = [to_rbx @ (obj.matrix_world @ v.co) for v in obj.data.vertices]
top = max(vs, key=lambda v: v.y)
bot = min(vs, key=lambda v: v.y)
split = [((top.x + 1e-5, 0.0, 0.0), (1.0, 0.0, 0.0)),            # down past the top pole
         ((0.0, 0.0, top.z - 1e-5), (0.0, 0.0, 1.0)),            # ... and across it
         ((bot.x - 1e-5, 0.0, 0.0), (1.0, 0.2, 0.0))]            # slanted, past the bottom pole
n = a.zone("Knob", "grip", lambda c, nrm: c[0] > top.x and c[2] < top.z, split=split)
print(f"zone faces: {n}")
a.build()
