"""build_cage_stacked.py — NEGATIVE fixture (card xxp7: "two differently named identical parts stacked on one place of
the map can be given two cages (the last bake wins)"): the high-and-low route, two identical CAD pegs that the unwrap
lays on one place of the map, given different cages by a.bake_cage - the build must STOP and say so by their names.
Used by kit/test/python/test_seam_left.py. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_cage_stacked", tex=128, size=(1.2, 0.4, 0.4), ground=True, low=True,
              allow_floating=("PegA", "PegB"))
a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.4)
PEG = "part = Cylinder(40, 100, rotation=(90, 0, 0))\n"
a.cad("PegA", PEG, "steel", pos=(-0.4, 0.2, 0), fillet_mm=2.0)
a.cad("PegB", PEG, "steel", pos=(0.4, 0.2, 0), fillet_mm=2.0)
a.bake_cage(2.0, parts=["PegA"])
a.bake_cage(4.0, parts=["PegB"])
a.build()
