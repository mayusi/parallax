"""build_studio_chart.py — the presentation studio must not LIE about colour. One chip at the centre of the frame, lit by
rbx.Asset._studio exactly as the hero shot is, re-rendered in each known albedo (18% grey, white, black, the starters'
woods, a white shell, red, gold, steel): every chip sees the SAME light, so the grey chip's render calibrates them all.
Checks, in numbers (exposure-normalised Lab): grey near middle grey; the colour chips within dE 8 of their true colour on
average; warm wood keeping >= 85% of its saturation; gold not reflecting itself dark (L >= 65, chroma >= 80% of true).
`-- --lie` renders with the OLD studio (AgX at 0 EV, no reflection sky): the selftest expects that to FAIL — proof the
check catches a lying studio. Used by `lune run kit selftest`. Never "fix" this file to pass."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import json  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx  # noqa: E402
from mathutils import Vector  # noqa: E402

LIE = "--lie" in sys.argv
CHIPS = [  # name, albedo (linear), metallic, roughness — grey FIRST (it calibrates the rest)
    ("grey18", (0.18, 0.18, 0.18), 0.0, 0.5), ("white80", (0.8, 0.8, 0.8), 0.0, 0.5), ("black04", (0.04, 0.04, 0.04), 0.0, 0.5),
    ("wood_chest", (0.42, 0.22, 0.10), 0.0, 0.8), ("wood_crate", (0.50, 0.32, 0.17), 0.0, 0.85), ("shell", (0.88, 0.89, 0.90), 0.1, 0.4),
    ("red", (0.60, 0.08, 0.06), 0.0, 0.5), ("gold", (0.86, 0.63, 0.20), 1.0, 0.3), ("steel", (0.25, 0.27, 0.30), 0.6, 0.5),
]
COLOUR = ("white80", "wood_chest", "wood_crate", "shell", "red")  # judged on dE (black and the metals: own checks)


def srgb_to_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lab(rgb):
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = m @ np.asarray(rgb, float) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


a = rbx.Asset("_selftest_studio", size=(1, 1, 0.05), ground=False)
sc = a.scene
d = (rbx.BL_FROM_RBX.to_3x3() @ Vector((-0.75, 0.4, -0.6))).normalized()  # the hero camera's direction
bpy.ops.mesh.primitive_plane_add(size=1.0)
chip = bpy.context.active_object
chip.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()  # facing the camera
mat = bpy.data.materials.new("Chip")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
chip.data.materials.append(mat)
cam = bpy.data.objects.new("ChartCam", bpy.data.cameras.new("ChartCam"))
sc.collection.objects.link(cam)
cam.location = d * 3.5
cam.data.lens = 50
cam.rotation_euler = (-cam.location).to_track_quat("-Z", "Y").to_euler()
sc.camera = cam
sc.render.engine = "CYCLES"
rbx.cycles_device(sc)
sc.cycles.samples = 24
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 160, 120
a._studio([chip], (0.42, 0.45, 0.5))
if LIE:  # the old studio: AgX at 0 EV, reflections of the dark room
    sc.view_settings.view_transform, sc.view_settings.exposure = "AgX", 0.0
    for n in sc.world.node_tree.nodes:
        if n.type == "BACKGROUND" and abs(n.inputs["Strength"].default_value - 1.5) < 1e-6:
            n.inputs["Strength"].default_value = 0.0
path = os.path.join(rbx.RENDERS, f"_selftest_studio{'_lie' if LIE else ''}.png")
got = {}
for nm, col, met, rough in CHIPS:
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    bsdf.inputs["Metallic"].default_value = met
    bsdf.inputs["Roughness"].default_value = rough
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(h, w, 4)
    got[nm] = px[h // 2 - 8:h // 2 + 8, w // 2 - 8:w // 2 + 8, :3].reshape(-1, 3).mean(axis=0)
gain = float(srgb_to_lin(got["grey18"]).mean() / 0.18)  # every chip saw this light: scale the albedos to it
res = {}
for nm, col, met, _ in CHIPS:
    lg, li = lab(srgb_to_lin(got[nm])), lab(np.clip(np.array(col) * gain, 0, 1))
    res[nm] = {"dE": float(np.linalg.norm(lg - li)), "L": float(lg[0]), "L_true": float(li[0]),
               "chroma": float(np.hypot(*lg[1:])), "chroma_true": float(np.hypot(*li[1:]))}
grey = float(got["grey18"].mean())
mean_de = float(np.mean([res[n]["dE"] for n in COLOUR]))
wood_sat = min(res[n]["chroma"] / res[n]["chroma_true"] for n in ("wood_chest", "wood_crate"))
gold = res["gold"]
problems = []
if not 0.40 <= grey <= 0.56:
    problems.append(f"18% grey renders at {grey:.2f} (middle grey is ~0.46)")
if mean_de > 8:
    problems.append(f"colours are dE {mean_de:.1f} off their true colour on average (limit 8)")
if wood_sat < 0.85:
    problems.append(f"warm wood keeps only {wood_sat:.0%} of its saturation (limit 85%)")
if gold["L"] < 65 or gold["chroma"] < 0.8 * gold["chroma_true"]:
    problems.append(f"gold renders dark/dull (L {gold['L']:.0f}, chroma {gold['chroma'] / gold['chroma_true']:.0%} of true)")
facts = f"grey {grey:.2f}, mean dE {mean_de:.1f}, wood saturation {wood_sat:.0%}, gold L {gold['L']:.0f}"
print(json.dumps({
    "schema": 1, "status": "fail" if problems else "pass",
    "summary": (f"studio LYING about colour: {'; '.join(problems)}" if problems else f"studio is honest: {facts}"),
    "next_action": ("fix rbx.studio_view / _studio (view transform, exposure, reflection sky) until the chart is true"
                    if problems else "none — proceed"),
    "chart": {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in res.items()}, "grey": round(grey, 3)}))
sys.exit(1 if problems else 0)
