"""game_fidelity.py — the `game_fidelity` gate of `kit optimize`: does the GAME version show what the master shows?

  blender -b <EXPORTS>/<name>_game.blend -P kit/blender/game_fidelity.py -- <EXPORTS>/<name>.blend <out_dir>
          [--swap <channel>=<png> ...]   (selftest: the game's map of that channel replaced by another picture)
          [--master-own-colour]          (the master is a HIGH, <name>_high.blend: its own colour; the albedo's median
                                          gates, its p95 is reported only - the low carries its baked shadow)
          [--mm <mm a stud>]             (the scene's scale, for the close-up pass's millimetres; 280 when not given)

Two pictures of each version, from the same 6 cameras (5 orthographic: front, back, left, right, top + one 3/4), framed
on the MASTER (512 px, transparent film, EEVEE, no light):
  albedo   its baked colour map, unlit (Emission 1, view transform Standard, sRGB 8 bit)
  normal   its world-space SHADING normal (the baked tangent normal map applied), as colour n * 0.5 + 0.5 (float)
Over the pixels both silhouettes cover (all 6 views together):
  albedo   |delta luma| (luma = mean of R, G, B, 0-255)    PASS: median <= 8 and 95th percentile <= 25
  normal   the angle between the two normals (degrees)     PASS: median <= 4 and 95th percentile <= 20
(the metrics and limits of experiments/exp2/fidelity.py + exp3/normal_fidelity.py: the master against itself scores
0; a game mesh with no normal map, or the old re-derived game bake, fails).

THE CLOSE-UP PASS (the owner, 2026-11-10: the car rim's S1 game version passed the numbers above - normal median 0.35 /
p95 3.4 degrees - with a sawtoothed lip, a bright slit where a spoke meets it, a lumpy bore and its lug threads only
painted into the normal map: at 512 px a whole rim is ~1.5 mm a pixel, so every fault was a pixel or less, pooled with
the open face). The same 6 cameras at CLOSE_MM_PX a pixel (0.25 mm; 512 to 2048 px), each version's shading normal and DEPTH along the camera, judged
in local WIN px windows - one global number hides a wrong region. A window is a FAULT where, on the same surface (the
two hits within SAME_MM along the pixel's ray), the shading normals part by over ANG_BAD degrees across FRAC_S of it
(a stair-stepped, striped or slit shading), or where across FRAC_G of it the game shows shape the master lacks or
lacks shape it has: its surface over GEO_MM off the master's (along the master's normal), a hit SAME_MM or more away
(a deep hole capped flat), or a surface only one of the two has (detail only painted on: threads, holes, rounds). The
depth is written split - (floor(t K) / K, frac(t K)), one sample a pixel - because EEVEE's film is half float. More than MAX_FAULTS fault
windows over the 6 views FAIL the high-and-low route (--master-own-colour); for any other game version they are
reported. The worst windows' crops (master | game shading normals) are kept in <out_dir>/close/ - look at them.

The verdict is the last JSON line; <out_dir>/game_fidelity.json keeps the numbers. Exit 0 = pass, 1 = fail."""

import glob
import json
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

VIEWS = ("front", "back", "left", "right", "top", "q34")
DIRS = {"front": (0, 1, 0), "back": (0, -1, 0), "left": (-1, 0, 0), "right": (1, 0, 0), "top": (0, 0.0001, 1),
        "q34": (0.8, 1, 0.55)}
RES = 512
LIMITS = {"albedo": (8.0, 25.0), "normal": (4.0, 20.0)}  # (median, p95): delta luma 0-255 / degrees
CLOSE_RES = 2048  # px at most: the car rim (a 525 mm frame) at 0.26 mm a pixel - a 1.5 mm round is 6 of them
CLOSE_MM_PX = 0.25  # mm a pixel the close-up looks at (what it was tuned on: the car rim, still 2048 px). A small model framed whole at
#                    CLOSE_RES was looked at far finer - a 112 mm plate at 0.05 mm a pixel, where a band a tenth of a
#                    millimetre wide along a crisp rim filled windows (card 3aan): the pixels follow the model's size
CLOSE_MIN = 512    # px at least (a tiny model still gets windows to judge)


