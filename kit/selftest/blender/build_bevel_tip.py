"""build_bevel_tip.py — POSITIVE fixture: an ornate bar carved from a pointed leaf (side) and a curved band (front),
like a spine along a tube's flank. Where its pointed tips meet the band, several sharp edges converge and the clamped
bevel leaves faces 0.003-0.009 mm across — under the validator's zero-area line. The blanket dissolve_degenerate
missed them (and, on the real part, tore 3 edges open); rbx._drop_micro_faces collapses exactly those faces (found by
the Gjallarhorn test's SideSpine, 2026-10-06). Must NOT be flagged: degenerate_faces, manifold.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

# the side: a leaf 0.83 studs long, pointed at both ends (64 points)
leaf = []
for i in range(64):
    t = 2 * math.pi * i / 64
    x = math.cos(t)
    leaf.append((x * 0.415, 0.4 + math.sin(t) * (1 - abs(x) ** 1.5) ** 0.5 * 0.09))
# the front: a curved band 0.123 .. 0.155 studs out from an axis at height 0.4, from -28 to 40 degrees
band = ([(0.155 * math.cos(math.radians(t)), 0.4 + 0.155 * math.sin(math.radians(t))) for t in range(-28, 44, 6)]
        + [(0.123 * math.cos(math.radians(t)), 0.4 + 0.123 * math.sin(math.radians(t))) for t in range(40, -32, -6)])

a = rbx.Asset("_selftest_bevel_tip", tex=64, size=(0.4, 0.6, 1.0), ground=False)
a.material("bronze", color=(0.58, 0.40, 0.25))
a.carve("Spine", "bronze", side=leaf, front=band, segments=2)
a.build()
