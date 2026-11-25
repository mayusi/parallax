"""rbx_optimize.py — `kit optimize <name>`: the GAME version of a master (rbx.Asset(stage="master")).

The master's build script runs again with --optimize, and rbx.Asset builds <name>_game at the game stage (Roblox's
limits, 1024 maps, floaters baked). Here, per mesh group:
  keep_high(obj)        the master's full-detail join, kept as the bake SOURCE (high-to-low)
  reduce(obj, target)   the game mesh cut to its share of the tier's budget: near-coplanar faces merged first (free),
                        then edges collapsed (Blender's decimator) — materials never merged across
  deviation(high, low)  how far the game surface lies from the master's, in mm (mean / 95th percentile / max):
                        the geometric LOSS, gated (rbx.Asset.build) before the baked maps put the detail back
budgets(...) splits the tier's triangle budget between the groups: every group keeps a floor (a trigger keeps its
shape), the rest goes by size; nothing above the master's own count or Roblox's 20k a mesh.
"""

import math
import random

import bpy
from mathutils.bvhtree import BVHTree

ROBLOX_MESH_CAP = 20000
RETOPO_SCALE = 1000.0   # (QuadriFlow's absolute 1e-4 edge test: see retopo)


def budgets(group_tris, total, floor=400):
    """{group: master triangles} -> {group: game triangles} (pure: kit/test/python/test_optimize.py)"""
    out = {g: min(n, floor) for g, n in group_tris.items()}
    left = max(0, total - sum(out.values()))
    extra = {g: n - out[g] for g, n in group_tris.items() if n > out[g]}
    room = sum(extra.values())
    for g, e in extra.items():
        out[g] = min(group_tris[g], ROBLOX_MESH_CAP, out[g] + (int(left * e / room) if room else 0))
    return out


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def keep_high(obj, collection):
    """a full-detail copy of the joined group (its own mesh data), linked for the bake -> the copy"""
    high = obj.copy()
    high.data = obj.data.copy()
    high.name = f"{obj.name}_MASTER"
    collection.objects.link(high)
    return high


