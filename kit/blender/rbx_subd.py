"""rbx_subd.py — SMOOTH ANY PART BY SUBDIVISION, its chosen edges held crisp (bmesh + a subdivision modifier;
rbx.Asset.smooth calls it on a part and on every copy of it).

The other half of box modelling: cut ONE box into a rough form (a.loop / a.inset / a.push), then subdivide it
(Catmull-Clark) and the rough form becomes a smooth one - a pod, a helmet, a moulded handle, a pebble, a seat.
Edges that must stay edges are HELD (creased): hard where the form is hard, soft everywhere else. Until now only
a.cage could do this, and only from a traced outline extruded flat.

    a.box("Pod", (2, 1, 1), (0, 0.5, 0), "shell", bevel=0)
    a.loop("Pod", "X", at=[0.3, 0.7])
    a.smooth("Pod", levels=2, crisp=lambda c, d: c[1] < 0.01)      # everything soft but its foot

crisp says which edges are held:
    None                    none: the whole part goes soft (a SHARP box becomes a pebble)
    "sharp"                 every edge whose faces meet at more than `angle` degrees, and the edges that only
                            divide a flat face between them: a part of flat faces keeps its shape exactly and
                            only gains faces (with hold under 1: every hard edge eased)
    lambda centre, way: ..  any rule: the edge's middle and its direction (unit; its largest part made
                            positive, so `d[2] > 0.9` is every edge along z), the model's frame; True / False,
                            or a number 0..1 for how hard it is held
hold: how hard a held edge stays, 0..1, the same at every `levels`: 1 a true edge, 0.5 an edge rounded over
half of the levels, 0.25 a soft-hard edge that still reads, 0 not held.
A held OUTLINE keeps its corners (a square foot stays square): plain subdivision would round them off.
A face of more than four corners (a cut's flat face round a hole, a cylinder's cap) or one that is not convex
is split into triangles first: subdivision puts such a face's middle outside it, and it folds.
"""

import math

import bmesh
import bpy

MAX_LEVELS = 4
MAX_FACES = 120000
CORNER = math.cos(math.radians(35.0))   # two held edges that turn more than 35 degrees make a corner


def levels_of(levels):
    if isinstance(levels, bool) or not isinstance(levels, int) or not 1 <= levels <= MAX_LEVELS:
        raise ValueError(f"smooth: levels={levels!r} - a whole number 1..{MAX_LEVELS} (each level: four times the "
                         "faces; 1 leaves facets, 2 reads smooth)")
    return levels


def prepare(bm):
    """every face of more than four corners, and every four-cornered face that is not convex, split into
    triangles -> how many faces were split. (Catmull-Clark puts a face's middle at the mean of its corners:
    outside a face that is not convex, which then folds through its neighbours. A cut leaves such faces.)"""
    odd = [f for f in bm.faces if len(f.verts) > 4 or (len(f.verts) == 4 and any(not c.is_convex for c in f.loops))]
    if not odd:
        return 0
    bmesh.ops.triangulate(bm, faces=odd, quad_method="BEAUTY", ngon_method="EAR_CLIP")
    bm.normal_update()
    return len(odd)


def budget(bm, levels):
    """the faces a part will have after `levels` levels (a triangle: three quads at the first level)"""
    first = sum(len(f.verts) for f in bm.faces)
    return first * 4 ** (levels - 1)


def _corners(bm, layer):
    """a held outline keeps its CORNERS: where two held edges meet at an angle (and no third one makes the vertex
    a corner by itself) the vertex is held too - plain subdivision rounds a held square's corners off, as it
    rounds any curve drawn through its points"""
    spot = bm.verts.layers.float.get("crease_vert") or bm.verts.layers.float.new("crease_vert")
    for v in bm.verts:
        held = [e for e in v.link_edges if e[layer] > 0.0]
        v[spot] = 0.0
        if len(held) != 2:
            continue
        a, b = ((e.other_vert(v).co - v.co).normalized() for e in held)
        if a.dot(b) > -CORNER:                                 # (not a straight run: a corner)
            v[spot] = min(e[layer] for e in held)


def _strength(hold, levels):
    """how hard, 0..1 -> the crease value that gives it at this many levels. A crease stays sharp for
    (10 x crease squared) levels and then lets go: `hold` of 1 is sharp at every level, 0.5 at half of them."""
    if hold >= 1.0:
        return 1.0
    return math.sqrt(max(0.0, hold) * levels / 10.0)


