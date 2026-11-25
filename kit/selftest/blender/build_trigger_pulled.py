"""build_trigger_pulled.py — POSITIVE fixture: the same frame and trigger as build_trigger_pushed.py, its hinge about
-X, so the blade's tip moves BACK toward the grip (+Z) when pulled - a trigger as it works. Must NOT be flagged by
the pull's direction ("toward the MUZZLE").
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_trigger_pulled", tex=64, size=(0.3, 0.8, 1.2))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Frame", (0.3, 0.2, 1.2), (0, 0.7, 0), "body", bevel=0)
a.box("Trigger", (0.06, 0.4, 0.08), (0, 0.32, 0), "trim", bevel=0, group="trigger")
a.joint("Trigger", "trigger", "hinge", axis=(-1, 0, 0), pivot=(0, 0.55, 0), max=8)     # pulled: the blade goes BACK
a.build()
