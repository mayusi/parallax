"""build_bad_marking.py — NEGATIVE fixture: a stamped marking runs off the edge of its body — half of the letters
are printed on air. Must be flagged: marking_placement.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_marking", tex=64, size=(0.6, 0.6, 1.0))
a.real_scale(100)
a.material("body", color=(0.55, 0.56, 0.6))
a.material("ink", color=(0.05, 0.05, 0.05))
a.box("Body", (0.6, 0.6, 0.4), (0, 0.3, 0), "body", bevel=0)
a.text("Stamp", "KIT SELFTEST", (0.305, 0.3, 0.3), "ink", size=0.12, facing="+X")  # centred past the body's end
a.build()
