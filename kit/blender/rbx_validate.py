"""rbx_validate.py — Roblox mesh gate. Pure checks on a Blender mesh object, no side effects.

Every check returns {name, ok, severity, value, limit, fix}. `fix` is a one-line instruction a
weak model can act on without reading anything else. severity "error" fails the asset, "warn" doesn't.
"""

import math

import bmesh
import bpy

DEFAULT_LIMITS = {
    "max_tris": 20000,  # Roblox MeshPart hard cap
    "max_tex": 4096,  # Roblox says it shows a map at up to 4096 x 4096 (rbx_optimize.ROBLOX_MAX_TEX, with its sources)
    "game_tex": 4096,  # ... and the largest the kit has SEEN it keep (rbx_optimize.GAME_MAP_CAP: rbx.Asset sets it)
    "max_size_studs": 2048,  # MeshPart max dimension
    "require_manifold": True,
    "max_materials": 1,
}


def _check(name, ok, value, limit, fix, severity="error"):
    return {
        "name": name,
        "ok": bool(ok),
        "severity": severity,
        "value": value,
        "limit": limit,
        "fix": "" if ok else fix,
    }


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def size_studs(obj):
    """World-space size of the object in Roblox axes (x, y, z) = Blender (x, z, y)."""
    corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
    if not corners:
        return [0.0, 0.0, 0.0]
    xs, ys, zs = zip(*[(c.x, c.y, c.z) for c in corners])
    return [round(max(xs) - min(xs), 3), round(max(zs) - min(zs), 3), round(max(ys) - min(ys), 3)]


def center_studs(obj):
    """World-space bounding-box centre in Roblox axes: where the uploaded (re-centred) mesh must sit."""
    corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
    if not corners:
        return [0.0, 0.0, 0.0]
    xs, ys, zs = zip(*[(c.x, c.y, c.z) for c in corners])
    mid = lambda a: round((max(a) + min(a)) / 2, 4)  # noqa: E731
    return [mid(xs), mid(zs), -mid(ys)]  # Blender (x, y, z) -> Roblox (x, z, -y)


def validate_mesh(obj, limits=None):
    lim = dict(DEFAULT_LIMITS)
    lim.update(limits or {})
    checks = []
    mesh = obj.data

    tris = tri_count(obj)
    master = lim.get("max_tris") is None  # a MASTER (Asset(stage="master")): no cap — `kit optimize` makes the game mesh
    checks.append(
        _check(
            "tris",
            master or tris <= lim["max_tris"],
            tris,
            "none: a master (its game version is capped)" if master else lim["max_tris"],
            "lower segments= on cylinder/sphere/loft/tube, drop hidden detail, or split into another group=",
        )
    )

    bm = bmesh.new()
    bm.from_mesh(mesh)
    # (an edge left open by a.drop_hidden - the rim of a face no eye could reach - is meant: not a hole)
    rim = bm.edges.layers.int.get("kit_dropped")
    open_edges = sum(1 for e in bm.edges if not e.is_manifold and not e.is_wire and not (rim is not None and e[rim]))
    wire_edges = sum(1 for e in bm.edges if e.is_wire)
    loose_verts = sum(1 for v in bm.verts if not v.link_edges)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
    bm.free()
    checks.append(
        _check(
            "manifold",
            open_edges == 0 or not lim["require_manifold"],
            open_edges,
            0,
            "a mesh()/adopted object has open edges — close it (cap the ends), or pass "
            "require_manifold=False to Asset() with a comment saying why",
        )
    )
    checks.append(
        _check("wire_edges", wire_edges == 0, wire_edges, 0, "delete edges that have no faces", "warn")
    )
    checks.append(
        _check("loose_verts", loose_verts == 0, loose_verts, 0, "delete vertices with no edges", "warn")
    )
    checks.append(
        _check(
            "degenerate_faces",
            degenerate == 0,
            degenerate,
            0,
            "zero-area faces: a size of 0, two outline points on top of each other, or a cut that only grazes a "
            "face — give every size > 0 and make cutters overlap the part clearly",
            "warn",
        )
    )

    mats = [m for m in mesh.materials if m is not None]
    checks.append(
        _check(
            "materials",
            len(mats) <= lim["max_materials"],
            len(mats),
            lim["max_materials"],
            "run Asset.build() (it bakes to one material) instead of exporting by hand",
        )
    )

    uv = mesh.uv_layers.active
    if uv is None:
        checks.append(_check("uv", False, "missing", "0..1", "run Asset.build(); it UV-unwraps before baking"))
    else:
        out = 0
        eps = 1e-4
        for d in uv.data:
            u, v = d.uv
            if u < -eps or u > 1 + eps or v < -eps or v > 1 + eps:
                out += 1
        fix = "UVs outside 0..1 — re-unwrap (smart project) before baking"
        if out:   # (is it a map too SMALL for its islands? each needs a cell with its pad - card a2ym)
            tex_ = max((max(tuple(nd.image.size)) for m in mats if m.use_nodes for nd in m.node_tree.nodes
                        if nd.type == "TEX_IMAGE" and nd.image is not None), default=0)
            k_ = uv_islands(mesh)
            need = int(k_ * (1 + 2 * UV_PAD_PX) ** 2)
            if tex_ and need > tex_ * tex_:
                fix = (f"the map is too SMALL for its {k_} islands: each needs a {1 + 2 * UV_PAD_PX:.0f} x "
                       f"{1 + 2 * UV_PAD_PX:.0f}-texel cell with its pad - {need:,} texels on a {tex_} x {tex_} map "
                       f"({tex_ * tex_:,}): give the group a map of {_pow2_at_least(math.sqrt(need))} or more "
                       "(a.group_texture), or fewer islands (a.seams, a coarser part)")
        checks.append(_check("uv", out == 0, out, 0, fix))

    sizes = []
    for m in mats:
        if not m.use_nodes:
            continue
        for node in m.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                sizes.append(tuple(node.image.size))
    biggest = max((max(s) for s in sizes), default=0)
    pow2 = all(s[0] > 0 and (s[0] & (s[0] - 1)) == 0 and (s[1] & (s[1] - 1)) == 0 for s in sizes)
    checks.append(
        _check("texture_size", biggest <= lim["max_tex"], biggest, lim["max_tex"],
               f"use Asset(tex=) of {lim['max_tex']} at most: Roblox shows no map larger")
    )
    checks.append(_check("texture_pow2", pow2, sizes, "power of two", "use tex=256/512/1024/2048/4096", "warn"))
    game_tex = lim.get("game_tex", 4096)
    checks.append(
        _check(
            "texture_roblox",
            master or biggest <= game_tex,
            biggest,
            game_tex,
            f"a game map above {game_tex} has not been seen to arrive whole: {game_tex} is the largest the kit's own "
            f"test upload showed in Studio (rbx_optimize.GAME_MAP_CAP, 2026-11-12) - tex={game_tex} at most, and a "
            f"part that needs more in a group of its own",
            "warn",
        )
    )

    size = size_studs(obj)
    big = max(size)
    checks.append(
        _check(
            "size_studs",
            0 < big <= lim["max_size_studs"],
            size,
            lim["max_size_studs"],
            "authoring is in studs: a value is off by a factor (check you did not author in cm/meters)",
        )
    )
    if not math.isfinite(big):
        checks[-1]["ok"] = False
    return {"tris": tris, "size_studs": size, "checks": checks}


