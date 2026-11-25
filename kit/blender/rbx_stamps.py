"""rbx_stamps.py — DETAIL STAMPS: the small surface detail an AAA artist stamps into a part's normal map instead of
modelling it (a.stamp): rivets, screws, bolts, vents, panel lines, grilles, knurling, weld beads. numpy only (tested
without Blender): each kind is a HEIGHT FIELD in millimetres over the stamp's box — 0 is the surface, + stands proud
(a rivet's dome), - is cut in (a vent's slot, a panel line) — and 0 on the box's border, so nothing steps where the
stamp ends. The bake projects it along the part's facing into the normal map (a Bump after the bevel normals): no
triangles, the detail the light catches (the owner judges close-ups; geometry for every rivet costs tris and floats).

    height(kind, size_mm=(w, h), px_per_mm=8, **opts) -> float32 (H, W), mm; row 0 is the box's TOP

kinds (opts):
    rivets      a row along the box's long side: count (auto by pitch), radius_mm (half the short side * 0.6)
    screws      domes with a slot or a cross: count, radius_mm, drive="slot" | "cross"
    bolts       hex heads, flat top, chamfered: count, radius_mm
    vent        slots across the long side: slats (auto), depth_mm
    panel_line  a groove round the box (outline) or along it (line=True): width_mm, depth_mm
    grille      a grid of round holes: pitch_mm, radius_mm, depth_mm
    knurl       a diamond knurl: pitch_mm, depth_mm
    weld        a bead of overlapping ripples along the long side: height_mm, ripple_mm
    stitches    a sewn seam: thread dashes along the long side: pitch_mm, thread_mm
    socket      cap screws with a HEX SOCKET (an Allen head): a flat round head, its edge rounded: count, radius_mm
    treadplate  DIAMOND / CHECKER PLATE: short raised bars, each cell's turned the other way: pitch_mm, height_mm
    louver      angled LOUVRES (a vent of lips, not slots): each slat a lip that stands proud and slopes back into
                the panel: slats, depth_mm
    hinge       a BARREL HINGE along the long side: its knuckles with a gap between each: knuckles, radius_mm
    rib         GRIP RIBS across the long side, rounded: count / pitch_mm, height_mm
    hammered    HAMMERED METAL: overlapping shallow dimples, the same on every build: pitch_mm, depth_mm
    nameplate   a raised PLATE with chamfered edges and a screw in each corner: height_mm, radius_mm (the screws)
    rope        a TWISTED ROPE along the long side: round strands laid at 35 degrees, a V between each: pitch_mm (one
                strand to the next along the rope), height_mm
    fluting     FLUTES: rounded channels cut along the long side, side by side across it, a flat fillet between each,
                their ends rounded like a column's: count, depth_mm
    milgrain    MILGRAIN: a row of tiny touching beads along the long side (a jeweller's or a bell's beaded edge):
                radius_mm, count
    scales      overlapping SCALES in offset rows, each one's free edge standing over the next row (a fish's, a
                dragon's): pitch_mm (a scale's width), height_mm, shape="round" | "pointed"; their free edges point
                DOWN the stamp (its row 0 is the top)
    scroll      a RUNNING SCROLL (the Vitruvian wave) along the long side: a raised round line that runs along the
                bottom, rises over each crest and curls into a spiral: pitch_mm (one wave), line_mm, height_mm
    ornament    ANY DRAWN ORNAMENT (H4, a.ornament): a mask picture (mask=: .png / .npy / .npz; an .svg is drawn to an
                .npy by rbx first) as relief - raised (or cut=True: engraved) depth_mm, its edge shaped by profile=
                "round" (a rounded bead), "v" (a chamfer to a ridge) or "flat" (a sharp-walled plateau) over edge_mm,
                from the EXACT distance of each pixel to the ornament's border (a signed-distance field, never a blur);
                threshold= where the mask turns ornament (0.5), invert=True for light lines on dark. finest_mm: the
                thinnest stroke's width (the bake's 2.5-texel check reads it)
"""

import os

import numpy as np

KINDS = ("rivets", "screws", "bolts", "vent", "panel_line", "grille", "knurl", "weld", "stitches",
         "socket", "treadplate", "louver", "hinge", "rib", "hammered", "nameplate",
         # (the ornament reliefs his V3 list asked for, 2026-11-18: the geometric ones - an acanthus leaf or a feather
         #  row is an organic form, drawn as a picture and stamped by a.ornament: typed organic forms were his
         #  verdict of 2026-11-12, "horrible")
         "rope", "fluting", "milgrain", "scales", "scroll")
OPEN_KINDS = ("hammered",)   # (shallow open dimples: never darkened as a recess that holds dirt)
PICTURE_KINDS = ("ornament",)   # (a stamp made from its own picture: no default to draw without one)
OPTIONS = {   # what each kind reads: anything else is a typo, refused (it would be silently ignored)
    "rivets": {"count", "radius_mm"}, "screws": {"count", "radius_mm", "drive"}, "bolts": {"count", "radius_mm"},
    "vent": {"slats", "depth_mm"}, "panel_line": {"width_mm", "depth_mm", "line"},
    "grille": {"pitch_mm", "radius_mm", "depth_mm"}, "knurl": {"pitch_mm", "depth_mm"},
    "weld": {"height_mm", "ripple_mm"},
    "stitches": {"pitch_mm", "thread_mm"},   # (a sewn seam: a row of thread dashes along the stamp's long side)
    "socket": {"count", "radius_mm"}, "treadplate": {"pitch_mm", "height_mm"}, "louver": {"slats", "depth_mm"},
    "hinge": {"knuckles", "radius_mm"}, "rib": {"count", "pitch_mm", "height_mm"},
    "hammered": {"pitch_mm", "depth_mm"}, "nameplate": {"height_mm", "radius_mm"},
    "rope": {"pitch_mm", "height_mm"}, "fluting": {"count", "depth_mm"}, "milgrain": {"radius_mm", "count"},
    "scales": {"pitch_mm", "height_mm", "shape"}, "scroll": {"pitch_mm", "line_mm", "height_mm"},
    "ornament": {"mask", "depth_mm", "profile", "edge_mm", "cut", "threshold", "invert"}}
