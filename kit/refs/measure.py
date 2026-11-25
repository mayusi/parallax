"""measure.py — MEASURE a 3D reference (Blender, headless): a real-scale model (a Poly Haven CC0 scan, any glTF / FBX /
OBJ) -> the numbers and outlines a build is made from.

    blender -b --factory-startup --python-exit-code 2 -P kit/refs/measure.py -- <model> --name <name>
        [--stations 24] [--axis auto|x|y] [--out refs] [--length-mm L] [--frame N] [--only a,b] [--skip a,b]
        [--front max|min] [--views all|side-left,side-right,top,front,rear] [--view-px-mm 6] [--cut L0..L1,H0..H1]
        (lune run kit refs measure <model> --name <name>)
  --length-mm: the model is NOT at real scale (a library model: its author's units) — scale it so its length is L mm
  --only / --skip: keep only / leave out the objects whose names contain one of these words (one part of a model)
  --front min: the model's front (a muzzle, a nose) is at the length's MIN end — LOOK at the side silhouette: its front
    must point RIGHT; a library model faces whichever way its author liked
  --cut: the SIZES (size_mm) without what lies in a box across the whole width — L0..L1 mm from the REAR (the
    length's min end, after --front), H0..H1 mm up from the bottom: a published size that goes OVER a protrusion
    (GLOCK's width over its slide stop levers) is measured without it. Recorded in the result ("cut", the vertices
    left out, "size_uncut_mm"); the sections, levels and silhouettes stay the whole model's
  --views: also the model's own SQUARE views, shaded (its textures, studio light, cavities) on white, at --view-px-mm
    (6) — orthographic, so no camera error: the views a photo set lacks (a gun's rear end-on, its top). Oriented like
    photographs: side-right, top and side-left show the length across (front to the right; side-left: to the left),
    front / rear end-on -> build/refs/<name>_<view>_view.png (a dossier picture: kit dossier add --kind drawing)

  A library model is often STAGED: a floor / backdrop plane (flat and as big as the rest) is left out by itself, and
  so is anything apart from the object (a tool, a prop: not touching the main group of parts); an ANIMATED one (an
  assembly / take-apart animation) is measured at its most-assembled frame — the most parts together, then the
  smallest box — unless --frame says which. All of it is reported, and so is every part's own size ("parts").

  -> refs/<name>.measure.json   {size_mm: [width, height, length], stations: [{u, rx_mm, ry_mm, off_mm, squareness}],
                                 masks: {side, front, top}} — real millimetres (the model's own metres x 1000)
  -> build/refs/<name>_<view>_mask.png   perspective-free silhouettes (side / front / top), traced next by
     kit/blender/trace.py into assets/models/<name>_<view>.trace.json (smooth curves) — references with NO camera
     error: what `a.carve(side=, top=, front=)` and `Asset(reference=...)` want.

Axes: the model stands on Blender's Z (glTF's +Y up). LENGTH = its longest horizontal extent (the X or Y axis, or
--axis), u = 0 .. 1 from that axis' minimum to its maximum; WIDTH = the other horizontal axis; HEIGHT = Z. The FRONT is the
length's max end (u = 1); the silhouettes are oriented like the kit's own views: side = front to the right, top =
front pointing down, front = seen from the front. A station
is the cross-section across the length at u: half-width rx, half-height ry, the section's centre offset (width, height)
from the model's centre line, and its squareness (2 = an ellipse, 4+ = a rounded box: the superellipse exponent with
the same fill — what rbx's a.loft(stations) takes).
"""

import json
import math
import os
import re
import sys

import bmesh
import bpy
from mathutils import Vector

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    model = argv[0] if argv and not argv[0].startswith("--") else None
    opt = {"name": None, "stations": 24, "axis": "auto", "build": os.environ.get("KIT_BUILD", "build"), "out": "refs",
           "length-mm": None, "height-mm": None, "frame": None, "only": None, "skip": None, "front": "max", "views": None,
           "view-px-mm": "6", "cut": None}
    for i, a in enumerate(argv):
        if a.startswith("--") and i + 1 < len(argv):
            key = a[2:]
            if key in opt:
                opt[key] = argv[i + 1]
    opt["stations"] = int(opt["stations"])
    return model, opt


def _emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


