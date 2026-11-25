"""flipbook.py — volumetric flipbooks for Roblox particles, rendered headless in Blender (Cycles volumes).

    blender -b --factory-startup --python-exit-code 2 -P kit/vfx/flipbook.py -- --specs assets/textures
            --out build/textures --registry assets/effects/_textures.json [--force] [name ...]

Procedural noise textures (textures.py) are flat. Real smoke, fire, explosions and energy have volume: lit
billows, a hot core, wisps. This renders a small 3D volume over N frames into a Grid4x4 / Grid8x8 sheet.
Spec: assets/textures/<name>.json with "engine": "blender":
  {"engine": "blender", "kind": "smoke|fire|explosion|energy", "size": 1024, "grid": 4, "seed": 3,
   "density": 1.0, "detail": 1.0, "grow": 1.0}
Output is GRAYSCALE + alpha (the preset's colour sequence tints it, exactly like the procedural textures), with a
transparent border on every cell. Only re-renders when the spec is newer than the PNG (renders take ~10-60 s).
The texture gate in textures.py checks the result; the registry gets an entry (grid, file) if it has none.
Prints one JSON line: {status, summary, next_action, flipbooks:[{name, file, seconds, rendered}]}.
"""

import json
import math
import os
import sys
import time

import bpy
import numpy as np

KINDS = ("smoke", "fire", "explosion", "energy")


def args():
    a = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    out = {"names": [], "force": False}
    i = 0
    while i < len(a):
        if a[i] == "--force":
            out["force"] = True
            i += 1
        elif a[i].startswith("--"):
            out[a[i][2:]] = a[i + 1]
            i += 2
        else:
            out["names"].append(a[i])
            i += 1
    return out


