"""build_sculpt_texels_fine.py — NEGATIVE fixture: the same sculpted log section as build_sculpt_texels.py, its
sawn ends END GRAIN at 2 mm a ring on the same 1024 map — under 4 px of map a ring: the bake blurs them to mottling,
which pattern_resolution must name (a warning). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

MM = 280.0
a = rbx.Asset("_selftest_sculpt_texels_fine", tex=1024, size=(1.07, 1.43, 1.07), stage="master")
a.real_scale(MM)
a.material("bark", **rbx.look("bark"), life="used")
a.material("endgrain", **rbx.look("end_grain", pattern_mm=2.0), grain=(0, 1, 0), life="light")
s = a.sculpt("Log", "bark", voxel_mm=4.0)
G = rbx.sculpt_shapes
s.capsule((0, -60, 0), (0, 460, 0), 150, 140)
s.keep(G.Box((0, 200, 0), (600, 400, 600)), blend=4)                        # sawn flat at both ends
s.noise(4.0, (12.0, 70.0, 12.0), kind="ridged", seed=2, where=G.Box((0, 200, 0), (600, 360, 600)), falloff=15)
s.done(adaptivity=0.1)
a.zone("Log", "endgrain", lambda c, n: abs(n[1]) > 0.85)
a.build()
