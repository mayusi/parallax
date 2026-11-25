"""terrain.py — HEIGHTMAPS for kit worlds: fractal noise (or a picture: a DEM, a painted sketch) + erosion.

Usage: python kit/world/terrain.py <out.hm.json> [--size 512] [--step 4] [--seed 3] [--octaves 6] [--scale 180]
          [--relief 60] [--erosion 60000] [--thermal 25] [--from <image>] [--flat x,z,radius ...]
       (normally: lune run kit world terrain <Name> [same flags]  ->  assets/worlds/terrain/<Name>.hm.json)
Writes the grid ({nx, nz, step, relief, heights[nx*nz] in studs 0..relief}) and <out>.png: a shaded relief with the
steep slopes (rock in game) and the erosion channels, to LOOK at before building on it.
  noise     fBm (value noise, `octaves`, `scale` studs per big feature), then ridged a little for mountains
  --from    an image's brightness is the height (white = high): a real DEM tile, or a sketch the owner painted
  thermal   talus slumping: slopes steeper than ~38 degrees shed material downhill (screes, softened cliffs)
  erosion   droplet hydraulic erosion, all droplets at once (numpy): water picks up sediment going fast down hill
            and drops it where it slows — valleys, gullies, alluvial fans: the difference between "noise" and "land"
  --flat    level pads (x,z,radius in studs from the grid's centre) blended in after erosion: arenas, towns
Blueprint: "terrain": [{ "heightmap": { "center": [0, 0, 0], "size": [512, 512], "source":
  "assets/worlds/terrain/<Name>.hm.json", "material": "Grass", "rock": "Rock", "rockSlope": 38 } }]
"""

import json
import math
import os
import sys

import numpy as np


# ------------------------------------------------------------------ height sources
_CURVE = None


def _curve():
    """kit/world/curve.py, loaded by its path under its own name (the lanes' tools share module names)"""
    global _CURVE
    if _CURVE is None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("kit_world_curve", os.path.join(os.path.dirname(os.path.abspath(__file__)), "curve.py"))
        _CURVE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_CURVE)
    return _CURVE


def value_noise(n, cells, rng):
    """Smooth value noise on an n x n grid with `cells` lattice cells across (cubic interpolation)."""
    lat = rng.random((cells + 3, cells + 3))
    t = np.linspace(0, cells, n, endpoint=False)
    i = np.floor(t).astype(int)
    f = t - i
    f = f * f * (3 - 2 * f)
    a = lat[i][:, i]
    b = lat[i + 1][:, i]
    c = lat[i][:, i + 1]
    d = lat[i + 1][:, i + 1]
    fx, fz = f[:, None], f[None, :]
    return (a * (1 - fx) + b * fx) * (1 - fz) + (c * (1 - fx) + d * fx) * fz


def gradient_noise(X, Z, cells, rng):
    """Perlin gradient noise at lattice coordinates X, Z (any shape, 0..cells): no axis-aligned blobs (value noise's
    look), quintic fade -> about -0.7..0.7"""
    ang = rng.random((cells + 3, cells + 3)) * 2 * np.pi
    gx, gz = np.cos(ang), np.sin(ang)
    X = np.clip(X, 0, cells + 0.999)
    Z = np.clip(Z, 0, cells + 0.999)
    ix, iz = np.floor(X).astype(int), np.floor(Z).astype(int)
    fx, fz = X - ix, Z - iz

    def corner(ox, oz):
        return gx[ix + ox, iz + oz] * (fx - ox) + gz[ix + ox, iz + oz] * (fz - oz)

    u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    v = fz * fz * fz * (fz * (fz * 6 - 15) + 10)
    a = corner(0, 0) + (corner(1, 0) - corner(0, 0)) * u
    b = corner(0, 1) + (corner(1, 1) - corner(0, 1)) * u
    return a + (b - a) * v


def fbm(n, size, scale, octaves, seed, warp=0.0):
    """fBm of gradient noise, optionally domain-warped (`warp` studs: the coordinates are bent by two more noise
    fields first — folded, flowing land instead of round bumps)"""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, n, endpoint=False)
    U, V = np.meshgrid(t, t, indexing="ij")
    if warp:
        wr = np.random.default_rng(seed + 7)
        c = max(1, int(size / (scale * 1.5)))
        U = U + gradient_noise(U * c, V * c, c, wr) * warp / size
        V = V + gradient_noise(U * c + 5.2, V * c + 1.3, c + 6, wr) * warp / size
        U, V = np.clip(U, 0, 0.9999), np.clip(V, 0, 0.9999)
    h = np.zeros((n, n))
    amp, total = 1.0, 0.0
    cells = max(1, int(size / scale))
    for _ in range(octaves):
        h += (gradient_noise(U * cells, V * cells, cells, rng) + 0.7) / 1.4 * amp
        total += amp
        amp *= 0.5
        cells *= 2
    h /= total
    ridged = 1 - np.abs(2 * h - 1)  # a touch of ridging: mountain spines instead of blobs
    h = 0.75 * h + 0.25 * ridged
    return (h - h.min()) / max(h.max() - h.min(), 1e-9)


def ridged_mf(n, size, scale, octaves, seed, gain=2.0, offset=1.0):
    """Musgrave's ridged multifractal: each octave is |noise| folded into a crest, weighted by the octave before it,
    so detail grows ON the ridges and the valleys stay smooth — connected, branching ridgelines with saddles (a
    mountain RANGE), not the separate cones a folded fBm gives. -> 0..1"""
    rng = np.random.default_rng(seed)
    cells = max(1, int(size / scale))
    h = np.zeros((n, n))
    weight = np.ones((n, n))
    amp, total = 1.0, 0.0
    for _ in range(octaves):
        t = np.linspace(0, cells, n, endpoint=False)
        U, V = np.meshgrid(t, t, indexing="ij")
        sig = offset - np.abs(gradient_noise(U, V, cells, rng) * 1.4)
        sig = sig * sig * weight
        weight = np.clip(sig * gain, 0, 1)
        h += sig * amp
        total += amp
        amp *= 0.5
        cells *= 2
    h /= total
    return (h - h.min()) / max(h.max() - h.min(), 1e-9)


def from_image(path, n):
    from PIL import Image

    img = Image.open(path).convert("I;16" if path.lower().endswith(".png") else "L").resize((n, n), Image.BILINEAR)
    h = np.asarray(img, dtype=np.float64).T  # image x = world x, image y = world z (top = -Z / north)
    return (h - h.min()) / max(h.max() - h.min(), 1e-9)


# ------------------------------------------------------------------ designed land (--design <file.json>)
def smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def blur(h, px):
    """a separable gaussian of `px` cells (DEM pixel edges otherwise read as terraces in Roblox's 4-stud voxels)"""
    if not px or px <= 0:
        return h
    r = max(1, int(math.ceil(px * 3)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / px) ** 2)
    k /= k.sum()
    p = np.pad(h, ((r, r), (0, 0)), mode="edge")
    h = sum(k[i] * p[i: i + h.shape[0], :] for i in range(2 * r + 1))
    p = np.pad(h, ((0, 0), (r, r)), mode="edge")
    return sum(k[i] * p[:, i: i + h.shape[1]] for i in range(2 * r + 1))


def dem_base(n, size, cfg, design_dir):
    """REAL land (kit world dem: USGS 3DEP) as the design's base, in studs. Slopes stay TRUE: the box's real width
    maps to the map's `size`, so metres per stud horizontally = vertically ("vexag" exaggerates on purpose; "relief"
    instead scales the range to that many studs). -> heights >= 0"""
    import dem as D

    path = cfg["file"]
    for cand in (path, os.path.join(design_dir, path)):
        if os.path.isfile(cand):
            path = cand
            break
    else:
        raise ValueError(f"no DEM {cfg['file']} (fetch it: lune run kit world dem <Name> --bbox ...)")
    h, meta = D.load(path, n)
    h = blur(h - h.min(), cfg.get("blur", 1.0))
    if cfg.get("relief"):
        return h / max(h.max(), 1e-9) * float(cfg["relief"])
    width_m = meta.get("width_m") or cfg.get("width_m")
    if not width_m:
        raise ValueError(f"{path}: no sidecar with width_m (fetch with kit world dem, or give \"relief\")")
    return h / (float(width_m) / size) * float(cfg.get("vexag", 1.0))


# ---------------------------------------------------------------- the ground as an aerial picture shows it
# `kit world dem` brings a box's real heights; `kit world imagery` the same box's real look from above, read as the
# painter's roles (kit/world/imagery.py: green = meadow, dark green = lush, grey = rock, brown = dirt, pale tan =
# sand, white = snow, dark = mud). --imagery <file.img.png> (or the design's "paint": {"imagery": "<file>"}) lays that
# read on the land: on the SOIL and on the rock a slope does not make - cliffs and scree are the land's own shape
# and stay, mud where the water runs stays, a shore stays. It is the real place's cover only on the real place's
# land: the picture's box must be the box of the design's DEM.
IMAGERY_ROLE = {"meadow": 0, "lush": 1, "dirt": 2, "mud": 3, "rock": 4, "snow": 6, "sand": 7}


