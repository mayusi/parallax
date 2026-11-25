"""modkit_facade.py - the W3 KIT CUT AS THE WORLD COMPILER'S FACADE MODULES (kit/lib/worldfacade.luau; kit world meshes
kind "gothic_module" with "kit": "w3"). The owner, 2026-11-23: "keep rolling straight through W3 GothicCourtyard swap".

The compiler's facade route splits every storey of every wall on the very gaps it cut for its collision and fills
each piece with ONE module stretched to fit: wall, window, windowb, door, oriel (a storey height each), band, roof,
chimney (one each for the town) - and, a W3 kit, a quoin up each corner of each storey. kit/world/gothic_blender.py
models those with its own procedural ashlar and a per-piece 1024 atlas; this cuts them from the W3 kit instead
(kit/world/modkit.py's geometry: bevelled boxes, the equilateral pointed arch through the wall, its reveal; mapped
onto the two SHARED trim sheets of kit/world/trims.py at 64 px/stud), so a court of houses wears 6 maps in all.

  wall     a plain ashlar panel, both faces
  window   the gap the building cuts (width, height = sill + the window's own, sill) as a pointed lancet whose crown
           is the gap's top and whose jambs are its sides: the wall under the sill and over the crown, the spandrels,
           the reveal through the wall; leaded glass set back in the reveal, an iron mullion and transom (roof sheet)
  windowb  the same lancet under a hood moulding (the drip stone of the kit's portal), no transom: a second look
  door     the doorway (sill 0): a pointed arch, its crown the gap's top, a hood moulding, the reveal in quoin stone -
           OPEN: no leaves (what you see is what you walk through)
  oriel    the wall's own lancet opening, open, with a bay standing out in front of it: stone cheeks, a corbel, a
           front with its own glazed lancet, a slate lean-to over it
  band     a moulded string course standing proud of the wall at a storey's foot
  roof     a gable roof: two slate slopes (their ridge along the module's depth), boarded undersides, an ashlar
           gable at each end, an iron ridge roll
  chimney  an ashlar stack under a moulded cap
  quoin    long-and-short blocks up one corner of one storey, wrapping it (it closes the corner the walls leave)

FRAME (the facade's, Roblox axes): origin at the foot of the module's middle on the wall's CENTRE LINE, x along the
wall, y up, +z out to the street (the wall's front face at z = +t/2, its back at -t/2). A roof: origin at the middle
of its foot, x across the gable, z along the ridge (the street's gable at +z). A quoin: origin at the corner's OUTER
edge, its long blocks along +x on the front face (z = 0), its return along -z on the other wall's face (x = 0).
module(rec) -> {"parts": [{"sheet", "verts", "faces", "uvs"}], "opening"?} - one part a sheet (a MeshPart wears one
SurfaceAppearance), the first the module's own mesh, the rest its companions. Pure numpy.
Not here: Blender (kit/world/meshes_blender.py writes the parts), the upload (the orchestrator's), collision (the
compiler's invisible walls stay the collision)."""
import math

import numpy as np

import modkit as M

MODULES = ("wall", "window", "windowb", "door", "oriel", "band", "roof", "chimney", "quoin")
X, Y, Z = np.eye(3)
SQ3 = math.sqrt(3.0)


def _face(m, pts, look, strip, ua, va):
    """a polygon drawn for the side `look` points to (Roblox draws ONE side of a face)"""
    pts = [np.asarray(p, float) for p in pts]
    n = sum(np.cross(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))
    if n @ np.asarray(look, float) < 0:
        pts = pts[::-1]
    m.poly(pts, strip, ua, va)


def _spring(gap):
    """(half-width, sill, springing) of the equilateral lancet whose crown is the gap's top"""
    half = float(gap["width"]) / 2
    top = float(gap["height"])
    sill = float(gap.get("sill", 0.0))
    spring = top - half * SQ3  # (an equilateral arch of half-span r rises r * sqrt(3) over its springing)
    if spring < sill + 0.3:
        raise ValueError(f"an opening {gap['width']} wide cannot have a pointed head under {top} (its sill {sill})")
    return half, sill, spring


