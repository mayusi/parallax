"""build_ornament.py — fixture for ORNAMENT AS RELIEF (H4, a.ornament): a steel plate. By the word after `--`:
  good   two ornaments on its front: an .svg crest with a round hole (kit/selftest/blender/ornament_crest.svg),
         raised with a round edge, and a .png scroll (ornament_scroll.png, dark strokes on light paper) engraved
         with a V cut - both read in the normal map, the hole left flat, the engraving darkened in the colour
  none   the same plate with no ornament (what flat reads as)
  fine   the scroll shrunk to 2 cm: its strokes are under 2.5 texels of the plate's 128 map - the build says so
         (facts.stamps_too_fine, the stamp_texels warning)
  wrap   a steel CYLINDER (radius 0.3, up Y) with the scroll WRAPPED round it (around=("Y", ...)): 0.8 studs of arc,
         about 153 degrees centred on its front - it reads all the way round that arc, not past it
  flat   the same cylinder with the same scroll projected flat from the front (what wrapping is for: the flat
         projection is 0.8 wide on a 0.6 wide cylinder - it falls off the sides)
  stitch the plate with a SEWN SEAM along a half circle (a.stitch_line, card maah): the normal map turns along the
         arc and not beside it (`STITCH {json}`: the bent share on the arc, beside it, and on the plain plate)
After the build `ORN {json}`: over the plate's front, the share of texels whose baked normal turns more than 10
degrees from flat - in the crest's box, in its hole, in the scroll's box - and the colour's darkening in the scroll.
Used by kit/test/python/test_ornament.py. Never "fix" this file."""

import json
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
HOW = next((w for w in ("none", "fine", "wrap", "flat", "stitch") if w in ARGS), "good")
HERE = "kit/selftest/blender"
TEX = 128 if HOW == "fine" else 512

