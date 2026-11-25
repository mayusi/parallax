"""spin_blender.py — the Blender half of `kit ui spin` (run headless by kit/ui/spin.py):

    blender -b --factory-startup --python-exit-code 2 -P kit/ui/spin_blender.py -- --job <job.json>

The job (written by kit/ui/spin.py): {"polys": [[[x, y], ...], ...] (the piece's silhouette in IMAGE pixels, even-odd),
"image": <the piece PNG>, "size": [w, h], "material": "gold" | "chrome" | "enamel" | {base, roughness, metallic},
"face": true (the artwork on the front face), "depth": 0.12, "layers": [{"polys", "z", "depth"}] (a relief), "bevel": 0.03, "frames": 24, "res": 384, "samples": 24,
"motion": "spin" | "sway" | "flip" | "land", "back": <a picture for the reverse>, "out": <frames dir>, "fbx": <mesh path>}
-> <out>/f_000.png ... (transparent film, orthographic, the kit's key / rim / strip rig) + the FBX.
"""
import json
import math
import os
import sys

import bpy  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
job = json.load(open(argv[argv.index("--job") + 1], encoding="utf-8"))

METALS = {"gold": {"base": (0.95, 0.72, 0.30), "roughness": 0.22, "metallic": 1.0},
          "chrome": {"base": (0.86, 0.88, 0.92), "roughness": 0.12, "metallic": 1.0},
          "enamel": {"base": (0.08, 0.06, 0.14), "roughness": 0.35, "metallic": 0.0},
          "silver": {"base": (0.80, 0.82, 0.88), "roughness": 0.25, "metallic": 1.0}}

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc = bpy.context.scene

