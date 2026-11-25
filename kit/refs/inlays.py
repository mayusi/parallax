"""inlays.py — `kit refs inlays`: a reference view's COLOURED TRIM traced into millimetre polygons — gold inlays, a
script logo, chrome bands, painted stripes — to build FROM (a.cad: extrude them, wrap them onto a curved part with
cad_parts.inlay). Scarborough Fair's gold crescent, arcs, hub trim and its "Scarborough Fair" script came from the
game's own side view this way (owner 9/10, 2026-10-21); a hand-drawn circle stood in for the crescent first and read
nothing like it.

    lune run kit refs inlays <picture> --name <name> --hue 34-72 [--sat 0.28] [--val 0.30] [--box x0,y0,x1,y1]
        [--exclude x0,y0,x1,y1 ...] [--trace <trace.json> --length-mm L | --mm-per-px f] [--split-y px]
        [--close 9] [--bridge 15] [--fill 1500] [--raw] [--min-area 400] [--eps 0.9] [--centrelines] [--out <path>]

--hue: the colour's hue range in degrees (gold 34-72, chrome: use --sat 0 --sat-max 0.12 --val 0.6); by default the
render's mask is CLEANED into the design (clean(): gaps --close px closed, stripes --bridge px tall bridged, holes
under --fill px filled, smoothed by thickness; --raw keeps the render's own mask); build the polygons with
cad_parts.outline (smooth fitted curves), never a raw Polygon; --split-y: a picture row the pieces are cut at
(the parts above and below sit on different surfaces: "upper" / "lower"). Coordinates: with --trace (a kit trace of
the same picture) x mm from the trace frame's left end, y mm up from its bottom (the frame's own mm with
--length-mm); else --mm-per-px from the box's bottom-left. Writes assets/models/<name>.inlays.json and the preview
build/refs/<name>_inlays.png; prints one JSON line (summary / next_action). --centrelines: each thin trim's centre
path + width too ("centrelines": [{"path" mm, "width_mm", "closed"}], orange in the preview): raised trim is built
as cad_parts.bead(path, width, height) — a swept half-round, not a flat extrusion with square shoulders.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def colour_mask(rgb, hue, sat=0.28, val=0.30, sat_max=1.01):
    """(H, W, 3) uint8 RGB -> bool mask of the pixels whose hue (degrees) is in hue=(lo, hi) and saturation / value
    clear the floors (pure numpy: test_inlays.py)"""
    import numpy as np  # noqa: PLC0415

    x = rgb.astype(np.float32) / 255.0
    mx, mn = x.max(axis=2), x.min(axis=2)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.0)
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    h[rm] = (60 * ((g - b)[rm] / d[rm])) % 360
    h[gm] = 60 * ((b - r)[gm] / d[gm]) + 120
    h[bm] = 60 * ((r - g)[bm] / d[bm]) + 240
    lo, hi = hue
    inside = (h >= lo) & (h <= hi) if lo <= hi else (h >= lo) | (h <= hi)
    if sat <= 0 and sat_max < 1:   # (a colourless trim: chrome, silver, white enamel)
        inside = np.ones_like(inside)
    return inside & (s >= sat) & (s < sat_max) & (mx >= val)


def clean(mask, close=9, bridge=0, fill_px=1500, wide_px=17, sigma_wide=8.0, sigma_thin=1.3, speck_px=300):
    """a lit render's colour mask -> the DESIGN's mask (pure: test_inlays.py): gaps up to `close` px closed, stripes
    up to `bridge` px tall bridged (a groove crossing the trim), holes under `fill_px` filled (reflections are not
    design), then smoothed BY THICKNESS — the wide regions (what a wide_px opening keeps) by sigma_wide, the thin lines
    by sigma_thin: one strong blur erases 2 mm trim lines, a light one leaves the wide bands' wobble (Scarborough Fair:
    the owner, "the designs look weird ... not a fully polished model")"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    m = mask.astype(np.uint8)
    if close > 1:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
    if bridge > 1:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((bridge, 1), np.uint8))
    if fill_px > 0:
        n_, lab_, st_, _c = cv2.connectedComponentsWithStats((1 - m).astype(np.uint8), connectivity=4)
        for k in range(1, n_):
            if st_[k, cv2.CC_STAT_AREA] < fill_px:
                m[lab_ == k] = 1
    ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (wide_px, wide_px))
    thick = cv2.morphologyEx(m, cv2.MORPH_OPEN, ell)
    thin = m & (1 - cv2.dilate(thick, np.ones((3, 3), np.uint8)))
    n_, lab_, st_, _c = cv2.connectedComponentsWithStats(thin.astype(np.uint8), connectivity=8)
    for k in range(1, n_):   # (a short thin speck on a band's edge is a highlight, not a trim line)
        if st_[k, cv2.CC_STAT_AREA] < speck_px:
            thin[lab_ == k] = 0
    thick_s = (cv2.GaussianBlur(thick.astype(np.float32), (0, 0), sigma_wide) > 0.5).astype(np.uint8)
    thin_s = (cv2.GaussianBlur(thin.astype(np.float32), (0, 0), sigma_thin) > 0.45).astype(np.uint8)
    return cv2.morphologyEx(thick_s | thin_s, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)


