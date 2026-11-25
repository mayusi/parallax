"""rbx_lookdev.py — how a built asset is SHOWN to the owner (the 3D crafts plan, S0; board card macm).

The owner judges 3D in Blender itself, in Material Preview under its default forest HDRI ("the pictures don't do it
enough justice"). Every full build's .blend is saved dressed for that:
  owner_view()      every 3D viewport opens in Material Preview, forest HDRI, scene lights and world off (his view);
  light_rig(...)    a world + light that are a ROBLOX LOOK: a place's Lighting (kit/blender/roblox_looks.json, read from
                    his place in Studio) mapped to EEVEE;
  dress(scene, game) his view + two more scenes of the same file, "Roblox look - day" / "- as read" (the build's meshes
                    linked, each with its own Roblox look): the Scene list -> a Roblox look, then Z -> Rendered. The
                    build's own scene is never changed; undo() after the save removes the two scenes.

Roblox Lighting -> Blender, approximate (the owner's eye calibrates SUN_PER_BRIGHTNESS and MOON_SHARE):
  the key light: the place's MOON when its sun is below the horizon (Roblox's own GetMoonDirection), else its sun;
    a "day" variant puts a midday sun at DAY_ELEVATION instead (not measured: the place's clock is never changed);
  strength = Brightness * SUN_PER_BRIGHTNESS (* MOON_SHARE for the moon) * 2^ExposureCompensation;
  colour = white tinted halfway to ColorShift_Top (the hue on surfaces facing the sun or moon);
  softness: ShadowSoftness -> the light's angle;
  the sky light: a gradient, ground = Ambient, horizon = OutdoorAmbient, zenith = OutdoorAmbient tinted by
    ColorShift_Top, at strength (0.5 + 0.5 * EnvironmentDiffuseScale) * 2^ExposureCompensation;
  Roblox axes (Y up, -Z front) -> Blender (Z up, front +Y): (x, y, z) -> (x, -z, y).
  Not carried: bloom, colour grading, atmosphere haze, sun rays, depth of field, the skybox picture.
"""

import json
import math
import os

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LOOKS = os.path.join(HERE, "roblox_looks.json")
SUN_PER_BRIGHTNESS = 3.5   # Blender sun W/m2 per unit of Roblox Brightness (AgX view; assumed, not measured)
MOON_SHARE = 0.15          # the moon's light against the sun's at the same Brightness (assumed, not measured)
DAY_ELEVATION = 50.0       # the "day" variant's sun height, degrees (assumed)
DEFAULT_PRESET = "Default"   # a typical daylight place: the light for every piece no game preset names
OWNER_HDRI = "forest.exr"  # Blender's default Material Preview world, the owner's own view


def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin3(rgb):
    return [srgb_to_linear(float(v)) for v in rgb]


def presets():
    with open(LOOKS, encoding="utf-8") as fh:
        return {k: v for k, v in json.load(fh).items() if not k.startswith("_")}


_CAL = []   # (read once a process: a build never mixes two calibrations, nor a half-written file's)


def _has_transform(name):
    """is this colour curve in this Blender (the view transforms come from its colour configuration)"""
    try:
        vs = bpy.context.scene.view_settings
    except AttributeError:
        return True
    was = vs.view_transform
    try:
        vs.view_transform = name
        vs.view_transform = was
        return True
    except TypeError:
        return False


def calibration():
    """the rig FITTED to Roblox Studio (roblox_looks.json "_calibration", written by kit/tools/studio_calibrate.py fit
    from a grey sphere shot in Studio under several Lighting states) -> its numbers, or None (the assumed rig below).
    None too when this Blender lacks the fitted colour curve: the numbers were solved under it, and under another
    curve they are several grey levels off (review 2026-11-18) - the assumed rig is then used, and said"""
    if not _CAL:
        cal = None
        try:
            with open(LOOKS, encoding="utf-8") as fh:
                cal = json.load(fh).get("_calibration")
        except (OSError, ValueError):
            cal = None
        need = ("view_transform", "sun_per_brightness", "ambient_strength", "sky_strength", "sky_colour")
        if not (isinstance(cal, dict) and all(k in cal for k in need)):
            cal = None
        elif not _has_transform(cal["view_transform"]):
            print(f"[rbx_lookdev] this Blender has no '{cal['view_transform']}' colour curve: the ASSUMED Roblox "
                  "look is used, not the one fitted to Studio")
            cal = None
        _CAL.append(cal)
    return _CAL[0]