def _hood(m, cx, half, spring, proud=0.35):
    """a hood moulding: a drip stone between two arches (0.1 and 0.7 outside the opening's), `proud` out of the wall's
    face (z = 0), its outer and inner edges closed (the kit's portal's)"""
    inner, outer = M._arch(cx, half + 0.1, spring), M._arch(cx, half + 0.7, spring)
    for (a, b), (c, d) in zip(zip(inner[:-1], inner[1:]), zip(outer[:-1], outer[1:])):
        a0, b0 = np.array([a[0], a[1], proud]), np.array([b[0], b[1], proud])
        c0, d0 = np.array([c[0], c[1], proud]), np.array([d[0], d[1], proud])
        t = b0 - a0
        t /= np.linalg.norm(t)
        out = np.array([-t[1], t[0], 0.0])
        if out @ (c0 - a0) < 0:
            out = -out
        _face(m, [a0, b0, d0, c0], Z, "moulding", t, out)  # its face to the street
        # its outer edge (looks away from the opening) and its inner edge (looks into it)
        for p, q, look in ((c0, d0, out), (a0, b0, -out)):
            _face(m, [p, q, q - Z * proud, p - Z * proud], look, "moulding", t, -Z)
    # the two feet: the drip ends square on the springing line, their undersides closed
    for sx in (-1, 1):
        xa, xb = cx + sx * (half + 0.1), cx + sx * (half + 0.7)
        _face(m, [(xa, spring, proud), (xb, spring, proud), (xb, spring, 0.0), (xa, spring, 0.0)], -Y, "moulding", X, Z)


def _glazing(m, cx, half, sill, spring, zg, transom=True):
    """leaded glass in a lancet at depth zg (seen from the street AND the room: one face each way, a twentieth of a
    stud apart), an iron mullion and (as asked) a transom in front of it"""
    ring = [(cx - half, sill)] + M._arch(cx, half, spring) + [(cx + half, sill)]
    _face(m, [(x, y, zg) for x, y in ring], Z, "glass", X, Y)
    _face(m, [(x, y, zg - 0.05) for x, y in ring], -Z, "glass", -X, Y)
    apex = spring + half * SQ3
    m.box(cx - 0.08, cx + 0.08, sill, apex - 0.4, zg, zg + 0.16, "iron", faces="flrt")
    if transom:
        m.box(cx - half, cx + half, spring - 0.08, spring + 0.08, zg, zg + 0.16, "iron", faces="ftb")


def _shift(m, dx, dy, dz):
    m.v = [(x + dx, y + dy, z + dz) for x, y, z in m.v]
    return m


def _wall(w, h, t):
    m = M.Mesh()
    m.box(0, w, 0, h, -t, 0, "ashlar", faces="fk")
    return [("stone", m)]


def _lancet(w, h, t, gap, hood):
    stone, glass = M.Mesh(), M.Mesh()
    half, sill, spring = _spring(gap)
    cx = w / 2
    M._opening(stone, 0, w, h, cx, half, sill, spring, depth=t)
    if hood:
        _hood(stone, cx, half, spring)
    _glazing(glass, cx, half, sill, spring, -t * 0.6, transom=not hood)
    return [("stone", stone), ("roof", glass)]


def _door(w, h, t, gap):
    stone = M.Mesh()
    half, sill, spring = _spring(gap)
    M._opening(stone, 0, w, h, w / 2, half, 0.0, spring, reveal_strip="quoin", depth=t)
    _hood(stone, w / 2, half, spring)
    return [("stone", stone)]


