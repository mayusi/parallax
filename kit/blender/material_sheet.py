"""material_sheet.py — EVERY measured material (kit/materials/physicallybased.json) on a sphere, as a build gets it
(rbx.real(): its colour, metalness, roughness), in one lit picture — so a material is chosen by LOOKING, not from a
list of numbers. Run by `lune run kit materials --sheet` (Blender, headless):

    blender -b --factory-startup --python-exit-code 2 -P kit/blender/material_sheet.py -- [--out build/materials]

  -> <out>/sheet_raw.png + <out>/sheet.json (each sphere's place in the picture, its name and values); then
     kit/blender/material_labels.py writes <out>/sheet.png with every name under its sphere.
Lighting: a sky that runs from a dark floor to a bright top (metals need something to reflect, as in the kit's own
studio), a key sun from the upper left and a soft fill.
"""

import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import rbx_materials  # noqa: E402

COLS, STEP_X, STEP_Y, R = 10, 1.25, 1.55, 0.5


def _arg(flag, default):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _world(scene):
    w = bpy.data.worlds.new("SheetSky")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.35, (0.03, 0.03, 0.035, 1)
    els[1].position, els[1].color = 0.75, (0.9, 0.92, 0.95, 1)
    mid = els.new(0.52)
    mid.color = (0.22, 0.22, 0.24, 1)
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def main():
    out_dir = _arg("--out", os.path.join(REPO, "build", "materials"))
    out_dir = out_dir if os.path.isabs(out_dir) else os.path.join(REPO, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    lib = rbx_materials.load()
    names = sorted(lib, key=lambda n: ((lib[n].get("category") or ["~"])[0], n))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = engine
            break
        except TypeError:
            continue
    _world(sc)
    rows = math.ceil(len(names) / COLS)
    w_world, h_world = COLS * STEP_X, rows * STEP_Y
    px_w = 2000
    px_h = int(px_w * h_world / w_world)
    sc.render.resolution_x, sc.render.resolution_y = px_w, px_h
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX" if "AgX" in [v.identifier for v in sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    cam = bpy.data.objects.new("SheetCam", bpy.data.cameras.new("SheetCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = w_world
    cam.data.sensor_fit = "HORIZONTAL"  # the picture is taller than wide: the scale is its WIDTH (else columns are cut)
    cam.location = (0.0, -20.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sun = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), math.radians(-35), math.radians(-20))
    sc.collection.objects.link(sun)
    spots = []
    for i, name in enumerate(names):
        r, c = divmod(i, COLS)
        x = (c - (COLS - 1) / 2) * STEP_X
        z = h_world / 2 - (r + 0.42) * STEP_Y
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=R, location=(x, 0, z))
        o = bpy.context.object
        bpy.ops.object.shade_smooth()
        v = rbx_materials.real(name)
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        p = m.node_tree.nodes["Principled BSDF"]
        p.inputs["Base Color"].default_value = (*v["color"], 1.0)
        p.inputs["Metallic"].default_value = v["metal"]
        p.inputs["Roughness"].default_value = v["rough"]
        o.data.materials.append(m)
        # where the label goes (pixels, from the top-left): under the sphere
        u = (x + w_world / 2) / w_world
        t = (h_world / 2 - (z - R * 1.08)) / h_world
        spots.append({"name": name, "x": round(u * px_w), "y": round(t * px_h), "metal": v["metal"],
                      "rough": round(v["rough"], 2), "category": (lib[name].get("category") or [""])[0]})
    raw = os.path.join(out_dir, "sheet_raw.png")
    sc.render.filepath = raw
    bpy.ops.render.render(write_still=True)
    with open(os.path.join(out_dir, "sheet.json"), "w", encoding="utf-8") as fh:
        json.dump({"picture": raw, "size": [px_w, px_h], "spots": spots}, fh, indent=1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"material sheet: {len(names)} materials rendered",
                      "next_action": "label it: python kit/blender/material_labels.py", "sheet": raw,
                      "meta": os.path.join(out_dir, "sheet.json")}))


main()
