"""build_repair.py — POSITIVE fixture for REPAIR (a.repair, rbx_repair; the build's own seam weld). On a base
slab, three parts given as raw faces that are NOT closed solids:
  - a bin: a box listed without its top - a.repair caps the flat hole,
  - a pipe: a sixteen-sided tube listed without its ends - a.repair caps both,
  - a shell: a box listed as six faces that share no point - never repaired by the script: the BUILD welds its
    seams itself (points on each other are one point).
It must build as closed solids, and its summary must say what was closed ("repaired: ..."). Used by `lune run kit
selftest`. Never "fix" this file."""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def box(x, y, z, s=0.6):
    return [(px * s + x, py * s + y, pz * s + z) for px, py, pz in CUBE]


a = rbx.Asset("_selftest_repair", size=(3.4, 1.0, 1.4), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("wood", color=(0.42, 0.29, 0.17), rough=0.7)
a.box("Base", (3.4, 0.2, 1.4), (0, 0.1, 0), "iron", bevel=0.02)
a.mesh("Bin", box(-1.4, 0.2, -0.3), [f for k, f in enumerate(FACES) if k != 4], "wood")   # no top (+Y)
a.repair("Bin")
ring = [(0.25 * math.cos(2 * math.pi * i / 16), 0.25 * math.sin(2 * math.pi * i / 16)) for i in range(16)]
pipe = [(x, 0.2, z) for x, z in ring] + [(x, 0.9, z) for x, z in ring]
a.mesh("Pipe", pipe, [(i, (i + 1) % 16, 16 + (i + 1) % 16, 16 + i) for i in range(16)], "iron")
a.repair("Pipe")
apart, faces = [], []
for f in FACES:
    faces.append(tuple(range(len(apart), len(apart) + 4)))
    apart += [box(0.8, 0.2, -0.3)[v] for v in f]
a.mesh("Shell", apart, faces, "wood")
a.build()