def close_res(size, mm=280.0):
    """the close-up's pixels for a frame `size` studs across at `mm` a stud: CLOSE_MM_PX a pixel, CLOSE_MIN to
    CLOSE_RES, a whole number of windows"""
    want = float(size) * float(mm) / CLOSE_MM_PX
    px = int(round(max(CLOSE_MIN, min(CLOSE_RES, want)) / WIN)) * WIN
    return max(WIN, px)
WIN = 32  # px: a window (~12 mm on the rim)
ERODE = 2  # px taken off every silhouette edge (an edge pixel can hit either side)
SAME_MM = 4.0  # two hits further apart than this along their ray are two surfaces (an occlusion): never compared
ANG_BAD = 10.0  # degrees between the shading normals: a pixel that shades wrong
GEO_MM = 0.6  # mm off the master's surface, along its normal: a pixel whose shape is missing (painted on)
MIN_PX = 160  # px of a window compared before it is judged
FRAC_S = 0.08  # of a window's compared pixels shading wrong: a shading fault (a stair-step band is ~3 px of 32)
FRAC_G = 0.20  # of a window's compared pixels off the master's surface: a geometry fault
MAX_FAULTS = 3  # fault windows over the 6 views the high-and-low route allows (the rim's S1: dozens)
CROP = 96  # px of each worst window's crop (master | game)
AA_SAMPLES, AA_FILTER = 16, 1.5  # the close shading pass's anti-aliasing: the same for master and game, never the
#  files' own (two files saved with different samples would part at every crease)
DEPTH_SPAN = 3 ** 0.5  # frame sizes the depth spans (the frame's diagonal: t = dot / (size * span) + 0.5 is in 0..1)
DEPTH_K = 64  # the depth is written as floor(t * K) / K + frac(t * K): EEVEE's film is HALF float (a position
#  written whole was on its 2^-11 grid: 0.26 mm on the rim, 1.2 mm on an 8-stud piece - over GEO_MM); split, ~0.02 mm


def _objects(sc):
    objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and o.visible_get()]
    for o in sc.objects:
        if (o.type == "MESH" and o not in objs) or o.type in ("CAMERA", "LIGHT"):
            o.hide_render = True
    return objs


def _source(mat, socket):
    """the image node feeding the baked material's Principled <socket> (through its Normal Map for Normal) + its UV"""
    if not (mat and mat.use_nodes):
        return None, None
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None or not bsdf.inputs[socket].is_linked:
        return None, None
    n = bsdf.inputs[socket].links[0].from_node
    uv = None
    if n.type == "NORMAL_MAP":
        uv = n.uv_map or None
        n = n.inputs["Color"].links[0].from_node if n.inputs["Color"].is_linked else None
    if n is None or n.type != "TEX_IMAGE":
        return None, None
    if n.inputs["Vector"].is_linked and n.inputs["Vector"].links[0].from_node.type == "UVMAP":
        uv = n.inputs["Vector"].links[0].from_node.uv_map
    return n.image, uv


def _own_colour(m, name):
    """an unlit copy of material m showing its OWN Principled Base Color (its node graph, or its colour): a HIGH's
    procedural materials (the high-and-low route) — its colour was never baked"""
    em = m.copy()
    em.name = name
    nt = em.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    outn = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
    emis = nt.nodes.new("ShaderNodeEmission")
    if bsdf is not None and bsdf.inputs["Base Color"].is_linked:
        nt.links.new(bsdf.inputs["Base Color"].links[0].from_socket, emis.inputs["Color"])
    elif bsdf is not None:
        emis.inputs["Color"].default_value = bsdf.inputs["Base Color"].default_value
    else:
        emis.inputs["Color"].default_value = (1, 0, 1, 1)
    nt.links.new(emis.outputs["Emission"], outn.inputs["Surface"])
    return em


