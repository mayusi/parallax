"""build_filled_bore.py — NEGATIVE fixture: a barrel that was never bored out (a solid rod) with a clear path
stated down its bore. Must be flagged: clear:Bore.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_bore", tex=64, size=(0.2, 0.2, 1.2))
a.real_scale(100)
a.material("steel", color=(0.3, 0.3, 0.32), metal=1.0, rough=0.35)
a.cylinder("Barrel", 0.08, 1.2, (0, 0.1, 0), "steel", axis="Z", bevel=0)  # solid: no bore cut
a.clear_path("Bore", (0, 0.1, 0.65), (0, 0.1, -0.65), radius=0.02, why="a barrel is a TUBE: cut the bore")
a.build()
