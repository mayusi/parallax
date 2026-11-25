"""rbx_parts.py — proven detail parts for rbx.Asset. Detail is what makes a model read as "finished": bolts,
grips, vents, panel lines, rivets, frames, lights, wheels, handles. Each is a function that builds through the
normal Asset API, so frames, mirror() and the gates all apply. Positions are Roblox studs in the current frame.

    import rbx, rbx_parts as P
    P.bolts(a, "Bolt", [(1, 2, -1.01), (-1, 2, -1.01)], "steel", facing="-Z")
    P.vent(a, "Body", "Vent", center=(0, 2, -1), size=(1.2, 0.8), facing="-Z", mat="dark")

facing: the direction a surface detail points OUT of the surface: "-Z" (front), "+Z" (back), "+X" (right),
"-X" (left), "+Y" (up), "-Y" (down). Put `pos` ON the surface; the part sits half in, half out.
"""

import math

_FACING = {
    "-Z": ("Z", (0, 0, -1)),
    "+Z": ("Z", (0, 0, 1)),
    "+X": ("X", (1, 0, 0)),
    "-X": ("X", (-1, 0, 0)),
    "+Y": ("Y", (0, 1, 0)),
    "-Y": ("Y", (0, -1, 0)),
}


def _facing(facing):
    if facing not in _FACING:
        raise ValueError(f'facing must be one of {", ".join(_FACING)} (got "{facing}")')
    return _FACING[facing]


def _add(p, d, k):
    return tuple(p[i] + d[i] * k for i in range(3))


def bolt(a, name, pos, mat, facing="-Z", radius=0.08, height=0.06):
    """Hex bolt head sitting on a surface."""
    axis, d = _facing(facing)
    return a.cylinder(name, radius, height, _add(pos, d, height * 0.25), mat, axis=axis, segments=6, bevel=height * 0.25)


def bolts(a, prefix, positions, mat, facing="-Z", radius=0.08, height=0.06):
    """Several bolts: names prefix1, prefix2, ..."""
    return [bolt(a, f"{prefix}{i + 1}", p, mat, facing, radius, height) for i, p in enumerate(positions)]


