"""rbx_strip.py — ASSEMBLY / DISASSEMBLY: the order a thing comes apart, part by part, checked like the real thing.

Declared in the build script (rbx.Asset.disassembly): an ordered list of steps — which parts come off, along which
path (straight moves, studs, in the build's frame, and TURNS: {"turn": deg, "axis": (x, y, z), "pivot": (x, y, z)} —
a part rotated about a pivot it carries with it, as a pistol's barrel tips out of its slide: its muzzle is held in
the slide's front ring, its chamber against the breech face, and no straight move frees it) — and the parts that stay
(base: the frame everything comes off). Like a field strip and a detail strip in a manual. At build time:
  check(...)   every step's parts must come out along their path WITHOUT driving into what is still assembled (a BVH
               of the movers along the path against the rest: overlap growing beyond the contact they had at rest =
               blocked, named "Slide runs into Frame at 40% of its path"), and every part must come off by the end
               (none left that is not base) — gate `disassembly`
  sheet(...)   the steps as pictures: the model taken apart one step at a time (build/renders/<asset>_strip.png)
  export(...)  the ASSEMBLY: every part its own mesh (split from its baked group, keeping its UVs and maps) in one FBX
               (exports/<asset>_assembly.fbx), the steps in the manifest — an assembly a player or an animator can
               take apart and put back together
The owner, 2026-10-07: "literally a suppressor gun that you can assemble and disassemble".
"""

import fnmatch
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def _base(name):
    return name.split("~")[0]


def matches(name, pats):
    return any(fnmatch.fnmatchcase(_base(name), p) for p in pats)


def _world(o):
    me = o.data
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(o.matrix_world)
    co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    return co, [tuple(p.vertices) for p in me.polygons]


class _Set:
    """several parts as one triangle soup; every face knows its part"""

    def __init__(self, items):
        self.names, cos, self.polys, self.owner, off = [], [], [], [], 0
        for i, (nm, co, ps) in enumerate(items):
            self.names.append(nm)
            cos.append(co)
            self.polys += [tuple(v + off for v in p) for p in ps]
            self.owner += [i] * len(ps)
            off += len(co)
        self.co = np.concatenate(cos) if cos else np.zeros((0, 3))
        self.shift = np.zeros((len(self.co), 3))

    def tree(self, t=0.0, move=None):
        """the set moved by t * its per-vertex move (None: at rest)"""
        if not self.polys:
            return None
        co = self.co if move is None else self.co + t * move
        return BVHTree.FromPolygons(co.tolist(), self.polys)


TURN_WEIGHT = 0.2   # (a turn's share of a path's length, per radian: "at 40% of its path" counts turns too)


def _seg_len(seg):
    return abs(seg[2]) * TURN_WEIGHT if seg[0] == "turn" else seg[1].length


def _apply(seg, k, state):
    """one path segment, k (0..1) of the way, on top of a part's state (a 4x4 world matrix from its assembled place):
    a move is a world translation; a turn rotates about the pivot and axis the part CARRIES (where its state has put
    them), so "tip the barrel about its muzzle" means its muzzle wherever the barrel now is"""
    if seg[0] == "move":
        return Matrix.Translation(seg[1] * k) @ state
    _kind, axis, angle, pivot = seg
    p = state @ pivot
    a = (state.to_3x3() @ axis).normalized()
    return Matrix.Translation(p) @ Matrix.Rotation(angle * k, 4, a) @ Matrix.Translation(-p) @ state


def _mirror(seg):
    """the same motion mirrored across x = 0 (an "outward" left part does the right part's motion, mirrored)"""
    if seg[0] == "move":
        v = seg[1].copy()
        v.x = -v.x
        return ("move", v)
    _kind, axis, angle, pivot = seg
    a, p = axis.copy(), pivot.copy()
    a.x = -a.x
    p.x = -p.x
    return ("turn", a, -angle, p)   # (a mirrored rotation turns the other way about the mirrored axis)


def _path_states(path, state, n_per):
    """a path of segments from a part's state -> [(state at that point, fraction of the whole path)], end state"""
    pts, total = [], sum(_seg_len(sg) for sg in path) or 1.0
    done = 0.0
    for sg in path:
        for i in range(1, n_per + 1):
            pts.append((_apply(sg, i / n_per, state), (done + _seg_len(sg) * i / n_per) / total))
        state = _apply(sg, 1.0, state)
        done += _seg_len(sg)
    return pts, state