PROFILES = ("round", "v", "flat")
MASK_READER = None   # (path -> float (H, W) 0..1, 1 = ornament): set by rbx inside Blender (no PIL there)
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MAX_PX = 2048   # a stamp's height image at most this many pixels a side (px_per_mm lowered to fit)


def check(kind, **o):
    """refuse an unknown kind, an option the kind does not read, a count / slats under 1, a size <= 0"""
    if kind not in KINDS + PICTURE_KINDS:
        raise ValueError(f'stamp: kind="{kind}" — one of {", ".join(KINDS + PICTURE_KINDS)}')
    bad = sorted(set(o) - OPTIONS[kind])
    if bad:
        raise ValueError(f'stamp "{kind}": no option {", ".join(bad)} (it reads {", ".join(sorted(OPTIONS[kind]))})')
    for k in ("count", "slats", "knuckles"):
        if k in o and int(o[k]) < 1:
            raise ValueError(f'stamp "{kind}": {k} must be >= 1')
    for k, v in o.items():
        if k.endswith("_mm") and float(v) <= 0:
            raise ValueError(f'stamp "{kind}": {k} must be > 0')
    if kind == "stitches" and "pitch_mm" in o and "thread_mm" in o and float(o["pitch_mm"]) < 2 * float(o["thread_mm"]):
        raise ValueError(f'stamp "stitches": pitch_mm={o["pitch_mm"]} is under twice thread_mm={o["thread_mm"]} - '
                         "a stitch and its gap need at least two threads' width")
    if kind == "ornament":
        if not o.get("mask"):
            raise ValueError('stamp "ornament": mask= (a .png / .npy / .npz picture of the ornament) is required')
        if "profile" in o and o["profile"] not in PROFILES:
            raise ValueError(f'stamp "ornament": profile="round", "v" or "flat", not {o["profile"]!r}')
        if "threshold" in o and not 0 < float(o["threshold"]) < 1:
            raise ValueError('stamp "ornament": threshold= between 0 and 1')
    if kind == "scales" and o.get("shape", "round") not in ("round", "pointed"):
        raise ValueError(f'stamp "scales": shape="round" or "pointed", not {o["shape"]!r}')
    if "drive" in o and o["drive"] not in ("slot", "cross"):
        raise ValueError(f'stamp "screws": drive="slot" or "cross", not {o["drive"]!r}')


def _grid(size_mm, px_per_mm):
    w_mm, h_mm = float(size_mm[0]), float(size_mm[1])
    W, H = max(8, int(round(w_mm * px_per_mm))), max(8, int(round(h_mm * px_per_mm)))
    x = (np.arange(W) + 0.5) / W * w_mm   # (mm from the left edge)
    y = (np.arange(H) + 0.5) / H * h_mm   # (mm from the top edge)
    return np.meshgrid(x, y), w_mm, h_mm


def _centres(w_mm, h_mm, count, r):
    """count centres along the long side, inset a radius and a half from its ends"""
    long_x = w_mm >= h_mm
    L = w_mm if long_x else h_mm
    lo, hi = min(r * 1.5, L / 2), max(L - r * 1.5, L / 2)
    ts = [L / 2] if count == 1 else list(np.linspace(lo, hi, count))
    return [(t, h_mm / 2) if long_x else (w_mm / 2, t) for t in ts]


def _dome(X, Y, cx, cy, r, h):
    d2 = ((X - cx) ** 2 + (Y - cy) ** 2) / (r * r)
    return np.where(d2 < 1, h * np.sqrt(np.clip(1 - d2, 0, 1)), 0.0)


