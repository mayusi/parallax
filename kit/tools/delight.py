"""INVERSE RENDERING: the photographed light taken out of a scan's colour (the owner's limitations, D-R03: "Inverse
rendering is not a production geometry/material recovery solve ... Benchmark a constrained optimizer against the
existing fitting route; show held-out improvement without baking lighting errors into geometry or albedo"; the 3D
methods audit, stage L).

    python kit/tools/delight.py <name> [--work build/scan/<name>] [--out assets/models] [--steps 300]

A scan (kit/tools/photoscan.py) carries its colour AS PHOTOGRAPHED: the side the lamp lit is light, the far side
dark, and that shading is painted into the texture - in the game Roblox's own light then falls on a surface that
already has a light painted on it. A photographed texel is colour x light, and any split with the same product
fits the photos alike, so ONE ASSUMPTION picks the split: the thing's own colour does not depend on the way its
surface faces. The shading is then the part of the photographed brightness the facing explains (a least-squares
fit of the colour on 9 spherical-harmonic terms of the facing, a channel - what a matte surface under distant light
shows), and the colour without its light is the photographed colour divided by it, held to [0, 1] and to the
photographed colour's mean (light and colour share a scale). The geometry is never touched.
Then Mitsuba (vetted, local, on the GPU: VETLOG 2026-10-06) CHECKS and SCORES it, over the pixels both the photo's
cut-out and the scan cover (kit/tools/delight_mitsuba.py): the camera check (the outline, and the photographed colour
against each photo); under the SAME light how each colouring reproduces held-out photos (said, not judged: the
photographed colour IS that light); and - with --relight, photos of the same thing from the same places under
ANOTHER light - THE BENCHMARK: each colouring gets the new light fitted on some of them and the rest are scored. The
tool FAILS (exit 2, nothing delivered) when the colour without its light does no better there; without --relight it
delivers the colour and says it is NOT PROVEN.
-> <name>.albedo.png (the colour without its light), <name>.delit.glb (the scan wearing it) and <name>.delight.json.
"""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
MITSUBA = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "envs", "mitsuba", "Scripts", "python.exe")
FILM_W = 320          # the fits render at this width (the photos resampled to it)
HOLD_EVERY = 4        # every fourth photo is held out


def blender():
    sys.path.insert(0, HERE)
    import cad_check  # noqa: PLC0415

    return cad_check.blender()