def _depth(ctr, size):
    """ONE unlit material for every object: the depth along the camera, t = (P - ctr) . forward / size + 0.5, written
    as (floor(t K) / K, frac(t K), 0) so EEVEE's half-float film keeps it to ~1e-5 of the frame (the close-up pass;
    _aim_depth sets the forward of each view)"""
    em = bpy.data.materials.new("gf_depth")
    em.use_nodes = True
    nt = em.node_tree
    nt.nodes.clear()
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    emis = nt.nodes.new("ShaderNodeEmission")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = tuple(ctr)
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.name = "gf_forward"
    t = nt.nodes.new("ShaderNodeMath")
    t.operation = "MULTIPLY_ADD"
    t.inputs[1].default_value = DEPTH_K / (size * DEPTH_SPAN)
    t.inputs[2].default_value = DEPTH_K * 0.5
    coarse = nt.nodes.new("ShaderNodeMath")
    coarse.operation = "FLOOR"
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "DIVIDE"
    scale.inputs[1].default_value = DEPTH_K
    fine = nt.nodes.new("ShaderNodeMath")
    fine.operation = "FRACT"
    rgb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(geo.outputs["Position"], sub.inputs[0])
    nt.links.new(sub.outputs["Vector"], dot.inputs[0])
    nt.links.new(dot.outputs["Value"], t.inputs[0])
    nt.links.new(t.outputs["Value"], coarse.inputs[0])
    nt.links.new(coarse.outputs["Value"], scale.inputs[0])
    nt.links.new(t.outputs["Value"], fine.inputs[0])
    nt.links.new(scale.outputs["Value"], rgb.inputs["X"])
    nt.links.new(fine.outputs["Value"], rgb.inputs["Y"])
    nt.links.new(rgb.outputs["Vector"], emis.inputs["Color"])
    nt.links.new(emis.outputs["Emission"], outn.inputs["Surface"])
    return em


def _aim_depth(mat, forward):
    mat.node_tree.nodes["gf_forward"].inputs[1].default_value = tuple(forward)


def _materials(objs, swap, own_colour=False, pos=None):
    """per object: its albedo material and its normal material (unlit emissions), + the shared depth material when
    pos = (ctr, size) -> {object: (albedo, normal, depth)}; own_colour: a material with no colour map shows its own Base
    Color (a HIGH's), never the magenta of a missing map"""
    loaded = {}

    def swapped(img, channel):
        path = swap.get(channel)
        if not path:
            return img
        if path not in loaded:
            loaded[path] = bpy.data.images.load(os.path.abspath(path), check_existing=False)
        return loaded[path]

    out = {}
    depth = _depth(*pos) if pos is not None else None
    for o in objs:
        sets = ([], [], [])
        for m in o.data.materials or [None]:
            for k, socket in enumerate(("Base Color", "Normal")):
                img, uv = _source(m, socket)
                img = swapped(img, "color" if k == 0 else "normal")
                if k == 0 and img is None and own_colour and m is not None and m.use_nodes:
                    sets[k].append(_own_colour(m, f"gf_{k}_{o.name}"))
                    continue
                em = bpy.data.materials.new(f"gf_{k}_{o.name}")
                em.use_nodes = True
                nt = em.node_tree
                nt.nodes.clear()
                outn = nt.nodes.new("ShaderNodeOutputMaterial")
                emis = nt.nodes.new("ShaderNodeEmission")
                nt.links.new(emis.outputs["Emission"], outn.inputs["Surface"])
                tex = None
                if img is not None:
                    tex = nt.nodes.new("ShaderNodeTexImage")
                    tex.image = img
                    img.colorspace_settings.name = "sRGB" if k == 0 else "Non-Color"
                    if uv:
                        uvn = nt.nodes.new("ShaderNodeUVMap")
                        uvn.uv_map = uv
                        nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
                if k == 0:
                    if tex is not None:
                        nt.links.new(tex.outputs["Color"], emis.inputs["Color"])
                    else:
                        emis.inputs["Color"].default_value = (1, 0, 1, 1)   # (no colour map: magenta, never grey)
                else:
                    mad = nt.nodes.new("ShaderNodeVectorMath")
                    mad.operation = "MULTIPLY_ADD"
                    mad.inputs[1].default_value = (0.5, 0.5, 0.5)
                    mad.inputs[2].default_value = (0.5, 0.5, 0.5)
                    if tex is not None:
                        nmap = nt.nodes.new("ShaderNodeNormalMap")
                        nmap.space = "TANGENT"
                        if uv:
                            nmap.uv_map = uv
                        nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
                        nt.links.new(nmap.outputs["Normal"], mad.inputs[0])
                    else:
                        geo = nt.nodes.new("ShaderNodeNewGeometry")
                        nt.links.new(geo.outputs["Normal"], mad.inputs[0])
                    nt.links.new(mad.outputs["Vector"], emis.inputs["Color"])
                sets[k].append(em)
        if depth is not None:
            sets[2].extend([depth] * len(sets[0]))
        out[o.name] = sets
    return out


def _use(objs, mats, k):
    for o in objs:
        o.data.materials.clear()
        for m in mats[o.name][k]:
            o.data.materials.append(m)


