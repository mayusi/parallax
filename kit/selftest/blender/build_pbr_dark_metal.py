"""build_pbr_dark_metal.py — NEGATIVE fixture: the "gunmetal" mistake. A frame that is a METAL at ~60 sRGB (no bare
metal is darker than ~150: a dark gun finish is a coating, metal 0) and a slide at metal 0.5 (half a metal). Must be
named: pbr_values (a warning on a prop, an error at hero / aaa). Used by `lune run kit selftest`. Never "fix" this
file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_pbr_dark_metal", tex=64, size=(0.4, 0.5, 1.6), ground=False)
a.material("frame", (0.045, 0.046, 0.05), metal=1.0, rough=0.3)  # a metal at 60 sRGB
a.material("slide", (0.2, 0.2, 0.21), metal=0.5, rough=0.4)  # half a metal
a.box("Frame", (0.4, 0.3, 1.6), (0, 0.15, 0), "frame", bevel=0)
a.box("Slide", (0.36, 0.2, 1.4), (0, 0.4, 0), "slide", bevel=0)
a.build()
