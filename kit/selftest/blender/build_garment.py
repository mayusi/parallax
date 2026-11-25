"""build_garment.py — fixture: rbx_garment (a sleeve DRAPED by Blender's cloth simulation on an R6 arm, its slack
pulled up into folds, then given a wall and a lining). kit/test/python/test_garment.py reads
build/models/_selftest_garment.check.json. Never "fix" this file."""

import json
import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bmesh  # noqa: E402
import rbx  # noqa: E402
import rbx_garment as G  # noqa: E402

a = rbx.Asset("_selftest_garment", tex=256, size=(1.2, 2.2, 1.2))
a.real_scale(280.0)
a.material("cloth", **rbx.look("cloth", color=(0.4, 0.02, 0.02)))
a.material("lining", **rbx.look("cloth", color=(0.05, 0.01, 0.01)))
a.box("Arm", (1, 2, 1), (0, 1, 0), "cloth")
G.tube(a, "Sleeve", "cloth", centre=(0, 0, 0), half=(0.585, 0.585), y_top=2.05, y_bottom=0.6, slack=1.4, p=4.0)
facts = G.drape(a, "Sleeve", colliders=["Arm"], pull_end=True, end_y=0.6, bending=0.8)
G.finish(a, "Sleeve", thickness_mm=9, lining="lining")


def rbx_verts(name):
    o = G._part(a, name)
    return [G._rbx(o, v.co) for v in o.data.vertices], o


sv, so = rbx_verts("Sleeve")
lv, _lo = rbx_verts("SleeveLining")
radii = [math.hypot(v.x, v.z) for v in sv]
bm = bmesh.new()
bm.from_mesh(so.data)
check = {
    "drape": facts,
    "y": [min(v.y for v in sv), max(v.y for v in sv)],
    "radius_max": max(radii),
    "radius_spread": max(radii) - min(radii),
    "lining_radius_max": max(math.hypot(v.x, v.z) for v in lv),
    "non_manifold": sum(1 for e in bm.edges if not e.is_manifold),
    "parts": sorted(o.name for o, _g in a.parts),
    "coverage": G.coverage(a, {"main": "Arm"})[0]["main"],
}
bm.free()
os.makedirs(os.path.join(_root, "build", "models"), exist_ok=True)
with open(os.path.join(_root, "build", "models", "_selftest_garment.check.json"), "w", encoding="utf-8") as fh:
    json.dump(check, fh, indent=1)
