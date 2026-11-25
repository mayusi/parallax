"""camfit.py — CAMERA FITTING (Blender, headless): find the camera a photo was taken from, given the 3D model.

    blender -b --factory-startup --python-exit-code 2 -P kit/blender/camfit.py -- <model.blend> <mask.png>
        [--out build/camfit/<name>] [--starts 8] [--evals 400] [--fov auto|<deg>] [--ignore bipod,monopod]
        [--exclude "x0,y0,x1,y1;..."]  (photo pixels that do not count: a part the photo shows differently)
        [--start yaw,pitch,roll]        (a known rough view: searched from there instead of all round)
        [--points "Muzzle=x,y;Grip=x,y"]  (the asset's ANCHORS at photo pixels: 2-4 marks pin a thin object's pose)
    (lune run kit fit camera <photo> --asset <name> cuts the photo out first and runs this)

The photo's object mask (white = the object, from kit vision's cutout) is matched by the model's silhouette rendered
from a camera with 6 unknowns: yaw and pitch around the model, roll, the model's size in the frame and its position
(x, y) in the frame, plus the lens (field of view) unless --fov fixes it. Silhouettes render with Workbench at 192 px
(milliseconds each), CMA-ES (kit/blender/cmaes.py) maximises the IoU from several yaw starts (a silhouette alone
cannot tell a left view from a right one, or front from back — every start is tried), and the best is polished at
384 px. -> <out>/camera.json {yaw, pitch, roll, fov, iou, ...} + <out>/overlay.png (photo mask vs the fitted model).
"""

import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cmaes import CMAES  # noqa: E402

PARAMS = ("yaw", "pitch", "roll", "scale", "x", "y", "fov")


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or not argv[i - 1].startswith("--"))]
    opt = {"out": None, "starts": "8", "evals": "400", "fov": "auto", "seed": "0", "ignore": "", "exclude": "",
           "roll": "25", "ends": "auto", "start": "", "points": "", "manifest": ""}
    for i, a in enumerate(argv):
        if a.startswith("--") and i + 1 < len(argv) and a[2:] in opt:
            opt[a[2:]] = argv[i + 1]
    return pos, opt


def _care(path, size, boxes):
    """True where the photo counts: everything but the --exclude boxes (photo pixels), at the mask's size"""
    img = bpy.data.images.load(path)
    w, h = img.size
    bpy.data.images.remove(img)
    hh = max(8, int(round(size * h / w)))
    care = np.ones((hh, size), dtype=bool)
    for x0, y0, x1, y1 in boxes:
        care[int(y0 * hh / h):int(np.ceil(y1 * hh / h)), int(x0 * size / w):int(np.ceil(x1 * size / w))] = False
    return care


def _load_mask(path, size):
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(h, w, 4)[::-1]
    m = (px[..., 3] > 0.5) & (px[..., :3].mean(-1) > 0.5) if (px[..., 3] < 0.99).any() else px[..., :3].mean(-1) > 0.5
    # nearest resample to `size` wide, the photo's own aspect
    hh = max(8, int(round(size * h / w)))
    ys = (np.arange(hh) * h / hh).astype(int)
    xs = (np.arange(size) * w / size).astype(int)
    return m[ys][:, xs]


