"""build_lamp_post.py — STARTER: street lamp (10 studs). Shows: a stepped octagonal base, rings that break up a
long pole, a hexagonal lantern with a separate transparent glass group (group="glass" -> its own FBX), a cone roof
and finial. Run: lune run kit asset lamp_post
"""

import math
import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("g_lamp_post_old", size=(1.4, 10.5, 1.4), symmetric=True)
a.material("stone", (0.42, 0.42, 0.44), rough=0.9, wear=0.5)
a.material("iron", (0.13, 0.14, 0.15), metal=0.8, rough=0.45, wear=0.3)
a.material("glass", (1.0, 0.8, 0.45), rough=0.1, alpha=0.55)

a.cylinder("Base", 0.7, 0.5, (0, 0.25, 0), "stone", segments=8)
a.cylinder("Step", 0.52, 0.3, (0, 0.65, 0), "stone", segments=8)
a.cylinder("Pole", 0.15, 8.0, (0, 4.8, 0), "iron", segments=12)
for i, y in enumerate((0.9, 1.6, 7.9)):
    a.cylinder(f"Ring{i + 1}", 0.23, 0.14, (0, y, 0), "iron", segments=12)
a.cylinder("Plate", 0.55, 0.12, (0, 8.86, 0), "iron", segments=6)
a.cylinder("Glass", 0.43, 1.0, (0, 9.42, 0), "glass", segments=6, group="glass")
for k in range(6):
    ang = math.radians(60 * k)
    a.cylinder(f"Bar{k + 1}", 0.045, 1.0, (math.cos(ang) * 0.47, 9.42, math.sin(ang) * 0.47), "iron", segments=6, bevel=0)
a.cylinder("Roof", 0.62, 0.45, (0, 10.1, 0), "iron", segments=6, radius_top=0.08)
a.sphere("Finial", 0.11, (0, 10.36, 0), "iron")
a.build()
