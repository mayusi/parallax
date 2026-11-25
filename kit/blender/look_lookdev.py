"""look_lookdev.py — run by kit/tools/look.py inside Blender on a built asset's .blend: the whole asset from one hero
camera under several lights (Blender's bundled CC0 world HDRIs) plus a CLAY pass (every material a neutral grey: the
form judged alone) — an AAA asset is validated in a controlled rig before creative lighting, under more than one light
(the ODM blade's chrome hid its lines under one studio light; the owner caught it).

    blender -b <asset>.blend -P kit/blender/look_lookdev.py -- <out_dir> [--res 900x600] [--samples 48]
writes <out_dir>/<light>.png for studio, courtyard, sunset, interior, clay
"""

import math
import os
import sys

import bpy
import mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir = argv[0]


def arg(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


LIGHTS = [("studio", "studio.exr", 1.0), ("courtyard", "courtyard.exr", 1.0), ("sunset", "sunset.exr", 1.3),
          ("interior", "interior.exr", 1.2)]
w, h = (int(v) for v in arg("--res", "900x600").split("x"))
sc = bpy.context.scene
objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
pts = np.array([list(o.matrix_world @ mathutils.Vector(c)) for o in objs for c in o.bound_box])
lo, hi = pts.min(axis=0), pts.max(axis=0)
c = mathutils.Vector(((lo + hi) / 2).tolist())
size = float(np.linalg.norm(hi - lo))
cam = bpy.data.objects.new("lookdev_cam", bpy.data.cameras.new("lookdev_cam"))
sc.collection.objects.link(cam)
cam.data.lens = 70.0
fov = 2 * math.atan(cam.data.sensor_width / 2 / cam.data.lens)
dist = (size * 0.55) / math.tan(fov / 2)
d = mathutils.Vector((0.6, 0.7, 0.42)).normalized()   # (the hero three-quarter: the kit's front -Z is Blender's +Y)
cam.location = c + d * dist
cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.clip_start, cam.data.clip_end = dist * 0.01, dist * 50
sc.camera = cam
if sc.world is None:
    sc.world = bpy.data.worlds.new("lookdev_world")
sc.world.use_nodes = True
nt = sc.world.node_tree
bg = nt.nodes.get("Background")
env = nt.nodes.new("ShaderNodeTexEnvironment")
nt.links.new(env.outputs["Color"], bg.inputs["Color"])
base = bpy.utils.system_resource("DATAFILES", path="studiolights/world")
sc.render.engine = "CYCLES"
sc.cycles.samples = int(arg("--samples", 48))
try:
    sc.cycles.device = "GPU"
except Exception:  # noqa: BLE001 — CPU then
    pass
sc.render.resolution_x, sc.render.resolution_y = w, h
sc.render.film_transparent = False
os.makedirs(out_dir, exist_ok=True)
for name, exr, strength in LIGHTS:
    env.image = bpy.data.images.load(os.path.join(base, exr), check_existing=True)
    bg.inputs["Strength"].default_value = strength
    sc.render.filepath = os.path.join(out_dir, f"{name}.png")
    bpy.ops.render.render(write_still=True)
# the clay pass: the form alone (a neutral 18% grey, a little rough), under the studio light
clay = bpy.data.materials.new("lookdev_clay")
clay.use_nodes = True
bsdf = clay.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.18, 0.18, 0.18, 1.0)
bsdf.inputs["Roughness"].default_value = 0.55
bsdf.inputs["Metallic"].default_value = 0.0
sc.view_layers[0].material_override = clay
env.image = bpy.data.images.load(os.path.join(base, "studio.exr"), check_existing=True)
bg.inputs["Strength"].default_value = 1.0
sc.render.filepath = os.path.join(out_dir, "clay.png")
bpy.ops.render.render(write_still=True)
print("LOOKDEV_RENDERED", out_dir)
