"""build_travel_seated.py — NEGATIVE fixture for the mechanism gate's TRAVEL (rbx_travel; the review of D-R05): the
runner RESTS on six seat blocks of the bed's group (sunk a hair into them: many colliding triangle pairs at rest),
slides off them, and then drives into a tall pin of the SAME group, between the old five stops. While it cuts the
pin the group's total of colliding pairs is LOWER than at rest - a check that only asks "more pairs than at rest?"
before it looks deeper passes this (a slide on its rails that meets a strap of the same body). Must be flagged:
mechanism, naming the pin. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_travel_seated", tex=64, size=(6.0, 0.8, 1.5))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Bed", (6.0, 0.2, 1.5), (0, 0.1, 0), "body", bevel=0)
for i in range(6):   # the seats: y 0.200 .. 0.304, the runner's underside (y 0.300) sunk 0.004 into them
    a.box(f"Seat{i}", (0.04, 0.104, 0.25), (-2.125 + i * 0.05, 0.252, 0), "body", bevel=0)
a.box("Pin", (0.1, 0.6, 0.1), (-0.5, 0.5, 0.0), "body", bevel=0)                        # y 0.2 .. 0.8, in the path
a.box("Runner", (0.3, 0.3, 0.3), (-2.0, 0.45, 0), "trim", bevel=0, group="runner")     # y 0.30 .. 0.60
a.joint("Runner", "runner", "slide", axis=(1, 0, 0), max=4.0)
a.build()