def plan(steps, frame):
    """the declared steps -> Blender-space paths ({"name", "parts", "path": [("move", v) | ("turn", axis, rad, pivot)],
    "outward": bool})"""
    import math  # noqa: PLC0415

    from rbx import BL_FROM_RBX  # noqa: PLC0415

    out = []
    for st in steps:
        segs = []
        for m in st.get("path") or [st["move"]]:
            if isinstance(m, dict):
                axis = BL_FROM_RBX.to_3x3() @ (frame.to_3x3() @ Vector(m.get("axis", (1, 0, 0))))
                pivot = BL_FROM_RBX @ (frame @ Vector(m.get("pivot", (0, 0, 0))))
                segs.append(("turn", axis.normalized(), math.radians(float(m["turn"])), pivot))
            else:
                segs.append(("move", BL_FROM_RBX.to_3x3() @ (frame.to_3x3() @ Vector(m))))
        out.append({"name": st.get("name") or ", ".join(st["parts"])[:40], "parts": list(st["parts"]),
                    "path": segs, "outward": bool(st.get("outward"))})
    return out


def _moved(co, m):
    """assembled vertices (n, 3) -> where a 4x4 state puts them"""
    a = np.array(m)
    return co @ a[:3, :3].T + a[:3, 3]


# SOFT parts: what squeezes past instead of jamming — a spring compresses (a firing pin pushed in against its spring),
# rubber stretches (a grip sleeve rolled off over the frame). Their overlaps are not counted as a jam; every step that
# relied on one says so (rows[].squeezed) and the facts list them (facts.soft): never silently.
SOFT_MATERIALS = ("rubber", "silicone", "leather", "fabric", "cloth", "foam", "elastic")


def soft(o, asset=None):
    """a spring (by its name) or a part made of a soft material (its faces' kit materials: named "<asset>_<name>",
    read without the asset's name — an asset called "..._rubber" makes nothing soft)"""
    nm = _base(o.name).lower()
    if nm.endswith("spring"):
        return True
    slots = getattr(o, "material_slots", [])
    if o.type != "MESH" or not slots:
        return False
    idx = np.zeros(len(o.data.polygons), np.int32)
    o.data.polygons.foreach_get("material_index", idx)
    used = [slots[i].material for i in set(idx.tolist()) if i < len(slots) and slots[i].material]  # (its faces')
    own = [m.name[len(asset) + 1:] if asset and m.name.startswith(f"{asset}_") else m.name for m in used]
    return bool(own) and all(any(w in m.lower() for w in SOFT_MATERIALS) for m in own)


def _signs(items, outward):
    """per part: +1 / -1 (outward: a left part does the motion mirrored across x = 0, a right part as given)"""
    return {nm: (-1.0 if outward and co[:, 0].mean() < 0 else 1.0) for nm, co, _ps in items}


def _box(co, m):
    """the axis-aligned box of a part's assembled vertices where a 4x4 state puts them (its 8 corners: cheap)"""
    lo, hi = co.min(0), co.max(0)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    c = _moved(corners, m)
    return c.min(0), c.max(0)


