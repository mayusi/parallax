"""build_bad_asset.py — NEGATIVE fixture: must FAIL the gate (too many tris + an open mesh).
Used by `lune run kit selftest` to prove the Blender gate actually bites. Never "fix" this file.
"""

import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_bad", tex=64)
a.material("grey", color=(0.5, 0.5, 0.5))
a.sphere("TooDense", 2.0, (0, 2, 0), "grey", segments=256, rings=128)  # ~65k tris > 20k
a.mesh("OpenSheet", [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], [(0, 1, 2, 3)], "grey", pos=(4, 0, 0))
a.build()