def _box(meta):
    """a sidecar's box: four numbers (not words, not NaN), or None"""
    b = meta.get("bbox") if isinstance(meta, dict) else None
    if not (isinstance(b, list) and len(b) == 4):
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == v for v in b):
        return None
    return [float(v) for v in b]


def imagery_read(path, n, design, design_dir):
    """the picture's read on the land's own grid, held to the land -> ({"names": [x, z] array, "record": {...}}, None)
    or (None, why)"""
    import imagery as IM

    found = None
    for cand in (path, os.path.join(design_dir, path)):
        if os.path.isfile(cand):
            found = cand
            break
    if found is None:
        return None, f"no picture {path} (fetch it: lune run kit world imagery <Name> --bbox ...)"
    if not os.path.isfile(IM.sidecar(found)):
        return None, f"{found} has no sidecar (the box it shows): fetch it with kit world imagery"
    cfg = (design or {}).get("dem")
    if not cfg:
        return None, ("an aerial picture is the cover of a REAL place: the land must be that place's "
                      "(a design with a \"dem\" of the same box)")
    import dem as D

    dem_path = cfg["file"] if os.path.isfile(cfg["file"]) else os.path.join(design_dir, cfg["file"])
    try:
        dem_meta = {}
        if os.path.isfile(D.sidecar(dem_path)):
            with open(D.sidecar(dem_path), encoding="utf-8") as fh:
                dem_meta = json.load(fh)
        names, meta = IM.load(found, n)
    except Exception as e:  # noqa: BLE001 - a damaged picture or sidecar is said in one line
        return None, f"{found} or its sidecar (or the dem's) cannot be read: {e}"
    a, b = _box(meta), _box(dem_meta)
    if a is None or b is None or not all(abs(a[k] - b[k]) <= 1e-6 for k in range(4)):
        return None, (f"the picture shows the box {meta.get('bbox') if isinstance(meta, dict) else None} and the land is "
                      f"the box {dem_meta.get('bbox') if isinstance(dem_meta, dict) else None}: an aerial picture colours "
                      "the land it was taken of (four numbers each, the same)")
    if not isinstance(meta.get("covers"), dict):
        return None, (f"{found} was fetched before the picture was asked for the ground the heights cover: it does not "
                      "lie on the land. Fetch it again: lune run kit world imagery <Name> --bbox ...")
    credit = meta.get("credit")
    if not isinstance(credit, str) or not credit.strip():
        return None, f"{found}'s sidecar names no credit: fetch it with kit world imagery"
    return {"names": names, "record": {"file": os.path.basename(found), "credit": credit, "bbox": a}}, None


def designed(n, size, design, seed, design_dir="."):
    """Heights in STUDS from macro shapes over a little noise — geography decided by the designer, erosion adds the
    detail. Coordinates are studs from the grid's centre (x right, z down, as kit world).
    { "noise": { "relief": 14, "scale": 160, "octaves": 5 },
      "shapes": [ { "type": "rim", "height": 120, "width": 140 },              mountains framing the map
                  { "type": "plateau", "center": [x, z], "radius": 110, "height": 55, "edge": 35 },
                  { "type": "basin", "center": [x, z], "radius": 150, "depth": 22, "edge": 60 },
                  { "type": "hill", "center": [x, z], "radius": 90, "height": 45 },   (a soft dome)
                  { "type": "ridge", "from": [x, z], "to": [x, z], "width": 40, "height": 30 },
                  { "type": "ring", "inner": 660, "outer": 1010, "height": 250, "ridgeScale": 420 },  far ranges
                  (ring: ridged multifractal ridgelines by default, "ridges": false = the old folded peaks;
                   rim: "ridges": true opts in)
                  { "type": "ramp", "from": [x, z], "to": [x, z], "width": 24, "h0": 20, "h1": 70 } ] }
    a ramp OVERRIDES what is under it (a walkable grade up a plateau's cliff); the others add up."""
    nz_cfg = design.get("noise", {})
    if design.get("dem"):  # real land as the base; the shapes below still add (plateau, basin, ramp, keeps)
        h = dem_base(n, size, design["dem"], design_dir)
        if nz_cfg:
            h = h + fbm(n, size, nz_cfg.get("scale", 160), int(nz_cfg.get("octaves", 5)), seed,
                        warp=nz_cfg.get("warp", 0)) * nz_cfg.get("relief", 0)
    else:
        h = fbm(n, size, nz_cfg.get("scale", 160), int(nz_cfg.get("octaves", 5)), seed,
                warp=nz_cfg.get("warp", 0)) * nz_cfg.get("relief", 14)
    xs = np.linspace(-size / 2, size / 2, n)
    X0, Z0 = np.meshgrid(xs, xs, indexing="ij")
    # domain warp: every shape's outline is bent by noise (perfect circles and a square frame read as artificial)
    warp = design.get("warp", 70)
    X = X0 + (fbm(n, size, 260, 4, seed + 101) - 0.5) * 2 * warp
    Z = Z0 + (fbm(n, size, 260, 4, seed + 202) - 0.5) * 2 * warp
    peaks = fbm(n, size, 110, 5, seed + 303)  # where the rim rises into peaks and where it saddles
    # what erosion may not change: a basin's bowl (its lake), a plateau's top (the castle on it), a ramp's grade —
    # re-imposed after erosion ("keep": false on a shape lets the water have it)
    keep = np.zeros((n, n))
    mtn = np.zeros((n, n))  # where the mountain shapes (rim, ring) stand: strata go there only
    ramps = []
    for s in design.get("shapes", []):
        t = s.get("type")
        if t == "rim":
            d = np.minimum.reduce([X0 + size / 2, size / 2 - X0, Z0 + size / 2, size / 2 - Z0])
            d = d + (fbm(n, size, 180, 4, seed + 404) - 0.5) * s.get("width", 120) * 0.9  # a ragged inner edge
            if s.get("ridges"):  # opt-in: ridgelines and saddles (ridged multifractal)
                ridged = ridged_mf(n, size, s.get("ridgeScale", 260), int(s.get("ridgeOctaves", 4)), seed + 606) ** 0.9
            else:
                ridged = 1 - np.abs(2 * peaks - 1)
            fr = smoothstep(1 - d / s.get("width", 120))
            h += s.get("height", 100) * fr ** 1.3 * (0.45 + 0.9 * ridged)
            mtn = np.maximum(mtn, smoothstep(fr * 3))
        elif t == "river":
            # a channel carved along "points" (unwarped, so the water boxes you lay along it fit): flat bed "width"
            # wide, banks rising over "edge", "depth" deep
            pts = s.get("points", [])
            # "curve": the smooth line through the points (kit/world/curve.py), read as the compiler reads a path's:
            # true, or { "step", "maxTurn", "least", "closed" }; false / absent = the typed corners; anything else
            # is an error, and so is a point that is not [x, z]
            cv = s.get("curve")
            if cv is not None and cv is not False:
                if cv is not True and not isinstance(cv, dict):
                    raise ValueError('a river\'s "curve" is true, false or { "step", "maxTurn", "least", "closed" }')
                if any(not isinstance(q, (list, tuple)) or len(q) != 2 for q in pts):
                    raise ValueError("a river's points are [x, z]")
                o = cv if isinstance(cv, dict) else {}
                pts = _curve().through([[float(q[0]), float(q[1])] for q in pts], step=o.get("step"),
                                       max_turn=o.get("maxTurn"), least=o.get("least"), closed=o.get("closed") is True)
            dmin = np.full_like(X0, 1e9, dtype=float)
            for k in range(len(pts) - 1):
                (x1, z1), (x2, z2) = pts[k], pts[k + 1]
                vx, vz = x2 - x1, z2 - z1
                t2 = np.clip(((X0 - x1) * vx + (Z0 - z1) * vz) / max(vx * vx + vz * vz, 1e-9), 0, 1)
                dmin = np.minimum(dmin, np.hypot(X0 - x1 - vx * t2, Z0 - z1 - vz * t2))
            h -= s.get("depth", 12) * (1 - smoothstep((dmin - s.get("width", 20) / 2) / max(s.get("edge", 14), 1)))
        elif t == "dunes":
            # wind-built sand: parallel crescents across "direction", each a long gentle windward slope and a short
            # steep lee face (the crest is sharp), wavelength + height varying by noise; optional "center"/"radius"
            # keeps them to an area (they fade out over "edge")
            dx, dz = s.get("direction", [1, 0.3])
            dl = max(np.hypot(dx, dz), 1e-6)
            dx, dz = dx / dl, dz / dl
            wl = s.get("wavelength", 90)
            along = (X * dx + Z * dz) / wl + (fbm(n, size, 160, 4, seed + 606) - 0.5) * s.get("bend", 1.6)
            f = along - np.floor(along)
            lee = s.get("lee", 0.18)  # share of the wave that is the steep face
            profile = np.where(f < 1 - lee, f / (1 - lee), (1 - f) / lee)
            profile = profile ** 1.4
            amp = s.get("height", 20) * (0.55 + 0.9 * fbm(n, size, 220, 3, seed + 707))
            mask = 1.0
            if "center" in s:
                c = s["center"]
                dist = np.hypot(X - c[0], Z - c[1])
                mask = 1 - smoothstep((dist - s.get("radius", 400)) / max(s.get("edge", 120), 1))
            h += amp * profile * mask
        elif t == "ring":
            # far mountains AROUND a map (a second, coarse heightmap op): a square ring that starts rising at
            # "inner" (just outside the playable map) and peaks by "outer"; "inside" lowers everything within.
            # The designed map is shifted so its lowest point is 0, so the middle ends up near 0: SINK the op
            # itself ("center": [0, -110, 0] in the blueprint) so the middle stays under the real map (its lakes).
            # d = distance from the centre, square (the map is square)
            c = s.get("center", [0, 0])
            d = np.maximum(np.abs(X - c[0]), np.abs(Z - c[1]))
            d = d + (fbm(n, size, 200, 4, seed + 505) - 0.5) * s.get("ragged", 160)
            inner, outer = s.get("inner", 560), s.get("outer", 900)
            f = smoothstep((d - inner) / max(outer - inner, 1))
            if s.get("ridges", True):  # a range: ridgelines and saddles (ridged multifractal)
                rm = ridged_mf(n, size, s.get("ridgeScale", 420), int(s.get("ridgeOctaves", 4)), seed + 606)
                h += s.get("height", 400) * f ** 1.1 * (0.2 + 1.0 * rm ** 0.9)
            else:
                ridged = 1 - np.abs(2 * peaks - 1)
                h += s.get("height", 400) * f ** 1.2 * (0.35 + 0.95 * ridged)
            h += s.get("inside", 0) * (1 - smoothstep((d - inner + 60) / 60))
            mtn = np.maximum(mtn, smoothstep(f * 3))
        elif t in ("plateau", "basin"):
            cx, cz = s["center"]
            d = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2)
            edge = s.get("edge", 40)
            f = smoothstep((s["radius"] - d) / edge + 0.5)
            h += f * (s.get("height", 0) if t == "plateau" else -s.get("depth", 20))
            if s.get("keep", True):
                # (a plateau keeps its edge too: rivers cutting along a cliff top cut the castle off its ramp)
                keep = np.maximum(keep, f if t == "basin" else smoothstep((s["radius"] + edge * 0.8 - d) / edge))
        elif t == "hill":
            cx, cz = s["center"]
            d2 = ((X - cx) ** 2 + (Z - cz) ** 2) / max(s["radius"], 1) ** 2
            h += s.get("height", 30) * np.exp(-2.5 * d2)
            if s.get("keep", True):  # (its core: what stands on a hill is placed at its designed height)
                keep = np.maximum(keep, smoothstep(1 - d2 * 1.6))
        elif t == "ridge":
            (ax, az), (bx, bz) = s["from"], s["to"]
            vx, vz = bx - ax, bz - az
            L2 = max(vx * vx + vz * vz, 1e-9)
            tt = np.clip(((X - ax) * vx + (Z - az) * vz) / L2, 0, 1)
            d = np.sqrt((X - (ax + tt * vx)) ** 2 + (Z - (az + tt * vz)) ** 2)
            h += s.get("height", 30) * smoothstep(1 - d / s.get("width", 40))
        elif t == "ramp":
            ramps.append(s)
        else:
            raise ValueError(f"unknown shape {t!r} (rim | ring | dunes | river | plateau | basin | hill | ridge | ramp)")
    for s in ramps:  # after the rest: a grade that overrides the cliff it climbs
        (ax, az), (bx, bz) = s["from"], s["to"]
        vx, vz = bx - ax, bz - az
        L2 = max(vx * vx + vz * vz, 1e-9)
        tt = np.clip(((X0 - ax) * vx + (Z0 - az) * vz) / L2, 0, 1)
        d = np.sqrt((X0 - (ax + tt * vx)) ** 2 + (Z0 - (az + tt * vz)) ** 2)
        target = s.get("h0", 0) + (s.get("h1", 0) - s.get("h0", 0)) * tt
        w = smoothstep(1 - (d - s.get("width", 20) / 2) / max(s.get("edge", 12), 1))
        h = h * (1 - w) + target * w  # (h0 / h1 in the same frame as the shapes: before the final shift)
        if s.get("keep", True):  # (with its shoulders: a gully beside a ramp is a trap)
            keep = np.maximum(keep, smoothstep(1 - (d - s.get("width", 20) / 2 - 10) / max(s.get("edge", 12) + 10, 1)))
    return h - h.min(), keep, mtn


