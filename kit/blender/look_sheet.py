"""look_sheet.py — the PRESENTATION sheet's renders, run by kit/tools/look.py inside Blender on a built asset's .blend
(the 3D crafts plan, S0; board card macm): one hero camera, six looks, the way game studios show a prop.

    blender -b <asset>.blend -P kit/blender/look_sheet.py -- <out_dir> [--game <Name>] [--res 560x420]
writes <out_dir>/<tile>.png:
  owner        the owner's own view: Blender's forest HDRI (his Material Preview), EEVEE
  roblox_day   the Roblox look at midday (kit/blender/rbx_lookdev.py: his place's Lighting, a midday sun)
  roblox_night the Roblox look as his place was read (its moon when its sun is down)
  clay         every material a neutral 18% grey under the forest HDRI: the form alone
  wire         the game mesh's triangles over light grey (Cycles, the Wireframe node): where the triangles go
  texels       a colour grid laid on the UVs, unlit: even squares = even sharpness, big squares = blurry
Prints LOOK_SHEET <json> with what each tile shows.
"""

import json
import math
import os
import sys

import bpy
import mathutils
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rbx_lookdev  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir = argv[0]


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


w, h = (int(v) for v in arg("--res", "560x420").split("x"))
game = arg("--game")
sc = bpy.context.scene
objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
for o in sc.objects:   # the .blend's own lights (a saved Roblox look) never leak into another tile
    if o.type == "LIGHT":
        o.hide_render = True
pts = np.array([list(o.matrix_world @ mathutils.Vector(c)) for o in objs for c in o.bound_box])
lo, hi = pts.min(axis=0), pts.max(axis=0)
centre = mathutils.Vector(((lo + hi) / 2).tolist())
size = float(np.linalg.norm(hi - lo))
cam = bpy.data.objects.new("sheet_cam", bpy.data.cameras.new("sheet_cam"))
sc.collection.objects.link(cam)
cam.data.lens = 70.0
fov = 2 * math.atan(cam.data.sensor_width / 2 / cam.data.lens)
dist = (size * 0.55) / math.tan(fov / 2)
d = mathutils.Vector((0.6, 0.7, 0.42)).normalized()   # (the hero three-quarter: the kit's front -Z is Blender's +Y)
cam.location = centre + d * dist
cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.clip_start, cam.data.clip_end = dist * 0.01, dist * 50
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = w, h
sc.render.resolution_percentage = 100
sc.render.film_transparent = False
os.makedirs(out_dir, exist_ok=True)
hdri_dir = bpy.utils.system_resource("DATAFILES", path="studiolights/world")
shown = {}


def forest_world():
    world = bpy.data.worlds.new("sheet_forest")
    if hasattr(world, "use_nodes") and not world.node_tree:
        world.use_nodes = True
    nt = world.node_tree
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None) or nt.nodes.new("ShaderNodeBackground")
    out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None) or nt.nodes.new("ShaderNodeOutputWorld")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.join(hdri_dir, rbx_lookdev.OWNER_HDRI), check_existing=True)
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    bg.inputs["Strength"].default_value = 1.0
    return world


def render(tile):
    sc.render.filepath = os.path.join(out_dir, f"{tile}.png")
    bpy.ops.render.render(write_still=True)


def drop(made):
    for d_ in made:
        try:
            if isinstance(d_, bpy.types.Object):
                bpy.data.objects.remove(d_, do_unlink=True)
            elif isinstance(d_, bpy.types.Light):
                bpy.data.lights.remove(d_)
        except ReferenceError:
            pass


