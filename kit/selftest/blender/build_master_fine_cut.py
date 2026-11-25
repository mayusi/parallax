"""build_master_fine_cut.py — POSITIVE fixture: a MASTER (stage="master") plate with two small screw recesses cut into
it. On a game build a recess smaller than a finger is a waste of triangles (tiny_cuts: bake it); a master is the
no-limits original whose real recesses ARE its detail (the game version bakes them) — so the master is never warned
(found by the Gjallarhorn test's vent ports, 2026-10-06). Must NOT be flagged: tiny_cuts.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_master_fine_cut", tex=64, size=(1.0, 0.2, 1.0), stage="master")
a.material("steel", color=(0.55, 0.56, 0.6))
a.box("Plate", (1.0, 0.2, 1.0), (0, 0.1, 0), "steel", bevel=0)
for i, x in enumerate((-0.3, 0.3)):  # two screw recesses, 0.02 studs across, 0.015 deep
    a.cut("Plate", a.cylinder(f"Screw{i + 1}Cut", 0.01, 0.03, (x, 0.2, 0), "steel", segments=16))
a.build()
