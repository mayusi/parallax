"""build_cad_notch.py — fixture: a 60 x 30 mm CAD slab, 10 mm thick, with ONE 1 mm notch cut into its top edge, rounded
2 mm (a.cad round_mm). Blender's clamp_overlap once shrank the whole round to its tightest spot (the notch): 0.45 mm
everywhere. kit/test/python/test_cad_notch.py reads facts.cad[].round_built. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

SLAB = """
part = Box(60, 30, 10)
part = part - Pos(0, 15, 0) * Box(1, 2, 12)
"""
a = rbx.Asset("_selftest_cad_notch", tex=256, size=(0.25, 0.12, 0.05), ground=False, allow_floating=["Notched"])
a.real_scale(280.0)
a.material("grey", (0.35, 0.35, 0.36), rough=0.4)
a.cad("Notched", SLAB, "grey", round_mm=2.0)
a.build()
