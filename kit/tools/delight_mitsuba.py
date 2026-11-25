"""delight_mitsuba.py - the inverse-rendering checks and benchmark (his D-R03), run by kit/tools/delight.py in the
vetted Mitsuba environment (~/.cache/roblox-kit/envs/mitsuba: mitsuba 3.9.1 + drjit, NO numpy - every array here
is a Dr.Jit one).

    <mitsuba python> -I delight_mitsuba.py <job.json>

The scan (an OBJ in the cameras' frame), its colour as photographed, the split colour without its light
(kit/tools/delight.py), the photos and the object's cut-out in each, the cameras. Every score is over the pixels
BOTH the photo's cut-out and the scan cover (the background, where a light map can learn each view, never counts:
the review, 2026-11-16, found a light fitted to the visible background memorising the training views).
  CAMERA CHECK   the scan's outline through each camera against the cut-out; and its photographed colour, shown
                 under an even light, against the photo (a mirrored frame keeps the outline of a round thing but
                 not its pattern) -> exit 3 when either fails
  SAME LIGHT     reported, not judged: how well each colouring reproduces held-out photos under the light the
                 scan was photographed in (the photographed colour wins here by definition: it IS that light)
  RELIGHTING     the benchmark, when photos of the same thing from the same places under ANOTHER light are given:
                 for each colouring the new light is fitted on some of them and the rest are scored. A colour with
                 its light truly out matches the new light; one with the old light painted in does not.
-> <out>/report.json"""

import json
import math
import sys
import time

import drjit as dr
import mitsuba as mi

mi.set_variant("cuda_ad_rgb")
JOB = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = JOB["out"]
W, H = JOB["film"]
ENV = (16, 32)                      # the light: an environment map this coarse (a key, a fill, a sky)
STEPS, LR, SPP, EVAL_SPP = JOB.get("steps", 300), JOB.get("lr", 0.03), 8, 32
CAMERA_BAR, COLOUR_BAR = 0.85, 0.5


def num(x):
    """a plain number out of a Dr.Jit result (a 0-dimensional tensor, a 1-long array, a float)"""
    if hasattr(x, "array"):
        x = x.array
    try:
        return float(x[0])
    except (TypeError, IndexError):
        return float(x)


def to_world(view):
    """COLMAP's R (world -> camera, x right, y DOWN, z ahead), t -> Mitsuba's camera (x LEFT, y up, z ahead)"""
    r, t = view["R"], view["t"]
    c = [-sum(r[k][i] * t[k] for k in range(3)) for i in range(3)]
    col = [[-r[0][i] for i in range(3)], [-r[1][i] for i in range(3)], [r[2][i] for i in range(3)]]
    return mi.ScalarTransform4f([[col[0][0], col[1][0], col[2][0], c[0]], [col[0][1], col[1][1], col[2][1], c[1]],
                                 [col[0][2], col[1][2], col[2][2], c[2]], [0, 0, 0, 1]])


def picture(path, fmt, linear=True):
    b = mi.Bitmap(path).convert(fmt, mi.Struct.Type.Float32, srgb_gamma=not linear)
    if list(b.size()) != [W, H]:
        b = b.resample([W, H])
    return mi.TensorXf(b)


def texture_tensor(path):
    """a colour texture as linear floats, the way Mitsuba itself reads it (a Bitmap turned into a tensor here
    came out empty at 2048)"""
    t = mi.traverse(mi.load_dict({"type": "bitmap", "filename": path, "raw": False, "format": "variant"}))["data"]
    return mi.TensorXf(t)


env0 = mi.Bitmap(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.Float32, [ENV[1], ENV[0]])
scene = mi.load_dict({
    "type": "scene",
    "integrator": {"type": "prb", "max_depth": 3},
    "sensor": {"type": "perspective", "fov_axis": "x", "fov": 40.0, "to_world": to_world(JOB["views"][0]),
               "film": {"type": "hdrfilm", "width": W, "height": H, "pixel_format": "rgba",
                        "rfilter": {"type": "box"}}},
    "shape": {"type": "obj", "filename": JOB["mesh"], "face_normals": False,
              "bsdf": {"type": "diffuse", "reflectance": {"type": "bitmap", "filename": JOB["texture"],
                                                          "raw": False, "format": "variant"}}},
    "emitter": {"type": "envmap", "bitmap": env0},
})
params = mi.traverse(scene)
KA, KE = "shape.bsdf.reflectance.data", "emitter.data"
COLOURS = {"photographed": texture_tensor(JOB["texture"]), "delit": texture_tensor(JOB["delit"])}
for k, t in COLOURS.items():
    assert len(t.shape) == 3 and t.shape[2] == 3, f"the {k} texture loaded as {t.shape}"
shape_e = params[KE].shape
EVEN = mi.TensorXf(dr.full(mi.Float, 1.0, math.prod(shape_e)), shape=shape_e)


def show(view, colour=None, light=None):
    params["sensor.to_world"] = to_world(view)
    params["sensor.x_fov"] = view["fov"]
    if colour is not None:
        params[KA] = colour
    if light is not None:
        params[KE] = light
    params.update()


