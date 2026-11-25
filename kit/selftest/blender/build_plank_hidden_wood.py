"""build_plank_hidden_wood.py — NOISE, watered down: a wooden block with two broad recesses carved into its faces
(about a fifth of its surface is carved walls) and a stack of thin wooden sheets hidden INSIDE it (a.internal: never
seen). Counting the hidden sheets as wood surface diluted the carved share below the line; the selftest requires the
carved share measured on the wood that is SEEN (at least the 8% line, like the same block without the sheets). Never
"fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_plank_hidden_wood", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
S = 2.0
a.box("Body", (S, 1.5, S), (0, 0.75, 0), "wood", bevel=0.03)
for z in (-1.0, 1.0):  # a broad recess 0.1 deep in the front and the back
    a.cut("Body", a.box(f"Recess{'F' if z < 0 else 'B'}", (1.6, 1.1, 0.2), (0, 0.75, z), "seam", bevel=0))
with a.internal():  # twelve thin sheets inside the block, clear of the recesses: wood nobody ever sees
    for i in range(12):
        a.box(f"Sheet{i}", (1.8, 1.3, 0.02), (0, 0.75, -0.77 + i * 0.14), "wood", bevel=0)
a.build()
