"""build_section_boxy.py — NEGATIVE fixture: a grip built as a BOX where its reference wraps round. Must be named:
section_match. Never "fix" this file.
The reference (kit/selftest/refs/_round_grip.measure.json, made by `kit refs measure` from _round_grip.glb): an
elliptical grip, 30 x 50 mm, squareness 2 at every height. This grip is a 30 x 50 mm box (squareness ~12): the
owner's "the grip isn't squarish, it wraps around". Used by `lune run kit selftest`.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

REF = os.path.join(_root, "kit", "selftest", "refs", "_round_grip.measure.json")
a = rbx.Asset("_selftest_wrap_boxy", tex=64, size=(0.30, 1.15, 2.0))
a.real_scale(100.0)  # 1 stud = 100 mm
a.material("steel", color=(0.5, 0.5, 0.52))
a.box("Body", (0.30, 0.35, 2.0), (0, 0, 0), "steel", bevel=0)
a.box("Grip", (0.30, 0.80, 0.50), (0, -0.575, 0.65), "steel", bevel=0)  # at the back (+z): a kit model faces -Z
a.section_match(REF, levels=(0.15, 0.3, 0.45))
a.build()
