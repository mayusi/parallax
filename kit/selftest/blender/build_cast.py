"""build_cast.py — fixture for CAST AS ONE PIECE (S4, a.cast): a round post standing on a plate, poured as one with
an 8 mm fillet where they meet. By the word after `--`:
  geo    the cast REPLACES the parts (no high-and-low route): one part, its fillet real geometry
  apart  the post hovers 14 mm over the plate: no fillet can form - cast_fillet fails the build by name
  low    Asset(low=True), parts made in Blender (the distance-field route): the game mesh is the cast reduced to
         its budget, the full cast its bake source
  cad    the plate and post made by a.cad: the CAD route - fused in OpenCASCADE, only their junction filleted
  cadlow the same with Asset(low=True): the cast an a.cad part on the high-and-low route (its low the kit's own)
  grain  geo with a sand-cast skin (grain_mm=4, 0.4 mm deep): the post's radius varies round it, the plain one does not
After the build `CAST {json}`: the casts' facts (design.casts) and, for geo / cad / grain, the cast's radius round
the post's axis
(mm) at heights over the plate's top - wider low down (the fillet), the post's own radius higher up - its spread
round the post 60 mm up (the grain), and how near a vertex lies to the plate's outer corner (kept sharp).
Used by kit/test/python/test_cast.py. Never "fix" this file."""

import json
import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((w for w in ("apart", "cadlow", "low", "cad", "grain") if w in ARGS), "geo")
MM = 280.0
R, PLATE_TOP = 0.06, 0.06   # studs: the post's radius, the plate's top

a = rbx.Asset("_selftest_cast_" + HOW, tex=256, size=(0.4, 0.46, 0.4), ground=True,
              allow_floating=("Post",) if HOW == "apart" else (), **({"low": True} if HOW in ("low", "cadlow") else {}))
a.material("iron", color=(0.3, 0.3, 0.32), metal=1.0, rough=0.6)
gap = 0.05 if HOW == "apart" else -0.01
if HOW in ("cad", "cadlow"):   # (the CAD code in mm, the kit's axes; the post placed by a.cad's own pos=)
    a.cad("Plate", f"part = Pos(0, {PLATE_TOP * MM / 2}, 0) * Box({0.4 * MM}, {PLATE_TOP * MM}, {0.4 * MM})\n",
          "iron", group="cast")
    a.cad("Post", f"part = Cylinder({R * MM}, {0.4 * MM}, rotation=(90, 0, 0))\n", "iron",
          pos=(0, PLATE_TOP + gap + 0.2, 0), group="cast")
else:
    a.box("Plate", (0.4, PLATE_TOP, 0.4), (0, PLATE_TOP / 2, 0), "iron", bevel=0, group="cast")
    a.cylinder("Post", R, 0.4, (0, PLATE_TOP + gap + 0.2, 0), "iron", axis="Y", segments=48, bevel=0, group="cast")
a.cast("Casting", ["Plate", "Post"], "iron", fillet_mm=8.0, **({"grain_mm": 4.0, "grain_amp_mm": 0.4} if HOW == "grain" else {}))
a.build()

import bpy  # noqa: E402
import mathutils  # noqa: E402

out = {"casts": a.design.get("casts")}
if HOW in ("geo", "cad", "grain"):
    obj = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("_selftest_cast"))
    me = obj.data
    me.calc_loop_triangles()
    tris_ = list(me.loop_triangles)
    to_bl = obj.matrix_world.inverted() @ rbx.BL_FROM_RBX
    bvh = mathutils.bvhtree.BVHTree.FromPolygons([v.co for v in me.vertices], [tuple(t.vertices) for t in tris_])
    radius = {}
    for h_mm in (1.0, 2.0, 4.0, 8.0, 20.0, 60.0):
        y = PLATE_TOP + h_mm / MM
        rs = []
        for k in range(8):   # from outside toward the axis, round it
            t = 2 * math.pi * k / 8
            o_ = to_bl @ mathutils.Vector((0.3 * math.cos(t), y, 0.3 * math.sin(t)))
            d_ = (to_bl.to_3x3() @ mathutils.Vector((-math.cos(t), 0, -math.sin(t)))).normalized()
            loc, _n, _i, dist = bvh.ray_cast(o_, d_)
            if loc is not None:
                rs.append((0.3 - dist / to_bl.to_3x3().median_scale) * MM)
        radius[str(h_mm)] = round(sum(rs) / len(rs), 2) if rs else None
        if h_mm == 60.0:
            out["spread_mm"] = round(max(rs) - min(rs), 3) if rs else None   # (round the post: the grain's relief)
    out["radius_mm"] = radius
    corner = to_bl @ mathutils.Vector((0.2, PLATE_TOP, 0.2))
    near = min((v.co - corner).length for v in me.vertices) / to_bl.to_3x3().median_scale * MM
    out["corner_mm"] = round(near, 3)
print("CAST " + json.dumps(out))
