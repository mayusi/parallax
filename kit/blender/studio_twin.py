"""studio_twin.py - the Blender TWIN of a Studio capture: the same built model, the same camera, Roblox's light as the
kit's look rig maps it (rbx_lookdev.light_rig) from the Lighting READ in Studio (kit/tools/studio_model.py twin).

blender -b <asset>.blend --factory-startup --python-exit-code 2 -P studio_twin.py -- <manifest.json> <look.json> <out.png>

look.json is what the Studio side read (kit/tools/studio_model.py look_script): the Lighting values the rig takes
(Brightness, ExposureCompensation, EnvironmentDiffuseScale, ShadowSoftness, Ambient, OutdoorAmbient, ColorShift_Top,
SunDirection, MoonDirection), the camera (position, look, up, vertical fov, viewport px) and `at` (where the model's
origin stood). Only the manifest's groups are drawn, on a clear film (the picture's alpha is the model). Prints
TWIN {json}."""

import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rbx_lookdev  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:]
MANIFEST, LOOK, OUT = ARGS[0], ARGS[1], ARGS[2]
with open(MANIFEST, encoding="utf-8") as fh:
    manifest = json.load(fh)
with open(LOOK, encoding="utf-8") as fh:
    look = json.load(fh)

scene = bpy.context.scene
groups = {os.path.splitext(os.path.basename(e.get("fbx") or ""))[0] for e in manifest["groups"].values()}
drawn = []
for obj in scene.objects:
    if obj.type == "LIGHT" or (obj.type == "MESH" and obj.name not in groups) or obj.type not in ("MESH", "CAMERA"):
        obj.hide_render = True
    elif obj.type == "MESH":
        obj.hide_render = False
        drawn.append(obj.name)
missing = sorted(groups - set(drawn))

made, label = rbx_lookdev.light_rig(scene, "studio", look, "as_read")
rbx_lookdev.eevee(scene)
rbx_lookdev.roblox_view(scene)            # (the colour curve fitted to Studio, when there is one)

cam = look["camera"]
# (model_shot.luau gives the camera in the model's own frame: space "model"; an older look.json gave it in the
#  world, the model's origin at `at`, unturned)
at = [0, 0, 0] if cam.get("space") == "model" else (look.get("at") or [0, 0, 0])
pos = rbx_lookdev.to_blender([c - a for c, a in zip(cam["position"], at)])
fwd = rbx_lookdev.to_blender(cam["look"]).normalized()
up = rbx_lookdev.to_blender(cam["up"]).normalized()
right = fwd.cross(up).normalized()
up = right.cross(fwd).normalized()
cd = bpy.data.cameras.new("Studio twin")
cd.sensor_fit = "VERTICAL"
cd.angle_y = math.radians(float(cam["fov"]))
cd.clip_start = 0.01
co = bpy.data.objects.new("Studio twin", cd)
scene.collection.objects.link(co)
co.matrix_world = Matrix((
    (right.x, up.x, -fwd.x, pos.x),
    (right.y, up.y, -fwd.y, pos.y),
    (right.z, up.z, -fwd.z, pos.z),
    (0, 0, 0, 1),
))
scene.camera = co
w, h = (int(v) for v in cam["viewport"])
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = w, h, 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("TWIN " + json.dumps({"drawn": drawn, "missing": missing, "light": label,
                            "view_transform": scene.view_settings.view_transform, "size": [w, h],
                            "camera_blender": [round(v, 4) for v in pos]}))
sys.exit(1 if missing or not drawn else 0)
