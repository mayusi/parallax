"""build_tiny_cuts.py — DETAIL CUT INSTEAD OF BAKED: pin-hole dimples a few hundredths of a stud wide cut into a
2-stud box — triangles spent on what the normal map shows as well. The selftest requires the tiny_cuts warning (a
floater would carry them for free). Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_tiny_cuts", size=(2.0, 1.0, 2.0), symmetric=True)
a.material("paint", (0.45, 0.47, 0.5), rough=0.6)
a.material("dark", (0.05, 0.05, 0.05), rough=0.8)
a.box("Body", (2.0, 1.0, 2.0), (0, 0.5, 0), "paint")
for i, x in enumerate((-0.4, 0.0, 0.4)):  # three pin-hole dimples in the top face, 0.03 deep
    a.cut("Body", a.cylinder(f"Pin{i}", 0.02, 0.06, (x, 1.0, 0.0), "dark", segments=8))
a.build()
