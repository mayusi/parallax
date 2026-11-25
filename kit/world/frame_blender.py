"""frame_blender.py — `kit world frame <scene.json>`: a DIRECTION / MOOD FRAME from the kit's real pieces (Blender, GPU).

    blender -b --factory-startup --python-exit-code 2 -P kit/world/frame_blender.py -- <scene.json> <out.png> [samples]

A direction is shown, not described: a composed shot (camera low on the approach, the silhouette against a designed
sky) built from the SAME pieces the game will use (castle_blender: wall / tower / roof / root), plus quick props,
with the direction's light: a designed sky gradient, a key and a bounce, aerial haze, a glowing landmark, motes.
Lessons baked in (Stormhold, 2026-10-24): the camera's clip_end must reach the horizon (the default 100 hid the
Erdtree); the fill comes from the camera side (a backlit face reads black); haze thick enough to read near is opaque
far; glow belongs in cracks, not on whole surfaces.

scene: {"pieces": [{"recipe": {kit recipe: kind wall|tower|roof|root|cairn|rock|cliff ...}, "at": [x, y, z], "rot": deg}],
        "boxes": [{"at": [..], "size": [..], "color": [r, g, b] 0..1, "rot": [x, y, z] deg, "emit": [..], "strength": 0}],
        "landmark": {"at": [x, y, z], "size": [sx, sy, sz], "color": [..], "strength": 2.0, "trunk": 70}
                    | {"tree": {kit tree recipe}, "height": 900, "at": [..], "strength": 1.5} (a real tree, colossal),
        "ground": [r, g, b], "motes": {"n": 70, "at": [x, y, z], "spread": [sx, sy, sz]},
        "sky": [[0.0, [r, g, b]], [0.25, [..]], [0.8, [..]]], "sky_strength": 1.0,
        "key": {"rot": [x, z] deg, "energy": 3, "color": [..]}, "fill": {"rot": [x, z], "energy": 2, "color": [..]},
        "haze": {"density": 0.0006, "color": [..]},
        "water": {"level": 0, "depth": 40, "color": [..], "deep": [..], "murk": 0.08}, "ground_z": -12,
        "mist": {"top": 6, "density": 0.03, "color": [..]}, pieces may "tilt": [x, y] deg; kinds rock | cliff too,
        "scatter": [{"recipe": {kind cairn ...}, "variants": 20, "count": 1500, "area": [cx, cy, r_in, r_out],
                     "scale": [0.7, 1.3], "clear": [[x, y, r], ...]}], "discs": [{"at", "radius", "color"}],
        "figures": [{"at", "rot", "pose": stand|sit|kneel, "color", "emit", "strength", "alpha"}],
        "lights": [{"at", "energy", "color", "radius"}],
        "camera": {"at": [..], "target": [..], "lens": 26}, "size": [1600, 900], "look": "AgX - Punchy"},
        "labels": [{"at": [x, y, z], "text": "the cathedral (ahead)"}]  (plain words on what the owner is looking at)
Labels: each point is projected into the shot (and ray-cast from the camera: a point behind a wall is "not in view");
<out>.labels.json goes beside the render and kit world frame draws them on (kit/world/frame_labels.py). The owner on an
unlabelled test frame, 2026-11-11: "I don't know what I'm exactly looking at" - a direction must read at a glance.
Prints one JSON line (pieces built, where the landmark sits in frame, the render path).
"""

import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import castle_blender  # noqa: E402
import meshes_blender  # noqa: E402


