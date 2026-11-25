"""build_fastener_seat_ok.py — POSITIVE fixture: the same M4 x 16 screw as build_fastener_seat_buried.py, in a hole
cut through its block at the ISO 273 clearance size (clearance('M4') = 4.5 mm). Must NOT be named: fastener_seat.
Never "fix" this file. Used by `lune run kit selftest` (needs the cad env).
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_seated_ok", tex=64, size=(0.4, 0.3, 0.4))
a.real_scale(100.0)
a.material("steel", color=(0.5, 0.5, 0.52))
# the block in CAD with its hole: a 4.5 mm bore straight through it, top to bottom
a.cad("Block", "part = Box(40, 20, 40) - Rot(90, 0, 0) * Cylinder(clearance('M4') / 2, 40)\n", "steel")
a.cad("Screw", "part = Rot(-90, 0, 0) * screw('M4-0.7', 16)\n", "steel", pos=(0, 0.10, 0))
a.build()
