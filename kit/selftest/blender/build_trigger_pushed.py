"""build_trigger_pushed.py — NEGATIVE fixture: a trigger hung below its pivot on a hinge of +8 degrees about +X - which
swings its blade FORWARD, toward the muzzle (-Z), as the revolver's build 4 did at its shot (the owner, 2026-11-11:
"imagine you actually try to shoot it with that type of trigger, it didn't work out"). Clear of everything, so only the
pull's direction is wrong. Must be flagged: mechanism ("toward the MUZZLE").
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_trigger_pushed", tex=64, size=(0.3, 0.8, 1.2))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Frame", (0.3, 0.2, 1.2), (0, 0.7, 0), "body", bevel=0)                         # y 0.6 .. 0.8
a.box("Trigger", (0.06, 0.4, 0.08), (0, 0.32, 0), "trim", bevel=0, group="trigger")    # y 0.12 .. 0.52, hangs free
a.joint("Trigger", "trigger", "hinge", axis=(1, 0, 0), pivot=(0, 0.55, 0), max=8)      # +8 about +X: the blade goes FORWARD
a.build()
