"""build_repeat.py — POSITIVE fixture for REPEAT (a.repeat, rbx_repeat): one part modelled, many made. A slab with
  - a ROW of 12 teeth along its front edge (each 0.3 studs from the last),
  - a RING of 8 posts about its centre,
  - studs ALONG A PATH that turns a corner (each turned to follow it),
  - a 3 x 3 grid of pegs (a row inside a row), every peg a little different (vary=),
  - fins repeated in a row on BOTH sides (a.mirror with a.repeat).
Its summary must name what was repeated ("repeats: ..."). `--report` prints every part's place before the build
(one line `REPEAT_PARTS {json}`: the box each copy fills, in the model's own frame) for
kit/test/python/test_repeat.py. Used by `lune run kit selftest`. Never "fix" this file.
"""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_repeat", size=(4.4, 0.8, 4.4), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("paint", color=(0.55, 0.2, 0.15), rough=0.6)
a.box("Slab", (4.0, 0.2, 4.0), (0, 0.1, 0), "iron", bevel=0.02)
with a.repeat(12, step=(0.3, 0, 0)):                              # a row
    a.box("Tooth", (0.16, 0.3, 0.2), (-1.65, 0.34, -1.8), "paint", bevel=0.01)
with a.repeat(8, around="Y", centre=(0, 0, 0)):                   # a ring
    a.cylinder("Post", 0.08, 0.5, (1.0, 0.44, 0), "iron", axis="Y", segments=12)
with a.repeat(9, along=[(-1.6, 0.25, 1.2), (0.0, 0.25, 1.2), (0.0, 0.25, 1.8)], smooth=False):   # a path with a corner
    a.box("Stud", (0.3, 0.1, 0.1), (-1.6, 0.25, 1.2), "paint", bevel=0.01)
with a.repeat(3, step=(0.3, 0, 0)):                               # a grid: a row inside a row, every peg its own
    with a.repeat(3, step=(0, 0, 0.3), vary={"size": 0.25, "turn": 20}):
        a.box("Peg", (0.14, 0.24, 0.14), (1.1, 0.31, 0.9), "iron", bevel=0.01)
with a.mirror("X"):                                               # both sides
    with a.repeat(4, step=(0, 0, 0.5)):
        a.box("Fin", (0.1, 0.36, 0.3), (1.95, 0.3, -0.9), "paint", bevel=0.01)

if "--report" in sys.argv:
    back = rbx.BL_FROM_RBX.inverted()
    rows = {}
    for o, _g in a.parts:
        cs = [back @ (o.matrix_world @ rbx.Vector(c)) for c in o.bound_box]
        lo = [min(c[i] for c in cs) for i in range(3)]
        hi = [max(c[i] for c in cs) for i in range(3)]
        rows[o.name] = {"mid": [round((p + q) / 2, 4) for p, q in zip(lo, hi)],
                        "size": [round(q - p, 4) for p, q in zip(lo, hi)]}
    print("REPEAT_PARTS " + json.dumps(rows))
a.build()
