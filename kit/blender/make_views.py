"""make_views.py — one candidate mesh seen the way the photos see the object, for `kit make`'s tournament:

    blender -b --factory-startup -P kit/blender/make_views.py -- <mesh.glb> <out_dir>

Writes <out_dir>/front.png, back.png, left.png, right.png, top.png (orthographic SILHOUETTES: alpha = the object,
fitted to the frame) and look.png (a shaded three-quarter view on white, for the look comparison), plus views.json
(the object's size along x / y / z in its own units: its proportions). The mesh is read in the kit's generator frame
(Roblox: y up, front -Z), which glTF import turns into Blender's z up, front +Y; its right side is +X.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
path, out = os.path.abspath(argv[0]), os.path.abspath(argv[1])
os.makedirs(out, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(path)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(path))
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=os.path.abspath(path))
else:
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(path))
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
centre, ext3 = (lo + hi) / 2, hi - lo
big = max(ext3)

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = scene.render.resolution_y = 512
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
shading = scene.display.shading
shading.light = "STUDIO"
shading.color_type = "MATERIAL"
cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

# (direction FROM the object TO the camera, the camera's up) — the model's front is +Y here, its right +X
VIEWS = {"front": (Vector((0, 1, 0)), Vector((0, 0, 1))), "back": (Vector((0, -1, 0)), Vector((0, 0, 1))),
         "left": (Vector((-1, 0, 0)), Vector((0, 0, 1))), "right": (Vector((1, 0, 0)), Vector((0, 0, 1))),
         "top": (Vector((0, 0, 1)), Vector((0, 1, 0)))}


def aim(direction, up, ortho=True):
    cam.location = centre + direction * big * 3
    look = -direction
    right = look.cross(up).normalized()
    true_up = right.cross(look).normalized()
    from mathutils import Matrix  # noqa: PLC0415

    rot = Matrix((right, true_up, -look)).transposed()
    cam.rotation_euler = rot.to_euler()
    cam_data.type = "ORTHO" if ortho else "PERSP"
    cam_data.ortho_scale = big * 1.08
    cam_data.lens = 50
    cam_data.clip_end = big * 10


for name, (d, up) in VIEWS.items():
    aim(d, up)
    scene.render.filepath = os.path.join(out, f"{name}.png")
    bpy.ops.render.render(write_still=True)

# the look: a three-quarter view from the front-right, a little above, on white (no transparency)
scene.render.film_transparent = False
scene.world = bpy.data.worlds.new("w") if not scene.world else scene.world
shading.background_type = "VIEWPORT"
shading.background_color = (1.0, 1.0, 1.0)
d = Vector((0.75, 0.75, 0.45)).normalized()
aim(d, Vector((0, 0, 1)), ortho=False)
cam.location = centre + d * big * 2.2
scene.render.filepath = os.path.join(out, "look.png")
bpy.ops.render.render(write_still=True)

with open(os.path.join(out, "views.json"), "w", encoding="utf-8") as fh:
    json.dump({"size": [round(v, 5) for v in ext3], "axes": "x right, y front, z up (Blender)"}, fh)
print(json.dumps({"schema": 1, "status": "pass", "summary": f"make_views: {path} -> {out}", "next_action": "none"}))
