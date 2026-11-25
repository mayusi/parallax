"""rbx_critic.py — design gates: measured facts about a model BEFORE its parts are joined.

The mesh gate (rbx_validate) answers "will Roblox accept it?". This answers "is it built right?": parts that
float in the air, parts buried inside others, a model the wrong size for its job, one flat colour, no small
detail, broken symmetry. A model can't see its own model; these numbers are its eyes. Every check returns
{name, ok, severity, value, limit, fix} like rbx_validate, so the verdict prints one actionable next step.
"""

import math

from mathutils import Vector
from mathutils.bvhtree import BVHTree

import rbx_sizes

R6_HEIGHT = 5.0  # studs, an R6 character standing


def _check(name, ok, value, limit, fix, severity="error"):
    return {"name": name, "ok": bool(ok), "severity": severity, "value": value, "limit": limit, "fix": "" if ok else fix}


def base_name(name):
    return name.split("~")[0]


class _Part:
    def __init__(self, obj, group):
        self.name = obj.name
        self.group = group
        m = obj.matrix_world
        self.verts = [m @ v.co for v in obj.data.vertices]  # Blender world space
        polys = [list(p.vertices) for p in obj.data.polygons]
        self.tris = sum(len(p) - 2 for p in polys)
        self.bvh = BVHTree.FromPolygons(self.verts, polys, epsilon=0.0) if polys else None
        self.lo = Vector([min(v[i] for v in self.verts) for i in range(3)])
        self.hi = Vector([max(v[i] for v in self.verts) for i in range(3)])
        self.diag = (self.hi - self.lo).length
        self.mat = obj.data.materials[0].name if obj.data.materials else None
        # signed volume (divergence theorem): negative = the faces point INWARD (Roblox culls them -> invisible)
        vol = 0.0
        for p in polys:
            a = self.verts[p[0]]
            for i in range(1, len(p) - 1):
                vol += a.dot(self.verts[p[i]].cross(self.verts[p[i + 1]])) / 6
        self.volume = vol

    def sample(self, n):
        step = max(1, len(self.verts) // n)
        return self.verts[::step]


def _boxes_near(a, b, tol):
    return all(a.lo[i] - tol <= b.hi[i] and b.lo[i] - tol <= a.hi[i] for i in range(3))


def _inside(point, part):
    """Ray parity test against a closed mesh."""
    if part.bvh is None:
        return False
    d = Vector((0.5773, 0.5779, 0.5767)).normalized()
    origin, hits = point.copy(), 0
    for _ in range(64):
        loc, _, _, _ = part.bvh.ray_cast(origin, d)
        if loc is None:
            break
        hits += 1
        origin = loc + d * 1e-4
    return hits % 2 == 1


def _touch(a, b, tol):
    if a.bvh is None or b.bvh is None or not _boxes_near(a, b, tol):
        return False
    if a.bvh.overlap(b.bvh):
        return True
    for x, y in ((a, b), (b, a)):
        for v in x.sample(300):
            if y.bvh.find_nearest(v, tol)[0] is not None:
                return True
    return _inside(a.verts[0], b) or _inside(b.verts[0], a)


def _hidden_in(a, b):
    """a sits entirely inside b (its triangles cost tris but can never be seen)."""
    if not all(b.lo[i] <= a.lo[i] and a.hi[i] <= b.hi[i] for i in range(3)):
        return False
    if a.bvh.overlap(b.bvh):
        return False
    return all(_inside(v, b) for v in a.sample(40))


def _lum(color):
    r, g, b = color[:3]
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) ** (1 / 2.2)


