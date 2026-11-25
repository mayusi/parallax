"""build_sliver.py — NEGATIVE fixture: a pocket cut from below stops 0.5 mm under the top face, leaving a paper-thin
skin on a solid 60 mm block (two cuts / outlines that nearly coincide). Must be flagged: slivers.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_sliver", tex=64, size=(1, 0.6, 0.6))
a.real_scale(100)  # 1 stud = 100 mm: the sliver limit (1.5 mm) is 0.015 studs
a.material("body", color=(0.55, 0.56, 0.6))
a.material("dark", color=(0.1, 0.1, 0.1))
a.box("Body", (1.0, 0.6, 0.6), (0, 0.3, 0), "body", bevel=0)
a.cut("Body", a.box("Pocket", (0.6, 0.695, 0.4), (0, 0.2475, 0), "dark", bevel=0))  # top at 0.595: a 0.5 mm skin
a.build()
