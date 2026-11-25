"""build_ref_doubtful.py — NEGATIVE fixture: every linked part at the reference's size and place, but the bracket's
reference is a mask kit trace judged DOUBTFUL (its box prompt's mask filled the box). Must be named:
ref_sizes_doubtful (a warning: what a doubtful mask measures may be the mask's mistake). Never "fix" this file.
The reference is kit/selftest/refs/ref_doubtful.views.json (kit refs views' format, with kit trace's part_quality
carried into it). Used by `lune run kit selftest`.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_ref_doubtful", tex=64, size=(1.0, 3.6, 10.0))
a.real_scale(100.0)  # 1 stud = 100 mm: the body is 10 studs long
a.spec({"views": "kit/selftest/refs/ref_doubtful.views.json", "parts": [
    {"name": "Body", "what": "the body", "ref": "body"},
    {"name": "Bracket", "what": "the bracket on its top", "attaches": ["Body"], "ref": "bracket"},
    {"name": "Knob", "what": "the knob under its front", "attaches": ["Body"], "ref": "knob"}]})
a.material("body", color=(0.5, 0.5, 0.52))
a.material("trim", color=(0.15, 0.15, 0.16))
a.box("Body", (1.0, 2.0, 10.0), (0, 1.0, 0), "body", bevel=0)
a.box("Bracket", (0.6, 1.0, 0.4), (0, 2.0 + 1.0 / 2, -1.2), "trim", bevel=0)  # 600-640 mm from the back (z = 5)
a.box("Knob", (0.6, 0.6, 1.2), (0, -0.3, -3.8), "trim", bevel=0)
a.build()
