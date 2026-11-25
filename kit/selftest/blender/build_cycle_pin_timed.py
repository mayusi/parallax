"""build_cycle_pin_timed.py — POSITIVE fixture: the same wheel, lug and pin as build_cycle_pin_in_path.py, but the
pin comes down only AFTER the wheel has turned the lug past it - a timed mechanism (a revolver's stop rising into the
next notch once the cylinder has turned). Must NOT be flagged: mechanism_cycle.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_cycle_timed", tex=64, size=(1.0, 1.2, 0.4))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Base", (0.9, 0.1, 0.3), (0, 0.05, 0), "body", bevel=0)
a.box("Post", (0.08, 0.4, 0.08), (0, 0.3, -0.12), "body", bevel=0)
a.cylinder("Wheel", 0.25, 0.1, (0, 0.5, 0), "trim", axis="Z", segments=32, group="wheel")
a.box("Lug", (0.12, 0.06, 0.1), (0.31, 0.5, 0), "trim", bevel=0, group="wheel")
a.box("Pin", (0.06, 0.2, 0.06), (0, 1.0, 0), "body", bevel=0, group="pin")
a.joint("Wheel", "wheel", "hinge", axis=(0, 0, 1), pivot=(0, 0.5, 0), max=180)
a.joint("Pin", "pin", "slide", axis=(0, -1, 0), max=0.12)
# timed: the wheel turns the lug past 90 degrees first, then the pin comes down behind it (the pin HELD up until
# frame 20: each joint eases between its own keys, so a pin keyed only at 1 and 26 would sink through the turn)
a.cycle("Timed", [(1, {"Pin": 0, "Wheel": 0}), (20, {"Wheel": 180, "Pin": 0}), (26, {"Pin": "max"})])
a.build()