# --- the shape: one curve per LAYER, every silhouette polygon a closed POLY spline (even-odd fill makes the holes);
# layer 0 is the whole piece, a relief (--relief N) stacks brighter levels on top, each raised a step: joined into one mesh
w, h = job["size"]
unit = 2.0 / max(w, h)  # the piece's long side = 2 scene units
layers = job.get("layers") or [{"polys": job["polys"], "z": 0.0, "depth": float(job.get("depth", 0.12))}]
parts = []
for li, layer in enumerate(layers):
    cu = bpy.data.curves.new(f"shape{li}", type="CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    for poly in layer["polys"]:
        if len(poly) < 3:
            continue
        sp = cu.splines.new("POLY")
        sp.points.add(len(poly) - 1)
        for i, (x, y) in enumerate(poly):
            sp.points[i].co = ((x - w / 2) * unit, (h / 2 - y) * unit, 0.0, 1.0)
        sp.use_cyclic_u = True
    if not cu.splines:
        continue
    cu.extrude = float(layer["depth"]) / 2
    # (the relief's steps stay crisp: a bevel on a ragged brightness edge mitres acute corners into long spikes)
    cu.bevel_depth = float(job.get("bevel", 0.03)) if li == 0 else 0.0
    cu.bevel_resolution = 3
    o = bpy.data.objects.new(f"piece{li}", cu)
    sc.collection.objects.link(o)
    o.location.z = float(layer["z"])
    parts.append(o)
bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.convert(target="MESH")
if len(parts) > 1:
    bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
ob.name = "piece"

# --- a DEPTH relief (--depth-relief): a grid over the opaque pixels raised by the depth estimate, standing on the base's
# front (its edges ramp down to it), joined into the piece; its faces take the art like the front
FRONT = float(job.get("depth", 0.12)) / 2 + float(job.get("bevel", 0.03))
grid = job.get("relief_grid")
if grid:
    import numpy as np
    Z = np.load(grid["path"])
    gh, gw = Z.shape
    H = float(grid["height"])
    idx = -np.ones((gh, gw), dtype=np.int64)
    verts = []
    for gy in range(gh):
        for gx in range(gw):
            z = Z[gy, gx]
            if np.isnan(z):
                continue
            idx[gy, gx] = len(verts)
            px, py = (gx + 0.5) / gw * w, (gy + 0.5) / gh * h
            verts.append(((px - w / 2) * unit, (h / 2 - py) * unit, FRONT + 0.002 + H * float(z)))
    faces = []
    for gy in range(gh - 1):
        for gx in range(gw - 1):
            a, b, c, d = idx[gy, gx], idx[gy, gx + 1], idx[gy + 1, gx + 1], idx[gy + 1, gx]
            if min(a, b, c, d) >= 0:
                faces.append((int(a), int(d), int(c), int(b)))  # (counter-clockwise from the front: the normal faces +z)
    gm = bpy.data.meshes.new("relief")
    gm.from_pydata(verts, [], faces)
    gm.update()
    for poly in gm.polygons:
        poly.use_smooth = True
    go = bpy.data.objects.new("relief", gm)
    sc.collection.objects.link(go)
    bpy.ops.object.select_all(action="DESELECT")
    go.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
me = ob.data

# --- materials: metal everywhere, the artwork on the front face (UVs = the image's own pixels)
spec = job.get("material", "gold")
cfg = METALS.get(spec, METALS["gold"]) if isinstance(spec, str) else spec
# the EDGE (sides + bevel) may differ from the face's metal (--edge): a gold face on a dark enamel rim, a silver rim
edge = job.get("edge")
if isinstance(edge, str) and edge.startswith("#") and len(edge) == 7:
    lin = [((int(edge[i:i + 2], 16) / 255) ** 2.2) for i in (1, 3, 5)]  # (sRGB -> linear: Blender colours are linear)
    ecfg = {"base": lin, "metallic": 0.15, "roughness": 0.4}
else:
    ecfg = METALS.get(edge, cfg) if edge else cfg
metal = bpy.data.materials.new("metal")
metal.use_nodes = True
b = metal.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = tuple(ecfg["base"]) + (1.0,)
b.inputs["Metallic"].default_value = float(ecfg.get("metallic", 1.0))
b.inputs["Roughness"].default_value = float(ecfg.get("roughness", 0.25))
if "Coat Weight" in b.inputs:
    b.inputs["Coat Weight"].default_value = 0.3
me.materials.append(metal)
def art_material(name, path):
    """a printed face: the picture on the kit's own UV map, a little metal, a coat by --gloss"""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    fb = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "uv"  # (a converted curve already carries its own UV layer: name ours, or the face samples that one)
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], fb.inputs["Base Color"])
    gloss = min(1.0, max(0.0, float(job.get("gloss", 0.5))))
    fb.inputs["Metallic"].default_value = float(job.get("face_metallic", 0.2))
    # (0.3 burnt to white facing the key; a matte print is rough too: gloss 0.5 -> 0.45, gloss 0.1 -> 0.69)
    fb.inputs["Roughness"].default_value = float(job.get("face_roughness", 0.75 - 0.6 * gloss))
    if "Coat Weight" in fb.inputs:
        fb.inputs["Coat Weight"].default_value = gloss  # (a printed logo ~0.1, a lacquered card 0.5)
    # where the art is TRANSPARENT (a gap the silhouette closed, e.g. between a figure's legs) the face shows the metal
    # backing, not the transparent pixels' colour (it printed grey there)
    # (the backing is the EDGE material: a gap the outline bridged reads as the rim — with a dark --edge it sinks away
    # instead of glowing gold between a figure's legs)
    mb = nt.nodes.new("ShaderNodeBsdfPrincipled")
    mb.inputs["Base Color"].default_value = tuple(ecfg["base"]) + (1.0,)
    mb.inputs["Metallic"].default_value = float(ecfg.get("metallic", 1.0))
    mb.inputs["Roughness"].default_value = float(ecfg.get("roughness", 0.25))
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(mb.outputs["BSDF"], mix.inputs[1])
    nt.links.new(fb.outputs["BSDF"], mix.inputs[2])
    out = nt.nodes["Material Output"]
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return m


