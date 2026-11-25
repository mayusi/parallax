"""build_sculpt_texels.py — POSITIVE fixture: a sculpted log section (a.sculpt: a trunk with ridged bark, sawn flat at
both ends) whose sawn ends are END GRAIN at 10 mm a ring, on a 1024 map. A sculpt's relief once cut its UVs into
thousands of islands (a smart projection: the tree stump's map was 0.11% surface, 0.05 px per mm — every ring under one
pixel): its faces are now unwrapped by their FORM (rbx_uvcharts), so a ring gets its 4+ px and pattern_resolution
stays quiet. Its twin: build_sculpt_texels_fine.py (2 mm rings: under 4 px, named). Used by `lune run kit selftest`.
Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

MM = 280.0
a = rbx.Asset("_selftest_sculpt_texels", tex=1024, size=(1.07, 1.43, 1.07), stage="master")
a.real_scale(MM)
a.material("bark", **rbx.look("bark"), life="used")
a.material("endgrain", **rbx.look("end_grain", pattern_mm=10.0), grain=(0, 1, 0), life="light")
s = a.sculpt("Log", "bark", voxel_mm=4.0)
G = rbx.sculpt_shapes
s.capsule((0, -60, 0), (0, 460, 0), 150, 140)
s.keep(G.Box((0, 200, 0), (600, 400, 600)), blend=4)                        # sawn flat at both ends
s.noise(4.0, (12.0, 70.0, 12.0), kind="ridged", seed=2, where=G.Box((0, 200, 0), (600, 360, 600)), falloff=15)
s.done(adaptivity=0.1)
a.zone("Log", "endgrain", lambda c, n: abs(n[1]) > 0.85)
a.build()
