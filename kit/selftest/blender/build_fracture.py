"""build_fracture.py — fixtures for A PART BROKEN BEFOREHAND (a.fracture, rbx_fracture; the 3D methods audit, stage
O). By the word after `--`:
  (none)   a crate on a slab, the crate (a group of its own) broken into five pieces that fit together: the crate
           stays, five closed pieces are added, each a group of its own, their volumes adding up to the crate's
           (`fracture` holds), the manifest's `fracture` naming the whole's group and the pieces'. After the build
           `FRACTURE {json}`.
  open     a crate with NO lid (not a closed solid) broken the same way: the build must STOP and say the part is
           not closed (build_fracture_open.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OPEN = "open" in ARGS

a = rbx.Asset("_selftest_fracture_open" if OPEN else "_selftest_fracture", tex=64, size=(4.0, 2.5, 4.0),
              ground=True, **({"require_manifold": False} if OPEN else {}))
a.material("stone", color=(0.6, 0.6, 0.58), rough=0.8)
a.material("wood", color=(0.5, 0.33, 0.18), rough=0.7)
a.box("Slab", (4.0, 0.5, 4.0), (0, 0.25, 0), "stone", bevel=0)
if OPEN:
    v = [(-1, 0.5, -1), (1, 0.5, -1), (1, 0.5, 1), (-1, 0.5, 1), (-1, 2.5, -1), (1, 2.5, -1), (1, 2.5, 1),
         (-1, 2.5, 1)]
    a.mesh("Crate", v, [(0, 1, 2, 3), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)], "wood",
           group="crate")   # no lid
else:
    a.box("Crate", (2.0, 2.0, 2.0), (0, 1.5, 0), "wood", bevel=0, group="crate")
a.vertex_paint(0.8, parts=["Crate"])      # (said for the crate: its pieces must carry it too)
a.fracture("Crate", pieces=5, seed=2)
a.build()

manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
print("FRACTURE " + json.dumps({"fracture": manifest.get("fracture"), "groups": sorted(manifest["groups"])}))