def roblox_view(scene):
    """the picture's colour curve of a Roblox look: the fitted one (Roblox squeezes bright light; AgX and Standard
    fit it worse - measured), else the scene's own. -> restore(): puts the scene's curve AND look back"""
    vs = scene.view_settings
    was, look = vs.view_transform, vs.look
    cal = calibration()
    if cal:
        vs.view_transform = cal["view_transform"]
        vs.look = "None"

    def restore():
        vs.view_transform = was
        try:
            vs.look = look
        except TypeError:
            pass

    return restore


def preset_for(game):
    """the place's look for a game (its own preset when there is one), else the default preset"""
    ps = presets()
    return (game if game in ps else DEFAULT_PRESET), ps.get(game) or ps[DEFAULT_PRESET]


def game_of_build():
    """the game a build is for, from KIT_BUILD (games/<Name>/build), else None (the kit home)"""
    kb = (os.environ.get("KIT_BUILD") or "").replace("\\", "/").rstrip("/")
    parts = kb.split("/")
    if len(parts) >= 3 and parts[-1] == "build" and parts[-3] == "games":
        return parts[-2]
    return None


def to_blender(v):
    return Vector((v[0], -v[2], v[1]))


def fitted_light(p, cal, variant="as_read"):
    """THE fitted rule - one formula, used by the rig (calibrated_rig) and by the fit that solved its numbers
    (kit/blender/studio_fit.py), so the two can never drift apart: a place's Lighting `p` and the fitted numbers
    `cal` -> (direction TO the key light in Blender space, its strength W/m2, the world's even colour (linear RGB),
    what the key is). Measured 2026-11-18 on a grey sphere in Studio:
      by day the sun, white, Brightness x sun_per_brightness;
      at night the moon at moon_share of that, plus the night sky's light along the moon (EnvironmentDiffuseScale x
        night_sky_key - the default night sky is bright toward the moon, near black away); no key light when the moon
        is below the ground too;
      the world: the larger of Ambient and OutdoorAmbient x ambient_strength, plus EnvironmentDiffuseScale x the
        default sky's colour x sky_strength (x night_sky at night); everything x 2^ExposureCompensation."""
    gain = 2.0 ** float(p.get("ExposureCompensation", 0.0))
    eds = float(p.get("EnvironmentDiffuseScale", 0.0))
    sun_power = float(p.get("Brightness", 2.0)) * float(cal["sun_per_brightness"]) * gain
    night = False
    if variant == "day":
        e = math.radians(DAY_ELEVATION)
        d = Vector((-0.55, 0.83, 0.0)).normalized() * math.cos(e) + Vector((0, 0, math.sin(e)))
        energy, what = sun_power, f"a midday sun at {DAY_ELEVATION:g} deg (assumed)"
    else:
        d = to_blender(p.get("SunDirection") or (0.0, 1.0, 0.0))
        if d.z > 0.02:
            energy, what = sun_power, "the place's sun (as read)"
        else:
            night = True
            d = to_blender(p.get("MoonDirection") or (0.0, 1.0, 0.0))
            if d.z <= 0.0:
                energy, what = 0.0, "no key light (the sun and the moon are both below the horizon)"
            else:
                energy = sun_power * float(cal.get("moon_share", MOON_SHARE)) + eds * float(
                    cal.get("night_sky_key", 0.0)) * gain
                what = "the place's moon and the night sky round it (as read)"
    amb = [max(a, b) for a, b in zip(lin3(p.get("Ambient", (0, 0, 0))), lin3(p.get("OutdoorAmbient", (0, 0, 0))))]
    sky = eds * float(cal["sky_strength"]) * (float(cal.get("night_sky", 1.0)) if night else 1.0)
    col = [(a * float(cal["ambient_strength"]) + sky * float(c)) * gain for a, c in zip(amb, cal["sky_colour"])]
    return d.normalized(), energy, col, what


