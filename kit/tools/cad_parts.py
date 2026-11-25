"""cad_parts.py — real FASTENERS and SPRINGS for a.cad part scripts (cad env; kit/tools/cad_run.py hands these to
every part script, like fillet_soft). Down to the screws (the owner, 2026-10-07): a mechanism's screws, pins and
springs are real parts at real sizes, not painted dots.

    screw("M3-0.5", 10, head="socket", threads=False)   a metric screw (bd_warehouse, ISO tables): head "socket"
        (ISO 4762), "button" (ISO 7380), "countersunk" (ISO 10642), "pan" (ISO 1580), "hex" (ISO 4014); threads=True
        models the thread itself (slow: hero close-ups only). Its head's top at z = 0... its shank down to z = -length
        (bd_warehouse's convention).
    nut("M3-0.5")                                         an ISO 4032 hex nut, its bottom at z = 0
    pin(d, length, chamfer=None)                          a solid pin (a dowel / a 1911's hammer pin) from z = 0 to
                                                          z = length, both ends chamfered (default: 0.1 d)
    roll_pin(d, length, wall=None)                        a slotted spring pin (ISO 8752): a tube with a slit along it
    spring(mean_d, wire_d, length, coils, ground=True)    a helical compression spring: a circle swept along a helix
                                                          from z = 0 to z = length; ground=True: both ends cut flat
    clearance("M3", fit="normal")                         the ISO 273 clearance hole's diameter (close / normal / loose)
    section(w, d, squareness, squareness_front=None)      a superellipse section (2 = ellipse ... 6+ = boxy); its
                                                          front half its own (a grip: boxy front, round back strap)
    outline(pts, corner_deg=35)                           a TRACED outline as a smooth Face: a curve per run between
                                                          its corners, the corners kept (add(outline(...)) in a sketch)
    loft_sections(stations, axis="y")                     a solid lofted through sections: a grip that WRAPS around
    from_levels(levels, height_mm, length_mm, hs=...)     a reference's measured slices -> those stations
    ring(r_in, r_out, height, round=1.0, base=0.0)       a ROUNDED RING / setting / coin, revolved about Z from z = 0:
                                                          its top corners rounded by round x min(height, width / 2)
                                                          (1.0 + a tall enough ring: a half-round bead; r_in 0: a domed
                                                          coin) — a jewel's bezel, a gold collar, a medallion: never a
                                                          square-edged disc (Scarborough Fair, 2026-10-22)
    turned(top, back=None, tol=0.005)                    a LATHE part: an (r, z) profile revolved about Z, its
                                                          nearly-collinear samples dropped (else OpenCASCADE's solid is
                                                          invalid) — a stepped shield face, a bell, a turned knob
    inlay(shape, host, proud=0.85, under=0.3)             DECORATION THAT WRAPS a curved part: the part of `shape` (a
                                                          traced logo / trim extruded right through the host) inside
                                                          a thin skin of the host's own surface — never a flat plate
                                                          that floats off a tube (Scarborough Fair, 2026-10-21)
    redraw(pts, tol=0.15, mirror=None)                    a TRACE REDRAWN as true lines + arcs (kit/tools/primfit.py),
                                                          near-equal radii made equal, mirror=("x", 0): symmetric — a
                                                          clean Face that fillets (kit refs redraw writes the prims)
    bead(path, width, height, round=1.0, ends="round")    raised TRIM: a half-round profile swept along a path in XY,
                                                          domed ends (never a flat border with square shoulders)
    setting(stone_d, girdle_z=1, wall=1, lip=0.35, prongs=0)  a jewel's BEZEL: a seat under the girdle, a lip over it
All in millimetres; fasteners along Z; place them with Pos / Rot (or Location) like any build123d shape.
"""

import math

import build123d as bd

_HEADS = {"socket": ("SocketHeadCapScrew", "iso4762"), "button": ("ButtonHeadScrew", "iso7380_1"),
          "countersunk": ("CounterSunkScrew", "iso10642"), "pan": ("PanHeadScrew", "iso1580"),
          "hex": ("HexHeadScrew", "iso4014")}


