"""build_broken_expect.py — NEGATIVE fixture: the build script states something that is not true (the lid is
said to be above the handle, but the handle is on top). Must FAIL with expect:Lid.
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

a = rbx.Asset("_selftest_broken_expect", tex=64, size=(4, 5, 4))
a.material("body", color=(0.6, 0.6, 0.6))
a.material("trim", color=(0.1, 0.1, 0.1))
a.box("Body", (4, 4, 4), (0, 2, 0), "body")
a.box("Lid", (4.2, 0.3, 4.2), (0, 4.1, 0), "trim")
a.box("Handle", (1, 0.6, 0.4), (0, 4.5, 0), "trim")
a.expect("Lid", above="Handle")  # false on purpose
a.expect("Handle", touches="Lid")  # true
a.build()
