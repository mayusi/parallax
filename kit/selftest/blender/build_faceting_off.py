"""build_faceting_off.py — NEGATIVE fixture: a hero barrel, 40 mm across, made of only 12 sides — its facets sit
0.68 mm off the true circle (a polygon where the real part is round). Must be named: faceting. Never "fix" this
file. Used by `lune run kit selftest`.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_polygon_barrel", tex=64, size=(0.4, 0.4, 1.0), quality="hero", stage_gate=False)
a.real_scale(100.0)  # 1 stud = 100 mm
a.material("steel", color=(0.5, 0.5, 0.52))
a.cylinder("Barrel", 0.20, 1.0, (0, 0, 0), "steel", axis="Z", segments=12)
a.build()