def screw(size, length, head="socket", threads=False):
    from bd_warehouse import fastener  # noqa: PLC0415

    cls, std = _HEADS[head]
    try:
        return getattr(fastener, cls)(size, length, fastener_type=std, simple=not threads)
    except (ValueError, KeyError):  # a standard this head type names differently: its own default
        return getattr(fastener, cls)(size, length, simple=not threads)


def nut(size, threads=False):
    from bd_warehouse import fastener  # noqa: PLC0415

    return fastener.HexNut(size, simple=not threads)


def pin(d, length, chamfer=None):
    c = 0.1 * d if chamfer is None else chamfer
    body = bd.Cylinder(d / 2, length, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    if c > 0:
        body = bd.chamfer(body.edges().filter_by(bd.GeomType.CIRCLE), c)
    return body


def roll_pin(d, length, wall=None):
    w = wall if wall is not None else max(0.1 * d, 0.2)
    outer = bd.Cylinder(d / 2, length, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    inner = bd.Cylinder(d / 2 - w, length, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    slit = bd.Pos(d / 2, 0, length / 2) * bd.Box(d, 0.15 * d, length)
    return outer - inner - slit


def spring(mean_d, wire_d, length, coils, ground=True):
    """a compression spring: a wire circle swept along a helix; ground ends cut flat at z = 0 and z = length"""
    extra = wire_d if ground else 0.0
    height = length + 2 * extra
    path = bd.Helix(pitch=height / coils, height=height, radius=mean_d / 2)
    start, tangent = path @ 0, path % 0
    section = bd.Plane(origin=start, z_dir=tangent) * bd.Circle(wire_d / 2)
    coil = bd.sweep(section, path=path, is_frenet=True)
    coil = bd.Pos(0, 0, -extra) * coil
    if ground:
        keep = bd.Box(mean_d + 2 * wire_d, mean_d + 2 * wire_d, length,
                      align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        coil = coil & keep
    return coil


def clearance(size, fit="normal"):
    """the ISO 273 clearance hole diameter for a metric size ("M3" or "M3-0.5")"""
    from bd_warehouse import fastener  # noqa: PLC0415

    nominal = size.split("-")[0]
    data = fastener.read_fastener_parameters_from_csv("clearance_hole_sizes.csv")
    return float(data[nominal][{"close": "Close", "normal": "Normal", "loose": "Loose"}[fit]])


def section(w, d, squareness=2.0, n=48, squareness_front=None):
    """a closed SECTION w across x d deep (mm): a superellipse — squareness 2 = an ellipse, 3 = a soft rounded box,
    6+ = a box with small corners (the number kit refs measure reports per level / station) — as a flat Face in XY.
    squareness_front: the +y half's own (a grip is BOXY at the front round its magazine and round at the back strap:
    symmetric at the scan's 3, the Glock's grip narrowed to +-10 mm 3 mm behind its front strap and the +-11.3 mm
    magazine well broke out through its sides)"""
    e = 2.0 / max(squareness, 0.5)
    e_front = 2.0 / max(squareness_front, 0.5) if squareness_front else e
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        c, s = math.cos(t), math.sin(t)
        e_ = e_front if s > 0 else e
        pts.append(bd.Vector(math.copysign(abs(c) ** e_, c) * w / 2, math.copysign(abs(s) ** e_, s) * d / 2, 0))
    return bd.Face(bd.Wire([bd.Edge.make_spline(pts, periodic=True)]))


def outline(pts, corner_deg=35.0, tol=0.03):
    """a TRACED outline (a closed polyline in a sketch's own x, y — a photo's trace, mm) as one smooth Face: the runs
    between its CORNERS (a turn sharper than corner_deg) become curves fitted through the traced points (within tol mm),
    the corners stay corners. A polygon gives a facet at every traced point, and an offset (clean_profile) a 0.05 mm arc
    at each one — no fillet takes a wall of those (the Glock's frame: every edge refused, even alone); one smooth wall
    per run does, and shades like the moulded / machined surface it is. In a sketch: add(outline(pts))"""
    ps = []
    for x, y in pts:
        v = bd.Vector(float(x), float(y), 0.0)
        if not ps or (v - ps[-1]).length > 1e-3:
            ps.append(v)
    if len(ps) > 2 and (ps[0] - ps[-1]).length <= 1e-3:
        ps.pop()
    n = len(ps)
    if n < 3:
        raise ValueError("outline: needs 3 or more distinct points")

    def turn(i):
        a, b = ps[i] - ps[i - 1], ps[(i + 1) % n] - ps[i]
        return abs(math.degrees(math.atan2(a.X * b.Y - a.Y * b.X, a.X * b.X + a.Y * b.Y)))

    corners = [i for i in range(n) if turn(i) > corner_deg]
    if not corners:  # a smooth closed loop (an oval, a hole): two fitted curves, split at its sharpest turn and
        i0 = max(range(n), key=turn)  # half way round (an interpolating loop would follow the trace's noise)
        corners = sorted({i0, (i0 + n // 2) % n})
    edges = []
    for k, c in enumerate(corners):
        nxt = corners[(k + 1) % len(corners)]
        run = [ps[j % n] for j in range(c, (nxt if nxt > c else nxt + n) + 1)]
        straight = max((_off_line(p, run[0], run[-1]) for p in run[1:-1]), default=0.0) <= tol
        if len(run) == 2 or straight:
            edges.append(bd.Edge.make_line(run[0], run[-1]))
        elif len(run) == 3:
            edges.append(bd.Edge.make_three_point_arc(*run))
        else:  # (a fit, not an interpolation: a trace's pixel noise is not followed into wiggles)
            edges.append(bd.Edge.make_spline_approx(run, tol=tol, max_deg=3))
    return bd.Face(bd.Wire(edges))


def _off_line(p, a, b):
    ab = b - a
    if ab.length < 1e-9:
        return (p - a).length
    return abs(ab.X * (p - a).Y - ab.Y * (p - a).X) / ab.length


def loft_sections(stations, axis="y"):
    """a solid LOFTED through sections — a grip that WRAPS around, a tapered barrel shroud, a stock. stations: dicts
    {"at": mm along the axis, "width", "depth", "squareness", "squareness_front", "centre": (a, b)} or tuples (at,
    width, depth, squareness[, (a, b)]). axis "y" (up: a grip's sections are horizontal; centre = (x, z), depth along z;
    squareness_front: the FRONT half's, toward -z) or "z" (along the length: centre = (x, y), depth along y;
    squareness_front: the TOP half's). The kit's axes: x right, y up, z back."""
    faces = []
    for st in stations:
        sqf = None
        if isinstance(st, dict):
            at, w, d, sq, cen = st["at"], st["width"], st["depth"], st.get("squareness", 2.0), st.get("centre", (0, 0))
            sqf = st.get("squareness_front")
        else:
            at, w, d, sq = st[:4]
            cen = st[4] if len(st) > 4 else (0, 0)
        if axis == "y":
            plane = bd.Plane(origin=(cen[0], at, cen[1]), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        else:
            plane = bd.Plane(origin=(cen[0], cen[1], at), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
        faces.append(plane * section(w, d, sq, squareness_front=sqf))
    return bd.loft(faces)


def from_levels(levels, height_mm, length_mm, hs=None):
    """a reference's measured horizontal slices (kit refs measure: refs/<name>.measure.json "levels") -> loft_sections
    stations along y in the kit's frame (origin at the object's centre, its bottom at y = -height/2, the front at -z):
    `part = loft_sections(from_levels(P["levels"], 135, 216, hs=(0.1, 0.2, 0.3, 0.4)))` — a grip wrapped like the
    real one. hs: which levels (fractions of the height), else all"""
    out = []
    for lv in levels:
        if hs is not None and not any(abs(lv["h"] - h) < 1e-6 for h in hs):
            continue
        cx, along = lv.get("centre_mm", (0.0, length_mm / 2))
        out.append({"at": lv["h"] * height_mm - height_mm / 2, "width": lv["width_mm"], "depth": lv["depth_mm"],
                    "squareness": lv.get("squareness", 2.0), "centre": (cx, length_mm / 2 - along)})
    return out


HELPERS = {"screw": screw, "nut": nut, "pin": pin, "roll_pin": roll_pin, "spring": spring, "clearance": clearance,
           "section": section, "outline": outline, "loft_sections": loft_sections, "from_levels": from_levels}
_ = math  # (kept for scripts that import * from here)


def inlay(shape, host, proud=0.85, under=0.3):
    """the part of `shape` inside the host's SKIN: from `under` mm below its surface to `proud` mm above it — a traced
    logo, a gold trim line, an engraved band laid ON a curved part (extrude the 2D shape right through the host, pass
    it here). A flat plate at the widest point floats off a tube everywhere else (the owner saw it: Scarborough Fair's
    barrels, 2026-10-21). Raises ValueError when OpenCASCADE cannot offset the host (then build the skin from the
    host's own primitives: an offset cylinder minus a smaller one)"""
    try:
        outer = bd.offset(host, amount=proud)
        inner = bd.offset(host, amount=-under)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"inlay: OpenCASCADE could not offset the host ({e}); build its skin from primitives") from e
    return shape & (outer - inner)



def ring(r_in, r_out, height, round=1.0, base=0.0):
    """a ring (or, with r_in = 0, a coin) revolved about Z, standing on z = 0, its TOP corners rounded by
    round x min(height, width / 2) and its bottom ones by base x that — the soft collar / bezel / medallion of an
    ornate piece. A square-edged cylinder minus a cylinder read as a cheap washer beside the art's domed setting"""
    w = float(r_out) - float(r_in)
    if w <= 0 or height <= 0:
        raise ValueError("ring: r_out > r_in and height > 0")
    rt = max(0.0, min(1.0, round)) * min(height, w / 2) * 0.999
    rb = max(0.0, min(1.0, base)) * min(height, w / 2) * 0.999
    pts = []

    def arc(cx, cy, r, a0, a1, n=10):
        return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                 cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    x0, x1, h = float(r_in), float(r_out), float(height)
    pts += [(x0 + rb, 0.0)] if rb > 0 and x0 > 0 else [(x0, 0.0)]
    pts += arc(x1 - rb, rb, rb, 270, 360) if rb > 0 else [(x1, 0.0)]
    pts += arc(x1 - rt, h - rt, rt, 0, 90) if rt > 0 else [(x1, h)]
    pts += (arc(x0 + rt, h - rt, rt, 90, 180) if (rt > 0 and x0 > 0) else [(x0, h)])
    if rb > 0 and x0 > 0:
        pts += arc(x0 + rb, rb, rb, 180, 270)
    clean = []
    for p in pts:
        if not clean or abs(p[0] - clean[-1][0]) + abs(p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    if abs(clean[0][0] - clean[-1][0]) + abs(clean[0][1] - clean[-1][1]) < 1e-6:
        clean.pop()
    with bd.BuildSketch(bd.Plane.XZ) as sk2:
        bd.Polygon(*clean, align=None)
    return bd.revolve(sk2.sketch, axis=bd.Axis.Z)


def _straighten(pts, tol):
    """Douglas-Peucker on an open run: the points within tol mm of a straight line between their neighbours dropped"""
    if len(pts) < 3:
        return list(pts)
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy) or 1e-12
    far, idx = -1.0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][0] - x0) - dx * (pts[i][1] - y0)) / ln
        if d > far:
            far, idx = d, i
    if far <= tol:
        return [pts[0], pts[-1]]
    return _straighten(pts[: idx + 1], tol)[:-1] + _straighten(pts[idx:], tol)


def turned(top, back=None, tol=0.005):
    """a LATHE part: a profile in (r, z) revolved about Z — `top` the face from the axis (r = 0) out to the rim, `back`
    the other side from the rim back to the axis (default: flat at z = 0). Points within `tol` mm of a straight line
    are dropped first: sampled flat stretches (a terrace, a band) leave nearly-collinear points, and OpenCASCADE's
    revolve of them is no valid solid (the Tide Shield's stepped face, 2026-10-25: 1,200 samples -> invalid, the same
    profile straightened to 0.005 mm -> valid). A shield's stepped face, a bell, a turned knob, a vase"""
    top = [(max(0.0, float(r)), float(z)) for r, z in top]
    back = [(max(0.0, float(r)), float(z)) for r, z in back] if back else [(top[-1][0], 0.0), (0.0, 0.0)]
    pts = _straighten(top, tol) + _straighten(back, tol)
    clean = []
    for p in pts:
        if not clean or abs(p[0] - clean[-1][0]) + abs(p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    if abs(clean[0][0] - clean[-1][0]) + abs(clean[0][1] - clean[-1][1]) < 1e-6:
        clean.pop()
    with bd.BuildSketch(bd.Plane.XZ) as sk:
        bd.Polygon(*clean, align=None)
    return bd.revolve(sk.sketch, axis=bd.Axis.Z)


HELPERS["inlay"] = inlay
HELPERS["ring"] = ring
HELPERS["turned"] = turned


def _xy(v):
    return bd.Vector(float(v[0]), float(v[1]), 0.0)


def prims_face(prims):
    """primitives (kit/tools/primfit.py: lines + three-point arcs, a closed chain) -> one flat Face in XY"""
    edges = []
    for q in prims:
        a, b = _xy(q["a"]), _xy(q["b"])
        if (b - a).length < 1e-6:
            continue
        if q["type"] == "arc":
            edges.append(bd.Edge.make_three_point_arc(a, _xy(q["m"]), b))
        else:
            edges.append(bd.Edge.make_line(a, b))
    return bd.Face(bd.Wire(edges))


def redraw(pts, tol=0.15, corner_deg=35.0, mirror=None, equal_radii=0.08):
    """a TRACED outline REDRAWN as true lines + arcs (the way the part was designed) and returned as a Face: a 12 mm
    round is one 12 mm arc, a straight edge one line, near-equal radii made equal (equal_radii: their relative spread,
    0 = off), mirror=("x", 0.0): fitted on one side of x = 0 and mirrored (a symmetric part exactly symmetric). Lines
    and arcs fillet where a fitted spline refuses (Scarborough Fair, 2026-10-22: "the designs on it look so weird").
    pts may already be primitives (a dict list from `kit refs redraw`). In a sketch: add(redraw(pts))"""
    import primfit  # noqa: PLC0415  (kit/tools, next to this file)

    if pts and isinstance(pts[0], dict):
        prims = pts
    elif mirror:
        prims = primfit.fit_mirrored(pts, mirror[0], float(mirror[1]), tol=tol, corner_deg=corner_deg,
                                     equal=equal_radii or 0.0)
    else:
        prims = primfit.fit(pts, tol=tol, corner_deg=corner_deg, equal=equal_radii or 0.0)
    return prims_face(prims)   # (smooth joints TANGENT, radii made equal inside the fit: both hold — fillets take it)


def _half_profile(width, height, round_=1.0, n=24):
    """a bead's section in its own XY: a half superellipse w wide, h high, standing on y = 0 (round 1 = a half
    ellipse, less = flatter shoulders)"""
    e = 2.0 / max(2.0 * round_, 0.5)
    pts = [bd.Vector(width / 2, 0, 0)]
    for k in range(1, n):
        t = math.pi * k / n
        c, s = math.cos(t), math.sin(t)
        pts.append(bd.Vector(math.copysign(abs(c) ** e, c) * width / 2, (abs(s) ** e) * height, 0))
    pts.append(bd.Vector(-width / 2, 0, 0))
    arc = bd.Edge.make_spline(pts)
    return bd.Wire([arc, bd.Edge.make_line(pts[-1], pts[0])])


def bead(path, width, height, round=1.0, ends="round", tol=0.05):  # noqa: A002  (round: the profile's fullness)
    """raised TRIM as a real bead: a half-round (round=1) profile `width` wide and `height` high SWEPT along a path in
    the XY plane (mm, the surface at z = 0, the bead rising toward +z), its ends domed (ends="round") or cut ("flat").
    A gold border traced and extruded flat has square shoulders; a swept bead has the soft round top and clean ends of
    the art's raised trim (Scarborough Fair, 2026-10-22). Lay it on a curved part with inlay() or a.cad's own frame.
    path: [(x, y), ...] (a trim's centreline: kit refs inlays --centrelines), smoothed to tol mm"""
    ps = []
    for x, y in path:
        v = _xy((x, y))
        if not ps or (v - ps[-1]).length > 1e-3:
            ps.append(v)
    if len(ps) < 2:
        raise ValueError("bead: the path needs 2 or more distinct points")
    closed = (ps[0] - ps[-1]).length < 1e-3 and len(ps) > 3
    if closed:
        ps.pop()
    if len(ps) == 2:
        spine = bd.Edge.make_line(ps[0], ps[1])
    else:
        spine = (bd.Edge.make_spline(ps, periodic=True) if closed else bd.Edge.make_spline_approx(ps, tol=tol,
                                                                                                  max_deg=3))
    start, tan = spine @ 0, spine % 0
    side = bd.Vector(0, 0, 1).cross(tan).normalized()  # (in the surface, across the path)
    plane = bd.Plane(origin=start, x_dir=side, z_dir=tan)
    # the profile's own y is the plane's (z_dir x x_dir) = up (+z): the bead stands on the surface
    prof = bd.Face(plane * _half_profile(width, height, round))
    body = bd.sweep(prof, path=bd.Wire([spine]), transition=bd.Transition.ROUND)
    if ends == "round" and not closed:
        for at in (0.0, 1.0):
            cap = bd.Pos(spine @ at) * bd.scale(bd.Sphere(width / 2), by=(1, 1, 2 * height / width))
            cap = cap & (bd.Pos(spine @ at) * bd.Box(width * 2, width * 2, height * 2,
                                                                     align=(bd.Align.CENTER, bd.Align.CENTER,
                                                                            bd.Align.MIN)))
            body = body + cap
    return body


def setting(stone_d, girdle_z=1.0, wall=1.0, lip=0.35, lip_t=0.6, seat=0.5, height=None, round=1.0,  # noqa: A002
            prongs=0, prong_d=None):
    """a jewel's SETTING (bezel), revolved about Z from z = 0: a SEAT ledge the stone's girdle rests on at girdle_z,
    a wall `wall` mm thick round it, and a LIP that curls `lip` mm over the girdle (lip_t thick), its outer top
    rounded (round x the wall). prongs=N adds N claws leaning over the stone. A gem in a plain ring floats; a
    setting holds it, the way the art's surround does (Scarborough Fair, 2026-10-22: "the surrounding of it all
    smooth, not a square")"""
    rs = float(stone_d) / 2
    h = float(height) if height is not None else girdle_z + lip_t + 0.25
    ro = rs + wall
    r_lip = rs - lip
    rr = max(0.0, min(1.0, round)) * min(wall, h - girdle_z) * 0.95
    pts = [(rs - seat, 0.0), (ro, 0.0), (ro, h - rr)]
    for k in range(1, 11):  # (the outer top corner, rounded)
        t = math.radians(90 * k / 10)
        pts.append((ro - rr + rr * math.cos(t), h - rr + rr * math.sin(t)))
    pts += [(r_lip, h), (r_lip, h - lip_t), (rs + 0.02, h - lip_t), (rs + 0.02, girdle_z), (rs - seat, girdle_z)]
    clean = []
    for p in pts:
        if not clean or abs(p[0] - clean[-1][0]) + abs(p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    with bd.BuildSketch(bd.Plane.XZ) as sk:
        bd.Polygon(*clean, align=None)
    body = bd.revolve(sk.sketch, axis=bd.Axis.Z)
    if prongs:
        pd = float(prong_d) if prong_d else max(0.6, wall * 0.9)
        for k in range(int(prongs)):
            a = 360.0 * k / int(prongs)
            claw = bd.Pos(rs + pd * 0.25, 0, h) * bd.Rot(0, -25, 0) * bd.Cylinder(
                pd / 2, h * 0.9, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
            tip = bd.Pos(rs + pd * 0.25 - math.sin(math.radians(25)) * h * 0.9, 0,
                         h + math.cos(math.radians(25)) * h * 0.9) * bd.Sphere(pd / 2)
            body = body + bd.Rot(0, 0, a) * (claw + tip)
    return body


def lobed(r, n, depth, round=0.5):  # noqa: A002
    """a SCALLOPED round outline (a rosette, a cog-like housing, a crown): n lobes of radius r, the dips between them
    `depth` deep, every join TANGENT (arcs only: it fillets and offsets cleanly). round: the dips' share of each lobe
    (0.5: lobes and dips alike). -> a Face in XY, centred on the origin"""
    n = int(n)
    if n < 3 or depth <= 0 or depth >= r:
        raise ValueError("lobed: n >= 3 and 0 < depth < r")
    import primfit  # noqa: PLC0415  (kit/tools: the wave drawn as tangent ARCS — a spline would not offset)

    pts = []
    m = 48
    for k in range(n * m):
        t = 2 * math.pi * k / (n * m)
        # a smooth wave round the circle: lobes at r, dips at r - depth (a raised cosine: tangent everywhere)
        phase = (k % m) / m
        w = 0.5 * (1 - math.cos(2 * math.pi * phase))           # 0 at a lobe's top, 1 at a dip
        w = w ** (1.0 / max(0.15, min(round * 2, 3.0)))
        rr = r - depth * w
        pts.append((rr * math.cos(t), rr * math.sin(t)))
    return prims_face(primfit.fit(pts, tol=max(0.01, depth * 0.02), equal=0.02))


def dome(face, height, edge=None, steps=8, top=0.0):
    """a SCULPTED PILLOW on a flat outline (XY, rising along +Z from z = 0): the outline's wall rises and rolls over
    into the top on a quarter ellipse — `edge` wide, `height` high (edge = height: a round rim; edge > height: a
    long soft shoulder; edge = the outline's half width: a full dome) — and `top` more mm bulges its middle. A
    grip panel, a jewel's housing, a frame's side: never a flat plate with a bevel (the owner, 2026-10-23: "do not
    confuse smooth shading with smooth geometry"). Built as a loft through the outline's inward offsets, so it is
    exact CAD (fillets, cuts and unions take it). For simple outlines (a disc, lobed(), a rounded rectangle):
    OpenCASCADE's offsets split or fail on real TRACED outlines with thin spots — inflate those in Blender with
    a.pillow (kit/blender/rbx_pillow.py: the height from the distance to the outline, it never fails)"""
    edge = float(edge if edge is not None else height)
    stations = []
    for k in range(steps + 1):
        th = 0.5 * math.pi * k / steps
        d = edge * (1 - math.cos(th))          # (inset)
        z = height * math.sin(th)              # (rise)
        stations.append((d, z))
    wires = []
    for d, z in stations:
        f = face if d < 1e-6 else bd.offset(face, amount=-d, kind=bd.Kind.ARC)
        faces = f.faces() if hasattr(f, "faces") else [f]
        big = max(faces, key=lambda q: q.area)
        wires.append(bd.Pos(0, 0, z) * big.outer_wire())
    body = bd.loft([bd.Face(w) for w in wires], ruled=False)
    if top > 0:   # (the middle bulges a little more: a spherical cap over the flat top)
        inner = wires[-1]
        bb = inner.bounding_box()
        rad = 0.5 * max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y)
        R = (rad * rad + top * top) / (2 * top)
        cap = bd.Pos((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, height + top - R) * bd.Sphere(R)
        body = body + (cap & bd.extrude(bd.Face(inner), amount=top + 1e-3))
    return body


HELPERS.update(redraw=redraw, prims_face=prims_face, bead=bead, setting=setting, lobed=lobed, dome=dome)
