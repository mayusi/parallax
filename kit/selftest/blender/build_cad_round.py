"""build_cad_round.py — fixture: a.cad(..., round_mm=) rounds a part's real edges on the mesh (a traced outline
OpenCASCADE will not fillet): one CAD slab built twice, sharp and rounded 2 mm. kit/test/python/test_cad_round.py
counts the hard edges left and reads facts.cad[].round_mm. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

SLAB = """
pts = [(0, 0), (60, 0), (60, 18), (42, 30), (10, 30), (0, 12)]
with BuildSketch(Plane.XY) as sk:
    Polygon(*pts, align=None)
part = extrude(sk.sketch, amount=10, both=True)
"""
a = rbx.Asset("_selftest_cad_round", tex=256, size=(0.3, 0.12, 0.08), ground=False, allow_floating=["Sharp", "Round"])
a.real_scale(280.0)
a.material("steel", (0.5, 0.5, 0.52), metal=1.0, rough=0.3)
a.cad("Sharp", SLAB, "steel", pos=(-0.15, 0, 0))
a.cad("Round", SLAB, "steel", pos=(0.15, 0, 0), round_mm=2.0)
a.build()
