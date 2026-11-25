"""build_plank_metal_carved.py — NOISE, carved below the line: a wooden block between steel plates and corner posts, 40
dark grooves carved into its faces. A groove's walls take the cutter's material; counting them out of the wood let
the carving itself push the wood under the "wooden model" line (25% of the surface: here about a fifth without the
walls, nearly half with them) and switch the carving charge off — the score-chased crate's 289 grooves did exactly
that. The selftest requires the craft charge (craft at least 0.1 below the clean board box, build_plank_grained.py):
the walls carved into wood are the wood's own surface. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_plank_metal_carved", size=(2.8, 2.3, 2.8), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
a.material("steel", (0.56, 0.57, 0.6), metal=1.0, rough=0.4)
a.box("Base", (2.8, 0.4, 2.8), (0, 0.2, 0), "steel", bevel=0.02)
a.box("Body", (2.0, 1.5, 2.0), (0, 1.15, 0), "wood", bevel=0.02)
a.box("Top", (2.8, 0.4, 2.8), (0, 2.1, 0), "steel", bevel=0.02)
for x in (-1.2, 1.2):
    for z in (-1.2, 1.2):
        a.box(f"Post{'L' if x < 0 else 'R'}{'F' if z < 0 else 'B'}", (0.4, 1.5, 0.4), (x, 1.15, z), "steel", bevel=0.02)
for i in range(10):
    y = 0.48 + i * 0.15
    for z in (-1.0, 1.0):
        a.cut("Body", a.box(f"Groove{'F' if z < 0 else 'B'}{i}", (1.96, 0.06, 0.24), (0, y, z), "seam", bevel=0))
    for x in (-1.0, 1.0):
        a.cut("Body", a.box(f"Groove{'L' if x < 0 else 'R'}{i}", (0.24, 0.06, 1.96), (x, y, 0), "seam", bevel=0))
a.build()
