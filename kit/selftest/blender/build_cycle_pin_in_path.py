"""build_cycle_pin_in_path.py — NEGATIVE fixture: a wheel with a lug turns half a turn while a pin has already been
let down into the lug's path. Each joint ALONE is clear (the wheel turning with the pin up; the pin coming down with
the lug elsewhere), so the per-joint `mechanism` gate passes - only the action cycle, with both joints posed together
frame by frame, finds the lug driving into the pin (the revolver's case: a cylinder turned while its stop is still
up in the notch). Must be flagged: mechanism_cycle.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_cycle_jam", tex=64, size=(1.0, 1.2, 0.4))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Base", (0.9, 0.1, 0.3), (0, 0.05, 0), "body", bevel=0)
a.box("Post", (0.08, 0.4, 0.08), (0, 0.3, -0.12), "body", bevel=0)
a.cylinder("Wheel", 0.25, 0.1, (0, 0.5, 0), "trim", axis="Z", segments=32, group="wheel")
a.box("Lug", (0.12, 0.06, 0.1), (0.31, 0.5, 0), "trim", bevel=0, group="wheel")       # sweeps radius 0.25 .. 0.37
a.box("Pin", (0.06, 0.2, 0.06), (0, 1.0, 0), "body", bevel=0, group="pin")           # y 0.90 .. 1.10 at rest
a.joint("Wheel", "wheel", "hinge", axis=(0, 0, 1), pivot=(0, 0.5, 0), max=180)
a.joint("Pin", "pin", "slide", axis=(0, -1, 0), max=0.12)                            # down to y 0.78 .. 0.98
# the fault: the pin comes down FIRST, then the wheel turns - the lug passes 90 degrees under the pin mid-turn
a.cycle("Jam", [(1, {"Pin": 0, "Wheel": 0}), (6, {"Pin": "max"}), (20, {"Wheel": 180})])
a.build()
