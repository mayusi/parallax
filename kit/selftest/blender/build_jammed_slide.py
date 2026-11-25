"""build_jammed_slide.py — NEGATIVE fixture: a slide that sits half INSIDE its frame at rest (no clearance cut).
Must be flagged: mechanism.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_jam", tex=64, size=(1.2, 0.4, 0.4))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Frame", (1.0, 0.3, 0.3), (0, 0.15, 0), "body", bevel=0)
a.box("Slide", (0.6, 0.2, 0.2), (0.3, 0.2, 0), "trim", bevel=0, group="slide")  # x 0..0.6: half inside the frame
a.joint("Slide", "slide", "slide", axis=(1, 0, 0), max=0.3)
a.build()
