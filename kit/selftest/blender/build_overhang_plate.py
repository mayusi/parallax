"""build_overhang_plate.py — NEGATIVE fixture: a 1 mm plate twice as long as the face it rests on — half of its
back hangs in the air (a flat plate under a slanted / shorter face). Must be flagged: plate_support.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_overhang", tex=64, size=(1.2, 0.5, 0.6))
a.real_scale(100)
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Host", (0.6, 0.4, 0.6), (0, 0.2, 0), "body", bevel=0)
a.box("Plate", (1.2, 0.01, 0.6), (0, 0.407, 0), "trim", bevel=0)  # 0.2 mm above the host, 0.3 studs off each end
a.build()
