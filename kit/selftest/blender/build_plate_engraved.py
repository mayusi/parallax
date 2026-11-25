"""build_plate_engraved.py — a bronze plate with ENGRAVED scrollwork (pattern="engraved": spiral scrolls, a vine,
leaves, dark tarnish in the grooves). The selftest requires its visible texture to beat its plain twin
(build_plate_plain.py): an engraving the player cannot see is not an engraving. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_plate_engraved", size=(1.2, 0.3, 1.2), symmetric=True, bevel=0)
a.material("bronze", (0.58, 0.40, 0.25), metal=1.0, rough=0.34, pattern="engraved")
a.box("Plate", (1.2, 0.3, 1.2), (0, 0.15, 0), "bronze", bevel=0.01)
a.build()
