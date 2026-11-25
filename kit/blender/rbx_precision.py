"""rbx_precision.py — turn "does it look right?" into numbers a model can act on.

Models misjudge small details in pictures. These tools replace judging with measuring:
  expectations   a.expect("Guard", touches="Blade", above="Grip", size={"x": (1.4, 1.8)}) -> exact pass/fail + distance
  inspect        --inspect Guard -> close-up render of one part, everything else ghosted
  labels         part names projected onto the sheet's views (drawn by kit/blender/labels.py)
  reference      Asset(reference={"side": "refs/blaster_side.png"}) -> silhouette match score + diff image
Everything is in ROBLOX space (studs, Y up, -Z front) in its messages.
"""

import math
import os

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

import rbx_critic
import rbx_gaps
from rbx_colour import colour_off, colour_words, srgb_to_lab

RELATIONS = {
    # name: (axis index in Roblox space, sign) — "A above B" = A's lowest point >= B's highest point
    "above": (1, 1),
    "below": (1, -1),
    "right_of": (0, 1),
    "left_of": (0, -1),
    "in_front_of": (2, -1),  # front = -Z
    "behind": (2, 1),
}
AXES = "xyz"


def _rbx_box(p):
    """_Part bbox in Roblox space: (lo, hi) as [x, y, z]; Blender (x, y, z) -> Roblox (x, z, -y)."""
    lo = [p.lo.x, p.lo.z, -p.hi.y]
    hi = [p.hi.x, p.hi.z, -p.lo.y]
    return lo, hi


def _distance(a, b):
    """surface distance in studs (0 when touching/overlapping)."""
    if a.bvh is None or b.bvh is None:
        return float("inf")
    if a.bvh.overlap(b.bvh):
        return 0.0
    best = float("inf")
    for x, y in ((a, b), (b, a)):
        for v in x.sample(400):
            hit = y.bvh.find_nearest(v)
            if hit[0] is not None:
                best = min(best, hit[3])
    return best


def check_expectations(parts, expects, tol):
    """parts: [(obj, group)] before join; expects: [(name, {relation: value})]. -> checks (rbx_critic format)."""
    by = {}
    for o, g in parts:
        if len(o.data.vertices):
            by.setdefault(o.name, rbx_critic._Part(o, g))
    checks = []

    def fail(name, msg, fix):
        checks.append(rbx_critic._check(f"expect:{name}", False, msg, "as stated", fix))

    for name, rules in expects:
        if name not in by:
            fail(name, "no such part", f'a.expect("{name}", ...): no part with that name (names are case-sensitive)')
            continue
        a = by[name]
        alo, ahi = _rbx_box(a)
        ok_all = True
        for rel, val in rules.items():
            if rel in ("touches", "gap"):
                other, lo_g, hi_g = (val, 0.0, tol) if rel == "touches" else val
                if other not in by:
                    fail(name, f"{rel}: no part {other}", f"check the name {other}")
                    ok_all = False
                    continue
                d = _distance(a, by[other])
                if not (lo_g - 1e-6 <= d <= hi_g + 1e-6):
                    ok_all = False
                    if rel == "touches":
                        fail(name, f"{d:.3f} studs from {other}", f"move {name} {d:.3f} studs toward {other} so they touch (or overlap slightly)")
                    else:
                        fail(name, f"gap to {other} is {d:.3f} (want {lo_g}..{hi_g})", f"adjust {name}'s position by {(lo_g - d) if d < lo_g else (d - hi_g):.3f} studs")
            elif rel in RELATIONS:
                if val not in by:
                    fail(name, f"{rel}: no part {val}", f"check the name {val}")
                    ok_all = False
                    continue
                axis, sign = RELATIONS[rel]
                blo, bhi = _rbx_box(by[val])
                # A above B: A.lo >= B.hi ; A below B: A.hi <= B.lo (with tolerance)
                margin = (alo[axis] - bhi[axis]) if sign > 0 else (blo[axis] - ahi[axis])
                if margin < -tol:
                    ok_all = False
                    fail(name, f"not {rel} {val}: overlaps by {-margin:.3f} studs on {AXES[axis].upper()}", f"move {name} {-margin:.3f} studs along {'+' if sign > 0 else '-'}{AXES[axis].upper()} (Roblox space)")
            elif rel in ("size", "at"):
                for ax, (lo_v, hi_v) in val.items():
                    i = AXES.index(ax)
                    got = (ahi[i] - alo[i]) if rel == "size" else (alo[i] + ahi[i]) / 2
                    if not (lo_v - 1e-6 <= got <= hi_v + 1e-6):
                        ok_all = False
                        what = "size" if rel == "size" else "centre"
                        fail(name, f"{what} {ax.upper()} = {got:.3f} (want {lo_v}..{hi_v})", f"set {name}'s {what} on {ax.upper()} into {lo_v}..{hi_v} (off by {(lo_v - got) if got < lo_v else (got - hi_v):.3f})")
            else:
                fail(name, f"unknown relation {rel}", "use touches/gap/above/below/left_of/right_of/in_front_of/behind/size/at")
                ok_all = False
        if ok_all:
            checks.append(rbx_critic._check(f"expect:{name}", True, "ok", "as stated", ""))
    return checks


def label_points(parts, limit=8):
    """[(name, Blender-space centre)] of the biggest original parts (mirror copies and small details skipped:
    a label on every bolt hides the model). Inspect a detail with --inspect <Part> instead."""
    items = []
    for o, _ in parts:
        if "~" in o.name or not len(o.data.vertices):
            continue
        cs = [o.matrix_world @ v.co for v in o.data.vertices]
        lo = Vector([min(c[i] for c in cs) for i in range(3)])
        hi = Vector([max(c[i] for c in cs) for i in range(3)])
        items.append(((hi - lo).length, o.name, (lo + hi) / 2))
    items.sort(key=lambda t: -t[0])
    biggest = items[0][0] if items else 0
    return [(n, c) for d, n, c in items[:limit] if d >= biggest * 0.15]


def project_labels(scene, cam, points):
    """[(name, centre)] -> [{name, u, v}] in 0..1 image space (v from the top) for this camera."""
    out = []
    for name, c in points:
        p = world_to_camera_view(scene, cam, c)
        if 0 <= p.x <= 1 and 0 <= p.y <= 1 and p.z > 0:
            out.append({"name": name, "u": round(p.x, 4), "v": round(1 - p.y, 4)})
    return out


