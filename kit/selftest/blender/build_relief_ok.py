"""build_relief_ok.py — POSITIVE fixture: ornaments built from a relief height field (the .npz `kit vision relief`
writes): a dome rising from a plate, and a bust (both_sides: mirrored through its base plane) beside it. Their picture
is a disc 56 px across in a 64 px frame with a 2-pixel strand sticking out of its left side (the outline opening drops
it). At width=2.0 studs a disc is ~1.7 studs across, so the model is ~3.7 x 1.7 x 0.70 studs — a relief at the wrong
scale or depth misses that target. Must NOT be named: manifold, wire_edges, loose_verts, degenerate_faces,
floating_parts, inside_out, size_vs_target. Used by `lune run kit selftest`.
"""

import os
import sys

import numpy as np

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

n, r = 64, 28.0
yy, xx = np.mgrid[0:n, 0:n].astype(float)
rr = ((xx - (n - 1) / 2) ** 2 + (yy - (n - 1) / 2) ** 2) / r**2
mask = rr < 1.0
mask[31:33, 0:6] = True  # the strand: 2 px thick (an outline opening of 1 px drops it)
height = np.where(rr < 1.0, np.sqrt(np.clip(1.0 - rr, 0.0, None)), 0.0)
path = os.path.join(rbx.BUILD, "selftest", "_selftest_relief.npz")
os.makedirs(os.path.dirname(path), exist_ok=True)
np.savez_compressed(path, height=height.astype(np.float32), mask=mask)

a = rbx.Asset("_selftest_relief_ok", tex=64, size=(3.75, 1.75, 0.70))
a.material("plate", color=(0.5, 0.5, 0.52))
a.material("bronze", color=(0.55, 0.36, 0.2), metal=1.0, rough=0.4)
a.box("Plate", (3.0, 1.0, 0.2), (0, 0.875, 0), "plate", bevel=0)
a.relief("Dome", path, "bronze", width=2.0, depth=0.3, base=0.05, pos=(-1.0, 0.875, 0.1))  # rises toward +Z
a.relief("Bust", path, "bronze", width=2.0, depth=0.3, base=0.05, both_sides=True, pos=(1.0, 0.875, 0.1))
a.build()