def _load(path):
    """a rendered picture -> RGBA float array (rows bottom-up, as Blender keeps them); an 8-bit PNG reads back as its
    bytes / 255"""
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    px = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    return px.reshape(h, w, 4)


def frame(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return (lo + hi) / 2, max(hi - lo) * 1.12


def render(out, ctr, size, swap=None, own_colour=False, close=None, close_px=CLOSE_RES):
    """the open scene -> {view: (albedo RGBA 0-255 float, normal RGBA float)}; pictures kept in out/. close(view,
    (normal, depth)): the close-up pass, called per view at CLOSE_RES (its EXRs removed once read)"""
    sc = bpy.context.scene
    objs = _objects(sc)
    mats = _materials(objs, swap or {}, own_colour, pos=(ctr, size) if close else None)
    cam = bpy.data.objects.new("gf_cam", bpy.data.cameras.new("gf_cam"))
    sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = size
    cam.data.clip_end = size * 20
    sc.camera = cam
    r = sc.render
    r.resolution_x = r.resolution_y = RES
    r.resolution_percentage = 100
    r.film_transparent = True
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    r.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    vs = sc.view_settings
    vs.view_transform, vs.look, vs.exposure, vs.gamma = "Standard", "None", 0.0, 1.0
    sc.display_settings.display_device = "sRGB"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("gf_world")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0, 0, 0, 1)
        bg.inputs[1].default_value = 0.0
    for attr in ("use_gtao", "use_bloom", "use_ssr", "use_motion_blur"):
        if hasattr(sc.eevee, attr):
            setattr(sc.eevee, attr, False)
    os.makedirs(out, exist_ok=True)

    def aim(v):
        d = Vector(DIRS[v]).normalized()
        fwd = -d
        upw = Vector((0, 1, 0)) if v == "top" else Vector((0, 0, 1))
        right = fwd.cross(upw).normalized()
        up = right.cross(fwd).normalized()
        cam.matrix_world = Matrix.Translation(ctr + d * size * 4) @ Matrix((
            (right.x, up.x, -fwd.x, 0), (right.y, up.y, -fwd.y, 0), (right.z, up.z, -fwd.z, 0), (0, 0, 0, 1)))

    def shoot(k, path, fmt, depth):
        _use(objs, mats, k)
        r.image_settings.file_format = fmt
        r.image_settings.color_mode = "RGBA"
        r.image_settings.color_depth = depth
        r.filepath = path
        bpy.ops.render.render(write_still=True)
        return _load(path)

    pics = {}
    for v in VIEWS:
        aim(v)
        got = []
        for k, (fmt, depth, ext) in enumerate((("PNG", "8", "png"), ("OPEN_EXR", "32", "exr"))):
            px = shoot(k, os.path.join(out, f"{('albedo', 'normal')[k]}_{v}.{ext}"), fmt, depth)
            got.append(px * 255 if k == 0 else px)
        pics[v] = tuple(got)
    if close is not None:
        # the shading normal as the game shows it, anti-aliased the same for both files (AA_SAMPLES / AA_FILTER); the
        # depth at ONE sample a pixel, no pixel filter - an averaged depth across a band edge or a silhouette is no depth
        kept = {"samples": getattr(sc.eevee, "taa_render_samples", None), "filter": getattr(r, "filter_size", None)}

        def exact(on, restore=False):
            if kept["samples"] is not None:
                sc.eevee.taa_render_samples = kept["samples"] if restore else 1 if on else AA_SAMPLES
            if kept["filter"] is not None:
                try:
                    r.filter_size = kept["filter"] if restore else 0.0 if on else AA_FILTER
                except (TypeError, ValueError):
                    pass

        r.resolution_x = r.resolution_y = int(close_px)
        depth = mats[objs[0].name][2][0] if objs and mats[objs[0].name][2] else None
        for v in VIEWS:
            aim(v)
            if depth is not None:
                _aim_depth(depth, -Vector(DIRS[v]).normalized())
            got = []
            for k, name in ((1, "normal"), (2, "depth")):
                exact(k == 2)
                path = os.path.join(out, f"close_{name}_{v}.exr")
                got.append(shoot(k, path, "OPEN_EXR", "32"))
                os.remove(path)  # (64 MB each: the numbers are kept, never the picture)
            close(v, tuple(got))
        exact(False, restore=True)
        r.resolution_x = r.resolution_y = RES
    return pics


