"""look_ortho.py — run by kit/tools/look_details.py (and kit look zebra) inside Blender on a built asset's .blend: an
ORTHOGRAPHIC view of one region — the same projection as a game's orthographic reference render, so the reference's
detail crops and the build's line up after a scale + shift — clipped to the region's slab along the view (four guns
side by side: only the one asked for), on a transparent film.

    blender -b <asset>.blend -P kit/blender/look_ortho.py -- <out.png> <lo x,y,z> <hi x,y,z> [--view side|left|front|back|top|bottom]
        [--px 2400] [--samples 48] [--zebra | --clay | --ids]

--ids: every part a flat colour from its id (kit_part; decoded by kit look edges). --clay: the edge calibration's
matte grey, with each part's shaded round. --zebra: every surface a plain glossy grey under a STRIPED light (the car-body test): a dent, a pinch or a wavy face
breaks the stripes; a clean surface bends them smoothly. Prints LOOK_ORTHO <json> (the projection: px per unit).
"""

import json
import math
import os
import sys

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]
lo = mathutils.Vector([float(v) for v in argv[1].split(",")])
hi = mathutils.Vector([float(v) for v in argv[2].split(",")])


def arg(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


view = arg("--view", "side")
# (camera direction from the subject, its up; Blender axes: the kit's front -Z is Blender's +Y, up is +Z)
VIEWS = {"side": ((1, 0, 0), (0, 0, 1)), "left": ((-1, 0, 0), (0, 0, 1)), "front": ((0, 1, 0), (0, 0, 1)),
         "back": ((0, -1, 0), (0, 0, 1)), "top": ((0, 0, 1), (0, 1, 0)), "bottom": ((0, 0, -1), (0, 1, 0))}
d, up = (mathutils.Vector(v) for v in VIEWS[view])
c = (lo + hi) / 2
ext = hi - lo
right = up.cross(d).normalized()  # (screen x)
w_u = abs(ext.dot(right)) or 1e-3
h_u = abs(ext.dot(up)) or 1e-3
depth = abs(ext.dot(d)) or 1e-3
px = int(arg("--px", 2400))
pad = 1.08
if w_u >= h_u:
    W, H = px, max(16, int(px * h_u / w_u))
else:
    W, H = max(16, int(px * w_u / h_u)), px
sc = bpy.context.scene
cam = bpy.data.objects.new("ortho_cam", bpy.data.cameras.new("ortho_cam"))
sc.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(w_u, h_u) * pad
margin = depth * 0.5 + 0.05
cam.location = c + d * (depth / 2 + margin)
cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
# the track gives the camera's own up; turn it about its axis so screen-up is `up`
cam_up = cam.rotation_euler.to_matrix() @ mathutils.Vector((0, 1, 0))
ang = math.atan2(cam_up.cross(up).dot(-d), cam_up.dot(up))
cam.rotation_euler = (mathutils.Matrix.Rotation(ang, 4, -d) @ cam.rotation_euler.to_matrix().to_4x4()).to_euler()
cam.data.clip_start = margin * 0.5
cam.data.clip_end = margin + depth * 1.02   # (only this slab: a neighbour behind it is clipped away)
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.resolution_percentage = 100
sc.render.film_transparent = True
sc.render.engine = "CYCLES"
sc.cycles.samples = int(arg("--samples", 48))
try:
    sc.cycles.device = "GPU"
except Exception:  # noqa: BLE001
    pass
if sc.world is None:
    sc.world = bpy.data.worlds.new("ortho_world")
sc.world.use_nodes = True
nt = sc.world.node_tree
bg = nt.nodes.get("Background")
if "--zebra" in argv:
    # stripes of light across the view's up: an emission wave in the world, a mirror-like grey on everything
    for n in list(nt.nodes):
        if n.type not in ("BACKGROUND", "OUTPUT_WORLD"):
            nt.nodes.remove(n)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 6.0
    wave.inputs["Distortion"].default_value = 0.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.02, 0.02, 0.02, 1)
    ramp.color_ramp.elements[1].position = 0.5
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)
    nt.links.new(coord.outputs["Generated"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    zmat = bpy.data.materials.new("zebra")
    zmat.use_nodes = True
    bsdf = zmat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.04
    for ob in sc.objects:
        if ob.type == "MESH":
            ob.data.materials.clear()
            ob.data.materials.append(zmat)
    sc.render.film_transparent = False
else:
    hdri = os.path.join(bpy.utils.system_resource("DATAFILES", path="studiolights/world"), "studio.exr")
    if bg is not None and os.path.isfile(hdri):
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(hdri)
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 1.0
    for k, (energy, direction) in enumerate(((3.0, (2, -3, 4)), (1.0, (-3, 2, 2)))):
        lamp = bpy.data.objects.new(f"ortho_l{k}", bpy.data.lights.new(f"ortho_l{k}", "SUN"))
        lamp.data.energy = energy
        lamp.rotation_euler = (mathutils.Vector(direction) * -1).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lamp)
    if "--ids" in argv:
        # every part a FLAT colour from its id (face attribute kit_part): R = 16 x (id % 16) + 8, G = 16 x (id // 16)
        # + 8, unlit, no anti-aliasing, no view transform — kit look edges reads each part's pixels back
        idm = bpy.data.materials.new("kit_ids")
        idm.use_nodes = True
        nt_ = idm.node_tree
        for n_ in list(nt_.nodes):
            nt_.nodes.remove(n_)
        o_ = nt_.nodes.new("ShaderNodeOutputMaterial")
        em = nt_.nodes.new("ShaderNodeEmission")
        at = nt_.nodes.new("ShaderNodeAttribute")
        at.attribute_type = "GEOMETRY"
        at.attribute_name = "kit_part"
        mod16 = nt_.nodes.new("ShaderNodeMath")
        mod16.operation = "MODULO"
        mod16.inputs[1].default_value = 16.0
        nt_.links.new(at.outputs["Fac"], mod16.inputs[0])
        div16 = nt_.nodes.new("ShaderNodeMath")
        div16.operation = "DIVIDE"
        div16.inputs[1].default_value = 16.0
        nt_.links.new(at.outputs["Fac"], div16.inputs[0])
        flo = nt_.nodes.new("ShaderNodeMath")
        flo.operation = "FLOOR"
        nt_.links.new(div16.outputs[0], flo.inputs[0])
        comb = nt_.nodes.new("ShaderNodeCombineColor")

        def chan(src, sock):
            mul = nt_.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY_ADD"
            nt_.links.new(src.outputs[0], mul.inputs[0])
            mul.inputs[1].default_value = 16.0 / 255.0
            mul.inputs[2].default_value = 8.0 / 255.0
            nt_.links.new(mul.outputs[0], sock)
        chan(mod16, comb.inputs[0])
        chan(flo, comb.inputs[1])
        comb.inputs[2].default_value = 0.0
        nt_.links.new(comb.outputs[0], em.inputs["Color"])
        em.inputs["Strength"].default_value = 1.0
        nt_.links.new(em.outputs[0], o_.inputs["Surface"])
        for ob in sc.objects:
            if ob.type == "MESH":
                ob.data.materials.clear()
                ob.data.materials.append(idm)
        for ob in [o for o in sc.objects if o.type == "LIGHT"]:
            ob.hide_render = True
        if bg is not None:
            bg.inputs["Strength"].default_value = 0.0
        sc.cycles.samples = 1
        sc.render.filter_size = 0.01
        sc.cycles.use_denoising = False
        try:
            sc.view_settings.view_transform = "Raw"
        except TypeError:
            sc.view_settings.view_transform = "Standard"
    if "--clay" in argv:
        # every surface the edge calibration's matte grey (kit/tools/edge_calibrate.py): a glossy metal meets the
        # backdrop with a hard reflection whatever its round — clay shows the round as the shading turning away
        clay = bpy.data.materials.new("clay")
        clay.use_nodes = True
        b_ = clay.node_tree.nodes.get("Principled BSDF")
        b_.inputs["Base Color"].default_value = (0.35, 0.35, 0.36, 1)
        b_.inputs["Roughness"].default_value = 0.4
        b_.inputs["Metallic"].default_value = 0.0
        # (the same rounded-edge SHADING the bake gives: each a.cad part's asked round, kit_edge_r)
        bev = clay.node_tree.nodes.new("ShaderNodeBevel")
        bev.samples = 16
        nt_ = clay.node_tree
        attr = nt_.nodes.new("ShaderNodeAttribute")
        attr.attribute_type = "GEOMETRY"
        attr.attribute_name = "kit_edge_r"
        nt_.links.new(attr.outputs["Fac"], bev.inputs["Radius"])
        nt_.links.new(bev.outputs["Normal"], b_.inputs["Normal"])
        for ob in sc.objects:
            if ob.type == "MESH":
                ob.data.materials.clear()
                ob.data.materials.append(clay)
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("LOOK_ORTHO " + json.dumps({"out": out, "w": W, "h": H, "px_per_unit": W / (cam.data.ortho_scale if W >= H else
                                                                               cam.data.ortho_scale * W / H),
                                  "view": view, "transform": sc.view_settings.view_transform}))
