"""kit world sky - A SKY OF THE KIT'S OWN: six square pictures rendered in Blender (run by Blender, background; the
owner's method list: "Skyboxes").

    blender -b --factory-startup --python-exit-code 2 -P kit/world/sky_blender.py -- <out_dir> --name <Name>
            [--sun <elevation>,<azimuth>] [--clouds 0..1] [--seed n] [--size 256|512|1024]

A physical sky (Blender's sky texture: the air scatters the sun's light) with the sun where it is asked for and a
layer of clouds by noise, looked at from the middle by six square 90-degree cameras - one a face of Roblox's sky
cube, each looking and standing as kit/world/sky.py says (measured in Roblox Studio). The six join without a seam
because they are six views of one sky.
  --sun     <elevation over the horizon>,<azimuth from -Z round toward +X> in degrees (35,135 unless said)
  --clouds  0 (clear) to 1 (overcast)
out_dir/<Name>_ft.png, _bk, _lf, _rt, _up, _dn and <Name>.sky.json: {"name", "faces": {"SkyboxFt": "<file>" ...},
"sun": {"elevation", "azimuth", "vector": [x, y, z] (Roblox space)}, "clouds", "seed", "size", "checked": where the
brightest spot of the six pictures is and where the sun was asked for}
The run CHECKS ITSELF, as far as Blender can: six test suns, one off the middle of each face, are rendered alone on a
black sky through the six cameras, and each must show at its place in its own picture - so a camera that is turned,
mirrored or looking another way than kit/world/sky.py's table says fails here. And the finished sky must be brighter
on the asked sun's side. What this does NOT hold is the table itself against Roblox: which way each face looks was
measured in Studio once (sky.py), and is seen in a game only with the pictures uploaded.
A sun under the horizon is not drawn (its glow is). A run that fails leaves no pictures and no record of that name.
The last line printed is a JSON verdict: {"status": "pass" | "fail", "summary", "next_action"}."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sky as rules  # noqa: E402


def fail(why):
    print(json.dumps({"status": "fail", "summary": why, "next_action": why}))
    sys.exit(1)


def build_world(s):
    import bpy

    world = bpy.data.worlds.new("KitSky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    air = nt.nodes.new("ShaderNodeTexSky")
    air.sky_type = "MULTIPLE_SCATTERING"
    air.sun_disc = True
    air.sun_size = math.radians(2.5)  # (wider than the real sun's half degree: a spot a 512 picture can show)
    air.sun_intensity = 1.0
    air.sun_elevation = math.radians(s["sun"][0])
    # the sun's turn about the zenith: Blender turns it from its +Y toward its +X; the kit's azimuth runs from Roblox's
    # -Z (Blender's +Y) toward Roblox's +X (Blender's +X): the same turn (held by the run's own check below)
    air.sun_rotation = math.radians(s["sun"][1])
    # the clouds: noise over the way a ray points, flattened toward the horizon (a layer seen from under it)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Generated"], sep.inputs[0])
    lift = nt.nodes.new("ShaderNodeMath")  # (z + 0.15: the layer's height over the eye)
    lift.operation = "ADD"
    lift.inputs[1].default_value = 0.15
    nt.links.new(sep.outputs["Z"], lift.inputs[0])
    plane = nt.nodes.new("ShaderNodeVectorMath")  # (the ray carried up to the layer: x / z, y / z)
    plane.operation = "DIVIDE"
    spread = nt.nodes.new("ShaderNodeCombineXYZ")
    for k in ("X", "Y", "Z"):
        nt.links.new(lift.outputs[0], spread.inputs[k])
    nt.links.new(coord.outputs["Generated"], plane.inputs[0])
    nt.links.new(spread.outputs[0], plane.inputs[1])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "4D"
    noise.inputs["W"].default_value = float(s["seed"]) * 1.37
    noise.inputs["Scale"].default_value = 2.2
    noise.inputs["Detail"].default_value = 7.0
    noise.inputs["Roughness"].default_value = 0.6
    nt.links.new(plane.outputs[0], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cover = max(0.0, min(1.0, s["clouds"]))
    ramp.color_ramp.elements[0].position = 0.72 - 0.45 * cover
    ramp.color_ramp.elements[1].position = min(0.99, 0.84 - 0.35 * cover)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    above = nt.nodes.new("ShaderNodeMapRange")  # (no clouds under the horizon, thinning toward it)
    above.inputs["From Min"].default_value = 0.0
    above.inputs["From Max"].default_value = 0.18
    nt.links.new(sep.outputs["Z"], above.inputs["Value"])
    mask = nt.nodes.new("ShaderNodeMath")
    mask.operation = "MULTIPLY"
    nt.links.new(ramp.outputs["Color"], mask.inputs[0])
    nt.links.new(above.outputs["Result"], mask.inputs[1])
    amount = nt.nodes.new("ShaderNodeMath")
    amount.operation = "MULTIPLY"
    amount.inputs[1].default_value = 1.0 if cover > 0 else 0.0
    nt.links.new(mask.outputs[0], amount.inputs[0])
    mix = nt.nodes.new("ShaderNodeMixRGB")
    # (a cloud is lit by the sun: bright by day, dim and warm when the sun is low)
    high = max(0.0, math.sin(math.radians(max(s["sun"][0], 0.0))))
    # (in the sky texture's own measure the day's blue is about 6 to 10: a lit cloud is brighter than that)
    mix.inputs["Color2"].default_value = (1.6 + 20.0 * high, 1.5 + 20.0 * high, 1.5 + 21.0 * high, 1.0)
    nt.links.new(amount.outputs[0], mix.inputs["Fac"])
    nt.links.new(air.outputs["Color"], mix.inputs["Color1"])
    # the sun's own disc (the sky texture draws none in this renderer): every ray within a degree and a half of the
    # way to the sun is the sun - the kit's own vector, so the run's check below holds the faces AND the sun to it
    ray = nt.nodes.new("ShaderNodeVectorMath")
    ray.operation = "NORMALIZE"
    nt.links.new(coord.outputs["Generated"], ray.inputs[0])
    # (the check's sky has several test suns; the sky asked for has its one, and none when it is under the horizon)
    if s.get("only_sun"):
        suns = list(s["only_sun"])
    else:
        suns = [rules.sun_vector(*s["sun"])] if s["sun"][0] > 0 else []
    disc = None
    for vector in suns:
        along = nt.nodes.new("ShaderNodeVectorMath")
        along.operation = "DOT_PRODUCT"
        along.inputs[1].default_value = rules.to_blender(vector)
        nt.links.new(ray.outputs[0], along.inputs[0])
        one = nt.nodes.new("ShaderNodeMath")
        one.operation = "GREATER_THAN"
        one.inputs[1].default_value = math.cos(math.radians(1.5))
        nt.links.new(along.outputs["Value"], one.inputs[0])
        if disc is None:
            disc = one
        else:
            both = nt.nodes.new("ShaderNodeMath")
            both.operation = "MAXIMUM"
            nt.links.new(disc.outputs[0], both.inputs[0])
            nt.links.new(one.outputs[0], both.inputs[1])
            disc = both
    if disc is None:  # (no sun to draw)
        disc = nt.nodes.new("ShaderNodeValue")
        disc.outputs[0].default_value = 0.0
    clear = nt.nodes.new("ShaderNodeMath")  # (a cloud in front of the sun hides it)
    clear.operation = "SUBTRACT"
    clear.use_clamp = True
    nt.links.new(disc.outputs[0], clear.inputs[0])
    nt.links.new(amount.outputs[0], clear.inputs[1])
    sun = nt.nodes.new("ShaderNodeMixRGB")
    sun.inputs["Color2"].default_value = (60.0, 56.0, 48.0, 1.0)
    nt.links.new(clear.outputs[0], sun.inputs["Fac"])
    if s.get("only_sun"):  # (the check's sky: black, the disc alone)
        sun.inputs["Color1"].default_value = (0.0, 0.0, 0.0, 1.0)
    else:
        # under the horizon the sky texture is dark (a world with no land to the horizon would stand over a black
        # bowl): a haze of the horizon's own tone there, joined to the sky over a few degrees
        low = nt.nodes.new("ShaderNodeMapRange")
        low.inputs["From Min"].default_value = -0.06
        low.inputs["From Max"].default_value = 0.0
        nt.links.new(sep.outputs["Z"], low.inputs["Value"])
        haze = nt.nodes.new("ShaderNodeMixRGB")
        haze.inputs["Color1"].default_value = (0.9 + 9.0 * high, 1.0 + 10.0 * high, 1.2 + 11.0 * high, 1.0)
        nt.links.new(low.outputs["Result"], haze.inputs["Fac"])
        nt.links.new(mix.outputs["Color"], haze.inputs["Color2"])
        nt.links.new(haze.outputs["Color"], sun.inputs["Color1"])
    last = sun
    layers = [] if s.get("only_sun") else rules.ridge_layers(s.get("ridges", 0), s.get("ridge_height") or 0.0)
    if layers:
        last = ridges(nt, s, layers, sep, sun, high)
    nt.links.new(last.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = s.get("strength", 0.05)
    nt.links.new(bg.outputs[0], out.inputs["Surface"])


def ridges(nt, s, layers, sep, behind, high):
    """FAR RIDGES in the sky's own shader: a ray is in a range when it stands lower than that range's crest at the
    ray's compass side (noise round the horizon: the same in every face, so no seam). Farthest first, each nearer one
    over it; under the horizon a range fades back into what was there (the haze) -> the last mix node"""
    # the ray's height over the horizon, in degrees, and its way along the ground
    flat = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs["X"], flat.inputs["X"])
    nt.links.new(sep.outputs["Y"], flat.inputs["Y"])
    flat.inputs["Z"].default_value = 0.0
    ground = nt.nodes.new("ShaderNodeVectorMath")
    ground.operation = "NORMALIZE"
    nt.links.new(flat.outputs[0], ground.inputs[0])
    reach = nt.nodes.new("ShaderNodeVectorMath")
    reach.operation = "LENGTH"
    nt.links.new(flat.outputs[0], reach.inputs[0])
    angle = nt.nodes.new("ShaderNodeMath")
    angle.operation = "ARCTAN2"
    nt.links.new(sep.outputs["Z"], angle.inputs[0])
    nt.links.new(reach.outputs["Value"], angle.inputs[1])
    degrees = nt.nodes.new("ShaderNodeMath")
    degrees.operation = "MULTIPLY"
    degrees.inputs[1].default_value = 180.0 / math.pi
    nt.links.new(angle.outputs[0], degrees.inputs[0])
    under = nt.nodes.new("ShaderNodeMapRange")  # (a range fades out under the horizon: -1 to -6 degrees)
    under.inputs["From Min"].default_value = -6.0
    under.inputs["From Max"].default_value = -1.0
    nt.links.new(degrees.outputs[0], under.inputs["Value"])
    last = behind
    haze_tone = (0.9 + 9.0 * high, 1.0 + 10.0 * high, 1.2 + 11.0 * high)
    rock_tone = (0.10 + 0.9 * high, 0.13 + 1.1 * high, 0.19 + 1.4 * high)  # (far rock under this sun: dark and blue)
    for i, layer in enumerate(layers):
        scaled = nt.nodes.new("ShaderNodeVectorMath")
        scaled.operation = "SCALE"
        scaled.inputs["Scale"].default_value = layer["scale"]
        nt.links.new(ground.outputs[0], scaled.inputs[0])
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.noise_dimensions = "4D"
        noise.inputs["W"].default_value = float(s["seed"]) * 1.37 + 31.0 * (i + 1)
        noise.inputs["Scale"].default_value = 1.0
        noise.inputs["Detail"].default_value = 5.0
        noise.inputs["Roughness"].default_value = 0.55
        nt.links.new(scaled.outputs[0], noise.inputs["Vector"])
        crest = nt.nodes.new("ShaderNodeMapRange")  # (the noise's middle half -> the range's lowest to highest crest)
        crest.inputs["From Min"].default_value = 0.3
        crest.inputs["From Max"].default_value = 0.7
        crest.inputs["To Min"].default_value = layer["low"]
        crest.inputs["To Max"].default_value = layer["top"]
        nt.links.new(noise.outputs["Fac"], crest.inputs["Value"])
        inside = nt.nodes.new("ShaderNodeMath")
        inside.operation = "LESS_THAN"
        nt.links.new(degrees.outputs[0], inside.inputs[0])
        nt.links.new(crest.outputs["Result"], inside.inputs[1])
        shown = nt.nodes.new("ShaderNodeMath")
        shown.operation = "MULTIPLY"
        nt.links.new(inside.outputs[0], shown.inputs[0])
        nt.links.new(under.outputs["Result"], shown.inputs[1])
        mix = nt.nodes.new("ShaderNodeMixRGB")
        if s.get("only_ridges"):  # (the check's sky: the ranges alone, white on black)
            tone = (1.0, 1.0, 1.0)
        else:
            air = layer["air"]
            tone = tuple(rock_tone[k] * (1 - air) + haze_tone[k] * air for k in range(3))
        mix.inputs["Color2"].default_value = (tone[0], tone[1], tone[2], 1.0)
        if not s.get("only_ridges"):
            # (mist lies in the valleys: a range is paler toward its foot, its own tone at its crest)
            share = nt.nodes.new("ShaderNodeMath")
            share.operation = "DIVIDE"
            share.use_clamp = True
            nt.links.new(degrees.outputs[0], share.inputs[0])
            nt.links.new(crest.outputs["Result"], share.inputs[1])
            foot = nt.nodes.new("ShaderNodeMapRange")
            foot.inputs["To Min"].default_value = 0.55
            foot.inputs["To Max"].default_value = 0.0
            nt.links.new(share.outputs[0], foot.inputs["Value"])
            misted = nt.nodes.new("ShaderNodeMixRGB")
            misted.inputs["Color1"].default_value = (tone[0], tone[1], tone[2], 1.0)
            misted.inputs["Color2"].default_value = (haze_tone[0], haze_tone[1], haze_tone[2], 1.0)
            nt.links.new(foot.outputs["Result"], misted.inputs["Fac"])
            nt.links.new(misted.outputs["Color"], mix.inputs["Color2"])
        nt.links.new(shown.outputs[0], mix.inputs["Fac"])
        if s.get("only_ridges") and last is behind:
            mix.inputs["Color1"].default_value = (0.0, 0.0, 0.0, 1.0)
        else:
            nt.links.new(last.outputs["Color"], mix.inputs["Color1"])
        last = mix
    return last


def check_ridges(s):
    """THE RANGES HELD TO WHAT WAS ASKED: the ranges alone, white on black, through the four side cameras -> the crest
    line read off the pictures column by column. It must stand on every compass side, never higher than the height
    asked, reach most of that height somewhere, and meet itself across the four seams between faces"""
    import bpy
    import shutil
    import tempfile

    scratch = tempfile.mkdtemp(prefix="kit_sky_ridges_")
    size = 256
    try:
        probe = dict(s, clouds=0.0, size=size, name="ridges", out=scratch, only_ridges=True, view="Standard", strength=1.0)
        build_world(probe)
        files = render_faces(probe)
        line = []  # (compass side, the crest's height in degrees, its face)
        for face in ("ft", "lf", "bk", "rt"):
            img = bpy.data.images.load(files[face])
            px = list(img.pixels)  # (rows from the BOTTOM, rgba)
            bpy.data.images.remove(img)
            tops = []
            for col in range(size):
                top = None
                for row in range(size - 1, -1, -1):  # (from the top of the picture down)
                    if px[(row * size + col) * 4] > 0.5:
                        top = row
                        break
                if top is None:
                    fail(f"sky: no ridge stands in the face {face} at column {col}: a range has a gap")
                way = rules.direction(face, (col + 0.5) / size, 1 - (top + 1.0) / size)
                tops.append((rules.compass(way), rules.elevation(way), face))
            line += tops
        line.sort()
        highest = max(e for _, e, _ in line)
        lowest = min(e for _, e, _ in line)
        asked = s["ridge_height"]
        if highest > asked + 1.0:
            fail(f"sky: a crest stands {highest:.1f} degrees over the horizon, higher than the {asked:g} asked")
        if highest < asked * 0.6:
            fail(f"sky: the highest crest stands {highest:.1f} degrees over the horizon: far under the {asked:g} asked")
        if lowest < 0.2:
            fail(f"sky: the ridge line falls to the horizon ({lowest:.2f} degrees): a range has a gap")
        # across a seam: sorted round the compass, two neighbours are a column apart whether they lie in one face or
        # in two; the crest may step between two faces no more than half as much again as the steepest step inside a
        # face (half a degree at least). The ranges are in the shader by the ray's own way, so this cannot fail while
        # the cameras are right: it is the cameras' check said once more, on the ranges
        inside, worst = 0.0, 0.0
        for k in range(len(line)):
            p, q = line[k], line[(k + 1) % len(line)]
            step = abs(p[1] - q[1])
            if p[2] == q[2]:
                inside = max(inside, step)
            else:
                worst = max(worst, step)
        if worst > max(0.5, inside * 1.5):
            fail(f"sky: the ridge line steps {worst:.1f} degrees across a seam between two faces "
                 f"(inside a face it steps {inside:.1f} at most)")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if bpy.context.scene.world:
            bpy.data.worlds.remove(bpy.context.scene.world)
        for cam in [o for o in bpy.data.objects if o.type == "CAMERA"]:
            bpy.data.objects.remove(cam)
    return {"highest_degrees": round(highest, 2), "lowest_degrees": round(lowest, 2), "seam_step_degrees": round(worst, 2),
            "steepest_step_degrees": round(inside, 2)}


def render_faces(s):
    import bpy
    from mathutils import Matrix

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = s["size"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = s.get("view", "AgX")
    cam_data = bpy.data.cameras.new("face")
    cam_data.type = "PERSP"
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.angle = math.pi / 2
    cam_data.clip_start, cam_data.clip_end = 0.1, 1000.0
    cam = bpy.data.objects.new("face", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    files = {}
    for face in rules.FACES:
        rows = rules.camera_matrix(face)
        cam.matrix_world = Matrix((rows[0] + [0.0], rows[1] + [0.0], rows[2] + [0.0], [0.0, 0.0, 0.0, 1.0]))
        path = os.path.join(s["out"], f'{s["name"]}_{face}.png')
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        files[face] = path
    return files


def brightest(files, size):
    """the brightest spot of the six pictures -> (face, u, v, how bright 0..3), the middle of its brightest pixels"""
    import bpy

    best = (None, 0.0, 0.0, -1.0)
    for face, path in files.items():
        img = bpy.data.images.load(path)
        px = list(img.pixels)  # (rows from the BOTTOM, rgba)
        top = -1.0
        spots = []
        for i in range(0, len(px), 4):
            b = px[i] + px[i + 1] + px[i + 2]
            if b > top + 1e-6:
                top, spots = b, [i // 4]
            elif abs(b - top) <= 1e-6:
                spots.append(i // 4)
        if top > best[3] + 1e-6 and len(spots) < size * size / 4:  # (a picture that is all one white is no spot)
            cols = [k % size for k in spots]
            rows = [k // size for k in spots]
            u = (sum(cols) / len(cols) + 0.5) / size
            v = 1 - (sum(rows) / len(rows) + 0.5) / size
            best = (face, u, v, top)
        bpy.data.images.remove(img)
    return best


def check_cameras(s):
    """THE CAMERAS HELD TO THE TABLE: six test suns (one off the middle of each face) alone on a black sky, through the
    six cameras, in pictures of their own that are thrown away -> how far off the worst one is, in degrees; a run
    whose cameras are off fails here"""
    import bpy
    import shutil
    import tempfile

    suns = rules.test_suns()
    scratch = tempfile.mkdtemp(prefix="kit_sky_check_")
    try:
        probe = dict(s, clouds=0.0, size=128, name="check", out=scratch, only_sun=list(suns.values()), view="Standard")
        build_world(probe)
        small = render_faces(probe)
        worst = 0.0
        for face, vector in suns.items():
            got = brightest({face: small[face]}, probe["size"])
            off = rules.apart(rules.direction(face, got[1], got[2]), vector) if got[0] else 180.0
            worst = max(worst, off)
            if off > 3.0:
                want = rules.falls(vector)
                fail(f"sky: the camera of the face {face} does not show what sky.py says it does: its test sun belongs at "
                     f"{want[1]:.2f}, {want[2]:.2f} of its picture and shows at {got[1]:.2f}, {got[2]:.2f} ({off:.0f} degrees off)")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if bpy.context.scene.world:
            bpy.data.worlds.remove(bpy.context.scene.world)
        for cam in [o for o in bpy.data.objects if o.type == "CAMERA"]:
            bpy.data.objects.remove(cam)
    return {"faces": len(suns), "worst_degrees": round(worst, 2)}


def check_light(s, files):
    """THE AIR'S OWN LIGHT IS ON THE SUN'S SIDE: the face toward the asked sun's compass side is brighter than the one
    behind it (Blender turns the sky texture's sun by its own rule, the kit turns the disc by sky.py's: they must
    agree) -> {face: brightness} for the two, or None when the sun is too low or too high for a side to show"""
    import bpy

    if not 3 <= s["sun"][0] <= 60:
        return None
    flat = rules.sun_vector(0, s["sun"][1])
    toward, _, _ = rules.falls(flat)
    behind, _, _ = rules.falls(tuple(-c for c in flat))
    light = {}
    for face in (toward, behind):
        img = bpy.data.images.load(files[face])
        px = list(img.pixels)
        light[face] = sum(px[i] + px[i + 1] + px[i + 2] for i in range(0, len(px), 4)) / (len(px) / 4)
        bpy.data.images.remove(img)
    if light[toward] <= light[behind]:
        fail(f"sky: the sky is brighter behind the sun ({behind}: {light[behind]:.2f}) than toward it ({toward}: "
             f"{light[toward]:.2f}): the air's light and the sun's disc are turned apart")
    return {toward: round(light[toward], 3), behind: round(light[behind], 3)}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    s, why = rules.arguments(argv)
    if why:
        fail(why)
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    s["out"] = os.path.abspath(s["out"])  # (Blender resolves a relative path against the .blend, not where it was run)
    os.makedirs(s["out"], exist_ok=True)
    mine = [s["name"] + ".sky.json"] + [f'{s["name"]}_{face}.png' for face in rules.FACES]

    def clear():
        for name in mine:
            if os.path.isfile(os.path.join(s["out"], name)):
                os.remove(os.path.join(s["out"], name))

    clear()  # (nothing of an earlier sky of this name is left to be taken for this one)
    vector = rules.sun_vector(*s["sun"])
    want = rules.falls(vector)
    checked = {"asked": {"face": want[0], "u": round(want[1], 3), "v": round(want[2], 3)}}
    try:
        checked["cameras"] = check_cameras(s)
        if s["ridges"] > 0:
            checked["ridges"] = check_ridges(s)
        build_world(s)
        files = render_faces(s)
        checked["light"] = check_light(s, files)
    except BaseException:
        clear()  # (a sky that failed leaves no pictures and no record)
        raise
    record = {"name": s["name"], "faces": {rules.PROPERTY[f]: os.path.basename(p) for f, p in files.items()},
              "sun": {"elevation": s["sun"][0], "azimuth": s["sun"][1], "vector": [round(c, 5) for c in vector],
                      "drawn": s["sun"][0] > 0},
              "clouds": s["clouds"], "seed": s["seed"], "size": s["size"], "checked": checked}
    if s["ridges"] > 0:
        # (mountains do not wheel round the horizon with the hour: a sky with ridges is not turned to the light)
        record["ridges"] = {"count": s["ridges"], "height": s["ridge_height"], "layers": rules.ridge_layers(s["ridges"], s["ridge_height"])}
        record["fixed"] = True
    with open(os.path.join(s["out"], s["name"] + ".sky.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    said = "the six cameras, the light's side" if checked["light"] else \
        "the six cameras; the light's side NOT checked: the sun stands under 3 or over 60 degrees"
    if s["sun"][0] <= 0:
        said += "; the sun is under the horizon: no disc is drawn"
    if s["ridges"] > 0 and 0 < s["sun"][0] < s["ridge_height"]:
        said += (f'; the sun stands {s["sun"][0]:g} degrees up and the ranges up to {s["ridge_height"]:g}: its disc may be '
                 f'hidden behind a crest')
    if s["ridges"] > 0:
        r = checked["ridges"]
        said += (f'; {s["ridges"]} far ridge(s), crests {r["lowest_degrees"]} to {r["highest_degrees"]} degrees up, '
                 f'unbroken round the horizon: this sky is NOT turned to the light in the game (render it with the '
                 f'sun where the world\'s light is)')
    print(json.dumps({"status": "pass",
                      "summary": f'sky: {s["name"]}: six faces of {s["size"]} px -> {s["out"]} (checked: {said})',
                      "next_action": "LOOK at the six pictures; they are not in a game until they are uploaded"}))


if __name__ == "__main__":
    main()