def polygons(mask, close=9, min_area=250.0, eps=1.6, split_y=None):
    """mask -> [{"outline": [[x, y] px], "holes": [...], "area_px", "side": "upper"/"lower"/None}] — closed by `close`
    px, validated (a self-crossing outline repaired), cut at the row split_y (pure: test_inlays.py)"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from shapely.geometry import Polygon as SP  # noqa: PLC0415
    from shapely.geometry import box as SB  # noqa: PLC0415

    m = mask.astype(np.uint8)
    if close > 1:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
    cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    H, W = m.shape
    halves = [(SB(0, 0, W, split_y), "upper"), (SB(0, split_y, W, H), "lower")] if split_y else [(None, None)]
    for i, c in enumerate(cs):
        if hier[0][i][3] != -1 or cv2.contourArea(c) < min_area:
            continue
        o = cv2.approxPolyDP(c, eps, True)[:, 0, :]
        hs = [cv2.approxPolyDP(cs[j], eps, True)[:, 0, :] for j in range(len(cs))
              if hier[0][j][3] == i and cv2.contourArea(cs[j]) > min_area * 0.4]
        if len(o) < 3:
            continue
        poly = SP(o, [h for h in hs if len(h) >= 3]).buffer(0)
        for half, side in halves:
            q = poly if half is None else poly.intersection(half)
            for g in ([q] if q.geom_type == "Polygon" else [x for x in getattr(q, "geoms", []) if x.geom_type == "Polygon"]):
                if g.area < min_area:
                    continue
                out.append({"outline": [[float(x), float(y)] for x, y in list(g.exterior.coords)[:-1]],
                            "holes": [[[float(x), float(y)] for x, y in list(r.coords)[:-1]] for r in g.interiors],
                            "area_px": round(g.area, 1), "side": side})
    return out


def thin(mask):
    """Zhang-Suen thinning (pure numpy): a mask -> its one-pixel skeleton"""
    import numpy as np  # noqa: PLC0415

    m = np.pad(mask.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p = m
            n = [np.roll(np.roll(p, dy, 0), dx, 1) for dy, dx in
                 ((1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1))]
            # P2..P9 clockwise from north: north = the row above (roll +1 brings it down)
            P2, P3, P4, P5, P6, P7, P8, P9 = n
            B = sum(n)
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            c = (P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0) if step == 0 else (P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0)
            kill = (p == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if kill.any():
                m = m & ~kill.astype(np.uint8) if m.dtype == np.bool_ else (m * (1 - kill)).astype(np.uint8)
                changed = True
        if not changed:
            return m[1:-1, 1:-1].astype(bool)


def centrelines(mask, min_len_px=12, smooth=2, max_width=0.34):
    """thin trim (a border, a bead, a script stroke) -> its CENTRELINES: [{"path": [[x, y] px], "width_px": w,
    "closed": bool}] — each skeleton chain between ends / junctions, smoothed, with the trim's width there (twice the
    distance to its edge): the path and width cad_parts.bead() sweeps a round profile along; a chain wider than
    max_width x its length is a panel's medial axis, dropped (pure: test_inlays.py)"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    sk = thin(mask)
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    H, W = sk.shape
    pts = set(zip(*np.nonzero(sk)))
    nb = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    def nbrs(p):
        """8-neighbours, minus a diagonal one also reached through a shared side neighbour (a staircase step: else
        every step reads as a junction and the line falls apart into stubs)"""
        out = []
        for dy, dx in nb:
            q = (p[0] + dy, p[1] + dx)
            if q not in pts:
                continue
            if dy and dx and ((p[0] + dy, p[1]) in pts or (p[0], p[1] + dx) in pts):
                continue
            out.append(q)
        return out
    deg = {p: len(nbrs(p)) for p in pts}
    nodes = {p for p, d in deg.items() if d != 2}
    used = set()
    chains = []

    def walk(a, b):
        chain = [a, b]
        used.add(frozenset((a, b)))
        prev, cur = a, b
        while cur not in nodes:
            nxt = [q for q in nbrs(cur) if q != prev and frozenset((cur, q)) not in used]
            if not nxt:
                break
            used.add(frozenset((cur, nxt[0])))
            prev, cur = cur, nxt[0]
            chain.append(cur)
            if cur == chain[0]:
                break
        return chain
    for a in nodes:
        for b in nbrs(a):
            if frozenset((a, b)) not in used:
                chains.append(walk(a, b))
    for p in pts:  # closed loops (no end, no junction)
        for q in nbrs(p):
            if frozenset((p, q)) not in used and p not in nodes:
                chains.append(walk(p, q))
    out = []
    for ch in chains:
        if len(ch) < min_len_px:
            continue
        closed = ch[0] == ch[-1] and len(ch) > 3
        arr = np.array([(x, y) for y, x in ch], float)
        if smooth and len(arr) > 2 * smooth + 1:
            k = np.ones(2 * smooth + 1) / (2 * smooth + 1)
            mode = "wrap" if closed else "edge"
            pad = np.pad(arr, ((smooth, smooth), (0, 0)), mode=mode)
            arr = np.column_stack([np.convolve(pad[:, 0], k, "valid"), np.convolve(pad[:, 1], k, "valid")])
            arr[0], arr[-1] = (arr[0], arr[-1]) if closed else ((ch[0][1], ch[0][0]), (ch[-1][1], ch[-1][0]))
        simp = cv2.approxPolyDP(arr.astype(np.float32).reshape(-1, 1, 2), 0.6, closed)[:, 0, :]
        w = float(np.median([2 * dist[y, x] - 1 for y, x in ch]))  # (distances run to the edge pixels' centres)
        length = float(np.sum(np.hypot(*np.diff(arr, axis=0).T)))
        if w > max_width * length:  # (a wide PANEL's medial axis, not a thin trim's centre: no bead there)
            continue
        out.append({"path": [[round(float(x), 2), round(float(y), 2)] for x, y in simp], "width_px": round(w, 2),
                    "closed": bool(closed)})
    return out


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def _box(text):
    return tuple(int(float(v)) for v in text.split(","))


