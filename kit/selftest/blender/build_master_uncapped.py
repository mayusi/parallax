"""build_master_uncapped.py — POSITIVE fixture: a MASTER (Asset(stage="master")) carrying ~65k triangles in ONE mesh.
A master is the no-limits original (the first product must look its best; `kit optimize` makes the game mesh from
it): Roblox's 20k-per-mesh cap and the tier's triangle budget do not apply to it. Must NOT be flagged: tris.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_master", tex=64, size=(1.0, 1.0, 1.0), ground=False, stage="master")
a.material("body", color=(0.55, 0.56, 0.6))
a.sphere("Ball", 0.5, (0, 0, 0), "body", segments=256, rings=128)
a.build()
