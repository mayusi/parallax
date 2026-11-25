"""build_cad_open.py — NEGATIVE fixture: a.cad given a SURFACE, not a solid — a filleted rectangle Face (a sketch
never extruded), so the part has no volume and its mesh is all open edges. Must be named: cad_solid. Used by
`lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_cad_open", tex=64, size=(0.4, 0.3, 0.05), ground=False)
a.real_scale(280)
a.material("steel", (0.56, 0.57, 0.58), metal=1.0, rough=0.35)
a.cad("Plate", """
    with BuildSketch() as sk:
        RectangleRounded(110, 80, 8)
    part = sk.sketch                     # (the mistake: no extrude — a Face, not a Part)
    """, "steel")
a.box("Base", (0.4, 0.05, 0.3), (0, -0.05, 0), "steel", bevel=0)
a.build()
