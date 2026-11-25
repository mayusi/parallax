"""build_plank_stencils.py — CRAFT with markings: the clean board box of build_plank_grained.py with a "SUPPLY"
stencil on each face (a.text, baked as floaters; the two side ones are one mirrored call). Text on wood is a marking, never a seam drawn into the maps: judged
by name, four stencils (none called "text" or "decal") counted as four baked lines and charged an honest crate. The
selftest requires it spared (no wood_grooves): text is exempt by its tag. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_plank_stencils", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("core", (0.12, 0.08, 0.05), rough=0.95)
a.material("paint", (0.1, 0.1, 0.1), rough=0.7)
S, T, gap = 2.0, 0.08, 0.03
a.box("Core", (S - 2 * T + 0.02, 1.5 - T + 0.01, S - 2 * T + 0.02), (0, (1.5 - T + 0.01) / 2, 0), "core")
w = (1.5 - 3 * gap) / 4
for i in range(4):
    y = w / 2 + i * (w + gap)
    with a.mirror("Z"):
        a.box(f"BoardF{i}", (S, w, T), (0, y, -S / 2 + T / 2), "wood", bevel=0.02)
    with a.mirror("X"):
        a.box(f"BoardS{i}", (T, w, S - 2 * T), (S / 2 - T / 2, y, 0), "wood", bevel=0.02)
wt = (S - 3 * gap) / 4
for i in range(4):
    a.box(f"BoardTop{i}", (wt, T, S), (-S / 2 + wt / 2 + i * (wt + gap), 1.5 - T / 2, 0), "wood", bevel=0.02)
with a.floaters():
    a.text("StencilF", "SUPPLY", (0, 0.75, -S / 2 - 0.002), "paint", size=0.3, facing="-Z")
    a.text("StencilB", "SUPPLY", (0, 0.75, S / 2 + 0.002), "paint", size=0.3, facing="+Z")
    with a.mirror("X"):  # (the sides: ONE call, its mirrored copy on the other side — a copy is text as well)
        a.text("StencilR", "SUPPLY", (S / 2 + 0.002, 0.75, 0), "paint", size=0.3, facing="+X")
a.build()
