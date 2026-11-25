"""build_sloppy.py — NEGATIVE fixture: passes the hard gates but is sloppy. Must WARN with hidden_parts,
palette, detail and symmetry. Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_sloppy", tex=64, size=(5.25, 4, 4.7), symmetric=True)
a.material("body", color=(0.6, 0.6, 0.6))
a.box("Body", (4, 4, 4), (0, 2, 0), "body")
a.box("Buried", (1, 1, 1), (0, 2, 0), "body")  # fully inside Body: never visible
a.box("Arm", (1.5, 1, 1), (2.5, 3, 0), "body")  # one side only, symmetric=True
a.box("Leg", (1, 1, 1), (1, 0.5, -2.2), "body")
a.build()
