"""build_seam_routes.py - fixture for SEAMS YOU PLACE ON EVERY ROUTE (a.seams; the 3D methods audit's PARTLY "seam
placement on a sculpt, a generated mesh, or the high-and-low route's game mesh - a.seams only works on a
kit-modelled part"). After `--`:
  low     the round handle of build_seam_placed.py on the HIGH-AND-LOW route (Asset(low=)): cut down
          its back (z > 0.49) and its caps off (sharp=60) - laid along those cuts, then packed with the rest as a
          part that brings its own layout. Down the front every vertex is ONE place on the map, down the back TWO
  sculpt  a sculpted ball cut down its back half (x near 0, z > 0): its faces leave the sculpt charts and are laid
          along that cut - the build says "placed seams: Ball" and passes seam_placed
  thin    the same ball cut along a line too thin for its voxels (scattered edges, no connected cut): the unwrap
          cannot open them - seam_placed must FAIL there too
  mixed   a sculpted ball AND a kit-made strap (a ring) with its seam placed, in one group: the ball keeps its sculpt
          charts, the strap is laid along its cut and packed APART from the charts (review 2026-11-17: they lay on
          them) - seam_placed and uv_overlap pass, the charts are said
  twins   two identical rods on the high-and-low route, seams placed on the second only: it keeps its own cuts,
          never stacked under its twin's automatic strips (review 2026-11-17)
Prints SEAMS {...}. Used by kit/test/python/test_seam_routes_build.py. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((h for h in ("thin", "sculpt", "mixed", "twins") if h in ARGS), "low")

if HOW == "twins":
    a = rbx.Asset("_selftest_seamroute_twins", tex=256, size=(2.0, 3.0, 1.0), ground=True, low=4000)
    a.material("wood", (0.45, 0.3, 0.18), rough=0.7)
    a.cylinder("Rod1", 0.5, 3.0, (-0.6, 1.5, 0), "wood", axis="Y", segments=16, bevel=0)
    a.cylinder("Rod2", 0.5, 3.0, (0.6, 1.5, 0), "wood", axis="Y", segments=16, bevel=0)
    a.seams("Rod2", cut=lambda p, q: p[2] > 0.49 and q[2] > 0.49, sharp=60)
elif HOW == "mixed":
    a = rbx.Asset("_selftest_seamroute_mixed", tex=256, size=(1.6, 0.8, 0.8), ground=False)
    a.material("paint", (0.6, 0.55, 0.5), rough=0.6)
    s = a.sculpt("Ball", "paint", voxel_mm=4.0)
    s.ball((0, 0, 0), 0.4 * 280.0)
    s.done(adaptivity=0.0, tris=4000)
    a.cylinder("Strap", 0.2, 0.6, (0.6, 0.0, 0.0), "paint", axis="Y", segments=16, bevel=0)
    a.seams("Strap", cut=lambda p, q: p[2] > 0.19 and q[2] > 0.19, sharp=60)
elif HOW == "low":
    a = rbx.Asset("_selftest_seamroute_low", tex=256, size=(1.0, 3.0, 1.0), ground=True, low=2000)
    a.material("wood", (0.45, 0.3, 0.18), rough=0.7)
    a.cylinder("Handle", 0.5, 3.0, (0, 1.5, 0), "wood", axis="Y", segments=16, bevel=0)   # (its surface its own high)
    a.seams("Handle", cut=lambda p, q: p[2] > 0.49 and q[2] > 0.49, sharp=60)
else:
    a = rbx.Asset(f"_selftest_seamroute_{HOW}", tex=256, size=(0.8, 0.8, 0.8), ground=False)
    a.material("paint", (0.6, 0.55, 0.5), rough=0.6)
    s = a.sculpt("Ball", "paint", voxel_mm=4.0)
    s.ball((0, 0, 0), 0.4 * 280.0)
    s.done(adaptivity=0.0, tris=4000)
    w = 0.008 if HOW == "thin" else 0.03
    a.seams("Ball", cut=lambda p, q: abs(p[0]) < w and abs(q[0]) < w and p[2] > 0.0 and q[2] > 0.0)
a.build()

obj = bpy.data.objects[a.name]
back = rbx.BL_FROM_RBX.inverted() @ obj.matrix_world
uv = obj.data.uv_layers.active.data
out = {"how": HOW}
if HOW == "low":
    places = {"front": {}, "back": {}}
    for poly in obj.data.polygons:
        if abs((back.to_3x3() @ poly.normal)[1]) > 0.5:
            continue                                      # (a cap)
        for li in poly.loop_indices:
            p = back @ obj.data.vertices[obj.data.loops[li].vertex_index].co
            side = "front" if p[2] < -0.49 else "back" if p[2] > 0.49 else None
            if side:
                places[side].setdefault(round(p[1], 3), set()).add((round(uv[li].uv[0], 4), round(uv[li].uv[1], 4)))
    out.update({k: sorted(len(v) for v in d.values()) for k, d in places.items()})
print("SEAMS " + json.dumps(out))
