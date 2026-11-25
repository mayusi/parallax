"""build_plank_fused_nub.py — NOISE, hidden behind steel: a wooden block FUSED into a small steel nub (the nub is the
fuse target, so steel is the part's first material), then 28 grooves carved into it. Judging a part by its first
material saw a steel part — no wood, no carving; the selftest requires the wood_grooves flag AND a score below the
clean board box (build_plank_grained.py): wood is judged per face, where the wood is. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("_selftest_plank_fused_nub", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
a.material("steel", (0.56, 0.57, 0.6), metal=1.0, rough=0.4)
S = 2.0
a.box("Nub", (0.3, 0.3, 0.1), (0, 0.75, -0.98), "steel", bevel=0.01)  # a boss on the front face, mostly sunk in
a.box("Body", (S, 1.5, S), (0, 0.75, 0), "wood", bevel=0.03)
a.fuse("Nub", "Body")
for i in range(7):  # the grooves of build_plank_grooved.py, cut into the fused part (named after its target: Nub)
    y = 0.12 + i * 0.2
    if abs(y - 0.75) < 0.2:
        continue  # (the rows behind the nub)
    with a.mirror("Z"):
        P.panel_line(a, "Nub", f"GrooveF{i}", (-1.0, y, -1.0), (1.0, y, -1.0), "seam", width=0.04, depth=0.05,
                     facing="-Z")
    with a.mirror("X"):
        P.panel_line(a, "Nub", f"GrooveS{i}", (1.0, y, -1.0), (1.0, y, 1.0), "seam", width=0.04, depth=0.05,
                     facing="+X")
for i in range(9):
    x = -0.8 + i * 0.2
    P.panel_line(a, "Nub", f"GrooveT{i}", (x, 1.5, -1.0), (x, 1.5, 1.0), "seam", width=0.04, depth=0.05, facing="+Y")
a.build()