def check(parts, steps, base, asset=None):
    """-> (problems, facts, states {part name: final 4x4 Blender state}, per-step states [{part: state}]) — see the
    module doc. A part moved in one step can move again in a later one (a sub-assembly taken off, then taken apart:
    the magazine out, then its rounds out of it); every test runs against where the other parts ARE at that step."""
    items, soft_parts = {}, set()
    for o, _g in parts:
        if o.type == "MESH" and len(o.data.polygons):
            items[o.name] = _world(o)
            if soft(o, asset):
                soft_parts.add(o.name)
    cur = {n: Matrix.Identity(4) for n in items}  # where each part is now (a world matrix on its assembled place)
    moved, problems, rows, history = set(), [], [], []
    for k, st in enumerate(steps):
        movers = [n for n in items if matches(n, st["parts"])]
        label = f"step {k + 1} '{st['name']}'"
        if not movers:
            problems.append(f"{label} moves nothing: no part named {', '.join(st['parts'])}")
            rows.append({"step": st["name"], "parts": 0, "clear": False})
            history.append({n: m.copy() for n, m in cur.items()})
            continue
        sign = _signs([(n, *items[n]) for n in movers], st["outward"])
        paths = {}
        for n in movers:
            segs = st["path"] if sign[n] > 0 else [_mirror(sg) for sg in st["path"]]
            paths[n] = _path_states(segs, cur[n], 24)
        n_pts = len(paths[movers[0]][0])
        # only the parts the movers can REACH: those whose box meets the box the movers sweep along the whole path
        # (same answer — a part outside it can touch nothing that moves — at a fraction of the work: the whole gun's
        # tree was rebuilt every step)
        sw_lo, sw_hi = np.full(3, np.inf), np.full(3, -np.inf)
        for n in movers:
            for m in [cur[n]] + [q for q, _f in paths[n][0]]:
                lo_, hi_ = _box(items[n][0], m)
                sw_lo, sw_hi = np.minimum(sw_lo, lo_), np.maximum(sw_hi, hi_)
        pad = 1e-4 * float(np.max(sw_hi - sw_lo))
        rest = []
        for n in items:
            if n in movers:
                continue
            lo_, hi_ = _box(items[n][0], cur[n])
            if np.all(lo_ <= sw_hi + pad) and np.all(hi_ >= sw_lo - pad):
                rest.append(n)
        M = _Set([(n, _moved(items[n][0], cur[n]), items[n][1]) for n in movers])
        R = _Set([(n, _moved(items[n][0], cur[n]), items[n][1]) for n in rest])
        rt = R.tree()
        m_soft = [M.names[k_] in soft_parts for k_ in M.owner]
        r_soft = [R.names[k_] in soft_parts for k_ in R.owner]

        def hard(pairs_):  # (the pairs where neither face is a soft part's)
            return [(i, j) for i, j in pairs_ if not (r_soft[i] or m_soft[j])]

        rest_pairs = rt.overlap(M.tree()) if rt else []
        at_rest, at_rest_all = len(hard(rest_pairs)), len(rest_pairs)
        blocked, squeezed = None, None
        for idx in range(n_pts):
            if rt is None:
                break
            frac = paths[movers[0]][0][idx][1]
            co_t = np.concatenate([_moved(items[n][0], paths[n][0][idx][0]) for n in M.names])
            every = rt.overlap(BVHTree.FromPolygons(co_t.tolist(), M.polys))
            pairs = hard(every)
            if squeezed is None and len(every) > at_rest_all * 1.34 + 2 and len(pairs) <= at_rest * 1.34 + 2:
                cnt = {}
                for i, j in every:
                    if r_soft[i] or m_soft[j]:
                        key = (_base(M.names[M.owner[j]]), _base(R.names[R.owner[i]]))
                        cnt[key] = cnt.get(key, 0) + 1
                (sa, sb), _n = max(cnt.items(), key=lambda kv: kv[1])
                squeezed = f"{sa} squeezed past {sb} at {frac:.0%} of its path"
            if len(pairs) > at_rest * 1.34 + 2:
                cnt = {}
                for i, j in pairs:  # (rest's face, mover's face: overlap() lists the calling tree's first)
                    key = (_base(M.names[M.owner[j]]), _base(R.names[R.owner[i]]))
                    cnt[key] = cnt.get(key, 0) + 1
                (a_, b_), n_ = max(cnt.items(), key=lambda kv: kv[1])
                # WHERE: the middle of the mover's colliding faces (that pair's), in Roblox studs (x, y up, z) — the
                # spot to cut the clearance, or the path to change, without guessing
                hit = [j for i, j in pairs if (_base(M.names[M.owner[j]]), _base(R.names[R.owner[i]])) == (a_, b_)]
                mid = np.mean([co_t[list(M.polys[j])].mean(0) for j in hit[:400]], axis=0)
                blocked = (frac, a_, b_, n_, (round(float(mid[0]), 3), round(float(mid[2]), 3), round(float(-mid[1]), 3)))
                break
        rows.append({"step": st["name"], "parts": len(movers), "clear": blocked is None,
                     **({"squeezed": squeezed} if squeezed and not blocked else {}),
                     **({"blocked_at": round(blocked[0], 2), "by": f"{blocked[1]} into {blocked[2]}",
                         "around": blocked[4]} if blocked else {})})
        if blocked:
            problems.append(f"{label}: {blocked[1]} runs into {blocked[2]} at {blocked[0]:.0%} of its path "
                            f"({blocked[3]} triangle pairs, around {blocked[4]} studs) — take {blocked[2]} out first, "
                            "change the path (a part held at both ends TURNS out: a path step {'turn': deg, 'axis', "
                            "'pivot'}), or cut the clearance the real part has")
        for n in movers:
            cur[n] = paths[n][1]
        moved |= set(movers)
        history.append({n: m.copy() for n, m in cur.items()})
    never = sorted({_base(n) for n in items if n not in moved and not matches(n, base)})
    if never:
        problems.append(f"never taken apart: {', '.join(never[:10])}{' ...' if len(never) > 10 else ''} — give each a "
                        "step (or name it in base= if everything comes off it)")
    facts = {"steps": rows, "parts": len(items), "taken_apart": len(moved),
             "soft": sorted({_base(n) for n in soft_parts}),
             "base": sorted({_base(n) for n in items if matches(n, base)})}
    return problems, facts, {n: m.copy() for n, m in cur.items()}, history


