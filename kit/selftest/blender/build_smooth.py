"""build_smooth.py — POSITIVE fixture for SMOOTHING BY SUBDIVISION (a.smooth, rbx_subd), the other half of box
modelling. On a base slab:
  - a pod: ONE box, cut twice across, the middle of its top pushed up, then smoothed - all soft but the four
    edges of its foot (held: it stands on the full square it was cut from),
  - a case: a box with its lid inset and sunk, every sharp edge only SOFTENED (held at 0.5): it keeps its shape, its edges go round.
Its summary must name the steps ("modelled: ..."). Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_smooth", size=(4.4, 1.6, 1.6), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("shell", color=(0.62, 0.66, 0.7), rough=0.45)
a.material("wood", color=(0.42, 0.29, 0.17), rough=0.7)
a.box("Base", (4.4, 0.2, 1.6), (0, 0.1, 0), "iron", bevel=0.02)
a.box("Pod", (1.8, 0.9, 1.2), (-1.1, 0.64, 0), "shell", bevel=0)
a.loop("Pod", "X", at=[0.3, 0.7])
a.push("Pod", lambda c, n: n[1] > 0.9 and abs(c[0] + 1.1) < 0.3, 0.35)
a.smooth("Pod", levels=2, crisp=lambda c, d: c[1] < 0.2)
a.box("Case", (1.6, 0.8, 1.1), (1.2, 0.59, 0), "wood", bevel=0)
a.inset("Case", "+Y", 0.14, depth=-0.08)
a.smooth("Case", levels=2, crisp="sharp", hold=0.5)
a.build()
