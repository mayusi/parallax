"""build_deform.py — POSITIVE fixture for DEFORM (a.bend / a.twist / a.taper / a.conform, rbx_deform): parts built
straight, then shaped. A barrel lying on its side with
  - a horn on each side (a.mirror): a plain upright cylinder, tapered to a point, twisted, then bent outward,
  - a strap built flat above it, laid onto its curve (it keeps its thickness).
Its summary must name what was deformed ("deformed: ..."). Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_deform", size=(2.6, 2.0, 1.0), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("bone", color=(0.78, 0.72, 0.6), rough=0.55)
a.material("leather", color=(0.3, 0.18, 0.1), rough=0.7)
a.cylinder("Body", 0.5, 2.0, (0, 0.5, 0), "iron", axis="X", segments=32)
a.box("Strap", (0.25, 0.04, 0.8), (0, 1.3, 0), "leather", bevel=0.005)
a.conform("Strap", "Body", toward="-Y", gap=0.004)
with a.mirror("X"):
    a.cylinder("Horn", 0.12, 0.9, (0.7, 1.4, 0), "bone", axis="Y", segments=16)
a.taper("Horn", along="Y", end=0.15)
a.twist("Horn", along="Y", angle=120)
a.bend("Horn", along="Y", toward="X", angle=70)
a.build()
