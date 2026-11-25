"""build_batch.py — fixtures for WHAT A MODEL COSTS TO DRAW, PAST ITS TRIANGLES (rbx_batch; the 3D methods audit,
stage O). By the word after `--`:
  (none)   POOR: six solid blocks, each a group of its own though none ever moves (six draws where one would do),
           and eight glass panes in a row (a line of sight along the row meets eight faces that face it):
           `draw_calls` and `overdraw` must WARN.
  fine     a block and one glass pane in a group of its own: neither warns (build_batch_fine.py).
After the build `BATCH {json}`: the facts. Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FINE = "fine" in ARGS

a = rbx.Asset("_selftest_batch_fine" if FINE else "_selftest_batch", tex=64, size=(6.0, 2.0, 5.0), ground=True)
a.material("stone", color=(0.6, 0.6, 0.58), rough=0.8)
a.material("glass", color=(0.7, 0.85, 0.9), rough=0.1, alpha=0.3)
if FINE:
    a.box("Base", (6.0, 0.5, 5.0), (0, 0.25, 0), "stone", bevel=0)
    a.box("Pane", (4.0, 1.5, 0.1), (0, 1.25, 0), "glass", bevel=0, group="glass")
else:
    for i in range(6):
        a.box(f"Block{i}", (1.0, 0.5, 5.0), (-2.5 + i, 0.25, 0), "stone", bevel=0,
              group="main" if i == 0 else f"block{i}")
    for i in range(8):
        a.box(f"Pane{i}", (4.0, 1.5, 0.1), (0, 1.25, -2.1 + i * 0.6), "glass", bevel=0, group="glass")
a.build()

line = None
manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
print("BATCH " + json.dumps({"groups": sorted(manifest["groups"])}))