def _split_parts(objs):
    """a kit build's baked group -> one object per part (its "kit_part" face tag), the group itself removed"""
    import numpy as np  # noqa: PLC0415

    for obj in objs:
        attr = obj.data.attributes.get("kit_part")
        names = list(obj.get("kit_parts") or [])
        if attr is None or not names:
            continue
        idx = np.zeros(len(obj.data.polygons), np.int32)
        attr.data.foreach_get("value", idx)
        for i, nm in enumerate(names):
            if not (idx == i).any():
                continue
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            lay = bm.faces.layers.int.get("kit_part")
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] != i], context="FACES")
            me = bpy.data.meshes.new(nm)
            bm.to_mesh(me)
            bm.free()
            for m in obj.data.materials:
                me.materials.append(m)
            part = bpy.data.objects.new(nm, me)
            part.matrix_world = obj.matrix_world.copy()
            bpy.context.scene.collection.objects.link(part)
        bpy.data.objects.remove(obj)


def _import(path):
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".blend":
        # OUR OWN build's master (kit asset output) — its objects appended as data: no script in it runs (Blender runs
        # a .blend's scripts only when opened with auto-run). A DOWNLOADED .blend is never accepted by kit library get.
        # A baked group (one mesh, its faces tagged "kit_part", the names in obj["kit_parts"]) is split back into its
        # parts, like the assembly export (rbx_strip.export)
        if os.path.abspath(path).startswith(os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "library")):
            raise ValueError("measure: a downloaded .blend is never opened (it can carry scripts) — use its glTF")
        with bpy.data.libraries.load(os.path.abspath(path), link=False) as (src, dst):
            dst.objects = list(src.objects)
        for o in dst.objects:
            if o is not None:
                bpy.context.scene.collection.objects.link(o)
        _split_parts([o for o in dst.objects if o is not None and o.type == "MESH"])
    else:
        raise ValueError(f"measure: cannot read {ext} (glb / gltf / fbx / obj, or our own build's .blend)")
    return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]


def _world_box(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(p[i] for p in pts) for i in range(3))), Vector((max(p[i] for p in pts) for i in range(3))))


def _box_of(objs):
    boxes = [_world_box(o) for o in objs]
    return (Vector((min(b[0][i] for b in boxes) for i in range(3))),
            Vector((max(b[1][i] for b in boxes) for i in range(3))))


def _backdrops(objs):
    """a staged model's floor / backdrop: FLAT (thinner than 1% of its own size) and at least half as big as all the
    rest together — never part of the object (a decal or a thin plate is far smaller than the whole)"""
    out = []
    for o in objs:
        rest = [p for p in objs if p is not o and p not in out]
        if not rest:
            break
        lo, hi = _world_box(o)
        e, (rlo, rhi) = hi - lo, _box_of(rest)
        if min(e) < 0.01 * max(e) and max(e) >= 0.5 * max(rhi - rlo):
            out.append(o)
    return out


def _main_group(objs):
    """the OBJECT itself: the group of parts whose boxes touch (within 5% of the biggest part's size), the one with the
    most volume — a tool, a prop, or a part still flying in during an animation sits apart from it"""
    boxes = [_world_box(o) for o in objs]
    tol = 0.05 * max(max(hi - lo) for lo, hi in boxes)
    up = list(range(len(objs)))

    def root(i):
        while up[i] != i:
            up[i] = up[up[i]]
            i = up[i]
        return i

    for i, (alo, ahi) in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            blo, bhi = boxes[j]
            if all(alo[k] - tol <= bhi[k] and blo[k] - tol <= ahi[k] for k in range(3)):
                up[root(i)] = root(j)
    groups = {}
    for i, (lo, hi) in enumerate(boxes):
        e = hi - lo
        g = groups.setdefault(root(i), [0.0, []])
        g[0] += max(e.x, 1e-9) * max(e.y, 1e-9) * max(e.z, 1e-9)
        g[1].append(objs[i])
    return max(groups.values(), key=lambda g: g[0])[1]


