"""build_cage.py — fixture: a.cage() makes a SOFT-HARD part by subdivision: a 60 x 30 mm L-shaped outline (concave)
12 mm thick, soft 1.5 mm, and the same with crisp corners. kit/test/python/test_cage.py reads facts.cage[]. Never
"fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

L_SHAPE = [(0, 0), (60, 0), (60, 12), (20, 12), (20, 30), (0, 30)]
a = rbx.Asset("_selftest_cage", tex=256, size=(0.5, 0.12, 0.05), ground=False, allow_floating=["Soft", "Crisp"])
a.real_scale(280.0)
a.material("black", (0.04, 0.04, 0.045), rough=0.4)
a.cage("Soft", L_SHAPE, 12, "black", soft=1.5, pos=(-0.15, 0, 0))
a.cage("Crisp", L_SHAPE, 12, "black", soft=1.5, crisp_corners=True, pos=(0.15, 0, 0))
a.build()
