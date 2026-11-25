"""build_drop_flat.py — fixture for TAKING OUT WHAT SHAPES NOTHING (card fw6p): a Block built as a grid of 12 x 12
faces on each side (1,728 triangles for a box) and a Peg sunk half into it. a.drop_flat("Block") dissolves every
vertex in the middle of a flat side or along a straight edge: the Block comes back as a box (12 triangles), its
size unchanged. Two Pegs sunk half into it: their bottoms (4 of 36 triangles) are never seen and nobody asked a.drop_hidden: the summary says what it would
take. Used by kit/test/python/test_topology_tools.py. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

N, S = 12, 0.6
verts, faces, index = [], [], {}


def v(p):
    key = tuple(round(c, 6) for c in p)
    if key not in index:
        index[key] = len(verts)
        verts.append(key)
    return index[key]


sides = [((-S / 2, 0, -S / 2), (0, 0, S), (S, 0, 0)), ((-S / 2, S, -S / 2), (S, 0, 0), (0, 0, S)),
         ((-S / 2, 0, -S / 2), (S, 0, 0), (0, S, 0)), ((-S / 2, 0, S / 2), (0, S, 0), (S, 0, 0)),
         ((-S / 2, 0, -S / 2), (0, S, 0), (0, 0, S)), ((S / 2, 0, -S / 2), (0, 0, S), (0, S, 0))]
for o, du, dv in sides:
    for i in range(N):
        for j in range(N):
            faces.append([v(tuple(o[k] + du[k] * (i + a) / N + dv[k] * (j + b) / N for k in range(3)))
                          for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))])
a = rbx.Asset("_selftest_drop_flat", tex=64, size=(0.6, 0.8, 0.6), ground=True)
a.material("steel", color=(0.55, 0.56, 0.6), metal=0.9, rough=0.35)
a.mesh("Block", verts, faces, "steel")
a.drop_flat("Block")
a.box("Peg", (0.2, 0.4, 0.2), (-0.15, 0.6, 0.0), "steel", bevel=0)
a.box("Peg2", (0.2, 0.4, 0.2), (0.15, 0.6, 0.0), "steel", bevel=0)
a.build()