def _assembled_frame(objs):
    """an ANIMATED model (an assembly / take-apart animation: its parts spread out at one end) is measured where it is
    most together — the frame with the most parts in the object's main group, then the smallest box (the earliest of
    equals). None: nothing is animated."""
    acts = list(bpy.data.actions)
    if not acts:
        return None
    f0 = int(math.floor(min(a.frame_range[0] for a in acts)))
    f1 = int(math.ceil(max(a.frame_range[1] for a in acts)))
    sc, best = bpy.context.scene, None
    for f in sorted(set(range(f0, f1 + 1, max(1, (f1 - f0) // 60))) | {f1}):
        sc.frame_set(f)
        main = _main_group(objs)
        lo, hi = _box_of(main)
        n, d = len(main), (hi - lo).length
        if best is None or n > best[0] or (n == best[0] and d < best[1] * (1 - 1e-6)):
            best = (n, d, f)
    sc.frame_set(best[2])
    return best[2]


def _tokens(name):
    """a part name's words: split at anything not a letter / digit and at camelCase ("Grip_SafetyLever" -> grip,
    safety, lever)"""
    return [t.lower() for t in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


def _named(o, words):
    """a word must START one of the name's words ("ring" is not "Spring"; "safety" finds "Grip_Safety" and
    "Safety_lock1"); a phrase ("grip safety") must start consecutive ones"""
    toks = _tokens(o.name)
    for w in (w.strip().lower() for w in words.split(",")):
        parts = re.findall(r"[a-z]+|\d+", w)
        if parts and any(all(i + k < len(toks) and toks[i + k].startswith(q) for k, q in enumerate(parts))
                         for i in range(len(toks))):
            return True
    return False


def _joined_mesh(objs):
    """every mesh of the model in world space, in one bmesh (triangulated)"""
    bm = bmesh.new()
    deps = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        ev.to_mesh_clear()
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    return bm


def _biggest_island(segments, eps):
    """the points of the biggest island of a slice's outline (biggest = the largest box): a slice through a grip also
    cuts the trigger guard and the magazine's foot — the grip is the one that matters. An island is CONNECTED by the
    outline's segments (each face crossing the plane gives one), points closer than eps being one point — not by
    nearness alone: a low-poly box's slice is only its 4 corners, far apart but one outline"""
    keys, pts, up = {}, [], []

    def pid(p):
        k = (round(p[0] / eps), round(p[1] / eps))
        if k not in keys:
            keys[k] = len(pts)
            pts.append(p)
            up.append(len(up))
        return keys[k]

    def root(i):
        while up[i] != i:
            up[i] = up[up[i]]
            i = up[i]
        return i

    for seg in segments:
        ids = [pid(p) for p in seg]
        for j in ids[1:]:
            a, b = root(ids[0]), root(j)
            if a != b:
                up[a] = b
    groups = {}
    for i in range(len(pts)):
        groups.setdefault(root(i), []).append(pts[i])

    def box_area(g):
        xs, ys = [p[0] for p in g], [p[1] for p in g]
        return (max(xs) - min(xs)) * (max(ys) - min(ys))

    return max(groups.values(), key=box_area) if groups else []


def levels(bm, lo, hi, axis, w_axis, fracs=None):
    """HORIZONTAL slices of the object at fractions of its height: the biggest island's width (across), depth (along
    the length), roundness (squareness: 2 = an ellipse, 4+ = a rounded box) and centre — what a grip that WRAPS around
    is built from (cad_parts.loft_sections) and checked against (a.section_match)"""
    fracs = fracs or [round(0.05 * k, 2) for k in range(1, 20)]
    faces = []
    for f in bm.faces:
        vs = [v.co.copy() for v in f.verts]
        zs = [v.z for v in vs]
        faces.append((min(zs), max(zs), vs))
    ext = hi - lo
    eps = 1e-5 * max(ext)  # (a crossing shared by two faces: one point)
    out = []
    for fr in fracs:
        z = lo.z + fr * ext.z
        segs = []
        for z0, z1, vs in faces:
            if not (z0 <= z <= z1):
                continue
            ds = [v.z - z for v in vs]
            seg = []
            for i in range(len(vs)):
                a, b = vs[i], vs[(i + 1) % len(vs)]
                da, db = ds[i], ds[(i + 1) % len(vs)]
                if (da < 0) != (db < 0):
                    p = a.lerp(b, da / (da - db))
                    seg.append((p[w_axis], p[axis]))
            if len(seg) >= 2:
                segs.append(seg)
        isle = _biggest_island(segs, eps)
        if len(isle) < 3:
            continue
        ws, ls = [p[0] for p in isle], [p[1] for p in isle]
        rw, rl = (max(ws) - min(ws)) / 2, (max(ls) - min(ls)) / 2
        if rw <= 0 or rl <= 0:
            continue
        fill = _hull_area(isle) / (4 * rw * rl)
        out.append({"h": fr, "width_mm": round(2 * rw * 1000, 1), "depth_mm": round(2 * rl * 1000, 1),
                    "fill": round(fill, 3), "squareness": superellipse_n(fill),
                    "centre_mm": [round(((max(ws) + min(ws)) / 2 - (lo[w_axis] + ext[w_axis] / 2)) * 1000, 1),
                                  round(((max(ls) + min(ls)) / 2 - lo[axis]) * 1000, 1)]})
    return out


def superellipse_n(fill):
    """the exponent n whose superellipse |x/a|^n + |y/b|^n <= 1 fills `fill` of its bounding box (pi/4 -> 2)"""
    def area(n):
        return math.gamma(1 + 1 / n) ** 2 / math.gamma(1 + 2 / n)

    fill = min(0.995, max(0.5, fill))
    lo, hi = 1.0, 64.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if area(mid) < fill:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def _hull_area(pts):
    pts = sorted(set((round(p[0], 7), round(p[1], 7)) for p in pts))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return 0.5 * abs(sum(hull[i][0] * hull[i - 1][1] - hull[i - 1][0] * hull[i][1] for i in range(len(hull))))


def section(bm, axis, at, w_axis):
    """the cross-section of the mesh by the plane axis = at: the segments where triangles cross it -> their points
    as (width, height) pairs"""
    pts = []
    for f in bm.faces:
        vs = [v.co for v in f.verts]
        ds = [v[axis] - at for v in vs]
        for i in range(3):
            a, b = vs[i], vs[(i + 1) % 3]
            da, db = ds[i], ds[(i + 1) % 3]
            if (da < 0) != (db < 0):
                t = da / (da - db)
                p = a.lerp(b, t)
                pts.append((p[w_axis], p[2]))
    return pts


def _mask(objs, view, center, extent, out, px=1024, length_axis=0, shaded=False):
    """an orthographic silhouette (white on transparent) of the model from one side; shaded: the model as it looks
    (its textures, studio light, cavities) on white, the top view with the front to the RIGHT like a photograph"""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.film_transparent = not shaded
    sc.render.image_settings.color_mode = "RGB" if shaded else "RGBA"
    sc.display.shading.light = "STUDIO" if shaded else "FLAT"
    sc.display.shading.color_type = "TEXTURE" if shaded else "SINGLE"
    sc.display.shading.single_color = (1, 1, 1)
    sc.display.shading.show_cavity = shaded
    if shaded:
        sc.display.shading.cavity_type = "BOTH"
        if sc.world is None:
            sc.world = bpy.data.worlds.new("MeasureWorld")
        sc.world.color = (1, 1, 1)
    sc.view_settings.view_transform = "Standard"
    cam = bpy.data.objects.new("MeasureCam", bpy.data.cameras.new("MeasureCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    direction, (w, h) = view
    span = max(w, h) * 1.1
    cam.data.ortho_scale = span
    sc.render.resolution_x = px if w >= h else max(64, int(px * w / h))
    sc.render.resolution_y = px if h >= w else max(64, int(px * h / w))
    d = max(extent) * 4 + 1
    cam.location = center + direction * d
    up = Vector((0, 0, 1)) if abs(direction.z) < 0.9 else Vector((0, 1, 0))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y" if up.z else "Y").to_euler()
    if abs(direction.z) >= 0.9:  # top: looking down, the FRONT (the length's max end) pointing DOWN — as the kit's
        # own top view shows a model (rbx sheets: "top (front points down)"), so the trace matches its renders
        cam.rotation_euler = (0, 0, math.pi if length_axis == 1 else math.pi / 2)
        if shaded:  # (a photograph's top view: the front to the right)
            cam.rotation_euler = (0, 0, math.pi / 2 if length_axis == 1 else 0.0)
    cam.data.clip_end = d * 3
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)


def load_object(model, opt):
    """import a reference model and leave out its staging: -> (objs, dropped, frame); objs = [] when nothing is left.
    --only / --skip, flat backdrops, the most-assembled frame of an animation, parts apart from the object (shared by
    kit/refs/inspect_model.py: whatever is not the object is hidden from renders too)"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs, dropped, frame = _import(model), [], None
    for words, why, keep in ((opt.get("only"), "not in --only", True), (opt.get("skip"), "--skip", False)):
        if words:
            dropped += [{"name": o.name, "why": why} for o in objs if _named(o, words) != keep]
            objs = [o for o in objs if _named(o, words) == keep]
    for _ in range(2):  # the backdrop check again at the assembled frame: spread-out parts can hide a backdrop's size
        gone = _backdrops(objs)
        dropped += [{"name": o.name, "why": "a flat backdrop / floor (staging, not the object)"} for o in gone]
        objs = [o for o in objs if o not in gone]
        if not objs:
            return [], dropped, frame
        if frame is None:
            frame = int(opt["frame"]) if opt.get("frame") is not None else _assembled_frame(objs)
            if opt.get("frame") is not None:
                bpy.context.scene.frame_set(frame)
    # --all-parts keeps what lies apart (a display's spare parts, its loose rounds) — every part dissected, not only
    # the assembled object's
    main = objs if opt.get("all-parts") else _main_group(objs)
    dropped += [{"name": o.name, "why": "apart from the object (a tool, a prop, or a part not in place at this frame)"}
                for o in objs if o not in main]
    for o in bpy.data.objects:  # renders draw the scene: whatever is not the object is not drawn either
        if o.type == "MESH" and o not in main:
            o.hide_render = True
    return main, dropped, frame


def _bounds(bm):
    lo = Vector((min(v.co[i] for v in bm.verts) for i in range(3)))
    hi = Vector((max(v.co[i] for v in bm.verts) for i in range(3)))
    return lo, hi, hi - lo


def place(objs, opt):
    """real size and the front: -> (bm of the object in world space, lo, hi, ext, length axis, scale or None).
    One parent over everything is scaled / turned: an ANIMATED part's own keys would overwrite a change on the part"""
    bm = _joined_mesh(objs)
    lo, hi, ext = _bounds(bm)
    axis = {"x": 0, "y": 1}.get(opt.get("axis", "auto"), 0 if ext.x >= ext.y else 1)
    scaled = None
    if opt.get("length-mm") or opt.get("height-mm") or opt.get("front") == "min":
        root = bpy.data.objects.new("MeasureRoot", None)
        bpy.context.scene.collection.objects.link(root)
        for o in [o for o in bpy.data.objects if o.parent is None and o is not root]:
            o.parent = root
        if opt.get("length-mm"):  # a model not at real scale (a library model's units are its author's)
            scaled = float(opt["length-mm"]) / 1000.0 / max(ext[axis], 1e-9)
            root.scale = (scaled, scaled, scaled)
        elif opt.get("height-mm"):  # an UPRIGHT object (a barrel, a lamp post, an extinguisher): its real size is its
            # height — its length is whichever way it faces (a library prop's front-back depth was scaled to 387 mm
            # and the extinguisher came out 716 mm tall)
            scaled = float(opt["height-mm"]) / 1000.0 / max(ext.z, 1e-9)
            root.scale = (scaled, scaled, scaled)
        if opt.get("front") == "min":  # its front is the length's MIN end: TURNED half a turn (never mirrored: a
            # mirror would show its left side as a right side), so the front is the max end, the side view its right
            root.rotation_euler = (0.0, 0.0, math.pi)
        bpy.context.view_layer.update()
        bm.free()
        bm = _joined_mesh(objs)
        lo, hi, ext = _bounds(bm)
    return bm, lo, hi, ext, axis, scaled


def parse_cut(text):
    """'L0..L1,H0..H1' (mm) -> ((L0, L1), (H0, H1)), or None"""
    try:
        a, b = (tuple(float(x) for x in part.split("..")) for part in str(text).split(","))
    except ValueError:
        return None
    if len(a) != 2 or len(b) != 2 or a[0] >= a[1] or b[0] >= b[1]:
        return None
    return a, b


def cut_size(bm, lo, axis, w_axis, cut):
    """the model's size (m) without the vertices in the cut box -> (Vector of extents in x/y/z, how many left out)"""
    (l0, l1), (h0, h1) = cut
    keep, out = [], 0
    for v in bm.verts:
        u, h = (v.co[axis] - lo[axis]) * 1000.0, (v.co.z - lo.z) * 1000.0
        if l0 <= u <= l1 and h0 <= h <= h1:
            out += 1
        else:
            keep.append(v.co)
    if not keep:
        return None, out
    clo = Vector((min(c[i] for c in keep) for i in range(3)))
    chi = Vector((max(c[i] for c in keep) for i in range(3)))
    return chi - clo, out


def main():
    model, opt = _args()
    if not model or not os.path.isfile(model):
        return _emit("fail", f"measure: no model file {model}", "lune run kit refs measure <model.glb> --name <name>")
    name = opt["name"] or os.path.splitext(os.path.basename(model))[0]
    objs, dropped, frame = load_object(model, opt)
    if not objs:
        return _emit("fail", f"measure: nothing of {model} is left to measure (no meshes, or all left out)",
                     "check the file in Blender; loosen --only / --skip")
    bm, lo, hi, ext, axis, scaled = place(objs, opt)
    w_axis = 1 - axis
    cut, cut_ext, cut_out = None, None, 0
    if opt.get("cut"):
        cut = parse_cut(opt["cut"])
        if cut is None:
            return _emit("fail", f"measure: --cut {opt['cut']!r} is not L0..L1,H0..H1 (mm from the rear, from the bottom)",
                         "e.g. --cut 45..85,98..118")
        cut_ext, cut_out = cut_size(bm, lo, axis, w_axis, cut)
        if cut_ext is None or cut_out == 0:
            return _emit("fail", f"measure: --cut {opt['cut']} leaves out {'everything' if cut_ext is None else 'nothing'}",
                         "LOOK at the side silhouette (front to the right: the rear is at 0 mm) and box the part")
    stations = []
    n = max(3, opt["stations"])
    for k in range(n):
        u = (k + 0.5) / n
        at = lo[axis] + u * ext[axis]
        pts = section(bm, axis, at, w_axis)
        if len(pts) < 3:
            continue
        ws, hs = [p[0] for p in pts], [p[1] for p in pts]
        rx, ry = (max(ws) - min(ws)) / 2, (max(hs) - min(hs)) / 2
        if rx <= 0 or ry <= 0:
            continue
        fill = _hull_area(pts) / (4 * rx * ry)
        cw, ch = (max(ws) + min(ws)) / 2, (max(hs) + min(hs)) / 2
        stations.append({"u": round(u, 4), "rx_mm": round(rx * 1000, 1), "ry_mm": round(ry * 1000, 1),
                         "off_mm": [round((cw - (lo[w_axis] + ext[w_axis] / 2)) * 1000, 1),
                                    round((ch - lo.z) * 1000, 1)],
                         "fill": round(fill, 3), "squareness": superellipse_n(fill)})
    lev = levels(bm, lo, hi, axis, w_axis)
    bm.free()
    out_dir = os.path.join(REPO, opt["build"], "refs") if not os.path.isabs(opt["build"]) else os.path.join(opt["build"], "refs")
    os.makedirs(out_dir, exist_ok=True)
    center = (lo + hi) / 2
    length_dir = Vector((1, 0, 0)) if axis == 0 else Vector((0, 1, 0))
    # the side camera sits on the side where the length's MAX end shows on the picture's RIGHT ("front points right"):
    # looking down -X from +X puts +Y on the right (a Y-long model); an X-long one is seen from -Y (from +Y, +X is left)
    width_dir = Vector((0, -1, 0)) if axis == 0 else Vector((1, 0, 0))
    views = {"side": (width_dir, (ext[axis], ext.z)), "front": (length_dir, (ext[w_axis], ext.z)),
             "top": (Vector((0, 0, 1)), (ext[w_axis], ext[axis]))}
    masks = {}
    for view, spec in views.items():
        out = os.path.join(out_dir, f"{name}_{view}_mask.png")
        _mask(objs, spec, center, ext, out, length_axis=axis)
        masks[view] = os.path.relpath(out, REPO).replace("\\", "/")
    shots = {}
    if opt.get("views"):  # the model's own square views, shaded, at a known px per mm
        ppm = float(opt["view-px-mm"])
        ends = {"side-right": (width_dir, (ext[axis], ext.z)), "side-left": (-width_dir, (ext[axis], ext.z)),
                "top": (Vector((0, 0, 1)), (ext[axis], ext[w_axis])), "front": (length_dir, (ext[w_axis], ext.z)),
                "rear": (-length_dir, (ext[w_axis], ext.z))}
        want = list(ends) if opt["views"] == "all" else [v.strip() for v in opt["views"].split(",") if v.strip()]
        for view in want:
            if view not in ends:
                return _emit("fail", f"measure: no view {view!r}", f"--views all, or some of {', '.join(ends)}")
            out = os.path.join(out_dir, f"{name}_{view}_view.png")
            _mask(objs, ends[view], center, ext, out, px=int(math.ceil(ppm * max(ends[view][1]) * 1100)),
                  length_axis=axis, shaded=True)
            shots[view] = os.path.relpath(out, REPO).replace("\\", "/")
    parts = []  # every part's own size and place: width x height x length, centre from the centre line / bottom / back
    for o in objs:
        plo, phi = _world_box(o)
        e, c = phi - plo, (plo + phi) / 2
        parts.append({"name": o.name, "size_mm": [round(e[w_axis] * 1000, 1), round(e.z * 1000, 1), round(e[axis] * 1000, 1)],
                      "centre_mm": [round((c[w_axis] - center[w_axis]) * 1000, 1), round((c.z - lo.z) * 1000, 1),
                                    round((c[axis] - lo[axis]) * 1000, 1)]})
    parts.sort(key=lambda p: -p["size_mm"][0] * p["size_mm"][1] * p["size_mm"][2])
    size = [round(ext[w_axis] * 1000, 1), round(ext.z * 1000, 1), round(ext[axis] * 1000, 1)]
    cut_info = {}
    if cut:
        cut_info = {"cut": {"length_mm": list(cut[0]), "height_mm": list(cut[1]), "vertices_left_out": cut_out,
                            "about": "the sizes leave out what lies in this box across the whole width (mm from the "
                                     "rear / from the bottom); sections, levels and silhouettes are the whole model's"},
                    "size_uncut_mm": size}
        size = [round(cut_ext[w_axis] * 1000, 1), round(cut_ext.z * 1000, 1), round(cut_ext[axis] * 1000, 1)]
    result = {"name": name, "source": os.path.relpath(os.path.abspath(model), REPO).replace("\\", "/"),
              "size_mm": size, **cut_info,
              "scaled_by": scaled, "front_was": opt["front"], "frame": frame, "dropped": dropped, "parts": parts[:400],
              "axes": {"length": "xy"[axis], "width": "xy"[w_axis], "height": "z"}, "stations": stations,
              # horizontal slices (h = a fraction of the height): the biggest island's width / depth / roundness
              "levels": lev,
              "masks": masks,
              **({"shots": shots, "shot_px_per_mm": float(opt["view-px-mm"])} if shots else {}),
              # how each silhouette lies: picture x / picture up, in the model's own directions (u = length min->max)
              # front = the length's max end (u = 1), as the kit's views: side "front points right", top "front
              # points down", front "seen from the front"
              "views": {"side": ["+length", "+height"], "front": ["width, seen from the front", "+height"],
                        "top": ["width", "toward the BACK (the front is down)"]}}
    out_json = opt["out"] if os.path.isabs(opt["out"]) else os.path.join(REPO, opt["out"])
    os.makedirs(out_json, exist_ok=True)
    path = os.path.join(out_json, f"{name}.measure.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    w_mm, h_mm, l_mm = result["size_mm"]
    cut_note = (f", sizes without the cut box ({cut_out} vertices left out; whole model: {cut_info['size_uncut_mm']})"
                if cut else "")
    staged = (f", left out {len(dropped)} ({', '.join(d['name'] for d in dropped[:3])}"
              f"{', ...' if len(dropped) > 3 else ''})" if dropped else "")
    return _emit("pass", f"measure {name}: {l_mm:.0f} x {w_mm:.0f} x {h_mm:.0f} mm (length x width x height), "
                 f"{len(stations)} sections, {len(lev)} level(s), {len(parts)} part(s){staged}"
                 f"{f', at frame {frame} (most assembled)' if frame is not None and opt['frame'] is None else ''}, "
                 f"3 silhouettes{f', {len(shots)} square view(s)' if shots else ''}{cut_note} -> refs/{name}.measure.json",
                 f"trace the silhouettes: lune run kit refs measure ... does it; then a.carve(side=, top=, front=) or "
                 f"a.loft(stations) from refs/{name}.measure.json", measure=os.path.relpath(path, REPO).replace("\\", "/"),
                 masks=masks, **({"shots": shots} if shots else {}))


if __name__ == "__main__":
    main()