def rivets(a, prefix, start, end, count, mat, facing="-Z", radius=0.05, sunk=None, segments=8):
    """A row of small domes from start to end (seams, armour plates, hulls). start / end on the surface: with `sunk`
    (0..1 of the radius, 0.4 a riveted head) each dome is pushed out along `facing` so only that much is in the plate
    (a sphere centred ON the face is >50% inside it: the fastener_seat gate calls it buried); None = centred (old).
    `segments` 16 for a close-up: 8 reads faceted and its 45-degree facets are hard edges to the bevel gate."""
    out = []
    push = [0.0, 0.0, 0.0]
    if sunk is not None:
        push["XYZ".index(facing[-1].upper())] = (-1.0 if facing.startswith("-") else 1.0) * radius * (1 - sunk)
    for i in range(count):
        t = i / max(1, count - 1)
        p = tuple(start[k] + (end[k] - start[k]) * t + push[k] for k in range(3))
        out.append(a.sphere(f"{prefix}{i + 1}", radius, p, mat, scale=(1, 1, 1), segments=segments,
                            rings=max(4, segments // 2)))
    return out


def grip(a, name, bottom, length, radius, mat, wrap_mat, wraps=4, axis="Y"):
    """Handle/grip with raised wraps (swords, tools, bats, torches). `bottom` is the lower end's centre."""
    ax = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis]
    out = [a.cylinder(name, radius, length, _add(bottom, ax, length / 2), mat, axis=axis, segments=12)]
    for i in range(wraps):
        t = (i + 0.5) / wraps
        out.append(
            a.cylinder(f"{name}Wrap{i + 1}", radius * 1.12, length * 0.07, _add(bottom, ax, length * t), wrap_mat, axis=axis, segments=12)
        )
    return out


def panel_line(a, target, name, start, end, mat, width=0.05, depth=0.04, facing="-Z"):
    """Thin groove cut into `target` along a surface from start to end (both ON the surface): breaks big flat
    areas into plates — the cheapest way to make a hull, wall or crate look engineered."""
    axis, d = _facing(facing)
    dx, dy, dz = (end[i] - start[i] for i in range(3))
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    mid = tuple((start[i] + end[i]) / 2 for i in range(3))
    # groove box: long along the line, `width` across, `depth*2` into the surface (half is outside: clean cut)
    if axis == "Z":
        size, rot = (length, width, depth * 2), (0, 0, math.degrees(math.atan2(dy, dx)))
    elif axis == "X":
        size, rot = (depth * 2, width, length), (-math.degrees(math.atan2(dy, dz)), 0, 0)
    else:
        size, rot = (length, depth * 2, width), (0, -math.degrees(math.atan2(-dz, dx)), 0)
    return a.cut(target, a.box(name, size, mid, mat, rot=rot, bevel=0))


def vent(a, target, name, center, size, mat, facing="-Z", slats=4, depth=0.12):
    """Slotted vent cut into `target`: `slats` horizontal slots filling size=(width, height) on the surface."""
    axis, d = _facing(facing)
    w, h = size
    gap = h / (slats * 2 - 1)
    for i in range(slats):
        y = center[1] + h / 2 - gap / 2 - i * gap * 2
        if axis == "Z":
            box = (w, gap, depth * 2)
        elif axis == "X":
            box = (depth * 2, gap, w)
        else:
            raise ValueError("vent: facing must be a side (±X or ±Z)")
        a.cut(target, a.box(f"{name}{i + 1}", box, (center[0], y, center[2]), mat, bevel=0))


def frame(a, name, size, pos, mat, thickness=0.2, depth=0.2, facing="-Z"):
    """Rectangular border (door/window/screen/crate frame). size=(width, height) on a ±Z or ±X surface."""
    axis, d = _facing(facing)
    w, h = size
    t = thickness
    out = []
    for nm, s, off in (
        ("Top", (w, t), (0, h / 2 - t / 2)),
        ("Bottom", (w, t), (0, -h / 2 + t / 2)),
        ("Left", (t, h - 2 * t), (-w / 2 + t / 2, 0)),
        ("Right", (t, h - 2 * t), (w / 2 - t / 2, 0)),
    ):
        if axis == "Z":
            p = (pos[0] + off[0], pos[1] + off[1], pos[2] + d[2] * depth / 2)
            out.append(a.box(f"{name}{nm}", (s[0], s[1], depth), p, mat))
        else:
            p = (pos[0] + d[0] * depth / 2, pos[1] + off[1], pos[2] + off[0])
            out.append(a.box(f"{name}{nm}", (depth, s[1], s[0]), p, mat))
    return out


def light(a, name, pos, radius, housing_mat, lens_mat, facing="-Z"):
    """Housing ring + domed lens (headlights, lamps, indicator lights, sci-fi panels)."""
    axis, d = _facing(facing)
    out = [a.cylinder(f"{name}Housing", radius * 1.25, radius * 0.5, _add(pos, d, radius * 0.2), housing_mat, axis=axis, segments=16)]
    scale = {"X": (0.45, 1, 1), "Y": (1, 0.45, 1), "Z": (1, 1, 0.45)}[axis]
    out.append(a.sphere(f"{name}Lens", radius, _add(pos, d, radius * 0.45), lens_mat, scale=scale, segments=16, rings=8))
    return out


def wheel(a, name, pos, radius, width, tire_mat, rim_mat, axis="X", spokes=5):
    """Tire + recessed rim + hub + lug bolts. axis = the axle direction (X for a car facing -Z)."""
    out = [a.cylinder(f"{name}Tire", radius, width, pos, tire_mat, axis=axis, segments=24, bevel=radius * 0.18)]
    ax = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis]
    for side in (-1, 1):
        face = _add(pos, ax, side * width / 2)
        out.append(a.cylinder(f"{name}Rim{'L' if side < 0 else 'R'}", radius * 0.62, width * 0.12, face, rim_mat, axis=axis, segments=20))
        out.append(a.cylinder(f"{name}Hub{'L' if side < 0 else 'R'}", radius * 0.2, width * 0.2, _add(face, ax, side * width * 0.06), rim_mat, axis=axis, segments=12))
        for k in range(spokes):
            ang = 2 * math.pi * k / spokes
            u, v = math.cos(ang) * radius * 0.4, math.sin(ang) * radius * 0.4
            off = {"X": (0, u, v), "Y": (u, 0, v), "Z": (u, v, 0)}[axis]
            p = tuple(face[i] + off[i] + ax[i] * side * width * 0.07 for i in range(3))
            out.append(a.cylinder(f"{name}Lug{'L' if side < 0 else 'R'}{k + 1}", radius * 0.06, width * 0.06, p, rim_mat, axis=axis, segments=6, bevel=0))
    return out


def handle(a, name, a_end, b_end, mat, radius=0.08, lift=0.35, facing="-Z", segments=8):
    """U-shaped grab handle between two points on a surface, standing `lift` studs out of it. Each end sinks `radius`
    into the surface, so put a_end / b_end exactly ON a real face (a board, or a mount plate — mounts also read as how
    a real handle is fixed): an end point that sits off the face (the old crate's were 0.12 out, past the frame line)
    leaves an air gap the floating-part check reports. segments=6 is round enough for a thin handle at game
    distance (triangles grow with segments: 6 costs about 3/4 of 8)."""
    _, d = _facing(facing)
    p0, p3 = a_end, b_end
    p1, p2 = _add(p0, d, lift), _add(p3, d, lift)
    inset0, inset3 = _add(p0, d, -radius), _add(p3, d, -radius)
    return a.tube(name, [inset0, p1, p2, inset3], radius, mat, segments=segments)


# ---------------------------------------------------------------- AAA hard-surface kit (secondary + tertiary forms)
# Outlines below are 2D in a plane, exactly like a.extrude: plane="side" -> (u = toward the FRONT, v = up) on the
# +X / -X face; "front" -> (u = right, v = up) on the -Z / +Z face; "top" -> (u = right, v = toward the front).
# `surface` is the face's coordinate along the plane normal (side: x of the face; front: z; top: y) and `side`
# is which way is OUT (+1 / -1). Chamfers catch light — the difference between "machined" and "a box".


def plate(a, name, outline, mat, plane="side", surface=0.0, side=1, thickness=0.03, chamfer=0.015):
    """A raised armour plate / cover / pad with chamfered edges, sitting ON the surface."""
    return a.slab(name, outline, plane, surface - side * 0.002, thickness + 0.002, mat, chamfer=chamfer, direction=side)


def inset_panel(a, target, name, outline, mat, plane="side", surface=0.0, side=1, depth=0.03, chamfer=0.015):
    """A recessed panel cut INTO `target`, with chamfered walls (the floor and walls take `mat`)."""
    cutter = a.slab(f"{name}Cut", outline, plane, surface + side * 0.02, depth + 0.02, mat, chamfer=chamfer, direction=-side)
    return a.cut(target, cutter)


def stripes(a, prefix, origin, size, mats, plane="side", surface=0.0, side=1, count=6, slant=0.6, thickness=0.006):
    """Hazard / warning stripes: `count` slanted bands across a size=(w, h) box starting at origin (u, v)."""
    w, h = size
    step = w / count
    out = []
    for i in range(count):
        u0 = origin[0] + i * step
        pts = [(u0, origin[1]), (u0 + step * 0.5, origin[1]), (u0 + step * 0.5 + h * slant, origin[1] + h), (u0 + h * slant, origin[1] + h)]
        pts = [(min(max(p[0], origin[0]), origin[0] + w + h * slant), p[1]) for p in pts]
        out.append(a.slab(f"{prefix}Stripe{i}", pts, plane, surface - side * 0.001, thickness, mats[i % len(mats)], direction=side))
    return out


def screw(a, name, pos, mat, facing="-Z", radius=0.05, height=0.03, socket_mat=None):
    """A socket-head screw: a low dome-ish head with a hex socket cut in it (reads at close range)."""
    axis, d = _facing(facing)
    head = a.cylinder(name, radius, height, _add(pos, d, height * 0.3), mat, axis=axis, segments=8, bevel=height * 0.35)
    a.cut(name, a.cylinder(f"{name}Socket", radius * 0.45, height, _add(pos, d, height * 0.9), socket_mat or mat, axis=axis, segments=6, bevel=0))
    return head


def screws(a, prefix, positions, mat, facing="-Z", radius=0.05):
    return [screw(a, f"{prefix}{i + 1}", p, mat, facing, radius) for i, p in enumerate(positions)]


_SLOTTED = '''
r, h, w = P["r"], P["h"], P["w"]
head = Cylinder(r, h * 0.35, align=(Align.CENTER, Align.CENTER, Align.MIN))
dome = scale(Sphere(r * 0.98), (1, 1, (h * 0.65) / r))
dome = dome & Box(3 * r, 3 * r, 3 * r, align=(Align.CENTER, Align.CENTER, Align.MIN))
part = head + dome.translate((0, 0, h * 0.35))
part -= Box(2.4 * r, w, h, align=(Align.CENTER, Align.CENTER, Align.MIN)).translate((0, 0, h * 0.5))
part = part.rotate(Axis.Z, P["slot_deg"]).translate((0, 0, -h * 0.08))   # (seated a hair into its surface)
f = P["face"]
part = {"+Z": part, "-Z": part.rotate(Axis.X, 180), "+X": part.rotate(Axis.Y, 90), "-X": part.rotate(Axis.Y, -90),
        "+Y": part.rotate(Axis.X, -90), "-Y": part.rotate(Axis.X, 90)}[f]
'''


def brilliant(radius=1.0, table=0.57, crown=0.32, star=0.8, star_z=0.6, girdle=0.04, pavilion=0.86):
    """a ROUND BRILLIANT cut stone as (verts, faces), its axis +Z, the girdle's top at z = 0 (pure: test_gem.py): an
    octagonal table, 8 star facets, 8 kite (bezel) facets, 16 upper-girdle facets, a 16-sided girdle band, 16 pavilion
    mains to the culet — closed. An 8-sided lofted stone read low-poly beside the game's cut jewel (Scarborough Fair,
    2026-10-21). Proportions (of the radius): table 0.57 wide, crown 0.32 high, pavilion 0.86 deep."""
    import math as _m  # noqa: PLC0415

    R, hc = radius, crown * radius
    v, f = [], []
    T = [len(v) + k for k in range(8)]
    v += [(table * R * _m.cos(_m.radians(45 * k)), table * R * _m.sin(_m.radians(45 * k)), hc) for k in range(8)]
    S = [len(v) + k for k in range(8)]
    v += [(star * R * _m.cos(_m.radians(45 * k + 22.5)), star * R * _m.sin(_m.radians(45 * k + 22.5)), hc * star_z)
          for k in range(8)]
    G = [len(v) + j for j in range(16)]
    v += [(R * _m.cos(_m.radians(22.5 * j)), R * _m.sin(_m.radians(22.5 * j)), 0.0) for j in range(16)]
    B = [len(v) + j for j in range(16)]
    v += [(R * _m.cos(_m.radians(22.5 * j)), R * _m.sin(_m.radians(22.5 * j)), -girdle * R) for j in range(16)]
    C = len(v)
    v.append((0.0, 0.0, -pavilion * R))
    f.append(list(T))                                                         # the table
    for k in range(8):
        f.append([T[k], S[k], T[(k + 1) % 8]])                                # star facets
        f.append([S[(k - 1) % 8], G[2 * k], S[k], T[k]])                      # kite (bezel) facets
        f.append([S[k], G[2 * k], G[2 * k + 1]])                              # upper girdle facets
        f.append([S[k], G[2 * k + 1], G[(2 * k + 2) % 16]])
    for j in range(16):
        f.append([G[j], B[j], B[(j + 1) % 16], G[(j + 1) % 16]])              # the girdle band
        f.append([B[(j + 1) % 16], B[j], C])                                  # pavilion mains
    return v, f


IOR = {"diamond": 2.42, "sapphire": 1.77, "ruby": 1.77, "emerald": 1.58, "peridot": 1.67, "amethyst": 1.54,
       "topaz": 1.62, "garnet": 1.76, "quartz": 1.54, "glass": 1.5, "crystal": 1.55}


def gem(a, name, center, radius, mat, facing="+Z", group="main", ior=1.6, **cut):
    """a ROUND BRILLIANT cut stone (brilliant()) set at `center` (studs: the girdle's top), its table toward `facing`,
    `radius` in studs — every facet edge marked sharp so the group's smooth-by-angle shading keeps the facets. Its
    faces carry `ior` (a number, or a stone's name: IOR) in the face attribute kit_gem: the SHOWCASE renders them as a
    cut stone that refracts (glass_gems), the game keeps the baked colour"""
    v, f = brilliant(radius, **cut)
    fc = facing.upper() if facing[0] in "+-" else "+" + facing.upper()
    rot = {"+Z": lambda p: p, "-Z": lambda p: (p[0], -p[1], -p[2]), "+X": lambda p: (p[2], p[1], -p[0]),
           "-X": lambda p: (-p[2], p[1], p[0]), "+Y": lambda p: (p[0], p[2], -p[1]),
           "-Y": lambda p: (p[0], -p[2], p[1])}[fc]
    obj = a.mesh(name, [rot(p) for p in v], f, mat, pos=center, group=group)
    for e in getattr(getattr(obj, "data", None), "edges", []):   # (sharp: the facets stay facets)
        e.use_edge_sharp = True
    return tag_gem(obj, ior)


def tag_gem(obj, ior=1.5):
    """mark every face of a part as glass / a stone (`ior` a number or a stone's name: IOR) in the face attribute
    kit_gem: the SHOWCASE renders it refracting (glass_gems), the game keeps the baked colour. A lantern's globe:
    P.tag_gem(a.sphere("Globe", ...), "glass"). (No mesh — kit cad check's stand-in — is fine: nothing to tag.)"""
    me = getattr(obj, "data", None)
    if me is not None and hasattr(me, "attributes"):
        at = me.attributes.get("kit_gem") or me.attributes.new("kit_gem", "FLOAT", "FACE")
        at.data.foreach_set("value", [float(IOR.get(str(ior).lower(), ior))] * len(me.polygons))
    return obj


def glass_gems(objs, dispersion=0.35, tint_gain=2.5, glow=0.15):
    """the SHOWCASE's stones: every face tagged kit_gem (P.gem) gets a glass twin of its own material — full
    transmission at the stone's IOR, no roughness, dispersion where Cycles has it (a baked colour reads as plastic; a
    cut stone bends the light behind it). Its body colour is its own colour BRIGHTENED (x tint_gain, the hue kept) and
    it glows a little of it (glow): a dark tint taken through every bounce turns a stone over a black setting black
    (Scarborough Fair's olive peridot did). -> how many faces"""
    done = 0
    for ob in objs:
        me = getattr(ob, "data", None)
        at = me.attributes.get("kit_gem") if me is not None and hasattr(me, "attributes") else None
        if at is None or at.domain != "FACE":
            continue
        vals = [0.0] * len(me.polygons)
        at.data.foreach_get("value", vals)
        if not any(v > 0 for v in vals):
            continue
        if len(me.materials) == 0:  # (no material at all: slot 0 for the rest first, or the twin would take it all)
            me.materials.append(_new_glass_base())
        twins = {}
        for poly, ior in zip(me.polygons, vals):
            if ior <= 0:
                continue
            key = (poly.material_index, round(ior, 2))
            if key not in twins:
                src = me.materials[poly.material_index] if poly.material_index < len(me.materials) else None
                m = src.copy() if src is not None else _new_glass_base()
                m.name = f"{(src.name if src else 'gem')}_glass{key[1]}"
                bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m.use_nodes \
                    else None
                if bsdf is not None:
                    _bright_tint(m, bsdf, tint_gain, glow)
                    for k, v in (("Transmission Weight", 1.0), ("Transmission", 1.0), ("IOR", float(ior)),
                                 ("Roughness", 0.0), ("Metallic", 0.0), ("Dispersion", float(dispersion))):
                        if k in bsdf.inputs and not bsdf.inputs[k].is_linked:
                            bsdf.inputs[k].default_value = v
                        elif k in bsdf.inputs and k in ("Roughness", "Metallic", "Emission Strength"):
                            for link in list(bsdf.inputs[k].links):  # (a baked roughness / emission map: off)
                                m.node_tree.links.remove(link)
                            bsdf.inputs[k].default_value = v
                me.materials.append(m)
                twins[key] = len(me.materials) - 1
            poly.material_index = twins[key]
            done += 1
    return done


def _bright_tint(m, bsdf, gain, glow):
    """the stone's own colour (a texture or a value), brightened with its hue kept, as its body tint + a faint glow"""
    nt = m.node_tree
    col = bsdf.inputs["Base Color"]
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Value"].default_value = float(gain)
    hsv.inputs["Saturation"].default_value = 1.1
    if col.is_linked:
        src = col.links[0].from_socket
        nt.links.remove(col.links[0])
        nt.links.new(src, hsv.inputs["Color"])
    else:
        hsv.inputs["Color"].default_value = tuple(col.default_value)
    nt.links.new(hsv.outputs["Color"], col)
    for k in ("Emission Color", "Emission"):
        if k in bsdf.inputs:
            for link in list(bsdf.inputs[k].links):
                nt.links.remove(link)
            nt.links.new(hsv.outputs["Color"], bsdf.inputs[k])
            break
    if "Emission Strength" in bsdf.inputs:
        for link in list(bsdf.inputs["Emission Strength"].links):
            nt.links.remove(link)
        bsdf.inputs["Emission Strength"].default_value = float(glow)


def _new_glass_base():
    import bpy  # noqa: PLC0415

    m = bpy.data.materials.new("gem")
    m.use_nodes = True
    return m


_TORUS = '''
part = Torus(P["r"], P["w"])
part = {"Z": part, "X": part.rotate(Axis.Y, 90), "Y": part.rotate(Axis.X, 90)}[P["axis"]].translate(tuple(P["at"]))
'''
_LINK = '''
with BuildSketch(Plane.XY) as sk:
    RectangleRounded(P["W"], P["L"], P["W"] * 0.42)
    RectangleRounded(P["W"] - 2 * P["band"], P["hole"], (P["W"] - 2 * P["band"]) * 0.36, mode=Mode.SUBTRACT)
part = extrude(sk.sketch, amount=P["t"] / 2, both=True)
for r in (P["t"] * 0.42, P["t"] * 0.28):
    try:
        part = fillet(part.edges(), r)
        break
    except Exception:
        pass
part = (part if P["axis"] == "Z" else part.rotate(Axis.Y, 90)).translate(tuple(P["at"]))
'''


def chain_layout(top_y, links=3, link_mm=(11.0, 16.0), band_mm=2.9, loop_mm=(3.6, 1.3), ring_mm=(5.0, 1.1),
                 bail_mm=(2.6, 0.9), embed=0.5):
    """the heights (mm) of a hanging chain's pieces under a host at top_y, each lower wire inside the next hole (pure:
    test_chain.py) -> {"loop", "links": [...], "ring", "bail", "pendant_top", "hole", "spacing"}"""
    _w, L = link_mm
    hole = L - 2 * band_mm
    r_l, w_l = loop_mm
    r_r, w_r = ring_mm
    r_b, w_b = bail_mm
    loop = top_y - (r_l + w_l) + embed                       # (its top `embed` mm into the host)
    spacing = L / 2 - band_mm / 2 + hole / 2 - 0.15          # (each lower wire just inside the next link's hole)
    first = loop - r_l - hole / 2 + w_l + 0.5                # (the loop's lower wire inside the first link's hole)
    ys = [first - spacing * k for k in range(links)]
    ring = ys[-1] - (L / 2 - band_mm / 2) - (r_r - w_r) / 2 - 0.5
    bail = ring - r_r - 0.5
    return {"loop": loop, "links": ys, "ring": ring, "bail": bail, "pendant_top": bail - r_b - w_b + 0.8,
            "hole": hole, "spacing": spacing}


def hanging_chain(a, prefix, anchor, mat, loop_axis="X", links=3, link_mm=(11.0, 16.0), band_mm=2.9, wire_mm=2.8,
                  loop_mm=(3.6, 1.3), ring_mm=(5.0, 1.1), bail_mm=(2.6, 0.9), loop_mat=None, group="main"):
    """A CHAIN THAT HANGS, every piece threaded through the next (a lanyard on a grip, a charm, a pendant, a lamp's
    pull): a loop seated 0.5 mm into the host at `anchor` (studs: the point on the host's underside it hangs from),
    `links` flat oval links each turned 90 degrees to the one above, a ring through the last, a bail through the ring
    (chain_layout). loop_axis: the loop's axis ("X": the loop lies in the YZ plane). link_mm: (width, length) of a
    link, band_mm its rim, wire_mm its thickness; *_mm of the rings: (radius, wire radius). A hand-placed column of
    links did not touch at all (the owner, 2026-10-21: "the chains under the gun arent even connected to the gun").
    -> the pendant's top point (studs): hang the charm from there."""
    mm = getattr(a, "mm_per_stud", None)
    mm = float((mm() if callable(mm) else mm) or 280.0)
    ax, ay, az = (v * mm for v in anchor)
    W, L = link_mm
    lay = chain_layout(ay, links, link_mm, band_mm, loop_mm, ring_mm, bail_mm)
    other = {"X": "Z", "Z": "X"}[loop_axis]
    a.cad(f"{prefix}Loop", _TORUS, loop_mat or mat,
          params={"r": loop_mm[0], "w": loop_mm[1], "axis": loop_axis, "at": [ax, lay["loop"], az]},
          tol=0.02, angle=8.0, group=group)
    for k, y in enumerate(lay["links"]):
        a.cad(f"{prefix}Link{k}", _LINK, mat, params={"W": W, "L": L, "band": band_mm, "hole": lay["hole"],
                                                      "t": wire_mm, "axis": other if k % 2 == 0 else loop_axis,
                                                      "at": [ax, y, az]}, tol=0.02, angle=8.0, group=group)
    ring_axis = loop_axis if links % 2 else other
    a.cad(f"{prefix}Ring", _TORUS, mat, params={"r": ring_mm[0], "w": ring_mm[1], "axis": ring_axis,
                                                "at": [ax, lay["ring"], az]}, tol=0.02, angle=8.0, group=group)
    a.cad(f"{prefix}Bail", _TORUS, mat, params={"r": bail_mm[0], "w": bail_mm[1],
                                                "axis": other if ring_axis == loop_axis else loop_axis,
                                                "at": [ax, lay["bail"], az]}, tol=0.02, angle=8.0, group=group)
    return (ax / mm, lay["pendant_top"] / mm, az / mm)


def slotted_screws(a, prefix, positions, mat, facing="-Z", radius=0.05, height=None, slot_deg=0.0, group="main"):
    """SLOTTED DOME SCREWS (CAD: exact): a low cylinder, a domed head and a straight slot across it — the classic
    screw of an ornate or antique piece (a Derringer's frame, a clock, a lock plate), where a socket head (screw)
    reads modern. positions on the surface, facing its outward axis; radius / height in studs (height default
    0.55 radius); slot_deg turns each slot (a single number, or one per position: real screws stop at any angle)."""
    mm = getattr(a, "mm_per_stud", None)
    mm = float((mm() if callable(mm) else mm) or 280.0)   # (an attribute on the Asset, a method on kit cad check's stub)
    f = facing.upper() if facing[0] in "+-" else "+" + facing.upper()
    h = height if height is not None else radius * 0.55
    out = []
    for i, p in enumerate(positions):
        deg = slot_deg[i % len(slot_deg)] if isinstance(slot_deg, (list, tuple)) else slot_deg
        out.append(a.cad(f"{prefix}{i + 1}", _SLOTTED, mat, pos=p,
                         params={"r": radius * mm, "h": h * mm, "w": max(radius * mm * 0.22, 0.4), "face": f,
                                 "slot_deg": float(deg)}, tol=0.02, angle=8.0, group=group))
    return out


def latch(a, name, pos, mat, facing="+X", size=(0.12, 0.22), mat2=None):
    """A spring latch / clip: a base plate and a hinged lever with a grip ridge."""
    axis, d = _facing(facing)
    w, h = size
    t = 0.025
    thin = {"X": (t, h, w), "Y": (w, t, h), "Z": (w, h, t)}[axis]
    lever = {"X": (t * 1.4, h * 0.7, w * 0.6), "Y": (w * 0.6, t * 1.4, h * 0.7), "Z": (w * 0.6, h * 0.7, t * 1.4)}[axis]
    a.box(f"{name}Base", thin, _add(pos, d, t * 0.5), mat, bevel=0.006)
    return a.box(name, lever, _add(pos, d, t * 1.6), mat2 or mat, bevel=0.008)


def knurl(a, prefix, center, mat, axis="Z", radius=0.06, length=0.2, rings=5):
    """Knurled grip rings around a rod / knob (scope turrets, focus rings, adjusters)."""
    ax = {"X": 0, "Y": 1, "Z": 2}[axis]
    out = []
    for i in range(rings):
        p = list(center)
        p[ax] += (i - (rings - 1) / 2) * length / rings
        out.append(a.cylinder(f"{prefix}Knurl{i}", radius, length / rings * 0.55, tuple(p), mat, axis=axis, segments=16, bevel=0.004))
    return out


def connector(a, name, pos, mat, facing="+X", radius=0.04, ring_mat=None):
    """A cable connector: collar + nut + pin stub (where cables plug into a body)."""
    axis, d = _facing(facing)
    a.cylinder(f"{name}Collar", radius * 1.4, radius * 0.5, _add(pos, d, radius * 0.25), ring_mat or mat, axis=axis, segments=6, bevel=0.004)
    return a.cylinder(name, radius, radius * 1.6, _add(pos, d, radius * 1.2), mat, axis=axis, segments=12, bevel=0.006)


def fins(a, prefix, start, end, count, size, mat):
    """Heat-sink fins: `count` thin plates of size (x, y, z) evenly from start to end."""
    out = []
    for i in range(count):
        t = i / max(1, count - 1)
        p = tuple(start[k] + (end[k] - start[k]) * t for k in range(3))
        out.append(a.box(f"{prefix}Fin{i}", size, p, mat, bevel=min(size) * 0.25))
    return out


def led(a, name, pos, mat_glow, mat_housing, facing="+X", radius=0.025):
    """A small indicator LED in a bezel."""
    axis, d = _facing(facing)
    a.cylinder(f"{name}Bezel", radius * 1.6, 0.02, _add(pos, d, 0.006), mat_housing, axis=axis, segments=12, bevel=0.004)
    return a.cylinder(name, radius, 0.024, _add(pos, d, 0.012), mat_glow, axis=axis, segments=12, bevel=0)


def groove(a, target, name, points, mat, plane="side", surface=0.0, side=1, width=0.012, depth=0.01):
    """An angular panel line cut along a polyline [(u, v), ...] — chamfer the corners yourself with 45-degree
    segments (the "sci-fi panel" look). Each segment is its own thin cut, so any shape works."""
    out = []
    for i in range(len(points) - 1):
        (u0, v0), (u1, v1) = points[i], points[i + 1]
        dx, dy = u1 - u0, v1 - v0
        ln = math.hypot(dx, dy) or 1e-6
        nx, ny = -dy / ln * width / 2, dx / ln * width / 2
        ex, ey = dx / ln * width / 2, dy / ln * width / 2
        # extend only FORWARD into the next segment: every joint is covered exactly once (a joint cut twice by
        # coincident cutters leaves a zero-area sliver behind)
        quad = [(u0 + nx, v0 + ny), (u1 + ex + nx, v1 + ey + ny), (u1 + ex - nx, v1 + ey - ny), (u0 - nx, v0 - ny)]
        cutter = a.slab(f"{name}Seg{i}", quad, plane, surface + side * 0.02, depth + 0.02, mat, direction=-side)
        out.append(a.cut(target, cutter))
    return out


def weld(a, prefix, points, mat, radius=0.012, overlap=0.55):
    """A WELD BEAD along a polyline (studs): overlapping small domes CENTRED on the seam line — a bead fills the corner
    where two surfaces meet, half in each (a bracket's foot, a frame's corner): the rippled bead a welded joint shows
    up close, from the first point to the last. overlap: how far each dome steps, in diameters."""
    import math  # noqa: PLC0415

    out, k = [], 0
    segs = list(zip(points[:-1], points[1:]))
    for s_i, (p0, p1) in enumerate(segs):
        seg = math.dist(p0, p1)
        n = max(1, int(seg / (2 * radius * overlap)))
        for i in range(n + (1 if s_i == len(segs) - 1 else 0)):   # (the last segment ends ON its last point)
            t = i / n
            p = tuple(p0[j] + (p1[j] - p0[j]) * t for j in range(3))
            k += 1
            out.append(a.sphere(f"{prefix}{k}", radius * (0.9 + 0.2 * ((k * 37) % 7) / 6), p, mat, segments=8, rings=4))
    return out


def rivet_ring(a, prefix, center, ring_radius, count, mat, axis="Z", radius=0.02, start_deg=0.0, sunk=0.4):
    """RIVETS round a cylinder's band (a canister's collar, a pipe flange): `count` domes on the circle of
    `ring_radius` about `axis` through `center` (studs), each sunk `sunk` of its radius into the surface."""
    import math  # noqa: PLC0415

    ax = "XYZ".index(axis.upper())
    u, v = [i for i in range(3) if i != ax]
    out = []
    for i in range(count):
        t = math.radians(start_deg + 360.0 * i / count)
        p = list(center)
        rr = ring_radius + radius * (1 - sunk)
        p[u] += rr * math.cos(t)
        p[v] += rr * math.sin(t)
        out.append(a.sphere(f"{prefix}{i + 1}", radius, tuple(p), mat, segments=10, rings=5))
    return out


def thread_mesh(major_mm, pitch_mm, length_mm, internal=True, segments=12, fade_turns=0.5, start_deg=0.0):
    """a SCREW THREAD's ridge as a light game mesh (pure: kit/test/python/test_thread.py): an ISO 60-degree V ridge
    wound round the z axis from z = 0 to length_mm (mm), `segments` facets a turn, its height faded in over the first
    `fade_turns` turns. internal: the ridge stands IN from a hole's wall (its base on the major radius, its crest
    5/8 H inward, H = 0.866 x pitch); else OUT from a rod (base on the minor radius, crest on the major). A closed
    prism (two flanks + the base hidden in the wall + two end caps): ~6 triangles a facet, 482 for 10 mm of M14 x 1.5
    at 12 a turn - the five threaded lug holes of round 3 took 8,100 from the CAD. -> (verts, faces, uvs) in mm:
    its own UVs are straight strips along the helix, one per flank and turn (a.mesh(uvs=...): kept by the unwrap)."""
    h_full = 0.625 * 0.8660254 * pitch_mm   # (5/8 H: the basic thread depth)
    r_base = major_mm / 2.0 if internal else major_mm / 2.0 - h_full
    sign = -1.0 if internal else 1.0         # (the crest's way from the base: inward for a hole)
    half = 0.5 * pitch_mm * 0.75             # (the base half-width: three quarters of the pitch, the root flat between)
    turns = length_mm / pitch_mm
    m = max(2, int(round(turns * segments)))
    verts, faces, uvs = [], [], []
    rings = []
    for i in range(m + 1):
        t = turns * i / m                    # (turns from the start)
        phi = math.radians(start_deg) + 2 * math.pi * t
        z = pitch_mm * t
        k = min(1.0, t / fade_turns) if fade_turns > 0 else 1.0
        k = max(0.06, k * k * (3 - 2 * k))   # (smoothstep, never quite zero: the prism stays closed and clean)
        h, w = h_full * k, half * k
        c, s = math.cos(phi), math.sin(phi)
        r_crest = r_base + sign * h
        base = len(verts)
        verts += [(r_base * c, r_base * s, z - w), (r_crest * c, r_crest * s, z), (r_base * c, r_base * s, z + w)]
        rings.append((base, base + 1, base + 2, h, w))
    # strip lengths: along the helix at each face's middle radius; across: the flank's and the base's own width
    step_mid = math.hypot(2 * math.pi * (r_base + sign * h_full * 0.5) * turns / m, pitch_mm * turns / m)
    step_base = math.hypot(2 * math.pi * r_base * turns / m, pitch_mm * turns / m)
    for i in range(m):
        a0, c0, b0, h0, w0 = rings[i]
        a1, c1, b1, h1, w1 = rings[i + 1]
        j = i % segments                      # (a new strip every turn: its u starts at 0)
        u0m, u1m = j * step_mid, (j + 1) * step_mid
        u0b, u1b = j * step_base, (j + 1) * step_base
        f0, f1 = math.hypot(h0, w0), math.hypot(h1, w1)   # (a flank's width there)
        # each face wound so its normal points out of the ridge (internal: the flank toward the hole's middle)
        faces.append((a0, a1, c1, c0)); uvs.append(((u0m, 0.0), (u1m, 0.0), (u1m, f1), (u0m, f0)))
        faces.append((c0, c1, b1, b0)); uvs.append(((u0m, 0.0), (u1m, 0.0), (u1m, f1), (u0m, f0)))
        faces.append((b0, b1, a1, a0)); uvs.append(((u0b, 0.0), (u1b, 0.0), (u1b, 2 * w1), (u0b, 2 * w0)))
    a0, c0, b0, h0, w0 = rings[0]
    a1, c1, b1, h1, w1 = rings[-1]
    faces.append((a0, c0, b0)); uvs.append(((0.0, 0.0), (w0, h0), (2 * w0, 0.0)))
    faces.append((b1, c1, a1)); uvs.append(((0.0, 0.0), (w1, h1), (2 * w1, 0.0)))
    # every face turned (with its UVs) so its normal leaves the ridge: away from the prism's own middle there (the
    # rings it touches; a cap: its ring and the next); then each kind of strip read the right way round on the map
    # (a mirrored island turns its normal map over) - flank A, flank B, base, caps
    kinds = [n % 3 for n in range(3 * m)] + [3, 3]
    flip_uv = {}
    for n, f in enumerate(faces):
        i = n // 3 if n < 3 * m else (0 if n == 3 * m else m - 1)
        ring_pts = [verts[q] for q in rings[i][:3] + rings[i + 1][:3]]
        mid = [sum(q[k] for q in ring_pts) / 6.0 for k in range(3)]
        p_ = [verts[q] for q in f]
        cen = [sum(q[k] for q in p_) / len(p_) for k in range(3)]
        nrm = _newell(p_)
        if sum(nrm[k] * (cen[k] - mid[k]) for k in range(3)) < 0:
            faces[n] = tuple(reversed(f))
            uvs[n] = tuple(reversed(uvs[n]))
        kind = kinds[n]
        if kind not in flip_uv:
            flip_uv[kind] = _area2(uvs[n]) < 0
        if flip_uv[kind]:
            uvs[n] = tuple((-u_, v_) for u_, v_ in uvs[n])
    return verts, faces, uvs


def _newell(p):
    """a polygon's normal (Newell's method: any winding, quads not quite flat)"""
    nx = ny = nz = 0.0
    for k in range(len(p)):
        x0, y0, z0 = p[k]
        x1, y1, z1 = p[(k + 1) % len(p)]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return nx, ny, nz


def _area2(q):
    """twice a UV polygon's signed area (> 0: counter-clockwise)"""
    return sum(q[k][0] * q[(k + 1) % len(q)][1] - q[(k + 1) % len(q)][0] * q[k][1] for k in range(len(q)))


def thread(a, name, mat, at_mm, axis_from_mm, length_mm, major_mm, pitch_mm, pos=(0, 0, 0), internal=True,
           segments=12, fade_turns=0.5, start_deg=0.0, group="main", fine_segments=48):
    """A SCREW THREAD as real, light game geometry (thread_mesh): an ISO 60-degree ridge in a hole (internal) or on a
    rod, wound round the axis through `at_mm` = (x, y) mm, from z = `axis_from_mm` back `length_mm` (the kit's CAD
    frame: mm, x right, y up, z back; `pos` in studs as for a.cad), `major_mm` across, `pitch_mm` a turn, faded in
    over `fade_turns` at its start; its UVs are straight strips along the helix. fine_segments: the same thread
    at that many facets a turn as a FLOATER (never in the game mesh) baked onto it - the light ridge's facets shade
    as one smooth helix (the same generator: the two helices lie on each other, no phase to match).
    The car rim's lug holes (the owner, 2026-11-10: "its threads only painted into the normal map" - fix it first):
    five of these at 482 triangles each, where round 3 spent 8,100 on CAD threads."""
    v, f, uv = thread_mesh(major_mm, pitch_mm, length_mm, internal=internal, segments=segments,
                           fade_turns=fade_turns, start_deg=start_deg)
    mm = float(getattr(a, "mm_per_stud", None) or 280.0)
    x0, y0 = at_mm
    verts = [((x + x0) / mm, (y + y0) / mm, (z + axis_from_mm) / mm) for x, y, z in v]
    obj = a.mesh(name, verts, f, mat, pos=pos, group=group, uvs=uv)
    if fine_segments and fine_segments > segments:
        vf, ff, _uvf = thread_mesh(major_mm, pitch_mm, length_mm, internal=internal, segments=fine_segments,
                                   fade_turns=fade_turns, start_deg=start_deg)
        with a.floaters(onto=group):
            a.mesh(f"{name}Fine", [((x + x0) / mm, (y + y0) / mm, (z + axis_from_mm) / mm) for x, y, z in vf], ff, mat,
                   pos=pos, group=group)
    return obj
