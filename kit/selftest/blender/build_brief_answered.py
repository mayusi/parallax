"""build_brief_answered.py — POSITIVE fixture: the same model WITH its brief answered
(_selftest_brief_answered.brief.md beside this script). Must NOT be named: brief.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_brief_answered", tex=64, size=(1.0, 0.5, 1.0))
a.material("body", color=(0.55, 0.56, 0.6))
a.box("Body", (1.0, 0.5, 1.0), (0, 0.25, 0), "body", bevel=0)
a.build()
