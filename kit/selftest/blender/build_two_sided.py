"""build_two_sided.py — POSITIVE fixture for TWO-SIDED surfaces (a.two_sided): on a base slab, a banner on a pole
(one curved sheet of faces) and two leaves (a sheet, mirrored), each a surface with NO thickness given its back as
real faces. It must build as closed solids - no open edge, nothing inside out - and its summary must say so
("two-sided: ..."). Without a.two_sided the same model fails `openings` by name (build_open.py's sheet). Used by
`lune run kit selftest`. Never "fix" this file."""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402


def sheet(nx, nz, at):
    """a grid of nx x nz squares -> (points by at(u, v), faces)"""
    verts = [at(x / nx, z / nz) for z in range(nz + 1) for x in range(nx + 1)]
    faces = [(z * (nx + 1) + x, z * (nx + 1) + x + 1, (z + 1) * (nx + 1) + x + 1, (z + 1) * (nx + 1) + x)
             for z in range(nz) for x in range(nx)]
    return verts, faces


a = rbx.Asset("_selftest_two_sided", size=(3.0, 2.2, 1.4), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("cloth", color=(0.62, 0.12, 0.1), rough=0.8)
a.material("leaf", color=(0.2, 0.42, 0.16), rough=0.6)
a.box("Base", (3.0, 0.2, 1.4), (0, 0.1, 0), "iron", bevel=0.02)
a.cylinder("Pole", 0.04, 1.9, (-1.1, 1.15, 0), "iron", axis="Y", segments=12)
a.mesh("Banner", *sheet(8, 4, lambda u, v: (-1.06 + 1.2 * u, 2.0 - 0.9 * v, 0.12 * math.sin(5 * u))), "cloth")
a.two_sided("Banner")
with a.mirror("Z"):
    a.mesh("Frond", *sheet(4, 2, lambda u, v: (0.6 + 0.9 * u, 0.19 + 0.9 * u - 0.7 * u * u,
                                               0.2 + (v - 0.5) * 0.3 * (1 - u * 0.8))), "leaf")
a.two_sided("Frond")
a.build()
