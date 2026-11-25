"""build_sharp_edges_off.py — NEGATIVE fixture: a hero part whose every hard edge is left SHARP (a box, bevel=0).
Must be named: sharp_edges. Never "fix" this file.
The owner, 2026-10-07: "you can never make parts bevelled" — a real part's edges are rounded or chamfered; a sharp
CG edge reads fake. Used by `lune run kit selftest`.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_bevel_off", tex=64, size=(0.6, 0.4, 2.0), quality="hero", stage_gate=False)
a.real_scale(100.0)  # 1 stud = 100 mm
a.material("steel", color=(0.5, 0.5, 0.52))
a.box("Slide", (0.30, 0.35, 2.0), (0, 0, 0), "steel", bevel=0)
a.build()
