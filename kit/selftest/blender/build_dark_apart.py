"""build_dark_apart.py — POSITIVE twin of build_dark_alike.py: the same block, its polymer body at the owner-rated
Glock's frame value (0.095: 86 sRGB) under the same nitride top (51) — two materials a clear step apart. Must NOT be
named: dark_finishes. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_dark_apart", tex=512, size=(3, 1.6, 0.8))
a.material("body", **rbx.finish("polymer", color=(0.095, 0.094, 0.092), rough=0.72), wear=0.2)
a.material("top", **rbx.finish("nitride"), wear=0.2)
a.box("Body", (3, 1.0, 0.8), (0, 0.5, 0), "body", bevel=0.03)
a.box("Top", (3, 0.6, 0.7), (0, 1.3, 0), "top", bevel=0.03)
a.build()