def compare(master, game):
    """{view: (albedo, normal)} x 2 -> {"albedo": {...}, "normal": {...}} (pure numpy: kit/test/python)"""
    dl, ang = [], []
    for v in VIEWS:
        (aa, an), (ba, bn) = master[v], game[v]
        m = (aa[..., 3] > 127) & (ba[..., 3] > 127)
        dl.append(np.abs(aa[..., :3].mean(2)[m] - ba[..., :3].mean(2)[m]))
        m = (an[..., 3] > 0.5) & (bn[..., 3] > 0.5)
        na, nb = an[..., :3][m] * 2 - 1, bn[..., :3][m] * 2 - 1
        na /= np.maximum(np.linalg.norm(na, axis=1, keepdims=True), 1e-8)
        nb /= np.maximum(np.linalg.norm(nb, axis=1, keepdims=True), 1e-8)
        ang.append(np.degrees(np.arccos(np.clip((na * nb).sum(1), -1, 1))))
    out = {}
    for key, vals in (("albedo", np.concatenate(dl)), ("normal", np.concatenate(ang))):
        med, p95 = (round(float(np.median(vals)), 2), round(float(np.percentile(vals, 95)), 2)) if len(vals) else (None, None)
        lim = LIMITS[key]
        out[key] = {"pixels": int(len(vals)), "median": med, "p95": p95, "limit": {"median": lim[0], "p95": lim[1]},
                    "pass": bool(len(vals)) and med <= lim[0] and p95 <= lim[1]}
    return out


def _erode(mask, k):
    """mask with k pixels taken off every edge (4-neighbour)"""
    for _ in range(k):
        e = mask.copy()
        e[1:, :] &= mask[:-1, :]
        e[:-1, :] &= mask[1:, :]
        e[:, 1:] &= mask[:, :-1]
        e[:, :-1] &= mask[:, 1:]
        mask = e
    return mask


def compare_close(master, game, size, mm=280.0, forward=(0.0, 0.0, -1.0)):
    """one view of the close-up pass (pure numpy: kit/test/python): master / game = (normal RGBA, depth RGBA) float
    pictures at the same size - the depth along the camera written (floor(t K) / K, frac(t K)) with t in frame sizes
    (size studs, mm a stud), forward the camera's -> {compared, judged, faults, shading, geometry, p99_deg, windows:
    [(row, col, kind, share)], worst shares}. A window (WIN px) is a SHADING fault where, on the same surface (both hits
    within SAME_MM along the ray), over FRAC_S of its pixels part from the master's normal by > ANG_BAD; a GEOMETRY fault
    where over FRAC_G of its pixels show shape the game lacks or adds: > GEO_MM off the master's surface (along its
    normal), a hit SAME_MM or more away (a deep hole capped flat), or a surface only one of the two has"""
    (mn, mp), (gn, gp) = master, game
    am, ag = mn[..., 3] > 0.5, gn[..., 3] > 0.5
    em, eg = _erode(am, ERODE), _erode(ag, ERODE)
    cover = em & eg
    one = (em & ~ag) | (eg & ~am)  # (a surface only one has, ERODE px inside its own silhouette)
    na = mn[..., :3].astype(np.float32) * 2 - 1
    nb = gn[..., :3].astype(np.float32) * 2 - 1
    na /= np.maximum(np.linalg.norm(na, axis=2, keepdims=True), 1e-8)
    nb /= np.maximum(np.linalg.norm(nb, axis=2, keepdims=True), 1e-8)
    ang = np.degrees(np.arccos(np.clip((na * nb).sum(2), -1, 1)))
    tm = mp[..., 0].astype(np.float64) + mp[..., 1].astype(np.float64) / DEPTH_K
    tg = gp[..., 0].astype(np.float64) + gp[..., 1].astype(np.float64) / DEPTH_K
    dist = np.abs(tg - tm) * (size * DEPTH_SPAN * mm)  # mm along the pixel's ray (orthographic: one ray, both hits)
    fwd = np.asarray(forward, np.float32)
    fwd = fwd / max(float(np.linalg.norm(fwd)), 1e-8)
    sep = dist * np.abs(na @ fwd)  # mm off the master's surface, along its normal
    same = cover & (dist < SAME_MM)
    bad_s = same & (ang > ANG_BAD)
    bad_g = (same & (sep > GEO_MM)) | (cover & ~same) | one
    h, w = am.shape[0] // WIN, am.shape[1] // WIN

    def tiles(x):
        return x[:h * WIN, :w * WIN].reshape(h, WIN, w, WIN).sum(axis=(1, 3))

    n_s, n_g = tiles(same), tiles(cover | one)
    fs, fg = tiles(bad_s) / np.maximum(n_s, 1), tiles(bad_g) / np.maximum(n_g, 1)
    fault_s = (n_s >= MIN_PX) & (fs >= FRAC_S)
    fault_g = (n_g >= MIN_PX) & (fg >= FRAC_G)
    judged = (n_s >= MIN_PX) | (n_g >= MIN_PX)
    wins = [(int(r), int(c), "shading", round(float(fs[r, c]), 3)) for r, c in np.argwhere(fault_s)]
    wins += [(int(r), int(c), "geometry", round(float(fg[r, c]), 3)) for r, c in np.argwhere(fault_g & ~fault_s)]
    wins.sort(key=lambda x: -x[3])
    return {"compared": int(same.sum()), "judged": int(judged.sum()), "faults": int((fault_s | fault_g).sum()),
            "shading": int(fault_s.sum()), "geometry": int(fault_g.sum()),
            "p99_deg": round(float(np.percentile(ang[same], 99)), 2) if same.any() else None,
            "worst_shading": round(float(fs[n_s >= MIN_PX].max()), 3) if (n_s >= MIN_PX).any() else 0.0,
            "worst_geometry": round(float(fg[n_g >= MIN_PX].max()), 3) if (n_g >= MIN_PX).any() else 0.0,
            "windows": wins}