def crease(bm, to_part, crisp, angle=30.0, hold=1.0, corners=True, levels=2):
    """mark the edges to hold on the bmesh's own crease layer (and, corners=True, the corners of a held outline)
    -> how many edges were held"""
    if isinstance(hold, bool) or not isinstance(hold, (int, float)) or not 0.0 <= float(hold) <= 1.0:
        raise ValueError(f"smooth: hold={hold!r} - how hard a held edge stays, 0..1")
    if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not 0.0 < float(angle) < 180.0:
        raise ValueError(f"smooth: angle={angle!r} - degrees between two faces from which an edge counts as sharp")
    held = _crease(bm, to_part, crisp, float(angle), float(hold), levels)
    if corners and held:
        _corners(bm, bm.edges.layers.float.get("crease_edge"))
    return held


def _crease(bm, to_part, crisp, angle, hold, levels):
    layer = bm.edges.layers.float.get("crease_edge") or bm.edges.layers.float.new("crease_edge")
    for e in bm.edges:
        e[layer] = 0.0
    if crisp is None or crisp is False:
        return 0
    held = 0
    if isinstance(crisp, str):
        if crisp != "sharp":
            raise ValueError(f'smooth: crisp={crisp!r} - None (all soft), "sharp" (every sharp edge held) or a rule '
                             "lambda centre, way: True / False / 0..1")
        if hold <= 0.0:
            return 0
        limit, value = math.radians(angle), _strength(hold, levels)
        for e in bm.edges:
            if e.is_manifold and e.calc_face_angle(0.0) > limit:
                e[layer] = value
                held += 1
        # a FLAT face keeps its plan too: an edge that only divides a flat area (a rim's mitre between two of
        # its strips, the cuts across a many-cornered face) and runs from one held edge to another is held with
        # them. Left soft, subdivision pulls its middle toward the strips' centres - round the corner, across
        # the held edge, and the rim folds over the pocket beside it.
        flat = [e for e in bm.edges if e[layer] == 0.0 and e.is_manifold and e.calc_face_angle(0.0) < math.radians(1.0)
                and all(any(k[layer] > 0.0 for k in v.link_edges) for v in e.verts)]
        for e in flat:
            e[layer] = value
        return held
    if not callable(crisp):
        raise ValueError(f'smooth: crisp={crisp!r} - None, "sharp" or a rule lambda centre, way: ...')
    turn = to_part.to_3x3()
    for e in bm.edges:
        a, b = (to_part @ v.co for v in e.verts)
        mid, way = (a + b) / 2, (turn @ (e.verts[1].co - e.verts[0].co))
        if way.length < 1e-12:
            continue
        way.normalize()
        if way[max(range(3), key=lambda i: abs(way[i]))] < 0:   # (one way round for every edge: its largest part +)
            way = -way
        answer = crisp((mid.x, mid.y, mid.z), (way.x, way.y, way.z))
        if answer is None or type(answer).__name__ in ("bool", "bool_"):
            amount = hold if answer else 0.0
        elif isinstance(answer, (int, float)) or type(answer).__name__.startswith(("float", "int")):
            amount = float(answer)
        else:
            raise ValueError("smooth: the rule must answer True, False or a number 0..1 for one edge")
        if not (math.isfinite(amount) and 0.0 <= amount <= 1.0):
            raise ValueError(f"smooth: the rule answered {amount!r} for an edge - True, False or 0..1")
        if amount > 0:
            e[layer] = _strength(amount, levels)
            held += 1
    return held


def subdivide(bm, levels):
    """the bmesh subdivided IN PLACE, Catmull-Clark, its crease layers honoured; face materials kept"""
    levels = levels_of(levels)
    after = budget(bm, levels)
    if after > MAX_FACES:
        raise ValueError(f"smooth: {len(bm.faces)} faces at levels={levels} is {after} faces - at most "
                         f"{MAX_FACES} (fewer levels, or a coarser part)")
    me = bpy.data.meshes.new("_kit_subd")
    ob = bpy.data.objects.new("_kit_subd", me)
    out = None
    try:
        bm.to_mesh(me)
        bpy.context.scene.collection.objects.link(ob)
        mod = ob.modifiers.new("subsurf", "SUBSURF")
        mod.levels = mod.render_levels = levels
        mod.subdivision_type = "CATMULL_CLARK"
        if hasattr(mod, "use_creases"):
            mod.use_creases = True
        if hasattr(mod, "use_limit_surface"):
            mod.use_limit_surface = False
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        out = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        bm.clear()
        bm.from_mesh(out)
    finally:
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
        if out is not None:
            bpy.data.meshes.remove(out)
    for layers, name in ((bm.edges.layers.float, "crease_edge"), (bm.verts.layers.float, "crease_vert")):
        layer = layers.get(name)
        if layer is not None:   # (the creases did their work: the smoothed part carries none)
            layers.remove(layer)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    return bm
