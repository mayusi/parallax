"""look_closeup.py — run by kit/tools/look.py inside Blender on a built asset's .blend: one region framed at hero
distance (an 85 mm lens, a three-quarter view by default), lit by Blender's bundled studio HDRI plus a key and a fill,
rendered in Cycles — the detail judged where it shows, never in a whole-asset sheet where it is a few pixels.

    blender -b <asset>.blend -P kit/blender/look_closeup.py -- <out.png> <cx> <cy> <cz> <size> [--view three-quarter]
        [--res 1400x900] [--samples 64]
"""

import math
import os
import sys

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]
c = mathutils.Vector([float(v) for v in argv[1:4]])
size = float(argv[4])


def arg(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


VIEWS = {   # (camera direction from the subject, Blender axes: the kit's front -Z is Blender's +Y)
    "three-quarter": (0.55, 0.65, 0.55), "three-quarter-left": (-0.55, 0.65, 0.45), "front": (0.0, 1.0, 0.12), "back": (0.0, -1.0, 0.12),
    "side": (1.0, 0.0, 0.12), "left": (-1.0, 0.0, 0.12), "top": (0.05, 0.15, 1.0), "below": (0.3, 0.5, -0.6)}
view = arg("--view", "three-quarter")
d = mathutils.Vector(VIEWS.get(view, VIEWS["three-quarter"])).normalized()
w, h = (int(v) for v in arg("--res", "1400x900").split("x"))
sc = bpy.context.scene
cam = bpy.data.objects.new("look_cam", bpy.data.cameras.new("look_cam"))
sc.collection.objects.link(cam)
cam.data.lens = 85.0
fov = 2 * math.atan(cam.data.sensor_width / 2 / cam.data.lens)
dist = (size * 0.62) / math.tan(fov / 2)   # (the region fills ~80% of the frame)
cam.location = c + d * dist
cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.clip_start = dist * 0.01
cam.data.clip_end = dist * 50
sc.camera = cam
for k, (energy, direction) in enumerate(((3.2, (2, -3, 4)), (1.1, (-3, 2, 2)), (1.6, (0, 4, 1.5)))):   # key, fill, rim
    lamp = bpy.data.objects.new(f"look_l{k}", bpy.data.lights.new(f"look_l{k}", "SUN"))
    lamp.data.energy = energy
    lamp.rotation_euler = (mathutils.Vector(direction) * -1).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(lamp)
if sc.world is None:
    sc.world = bpy.data.worlds.new("look_world")
sc.world.use_nodes = True
nt = sc.world.node_tree
hdri = os.path.join(bpy.utils.system_resource("DATAFILES", path="studiolights/world"), "studio.exr")
bg = nt.nodes.get("Background")
if bg is not None and os.path.isfile(hdri):
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(hdri)
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
sc.render.film_transparent = False
try:  # (P.gem's stones refract at hero distance, as in the showcase)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import rbx_parts  # noqa: E402

    rbx_parts.glass_gems([o for o in sc.objects if o.type == "MESH"])
except Exception as e:  # noqa: BLE001 — a close-up without glass stones, said
    print("LOOK_GLASS_SKIPPED", e)
sc.render.engine = "CYCLES"
sc.cycles.samples = int(arg("--samples", 64))
try:
    sc.cycles.device = "GPU"
except Exception:  # noqa: BLE001 — CPU then
    pass
sc.render.resolution_x, sc.render.resolution_y = w, h
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("LOOK_RENDERED", out)