class Silhouette:
    """the model, a camera aimed at its centre, a Workbench silhouette render -> a boolean mask"""

    def __init__(self, blend, ignore=()):
        bpy.ops.wm.open_mainfile(filepath=blend)
        sc = bpy.context.scene
        for o in sc.objects:  # groups the photo shows differently (a bipod deployed / folded): left out of the match
            if o.type == "MESH" and any(o.name == g or o.name.endswith("_" + g) for g in ignore):
                o.hide_render = True
        self.objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
        for o in sc.objects:
            if o.type in ("LIGHT", "CAMERA"):
                o.hide_render = True
        corners = [o.matrix_world @ Vector(c) for o in self.objs for c in o.bound_box]
        lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
        hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
        self.center, self.radius = (lo + hi) / 2, (hi - lo).length / 2
        # the model's two ENDS along its longest axis (a rifle's muzzle and butt): for a long thin object the
        # silhouette alone fits mirrored / rolled poses as well — its ends pin the pose (see fit)
        vs = np.array([tuple(o.matrix_world @ v.co) for o in self.objs for v in o.data.vertices], dtype=np.float64)
        mu = vs.mean(0)
        evals, evecs = np.linalg.eigh(np.cov((vs - mu).T))
        axis = evecs[:, -1]
        t = (vs - mu) @ axis
        span = t.max() - t.min()
        self.elongation = float(np.sqrt(evals[-1] / max(evals[-2], 1e-12)))
        self.ends = [Vector(vs[t >= t.max() - 0.01 * span].mean(0)), Vector(vs[t <= t.min() + 0.01 * span].mean(0))]
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.render.film_transparent = True
        sh = sc.display.shading
        sh.light, sh.color_type, sh.single_color = "FLAT", "SINGLE", (1, 1, 1)
        sh.show_cavity = sh.show_object_outline = False
        sc.view_settings.view_transform = "Standard"
        sc.render.image_settings.file_format = "PNG"
        cam = bpy.data.objects.new("FitCam", bpy.data.cameras.new("FitCam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
        self.cam, self.sc = cam, sc
        self.path = os.path.join(bpy.app.tempdir or os.environ.get("TEMP", "."), "camfit_sil.png")

    care = None  # (set by main: photo regions left out of the match — a deployed bipod the model shows folded)

    def place(self, p, w, h):
        """aim the camera: it orbits the model's centre at yaw / pitch (degrees; yaw 0 = the camera on the model's +Y
        (Roblox -Z: its FRONT) looking back along its length, yaw +-90 = the sides, +-45 / +-135 = three-quarter views;
        pitch > 0 = from above), rolls about its view axis, and frames the model so its bounding sphere spans `scale`
        of the picture's width, shifted by (x, y) picture widths"""
        sc, cam = self.sc, self.cam
        sc.render.resolution_x, sc.render.resolution_y = w, h
        fov = math.radians(max(5.0, min(100.0, p["fov"])))
        cam.data.type = "PERSP"
        cam.data.sensor_fit = "HORIZONTAL"
        cam.data.angle = fov
        # distance at which the bounding sphere spans `scale` of the width
        dist = self.radius / max(1e-3, math.tan(fov / 2) * max(0.05, p["scale"]))
        yaw, pitch = math.radians(p["yaw"]), math.radians(p["pitch"])
        direction = Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), -math.sin(pitch)))
        cam.location = self.center - direction * dist
        rot = direction.to_track_quat("-Z", "Y").to_matrix().to_4x4()  # (local -Z looks, local +Y is up: a level camera)
        cam.matrix_world = Matrix.Translation(cam.location) @ rot @ Matrix.Rotation(math.radians(p["roll"]), 4, "Z")
        cam.data.shift_x, cam.data.shift_y = -p["x"], -p["y"] * (h / w) if w >= h else -p["y"]
        cam.data.clip_start, cam.data.clip_end = max(1e-3, dist - 2 * self.radius), dist + 2 * self.radius

    def project(self, pts, p, w, h):
        """world points -> pixel positions (x right, y down) in a (w, h) picture from camera p"""
        from bpy_extras.object_utils import world_to_camera_view  # noqa: PLC0415

        self.place(p, w, h)
        bpy.context.view_layer.update()
        out = []
        for pt in pts:
            co = world_to_camera_view(self.sc, self.cam, pt)
            out.append((co.x * w, (1 - co.y) * h))
        return np.array(out)

    def render(self, p, w, h):
        """p = dict of PARAMS -> boolean mask (h, w) of the model's silhouette from that camera (see place)"""
        sc = self.sc
        self.place(p, w, h)
        sc.render.filepath = self.path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(self.path)
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        m = px.reshape(h, w, 4)[::-1][..., 3] > 0.5
        if self.care is not None and w in self.care:
            m &= self.care[w]
        return m


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def _blur(m, r):
    """box blur of a mask (integral image): a pixel's share of solid neighbours within r"""
    a = m.astype(np.float32)
    p = np.pad(a, r + 1, mode="constant").cumsum(0).cumsum(1)
    k = 2 * r + 1
    return (p[k:, k:] - p[:-k, k:] - p[k:, :-k] + p[:-k, :-k])[: a.shape[0], : a.shape[1]] / (k * k)


def soft_iou(a, b_soft, r):
    """IoU of blurred masks (sum of min / sum of max): a pixel or two off on a thin barrel is a near miss, not a total
    one — the optimiser can feel its way to the alignment; the reported score is the plain IoU"""
    a_soft = _blur(a, r)
    den = np.maximum(a_soft, b_soft).sum()
    return float(np.minimum(a_soft, b_soft).sum() / den) if den else 0.0


STEP = np.array([25.0, 15.0, 10.0, 0.15, 0.08, 0.08, 10.0])  # one search unit per parameter (deg, deg, deg, ...)
# roll within +-25 deg: cameras are held near level, product shots are often tilted for effect (a real M107 shot
# fitted at ~15-20 deg); a free roll lets a thin object's silhouette fit a mirrored pose. --roll <deg> changes it
LO = np.array([-180.0, -80.0, -25.0, 0.1, -0.6, -0.6, 10.0])
HI = np.array([180.0, 80.0, 25.0, 1.6, 0.6, 0.6, 90.0])