def _auto_count(w_mm, h_mm, r, pitch=3.2):
    return max(1, int((max(w_mm, h_mm) - r) // (r * pitch)) + 1)


def height(kind, size_mm=(20.0, 6.0), px_per_mm=8.0, **o):
    """the stamp's height field (mm, + proud / - cut in), (H, W) float32, 0 on the border — see the module page"""
    check(kind, **o)
    px_per_mm = min(float(px_per_mm), MAX_PX / max(float(size_mm[0]), float(size_mm[1]), 1e-6))
    (X, Y), w_mm, h_mm = _grid(size_mm, px_per_mm)
    short = min(w_mm, h_mm)
    out = np.zeros_like(X)
    if kind in ("rivets", "screws", "bolts"):
        r = float(o.get("radius_mm", short * 0.3))
        n = int(o.get("count", _auto_count(w_mm, h_mm, r)))
        for cx, cy in _centres(w_mm, h_mm, n, r):
            if kind == "rivets":   # a round head: a dome a little under half its radius tall
                out = np.maximum(out, _dome(X, Y, cx, cy, r, r * 0.45))
            elif kind == "screws":   # a lower dome with its drive cut in
                head = _dome(X, Y, cx, cy, r, r * 0.3)
                slot = (np.abs(Y - cy) < r * 0.12) & (np.abs(X - cx) < r * 0.75)
                if o.get("drive", "slot") == "cross":
                    slot |= (np.abs(X - cx) < r * 0.12) & (np.abs(Y - cy) < r * 0.75)
                # (np.where, not np.maximum: a maximum with the flat surface's 0 would erase the drive cut below it)
                out = np.where(head > 0, np.where(slot, -r * 0.15, head), out)
            else:   # a hex head: flat top, its six sides chamfered down to the surface
                ang = np.arctan2(Y - cy, X - cx)
                rad = np.hypot(X - cx, Y - cy)
                sector = np.cos((ang % (np.pi / 3)) - np.pi / 6)   # (the hexagon's distance to its edge, per angle)
                edge = r * np.cos(np.pi / 6) / np.maximum(sector, 1e-6)
                top = r * 0.55
                hgt = np.clip((edge - rad) / (r * 0.18), 0, 1) * top
                out = np.maximum(out, np.where(rad < edge, hgt, 0.0))
    elif kind == "vent":
        depth = float(o.get("depth_mm", short * 0.15))
        long_x = w_mm >= h_mm
        L, S = (w_mm, h_mm) if long_x else (h_mm, w_mm)
        n = int(o.get("slats", max(3, int(L / max(S * 0.18, 1.5)))))   # (a slot every ~a fifth of the width)
        pitch = L / (n + 0.5)
        t = (X if long_x else Y)
        s = (Y if long_x else X)
        k = (t - pitch * 0.75) / pitch
        in_slot = (np.abs(k - np.round(k)) < 0.22) & (k > -0.5) & (k < n - 0.5) & (np.abs(s - S / 2) < S * 0.38)
        out = np.where(in_slot, -depth, 0.0)
    elif kind == "panel_line":
        width = float(o.get("width_mm", max(0.6, short * 0.08)))
        depth = float(o.get("depth_mm", width * 0.6))
        if o.get("line"):   # (along the long side, through the middle)
            dist = np.abs((Y if w_mm >= h_mm else X) - (h_mm if w_mm >= h_mm else w_mm) / 2)
        else:   # (a rectangle inset from the border: a hatch, a cover plate)
            inset = width * 1.5
            dist = np.abs(np.minimum(np.minimum(X - inset, w_mm - inset - X), np.minimum(Y - inset, h_mm - inset - Y)))
        # a rounded groove: deepest on its line, back to the surface at its edges
        out = -depth * np.sqrt(np.clip(1 - (dist / (width / 2)) ** 2, 0, 1))
    elif kind == "grille":
        pitch = float(o.get("pitch_mm", short / 3))
        r = float(o.get("radius_mm", pitch * 0.32))
        depth = float(o.get("depth_mm", r))
        gx = (X - w_mm / 2) / pitch
        gy = (Y - h_mm / 2) / pitch
        col = np.round(gx)
        gy_s = gy + 0.5 * (col % 2)   # (staggered rows: a punched grille)
        row = np.round(gy_s)
        d = np.hypot(gx - col, gy_s - row) * pitch
        hx = col * pitch + w_mm / 2                      # (each hole's centre: a hole that would cross the border
        hy = (row - 0.5 * (col % 2)) * pitch + h_mm / 2  #  is left out whole, never cut in half)
        inside = (hx - r > r * 0.5) & (hx + r < w_mm - r * 0.5) & (hy - r > r * 0.5) & (hy + r < h_mm - r * 0.5)
        out = np.where((d < r) & inside, -depth, 0.0)
    elif kind == "knurl":
        pitch = float(o.get("pitch_mm", 1.2))
        depth = float(o.get("depth_mm", pitch * 0.3))
        a = np.abs(((X + Y) / pitch) % 1 - 0.5) * 2   # (two crossing ridges: 1 on a crest, 0 in a groove)
        b = np.abs(((X - Y) / pitch) % 1 - 0.5) * 2
        out = (np.minimum(a, b) - 0.5) * depth
    elif kind == "weld":
        hgt = float(o.get("height_mm", short * 0.3))
        ripple = float(o.get("ripple_mm", short * 0.35))
        long_x = w_mm >= h_mm
        t, s, S = (X, Y, h_mm) if long_x else (Y, X, w_mm)
        across = np.clip(1 - ((s - S / 2) / (S * 0.45)) ** 2, 0, 1)
        arcs = 0.82 + 0.18 * np.cos(2 * np.pi * (t / ripple + ((s - S / 2) / S) ** 2 * 1.4))   # (the bead's ripples)
        L = w_mm if long_x else h_mm
        ends = np.clip(np.minimum(t, L - t) / ripple, 0, 1) ** 0.5   # (the bead starts and stops: tapered ends)
        out = hgt * np.sqrt(across) * arcs * ends
    elif kind == "stitches":
        # A SEWN SEAM: thread dashes along the long side, each a rounded ridge that dives into the cloth at both
        # ends (a small dip where the needle went in), a gap between one stitch and the next
        thread = min(float(o.get("thread_mm", max(0.5, short * 0.25))), short)   # (never wider than the stamp)
        pitch = float(o.get("pitch_mm", thread * 4.0))
        long_x = w_mm >= h_mm
        t, s, S = (X, Y, h_mm) if long_x else (Y, X, w_mm)
        along = (t / pitch) % 1.0                                   # 0..1 within one stitch
        on = np.clip((0.5 - np.abs(along - 0.5)) / 0.5 * 2.8, 0, 1) * (np.abs(along - 0.5) < 0.36)
        across = np.clip(1 - ((s - S / 2) / (thread / 2)) ** 2, 0, 1)
        ridge = thread * 0.5 * np.sqrt(across) * np.sqrt(on)        # a round thread, tapering into its holes
        hole = np.exp(-(((np.abs(along - 0.5) - 0.36) * pitch) ** 2 + (s - S / 2) ** 2) / (thread * 0.35) ** 2)
        out = ridge - thread * 0.3 * hole
    elif kind == "socket":   # a cap screw's flat round head, its rim rounded, a hex socket cut into it
        r = float(o.get("radius_mm", short * 0.3))
        n = int(o.get("count", _auto_count(w_mm, h_mm, r)))
        for cx, cy in _centres(w_mm, h_mm, n, r):
            rad = np.hypot(X - cx, Y - cy)
            top = r * 0.4
            head = np.where(rad < r, top * np.sqrt(np.clip(1 - np.clip((rad - r * 0.75) / (r * 0.25), 0, 1) ** 2, 0, 1)), 0)
            ang = np.arctan2(Y - cy, X - cx)
            sector = np.cos((ang % (np.pi / 3)) - np.pi / 6)
            hexr = r * 0.45 / np.maximum(sector, 1e-6) * np.cos(np.pi / 6)   # (the socket: 0.9 r corner to corner)
            # its mouth chamfered: from the head's top down to the socket's floor over a tenth of the radius
            sock = top - np.clip((hexr - rad) / (r * 0.1), 0, 1) * (top + r * 0.2)
            out = np.where(rad < r, np.where(rad < hexr, sock, head), out)
    elif kind == "treadplate":
        pitch = float(o.get("pitch_mm", max(short / 3, 4.0)))
        hgt = float(o.get("height_mm", pitch * 0.12))
        gx, gy = X / pitch, Y / pitch
        cx_, cy_ = np.floor(gx), np.floor(gy)
        fx, fy = gx - cx_ - 0.5, gy - cy_ - 0.5
        turn = np.where((cx_ + cy_) % 2 == 0, 1.0, -1.0)            # (each cell's bar the other way: the checker)
        a_ = (fx + turn * fy) / np.sqrt(2)                          # along the bar
        b_ = (fx - turn * fy) / np.sqrt(2)                          # across it
        bar = np.clip(1 - (np.abs(a_) / 0.36) ** 4, 0, 1) * np.sqrt(np.clip(1 - (b_ / 0.09) ** 2, 0, 1))
        out = hgt * bar
    elif kind == "louver":
        depth = float(o.get("depth_mm", short * 0.12))
        long_x = w_mm >= h_mm
        L, S_ = (w_mm, h_mm) if long_x else (h_mm, w_mm)
        n = int(o.get("slats", max(3, int(L / max(S_ * 0.22, 2.0)))))
        pitch = L / (n + 0.5)
        t = (X if long_x else Y)
        s_ = (Y if long_x else X)
        k = (t - pitch * 0.25) / pitch
        f = k - np.floor(k)                                         # 0..1 within a slat
        inside = (k >= 0) & (k < n) & (np.abs(s_ - S_ / 2) < S_ * 0.4)
        lip = np.where(f < 0.15, f / 0.15, 1 - (f - 0.15) / 0.85)   # (a sharp rise to the lip, a long slope back)
        ends = np.clip((S_ * 0.4 - np.abs(s_ - S_ / 2)) / (S_ * 0.06), 0, 1)
        out = np.where(inside, depth * (lip * 1.4 - 0.6) * ends, 0.0)
    elif kind == "hinge":
        long_x = w_mm >= h_mm
        L, S_ = (w_mm, h_mm) if long_x else (h_mm, w_mm)
        r = min(float(o.get("radius_mm", S_ * 0.35)), S_ / 2)
        n = int(o.get("knuckles", max(3, int(round(L / max(r * 4, 1e-6))) | 1)))
        t = (X if long_x else Y)
        s_ = (Y if long_x else X)
        seg = L / n
        gap = seg * 0.08
        f = (t % seg)
        on = (f > gap / 2) & (f < seg - gap / 2)
        barrel = r * np.sqrt(np.clip(1 - ((s_ - S_ / 2) / r) ** 2, 0, 1))
        out = np.where(on, barrel, 0.0)
    elif kind == "rib":
        long_x = w_mm >= h_mm
        L, S_ = (w_mm, h_mm) if long_x else (h_mm, w_mm)
        pitch = float(o.get("pitch_mm", L / int(o["count"]) if "count" in o else max(S_ * 0.25, 1.5)))
        hgt = float(o.get("height_mm", pitch * 0.25))
        t = (X if long_x else Y)
        s_ = (Y if long_x else X)
        f = ((t - (L % pitch) / 2) / pitch) % 1.0 - 0.5
        rib = np.sqrt(np.clip(1 - (f / 0.3) ** 2, 0, 1))
        ends = np.clip((S_ * 0.45 - np.abs(s_ - S_ / 2)) / (S_ * 0.08), 0, 1)
        out = hgt * rib * ends
    elif kind == "hammered":
        pitch = float(o.get("pitch_mm", max(short / 4, 2.0)))
        depth = float(o.get("depth_mm", pitch * 0.08))   # (0.24 mm at a 3 mm pitch: a hammered sheet's dimple)
        rng = np.random.default_rng(1729)   # (the same dimples on every build)
        nx, ny = int(np.ceil(w_mm / pitch)) + 2, int(np.ceil(h_mm / pitch)) + 2
        cx_ = (np.arange(nx)[None, :] - 0.5 + rng.uniform(-0.35, 0.35, (ny, nx))) * pitch
        cy_ = (np.arange(ny)[:, None] - 0.5 + rng.uniform(-0.35, 0.35, (ny, nx))) * pitch
        rr = pitch * rng.uniform(0.6, 0.85, (ny, nx))
        dd = rng.uniform(0.6, 1.0, (ny, nx))                        # (each blow a little deeper or shallower)
        # each dimple a shallow bowl; where two overlap the deeper wins SOFTLY (a smooth maximum: a hammered
        # surface's ridges are rounded by the next blow, never sharp creases)
        acc = np.zeros_like(X)
        k = 8.0
        for cx, cy, r, dk in zip(cx_.ravel(), cy_.ravel(), rr.ravel(), dd.ravel()):
            b = dk * np.clip(1 - ((X - cx) ** 2 + (Y - cy) ** 2) / (r * r), 0, 1) ** 1.5
            acc += np.exp(k * b) - 1
        out = -depth * np.log1p(acc) / k
        # centred on the surface: the ridges stand as far proud as the dimples sink (all of it below the surface,
        # the bake darkened every dimple like grime in a recess: blotches, not hammered metal)
        out = out - float(out.mean())
    elif kind == "nameplate":
        hgt = float(o.get("height_mm", min(short * 0.06, 1.2)))
        inset = max(short * 0.06, 2.0 / px_per_mm)
        edge = max(hgt * 1.5, 1.5 / px_per_mm)
        d = np.minimum(np.minimum(X - inset, w_mm - inset - X), np.minimum(Y - inset, h_mm - inset - Y))
        out = hgt * np.clip(d / edge, 0, 1)                          # (the plate, its edges chamfered)
        r = float(o.get("radius_mm", short * 0.07))
        for cx, cy in ((inset + edge + r * 1.4, inset + edge + r * 1.4), (w_mm - inset - edge - r * 1.4, inset + edge + r * 1.4),
                       (inset + edge + r * 1.4, h_mm - inset - edge - r * 1.4),
                       (w_mm - inset - edge - r * 1.4, h_mm - inset - edge - r * 1.4)):
            out = out + _dome(X, Y, cx, cy, r, r * 0.4)
    elif kind in ("rope", "fluting", "milgrain", "scales", "scroll"):
        out = _ornament_relief(kind, X, Y, w_mm, h_mm, o)
    elif kind == "ornament":
        on = ornament_mask(o, X.shape)
        d = inside_distance(on, int(np.ceil(_edge_mm(o) * px_per_mm)) + 2) - 0.5   # (px: the border's own pixel 0.5)
        out = _profile(d / px_per_mm, o)
    # 0 on the border: a 1-px frame, faded over 1.5 px, so the stamp never steps where it ends
    fade = np.minimum.reduce([X, w_mm - X, Y, h_mm - Y]) * px_per_mm
    out = out * np.clip((fade - 1.0) / 1.5, 0, 1)
    return out.astype(np.float32)


def _scroll_sizes(w_mm, h_mm, o):
    """-> (pitch, line width, height, outer radius) of a running scroll in this box (mm)"""
    S = min(w_mm, h_mm)
    pitch = float(o.get("pitch_mm", S * 1.15))
    line = float(o.get("line_mm", pitch * 0.085))
    hgt = float(o.get("height_mm", line * 0.55))
    r0 = min(pitch / 2.4, (S / 2 - line) / 0.94)   # (the spiral's outer turn: it fits the band and the wave)
    return pitch, line, hgt, max(r0, line * 1.5)


def _seg_distance(px, py, pts):
    """the distance (mm) from every point (px, py) to the polyline pts (n, 2) -> (px.shape)"""
    qx, qy = px.ravel()[None], py.ravel()[None]
    best = np.full(qx.shape[1], np.inf)
    a, b = pts[:-1], pts[1:]
    for k in range(0, len(a), 64):   # (64 segments at a time: memory stays small on a 2048-px stamp)
        ax, ay = a[k:k + 64, 0][:, None], a[k:k + 64, 1][:, None]
        dx, dy = b[k:k + 64, 0][:, None] - ax, b[k:k + 64, 1][:, None] - ay
        u = np.clip(((qx - ax) * dx + (qy - ay) * dy) / np.maximum(dx * dx + dy * dy, 1e-12), 0, 1)
        best = np.minimum(best, np.hypot(qx - (ax + u * dx), qy - (ay + u * dy)).min(0))
    return best.reshape(px.shape)


def scroll_line(w_mm, h_mm, o):
    """the running scroll's centre line along t (the long side) and s (across it, growing DOWN the stamp), mm: one
    polyline a wave - the trough leaving the last spiral's foot along the bottom, the back of the wave, the crest,
    and the spiral it curls into (2.25 turns, its radius falling to 0.15 of its outer turn). -> [(n, 2) arrays]"""
    L, S = max(w_mm, h_mm), min(w_mm, h_mm)
    pitch, line, _h, r0 = _scroll_sizes(w_mm, h_mm, o)
    n = max(1, int((L - 2 * line - 2.2 * r0) // pitch) + 1)
    used = (n - 1) * pitch + 1.9 * r0
    x0 = (L - used) / 2 + r0                      # (the first spiral's centre: the waves centred along the band)
    cy = S / 2
    b = np.log(1 / 0.15) / (4.5 * np.pi)
    foot = r0 * np.exp(-b * 1.5 * np.pi)          # (the outer turn's lowest point, under its centre)
    out = []
    for k in range(n):
        cx = x0 + k * pitch
        phi = np.linspace(np.pi, np.pi + 4.5 * np.pi, 160)
        r = r0 * np.exp(-b * (phi - np.pi))
        spiral = np.stack([cx + r * np.cos(phi), cy + r * np.sin(phi)], 1)
        pa = np.array([cx - pitch, cy + foot]) if k else np.array([max(line, cx - pitch * 0.85), cy + foot])
        pb = spiral[0]
        c1, c2 = pa + [pitch * 0.35, 0.0], pb + [0.0, r0 * 0.9]
        u = np.linspace(0, 1, 40)[:, None]
        trough = (1 - u) ** 3 * pa + 3 * (1 - u) ** 2 * u * c1 + 3 * (1 - u) * u ** 2 * c2 + u ** 3 * pb
        out.append(np.vstack([trough, spiral[1:]]))
    return out


def _box(X, Y, x0, x1, y0, y1):
    """the pixels of the grid (X, Y) whose centres fall in [x0, x1] x [y0, y1] mm, as a slice pair, or None"""
    xs, ys = X[0], Y[:, 0]
    i0, i1 = int(np.searchsorted(xs, x0)), int(np.searchsorted(xs, x1, side="right"))
    j0, j1 = int(np.searchsorted(ys, y0)), int(np.searchsorted(ys, y1, side="right"))
    return (slice(j0, j1), slice(i0, i1)) if i1 > i0 and j1 > j0 else None


def _ornament_relief(kind, X, Y, w_mm, h_mm, o):
    """the geometric ornament reliefs (rope, fluting, milgrain, scales, scroll): their height field, mm"""
    short = min(w_mm, h_mm)
    long_x = w_mm >= h_mm
    t, s_, L, S = (X, Y, w_mm, h_mm) if long_x else (Y, X, h_mm, w_mm)
    if kind == "rope":
        pitch = float(o.get("pitch_mm", S * 0.6))
        hgt = float(o.get("height_mm", S * 0.3))
        R = S * 0.48
        cord = np.sqrt(np.clip(1 - ((s_ - S / 2) / R) ** 2, 0, 1))                # (the rope's round section)
        # each strand is a HELIX round the rope: seen from the front its groove is the helix's projection, steep
        # across the middle and turning along the rope at its edges (three strands: one turn is three pitches)
        theta = np.arcsin(np.clip((s_ - S / 2) / R, -1, 1))
        f = ((t - 3 * pitch * theta / (2 * np.pi)) / pitch) % 1.0                  # (where in its strand)
        strand = np.sqrt(np.clip(1 - (2 * f - 1) ** 2, 0, 1)) ** 0.7              # (round strands, a V between)
        ends = np.clip(np.minimum(t, L - t) / (S * 0.25), 0, 1) ** 0.5           # (the rope is whipped at its ends)
        return hgt * cord * (0.62 + 0.38 * strand) * ends
    if kind == "fluting":
        n = int(o.get("count", 5))
        pitch = S / n
        depth = float(o.get("depth_mm", pitch * 0.32))
        u = (s_ / pitch) % 1.0 - 0.5                                               # (across one flute)
        cut = np.sqrt(np.clip(1 - (u / 0.42) ** 2, 0, 1))                          # (its round channel; 16% fillet)
        e = np.minimum(t, L - t) - pitch * 0.5                                     # (its ends rounded, a radius in)
        end = np.sqrt(np.clip(1 - np.clip(-e / (pitch * 0.42), 0, None) ** 2, 0, 1)) * (e > -pitch * 0.42)
        return -depth * cut * end
    if kind == "milgrain":
        r = min(float(o.get("radius_mm", S * 0.35)), S * 0.45)
        pitch = 2 * r * 1.08                                                       # (touching beads, a hair apart)
        n = int(o.get("count", max(1, int((L - 0.6 * r) // pitch))))
        out = np.zeros_like(X)
        for k in range(n):
            c = (L - (n - 1) * pitch) / 2 + k * pitch
            box = _box(X, Y, *((c - r, c + r, 0, S) if long_x else (0, S, c - r, c + r)))
            out[box] = np.maximum(out[box], _dome(t[box], s_[box], c, S / 2, r, r * 0.8))
        return out
    if kind == "scales":
        pitch = float(o.get("pitch_mm", short / 3))
        hgt = float(o.get("height_mm", pitch * 0.12))
        r, row = pitch / 2, pitch * 0.42                                           # (rows overlap by over half)
        pointed = o.get("shape", "round") == "pointed"
        out = np.zeros_like(X)
        # the BOTTOM row first: each row above lays its free lower edge over the row below (a fish's scales overlap
        # toward its tail), so what shows of a scale is its lower part, rising to the edge that stands over the next
        for j in range(int(np.ceil(h_mm / row)) + 1, -2, -1):
            cy = j * row
            for i in range(-1, int(np.ceil(w_mm / pitch)) + 2):
                cx = (i + (0.5 if j % 2 else 0.0)) * pitch
                box = _box(X, Y, cx - r, cx + r, cy - r, cy + r * 1.35)            # (only this scale's pixels)
                if box is None:
                    continue
                dx, dy = X[box] - cx, Y[box] - cy
                inside = dx * dx + dy * dy <= r * r
                if pointed:   # (round shoulders, a pointed tip below: a dragon's)
                    inside = np.where(dy > 0, np.abs(dx) <= r * np.clip(1 - dy / (r * 1.35), 0, 1), inside)
                rise = np.clip((dy / r + 1) / 2, 0, 1) ** 1.6                      # (tucked under above, proud below: smooth)
                dome = np.sqrt(np.clip(1 - (dx / r) ** 2, 0, 1))
                out[box] = np.where(inside, hgt * (0.15 + 0.85 * rise) * (0.35 + 0.65 * dome), out[box])
        return out
    if kind == "scroll":
        _p, line, hgt, _r = _scroll_sizes(w_mm, h_mm, o)
        d = np.full(X.shape, np.inf)
        for pts in scroll_line(w_mm, h_mm, o):
            lo, hi = pts[:, 0].min() - line, pts[:, 0].max() + line   # (only the columns this wave is in)
            if long_x:
                cols = (t[0] >= lo) & (t[0] <= hi)
                if cols.any():
                    d[:, cols] = np.minimum(d[:, cols], _seg_distance(t[:, cols], s_[:, cols], pts))
            else:
                rows = (t[:, 0] >= lo) & (t[:, 0] <= hi)
                if rows.any():
                    d[rows, :] = np.minimum(d[rows, :], _seg_distance(t[rows, :], s_[rows, :], pts))
        return hgt * np.sqrt(np.clip(1 - (d / (line / 2)) ** 2, 0, 1))             # (a round line)
    raise ValueError(kind)


def facing_axes(facing):
    """(normal, right, up) unit vectors in the kit's frame (x right, y up, z back) for a stamp on a face pointing
    `facing`: the picture is seen from outside that face, its right and up as a viewer standing there sees them"""
    f = facing.upper()
    # (right = up x normal: a viewer standing outside the FRONT face (-Z) sees the model's +X on their LEFT — the
    #  model's own right; from above, the picture's up is the back (+Z), from below the front (-Z))
    table = {
        "-Z": ((0, 0, -1), (-1, 0, 0), (0, 1, 0)), "+Z": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
        "-X": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)), "+X": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
        "+Y": ((0, 1, 0), (-1, 0, 0), (0, 0, 1)), "-Y": ((0, -1, 0), (-1, 0, 0), (0, 0, -1))}
    key = f if f[0] in "+-" else "+" + f
    if key not in table:
        raise ValueError(f'stamp: facing="{facing}" — one of +X -X +Y -Y +Z -Z')
    return tuple(np.array(v, dtype=np.float64) for v in table[key])


def finest_mm(kind, size_mm, px_per_mm=None, **o):
    """the smallest thing a stamp must show (mm): a rivet's dome, a screw's drive slot, a bolt's chamfer, a vent's
    slot, a panel line, a grille's hole, half a knurl pitch, a weld's ripple — what has to cover a few texels of the
    baked map to read at all (a 3 mm screw's slot on a 2048 map of a 1.5 m model is under one texel)"""
    check(kind, **o)
    w_mm, h_mm = float(size_mm[0]), float(size_mm[1])
    short = min(w_mm, h_mm)
    r = float(o.get("radius_mm", short * 0.3))
    if kind == "rivets":
        return 2 * r
    if kind == "screws":
        return r * 0.24
    if kind == "bolts":
        return r * 0.18
    if kind == "vent":
        L = max(w_mm, h_mm)
        n = int(o.get("slats", max(3, int(L / max(short * 0.18, 1.5)))))
        return L / (n + 0.5) * 0.44
    if kind == "panel_line":
        return float(o.get("width_mm", max(0.6, short * 0.08)))
    if kind == "stitches":
        return float(o.get("thread_mm", max(0.5, short * 0.25)))
    if kind == "grille":
        pitch = float(o.get("pitch_mm", short / 3))
        return 2 * float(o.get("radius_mm", pitch * 0.32))
    if kind == "knurl":
        return float(o.get("pitch_mm", 1.2)) / 2
    if kind == "socket":
        return r * 0.3
    if kind == "treadplate":
        return float(o.get("pitch_mm", max(short / 3, 4.0))) * 0.18
    if kind == "louver":
        L = max(w_mm, h_mm)
        n = int(o.get("slats", max(3, int(L / max(short * 0.22, 2.0)))))
        return L / (n + 0.5) * 0.15
    if kind == "hinge":
        L = max(w_mm, h_mm)
        r_ = min(float(o.get("radius_mm", short * 0.35)), short / 2)
        n = int(o.get("knuckles", max(3, int(round(L / max(r_ * 4, 1e-6))) | 1)))
        return L / n * 0.08
    if kind == "rib":
        L = max(w_mm, h_mm)
        return float(o.get("pitch_mm", L / int(o["count"]) if "count" in o else max(short * 0.25, 1.5))) * 0.6
    if kind == "hammered":
        return float(o.get("pitch_mm", max(short / 4, 2.0))) * 0.5
    if kind == "nameplate":
        return float(o.get("radius_mm", short * 0.07)) * 2
    if kind == "rope":   # (the V between two strands)
        return float(o.get("pitch_mm", short * 0.6)) * 0.25
    if kind == "fluting":   # (the fillet between two flutes)
        return short / int(o.get("count", 5)) * 0.16
    if kind == "milgrain":   # (a bead's radius: the row reads as beads only while each covers a few texels)
        return min(float(o.get("radius_mm", short * 0.35)), short * 0.45)
    if kind == "scales":   # (the step of a free edge)
        return float(o.get("pitch_mm", short / 3)) * 0.12
    if kind == "scroll":
        return _scroll_sizes(w_mm, h_mm, o)[1]
    if kind == "ornament":   # the thinnest stroke (a 5th percentile over the strokes' middle lines, never one stray pixel)
        px_per_mm = min(8.0 if px_per_mm is None else float(px_per_mm), MAX_PX / max(w_mm, h_mm, 1e-6))
        (X, _Y), _w, _h = _grid(size_mm, px_per_mm)
        return stroke_widths(ornament_mask(o, X.shape), STROKE_CAP)[0] / px_per_mm
    return float(o.get("ripple_mm", short * 0.35))   # weld


# --- ornament (H4): a mask picture as relief, its edge from the exact distance to the border -----------------------

STROKE_CAP = 96   # px: strokes wider than twice this are measured as this (none of them is the finest)


def _edge_mm(o):
    depth = abs(float(o.get("depth_mm", 0.8)))
    return float(o.get("edge_mm", max(depth, 0.2)))


def _profile(d_mm, o):
    """height (mm) from each pixel's distance inside the ornament (mm; <= 0 outside): round = a quarter circle over
    edge_mm, v = a straight chamfer over it, flat = a sharp wall (one pixel's ramp); cut=True engraves (negative)"""
    depth = abs(float(o.get("depth_mm", 0.8)))
    b = _edge_mm(o)
    t = np.clip(d_mm / max(b, 1e-6), 0, 1)
    prof = o.get("profile", "round")
    if prof == "round":
        h = np.sqrt(np.clip(1 - (1 - t) ** 2, 0, 1))
    elif prof == "v":
        h = t
    else:
        h = (d_mm > 0).astype(np.float64)
    h = np.where(d_mm > 0, h, 0.0) * depth
    return -h if o.get("cut") else h


def read_mask(path):
    """a mask picture -> float (H, W) 0..1, 1 = ornament, row 0 the TOP: a .npy / .npz ("mask") as it is; a picture
    with a real alpha (some pixels clear, some solid) by its alpha, else by its darkness (dark lines on light paper)"""
    full = path if os.path.isabs(path) else os.path.join(REPO, path)
    if not os.path.isfile(full):
        raise FileNotFoundError(f'stamp "ornament": mask {path} not found')
    low = full.lower()
    if low.endswith(".npy"):
        a = np.load(full).astype(np.float64)
    elif low.endswith(".npz"):
        a = np.load(full)["mask"].astype(np.float64)
    else:
        try:
            from PIL import Image  # noqa: PLC0415
            a = np.asarray(Image.open(full).convert("RGBA"), np.float64) / 255.0
        except ImportError:
            if MASK_READER is None:
                raise
            a = np.asarray(MASK_READER(full), np.float64)
        if a.ndim == 3:
            alpha = a[..., 3]
            if alpha.min() < 0.5 < alpha.max():
                a = alpha
            else:
                a = 1.0 - (a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722)
    if a.ndim != 2:
        raise ValueError(f'stamp "ornament": mask {path} is not one picture (shape {a.shape})')
    if a.max() > 1.0:
        a = a / 255.0
    return np.clip(a, 0, 1)


def _resample(a, shape):
    """bilinear resample of a (h, w) picture to `shape` (pixel centres aligned)"""
    h, w = a.shape
    H, W = shape
    y = np.clip((np.arange(H) + 0.5) / H * h - 0.5, 0, h - 1)
    x = np.clip((np.arange(W) + 0.5) / W * w - 0.5, 0, w - 1)
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    fy, fx = (y - y0)[:, None], (x - x0)[None, :]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bot = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


def ornament_mask(o, shape):
    """the ornament's pixels on the stamp's grid (bool, row 0 the top)"""
    a = read_mask(str(o["mask"]))
    if o.get("invert"):
        a = 1.0 - a
    return _resample(a, shape) >= float(o.get("threshold", 0.5))


def inside_distance(mask, cap):
    """px from each True pixel's centre to the nearest False pixel's centre - the EXACT Euclidean distance up to
    `cap` (beyond it: cap); 0 on False pixels. Outside the picture counts as False (an ornament ends at its border)"""
    m = np.asarray(mask, bool)
    H, W = m.shape
    cap = int(max(1, cap))
    big = np.float32(cap + 1)
    g = np.empty((H, W), np.float32)   # down each column: the distance to the nearest False row
    run = np.zeros(W, np.float32)
    for y in range(H):
        run = np.where(m[y], np.minimum(run + 1, big), 0)
        g[y] = run
    run = np.zeros(W, np.float32)
    for y in range(H - 1, -1, -1):
        run = np.where(m[y], np.minimum(run + 1, big), 0)
        g[y] = np.minimum(g[y], run)
    pad = np.pad(g, ((0, 0), (cap, cap)), constant_values=0)   # (outside: False)
    best = g.astype(np.float64) ** 2
    for k in range(1, cap + 1):   # along each row: the nearest column's distance with its offset (exact to `cap`)
        near = np.minimum(pad[:, cap - k:cap - k + W], pad[:, cap + k:cap + k + W]).astype(np.float64)
        best = np.minimum(best, near ** 2 + k * k)
    return np.minimum(np.sqrt(best), cap).astype(np.float32) * m


def stroke_widths(mask, cap=STROKE_CAP):
    """(the thinnest stroke's width in px - a 5th percentile over the strokes' middle lines -, every middle-line
    width): a middle-line pixel is one no 8-neighbour lies deeper inside than; its stroke is 2 d - 1 px wide"""
    d = inside_distance(mask, cap)
    if not d.any():
        return 0.0, np.zeros(0, np.float32)
    p = np.pad(d, 1)
    nb = np.max([p[1 + dy:1 + dy + d.shape[0], 1 + dx:1 + dx + d.shape[1]]
                 for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx], axis=0)
    ridge = (d > 0) & (d >= nb)
    w = 2 * d[ridge] - 1
    return float(np.percentile(w, 5)), w


def raster_triangles(tris, H, W):
    """triangles in pixel coordinates (N, 3, 2: x right, y down) -> a (H, W) bool mask of the pixel centres they cover
    (an .svg ornament's filled shapes, triangulated by Blender: holes are already left out of the triangles)"""
    out = np.zeros((H, W), bool)
    for t in np.asarray(tris, np.float64):
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = t
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / d
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / d
        inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (l1 + l2 <= 1 + 1e-9)
        out[y0:y1 + 1, x0:x1 + 1] |= inside
    return out


AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def wrap_of(around, at):
    """a stamp wrapped round a cylinder: around=(axis "X" | "Y" | "Z", a point on the axis) and the stamp's centre
    `at` (the kit's frame, studs) -> {"axis", "centre", "radius", "out" (outward at `at`), "along" (`at`'s place
    along the axis from centre)}. Refused: an unknown axis, or `at` ON the axis (no radius)"""
    try:
        axis_name, centre = around
    except (TypeError, ValueError):
        raise ValueError('stamp: around=("X" | "Y" | "Z", (x, y, z) a point on the axis)') from None
    key = str(axis_name).upper().lstrip("+")
    if key not in AXES:
        raise ValueError(f'stamp: around axis "{axis_name}" - "X", "Y" or "Z"')
    ax = np.array(AXES[key])
    c = np.array([float(v) for v in centre], np.float64)
    d = np.array([float(v) for v in at], np.float64) - c
    along = float(d @ ax)
    off = d - along * ax
    r = float(np.linalg.norm(off))
    if r < 1e-6:
        raise ValueError("stamp: at= lies on the around= axis - it must be ON the surface, its radius from the axis")
    return {"axis": tuple(ax), "centre": tuple(c), "radius": r, "out": tuple(off / r), "along": along}