def _apply(obj, kind, **props):
    mod = obj.modifiers.new(f"optimize_{kind.lower()}", kind)
    for k, v in props.items():
        setattr(mod, k, v)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def retopo(obj, target):
    """Blender's built-in QuadriFlow remesher (no install): an even quad flow at about target / 2 quads, triangulated
    -> its triangles after, or None when QuadriFlow fails (not manifold, too few faces) — for SCULPTED / GENERATED
    groups (a generator's triangle soup, a sculpt's dense mesh): their detail comes back from the master in the bake.
    Never for hard surface: it rounds the sharp edges a CAD part is made of"""
    from mathutils import Matrix  # noqa: PLC0415

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # QuadriFlow refuses a mesh with any edge under 1e-4 UNITS on every axis ("needs to be manifold ... consistent
    # normals" — its own source: a zero-length-edge test at an absolute 1e-4). A sculpt in studs has hundreds (the
    # skull: 778 of 495k): remeshed at x1000 and scaled back, the same surface passes (2026-10-18)
    before = (len(obj.data.vertices), len(obj.data.polygons))
    obj.data.transform(Matrix.Scale(RETOPO_SCALE, 4))
    try:
        res = bpy.ops.object.quadriflow_remesh(target_faces=max(64, int(target) // 2), use_mesh_symmetry=False,
                                               use_preserve_sharp=False, use_preserve_boundary=True,
                                               smooth_normals=False, seed=0)
    except RuntimeError:
        res = {"CANCELLED"}
    obj.data.transform(Matrix.Scale(1.0 / RETOPO_SCALE, 4))
    obj.data.update()
    # (a refusal is a warning, not an exception: an UNCHANGED mesh is a failure whatever the operator returned)
    if "FINISHED" not in res or not obj.data.polygons or (len(obj.data.vertices), len(obj.data.polygons)) == before:
        return None
    _apply(obj, "TRIANGULATE")
    return tris(obj)


PROTECT = "kit_protect"      # the vertex group the decimator spares
PROTECT_BAR = 0.1            # the game surface may lie this share of a protected place's radius off the model ...
PROTECT_FLOOR = 0.005        # ... and never needs to be nearer than this (studs)


def near(points, places):
    """which points lie in a protected place -> [bool]. places: [(centre (x, y, z), radius)], the points' frame"""
    out = []
    for p in points:
        out.append(any(math.dist(p, c) <= r for c, r in places))
    return out


def protect_group(obj, places):
    """the points of obj (its own frame) inside a protected place, put in the vertex group the decimator spares
    -> how many (0: no group is left on it)"""
    old = obj.vertex_groups.get(PROTECT)
    if old is not None:
        obj.vertex_groups.remove(old)
    if not places:
        return 0
    inside = near([tuple(v.co) for v in obj.data.vertices], places)
    picked = [i for i, hit in enumerate(inside) if hit]
    if not picked:
        return 0
    group = obj.vertex_groups.new(name=PROTECT)
    group.add(picked, 1.0, "REPLACE")
    rest = [i for i, hit in enumerate(inside) if not hit]
    if rest:
        group.add(rest, 0.0, "REPLACE")
    return len(picked)


def _collapse(obj, ratio):
    """the decimator to a share of the triangles; where obj carries protected points, they go last"""
    held = obj.vertex_groups.get(PROTECT) is not None
    _apply(obj, "DECIMATE", decimate_type="COLLAPSE", ratio=ratio, use_collapse_triangulate=True,
           **({"vertex_group": PROTECT, "invert_vertex_group": True} if held else {}))


def place_deviation(high, low, places, count=20000):
    """how far the game surface lies from the master's INSIDE each protected place -> [{"p99": studs or None,
    "points": the master's sampled points there}] in the places' order. places: [(centre, radius)] WORLD frame.
    None: the master has (almost) no surface there - nothing to hold."""
    mw = low.matrix_world
    tree = BVHTree.FromPolygons([mw @ v.co for v in low.data.vertices], [tuple(p.vertices) for p in low.data.polygons])
    # points sampled IN each place (the review: 20,000 points over a 16 x 16 plate left under 8 inside a socket's
    # 0.1 studs, and the place was said to be off the model): the master's triangles that reach into the place,
    # sampled by area, the points inside it kept
    me = high.data
    me.calc_loop_triangles()
    hw = high.matrix_world
    vs = [hw @ v.co for v in me.vertices]
    tri = [(vs[t.vertices[0]], vs[t.vertices[1]], vs[t.vertices[2]]) for t in me.loop_triangles]
    out = []
    for k, (centre, radius) in enumerate(places):
        c = type(vs[0])(centre) if vs else None
        near_ = []
        for a, b, cc in tri:
            reach = max((a - b).length, (b - cc).length, (cc - a).length)
            if ((a + b + cc) / 3 - c).length <= radius + reach:
                near_.append((a, b, cc))
        areas = [((b - a).cross(cc - a)).length / 2 for a, b, cc in near_]
        d = []
        if near_ and sum(areas) > 0:
            rng = random.Random(7 + k)
            want = max(200, min(count, 4000))
            for i in rng.choices(range(len(near_)), weights=areas, k=want * 4):
                a, b, cc = near_[i]
                u, v = rng.random(), rng.random()
                if u + v > 1:
                    u, v = 1 - u, 1 - v
                p = a + (b - a) * u + (cc - a) * v
                if (p - c).length <= radius:
                    d.append(tree.find_nearest(p)[3] or 0.0)
                    if len(d) >= want:
                        break
        d.sort()
        out.append({"p99": d[min(len(d) - 1, int(0.99 * len(d)))] if len(d) >= 8 else None, "points": len(d)})
    return out


def protect_bar(radius, within=None):
    return float(within) if within else max(PROTECT_FLOOR, PROTECT_BAR * float(radius))


def protect_problem(name, found, radius, within=None):
    """a protected place the reduction did not spare -> a sentence, or None"""
    if found["p99"] is None:
        return (f"{name}: the model has no surface within {radius:g} studs of it - nothing there to protect "
                "(a place off the model, or a radius too small)")
    if found["p99"] > protect_bar(radius, within):
        return (f"{name}: the game version lies {found['p99']:.3g} studs off the model there "
                f"(the place holds {protect_bar(radius, within):.3g})")
    return None


def reduce(obj, target, use_retopo=False, protect=None):
    """cut obj to about `target` triangles -> its triangles after (obj["kit_reduce"]: the method used). use_retopo:
    QuadriFlow first (retopo; an overshoot decimated to the budget), back to the decimator when it fails.
    protect: [(centre, radius)] in obj's own frame - places whose points the DECIMATOR spares until last (a
    retopology rebuilds the whole surface and spares nothing: said by obj["kit_protected"] = 0)"""
    obj["kit_protected"] = 0
    if tris(obj) <= target:
        obj["kit_reduce"] = "kept"
        return tris(obj)
    if use_retopo:
        keep = obj.data.copy()
        n = retopo(obj, target)
        if n is not None:
            bpy.data.meshes.remove(keep)
            obj["kit_reduce"] = "quadriflow"
            if n > target:   # (QuadriFlow lands near, not on, its count: the decimator takes it to the budget)
                _apply(obj, "DECIMATE", decimate_type="COLLAPSE", ratio=max(0.01, target / n),
                       use_collapse_triangulate=True)
            return tris(obj)
        name = obj.data.name
        old, obj.data = obj.data, keep   # (QuadriFlow failed: the decimator on the untouched mesh)
        bpy.data.meshes.remove(old)
        keep.name = name
    obj["kit_reduce"] = "decimate"
    # flat regions first: faces within 1 degree of each other merge without moving the surface at all (a bevelled box
    # keeps its bevels: their faces are far more than a degree apart); never across a material
    _apply(obj, "DECIMATE", decimate_type="DISSOLVE", angle_limit=math.radians(1.0), delimit={"MATERIAL"})
    _apply(obj, "TRIANGULATE")
    n = tris(obj)
    if n > target:
        obj["kit_protected"] = protect_group(obj, protect or [])
        _collapse(obj, max(0.01, target / n))
        old = obj.vertex_groups.get(PROTECT)
        if old is not None:
            obj.vertex_groups.remove(old)
    return tris(obj)


def _surface_points(obj, count, seed=7):
    """`count` points spread over obj's surface by area (deterministic), world space"""
    me = obj.data
    me.calc_loop_triangles()
    mw = obj.matrix_world
    vs = [mw @ v.co for v in me.vertices]
    tri = [(vs[t.vertices[0]], vs[t.vertices[1]], vs[t.vertices[2]]) for t in me.loop_triangles]
    areas = [((b - a).cross(c - a)).length / 2 for a, b, c in tri]
    total = sum(areas)
    if not tri or total <= 0:
        return []
    rng = random.Random(seed)
    picks = rng.choices(range(len(tri)), weights=areas, k=count)
    out = []
    for i in picks:
        a, b, c = tri[i]
        u, v = rng.random(), rng.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        out.append(a + (b - a) * u + (c - a) * v)
    return out


def deviation(high, low, mm_per_stud=None, count=20000):
    """how far the game surface (low) lies from the master's (high): points over the master's surface -> distance to
    the game mesh -> {"mean_mm", "p95_mm", "max_mm", "p99_studs"} (mm when the asset declared its scale, else studs)"""
    mw = low.matrix_world
    tree = BVHTree.FromPolygons([mw @ v.co for v in low.data.vertices], [tuple(p.vertices) for p in low.data.polygons])
    d = sorted(tree.find_nearest(p)[3] or 0.0 for p in _surface_points(high, count))
    if not d:
        return {"mean_mm": 0.0, "p95_mm": 0.0, "max_mm": 0.0, "p99_studs": 0.0}
    k = (mm_per_stud or 1.0)
    pick = lambda q: d[min(len(d) - 1, int(q * len(d)))]  # noqa: E731
    return {"mean_mm": round(sum(d) / len(d) * k, 2), "p95_mm": round(pick(0.95) * k, 2), "max_mm": round(d[-1] * k, 2),
            "p99_studs": pick(0.99)}


ROBLOX_PX_PER_STUD = 51.2   # Roblox's texture guidance: 256 px for a 5-stud object, 512 for 10, 1024 for 20
#   (create.roblox.com/docs/art/modeling/texture-specifications, read 2026-10-18)

# THE MAP'S SIZE FROM THE NEED (the 3D studio route's H3, 2026-11-12). What Roblox SAYS: it renders a texture at up to
# 4096 x 4096 where the device has the memory and the view needs it, and a smaller version of it everywhere else
# (texture streaming picks, per object and view point; in Studio only with Texture Streaming enabled); an image is
# stored as imported up to 8192 and served at 4096 at most. Sources: Roblox staff, DevForum "4k Texture Rendering",
# 2026-01-30 (MeshPart, SurfaceAppearance, Texture, Decal, MaterialVariant); create.roblox.com/docs/art/modeling/
# texture-specifications ("supports up to 4096x4096", read 2026-11-12 - the SAME page still says "up to 1024x1024
# pixel spaces for texture maps" under UV mapping).
ROBLOX_MAX_TEX = 4096       # the largest map a MASTER gets (it is judged in Blender and is every game bake's source)
# What the kit has SEEN (the test upload of 2026-11-12, the owner's "Yes, one upload", card v57z): 4096. One plain
# stripe chart sent at 1024, 2048 and 4096 through kit upload's own request (Open Cloud, an Image asset), each on a
# test slab in Roblox Studio, looked at from close: the 4096 chart showed its one-texel stripes, the 2048 chart its
# own, as SurfaceAppearance.ColorMap and as MeshPart.TextureID. So a GAME build and a game version may carry maps
# up to here, and kit optimize no longer cuts a main mesh up to keep its sharpness (_split_for_maps reads this).
# Two things that test also showed: the plain DOWNLOAD of an image asset (asset delivery) is a 1024 copy whatever
# was sent, and softer than a native 1024 - never judge an upload by downloading it; and what a phone shows is not
# tested (texture streaming picks a smaller level by memory and distance). Only normal / roughness / metalness
# maps were not looked at. Lower this ONE number if a later look says otherwise: every rule below reads it.
GAME_MAP_CAP = 4096
# How sharp is sharp enough: one texel a screen pixel at the distance the piece is judged from (more texels than
# that cannot be seen, fewer read as blur). Roblox's camera: 70 degrees of vertical field of view; a 1080-line screen.
# The distances are the kit's own (labelled, not measured): a hero piece is held in first person or inspected
# (0.75 m), a prop is seen past the third-person camera (3 m).
SEEN_M = {"prop": 3.0, "hero": 0.75, "aaa": 0.75}
SCREEN_LINES, CAMERA_FOV = 1080, 70.0
GAME_TEX = 1024             # the game map no rule has sized (what every build got until 2026-11-12)
MAP_MARGIN = 2.0            # a map's pixels over the pixels its faces use: 1 / 0.50, the median share of their map
#   that 246 mesh groups of 96 built models cover (measured 2026-11-12 off their manifests: a quarter under 0.37, a
#   quarter over 0.61). The texel rule's older 1.4 is the best tenth's.


def screen_px_per_m(distance_m, lines=SCREEN_LINES, fov=CAMERA_FOV):
    """screen pixels a metre of surface covers, seen square-on from distance_m (pure: test_texel.py):
    lines / (2 d tan(fov / 2)) - 1028 at 0.75 m, 257 at 3 m"""
    return lines / (2.0 * max(float(distance_m), 1e-6) * math.tan(math.radians(fov) / 2.0))


def texel_bar(quality):
    """the texture density (px per metre) a tier's piece needs where it is judged: SEEN_M's distance on the screen"""
    return round(screen_px_per_m(SEEN_M.get(quality, SEEN_M["prop"])), 1)


def map_for_area(area_m2, bar, floor=GAME_TEX, cap=ROBLOX_MAX_TEX, margin=MAP_MARGIN):
    """the map a group needs BEFORE its UVs exist (pure: test_texel.py): `bar` px a metre over its whole surface
    (area_m2, x margin: what packing leaves unused, MAP_MARGIN) -> the smallest power of two in [floor, cap]. Never
    under `floor`: this rule only ever makes a map larger. An estimate - the build's texel_bar check MEASURES the
    density the bake really got and names a group that is still short."""
    need = float(bar) * math.sqrt(max(float(area_m2), 0.0) * margin)
    size = int(floor)
    while size < need and size < cap:
        size *= 2
    return int(min(size, cap))


def map_to_reach(px_per_m, tex, bar, cap=ROBLOX_MAX_TEX):
    """a group's MEASURED density (px_per_m at a tex x tex map) against `bar` (pure: test_texel.py) -> None when it
    reaches it, else {"tex": the smallest power of two that does (at most cap), "px_per_m": its density at that size,
    "reaches": False when even the cap falls short - then the group wants maps of its own (a.group), not a size}"""
    if px_per_m <= 0 or px_per_m >= bar:
        return None
    size = int(tex)
    while size < cap and px_per_m * size / tex < bar:
        size *= 2
    size = int(min(size, cap))
    got = px_per_m * size / tex
    return {"tex": size, "px_per_m": round(got, 1), "reaches": bool(got >= bar)}


def surface_m2(obj, mm_per_stud=None):
    """a mesh object's surface in square metres (its world size; 1 stud = 0.28 m without a real scale)"""
    import numpy as np  # noqa: PLC0415

    me = obj.data
    if not me.polygons:
        return 0.0
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    verts = np.empty(n * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", verts)
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(obj.matrix_world, dtype=np.float64)
    p = (co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])[verts.reshape(-1, 3)]
    k = (mm_per_stud or 280.0) / 1000.0
    return float(np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum() / 2 * k * k)


def density_stats(uv_areas, world_areas, tex, m_per_unit=0.28):
    """TEXEL DENSITY (pure: kit/test/python/test_texel.py): per face, its share of the map (uv area, 0..1 units) and
    its surface (scene units^2) -> px per metre, weighted by surface: {"px_per_m", "px_per_stud", "p10", "p90",
    "spread", "coverage"} — spread = p90 / p10 (1.0: every face as sharp as the rest; an AAA asset keeps it near 1: one part
    blurred beside a sharp one reads as a mistake)"""
    import numpy as np  # noqa: PLC0415

    uv = np.asarray(uv_areas, dtype=np.float64)
    wa = np.asarray(world_areas, dtype=np.float64) * m_per_unit * m_per_unit
    keep = (uv > 0) & (wa > 0)
    if not keep.any():
        return {"px_per_m": 0.0, "px_per_stud": 0.0, "p10": 0.0, "p90": 0.0, "spread": 0.0, "coverage": 0.0}
    d = np.sqrt(uv[keep] * tex * tex / wa[keep])
    w = wa[keep]
    order = np.argsort(d)
    cum = np.cumsum(w[order]) / w.sum()

    def q(f):
        return float(d[order][min(len(d) - 1, int(np.searchsorted(cum, f)))])
    med, p10, p90 = q(0.5), q(0.1), q(0.9)
    return {"px_per_m": round(med, 1), "px_per_stud": round(med * m_per_unit, 1), "p10": round(p10, 1),
            "p90": round(p90, 1), "spread": round(p90 / max(p10, 1e-9), 2),
            "coverage": round(float(uv[keep].sum()), 3)}   # (the share of the map the faces cover: padding wastes it)


def texel_density(obj, tex, mm_per_stud=None):
    """density_stats of obj's active UV map at a tex x tex map — per loop triangle, in numpy (a 495k-face sculpt in
    about a second: a per-polygon Python loop took tens)"""
    import numpy as np  # noqa: PLC0415

    me = obj.data
    if not me.uv_layers or not me.polygons:
        return None
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    loops = np.empty(n * 3, np.int64)
    verts = np.empty(n * 3, np.int64)
    me.loop_triangles.foreach_get("loops", loops)
    me.loop_triangles.foreach_get("vertices", verts)
    uv = np.empty(len(me.loops) * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)[loops.reshape(-1, 3)]
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(obj.matrix_world, dtype=np.float64)
    co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    p = co[verts.reshape(-1, 3)]
    e1, e2 = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
    uv_a = np.abs(e1[:, 0] * e2[:, 1] - e2[:, 0] * e1[:, 1]) / 2
    w_a = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1) / 2
    return density_stats(uv_a, w_a, tex, (mm_per_stud or 280.0) / 1000.0)


