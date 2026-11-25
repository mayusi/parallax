"""build_hair.py — fixtures for HAIR AS LOCKS SCATTERED ALONG A FLOW (a.lock + a.scatter; the 3D methods audit, stage
H). By the word after `--`:
  (none)   a scalp block with forty locks scattered over its top, swept back (facing -z), each a little different.
           Before the build `HAIR {json}` is printed: how many locks stand, how far their roots are from the
           scalp's top, and which way they lean.
  thin     a.lock with one segment: the build must STOP and say what a lock takes (build_hair_thin.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import numpy as np  # noqa: E402
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
THIN = "thin" in ARGS

a = rbx.Asset("_selftest_hair_thin" if THIN else "_selftest_hair", tex=128, size=(2.0, 1.8, 3.4), ground=True)
a.material("skin", color=(0.8, 0.62, 0.5), rough=0.6)
a.material("hair", color=(0.2, 0.12, 0.06), rough=0.5)
a.box("Scalp", (2.0, 1.0, 2.0), (0, 0.5, 0), "skin", bevel=0)
with a.scatter("Scalp", count=40, facing=(0, 0, -1), where=lambda c, n: n[1] > 0.5, vary={"size": 0.3}, margin=0.1):
    a.lock("Lock", 0.9, 0.14, "hair", droop=0.7, segments=1 if THIN else 4)
a.lock("Fringe", 0.8, 0.14, "hair", droop=2.0, pos=(0, 1.0, 0.85))   # one that HANGS over the back edge

back = rbx.BL_FROM_RBX.inverted()
roots, lean, fringe = [], [], None
for o, _g in a.parts:
    if o.name.startswith("Fringe"):
        pts = np.array([tuple(back @ (o.matrix_world @ v.co)) for v in o.data.vertices])
        tv = np.array([[lt.vertices[0], lt.vertices[1], lt.vertices[2]]
                       for lt in (o.data.calc_loop_triangles() or o.data.loop_triangles)])
        p = np.array([tuple(v.co) for v in o.data.vertices])[tv]
        fringe = {"volume": round(float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6.0), 5),
                  "tip_y": round(float(pts[np.linalg.norm(pts - pts[pts[:, 1].argmax()], axis=1).argmax()][1]), 3)}
        continue
    if not o.name.startswith("Lock"):
        continue
    pts = np.array([tuple(back @ (o.matrix_world @ v.co)) for v in o.data.vertices])
    low = pts[pts[:, 1].argmin()]
    far = pts[np.linalg.norm(pts - low, axis=1).argmax()]
    roots.append(float(low[1]))
    lean.append(float(far[2] - low[2]))
print("HAIR " + json.dumps({"locks": len(roots), "root_off": round(max(abs(r - 1.0) for r in roots), 4),
                            "lean_z": round(float(np.mean(lean)), 3), "fringe": fringe}))
a.build()
