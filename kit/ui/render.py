"""render.py — UI pieces RENDERED in Blender (headless), not drawn by the engine or by PIL.

    blender -b --factory-startup --python-exit-code 2 -P kit/ui/render.py -- --spec <x.render.json> --out <x.png>

A hero HUD is painted art: a chrome-bevelled logotype, a lit metal plate, a glowing emblem. Enum.Font + a flat tint
cannot be that; a Cycles render can. The spec (assets/ui/art/<identity>/<name>.render.json):

{
  "size": [1024, 1024],              // output pixels, transparent film
  "samples": 96,
  "material": "chrome_gold",         // chrome_gold | chrome_silver | chrome_red | black_steel | custom {base, roughness}
  "depth": 0.10,                     // extrusion (text thickness) in scene units (a glyph of scale 1 is ~1 unit tall)
  "bevel": 0.025,                    // bevel depth: the chisel edge that catches light
  "outline": 0.035,                  // a black outline shell behind the glyphs (0 = none)
  "glow": 0.0,                       // emission strength of the base colour (a hot logotype)
  "items": [                         // text pieces, placed in scene units from the centre
    {"text": "S", "font": "GrenzeGotisch", "scale": 1.0, "x": 0, "y": 0, "rot": -6},
    {"text": "S", "font": "GrenzeGotisch", "scale": 0.62, "x": 0.95, "y": -0.42, "rot": -6}
  ]                                  // a text item's "tracking": letter-spacing (1.0 = the font's own)
}

"font" is an Enum.Font name: the TTF comes from the kit's font cache (kit ui fonts fetched it) via kit/ui/fonts.json.
A "gem" item is ONE glass cell for a gauge: {"gem": true, "size": [2.0, 0.62], "color": [r, g, b], "lit": true,
"glow": 4, "halo": 0.5, "bevel": 0.06} — a bevelled glowing slab in a thin dark lip with a soft halo past it (unlit:
smoked dark glass, no halo); the render writes <out>.anchors.json {"gem": {x, y, w, h}} = the slab inside the picture,
so kit ui gauge can stretch the picture until the slab covers a well ("cells": {"art_lit", "art_unlit"}).
A "gauge" item is a metal gauge plate: slanted troughs of inset cells with a spiked end cap, stacked rows —
{"gauge": true, "rows": [{"cells": 9, "length": 4.2}, {"cells": 5, "length": 2.2}], "cell": [0.42, 0.26], "gap": 0.05,
 "lean": 0.35, "row_gap": 0.14, "cap": "spike" | "horn" (a crescent curl, `horn_lift`), "cap_left": "horn", "frame": "black_steel" | {base, roughness, metallic},
 "frame_pad": 0.06, "bow": 0.1 (the row sweeps up at its middle), "taper": 0.35 (thinner at the right end), a row's own "cell": [w, h]} — and the render writes <out>.anchors.json:
every cell's rectangle in OUTPUT PIXELS, so the screen can lay its live fill cells exactly over the wells
(kit ui gauge <Screen> does that). A "ring" item draws broken energy strokes (the style-rank swirl, an aura): {"ring": true, "radius": 1.0, "strokes": 7,
"width": 0.03, "color": [1.0, 0.5, 0.12], "glow": 14, "seed": 3, "squash": 0.9, "tilt": 15} — thin bright arcs with a
wide faint halo each, random lengths and gaps, no fill: the letters show through.
Light rig: a warm key, a cool rim, a bright strip above and a dark floor below so chrome reads as chrome (banded
reflections). Camera: orthographic, fitted to the pieces with a margin. Output: PNG RGBA.
"""
import json
import math
import os
import sys

import bpy  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MATERIALS = {
    "chrome_gold": {"base": (1.0, 0.68, 0.18), "roughness": 0.18, "metallic": 1.0},
    "chrome_silver": {"base": (0.86, 0.86, 0.90), "roughness": 0.16, "metallic": 1.0},
    "chrome_red": {"base": (0.85, 0.10, 0.08), "roughness": 0.20, "metallic": 0.9},
    "black_steel": {"base": (0.05, 0.05, 0.06), "roughness": 0.45, "metallic": 0.9},
}


def cache_root():
    return os.environ.get("ROBLOX_KIT_CACHE") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit")


def resolve_font(name):
    """Enum.Font name -> a TTF in the kit's font cache (kit ui fonts), via kit/ui/fonts.json"""
    if os.path.isfile(name):
        return name
    with open(os.path.join(HERE, "fonts.json"), encoding="utf-8") as fh:
        table = json.load(fh)
    entry = (table.get("fonts") or {}).get(name)
    if not entry:
        raise SystemExit(f"render: unknown font {name!r} — an Enum.Font name from kit/ui/fonts.json")
    fam = (table.get("families") or {}).get(entry.get("family"), {})
    if fam.get("system"):
        win = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", entry.get("system", ""))
        if os.path.isfile(win):
            return win
    folder = os.path.join(cache_root(), "fonts", fam.get("folder", entry.get("family", "")))
    if not os.path.isdir(folder):
        raise SystemExit(f"render: font {name} is not fetched — lune run kit ui fonts (looked in {folder})")
    ttfs = sorted(f for f in os.listdir(folder) if f.lower().endswith((".ttf", ".otf")))
    if not ttfs:
        raise SystemExit(f"render: no TTF in {folder}")
    # an upright face unless the entry says italic: a variable family ships Name-Italic[wght].ttf beside Name[wght].ttf
    # and the sorted list put the Italic first, so 13 faces rendered slanted (audit 2026-10-16)
    upright = [f for f in ttfs if ("italic" in f.lower()) == bool(entry.get("italic"))]
    ttfs = upright or ttfs
    want = entry.get("weight", 400)
    # prefer a static file whose name carries the wanted weight, else the variable font, else the first
    names = {"Bold": 700, "SemiBold": 600, "Medium": 500, "Regular": 400, "Light": 300, "Black": 900}
    best = None
    for f in ttfs:
        for tag, w in names.items():
            if tag in f and w == want:
                best = f
    if best is None:
        best = next((f for f in ttfs if "[" in f), ttfs[0])
    return os.path.join(folder, best)


