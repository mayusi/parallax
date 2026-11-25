"""modkit_blender.py - LOOK at the W3 kit and the houses the facade grammar puts together from it (runs in Blender).

blender -b --factory-startup -P kit/world/modkit_blender.py -- <out_dir> [--world assets/worlds/GothicCourtyard.json]
    [--res 1600x900] [--samples 48]

Writes the kit (kit/world/modkit.py: one .obj a module part + kit.json) and the two trim sheets' maps
(kit/world/trims.py) into <out_dir>, builds two materials - the stone sheet and the roof sheet, each colour +
normal + roughness, as a SurfaceAppearance would wear them - then renders:
  kit_sheet.png   the eighteen modules in a row on a grey floor, lit from the front
  house_eye.png   one house from the grammar at a player's eye height (5 studs), three-quarter on
  court_*.png     with --world: every "building" of that blueprint put together by the grammar at its own place
                  and size (its door side, its storeys), seen from the court at eye level, at night (moon + lamps)
Roblox (x, y up, z) -> Blender (x, -z, y). One JSON line."""
import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import facade_grammar as G  # noqa: E402
import modkit as M  # noqa: E402
import trims  # noqa: E402


def to_b(p):
    return (p[0], -p[2], p[1])


def material(sheet, out):
    mat = bpy.data.materials.new(f"kit_{sheet}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    def img(m, colour):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(os.path.join(out, f"kit_trim_{sheet}_{m}.png"))
        if not colour:
            node.image.colorspace_settings.name = "Non-Color"
        return node
    c = img("color", True)
    nt.links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    r = img("roughness", False)
    nt.links.new(r.outputs["Color"], bsdf.inputs["Roughness"])
    n = img("normal", False)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mesh_of(name, part, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([to_b(v) for v in part["verts"]], [], [tuple(f) for f in part["faces"]])
    me.update()
    uvl = me.uv_layers.new(name="UV")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = part["uvs"][me.loops[li].vertex_index]
    me.materials.append(mat)
    return me


def place(me, pos, yaw, scale, coll):
    ob = bpy.data.objects.new(me.name, me)
    ob.location = to_b(pos)
    ob.rotation_euler = (0, 0, math.radians(yaw))
    ob.scale = (scale[0], scale[2], scale[1])
    coll.objects.link(ob)
    return ob


def camera(at, look, fov=70, res=(1600, 900)):
    cam = bpy.data.objects.get("Cam") or bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    if cam.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(cam)
    cam.data.angle = math.radians(fov)
    cam.data.clip_end = 5000
    cam.location = to_b(at)
    import mathutils

    d = mathutils.Vector(to_b(look)) - mathutils.Vector(to_b(at))
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(argv[0])
    world = argv[argv.index("--world") + 1] if "--world" in argv else None
    res = tuple(int(v) for v in (argv[argv.index("--res") + 1] if "--res" in argv else "1600x900").split("x"))
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 48
    os.makedirs(out, exist_ok=True)
    kit = M.build_kit()
    M.write(kit, out)
    if not os.path.isfile(os.path.join(out, "kit_trim_stone_color.png")):  # (PIL: written first outside Blender)
        trims.write(out)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX"
    mats = {s: material(s, out) for s in trims.SHEETS}
    meshes = {}
    for name, m in kit.items():
        meshes[name] = [mesh_of(f"{name}_{p['sheet']}", p, mats[p["sheet"]]) for p in m["parts"]]
    coll = bpy.data.collections.new("Kit")
    sc.collection.children.link(coll)
    # a floor and the light: a world colour, a sun
    bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, -0.01))
    floor = bpy.context.active_object
    fm = bpy.data.materials.new("floor")
    fm.use_nodes = True
    fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.05, 0.055, 1)
    floor.data.materials.append(fm)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    sun.data.energy = 3.0
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.36, 0.45, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    renders = []
    # 1. the kit sheet: every module in a row, 3 studs apart
    x = 0.0
    sheet_objs = []
    for name, m in kit.items():
        for me in meshes[name]:
            sheet_objs.append(place(me, (x, 0, 0), 0, (1, 1, 1), coll))
        x += m["size"][0] + 3.0
    camera((x / 2, 22, 96), (x / 2, 6, 0), fov=62, res=res)
    p = os.path.join(out, "kit_sheet.png")
    render(p)
    renders.append(p)
    for ob in sheet_objs:
        bpy.data.objects.remove(ob)
    # 2. one house at eye level (24 x 22, five storeys, its door to the south)
    pl, _ = G.house(24, 22, 5, "S", seed=5)
    house_objs = []
    for q in pl:
        for me in meshes[q["module"]]:
            house_objs.append(place(me, q["pos"], q["yaw"], q["scale"], coll))
    camera((-14, 5, 34), (2, 18, 0), fov=70, res=res)
    p = os.path.join(out, "house_eye.png")
    render(p)
    renders.append(p)
    for ob in house_objs:
        bpy.data.objects.remove(ob)
    placed = 0
    if world:
        bp = json.load(open(world, encoding="utf-8"))
        for st in bp.get("build", []):
            b = st.get("building")
            if not b:
                continue
            c = b["center"]
            pl, _ = G.house(b["size"][0], b["size"][1], b.get("floors", 2), (b.get("door") or {}).get("side", "S"),
                            seed=len(b.get("name", "")) * 7 + ord((b.get("name") or "x")[-1]))
            for q in pl:
                for me in meshes[q["module"]]:
                    place(me, (q["pos"][0] + c[0], q["pos"][1] + c[1] + 0.08, q["pos"][2] + c[2]), q["yaw"], q["scale"], coll)
                    placed += 1
        # night: a cold moon, a few warm lamps along the court
        sun.data.energy = 0.25
        sun.data.color = (0.6, 0.7, 1.0)
        w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.08
        for k, (lx, lz) in enumerate(((0, 0), (-20, 20), (20, 20), (-20, -20), (20, -20))):
            L = bpy.data.objects.new(f"Lamp{k}", bpy.data.lights.new(f"Lamp{k}", "POINT"))
            L.data.energy = 4000
            L.data.color = (1.0, 0.62, 0.32)
            L.location = to_b((lx, 9, lz))
            sc.collection.objects.link(L)
        for name, at, look in (("court_south", (0, 5, 30), (0, 16, -40)), ("court_corner", (-24, 5, 24), (20, 14, -20))):
            camera(at, look, fov=70, res=res)
            p = os.path.join(out, f"{name}.png")
            render(p)
            renders.append(p)
    errors, stats = M.check(kit)
    print(json.dumps({"status": "pass" if not errors else "fail",
                      "summary": f"{stats['modules']} modules, {stats['maps']} maps, {stats['tris']} tris; {len(renders)} render(s); {placed} module parts placed for the world",
                      "next_action": f"LOOK at {out}/kit_sheet.png, house_eye.png" + (", court_*.png" if world else ""),
                      "renders": renders}))


main()