LOD_CACHE_VERSION = 1   # (raised when lod_preview's measure changes: every kept answer is then asked again)


def lod_key(obj, mm_per_stud=None):
    """what lod_preview's answer depends on: the mesh's points and faces, its place and size in the world, the
    scale -> a hex digest (the simulation is deterministic: the decimator, and the deviation's seeded samples)"""
    import hashlib  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    me = obj.data
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    loops = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", loops)
    starts = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", starts)
    h = hashlib.sha1()
    h.update(np.round(co, 6).tobytes())
    h.update(loops.tobytes())
    h.update(starts.tobytes())
    h.update(np.round(np.array(obj.matrix_world, np.float64), 6).tobytes())
    h.update(repr((mm_per_stud, LOD_CACHE_VERSION)).encode())
    return h.hexdigest()[:20]


def lod_preview_kept(obj, mm_per_stud=None, cache_dir=None):
    """lod_preview, KEPT between builds by the mesh's own key (card fbvv: it ran on every full build and group -
    about 3.5 s on a 200k-triangle mesh) -> (its answer, True when it came from the cache). cache_dir None: asked"""
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415

    if not cache_dir:
        return lod_preview(obj, mm_per_stud), False
    path = os.path.join(cache_dir, lod_key(obj, mm_per_stud) + ".json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh), True
        except (OSError, ValueError):
            pass
    out = lod_preview(obj, mm_per_stud)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh)
    except OSError:
        pass
    return out, False