def critique(parts, mats, design):
    """parts: [(obj, group)], mats: {name: {"mat", "color", ...}}, design: Asset.design.
    Returns (checks, facts)."""
    ps = [_Part(o, g) for o, g in parts if len(o.data.vertices) > 0]
    checks, facts = [], {}
    if not ps:
        return checks, facts
    lo = Vector([min(p.lo[i] for p in ps) for i in range(3)])
    hi = Vector([max(p.hi[i] for p in ps) for i in range(3)])
    ext = hi - lo
    size = [round(ext.x, 2), round(ext.z, 2), round(ext.y, 2)]  # Roblox (x, y, z)
    diag = max(ext.length, 1e-6)
    # "touching" means touching: a gap you can SEE in a close-up is a gap (a 5-stud rifle allows 0.01 studs)
    tol = min(0.01, max(0.002, diag * 0.002))
    facts["size_studs"] = size
    facts["vs_r6_character"] = f"{size[1] / R6_HEIGHT:.2f}x as tall as an R6 character (5 studs)"
    facts["parts"] = len(ps)

    # ---- connectivity: union-find over touching parts
    parent = list(range(len(ps)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(ps)):
        for j in range(i + 1, len(ps)):
            if find(i) != find(j) and _touch(ps[i], ps[j], tol):
                parent[find(i)] = find(j)
    comps = {}
    for i, p in enumerate(ps):
        comps.setdefault(find(i), []).append(p)
    main = max(comps.values(), key=lambda c: sum(p.diag**3 for p in c))
    allowed = design.get("allow_floating", set())
    floating = sorted(
        {base_name(p.name) for c in comps.values() if c is not main for p in c} - set(allowed)
    )
    facts["floating"] = floating
    # how far each detached cluster hovers from the main body (so the fix is a number, not a guess)
    gaps = []
    for c in comps.values():
        if c is main or not ({base_name(p.name) for p in c} - set(allowed)):
            continue
        best = None
        for p in c:
            for v in p.sample(120):
                for q in main:
                    hit = q.bvh.find_nearest(v) if q.bvh else None
                    if hit and hit[0] is not None:
                        d = (hit[0] - v).length
                        if best is None or d < best[0]:
                            best = (d, p.name, q.name)
        if best:
            names = sorted({base_name(p.name) for p in c})
            gaps.append(f"{'+'.join(names[:4])}{'...' if len(names) > 4 else ''} hovers {best[0]:.3f} studs from {base_name(best[2])}")
    facts["floating_gaps"] = gaps
    checks.append(
        _check(
            "floating_parts",
            not floating,
            gaps or floating,
            "every part connects to the body",
            f"detached: {'; '.join(gaps[:3]) or ', '.join(floating[:4])} — a cluster that only touches itself still "
            "floats: extend its mounts/legs INTO the body (overlap a little), or list it in Asset(allow_floating=[...])",
        )
    )

    # ---- which parts carry zero-area faces (the joined-mesh gate can only count them; this names them)
    degenerate = []
    for o, _g in parts:
        bad = [poly for poly in o.data.polygons if poly.area < 1e-9]
        if bad:
            c = o.matrix_world @ bad[0].center  # Blender -> Roblox (x, z, -y)
            degenerate.append(f"{o.name} ({len(bad)}, first at x={c.x:.2f} y={c.z:.2f} z={-c.y:.2f})")
    facts["degenerate_parts"] = degenerate
    # ---- which parts have open (non-manifold) edges: name + where, so a failed manifold gate is fixable
    import bmesh

    open_parts = []
    for o, _g in parts:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bad = [e for e in bm.edges if not e.is_manifold]
        if bad:
            c = o.matrix_world @ ((bad[0].verts[0].co + bad[0].verts[1].co) / 2)
            open_parts.append(f"{o.name} ({len(bad)} open edges, first at x={c.x:.2f} y={c.z:.2f} z={-c.y:.2f})")
        bm.free()
    facts["open_parts"] = open_parts

    # ---- inside-out parts (closed meshes with inward normals render as holes in Roblox)
    inverted = sorted(p.name for p in ps if p.volume < -1e-9)
    facts["inside_out"] = inverted
    checks.append(
        _check(
            "inside_out",
            not inverted,
            inverted,
            "normals point out",
            f"{', '.join(inverted[:4])} face inward (Roblox hides those faces) — a raw a.mesh() with reversed faces, "
            "or a mirrored copy; report it if it came from the kit's own tools",
        )
    )

    # ---- hidden parts (fully buried inside another)
    hidden = []
    internal = design.get("internal", set())  # a.internal(): mechanism parts that are MEANT to be inside
    for a in ps:
        if base_name(a.name) in internal:
            continue
        for b in ps:
            if a is not b and a.diag < b.diag and _hidden_in(a, b):
                hidden.append(f"{base_name(a.name)} in {base_name(b.name)}")
                break
    facts["hidden"] = hidden
    checks.append(
        _check(
            "hidden_parts",
            not hidden,
            hidden,
            "none",
            f"{hidden[0] if hidden else ''} is completely buried — it costs tris and is never seen; delete or move it",
            "warn",
        )
    )

    # ---- size vs the design target
    target = design.get("size")
    kind = design.get("kind")
    if target:
        ratios = [size[i] / target[i] if target[i] > 0 else 1.0 for i in range(3)]
        worst = max(range(3), key=lambda i: abs(ratios[i] - 1))
        off = abs(ratios[worst] - 1) > 0.25
        axis = "XYZ"[worst]
        checks.append(
            _check(
                "size_vs_target",
                not off,
                size,
                list(target),
                f"{axis} is {ratios[worst]:.2f}x the target ({size[worst]} vs {target[worst]} studs) — rescale "
                f"the {axis} positions/sizes, or change Asset(size=...) if the design changed on purpose",
            )
        )
    else:
        typ = rbx_sizes.typical(kind, mm_per_stud=design.get("mm_per_stud")) if kind else None
        hint = (
            f"a {kind} is about {' x '.join('any' if v is None else f'{v:g}' for v in typ)} studs (wide x tall x "
            "deep, kit/real_sizes.json)"
            if typ
            else "a door is 4x7, a sword ~1x4.5x0.3, an R6 is 5 tall"
        )
        checks.append(
            _check(
                "size_vs_target",
                False,
                size,
                "Asset(size=(x, y, z))",
                f"no target size — decide it first ({hint}) and pass Asset(size=...) so proportions are checked",
                "warn",
            )
        )

    # ---- size vs the real world: what the object IS (Asset(kind=...)) against the range real ones come in — the
    # target above can be the mistake too. Ranges read from Infinigen (kit/real_sizes.json); a warning: a throne is a chair
    if kind:
        ok, fix, fact = rbx_sizes.judge(size, kind, mm_per_stud=design.get("mm_per_stud"))
        if fact:
            facts["real_size"] = fact
        checks.append(_check("size_plausible", bool(ok), size, kind, fix, "warn"))

    # ---- grounded
    if design.get("ground", True):
        base = round(lo.z, 3)  # Blender z == Roblox y
        checks.append(
            _check(
                "grounded",
                abs(base) <= 0.05,
                base,
                0,
                f"the lowest point is at y={base} — shift everything by {-base:+.2f} so it rests on y=0 "
                "(handheld item? Asset(ground=False))",
                "warn",
            )
        )

    # ---- palette
    names = [m for m in mats if any(p.mat == mats[m]["mat"].name for p in ps)]
    lums = [_lum(mats[m]["color"]) for m in names]
    contrast = round(max(lums) - min(lums), 3) if lums else 0
    facts["materials"] = names
    facts["value_contrast"] = contrast
    if len(names) <= 1:
        checks.append(
            _check(
                "palette",
                len(ps) < 4,
                names,
                ">= 2 materials",
                f"{len(ps)} parts in one material reads as a plastic blob — add a darker trim/accent material "
                "for edges, grips, bolts or panels",
                "warn",
            )
        )
    else:
        checks.append(
            _check(
                "palette",
                contrast >= 0.12,
                contrast,
                0.12,
                "every material has nearly the same brightness — make the trim/accent clearly darker or lighter "
                "(value contrast is what reads at a distance, not hue)",
                "warn",
            )
        )

    # ---- detail tiers (big shapes / medium / small details)
    tiers = {"primary": 0, "secondary": 0, "detail": 0}
    for p in ps:
        r = p.diag / diag
        tiers["primary" if r >= 0.5 else "secondary" if r >= 0.15 else "detail"] += 1
    facts["tiers"] = tiers
    checks.append(
        _check(
            "detail",
            tiers["detail"] >= 3 or len(ps) < 3,
            tiers,
            ">= 3 small details",
            # (a REPORT, never the next step — rbx_validate.REPORT_ONLY: "add 3+ small parts" is how builders greebled
            #  the starter props to an owner 0.1/10; the real object decides what small parts there are)
            "fewer than 3 small parts — only where the REAL object has them (its fasteners, trims, labels, at their "
            "measured place: look at the references); never add parts the object does not have to clear this",
            "warn",
        )
    )

    # ---- symmetry
    if design.get("symmetric"):
        cx = (lo.x + hi.x) / 2
        samples = [v for p in ps for v in p.sample(200)]
        good = 0
        for v in samples:
            m = Vector((2 * cx - v.x, v.y, v.z))
            if any(p.bvh and p.bvh.find_nearest(m, tol * 3)[0] is not None for p in ps):
                good += 1
        score = round(good / max(1, len(samples)), 3)
        facts["symmetry"] = score
        checks.append(
            _check(
                "symmetry",
                score >= 0.9,
                score,
                0.9,
                "left and right don't match — build one side inside `with a.mirror(\"X\"):` so the other is exact",
                "warn",
            )
        )
    # PLAUSIBILITY (would the real object be made this way?)
    split = design.get("split_cuts") or []
    checks.append(_check("cut_through", not split, split[:4] or "no cut splits a part", "a cut carves INTO a part",
                         f"{'; '.join(split[:4])} — a groove or slot went right through: cut shallower, or build the "
                         "pieces as separate parts on purpose", "warn"))
    grooves = list(design.get("wood_grooves") or [])
    lines = design.get("wood_lines") or []
    if len(lines) >= 3:  # (named from 3: a pattern of seams — the score counts every line with the grooves, 4+ charge)
        grooves.append(f"{len(lines)} lines baked on wood ({', '.join(sorted(set(lines))[:3])}...)")
    checks.append(_check("wood_grooves", not grooves, grooves[:4] or "no grooves carved into wood",
                         "wood gets boards, not carved grooves",
                         f"{'; '.join(grooves[:4])} — wood is not hard-surface: make each board its own part (small gaps "
                         "over a dark core read as seams) and let material(pattern=\"wood\") carry the grain — a seam "
                         "baked on (a floater) draws the same groove into its maps", "warn"))
    # a material NAMED like a real substance must look like it (measured values: rbx_materials, physicallybased.info):
    # "gold" that is yellow plastic, "steel" that is not a metal
    import rbx_materials  # noqa: PLC0415

    wrong = [w for w in (rbx_materials.check(k, v.get("color", (0.5, 0.5, 0.5)), v.get("metal", 0.0))
                         for k, v in mats.items()) if w]
    checks.append(_check("material_values", not wrong, wrong[:4] or "every named material looks like the real one",
                         "a material named after a real substance has its measured colour and metalness",
                         f"{'; '.join(wrong[:3])}", "warn"))
    # ...and EVERY material must be one a real surface could be (rbx_pbr: metalness 0 or 1, a metal's base 180-255
    # sRGB, a non-metal's 30-240): a "metal" at 60 sRGB reads murky plastic — a dark gun finish is a coating, metal 0.
    # Judged: the materials the parts and floaters wear. a.material(..., pbr=False) opts one out (stylised on purpose)
    import rbx_pbr  # noqa: PLC0415

    quality = design.get("quality", "prop")
    worn = {m.name for o, _g in parts for m in o.data.materials if m} | set(design.get("floater_materials") or ())
    bad, waived, satin = [], [], []
    for k, v in mats.items():
        if v["mat"].name not in worn:
            continue
        if not v.get("pbr", True):
            waived.append(k)
            continue
        if v.get("satin"):
            satin.append(k)
        bad += rbx_pbr.judge(k, v.get("color", (0.5, 0.5, 0.5)), v.get("metal", 0.0), v.get("rough", 0.6),
                             satin=v.get("satin", False), strict=quality == "aaa", glow=v.get("emit", 0.0) > 0,
                             clear=v.get("alpha", 1.0) < 1.0)
        if v.get("chip", 0.0) > 0:
            bad += rbx_pbr.judge_under(k, v.get("under", (0.56, 0.57, 0.6)))
    facts["pbr"] = {"judged": sorted(k for k, v in mats.items() if v["mat"].name in worn and v.get("pbr", True)),
                    "opted_out": sorted(waived), "satin": sorted(satin), "problems": [rbx_pbr.say(p) for p in bad]}
    lo = rbx_pbr.NONMETAL_STRICT_SRGB if quality == "aaa" else rbx_pbr.NONMETAL_SRGB[0]
    checks.append(_check("pbr_values", not bad, [f"{p['material']}: {p['what']}" for p in bad[:6]] or
                         "every material a real surface could be",
                         f"metalness 0 or 1; a metal's base {rbx_pbr.METAL_SRGB[0]}-255 sRGB, a non-metal's "
                         f"{lo}-{rbx_pbr.NONMETAL_SRGB[1]}",
                         "; ".join(rbx_pbr.say(p) for p in bad[:3]) + (f" (+{len(bad) - 3} more: facts.pbr)"
                                                                       if len(bad) > 3 else ""),
                         "error" if quality in ("hero", "aaa") else "warn"))
    tiny = design.get("tiny_cuts") or []
    if design.get("stage") == "master":
        # a MASTER is the no-limits original: a real recess is what it is for (triangles are free there); the game
        # version (kit optimize) bakes these, so they stay listed — never a warning on the master itself
        facts["master_fine_cuts"] = tiny
        tiny = []
    checks.append(_check("tiny_cuts", not tiny, tiny[:6] or "no cut smaller than a finger",
                         "detail smaller than a finger is baked, not cut",
                         f"{'; '.join(tiny[:4])}{' ...' if len(tiny) > 4 else ''} — a recess this small costs triangles "
                         "for what the normal map shows as well: model it ON the surface inside `with a.floaters():` "
                         "(a dark disc for a pin hole, a slot plate, a screw head) — baked into the maps, zero "
                         "triangles; keep cuts for what the outline or a see-through opening needs", "warn"))
    return checks, facts
