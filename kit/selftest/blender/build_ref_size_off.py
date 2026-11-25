"""build_ref_size_off.py — NEGATIVE fixture: its bracket is HALF the height of the reference's (50 mm, not 100: the
judges' "brackets short"). Must FAIL naming ref_sizes. Never "fix" this file.
Spec parts linked to the traced parts of a reference ("ref") are measured against them in mm on every build: the
reference is kit/selftest/refs/ref_sizes.views.json (kit refs views' format). Used by `lune run kit selftest`.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_ref_size_off", tex=64, size=(1.0, 3.6, 10.0))
a.real_scale(100.0)  # 1 stud = 100 mm: the body is 10 studs long
a.spec({"views": "kit/selftest/refs/ref_sizes.views.json", "parts": [
    {"name": "Body", "what": "the body", "ref": "body"},
    {"name": "Bracket", "what": "the bracket on its top", "attaches": ["Body"], "ref": "bracket"},
    {"name": "Knob", "what": "the knob under its front", "attaches": ["Body"], "ref": "knob"}]})
a.material("body", color=(0.5, 0.5, 0.52))
a.material("trim", color=(0.15, 0.15, 0.16))
a.box("Body", (1.0, 2.0, 10.0), (0, 1.0, 0), "body", bevel=0)
a.box("Bracket", (0.6, 0.5, 0.4), (0, 2.0 + 0.5 / 2, -1.2), "trim", bevel=0)  # 600-640 mm from the back (z = 5)
a.box("Knob", (0.6, 0.6, 1.2), (0, -0.3, -3.8), "trim", bevel=0)
a.build()
