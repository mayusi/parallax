"""build_pattern3.py — fixture for PATTERNS ON THE MODEL (H6 / S3: rbx_wear.pattern3, rbx_layers "radial"): four
parts, each its own group (its own map), facing the front (-Z):
  Disc    a turned face: pattern="lathe" round its own axis (Z through its centre), a ring every 1.5 mm
  Panel   car paint: pattern="flake", a flake every 1.2 mm (each pitch 4+ texels of its map: resolved)
  Brush   brushed steel: pattern="brushed" with pattern_axis="X" - its streaks run along X on the model
  Hub     a plate under brake dust: a soot layer where="radial" round Z - most at its centre, none at its rim
After the build `PAT3 {json}`: the patterns' facts (facts.patterns) and, read off each baked map through its UVs on
the front face: the Disc's normal turning (degrees) round rings vs along them, the Brush's normal change along X vs
along Y, the Panel's normal spread, and the Hub's colour from its centre outward (darker in the middle).
Used by kit/test/python/test_pattern3.py. Never "fix" this file."""

import json
import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import mathutils  # noqa: E402
import numpy as np  # noqa: E402
import rbx  # noqa: E402

MM = 280.0
a = rbx.Asset("_selftest_pattern3", tex=1024, size=(2.3, 0.6, 0.08), ground=False, edge_wear=0.0, ao=0.0,
              allow_floating=("Panel", "Brush", "Hub"))
DISC_C = (-0.85, 0.0, 0.0)
a.material("turned", color=(0.6, 0.6, 0.62), metal=1.0, rough=0.3, pattern="lathe", pattern_mm=1.5,
           pattern_axis=("Z", tuple(c * MM for c in DISC_C)))
a.material("paint", color=(0.5, 0.05, 0.05), metal=0.3, rough=0.35, pattern="flake", pattern_mm=1.2)
a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.35, pattern="brushed", pattern_mm=1.2,
           pattern_axis="X")
a.material("hub", color=(0.7, 0.7, 0.72), metal=1.0, rough=0.4,
           layers=[rbx.layer("soot", where="radial", amount=0.6, opacity=0.55, breakup=0.45,
                             axis=("Z", (0.85 * MM, 0.0, 0.0)))])
a.cylinder("Disc", 0.28, 0.06, DISC_C, "turned", axis="Z", segments=64, bevel=0, group="disc")
a.box("Panel", (0.5, 0.5, 0.06), (-0.28, 0, 0), "paint", bevel=0, group="panel")
a.box("Brush", (0.5, 0.5, 0.06), (0.28, 0, 0), "steel", bevel=0, group="brush")
a.cylinder("Hub", 0.28, 0.06, (0.85, 0, 0), "hub", axis="Z", segments=64, bevel=0, group="hub")
for g in ("disc", "panel", "brush", "hub"):
    a.group_texture(g, 1024)
a.build()


def front(part_prefix):
    """(sample(x, y) -> the baked normal (3,) and colour (3,) at that point of the part's FRONT face (studs, the
    model's frame), via a ray from the front and its triangle's UVs"""
    obj = next(o for o in bpy.data.objects if o.type == "MESH" and part_prefix in o.name and not o.hide_render)
    me = obj.data
    me.calc_loop_triangles()
    tris = list(me.loop_triangles)
    bvh = mathutils.bvhtree.BVHTree.FromPolygons([v.co for v in me.vertices], [tuple(t.vertices) for t in tris])
    to_bl = obj.matrix_world.inverted() @ rbx.BL_FROM_RBX
    uv = me.uv_layers.active.data
    maps = {}
    for ch in ("normal", "color"):
        img = bpy.data.images.load(os.path.join(rbx.TEXTURES, f"{obj.name}_{ch}.png"), check_existing=False)
        img.colorspace_settings.name = "Non-Color"
        n = img.size[0]
        px = np.empty(n * img.size[1] * 4, np.float32)
        img.pixels.foreach_get(px)
        maps[ch] = px.reshape(img.size[1], n, 4)
        bpy.data.images.remove(img)

    def sample(x, y):
        o_ = to_bl @ mathutils.Vector((x, y, -1.0))
        d_ = (to_bl.to_3x3() @ mathutils.Vector((0, 0, 1))).normalized()
        loc, _n, idx, _d = bvh.ray_cast(o_, d_)
        if loc is None:
            return None
        t = tris[idx]
        u, v, _ = mathutils.geometry.barycentric_transform(loc, *[me.vertices[i].co for i in t.vertices],
                                                           *[uv[li].uv.to_3d() for li in t.loops])
        out = []
        for ch in ("normal", "color"):
            m = maps[ch]
            out.append(m[min(m.shape[0] - 1, int(v * m.shape[0])), min(m.shape[1] - 1, int(u * m.shape[1])), :3])
        return out
    return sample


def turning(sample, pts):
    ns = [sample(x, y) for x, y in pts]
    ns = [np.array(n[0]) * 2 - 1 for n in ns if n is not None]
    return float(np.mean([math.degrees(math.acos(np.clip(np.dot(a_ / np.linalg.norm(a_), b_ / np.linalg.norm(b_)), -1, 1)))
                          for a_, b_ in zip(ns, ns[1:])]))


out = {}
disc = front("disc")
step = 0.375 / MM   # 0.375 mm steps: a quarter of a ring
cx, cy = DISC_C[0], DISC_C[1]
out["disc_across_rings_deg"] = round(turning(disc, [(cx + 0.15 + k * step, cy) for k in range(60)]), 3)
out["disc_along_ring_deg"] = round(turning(disc, [(cx + 0.15 * math.cos(k * 0.0015), cy + 0.15 * math.sin(k * 0.0015))
                                                  for k in range(60)]), 3)
brush = front("brush")
out["brush_along_x_deg"] = round(turning(brush, [(0.2 + k * step, 0.05) for k in range(60)]), 3)
out["brush_along_y_deg"] = round(turning(brush, [(0.28, 0.05 + k * step) for k in range(60)]), 3)
panel = front("panel")
ns = [panel(-0.28 + k * step * 2, 0.02) for k in range(80)]
ns = [np.array(n[0]) * 2 - 1 for n in ns if n is not None]
out["flake_spread_deg"] = round(float(np.std([math.degrees(math.atan2(n[0], n[2])) for n in ns])), 3)
hub = front("hub")
lum = [float(np.dot(hub(0.85 + r, 0.0)[1], [0.2126, 0.7152, 0.0722])) for r in (0.02, 0.1, 0.18, 0.26)]
out["hub_lum_out"] = [round(v_, 4) for v_ in lum]
print("PAT3 " + json.dumps(out))
