"""build_inside_out.py — NEGATIVE fixture: a part whose faces point inward (Roblox would show a hole).
Must FAIL with inside_out. Also builds a nested X+Z mirror, whose copies must NOT be flagged.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_inside_out", tex=64, size=(4, 4, 4))
a.material("body", color=(0.6, 0.6, 0.6))
a.material("trim", color=(0.1, 0.1, 0.1))
a.box("Body", (4, 4, 4), (0, 2, 0), "body")
with a.mirror("X"):
    with a.mirror("Z"):
        a.box("Corner", (0.5, 0.5, 0.5), (2, 3.5, 2), "trim")  # 4 copies, all must face outward
inverted = a.box("Lid", (3, 0.2, 3), (0, 4.1, 0), "trim")
inverted.data.flip_normals()
a.build()
