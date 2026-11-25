"""studio_fit.py - the Roblox-look rig FITTED to Studio (kit/tools/studio_calibrate.py fit): the calibration sphere
(kit/studio/calib_sphere.py) rendered under each Lighting state Studio was shot in, and the rig's numbers solved so
its picture reads as Studio's.

blender -b <_kit_calib_sphere.blend> --factory-startup --python-exit-code 2 -P studio_fit.py -- <manifest> <states.json> <out.json>

states.json: [{"name", "look" (the shot's look.json), "studio": {"p5", "p50", "p95"} (the sphere's luminance in
Studio, 0-255)}]. The rig fitted (rbx_lookdev.calibrated_rig takes the same numbers):
  the sun: Brightness x sun_per_brightness x 2^ExposureCompensation W/m2, white;
  the ambient: ONE even colour - the larger of Ambient and OutdoorAmbient (measured 2026-11-18: either alone lit
    the sphere the same, both together no more) x ambient_strength x 2^EC - plus the sky's own light
    (EnvironmentDiffuseScale x sky_colour x sky_strength);
  the picture: the view transform whose curve fits Studio's best (Brightness 2 -> 4 is not twice as bright there).
Fitted: per view transform, sun_per_brightness on the sun-only states' lit side (p95), ambient_strength on the
ambient-only states (p50), sky on the sky-only state; the transform with the least error over EVERY state wins.
Prints FIT {json}."""

import json
import math
import os
import sys
import tempfile

import bpy
import numpy as np
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rbx_lookdev  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:]
MANIFEST, STATES, OUT = ARGS[0], ARGS[1], ARGS[2]
with open(STATES, encoding="utf-8") as fh:
    states = json.load(fh)
SCALE = 0.5                      # (half the shot's size: the percentiles hold, the renders are four times quicker)
LUM = np.array([0.2126, 0.7152, 0.0722])
TMP = tempfile.mkdtemp(prefix="kitfit_")

scene = bpy.context.scene
for obj in scene.objects:
    if obj.type == "LIGHT":
        obj.hide_render = True
rbx_lookdev.eevee(scene)
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.look = "None"

