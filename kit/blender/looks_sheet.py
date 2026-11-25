"""looks_sheet.py — every LOOK (rbx.look, kit/materials/looks.json) on a bevelled block, BUILT AND BAKED like any asset
(its scan, its pattern, its colour variation and a life all on it), in one lit picture — so a surface is chosen by
LOOKING, not from a list of numbers. Run by `lune run kit materials --looks --sheet` (Blender, headless):

    blender -b --factory-startup --python-exit-code 2 -P kit/blender/looks_sheet.py -- --no-preview
        [--out build/materials/looks] [--life used]

  -> <out>/sheet_raw.png + <out>/sheet.json (each block's place, its look and values); kit/blender/material_labels.py
     <out>/sheet.json then writes <out>/sheet.png with every look's name under its block.
The blocks are 80 mm (real_scale 100 mm a stud), turned so a top, a side and the edges between show — where a life
burnishes, chips and rubs.
"""

import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import rbx  # noqa: E402
import rbx_looks  # noqa: E402

COLS, STEP, BLOCK = 6, 1.4, 0.8   # (studs: 6 a row, 140 mm apart, 80 mm blocks at 100 mm a stud)


def _arg(flag, default):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _world(scene):
    """the material sheet's sky: a dark floor up to a bright top (metals need something to reflect)"""
    w = bpy.data.worlds.new("LooksSky")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    coord, sep = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp, bg, out = nt.nodes.new("ShaderNodeValToRGB"), nt.nodes.new("ShaderNodeBackground"), nt.nodes.new(
        "ShaderNodeOutputWorld")
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.35, (0.03, 0.03, 0.035, 1)
    els[1].position, els[1].color = 0.75, (0.9, 0.92, 0.95, 1)
    mid = els.new(0.52)
    mid.color = (0.22, 0.22, 0.24, 1)
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def main():
    out_dir = _arg("--out", os.path.join(REPO, "build", "materials", "looks"))
    out_dir = out_dir if os.path.isabs(out_dir) else os.path.join(REPO, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    life = _arg("--life", "used")
    names = [n for n, _a, _s in rbx_looks.looks()]
    rows = math.ceil(len(names) / COLS)
    a = rbx.Asset("_looks_sheet", tex=2048, size=(COLS * STEP, rows * STEP, 1.0), ground=False,
                  allow_floating=[f"L{i:02d}" for i in range(len(names))])
    a.real_scale(100.0)
    spots = []
    for i, name in enumerate(names):
        r, c = divmod(i, COLS)
        kw = rbx_looks.look(name)
        extra = {"grain": (0, 1, 0)} if kw.get("pattern") == "endgrain" else {}
        a.material(name, **kw, life=None if life == "none" else life, **extra)
        x, y = (c - (COLS - 1) / 2) * STEP, (rows - 1 - r) * STEP
        a.box(f"L{i:02d}", (BLOCK, BLOCK, BLOCK), (x, y, 0), name, rot=(-25, 35, 0), bevel=0.06)
        spots.append({"name": name, "x_studs": x, "y_studs": y, "metal": kw["metal"], "rough": round(kw["rough"], 2)})
    a.build()

    # the sheet: the BAKED blocks (each group carries its baked maps now), straight on, in the sheet's own light
    sc = bpy.context.scene
    for o in list(sc.objects):
        if o.type in ("CAMERA", "LIGHT"):
            o.hide_render = True
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = engine
            break
        except TypeError:
            continue
    _world(sc)
    w_world, h_world = COLS * STEP, rows * STEP
    px_w = 2000
    px_h = int(px_w * h_world / w_world)
    sc.render.resolution_x, sc.render.resolution_y = px_w, px_h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    cam = bpy.data.objects.new("LooksCam", bpy.data.cameras.new("LooksCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type, cam.data.ortho_scale, cam.data.sensor_fit = "ORTHO", w_world, "HORIZONTAL"
    centre_z = (rows - 1) * STEP / 2 - 0.12   # (Roblox y up = Blender z)
    cam.location = (0.0, -30.0, centre_z)
    cam.rotation_euler = (math.radians(90), 0, 0)
    cam.data.clip_end = 100.0
    sun = bpy.data.objects.new("LooksKey", bpy.data.lights.new("LooksKey", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), math.radians(-35), math.radians(-20))
    sc.collection.objects.link(sun)
    for s in spots:   # (where each name goes, in pixels from the top-left: under its block)
        s["x"] = round((s["x_studs"] + w_world / 2) / w_world * px_w)
        s["y"] = round((centre_z + h_world / 2 - (s["y_studs"] - BLOCK * 0.78)) / h_world * px_h)
    raw = os.path.join(out_dir, "sheet_raw.png")
    sc.render.filepath = raw
    bpy.ops.render.render(write_still=True)
    with open(os.path.join(out_dir, "sheet.json"), "w", encoding="utf-8") as fh:
        json.dump({"picture": raw, "size": [px_w, px_h], "spots": spots, "life": life}, fh, indent=1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"looks sheet: {len(names)} looks built and baked "
                      f"(life {life})", "next_action": "label it: python kit/blender/material_labels.py "
                      f"{os.path.relpath(os.path.join(out_dir, 'sheet.json'), REPO)}", "sheet": raw,
                      "meta": os.path.join(out_dir, "sheet.json")}))


main()
