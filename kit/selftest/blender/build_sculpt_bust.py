"""build_sculpt_bust.py — POSITIVE fixture: a sculpted creature bust (a.sculpt) — a skull, a muzzle blended into it,
brow strokes, eye sockets carved, a wrinkle creased, ridged skin on the crown, mirrored across x, and a horn LOFTED
first then taken in as clay (add_part) — must come out one closed, clean part: NOT named sculpt_detail, manifold,
degenerate_faces or open_parts. Its twin: build_sculpt_thin.py. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_sculpt_bust", tex=512, size=(0.71, 1.25, 0.85))
a.real_scale(280.0)
a.material("hide", **rbx.real("Skin III"), life="used")
a.loft("Horn", [(0.0, 0.05), (0.15, 0.04), (0.3, 0.02)], "hide", axis="Y", pos=(0.12, 0.95, -0.05))
s = a.sculpt("Bust", "hide", voxel_mm=1.2, mirror="x")
s.ellipsoid((0, 190, 0), (100, 115, 110))                                  # the skull
s.ellipsoid((0, 120, 60), (65, 55, 70), blend=30)                         # the muzzle, filleted in
s.ellipsoid((0, 70, -10), (90, 70, 95), blend=40)                          # the neck's root
s.stroke([(20, 225, 92), (55, 235, 72), (85, 220, 30)], [15, 11, 7], blend=10)   # a brow ridge, tapering
s.ball((42, 190, 100), 20, carve=True, blend=6)                           # an eye socket
s.crease([(15, 115, 126), (45, 104, 114)], 4.0)                           # a wrinkle on the muzzle
s.noise(1.5, 10.0, kind="ridged", where=rbx.sculpt_shapes.Ball((0, 270, 0), 80), falloff=30)   # crown hide
s.add_part("Horn", blend=8)                                               # the lofted horn, now clay
s.done(adaptivity=0.2, tris=18_000)
a.build()