def lod_preview(obj, mm_per_stud=None):
    """what Roblox's OWN level of detail does to obj (custom LOD meshes are not supported: RenderFidelity=Automatic
    halves the triangles at 250 studs and again at 500 — create.roblox.com RenderFidelity): each level simulated by
    the decimator and measured against obj -> {"lod1": {...}, "lod2": {...}, "render_fidelity": ..., "why": ...}"""
    out = {}
    size = max(obj.dimensions) * (mm_per_stud or 1.0)
    for lvl, ratio in (("lod1", 0.5), ("lod2", 0.25)):
        cp = obj.copy()
        cp.data = obj.data.copy()
        bpy.context.scene.collection.objects.link(cp)
        _apply(cp, "DECIMATE", decimate_type="COLLAPSE", ratio=ratio, use_collapse_triangulate=True)
        dev = deviation(obj, cp, mm_per_stud, count=6000)
        dev.pop("p99_studs", None)
        out[lvl] = {"tris": tris(cp), "studs_from": 250 if lvl == "lod1" else 500, **dev}
        me = cp.data
        bpy.data.objects.remove(cp)
        bpy.data.meshes.remove(me)
    bad = out["lod1"]["p95_mm"] > 0.01 * size   # (the silhouette moves over 1% of the object at the first level)
    out["render_fidelity"] = "Precise" if bad else "Automatic"
    out["why"] = (f"Roblox's 250-stud level moves 95% of the surface up to {out['lod1']['p95_mm']} (over 1% of its "
                  f"{size:.0f}): Precise if it is seen from afar, Automatic if it stays close (held)" if bad else
                  f"Roblox's 250-stud level moves it {out['lod1']['p95_mm']} at most for 95% of it: Automatic is safe")
    return out


def detail_map_size(features, area, cap=1024, texels=8.0, floor=128, margin=1.4):
    """the map a DETAIL mesh needs (pure: test_texel.py): its smallest feature (studs) gets `texels` texels across,
    over its whole surface `area` (studs^2, x margin for packing) -> the smallest power of two in [floor, cap]. The
    barrel's 12 small details got a whole 1024 map: 9428 px a stud, ~120x its body's (2026-10-18)"""
    f = max(min(features), 1e-6) if features else 1.0
    need = texels / f * math.sqrt(max(area, 1e-9) * margin)
    size = floor
    while size < need and size < cap:
        size *= 2
    return int(min(size, cap))