if HOW in ("wrap", "flat"):
    a = rbx.Asset("_selftest_ornament_" + HOW, tex=1024, size=(0.6, 0.6, 0.6), ground=False, edge_wear=0.0, ao=0.0)
    a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.35)
    a.cylinder("Drum", 0.3, 0.6, (0, 0, 0), "steel", axis="Y", segments=64)
    a.ornament(f"{HERE}/ornament_scroll.png", at=(0, 0, -0.3), width=0.8, facing="-Z", depth_mm=3.0, profile="v",
               edge_mm=4.0, around=("Y", (0, 0, 0)) if HOW == "wrap" else None)
    a.build()
    obj = next(o for o in bpy.data.objects if o.type == "MESH")
    import mathutils  # noqa: E402
    me = obj.data
    me.calc_loop_triangles()
    img = bpy.data.images.load(os.path.join(rbx.TEXTURES, f"{obj.name}_normal.png"), check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    N = img.size[0]
    px = np.empty(N * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(img.size[1], N, 4)
    tris_ = list(me.loop_triangles)
    bvh = mathutils.bvhtree.BVHTree.FromPolygons([v.co for v in me.vertices], [tuple(tr.vertices) for tr in tris_])
    uv = me.uv_layers.active.data
    to_bl = obj.matrix_world.inverted() @ rbx.BL_FROM_RBX
    bins = {}
    for deg in range(-120, 121, 10):   # (0 = the front, -Z; + toward the model's -X: the picture's right seen there)
        t = np.radians(deg)
        hits = []
        for y in np.linspace(-0.15, 0.15, 25):
            for dt in np.linspace(-0.08, 0.08, 9):
                out = np.array([-np.sin(t + dt), 0.0, -np.cos(t + dt)])
                o_ = to_bl @ mathutils.Vector((out * 1.0) + np.array([0, y, 0]))
                d_ = (to_bl.to_3x3() @ mathutils.Vector(-out)).normalized()
                loc, _n, idx, _d = bvh.ray_cast(o_, d_)
                if loc is None:
                    continue
                tri = tris_[idx]
                vs = [me.vertices[v].co for v in tri.vertices]
                uvs = [uv[li].uv.to_3d() for li in tri.loops]
                u, v_, _ = mathutils.geometry.barycentric_transform(loc, *vs, *uvs)
                b = px[min(N - 1, int(v_ * N)), min(N - 1, int(u * N)), 2] * 2 - 1
                hits.append(np.degrees(np.arccos(np.clip(b, -1, 1))) > 10)
        bins[deg] = round(float(np.mean(hits)), 3) if hits else None
    print("ORNWRAP " + json.dumps(bins))
    sys.exit(0)

a = rbx.Asset("_selftest_ornament_" + HOW, tex=TEX, size=(2.0, 1.2, 0.2), ground=False, edge_wear=0.0, ao=0.0)
a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.35)
a.box("Plate", (2.0, 1.2, 0.2), (0, 0, 0), "steel", bevel=0)
CREST = {"at": (-0.5, 0.0, -0.1), "height": 0.8}
SCROLL = {"at": (0.5, 0.0, -0.1), "width": 0.8}
if HOW == "good":
    a.ornament(f"{HERE}/ornament_crest.svg", at=CREST["at"], height=CREST["height"], facing="-Z", depth_mm=4.0,
               profile="round", edge_mm=6.0)
    a.ornament(f"{HERE}/ornament_scroll.png", at=SCROLL["at"], width=SCROLL["width"], facing="-Z", depth_mm=3.0,
               profile="v", cut=True, edge_mm=4.0)
elif HOW == "stitch":
    import math  # noqa: E402

    arc = [(0.5 * math.cos(t), 0.5 * math.sin(t) - 0.2, -0.1) for t in [math.pi * k / 24 for k in range(25)]]
    a.stitch_line(arc, facing="-Z", thread_mm=2.0, pitch_mm=8.0)
elif HOW == "fine":
    a.ornament(f"{HERE}/ornament_scroll.png", at=SCROLL["at"], width=0.07, facing="-Z", depth_mm=0.5)
a.build()


def front_maps():
    """the plate's baked normal and colour over its FRONT face (-Z): (normal (h, w, 3), colour (h, w, 3)) sampled
    on a grid across the face through its UVs, row 0 the top, column 0 the model's +X side seen from the front"""
    obj = next(o for o in bpy.data.objects if o.type == "MESH")
    me = obj.data
    uv = me.uv_layers.active.data
    to_rbx = rbx.BL_FROM_RBX.inverted()
    face = max((p for p in me.polygons if (to_rbx.to_3x3() @ (obj.matrix_world.to_3x3() @ p.normal)).z < -0.9),
               key=lambda p: p.area)
    corners = [(to_rbx @ (obj.matrix_world @ me.vertices[me.loops[li].vertex_index].co), uv[li].uv.copy())
               for li in face.loop_indices]
    maps = {}
    for ch in ("normal", "color"):
        img = bpy.data.images.load(os.path.join(rbx.TEXTURES, f"{obj.name}_{ch}.png"), check_existing=False)
        img.colorspace_settings.name = "Non-Color"
        n = img.size[0]
        px = np.empty(n * img.size[1] * 4, np.float32)
        img.pixels.foreach_get(px)
        maps[ch] = px.reshape(img.size[1], n, 4)
        bpy.data.images.remove(img)
    # the face's UV as a bilinear map of its four corners (x, y in the model's frame)
    pts = np.array([[p.x, p.y] for p, _u in corners])
    uvs = np.array([[u.x, u.y] for _p, u in corners])
    xs, ys = np.linspace(pts[:, 0].max() - 0.01, pts[:, 0].min() + 0.01, 200), np.linspace(0.59, -0.59, 120)
    X, Y = np.meshgrid(xs, ys)
    # (an axis-aligned rectangle: u, v vary linearly in x and y - solved from the corners by least squares)
    A = np.c_[pts, np.ones(len(pts))]
    cu, cv = np.linalg.lstsq(A, uvs[:, 0], rcond=None)[0], np.linalg.lstsq(A, uvs[:, 1], rcond=None)[0]
    U = cu[0] * X + cu[1] * Y + cu[2]
    V = cv[0] * X + cv[1] * Y + cv[2]
    out = []
    for ch in ("normal", "color"):
        m = maps[ch]
        H, W = m.shape[:2]
        out.append(m[np.clip((V * H).astype(int), 0, H - 1), np.clip((U * W).astype(int), 0, W - 1), :3])
    return X, Y, out[0], out[1]


X, Y, nrm, col = front_maps()
bent = np.degrees(np.arccos(np.clip((nrm[..., 2] * 2 - 1), -1, 1))) > 10   # (tangent space: blue = straight out)


def share(mask):
    return round(float(bent[mask].mean()), 4) if mask.any() else None


crest = (np.abs(X - CREST["at"][0]) < 0.3) & (np.abs(Y) < 0.38)
hole = np.hypot(X - CREST["at"][0], Y - (0.4 - 70 / 240 * 0.8)) < 0.06   # (the svg's hole: centre (100, 70) of 200 x 240)
scroll = (np.abs(X - SCROLL["at"][0]) < 0.38) & (np.abs(Y) < 0.18)
plain = (np.abs(X) < 0.05) & (np.abs(Y) < 0.5)
# which way up: the hole's rim (radius 30 of 240 -> 0.1 stud) bends the normal where the drawing puts it (its centre
# 70 of 240 from the TOP), not at the same place mirrored top to bottom
r_ = np.hypot(X - CREST["at"][0], Y - (0.4 - 70 / 240 * 0.8))
r_flip = np.hypot(X - CREST["at"][0], Y + (0.4 - 70 / 240 * 0.8))
if HOW == "stitch":
    import math  # noqa: E402
    r_ = np.hypot(X, Y + 0.2)
    up_ = Y + 0.2 > 0.02
    print("STITCH " + json.dumps({"on_arc": share(up_ & (np.abs(r_ - 0.5) < 0.008)),
                                  "beside": share(up_ & (np.abs(r_ - 0.5) > 0.04) & (np.abs(r_ - 0.5) < 0.08)),
                                  "plain": share(plain)}))
    sys.exit(0)
print("ORN " + json.dumps({"crest": share(crest), "hole": share(hole), "scroll": share(scroll), "plain": share(plain),
                           "rim_up": share((r_ > 0.08) & (r_ < 0.12)), "rim_flipped": share((r_flip > 0.08) & (r_flip < 0.12)),
                           # the scroll's LEFT spiral (x 90 of 320) arcs above its stem: seen from the front the
                           # picture's left is the model's +X (0.5 + 0.8 * 70 / 320), its right the model's -X
                           "spiral_left_above": share((np.abs(X - (0.5 + 0.8 * 70 / 320)) < 0.12) & (Y > 0.03) & (Y < 0.13)),
                           "spiral_left_below": share((np.abs(X - (0.5 + 0.8 * 70 / 320)) < 0.12) & (Y < -0.03) & (Y > -0.13)),
                           "scroll_dark": round(float(col[scroll].mean() / max(col[plain].mean(), 1e-6)), 4)}))
