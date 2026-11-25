"""build_lid_into_wall.py — NEGATIVE fixture: a lid on a hinge that swings, through its travel, straight into a wall
standing beside the box (clear at rest, buried at 90 degrees). The travel check built its collision trees in each
object's OWN space, so a part moved through its travel was tested where it rests: no travel collision was ever
caught (found by the Gjallarhorn test, 2026-10-06). Must be flagged: mechanism.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_lid_wall", tex=64, size=(1.2, 1.2, 1.0))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Box", (1.0, 0.4, 1.0), (0, 0.2, 0), "body", bevel=0)
a.box("Wall", (1.0, 1.2, 0.1), (0, 0.6, 0.6), "body", bevel=0)  # behind the box (+Z), clear of it, up to y 1.2
# the lid rests on the box; its hinge is the back edge (z 0.5): opening by 90 degrees swings it up and back into the wall
a.box("Lid", (1.0, 0.05, 1.0), (0, 0.425, 0), "trim", bevel=0, group="lid")
a.joint("Lid", "lid", "hinge", axis=(1, 0, 0), pivot=(0, 0.45, 0.5), max=100)
a.build()