def _search(loss, x0, evals, seed, sigma=1.0, popsize=10):
    """CMA-ES in normalised units (each parameter divided by its STEP): -> (best params vector, best loss)"""
    es = CMAES(np.zeros(len(x0)), sigma, lo=(LO - x0) / STEP, hi=(HI - x0) / STEP, seed=seed, max_evals=evals,
               popsize=popsize)
    while not es.done():
        zs = es.ask()
        es.tell(zs, [loss(x0 + np.asarray(z) * STEP) for z in zs])
    return x0 + es.best_x * STEP, es.best_f


def photo_ends(mask):
    """the photo object's two ends along its longest axis (pixel x, y): where a rifle's muzzle and butt are"""
    ys, xs = np.nonzero(mask)
    pts = np.c_[xs, ys].astype(np.float64)
    mu = pts.mean(0)
    _w, v = np.linalg.eigh(np.cov((pts - mu).T))
    t = (pts - mu) @ v[:, -1]
    span = t.max() - t.min()
    return np.array([pts[t >= t.max() - 0.01 * span].mean(0), pts[t <= t.min() + 0.01 * span].mean(0)])


def fit(sil, target_lo, target_hi, starts, evals, fov_fixed, seed, use_ends=False, start=None, marks=None,
        photo_w=None):
    """multi-start CMA-ES on the low-res target, the best polished on the high-res one -> (params, soft iou there)"""
    h_lo, w_lo = target_lo.shape
    h_hi, w_hi = target_hi.shape
    # the target's own size in the frame starts the scale; its centre starts (x, y)
    ys, xs = np.nonzero(target_lo)
    span = max((xs.max() - xs.min()) / w_lo, (ys.max() - ys.min()) / w_lo) if len(xs) else 0.6
    cx = (xs.mean() / w_lo - 0.5) if len(xs) else 0.0
    cy = ((0.5 - ys.mean() / h_lo) * (h_lo / w_lo)) if len(xs) else 0.0

    def to_params(v):
        p = dict(zip(PARAMS, (float(t) for t in v)))
        if fov_fixed is not None:
            p["fov"] = fov_fixed
        return p

    soft_lo, soft_hi = _blur(target_lo, 1), _blur(target_hi, 3)
    ends_hi = photo_ends(target_hi) if use_ends else None

    def ends_error(v, w, h):
        """how far the model's two ends land from the photo's (either way round), in picture widths"""
        if ends_hi is None:
            return 0.0
        pe = ends_hi * (w / w_hi)
        pm = sil.project(sil.ends, to_params(v), w, h)
        return float(min(np.linalg.norm(pm - pe, axis=1).mean(), np.linalg.norm(pm[::-1] - pe, axis=1).mean())) / w

    def marks_error(v, w, h):
        """how far the model's named anchors land from the points marked on the photo (picture widths) — two to
        four marks pin a pose the silhouette alone cannot (a thin rifle's mirrored / rolled look-alikes)"""
        if not marks:
            return 0.0
        world = [m[0] for m in marks]
        want = np.array([(m[1][0] * w / photo_w, m[1][1] * w / photo_w) for m in marks])
        got = sil.project(world, to_params(v), w, h)
        return 2.0 * float(np.linalg.norm(got - want, axis=1).mean()) / w

    def loss_lo(v):
        return (1.0 - soft_iou(sil.render(to_params(v), w_lo, h_lo), soft_lo, 1) + ends_error(v, w_lo, h_lo)
                + marks_error(v, w_lo, h_lo))

    def loss_hi(v):
        return (1.0 - soft_iou(sil.render(to_params(v), w_hi, h_hi), soft_hi, 3) + ends_error(v, w_hi, h_hi)
                + marks_error(v, w_hi, h_hi))

    rng = np.random.default_rng(seed)
    # successive halving: every yaw start gets a short run (a silhouette cannot tell left from right on its own), the
    # two best continue, the best is polished at full resolution — the budget goes where the right basin is
    runs = []
    if start is not None:  # a known rough view (yaw, pitch, roll): searched from there only
        x0 = np.array([start[0], start[1], start[2], span, cx, cy, fov_fixed if fov_fixed is not None else 35.0])
        v, f = _search(loss_lo, x0, max(60, evals // 2), int(rng.integers(1 << 30)), sigma=0.6)
        runs.append((f, v))
        starts = 0
    for k in range(starts):
        x0 = np.array([-180 + 360 * (k + 0.5) / starts, 15.0, 0.0, span, cx, cy,
                       fov_fixed if fov_fixed is not None else 35.0])
        v, f = _search(loss_lo, x0, max(40, evals // (4 * starts)), int(rng.integers(1 << 30)))
        runs.append((f, v))
    runs.sort(key=lambda r: r[0])
    best_f, best_v = 2.0, None
    for f0, v0 in runs[:2]:
        v, f = _search(loss_lo, v0, max(60, evals // 4), int(rng.integers(1 << 30)), sigma=0.5)
        if min(f, f0) < best_f:
            best_f, best_v = (f, v) if f < f0 else (f0, v0)
    v, f = _search(loss_hi, best_v, max(60, evals // 4), seed + 7, sigma=0.2, popsize=10)
    if f > loss_hi(best_v):  # (the polish only refines: never accept a worse camera)
        v = best_v
        f = loss_hi(v)
    return to_params(v), 1.0 - f


def main():
    pos, opt = _args()
    if len(pos) < 2 or not all(os.path.isfile(p) for p in pos[:2]):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "camfit: needs <model.blend> <mask.png>",
                          "next_action": "lune run kit fit camera <photo> --asset <name>"}))
        return
    blend, mask_path = os.path.abspath(pos[0]), os.path.abspath(pos[1])  # (Blender reads images by absolute path)
    LO[2], HI[2] = -abs(float(opt["roll"])), abs(float(opt["roll"]))
    out = os.path.abspath(opt["out"] or os.path.join("build", "camfit", os.path.splitext(os.path.basename(blend))[0]))
    os.makedirs(out, exist_ok=True)
    target_lo = _load_mask(mask_path, 192)
    target_hi = _load_mask(mask_path, 768)  # (thin parts — a barrel, a rail — need pixels to align on)
    ignore = [g.strip() for g in opt["ignore"].split(",") if g.strip()]
    boxes = [[float(v) for v in b.split(",")] for b in opt["exclude"].split(";") if b.strip()]
    sil = Silhouette(blend, ignore)
    if boxes:  # photo regions that do not count (both the photo's and the model's pixels there are left out)
        sil.care = {192: _care(mask_path, 192, boxes), 768: _care(mask_path, 768, boxes)}
        target_lo &= sil.care[192]
        target_hi &= sil.care[768]
    fov_fixed = None if opt["fov"] == "auto" else float(opt["fov"])
    use_ends = {"on": True, "off": False}.get(opt["ends"], sil.elongation >= 3.0)  # (auto: long thin models)
    start = [float(v) for v in opt["start"].split(",")] if opt["start"] else None
    marks = []
    if opt["points"]:  # "Muzzle=x,y;Grip=x,y": the asset's anchors (its manifest, Roblox space) at photo pixels
        mpath = opt["manifest"] or os.path.splitext(blend)[0] + ".manifest.json"
        with open(mpath, encoding="utf-8") as fh:
            anchors = json.load(fh).get("anchors") or {}
        for item in opt["points"].split(";"):
            name, xy = item.split("=")
            if name.strip() not in anchors:
                raise SystemExit(f"camfit: no anchor {name!r} in {mpath} (it has: {', '.join(anchors)})")
            ax, ay, az = anchors[name.strip()]
            marks.append((Vector((ax, -az, ay)), tuple(float(t) for t in xy.split(","))))  # Roblox -> Blender
    img = bpy.data.images.load(mask_path)
    photo_w = img.size[0]
    bpy.data.images.remove(img)
    params, _soft = fit(sil, target_lo, target_hi, int(opt["starts"]), int(opt["evals"]), fov_fixed, int(opt["seed"]),
                        use_ends and not marks, start, marks, photo_w)
    got = sil.render(params, target_hi.shape[1], target_hi.shape[0])
    score = iou(got, target_hi)  # the PLAIN overlap at full resolution: what the report and the criteria read
    # overlay: green = both, red = photo only, blue = model only
    over = np.zeros(target_hi.shape + (4,), dtype=np.float32)
    over[..., 3] = 1.0
    over[target_hi & got] = (0.2, 0.8, 0.3, 1.0)
    over[target_hi & ~got] = (0.9, 0.2, 0.2, 1.0)
    over[~target_hi & got] = (0.2, 0.3, 0.9, 1.0)
    img = bpy.data.images.new("camfit_overlay", target_hi.shape[1], target_hi.shape[0], alpha=True)
    img.pixels.foreach_set(over[::-1].ravel())
    img.filepath_raw = os.path.join(out, "overlay.png")
    img.file_format = "PNG"
    img.save()
    result = {**{k: round(v, 3) for k, v in params.items()}, "iou": round(score, 4), "model": blend,
              "mask": mask_path, "ignored": ignore, "excluded": boxes, "ends_used": use_ends,
              "elongation": round(sil.elongation, 2), "overlay": os.path.join(out, "overlay.png")}
    with open(os.path.join(out, "camera.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"camfit: yaw {params['yaw']:.1f} pitch {params['pitch']:.1f} roll {params['roll']:.1f} "
                                 f"fov {params['fov']:.1f} deg — silhouette IoU {score:.3f}",
                      "next_action": f"look at {result['overlay']} (green = both, red = photo only, blue = model only)",
                      "camera": result}))


if __name__ == "__main__":
    main()
