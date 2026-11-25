"""inspect_model.py — LOOK INSIDE a reference model (Blender, headless): not only its outside (kit/refs/measure.py) but
every part — its real size along its own axes, volume, through-holes, what kind of part it is, what it touches, its
material (colour, metalness, roughness read from its textures under ITS OWN UVs), and — when the model is an assembly
animation — the order and the direction each part goes in and comes out: a real take-apart, from the model's author.

    blender -b --factory-startup --python-exit-code 2 -P kit/refs/inspect_model.py -- <model | library uid>
        --name <name> [--length-mm L | --height-mm H] [--front min] [--only a,b] [--skip a,b] [--frame N] [--part <words>] [--px 400]
        [--all-parts]   (also the pieces lying apart: a display's spare parts, its loose rounds)
    (lune run kit library inspect ...: then kit/refs/inspect_sheet.py draws the labelled sheets)

  -> refs/<name>.inspect.json        {size_mm, parts: [...], contacts, motion: {assembly_order, takeapart_order}, ...}
  -> build/library/<name>/parts/NN_<part>.png   each part ALONE from its broadest side (its material colour)
  -> build/library/<name>/assembled.png, exploded.png   the object from the front-right, whole and pulled apart
  -> build/library/<name>/part_<part>_<view>.png        --part: that part from side / top / front / 3-4 at a known
     mm per pixel (orthographic, no camera error: a part reference to trace and build FROM)

A part (in the model frame, like refs measure: width x height x length, the front = the length's max end):
  size_mm      its box in the model's directions;  own_mm: its size along its OWN axes (long, mid, short) — a slanted
               part's real length; long_axis: which way its long side runs
  volume_mm3 / closed / shells / holes: for a closed (watertight) shell, holes = its genus = through-holes (a pin's
               hole, a trigger guard's opening); an open mesh says closed: false and holes: null (unknown)
  kind         pin / rod / spring / plate / block — from its own proportions and fill (a guess: LOOK at its tile)
  material     per slot: base colour (sRGB hex, the texture averaged under this part's own UVs), metallic, roughness
  touches      the parts it touches or sits in (BVH: overlap, or nearer than 0.3 mm)
  motion       animated: when it leaves / arrives, how far, and the direction it first moves (its way out)
"""

import json
import math
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dissect  # noqa: E402  (what each part is made of: edges, bevels, surface, UV, detail, wear)
import measure  # noqa: E402  (its loader: staging left out, the assembled frame, real size, the front)

REPO = measure.REPO
LIBRARY = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "library")
TOUCH_MM = 0.3


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    model = argv[0] if argv and not argv[0].startswith("--") else None
    opt = {"name": None, "build": os.environ.get("KIT_BUILD", "build"), "out": "refs", "length-mm": None, "height-mm": None,
           "frame": None, "only": None, "skip": None, "front": "max", "axis": "auto", "part": None, "px": "400", "all-parts": None}
    for i, a in enumerate(argv):
        if a == "--all-parts":
            opt["all-parts"] = True
        elif a.startswith("--") and i + 1 < len(argv) and a[2:] in opt:
            opt[a[2:]] = argv[i + 1]
    return model, opt


def resolve(model):
    """a file, or a library uid (kit library get) -> its downloaded glTF"""
    if model and os.path.isfile(model):
        return model
    if model and re.fullmatch(r"[0-9a-f]{32}", model):
        folder = os.path.join(LIBRARY, model)
        for root, _, files in os.walk(folder):
            for f in sorted(files):
                if f.lower().endswith((".glb", ".gltf")):
                    return os.path.join(root, f)
    return None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "part"


# ---------------------------------------------------------------- one part's geometry
def part_mesh(o):
    """the part in world space (metres), welded: a game mesh is split at UV seams / hard edges, which would make every
    face its own open shell"""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(deps)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    ev.to_mesh_clear()
    bm.transform(o.matrix_world)
    if bm.verts:
        lo, hi, ext = measure._bounds(bm)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=max(1e-7, 1e-5 * max(ext)))
    return bm


