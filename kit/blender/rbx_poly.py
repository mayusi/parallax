"""rbx_poly.py — BOX MODELLING BY RULE: inset, push (extrude) and pick the faces of a part by where they look
(bmesh; rbx.Asset.inset / push / loop / round call it on a part and on every copy of it).

The classic way a hand-made game prop is built: start from a box, cut it into the pieces the form needs (loop
cuts), INSET a face (a panel, a window, a lid's rim), PUSH faces in or out (a recess, a boss, a handle's stub),
round the edges last. A build script had none of it: a form was typed as raw vertex lists (a.mesh) or stacked
from separate boxes, which is why crates and cases read as stacked boxes.

    a.box("Crate", (2, 1, 1), (0, 0.5, 0), "wood", bevel=0)          # sharp: it is rounded at the end
    a.inset("Crate", "+Y", 0.12, depth=-0.04)                        # its lid: a rim, the panel sunk 0.04
    a.loop("Crate", "X", at=[0.35, 0.65])                            # two cuts across its length
    a.push("Crate", lambda c, n: n[2] > 0.9 and abs(c[0]) < 0.3 and c[2] > 0.45, 0.1)   # the middle of its back, out
    a.round("Crate", 0.02)

The faces are PICKED BY RULE, never by number (a number means nothing after the next cut):
    "+Y", "-X", "Z" ...            the faces that look that way (within 12 degrees: a flat side, not the rounded
                                   strips beside it), in the model's frame
    lambda centre, normal: ...     any rule, as a.zone's: both in the model's frame (a scattered piece: as modelled)
A rule by direction alone picks EVERY face that looks that way - the walls of a pocket made a step earlier too.
Say where the face is as well (`n[2] > 0.9 and c[2] > 0.45`); the build says "(2 places)" when a rule picked
faces in more than one patch.
"""

import math

import bmesh
from mathutils import Vector

FACING = math.cos(math.radians(12.0))
ALONG = 0.02          # a neighbour whose normal is this square to the push is a WALL along it
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def chooser(where, what="faces"):
    """a rule -> a function (centre, normal) -> bool. A direction name picks the faces that look that way."""
    if callable(where):
        return where
    if isinstance(where, str):
        name = where.strip().upper()
        sign = -1.0 if name.startswith("-") else 1.0
        axis = AXES.get(name.lstrip("+-"))
        if axis is not None:
            want = Vector(axis) * sign
            return lambda _c, n: Vector(n).dot(want) > FACING
    raise ValueError(f'{what}: where={where!r} - "+Y", "-X" ... (the faces that look that way) or a rule '
                     "lambda centre, normal: True / False")


def scale_of(to_part):
    """how many of the part's studs one of the mesh's own units is (a copy made bigger by vary=: its scale)"""
    return abs(to_part.to_3x3().determinant()) ** (1.0 / 3.0)


def picked(bm, to_part, where, what="faces"):
    """the faces a rule picks -> [BMFace]; `to_part`: the mesh's own coordinates -> the part's frame (4 x 4)"""
    rule = chooser(where, what)
    turn = to_part.to_3x3().inverted().transposed()
    out = []
    for f in bm.faces:
        c = to_part @ f.calc_center_median()
        n = (turn @ f.normal).normalized()
        answer = rule((c.x, c.y, c.z), (n.x, n.y, n.z))   # (what the rule itself raises is the rule's to say)
        try:
            ok = bool(answer)
        except ValueError:
            raise ValueError(f"{what}: the rule must answer True or False for one face") from None
        if ok:
            out.append(f)
    return out


def places(faces):
    """how many separate patches the picked faces make (faces that share an edge are one patch). A rule by
    direction alone also picks the walls of a pocket made earlier: more than one place is said, never hidden."""
    left, n = set(faces), 0
    while left:
        n += 1
        todo = [left.pop()]
        while todo:
            f = todo.pop()
            for e in f.edges:
                for g in e.link_faces:
                    if g in left:
                        left.remove(g)
                        todo.append(g)
    return n


def faults(bm):
    """(edges that do not join exactly two faces, faces of no area) - a closed, sound mesh: (0, 0)"""
    return (sum(1 for e in bm.edges if len(e.link_faces) != 2), sum(1 for f in bm.faces if f.calc_area() < 1e-9))


def doubled(bm):
    """pairs of faces that lie ON each other looking opposite ways (a wall of no thickness: closed by the count
    of its edges, and still no solid) -> how many"""
    planes = {}
    for f in bm.faces:
        n = f.normal
        if n.length < 0.5:
            continue
        lead = max(range(3), key=lambda i: abs(n[i]))
        sign = 1.0 if n[lead] > 0 else -1.0
        key = (round(n.x * sign, 3), round(n.y * sign, 3), round(n.z * sign, 3),
               round(f.verts[0].co.dot(n) * sign, 4))
        planes.setdefault(key, []).append((sign, f, lead))
    count = 0
    for rows in planes.values():
        ups = [r for r in rows if r[0] > 0]
        downs = [r for r in rows if r[0] < 0]
        for _s, f, lead in ups:
            axes = [i for i in range(3) if i != lead]
            box = [(min(v.co[i] for v in f.verts), max(v.co[i] for v in f.verts)) for i in axes]
            for _t, g, _l in downs:
                other = [(min(v.co[i] for v in g.verts), max(v.co[i] for v in g.verts)) for i in axes]
                if all(min(a[1], b[1]) - max(a[0], b[0]) > 1e-6 for a, b in zip(box, other)):
                    count += 1
    return count