def main(argv):
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageDraw  # noqa: PLC0415

    if not argv or argv[0].startswith("--") or "--name" not in argv or "--hue" not in argv:
        return emit("fail", "refs inlays: needs <picture> --name <name> --hue lo-hi",
                    "lune run kit refs inlays refs/private/x/side.png --name x_gold --hue 34-72 --trace "
                    "assets/models/x_side.trace.json --length-mm 280")
    pic, name = argv[0], _arg(argv, "--name")
    if not os.path.isfile(pic):
        return emit("fail", f"refs inlays: {pic} not found", "give the picture's path")
    rgb = np.asarray(Image.open(pic).convert("RGB"))
    H, W = rgb.shape[:2]
    lo, hi = (float(v) for v in _arg(argv, "--hue").split("-"))
    mask = colour_mask(rgb, (lo, hi), float(_arg(argv, "--sat", 0.28)), float(_arg(argv, "--val", 0.30)),
                       float(_arg(argv, "--sat-max", 1.01)))
    keep = np.zeros_like(mask)
    x0, y0, x1, y1 = _box(_arg(argv, "--box", f"0,0,{W},{H}"))
    keep[y0:y1, x0:x1] = True
    for i, a in enumerate(argv):
        if a == "--exclude":
            ex0, ey0, ex1, ey1 = _box(argv[i + 1])
            keep[ey0:ey1, ex0:ex1] = False
    mask &= keep
    unfilled = mask
    if "--raw" not in argv:   # (the design, not the render: reflections filled, grooves bridged, smoothed by thickness)
        mask = clean(mask, int(_arg(argv, "--close", 9)), int(_arg(argv, "--bridge", 15)),
                     int(_arg(argv, "--fill", 1500)))
    split = _arg(argv, "--split-y")
    pieces = polygons(mask, 1, float(_arg(argv, "--min-area", 400)),
                      float(_arg(argv, "--eps", 0.9)), int(split) if split else None)
    if "--trace" in argv:
        with open(_arg(argv, "--trace"), encoding="utf-8") as fh:
            fr = json.load(fh)["frame"]
        if "--length-mm" not in argv:
            return emit("fail", "refs inlays: --trace needs --length-mm (the traced view's length in mm)",
                        "add --length-mm <the object's length>")
        mpp = float(_arg(argv, "--length-mm")) / float(fr["length_px"])
        ox, oy = float(fr["x0"]), float(fr["y1"])
    else:
        mpp = float(_arg(argv, "--mm-per-px", 0) or 0)
        if mpp <= 0:
            return emit("fail", "refs inlays: give --trace <trace.json> --length-mm L, or --mm-per-px f",
                        "the trace of the same picture gives the mm frame")
        ox, oy = float(x0), float(y1)

    def mm(pts):
        return [[round((x - ox) * mpp, 3), round((oy - y) * mpp, 3)] for x, y in pts]

    out = [{"outline": mm(p["outline"]), "holes": [mm(h) for h in p["holes"]], "side": p["side"],
            "area_mm2": round(p["area_px"] * mpp * mpp, 2)} for p in pieces]
    # (centrelines from the mask cleaned WITHOUT its hole filling: a small bezel ring stays a ring, not a disc)
    if "--centrelines" in argv:
        base = unfilled if "--raw" in argv else clean(unfilled, int(_arg(argv, "--close", 9)),
                                                       int(_arg(argv, "--bridge", 15)), 0)
        lines = centrelines(base, int(_arg(argv, "--min-len", 12)))
    else:
        lines = []
    beads = [{"path": mm(c["path"]), "width_mm": round(c["width_px"] * mpp, 3), "closed": c["closed"]} for c in lines]
    dest = _arg(argv, "--out") or os.path.join(REPO, "assets", "models", f"{name}.inlays.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump({"source": pic.replace(os.sep, "/"), "hue": [lo, hi], "mm_per_px": mpp,
                   "frame": "x mm from the frame's left (the trace's x0), y mm up from its bottom", "inlays": out,
                   **({"centrelines": beads} if "--centrelines" in argv else {})}, fh)
    prev = Image.fromarray(rgb).convert("RGB")
    dr = ImageDraw.Draw(prev)
    for c in lines:
        dr.line([tuple(q) for q in c["path"]], fill=(255, 140, 0), width=2)
    for p in pieces:
        dr.line([tuple(q) for q in p["outline"]] + [tuple(p["outline"][0])], fill=(0, 255, 255), width=3)
        for h in p["holes"]:
            dr.line([tuple(q) for q in h] + [tuple(h[0])], fill=(255, 60, 200), width=2)
    pv = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", f"{name}_inlays.png")
    os.makedirs(os.path.dirname(pv), exist_ok=True)
    prev.save(pv)
    rel = lambda p: os.path.relpath(p, REPO).replace(os.sep, "/")  # noqa: E731
    if not out:
        return emit("fail", f"refs inlays {name}: no piece of hue {lo:g}-{hi:g} in the box",
                    "widen --hue / lower --sat --val, or check the box", preview=rel(pv))
    area = sum(p["area_mm2"] for p in out)
    return emit("pass", f"refs inlays {name}: {len(out)} piece(s), {sum(len(p['holes']) for p in out)} hole(s), "
                f"{area:.0f} mm2" + (f", {len(beads)} centreline(s) for cad_parts.bead" if lines else "") +
                f" -> {rel(dest)}",
                f"LOOK at {rel(pv)} (cyan: each piece, pink: its holes); build them: a.cad extrudes "
                "the polygons, cad_parts.inlay(shape, host) wraps them onto a curved part", pieces=len(out),
                preview=rel(pv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