def mat(name, rgb, rough=0.7, emit=None, strength=0.0, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def figure(fg, k):
    """an R6-proportioned figure (5 studs) of boxes: stand | sit | kneel; a phantom when it glows and fades (alpha)"""
    col = fg.get("color", [0.1, 0.09, 0.09])
    m = mat(f"fig{k}", col, 0.7, fg.get("emit"), fg.get("strength", 0.0))
    if fg.get("alpha") is not None:
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Alpha"].default_value = fg["alpha"]
        try:
            m.blend_method = "BLEND"
        except AttributeError:
            pass
    pose = fg.get("pose", "stand")
    # (offset from the figure's ground point, size) in studs, before the figure's turn
    parts = {"stand": [((0, 0, 3.0), (2, 1, 2)), ((0, 0, 4.6), (1.2, 1.2, 1.2)), ((-1.5, 0, 3.0), (1, 1, 2)), ((1.5, 0, 3.0), (1, 1, 2)),
                       ((-0.5, 0, 1.0), (1, 1, 2)), ((0.5, 0, 1.0), (1, 1, 2))],
             "sit": [((0, 0, 2.4), (2, 1, 2)), ((0, 0, 4.0), (1.2, 1.2, 1.2)), ((-1.5, -0.4, 2.3), (1, 1, 2)), ((1.5, -0.4, 2.3), (1, 1, 2)),
                     ((-0.5, -1.0, 0.9), (1, 2, 1)), ((0.5, -1.0, 0.9), (1, 2, 1))],
             "kneel": [((0, 0, 3.0), (2, 1, 2)), ((0, -0.3, 4.6), (1.2, 1.2, 1.2)), ((-1.5, -0.3, 3.0), (1, 1, 2)), ((1.5, -0.3, 3.0), (1, 1, 2)),
                       ((-0.5, 0.4, 1.0), (1, 1, 2)), ((0.5, 0.4, 0.5), (1, 2, 1))]}[pose]
    rot = math.radians(fg.get("rot", 0))
    cx, cy, cz = fg["at"]
    for (ox, oy, oz), size in parts:
        x, y = ox * math.cos(rot) - oy * math.sin(rot), ox * math.sin(rot) + oy * math.cos(rot)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx + x, cy + y, cz + oz), rotation=(0, 0, rot))
        o = bpy.context.active_object
        o.scale = size
        o.data.materials.append(m)


def scatter(sc_, k):
    """many copies of a few kit-piece variants (linked duplicates) over a ring: a field of cairns"""
    r = random.Random(sc_.get("seed", 1))
    base = dict(sc_["recipe"])
    variants = []
    for v in range(int(sc_.get("variants", 20))):
        rec = dict(base, name=f"sc{k}_{v}", seed=int(base.get("seed", 1)) * 100 + v)
        o, img = castle_blender.build_piece(rec)
        meshes_blender._texture(o, img, rec["name"])
        o.location = (0, 0, -1000)  # (the variants themselves stay out of view)
        variants.append(o)
    cx, cy, r_in, r_out = sc_["area"]
    lo, hi = sc_.get("scale", [0.7, 1.3])
    clear = sc_.get("clear", [])  # [[x, y, radius], ...] kept empty (the road, the grace itself)
    placed = 0
    tries = 0
    while placed < int(sc_.get("count", 200)) and tries < int(sc_.get("count", 200)) * 20:
        tries += 1
        a = r.uniform(0, 2 * math.pi)
        d = math.sqrt(r.uniform(r_in ** 2, r_out ** 2))
        x, y = cx + d * math.cos(a), cy + d * math.sin(a)
        if any(math.hypot(x - c[0], y - c[1]) < c[2] for c in clear):
            continue
        src = variants[r.randrange(len(variants))]
        o = src.copy()
        o.location = (x, y, sc_.get("z", 0.0))
        o.rotation_euler[2] = r.uniform(0, 2 * math.pi)
        s_ = r.uniform(lo, hi)
        o.scale = (s_, s_, s_)
        bpy.context.collection.objects.link(o)
        placed += 1
    return placed


def place(o, at, rot=0.0, tilt=None):
    o.location = Vector(at)
    o.rotation_euler[2] = math.radians(rot)
    if tilt:  # a leaning piece (degrees about x, y): a sinking tower
        o.rotation_euler[0], o.rotation_euler[1] = math.radians(tilt[0]), math.radians(tilt[1])