def close_verdict(views, res=CLOSE_RES, mm_px=None):
    """the close-up pass over all views -> {faults, limit, pass, views}"""
    faults = sum(v["faults"] for v in views.values())
    return {"res": int(res), **({"mm_a_px": round(float(mm_px), 3)} if mm_px else {}), "window_px": WIN, "faults": faults, "limit": MAX_FAULTS, "pass": faults <= MAX_FAULTS,
            "views": views}


def verdict(res, own_colour=False):
    """compare()'s result -> (pass, the measures that failed). Against a master in its OWN colour (a HIGH: the
    high-and-low route) the albedo's median still gates — most of a surface is open, so a wrong colour map shows there
    (the car rim with another map swapped in: median 105) — and its p95 is reported only: the low's colour carries its
    baked crevice shadow, the high's own colour none (the rim: median 0.33, p95 32). The close-up pass (res["close"])
    gates the high-and-low route; any other game version's is reported"""
    a, n = res["albedo"], res["normal"]
    a_ok = a["pass"] if not own_colour else (bool(a["pixels"]) and a["median"] is not None
                                             and a["median"] <= a["limit"]["median"])
    c = res.get("close")
    c_ok = not own_colour or c is None or c["pass"]
    bad = [k for k, ok in (("albedo", a_ok), ("normal", n["pass"]), ("close-up", c_ok)) if not ok]
    return not bad, bad


