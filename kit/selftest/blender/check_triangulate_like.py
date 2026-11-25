"""rbx_uvparts.triangulate_like: a turned copy's n-gon is cut along its ORIGINAL's diagonals. A hexagon and its copy
turned 72 degrees, the copy's face started at each of its six corners: BEAUTY alone cuts some of them otherwise (the
car rim's Spoke2 - corners laid from other islands, a striped blotch, rework 6ebz); triangulate_like cuts every one
alike. Prints one line TRI_LIKE {json}. Run by kit/test/python/test_uvparts_blender.py."""
import json
import math
import os
import sys

import bmesh
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_uvparts as U  # noqa: E402


def build(start):
    bm = bmesh.new()
    kp = bm.faces.layers.int.new("kit_part")
    ring = [(math.cos(math.radians(60 * k)), 0.7 * math.sin(math.radians(60 * k)), 0.0) for k in range(6)]
    va = [bm.verts.new(p) for p in ring]
    a = math.radians(72)
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    vb = [bm.verts.new((rz @ np.array(p) + [3, 0, 0]).tolist()) for p in ring]
    fa = bm.faces.new(va)
    fa[kp] = 0
    fb = bm.faces.new(vb[start:] + vb[:start])
    fb[kp] = 1
    bm.verts.index_update()
    bm.faces.index_update()
    return bm, kp


def tris(bm, kp, part):
    """a part's triangles by its own corners (0-5)"""
    return sorted(tuple(sorted(v.index % 6 for v in f.verts)) for f in bm.faces if f[kp] == part)


out = {"beauty_alike": [], "like_alike": [], "failed": [], "faces": [], "copies": []}
for start in range(6):
    bm, kp = build(start)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
    out["beauty_alike"].append(tris(bm, kp, 0) == tris(bm, kp, 1))
    bm.free()
    bm, kp = build(start)
    co = np.array([v.co[:] for v in bm.verts])
    dup = U.copies(co, [tuple(v.index for v in f.verts) for f in bm.faces], [f[kp] for f in bm.faces])
    out["copies"].append({str(k): v for k, v in dup.items()})
    failed = U.triangulate_like(bm, dup, kp)
    kp = bm.faces.layers.int.get("kit_part")
    out["like_alike"].append(tris(bm, kp, 0) == tris(bm, kp, 1))
    out["failed"].append(sorted(failed))
    out["faces"].append(len(bm.faces))
    bm.free()
print("TRI_LIKE " + json.dumps(out))
