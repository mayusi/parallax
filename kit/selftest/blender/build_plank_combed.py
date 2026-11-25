"""build_plank_combed.py — NOISE, carved the sly way: the same 37 grooves as build_plank_grooved.py, but cut by three
COMB-shaped cutters (one cut() each, a mirrored copy for the opposite face) instead of 37 panel lines. Counting cut()
calls saw 3 cuts and let it outscore real boards; the selftest requires the wood_grooves flag AND a score below the
clean board box (build_plank_grained.py): carving is counted in the regions it leaves. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402


def comb(levels, inner, outer, spine, lo, hi, w=0.04):
    """a comb outline (u, v): a spine just outside the face (u from outer to spine) and one tooth per level reaching
    `inner` (into the block) — every tooth carves one groove, the spine touches nothing"""
    pts = [(spine, lo), (spine, hi), (outer, hi)]
    for v in sorted(levels, reverse=True):
        pts += [(outer, v + w / 2), (inner, v + w / 2), (inner, v - w / 2), (outer, v - w / 2)]
    pts.append((outer, lo))
    return pts


a = rbx.Asset("_selftest_plank_combed", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
S = 2.0
a.box("Body", (S, 1.5, S), (0, 0.75, 0), "wood", bevel=0.03)
rows = [0.12 + i * 0.2 for i in range(7)]
with a.mirror("Z"):  # the front face (u = toward the front) and the back
    a.cut("Body", a.extrude("CombF", comb(rows, 0.95, 1.05, 1.1, 0.02, 1.48), 2.2, "seam", plane="side"))
with a.mirror("X"):  # the right face and the left
    a.cut("Body", a.extrude("CombS", comb(rows, 0.95, 1.05, 1.1, 0.02, 1.48), 1.96, "seam", plane="front"))
cols = [-0.8 + i * 0.2 for i in range(9)]  # the top: grooves front-to-back, the spine past the front edge
a.cut("Body", a.extrude("CombT", comb(cols, -0.98, 1.05, 1.1, -0.9, 0.9), 0.1, "seam", plane="top",
                         pos=(0, 1.5, 0)))
a.build()