def _save_crop(path, a, b, row, col):
    """a worst window's crop: the master's shading normals | the game's (rows bottom-up, as rendered)"""
    H, W = a.shape[:2]
    cy, cx = row * WIN + WIN // 2, col * WIN + WIN // 2
    y0, x0 = max(0, min(H - CROP, cy - CROP // 2)), max(0, min(W - CROP, cx - CROP // 2))
    img = np.ones((CROP, CROP * 2 + 4, 4), np.float32)
    img[:, :CROP, :3] = a[y0:y0 + CROP, x0:x0 + CROP, :3]
    img[:, CROP + 4:, :3] = b[y0:y0 + CROP, x0:x0 + CROP, :3]
    im = bpy.data.images.new("gf_crop", CROP * 2 + 4, CROP, alpha=True)
    im.pixels.foreach_set(img.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def main(argv):
    master_blend, out = argv[0], os.path.abspath(argv[1])
    swap = {}
    if "--swap" in argv:   # channel=png pairs, up to the next --flag (--master-own-colour may follow)
        for a in argv[argv.index("--swap") + 1:]:
            if a.startswith("--"):
                break
            k, v = a.split("=", 1)
            swap[k] = v
    mm = 280.0
    if "--mm" in argv and argv.index("--mm") + 1 < len(argv):
        try:
            mm = float(argv[argv.index("--mm") + 1]) or 280.0
        except ValueError:
            pass
    game_blend = bpy.data.filepath
    name = os.path.splitext(os.path.basename(game_blend))[0]
    if not os.path.isfile(master_blend):
        print(json.dumps({"status": "fail", "summary": f"game_fidelity: no master build {master_blend}",
                          "next_action": "build the master first (lune run kit asset <name>), then kit optimize"}))
        return 1
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(master_blend))
    ctr, size = frame(_objects(bpy.context.scene))
    # --master-own-colour: the master is a HIGH (the high-and-low route, <name>_high.blend): its colour is its own
    # materials', never baked; the game version must still show baked maps (no map: magenta, as ever)
    own = "--master-own-colour" in argv
    close_dir = os.path.join(out, "close")
    os.makedirs(close_dir, exist_ok=True)
    for old in glob.glob(os.path.join(close_dir, "*.png")):
        os.remove(old)
    held = {}  # (the master's close-up pass, held for the game's: normals at half precision, depths full)

    def keep(v, got):
        held[v] = (got[0].astype(np.float16), got[1])

    px_ = close_res(size, mm)   # (the close-up at the model's own scale: CLOSE_MM_PX a pixel - card 3aan)
    master = render(os.path.join(out, "master"), ctr, size, own_colour=own, close=keep, close_px=px_)
    bpy.ops.wm.open_mainfile(filepath=game_blend)
    views, worst = {}, []

    def judge(v, got):
        m = held.pop(v)
        m = (m[0].astype(np.float32), m[1])
        st = compare_close(m, got, size, mm, tuple(-Vector(DIRS[v]).normalized()))
        for r_, c_, kind, share in st["windows"][:2]:
            crop = os.path.join(close_dir, f"{v}_{kind}_{r_}_{c_}.png")
            _save_crop(crop, m[0], got[0], r_, c_)
            worst.append({"view": v, "x": c_ * WIN + WIN // 2, "y": px_ - 1 - (r_ * WIN + WIN // 2),
                          "kind": kind, "share": share, "crop": crop})
        st["windows"] = st["windows"][:12]
        views[v] = st

    game = render(os.path.join(out, "game"), ctr, size, swap, close=judge, close_px=px_)
    res = compare(master, game)
    res["close"] = {**close_verdict(views, px_, float(size) * mm / px_), "gates": own, "mm_a_stud": mm,
                    "worst": sorted(worst, key=lambda w: -w["share"])[:8]}
    ok, bad = verdict(res, own)
    a, n, c = res["albedo"], res["normal"], res["close"]
    summary = (f"game_fidelity {name}: albedo |dluma| median {a['median']} / p95 {a['p95']} "
               f"({'<= 8; the p95 reported only: the low carries its baked shadow' if own else '<= 8 / 25'}), normal "
               f"median {n['median']} / p95 {n['p95']} deg (<= 4 / 20), close-up {c['faults']} fault window(s) at "
               f"{px_} px, {float(size) * mm / px_:.2f} mm a pixel ({'<= ' + str(MAX_FAULTS) if own else 'reported only'}) - "
               f"{'PASS' if ok else 'FAIL (' + ', '.join(bad) + ')'}")
    with open(os.path.join(out, "game_fidelity.json"), "w", encoding="utf-8") as fh:
        json.dump({"game": name, "master": os.path.basename(master_blend), "swap": swap, "own_colour": own, **res,
                   "pass": ok}, fh, indent=1)
    look = (f"; LOOK at the worst windows (master | game shading normals): "
            f"{', '.join(w['crop'] for w in c['worst'][:4])}") if c["worst"] else ""
    print(json.dumps({"status": "pass" if ok else "fail", "summary": summary, "game_fidelity": res,
                      "next_action": "none - the game version shows the master's maps" if ok else
                      f"the game version's {' and '.join(bad)} differ from the master's (pictures: {out}){look} - " +
                      (f"the low's maps and shape must carry its high there: look at the pictures, then rebuild "
                       f"(lune run kit asset {name})" if own else
                       "its maps must be the master's own, transferred: rebuild the master, then lune run kit optimize "
                       "again")}))
    return 0 if ok else 1


if __name__ == "__main__":
    code = main(sys.argv[sys.argv.index("--") + 1:])
    sys.stdout.flush()
    os._exit(code)
