"""rbx_cage.py — the SUBDIVISION CAGE route for soft-hard parts (a grip, a hammer, an ornate frame, a game gun's body):
a low quad cage from a traced outline, HOLDING LOOPS `soft` mm inside every edge (the rims of both caps and the side
wall's two ends), then Catmull-Clark subdivision. What comes out is smooth everywhere and crisp exactly where a loop
holds it — the look of game art ("most parts of the gun are all smooth edges", the owner, 2026-10-22), which CAD
fillets on traced outlines refused and a mesh bevel only imitates at the edges.

    bm = cage_mesh(outline_mm, depth_mm, soft_mm=1.5, levels=2, crisp_corners=False, mm=280.0)

outline_mm: a closed polyline in the part's XY (a side profile, mm); the part is `depth_mm` thick along Z, centred
on z = 0. Corners (a turn over 35 deg) stay cage vertices; crisp_corners=True creases the side wall there (a cut
corner keeps its point in XY). Returns a bmesh in studs (mm / `mm`). Asset.cage() places it.
"""

import math

import bmesh
import bpy


def _turn(p, i):
    n = len(p)
    ax, ay = p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]
    bx, by = p[(i + 1) % n][0] - p[i][0], p[(i + 1) % n][1] - p[i][1]
    return abs(math.degrees(math.atan2(ax * by - ay * bx, ax * bx + ay * by)))


def resample(outline, step, corner_deg=35.0):
    """the outline at even spacing ~step, every corner (a turn over corner_deg) kept as a vertex"""
    p = [(float(x), float(y)) for x, y in outline]
    if len(p) > 2 and math.dist(p[0], p[-1]) < 1e-6:
        p.pop()
    n = len(p)
    corners = [i for i in range(n) if _turn(p, i) > corner_deg] or [0]
    out = []
    for k, c in enumerate(corners):
        nxt = corners[(k + 1) % len(corners)]
        run = [p[j % n] for j in range(c, (nxt if nxt > c else nxt + n) + 1)]
        seg = [math.dist(run[i], run[i + 1]) for i in range(len(run) - 1)]
        total = sum(seg)
        m = max(1, round(total / step))
        for s in range(m):
            t, acc = total * s / m, 0.0
            for i, L in enumerate(seg):
                if acc + L >= t - 1e-9:
                    f = (t - acc) / L if L > 0 else 0.0
                    out.append((run[i][0] + (run[i + 1][0] - run[i][0]) * f, run[i][1] + (run[i + 1][1] - run[i][1]) * f,
                                s == 0))
                    break
                acc += L
    return out  # [(x, y, is_corner)]


def _area(p):
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def inset(p, d):
    """a closed polygon offset INWARD by d (mitred, the miter clamped to 3 d)"""
    n = len(p)
    ccw = _area(p) > 0
    out = []
    for i in range(n):
        a, b, c = p[i - 1], p[i], p[(i + 1) % n]

        def nrm(u, v):
            dx, dy = v[0] - u[0], v[1] - u[1]
            L = math.hypot(dx, dy) or 1.0
            return (-dy / L, dx / L) if ccw else (dy / L, -dx / L)  # (the inward normal)
        n1, n2 = nrm(a, b), nrm(b, c)
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        L = math.hypot(mx, my)
        if L < 1e-9:
            mx, my, L = n1[0], n1[1], 1.0
        mx, my = mx / L, my / L
        cosh = max(mx * n1[0] + my * n1[1], 1.0 / 3.0)
        out.append((b[0] + mx * d / cosh, b[1] + my * d / cosh))
    return out


def cage_mesh(outline_mm, depth_mm, soft_mm=1.5, levels=2, crisp_corners=False, mm=280.0, step_mm=None):
    """the cage (rings: front rim, front holding loop on the cap, side wall's two holding loops, back ones), each cap
    an n-gon inside its holding loop, subdivided `levels` times (Catmull-Clark) -> bmesh in studs"""
    d, s = float(depth_mm), float(soft_mm)
    if d <= 2 * s:
        raise ValueError(f"cage: depth {d} mm must be over twice soft_mm ({s})")
    ring = resample(outline_mm, step_mm or max(2.0 * s, 0.5))
    xy = [(x, y) for x, y, _c in ring]
    corner = [c for _x, _y, c in ring]
    cap_in = inset(xy, s)
    zf, zb = d / 2, -d / 2
    loops = [  # (points, z): from the front cap's holding loop round the rim and side to the back's
        (cap_in, zf), (xy, zf), (xy, zf - s), (xy, zb + s), (xy, zb), (cap_in, zb)]
    bm = bmesh.new()
    vs = [[bm.verts.new((x / mm, y / mm, z / mm)) for x, y in pts] for pts, z in loops]
    n = len(xy)
    ccw = _area(xy) > 0
    for L in range(len(vs) - 1):
        a, b = vs[L], vs[L + 1]
        for i in range(n):
            j = (i + 1) % n
            quad = (a[i], a[j], b[j], b[i])
            bm.faces.new(quad if ccw else quad[::-1])
    front = bm.faces.new(vs[0][::-1] if ccw else vs[0])
    back = bm.faces.new(vs[-1] if ccw else vs[-1][::-1])
    # a concave cap's n-gon has its centre OUTSIDE it (Catmull-Clark would bulge there): ear-clipped, joined into
    # quads — a flat cap subdivides flat whatever its topology
    tri = bmesh.ops.triangulate(bm, faces=[front, back], quad_method="BEAUTY", ngon_method="EAR_CLIP")
    bmesh.ops.join_triangles(bm, faces=tri["faces"], angle_face_threshold=math.radians(5),
                             angle_shape_threshold=math.radians(180))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if crisp_corners:
        cr = bm.edges.layers.float.get("crease_edge") or bm.edges.layers.float.new("crease_edge")
        for i in range(n):
            if not corner[i]:
                continue
            for L in range(1, 4):  # (the side wall's vertical edges at the corner)
                e = bm.edges.get((vs[L][i], vs[L + 1][i]))
                if e is not None:
                    e[cr] = 1.0
    _ = (front, back)
    me = bpy.data.meshes.new("_kit_cage")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("_kit_cage", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("subsurf", "SUBSURF")
    mod.levels = mod.render_levels = int(levels)
    mod.subdivision_type = "CATMULL_CLARK"
    if hasattr(mod, "use_creases"):
        mod.use_creases = True
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    out_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    out = bmesh.new()
    out.from_mesh(out_me)
    bpy.data.meshes.remove(out_me)
    return out
