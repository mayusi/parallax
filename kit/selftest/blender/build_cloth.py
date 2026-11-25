"""build_cloth.py — fixtures for A CLOTH LAID BY SIMULATION (a.cloth, rbx_garment; the 3D methods audit, stage H). By
the word after `--`:
  (none)   a table and a cover larger than its top, dropped on it: the cover must come to rest on the table, hang
           down round it and not lie inside it (`cloth` holds). The build says "cloth laid: Cover over Table".
  missed   the same cover dropped BESIDE the table: it never comes to rest on it - `cloth` must FAIL
           (build_cloth_missed.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MISSED = "missed" in ARGS

a = rbx.Asset("_selftest_cloth_missed" if MISSED else "_selftest_cloth", tex=128, size=(2.8, 1.1, 2.8),
              ground=False)
a.material("wood", color=(0.45, 0.3, 0.18), rough=0.7)
a.material("linen", color=(0.85, 0.82, 0.74), rough=0.9)
a.box("Table", (2.0, 1.0, 2.0), (0, 0.5, 0), "wood", bevel=0)
a.cloth("Cover", (3.0, 3.0), (6.0 if MISSED else 0.0, 1.3, 0), "linen", over=["Table"], cells=20, frames=45)
a.build()