def render_inspect(asset, part_name, renders):
    """Close-ups of one part: front, right side and 3/4, other parts ghosted. Workbench, before the join."""
    target = None
    for o, _ in asset.parts:
        if o.name == part_name:
            target = o
    if target is None:
        names = ", ".join(sorted(o.name for o, _ in asset.parts if "~" not in o.name))
        raise KeyError(f'--inspect: no part "{part_name}". Parts: {names}')
    sc = asset.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0  # (a studio render before this must not leave its exposure)
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "OBJECT"
    sh.show_object_outline = True
    sh.show_xray = False
    sc.render.resolution_x, sc.render.resolution_y = 480, 360
    for o, _ in asset.parts:
        o.color = (0.55, 0.57, 0.62, 0.18)
    target.color = (1.0, 0.55, 0.15, 1.0)
    sh.show_xray = True
    sh.xray_alpha = 0.35
    if sc.world is None:
        sc.world = bpy.data.worlds.new("InspectWorld")
    sc.world.color = (0.12, 0.13, 0.16)
    cs = [target.matrix_world @ v.co for v in target.data.vertices]
    lo = Vector([min(c[i] for c in cs) for i in range(3)])
    hi = Vector([max(c[i] for c in cs) for i in range(3)])
    center = (lo + hi) / 2
    rad = max((hi - lo).length / 2, 0.05) * 2.2
    cam = bpy.data.objects.new("InspectCam", bpy.data.cameras.new("InspectCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = rad * 2 * 4 / 3
    tiles = []
    from rbx import BL_FROM_RBX  # noqa: PLC0415 — avoid an import cycle at module load

    for i, d in enumerate([(0, 0, -1), (1, 0, 0), (-0.7, 0.45, -0.7)]):
        direction = (BL_FROM_RBX.to_3x3() @ Vector(d)).normalized()
        cam.location = center + direction * (rad * 6 + 5)
        cam.data.clip_end = rad * 20 + 50
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        path = os.path.join(renders, f"_{asset.name}_inspect_{i}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        tiles.append(path)
    sh.show_xray = False
    for o, _ in asset.parts:
        o.color = (1, 1, 1, 1)
    bpy.data.objects.remove(cam)
    out = os.path.join(renders, f"{asset.name}_inspect_{part_name}.png")
    _hstack(tiles, out)
    return out


def _load_pixels(path):
    im = bpy.data.images.load(path)
    w, h = im.size
    px = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    return px.reshape(h, w, 4)[::-1]  # top row first


def _save_pixels(arr, path):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1]).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def _hstack(paths, out):
    arrs = [_load_pixels(p) for p in paths]
    for p in paths:
        os.remove(p)
    _save_pixels(np.concatenate(arrs, axis=1), out)


def _mask_from_image(arr):
    """foreground mask of a reference picture: alpha when it has one, else 'differs from the corner colour'."""
    a = arr[..., 3]
    if a.min() < 0.9:
        return a > 0.5
    bg = np.median(np.concatenate([arr[:4, :4, :3].reshape(-1, 3), arr[-4:, -4:, :3].reshape(-1, 3)]), axis=0)
    return np.abs(arr[..., :3] - bg).sum(axis=2) > 0.25


def _normalise(mask, n=256):
    """crop to content, scale the longer side to n (nearest), centre in an n x n canvas."""
    out, aspect, _xf = _normalise_xf(mask, n)
    return out, aspect


def _normalise_xf(mask, n=256):
    """_normalise, and how it moved the pixels: (row0, col0, scale, y0, x0) — a pixel (r, c) of the input lands at
    ((r - row0) * scale + y0, (c - col0) * scale + x0); scale * the content's longer side = n"""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return np.zeros((n, n), bool), 1.0, (0, 0, 1.0, 0, 0)
    crop = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    h, w = crop.shape
    s = n / max(h, w)
    nh, nw = max(1, int(round(h * s))), max(1, int(round(w * s)))
    yi = (np.arange(nh) / s).astype(int).clip(0, h - 1)
    xi = (np.arange(nw) / s).astype(int).clip(0, w - 1)
    small = crop[yi][:, xi]
    out = np.zeros((n, n), bool)
    y0, x0 = (n - nh) // 2, (n - nw) // 2
    out[y0 : y0 + nh, x0 : x0 + nw] = small
    return out, w / h, (int(ys.min()), int(xs.min()), s, y0, x0)


VIEWS = {"front": (0, 0, -1), "side": (1, 0, 0), "back": (0, 0, 1), "top": (0, 1, 0.0001), "side_left": (-1, 0, 0)}
# side_left: the model's LEFT flank (a photo of the left side, the slide stop and thumb safety of a pistol) — rendered
# from -X and mirrored, so its front is on the RIGHT like every trace (kit trace stores back -> front)
# what a reference that fits better flipped means, per view (the normalised frames of reference_match: a side or top
# view runs along its picture's width; a top view's up-down is the model's left-right)
_MIRRORED = ("a mirror image of the model — a chart drawn flipped, or the model's one-sided parts (a scope, a banner, a "
             "charging handle) on the wrong side")
MIRROR_MEANING = {("front", "left-right"): _MIRRORED, ("back", "left-right"): _MIRRORED, ("top", "up-down"): _MIRRORED,
                  ("side", "left-right"): "its front and back are swapped (traced with the wrong --front)",
                  ("top", "left-right"): "its front and back are swapped (traced with the wrong --front)",
                  ("side", "up-down"): "it is upside down", ("front", "up-down"): "it is upside down",
                  ("side_left", "left-right"): "its front and back are swapped (traced with the wrong --front)",
                  ("side_left", "up-down"): "it is upside down",
                  ("back", "up-down"): "it is upside down"}


def trace_mask(trace_path, px=1024):
    """a `kit trace` outline (u back->front, h up, holes cut out) as a filled mask, front on the RIGHT — the way the
    side camera sees the model (looking down -X, front = -Z to the right)."""
    import json  # noqa: PLC0415

    with open(trace_path, encoding="utf-8") as fh:
        t = json.load(fh)
    hr = max(float(t.get("height_ratio", 0.3)), 0.01)
    return _rings_mask([t["outline"], *t.get("holes", [])], hr, px)


def _rings_mask(rings, hr, px):
    """even-odd fill of rings in a trace's design units (u 0..1 back->front, h 0..hr up) — trace_mask's frame, so a
    trace's PARTS land exactly where its outline does"""
    w, h = px, max(8, int(px * hr))
    # even-odd scanline fill of the outline + holes (no PIL inside Blender's Python)
    edges = []
    for ring in rings:
        pts = [(1 + p[0] * w, 1 + (hr - p[1]) / hr * h) for p in ring]
        edges += [(pts[i - 1], pts[i]) for i in range(len(pts))]
    e = np.array(edges, float)  # (n, 2, 2)
    x0, y0, x1, y1 = e[:, 0, 0], e[:, 0, 1], e[:, 1, 0], e[:, 1, 1]
    mask = np.zeros((h + 2, w + 2), bool)
    xs = np.arange(w + 2) + 0.5
    for row in range(h + 2):
        yc = row + 0.5
        hit = (y0 <= yc) != (y1 <= yc)
        if not hit.any():
            continue
        xc = np.sort(x0[hit] + (yc - y0[hit]) * (x1[hit] - x0[hit]) / (y1[hit] - y0[hit]))
        mask[row] = (np.searchsorted(xc, xs) % 2) == 1
    return mask


COLOUR_VIEWS = ("side", "side_left", "front", "back", "top")


def colour_match(asset, objs, trace_path, albedo_path, regions_path, renders, n=1024, view="side"):
    """The model's colour against the reference's, region by region: the model's baked colour map seen flat (no light:
    what the texture holds) from the traced VIEW (side, side_left, front, back, top — as reference_match sees it: a
    side_left mirrored, a front with the model's right on the picture's left, a top turned a quarter so its front is
    on the right and the model's LEFT at the top, as a photo's top trace lies), against the reference's colours — the traced picture itself, or its colour
    with the lighting taken out (`kit vision albedo`'s .npz) — both sampled in the side trace's frame, inside both
    outlines. -> (facts, checks). A region is off when its median colour is another HUE (30 degrees apart) or half /
    twice as saturated (rbx_colour.colour_off). Lightness is said in words, never judged: a lit picture's lightness is
    its light's (and Marigold-IID gives a metal its bright specular colour, which is right for PBR). A warning."""
    import json  # noqa: PLC0415

    if view not in COLOUR_VIEWS:
        return {"note": f"colour_match: the {view} view is not compared yet ({', '.join(COLOUR_VIEWS)})"}, []
    with open(trace_path, encoding="utf-8") as fh:
        t = json.load(fh)
    with open(regions_path, encoding="utf-8") as fh:
        regs = json.load(fh)
    fr, src = t.get("frame") or {}, (t.get("source") or "").replace("\\", "/")
    if regs.get("image", "").replace("\\", "/") != src or not {"x0", "y1", "length_px"} <= set(fr):
        return {"note": f"the regions are drawn on {regs.get('image')}, the trace on {src}: not one picture"}, []
    if albedo_path.endswith(".npz"):
        z = np.load(albedo_path)
        alb = z["albedo"].astype(np.float32)
        meta = json.loads(str(z["meta"])) if "meta" in z.files else {}
        if meta.get("source", src).replace("\\", "/") != src:
            return {"note": f"{albedo_path} is the colour of {meta.get('source')}, not of {src}"}, []
    else:  # the traced picture itself (its sRGB values as they are)
        alb = _load_pixels(albedo_path)[..., :3]
    hr = max(float(t.get("height_ratio", 0.3)), 0.01)
    tm = trace_mask(trace_path, n)  # (hpx + 2, n + 2), front on the RIGHT
    hpx = tm.shape[0] - 2
    rows, cols = np.mgrid[0 : tm.shape[0], 0 : tm.shape[1]].astype(np.float64)
    u = (cols + 0.5 - 1) / n
    h = hr - (rows + 0.5 - 1) / hpx * hr
    L, x0, y1 = float(fr["length_px"]), float(fr["x0"]), float(fr["y1"])
    px = x0 + ((1 - u) if t.get("front") == "left" else u) * L
    py = y1 - h * L
    H, W = alb.shape[:2]
    inside = tm & (px >= 0) & (px < W) & (py >= 0) & (py < H)
    ref = np.zeros(tm.shape + (3,), np.float32)
    ref[inside] = alb[py[inside].astype(int), px[inside].astype(int)]
    # the model, flat: its colour map as the game holds it (or each material's colour in a --geo check)
    from rbx import BL_FROM_RBX  # noqa: PLC0415

    sc = asset.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.render.film_transparent = True
    sh = sc.display.shading
    sh.light, sh.show_cavity, sh.show_object_outline, sh.show_xray = "FLAT", False, False, False
    baked = [m for o in objs for m in o.data.materials if m and m.name.endswith("_baked") and m.node_tree]
    if baked:
        for m in baked:
            for nd in m.node_tree.nodes:
                if nd.type == "TEX_IMAGE" and nd.image and nd.image.name.endswith("_color"):
                    m.node_tree.nodes.active = nd
        sh.color_type = "TEXTURE"
    else:
        spec = {v["mat"].name: v["color"] for v in asset.mats.values()}
        for o in objs:
            for m in o.data.materials:
                if m and m.name in spec:
                    m.diffuse_color = (*spec[m.name], 1.0)
        sh.color_type = "MATERIAL"
    hidden = [o for o in sc.objects if o.type == "MESH" and o not in objs]
    for o in hidden:
        o.hide_render = True
    corners = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    centre, rad = (lo + hi) / 2, max((hi - lo).length / 2, 0.05)
    cam = bpy.data.objects.new("ColourCam", bpy.data.cameras.new("ColourCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type, cam.data.ortho_scale = "ORTHO", rad * 2.2
    cam.location = centre + (BL_FROM_RBX.to_3x3() @ Vector(VIEWS[view])).normalized() * (rad * 6 + 5)
    cam.data.clip_end = rad * 20 + 50
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    res = (sc.render.resolution_x, sc.render.resolution_y)
    sc.render.resolution_x = sc.render.resolution_y = 2048
    tmp = os.path.join(renders, f"_{asset.name}_colour.png")
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    sc.render.resolution_x, sc.render.resolution_y = res
    bpy.data.objects.remove(cam)
    for o in hidden:
        o.hide_render = False
    sc.render.film_transparent = False
    shot = _load_pixels(tmp)
    os.remove(tmp)
    if view == "side_left":   # (seen from -X the front is on the left: mirrored, it lies like its trace)
        shot = shot[:, ::-1].copy()
    elif view == "top":   # (the top camera has the front UP: a quarter turn puts it on the right, like the trace)
        shot = np.rot90(shot, -1).copy()
    ys, xs = np.nonzero(shot[..., 3] > 0.5)
    if not len(xs):
        return {"note": "the model rendered empty"}, []
    crop = shot[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]  # its outline's box = the trace's (u 0..1, h 0..hr)
    yi = (np.arange(hpx) * crop.shape[0] / hpx).astype(int).clip(0, crop.shape[0] - 1)
    xi = (np.arange(n) * crop.shape[1] / n).astype(int).clip(0, crop.shape[1] - 1)
    mod = np.zeros(tm.shape + (4,), np.float32)
    mod[1 : 1 + hpx, 1 : 1 + n] = crop[yi][:, xi]
    both = inside & (mod[..., 3] > 0.5)
    rows_out, off, sheet_boxes = [], [], []
    for reg in regs.get("regions", []):
        bx0, by0, bx1, by1 = reg["box"]
        us = sorted(((1 - (b - x0) / L) if t.get("front") == "left" else (b - x0) / L) for b in (bx0, bx1))
        hs = sorted((y1 - b) / L for b in (by0, by1))
        c0, c1 = int(1 + us[0] * n), int(1 + us[1] * n) + 1
        r0, r1 = int(1 + (hr - hs[1]) / hr * hpx), int(1 + (hr - hs[0]) / hr * hpx) + 1
        sel = np.zeros_like(both)
        sel[max(r0, 0) : r1, max(c0, 0) : c1] = True
        sel &= both
        if sel.sum() < 50:
            continue
        rm, mm = np.median(ref[sel], axis=0), np.median(mod[sel][:, :3], axis=0)
        rl, ml = srgb_to_lab(rm), srgb_to_lab(mm)
        de = float(np.linalg.norm(ml - rl))
        bad = colour_off(ml, rl)
        row = {"region": reg["name"] if view == "side" else f"{view} {reg['name']}",
               "ref_srgb": [round(float(v), 3) for v in rm],
               "model_srgb": [round(float(v), 3) for v in mm], "delta_e": round(de, 1),
               "how": colour_words(ml, rl), "off": bool(bad), "px": int(sel.sum())}
        rows_out.append(row)
        sheet_boxes.append((r0, r1, c0, c1, bad))
        if bad:
            off.append(row)
    # the evidence: the reference's colour (top) over the model's (bottom), the regions boxed (red = off)
    sheet = np.zeros((2 * tm.shape[0], tm.shape[1], 4), np.float32)
    sheet[..., 3] = 1.0
    sheet[: tm.shape[0], :, :3] = np.where(inside[..., None], ref, 0.12)
    sheet[tm.shape[0] :, :, :3] = np.where((mod[..., 3] > 0.5)[..., None], mod[..., :3], 0.12)
    for r0, r1, c0, c1, bad in sheet_boxes:
        colr = (0.95, 0.2, 0.15) if bad else (0.3, 0.85, 0.4)
        for top in (0, tm.shape[0]):
            a0, a1 = max(top + r0, top), min(top + r1, top + tm.shape[0] - 1)
            b0, b1 = max(c0, 0), min(c1, tm.shape[1] - 1)
            sheet[a0 : a0 + 3, b0:b1, :3] = colr
            sheet[a1 - 3 : a1, b0:b1, :3] = colr
            sheet[a0:a1, b0 : b0 + 3, :3] = colr
            sheet[a0:a1, b1 - 3 : b1, :3] = colr
    out = os.path.join(renders, f"{asset.name}_colours_{view}.png")
    _save_pixels(sheet, out)  # (both halves are sRGB values already: a byte PNG keeps them as they are)
    off.sort(key=lambda r_: -r_["delta_e"])
    facts = {"reference_colours": albedo_path.replace("\\", "/"), "regions": rows_out,
             "sheet": out.replace("\\", "/")}
    text = "; ".join(f"{r_['region']}: {r_['how']}" for r_ in off[:4])
    checks = [rbx_critic._check(
        "colour_match", not off, [f"{r_['region']}: {r_['how']}" for r_ in off[:6]] or
        f"{len(rows_out)} region(s) in the reference's hues", "each region's hue within 30 degrees and its "
        "saturation within 2x of the reference's", f"colours off the reference's: {text} — change the material's "
        f"colour (or what wears it: wear, grime) toward the reference; look at {out} (the reference above, the model "
        "below)", "warn")]
    return facts, checks


def _lines_input(asset, view, ref_path, shaded, objs, dont_care, renders):
    """what kit/vision/lines.py needs to put the photo and the shaded model in ONE frame: the reference picture and
    how its trace was cut (box, rotation, exclusions, front), the model render, the don't-care boxes"""
    import json  # noqa: PLC0415

    from rbx import REPO  # noqa: PLC0415

    # the model's length in THIS view (the frame's width) — in Blender's axes: x = Roblox x, y = Roblox -z (the length of
    # a model facing -Z), z = up; a side view spans y, a front / back / top view spans x. With the real scale
    # (a.real_scale) the lines report says where a missing line is in millimetres from the back
    from mathutils import Vector  # noqa: PLC0415

    corners = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    ext = [max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3)] if corners else [0, 0, 0]
    across = {"side": 1, "front": 0, "back": 0, "top": 0}.get(view, 1)
    info = {"asset": asset.name, "view": view, "model": os.path.relpath(shaded, REPO).replace("\\", "/"),
            "dont_care": [list(b) for b in dont_care], "mm_per_stud": getattr(asset, "mm_per_stud", None),
            "length_studs": round(float(ext[across]), 4) or None,
            "quality": asset.quality, "groups": sorted({o.name for o in objs})}
    if ref_path.endswith(".trace.json"):
        with open(ref_path, encoding="utf-8") as fh:
            t = json.load(fh)
        info.update(trace=os.path.relpath(ref_path, REPO).replace("\\", "/"), photo=t.get("source"),
                    box=t.get("box"), rotate=t.get("rotate", 0.0), exclude=t.get("exclude", []),
                    protect=t.get("protect", []), front=t.get("front", "right"), height_ratio=t.get("height_ratio"),
                    mask=t.get("mask"), bg=t.get("bg", "auto"), threshold=t.get("threshold", 28.0),
                    open=t.get("open", 0), straighten=t.get("straighten"))
    else:
        info.update(trace=None, photo=os.path.relpath(ref_path, REPO).replace("\\", "/"), box=None, rotate=0.0,
                    exclude=[], protect=[], front="right", height_ratio=None)
    with open(os.path.join(renders, f"{asset.name}_ref_{view}_lines.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)


def _regions_in_frame(ref_path, regions_path, xf, px=2048):
    """refs/<asset>.regions.json boxes on the traced picture -> boxes in the normalised frame
    (rbx_gaps.regions_in_frame)"""
    import json  # noqa: PLC0415

    with open(ref_path, encoding="utf-8") as fh:
        t = json.load(fh)
    with open(regions_path, encoding="utf-8") as fh:
        regs = json.load(fh)
    return rbx_gaps.regions_in_frame(t, regs, xf, px)


# how each view's diff picture lies, for the gap messages (a trace of a top view runs back -> front like a side view)
VIEW_LEGEND = {"side": "the back on the left, the front on the right",
               "side_left": "the model's LEFT side, mirrored: the back on the left, the front on the right",
               "top": "seen from above, the back on the left, the front on the right",
               "front": "seen from the front: the model's right side (+X) on the left",
               "back": "seen from behind: the model's right side (+X) on the right"}


def _part_id_masks(asset, objs, renders, n_max=1023):
    """ONE flat render from the current camera, every face coloured by the part it was built as (a joined group's
    "kit_part" face attribute + its "kit_parts" names) -> {part name: the pixels where that part is SEEN} — a part
    hidden behind another is not seen, exactly as in a photo of the object"""
    sc = asset.scene
    sh = sc.display.shading
    names, made = [], []
    for o in objs:
        me = o.data
        n = len(me.polygons)
        part_names = list(o.get("kit_parts", [o.name]))
        idx = np.zeros(n, np.int32)
        attr = me.attributes.get("kit_part")
        if attr is not None and attr.domain == "FACE":
            attr.data.foreach_get("value", idx)
        gid = np.clip(idx + len(names) + 1, 1, n_max)  # (0 = the background)
        names += part_names
        col = np.zeros((n, 4), np.float32)
        col[:, 0], col[:, 1], col[:, 2], col[:, 3] = ((gid % 32) * 8 + 4) / 255, ((gid // 32) * 8 + 4) / 255, 0.5, 1.0
        totals = np.zeros(n, np.int32)
        me.polygons.foreach_get("loop_total", totals)
        ca = me.color_attributes.new("kit_partid", "BYTE_COLOR", "CORNER")
        ca.data.foreach_set("color_srgb", col[np.repeat(np.arange(n), totals)].ravel())
        prev = me.color_attributes.active_color
        me.color_attributes.active_color = ca
        made.append((me, ca, prev))
    keep = (sh.light, sh.color_type, sc.display.render_aa, sh.show_cavity, sh.show_shadows)
    sh.light = "FLAT"
    sh.show_cavity = sh.show_shadows = False  # (a preview leaves cavity on: 11% of the pixels decoded to a neighbour)
    for ct in ("VERTEX", "ATTRIBUTE"):
        try:
            sh.color_type = ct
            break
        except TypeError:
            continue
    sc.display.render_aa = "OFF"
    # the ids are EXACT 8-bit colours: an 8-bit PNG, no dither, whatever an earlier render left (a 16-bit PNG decoded
    # every part as another one)
    ims = sc.render.image_settings
    keep_out = (ims.file_format, ims.color_mode, ims.color_depth, sc.render.dither_intensity)
    ims.file_format = "PNG"
    ims.color_mode, ims.color_depth, sc.render.dither_intensity = "RGBA", "8", 0.0
    tmp = os.path.join(renders, f"_{asset.name}_partid.png")
    sc.render.filepath = tmp
    try:
        bpy.ops.render.render(write_still=True)
    finally:
        ims.file_format = keep_out[0]
        for _ in range(2):  # (the depth only sticks once the format allows it)
            ims.color_mode, sc.render.dither_intensity = keep_out[1], keep_out[3]
            try:
                ims.color_depth = keep_out[2]
            except TypeError:
                pass
    px = _load_pixels(tmp)
    os.remove(tmp)
    sh.light, sh.color_type, sc.display.render_aa, sh.show_cavity, sh.show_shadows = keep
    for me, ca, prev in made:
        if prev is not None:
            me.color_attributes.active_color = prev
        me.color_attributes.remove(ca)
    seen = px[..., 3] > 0.5
    gid = np.rint((px[..., 0] * 255 - 4) / 8).astype(int) + 32 * np.rint((px[..., 1] * 255 - 4) / 8).astype(int)
    gid[~seen] = 0
    return {nm: gid == i + 1 for i, nm in enumerate(names)}


def _apply_xf(mask, xf, n):
    """another mask of the same picture through the SAME normalisation (_normalise_xf's crop, scale and offset)"""
    row0, col0, s, y0, x0 = xf
    rows = ((np.arange(n) - y0) / s).astype(int) + row0
    cols = ((np.arange(n) - x0) / s).astype(int) + col0
    ok_r = (np.arange(n) >= y0) & (rows >= 0) & (rows < mask.shape[0])
    ok_c = (np.arange(n) >= x0) & (cols >= 0) & (cols < mask.shape[1])
    out = np.zeros((n, n), bool)
    out[np.ix_(ok_r, ok_c)] = mask[np.ix_(rows[ok_r], cols[ok_c])]
    return out


PART_BAR = 0.85  # a linked part's own outline against the one traced from the picture (hero / aaa: an error)


def _fill_holes(mask):
    """the mask with its enclosed holes filled (background that cannot reach the border), on its bounding box"""
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return mask
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = np.pad(mask[y0:y1, x0:x1], 1)
    out_ = np.zeros_like(sub)
    out_[0, :] = out_[-1, :] = True
    out_[:, 0] = out_[:, -1] = True
    out_ &= ~sub
    while True:  # grow the outside through the background, 4-connected
        grown = out_.copy()
        grown[1:] |= out_[:-1]
        grown[:-1] |= out_[1:]
        grown[:, 1:] |= out_[:, :-1]
        grown[:, :-1] |= out_[:, 1:]
        grown &= ~sub
        if (grown == out_).all():
            break
        out_ = grown
    filled = mask.copy()
    filled[y0:y1, x0:x1] = ~out_[1:-1, 1:-1]
    return filled


OPENING_FILLED_BAR = 0.5   # the model covers more than this share of the picture's openings: said (a warning)


def _holes_tool():
    """kit/tools/silhouette_holes.py: the holes a model leaves open and the openings both outlines enclose (plain
    numpy - tested without Blender)"""
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location(
        "silhouette_holes", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "silhouette_holes.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def part_match(asset, view, ref_path, parts, idmasks, m_xf, r_xf, n, mm_per_px, renders):
    """PER PART: each traced part of the picture (kit trace --part-box / --part-text / --part-point) against the
    model's parts it names — the outline only the part shows in both (IoU), and its edges in mm (rbx_gaps). The
    whole silhouette can match while the trigger, the barrel or a grip is wrong; this is what catches it.
    parts = {"<traced part>": ["<model part>", ...]} (a.trace_match(parts=...)). -> (facts, checks, sheet path)
    "<traced part>!" compares OUTLINES ONLY: the picture's see-through holes inside it and the model's own are both
    filled — for a part whose openings are a design detail that differs on purpose (the Silverballer's three-hole
    trigger against the Hardballer's windowed one); its outline is still held to the same bar."""
    import json  # noqa: PLC0415

    with open(ref_path, encoding="utf-8") as fh:
        t = json.load(fh)
    hr = max(float(t.get("height_ratio", 0.3)), 0.01)
    traced = t.get("parts") or {}
    # the picture's see-through holes (a trigger's window, the guard's opening) are background in EVERY part: a part's
    # traced ring is its outer edge only, so a hole inside it is taken out here
    seen_through = _rings_mask(t["holes"], hr, 2048) if t.get("holes") else None
    facts, bad, tiles = {}, [], []
    unit = "mm" if getattr(asset, "mm_per_stud", None) else "studs"
    for tname, mnames in parts.items():
        outline_only = tname.endswith("!")
        pieces = tname.rstrip("!").split("+")  # "slide+slidefront": a part the segmenter traced in pieces, joined
        lost = [pc for pc in pieces if pc not in traced]
        if lost:
            facts[tname] = {"error": f"no traced part '{lost[0]}' in {os.path.basename(ref_path)} "
                                     f"(it has: {', '.join(sorted(traced)) or 'none'})"}
            bad.append(f"{tname}: not traced")
            continue
        rp = np.zeros((n, n), bool)
        for pc in pieces:
            ring = _rings_mask([traced[pc]], hr, 2048)
            rp |= _apply_xf(ring & ~seen_through if seen_through is not None and not outline_only else ring, r_xf, n)
        hits = [k for k in idmasks if any(k == m_ or k.startswith(m_ + "~") for m_ in mnames)]
        if not hits:
            facts[tname] = {"error": f"no model part named {', '.join(mnames)}"}
            bad.append(f"{tname}: no model part {', '.join(mnames)}")
            continue
        mp = np.zeros_like(next(iter(idmasks.values())))
        for k in hits:
            mp |= idmasks[k]
        mp = _apply_xf(mp, m_xf, n)
        if not mp.any():  # (said plainly: "IoU 0.00, edges off 0" read as a match gone wrong)
            facts[tname] = {"model": hits, "error": "not seen in this view"}
            bad.append(f"{tname}: {', '.join(hits)} not seen in the model's {view} view (hidden behind another part, "
                       "or the part-id render failed)")
            continue
        if outline_only:
            mp = _fill_holes(mp)
        union = (mp | rp).sum()
        iou = float((mp & rp).sum() / union) if union else 0.0
        gaps, _marks = rbx_gaps.edge_gaps(mp, rp, mm_per_px, unit, view=view)
        ys, xs = np.nonzero(rp | mp)
        size = float(max(np.ptp(ys) + 1, np.ptp(xs) + 1) * mm_per_px) if len(xs) else 0.0
        tol = max(1.0 if unit == "mm" else 0.004, 0.04 * size)
        row = {"model": hits, "iou": round(iou, 3), "size": round(size, 1), "p95": gaps.get("p95", 0.0),
               "max": gaps.get("max", 0.0), "tolerance": round(tol, 2), "unit": unit,
               "worst": gaps.get("worst", [])[:2]}
        facts[tname] = row
        if iou < PART_BAR or row["p95"] > tol:
            how = (f"{tname}: IoU {iou:.2f}, edges off {row['p95']:g} {unit} (95%) / {row['max']:g} max"
                   + (f" — {row['worst'][0]}" if row["worst"] else ""))
            bad.append(how)
        if len(xs):  # its own tile: grey both, red the picture has it, blue the model sticks out
            pad = 6
            y0_, y1_ = max(0, ys.min() - pad), min(n, ys.max() + pad + 1)
            x0_, x1_ = max(0, xs.min() - pad), min(n, xs.max() + pad + 1)
            tile = np.zeros((y1_ - y0_, x1_ - x0_, 4), np.float32)
            tile[..., 3] = 1
            sm, sr = mp[y0_:y1_, x0_:x1_], rp[y0_:y1_, x0_:x1_]
            tile[sm & sr] = (0.75, 0.75, 0.78, 1)
            tile[sr & ~sm] = (0.95, 0.25, 0.2, 1)
            tile[sm & ~sr] = (0.2, 0.55, 1.0, 1)
            tiles.append(tile)
    sheet = None
    if tiles:
        hgt = max(tl.shape[0] for tl in tiles)
        row_ = np.zeros((hgt, sum(tl.shape[1] + 8 for tl in tiles), 4), np.float32)
        row_[..., 3] = 1
        x = 0
        for tl in tiles:
            row_[: tl.shape[0], x : x + tl.shape[1]] = tl
            x += tl.shape[1] + 8
        sheet = os.path.join(renders, f"{asset.name}_parts_{view}.png")
        _save_pixels(row_, sheet)
    hero = getattr(asset, "quality", "prop") in ("hero", "aaa")
    check = rbx_critic._check(
        f"part_match_{view}", not bad, bad[:4] or f"{len(facts)} part(s) match their traced outlines",
        f"every linked part IoU >= {PART_BAR} and its edges within its tolerance (1 mm or 4% of its size)",
        f"{'; '.join(bad[:3])} — reshape that part from its traced outline (the sheet "
        f"{(sheet or '').replace(chr(92), '/')}: one tile per part in the order of parts=; red = the picture has it, "
        "blue = the model sticks out)", "error" if hero else "warn")
    return facts, [check], sheet


DEPTH_BAR = 0.15   # the model's relief against the photo's (Pearson): under it, said (a warning). Measured on the
#                    Glock's side photo against its model: 0.32 aligned, -0.18..0.12 with the model shifted aside
DEPTH_RES = 384    # the model's depth: rays per side of the view


def _model_depth(objs, cam, res=DEPTH_RES):
    """the model's depth from the reference camera (orthographic), ray by ray -> (depth (res, res) studs from the
    camera's plane, nan where no ray hits), row 0 at the TOP like a picture"""
    from mathutils.bvhtree import BVHTree  # noqa: PLC0415

    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        base, mw = len(verts), o.matrix_world
        verts += [mw @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        ev.to_mesh_clear()
    out = np.full((res, res), np.nan, dtype=np.float32)
    if not polys:
        return out
    tree = BVHTree.FromPolygons(verts, polys)
    mw = cam.matrix_world
    way = (mw.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    half = cam.data.ortho_scale / 2.0
    steps = (np.arange(res) + 0.5) / res * 2.0 * half - half
    for iy, y in enumerate(steps[::-1]):
        for ix, x in enumerate(steps):
            hit = tree.ray_cast(mw @ Vector((float(x), float(y), 0.0)), way)
            if hit[0] is not None:
                out[iy, ix] = hit[3]
    return out


def _photo_relief(ref_path):
    """the trace's photo relief, made once and kept (kit/vision/depth_ref.py, the system python: torch is not in
    Blender's) -> (near, mask, source) or (None, None, why)"""
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    py = os.environ.get("PYTHON") or shutil.which("python") or "python"
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vision", "depth_ref.py")
    try:
        run = subprocess.run([py, tool, ref_path], capture_output=True, text=True, timeout=1200)
    except (OSError, subprocess.SubprocessError) as e:
        return None, None, f"depth_ref did not run ({e})"
    verdict = next((json.loads(ln) for ln in reversed(run.stdout.splitlines()) if ln.startswith("{")), None)
    if not verdict or verdict.get("status") != "pass" or not verdict.get("depth"):
        return None, None, (verdict or {}).get("summary") or (run.stderr or "depth_ref failed")[-300:]
    with np.load(verdict["depth"]) as z:
        return z["near"].astype(np.float32), z["mask"].astype(bool), str(z["source"]) if "source" in z else "?"


def _relief_tool():
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location(
        "depth_relief", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "depth_relief.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reference_match(asset, objs, view, ref_path, renders, bar=0.75, dont_care=(), regions=None, parts=None,
                    align=None, depth=False):
    """silhouette of the built model from `view` vs the reference picture (or a `kit trace` outline, *.trace.json)
    -> (facts, checks, diff path). Leave out of `objs` what the reference does not show (Asset.trace_match ignore=).
    A traced view is also measured EDGE TO EDGE (rbx_gaps): where the model's outline and the reference's disagree, in
    mm with a.real_scale (else studs), per 3 x 3 window and per region of `regions` (refs/<asset>.regions.json) —
    a warning `view_gaps_<view>` naming the worst three places beyond 3 mm or 2% of the view's size."""
    if view not in VIEWS:
        raise ValueError(f'reference view must be one of {", ".join(VIEWS)}')
    if not os.path.isfile(ref_path):
        raise FileNotFoundError(f"reference image not found: {ref_path}")
    from rbx import BL_FROM_RBX  # noqa: PLC0415

    sc = asset.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0  # (a studio render before this must not leave its exposure)
    sc.render.film_transparent = True
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "SINGLE"
    sh.single_color = (0, 0, 0)
    sh.show_object_outline = False
    sh.show_xray = False
    traced = ref_path.endswith(".trace.json")  # a trace is exact: measure it at a resolution thin parts survive
    sc.render.resolution_x = sc.render.resolution_y = 2048 if traced else 512
    hidden = [o for o in sc.objects if o.type == "MESH" and o not in objs]
    for o in hidden:
        o.hide_render = True
    corners = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    center = (lo + hi) / 2
    rad = max((hi - lo).length / 2, 0.05)
    cam = bpy.data.objects.new("RefCam", bpy.data.cameras.new("RefCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = rad * 2.2
    direction = (BL_FROM_RBX.to_3x3() @ Vector(VIEWS[view])).normalized()
    cam.location = center + direction * (rad * 6 + 5)
    cam.data.clip_end = rad * 20 + 50
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    tmp = os.path.join(renders, f"_{asset.name}_refsil.png")
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    model = _load_pixels(tmp)[..., 3] > 0.5
    studs_px = cam.data.ortho_scale / max(model.shape)  # one render pixel in studs (the gaps' scale)
    os.remove(tmp)
    traced_parts = bool(parts) and traced and view != "top"
    idmasks = _part_id_masks(asset, objs, renders) if traced_parts else None
    if view == "side_left":  # (seen from -X the front is on the left: mirrored, it lies like every trace)
        model = model[:, ::-1]
        if idmasks is not None:
            idmasks = {k: v[:, ::-1] for k, v in idmasks.items()}
    # the same view SHADED in the parts' own colours (studio light + cavity), always at full resolution:
    # kit/vision/lines.py runs one edge detector on it and on the reference photo and compares the lines INSIDE the
    # silhouette (seams, plates, slots, colour / finish changes) — what a silhouette cannot see
    baked = [m for o in objs for m in o.data.materials if m and m.name.endswith("_baked") and m.node_tree]
    if baked:  # a full build: the baked colour map is what the game shows (workbench samples the ACTIVE image node)
        for m in baked:
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image and n.image.name.endswith("_color"):
                    m.node_tree.nodes.active = n
        sh.color_type = "TEXTURE"
    else:  # a --geo check: each material's own base colour (workbench reads diffuse_color, which nothing else sets)
        spec = {v["mat"].name: v["color"] for v in asset.mats.values()}
        for o in objs:
            for m in o.data.materials:
                if m and m.name in spec:
                    m.diffuse_color = (*spec[m.name], 1.0)
        sh.color_type = "MATERIAL"
    sh.light, sh.show_cavity = "STUDIO", True
    res = (sc.render.resolution_x, sc.render.resolution_y)
    sc.render.resolution_x = sc.render.resolution_y = 2048  # (a plain-picture reference measures its silhouette at 512)
    shaded = os.path.join(renders, f"{asset.name}_ref_{view}_shaded.png")
    sc.render.filepath = shaded
    bpy.ops.render.render(write_still=True)
    if view == "side_left":  # (mirrored like the silhouette)
        _save_pixels(_load_pixels(shaded)[:, ::-1].copy(), shaded)
    sc.render.resolution_x, sc.render.resolution_y = res
    sh.show_cavity = False
    relief = None
    if depth and ref_path.endswith(".trace.json"):   # (the RELIEF: a.trace_match(..., depth=True))
        near_p, mask_p, source = _photo_relief(ref_path)
        if near_p is None:
            relief = {"error": source}
        else:
            md = _model_depth(objs, cam)
            got = _relief_tool().compare(near_p, mask_p, -np.nan_to_num(md), ~np.isnan(md))
            relief = got if got is not None else {"error": "the photo's and the model's insides do not overlap"}
            relief["source"] = source
    bpy.data.objects.remove(cam)
    if ((getattr(asset, "ref_options", None) or {}).get(view) or {}).get("lines", True):
        _lines_input(asset, view, ref_path, shaded, objs, dont_care, renders)
    else:   # (trace_match(lines=False): another specimen's inside lines are not this one's — and no stale input stays)
        stale = os.path.join(renders, f"{asset.name}_ref_{view}_lines.json")
        if os.path.isfile(stale):
            os.remove(stale)
    for o in hidden:
        o.hide_render = False
    sc.render.film_transparent = False
    ref = trace_mask(ref_path, 2048) if traced else _mask_from_image(_load_pixels(ref_path))
    if not ref.any():
        raise ValueError(
            f"no shape found in {ref_path} — use a picture with a transparent background, or a plain background "
            "that differs clearly from the object"
        )
    orientation = None
    if traced and view == "top":
        # the top camera sees the model with its front UP (+X on the right). A traced top view lies another way: a
        # photo's trace runs back -> front, left to right (as kit trace stores every side / top outline); a `kit refs
        # measure` mask has the front DOWN. The model is turned the way whose proportions the trace has (an elongated
        # object is never ambiguous)
        def _aspect(mask):
            ys_, xs_ = np.nonzero(mask)
            return (np.ptp(xs_) + 1) / (np.ptp(ys_) + 1) if len(xs_) else 1.0

        ra = _aspect(ref)
        turns = {"front on the right (a traced top view)": np.rot90(model, -1),
                 "front down (kit refs measure)": np.rot90(model, 2)}
        orientation = min(turns, key=lambda k_: abs(math.log(max(_aspect(turns[k_]), 1e-6) / max(ra, 1e-6))))
        model = turns[orientation]
    big = 1024 if traced else 256
    dc_raw = []  # the dont_care boxes in the reference's own pixels (trace_mask's frame: 1 px of padding round it)
    if dont_care and traced:
        import json  # noqa: PLC0415

        with open(ref_path, encoding="utf-8") as fh:
            hr_ = max(float(json.load(fh).get("height_ratio", 0.3)), 0.01)
        w_, h_ = ref.shape[1] - 2, ref.shape[0] - 2
        for u0, h0, u1, h1 in dont_care:
            dc_raw.append((1 + (hr_ - max(h0, h1)) / hr_ * h_, 1 + (hr_ - min(h0, h1)) / hr_ * h_,
                           1 + min(u0, u1) * w_, 1 + max(u0, u1) * w_))

    def to_norm(y, x, xf):
        row0, col0, s_, y0_, x0_ = xf
        return (y - row0) * s_ + y0_, (x - col0) * s_ + x0_

    def from_norm(y, x, xf):
        row0, col0, s_, y0_, x0_ = xf
        return (y - y0_) / s_ + row0, (x - x0_) / s_ + col0

    def box_slice(ya, yb, xa, xb, shape):
        # (both ends clamped into the picture: a box wholly above / behind it gave a NEGATIVE stop, which Python
        # counts from the end — 91% of the reference's rows blanked; found by the review)
        return (slice(max(0, min(shape[0], int(ya))), max(0, min(shape[0], int(math.ceil(yb)) + 1))),
                slice(max(0, min(shape[1], int(xa))), max(0, min(shape[1], int(math.ceil(xb)) + 1))))

    m, m_aspect, m_xf0 = _normalise_xf(model, big)
    r, r_aspect, r_xf = _normalise_xf(ref, big)
    if dc_raw:
        # a don't-care box is not compared — and it must not STEER the fit either: both outlines are fitted by their
        # bounding boxes, so a feature that differs on purpose inside a box (the Silverballer's taller rear sight
        # against the Hardballer photo's) would shift the whole frame by half its excess and make every part look
        # misplaced (measured: the trigger 0.82 -> 0.57, the slide stop 0.96 -> 0.59). Blank the boxes in both
        # pictures — in the model's where the first fit puts them — and fit again.
        ref = ref.copy()
        for ya, yb, xa, xb in dc_raw:
            ref[box_slice(ya, yb, xa, xb, ref.shape)] = False
        r, r_aspect, r_xf = _normalise_xf(ref, big)
        model0 = model
        for _pass in range(4):  # (each fit places the boxes better: a few passes settle it)
            model = model0.copy()
            for ya, yb, xa, xb in dc_raw:
                (na, ma), (nb, mb) = to_norm(ya, xa, r_xf), to_norm(yb, xb, r_xf)
                (ya_, xa_), (yb_, xb_) = from_norm(na, ma, m_xf0), from_norm(nb, mb, m_xf0)
                model[box_slice(ya_, yb_, xa_, xb_, model.shape)] = False
            m, m_aspect, fit = _normalise_xf(model, big)
            if fit == m_xf0:
                break
            m_xf0 = fit
    m_fit = None  # the model's frame when ALIGNED ON A PART (else each picture is fitted by its own box)
    if align and traced and idmasks is not None:
        # align=<traced part>: the model is laid on the picture by THAT part (its box's left end and length, its
        # height's middle) instead of by the whole outline's box — a part that sticks out differently (a cocked
        # hammer, a longer beavertail, a sight) no longer shifts and scales everything else. Pick a big part both
        # show whole (a can, a barrel, a receiver)
        import json  # noqa: PLC0415

        with open(ref_path, encoding="utf-8") as fh:
            t_ = json.load(fh)
        tparts = t_.get("parts") or {}
        if align not in tparts or align not in (parts or {}):
            raise ValueError(f"trace_match align={align!r}: it must be a part traced in {os.path.basename(ref_path)} "
                             f"({', '.join(sorted(tparts)) or 'none'}) AND a key of parts= (the model parts it is)")
        rp_raw = _rings_mask([tparts[align]], max(float(t_.get("height_ratio", 0.3)), 0.01), ref.shape[1] - 2)
        mp_raw = np.zeros(model.shape, bool)
        for k_, v_ in idmasks.items():
            if any(k_ == m_ or k_.startswith(m_ + "~") for m_ in parts[align]):
                mp_raw |= v_
        if not mp_raw.any() or not rp_raw.any():
            seen_ = sorted(((int(v_.sum()), k_) for k_, v_ in idmasks.items() if v_.any()), reverse=True)[:10]
            raise ValueError(f"trace_match align={align!r}: the part is not seen in the "
                             f"{'trace' if not rp_raw.any() else 'model view (its parts: ' + ', '.join(parts[align]) + ')'}"
                             f" — the part-ID render saw: {', '.join(f'{k_} {n_} px' for n_, k_ in seen_) or 'nothing'}")
        ry, rx = np.nonzero(rp_raw)
        my, mx = np.nonzero(mp_raw)
        y0n, x0n = to_norm(ry.min(), rx.min(), r_xf)
        y1n, x1n = to_norm(ry.max() + 1, rx.max() + 1, r_xf)
        s_fit = (x1n - x0n) / float(mx.max() + 1 - mx.min())
        # (in _apply_xf's form with the origin at the picture's corner: (r, c) -> (r * s + y0, c * s + x0); its
        # "content starts at y0" guard then only drops rows / columns that map outside the render)
        yc_m = (my.min() + my.max() + 1) / 2.0
        m_fit = (0, 0, s_fit, (y0n + y1n) / 2.0 - yc_m * s_fit, x0n - mx.min() * s_fit)
        m = _apply_xf(model, m_fit, big)
    ys_m, xs_m = np.nonzero(model)
    # one pixel of the normalised frame in studs: the model's longer side (in render pixels) fills n of them
    frame_studs = studs_px * max(np.ptp(ys_m) + 1, np.ptp(xs_m) + 1) / m.shape[0] if len(xs_m) else 0.0
    if m_fit is not None:
        frame_studs = studs_px / m_fit[2]
    dc_sl = []
    for ya, yb, xa, xb in dc_raw:  # the boxes in the fitted frame: out of the comparison on both sides
        (na, ma), (nb, mb) = to_norm(ya, xa, r_xf), to_norm(yb, xb, r_xf)
        sl = box_slice(na, nb, ma, mb, m.shape)
        m[sl] = False
        r[sl] = False
        dc_sl.append(sl)
    inter, union = np.logical_and(m, r).sum(), np.logical_or(m, r).sum()
    iou = float(inter / union) if union else 0.0
    opened = None
    if traced:
        # OPENINGS: only where the trace names its see-through holes (a trace without them says nothing about the
        # model's own: a tracer who skipped the trigger window must not make the fit close it)
        import json  # noqa: PLC0415

        with open(ref_path, encoding="utf-8") as fh:
            t_o = json.load(fh)
        mmps_ = getattr(asset, "mm_per_stud", None)
        if t_o.get("holes"):
            tool, skip = _holes_tool(), list(dc_sl)
            hr_o, tp_o = max(float(t_o.get("height_ratio", 0.3)), 0.01), t_o.get("parts") or {}
            for tname in parts or {}:   # a part traced "outlines only" ("<part>!"): its openings differ on purpose
                for pc in (tname.rstrip("!").split("+") if tname.endswith("!") else []):
                    if pc in tp_o:      # (grown 1% of the frame: the model's part sits near, not on, the traced one)
                        skip.append(tool.grow(_apply_xf(_rings_mask([tp_o[pc]], hr_o, 2048), r_xf, m.shape[0]),
                                              max(1, m.shape[0] // 100)))
            opened = tool.openings(r, m, skip, frame_studs * mmps_ if (mmps_ and frame_studs > 0) else None)
    # a reference that fits far better FLIPPED is not a shape to chase: a chart drawn as a mirror image, a model with
    # its one-sided parts (a scope, a banner) on the wrong side, a picture's front and back swapped. Side views cannot
    # show a mirror image, so only the other views catch it (the Gjallarhorn's chart: front IoU 0.41 as drawn, 0.72
    # flipped; top 0.45 / 0.87 — 18 builds measured against it before it was seen)
    flips = {}
    for key, rr in (("left-right", r[:, ::-1]), ("up-down", r[::-1, :])):
        u_ = np.logical_or(m, rr).sum()
        flips[key] = round(float(np.logical_and(m, rr).sum() / u_) if u_ else 0.0, 3)
    # where do they disagree most? 3x3 regions (top/middle/bottom x left/centre/right of the picture)
    worst, worst_val = None, 0.0
    n = m.shape[0]
    names_v, names_h = ("top", "middle", "bottom"), ("left", "centre", "right")
    for i in range(3):
        for j in range(3):
            sl = (slice(i * n // 3, (i + 1) * n // 3), slice(j * n // 3, (j + 1) * n // 3))
            missing = np.logical_and(r[sl], ~m[sl]).sum()
            extra = np.logical_and(m[sl], ~r[sl]).sum()
            if missing + extra > worst_val:
                worst_val = missing + extra
                worst = (names_v[i], names_h[j], "missing" if missing >= extra else "extra")
    diff = np.zeros((n, n, 4), dtype=np.float32)
    diff[..., 3] = 1
    diff[np.logical_and(m, r)] = (0.75, 0.75, 0.78, 1)  # both
    diff[np.logical_and(r, ~m)] = (0.95, 0.25, 0.2, 1)  # reference has it, model doesn't (missing)
    diff[np.logical_and(m, ~r)] = (0.2, 0.55, 1.0, 1)  # model has it, reference doesn't (extra)
    out = os.path.join(renders, f"{asset.name}_ref_{view}.png")
    gap_check = None
    if traced and frame_studs > 0:
        # edge to edge, in mm: WHERE the outlines disagree and by how much (the IoU only says how much is wrong)
        mmps = getattr(asset, "mm_per_stud", None)
        unit = "mm" if mmps else "studs"
        regs, reg_note = ([], None) if not regions else _regions_in_frame(ref_path, regions, r_xf)
        gaps, marks = rbx_gaps.edge_gaps(m, r, frame_studs * (mmps or 1.0), unit, view=view, regions=regs)
        if reg_note:
            gaps["regions_note"] = reg_note
        if orientation:
            gaps["orientation"] = orientation
        by_, bx_ = np.nonzero(m | r)
        rbx_gaps.annotate(diff, marks, box=(by_.min(), by_.max() + 1, bx_.min(), bx_.max() + 1))
        tol, out_ = f"{gaps['tolerance']:g} {unit}", out.replace("\\", "/")
        worst_regions = [h for row in gaps.get("regions", []) for h in row.get("how", [])]
        said = gaps.get("worst", [])[:3] + worst_regions[:2]
        gap_check = rbx_critic._check(
            f"view_gaps_{view}", not said, said or f"every edge within {tol} (mean {gaps.get('mean', 0):g} {unit})",
            f"every edge within {tol} of the reference's (3 mm or 2% of the view's size)",
            f"{view} view: {'; '.join(said)} — move or resize what makes that edge (the diff picture {out_}: yellow "
            f"= where, red = the reference has it, blue = the model sticks out; {VIEW_LEGEND[view]})"
            + ("" if mmps else " — a.real_scale(mm_per_stud) says it in millimetres"), "warn")
    hole_check = None
    if traced and frame_studs > 0 and getattr(asset, "mm_per_stud", None):
        # HOLES (the owner, 2026-11-11, on the revolver's build 4: "is some of the body not fully filled in?" - its side
        # view matched at IoU 0.936 while a 141 mm2 wedge behind the trigger was open): a region the reference has and
        # the model leaves open, region by region - one IoU and the edge gaps above never name a hole inside the outline
        sh_ = _holes_tool()
        mm_px = frame_studs * asset.mm_per_stud
        found = sh_.holes(r[::-1], m[::-1], mm_px)          # (row 0 at the bottom: y up)
        n_ = m.shape[1]
        where = [f"{h['area_mm2']:g} mm2 at {100 * h['x_mm'][0] / (n_ * mm_px):.0f}-{100 * h['x_mm'][1] / (n_ * mm_px):.0f}% "
                 f"across, {100 * h['y_mm'][0] / (n_ * mm_px):.0f}-{100 * h['y_mm'][1] / (n_ * mm_px):.0f}% up"
                 for h in found[:3]]
        hole_check = rbx_critic._check(
            f"silhouette_holes_{view}", not found, where or "no hole: every place the reference shows is filled",
            "no place the reference shows is left open (20 mm2 after a 0.75 mm erosion)",
            f"{view} view: {'; '.join(where)} — the picture has the object there and the model leaves it open: fill it "
            f"with the part the picture shows (the diff picture {out.replace(chr(92), '/')}: red)",
            "error" if getattr(asset, "quality", "prop") in ("hero", "aaa") else "warn")
    _save_pixels(diff, out)
    aspect_ratio = m_aspect / r_aspect if r_aspect else 1.0
    facts = {
        "reference": {"view": view, "iou": round(iou, 3), "aspect_model_vs_ref": round(aspect_ratio, 3), "diff": out.replace("\\", "/")},
    }
    if gap_check is not None:
        facts["reference"]["gaps"] = gaps
    facts["reference"]["flipped_iou"] = flips
    checks = []
    if relief is not None:
        facts["reference"]["depth"] = relief
        if "error" in relief:
            checks.append(rbx_critic._check(
                f"depth_{view}", False, relief["error"], "the photo's relief compared",
                f"{view} view: no relief compared - {relief['error']} (python kit/vision/depth_ref.py {ref_path})",
                "warn"))
        else:
            miss = [f"{w_['kind']} at {w_['across'][0]}-{w_['across'][1]}% across, {w_['up'][0]}-{w_['up'][1]}% up"
                    for w_ in relief.get("windows", [])[:3]]
            checks.append(rbx_critic._check(
                f"depth_{view}", relief["corr"] >= DEPTH_BAR,
                f"relief corr {relief['corr']:g} against the photo's ({relief.get('source')})"
                + (f"; {'; '.join(miss)}" if miss else ""),
                f"the model's relief runs with the photo's (corr >= {DEPTH_BAR:g})",
                f"{view} view: the steps and recesses inside the outline are not where the photo has them"
                + (f" ({'; '.join(miss)}: missing = the picture is recessed there and the model is not)" if miss
                   else "") + " - cut the recess / raise the panel the picture shows", "warn"))
    if opened is not None:
        facts["reference"]["openings"] = opened
        checks.append(rbx_critic._check(
            f"openings_{view}", opened["filled"] <= OPENING_FILLED_BAR,
            f"{100 * opened['filled']:.0f}% of the picture's see-through openings ({opened['reference']:g} "
            f"{opened['unit']}) covered solid; the openings match at IoU {opened['iou']:g}",
            f"the model keeps the openings the picture shows (at most {100 * OPENING_FILLED_BAR:.0f}% covered)",
            f"{view} view: the picture sees through there (a window, a guard's opening) and the model is solid - cut "
            f"or leave it open (the diff picture {out.replace(chr(92), '/')})", "warn"))
    if idmasks is not None and frame_studs > 0:
        m_xf = m_fit if m_fit is not None else _normalise_xf(model, m.shape[0])[2]
        pf, pc, psheet = part_match(asset, view, ref_path, parts, idmasks, m_xf, r_xf, m.shape[0],
                                    frame_studs * (getattr(asset, "mm_per_stud", None) or 1.0), renders)
        facts["reference"]["parts"] = pf
        if psheet:
            facts["reference"]["parts_sheet"] = psheet.replace("\\", "/")
        checks += pc
    flip, flip_iou = max(flips.items(), key=lambda kv: kv[1])
    if flip_iou >= max(iou + 0.15, 0.6):
        meaning = MIRROR_MEANING.get((view, flip), "it is flipped")
        checks.append(rbx_critic._check(
            f"reference_{view}_mirrored", False, {"as_is": round(iou, 3), flip: flip_iou}, "the reference as drawn fits best",
            f"the {view} reference fits {flip_iou:.0%} flipped {flip} against {iou:.0%} as drawn: {meaning} — find out "
            "which is right (the other views and the photos of the real thing) before shaping anything to this view; "
            "a chart drawn mirrored is traced again from its picture flipped", "warn"))
    region = f"{worst[0]}-{worst[1]}" if worst else "-"
    if worst:  # (where the outline is most off: the stage gate's next step names it)
        facts["reference"]["worst"] = f"{region} ({worst[2]})"
    checks.append(
        rbx_critic._check(
            f"reference_{view}",
            iou >= bar,
            round(iou, 3),
            bar,
            f"silhouette matches the {view} reference {iou:.0%}; biggest difference: {region} ({worst[2] if worst else ''}: "
            f"{'the reference has shape there, the model does not' if worst and worst[2] == 'missing' else 'the model sticks out there'}). "
            f"Width/height is {aspect_ratio:.2f}x the reference's. Diff image: red = missing, blue = extra",
            "warn",
        )
    )
    if gap_check is not None:
        checks.append(gap_check)
    if hole_check is not None:
        checks.append(hole_check)
    if abs(aspect_ratio - 1) > 0.15:
        checks.append(
            rbx_critic._check(
                f"reference_{view}_proportions",
                False,
                round(aspect_ratio, 3),
                "within 15%",
                f"the {view} silhouette is {'wider' if aspect_ratio > 1 else 'narrower'} than the reference by {abs(aspect_ratio - 1):.0%} "
                "(width/height) — fix proportions before details",
                "warn",
            )
        )
    if traced:
        # one global IoU hides a badly wrong REGION (0.93 overall with a mangled trigger guard): score the silhouette
        # in windows along the length (and top / bottom half), report the worst ones with where they are
        n_ = m.shape[0]
        ys_, xs_ = np.nonzero(r)
        ry0, ry1 = (ys_.min(), ys_.max() + 1) if len(ys_) else (0, n_)
        rx0, rx1 = (xs_.min(), xs_.max() + 1) if len(xs_) else (0, n_)
        # a TALL view (a long object's front / back): the windows run along its HEIGHT, split left / right on the object
        # itself — 40 strips across the square frame left its edges alone in their own strips, where 0.4 mm failed
        tall = (ry1 - ry0) > (rx1 - rx0)
        cols, rows = (2, 40) if tall else (40, 2)
        bad = []
        for ci in range(cols):
            if tall:
                xa, xb = rx0 + ci * (rx1 - rx0) // cols, rx0 + (ci + 1) * (rx1 - rx0) // cols
            else:
                xa, xb = ci * n_ // cols, (ci + 1) * n_ // cols
            for ri in range(rows):
                ya, yb = ry0 + ri * (ry1 - ry0) // rows, ry0 + (ri + 1) * (ry1 - ry0) // rows
                mw, rw = m[ya:yb, xa:xb], r[ya:yb, xa:xb]
                un = np.logical_or(mw, rw).sum()
                if un < (yb - ya) * (xb - xa) * 0.08:
                    continue  # mostly empty window: nothing to compare
                li = float(np.logical_and(mw, rw).sum() / un)
                if li < 0.8:
                    miss = int(np.logical_and(rw, ~mw).sum())
                    extra = int(np.logical_and(mw, ~rw).sum())
                    where = ((f"v {ri / rows:.3f}-{(ri + 1) / rows:.3f} from the top", "left" if ci == 0 else "right")
                             if tall else (f"u {ci / cols:.3f}-{(ci + 1) / cols:.3f}", "top" if ri == 0 else "bottom"))
                    bad.append((li, where[0], where[1], "missing" if miss >= extra else "extra"))
        bad.sort()
        facts["reference"]["local_worst"] = [f"{span} {half}: {li:.2f} ({kind})" for li, span, half, kind in bad[:6]]
        checks.append(
            rbx_critic._check(
                f"reference_{view}_local",
                not bad,
                facts["reference"]["local_worst"] or "every window >= 0.80",
                "every window >= 0.80",
                "the silhouette is right overall but WRONG LOCALLY: " + "; ".join(facts["reference"]["local_worst"][:4])
                + " (u = 0 back .. 1 front of the trace; 'missing' = the reference has shape there) — look at that "
                "window in the diff image beside the reference and rebuild that piece from its own traced shape",
                "error",
            )
        )
    return facts, checks, out