def water_body(w):
    """a clear cold water volume: a glassy surface (refracts, reflects the sky) over a body that absorbs with depth,
    so what stands in it shows near the surface and darkens going down"""
    level, depth = w.get("level", 0.0), w.get("depth", 40.0)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(w.get("at", [0, 0])[0], w.get("at", [0, 0])[1], level - depth / 2))
    o = bpy.context.active_object
    o.scale = (w.get("size", [4000, 4000])[0], w.get("size", [4000, 4000])[1], depth)
    m = bpy.data.materials.new("water")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*w.get("color", [0.05, 0.09, 0.1]), 1)
    b.inputs["Roughness"].default_value = w.get("rough", 0.03)
    b.inputs["IOR"].default_value = 1.33
    b.inputs["Transmission Weight"].default_value = 1.0
    absorb = nt.nodes.new("ShaderNodeVolumeAbsorption")
    absorb.inputs["Color"].default_value = (*w.get("deep", [0.1, 0.25, 0.25]), 1)
    absorb.inputs["Density"].default_value = w.get("murk", 0.08)
    nt.links.new(absorb.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    o.data.materials.append(m)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    scene_path, out = argv[0], os.path.abspath(argv[1])
    samples = int(argv[2]) if len(argv) > 2 else 96
    sc = json.load(open(scene_path, encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    built = []
    for i, pc in enumerate(sc.get("pieces", [])):
        rec = dict(pc["recipe"])
        rec.setdefault("name", f"p{i}")
        kind = rec.get("kind", "wall")
        if kind in ("rock", "cliff"):
            o = meshes_blender.build_rock(rec, cliff=kind == "cliff")
            o.data.materials.append(mat(rec["name"] + "_m", rec.get("color", [0.36, 0.34, 0.31]), 0.85))
            place(o, pc.get("at", [0, 0, 0]), pc.get("rot", 0), pc.get("tilt"))
            built.append(f"{rec['name']} ({kind})")
            continue
        if kind == "root":
            o, img, g = castle_blender.build_root(rec)
            meshes_blender._texture(o, img, rec["name"])
            place(g, pc.get("at", [0, 0, 0]), pc.get("rot", 0), pc.get("tilt"))
        else:
            o, img = castle_blender.build_piece(rec)
            meshes_blender._texture(o, img, rec["name"])
        place(o, pc.get("at", [0, 0, 0]), pc.get("rot", 0), pc.get("tilt"))
        if pc.get("scale"):
            o.scale = (pc["scale"],) * 3
        built.append(f"{rec['name']} ({kind})")
    for k, sc_ in enumerate(sc.get("scatter", [])):
        n = scatter(sc_, k)
        built.append(f"{n} x {sc_['recipe'].get('kind')} (scatter)")
    for k, fg in enumerate(sc.get("figures", [])):
        figure(fg, k)
    for k, dc in enumerate(sc.get("discs", [])):
        bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=dc["radius"], depth=0.05, location=dc["at"])
        bpy.context.active_object.data.materials.append(mat(f"disc{k}", dc.get("color", [0.5, 0.45, 0.3]), 0.95))
    for k, lt in enumerate(sc.get("lights", [])):
        L = bpy.data.lights.new(f"pt{k}", "POINT")
        L.energy = lt.get("energy", 500)
        L.color = lt.get("color", [1, 0.8, 0.45])
        L.shadow_soft_size = lt.get("radius", 0.5)
        lo_ = bpy.data.objects.new(f"pt{k}", L)
        lo_.location = lt["at"]
        bpy.context.scene.collection.objects.link(lo_)
    for k, bx in enumerate(sc.get("boxes", [])):
        bpy.ops.mesh.primitive_cube_add(size=1, location=bx["at"], rotation=[math.radians(a) for a in bx.get("rot", [0, 0, 0])])
        o = bpy.context.active_object
        o.scale = bx["size"]
        o.data.materials.append(mat(f"box{k}", bx.get("color", [0.5, 0.5, 0.5]), bx.get("rough", 0.8), bx.get("emit"), bx.get("strength", 0.0),
                                    bx.get("metal", 0.0)))
    if sc.get("water"):
        water_body(sc["water"])
    if "ground" in sc:
        bpy.ops.mesh.primitive_plane_add(size=6000, location=(0, 0, sc.get("ground_z", -0.05)))
        bpy.context.active_object.data.materials.append(mat("ground", sc["ground"], 0.95))
    lm = sc.get("landmark")
    crown = None
    if lm and lm.get("tree"):  # a REAL tree from the kit's tree builder, grown colossal, its leaves lit from within
        # (a picture's prop, not a mesh for a game: not asked for its "grammar" - but one that cannot be grown is
        # said, not a crash)
        try:
            g, img = meshes_blender.build_tree(dict(lm["tree"], name="landmark_tree"))
        except ValueError as e:
            raise SystemExit(f"frame: the landmark tree cannot be built - {e}")
        crown = meshes_blender.geo_to_object("landmark_tree", g, img)
        k = float(lm.get("height", 900)) / max(float(lm["tree"].get("height", 30)), 1)
        crown.scale = (k, k, k)
        crown.location = Vector(lm["at"])
        crown.rotation_euler[2] = math.radians(lm.get("rot", 0))
        mt = crown.data.materials[0]
        nt = mt.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])  # (the leaves glow their own gold)
        bsdf.inputs["Emission Strength"].default_value = lm.get("strength", 1.5)
        lm = None
    if lm:  # a colossal glowing landmark on the horizon (the Erdtree): a lumpy crown + a trunk
        col = lm.get("color", [1.0, 0.74, 0.3])
        gm = mat("landmark", col, emit=col, strength=lm.get("strength", 2.0))
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=1, location=lm["at"])
        crown = bpy.context.active_object
        crown.scale = lm.get("size", [600, 250, 350])
        tex = bpy.data.textures.new("lmtex", "CLOUDS")
        tex.noise_scale = 0.25
        dm = crown.modifiers.new("d", "DISPLACE")
        dm.texture = tex
        dm.strength = 0.25
        crown.data.materials.append(gm)
        if lm.get("trunk"):
            x, y, z = lm["at"]
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=lm["trunk"], depth=z * 1.6, location=(x, y, z * 0.2))
            bpy.context.active_object.data.materials.append(gm)
    mo = sc.get("motes")
    if mo:
        r = random.Random(5)
        mm = mat("mote", [1, 0.8, 0.4], emit=[1, 0.75, 0.35], strength=20)
        for _ in range(int(mo.get("n", 60))):
            loc = [c + r.gauss(0, s) for c, s in zip(mo["at"], mo["spread"])]
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.09, location=loc)
            bpy.context.active_object.data.materials.append(mm)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for dv in prefs.devices:
            dv.use = True
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = sc.get("size", [1600, 900])
    w = bpy.data.worlds.new("w")
    scene.world = w
    w.use_nodes = True
    wn = w.node_tree
    tcw = wn.nodes.new("ShaderNodeTexCoord")
    sep = wn.nodes.new("ShaderNodeSeparateXYZ")
    wn.links.new(tcw.outputs["Generated"], sep.inputs[0])
    ramp = wn.nodes.new("ShaderNodeValToRGB")
    pal = sc.get("sky", [[0.0, [1.0, 0.7, 0.4]], [0.8, [0.3, 0.3, 0.45]]])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = pal[0][0], (*pal[0][1], 1)
    els[1].position, els[1].color = pal[-1][0], (*pal[-1][1], 1)
    for pos, col in pal[1:-1]:
        els.new(pos).color = (*col, 1)
    wn.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    wn.links.new(ramp.outputs["Color"], wn.nodes["Background"].inputs["Color"])
    wn.nodes["Background"].inputs["Strength"].default_value = sc.get("sky_strength", 1.0)
    for key in ("key", "fill"):
        L = sc.get(key)
        if not L:
            continue
        sun = bpy.data.lights.new(key, "SUN")
        sun.energy = L.get("energy", 3.0)
        sun.color = L.get("color", [1, 0.85, 0.65])
        sun.angle = math.radians(1.5)
        so = bpy.data.objects.new(key, sun)
        so.rotation_euler = (math.radians(L["rot"][0]), 0, math.radians(L["rot"][1]))
        scene.collection.objects.link(so)
    hz = sc.get("haze")
    if hz:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
        haze = bpy.context.active_object
        haze.scale = (6000, 6000, 2400)
        hm = bpy.data.materials.new("haze")
        hm.use_nodes = True
        nt = hm.node_tree
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        vol = nt.nodes.new("ShaderNodeVolumePrincipled")
        vol.inputs["Color"].default_value = (*hz.get("color", [1, 0.85, 0.65]), 1)
        vol.inputs["Density"].default_value = hz.get("density", 0.0006)
        nt.links.new(vol.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
        haze.data.materials.append(hm)
    ms = sc.get("mist")
    if ms:  # mist lying ON the water: a thin dense layer, not the whole sky
        bpy.ops.mesh.primitive_cube_add(size=1, location=(*ms.get("at", [0, 0]), ms.get("top", 6) / 2))
        mo_ = bpy.context.active_object
        mo_.scale = (ms.get("size", [3000, 3000])[0], ms.get("size", [3000, 3000])[1], ms.get("top", 6))
        mm_ = bpy.data.materials.new("mist")
        mm_.use_nodes = True
        nt = mm_.node_tree
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        vol = nt.nodes.new("ShaderNodeVolumePrincipled")
        vol.inputs["Color"].default_value = (*ms.get("color", [0.85, 0.88, 0.92]), 1)
        vol.inputs["Density"].default_value = ms.get("density", 0.03)
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 0.02
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = 0.0
        mr.inputs["To Max"].default_value = ms.get("density", 0.03) * 2
        nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], vol.inputs["Density"])  # (banks of mist, not a flat sheet)
        nt.links.new(vol.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
        mo_.data.materials.append(mm_)
    cm = sc["camera"]
    cam = bpy.data.cameras.new("cam")
    cam.lens = cm.get("lens", 26)
    cam.clip_end = 20000  # (the default 100 clipped the horizon landmark away)
    co = bpy.data.objects.new("cam", cam)
    co.location = Vector(cm["at"])
    co.rotation_euler = (Vector(cm["target"]) - co.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(co)
    scene.camera = co
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = sc.get("look", "AgX - Punchy")
    bpy.context.view_layer.update()
    labels = []
    if sc.get("labels"):
        from bpy_extras.object_utils import world_to_camera_view
        w_px, h_px = scene.render.resolution_x, scene.render.resolution_y
        dg = bpy.context.evaluated_depsgraph_get()
        for lb in sc["labels"]:
            p = Vector(lb["at"])
            v = world_to_camera_view(scene, co, p)
            seen = v.z > 0 and 0.0 <= v.x <= 1.0 and 0.0 <= v.y <= 1.0
            if seen:  # nothing between the camera and the point (a label behind a wall is not in view)
                d = p - co.location
                hit, loc, _, _, _, _ = scene.ray_cast(dg, co.location, d.normalized(), distance=d.length)
                seen = not hit or (loc - co.location).length >= d.length - 1.0
            labels.append({"text": lb["text"], "px": [round(v.x * w_px, 1), round((1.0 - v.y) * h_px, 1)],
                           "seen": bool(seen)})
        with open(os.path.splitext(out)[0] + ".labels.json", "w", encoding="utf-8") as fh:
            json.dump({"size": [w_px, h_px], "labels": labels}, fh, indent=1)
    framepos = None
    if crown:
        from bpy_extras.object_utils import world_to_camera_view
        framepos = [round(v, 2) for v in world_to_camera_view(scene, co, crown.location)[:2]]
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print(json.dumps({"status": "pass", "summary": f"frame: {len(built)} kit piece(s) ({', '.join(built)})" + (f"; landmark at {framepos} of the frame" if framepos else ""),
                      "next_action": f"LOOK at {out}", "out": out, "landmark": framepos,
                      "labels": len(labels)}))


if __name__ == "__main__":
    main()