def terraces(h, mtn, tr, size, seed):
    """rock strata on the mountains: flat ledges and steep risers, bent by noise so no ledge is level. Applied
    AFTER erosion (thermal collapses any riser steeper than its talus: strata made first were melted away)."""
    n = h.shape[0]
    T = float(tr.get("step", 16))
    sharp = float(tr.get("sharp", 0.35))
    amount = float(tr.get("amount", 0.85))
    bend = (fbm(n, size, 140, 3, seed + 909) - 0.5) * T * 1.6
    x = (h + bend) / T
    f = x - np.floor(x)
    riser = smoothstep(np.clip((f - (1 - sharp)) / sharp, 0, 1))
    terr = (np.floor(x) + riser) * T - bend
    w = mtn * amount * smoothstep(np.clip(h / (T * 2), 0, 1))  # (not on the valley floors)
    return h * (1 - w) + terr * w


# ------------------------------------------------------------------ erosion
def thermal(h, cell, iters, talus_deg=38):
    talus = math.tan(math.radians(talus_deg)) * cell
    n0, n1 = h.shape
    for _ in range(iters):
        moved = np.zeros_like(h)
        # edge-padded neighbours (np.roll wrapped the map around: a dark seam along every border)
        p = np.pad(h, 1, mode="edge")
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = p[1 + dx : 1 + dx + n0, 1 + dz : 1 + dz + n1]
            excess = np.where(h - nb > talus, (h - nb - talus) * 0.25, 0.0)
            moved -= excess
            # the receiving cell gets it (dropped where the receiver would be off the map)
            recv = np.zeros_like(h)
            src = excess[max(0, -dx) : n0 - max(0, dx), max(0, -dz) : n1 - max(0, dz)]
            recv[max(0, dx) : n0 - max(0, -dx), max(0, dz) : n1 - max(0, -dz)] = src
            moved += recv
        h = h + moved
    return h


def _brush(radius):
    """the cells a droplet erodes around itself (weights fall off with distance, sum 1): wide brushes cut GULLIES,
    a one-cell brush digs pits"""
    offs, ws = [], []
    r = int(math.ceil(radius))
    for ox in range(-r, r + 1):
        for oz in range(-r, r + 1):
            d = math.hypot(ox, oz)
            if d <= radius:
                offs.append((ox, oz))
                ws.append(max(0.0, radius - d) + 0.25)
    ws = np.array(ws) / sum(ws)
    return offs, ws


def hydraulic(h, cell, droplets, seed, batch=1024, steps=64, radius=2.0):
    """Droplet erosion (Beyer 2015, vectorised): a batch of droplets at a time, each running down the gradient with
    inertia, eroding with a radius brush while it has capacity, depositing where it slows. -> (h, flow, deposit):
    flow = water that passed each cell (rivers, gullies), deposit = sediment laid down (fans, scree, valley floors)
    — the material painter reads both."""
    rng = np.random.default_rng(seed + 99)
    n = h.shape[0]
    inertia, capacity_k, min_cap, erode_k, deposit_k, evap, gravity = 0.05, 4.0, 0.01, 0.3, 0.3, 0.015, 4.0
    offs, bw = _brush(radius)
    flow = np.zeros_like(h)
    deposit = np.zeros_like(h)
    done = 0
    while done < droplets:
        m = min(batch, droplets - done)
        done += m
        px = rng.uniform(0, n - 1.001, m)
        pz = rng.uniform(0, n - 1.001, m)
        dx = np.zeros(m)
        dz = np.zeros(m)
        speed = np.ones(m)
        water = np.ones(m)
        sed = np.zeros(m)
        alive = np.ones(m, bool)
        for _ in range(steps):
            ix = np.clip(px.astype(int), 0, n - 2)
            iz = np.clip(pz.astype(int), 0, n - 2)
            fx, fz = px - ix, pz - iz
            h00, h10, h01, h11 = h[ix, iz], h[ix + 1, iz], h[ix, iz + 1], h[ix + 1, iz + 1]
            gx = (h10 - h00) * (1 - fz) + (h11 - h01) * fz
            gz = (h01 - h00) * (1 - fx) + (h11 - h10) * fx
            hh = h00 * (1 - fx) * (1 - fz) + h10 * fx * (1 - fz) + h01 * (1 - fx) * fz + h11 * fx * fz
            dx = dx * inertia - gx * (1 - inertia)
            dz = dz * inertia - gz * (1 - inertia)
            ln = np.sqrt(dx * dx + dz * dz)
            alive &= ln > 1e-9
            dx = np.where(alive, dx / np.maximum(ln, 1e-9), 0)
            dz = np.where(alive, dz / np.maximum(ln, 1e-9), 0)
            nx_, nz_ = px + dx, pz + dz
            alive &= (nx_ >= 0) & (nx_ < n - 1) & (nz_ >= 0) & (nz_ < n - 1)
            jx = np.clip(nx_.astype(int), 0, n - 2)
            jz = np.clip(nz_.astype(int), 0, n - 2)
            gx2, gz2 = nx_ - jx, nz_ - jz
            nh = (h[jx, jz] * (1 - gx2) * (1 - gz2) + h[jx + 1, jz] * gx2 * (1 - gz2)
                  + h[jx, jz + 1] * (1 - gx2) * gz2 + h[jx + 1, jz + 1] * gx2 * gz2)
            dh = nh - hh
            cap = np.maximum(-dh * speed * water * capacity_k, min_cap)
            # uphill or over capacity: deposit (bilinear, where it is); else erode with the brush (never deeper than
            # the drop; capped per step: droplets of one batch read the same old ground)
            dep = np.where(dh > 0, np.minimum(dh, sed), np.where(sed > cap, (sed - cap) * deposit_k, 0.0))
            ero = np.where((dh <= 0) & (sed <= cap), np.minimum((cap - sed) * erode_k, -dh), 0.0)
            dep = np.minimum(dep * alive, 0.08)
            ero = np.minimum(ero * alive, 0.08)
            for ox, oz, w in ((0, 0, (1 - fx) * (1 - fz)), (1, 0, fx * (1 - fz)), (0, 1, (1 - fx) * fz), (1, 1, fx * fz)):
                np.add.at(h, (ix + ox, iz + oz), dep * w)
                np.add.at(deposit, (ix + ox, iz + oz), dep * w)
            if ero.any():
                for (ox, oz), w in zip(offs, bw):
                    np.add.at(h, (np.clip(ix + ox, 0, n - 1), np.clip(iz + oz, 0, n - 1)), -ero * w)
            np.add.at(flow, (ix, iz), water * alive)
            sed = sed + ero - dep
            speed = np.sqrt(np.maximum(speed * speed + (-dh) * gravity, 0.0))
            water *= 1 - evap
            px, pz = np.where(alive, nx_, px), np.where(alive, nz_, pz)
            if not alive.any():
                break
        if not np.isfinite(h).all():
            raise ValueError("erosion diverged (non-finite heights) — lower --erosion")
    return h, flow, deposit


