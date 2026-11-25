"""build_plank_recess_grooves.py — NOISE, carved inside a carving: one shallow dark recess in a wooden block (alone it
is one region, a twentieth of the surface — under every line) and twenty grooves cut into the recess's floor. The
floor is dark, so judging a cut by the material it borders saw no wood at all; the selftest requires the twenty
grooves counted (carved_grooves): the walls a cut carves into wood stay wood to every later cut. Never "fix" this
file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_plank_recess_grooves", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
a.box("Body", (2.0, 1.5, 2.0), (0, 0.75, 0), "wood", bevel=0.03)
a.cut("Body", a.box("Recess", (1.2, 0.8, 0.12), (0, 0.75, -1.0), "seam", bevel=0))  # 0.06 deep, its floor at z -0.94
for i in range(20):  # 0.03 deep into the recess's floor, clear of its walls
    a.cut("Body", a.box(f"Groove{i}", (0.02, 0.7, 0.06), (-0.57 + i * 0.06, 0.75, -0.94), "seam", bevel=0))
a.build()