def topology(bm):
    """-> (closed, shells, holes): holes = the genus of the closed shells (through-holes), None when any is open"""
    bm.verts.index_update()
    up = {v.index: v.index for v in bm.verts}

    def root(i):
        while up[i] != i:
            up[i] = up[up[i]]
            i = up[i]
        return i

    for e in bm.edges:
        a, b = root(e.verts[0].index), root(e.verts[1].index)
        if a != b:
            up[a] = b
    shells = {}
    for v in bm.verts:
        shells.setdefault(root(v.index), [0, 0, 0, True])[0] += 1
    for e in bm.edges:
        s = shells[root(e.verts[0].index)]
        s[1] += 1
        if len(e.link_faces) != 2:
            s[3] = False
    for f in bm.faces:
        shells[root(f.verts[0].index)][2] += 1
    shells = [s for s in shells.values() if s[2] > 0]
    closed = bool(shells) and all(s[3] for s in shells)
    holes = sum(max(0, (2 - (v - e + f)) // 2) for v, e, f, _ in shells) if closed else None
    return closed, len(shells), holes


def own_axes(pts):
    """PCA: -> (extents long/mid/short in metres, the long axis' direction, the short axis' direction)"""
    c = pts.mean(axis=0)
    w, vec = np.linalg.eigh(np.cov((pts - c).T) if len(pts) > 3 else np.eye(3))
    vec = vec[:, np.argsort(w)[::-1]]
    proj = (pts - c) @ vec
    ext = proj.max(axis=0) - proj.min(axis=0)
    return ext, Vector(vec[:, 0]), Vector(vec[:, 2])


def kind_of(own, volume, holes, area):
    """a GUESS from proportions (LOOK at its tile): spring = a closed wire coil (little metal in a long round box, its
    wire thin, nothing through it: a bushing or a guide is a hollow tube, holes 1); pin / rod = solid and round; flat =
    one side far thinner than the others"""
    L, M, S = (max(x, 1e-9) for x in own)
    fill = volume / (L * M * S) if volume else None
    wire = 4 * volume / area if volume and area else None  # a tube's wire diameter is ~4 V / A
    if fill is not None and holes == 0 and fill < 0.25 and L > 1.8 * M and S / M > 0.5 and wire < 0.25 * M:
        return "spring"
    if M / L < 0.45 and S / M > 0.75 and (fill is None or fill > 0.5):
        if L < 0.045:
            return "pin"
        if M / L < 0.25:
            return "rod"
    if S / M < 0.25:
        return "flat"
    return "block"


# ---------------------------------------------------------------- materials
def _srgb(c):
    return [(12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055) for x in c]


def _linear(c):
    return [(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c]


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(x * 255))):02x}" for x in rgb[:3])


_SMALL = {}


def _small(img, n=256):
    """the image at n x n as a numpy array (h, w, 4) — cached; a 4K texture is never read whole"""
    key = (img.name, n)
    if key not in _SMALL:
        try:
            cp = img.copy()
            cp.scale(n, n)
            a = np.empty(n * n * 4, dtype=np.float32)
            cp.pixels.foreach_get(a)
            a = a.reshape(n, n, 4)
            bpy.data.images.remove(cp)
        except Exception:  # noqa: BLE001 — an unreadable image is reported as unread
            a = None
        _SMALL[key] = a
    return _SMALL[key]


def _role(node):
    """what an image texture feeds: ('Base Color' | 'Metallic' | 'Roughness' | 'Normal' | ..., channel or None)"""
    for link in node.outputs[0].links if node.outputs else []:
        to = link.to_node
        if to.type == "BSDF_PRINCIPLED":
            return link.to_socket.name, None
        if to.type == "NORMAL_MAP":
            return "Normal", None
        if to.type in ("SEPARATE_COLOR", "SEPARATE_RGB"):
            for ch, out in enumerate(to.outputs):
                for l2 in out.links:
                    if l2.to_node.type == "BSDF_PRINCIPLED":
                        return l2.to_socket.name, ch
        if to.type in ("MIX", "MIX_RGB", "GAMMA", "CURVE_RGB", "HUE_SAT"):  # a factor / tint between (MIX: its
            for out in to.outputs:                                          # colour result is not outputs[0])
                for l2 in out.links:
                    if l2.to_node.type == "BSDF_PRINCIPLED":
                        return l2.to_socket.name, None
    return None, None