forest = forest_world()
# 1. the owner's own view
sc.world = forest
rbx_lookdev.eevee(sc)
render("owner")
shown["owner"] = f"Blender's {rbx_lookdev.OWNER_HDRI} (your Material Preview), EEVEE"
# 2-3. the Roblox look, midday and as read
name, p = rbx_lookdev.preset_for(game)
for tile, variant in (("roblox_day", "day"), ("roblox_night", "as_read")):
    made, label = rbx_lookdev.light_rig(sc, name, p, variant)
    rbx_lookdev.eevee(sc)
    restore = rbx_lookdev.roblox_view(sc)     # (the colour curve fitted to Studio, when there is one)
    render(tile)
    restore()
    shown[tile] = label
    drop(made)
# 4. clay: the form alone
clay = bpy.data.materials.new("sheet_clay")
clay.use_nodes = True
b = clay.node_tree.nodes.get("Principled BSDF")
b.inputs["Base Color"].default_value = (0.18, 0.18, 0.18, 1.0)
b.inputs["Roughness"].default_value = 0.55
b.inputs["Metallic"].default_value = 0.0
sc.world = forest
sc.view_layers[0].material_override = clay
rbx_lookdev.eevee(sc)
render("clay")
shown["clay"] = "every material an 18% grey, forest HDRI: the form alone"
# 5. the triangles (Cycles: the Wireframe node is Cycles-only)
wire = bpy.data.materials.new("sheet_wire")
wire.use_nodes = True
nt = wire.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
outm = nt.nodes.new("ShaderNodeOutputMaterial")
mix = nt.nodes.new("ShaderNodeMixShader")
grey = nt.nodes.new("ShaderNodeBsdfDiffuse")
grey.inputs["Color"].default_value = (0.55, 0.56, 0.58, 1.0)
ink = nt.nodes.new("ShaderNodeEmission")
ink.inputs["Color"].default_value = (0.02, 0.03, 0.06, 1.0)
wf = nt.nodes.new("ShaderNodeWireframe")
wf.use_pixel_size = True
wf.inputs["Size"].default_value = 0.8
nt.links.new(wf.outputs["Fac"], mix.inputs["Fac"])
nt.links.new(grey.outputs["BSDF"], mix.inputs[1])
nt.links.new(ink.outputs["Emission"], mix.inputs[2])
nt.links.new(mix.outputs["Shader"], outm.inputs["Surface"])
sc.view_layers[0].material_override = wire
sc.render.engine = "CYCLES"
sc.cycles.samples = 16
try:
    sc.cycles.device = "GPU"
except Exception:  # noqa: BLE001 — CPU then
    pass
render("wire")
tris = 0
for o in objs:
    o.data.calc_loop_triangles()
    tris += len(o.data.loop_triangles)
shown["wire"] = f"{tris} triangles in {len(objs)} mesh(es)"
# 6. the texel checker: a colour grid on the UVs, unlit (emission)
grid = bpy.data.images.new("sheet_texels", 1024, 1024)
grid.generated_type = "COLOR_GRID"
chk = bpy.data.materials.new("sheet_texels")
chk.use_nodes = True
nt = chk.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
outm = nt.nodes.new("ShaderNodeOutputMaterial")
em = nt.nodes.new("ShaderNodeEmission")
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = grid
tex.interpolation = "Closest"
nt.links.new(tex.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], outm.inputs["Surface"])
sc.view_layers[0].material_override = chk
dark = bpy.data.worlds.new("sheet_dark")
if hasattr(dark, "use_nodes") and not dark.node_tree:
    dark.use_nodes = True
bgd = next((n for n in dark.node_tree.nodes if n.type == "BACKGROUND"), None)
if bgd:
    bgd.inputs["Color"].default_value = (0.02, 0.02, 0.025, 1.0)
sc.world = dark
rbx_lookdev.eevee(sc, samples=8)
view = sc.view_settings.view_transform
sc.view_settings.view_transform = "Standard"
render("texels")
sc.view_settings.view_transform = view
shown["texels"] = "Blender's colour grid on each mesh's UVs (one 1024 grid per map): even squares = even sharpness"
sc.view_layers[0].material_override = None
print("LOOK_SHEET", json.dumps({"out": out_dir, "tiles": shown, "preset": name}))
