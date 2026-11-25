"""build_lock_made.py — GOOD fixture for THE METHODS LOCK at build time (rbx.Asset's `methods` check): the model
of build_lock_typed.py made by the methods its brief names (_selftest_lock_made.brief.md, beside this file) - ONE
bolt inside a.repeat(at=its five places), ONE post inside a.repeat in a row of four. Built with
KIT_METHODS_LOCK=1 (kit/selftest/methods/run.py built) its `methods` check must PASS. Used by `lune run kit
selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

PLACES = [(0, 0.3, 0), (0.7, 0.3, 0.2), (1.1, 0.3, -0.6), (-0.9, 0.3, 0.4), (-0.3, 0.3, -0.8)]

a = rbx.Asset("_selftest_lock_made", size=(3.0, 1.2, 3.0), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.box("Plate", (3.0, 0.2, 3.0), (0, 0.1, 0), "iron", bevel=0.02)
with a.repeat(at=PLACES):
    a.cylinder("Bolt", 0.05, 0.2, PLACES[0], "iron", axis="Y", segments=8)
with a.repeat(4, step=(0.8, 0, 0)):
    a.box("Post", (0.1, 0.8, 0.1), (-1.2, 0.6, 1.3), "iron", bevel=0)
a.build()