def _uv_samples(o, slot_index, limit=4000):
    """UVs of this slot's faces (one corner per face, up to `limit`) — read in bulk: a scan has 100k+ faces"""
    me = o.data
    if not me.uv_layers or not me.polygons:
        return None
    n = len(me.polygons)
    mi, ls = np.empty(n, np.int32), np.empty(n, np.int32)
    me.polygons.foreach_get("material_index", mi)
    me.polygons.foreach_get("loop_start", ls)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    sel = ls[mi == slot_index]
    if not len(sel):
        return None
    return uv.reshape(-1, 2)[sel[:: max(1, len(sel) // limit)]]


def _biggest_map(o):
    """(width, height) of the biggest image any of the part's materials uses (the texture its density is read on)"""
    best = None
    for slot in o.material_slots:
        m = slot.material
        for n in (m.node_tree.nodes if m and m.node_tree else []):
            if n.type == "TEX_IMAGE" and n.image is not None and n.image.size[0] > 0:
                if best is None or n.image.size[0] * n.image.size[1] > best[0] * best[1]:
                    best = tuple(n.image.size)
    return best


def _maps(o):
    """the part's colour / roughness / metal images at 512 (cached), with the channel each is read from"""
    out = {}
    for slot in o.material_slots:
        m = slot.material
        for n in (m.node_tree.nodes if m and m.node_tree else []):
            if n.type != "TEX_IMAGE" or n.image is None:
                continue
            role, ch = _role(n)
            if role in ("Base Color", "Roughness", "Metallic") and role not in out:
                a = _small(n.image, 512)
                if a is not None:
                    out[role] = (a, ch)
    return out


def _normal_map(o):
    """the image the part's material feeds into its normal (the baked detail), or None"""
    for slot in o.material_slots:
        m = slot.material
        for n in (m.node_tree.nodes if m and m.node_tree else []):
            if n.type == "TEX_IMAGE" and n.image is not None and _role(n)[0] == "Normal":
                return n.image
    return None


def materials(o):
    out = []
    for si, slot in enumerate(o.material_slots):
        m = slot.material
        if m is None:
            continue
        f = {"name": m.name, "textured": [], "maps": {}}
        bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m.node_tree else None
        if bsdf is not None:
            for key, sock in (("base_srgb", "Base Color"), ("metallic", "Metallic"), ("roughness", "Roughness")):
                s = bsdf.inputs.get(sock)
                if s is not None and not s.is_linked:
                    v = s.default_value
                    f[key] = _hex(_srgb(list(v)[:3])) if key == "base_srgb" else round(float(v), 3)
        uvs = _uv_samples(o, si)
        for n in (m.node_tree.nodes if m.node_tree else []):
            if n.type != "TEX_IMAGE" or n.image is None:
                continue
            role, ch = _role(n)
            if role is None:
                continue
            f["textured"].append(role)
            f["maps"][role] = list(n.image.size)
            a = _small(n.image)
            if a is None or uvs is None or role == "Normal":
                continue
            h, w = a.shape[:2]
            px = a[np.clip(((uvs[:, 1] % 1.0) * (h - 1)).astype(int), 0, h - 1),
                   np.clip(((uvs[:, 0] % 1.0) * (w - 1)).astype(int), 0, w - 1)]
            mean = px.mean(axis=0)
            if role == "Base Color":
                # Image.pixels are the file's own values: an sRGB colour texture reads as sRGB already
                lin = n.image.colorspace_settings.name.lower() in ("non-color", "linear", "linear rec.709")
                f["base_srgb"] = _hex(_srgb(mean[:3]) if lin else mean[:3])
            elif role in ("Metallic", "Roughness"):
                f[role.lower()] = round(float(mean[ch] if ch is not None else mean[:3].mean()), 3)
        out.append(f)
    return out


# ---------------------------------------------------------------- rendering
def _setup(px):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.film_transparent = True
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_cavity = True
    sc.display.shading.cavity_type = "BOTH"
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    cam = bpy.data.objects.new("InspectCam", bpy.data.cameras.new("InspectCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    return cam


def _look(cam, centre, d, up, span, w_px, h_px, far):
    z = d.normalized()
    y = (up - up.dot(z) * z)
    y = y.normalized() if y.length > 1e-6 else (Vector((0, 1, 0)) - Vector((0, 1, 0)).dot(z) * z).normalized()
    x = y.cross(z)
    rot = Matrix((x, y, z)).transposed().to_4x4()
    cam.matrix_world = Matrix.Translation(centre + z * far) @ rot
    cam.data.ortho_scale = span
    cam.data.clip_end = far * 3
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w_px, h_px


def _fit(cam, objs, d, up, w_px, h_px, far):
    """aim at what is drawn and frame all of it: the parts' box corners on the picture plane"""
    z = d.normalized()
    y = (up - up.dot(z) * z).normalized()
    x = y.cross(z)
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    xs, ys, zs = [p.dot(x) for p in pts], [p.dot(y) for p in pts], [p.dot(z) for p in pts]
    mid = x * (min(xs) + max(xs)) / 2 + y * (min(ys) + max(ys)) / 2 + z * (min(zs) + max(zs)) / 2
    span = max(max(xs) - min(xs), (max(ys) - min(ys)) * w_px / h_px) * 1.06
    _look(cam, mid, d, up, span, w_px, h_px, far)


def _render(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def _only(objs, show):
    for o in objs:
        o.hide_render = o not in show


# ---------------------------------------------------------------- motion (an assembly / take-apart animation)
def motion(objs, frame, dirs, anchor):
    """every part's way in / out, RELATIVE TO THE ANCHOR (the biggest part, the frame): an animation that also moves
    or turns the whole object must not make every part 'move'"""
    acts = list(bpy.data.actions)
    if not acts or frame is None:
        return None
    f0 = int(math.floor(min(a.frame_range[0] for a in acts)))
    f1 = int(math.ceil(max(a.frame_range[1] for a in acts)))
    frames = sorted(set(range(f0, f1 + 1, max(1, (f1 - f0) // 400))) | {f1, frame})
    sc = bpy.context.scene

    def centres():  # in the anchor's own frame
        inv = anchor.matrix_world.inverted()
        return [inv @ (o.matrix_world @ (sum((Vector(c) for c in o.bound_box), Vector()) / 8)) for o in objs]

    track = []
    for f in frames:
        sc.frame_set(f)
        track.append(centres())
    sc.frame_set(frame)
    home = centres()
    to_world = anchor.matrix_world.to_3x3()  # an offset in the anchor's frame -> the model frame (real size)
    track = [[to_world @ c for c in row] for row in track]
    home = [to_world @ c for c in home]
    out = {}
    ia = frames.index(frame)
    for k, o in enumerate(objs):
        size = max(o.dimensions) * max(o.matrix_world.to_scale())  # world metres, like the offsets
        tol = max(0.0005, 0.02 * size)
        away = [(track[i][k] - home[k]).length > tol for i in range(len(frames))]
        if not any(away):
            continue
        far = max(range(len(frames)), key=lambda i: (track[i][k] - home[k]).length)
        rec = {"farthest_mm": round((track[far][k] - home[k]).length * 1000, 1)}
        before = [i for i in range(ia) if away[i]]
        after = [i for i in range(ia + 1, len(frames)) if away[i]]
        if before:  # arrives: the last away sample before the assembled frame
            i = before[-1]
            rec["arrives_frame"] = frames[min(i + 1, ia)]
            rec["comes_in_from"] = dirs((track[i][k] - home[k]).normalized())
        if after:  # leaves: the first away sample after it
            i = after[0]
            rec["leaves_frame"] = frames[i]
            rec["goes_out_toward"] = dirs((track[i][k] - home[k]).normalized())
        rec["_far"] = track[far][k] - home[k]
        out[o.name] = rec
    return out


# ---------------------------------------------------------------- the inspection
def main():
    model, opt = _args()
    path = resolve(model)
    if not path:
        return measure._emit("fail", f"inspect: no model file or library uid '{model}'",
                             "lune run kit library get <uid> first, or give a .glb / .gltf path")
    name = opt["name"] or slug(os.path.splitext(os.path.basename(path))[0])
    objs, dropped, frame = measure.load_object(path, opt)
    if not objs:
        return measure._emit("fail", f"inspect: nothing of {path} is left (no meshes, or all left out)",
                             "check the file in Blender; loosen --only / --skip")
    bm, lo, hi, ext, axis, scaled = measure.place(objs, opt)
    bm.free()
    w_axis = 1 - axis
    centre = (lo + hi) / 2
    length_dir = Vector((1, 0, 0)) if axis == 0 else Vector((0, 1, 0))
    side_dir = Vector((0, -1, 0)) if axis == 0 else Vector((1, 0, 0))  # the camera side of measure's side view
    up = Vector((0, 0, 1))

    def model_mm(v):  # a world vector -> [width, height, length] mm in the model frame
        return [round(v[w_axis] * 1000, 1), round(v.z * 1000, 1), round(v[axis] * 1000, 1)]

    def dirs(v):  # a direction in words: the strongest components, e.g. "back + down"
        words = []
        for comp, pos, neg in ((v[axis], "forward", "back"), (v.z, "up", "down"),
                               (v[w_axis] * (1 if side_dir[w_axis] > 0 else -1), "out to the right", "out to the left")):
            if abs(comp) > 0.35:
                words.append(pos if comp > 0 else neg)
        return " + ".join(words) or "mixed"

    px = int(opt["px"])
    out_dir = os.path.join(REPO, opt["build"], "library", name) if not os.path.isabs(opt["build"]) else \
        os.path.join(opt["build"], "library", name)
    parts, meshes, coords = [], {}, {}
    for o in objs:
        pbm = part_mesh(o)
        if not pbm.verts:
            pbm.free()
            continue
        plo, phi, pext = measure._bounds(pbm)
        closed, shells, holes = topology(pbm)
        vol = abs(pbm.calc_volume(signed=True)) if closed else None
        pts = np.array([v.co[:] for v in pbm.verts], dtype=np.float64)
        own, long_d, short_d = own_axes(pts)
        meshes[o.name], coords[o.name] = pbm, pts
        parts.append({
            "name": o.name, "size_mm": model_mm(pext), "centre_mm": model_mm((plo + phi) / 2 - centre),
            "own_mm": [round(x * 1000, 1) for x in own], "long_axis": dirs(long_d if long_d.dot(length_dir) >= 0 else -long_d),
            "volume_mm3": round(vol * 1e9, 1) if vol is not None else None, "closed": closed, "shells": shells,
            "holes": holes, "kind": kind_of(own, vol, holes, sum(f.calc_area() for f in pbm.faces)), "tris": sum(len(f.verts) - 2 for f in pbm.faces),
            "uv": bool(o.data.uv_layers), "material": materials(o), "touches": [], "edges": (ed := dissect.edges(pbm, max(own))), "surface": dissect.surface(pbm, ed),
            "uv_layout": dissect.uv_layout(pbm, _biggest_map(o)),
            "colour_wear": dissect.colour_wear(pbm, _maps(o)),
            "baked_detail": dissect.baked_detail(pbm, _normal_map(o), os.path.join(out_dir, "detail",
                                                                                    f"{slug(o.name)}_relief.png")),
            "_short": short_d, "_obj": o})
    # what touches what
    trees = {n: BVHTree.FromBMesh(b) for n, b in meshes.items()}
    boxes = {n: measure._bounds(b)[:2] for n, b in meshes.items()}
    tol = TOUCH_MM / 1000.0
    names = list(meshes)
    contacts = []
    for i, a in enumerate(names):
        alo, ahi = boxes[a]
        for b in names[i + 1:]:
            blo, bhi = boxes[b]
            if not all(alo[k] - tol <= bhi[k] and blo[k] - tol <= ahi[k] for k in range(3)):
                continue
            how = "overlap" if trees[a].overlap(trees[b]) else None
            if how is None:
                small, big = (a, b) if len(meshes[a].verts) <= len(meshes[b].verts) else (b, a)
                vs = coords[small]
                for co in vs[:: max(1, len(vs) // 400)]:
                    hit = trees[big].find_nearest(Vector(co.tolist()), tol)
                    if hit[0] is not None:
                        how = "touch"
                        break
            if how:
                contacts.append([a, b, how])
    by = {p["name"]: p for p in parts}
    for a, b, _ in contacts:
        by[a]["touches"].append(b)
        by[b]["touches"].append(a)
    anchor = max(parts, key=lambda p: p["own_mm"][0] * p["own_mm"][1] * p["own_mm"][2])["_obj"]
    moves = motion(objs, frame, dirs, anchor)
    for p in parts:
        if moves and p["name"] in moves:
            p["motion"] = {k: v for k, v in moves[p["name"]].items() if not k.startswith("_")}
    order = {}
    if moves:
        arr = sorted((m["arrives_frame"], n) for n, m in moves.items() if "arrives_frame" in m)
        lea = sorted((m["leaves_frame"], n) for n, m in moves.items() if "leaves_frame" in m)
        order["assembly_order"] = [n for _, n in arr]
        order["takeapart_order"] = [n for _, n in lea] if lea else [n for _, n in reversed(arr)]
        order["takeapart_from"] = "the animation" if lea else "the assembly, reversed"
        order["never_moves"] = [p["name"] for p in parts if p["name"] not in moves]
        order["relative_to"] = anchor.name
    # each part alone, from its broadest side, in its own colour
    for p in parts:
        for m in p["_obj"].material_slots:
            f = next((x for x in p["material"] if m.material and x["name"] == m.material.name), None)
            if f and f.get("base_srgb"):
                h = f["base_srgb"]
                m.material.diffuse_color = (*_linear([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]), 1.0)
    cam = _setup(px)
    parts.sort(key=lambda p: -(p["own_mm"][0] * p["own_mm"][1] * max(p["own_mm"][2], 0.1)))
    for i, p in enumerate(parts):
        o, d = p["_obj"], p.pop("_short")
        d = d if d.dot(side_dir) >= 0 else -d
        if abs(d.z) > 0.9:
            d = d if d.z > 0 else -d
        pup = up if abs(d.z) < 0.9 else length_dir
        b = meshes[o.name]
        pts = np.array([v.co[:] for v in b.verts])
        pc = Vector(((pts.min(0) + pts.max(0)) / 2).tolist())
        z = d.normalized()
        yv = (pup - pup.dot(z) * z).normalized()
        xv = yv.cross(z)
        rel = pts - np.array(pc[:])
        span = max(np.ptp(rel @ np.array(xv[:])), np.ptp(rel @ np.array(yv[:])), 1e-5) * 1.15
        _only(objs, {o})
        _look(cam, pc, d, pup, span, px, px, max(ext) * 4 + 1)
        tile = os.path.join(out_dir, "parts", f"{i + 1:02d}_{slug(o.name)}.png")
        _render(tile)
        p["tile"] = os.path.relpath(tile, REPO).replace("\\", "/")
        p["tile_mm_per_px"] = round(span * 1000 / px, 4)
    # the whole object, assembled and pulled apart, from the front-right
    _only(objs, set(objs))
    view = (side_dir + length_dir * 0.7 + up * 0.55).normalized()
    sc = bpy.context.scene
    if sc.world is None:
        sc.world = bpy.data.worlds.new("InspectWorld")
    sc.world.color = (0.16, 0.165, 0.18)  # the whole object on a neutral ground (the tiles stay see-through)
    sc.render.film_transparent = False
    _fit(cam, objs, view, up, 1400, 900, max(ext) * 6 + 1)
    shots = {"assembled": os.path.join(out_dir, "assembled.png")}
    _render(shots["assembled"])
    cap = 0.6 * max(ext)
    for p in parts:
        o = p["_obj"]
        far = moves.get(o.name, {}).get("_far") if moves else None
        pc = Vector([c / 1000 for c in p["centre_mm"]])
        world_c = Vector((0, 0, 0))
        world_c[w_axis], world_c.z, world_c[axis] = pc[0], pc[1], pc[2]
        want = far * 0.7 if far is not None else world_c * 0.9
        if want.length > cap:
            want = want.normalized() * cap
        p["_want"] = want
    for p in parts:  # a child moves with its parent: only the difference is its own
        o = p["_obj"]
        par = o.parent
        while par is not None and par.name not in by:
            par = par.parent
        delta = p["_want"] - (by[par.name]["_want"] if par is not None else Vector((0, 0, 0)))
        M = (o.parent.matrix_world @ o.matrix_parent_inverse) if o.parent else Matrix.Identity(4)
        o.delta_location = M.to_3x3().inverted() @ delta
    bpy.context.view_layer.update()
    _fit(cam, objs, view, up, 1400, 900, max(ext) * 8 + 1)
    shots["exploded"] = os.path.join(out_dir, "exploded.png")
    _render(shots["exploded"])
    sc.render.film_transparent = True
    for p in parts:
        p["_obj"].delta_location = (0, 0, 0)
    bpy.context.view_layer.update()
    # --part: one part from four sides at a known scale
    closeups = []
    if opt["part"]:
        for p in [p for p in parts if measure._named(p["_obj"], opt["part"])][:4]:
            o, b = p["_obj"], meshes[p["name"]]
            pts = np.array([v.co[:] for v in b.verts])
            pc = Vector(((pts.min(0) + pts.max(0)) / 2).tolist())
            pe = pts.max(0) - pts.min(0)
            _only(objs, {o})
            # from the side the part is ON: a left-side part (a 1911's thumb safety) shows its outside face
            on_left = (Vector(pc) - centre).dot(side_dir) < -0.002 * max(ext)
            sd, sname = (-side_dir, "side_from_left") if on_left else (side_dir, "side")
            tq = (sd + length_dir * 0.7 + up * 0.55).normalized()
            for vname, d, pup, faces in ((sname, sd, up, (axis, 2)), ("top", up, -length_dir, (w_axis, axis)),
                                          ("front", length_dir, up, (w_axis, 2)), ("three_quarter", tq, up, None)):
                span = max(pe) * 1.3 if faces is None else max(pe[faces[0]], pe[faces[1]]) * 1.15
                _look(cam, pc, d, pup, span, 800, 800, max(ext) * 4 + 1)
                img = os.path.join(out_dir, f"part_{slug(o.name)}_{vname}.png")
                _render(img)
                closeups.append({"part": p["name"], "view": vname, "image": os.path.relpath(img, REPO).replace("\\", "/"),
                                 "mm_per_px": round(span * 1000 / 800, 4)})
        _only(objs, set(objs))
    for p in parts:
        p.pop("_obj", None)
        p.pop("_want", None)
    for b in meshes.values():
        b.free()
    result = {"name": name, "source": path.replace("\\", "/"), "size_mm": model_mm(ext), "scaled_by": scaled,
              "front_was": opt["front"], "frame": frame, "dropped": dropped,
              "axes": {"size_mm / centre_mm": "width, height, length (the front = the length's max end)",
                       "centre_mm": "from the object's centre"},
              "parts": parts, "contacts": contacts, "motion": order or None,
              "renders": {k: os.path.relpath(v, REPO).replace("\\", "/") for k, v in shots.items()},
              "closeups": closeups}
    out_json = opt["out"] if os.path.isabs(opt["out"]) else os.path.join(REPO, opt["out"])
    os.makedirs(out_json, exist_ok=True)
    jpath = os.path.join(out_json, f"{name}.inspect.json")
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    w_mm, h_mm, l_mm = result["size_mm"]
    holed = sum(1 for p in parts if p["holes"])
    mv = f", {len(order.get('assembly_order', []) or order.get('takeapart_order', []))} part(s) move in the animation" \
        if order else ""
    return measure._emit(
        "pass", f"inspect {name}: {len(parts)} part(s), {l_mm:.0f} x {w_mm:.0f} x {h_mm:.0f} mm, {len(contacts)} contact(s),"
        f" {holed} part(s) with through-holes{mv}{f', left out {len(dropped)}' if dropped else ''}",
        f"LOOK at the parts sheet + the exploded view (build/library/{name}/), read refs/{name}.inspect.json; one part "
        f"up close: --part <words>", inspect=os.path.relpath(jpath, REPO).replace("\\", "/"))


if __name__ == "__main__":
    main()
