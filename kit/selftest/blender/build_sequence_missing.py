"""build_sequence_missing.py — NEGATIVE fixture: a cover that slides off a box, and an insert that lifts out of it — the insert
can only come out once the cover is off (a launcher's housing slides forward, THEN its shell lifts out).
Without after=, the insert lifts THROUGH the closed cover (half way up it is inside it): must be flagged: mechanism.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_sequence_missing", tex=64, size=(1.0, 0.6, 1.0))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Base", (1.0, 0.3, 1.0), (0, 0.15, 0), "body", bevel=0)
a.box("Insert", (0.6, 0.24, 0.6), (0, 0.425, 0), "trim", bevel=0, group="insert")  # y 0.305 .. 0.545 on the base
a.box("Cover", (1.0, 0.05, 1.0), (0, 0.575, 0), "body", bevel=0, group="cover")  # y 0.55 .. 0.6, over the insert
a.joint("Cover", "cover", "slide", axis=(0, 0, 1), max=1.1)  # slides back, clear of the insert
a.joint("Insert", "insert", "slide", axis=(0, 1, 0), max=0.5)
a.build()