def stream_power(h, cell, iters, k=0.012, m=0.5, keep=None, base=None):
    """River incision (the stream power law, Braun & Willett 2013's implicit solver, n = 1): water drains to the
    steepest of 8 neighbours, each cell's drainage AREA is summed downstream, and every step a cell is cut toward
    its receiver by K * A^m * slope. Big rivers carve valleys that branch up into the mass, ridges (tiny areas)
    stay sharp — a mountain RANGE with concave valley profiles instead of noise cones. `base` (a bool grid): cells
    that are base level INSIDE the map as the edge is (a lake, the sea in a bay, a basin's floor - --sink): water
    that reaches one leaves there, so the land round it is carved toward it, not only toward the rim. -> (h, area)"""
    n0, n1 = h.shape
    N = n0 * n1
    sq2 = math.sqrt(2.0)
    offs = [(-1, -1, sq2), (-1, 0, 1.0), (-1, 1, sq2), (0, -1, 1.0), (0, 1, 1.0), (1, -1, sq2), (1, 0, 1.0), (1, 1, sq2)]
    idx = np.arange(N).reshape(n0, n1)
    area = np.ones(N)
    hold = keep.ravel() if keep is not None else None
    rng = np.random.default_rng(int(iters) * 7919 + n0)
    for _ in range(int(iters)):
        # the routing sees the ground plus a little fresh noise each step: on a plane, steepest-descent water runs
        # dead straight along the 8 directions (stripes); jittered, the channels meander like real ones
        hr = h + rng.normal(0.0, 0.18 * cell, h.shape)
        p = np.pad(hr, 1, mode="edge")
        best = np.zeros((n0, n1))
        rec = idx.copy()
        dist = np.ones((n0, n1))
        for dx, dz, L in offs:
            nb = p[1 + dx: 1 + dx + n0, 1 + dz: 1 + dz + n1]
            drop = (hr - nb) / L
            better = drop > best
            best = np.where(better, drop, best)
            ni = np.clip(np.arange(n0)[:, None] + dx, 0, n0 - 1) * n1 + np.clip(np.arange(n1)[None, :] + dz, 0, n1 - 1)
            rec = np.where(better, ni, rec)
            dist = np.where(better, L, dist)
        rec[0, :] = idx[0, :]  # the map's edge is base level (water leaves)
        rec[-1, :] = idx[-1, :]
        rec[:, 0] = idx[:, 0]
        rec[:, -1] = idx[:, -1]
        if base is not None:  # (sinks inside the land: their water leaves there too)
            rec = np.where(base, idx, rec)
        hf = h.ravel().tolist()
        rl = rec.ravel().tolist()
        order = np.argsort(hr.ravel(), kind="stable").tolist()
        a = [1.0] * N
        for i in reversed(order):  # high to low: each cell passes its area to its receiver
            r = rl[i]
            if r != i:
                a[r] += a[i]
        F = (k * np.sqrt(np.array(a)) / dist.ravel()).tolist()
        hl = hold.tolist() if hold is not None else None
        for i in order:  # low to high: a receiver is solved before its donors (implicit, unconditionally stable)
            r = rl[i]
            if r != i:
                f = F[i] * (1.0 - hl[i]) if hl is not None else F[i]
                nh = (hf[i] + f * hf[r]) / (1.0 + f)
                if nh < hf[i]:
                    hf[i] = nh
        h = np.array(hf).reshape(n0, n1)
        area = np.array(a)
    return h, area.reshape(n0, n1)


def _resample(a, m):
    """bilinear resample of a square grid to m x m"""
    n = a.shape[0]
    src = np.linspace(0, n - 1, m)
    tmp = np.array([np.interp(src, np.arange(n), a[:, j]) for j in range(n)]).T  # rows resampled: (m, n)
    return np.array([np.interp(src, np.arange(n), tmp[i, :]) for i in range(m)])


