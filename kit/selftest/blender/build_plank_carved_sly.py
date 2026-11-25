"""build_plank_carved_sly.py — NOISE, carved the slyest way: the comb cutters of build_plank_combed.py, cut in the
board's OWN wood material (so no foreign material marks the grooves) with spines that SCRAPE the surface (so each comb
leaves one connected carving, not separate grooves). The selftest requires the wood_grooves flag AND a score below the
clean board box: each cut's own faces are found through the boolean, and the carved share of the surface counts.
Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402


def comb(levels, inner, outer, spine_in, lo, hi, w=0.04):
    """teeth reach `inner`; the spine's inner edge is `spine_in` — just INSIDE the face, so it scrapes the surface"""
    pts = [(outer + 0.05, lo), (outer + 0.05, hi), (spine_in, hi)]
    for v in sorted(levels, reverse=True):
        pts += [(spine_in, v + w / 2), (inner, v + w / 2), (inner, v - w / 2), (spine_in, v - w / 2)]
    pts.append((spine_in, lo))
    return pts


a = rbx.Asset("_selftest_plank_carved_sly", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
S = 2.0
a.box("Body", (S, 1.5, S), (0, 0.75, 0), "wood", bevel=0.03)
rows = [0.12 + i * 0.2 for i in range(7)]
with a.mirror("Z"):
    a.cut("Body", a.extrude("CombF", comb(rows, 0.95, 1.05, 0.995, 0.02, 1.48), 2.2, "wood", plane="side"))
with a.mirror("X"):
    a.cut("Body", a.extrude("CombS", comb(rows, 0.95, 1.05, 0.995, 0.02, 1.48), 1.96, "wood", plane="front"))
a.build()