if job.get("face", True) and os.path.isfile(job["image"]):
    me.materials.append(art_material("face", job["image"]))
    back = job.get("back")
    if back and os.path.isfile(back):  # a second picture on the reverse (a card's back: --back)
        me.materials.append(art_material("back", back))
    for old_uv in list(me.uv_layers):  # (a converted curve brings its own layer; Roblox and most engines read the FIRST)
        me.uv_layers.remove(old_uv)
    uv = me.uv_layers.new(name="uv")
    uv.active = uv.active_render = True
    for poly in me.polygons:
        is_back = back and poly.normal.z < -0.6
        on_relief = grid is not None and poly.center.z > FRONT + 0.001 and poly.normal.z > 0.0  # (a relief slope still shows the art)
        poly.material_index = 1 if (poly.normal.z > 0.6 or on_relief) else 2 if is_back else 0
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            u = v.x / (w * unit)
            # the back is seen from behind: mirror it, so its picture reads the right way round when the piece turns
            uv.data[li].uv = ((-u if is_back else u) + 0.5, v.y / (h * unit) + 0.5)

# --- render setup: Cycles on the GPU, transparent film, the kit's rig
sc.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            sc.cycles.device = "GPU"
            break
        except Exception:
            continue
except Exception:
    pass
res = int(job.get("res", 384))
sc.cycles.samples = int(job.get("samples", 24))
sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = res
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "Standard"
sc.view_settings.exposure = float(job.get("exposure", 0.0))  # (a big flat face toward the key burns: a card wants about -0.8)
world = bpy.data.worlds.new("w")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.2, 0.2, 0.24, 1.0)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.5


def light(name, loc, energy, color, size):
    import mathutils
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.color, ld.size = energy, color, size
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (-mathutils.Vector(loc)).to_track_quat("-Z", "Y").to_euler()


light("key", (-2.5, 2.5, 4.0), 560, (1.0, 0.93, 0.82), 3.0)
light("rim", (3.0, -0.5, 2.5), 500, (0.75, 0.85, 1.0), 2.0)
light("top", (0.0, 3.5, 2.0), 300, (1.0, 1.0, 1.0), 4.0)
cam = bpy.data.cameras.new("cam")
cam.type = "ORTHO"
cam.ortho_scale = 2.5
co = bpy.data.objects.new("cam", cam)
sc.collection.objects.link(co)
co.location = (0, 0, 10)
sc.camera = co

# --- the turntable: a full spin (a coin, an emblem), a sway (a card catching the light), a flip (back -> face, once), or a land (a medal spinning down to rest, once)
os.makedirs(job["out"], exist_ok=True)
n = int(job.get("frames", 24))  # (0: the mesh only, no turntable)
rots = job.get("rotations")  # (the motion as data, from kit/ui/spin.py; the branches below serve older jobs)
for i in range(n):
    t = i / n
    if rots:
        ob.rotation_euler = tuple(rots[i])
    elif job.get("motion", "spin") == "sway":
        ob.rotation_euler = (math.radians(8 * math.sin(2 * math.pi * t)), math.radians(28 * math.sin(2 * math.pi * t)), 0)
    elif job.get("motion") == "land":
        # a medal arriving, played ONCE: three turns spinning down to a stop face-on, a wobble that dies out
        e = 1 - (1 - t) ** 3
        ob.rotation_euler = (math.radians(14 * math.sin(6 * math.pi * t) * (1 - t)), 3 * 2 * math.pi * (1 - e), 0)
    elif job.get("motion") == "flip":
        # a reveal, played ONCE: the back held, a turn that eases out (a small overshoot), the face settles
        k = min(1.0, max(0.0, (t - 0.15) / 0.6))
        e = 1 - (1 - k) ** 3
        over = math.sin(math.pi * min(1.0, max(0.0, (t - 0.6) / 0.4))) * 0.12 * (1 - k * 0.5)
        ob.rotation_euler = (math.radians(10 * math.sin(math.pi * k)), math.pi * (1 + e) + over, 0)
    else:
        ob.rotation_euler = (0, 2 * math.pi * t, 0)
    sc.render.filepath = os.path.join(job["out"], f"f_{i:03d}.png")
    bpy.ops.render.render(write_still=True)
ob.rotation_euler = (0, 0, 0)
if job.get("fbx"):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.export_scene.fbx(filepath=job["fbx"], use_selection=True, object_types={"MESH"}, apply_unit_scale=True, path_mode="COPY", embed_textures=True)
print("SPIN_DONE", n)
