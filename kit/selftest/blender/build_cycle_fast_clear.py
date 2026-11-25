"""build_cycle_fast_clear.py — POSITIVE fixture for THE ACTION CYCLE CHECKED BY HOW FAR ITS PARTS MOVE (his D-R05, the
rest: "coordinated cycles ... remain sampled too"; the 3D methods audit, stage L). A wheel carrying a lug turns half
round in TWO frames - the frames the check used to look at show the lug at 0 and at 180 degrees, never at the 90
where a pin WOULD stand, were it not held up clear of the lug's path.
Must NOT be flagged: mechanism_cycle.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_cycle_fast_clear", tex=64, size=(1.0, 1.2, 0.4))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Base", (0.9, 0.1, 0.3), (0, 0.05, 0), "body", bevel=0)
a.box("Post", (0.08, 0.4, 0.08), (0, 0.3, -0.12), "body", bevel=0)
a.cylinder("Wheel", 0.25, 0.1, (0, 0.5, 0), "trim", axis="Z", segments=32, group="wheel")
a.box("Lug", (0.12, 0.06, 0.1), (0.31, 0.5, 0), "trim", bevel=0, group="wheel")
a.box("Pin", (0.06, 0.2, 0.06), (0, 1.0, 0), "body", bevel=0, group="pin")
a.joint("Wheel", "wheel", "hinge", axis=(0, 0, 1), pivot=(0, 0.5, 0), max=180)
a.joint("Pin", "pin", "slide", axis=(0, -1, 0), max=0.12)
a.cycle("Snap", [(1, {"Wheel": 0, "Pin": 0}), (3, {"Wheel": 180, "Pin": 0})])
a.build()