def stream_multiscale(h, cell, iters, k, keep=None, factor=4, base=None):
    """Rivers at two scales: the MAJOR valleys carved on a grid `factor` x coarser (they end up hundreds of studs
    apart — what shapes a range's silhouette from far away), their cut laid onto the full grid, then the gullies
    at full resolution."""
    n = h.shape[0]
    m = max(17, (n - 1) // factor + 1)
    hc = _resample(h, m)
    kc = _resample(keep, m) if keep is not None else None
    bc = (_resample(base.astype(float), m) > 0.5) if base is not None else None
    if bc is not None and not bc.any():  # (a sink smaller than a coarse cell is the fine pass's alone: a whole coarse
        bc = None  # cell laid at base level for it cut the slope above it LESS than no sink did - measured 11-18)
    if bc is not None:  # (the coarse grid's sink is as low as the fine one's: its averaging must not fill the pit)
        hc = sink_apply(hc, bc)
    cut, _ = stream_power(hc, cell * (n - 1) / (m - 1), iters, k * 1.6, keep=kc, base=bc)
    h = h + _resample(cut - hc, n)
    return stream_power(h, cell, max(1, iters // 2), k, keep=keep, base=base)


def sink_config(text):
    """'x,z,radius' (studs from the map's middle) -> ((x, z, r), None) | (None, why)"""
    try:
        x, z, r = (float(t) for t in str(text).split(","))
    except ValueError:
        return None, f"--sink {text!r}: give x,z,radius (studs from the map's middle)"
    if not (math.isfinite(x) and math.isfinite(z) and math.isfinite(r)) or r <= 0:
        return None, f"--sink {text!r}: its radius must be a number over 0"
    return (x, z, r), None


def sink_mask(sinks, n, cell):
    """the base-level cells of the sinks on an n x n grid of `cell` studs (x along axis 0, z along axis 1)"""
    if not sinks:
        return None
    half = (n - 1) * cell / 2
    xs = np.arange(n)[:, None] * cell - half
    zs = np.arange(n)[None, :] * cell - half
    m = np.zeros((n, n), bool)
    for x, z, r in sinks:
        m |= (xs - x) ** 2 + (zs - z) ** 2 <= r * r
    return m if m.any() else None


def sink_apply(h, base):
    """a sink is LOW: its cells lie at the land's lowest height (the rim's base level) - a lake's or a bay's floor that
    the rivers of the land round it run down to (a base-level cell on a slope would only stop the water already
    passing through it)"""
    if base is None:
        return h
    return np.where(base, np.minimum(h, float(h.min())), h)


# ------------------------------------------------------------------ stamps (land forms placed by name)
# The owner's method list: "Terrain stamping", "Terrain sculpting", "Heightmap terrain editing". A land was noise
# and erosion, or a design file; a single feature - a crater here, a mesa there - had no word. A STAMP is a land
# form from a small library, placed by name:
#   --stamp kind,x,z,radius,height[,turn][,worked]       (as often as wanted; x, z in studs from the map's middle)
#   crater  a bowl `height` deep with a raised rim        mesa    a flat top `height` up with steep sides
#   cone    a mountain with a small crater in its top     ridge   a long ridge along `turn` degrees (0 = along z)
#   valley  a long trough along `turn`                    mound   a smooth hill          pit   a smooth hollow
# A stamp is laid on the FINISHED land (after the rivers and the erosion): crisp, and LOCAL - outside its radius
# not one height of the land changes, so what stands on the land stays where it stood. That is how a land is
# edited. "worked" lays it BEFORE the rivers and the erosion instead, so they work on it (a mesa gets its talus, a
# valley its river) - and then the WHOLE land comes out another land: the erosion's droplets are chaotic, a 6-stud
# bump moves heights everywhere (a fresh reader measured 99 % of the map). Use it when the land is first made.
# A stamp never digs under the land's floor (height 0) and a mesa never lowers what is higher than its top: both
# are refused or left, not done without a word. Stamps are part of the land's recipe (recorded with it): kit world
# check re-makes the land from that recipe to prove its route, stamps and all.
STAMPS = ("crater", "mesa", "cone", "ridge", "valley", "mound", "pit")


def stamp_config(text):
    """ "crater,120,-40,60,25" -> ({kind, x, z, radius, height, turn, worked}, problem or None)"""
    bits = [b.strip() for b in str(text).split(",")]
    worked = False
    if bits and bits[-1] == "worked":
        worked, bits = True, bits[:-1]
    if len(bits) not in (5, 6):
        return None, f"stamp \"{text}\" is kind,x,z,radius,height[,turn][,worked]"
    if bits[0] not in STAMPS:
        return None, f"stamp \"{bits[0]}\": the stamps are {', '.join(STAMPS)}"
    try:
        nums = [float(b) for b in bits[1:]]
    except ValueError:
        return None, f"stamp \"{text}\": x, z, radius, height and turn are numbers"
    if any(v != v or abs(v) == float("inf") for v in nums):
        return None, f"stamp \"{text}\": x, z, radius, height and turn are numbers"
    x, z, radius, height = nums[:4]
    turn = nums[4] if len(nums) == 5 else 0.0
    if radius < 8 or radius > 4096:
        return None, f"stamp \"{text}\": its radius is 8 to 4096 studs (got {radius:g})"
    if height <= 0 or height > 2000:
        return None, f"stamp \"{text}\": its height (or depth) is over 0, up to 2000 studs (got {height:g})"
    return {"kind": bits[0], "x": x, "z": z, "radius": radius, "height": height, "turn": turn, "worked": worked}, None


def stamp_text(s):
    """the stamp as its recipe records it (and as --stamp reads it back)"""
    out = f"{s['kind']},{s['x']!r},{s['z']!r},{s['radius']!r},{s['height']!r},{s['turn']!r}"
    return out + (",worked" if s["worked"] else "")


def _ease(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def stamp(h, cell, s):
    """one land form laid on the heights (studs) -> new heights; nothing changes outside its radius"""
    n = h.shape[0]
    c = (n - 1) / 2
    xs = (np.arange(n) - c) * cell
    X, Z = np.meshgrid(xs, xs, indexing="ij")
    dx, dz = X - s["x"], Z - s["z"]
    R, H = s["radius"], s["height"]
    d = np.sqrt(dx * dx + dz * dz) / R  # 0 at its middle, 1 at its edge
    kind = s["kind"]
    if kind in ("ridge", "valley"):
        # a long form: along `turn` (0 = along z, 90 = along x) it runs its radius each way, across it a third of that
        a = np.radians(s["turn"])
        # (0.94 of the radius each way: with its third of a radius across, its corners stay inside the radius)
        along = (dx * np.sin(a) + dz * np.cos(a)) / (0.94 * R)
        across = (dx * np.cos(a) - dz * np.sin(a)) / (R / 3.0)
        shape = (1 - _ease(np.abs(across))) * (1 - _ease((np.abs(along) - 0.6) / 0.4))
        shape = np.where((np.abs(along) <= 1) & (np.abs(across) <= 1), shape, 0.0)
        return h + (H if kind == "ridge" else -H) * shape
    if kind == "mound":
        return h + H * (1 - _ease(d))
    if kind == "pit":
        return h - H * (1 - _ease(d))
    if kind == "crater":
        # a bowl to 0.7 of the radius, a rim a quarter of its depth high at 0.8, back to the land at the edge
        bowl = -H * (1 - _ease(d / 0.7))
        rim = 0.25 * H * (1 - _ease(np.abs(d - 0.8) / 0.2))
        return h + np.where(d <= 1, bowl + rim, 0.0)
    if kind == "cone":
        # straight flanks up to a rim at a fifth of the radius (the cone's full height), and inside the rim a crater
        # a quarter of the height deep
        flank = H * np.clip((1 - d) / 0.8, 0, 1)
        inner = H - 0.25 * H * (1 - _ease(d / 0.2))
        return h + np.where(d <= 1, np.where(d < 0.2, inner, flank), 0.0)
    # mesa: the land inside is lifted to ONE level (its own middle height + height), flat to 0.7 of the radius.
    # It never LOWERS the land: on a hillside the ground that stands higher than its top stays (a fresh reader: it
    # cut a notch 37 studs deep into the uphill side)
    inside = d <= 1
    if (d <= 0.7).any():
        under = float(np.median(h[d <= 0.7]))
    else:  # (a mesa smaller than the land's cells: the cell nearest ITS middle, not the map's)
        i = int(np.clip(round(s["x"] / cell + c), 0, n - 1))
        j = int(np.clip(round(s["z"] / cell + c), 0, n - 1))
        under = float(h[i, j])
    level = under + H
    t = _ease((d - 0.7) / 0.3)  # 0 on the top, 1 at the edge
    return np.where(inside, np.maximum(h, level * (1 - t) + h * t), h)


def smooth_pads(h, cell, pads):
    n = h.shape[0]
    c = (n - 1) / 2
    xs = (np.arange(n) - c) * cell
    X, Z = np.meshgrid(xs, xs, indexing="ij")
    for x, z, r in pads:
        d = np.sqrt((X - x) ** 2 + (Z - z) ** 2)
        inside = d <= r
        level = float(np.median(h[inside])) if inside.any() else float(h[int(c), int(c)])
        t = np.clip((d - r) / (r * 0.6 + 8), 0, 1)
        t = t * t * (3 - 2 * t)
        h = level * (1 - t) + h * t
    return h


# ------------------------------------------------------------------ the material painter
# Roles, not materials: the blueprint's heightmap op maps them ("paint": {"meadow": "Grass", ...}), so a desert or a
# snowfield reuses the same analysis. Stored in the .hm.json as one character per cell ("0".."8").
ROLES = ["meadow", "lush", "dirt", "mud", "rock", "cliff", "snow", "sand", "scree"]
# The painted roles go into the heightmap as ONE CHARACTER A CELL: role i is chr(48 + i) ("0" .. "9", then ":", ";",
# "<" ... "~"), so a land may hold PAINT_MAX roles (one decimal digit a cell held ten: the river made the tenth and
# no painter could add another - LIMITATIONS_FIXES_V3.md stage E.1). Readers: kit/world/rivers.py,
# kit/lib/environment.luau, kit/lib/world.luau World.roleAt, src/kit/Environment.luau, kit/lib/lanelocks.luau, web.py.
PAINT_BASE = 48
PAINT_MAX = 127 - PAINT_BASE  # (printable ASCII "0" .. "~": 79 roles)


def paint_encode(roles):
    """an int array of role indices -> the paint string (one character a cell, in ravel order)"""
    a = np.asarray(roles).ravel()
    if a.size and (int(a.min()) < 0 or int(a.max()) >= PAINT_MAX):
        raise ValueError(f"a painted role out of 0..{PAINT_MAX - 1}: {int(a.min())}..{int(a.max())}")
    return (a.astype(np.int64) + PAINT_BASE).astype(np.uint8).tobytes().decode("ascii")


def paint_decode(paint, shape=None):
    """the paint string -> an int array of role indices (shape (nx, nz) when given)"""
    a = np.frombuffer(paint.encode("ascii"), np.uint8).astype(np.int64) - PAINT_BASE
    if a.size and (int(a.min()) < 0 or int(a.max()) >= PAINT_MAX):
        raise ValueError("a paint character out of \"0\" .. \"~\"")
    return a.reshape(shape) if shape is not None else a
ROLE_COLORS = {"meadow": (106, 127, 63), "lush": (78, 112, 52), "dirt": (122, 98, 70), "mud": (84, 70, 52),
               "rock": (128, 124, 118), "cliff": (88, 88, 92), "snow": (236, 240, 244), "sand": (200, 182, 140),
               "scree": (150, 140, 124)}


def _smooth(a, k=1):
    p = np.pad(a, k, mode="edge")
    out = np.zeros_like(a)
    n0, n1 = a.shape
    for dx in range(-k, k + 1):
        for dz in range(-k, k + 1):
            out += p[k + dx: k + dx + n0, k + dz: k + dz + n1]
    return out / (2 * k + 1) ** 2


def _dilate(m, k=1):
    p = np.pad(m, k, mode="constant")
    out = np.zeros_like(m)
    n0, n1 = m.shape
    for dx in range(-k, k + 1):
        for dz in range(-k, k + 1):
            out |= p[k + dx: k + dx + n0, k + dz: k + dz + n1]
    return out


# ------------------------------------------------------------------ the climate (biomes by temperature and moisture)
# The owner's method list: "Rule-based biome distribution", "Biome-based generation", "Procedural snow coverage".
# The painter knew slope, hollows, water and height; a snowline was one height for the whole map, and nothing knew
# which side of a ridge the rain falls on. A climate says where the weather comes from:
#   --climate "wind=270,rain=0.6,sea=0.8,lapse=0.35,shade=0.12"     (or the design's "paint": {"climate": {...}})
#   wind   the compass bearing the wind blows FROM, degrees (0 = from the north, -Z; 90 = from the east, +X)
#   rain   0..1: how wet the air is before it meets the land
#   sea    0..1: how warm it is at height 0 (0 = freezing, 1 = hot)
#   lapse  how much colder it gets every 100 studs up (the same 0..1 scale)
#   shade  how much colder a slope that faces north is, and how much warmer one that faces south, than level
#          ground at the same height (at 45 degrees and steeper: twice the shade between the two faces)
# MOISTURE: the air drops its rain where the land lifts it (slopes that face the wind) and is dry behind what it
# has crossed (a rain shadow: the higher the ridge upwind, the drier - fading 240 studs behind it); the erosion's
# water and the hollows add their own. TEMPERATURE: the sea's warmth less the height's lapse, less the shade.
# The painter then reads the two: snow where it freezes (so the snowline sits lower on a north face), lush where it
# is wet and mild, bare ground and sand where it is dry and warm. Roles, not new materials: the same nine.
CLIMATE = {"wind": 270.0, "rain": 0.5, "sea": 0.7, "lapse": 0.3, "shade": 0.12}
CLIMATE_RANGE = {"wind": (0, 360), "rain": (0, 1), "sea": (0, 1), "lapse": (0, 2), "shade": (0, 0.5)}
SHADOW_REACH = 240.0  # studs behind a ridge its rain shadow reaches
SHADOW_HEIGHT = 60.0  # a ridge this much higher than the land behind it takes all the rain it can


def climate_config(text_or_dict):
    """a --climate string ("wind=270,rain=0.6") or a design's dict -> (config with every key, problems)"""
    cfg, problems = dict(CLIMATE), []
    given = {}
    if isinstance(text_or_dict, dict):
        given = dict(text_or_dict)
    elif isinstance(text_or_dict, str):
        for bit in filter(None, (b.strip() for b in text_or_dict.split(","))):
            k, sep, v = bit.partition("=")
            if not sep:
                problems.append(f"climate: \"{bit}\" is not key=value")
                continue
            given[k.strip()] = v.strip()
    else:
        return cfg, ["climate is \"wind=270,rain=0.6,sea=0.8,lapse=0.35,shade=0.12\" (any of them)"]
    for k, v in given.items():
        if k not in CLIMATE:
            problems.append(f"climate.{k}: a climate says wind, rain, sea, lapse, shade - nothing else")
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            problems.append(f"climate.{k} is a number (got {v!r})")
            continue
        lo, hi = CLIMATE_RANGE[k]
        if not (f == f) or f < lo or f > hi:
            problems.append(f"climate.{k} is {lo} to {hi} (got {v})")
            continue
        cfg[k] = f
    return cfg, problems


def climate(h, cell, cfg, flow=None):
    """the land's own weather -> (temperature [n, n] about 0..1, below 0 it freezes; moisture [n, n] 0..1)"""
    n0, n1 = h.shape
    gx, gz = np.gradient(h, cell)  # (axis 0 is x, axis 1 is z: the heights are h[ix, iz])
    # the unit vector the wind blows ALONG (it comes FROM the bearing): bearing 0 = from -Z, so it blows toward +Z
    a = np.radians(cfg["wind"])
    wx, wz = -np.sin(a), np.cos(a)
    # lift: the land rising along the wind (a slope that faces it)
    rise = gx * wx + gz * wz
    lift = np.clip(rise * 2.0, -0.3, 0.6)
    # rain shadow: the highest land upwind within reach, less what it has faded by then
    I, J = np.meshgrid(np.arange(n0), np.arange(n1), indexing="ij")
    barrier = np.zeros_like(h)
    steps = max(1, int(SHADOW_REACH / cell))
    # a ridge is what stands over the land's middle height: a hollow's own rim is no ridge to its floor (measured
    # against the higher of the place itself and the land's median)
    floor = np.maximum(h, float(np.median(h)))
    for s in range(1, steps + 1):
        ri, rj = np.rint(I - wx * s).astype(int), np.rint(J - wz * s).astype(int)
        inside = (ri >= 0) & (ri < n0) & (rj >= 0) & (rj < n1)  # (off the map is open air: no barrier)
        ii, jj = np.clip(ri, 0, n0 - 1), np.clip(rj, 0, n1 - 1)
        fade = 1.0 - s / steps
        barrier = np.maximum(barrier, np.where(inside, (h[ii, jj] - floor) * fade, 0.0))
    shadow = np.clip(barrier / SHADOW_HEIGHT, 0, 1)
    wet = np.zeros_like(h)
    if flow is not None:
        fl = _smooth(flow, 1)
        wet = np.clip(np.log1p(fl) / max(np.log1p(np.percentile(fl, 99.5)), 1e-6), 0, 1)
    hollow = np.clip((_smooth(h, 2) - h) / max(float(np.std(_smooth(h, 2) - h)), 1e-6), -1, 2)
    moisture = np.clip(cfg["rain"] * (1 - 0.95 * shadow) + cfg["rain"] * lift + 0.45 * wet + 0.06 * hollow, 0, 1)
    # a slope that faces north (its downhill way points to -Z) is the colder
    steep = np.sqrt(gx * gx + gz * gz)
    north = np.where(steep > 1e-9, gz / np.maximum(steep, 1e-9), 0.0)  # downhill is -grad: toward -Z when gz > 0
    temperature = cfg["sea"] - cfg["lapse"] * h / 100.0 - cfg["shade"] * north * np.clip(steep, 0, 1)
    return temperature, moisture


def paint(h, cell, flow, deposit, rock_slope, seed, opts):
    """What the land itself says each cell is made of -> (roles uint8 [n, n], shares {role: fraction}).
    slope: cliffs shed soil (rock past rockSlope, dark cliff past +14 deg, a scree apron under them);
    curvature: hollows hold water and soil (lush), sharp convex crests are bare (rock); flow: where the erosion's
    water ran — channels (mud) and wet banks (lush); deposit: where it dropped its sediment — fans and valley
    floors (dirt); height: a snowline broken by noise, a sandy shore at the water. Borders are broken by noise."""
    n = h.shape[0]
    gx, gz = np.gradient(h, cell)
    slope = np.degrees(np.arctan(np.sqrt(gx * gx + gz * gz)))
    lap = (_smooth(h, 2) - h)  # + in hollows, - on crests (studs)
    k = lap / max(float(np.std(lap)), 1e-6)
    t = np.linspace(0, 1, n, endpoint=False)
    U, V = np.meshgrid(t, t, indexing="ij")
    rng = np.random.default_rng(seed + 808)
    size = n * cell
    c1, c2 = max(2, int(size / 60)), max(4, int(size / 14))
    N = gradient_noise(U * c1, V * c1, c1, rng) * 1.4 + gradient_noise(U * c2, V * c2, c2, rng) * 0.5  # ~ -1..1
    if flow is None:
        flow = np.zeros_like(h)
    if deposit is None:
        deposit = np.zeros_like(h)
    fl = _smooth(flow, 1)
    F = np.clip(np.log1p(fl) / max(np.log1p(np.percentile(fl, 99.5)), 1e-6), 0, 1.5)
    D = _smooth(deposit, 1)
    Dn = D / max(float(np.percentile(D[D > 0], 95)) if (D > 0).any() else 1.0, 1e-6)

    r = np.zeros((n, n), np.uint8)  # meadow
    lush = 0.55 * np.clip(k, -1, 2) + 0.7 * np.clip(F - 0.35, 0, 1) + 0.35 * N
    r[(lush > 0.45) & (slope < 26)] = 1
    r[(Dn > 0.8 + 0.25 * N) & (slope < 18)] = 2
    r[(F > 0.95 + 0.05 * N) & (slope < 16)] = 3
    rs = rock_slope + 5 * N
    rocky = (slope > rs) | ((k < -1.6 + 0.4 * N) & (slope > 26))
    scree = _dilate(rocky, 2) & ~rocky & (slope > 14) & (slope < rock_slope + 4) & (N > -0.35)
    r[scree] = 8
    r[rocky] = 4
    r[slope > rock_slope + 14 + 4 * N] = 5
    cfg = opts.get("climate")
    if cfg is not None:
        # BY CLIMATE: wet and mild is lush; dry is bare ground and, where it is warm, sand. "Dry" is measured
        # against the air's own wetness as well as outright, so that the lee of a ridge dries in a wet country too
        # (a fresh reader: with outright levels alone nothing dried behind a ridge at the documented settings).
        # Under a warm climate rock, cliff and scree are the land's own shape and stay; where it freezes, snow lies
        # on everything flatter than 48 degrees but running water.
        T, M = climate(h, cell, cfg, flow)
        soil = (r <= 3) & (slope < 26)
        bare_under = max(0.26, 0.55 * cfg["rain"])
        sand_under = max(0.14, 0.30 * cfg["rain"])
        r[soil & (r <= 1) & (M + 0.12 * N > 0.62) & (T > 0.12)] = 1
        r[soil & (r == 1) & (M + 0.12 * N < 0.34)] = 0  # (a hollow in dry country is no meadow in flower)
        r[soil & (r != 3) & (M + 0.10 * N < bare_under) & (T > 0.3)] = 2
        r[soil & (r != 3) & (M + 0.10 * N < sand_under) & (T > 0.45) & (slope < 18)] = 7
        r[(r != 3) & (T + 0.06 * N < 0) & (slope < 48 + 6 * N)] = 6  # (it freezes: lower on a north face)
    seen = opts.get("imagery")
    if seen is not None:
        # BY THE PICTURE: what the real place shows, on the SOIL (roles 0, 1, 2). Rock a slope made (4) is too steep
        # for soil whatever the picture shows (a fresh reader: sand lay on 50 degrees): it stays rock, and takes only
        # snow, on nothing steeper than 48 degrees. Mud where the water runs (3), cliffs (5) and scree (8) are the
        # land's own and stay; what the picture reads as water says nothing (the land has its own water)
        soil_cells = r <= 2
        for name, role in IMAGERY_ROLE.items():
            here = soil_cells & (seen == name)
            if role == 6:
                here = (soil_cells | (r == 4)) & (seen == name) & (slope < 48)
            r[here] = role
    snowline = opts.get("snowline")
    if snowline is not None and cfg is None:
        r[(h > snowline + 26 * N) & (slope < 48 + 6 * N)] = 6
    shore = opts.get("shore")
    if shore is not None:
        beach = (h > shore - 3) & (h < shore + opts.get("shoreWidth", 3.5) + 2.5 * N) & (slope < 34)
        if cfg is not None:
            beach &= r != 6  # (a frozen shore is snow, not a ring of sand)
        r[beach] = 7
    shares = {ROLES[i]: round(float((r == i).mean()), 3) for i in range(len(ROLES))}
    return r, shares


def paint_preview(h, cell, roles, path):
    from PIL import Image

    gx, gz = np.gradient(h, cell)
    light = np.clip((-gx * 0.7 - gz * 0.7 + 1.0) / np.sqrt(gx * gx + gz * gz + 1.0) * 0.85, 0.2, 1.05)
    pal = np.array([ROLE_COLORS[x] for x in ROLES], float)
    rgb = np.clip(pal[roles] * light[..., None], 0, 255).astype(np.uint8)
    img = Image.fromarray(np.transpose(rgb, (1, 0, 2)))
    img = img.resize((min(1024, img.width * 4), min(1024, img.height * 4)), Image.NEAREST)
    img.save(path)


# ------------------------------------------------------------------ preview
def preview(h, cell, relief, rock_slope, path):
    from PIL import Image

    gx, gz = np.gradient(h * relief, cell)
    slope = np.degrees(np.arctan(np.sqrt(gx * gx + gz * gz)))
    light = np.clip((-gx * 0.7 - gz * 0.7 + 1.0) / np.sqrt(gx * gx + gz * gz + 1.0) * 0.8, 0.15, 1.0)
    low, high = np.array([86, 120, 62]), np.array([196, 190, 170])
    col = low[None, None, :] * (1 - h[..., None]) + high[None, None, :] * h[..., None]
    rock = slope > rock_slope
    col[rock] = np.array([120, 116, 110])
    rgb = np.clip(col * light[..., None], 0, 255).astype(np.uint8)
    img = Image.fromarray(np.transpose(rgb, (1, 0, 2)))  # x right, z down (like kit world's maps)
    img = img.resize((min(1024, img.width * 4), min(1024, img.height * 4)), Image.NEAREST)
    img.save(path)
    return float(rock.mean())


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: terrain.py <out.hm.json> [flags]", "next_action": "lune run kit world terrain <Name>"}))
        return 1
    out = argv[0]
    o = {"size": 512, "step": 4, "seed": 3, "octaves": 6, "scale": 180, "relief": 60, "erosion": 60000, "thermal": 25, "from": None, "design": None, "rockSlope": 38,
         "snowline": None, "shore": None, "warp": 0, "stream": None, "streamK": None}
    imagery_arg = None  # (the painter's too)
    climate_arg = None  # (kept out of the recipe `o`: the painter's, not the heights' - the route proof re-makes heights)
    stamps = []
    sinks = []
    flats = []
    i = 1
    while i < len(argv):
        k = argv[i].lstrip("-")
        v = argv[i + 1] if i + 1 < len(argv) else None
        if k == "flat":
            flats.append(tuple(float(t) for t in v.split(",")))
        elif k == "stamp":
            one, problem = stamp_config(v) if v is not None else (None, "--stamp needs kind,x,z,radius,height")
            if problem:
                print(json.dumps({"status": "fail", "summary": "terrain: " + problem,
                                  "next_action": "fix --stamp (kind,x,z,radius,height[,turn][,worked]) and run it again"}))
                return 1
            stamps.append(one)
        elif k == "sink":
            one, problem = sink_config(v) if v is not None else (None, "--sink needs x,z,radius")
            if problem:
                print(json.dumps({"status": "fail", "summary": "terrain: " + problem,
                                  "next_action": "fix --sink (x,z,radius in studs from the map's middle) and run it again"}))
                return 1
            sinks.append(one)
        elif k == "climate":
            if v is None or v.startswith("--"):
                print(json.dumps({"status": "fail", "summary": "terrain: --climate needs its words (\"wind=270,rain=0.6,sea=0.8\")",
                                  "next_action": "give --climate a value, or leave it out"}))
                return 1
            climate_arg = v
        elif k == "imagery":
            if imagery_arg is not None:
                print(json.dumps({"status": "fail", "summary": "terrain: --imagery is said twice",
                                  "next_action": "one picture paints a land"}))
                return 1
            if v is None or v.startswith("--"):
                print(json.dumps({"status": "fail", "summary": "terrain: --imagery needs the picture's file (<Name>.img.png)",
                                  "next_action": "give --imagery a file, or leave it out"}))
                return 1
            imagery_arg = v
        elif k in o:
            o[k] = v if k in ("from", "design") else float(v)
        elif k == "no-paint":
            o["noPaint"] = True
            i -= 1
        i += 2
    cli_flats = list(flats)  # (recorded with the recipe: kit world check re-makes a terrain from it to prove its route)
    n = int(o["size"] / o["step"]) + 1
    cell = o["step"]
    if o["design"]:
        with open(o["design"], encoding="utf-8") as fh:
            design = json.load(fh)
        h, keep, mtn = designed(n, o["size"], design, int(o["seed"]),
                                os.path.dirname(os.path.abspath(o["design"])))  # already in studs
        designed_h = h.copy()
        for p in design.get("flat", []):
            flats.append((p[0], p[1], p[2]))
        before = h / max(h.max(), 1e-9)
        o["relief"] = float(h.max())
    else:
        if o["from"]:
            h = from_image(o["from"], n)
        else:
            h = fbm(n, o["size"], o["scale"], int(o["octaves"]), int(o["seed"]), warp=o["warp"])
        before = h.copy()
        h = h * o["relief"]  # erosion works in studs
    def stamp_fail(why, fix):
        print(json.dumps({"status": "fail", "summary": "terrain: " + why, "next_action": fix}))
        return 1

    for one in stamps:
        if abs(one["x"]) - one["radius"] >= o["size"] / 2 or abs(one["z"]) - one["radius"] >= o["size"] / 2:
            return stamp_fail(f"the stamp {stamp_text(one)} lies off the land (the map is {o['size']:g} studs: "
                              f"x and z run -{o['size'] / 2:g} to {o['size'] / 2:g} from its middle)",
                              "move the stamp onto the land")
    for one in stamps:  # (worked: land forms the rivers and the erosion then work on)
        if one["worked"]:
            if o["design"] and (keep[stamp(np.zeros_like(h), cell, one) != 0] > 0.5).any():
                return stamp_fail(f"the worked stamp {stamp_text(one)} lies on a shape the design protects: the "
                                  "design's own heights are put back there after the erosion and the stamp would be "
                                  "thrown away", "lay it without \"worked\" (on the finished land), or move it")
            h = stamp(h, cell, one)
            if float(h.min()) < 0:
                return stamp_fail(f"the worked stamp {stamp_text(one)} digs {-float(h.min()):.0f} studs under the "
                                  "land's floor (height 0): the whole land would be lifted to make room",
                                  "make it shallower, or raise the land it is laid on")
    worked_base = h.copy() if any(one["worked"] for one in stamps) else None
    flow = deposit = None
    climate_from = "--climate"
    if o["design"] and climate_arg is None:
        designed_climate = (design.get("paint") or {}).get("climate")
        if designed_climate is not None and designed_climate is not False:  # (false: painted with none, meant)
            climate_arg, climate_from = designed_climate, f"the design's paint.climate ({o['design']})"
    climate_cfg = None
    if climate_arg is not None:
        if isinstance(climate_arg, str) and not climate_arg.strip():
            climate_problems = ["climate is empty: say its words, or leave it out"]
        elif not isinstance(climate_arg, (str, dict)):
            climate_problems = [f"climate is \"wind=270,rain=0.6\" or {{\"wind\": 270, ...}} (got {climate_arg!r})"]
        else:
            climate_cfg, climate_problems = climate_config(climate_arg)
        if climate_problems:
            print(json.dumps({"status": "fail", "summary": "terrain: " + "; ".join(climate_problems),
                              "next_action": f"fix {climate_from} (wind, rain, sea, lapse, shade) and run it again"}))
            return 1
    if o["design"]:  # the design may carry the painter's levels
        for key in ("snowline", "shore"):
            if o.get(key) is None and (design.get("paint") or {}).get(key) is not None:
                o[key] = float(design["paint"][key])
    if o["design"]:
        for key in ("stream", "streamK"):  # (the command line wins when it names them)
            if o[key] is None and (design.get("erosion") or {}).get(key) is not None:
                o[key] = float(design["erosion"][key])
    if o["design"] and imagery_arg is None:
        designed_imagery = (design.get("paint") or {}).get("imagery")
        if designed_imagery is not None and designed_imagery is not False:
            imagery_arg = designed_imagery
    seen_land = None
    if imagery_arg is not None:
        if not isinstance(imagery_arg, str) or not imagery_arg.strip():
            print(json.dumps({"status": "fail", "summary": f"terrain: imagery is a picture's file (got {imagery_arg!r})",
                              "next_action": "name the file kit world imagery wrote, or leave it out"}))
            return 1
        if o.get("noPaint"):
            print(json.dumps({"status": "fail", "summary": "terrain: --imagery paints the land and --no-paint says not to "
                              "paint it: one of them", "next_action": "drop --imagery, or drop --no-paint"}))
            return 1
        if climate_cfg is not None or o.get("snowline") is not None:
            # (two tellers of what covers the soil: one of them would be thrown away without a word)
            print(json.dumps({"status": "fail", "summary": "terrain: an aerial picture says what covers the land, and so does "
                              "a climate (or a snowline): one of them",
                              "next_action": "drop --imagery, or drop the climate / snowline"}))
            return 1
        seen_land, why = imagery_read(imagery_arg, n, design if o["design"] else None,
                                      os.path.dirname(os.path.abspath(o["design"])) if o["design"] else ".")
        if why:
            print(json.dumps({"status": "fail", "summary": "terrain: " + why, "next_action": "fix --imagery and run it again"}))
            return 1
    if climate_cfg is not None and o.get("snowline") is not None:
        # (a typed snowline beside a climate was dropped without a word: 80 % snow became none)
        print(json.dumps({"status": "fail", "summary": f"terrain: a climate makes its own snowline (where it freezes): "
                          f"a snowline of {o['snowline']:g} beside it would be thrown away",
                          "next_action": "drop the snowline (set the climate's sea and lapse for where the snow starts), or drop the climate"}))
        return 1
    # the river route BY DEFAULT: land from noise + thermal erosion alone is the route the owner's SampleRegion_terrain_v1
    # verdict rules out, and kit world check's terrain route gate refuses it. Stream 80 / K 0.015 is the kit's recipe
    # (its river step alone cuts 6-25 % of the relief); real land (a design "dem") is river-carved already and the pass
    # over-carves it, so it takes none unless asked. --stream 0 still opts out (the gate then wants real land).
    if o["stream"] is None:
        o["stream"] = 0 if (o["design"] and design.get("dem")) else 80
    if o["streamK"] is None:
        o["streamK"] = 0.015
    if o["stream"] > 0:  # rivers first: they decide where the valleys and the ridges are
        sunk = sink_mask(sinks, h.shape[0], cell)
        h = sink_apply(h, sunk)
        h, _ = stream_multiscale(h, cell, int(o["stream"]), o["streamK"], keep=keep if o["design"] else None,
                                 base=sunk)
    if o["thermal"] > 0:
        h = thermal(h, cell, int(o["thermal"]))
    if o["erosion"] > 0:
        h, flow, deposit = hydraulic(h / cell, cell, int(o["erosion"]), int(o["seed"]))
        h = h * cell
        deposit = deposit * cell
        h = thermal(h, cell, max(4, int(o["thermal"]) // 2))  # the fresh cuts collapse to their talus slope
    if o["design"]:
        if design.get("terraces"):
            h = terraces(h, mtn * (1 - keep), design["terraces"], o["size"], int(o["seed"]))
        h = h * (1 - keep) + designed_h * keep  # (the protected shapes, as designed)
        anchor = design.get("anchor")  # [x, z, height]: this spot keeps its height whatever the erosion did
        if anchor:
            c = (n - 1) / 2
            ax = int(round(np.clip(anchor[0] / cell + c, 0, n - 1)))
            az = int(round(np.clip(anchor[1] / cell + c, 0, n - 1)))
            h = h + (anchor[2] - h[ax, az])
    if not (o["design"] and design.get("anchor")):
        h = h - min(0.0, float(h.min()))  # (no anchor: carved channels lower the floor instead of being flattened)
    clipped = float((h < 0).mean())
    h = np.clip(h, 0, None)
    eroded = h.copy()
    for one in stamps:  # (laid on the finished land: crisp, and nothing outside its radius moves)
        if not one["worked"]:
            h = stamp(h, cell, one)
            if float(h.min()) < 0:
                return stamp_fail(f"the stamp {stamp_text(one)} digs {-float(h.min()):.0f} studs under the land's "
                                  "floor (height 0): it would be cut off flat there",
                                  "make it shallower, or lay it where the land is higher")
    relief = float(h.max()) if h.max() > 0 else 1.0
    hn = h / relief
    if flats:
        hn = smooth_pads(hn, cell, [(x, z, r) for x, z, r in flats])
    carved = float(np.mean(np.abs(hn * relief - before * o["relief"])))
    if stamps:  # (what the EROSION moved: a stamp is no erosion - measured before the stamps laid on the finished
        # land, against the land with its worked stamps)
        carved = float(np.mean(np.abs(eroded - (worked_base if worked_base is not None else before * o["relief"]))))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    roles, shares = None, {}
    if not o.get("noPaint"):
        roles, shares = paint(hn * relief, cell, flow, deposit, o["rockSlope"], int(o["seed"]),
                              {"snowline": o.get("snowline"), "shore": o.get("shore"), "climate": climate_cfg,
                               "imagery": seen_land["names"] if seen_land else None})
    data = {"nx": n, "nz": n, "step": cell, "relief": round(relief, 2), "seed": int(o["seed"]),
            "made_by": "kit/world/terrain.py", "options": {k: v for k, v in o.items() if v is not None},
            "heights": [round(float(v), 2) for v in (hn * relief).ravel()]}
    if cli_flats:  # (the design's own flats live in the design file; these came from the command line)
        data["options"]["flat"] = [list(f) for f in cli_flats]
    if sinks:  # (part of the heights' recipe too: where the rivers drain to)
        data["options"]["sink"] = [",".join(f"{v:g}" for v in one) for one in sinks]
    if stamps:  # (part of the heights' recipe: kit world check re-makes the land from it, stamps and all)
        data["options"]["stamp"] = [stamp_text(one) for one in stamps]
    if roles is not None:
        data["roles"] = ROLES
        data["paint"] = paint_encode(roles)
        if climate_cfg is not None:
            data["climate"] = climate_cfg  # (what the painter read: the build's lock asks a painted land for it)
        if seen_land is not None:
            data["imagery"] = seen_land["record"]  # (the picture the painter read, its box and its credit line)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, separators=(",", ":"))
    png = os.path.splitext(os.path.splitext(out)[0])[0] + ".hm.png"
    rock_share = preview(hn, cell, relief, o["rockSlope"], png)
    paint_png = None
    if roles is not None:
        paint_png = os.path.splitext(os.path.splitext(out)[0])[0] + ".paint.png"
        paint_preview(hn * relief, cell, roles, paint_png)
        top = sorted(shares.items(), key=lambda kv: -kv[1])
        rock_share = shares.get("rock", 0) + shares.get("cliff", 0)
    bad_clip = clipped > 0.05  # (an anchor set too low sinks the map under 0: it would be flattened)
    print(json.dumps({"status": "fail" if bad_clip else "pass", "summary": (f"{clipped * 100:.0f} % of the map fell under 0 and was flattened (the design's anchor?); " if clipped > 0.005 else "") + f"{n}x{n} heights ({o['size']:.0f} studs at {cell:.0f}), relief {relief:.1f}, erosion moved {carved:.2f} studs on average, {rock_share * 100:.0f} % rock (steeper than {o['rockSlope']:.0f} deg)"
                      + (f"; painted: {', '.join(f'{k} {v * 100:.0f} %' for k, v in top if v >= 0.01)} (LOOK at {paint_png.replace(os.sep, '/')})" if paint_png else ""),
                      "next_action": f"look at {png.replace(os.sep, '/')} — then use it: \"terrain\": [{{\"heightmap\": {{\"center\": [0, 0, 0], \"size\": [{o['size']:.0f}, {o['size']:.0f}], \"source\": \"{out.replace(os.sep, '/')}\", \"material\": \"Grass\", \"rock\": \"Rock\"}}}}]",
                      "file": out.replace(os.sep, "/"), "preview": png.replace(os.sep, "/")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
