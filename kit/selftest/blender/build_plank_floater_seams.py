"""build_plank_floater_seams.py — NOISE, baked instead of carved: one wooden block with 28 dark SEAMS baked onto it
(floaters: lines drawn into its maps, no geometry). Carved grooves are charged; the same grooves baked on draw the same
lie into the maps. The selftest requires the wood_grooves flag AND a score below the clean board box
(build_plank_grained.py): lines baked on wood count with the grooves. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_plank_floater_seams", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
S = 2.0
a.box("Body", (S, 1.5, S), (0, 0.75, 0), "wood", bevel=0.03)
with a.floaters():
    for i in range(7):
        y = 0.12 + i * 0.2
        a.box(f"SeamF{i}", (1.94, 0.03, 0.01), (0, y, -1.006), "seam", bevel=0)
        a.box(f"SeamB{i}", (1.94, 0.03, 0.01), (0, y, 1.006), "seam", bevel=0)
        a.box(f"SeamR{i}", (0.01, 0.03, 1.94), (1.006, y, 0), "seam", bevel=0)
        a.box(f"SeamL{i}", (0.01, 0.03, 1.94), (-1.006, y, 0), "seam", bevel=0)
a.build()
