"""build_floating.py — NEGATIVE fixture: a part hangs in the air (touches nothing). Must FAIL with
floating_parts. Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_floating", tex=64, size=(4, 6, 4))
a.material("body", color=(0.6, 0.6, 0.6))
a.material("trim", color=(0.1, 0.1, 0.1))
a.box("Body", (4, 4, 4), (0, 2, 0), "body")
a.box("Antenna", (0.4, 1, 0.4), (0, 5.5, 0), "trim")  # 1 stud gap above the body
a.build()
