"""build_uv_coil.py — fixture for AN ISLAND LAID OVER ITSELF (card keak; rbx_uvparts._folded): the high-and-low
route's unwrap by part on a flat ribbon swept two turns round a helix (a screw's thread flank, a spiral ramp). Its
broad face is one region with one border: Blender's angle-based unwrap lays a helicoid out as an arc of more than a
full turn, which coils back across itself (the karambit's screws: 1.05% of their map painted twice). The build must
re-project that island (facts.uv_parts.<group>.folded) and its map must paint nothing twice (uv_overlap passes).
Used by kit/test/python/test_uv_coil.py. Never "fix" this file."""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_uv_coil", tex=512, size=(1.23, 0.72, 1.22), ground=True, low=True)
a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.4)
helix = [(0.4 * math.cos(t), 0.05 + 0.5 * t / (4 * math.pi), 0.4 * math.sin(t))
         for t in [4 * math.pi * k / 96 for k in range(97)]]
a.sweep("Thread", helix, [(-0.22, -0.01), (0.22, -0.01), (0.22, 0.01), (-0.22, 0.01)], "steel", smooth=True,
        up=(0, 1, 0))
a.build()
