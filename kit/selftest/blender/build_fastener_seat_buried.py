"""build_fastener_seat_buried.py — NEGATIVE fixture: a real M4 x 16 socket head cap screw (kit/tools/cad_parts.py,
ISO 4762) sunk into a SOLID block — no hole cut for it. Must be named: fastener_seat. Never "fix" this file.
Down to the screws (the owner, 2026-10-07): a screw sits in a hole of its host; a take-apart would pull this one out
of solid metal. Used by `lune run kit selftest` (needs the cad env, like build_cad_ok.py).
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_seated_buried", tex=64, size=(0.4, 0.3, 0.4))
a.real_scale(100.0)  # 1 stud = 100 mm
a.material("steel", color=(0.5, 0.5, 0.52))
a.box("Block", (0.40, 0.20, 0.40), (0, 0, 0), "steel", bevel=0)  # 40 x 20 x 40 mm, solid
# the screw's head on the block's top face (y = 10 mm), its 16 mm shank straight down INTO the solid block
a.cad("Screw", "part = Rot(-90, 0, 0) * screw('M4-0.7', 16)\n", "steel", pos=(0, 0.10, 0))
a.build()
