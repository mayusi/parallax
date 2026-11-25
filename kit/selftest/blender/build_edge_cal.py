"""build_edge_cal.py — fixture: six CAD slabs (40 x 24 mm, 10 mm thick) with every edge rounded 0 / 0.5 / 1 / 2 / 3 /
4 mm (a.cad round_mm), side by side, 60 mm apart. kit/tools/edge_calibrate.py renders each from the front with the
kit's ortho studio light and fits how wide an edge's ramp is to its radius (kit/refs/edges.py CAL). Never "fix"
this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

SLAB = """
part = Box(40, 24, 10)
"""
ROUNDS = [0.0, 0.5, 1.0, 2.0, 3.0, 4.0]
names = [f"Slab{i}" for i in range(len(ROUNDS))]
a = rbx.Asset("_selftest_edge_cal", tex=256, size=(1.3, 0.1, 0.05), ground=False, allow_floating=names)
a.real_scale(280.0)
a.material("grey", (0.35, 0.35, 0.36), rough=0.4)
for i, r in enumerate(ROUNDS):
    a.cad(names[i], SLAB, "grey", pos=((i - 2.5) * 60.0 / 280.0, 0, 0), round_mm=r or None)
a.build()