def glb_texture(glb, out_png):
    """the base-colour picture packed in a GLB -> written to out_png"""
    data = open(glb, "rb").read()
    n = struct.unpack("<I", data[12:16])[0]
    j = json.loads(data[20:20 + n])
    binary = 20 + n + 8
    tex = j["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    img = j["images"][j["textures"][tex]["source"]]
    bv = j["bufferViews"][img["bufferView"]]
    start = binary + bv.get("byteOffset", 0)
    open(out_png, "wb").write(data[start:start + bv["byteLength"]])


SH = (0.282095, 0.488603, 1.092548, 0.315392, 0.546274)


def basis(n):
    """the 9 spherical-harmonic terms of a facing n (..., 3) -> (..., 9)"""
    import numpy as np  # noqa: PLC0415

    x, y, z = n[..., 0], n[..., 1], n[..., 2]
    return np.stack([np.full_like(x, SH[0]), SH[1] * y, SH[1] * z, SH[1] * x, SH[2] * x * y, SH[2] * y * z,
                     SH[3] * (3 * z * z - 1), SH[2] * x * z, SH[4] * (x * x - y * y)], -1)


def srgb_to_linear(a):
    import numpy as np  # noqa: PLC0415

    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def shading_split(texture, facing):
    """THE ASSUMPTION that picks one split out of many: the thing's own colour does not depend on the way its
    surface faces. A photographed texel is colour x light, and any split with the same product fits the photos
    alike (the first joint fit found a weak shading and left the colour 0.40 correlated with it); so the shading
    is the part of the photographed brightness the facing EXPLAINS - a least-squares fit, per channel, of the
    photographed colour on the 9 spherical-harmonic terms of the facing, over the texels a face covers.
    -> (27 coefficients, scaled so the shading's mean is 1 - the solve's starting point; facts)"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    photo = srgb_to_linear(np.asarray(Image.open(texture).convert("RGB"), float) / 255)
    fac = np.asarray(Image.open(facing).convert("RGB"), float) / 255
    cov = fac.sum(-1) > 0.02
    b = basis(fac * 2 - 1)[cov][::5]
    out = []
    for c in range(3):
        w = np.linalg.lstsq(b, photo[..., c][cov][::5], rcond=None)[0]
        e = b @ w
        out += list(w / max(float(e.mean()), 1e-6))
    return [round(float(v), 6) for v in out], None


def shading_left(texture, albedo_png, facing, sh):
    """how much of the solved shading is still IN a colour: the correlation, over the texels a face covers, between
    the colour's brightness and the shading's -> {"photographed", "delit"} (0: none left)"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    fac = np.asarray(Image.open(facing).convert("RGB"), float) / 255
    cov = fac.sum(-1) > 0.02
    b = basis(fac * 2 - 1)[cov]
    e = sum(w * (b @ np.array(sh[c * 9:(c + 1) * 9])) for c, w in enumerate((0.2126, 0.7152, 0.0722)))

    def tie(path):
        a = srgb_to_linear(np.asarray(Image.open(path).convert("RGB"), float) / 255)[cov]
        return round(float(np.corrcoef(a @ np.array([0.2126, 0.7152, 0.0722]), e)[0, 1]), 3)
    return {"photographed": tie(texture), "delit": tie(albedo_png)}


def delight(name, work=None, out_dir=None, steps=300, relight=None):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    if not os.path.isfile(MITSUBA):
        raise RuntimeError(f"the Mitsuba environment is not at {MITSUBA} - see VETLOG.md (2026-10-06)")
    work = os.path.abspath(work or os.path.join(REPO, "build", "scan", name))
    out_dir = os.path.abspath(out_dir or os.path.join(REPO, "assets", "models"))
    scan_json = os.path.join(out_dir, f"{name}.scan.json")
    glb = os.path.join(out_dir, f"{name}.scan.glb")
    spec_path = os.path.join(work, "outline_views.json")
    for p in (scan_json, glb, spec_path):
        if not os.path.isfile(p):
            raise RuntimeError(f"delight: no {p} - run kit/tools/photoscan.py for {name} first")
    if json.load(open(scan_json, encoding="utf-8")).get("weak"):
        raise RuntimeError(f"delight: the scan of {name} failed its capture checks - nothing to take the light out of")
    spec = json.load(open(spec_path, encoding="utf-8"))
    d = os.path.join(work, "delight")
    os.makedirs(d, exist_ok=True)
    mesh = os.path.join(d, "scan_cameras_frame.obj")
    texture = os.path.join(d, "photographed.png")
    glb_texture(glb, texture)
    tex_size = Image.open(texture).size[0]
    r = subprocess.run([blender(), "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(REPO, "kit", "blender", "delight_prep.py"), "--", glb, spec_path, mesh,
                        str(tex_size)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("delight: the scan could not be put in its cameras' frame: " + (r.stderr or r.stdout)[-400:])
    facing = os.path.splitext(mesh)[0] + "_facing.png"
    views, k = [], 0
    for v in spec["views"]:
        w0, h0 = v["width"], v["height"]
        film_h = int(round(FILM_W * h0 / w0))
        if k == 0:
            film = (FILM_W, film_h)
        if (FILM_W, film_h) != film:
            raise RuntimeError("delight: the photos are not all one size (photoscan refuses that)")
        m = np.load(v["mask"])
        mp = os.path.join(d, f"mask_{k:03d}.png")
        Image.fromarray((m > 0.5).astype(np.uint8) * 255).resize(film, Image.NEAREST).save(mp)
        pp = os.path.join(d, f"photo_{k:03d}.png")
        src = os.path.join(work, "dense", "images", v["image"])
        Image.open(src).convert("RGB").resize(film, Image.LANCZOS).save(pp)
        import math  # noqa: PLC0415

        views.append({"R": v["R"], "t": v["t"], "fov": math.degrees(2 * math.atan(w0 / (2 * v["fx"]))),
                      "photo": pp, "mask": mp, "held_out": k % HOLD_EVERY == HOLD_EVERY - 1})
        k += 1
    sh_init, _ = shading_split(texture, facing)
    # the colour without its light (the split), written BEFORE the checks: the solve only checks and scores it
    photo = srgb_to_linear(np.asarray(Image.open(texture).convert("RGB"), float) / 255)
    fac = np.asarray(Image.open(facing).convert("RGB"), float) / 255
    cov = fac.sum(-1) > 0.02
    b = basis(fac * 2 - 1)
    e = np.stack([b @ np.array(sh_init[c * 9:(c + 1) * 9]) for c in range(3)], -1)
    lin = np.where(cov[..., None], photo / np.maximum(e, 0.05), photo)
    lin = np.clip(lin * (photo[cov].mean() / max(float(lin[cov].mean()), 1e-9)), 0.002, 1.0)
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    delit_png = os.path.join(d, "delit.png")
    Image.fromarray((np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8)).save(delit_png)
    relight_views = relight_photos(relight, work, d, spec, film) if relight else None
    job = os.path.join(d, "job.json")
    json.dump({"out": d, "film": list(film), "mesh": mesh, "texture": texture, "delit": delit_png, "views": views,
               "relight": relight_views, "steps": int(steps)}, open(job, "w", encoding="utf-8"))
    t = time.time()
    r = subprocess.run([MITSUBA, "-I", os.path.join(HERE, "delight_mitsuba.py"), job], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    secs = round(time.time() - t, 1)
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DELIGHT ")), None)
    if line is None:
        raise RuntimeError("delight: the Mitsuba solve failed: " + (r.stderr or r.stdout)[-600:])
    rep = json.loads(line[8:])
    rep["seconds"] = secs
    if r.returncode == 3:
        raise RuntimeError(f"delight: the scan does not line up with its cameras ({rep['camera_check']}: the outline "
                           f"needs {0.85}, the photographed colour against the photo {0.5}) - the camera frame is "
                           "wrong (a mirror, a turn); nothing was scored")
    rep["shading_tie"] = shading_left(texture, delit_png, facing, sh_init)
    rel = rep["fits"].get("relight")
    if rel:
        p_, d_ = rel["photographed"], rel["delit"]
        rep["relight_gain"] = round(1.0 - d_ / p_, 4) if p_ > 0 else 0.0
        rep["proven"] = rep["relight_gain"] > 0
    else:
        rep["relight_gain"], rep["proven"] = None, None
    if rep["proven"] is False:   # (shown worse under another light: nothing is delivered beside the scan)
        rep["albedo"] = rep["glb"] = None
    else:
        albedo_png = os.path.join(out_dir, f"{name}.albedo.png")
        shutil.copyfile(delit_png, albedo_png)
        delit = os.path.join(out_dir, f"{name}.delit.glb")
        r = subprocess.run([blender(), "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(REPO, "kit", "blender", "delight_swap.py"), "--", glb, albedo_png, delit],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError("delight: the scan could not be given its new colour: " + (r.stderr or r.stdout)[-400:])
        rep["albedo"] = os.path.relpath(albedo_png, REPO).replace("\\", "/")
        rep["glb"] = os.path.relpath(delit, REPO).replace("\\", "/")
    json.dump(rep, open(os.path.join(out_dir, f"{name}.delight.json"), "w", encoding="utf-8"), indent=1)
    return rep


def relight_photos(folder, work, d, spec, film):
    """photos of the same thing from the SAME places (the same names as the scan's photos) under another light ->
    their views for the benchmark: each turned upright, undistorted with the scan's own solved cameras (COLMAP crops
    as it undistorts: the same crop as the scan's photos), resized to the film"""
    from PIL import Image  # noqa: PLC0415

    import photoscan  # noqa: PLC0415

    prep = os.path.join(work, "relight_photos")
    if os.path.isdir(prep):
        shutil.rmtree(prep)
    names = photoscan.prepare(folder, prep)
    have = {v["image"] for v in spec["views"]}
    missing = sorted(have - set(names))
    if missing:
        raise ValueError(f"delight: --relight needs a photo of each place the scan was photographed from, by the same "
                         f"name; missing {', '.join(missing[:4])}{' ...' if len(missing) > 4 else ''}")
    models = sorted(m for m in os.listdir(os.path.join(work, "sparse")) if m.isdigit())
    best = max(models, key=lambda m: os.path.getsize(os.path.join(work, "sparse", m, "images.bin")))
    out = os.path.join(work, "relight_dense")
    if os.path.isdir(out):
        shutil.rmtree(out)
    size = Image.open(os.path.join(work, "dense", "images", spec["views"][0]["image"])).size
    photoscan.run(["image_undistorter", "--image_path", prep, "--input_path", os.path.join(work, "sparse", best),
                   "--output_path", out, "--max_image_size", str(max(size))], os.path.join(work, "colmap.log"))
    views = []
    for k, v in enumerate(spec["views"]):
        src = os.path.join(out, "images", v["image"])
        im = Image.open(src).convert("RGB")
        if im.size != size:
            raise ValueError(f"delight: {v['image']} under the other light undistorts to {im.size}, not {size}")
        pp = os.path.join(d, f"relight_{k:03d}.png")
        im.resize(film, Image.LANCZOS).save(pp)
        views.append({"photo": pp})
    return views


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name")
    ap.add_argument("--work", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--relight", default=None, help="photos of the same thing from the same places under ANOTHER "
                    "light (same names): the benchmark that shows the light is out")
    a = ap.parse_args()
    try:
        rep = delight(a.name, a.work, a.out, a.steps, a.relight)
    except (RuntimeError, ValueError) as e:
        print(f"summary: delight failed - {e}")
        print("next_action: fix what it names and run it again")
        return 1
    print(json.dumps(rep, indent=1))
    same = rep["fits"]["same_light"]
    tie = rep["shading_tie"]
    head = (f"summary: delight {a.name}: camera check {rep['camera_check']['median']:.2f}, colour check "
            f"{rep['camera_check']['colour_median']:.2f}; the colour's tie to the split's shading "
            f"{tie['photographed']:.2f} as photographed, {tie['delit']:.2f} without its light; under the SAME light "
            f"the photographed colour reproduces unseen photos at {same['photographed_even']:.4f}, the colour without "
            f"its light relit at {same['delit_relit']:.4f} (the photographed colour IS that light: it wins there)")
    if rep["proven"] is None:
        print(head + " - NOT PROVEN: only photos under another light can show the light is out (--relight)")
        print(f"next_action: look at {rep['albedo']} beside the photographed texture before building with "
              f"{rep['glb']}; to prove it, photograph the thing again from the same places under another light")
        return 0
    rel = rep["fits"]["relight"]
    print(head + f"; UNDER ANOTHER LIGHT (the benchmark, {rel['held_out_views']} unseen photos) the colour without its "
          f"light {'does BETTER' if rep['proven'] else 'does WORSE'}: {rel['delit']:.4f} vs {rel['photographed']:.4f} "
          f"({abs(rep['relight_gain']) * 100:.0f}% {'less' if rep['proven'] else 'more'} error)")
    print(f"next_action: {'build with ' + rep['glb'] if rep['proven'] else 'keep the photographed colour: taking the light out did not earn its place on this thing'}")
    return 0 if rep["proven"] else 2


if __name__ == "__main__":
    sys.exit(main())
