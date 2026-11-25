"""build_strew.py — POSITIVE fixture for SCATTER (a.scatter, rbx_strew): one piece modelled, spread over a surface.
On one base slab:
  - a sloped roof with 12 slates, only on its slope, every front laid DOWN the slope (facing=), none touching
    another (pitch=) and none hanging over the roof's edge (margin=),
  - a dome with 24 rivets, only on its upper half, each stood square to the dome and a little its own size.
Its summary must name what was scattered ("repeats: ... (scatter on ...)"). `--report` prints every part's box
before the build (one line `STREW_PARTS {json}`) for kit/test/python/test_strew.py. Used by `lune run kit
selftest`. Never "fix" this file.
"""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_strew", size=(4.6, 1.4, 2.2), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("slate", color=(0.22, 0.24, 0.28), rough=0.75)
a.material("brass", color=(0.72, 0.55, 0.25), metal=1.0, rough=0.35)
a.box("Base", (4.4, 0.2, 2.2), (0, 0.1, 0), "iron", bevel=0.02)
a.wedge("Roof", (2.0, 0.8, 2.0), (-1.2, 0.6, 0), "iron", bevel=0.0)       # high at the back (+Z), down to the front
with a.scatter("Roof", count=12, pitch=0.36, margin=0.18, where=lambda c, n: n[1] > 0.3 and n[2] < -0.1,
               facing=(0, -1, 0), sink=0.004):
    a.box("Shingle", (0.2, 0.02, 0.28), (0, 0.01, 0), "slate", bevel=0.004)
a.sphere("Dome", 0.7, (1.4, 0.2, 0), "iron", segments=32, rings=16)       # half sunk in the base
with a.scatter("Dome", count=24, where=lambda c, n: c[1] > 0.35, vary={"size": 0.25}, sink=0.01):
    a.cylinder("Rivet", 0.035, 0.05, (0, 0.025, 0), "brass", axis="Y", segments=10)

if "--report" in sys.argv:
    back = rbx.BL_FROM_RBX.inverted()
    rows = {}
    for o, _g in a.parts:
        cs = [back @ (o.matrix_world @ rbx.Vector(c)) for c in o.bound_box]
        rows[o.name] = {"lo": [round(min(c[i] for c in cs), 4) for i in range(3)],
                        "hi": [round(max(c[i] for c in cs), 4) for i in range(3)]}
    print("STREW_PARTS " + json.dumps({"parts": rows, "scatters": a._scatter_facts}))
a.build()
