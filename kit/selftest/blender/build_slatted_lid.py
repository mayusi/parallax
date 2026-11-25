"""build_slatted_lid.py — SEE-THROUGH: a lid of slats with gaps and nothing behind them (the agent chest's lid). The
selftest requires the see_through flag. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("_selftest_slatted_lid", size=(2.4, 1.2, 1.6), symmetric=True, bevel=0)
a.material("wood", (0.45, 0.25, 0.12), rough=0.8, pattern="wood")
a.box("Base", (2.4, 0.6, 1.6), (0, 0.3, 0), "wood", bevel=0.02)
with a.mirror("X"):
    a.box("End", (0.1, 0.6, 1.6), (1.15, 0.9, 0), "wood", bevel=0.01)
for i in range(6):
    a.box(f"Slat{i}", (2.2, 0.06, 0.18), (0, 1.17, -0.65 + i * 0.26), "wood", bevel=0.01)
for i in range(4):
    with a.mirror("Z"):
        a.box(f"Side{i}", (2.2, 0.08, 0.06), (0, 0.66 + i * 0.14, -0.77), "wood", bevel=0.01)
a.build()
