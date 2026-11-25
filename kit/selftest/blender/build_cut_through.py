"""build_cut_through.py — a CUT THROUGH a part: a saw slot deeper and wider than the board splits it in two (the score-
chasing chest had grooves cut deeper than its boards). The selftest requires the cut_through warning. Never "fix" this
file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_cut_through", size=(2.0, 0.1, 0.4), bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
a.box("Board", (2.0, 0.1, 0.4), (0, 0.05, 0), "wood", bevel=0.01)
a.cut("Board", a.box("SawSlot", (0.06, 0.3, 0.6), (0, 0.05, 0), "seam"))  # deeper AND wider than the board
a.build()
