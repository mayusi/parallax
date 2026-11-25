"""build_wrong_size.py — NEGATIVE fixture: the design says 2x2x2, the model is 2x6x2. Must FAIL with
size_vs_target. Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_wrong_size", tex=64, size=(2, 2, 2))
a.material("body", color=(0.6, 0.6, 0.6))
a.material("trim", color=(0.1, 0.1, 0.1))
a.box("Body", (2, 6, 2), (0, 3, 0), "body")
a.build()