def _oriel(w, h, t, out, gap):
    """the wall's lancet (open) and a bay `out` studs out of the wall's face (z = 0 .. out)"""
    stone, roof = M.Mesh(), M.Mesh()
    half, sill, spring = _spring(gap)
    top = float(gap["height"])
    cx = w / 2
    M._opening(stone, 0, w, h, cx, half, sill, spring, depth=t)
    b0, b1 = max(0.6, sill - 0.6), min(h - 1.6, top + 0.5)  # the bay's floor and its ceiling
    skin = 0.25  # its front's and its cheeks' thickness
    # the cheeks: stone outside, the bay's own stone inside
    for x, look in ((0.0, -X), (w, X)):
        _face(stone, [(x, b0, 0.0), (x, b0, out), (x, b1, out), (x, b1, 0.0)], look, "ashlar", Z, Y)
        xi = x - look[0] * skin
        _face(stone, [(xi, b0, 0.0), (xi, b0, out - skin), (xi, b1, out - skin), (xi, b1, 0.0)], -look, "ashlar", Z, Y)
    # the floor (seen from the room; the corbel closes it underneath) and the ceiling (seen from the room)
    _face(stone, [(skin, b0, 0.0), (w - skin, b0, 0.0), (w - skin, b0, out - skin), (skin, b0, out - skin)], Y, "moulding", X, -Z)
    _face(stone, [(skin, b1, 0.0), (w - skin, b1, 0.0), (w - skin, b1, out - skin), (skin, b1, out - skin)], -Y, "moulding", X, -Z)
    # the cheeks' tops and feet between their two faces
    for x0, x1 in ((0.0, skin), (w - skin, w)):
        _face(stone, [(x0, b0, 0.0), (x1, b0, 0.0), (x1, b0, out), (x0, b0, out)], -Y, "moulding", X, Z)
        _face(stone, [(x0, b1, 0.0), (x1, b1, 0.0), (x1, b1, out), (x0, b1, out)], Y, "moulding", X, Z)
    # its front: a panel with a lancet, as thick as `skin`, its face to the street at z = out
    fh = b1 - b0
    fhalf = min(half, w / 2 - 0.45)
    fsill = sill - b0
    ftop = min(top - b0, fh - 0.4)
    fspring = ftop - fhalf * SQ3
    front = M.Mesh()
    M._opening(front, 0, w, fh, cx, fhalf, max(0.3, fsill), fspring, depth=skin)
    _shift(front, 0, b0, out)
    stone.v += front.v
    stone.uv += front.uv
    n0 = len(stone.v) - len(front.v)
    stone.f += [(a + n0, b + n0, c + n0) for a, b, c in front.f]
    _glazing(roof, cx, fhalf, b0 + max(0.3, fsill), b0 + fspring, out - skin * 0.6, transom=True)
    # the corbel: a slope from the wall's face down under the bay's floor, closed at its sides
    c0 = max(0.0, b0 - 1.6)
    s = 1 / math.sqrt(2)
    _face(stone, [(0, c0, 0.0), (0, b0, out), (w, b0, out), (w, c0, 0.0)], np.array([0, -1.0, 1.0]), "moulding", X,
          np.array([0, s, s]))
    _face(stone, [(0, c0, 0.0), (0, b0, 0.0), (0, b0, out)], -X, "moulding", -Z, Y)
    _face(stone, [(w, c0, 0.0), (w, b0, out), (w, b0, 0.0)], X, "moulding", Z, Y)
    # the lean-to roof: slates from over the bay's front up to the wall's face, its cheeks closed
    r1 = min(h - 0.1, b1 + 1.4)
    ov = 0.2
    a, b = np.array([-0.15, b1, out + ov]), np.array([w + 0.15, b1, out + ov])
    c, d = np.array([w + 0.15, r1, 0.0]), np.array([-0.15, r1, 0.0])
    up = (d - a) / np.linalg.norm(d - a)
    slope_n = np.cross(b - a, d - a)
    slope_n = slope_n if slope_n[1] > 0 else -slope_n
    _face(roof, [a, b, c, d], slope_n, "slate", X, up)
    _face(roof, [p - [0, 0.06, 0] for p in (a, b, c, d)], -slope_n, "beam", X, up)
    _face(stone, [(0, b1, out), (0, b1, 0.0), (0, r1, 0.0)], -X, "ashlar", -Z, Y)
    _face(stone, [(w, b1, out), (w, r1, 0.0), (w, b1, 0.0)], X, "ashlar", Z, Y)
    return [("stone", stone), ("roof", roof)]


def _band(w, h, d):
    m = M.Mesh()
    m.box(0, w, 0, h, 0.0, d, "moulding", faces="ftblr", bevel=min(0.15, h / 4))
    return [("stone", m)]


def _roof(w, h, d):
    """a gable roof, already in its own frame (x across, z along the ridge, its foot's middle the origin)"""
    slate, gable = M.Mesh(), M.Mesh()
    for sx in (-1, 1):
        eave = np.array([sx * w / 2, 0.0, 0.0])
        ridge = np.array([0.0, h, 0.0])
        up = (ridge - eave) / np.linalg.norm(ridge - eave)
        e0, e1 = eave + [0, 0, -d / 2], eave + [0, 0, d / 2]
        r0, r1 = ridge + [0, 0, -d / 2], ridge + [0, 0, d / 2]
        out = np.array([sx * h, w / 2, 0.0])  # (the slope's outward normal: up and away from the ridge)
        _face(slate, [e0, e1, r1, r0], out, "slate", Z, up)
        # the boards under it (seen from the top storey and from under the eaves), a fifth of a stud lower
        low = 0.2
        k = 1 - low / h  # (its eave a hair in from the slates' and its ridge `low` under theirs: parallel to them)
        under = [np.array([p[0] * k, 0.0 if p[1] < 1e-9 else h - low, p[2]]) for p in (e0, e1, r1, r0)]
        _face(slate, under, -out, "beam", Z, up)
    # the gables: ashlar to the street and to the yard, the attic's face a twentieth of a stud inside
    for zz, look in ((d / 2, 1.0), (-d / 2, -1.0)):
        _face(gable, [(-w / 2, 0.0, zz), (w / 2, 0.0, zz), (0.0, h, zz)], Z * look, "ashlar", X * look, Y)
        zi = zz - look * 0.05
        _face(gable, [(-w / 2, 0.0, zi), (w / 2, 0.0, zi), (0.0, h, zi)], -Z * look, "ashlar", -X * look, Y)
    # the ridge roll: two small slopes over the ridge line, the length of the roof
    for sx in (-1, 1):
        q = [(0.0, h + 0.3, -d / 2), (0.0, h + 0.3, d / 2), (sx * 0.4, h - 0.1, d / 2), (sx * 0.4, h - 0.1, -d / 2)]
        _face(slate, q, np.array([sx, 1.0, 0.0]), "iron", Z, np.array([sx, -1.0, 0.0]) / math.sqrt(2))
    return [("roof", slate), ("stone", gable)]