def key_light(p, variant):
    """(direction TO the light in Blender space, strength, what it is)"""
    gain = 2.0 ** float(p.get("ExposureCompensation", 0.0))
    cal = calibration()
    if cal:
        d, energy, _, what = fitted_light(p, cal, variant)
        return d, energy, what
    base = float(p.get("Brightness", 2.0)) * SUN_PER_BRIGHTNESS * gain
    if variant == "day":
        e = math.radians(DAY_ELEVATION)
        d = Vector((-0.55, 0.83, 0.0)).normalized() * math.cos(e) + Vector((0, 0, math.sin(e)))
        return d.normalized(), base, f"a midday sun at {DAY_ELEVATION:g} deg (assumed)"
    sun = to_blender(p.get("SunDirection") or (0.0, 1.0, 0.0))
    if sun.z > 0.02:
        return sun.normalized(), base, "the place's sun (as read)"
    moon = to_blender(p.get("MoonDirection") or (0.0, 1.0, 0.0))
    return moon.normalized(), base * MOON_SHARE, "the place's moon (as read; its sun is below the horizon)"


def light_rig(scene, name, p, variant="as_read"):
    """a world + key light for the preset -> (made datablocks, label); the scene's world is set to it. FITTED to
    Studio when roblox_looks.json has a "_calibration" (calibrated_rig), else the assumed mapping below"""
    if calibration():
        return calibrated_rig(scene, name, p, variant)
    made = []
    tint = [min(1.0, c) for c in lin3(p.get("ColorShift_Top", (255, 255, 255)))]
    peak = max(tint) or 1.0
    tint = [c / peak for c in tint]
    colour = [1.0 + 0.5 * (c - 1.0) for c in tint]
    d, strength, what = key_light(p, variant)
    light = bpy.data.lights.new("Roblox key light", "SUN")
    light.energy = strength
    light.color = colour
    light.angle = math.radians(1.0 + 30.0 * float(p.get("ShadowSoftness", 0.2)))
    if hasattr(light, "use_shadow"):
        light.use_shadow = True
    obj = bpy.data.objects.new("Roblox key light", light)
    scene.collection.objects.link(obj)
    obj.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    made += [obj, light]
    label = f"Roblox look: {name}" + (" (day)" if variant == "day" else "")
    world = bpy.data.worlds.new(label)
    if hasattr(world, "use_nodes") and not world.node_tree:
        world.use_nodes = True
    nt = world.node_tree
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None) or nt.nodes.new("ShaderNodeBackground")
    out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None) or nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value, rng.inputs["From Max"].default_value = -1.0, 1.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ground, horizon = lin3(p.get("Ambient", (0, 0, 0))), lin3(p.get("OutdoorAmbient", (127, 127, 127)))
    zenith = [h * (0.5 + 0.5 * t) for h, t in zip(horizon, tint)]
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*ground, 1.0)
    els[1].position, els[1].color = 1.0, (*zenith, 1.0)
    mid = els.new(0.5)
    mid.color = (*horizon, 1.0)
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], rng.inputs["Value"])
    nt.links.new(rng.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    gain = 2.0 ** float(p.get("ExposureCompensation", 0.0))
    bg.inputs["Strength"].default_value = (0.5 + 0.5 * float(p.get("EnvironmentDiffuseScale", 1.0))) * gain
    scene.world = world
    made.append(world)
    return made, f"{label} — key: {what}, {strength:.1f} W/m2"


def calibrated_rig(scene, name, p, variant="as_read"):
    """the rig as Studio was MEASURED to light a grey sphere (2026-11-18, kit/tools/studio_calibrate.py):
      the sun white (ColorShift_Top black or white changed nothing), Brightness x sun_per_brightness x 2^Exposure;
      the ambient ONE even colour - the larger of Ambient and OutdoorAmbient (either alone lit it the same, both
        together no more) x ambient_strength - plus the sky's own light (EnvironmentDiffuseScale x its colour x its
        strength), all x 2^Exposure; at night the moon (Brightness x the sun's number x moon_share) plus the night
        sky's light along the moon (EnvironmentDiffuseScale x night_sky_key), and the sky's even glow at night_sky of
        its daylight. The sky is Roblox's DEFAULT sky's: a place's own Sky was not measured. Call
        roblox_view(scene) for the fitted colour curve.
    -> (made datablocks, label)"""
    cal = calibration()
    made = []
    d, strength, col, what = fitted_light(p, cal, variant)
    light = bpy.data.lights.new("Roblox key light", "SUN")
    light.energy = strength
    light.color = (1.0, 1.0, 1.0)
    light.angle = math.radians(1.0 + 30.0 * float(p.get("ShadowSoftness", 0.2)))
    if hasattr(light, "use_shadow"):
        light.use_shadow = True
    obj = bpy.data.objects.new("Roblox key light", light)
    scene.collection.objects.link(obj)
    obj.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    made += [obj, light]
    label = f"Roblox look: {name}" + (" (day)" if variant == "day" else "") + " (fitted to Studio)"
    world = bpy.data.worlds.new(label)
    if hasattr(world, "use_nodes") and not world.node_tree:
        world.use_nodes = True
    nt = world.node_tree
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None) or nt.nodes.new("ShaderNodeBackground")
    out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None) or nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    bg.inputs["Color"].default_value = (*col, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    scene.world = world
    made.append(world)
    return made, f"{label} — key: {what}, {strength:.1f} W/m2"


def eevee(scene, samples=32):
    scene.render.engine = "BLENDER_EEVEE"
    ev = scene.eevee
    for attr, val in (("taa_render_samples", samples), ("use_raytracing", True), ("use_shadows", True)):
        if hasattr(ev, attr):
            try:
                setattr(ev, attr, val)
            except (AttributeError, TypeError):
                pass


def owner_view(hdri=OWNER_HDRI):
    """every 3D viewport of the saved file: Material Preview under the forest HDRI, scene lights/world off (Rendered
    mode keeps them on: Z -> Rendered shows the Roblox look) -> how many viewports were set"""
    n = 0
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D":
                    continue
                sh = space.shading
                sh.type = "MATERIAL"
                for attr, val in (("use_scene_lights", False), ("use_scene_world", False),
                                  ("use_scene_lights_render", True), ("use_scene_world_render", True)):
                    if hasattr(sh, attr):
                        setattr(sh, attr, val)
                try:
                    sh.studio_light = hdri
                except (TypeError, ValueError):
                    pass
                n += 1
    return n


def dress(scene, game=None):
    """the saved .blend's look for the owner: his view in every viewport, and the game's Roblox look as TWO more
    scenes of the same file ("Roblox look - day", "Roblox look - as read": the build's own meshes LINKED, each with its
    world, its light and EEVEE). The build's own scene keeps its world, engine and lights untouched, so every tool that
    opens the .blend (kit look closeup / lookdev / edges / zebra, game_fidelity, kit optimize) renders it as before.
    The owner: the Scene list at the top -> a Roblox look, then Z -> Rendered.
    Returns (undo, facts): undo() removes the two scenes and what they made."""
    name, p = preset_for(game)
    first = "as_read" if game == name else "day"   # (a kit-home piece: the place's light at midday comes first)
    meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    looks, made, labels = [], [], {}
    for variant in (first, "day" if first == "as_read" else "as_read"):
        look = bpy.data.scenes.new("Roblox look - " + ("day" if variant == "day" else "as read"))
        for o in meshes:
            look.collection.objects.link(o)
        made_, labels[variant] = light_rig(look, name, p, variant)
        eevee(look)
        look.view_settings.view_transform = scene.view_settings.view_transform
        roblox_view(look)                           # (the fitted colour curve, when there is one)
        looks.append(look)
        made += made_
    views = owner_view()

    def undo():
        for d in made:
            try:
                if isinstance(d, bpy.types.Object):
                    bpy.data.objects.remove(d, do_unlink=True)
                elif isinstance(d, bpy.types.Light):
                    bpy.data.lights.remove(d)
                elif isinstance(d, bpy.types.World):
                    bpy.data.worlds.remove(d)
            except ReferenceError:
                pass
        for lk in looks:
            try:
                bpy.data.scenes.remove(lk)
            except ReferenceError:
                pass

    return undo, {"roblox_look": labels[first], "roblox_looks": [lk.name for lk in looks], "preset": name,
                  "owner_view": f"Material Preview, {OWNER_HDRI}", "viewports": views, "source": p.get("source")}
