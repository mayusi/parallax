"""build_plank_grooved.py — NOISE: one wooden block carved with grooves on every face to look busy (what the
score-chasing agents did to the starters). The selftest requires the wood_grooves flag AND a score below the
clean board box (build_plank_grained.py). Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("_selftest_plank_grooved", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
S = 2.0
a.box("Body", (S, 1.5, S), (0, 0.75, 0), "wood", bevel=0.03)
for i in range(7):
    y = 0.12 + i * 0.2
    with a.mirror("Z"):
        P.panel_line(a, "Body", f"GrooveF{i}", (-1.0, y, -1.0), (1.0, y, -1.0), "seam", width=0.04, depth=0.05, facing="-Z")
    with a.mirror("X"):
        P.panel_line(a, "Body", f"GrooveS{i}", (1.0, y, -1.0), (1.0, y, 1.0), "seam", width=0.04, depth=0.05, facing="+X")
for i in range(9):
    x = -0.8 + i * 0.2
    P.panel_line(a, "Body", f"GrooveT{i}", (x, 1.5, -1.0), (x, 1.5, 1.0), "seam", width=0.04, depth=0.05, facing="+Y")
a.build()
