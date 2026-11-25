"""build_visible_internal.py — NEGATIVE fixture: an INTERNAL spring that pokes out through the top of its
housing — you can see it from outside. Must be flagged: part_visibility.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_internal", tex=64, size=(0.6, 0.8, 0.6))
a.real_scale(100)
a.material("body", color=(0.55, 0.56, 0.6))
a.material("spring", color=(0.7, 0.7, 0.72), metal=1.0, rough=0.3)
a.box("Housing", (0.6, 0.6, 0.6), (0, 0.3, 0), "body", bevel=0)
with a.internal():
    a.cylinder("Spring", 0.08, 0.5, (0, 0.55, 0), "spring", axis="Y", bevel=0)  # 0.2 studs above the housing
a.build()
