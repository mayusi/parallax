"""photoscan_outline.py - THE SCAN SEEN THROUGH ITS OWN CAMERAS (the photogrammetry route's capture check; his D-R02).

blender -b --factory-startup -P photoscan_outline.py -- <scan.glb> <views.json> <out.json>

A scan can come back wrong with every number about its cameras fine: the 24-photo trial (2026-11-16) placed all 24
photos at 0.43 px and still built a torn second shell round the object. What a person would do: look at the scan
from where each photo was taken and see whether it covers the object in that photo. Here: the finished scan is put
back in the cameras' own frame (views.json's "to_scan" undone), rendered flat through each solved camera at the
photo's own size, and its outline scored against the object's outline cut out of the photo (kit/vision cutout):
IoU, 1 = the same outline. -> out.json {"median", "worst": [[image, iou]], "views"}."""

import json
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
import os  # noqa: E402

GLB, VIEWS, OUT = (os.path.abspath(a) for a in ARGS[:3])   # (Blender saves a relative render path from its own root)
spec = json.load(open(VIEWS, encoding="utf-8"))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
objs = [o for o in bpy.data.objects if o.type == "MESH"]
back = Matrix(spec["to_scan"]).inverted()
white = bpy.data.materials.new("white")
for o in objs:
    o.data.transform(o.matrix_world)
    o.matrix_world = Matrix.Identity(4)
    o.data.transform(back)
    o.data.materials.clear()
    o.data.materials.append(white)

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "SINGLE"
sc.display.shading.single_color = (1, 1, 1)
sc.display.render_aa = "OFF"
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("black")
w.color = (0, 0, 0)
sc.world = w
sc.render.film_transparent = False
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "BW"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.sensor_fit = "HORIZONTAL"
cam.data.sensor_width = 36.0
cam.data.clip_start, cam.data.clip_end = 0.001, 10000.0

scores, tall = [], []
tmp = OUT + ".png"
for v in spec["views"]:
    r = np.array(v["R"])
    c = -r.T @ np.array(v["t"])
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = r.T[:, 0], -r.T[:, 1], -r.T[:, 2], c   # (COLMAP's y down, z ahead)
    cam.matrix_world = Matrix(m.tolist())
    W, H = v["width"], v["height"]
    sc.render.resolution_x, sc.render.resolution_y = W, H
    # (a pixel taller than wide when fx > fy, wider when fy > fx - Blender takes the aspect as two numbers of 1 or
    #  more, never below 1: the review found fy > fx clamped)
    if v["fx"] >= v["fy"]:
        sc.render.pixel_aspect_x, sc.render.pixel_aspect_y = 1.0, v["fx"] / v["fy"]
    else:
        sc.render.pixel_aspect_x, sc.render.pixel_aspect_y = v["fy"] / v["fx"], 1.0
    cam.data.lens = v["fx"] / W * 36.0
    # (with the sensor fitted across, both shifts are shares of the WIDTH - the review: a portrait photo's off-centre
    #  principal point was divided by its height)
    cam.data.shift_x = -(v["cx"] - W / 2) / W
    cam.data.shift_y = (v["cy"] - H / 2) / W
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(tmp)
    px = np.array(img.pixels[:], np.float32).reshape(H, W, -1)[::-1, :, 0] > 0.5
    bpy.data.images.remove(img)
    photo = np.load(v["mask"]) > 0.5
    union = int((px | photo).sum())
    scores.append((v["image"], round(float((px & photo).sum()) / union, 4) if union else 0.0))
    # how TALL the scan stands in this photo against the object: both outlines measured along the scan's up as this
    # camera sees it (so a camera held on its side measures the same thing). The IoU above barely moves when only
    # the bottom is missing (2026-11-18: a thin capture's scan 8% short scored 0.95 and passed; its scale, read from
    # its height, came out 10% too wide)
    d = r @ np.array(back.to_3x3() @ Vector((0.0, 0.0, 1.0)))   # (the scan's up, in this camera's frame)
    d2 = np.array([d[0], d[1]])   # (COLMAP's image x right, y down: the same as the pixel rows below)
    if np.linalg.norm(d2) > 1e-6 and px.any() and photo.any():
        d2 /= np.linalg.norm(d2)

        def span(mask):
            ys, xs = np.nonzero(mask)
            h = xs * d2[0] + ys * d2[1]
            return float(np.percentile(h, 99.5) - np.percentile(h, 0.5))
        tall.append((v["image"], round(span(px) / max(span(photo), 1.0), 4)))
vals = [s for _n, s in scores]
res = {"median": round(float(np.median(vals)), 4), "worst": sorted(scores, key=lambda x: x[1])[:3],
       "views": len(scores),
       "height": {"median": round(float(np.median([t for _n, t in tall])), 4) if tall else None,
                  "shortest": sorted(tall, key=lambda x: x[1])[:3]}}
json.dump(res, open(OUT, "w", encoding="utf-8"))
print("OUTLINE " + json.dumps({k: res[k] for k in ("median", "worst", "height")}))