REPORT_ONLY = frozenset({"quality", "detail", "texel_bar"})   # (mission 01-3d 5.10/5.11: the score and the small-part count are reports, never the target)


def verdict(results, design=None):
    """results: {group: validate_mesh(...)}, design: rbx_critic checks -> (status, summary, next_action).
    Errors fail the asset. Warnings pass, but next_action names the first one: it is the next improvement."""
    errors = []
    warns = []
    for group, res in results.items():
        for c in res["checks"]:
            if c["ok"]:
                continue
            (errors if c["severity"] == "error" else warns).append((group, c))
    for c in design or []:
        if not c["ok"]:
            (errors if c["severity"] == "error" else warns).append(("design", c))
    # a REPORT (the score) is listed last and is never the next step while a real check is open: its advice chased
    # numbers ("4+ kinds of small detail: screws, latches, LEDs") and bricked the starter props (owner 0.1/10)
    warns.sort(key=lambda gc: gc[1]["name"] in REPORT_ONLY)
    if errors:
        group, first = errors[0]
        summary = "; ".join(f"{g}.{c['name']}={c['value']} (limit {c['limit']})" for g, c in errors)
        if warns:  # a failing build still shows its taste problems: fix them in the same pass
            summary += f" (+{len(warns)} warning(s): {', '.join(c['name'] for _, c in warns)})"
        return "fail", summary, f"[{group}] {first['fix']}"
    parts = [f"{g}: {r['tris']} tris, {r['size_studs']} studs" for g, r in results.items()]
    summary = " | ".join(parts) + (f" ({len(warns)} warning(s): {', '.join(c['name'] for _, c in warns)})" if warns else "")
    if warns:
        group, first = warns[0]
        return "pass", summary, f"improve [{group}.{first['name']}]: {first['fix']} — then look at the sheet again"
    return "pass", summary, "look at the preview sheet against the design; then import FBX + textures per the manifest"


def mesh_objects():
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


UV_PAD_PX = 4.0   # the pad round every island the kit's packer keeps (texels; rbx.UV_PAD_PX)


def _pow2_at_least(x):
    p = 1
    while p < x:
        p *= 2
    return p


def uv_islands(mesh):
    """how many islands a mesh's UVs make: faces joined where an edge's two corners have the same UVs on both sides"""
    uv = mesh.uv_layers.active
    if uv is None or not mesh.polygons:
        return 0
    parent = list(range(len(mesh.polygons)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    at = {}
    for p in mesh.polygons:
        for li, vi in zip(p.loop_indices, p.vertices):
            key = (vi, round(uv.data[li].uv[0], 6), round(uv.data[li].uv[1], 6))
            j = at.setdefault(key, p.index)
            if j != p.index:
                parent[find(p.index)] = find(j)
    return len({find(i) for i in range(len(mesh.polygons))})
