"""build_loose_pin.py — NEGATIVE fixture: a hinge pin crosses 100 mm of open air between two posts (it should pass
THROUGH material: holes in walls / bosses). Must be flagged: fastener_support.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_loose_pin", tex=64, size=(1.2, 0.6, 0.4))
a.real_scale(100)
a.material("body", color=(0.55, 0.56, 0.6))
a.material("steel", color=(0.7, 0.7, 0.72), metal=1.0, rough=0.3)
a.box("Base", (1.2, 0.1, 0.4), (0, 0.05, 0), "body", bevel=0)
a.box("PostL", (0.1, 0.5, 0.2), (-0.55, 0.35, 0), "body", bevel=0)
a.box("PostR", (0.1, 0.5, 0.2), (0.55, 0.35, 0), "body", bevel=0)
a.cylinder("HingePin", 0.02, 1.2, (0, 0.45, 0), "steel", axis="X", bevel=0)  # 1.0 of its 1.2 studs in the air
a.build()
