"""capture_urn.py - a SYNTHETIC CAPTURE for the photogrammetry route's proof (kit/tools/photoscan.py; his D-R02): a
speckled urn with a side boss rendered from rings of cameras round it, the way a person walks round a thing with a
camera, plus the truth (its mesh and sizes).

    blender -b --factory-startup -P capture_urn.py -- <out folder> [good|thin]

  good   32 photos at 1024 x 768 on three rings (12, 12, 8): what a capture needs. photoscan must place them all,
         cover the urn's outline in every photo and land within a few percent of its true shape - with the
         textured ground it stands on left out of the scan.
  thin   24 photos at 800 x 600 (10, 9, 5): too few and too small - COLMAP places every camera and still builds a
         doubled shell round the urn (2026-11-16). photoscan must REFUSE it by the outline check.
  lit    the good capture under a strong lamp from one side and a dim sky: the scan's colour carries that shading,
         and kit/tools/delight.py (his D-R03) takes it out.
  lit2   the same places, the lamp on the OTHER side: the relighting benchmark - the colour with its light out must
         match these photos better than the colour as photographed (photo names and camera places as `lit`).
Writes <out>/images/v###.jpg, <out>/truth.obj, <out>/truth.json. Never "fix" this file."""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
OUT = ARGS[0]
HOW = next((w for w in ("thin", "lit2", "lit") if w in ARGS[1:]), "good")
RES, RINGS = {"good": ((1024, 768), ((0.25, 12, 1.9), (0.9, 12, 1.8), (1.6, 8, 1.6))),
              "lit": ((1024, 768), ((0.25, 12, 1.9), (0.9, 12, 1.8), (1.6, 8, 1.6))),
              "lit2": ((1024, 768), ((0.25, 12, 1.9), (0.9, 12, 1.8), (1.6, 8, 1.6))),
              "thin": ((800, 600), ((0.3, 10, 1.9), (1.0, 9, 1.8), (1.6, 5, 1.6)))}[HOW]
os.makedirs(os.path.join(OUT, "images"), exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# the object: a squat urn with a side boss, 0.75 x 0.8 x 0.9 m - a profile and a bump to recover
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.3, location=(0, 0, 0.45))
urn = bpy.context.object
for v in urn.data.vertices:
    z = v.co.z
    v.co.z = z * 1.5
    k = 1.0 + 0.25 * math.cos(z * 9.0)
    v.co.x *= k
    v.co.y *= k
bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.2, location=(0.32, 0, 0.5), rotation=(0, math.pi / 2, 0))
boss = bpy.context.object
for o in (urn, boss):
    o.select_set(True)
bpy.context.view_layer.objects.active = urn
bpy.ops.object.join()
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
urn.name = "Truth"

# a texture with features to match (a real capture needs a surface with detail: plain paint cannot be scanned)
mat = bpy.data.materials.new("speckle")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
noise = nt.nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 18.0
noise.inputs["Detail"].default_value = 8.0
vor = nt.nodes.new("ShaderNodeTexVoronoi")
vor.inputs["Scale"].default_value = 30.0
mix = nt.nodes.new("ShaderNodeMix")
mix.data_type = "RGBA"
mix.inputs["Factor"].default_value = 0.5
nt.links.new(noise.outputs["Color"], mix.inputs[6])
nt.links.new(vor.outputs["Color"], mix.inputs[7])
nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.8
urn.data.materials.append(mat)

# the ground it stands on, TEXTURED (a real table, floor or street: COLMAP finds points on it too - only the cut-out
# masks given to the fusion keep them out of the scan; the review, 2026-11-16: a plain backdrop never tested that)
bpy.ops.mesh.primitive_circle_add(vertices=64, radius=1.3, fill_type="NGON", location=(0, 0, 0))
floor = bpy.context.object
floor.name = "Floor"
fmat = bpy.data.materials.new("planks")
fmat.use_nodes = True
fnt = fmat.node_tree
wave = fnt.nodes.new("ShaderNodeTexWave")
wave.inputs["Scale"].default_value = 6.0
wave.inputs["Distortion"].default_value = 8.0
ramp = fnt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (0.18, 0.11, 0.06, 1)
ramp.color_ramp.elements[1].color = (0.55, 0.38, 0.22, 1)
fnt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
fnt.links.new(ramp.outputs["Color"], fnt.nodes["Principled BSDF"].inputs["Base Color"])
floor.data.materials.append(fmat)

# even light (a capture is lit flat), a plain backdrop beyond the ground
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.8, 0.8, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sc.world = w
if HOW in ("lit", "lit2"):   # (a strong lamp from one side and a dim sky: the shading kit/tools/delight.py takes out)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.25
    sun = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(35 if HOW == "lit" else 215))   # (lit2: the other side)
    sc.collection.objects.link(sun)
sc.render.engine = "CYCLES"
sc.cycles.samples = 16
sc.cycles.device = "GPU"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.get_devices()
for d in prefs.devices:
    d.use = True
sc.render.resolution_x, sc.render.resolution_y = RES
# (plain sRGB out: Blender 5.2 tone-maps with AgX by default, and a photo read as sRGB would then not be colour x
#  light - the review, 2026-11-16)
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 35
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam
target = Vector((0, 0, 0.45))
cams, n = [], 0
for ring_z, count, dist in RINGS:
    for i in range(count):
        a = 2 * math.pi * (i + (0.5 if ring_z > 1.5 else 0)) / count
        cam.location = Vector((dist * math.cos(a), dist * math.sin(a), ring_z))
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(OUT, "images", f"v{n:03d}.jpg")
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 92
        bpy.ops.render.render(write_still=True)
        cams.append({"image": f"v{n:03d}.jpg", "location": list(cam.location)})
        n += 1

bpy.data.objects.remove(floor)   # (the truth is the urn alone)
bpy.ops.wm.obj_export(filepath=os.path.join(OUT, "truth.obj"), export_selected_objects=False,
                      export_materials=False, forward_axis="Y", up_axis="Z")
json.dump({"how": HOW, "cameras": cams, "truth_dims_m": list(urn.dimensions)},
          open(os.path.join(OUT, "truth.json"), "w"), indent=1)
print("CAPTURE", HOW, n, "views; truth", [round(d, 4) for d in urn.dimensions])
