"""build_optimize_maps.py — a MASTER (stage="master") that names no map size, so its maps are 2048: a bevelled base
and eight tubes (nine parts in its main mesh), a floater rivet. The selftest builds its GAME version (--optimize): a
game map may be as large as the kit has seen Roblox keep (rbx_optimize.GAME_MAP_CAP: 4096 since the test upload of
2026-11-12; 1024 before it, when this main mesh had to be cut into "main" and "main_4" with a 1024 map each), so
the game version keeps its master's ONE 2048 map on one main mesh. Its summary must say so from the baked file:
"game maps: main 2048". A 1024 map (the master's sharpness lost) or a cut main mesh is the fault this catches.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_optimize_maps", size=(0.8, 0.2, 1.8), stage="master", ground=True)
a.real_scale(100.0)
a.material("steel", color=(0.55, 0.56, 0.6), metal=0.9, rough=0.35)
a.material("dark", color=(0.08, 0.08, 0.09), metal=0.6, rough=0.5)
a.box("Base", (0.8, 0.08, 1.8), (0, 0.04, 0), "dark", bevel=0.01)
for i in range(8):
    a.cylinder(f"Tube{i + 1}", 0.06, 0.6, (0, 0.08 + 0.06 - 0.004, -0.77 + i * 0.22), "steel", axis="X", segments=32,
               bevel=0.004)
with a.floaters():
    a.cylinder("Rivet", 0.02, 0.012, (0.36, 0.08 + 0.004, 0.85), "steel", segments=16)
a.build()
