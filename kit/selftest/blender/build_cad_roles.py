"""build_cad_roles.py — fixture: a.cad(..., round_mm=, edge_roles=) rounds a part's edges BY ROLE: the same CAD slab
rounded 2 mm everywhere except its top face's four edges, kept crisp by a box (round_mm 0), and its front end's
edges rounded 0.6 mm by another. kit/test/python/test_cad_roles.py reads facts.cad[].edge_roles. Never "fix" this
file."""

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
a = rbx.Asset("_selftest_cad_roles", tex=256, size=(0.3, 0.12, 0.08), ground=False, allow_floating=["Roles"])
a.real_scale(280.0)
a.material("steel", (0.5, 0.5, 0.52), metal=1.0, rough=0.3)
a.cad("Roles", SLAB, "steel", round_mm=2.0, edge_roles=[
    {"box": (-1, 29, -11, 61, 31, 11), "round_mm": 0},      # the top face: a cut edge, kept crisp
    {"box": (-1, -1, -11, 1, 13, 11), "round_mm": 0.6},     # the left end (x = 0): a small round
])
a.build()
