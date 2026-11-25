"""build_sweep.py — POSITIVE fixture for SWEEP (a.sweep, rbx_sweep): a section carried along a path. A base slab with
  - a horn: a round section along a curve, swelling a little and tapering to a POINT,
  - a rail: a moulding's outline along straight legs with one MITRED corner,
  - a rope ring: a six-sided section twisted two whole turns round a closed loop,
  - a strap: a flat section (wider than thick) along a curve, half as wide again in its middle.
Its summary must name what was swept ("swept: ..."). `--report` prints each part's box and the sweeps' facts
before the build (one line `SWEEP_PARTS {json}`) for kit/test/python/test_sweep.py. Used by `lune run kit
selftest`. Never "fix" this file.
"""

import json
import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_sweep", size=(4.2, 2.0, 4.2), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("bone", color=(0.78, 0.72, 0.6), rough=0.55)
a.material("hemp", color=(0.55, 0.45, 0.28), rough=0.8)
a.box("Slab", (4.0, 0.2, 4.0), (0, 0.1, 0), "iron", bevel=0.02)
a.sweep("Horn", [(-1.2, 0.15, -1.2), (-1.2, 0.9, -1.1), (-0.9, 1.5, -0.8), (-0.4, 1.8, -0.6)], 0.22, "bone",
        scale=[(0, 1), (0.25, 1.15), (1, 0)], sides=16)
MOULD = [(-0.12, 0.0), (0.12, 0.0), (0.12, 0.06), (0.05, 0.1), (0.05, 0.16), (-0.05, 0.16), (-0.05, 0.1), (-0.12, 0.06)]
a.sweep("Rail", [(-1.6, 0.2, 1.6), (1.6, 0.2, 1.6), (1.6, 0.2, 0.0)], MOULD, "iron", smooth=False)
RING = [(1.0 + 0.5 * math.cos(t), 0.26, -1.0 + 0.5 * math.sin(t))
        for t in (2 * math.pi * k / 16 for k in range(16))]
a.sweep("Ring", RING, 0.06, "hemp", sides=6, twist=720, closed=True)
a.sweep("Strap", [(-1.4, 0.21, 0.4), (-0.6, 0.5, 0.6), (0.2, 0.21, 0.4)],
        [(-0.15, -0.01), (0.15, -0.01), (0.15, 0.01), (-0.15, 0.01)], "hemp",
        scale=[(0, (1, 1)), (0.5, (1.6, 1)), (1, (1, 1))])

if "--report" in sys.argv:
    back = rbx.BL_FROM_RBX.inverted()
    rows = {}
    for o, _g in a.parts:
        cs = [back @ (o.matrix_world @ rbx.Vector(c)) for c in o.bound_box]
        rows[o.name] = {"lo": [round(min(c[i] for c in cs), 4) for i in range(3)],
                        "hi": [round(max(c[i] for c in cs), 4) for i in range(3)], "verts": len(o.data.vertices)}
    print("SWEEP_PARTS " + json.dumps({"parts": rows, "sweeps": a.design.get("sweeps")}))
a.build()
