"""build_open.py — BAD fixture for the `openings` check (rbx.Asset._openings_check, rbx_repair): two parts no
repair can close - a single flat sheet of faces (a surface with no thickness) and a tube with three wall panels
torn out (an open rim that is not flat). The build must FAIL, and say WHICH part is open, WHAT kind of opening it
is and what closes it - where the `manifold` gate only counts edges. Used by `lune run kit selftest`. Never "fix"
this file."""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_open", size=(3.0, 1.0, 1.4), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.box("Base", (3.0, 0.2, 1.4), (0, 0.1, 0), "iron", bevel=0.02)
a.mesh("Sheet", [(-1.2, 0.2, -0.3), (-0.4, 0.2, -0.3), (-0.4, 0.9, -0.3), (-1.2, 0.9, -0.3)], [(0, 1, 2, 3)], "iron")
ring = [(0.3 * math.cos(2 * math.pi * i / 16) + 0.8, 0.3 * math.sin(2 * math.pi * i / 16)) for i in range(16)]
verts = [(x, 0.2, z) for x, z in ring] + [(x, 0.9, z) for x, z in ring] + [(0.8, 0.2, 0.0), (0.8, 0.9, 0.0)]
walls = [(i, (i + 1) % 16, 16 + (i + 1) % 16, 16 + i) for i in range(16) if i not in (0, 1, 2)]
caps = [(i, 32, (i + 1) % 16) for i in range(16)] + [(16 + i, 16 + (i + 1) % 16, 33) for i in range(16)]
a.mesh("Torn", verts, walls + caps, "iron")
a.build()
