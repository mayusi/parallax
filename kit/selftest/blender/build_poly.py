"""build_poly.py — POSITIVE fixture for BOX MODELLING BY RULE (a.inset / a.push / a.loop / a.round, rbx_poly): a
crate made from ONE sharp box - its lid inset with the panel sunk, two cuts across its length, the middle of its
back pushed out (a boss) and the middle of its front inset with a sunk panel, its edges rounded last - on two feet
(a.mirror) whose outer sides are inset: the mirrored foot is inset on ITS outer side.
Its summary must name the steps ("modelled: ..."). Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_poly", size=(2.1, 1.2, 1.2), ground=True)
a.material("wood", color=(0.42, 0.29, 0.17), rough=0.7)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.box("Crate", (2.0, 1.0, 1.0), (0, 0.65, 0), "wood", bevel=0)
a.inset("Crate", "+Y", 0.12, depth=-0.05)
a.loop("Crate", "X", at=[0.35, 0.65])
a.push("Crate", lambda c, n: n[2] > 0.9 and abs(c[0]) < 0.25 and c[2] > 0.45, 0.08)   # (c[2]: not the lid's walls)
a.inset("Crate", lambda c, n: n[2] < -0.9 and abs(c[0]) < 0.25 and c[2] < -0.45, 0.08, depth=-0.06)
a.round("Crate", 0.02)
with a.mirror("X"):
    a.box("Foot", (0.3, 0.2, 0.9), (0.7, 0.08, 0), "iron", bevel=0)
a.inset("Foot", "+X", 0.03, depth=-0.03)
a.round("Foot", 0.012)
a.build()
