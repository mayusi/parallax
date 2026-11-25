"""build_optimize_dense.py — a MASTER (stage="master") for `kit optimize`: three dense tubes (256 segments) on a
bevelled base, a floater rivet. The selftest builds its GAME version (--optimize): cut to the prop budget with the
master's detail baked on, its surface within tolerance of the master's — optimize_loss must NOT be named. Starved to
60 triangles (--budget=60) the cut must be CAUGHT (optimize_loss named): the loss is measured, never assumed.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_optimize_dense", tex=64, size=(0.8, 0.32, 1.2), stage="master", ground=True)
a.real_scale(100.0)
a.material("steel", color=(0.55, 0.56, 0.6), metal=0.9, rough=0.35)
a.material("dark", color=(0.08, 0.08, 0.09), metal=0.6, rough=0.5)
a.box("Base", (0.8, 0.08, 1.2), (0, 0.04, 0), "dark", bevel=0.01)
for i, x in enumerate((-0.26, 0.0, 0.26)):
    a.cylinder(f"Tube{i + 1}", 0.12, 1.1, (x, 0.08 + 0.12 - 0.004, 0), "steel", axis="Z", segments=256, bevel=0.008)
    a.cut(f"Tube{i + 1}", a.cylinder(f"Tube{i + 1}BoreCut", 0.085, 1.3, (x, 0.2, 0), "steel", axis="Z", segments=256))
with a.floaters():
    a.cylinder("Rivet", 0.02, 0.012, (0.36, 0.08 + 0.004, 0.5), "steel", segments=16)
a.build()