def crossing(bm):
    """pairs of faces that pass THROUGH each other (faces that share a corner do not count: neighbours touch).
    A part can be closed, the right way out and free of faces lying on each other, and still fold through
    itself where a smoothing or a deep push carried one wall past another -> how many"""
    from mathutils.bvhtree import BVHTree  # noqa: PLC0415

    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm, epsilon=0.0)
    count = 0
    for i, j in tree.overlap(tree):
        if i < j and not set(bm.faces[i].verts) & set(bm.faces[j].verts):
            count += 1
    return count


def inset(bm, faces, amount, depth=0.0):
    """INSET the picked faces as one region: a FLAT rim `amount` wide inside its border, then the faces inside it
    pushed `depth` along the way they look (over 0: a raised panel; under 0: a sunk one), with straight walls.
    Units: the mesh's own. -> the inner faces. Refused (ValueError) when the faces have no room for the rim."""
    if not faces:
        raise ValueError("inset: the rule picked no face")
    if not (math.isfinite(amount) and amount > 0 and math.isfinite(depth)):
        raise ValueError(f"inset: amount={amount!r} (over 0) and depth={depth!r} are studs")
    before = {f: (f.normal.copy(), f.calc_area()) for f in faces}
    bmesh.ops.inset_region(bm, faces=faces, thickness=amount, depth=0.0, use_even_offset=True, use_boundary=True)
    bm.normal_update()
    for f, (n0, a0) in before.items():
        if not f.is_valid or f.calc_area() < 1e-9 or f.normal.dot(n0) < 0.5 or f.calc_area() >= a0 * 1.0001:
            raise ValueError(f"inset: a rim of {amount:g} is more than the picked faces have room for (a direction "
                             'like "+Y" also picks narrow faces that look that way: say where the face is)')
    inner = [f for f in faces if f.is_valid]
    return push(bm, inner, depth) if abs(depth) > 1e-9 else inner


def push(bm, faces, amount):
    """PUSH the picked faces `amount` along the way they look together (over 0: out, a boss; under 0: in, a
    pocket), walls made behind them - an extrude; the walls take the pushed faces' material. Units: the mesh's
    own. -> the moved faces. Refused: a push that would lay a new wall ON a wall that is already there (a face
    at the part's own edge pushed in; a pocket's floor pushed out)."""
    if not faces:
        raise ValueError("push: the rule picked no face")
    if not (math.isfinite(amount) and abs(amount) > 1e-9):
        raise ValueError(f"push: amount={amount!r} - studs, not 0 (over 0 out, under 0 in)")
    way = Vector((0.0, 0.0, 0.0))
    for f in faces:
        way += f.normal * f.calc_area()
    if way.length < 1e-12:
        raise ValueError("push: the picked faces look every way at once (they have no common direction): pick one "
                         "side")
    way.normalize()
    mine = set(faces)
    for f in faces:
        for e in f.edges:
            for g in e.link_faces:
                # a neighbour that runs ALONG the push is a wall already there. The new wall lies on it and looks
                # the other way when the faces are pushed IN at an outer edge, or OUT at the foot of a wall.
                if g in mine or abs(g.normal.dot(way)) > ALONG:
                    continue
                if amount < 0 and e.is_convex:
                    raise ValueError("push: the picked faces reach the part's own edge - pushed in, they would "
                                     "leave a wall of no thickness there (keep a rim: a.inset first, or cut the "
                                     "face both ways and push its middle)")
                if amount > 0 and not e.is_convex:
                    raise ValueError("push: the picked faces lie at the foot of a wall (a pocket's floor, a "
                                     "step) - pushed out, the new wall would lie on that one (say where the "
                                     "faces are so the rule does not take a pocket's own walls, or make the "
                                     "pocket shallower instead)")
    slots = [f.material_index for f in faces]
    slot = max(set(slots), key=slots.count)
    ext = bmesh.ops.extrude_face_region(bm, geom=faces)
    moved = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
    tops = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMFace)]
    bmesh.ops.translate(bm, verts=moved, vec=way * amount)
    left = [f for f in faces if f.is_valid and f not in tops]
    if left:   # (the faces it started from, now inside the part)
        bmesh.ops.delete(bm, geom=left, context="FACES")
    top_set = set(tops)
    for v in moved:   # (the walls: the boss's own material all round, not each neighbour's)
        for f in v.link_faces:
            if f not in top_set:
                f.material_index = slot
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    return tops


def sharp_room(bm, angle):
    """the shortest edge that is sharp (over `angle` degrees) or meets a sharp one: a round wider than HALF of it
    runs into the round from its other end -> its length (inf when the part has no sharp edge)"""
    limit = math.radians(angle)
    sharp = [e for e in bm.edges if e.is_manifold and e.calc_face_angle(0.0) > limit]
    near = set(sharp)
    for e in sharp:
        for v in e.verts:
            near.update(v.link_edges)
    return min((e.calc_length() for e in near), default=math.inf)
