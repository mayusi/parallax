"""build_noise3.py — fixture for NOISE IN THE MODEL'S OWN SPACE (H6, Asset(noise_3d=)): a sculpted ball (smooth
everywhere, unwrapped into many islands) under a soot layer the noise alone places over half of it (a patchwork of
two tones). By the word after `--`:
  on    noise_3d=True: the bake's noise fields at each texel's place on the model
  off   noise_3d=False: across the map (as every piece built before 2026-11-17 bakes)
After the build `NOISE3 {json}`: the baked colour's mean jump (0..255) across UV SEAMS that lie on a smooth surface
(two faces turned within 10 degrees of each other, cut apart in the map) and across the same kind of edge NOT cut
(the field's own change over that distance) - with the field on the model the two are alike; across the map the
seams jump. Used by kit/test/python/test_noise3.py. Never "fix" this file."""

import json
import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ON = "off" not in ARGS

a = rbx.Asset("_selftest_noise3_" + ("on" if ON else "off"), tex=512, size=(0.8, 0.8, 0.8), ground=False,
              noise_3d=ON, spec_occlusion=0.0, edge_wear=0.0, ao=0.0)
a.material("paint", color=(0.55, 0.5, 0.42), rough=0.5,
           layers=[rbx.layer("soot", where="all", amount=0.5, opacity=1.0, breakup=1.0)])
s = a.sculpt("Ball", "paint", voxel_mm=2.0)
s.ball((0, 0, 0), 0.4 * 280.0)
s.done(adaptivity=0.0, tris=15000)   # (under the 20,000 a game mesh may have)
a.build()

obj = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("_selftest_noise3"))
me = obj.data
uv = me.uv_layers.active.data
img = bpy.data.images.load(os.path.join(rbx.TEXTURES, f"{obj.name}_color.png"), check_existing=False)
N = img.size[0]
px = np.empty(N * img.size[1] * 4, np.float32)
img.pixels.foreach_get(px)
px = px.reshape(img.size[1], N, 4)


def lum(u, v):
    c = px[min(N - 1, max(0, int(v * N))), min(N - 1, max(0, int(u * N))), :3]
    return float(c @ np.array([0.2126, 0.7152, 0.0722])) * 255.0


faces_of = {}
for poly in me.polygons:
    for li, vi in zip(poly.loop_indices, poly.vertices):
        faces_of.setdefault(vi, []).append((poly.index, li))
seam, plain = [], []
for e in me.edges:
    a_, b_ = e.vertices
    fa = {f for f, _l in faces_of[a_]}
    shared = [f for f in {f for f, _l in faces_of[b_]} if f in fa]
    if len(shared) != 2:
        continue
    p0, p1 = (me.polygons[f] for f in shared)
    if p0.normal.angle(p1.normal) > math.radians(10):
        continue
    uvs = []
    for p in (p0, p1):
        at = {vi: uv[li].uv.copy() for li, vi in zip(p.loop_indices, p.vertices)}
        centre = sum((uv[li].uv for li in p.loop_indices), uv[p.loop_indices[0]].uv * 0) / len(p.loop_indices)
        mid = (at[a_] + at[b_]) / 2
        step = (centre - mid)
        step = step / max(step.length, 1e-9) * (1.5 / N)    # 1.5 texels into the face from the edge's middle
        uvs.append((mid + step, at[a_], at[b_]))
    cut = (uvs[0][1] - uvs[1][1]).length > 1e-4 or (uvs[0][2] - uvs[1][2]).length > 1e-4
    jump = abs(lum(*uvs[0][0]) - lum(*uvs[1][0]))
    (seam if cut else plain).append(jump)
print("NOISE3 " + json.dumps({"seam_edges": len(seam), "plain_edges": len(plain),
                              "seam_jump": round(float(np.mean(seam)), 3) if seam else None,
                              "plain_jump": round(float(np.mean(plain)), 3) if plain else None}))