def material(spec):
    m = spec.get("material", "chrome_gold")
    cfg = MATERIALS.get(m) if isinstance(m, str) else m
    if not cfg:
        raise SystemExit(f"render: material must be one of {sorted(MATERIALS)} or {{base, roughness, metallic}}")
    mat = bpy.data.materials.new("piece")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    base = tuple(cfg["base"]) + (1.0,)
    bsdf.inputs["Base Color"].default_value = base
    if spec.get("horizon", True):
        b = cfg["base"]
        tex = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (1.0, float(spec.get("horizon_scale", 0.9)), 1.0)
        mapping.inputs["Location"].default_value = (0.0, float(spec.get("horizon_offset", 0.55)), 0.0)
        grad = nodes.new("ShaderNodeTexGradient")
        ramp = nodes.new("ShaderNodeValToRGB")
        cr = ramp.color_ramp
        cr.interpolation = "LINEAR"
        light = (min(1, b[0] * 0.5 + 0.55), min(1, b[1] * 0.5 + 0.55), min(1, b[2] * 0.5 + 0.5), 1.0)
        dark = (b[0] * 0.22, b[1] * 0.16, b[2] * 0.08, 1.0)
        cr.elements[0].position, cr.elements[0].color = 0.0, (b[0] * 0.75, b[1] * 0.7, b[2] * 0.5, 1.0)
        cr.elements[1].position, cr.elements[1].color = 1.0, light
        e = cr.elements.new(0.46)
        e.color = light
        e = cr.elements.new(0.52)
        e.color = dark
        e = cr.elements.new(0.6)
        e.color = base
        links.new(tex.outputs["Object"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
        # the gradient runs along the object's Y (up the glyph): read the Y component
        sep = nodes.new("ShaderNodeSeparateXYZ")
        links.new(mapping.outputs["Vector"], sep.inputs["Vector"])
        links.new(sep.outputs["Y"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = float(cfg.get("metallic", 1.0))
    bsdf.inputs["Roughness"].default_value = float(cfg.get("roughness", 0.2))
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.4
    glow = float(spec.get("glow", 0))
    if glow > 0 and "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = base
        bsdf.inputs["Emission Strength"].default_value = glow
    return mat


def outline_material():
    mat = bpy.data.materials.new("outline")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    # pure INK: a metallic outline shell reflected the key light and rendered as a mid-grey slab behind every chrome
    # logotype (three judge pairs called it "a grey card / WordArt plate") — no reflection, no specular
    bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.0
    return mat


def emissive(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = tuple(color) + (1.0,)
    em.inputs["Strength"].default_value = strength
    mat.node_tree.links.new(em.outputs[0], out.inputs[0])
    return mat


def text_object(name, item, depth, bevel, offset, mat):
    cu = bpy.data.curves.new(name, type="FONT")
    cu.body = item["text"]
    cu.font = bpy.data.fonts.load(resolve_font(item.get("font", "GothamBold")))
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    # "tracking": letter-spacing as Blender's character spacing (1.0 = the font's own; inscriptional caps want ~1.15)
    cu.space_character = float(item.get("tracking", 1.0))
    cu.extrude = depth / 2
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    cu.offset = offset
    cu.fill_mode = "BOTH"
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    s = float(item.get("scale", 1.0))
    ob.scale = (s, s, s)
    ob.location = (float(item.get("x", 0)), float(item.get("y", 0)), float(item.get("z", 0)))
    ob.rotation_euler = (0.0, 0.0, math.radians(float(item.get("rot", 0))))
    ob.data.materials.append(mat)
    return ob


def ring_object(name, item, index):
    """broken emissive arcs around the centre: the energy swirl behind a rank letter"""
    import random
    import mathutils
    rnd = random.Random(int(item.get("seed", 1)) * 97 + index)
    r = float(item.get("radius", 1.0))
    squash = float(item.get("squash", 1.0))
    width = float(item.get("width", 0.03))
    color = tuple(item.get("color", (1.0, 0.5, 0.12)))
    glow = float(item.get("glow", 12))
    n = int(item.get("strokes", 7))
    tilt = math.radians(float(item.get("tilt", 0)))
    made = []
    for k in range(n):
        a0 = rnd.uniform(0, 2 * math.pi)
        span = rnd.uniform(0.6, 1.9)
        rr = r * rnd.uniform(0.9, 1.08)
        for halo in (False, True):
            cu = bpy.data.curves.new(f"{name}_{k}{'h' if halo else ''}", type="CURVE")
            cu.dimensions = "3D"
            cu.bevel_depth = width * (3.2 if halo else 1.0)
            cu.bevel_resolution = 3
            cu.use_fill_caps = True
            sp = cu.splines.new("NURBS")
            pts = 24
            sp.points.add(pts - 1)
            for i in range(pts):
                t = i / (pts - 1)
                a = a0 + span * t
                # taper: the stroke thins at both ends through the radius wobble
                wob = 1 + 0.02 * math.sin(t * math.pi * 3 + k)
                x, y = math.cos(a) * rr * wob, math.sin(a) * rr * squash * wob
                sp.points[i].co = (x, y, -0.3 + 0.02 * k, 1.0)
                sp.points[i].radius = math.sin(t * math.pi) ** 0.6 + 0.05
            sp.use_endpoint_u = True
            sp.order_u = 4
            ob = bpy.data.objects.new(cu.name, cu)
            bpy.context.scene.collection.objects.link(ob)
            ob.rotation_euler = (0.0, 0.0, tilt)
            mat = bpy.data.materials.new(cu.name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            nodes.clear()
            out = nodes.new("ShaderNodeOutputMaterial")
            em = nodes.new("ShaderNodeEmission")
            hot = (min(1, color[0] * 1.05 + 0.1), min(1, color[1] * 0.95 + 0.12), min(1, color[2] * 0.8 + 0.08))
            em.inputs["Color"].default_value = (tuple(color) if halo else hot) + (1.0,)
            em.inputs["Strength"].default_value = glow * (0.12 if halo else 1.0)
            if halo:
                mix = nodes.new("ShaderNodeMixShader")
                tr = nodes.new("ShaderNodeBsdfTransparent")
                mix.inputs[0].default_value = 0.35
                mat.node_tree.links.new(tr.outputs[0], mix.inputs[1])
                mat.node_tree.links.new(em.outputs[0], mix.inputs[2])
                mat.node_tree.links.new(mix.outputs[0], out.inputs[0])
                mat.blend_method = "BLEND" if hasattr(mat, "blend_method") else None
            else:
                mat.node_tree.links.new(em.outputs[0], out.inputs[0])
            ob.data.materials.append(mat)
            made.append(ob)
    return made


def gauge_objects(name, item, index, anchors):
    """metal troughs of inset cells, slanted, with a spiked cap at the right end; records each cell's scene rect"""
    import bmesh
    import mathutils
    frame_cfg = item.get("frame", "black_steel")
    frame_cfg = frame_cfg if isinstance(frame_cfg, dict) else MATERIALS.get(frame_cfg, MATERIALS["black_steel"])
    wear = float(item.get("wear", 0.6))
    horizon = bool(item.get("horizon", True))

    def frame_material(tag, y_top, y_bot):
        """the frame's metal: a reflected-horizon band across the trough (y_top..y_bot, scene units) x grime"""
        frame = bpy.data.materials.new(f"{name}_frame{tag}")
        frame.use_nodes = True
        fn, fl = frame.node_tree.nodes, frame.node_tree.links
        fb = fn["Principled BSDF"]
        b = frame_cfg["base"]
        fb.inputs["Base Color"].default_value = tuple(b) + (1.0,)
        colour = None  # the socket that becomes Base Color
        if horizon and y_top != y_bot:
            tex = fn.new("ShaderNodeTexCoord")
            sep = fn.new("ShaderNodeSeparateXYZ")
            fl.new(tex.outputs["Object"], sep.inputs["Vector"])
            m = fn.new("ShaderNodeMath")          # fac = (y - y_bot) / (y_top - y_bot): 0 at the bottom, 1 at the top
            m.operation = "MULTIPLY_ADD"
            m.inputs[1].default_value = 1.0 / (y_top - y_bot)
            m.inputs[2].default_value = -y_bot / (y_top - y_bot)
            fl.new(sep.outputs["Y"], m.inputs[0])
            ramp = fn.new("ShaderNodeValToRGB")
            cr = ramp.color_ramp
            cr.interpolation = "LINEAR"
            light = (min(1, b[0] * 0.5 + 0.55), min(1, b[1] * 0.5 + 0.55), min(1, b[2] * 0.5 + 0.5), 1.0)
            dark = (b[0] * 0.22, b[1] * 0.16, b[2] * 0.08, 1.0)
            cr.elements[0].position, cr.elements[0].color = 0.0, (b[0] * 0.75, b[1] * 0.7, b[2] * 0.5, 1.0)
            cr.elements[1].position, cr.elements[1].color = 1.0, light
            e = cr.elements.new(0.44)
            e.color = light
            e = cr.elements.new(0.5)
            e.color = dark
            e = cr.elements.new(0.6)
            e.color = tuple(b) + (1.0,)
            fl.new(m.outputs[0], ramp.inputs["Fac"])
            colour = ramp.outputs["Color"]
        if wear > 0:
            tex2 = fn.new("ShaderNodeTexCoord")
            noise = fn.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = float(item.get("wear_scale", 18.0))  # 18 = blotchy grime; ~50 = a fine brushed grain
            noise.inputs["Detail"].default_value = 8.0
            noise.inputs["Roughness"].default_value = 0.7
            fl.new(tex2.outputs["Object"], noise.inputs["Vector"])
            bump = fn.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = 0.25 * wear
            bump.inputs["Distance"].default_value = 0.02
            fl.new(noise.outputs["Fac"], bump.inputs["Height"])
            fl.new(bump.outputs["Normal"], fb.inputs["Normal"])
            # grime: the noise darkens the metal and roughens it in patches (a grey multiplier over the colour)
            grime = fn.new("ShaderNodeValToRGB")
            grime.color_ramp.elements[0].position = 0.35
            grime.color_ramp.elements[0].color = (1 - 0.65 * wear,) * 3 + (1.0,)
            grime.color_ramp.elements[1].position = 0.75
            grime.color_ramp.elements[1].color = (1.0 + 0.3 * wear,) * 3 + (1.0,)
            fl.new(noise.outputs["Fac"], grime.inputs["Fac"])
            if colour is not None:
                mix = fn.new("ShaderNodeMixRGB")
                mix.blend_type = "MULTIPLY"
                mix.inputs["Fac"].default_value = 1.0
                fl.new(colour, mix.inputs["Color1"])
                fl.new(grime.outputs["Color"], mix.inputs["Color2"])
                colour = mix.outputs["Color"]
            else:
                mix = fn.new("ShaderNodeMixRGB")
                mix.blend_type = "MULTIPLY"
                mix.inputs["Fac"].default_value = 1.0
                mix.inputs["Color1"].default_value = tuple(b) + (1.0,)
                fl.new(grime.outputs["Color"], mix.inputs["Color2"])
                colour = mix.outputs["Color"]
            rough = fn.new("ShaderNodeMath")
            rough.operation = "MULTIPLY_ADD"
            rough.inputs[1].default_value = 0.35 * wear
            rough.inputs[2].default_value = max(0.5, float(frame_cfg.get("roughness", 0.3))) - 0.15
            fl.new(noise.outputs["Fac"], rough.inputs[0])
            fl.new(rough.outputs[0], fb.inputs["Roughness"])
        if colour is not None:
            fl.new(colour, fb.inputs["Base Color"])
        # a gauge frame is worn dark steel: less mirror than a logotype, so the bright strip reads as a highlight edge
        fb.inputs["Metallic"].default_value = min(0.6, float(frame_cfg.get("metallic", 1.0)))
        fb.inputs["Roughness"].default_value = max(0.5, float(frame_cfg.get("roughness", 0.3)))
        return frame

    frame = frame_material("", 0.0, 0.0)  # the caps' fallback (no band)
    well = bpy.data.materials.new(f"{name}_well")
    well.use_nodes = True
    wb = well.node_tree.nodes["Principled BSDF"]
    wb.inputs["Base Color"].default_value = (0.006, 0.008, 0.006, 1.0)
    wb.inputs["Metallic"].default_value = 0.0
    wb.inputs["Roughness"].default_value = 0.92
    wb.inputs["Specular IOR Level"].default_value = 0.15 if "Specular IOR Level" in wb.inputs else None
    cw, ch = item.get("cell", [0.42, 0.26])
    gap = float(item.get("gap", 0.05))
    lean = float(item.get("lean", 0.35))  # the x run per unit height (parallelogram)
    row_gap = float(item.get("row_gap", 0.14))
    cap = item.get("cap", "spike")
    thick = float(item.get("depth", 0.09))
    made = []
    y = 0.0
    x_origin = float(item.get("x", 0.0))
    y_origin = float(item.get("y", 0.0))

    def slab(nm, x0, y0, x1, y1, z, h, mat, shear, nx=1):
        """a leaning slab from (x0,y0) to (x1,y1), height h in z, top at z; `nx` cuts along x (so a warp can bend it)"""
        bm = bmesh.new()
        verts = []
        for zz in (z - h, z):
            for (xx, yy) in ((x0, y0), (x1, y0), (x1 + shear * (y1 - y0), y1), (x0 + shear * (y1 - y0), y1)):
                verts.append(bm.verts.new((xx, yy, zz)))
        bm.verts.ensure_lookup_table()
        faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        for f in faces:
            try:
                bm.faces.new([verts[i] for i in f])
            except ValueError:
                pass
        if nx > 1:
            long_edges = [e for e in bm.edges if abs(e.verts[0].co.x - e.verts[1].co.x) > 0.5 * abs(x1 - x0)]
            bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=nx - 1, use_grid_fill=True)
        bm.normal_update()
        me = bpy.data.meshes.new(nm)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(nm, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width = min(0.03, h * 0.4)
        bev.segments = 3
        return ob

    import math
    pad = float(item.get("frame_pad", 0.06))      # frame above / below a well (0.06 = the character-action trough; thin bars ~0.03)
    bow = float(item.get("bow", 0.0))             # scene units the row rises at its middle (a gentle sweep)
    taper = float(item.get("taper", 0.0))         # 0..1: how much thinner the row is at its right end
    cap_left = item.get("cap_left", "none")       # "horn": the left end curls too (a crescent both ends)

    def warp(ob, x0, x1, yc):
        """bend a row piece: y += bow * sin(pi t), heights scale by (1 - taper t), t along the row"""
        if bow == 0 and taper == 0:
            return
        span = max(1e-6, x1 - x0)
        for v in ob.data.vertices:
            t = min(1.0, max(0.0, (v.co.x - x0) / span))
            v.co.y = yc + (v.co.y - yc) * (1.0 - taper * t) + bow * math.sin(math.pi * t)

    for r, row in enumerate(item.get("rows") or []):
        n = int(row.get("cells", 8))
        cw_, ch_ = row.get("cell", [cw, ch])
        length = float(row.get("length", n * (cw_ + gap) + 0.3))
        y0 = y_origin - y
        y1 = y0 - ch_ - 2 * pad - 0.06
        yc = (y0 + y1) / 2
        x0 = x_origin
        x1 = x0 + length
        nx = 24 if (bow or taper) else 1
        frame = frame_material(str(r), y0, y1)  # the band across THIS trough (rims, wells' frame and cap share it)
        row_pieces = [slab(f"{name}_trough{r}", x0, y0, x1, y1, 0.0, thick, frame, lean, nx)]
        rim = float(item.get("rim", 0.035))
        if rim > 0:
            row_pieces.append(slab(f"{name}_rimtop{r}", x0, y0, x1, y0 - rim, 0.025, thick * 0.3, frame, lean, nx))
            row_pieces.append(slab(f"{name}_rimbot{r}", x0, y1 + rim, x1, y1, 0.025, thick * 0.3, frame, lean, nx))
        # the cells: wells sunk into the trough
        cx = x0 + float(item.get("first_cell_at", 0.14))
        row_anchor = []
        for c in range(n):
            wx0, wx1 = cx, cx + cw_
            wy1, wy0 = y1 + 0.03 + pad, y0 - 0.03 - pad
            row_pieces.append(slab(f"{name}_well{r}_{c}", wx0, wy0, wx1, wy1, 0.02, thick * 0.5, well, lean))
            # the well's parallelogram leans with the trough: its top edge sits at wy0 (shear 0 at y0), bottom at wy1
            # — and follows the warp (its centre's bow, its height's taper)
            t = ((wx0 + wx1) / 2 - x0) / max(1e-6, x1 - x0)
            k_ = 1.0 - taper * t
            b_ = bow * math.sin(math.pi * t)
            slope = bow * math.pi / max(1e-6, x1 - x0) * math.cos(math.pi * t)   # dy/dx of the bow (scene, y up)
            row_anchor.append({"x0": wx0 + lean * (wy1 - wy0), "y0": yc + (wy0 - yc) * k_ + b_, "x1": wx1, "y1": yc + (wy1 - yc) * k_ + b_,
                               "rot": round(-math.degrees(math.atan(slope)), 2)})   # Roblox Rotation (clockwise +): rising right = negative
            cx += cw_ + gap
        for ob in row_pieces:
            warp(ob, x0, x1, yc)
        made.extend(row_pieces)
        anchors.append({"row": r, "cells": row_anchor, "lean": lean, "cell": [cw_, ch_]})
        if cap == "spike":
            # a blade-like spike past the right end
            bm = bmesh.new()
            tip = x1 + float(item.get("cap_length", 0.6)) + 0.1 * r
            v = [bm.verts.new(p_) for p_ in ((x1 - 0.05, y1, 0.0), (x1 - 0.05, y0, 0.0), (tip, (y0 + y1) / 2 + 0.05, 0.0),
                                              (x1 - 0.05, y1, -thick * 0.6), (x1 - 0.05, y0, -thick * 0.6), (tip, (y0 + y1) / 2 + 0.05, -thick * 0.6))]
            for f in ((0, 1, 2), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)):
                try:
                    bm.faces.new([v[i] for i in f])
                except ValueError:
                    pass
            me = bpy.data.meshes.new(f"{name}_cap{r}")
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(me.name, me)
            bpy.context.scene.collection.objects.link(ob)
            ob.data.materials.append(frame)
            made.append(ob)
        def horn(x_end, direction, hh, tag):
            # a crescent horn: from the row's end it sweeps out, then curls up and back over the trough, tapering to
            # a point — `cap_length` is its reach, `horn_lift` how far it climbs (row heights); direction +1 = right
            reach = float(item.get("cap_length", 0.6)) + 0.08 * r
            lift = float(item.get("horn_lift", 1.6)) * hh
            segs = int(item.get("horn_segments", 14))
            bm = bmesh.new()
            rings = []
            for i in range(segs + 1):
                t = i / segs
                ang = t * math.pi * 0.85                      # 0 → ~153°: out, up, and back
                px_ = x_end + direction * (-0.05 + reach * math.sin(ang))
                py_ = yc - lift * (1 - math.cos(ang)) / 2
                half = hh * 0.5 * (1.0 - 0.92 * t)              # tapers to a point
                zt = -thick * 0.55 * (1.0 - 0.8 * t)
                rings.append([bm.verts.new(p_) for p_ in ((px_, py_ + half, 0.0), (px_, py_ - half, 0.0),
                                                           (px_, py_ - half, zt), (px_, py_ + half, zt))])
            for a_, b_ in zip(rings, rings[1:]):
                for k in range(4):
                    try:
                        bm.faces.new([a_[k], a_[(k + 1) % 4], b_[(k + 1) % 4], b_[k]])
                    except ValueError:
                        pass
            try:
                bm.faces.new(rings[0])
            except ValueError:
                pass
            me = bpy.data.meshes.new(f"{name}_{tag}{r}")
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(me.name, me)
            bpy.context.scene.collection.objects.link(ob)
            ob.data.materials.append(frame)
            return ob

        if cap == "horn":
            made.append(horn(x1, +1, (y1 - y0) * (1.0 - taper), "horn"))
        if cap_left == "horn":
            made.append(horn(x0, -1, (y1 - y0), "hornl"))
        y += ch_ + 2 * pad + 0.06 + row_gap
    return made


def read_back(path, spec, gem_rects, gauge_anchors):
    """measure the finished picture the way a careful eye would, and name the knob when it is off:
    a gem whose slab clips to white (the colour then comes from the lights, not the glass), a gauge plate whose
    metal reads pale (a mirror steel reflects the lights), a logotype with most of its face clipped"""
    import numpy as np
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]   # Blender's rows run bottom-up
    rgb, alpha = px[:, :, :3], px[:, :, 3]
    notes = []
    kind = "gem" if gem_rects else ("gauge" if gauge_anchors else "text")
    solid = alpha > 0.8
    if not solid.any():
        return ["the picture is empty (no opaque pixel) — check the items' x / y and scale"]
    if kind == "gem":
        cy, cx = h // 2, w // 2
        core = rgb[max(0, cy - 4):cy + 4, max(0, cx - 4):cx + 4].mean(axis=(0, 1))
        if core.min() >= 0.95:   # white = every channel clipped; a saturated glass has one channel at 1.0 on purpose
            notes.append(f"gem clips to white at its centre (rgb {tuple(round(float(c), 2) for c in core)}): lower exposure (~0.03), coat ~0.25, roughness ~0.3 — the colour must come from the glass, not the lights")
        elif core.max() < 0.08 and spec.get("items", [{}])[0].get("lit", True):
            notes.append(f"a lit gem reads black at its centre (rgb {tuple(round(float(c), 2) for c in core)}): raise glow or exposure")
    elif kind == "gauge":
        mean = float(rgb[solid].mean())
        if mean > 0.55:
            notes.append(f"gauge plate reads pale (mean {mean:.2f} of 1): a mirror steel reflects the lights — frame base ~0.1-0.3, roughness ~0.3-0.4, exposure ~0.07-0.12")
        clipped = float((rgb[solid].max(axis=1) >= 0.99).mean())
        if clipped > 0.12:
            notes.append(f"{clipped:.0%} of the plate is clipped white: lower exposure")
    else:
        clipped = float((rgb[solid].max(axis=1) >= 0.99).mean())
        if clipped > 0.35:
            notes.append(f"{clipped:.0%} of the logotype's face is clipped white: lower exposure or the material's base")
    bpy.data.images.remove(img)
    return notes


def despeckle(path, erode=2, grow=4, threshold=0.15):
    """remove hairlines from a rendered RGBA PNG in place (see the call site); returns the count of pixels cleared"""
    import numpy as np
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    alpha = px[:, :, 3]
    mask = alpha > threshold

    def shrink(m, n):
        for _ in range(n):
            p_ = np.pad(m, 1, constant_values=False)
            m = (p_[1:-1, 1:-1] & p_[:-2, 1:-1] & p_[2:, 1:-1] & p_[1:-1, :-2] & p_[1:-1, 2:]
                 & p_[:-2, :-2] & p_[:-2, 2:] & p_[2:, :-2] & p_[2:, 2:])
        return m

    def swell(m, n):
        for _ in range(n):
            p_ = np.pad(m, 1, constant_values=False)
            m = (p_[1:-1, 1:-1] | p_[:-2, 1:-1] | p_[2:, 1:-1] | p_[1:-1, :-2] | p_[1:-1, 2:]
                 | p_[:-2, :-2] | p_[:-2, 2:] | p_[2:, :-2] | p_[2:, 2:])
        return m

    keep = swell(shrink(mask, erode), grow)
    gone = mask & ~keep
    n = int(gone.sum())
    if n:
        px[:, :, 3] = np.where(keep, alpha, 0.0)
        img.pixels = px.reshape(-1).tolist()
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    bpy.data.images.remove(img)
    return n


def gem_objects(name, item, index, gem_rects):
    """one glass cell: a bevelled slab (+ a thin dark frame behind, + a halo plane when lit); records the slab's rect"""
    gw, gh = item.get("size", [2.0, 0.62])
    depth = float(item.get("depth", 0.16))
    col = tuple(item.get("color", [0.64, 0.87, 0.99]))
    lit = bool(item.get("lit", True))
    glow = float(item.get("glow", 4.0)) if lit else 0.0
    halo = float(item.get("halo", 0.5)) if lit else 0.0
    bev = float(item.get("bevel", 0.06))
    made = []

    def box(nm, w, h, d, z, mat, bevel):
        me = bpy.data.meshes.new(nm)
        hw, hh = w / 2, h / 2
        me.from_pydata([(-hw, -hh, z - d), (hw, -hh, z - d), (hw, hh, z - d), (-hw, hh, z - d),
                        (-hw, -hh, z), (hw, -hh, z), (hw, hh, z), (-hw, hh, z)], [],
                       [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
        ob = bpy.data.objects.new(nm, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        if bevel > 0:
            b = ob.modifiers.new("bevel", "BEVEL")
            b.width = min(bevel, min(w, h, d) * 0.45)
            b.segments = 5
        return ob

    # the glass
    glass = bpy.data.materials.new(f"{name}_glass")
    glass.use_nodes = True
    gb = glass.node_tree.nodes["Principled BSDF"]
    if lit:
        gb.inputs["Base Color"].default_value = col + (1.0,)
        gb.inputs["Roughness"].default_value = float(item.get("roughness", 0.3))
        if "Emission Color" in gb.inputs:
            gb.inputs["Emission Color"].default_value = col + (1.0,)
            gb.inputs["Emission Strength"].default_value = glow
    else:
        dark = tuple(c * 0.08 for c in col)
        gb.inputs["Base Color"].default_value = dark + (1.0,)
        gb.inputs["Roughness"].default_value = 0.2
    gb.inputs["Metallic"].default_value = 0.0
    if "Coat Weight" in gb.inputs:
        gb.inputs["Coat Weight"].default_value = float(item.get("coat", 0.7 if lit else 0.25))
    if "Specular IOR Level" in gb.inputs:
        gb.inputs["Specular IOR Level"].default_value = float(item.get("specular", 0.6 if lit else 0.3))
    # the frame: a thin near-black steel lip behind the glass
    frame_cfg = MATERIALS["black_steel"]
    frame = bpy.data.materials.new(f"{name}_frame")
    frame.use_nodes = True
    fb = frame.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = tuple(frame_cfg["base"]) + (1.0,)
    fb.inputs["Metallic"].default_value = 0.3
    fb.inputs["Roughness"].default_value = 0.6
    lip = float(item.get("lip", 0.05))
    made.append(box(f"{name}_frame", gw + 2 * lip, gh + 2 * lip, depth * 0.5, -depth * 0.35, frame, lip * 0.5))
    made.append(box(f"{name}_glass", gw, gh, depth, 0.0, glass, bev))
    if halo > 0:
        # the halo: an emissive plane behind, fading out radially (an ellipse to the plane's edge)
        hw, hh = gw / 2 + halo, gh / 2 + halo
        me = bpy.data.meshes.new(f"{name}_halo")
        z = -depth * 0.9
        me.from_pydata([(-hw, -hh, z), (hw, -hh, z), (hw, hh, z), (-hw, hh, z)], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(ob)
        hm = bpy.data.materials.new(f"{name}_halomat")
        hm.use_nodes = True
        hm.blend_method = "BLEND" if hasattr(hm, "blend_method") else None
        hn, hl = hm.node_tree.nodes, hm.node_tree.links
        for n_ in list(hn):
            if n_.type != "OUTPUT_MATERIAL":
                hn.remove(n_)
        out = next(n_ for n_ in hn if n_.type == "OUTPUT_MATERIAL")
        tex = hn.new("ShaderNodeTexCoord")
        mapping = hn.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (1.0 / hw, 1.0 / hh, 1.0)
        grad = hn.new("ShaderNodeTexGradient")
        grad.gradient_type = "SPHERICAL"       # 1 at the centre, 0 at unit distance = the plane's edge
        ramp = hn.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.0
        ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
        ramp.color_ramp.elements[1].position = 0.75
        ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
        emit = hn.new("ShaderNodeEmission")
        emit.inputs["Color"].default_value = col + (1.0,)
        emit.inputs["Strength"].default_value = glow * float(item.get("halo_strength", 0.5))
        trans = hn.new("ShaderNodeBsdfTransparent")
        mix = hn.new("ShaderNodeMixShader")
        hl.new(tex.outputs["Object"], mapping.inputs["Vector"])
        hl.new(mapping.outputs["Vector"], grad.inputs["Vector"])
        hl.new(grad.outputs["Fac"], ramp.inputs["Fac"])
        hl.new(ramp.outputs["Color"], mix.inputs["Fac"])
        hl.new(trans.outputs["BSDF"], mix.inputs[1])
        hl.new(emit.outputs["Emission"], mix.inputs[2])
        hl.new(mix.outputs["Shader"], out.inputs["Surface"])
        ob.data.materials.append(hm)
        ob.visible_shadow = False
        made.append(ob)
    gem_rects.append({"x0": -gw / 2, "y0": gh / 2, "x1": gw / 2, "y1": -gh / 2})
    return made


def bounds(objects):
    xs, ys = [], []
    bpy.context.view_layer.update()
    for ob in objects:
        for v in ob.bound_box:
            p = ob.matrix_world @ bpy.mathutils.Vector(v) if hasattr(bpy, "mathutils") else ob.matrix_world @ __import__("mathutils").Vector(v)
            xs.append(p.x)
            ys.append(p.y)
    return min(xs), min(ys), max(xs), max(ys)


def pbr(name, base, roughness, metallic=0.0, coat=0.0, transmission=0.0, ior=1.45):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = tuple(base) + (1.0,)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
    for key in ("Transmission Weight", "Transmission"):
        if key in b.inputs:
            b.inputs[key].default_value = transmission
            break
    b.inputs["IOR"].default_value = ior
    return mat


def dial_objects(name, item, index, dial_info):
    """a round INSTRUMENT (a tachometer, a compass, a clock): a chrome bezel, a recessed dark face, an engraved track
    groove, emissive ticks (hot in the red zone), optional numerals, and a soft glare arc (a clear coat, not a dome).
    The sweep runs CLOCKWISE in screen space from `start` degrees (0 = right) through `sweep` degrees, like the art
    pieces it replaces; dial_info gets the track radius for the anchors file (the live overlays sit on it)"""
    R = float(item.get("radius", 1.0))
    start, sweep = float(item.get("start", 150)), float(item.get("sweep", 240))
    red_from = float(item.get("red_from", 0.8))
    face_col = tuple(item.get("face", (0.012, 0.016, 0.03)))
    tick_col = tuple(item.get("tick", (0.95, 0.97, 1.0)))
    red_col = tuple(item.get("red", (0.85, 0.12, 0.16)))
    track_r = R * float(item.get("track", 0.86))
    glow = float(item.get("tick_glow", 3.0))
    made = []

    def ang(t):  # screen-clockwise from the right -> Blender (y up) counter-clockwise
        return -math.radians(start + sweep * t)

    def arc(nm, radius, width, t0, t1, mat, z):
        """an emissive arc (a bevelled curve) from t0 to t1 of the sweep"""
        c = bpy.data.curves.new(nm, type="CURVE")
        c.dimensions = "3D"
        c.bevel_depth = width
        c.bevel_resolution = 2
        s = c.splines.new("POLY")
        m = max(8, int(96 * (t1 - t0)))
        s.points.add(m - 1)
        for i in range(m):
            a_ = ang(t0 + (t1 - t0) * i / (m - 1))
            s.points[i].co = (math.cos(a_) * radius, math.sin(a_) * radius, z, 1.0)
        ob = bpy.data.objects.new(nm, c)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        made.append(ob)
        return ob

    def halo_mat(nm, col, strength, alpha):
        """emission mixed with transparency: the soft glow around a neon arc (Cycles has no bloom on a film)"""
        hm = bpy.data.materials.new(nm)
        hm.use_nodes = True
        nodes = hm.node_tree.nodes
        nodes.clear()
        o_ = nodes.new("ShaderNodeOutputMaterial")
        e_ = nodes.new("ShaderNodeEmission")
        e_.inputs["Color"].default_value = (*col, 1)
        e_.inputs["Strength"].default_value = strength
        t_ = nodes.new("ShaderNodeBsdfTransparent")
        mx = nodes.new("ShaderNodeMixShader")
        mx.inputs[0].default_value = alpha
        hm.node_tree.links.new(t_.outputs[0], mx.inputs[1])
        hm.node_tree.links.new(e_.outputs[0], mx.inputs[2])
        hm.node_tree.links.new(mx.outputs[0], o_.inputs[0])
        return hm

    # "style": "open" — a street racer's tach (Need for Speed Heat, measured from its stills 2026-10-16): NO bezel, no
    # face, no glass — the world shows through; an outer neon arc (a bright core + a wide faint halo), a thin white track
    # arc the ticks hang from, the redline as its own red arc; ticks and numerals as below
    if item.get("style") == "open":
        glow_col = tuple(item.get("glow_arc", (0.25, 0.62, 1.0)))
        tick_col_ = tuple(item.get("tick", (0.95, 0.97, 1.0)))
        arc(f"{name}_glow_core", R * 0.97, R * 0.012, 0, 1, emissive(f"{name}_glowc", glow_col, glow * 1.6), R * 0.03)
        arc(f"{name}_glow_halo", R * 0.97, R * 0.05, 0, 1, halo_mat(f"{name}_glowh", glow_col, glow, 0.22), R * 0.02)
        arc(f"{name}_track", R * 0.78, R * 0.008, 0, red_from, emissive(f"{name}_trk", tick_col_, glow), R * 0.03)
        arc(f"{name}_redline", R * 0.78, R * 0.012, red_from, 1, emissive(f"{name}_rl", red_col, glow * 1.4), R * 0.03)
        arc(f"{name}_redhalo", R * 0.78, R * 0.04, red_from, 1, halo_mat(f"{name}_rlh", red_col, glow, 0.25), R * 0.02)
        track_r = R * 0.78
    else:
        made += instrument_body(name, item, R, face_col, track_r)
    majors, minors = int(item.get("majors", 10)), int(item.get("minors", 5))
    tick_mat = emissive(f"{name}_tick", tick_col, glow)
    red_mat = emissive(f"{name}_red", red_col, glow * 1.4)
    total = majors * minors
    for k in range(total + 1):
        t = k / total
        major = k % minors == 0
        r0, r1 = R * (0.62 if major else 0.68), R * 0.76
        a_ = ang(t)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(math.cos(a_) * (r0 + r1) / 2, math.sin(a_) * (r0 + r1) / 2, R * 0.04))
        tk = bpy.context.active_object
        tk.scale = (r1 - r0, R * (0.022 if major else 0.011), R * 0.01)
        tk.rotation_euler = (0, 0, a_)
        tk.data.materials.append(red_mat if t >= red_from else tick_mat)
        made.append(tk)
    font = item.get("numerals_font")
    if font:
        nmat = emissive(f"{name}_num", tick_col, glow * 0.8)
        nred = emissive(f"{name}_numred", red_col, glow * 1.1)
        for k in range(majors + 1):
            t = k / majors
            a_ = ang(t)
            ob = text_object(f"{name}_n{k}", {"text": str(k), "font": font, "scale": R * float(item.get("numerals_scale", 0.13)),
                                              "x": math.cos(a_) * R * 0.5, "y": math.sin(a_) * R * 0.5, "z": R * 0.04}, 0.005, 0.0, 0.0,
                             nred if t >= red_from else nmat)
            made.append(ob)
    if item.get("style") != "open" and item.get("glare", True):
        made.append(glare_arc(name, item, R))
    # the item's own place: everything moves by x, y (several dials on one plate each get their own anchors)
    ox, oy = float(item.get("x", 0)), float(item.get("y", 0))
    if ox or oy:
        for ob in made:
            ob.location.x += ox
            ob.location.y += oy
    dial_info.append({"track_r": track_r, "R": R, "start": start, "sweep": sweep, "x": ox, "y": oy})
    return made


def instrument_body(name, item, R, face_col, track_r):
    """the classic instrument: bezel, step, matte face, engraved track groove"""
    made = []
    start, sweep = float(item.get("start", 150)), float(item.get("sweep", 240))

    def ang(t):
        return -math.radians(start + sweep * t)

    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=R * float(item.get("bezel_width", 0.065)), major_segments=160, minor_segments=24)
    bz = bpy.context.active_object
    # the bezel's metal: chrome by default, or {"base", "roughness", "metallic"} (a smoked gunmetal ring for a street HUD)
    bzc = item.get("bezel") or {}
    bz.data.materials.append(pbr(f"{name}_bezel", tuple(bzc.get("base", (0.9, 0.9, 0.94))), float(bzc.get("roughness", 0.12)),
                                 float(bzc.get("metallic", 1.0)), float(bzc.get("coat", 0.5))))
    made.append(bz)
    bpy.ops.mesh.primitive_cylinder_add(vertices=160, radius=R * 0.955, depth=R * 0.06, location=(0, 0, -R * 0.02))
    st = bpy.context.active_object
    st.data.materials.append(pbr(f"{name}_step", tuple(item.get("step", (0.2, 0.21, 0.24))), 0.3, 1.0))
    made.append(st)
    bpy.ops.mesh.primitive_cylinder_add(vertices=160, radius=R * 0.93, depth=R * 0.04, location=(0, 0, R * 0.005))
    face = bpy.context.active_object
    fm = pbr(f"{name}_face", face_col, 0.8, 0.0, float(item.get("face_coat", 0.0)))
    # (a gauge face is MATTE: the studio key is huge, so even a 4 % dielectric sheen lit the black face mid-grey)
    fb = fm.node_tree.nodes["Principled BSDF"]
    if "Specular IOR Level" in fb.inputs:
        fb.inputs["Specular IOR Level"].default_value = float(item.get("face_sheen", 0.0))
    face.data.materials.append(fm)
    made.append(face)
    cu = bpy.data.curves.new(f"{name}_track", type="CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = R * float(item.get("track_width", 0.045))
    cu.bevel_resolution = 3
    sp = cu.splines.new("POLY")
    n = 96
    sp.points.add(n - 1)
    for i in range(n):
        a_ = ang(i / (n - 1))
        sp.points[i].co = (math.cos(a_) * track_r, math.sin(a_) * track_r, R * 0.03, 1.0)
    tr = bpy.data.objects.new(cu.name, cu)
    bpy.context.scene.collection.objects.link(tr)
    tr.data.materials.append(pbr(f"{name}_groove", (0.03, 0.035, 0.06), 0.5, 0.2))
    made.append(tr)
    return made


def glare_arc(name, item, R):
    """a soft glare arc: a glossy lacquer catching the strip light (not a dome)"""
    cu2 = bpy.data.curves.new(f"{name}_glare", type="CURVE")
    cu2.dimensions = "3D"
    cu2.bevel_depth = R * 0.05
    cu2.bevel_resolution = 3
    sp2 = cu2.splines.new("NURBS")
    m = 24
    sp2.points.add(m - 1)
    for i in range(m):
        a_ = math.radians(105 + 70 * i / (m - 1))
        sp2.points[i].co = (math.cos(a_) * R * 0.84, math.sin(a_) * R * 0.84, R * 0.06, 1.0)
        sp2.points[i].radius = math.sin(math.pi * i / (m - 1)) ** 0.8 + 0.02
    sp2.use_endpoint_u = True
    gl = bpy.data.objects.new(cu2.name, cu2)
    bpy.context.scene.collection.objects.link(gl)
    gm = bpy.data.materials.new(f"{name}_glare")
    gm.use_nodes = True
    nodes = gm.node_tree.nodes
    nodes.clear()
    o_ = nodes.new("ShaderNodeOutputMaterial")
    e_ = nodes.new("ShaderNodeEmission")
    e_.inputs["Color"].default_value = (1, 1, 1, 1)
    e_.inputs["Strength"].default_value = 0.9
    t_ = nodes.new("ShaderNodeBsdfTransparent")
    mx = nodes.new("ShaderNodeMixShader")
    mx.inputs[0].default_value = float(item.get("glare_alpha", 0.16))
    gm.node_tree.links.new(t_.outputs[0], mx.inputs[1])
    gm.node_tree.links.new(e_.outputs[0], mx.inputs[2])
    gm.node_tree.links.new(mx.outputs[0], o_.inputs[0])
    gl.data.materials.append(gm)
    return gl


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    spec_path, out = None, None
    for i, v in enumerate(a):
        if v == "--spec":
            spec_path = a[i + 1]
        if v == "--out":
            out = a[i + 1]
    if not spec_path or not out:
        raise SystemExit("render: --spec <x.render.json> --out <x.png>")
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    w, h = spec.get("size", [1024, 1024])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
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
    sc.cycles.samples = int(spec.get("samples", 96))
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = int(w), int(h)
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("w")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.22, 0.22, 0.26, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = float(spec.get("world", 0.6))

    depth = float(spec.get("depth", 0.10))
    bevel = float(spec.get("bevel", 0.025))
    outline = float(spec.get("outline", 0.035))
    mat = material(spec)
    pieces = []
    gauge_anchors = []
    gem_rects = []
    dial_info = []
    for i, item in enumerate(spec.get("items") or []):
        if item.get("ring"):
            pieces.extend(ring_object(f"ring{i}", item, i))
        elif item.get("dial"):
            pieces.extend(dial_objects(f"dial{i}", item, i, dial_info))
        elif item.get("gauge"):
            pieces.extend(gauge_objects(f"gauge{i}", item, i, gauge_anchors))
        elif item.get("gem"):
            pieces.extend(gem_objects(f"gem{i}", item, i, gem_rects))
        else:
            pieces.append(text_object(f"piece{i}", item, depth, bevel, 0.0, mat))
    if outline > 0:
        omat = outline_material()
        for i, item in enumerate(spec.get("items") or []):
            if item.get("ring") or item.get("gauge") or item.get("gem") or item.get("dial"):
                continue
            ob = text_object(f"outline{i}", item, depth * 0.9, 0.0, outline, omat)
            ob.location.z = -0.06

    # the rig: key (warm, top-left), rim (cool, right), a bright strip above and a dark floor below for the chrome
    def light(name, kind, loc, energy, color=(1, 1, 1), size=2.0):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = color
        if kind == "AREA":
            ld.size = size
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        direction = -__import__("mathutils").Vector(loc)
        lo.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        return lo

    x0, y0, x1, y1 = bounds(pieces)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    span = max(x1 - x0, y1 - y0) * 1.18
    ex = float(spec.get("exposure", 1.0))  # (a dark gauge plate wants ~0.3; a chrome logotype 1.0)
    light("key", "AREA", (cx - span, cy + span, span * 2.2), 900 * span * span * ex, (1.0, 0.92, 0.8), span * 1.5)
    light("rim", "AREA", (cx + span * 1.2, cy - span * 0.3, span * 1.4), 500 * span * span * ex, (0.75, 0.85, 1.0), span)
    strip = bpy.data.meshes.new("strip")
    strip.from_pydata([(cx - span * 3, cy + span * 1.2, span * 1.6), (cx + span * 3, cy + span * 1.2, span * 1.6),
                       (cx + span * 3, cy + span * 2.2, span * 0.8), (cx - span * 3, cy + span * 2.2, span * 0.8)], [], [(0, 1, 2, 3)])
    so = bpy.data.objects.new("strip", strip)
    sc.collection.objects.link(so)
    so.data.materials.append(emissive("hot", (1.0, 0.97, 0.9), 6.0 * ex))
    so.visible_camera = False
    floor = bpy.data.meshes.new("floor")
    floor.from_pydata([(cx - span * 3, cy - span * 1.2, span * 1.6), (cx + span * 3, cy - span * 1.2, span * 1.6),
                       (cx + span * 3, cy - span * 2.4, span * 0.6), (cx - span * 3, cy - span * 2.4, span * 0.6)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("floor", floor)
    sc.collection.objects.link(fo)
    fo.data.materials.append(emissive("dark", (0.05, 0.04, 0.03), 1.0))
    fo.visible_camera = False

    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.ortho_scale = span * (max(w, h) / min(w, h) if w >= h else 1.0)
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    co.location = (cx, cy, 10.0)
    co.rotation_euler = (0.0, 0.0, 0.0)
    sc.camera = co
    # the camera fits BOTH extents (ortho_scale = scene units across the image's longer side): a wide 2048x512 render
    # fitted only the width and a three-row gauge lost half its height (audit 2026-10-16)
    cw_, ch_ = (x1 - x0) * 1.18, (y1 - y0) * 1.18
    cam.ortho_scale = max(cw_, ch_ * w / h) if w >= h else max(ch_, cw_ * h / w)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    sc.render.filepath = os.path.abspath(out)
    bpy.ops.render.render(write_still=True)
    # (despeckle erodes 2 px and grows 4: it cleans a glass dome's hairlines, but it also ERASED an open neon dial's
    # numerals, minor ticks and thin arc cores — 2026-10-16; a spec may say "despeckle": false, an open dial skips it)
    open_dial = any(isinstance(it, dict) and it.get("dial") and it.get("style") == "open" for it in spec.get("items") or [])
    if spec.get("despeckle", not open_dial):
        despeckle(os.path.abspath(out))
    reads = read_back(os.path.abspath(out), spec, gem_rects, gauge_anchors)
    # ONE anchors file for every kind of item (gauge rows, dials, the gem): each used to write it alone and the last won
    longer = max(w, h)
    px_per_unit = longer / cam.ortho_scale

    def to_px(x, y):
        return [round((x - cx) * px_per_unit + w / 2, 1), round(h / 2 - (y - cy) * px_per_unit, 1)]
    anchors = {"schema": 1, "size": [w, h]}
    if gauge_anchors:  # (the ortho camera at (cx, cy) shows ortho_scale scene units across the LONGER side)
        rows = []
        for ga in gauge_anchors:
            cells = []
            for c in ga["cells"]:
                a = to_px(c["x0"], c["y0"])
                b = to_px(c["x1"], c["y1"])
                cells.append({"x": a[0], "y": a[1], "w": round(b[0] - a[0], 1), "h": round(b[1] - a[1], 1), "rot": c.get("rot", 0.0)})
            rows.append({"row": ga["row"], "cells": cells, "lean_px": round(ga["lean"] * ga["cell"][1] * px_per_unit, 1)})
        anchors["rows"] = rows
    if dial_info:  # the live overlays (a lit arc, a needle) need each dial's centre and track radius in pixels
        dials = []
        for d0 in dial_info:
            c_ = to_px(d0["x"], d0["y"])
            dials.append({"cx": c_[0], "cy": c_[1], "track_r_px": round(d0["track_r"] * px_per_unit, 1),
                          "radius_px": round(d0["R"] * px_per_unit, 1), "start": d0["start"], "sweep": d0["sweep"]})
        anchors["dial"] = dials[0]
        anchors["dials"] = dials
    if gem_rects:
        g = gem_rects[0]
        a = to_px(g["x0"], g["y0"])
        b = to_px(g["x1"], g["y1"])
        anchors["gem"] = {"x": a[0], "y": a[1], "w": round(b[0] - a[0], 1), "h": round(b[1] - a[1], 1)}
    if len(anchors) > 2:
        with open(os.path.splitext(os.path.abspath(out))[0] + ".anchors.json", "w", encoding="utf-8", newline=chr(10)) as fh:
            json.dump(anchors, fh, indent=1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"rendered {os.path.basename(out)} ({w}x{h}, {len(pieces)} piece(s), {spec.get('material', 'chrome_gold')})"
                      + (f" — {len(reads)} read-back warning(s)" if reads else ""),
                      "next_action": (reads[0] if reads else f"LOOK at {out}; use it as art:<identity>/<name> in the screen"), "warnings": reads}))


if __name__ == "__main__":
    main()