def sheet(asset, parts, steps, offsets, out_png, max_panels=12, history=None):
    """the model taken apart one step at a time: one workbench panel per step (evenly sampled when there are many)"""
    import rbx_precision  # noqa: PLC0415  (Blender's Python has no PIL: the kit's own pixel helpers)

    sc = asset.scene
    objs = [o for o, _g in parts if o.type == "MESH"]
    by_step = [[o for o in objs if matches(o.name, st["parts"])] for st in steps]
    idx = list(range(len(steps)))
    if len(idx) > max_panels:
        idx = sorted({round(i * (len(steps) - 1) / (max_panels - 1)) for i in range(max_panels)})
    rest = {o: o.matrix_world.copy() for o in objs}
    keep = (sc.render.engine, sc.camera, sc.render.resolution_x, sc.render.resolution_y, sc.render.filepath,
            sc.display.shading.light, sc.display.shading.color_type)
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light, sc.display.shading.color_type = "STUDIO", "MATERIAL"
    cam_data = bpy.data.cameras.new("_strip_cam")
    cam = bpy.data.objects.new("_strip_cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam_data.type = "ORTHO"
    sc.render.resolution_x, sc.render.resolution_y = 520, 360
    # frame: the whole taken-apart state
    for o in objs:
        if o.name in offsets:
            o.matrix_world = offsets[o.name] @ rest[o]
    bpy.context.view_layer.update()
    cs = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(c[i] for c in cs) for i in range(3)])
    hi = Vector([max(c[i] for c in cs) for i in range(3)])
    mid, size = (lo + hi) / 2, max(hi - lo)
    d = Vector((-0.55, 0.45, 0.6)).normalized()
    cam.location = mid + d * size * 3
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam_data.ortho_scale = size * 1.1
    cam_data.clip_end = size * 10
    tiles = []
    try:
        for k in idx:
            state = (history or [])[k] if history and k < len(history) else None
            done = {o.name for movers in by_step[: k + 1] for o in movers}
            for o in objs:
                if state is not None and o.name in state:
                    o.matrix_world = state[o.name] @ rest[o]
                else:
                    o.matrix_world = offsets[o.name] @ rest[o] if o.name in done and o.name in offsets else rest[o]
            bpy.context.view_layer.update()
            f = out_png.replace(".png", f"_{k}.png")
            sc.render.filepath = f
            bpy.ops.render.render(write_still=True)
            tiles.append((k, f))
    finally:
        for o in objs:
            o.matrix_world = rest[o]
        # (without this every matrix_world still says the LAST panel's place — everything taken apart: the part review's
        # camera, framing a part by its matrix, looked at empty air where the barrel had been parked: black tiles)
        bpy.context.view_layer.update()
        bpy.data.objects.remove(cam)
        (sc.render.engine, sc.camera, sc.render.resolution_x, sc.render.resolution_y, sc.render.filepath,
         sc.display.shading.light, sc.display.shading.color_type) = keep
    cols = 4
    rows_ = (len(tiles) + cols - 1) // cols
    sheet_ = np.zeros((rows_ * 368, cols * 528, 4), np.float32)
    sheet_[..., :3], sheet_[..., 3] = 0.09, 1.0
    for i, (k, f) in enumerate(tiles):  # (row-major, step order; the names are in the facts: steps[i])
        px = rbx_precision._load_pixels(f)
        x, y = (i % cols) * 528 + 4, (rows_ - 1 - i // cols) * 368 + 4  # (pixels are bottom-up)
        h_, w_ = px.shape[:2]
        sheet_[y:y + h_, x:x + w_] = px
        os.remove(f)
    rbx_precision._save_pixels(sheet_, out_png)
    return out_png


def export(asset, groups, path, fbx):
    """the assembly: every part of every baked group its own mesh (split by the faces' "kit_part" tag: same UVs, same
    maps), all in one FBX at `path`, named after the parts. groups: {group: joined object}. -> the parts written"""
    made = []
    for g, obj in groups.items():
        attr = obj.data.attributes.get("kit_part")
        names = list(obj.get("kit_parts") or [obj.name])
        if attr is None:
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
            o = bpy.data.objects.new(nm, me)
            o.matrix_world = obj.matrix_world.copy()
            o["kit_group"] = g
            asset.collection.objects.link(o)
            made.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in made:
        o.select_set(True)
    if made:
        bpy.context.view_layer.objects.active = made[0]
        fbx(path)
    names = [o.name for o in made]
    for o in made:
        me = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me)
    return names