def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def scene_for(spec, cell):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.volume_step_rate = 2.0
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = cell
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
    sc.world = world
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(35), math.radians(-30), 0)
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.3
    cam.location = (0, -6, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    bpy.ops.mesh.primitive_cube_add(size=2.2)
    domain = bpy.context.active_object
    mat = bpy.data.materials.new("Vol")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (1, 1, 1, 1)
    vol.inputs["Anisotropy"].default_value = 0.3
    vol.inputs["Blackbody Intensity"].default_value = 0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "4D"
    noise.inputs["Scale"].default_value = 1.7
    noise.inputs["Detail"].default_value = 5 * spec.get("detail", 1.0)
    noise.inputs["Roughness"].default_value = 0.55
    # radial falloff: 1 at the centre -> 0 at radius R (R animated per frame)
    length = nt.nodes.new("ShaderNodeVectorMath")
    length.operation = "LENGTH"
    fall = node(nt, "ShaderNodeMapRange", **{"From Min": 0.0, "To Min": 1.0, "To Max": 0.0})
    fall.clamp = True
    thresh = node(nt, "ShaderNodeMapRange", **{"From Max": 1.0, "To Min": 0.0, "To Max": 1.0})
    thresh.clamp = True
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    dens = nt.nodes.new("ShaderNodeMath")
    dens.operation = "MULTIPLY"
    emit = nt.nodes.new("ShaderNodeMath")
    emit.operation = "MULTIPLY"
    ridge = nt.nodes.new("ShaderNodeMath")  # energy: |noise - 0.5| -> thin filaments
    ridge.operation = "ABSOLUTE"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = 0.5
    L = nt.links.new
    L(coord.outputs["Object"], noise.inputs["Vector"])
    L(coord.outputs["Object"], length.inputs[0])
    # lumpy silhouette: the noise pushes the edge in/out (round balls read as fake)
    lump = nt.nodes.new("ShaderNodeMath")
    lump.operation = "MULTIPLY_ADD"
    lump.inputs[1].default_value = -0.45
    L(noise.outputs["Fac"], lump.inputs[0])
    L(length.outputs["Value"], lump.inputs[2])
    L(lump.outputs["Value"], fall.inputs["Value"])
    if spec["kind"] == "energy":
        L(noise.outputs["Fac"], sub.inputs[0])
        L(sub.outputs["Value"], ridge.inputs[0])
        L(ridge.outputs["Value"], thresh.inputs["Value"])
        thresh.inputs["To Min"].default_value = 1.0  # small |n-0.5| = bright filament
        thresh.inputs["To Max"].default_value = 0.0
    else:
        L(noise.outputs["Fac"], thresh.inputs["Value"])
    L(thresh.outputs["Result"], mul.inputs[0])
    L(fall.outputs["Result"], mul.inputs[1])
    L(mul.outputs["Value"], dens.inputs[0])
    L(mul.outputs["Value"], emit.inputs[0])
    L(dens.outputs["Value"], vol.inputs["Density"])
    L(emit.outputs["Value"], vol.inputs["Emission Strength"])
    vol.inputs["Emission Color"].default_value = (1, 1, 1, 1)
    L(vol.outputs["Volume"], out.inputs["Volume"])
    domain.data.materials.append(mat)
    return sc, {"noise": noise, "fall": fall, "thresh": thresh, "dens": dens, "emit": emit, "vol": vol}


def frame_params(kind, k, spec):
    """k in 0..1 across the flipbook -> node settings for this frame."""
    g = spec.get("grow", 1.0)
    d = spec.get("density", 1.0)
    ease = 1 - (1 - k) ** 2
    if kind == "smoke":
        return {"R": (0.3 + 0.42 * ease * g), "lo": 0.36 + 0.2 * k**2, "hi": 0.7, "dens": 16 * d, "emit": 0.0, "w": k * 1.4}
    if kind == "fire":
        return {"R": (0.22 + 0.45 * ease * g), "lo": 0.36 + 0.24 * k, "hi": 0.7, "dens": 6 * d, "emit": 9 * (1 - 0.7 * k), "w": k * 2.2}
    if kind == "explosion":
        hot = max(0.0, 1 - k / 0.4)
        return {"R": (0.22 + 0.52 * ease * g), "lo": 0.34 + 0.22 * k**2, "hi": 0.7, "dens": (12 + 10 * k) * d, "emit": 12 * hot**1.5, "w": k * 1.8}
    # energy
    return {"R": 0.62, "lo": 0.0, "hi": 0.06, "dens": 0.6 * d, "emit": 10 * (0.6 + 0.4 * math.sin(k * math.pi)), "w": k * 3.0}


def render(name, spec, out_dir):
    size, grid = int(spec.get("size", 1024)), int(spec.get("grid", 4))
    if spec.get("kind") not in KINDS:
        raise ValueError(f'kind must be one of {", ".join(KINDS)}')
    if grid not in (2, 4, 8) or size not in (256, 512, 1024):
        raise ValueError("grid must be 2|4|8 and size 256|512|1024")
    cell = size // grid
    border = max(2, cell // 32)
    inner = cell - 2 * border
    sc, n = scene_for(spec, inner)
    frames = grid * grid
    sheet = np.zeros((size, size, 4), dtype=np.float32)
    seed = spec.get("seed", 1)
    tmp = os.path.join(out_dir, f"_{name}_frame.png")
    for f in range(frames):
        k = f / max(1, frames - 1)
        p = frame_params(spec["kind"], k, spec)
        n["noise"].inputs["W"].default_value = seed * 7.31 + p["w"]
        n["fall"].inputs["From Max"].default_value = p["R"]
        n["thresh"].inputs["From Min"].default_value = p["lo"]
        n["thresh"].inputs["From Max"].default_value = p["hi"]
        n["dens"].inputs[1].default_value = p["dens"]
        n["emit"].inputs[1].default_value = p["emit"]
        sc.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp)
        px = np.empty(inner * inner * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        px = px.reshape(inner, inner, 4)[::-1]  # Blender rows are bottom-up
        lum = np.clip(px[..., :3].max(axis=2), 0, 1)
        # grayscale for tinting: normalise so the brightest frame pixel ~ white, keep alpha from coverage
        lum = lum / max(lum.max(), 1e-3)
        a = np.clip(px[..., 3] * 1.4, 0, 1)
        row, col = divmod(f, grid)
        y0, x0 = row * cell + border, col * cell + border
        sheet[y0 : y0 + inner, x0 : x0 + inner, 0] = lum
        sheet[y0 : y0 + inner, x0 : x0 + inner, 1] = lum
        sheet[y0 : y0 + inner, x0 : x0 + inner, 2] = lum
        sheet[y0 : y0 + inner, x0 : x0 + inner, 3] = a
    if os.path.isfile(tmp):
        os.remove(tmp)
    # Blender's bundled python has no PIL: save through a Blender image (its rows are bottom-up)
    img = bpy.data.images.new(f"{name}_sheet", size, size, alpha=True)
    img.pixels.foreach_set(sheet[::-1].ravel())
    img.filepath_raw = os.path.join(out_dir, f"{name}.png")
    img.file_format = "PNG"
    img.save()
    return grid


def main():
    a = args()
    # absolute: Blender resolves relative image paths against its own base, not the working directory
    specs, out, registry = (os.path.abspath(a[k]) for k in ("specs", "out", "registry"))
    os.makedirs(out, exist_ok=True)
    names = a["names"] or sorted(f[:-5] for f in os.listdir(specs) if f.endswith(".json"))
    reg = {}
    if os.path.isfile(registry):
        with open(registry, encoding="utf-8") as fh:
            reg = json.load(fh)
    results, errors = [], []
    for nm in names:
        path = os.path.join(specs, f"{nm}.json")
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
        if spec.get("engine") != "blender":
            continue
        png = os.path.join(out, f"{nm}.png")
        fresh = os.path.isfile(png) and os.path.getmtime(png) >= os.path.getmtime(path)
        t0 = time.time()
        try:
            if fresh and not a["force"]:
                grid = int(spec.get("grid", 4))
            else:
                grid = render(nm, spec, out)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{nm}: {e}")
            continue
        if not isinstance(reg.get(nm), dict):
            reg[nm] = {
                "id": "",
                "fallback": "rbxasset://textures/particles/smoke_main.dds",
                "grid": grid,
                "file": f"build/textures/{nm}.png",
            }
        else:
            reg[nm]["grid"] = grid
        results.append({"name": nm, "file": os.path.relpath(png).replace("\\", "/"), "seconds": round(time.time() - t0, 1), "rendered": not fresh or a["force"]})
    if results:
        with open(registry, "w", encoding="utf-8", newline="\n") as fh:  # LF + the format kit upload writes (no churn)
            json.dump(reg, fh, indent=2, sort_keys=True)
            fh.write("\n")
    status = "fail" if errors else "pass"
    rendered = [r["name"] for r in results if r["rendered"]]
    print(
        json.dumps(
            {
                "schema": 1,
                "status": status,
                "summary": "; ".join(errors)
                if errors
                else f"{len(results)} blender flipbook(s) ({len(rendered)} rendered: {', '.join(rendered) or 'all fresh'})",
                "next_action": f"fix assets/textures/{errors[0]}" if errors else "none — proceed",
                "flipbooks": results,
            }
        )
    )
    sys.exit(1 if errors else 0)


main()
