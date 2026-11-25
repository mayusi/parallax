"""build_copies.py — fixture for WHAT A PART'S COPIES TAKE FROM IT (card nrey: the repeat stage's review): parts made
inside `with a.mirror("X"):` - the part at +X, its copy at -X. By the word after `--`:
  fuse      a Body and a Boss pressed into it, both mirrored, then a.fuse("Body", "Boss"): each Body takes the Boss
            beside it (the copy its copy) - not both Bosses in the one at +X, the one at -X left bare
  displace  a Plate, mirrored, with a picture's detail pressed into it at +X (a bump in the picture's LEFT half
            only): the copy carries the same detail, mirrored - not nothing (it read the picture where it stands)
  texel     the high-and-low route: a Wheel, mirrored, given a.texel("Wheel", 2): the copy's islands as dense as the
            part's (twice a plain Block's) - not the plain density
After the build `COPIES {json}`: for fuse each Body's face count and volume and whether a Boss is left; for
displace each Plate's vertices moved off its flat face (count, deepest mm) and whether the copy's moved points are
the part's mirrored; for texel the measured texels per mm of the Wheel, its copy and the Block.
Used by kit/test/python/test_copies.py. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((w for w in ("displace", "texel") if w in ARGS), "fuse")
out = {}


def volume(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    v = bm.calc_volume(signed=False)
    bm.free()
    return round(v * float(o.matrix_world.to_3x3().determinant()) ** 0, 6)


def kit_points(o):
    to = rbx.BL_FROM_RBX.inverted() @ o.matrix_world
    return np.array([tuple(to @ v.co) for v in o.data.vertices])


if HOW == "fuse":
    a = rbx.Asset("_selftest_copies_fuse", tex=64, size=(2.4, 0.6, 0.6), ground=False, allow_floating=("Body",))
    a.material("iron", color=(0.4, 0.4, 0.42), metal=1.0, rough=0.5)
    with a.mirror("X"):
        a.box("Body", (0.8, 0.5, 0.5), (0.8, 0.0, 0.0), "iron", bevel=0)
        a.box("Boss", (0.3, 0.3, 0.3), (0.8, 0.3, 0.0), "iron", bevel=0)
    a.fuse("Body", "Boss", radius=0.0)
    objs = {o.name: o for o in bpy.data.objects if o.type == "MESH"}
    bodies = sorted(n for n in objs if n.startswith("Body"))
    out = {"bodies": {n: {"faces": len(objs[n].data.polygons), "volume": volume(objs[n])} for n in bodies},
           "boss_left": sorted(n for n in objs if n.startswith("Boss"))}
    a.build()
elif HOW == "displace":
    n, r = 64, 14.0
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    height = np.exp(-(((xx - 16) ** 2 + (yy - 32) ** 2) / r ** 2))   # (one bump, in the picture's left half)
    path = os.path.join(rbx.BUILD, "selftest", "_selftest_copies_bump.npz")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, height=height.astype(np.float32), mask=np.ones((n, n), bool))
    a = rbx.Asset("_selftest_copies_displace", tex=64, size=(2.4, 0.8, 0.2), ground=False,
                  allow_floating=("Plate",))
    a.material("clay", color=(0.6, 0.5, 0.4), rough=0.8)
    with a.mirror("X"):
        a.box("Plate", (0.8, 0.8, 0.1), (0.8, 0.0, 0.0), "clay", bevel=0)
    plain = {o.name: kit_points(o) for o in bpy.data.objects if o.type == "MESH"}
    a.displace("Plate", path, 0.05, width=0.8, pos=(0.8, 0.0, 0.05), detail_px=8.0, level=3, smooth=0.0)
    res = {}
    pts = {}
    for o in sorted((o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Plate")),
                    key=lambda o: o.name):
        p = kit_points(o)
        front = p[:, 2] > 0.04   # (the face toward +Z the picture looks at)
        moved = front & (np.abs(p[:, 2] - 0.05) > 1e-4)
        res[o.name] = {"moved": int(moved.sum()), "deepest_mm": round(float(np.abs(p[moved, 2] - 0.05).max() * 280.0)
                                                                   if moved.any() else 0.0, 3)}
        pts[o.name] = p[moved]
    names = sorted(pts)
    if len(names) == 2 and len(pts[names[0]]) and len(pts[names[1]]):
        a_, b_ = pts[names[0]], pts[names[1]] * np.array([-1.0, 1.0, 1.0])
        d = np.min(np.linalg.norm(a_[:, None, :] - b_[None, :, :], axis=2), axis=1)
        res["mirrored_max_mm"] = round(float(d.max() * 280.0), 4)
    out = res
    a.build()
else:
    a = rbx.Asset("_selftest_copies_texel", tex=256, size=(2.4, 0.6, 0.6), ground=False, low=True,
                  allow_floating=("Wheel", "Block"))
    a.material("rubber", color=(0.1, 0.1, 0.1), rough=0.9)
    with a.mirror("X"):
        a.cylinder("Wheel", 0.25, 0.2, (0.8, 0.0, 0.0), "rubber", axis="X", segments=24, bevel=0)
    a.box("Block", (0.5, 0.5, 0.5), (0.0, 0.0, 0.0), "rubber", bevel=0)
    a.texel("Wheel", 2.0)
    a.build()
    out = {"texel": "read facts.uv_parts from the build's status line"}
print("COPIES " + json.dumps(out))
