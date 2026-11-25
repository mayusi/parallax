"""build_dark_alike.py — NEGATIVE fixture: a pistol-like block whose two big dark materials sit 7 sRGB apart (a
polymer body at 58 sRGB under a nitride top at 51): fresh judges read the Glock's frame and slide 10 apart (57 / 47)
as "the same blue-navy" — one mass (2026-10-10). Must be named: dark_finishes (a warning). Its A/B twin:
build_dark_apart.py. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_dark_alike", tex=512, size=(3, 1.6, 0.8))
a.material("body", **rbx.finish("polymer", color=(0.042, 0.042, 0.042), rough=0.7), wear=0.2)
a.material("top", **rbx.finish("nitride"), wear=0.2)
a.box("Body", (3, 1.0, 0.8), (0, 0.5, 0), "body", bevel=0.03)
a.box("Top", (3, 0.6, 0.7), (0, 1.3, 0), "top", bevel=0.03)
a.build()
