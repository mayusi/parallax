"""build_lock_typed.py — BAD fixture for THE METHODS LOCK at build time (rbx.Asset's `methods` check). Its brief
(_selftest_lock_typed.brief.md, beside this file) plans five bolts by a.repeat at their places and a fence by
a.repeat in a row; this script types the five bolts and the four posts one by one, and makes a token repeat of
two unrelated nubs. Built with KIT_METHODS_LOCK=1 (kit/selftest/methods/run.py build) the build must FAIL its
`methods` check, naming the bolts' count, the parts typed alike. Used by `lune run kit selftest`. Never "fix"
this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

PLACES = [(0, 0.3, 0), (0.7, 0.3, 0.2), (1.1, 0.3, -0.6), (-0.9, 0.3, 0.4), (-0.3, 0.3, -0.8)]

a = rbx.Asset("_selftest_lock_typed", size=(3.0, 1.2, 3.0), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("brass", color=(0.7, 0.55, 0.25), metal=1.0, rough=0.4)
a.box("Plate", (3.0, 0.2, 3.0), (0, 0.1, 0), "iron", bevel=0.02)
for i, place in enumerate(PLACES, 1):                                   # five bolts, typed (one a hair taller,
    a.cylinder(f"Bolt{i}", 0.05, 0.2 + 0.0005 * (i == 3), place, "brass" if i % 2 else "iron", axis="Y", segments=8)
for i, x in enumerate((-1.2, -0.4, 0.4, 1.2), 1):                       # ... every other one another metal)
    a.box(f"Post{i}", (0.1, 0.8, 0.1), (x, 0.6, 1.3), "iron", bevel=0)  # a fence, post by post
with a.repeat(2, step=(0.3, 0, 0)):                                     # a token repeat: it covers nothing above
    a.box("Nub", (0.1, 0.1, 0.1), (-1.3, 0.25, -1.3), "iron", bevel=0)
a.build()
