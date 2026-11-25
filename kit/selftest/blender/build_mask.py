"""build_mask.py — POSITIVE fixture for A MASK THE AUTHOR PLACES (a.mask, rbx_mask; the 3D methods audit, S3): a
painted green block with two placed masks - a gold STRIPE round it by a rule on the point (1.0 < y < 1.5) and a
round rust STAIN on its front from a picture (a soft disc, drawn here into the build folder) - each named by a layer
of the paint (where="mask:..."). The build must lay each layer where its mask is and nowhere else, say how much of
the surface each mask is on ("masks: stain on ..., stripe on ..."), and with a.mesh_maps() write the mesh's own
curvature, occlusion and material-id maps and name them in the manifest. After the build one line `MASK {json}`
for kit/test/python/test_mask_build.py: the baked colour read at points of the surface (in the stripe, in the
stain, on plain paint, on the back). With `unplaced` after `--` a layer names a mask nobody placed
(build_mask_unplaced.py): the build must stop and say which. Used by `lune run kit selftest`. Never "fix" this
file."""

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

UNPLACED = "unplaced" in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else False

a = rbx.Asset("_selftest_mask_unplaced" if UNPLACED else "_selftest_mask", tex=256, size=(4.0, 3.0, 2.0),
              ground=True)
a.material("paint", color=(0.1, 0.4, 0.15), rough=0.6, layers=[
    rbx.layer("gold", color=(0.9, 0.7, 0.1), metal=1.0, rough=0.3, where="mask:stripe", amount=1.0, breakup=0.0),
    rbx.layer("rust", where="mask:stain", amount=1.0, breakup=0.0),
])
a.box("Block", (4.0, 3.0, 2.0), (0, 1.5, 0), "paint", bevel=0)
a.mask("stripe", keep=lambda p: 1.0 < p[1] < 1.5)
if UNPLACED:
    pass   # (the stain's layer names a mask nobody placed)
else:
    # a soft white disc on black, 128 x 128: the stain, looked at from the front and laid over the block's box
    side = 128
    yy, xx = np.mgrid[0:side, 0:side]
    r = np.sqrt((xx - 32.0) ** 2 + (yy - 32.0) ** 2)                      # centred in the picture's LOWER LEFT quarter
    disc = np.clip((24.0 - r) / 6.0, 0, 1)                                # (Blender's rows run bottom-up)
    px = np.ones((side, side, 4), np.float32)
    px[..., :3] = disc[..., None]
    pic = bpy.data.images.new("_selftest_mask_stain", side, side, alpha=False)
    pic.pixels.foreach_set(px.ravel())
    os.makedirs(rbx.RENDERS, exist_ok=True)
    pic.filepath_raw = os.path.join(rbx.RENDERS, "_selftest_mask_stain.png")
    pic.file_format = "PNG"
    pic.save()
    a.mask("stain", picture=pic.filepath_raw, view="front")
a.mesh_maps()
a.build()

# where the layers landed: the baked colour under points of the surface (the model's frame), through the UVs
manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
obj = bpy.data.objects[a.name]
color = manifest["groups"]["main"]["textures"]["color"]
img = bpy.data.images.load(color if os.path.isabs(color) else os.path.join(rbx.REPO, color), check_existing=False)
w, h = img.size
tex = np.empty(w * h * 4, np.float32)
img.pixels.foreach_get(tex)
tex = tex.reshape(h, w, 4)
back = rbx.BL_FROM_RBX.inverted() @ obj.matrix_world
uv = obj.data.uv_layers.active.data


def colour_at(point, facing):
    """the baked colour at a point of the surface on the face looking `facing` (the model's frame)"""
    best = None
    for poly in obj.data.polygons:
        n = back.to_3x3() @ poly.normal
        if n.dot(rbx.Vector(facing)) < 0.9:
            continue
        ps = [back @ obj.data.vertices[v].co for v in poly.vertices]
        us = [uv[li].uv for li in poly.loop_indices]
        # a box face is a quad (or two triangles of it): the point's place by its distances to the corners
        wts = np.array([1.0 / max((p - rbx.Vector(point)).length, 1e-6) ** 4 for p in ps])
        lo = [min(p[i] for p in ps) for i in range(3)]
        hi = [max(p[i] for p in ps) for i in range(3)]
        if not all(lo[i] - 1e-4 <= point[i] <= hi[i] + 1e-4 for i in range(3)):
            continue
        # bilinear on an axis-aligned quad: solve by the two in-plane axes
        axes = [i for i in range(3) if abs(n[i]) < 0.5]
        a0 = min(ps, key=lambda p: (p[axes[0]], p[axes[1]]))
        f = [(point[i] - lo[i]) / (hi[i] - lo[i]) if hi[i] > lo[i] else 0.0 for i in axes]
        corner = {(round((p[axes[0]] - lo[axes[0]]) / (hi[axes[0]] - lo[axes[0]])),
                   round((p[axes[1]] - lo[axes[1]]) / (hi[axes[1]] - lo[axes[1]]))): u for p, u in zip(ps, us)}
        if len(corner) < 4:
            continue                                                      # (a triangle of the face: its quad twin does)
        u_ = (corner[(0, 0)] * (1 - f[0]) * (1 - f[1]) + corner[(1, 0)] * f[0] * (1 - f[1])
              + corner[(0, 1)] * (1 - f[0]) * f[1] + corner[(1, 1)] * f[0] * f[1])
        best = tex[min(h - 1, int(u_[1] * h)), min(w - 1, int(u_[0] * w)), :3]
        _unused = (wts, a0)
        break
    return None if best is None else [round(float(c), 3) for c in best]


# the front is the -Z face; the stain's disc is in the picture's lower left quarter = the model's +X side, low
out = {"stripe_front": colour_at((0.0, 1.25, -1.0), (0, 0, -1)), "stripe_back": colour_at((0.0, 1.25, 1.0), (0, 0, 1)),
       "stripe_side": colour_at((2.0, 1.25, 0.0), (1, 0, 0)), "plain_front": colour_at((-1.5, 2.5, -1.0), (0, 0, -1)),
       "stain_front": colour_at((1.0, 0.75, -1.0), (0, 0, -1)), "plain_top": colour_at((0.0, 3.0, 0.0), (0, 1, 0)),
       "stain_back": colour_at((1.0, 0.75, 1.0), (0, 0, 1)),
       "mesh_maps": manifest["groups"]["main"].get("mesh_maps")}
print("MASK " + json.dumps(out))
