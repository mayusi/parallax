"""build_plate_seated.py — POSITIVE fixture: three plates that REST on their host — one made by the kit's own
rbx_parts.plate (it sinks the plate 0.002 studs into the surface, as a mount should), one flush on the face, one sunk
1 mm into it. Their backs start inside the host, where an outward ray finds no face: the gate read all three as
"0% of its back rests on anything" (the Gjallarhorn's crests and clamps, 2026-10-06). Must NOT be flagged:
plate_support. Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("_selftest_plate_seated", tex=64, size=(0.53, 0.53, 0.53), ground=False)
a.real_scale(280.0)
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Host", (0.5, 0.5, 0.5), (0, 0, 0), "body", bevel=0)
square = [(-0.15, -0.15), (0.15, -0.15), (0.15, 0.15), (-0.15, 0.15)]
P.plate(a, "KitPlate", square, "trim", plane="side", surface=0.25, side=1, thickness=0.0143, chamfer=0.003)  # +X face
a.box("FlushPlate", (0.3, 0.0143, 0.3), (0, 0.25 + 0.00715, 0), "trim", bevel=0)  # on the top face, exactly
a.box("SunkPlate", (0.3, 0.3, 0.0143), (0, 0, -0.25 - 0.00715 + 0.00357), "trim", bevel=0)  # 1 mm into the front face
a.build()