def _chimney(w, h, d):
    m = M.Mesh()
    cap = 0.8
    m.box(0, w, 0, h - cap, -d, 0, "ashlar", faces="fklrb")
    m.box(-0.3, w + 0.3, h - cap, h, -d - 0.3, 0.3, "moulding", faces="fklrtb", bevel=0.1)
    return [("stone", _shift(m, -w / 2, 0, d / 2))]


def _quoin(h, t):
    """long-and-short blocks up a corner: course by course a long block on the front face and a short one round the
    corner, then the other way about; each course one solid (no slit between courses: behind them the walls leave the
    corner open)"""
    m = M.Mesh()
    y, k = 0.0, 0
    proud = 0.15
    while y < h - 1e-6:
        ch = min(2.0, h - y)
        a = 2.6 if k % 2 == 0 else 1.6  # along the front face from the corner
        b = 1.6 if k % 2 == 0 else 2.6  # along the return
        m.box(-proud, a, y, y + ch, -t, proud, "quoin", faces="frtb", bevel=0.0)
        m.box(-proud, t, y, y + ch, -b, proud, "quoin", faces="lktb", bevel=0.0)
        y += ch
        k += 1
    return [("stone", m)]


def module(rec):
    """a facade module from its recipe -> {"parts": [{sheet, verts, faces, uvs}], "box": [w, h, d]}"""
    kind = rec.get("module")
    if kind not in MODULES:
        raise ValueError(f"gothic_module (kit w3): unknown module {kind!r} ({' | '.join(MODULES)})")
    w, h, d = [float(v) for v in rec.get("size", [M.GRID, M.FLOOR, M.WALL])]
    t = float(rec.get("thickness", M.WALL))
    gap = rec.get("gap") or {}
    if kind in ("window", "windowb", "door", "oriel"):
        for k in ("width", "height"):
            if not isinstance(gap.get(k), (int, float)):
                raise ValueError(f"gothic_module (kit w3) {kind}: its gap needs a {k} (the building's own opening)")
        if abs(float(gap["width"]) - w) > 1e-6:
            raise ValueError(f"gothic_module (kit w3) {kind}: {w} wide, its gap {gap['width']} (the module IS the opening)")
    if kind == "wall":
        parts, frame = _wall(w, h, t), "wall"
    elif kind in ("window", "windowb"):
        parts, frame = _lancet(w, h, t, gap, hood=(kind == "windowb")), "wall"
    elif kind == "door":
        parts, frame = _door(w, h, t, gap), "wall"
    elif kind == "oriel":
        parts, frame = _oriel(w, h, t, d - t, gap), "wall"
    elif kind == "band":
        parts, frame = _band(w, h, d), "face"
    elif kind == "roof":
        parts, frame = _roof(w, h, d), "own"
    elif kind == "chimney":
        parts, frame = _chimney(w, h, d), "own"
    else:
        parts, frame = _quoin(h, t), "own"
    out = []
    for sheet, m in parts:
        if not m.f:
            continue
        if frame == "wall":  # modkit's frame (x from the left end, the front face at z = 0) -> the centre line's
            _shift(m, -w / 2, 0, t / 2)
        elif frame == "face":  # a band: its back on the wall's front face
            _shift(m, -w / 2, 0, t / 2)
        out.append({"sheet": sheet, "verts": [tuple(float(c) for c in v) for v in m.v],
                    "faces": [tuple(int(i) for i in f) for f in m.f], "uvs": [tuple(float(c) for c in uv) for uv in m.uv]})
    return {"parts": out, "box": [w, h, d]}


def to_blender(part):
    """a part's vertices in Blender's frame (Roblox (x, y up, z) -> Blender (x, -z, y), as meshes_blender's geometry)"""
    return [(x, -z, y) for x, y, z in part["verts"]]
