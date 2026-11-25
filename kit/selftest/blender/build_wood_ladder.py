"""build_wood_ladder.py — a CORRECT wooden model with real openings: a ladder (two rails, five rungs) you can see
through between the rungs, as every ladder is. The selftest requires the see-through check to spare it: a real
opening is wide, a defect is a slit (light between slats that should meet). Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_wood_ladder", size=(0.9, 2.4, 0.12), symmetric=True, bevel=0)
a.material("wood", (0.52, 0.34, 0.18), rough=0.85, wear=0.3, grime=0.2, pattern="wood")
with a.mirror("X"):
    a.box("Rail", (0.1, 2.4, 0.12), (0.4, 1.2, 0), "wood", bevel=0.015)
for i in range(5):
    a.box(f"Rung{i}", (0.72, 0.07, 0.07), (0, 0.35 + i * 0.45, 0), "wood", bevel=0.01)
a.build()