cam_data = bpy.data.cameras.new("fit")
cam_data.sensor_fit = "VERTICAL"
cam = bpy.data.objects.new("fit", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
sun_data = bpy.data.lights.new("fit sun", "SUN")
sun = bpy.data.objects.new("fit sun", sun_data)
scene.collection.objects.link(sun)
world = bpy.data.worlds.new("fit world")
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
scene.world = world


def lin(c):
    return [rbx_lookdev.srgb_to_linear(float(v)) for v in c]


def place(look):
    c = look["camera"]
    pos = rbx_lookdev.to_blender(c["position"])
    fwd = rbx_lookdev.to_blender(c["look"]).normalized()
    up = rbx_lookdev.to_blender(c["up"]).normalized()
    right = fwd.cross(up).normalized()
    up = right.cross(fwd).normalized()
    cam.matrix_world = Matrix(((right.x, up.x, -fwd.x, pos.x), (right.y, up.y, -fwd.y, pos.y),
                               (right.z, up.z, -fwd.z, pos.z), (0, 0, 0, 1)))
    cam_data.angle_y = math.radians(float(c["fov"]))
    w, h = c["viewport"]
    scene.render.resolution_x, scene.render.resolution_y = int(w * SCALE), int(h * SCALE)


def light(look, p):
    """the fitted rule itself (rbx_lookdev.fitted_light: the rig uses the same function), with the trial numbers p"""
    d, energy, col, _ = rbx_lookdev.fitted_light(look, p, "as_read")
    sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sun_data.energy = energy
    sun_data.color = (1.0, 1.0, 1.0)
    sun_data.angle = math.radians(1.0 + 30.0 * float(look.get("ShadowSoftness", 0.2)))
    bg.inputs["Color"].default_value = (*col, 1.0)
    bg.inputs["Strength"].default_value = 1.0


def measure(look, p, transform):
    scene.view_settings.view_transform = transform
    place(look)
    light(look, p)
    path = os.path.join(TMP, "r.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)
    bpy.data.images.remove(img)
    m = px[..., 3] > 0.5
    lum = (px[..., :3][m] * 255.0) @ LUM        # (the PNG's own sRGB values, as Studio's picture is read)
    return {"p5": float(np.percentile(lum, 5)), "p50": float(np.percentile(lum, 50)), "p95": float(np.percentile(lum, 95))}


BOUNDS = []   # (the solved numbers that ran into the end of their search: the target was out of reach - said)


def solve(fn, target, lo, hi, steps=14, name="?"):
    """a monotone rising fn: the x in [lo, hi] (geometric) where fn(x) meets target; one that lands within 2% of an
    end of the search is noted in BOUNDS (the light could not reach Studio's value there)"""
    lo0, hi0 = lo, hi
    for _ in range(steps):
        mid = math.sqrt(lo * hi)
        if fn(mid) < target:
            lo = mid
        else:
            hi = mid
    x = math.sqrt(lo * hi)
    if x < lo0 * 1.02 or x > hi0 / 1.02:
        BOUNDS.append(name)
    return x


def is_night(look):
    return rbx_lookdev.to_blender(look.get("SunDirection") or (0, 1, 0)).z <= 0.02


def kind(look):
    if is_night(look):
        return "night"
    b = float(look.get("Brightness", 0)) > 0
    a = max(max(look.get("Ambient", (0, 0, 0))), max(look.get("OutdoorAmbient", (0, 0, 0)))) > 0
    s = float(look.get("EnvironmentDiffuseScale", 0)) > 0
    return {(True, False, False): "sun", (False, True, False): "ambient", (False, False, True): "sky"}.get((b, a, s), "mixed")


def accepted(name):
    """(the view transforms are filled in by the colour configuration at run time: try each name)"""
    try:
        scene.view_settings.view_transform = name
        return True
    except TypeError:
        return False


transforms = [t for t in ("AgX", "Standard", "Khronos PBR Neutral", "Filmic") if accepted(t)]
results = {}
for transform in transforms:
    p = {"sun_per_brightness": rbx_lookdev.SUN_PER_BRIGHTNESS, "ambient_strength": 1.0, "sky_strength": 1.0,
         "sky_colour": [0.0, 0.0, 0.0], "moon_share": rbx_lookdev.MOON_SHARE, "night_sky": 1.0, "night_sky_key": 0.0}
    suns = [s for s in states if kind(s["look"]) == "sun" and not s["look"].get("ExposureCompensation")]
    if suns:
        # (solved on a plain sun - no colour shift - so the colour-shift state stays a real held-out check)
        plain = [s for s in suns if not any(s["look"].get("ColorShift_Top") or [0])] or suns
        s0 = min(plain, key=lambda s: s["look"]["Brightness"])
        p["sun_per_brightness"] = solve(
            lambda k: measure(s0["look"], {**p, "sun_per_brightness": k}, transform)["p95"], s0["studio"]["p95"],
            0.05, 200.0, name="sun_per_brightness")
    ambs = [s for s in states if kind(s["look"]) == "ambient"]
    if ambs:
        a0 = ambs[0]
        p["ambient_strength"] = solve(
            lambda k: measure(a0["look"], {**p, "ambient_strength": k}, transform)["p50"], a0["studio"]["p50"],
            0.01, 50.0, name="ambient_strength")
    skies = [s for s in states if kind(s["look"]) == "sky"]
    if skies:
        k0 = skies[0]
        # the sky's colour from Studio's picture of the sphere: its median colour, made linear and divided by the
        # sphere's own grey (0.5) - then its strength solved on the median luminance
        rgb = k0["studio"].get("rgb50") or [k0["studio"]["p50"]] * 3
        base = [rbx_lookdev.srgb_to_linear(v) / 0.5 for v in rgb]
        peak = max(base) or 1.0
        p["sky_colour"] = [b / peak for b in base]
        p["sky_strength"] = solve(
            lambda k: measure(k0["look"], {**p, "sky_strength": k}, transform)["p50"], k0["studio"]["p50"], 0.01, 50.0, name="sky_strength")
    nights = [s for s in states if kind(s["look"]) == "night"]
    night_targets = []
    if nights:
        def sky_of(s):
            return float(s["look"].get("EnvironmentDiffuseScale", 0))

        def amb_of(s):
            return any(s["look"].get("Ambient") or [0]) or any(s["look"].get("OutdoorAmbient") or [0])

        plain = [s for s in nights if not s["look"].get("ExposureCompensation")] or nights
        # the MOON where no sky light is on (a night with ambient only, else any night without sky): a night sky lights
        # the moon's side too, and counted as moonlight it made the moon too strong (held-out nights 2026-11-18:
        # moon + outdoor ambient was 30 grey levels too bright)
        moon_states = [s for s in plain if sky_of(s) == 0 and amb_of(s)] or [s for s in plain if sky_of(s) == 0] or plain
        nm = moon_states[0]
        p["moon_share"] = solve(
            lambda k: measure(nm["look"], {**p, "moon_share": k}, transform)["p95"], nm["studio"]["p95"], 0.005, 2.0,
            name="moon_share")
        night_targets.append(nm)
        # then the night SKY on a night with sky and no ambient: its even glow on the side the moon misses (p5), then
        # its light along the moon's direction on the lit side (p95) - the moon's own share now known
        sky_states = [s for s in plain if sky_of(s) > 0 and not amb_of(s)]
        if sky_states:
            ns = sky_states[0]
            p["night_sky"] = solve(
                lambda k: measure(ns["look"], {**p, "night_sky": k}, transform)["p5"], ns["studio"]["p5"], 0.0005,
                2.0, name="night_sky")
            p["night_sky_key"] = solve(
                lambda k: measure(ns["look"], {**p, "night_sky_key": k}, transform)["p95"], ns["studio"]["p95"],
                0.001, 50.0, name="night_sky_key")
            night_targets.append(ns)
    targets = {x["name"] for x in (([s0] if suns else []) + ([a0] if ambs else []) + ([k0] if skies else [])
                                   + night_targets)}
    rows, err = [], 0.0
    for s in states:
        got = measure(s["look"], p, transform)
        want = s["studio"]
        e = sum(abs(got[q] - want[q]) for q in ("p5", "p50", "p95")) / 3.0
        err += e
        rows.append({"name": s["name"], "studio": {q: round(want[q], 1) for q in ("p5", "p50", "p95")},
                     "twin": {q: round(got[q], 1) for q in ("p5", "p50", "p95")}, "error": round(e, 1),
                     "solved_on": s["name"] in targets})
    held = [r["error"] for r in rows if not r["solved_on"]]
    results[transform] = {"params": {k: (round(v, 4) if isinstance(v, float) else [round(c, 4) for c in v])
                                     for k, v in p.items()}, "mean_error": round(err / max(1, len(states)), 2),
                          "held_out_error": round(sum(held) / len(held), 2) if held else None,
                          "worst": max(rows, key=lambda r: r["error"]) if rows else None,
                          "at_bound": sorted(set(BOUNDS)), "states": rows}
    BOUNDS.clear()
best = min(results, key=lambda t: results[t]["mean_error"])
out = {"best": best, "results": results}
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1)
print("FIT " + json.dumps({"best": best, "errors": {t: r["mean_error"] for t, r in results.items()},
                           "params": results[best]["params"]}))