def spread3(m):
    return mi.TensorXf(dr.gather(mi.Float, m.array, dr.arange(mi.UInt32, H * W * 3) // 3), shape=(H, W, 3))


def l1(img, ref, m3):
    """mean absolute error over the scored pixels (m3: the cover mask over the three channels), linear RGB"""
    return dr.sum(dr.abs(img[:, :, :3] - ref) * m3) / dr.maximum(dr.sum(m3), 1.0)


def lum(t):
    return t[:, :, 0] * 0.2126 + t[:, :, 1] * 0.7152 + t[:, :, 2] * 0.0722


# THE COVER: each view's pixels the photo's cut-out AND the scan both cover (the scan's outline from the camera)
show(JOB["views"][0], COLOURS["photographed"], EVEN)
views, ious, ties = [], [], []
for v in JOB["views"]:
    show(v)
    with dr.suspend_grad():
        img = mi.render(scene, spp=4)
    inside = dr.select(img[:, :, 3].array > 0.5, 1.0, 0.0)
    cut = picture(v["mask"], mi.Bitmap.PixelFormat.Y)
    cutm = dr.select(cut.array > 0.5, 1.0, 0.0)
    ious.append(num(dr.sum(inside * cutm)) / max(num(dr.sum(dr.maximum(inside, cutm))), 1.0))
    cover = inside * cutm
    photo = picture(v["photo"], mi.Bitmap.PixelFormat.RGB)
    # the colour check: the photographed colour under an even light against the photo, pixel by pixel
    a, b = lum(img).array, lum(photo).array
    n = dr.maximum(dr.sum(cover), 1.0)
    ma, mb = dr.sum(a * cover) / n, dr.sum(b * cover) / n
    cov = dr.sum((a - ma) * (b - mb) * cover)
    var = dr.sqrt(dr.sum(dr.square(a - ma) * cover) * dr.sum(dr.square(b - mb) * cover))
    ties.append(num(cov) / max(num(var), 1e-12))
    views.append({"view": v, "photo": photo, "m3": spread3(mi.TensorXf(cover, shape=(H, W))),
                  "held": v["held_out"]})
ious_s, ties_s = sorted(ious), sorted(ties)
report = {"camera_check": {"median": round(ious_s[len(ious_s) // 2], 4), "worst": round(ious_s[0], 4),
                           "colour_median": round(ties_s[len(ties_s) // 2], 4)}, "fits": {}}
if report["camera_check"]["median"] < CAMERA_BAR or report["camera_check"]["colour_median"] < COLOUR_BAR:
    json.dump(report, open(OUT + "/report.json", "w"))
    print("DELIGHT " + json.dumps(report))
    sys.exit(3)


def fit_light(colour, train):
    """the light that shows `colour` as the training photos show it -> the light tensor"""
    params[KA] = colour
    params[KE] = mi.TensorXf(EVEN)
    params.update()
    opt = mi.ad.Adam(lr=LR)
    opt[KE] = params[KE]
    for i in range(STEPS):
        x = train[i % len(train)]
        params["sensor.to_world"] = to_world(x["view"])
        params["sensor.x_fov"] = x["view"]["fov"]
        params[KE] = opt[KE]
        params.update()
        img = mi.render(scene, params, spp=SPP, seed=i)
        dr.backward(l1(img, x["photo"], x["m3"]))
        opt.step()
        opt[KE] = dr.maximum(opt[KE], 0.0)
    return mi.TensorXf(opt[KE])


def score(colour, light, held):
    errs = []
    for x in held:
        show(x["view"], colour, light)
        with dr.suspend_grad():
            img = mi.render(scene, params, spp=EVAL_SPP, seed=7)
        errs.append(num(l1(img, x["photo"], x["m3"])))
    return round(sum(errs) / max(len(errs), 1), 5)


def even_light(colour, train):
    """the photographed colour needs no light but an even one of the right strength: one number, from training"""
    tot_r = tot_p = 0.0
    for x in train:
        show(x["view"], colour, EVEN)
        with dr.suspend_grad():
            img = mi.render(scene, params, spp=SPP, seed=3)
        tot_r += num(dr.sum(img[:, :, :3] * x["m3"]))
        tot_p += num(dr.sum(x["photo"] * x["m3"]))
    return mi.TensorXf(EVEN * (tot_p / max(tot_r, 1e-9)))


train = [x for x in views if not x["held"]]
held = [x for x in views if x["held"]]
t0 = time.time()
report["fits"]["same_light"] = {
    "photographed_even": score(COLOURS["photographed"], even_light(COLOURS["photographed"], train), held),
    "delit_relit": score(COLOURS["delit"], fit_light(COLOURS["delit"], train), held),
    "held_out_views": len(held), "seconds": round(time.time() - t0, 1)}

if JOB.get("relight"):
    # THE BENCHMARK: the same places, ANOTHER light. Each colouring gets the new light fitted on the training
    # photos of it, the same steps; scored on the rest.
    rv = [{"view": base["view"], "photo": picture(v["photo"], mi.Bitmap.PixelFormat.RGB), "m3": base["m3"],
           "held": base["held"]} for v, base in zip(JOB["relight"], views)]
    rtrain, rheld = [x for x in rv if not x["held"]], [x for x in rv if x["held"]]
    t0 = time.time()
    res = {name: score(COLOURS[name], fit_light(COLOURS[name], rtrain), rheld) for name in ("photographed", "delit")}
    res["held_out_views"], res["seconds"] = len(rheld), round(time.time() - t0, 1)
    report["fits"]["relight"] = res

json.dump(report, open(OUT + "/report.json", "w"))
print("DELIGHT " + json.dumps(report))
