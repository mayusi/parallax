"""gothic_blender.py — gothic masonry pieces for the GothicCourtyard world set.

Look source: Bloodborne Cathedral Ward at night (assets/worlds/refs/GothicCourtyard/).
Palette: stone dark (42,47,53) / mid (72,75,79) / cool (58,75,81) / light (89,105,109),
         slate roof (24,27,33), wrought iron (18,18,20), plaster inside (118,110,98),
         dark wood (40,30,22).

Coordinate frame: Blender Z-up, 1 unit = 1 Roblox stud.
  Roblox (x, y_up, z) → Blender (x, -z, y).
  Front faces Blender -Y. Origin = piece foot as stated per kind.
  Every mesh ≤ 9000 triangles (MAX_TRIS in meshes_blender.py).

Entry:  build_piece(rec) → (obj, img)   — same contract as castle_blender.build_piece.
"""

import math
import random

import bpy
import numpy as np

import housebays  # (pure python beside this file: meshes_blender.py puts kit/world on the path before importing us)
import quoins  # (pure python too: a corner's quoin strip)

# ---------------------------------------------------------------------------
# Atlas (re-use _fbm pattern from castle_blender; we do NOT import it to stay independent)
# ---------------------------------------------------------------------------
TILE_N = 8          # 8 × 8 tiles
TILE_WORLD = 8.0    # one repeat per ~8 studs (texel density)
STONE_TILES = 48    # 0..47 stone, 48..55 edge/chamfer, 56..59 mortar
EDGE0, MORTAR0, PAVE0 = 48, 56, 60
SLATE0 = 40         # tiles 40..47 → roof slates when slate colour given
IRON0 = 62          # tiles 62..63 → wrought iron
GLASS0 = 60         # tiles 60..61 → amber glass
PLASTER0 = 36       # tiles 36..39 → plaster (inner walls)


def _fbm(shape, rng, scales):
    out = np.zeros(shape)
    for s, w in scales:
        g = rng.random((shape[0] // s + 2, shape[1] // s + 2))
        ys = np.linspace(0, g.shape[0] - 1.001, shape[0])
        xs = np.linspace(0, g.shape[1] - 1.001, shape[1])
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
        fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
        a = g[y0][:, x0] * (1 - fx) + g[y0][:, x0 + 1] * fx
        b = g[y0 + 1][:, x0] * (1 - fx) + g[y0 + 1][:, x0 + 1] * fx
        out += w * (a * (1 - fy) + b * fy)
    return out / sum(w for _, w in scales)


def gothic_atlas(stone, size, seed, slate=None, iron=False, with_plaster=True, with_glass=True):
    """RGBA float [size, size, 4].
    stone: dark Gothic ashlar — coursed, recessed joints, soot near top.
    slate: roof slates when given.
    iron: wrought iron tiles 62-63.
    """
    rng = np.random.default_rng(seed)
    t = size // TILE_N
    img = np.zeros((size, size, 4), dtype=np.float32)
    base = np.array(stone, float) / 255.0
    tones = []
    for i in range(STONE_TILES):
        tone = 0.78 + 0.28 * (i / (STONE_TILES - 1)) + rng.normal(0, 0.016)
        hue = np.array([1 + rng.normal(0, 0.010), 1 + rng.normal(0, 0.007), 1 + rng.normal(0, 0.013)])
        tones.append((tone, hue))
    plaster_base = np.array([118, 110, 98], float) / 255.0
    wood_base = np.array([40, 30, 22], float) / 255.0
    iron_base = np.array([18, 18, 20], float) / 255.0
    for k in range(TILE_N * TILE_N):
        r, c = divmod(k, TILE_N)
        grain = _fbm((t, t), rng, [(32, 0.5), (8, 0.3), (2, 0.2)])
        pits = (rng.random((t, t)) < 0.014) * rng.uniform(0.15, 0.40, (t, t))
        if slate is not None and SLATE0 <= k < STONE_TILES:
            sb = np.array(slate, float) / 255.0
            cleave = _fbm((t, t), rng, [(64, 0.6), (16, 0.4)])
            layers = _fbm((t, t), rng, [(2, 1.0)]) * 0.3 + np.repeat(_fbm((t, 1), rng, [(4, 1.0)]), t, 1) * 0.7
            col = sb * rng.uniform(0.78, 1.10) * (0.72 + 0.38 * cleave + 0.22 * layers)[..., None]
            wear = np.linspace(0.0, 1.0, t)[:, None] ** 6
            col = col * (1 - 0.32 * wear[..., None]) + base * 0.52 * 0.32 * wear[..., None]
        elif with_plaster and PLASTER0 <= k < SLATE0:
            # interior plaster: warm, lightly grained, darker patches at corners (moisture)
            col = plaster_base * rng.uniform(0.82, 1.08) * (0.88 + 0.22 * grain)[..., None]
            moisture = np.clip((_fbm((t, t), rng, [(16, 0.6), (4, 0.4)]) - 0.68) * 5, 0, 1)
            col = col * (1 - 0.18 * moisture)[..., None]
        elif iron and k >= IRON0:
            # wrought iron: near-black, slight sheen on edges
            col = iron_base * rng.uniform(0.9, 1.15) * (0.72 + 0.38 * grain)[..., None]
        elif with_glass and k >= GLASS0 and k < IRON0:
            # amber glass (lantern panes, window glass): warm translucent tint
            glass_base = np.array([80, 60, 20], float) / 255.0
            col = glass_base * rng.uniform(0.7, 1.1) * (0.6 + 0.5 * grain)[..., None]
        elif k < STONE_TILES:
            tone, hue = tones[k]
            col = base * hue * tone * (0.80 + 0.32 * grain)[..., None]
            col *= (1 - pits)[..., None]
            # soot near top / in recesses (Gothic buildings: very dark at the top, pale mid-section)
            if rng.random() < 0.30:
                soot = _fbm((t, t), rng, [(4, 1.0)])[:1].repeat(t, 0) * np.linspace(1, 0.3, t)[:, None]
                col *= (1 - 0.22 * soot)[..., None]
            if rng.random() < 0.10:
                m = np.clip((_fbm((t, t), rng, [(16, 0.7), (4, 0.3)]) - 0.65) * 7, 0, 1)
                col = col * (1 - m[..., None] * 0.55) + np.array([0.35, 0.37, 0.25]) * m[..., None] * 0.55
            # hard cap: no pure-stone ashlar tile lighter than RGB (110,114,118)/255 ≈ 0.431
            col = np.clip(col, 0, 110.0 / 255.0)
        elif k < MORTAR0:
            col = base * 0.55 * (0.78 + 0.44 * grain)[..., None] * (1 - pits * 1.6)[..., None]
        elif k < PAVE0:
            col = base * 0.36 * (0.72 + 0.55 * _fbm((t, t), rng, [(2, 1.0)]))[..., None]
        else:
            col = base * (0.88 + 0.12 * rng.random()) * (0.82 + 0.32 * grain)[..., None]
        img[r * t:(r + 1) * t, c * t:(c + 1) * t, :3] = np.clip(col, 0, 1)
        img[r * t:(r + 1) * t, c * t:(c + 1) * t, 3] = 1
    return img


# ---------------------------------------------------------------------------
# Pure-Python mesh builder (no Blender imports — same as castle_blender.Mesh)
# ---------------------------------------------------------------------------
class Mesh:
    def __init__(self, rng):
        self.v, self.f, self.uv, self.rng = [], [], [], rng

    def quad(self, pts, tile, u_axis, v_axis):
        pts = [np.array(p, float) for p in pts]
        us = [float(np.dot(p, u_axis)) for p in pts]
        vs = [float(np.dot(p, v_axis)) for p in pts]
        u0, v0 = min(us), min(vs)
        span = max(max(us) - u0, max(vs) - v0, 1e-6)
        scale = 1.0 / max(TILE_WORLD, span)
        ou = self.rng.uniform(0, max(0.0, 1 - (max(us) - u0) * scale))
        ov = self.rng.uniform(0, max(0.0, 1 - (max(vs) - v0) * scale))
        r, c = divmod(int(tile), TILE_N)
        pad = 2.0 / 1024
        i0 = len(self.v)
        for p, u, v in zip(pts, us, vs):
            uu = c / TILE_N + pad + (ou + (u - u0) * scale) * (1 / TILE_N - 2 * pad)
            vv = 1 - (r + 1) / TILE_N + pad + (ov + (v - v0) * scale) * (1 / TILE_N - 2 * pad)
            self.v.append(p)
            self.uv.append((uu, vv))
        self.f.append(list(range(i0, i0 + len(pts))))

    def tri(self, a, b, c):
        self.f.append([a, b, c])


X, Y, Z = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])


# ---------------------------------------------------------------------------
# Shared geometry helpers
# ---------------------------------------------------------------------------
def _pick(rng_obj, z, z_top, dark_base=0, light_base=28):
    """darker low, lighter mid, dark soot near top. Clamps to pure stone range (0..PLASTER0-1)."""
    t = min(1.0, max(0.0, (z - 0.5) / max(z_top * 0.6, 1)))
    return int(np.clip(rng_obj.gauss(dark_base + t * (light_base - dark_base), 5), 0, PLASTER0 - 1))


def _edge(rng_obj):
    return EDGE0 + rng_obj.randrange(8)


def _mortar(rng_obj):
    return MORTAR0 + rng_obj.randrange(4)


def _plaster(rng_obj):
    return PLASTER0 + rng_obj.randrange(4)


def _courses(h0, h1, ch=1.2):
    """course z-boundaries from h0 to h1, ~ch studs per course"""
    zs, z, k = [h0], h0, 0
    while z < h1 - 0.4:
        step = ch * (1.1 if k % 2 else 0.9)
        z = min(h1, z + step)
        if h1 - z < 0.4:
            z = h1
        zs.append(z)
        k += 1
    return zs


def _pointed_arch_pts(cx, cz_spring, r, n=16):
    """two-centred pointed arch: each semicircle centred at (cx ± r/2, cz_spring).
    Returns list of (x, z) from left springing up over crown and down to right springing.
    r = half-span (the arch spans 2r)."""
    pts = []
    offset = r * 0.5  # centre offset for a typical gothic two-centred arch
    # left semicircle (centre at cx - offset, cz_spring, r_circle = sqrt(r^2 + offset^2))
    r_circle = math.sqrt(r * r + offset * offset)
    # left half: angles from (pointing right at the spring) up to crown
    a_start_l = math.asin(-offset / r_circle)  # the angle at the left springing from left centre
    a_crown_l = math.pi - math.asin(offset / r_circle)
    for i in range(n // 2 + 1):
        a = a_start_l + (a_crown_l - a_start_l) * i / (n // 2)
        x = (cx - offset) + r_circle * math.cos(a)
        z = cz_spring + r_circle * math.sin(a)
        pts.append((x, z))
    # right half: mirror
    for i in range(1, n // 2 + 1):
        p = pts[n // 2 - i]
        pts.append((2 * cx - p[0], p[1]))
    return pts


def _quad_wall(m, x0, x1, y, z0, z1, tile, facing=-1):
    """a rectangular wall panel facing ±Y at a fixed y, running x0..x1, z0..z1"""
    if facing < 0:
        m.quad([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], tile, X, Z)
    else:
        m.quad([(x1, y, z0), (x0, y, z0), (x0, y, z1), (x1, y, z1)], tile, X, Z)


def _quad_xwall(m, x, y0, y1, z0, z1, tile, facing=1):
    """a rectangular wall panel facing ±X at a fixed x, running y0..y1, z0..z1"""
    if facing > 0:
        m.quad([(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], tile, Y, Z)
    else:
        m.quad([(x, y1, z0), (x, y0, z0), (x, y0, z1), (x, y1, z1)], tile, Y, Z)


def _ashlar_panel(m, rng_obj, x0, x1, y, z0, z1, z_top, facing=-1, block_w=(1.5, 3.0), is_inner=False):
    """fill a rectangular face with coursed ashlar blocks (no arch openings).
    facing: -1 = -Y face (front), +1 = +Y face, 'x+' = +X, 'x-' = -X"""
    zs = _courses(z0, z1)
    bx_rng = random.Random(rng_obj.randrange(10000))
    for iz, (za, zb) in enumerate(zip(zs[:-1], zs[1:])):
        # joint pattern: simple random
        xs = [x0]
        while xs[-1] < x1 - 0.4:
            xs.append(min(x1, xs[-1] + bx_rng.uniform(*block_w)))
        if xs[-1] < x1:
            xs[-1] = x1
        for ax, bx in zip(xs[:-1], xs[1:]):
            if bx - ax < 0.3:
                continue
            tile = _plaster(rng_obj) if is_inner else _pick(rng_obj, za, z_top)
            if facing == -1:
                m.quad([(ax, y, za), (bx, y, za), (bx, y, zb), (ax, y, zb)], tile, X, Z)
            elif facing == 1:
                m.quad([(bx, y, za), (ax, y, za), (ax, y, zb), (bx, y, zb)], tile, X, Z)
            elif facing == 'x+':
                m.quad([(y, ax, za), (y, bx, za), (y, bx, zb), (y, ax, zb)], tile, Y, Z)
            else:  # x-
                m.quad([(y, bx, za), (y, ax, za), (y, ax, zb), (y, bx, zb)], tile, Y, Z)


# ---------------------------------------------------------------------------
# POINTED ARCH with hood mould + jambs (shared: used by gothic_house and gothic_bay)
# ---------------------------------------------------------------------------
def _pointed_window_opening(m, rng_obj, cx, y_outer, depth, z_sill, z_head_spring, r_half,
                             z_top, hood_proj=0.25, hood_w=0.3, has_mullion=True, has_tracery=False):
    """Add a pointed window opening in a wall at y_outer (front face Y coord).
    The opening cuts from z_sill to pointed head.
    depth: wall thickness direction (into +Y from y_outer).
    r_half: half-span of opening (so opening is 2*r_half wide).
    Returns actual arch crown z."""
    n_arch = 8
    arch_pts = _pointed_arch_pts(cx, z_head_spring, r_half, n_arch)
    crown_z = max(p[1] for p in arch_pts)

    # soffit (arch underside, at y_outer going in depth)
    for i in range(len(arch_pts) - 1):
        xa, za = arch_pts[i]
        xb, zb = arch_pts[i + 1]
        m.quad([(xa, y_outer, za), (xb, y_outer, zb), (xb, y_outer + depth, zb), (xa, y_outer + depth, za)],
               _edge(rng_obj), X, Z)

    # jambs (sides of opening, below the arch spring)
    for sx, xx in ((-1, cx - r_half), (1, cx + r_half)):
        pts_out = [(xx, y_outer, z_sill), (xx, y_outer, z_head_spring)]
        pts_in = [(xx, y_outer + depth, z_sill), (xx, y_outer + depth, z_head_spring)]
        if sx > 0:
            m.quad([pts_out[0], pts_in[0], pts_in[1], pts_out[1]], _pick(rng_obj, z_sill, z_top), Y, Z)
        else:
            m.quad([pts_in[0], pts_out[0], pts_out[1], pts_in[1]], _pick(rng_obj, z_sill, z_top), Y, Z)

    # sill
    m.quad([(cx - r_half - 0.1, y_outer - 0.12, z_sill),
            (cx + r_half + 0.1, y_outer - 0.12, z_sill),
            (cx + r_half, y_outer + depth, z_sill),
            (cx - r_half, y_outer + depth, z_sill)],
           PAVE0 + rng_obj.randrange(4), X, Y)

    # hood mould (a stepped stone moulding projecting from the wall face above the arch)
    hood_pts = [(cx + arch_pts[i][0] - cx, arch_pts[i][1]) for i in range(len(arch_pts))]
    # project each arch point outward and add the hood projection
    for i in range(len(arch_pts) - 1):
        xa, za = arch_pts[i]
        xb, zb = arch_pts[i + 1]
        yh = y_outer - hood_proj
        # outer hood (slightly wider than arch)
        f = 1 + hood_w / r_half if r_half > 0.1 else 1
        xa2, xb2 = cx + (xa - cx) * f, cx + (xb - cx) * f
        za2 = z_head_spring + (za - z_head_spring) * f
        zb2 = z_head_spring + (zb - z_head_spring) * f
        m.quad([(xa2, yh, za2), (xb2, yh, zb2), (xb, y_outer, zb), (xa, y_outer, za)],
               _edge(rng_obj), X, Z)

    # mullion (thin bar splitting the window, doesn't block the view — just the quad)
    if has_mullion and r_half > 1.5:
        mw = 0.12
        m.quad([(cx - mw, y_outer + 0.08, z_sill + 0.3),
                (cx + mw, y_outer + 0.08, z_sill + 0.3),
                (cx + mw, y_outer + 0.08, z_head_spring - 0.3),
                (cx - mw, y_outer + 0.08, z_head_spring - 0.3)],
               _edge(rng_obj), X, Z)
        # transom on tall windows
        if z_head_spring - z_sill > 6:
            tz = z_sill + (z_head_spring - z_sill) * 0.45
            tw = 0.1
            m.quad([(cx - r_half + 0.1, y_outer + 0.08, tz - tw),
                    (cx + r_half - 0.1, y_outer + 0.08, tz - tw),
                    (cx + r_half - 0.1, y_outer + 0.08, tz + tw),
                    (cx - r_half + 0.1, y_outer + 0.08, tz + tw)],
                   _edge(rng_obj), X, Z)
    return crown_z


# ---------------------------------------------------------------------------
# gothic_house
# ---------------------------------------------------------------------------
def _house_mesh(rec):
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))

    W = float(rec.get("width", 22))
    D = float(rec.get("depth", 22))
    floors = int(rec.get("floors", 4))
    fH = float(rec.get("floorHeight", 14))
    thick = float(rec.get("thickness", 1.2))

    win_cfg = rec.get("windows", {})
    win_every = float(win_cfg.get("every", 10))
    win_w = float(win_cfg.get("width", 3.4))
    win_h = float(win_cfg.get("height", 7))
    win_sill = float(win_cfg.get("sill", 3.5))
    win_sides = win_cfg.get("sides", ["N", "E", "S", "W"])

    door_cfg = rec.get("door", {})
    door_side = door_cfg.get("side", "S")
    door_w = float(door_cfg.get("width", 5))
    door_h = float(door_cfg.get("height", 9))

    gable_cfg = rec.get("gable", {})
    gable_h = float(gable_cfg.get("height", 18))
    gable_steps = int(gable_cfg.get("steps", 6))

    has_chimney = bool(rec.get("chimney", True))

    total_h = floors * fH  # wall top (before gable)
    z_top = total_h + 2.5  # parapet eave

    # --- helper: outer face coords
    # Walls: outer face at X = ±(W/2 + 0.05), Y = ±(D/2 + 0.05)
    # thickness inward
    xo, yo = W / 2 + 0.05, D / 2 + 0.05  # outer face extents

    def side_params(side):
        """returns (y_outer, run_axis, run_lo, run_hi, len_run, facing, is_x_wall)"""
        if side == "S":   # front: Blender -Y face, run along -X
            return -yo, -1, -W / 2, W / 2, W, -1, False
        elif side == "N": # back: +Y face, run along +X
            return yo, 1, -W / 2, W / 2, W, 1, False
        elif side == "E": # right: +X face, run along -Y direction = Blender +Y → flip
            return xo, 1, -D / 2, D / 2, D, 1, True
        else:             # W: -X face, run along +Y
            return -xo, -1, -D / 2, D / 2, D, -1, True

    # Build each face
    for side in ["N", "E", "S", "W"]:
        y_outer, run_dir, run_lo, run_hi, run_len, facing, is_xwall = side_params(side)
        y_inner = y_outer + (thick if facing < 0 else -thick) if not is_xwall else (
            y_outer - thick if facing > 0 else y_outer + thick)
        is_xwall_check = is_xwall  # just alias

        has_windows = side in win_sides
        is_door_side = (side == door_side)

        # Compute window positions: n = floor((run_len - 4) / win_every)
        # At = -run_len/2 + (k - 0.5) * run_len / n for k in 1..n
        # (positions along the side measured from side midpoint)
        # (kit/world/housebays.py holds the rule for both sides: a wall too short for a bay has NO opening - the
        # building has none there either - and on the S and E walls the door's bay is counted from the far end,
        # where the building generator starts those walls: with an even count the door stood in a window's bay)
        bay_centres = housebays.centres(run_len, win_every)
        n_win = len(bay_centres)
        win_positions = []  # (pos along run axis, floor) -> x or y coord of window centre
        door_slot = housebays.door_slot(run_len, win_every, side)  # 1-based; 0 = no bay

        for fl in range(floors):
            for k in range(1, n_win + 1):
                at = bay_centres[k - 1]
                is_door = is_door_side and fl == 0 and k == door_slot
                win_positions.append((at, fl, is_door))

        # Build the wall face in sections around openings.
        # Economy: outer wall uses coarse courses (2 studs) and wide blocks (3-6 studs);
        # inner face is a single plaster panel per floor (no per-block subdivision).

        for fl in range(floors):
            z0_fl = fl * fH
            z1_fl = (fl + 1) * fH

            # Collect openings on this floor/side
            openings_this = []
            for at, ofl, is_door in win_positions:
                if ofl != fl:
                    continue
                if is_door:
                    openings_this.append((at, 0, door_h, door_w / 2))
                elif has_windows:
                    z_win_lo = z0_fl + win_sill
                    z_win_hi = z_win_lo + win_h
                    openings_this.append((at, z_win_lo, z_win_hi, win_w / 2))

            # Outer face: coarse ashlar courses (2.0 stud high), wide blocks (3-6 studs)
            zs = _courses(z0_fl, z1_fl, ch=2.0)
            for za, zb in zip(zs[:-1], zs[1:]):
                # horizontal intervals minus opening cuts
                intervals = [(run_lo, run_hi)]
                for (at, oz0, oz1, ohalf) in openings_this:
                    if za < oz1 and zb > oz0:
                        new_int = []
                        for a_, b_ in intervals:
                            lo_cut, hi_cut = at - ohalf - 0.08, at + ohalf + 0.08
                            if b_ <= lo_cut or a_ >= hi_cut:
                                new_int.append((a_, b_))
                            else:
                                if a_ < lo_cut:
                                    new_int.append((a_, lo_cut))
                                if b_ > hi_cut:
                                    new_int.append((hi_cut, b_))
                        intervals = new_int
                brng = random.Random(seed * 97 + fl * 13 + int(za * 10))
                for a_, b_ in intervals:
                    if b_ - a_ < 0.3:
                        continue
                    # wide blocks: 3-6 studs
                    bxs = [a_]
                    while bxs[-1] < b_ - 0.5:
                        bxs.append(min(b_, bxs[-1] + brng.uniform(3.0, 6.0)))
                    bxs[-1] = b_
                    for bxa, bxb in zip(bxs[:-1], bxs[1:]):
                        if bxb - bxa < 0.4:
                            continue
                        tile = _pick(rng, za, z_top)
                        if not is_xwall:
                            if facing < 0:
                                m.quad([(bxa, y_outer, za), (bxb, y_outer, za),
                                        (bxb, y_outer, zb), (bxa, y_outer, zb)], tile, X, Z)
                            else:
                                m.quad([(bxb, y_outer, za), (bxa, y_outer, za),
                                        (bxa, y_outer, zb), (bxb, y_outer, zb)], tile, X, Z)
                        else:
                            if facing > 0:
                                m.quad([(y_outer, bxa, za), (y_outer, bxb, za),
                                        (y_outer, bxb, zb), (y_outer, bxa, zb)], tile, Y, Z)
                            else:
                                m.quad([(y_outer, bxb, za), (y_outer, bxa, za),
                                        (y_outer, bxa, zb), (y_outer, bxb, zb)], tile, Y, Z)

        # inner face: plain plaster per floor (no per-block ashlar), CUT round the door and every window like the
        # outer face - one uncut sheet stood behind every opening: from inside, the door and the windows were a
        # plaster wall you could walk through but not see out of (2026-11-13)
        for fl in range(floors):
            z0_fl, z1_fl = fl * fH, (fl + 1) * fH
            tile = _plaster(rng)
            cuts = []  # (at, z lo, z hi, half width) of this floor's openings on this side
            for at, ofl, is_door in win_positions:
                if ofl != fl:
                    continue
                if is_door:
                    cuts.append((at, 0.0, door_h, door_w / 2))
                elif has_windows:
                    cuts.append((at, z0_fl + win_sill, z0_fl + win_sill + win_h, win_w / 2))
            levels = sorted({z0_fl, z1_fl} | {min(max(z, z0_fl), z1_fl) for c in cuts for z in (c[1], c[2])})
            for za, zb in zip(levels[:-1], levels[1:]):
                if zb - za < 1e-6:
                    continue
                spans = [(run_lo, run_hi)]
                for (at, oz0, oz1, ohalf) in cuts:
                    if za < oz1 - 1e-6 and zb > oz0 + 1e-6:
                        kept = []
                        for a_, b_ in spans:
                            lo_cut, hi_cut = at - ohalf, at + ohalf
                            if b_ <= lo_cut or a_ >= hi_cut:
                                kept.append((a_, b_))
                            else:
                                if a_ < lo_cut:
                                    kept.append((a_, lo_cut))
                                if b_ > hi_cut:
                                    kept.append((hi_cut, b_))
                        spans = kept
                for a_, b_ in spans:
                    if b_ - a_ < 1e-6:
                        continue
                    if not is_xwall:
                        if facing < 0:
                            m.quad([(b_, y_inner, za), (a_, y_inner, za),
                                    (a_, y_inner, zb), (b_, y_inner, zb)], tile, X, Z)
                        else:
                            m.quad([(a_, y_inner, za), (b_, y_inner, za),
                                    (b_, y_inner, zb), (a_, y_inner, zb)], tile, X, Z)
                    else:
                        if facing > 0:
                            m.quad([(y_inner, b_, za), (y_inner, a_, za),
                                    (y_inner, a_, zb), (y_inner, b_, zb)], tile, Y, Z)
                        else:
                            m.quad([(y_inner, a_, za), (y_inner, b_, za),
                                    (y_inner, b_, zb), (y_inner, a_, zb)], tile, Y, Z)

        # window and door openings
        for at, fl, is_door in win_positions:
            z0_fl = fl * fH
            if is_door:
                # pointed door arch
                depth_d = thick
                if not is_xwall:
                    _pointed_window_opening(m, rng, at, y_outer, depth_d,
                                            0, door_h - door_w / 2, door_w / 2, z_top,
                                            has_mullion=False)
                else:
                    # TODO: X-wall door (less common, skip for now)
                    pass
            elif has_windows:
                z_win_lo = z0_fl + win_sill
                z_win_hi = z_win_lo + win_h
                z_spring = z_win_lo + (win_h - win_w / 2)
                depth_w = thick
                if not is_xwall:
                    _pointed_window_opening(m, rng, at, y_outer, depth_w,
                                            z_win_lo, z_spring, win_w / 2, z_top,
                                            has_mullion=True)
                else:
                    # for X walls: window centre is at y_outer (the X value), runs along Y
                    # We need to rotate the opening 90 degrees
                    _pointed_window_opening(m, rng, at, y_outer, depth_w,
                                            z_win_lo, z_spring, win_w / 2, z_top,
                                            has_mullion=True)

        # string courses at every floor line
        for fl in range(1, floors + 1):
            z_sc = fl * fH
            sc_proj = 0.3
            sc_h = 0.4
            if not is_xwall:
                # projecting stone ledge
                m.quad([(run_lo, y_outer - sc_proj, z_sc),
                        (run_hi, y_outer - sc_proj, z_sc),
                        (run_hi, y_outer, z_sc),
                        (run_lo, y_outer, z_sc)],
                       _pick(rng, z_sc, z_top, 20, 35), X, Y)
                m.quad([(run_lo, y_outer - sc_proj, z_sc),
                        (run_hi, y_outer - sc_proj, z_sc),
                        (run_hi, y_outer - sc_proj, z_sc + sc_h),
                        (run_lo, y_outer - sc_proj, z_sc + sc_h)],
                       _pick(rng, z_sc, z_top, 20, 35), X, Z)
            else:
                m.quad([(y_outer + sc_proj * facing, run_lo, z_sc),
                        (y_outer + sc_proj * facing, run_hi, z_sc),
                        (y_outer, run_hi, z_sc),
                        (y_outer, run_lo, z_sc)],
                       _pick(rng, z_sc, z_top, 20, 35), Y, X)
                m.quad([(y_outer + sc_proj * facing, run_lo, z_sc),
                        (y_outer + sc_proj * facing, run_hi, z_sc),
                        (y_outer + sc_proj * facing, run_hi, z_sc + sc_h),
                        (y_outer + sc_proj * facing, run_lo, z_sc + sc_h)],
                       _pick(rng, z_sc, z_top, 20, 35), Y, Z)

        # plinth course (ground level, projecting 0.4)
        plinth_h = 1.8
        plinth_proj = 0.4
        if not is_xwall:
            m.quad([(run_lo, y_outer - plinth_proj, 0),
                    (run_hi, y_outer - plinth_proj, 0),
                    (run_hi, y_outer - plinth_proj, plinth_h),
                    (run_lo, y_outer - plinth_proj, plinth_h)],
                   _pick(rng, 0, z_top, 0, 8), X, Z)
            m.quad([(run_lo, y_outer - plinth_proj, plinth_h),
                    (run_hi, y_outer - plinth_proj, plinth_h),
                    (run_hi, y_outer, plinth_h),
                    (run_lo, y_outer, plinth_h)],
                   _pick(rng, 0, z_top, 0, 8), X, Y)

        # (corner quoins are NOT in this mesh - it stays within MAX_TRIS - but never stripped: the recipe's "quoins"
        # names a kind gothic_quoin strip (kit/world/quoins.py) the compiler stands at every corner of every storey)

    # --- Roof: steep gabled (crow-stepped) on S face, pitched ridge along Y
    # Wall top = total_h, gable peaks at total_h + gable_h on centre X (x=0)
    # Roof slopes from x = ±W/2 at z = total_h up to x = 0 at z = total_h + gable_h
    roof_base = total_h
    roof_peak = total_h + gable_h
    slate_tile = lambda: SLATE0 + rng.randrange(8)

    # Front and back gable walls (crow-stepped).
    # Each gable is ONE continuous wall rising from the front/back wall top (roof_base) to
    # roof_peak in gable_steps stacked tiers.  Step k spans the FULL remaining half-width
    # (narrowing each step going up) and sits on top of step k-1.  Nothing floats.
    # Layout (step 0 is widest, step gable_steps-1 is narrowest at the peak):
    #   half-width of step k = W/2 - k * step_w
    #   z range of step k    = roof_base + k*step_h  ..  roof_base + (k+1)*step_h
    for gy, gfacing in [(-yo, -1), (yo, 1)]:
        step_w = (W / 2) / gable_steps   # how much the gable narrows per step
        step_h = gable_h / gable_steps
        cope_proj = 0.3                   # coping overhang toward outside
        for step in range(gable_steps):
            hw = W / 2 - step * step_w    # half-width of this step block
            xlo, xhi = -hw, hw
            zlo = roof_base + step * step_h
            zhi = roof_base + (step + 1) * step_h
            tile = _pick(rng, zlo, z_top + gable_h)

            # Front face (facing outside, toward gy)
            if gfacing < 0:
                m.quad([(xlo, gy, zlo), (xhi, gy, zlo), (xhi, gy, zhi), (xlo, gy, zhi)], tile, X, Z)
            else:
                m.quad([(xhi, gy, zlo), (xlo, gy, zlo), (xlo, gy, zhi), (xhi, gy, zhi)], tile, X, Z)

            # Coping on top (overhangs outward by cope_proj)
            cope_tile = _pick(rng, zhi, z_top + gable_h, 20, 35)
            if gfacing < 0:
                m.quad([(xlo, gy - cope_proj, zhi), (xhi, gy - cope_proj, zhi),
                        (xhi, gy, zhi), (xlo, gy, zhi)],
                       cope_tile, X, Y)
                # top face of coping
                m.quad([(xlo, gy - cope_proj, zhi), (xhi, gy - cope_proj, zhi),
                        (xhi, gy - cope_proj, zhi + 0.15), (xlo, gy - cope_proj, zhi + 0.15)],
                       cope_tile, X, Z)
            else:
                m.quad([(xhi, gy + cope_proj, zhi), (xlo, gy + cope_proj, zhi),
                        (xlo, gy, zhi), (xhi, gy, zhi)],
                       cope_tile, X, Y)
                m.quad([(xhi, gy + cope_proj, zhi), (xlo, gy + cope_proj, zhi),
                        (xlo, gy + cope_proj, zhi + 0.15), (xhi, gy + cope_proj, zhi + 0.15)],
                       cope_tile, X, Z)

            # Left and right riser faces (exposed side of this step where it's wider than the one above)
            # Only needed when this step is wider than step above (all but top step)
            if step + 1 < gable_steps:
                hw_above = W / 2 - (step + 1) * step_w
                # Right riser: x from hw_above to hw, at y=gy, z=zhi (a thin exposed face)
                riser_tile = _pick(rng, zhi, z_top + gable_h)
                if gfacing < 0:
                    m.quad([(hw_above, gy, zhi), (hw, gy, zhi),
                            (hw, gy, zhi + step_h * 0.08), (hw_above, gy, zhi + step_h * 0.08)],
                           riser_tile, X, Z)
                    m.quad([(-hw, gy, zhi), (-hw_above, gy, zhi),
                            (-hw_above, gy, zhi + step_h * 0.08), (-hw, gy, zhi + step_h * 0.08)],
                           riser_tile, X, Z)
                else:
                    m.quad([(hw, gy, zhi), (hw_above, gy, zhi),
                            (hw_above, gy, zhi + step_h * 0.08), (hw, gy, zhi + step_h * 0.08)],
                           riser_tile, X, Z)
                    m.quad([(-hw_above, gy, zhi), (-hw, gy, zhi),
                            (-hw, gy, zhi + step_h * 0.08), (-hw_above, gy, zhi + step_h * 0.08)],
                           riser_tile, X, Z)

    # Roof slopes (slate): two faces, N and S slope (10 rows, max 8 slates each to stay within budget)
    n_slope_rows = 10
    for xsign in [-1, 1]:
        for row in range(n_slope_rows):
            t0, t1 = row / n_slope_rows, (row + 1) / n_slope_rows
            x0s = xsign * W / 2 * (1 - t0)
            x1s = xsign * W / 2 * (1 - t1)
            z0s = roof_base + gable_h * t0
            z1s = roof_base + gable_h * t1
            # Span Y from -yo to +yo (depth of roof), max 8 slates per row
            n_slates = min(8, max(4, int((D + 0.1) / 2.8)))
            for ks in range(n_slates):
                y0s = -yo + ks * (D + 0.1) / n_slates
                y1s = -yo + (ks + 1.6) * (D + 0.1) / n_slates  # overlap
                y1s = min(yo, y1s)
                tile = slate_tile()
                if xsign > 0:
                    m.quad([(x1s, y0s, z1s), (x1s, y1s, z1s),
                            (x0s, y1s, z0s), (x0s, y0s, z0s)], tile, Y, Z)
                else:
                    m.quad([(x0s, y0s, z0s), (x0s, y1s, z0s),
                            (x1s, y1s, z1s), (x1s, y0s, z1s)], tile, Y, Z)

    # Chimney (back corner, rises from roof_base to roof_base + gable_h + 4)
    if has_chimney:
        chx, chyr = W / 2 - 2.5, yo - 2.5
        chw, chd = 2.0, 2.0
        ch_base = roof_base
        ch_top = roof_peak + 4
        # four faces of chimney stack
        for face_y, run_x0, run_x1, face_fac in [
            (-chyr, chx - chw / 2, chx + chw / 2, -1),
            (chyr, chx - chw / 2, chx + chw / 2, 1),
        ]:
            zs_ch = _courses(ch_base, ch_top)
            for za, zb in zip(zs_ch[:-1], zs_ch[1:]):
                tile = _pick(rng, za, ch_top)
                if face_fac < 0:
                    m.quad([(run_x0, face_y, za), (run_x1, face_y, za),
                            (run_x1, face_y, zb), (run_x0, face_y, zb)], tile, X, Z)
                else:
                    m.quad([(run_x1, face_y, za), (run_x0, face_y, za),
                            (run_x0, face_y, zb), (run_x1, face_y, zb)], tile, X, Z)
        # chimney cap
        m.quad([(chx - chw / 2 - 0.1, -chyr - 0.1, ch_top),
                (chx + chw / 2 + 0.1, -chyr - 0.1, ch_top),
                (chx + chw / 2 + 0.1, chyr + 0.1, ch_top),
                (chx - chw / 2 - 0.1, chyr + 0.1, ch_top)],
               PAVE0 + rng.randrange(4), X, Y)

    # Floor slabs (simple horizontal quads at each floor)
    for fl in range(1, floors):
        z_fl = fl * fH
        m.quad([(-W / 2 + thick, -D / 2 + thick, z_fl),
                (W / 2 - thick, -D / 2 + thick, z_fl),
                (W / 2 - thick, D / 2 - thick, z_fl),
                (-W / 2 + thick, D / 2 - thick, z_fl)],
               PAVE0 + rng.randrange(4), X, Y)

    return m


# ---------------------------------------------------------------------------
# gothic_bay — cathedral flank module
# ---------------------------------------------------------------------------
def _bay_mesh(rec):
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))

    L = float(rec.get("length", 24))
    H = float(rec.get("height", 60))
    T = float(rec.get("thickness", 6))

    win_cfg = rec.get("window", {})
    win_w = float(win_cfg.get("width", 7))
    win_h = float(win_cfg.get("height", 32))
    win_sill_z = float(win_cfg.get("sill", 12))

    z_top = H
    # Outer face at Y=0 facing -Y; body goes from Y=0 to Y=T
    # Runs from X=0 to X=L

    # Outer face: ashlar wall with lancet window centred at X=L/2
    cx = L / 2
    win_half = win_w / 2
    win_spring = win_sill_z + (win_h - win_half * 2)

    # Build outer wall (Y=0, facing -Y) in courses, leaving window opening
    zs_all = _courses(0, H)
    for za, zb in zip(zs_all[:-1], zs_all[1:]):
        # intervals: skip window
        in_win = za < (win_sill_z + win_h + 2) and zb > win_sill_z and za >= win_sill_z
        if za < win_sill_z and zb > win_sill_z:
            # sill row: solid
            pass
        intervals = [(0, L)]
        if za >= win_sill_z:
            lo_cut, hi_cut = cx - win_half - 0.1, cx + win_half + 0.1
            arch_crown = win_spring + win_half * 1.3  # approx
            if za < arch_crown:
                intervals = [(0, lo_cut), (hi_cut, L)]
                for a_, b_ in [(0, lo_cut), (hi_cut, L)]:
                    if b_ - a_ < 0.3:
                        continue
                    brng = random.Random(seed * 23 + int(za * 10))
                    bxs = [a_]
                    while bxs[-1] < b_ - 0.4:
                        bxs.append(min(b_, bxs[-1] + brng.uniform(1.5, 3.0)))
                    bxs[-1] = b_
                    for bxa, bxb in zip(bxs[:-1], bxs[1:]):
                        if bxb - bxa < 0.3:
                            continue
                        m.quad([(bxa, 0, za), (bxb, 0, za), (bxb, 0, zb), (bxa, 0, zb)],
                               _pick(rng, za, z_top), X, Z)
                continue
        brng = random.Random(seed * 23 + int(za * 10))
        bxs = [0.0]
        while bxs[-1] < L - 0.4:
            bxs.append(min(L, bxs[-1] + brng.uniform(1.5, 3.0)))
        bxs[-1] = L
        for bxa, bxb in zip(bxs[:-1], bxs[1:]):
            if bxb - bxa < 0.3:
                continue
            m.quad([(bxa, 0, za), (bxb, 0, za), (bxb, 0, zb), (bxa, 0, zb)],
                   _pick(rng, za, z_top), X, Z)

    # Window opening (lancet with tracery)
    _pointed_window_opening(m, rng, cx, 0, T, win_sill_z, win_spring, win_half, z_top,
                            has_mullion=True, has_tracery=True)

    # Buttress at X=0, projecting -Y (depth 6, width 4, two weathering steps, then pinnacle)
    butt_proj = 6.0
    butt_w = 4.0
    butt_base_z = 0
    butt_top_z = H * 0.75  # buttress runs up to 3/4 height
    # Main buttress body (wider at base, two steps)
    for step, (xlo, xhi, ylo, yhi, zlo, zhi) in enumerate([
        (0, butt_w, -butt_proj, 0, 0, H * 0.3),
        (0, butt_w, -butt_proj * 0.65, 0, H * 0.3, H * 0.6),
        (0, butt_w, -butt_proj * 0.3, 0, H * 0.6, butt_top_z),
    ]):
        tile = _pick(rng, zlo, z_top)
        # front face
        m.quad([(xlo, ylo, zlo), (xhi, ylo, zlo), (xhi, ylo, zhi), (xlo, ylo, zhi)], tile, X, Z)
        # top weathering slope
        if step < 2:
            next_ylo = [-butt_proj * 0.65, -butt_proj * 0.3][step]
            m.quad([(xlo, ylo, zhi), (xhi, ylo, zhi), (xhi, next_ylo, zhi + 0.4), (xlo, next_ylo, zhi + 0.4)],
                   PAVE0 + rng.randrange(4), X, Y)
        # side faces
        m.quad([(xlo, ylo, zlo), (xlo, 0, zlo), (xlo, 0, zhi), (xlo, ylo, zhi)],
               _pick(rng, zlo, z_top), Y, Z)
        m.quad([(xhi, 0, zlo), (xhi, ylo, zlo), (xhi, ylo, zhi), (xhi, 0, zhi)],
               _pick(rng, zlo, z_top), Y, Z)

    # Pinnacle above buttress
    pin_x, pin_y = butt_w / 2, -butt_proj * 0.3 / 2
    pin_sz = 1.5  # half-width of pinnacle square shaft
    pin_base = butt_top_z
    pin_shaft_top = butt_top_z + 8
    pin_cap_top = pin_shaft_top + 4
    # Shaft (square)
    for px0, px1, py0, py1, pfacing in [
        (pin_x - pin_sz, pin_x + pin_sz, pin_y - 0.05, pin_y - 0.05, -1),
        (pin_x - pin_sz, pin_x + pin_sz, pin_y + pin_sz * 2, pin_y + pin_sz * 2, 1),
    ]:
        zs_pin = _courses(pin_base, pin_shaft_top, 1.0)
        for za, zb in zip(zs_pin[:-1], zs_pin[1:]):
            tile = _pick(rng, za, pin_cap_top, 15, 35)
            if pfacing < 0:
                m.quad([(px0, py0, za), (px1, py0, za), (px1, py0, zb), (px0, py0, zb)], tile, X, Z)
            else:
                m.quad([(px1, py1, za), (px0, py1, za), (px0, py1, zb), (px1, py1, zb)], tile, X, Z)
    # Pyramid cap
    cap_cx, cap_cy = pin_x, pin_y + pin_sz
    for ca0, ca1 in [(0, math.pi / 2), (math.pi / 2, math.pi), (math.pi, 3 * math.pi / 2), (3 * math.pi / 2, 2 * math.pi)]:
        x0c = cap_cx + pin_sz * math.cos(ca0 + math.pi / 4 + math.pi / 4)
        y0c = cap_cy + pin_sz * math.sin(ca0 + math.pi / 4 + math.pi / 4)
        x1c = cap_cx + pin_sz * math.cos(ca1 + math.pi / 4 + math.pi / 4)
        y1c = cap_cy + pin_sz * math.sin(ca1 + math.pi / 4 + math.pi / 4)
        m.quad([(x0c, y0c, pin_shaft_top), (x1c, y1c, pin_shaft_top),
                (cap_cx, cap_cy, pin_cap_top), (cap_cx, cap_cy, pin_cap_top)],
               slate_t := SLATE0 + rng.randrange(8), X, Z)

    # Parapet (pierced coped)
    par_proj = 0.3
    par_h = 2.5
    par_top = H + par_h
    # Front face of parapet
    m.quad([(0, -par_proj, H), (L, -par_proj, H), (L, -par_proj, par_top), (0, -par_proj, par_top)],
           _pick(rng, H, par_top, 20, 40), X, Z)
    # Parapet coping
    m.quad([(0, -par_proj - 0.1, par_top), (L, -par_proj - 0.1, par_top),
            (L, T + 0.1, par_top), (0, T + 0.1, par_top)],
           PAVE0 + rng.randrange(4), X, Y)
    # Plinth
    m.quad([(0, -0.5, 0), (L, -0.5, 0), (L, -0.5, 1.6), (0, -0.5, 1.6)],
           _pick(rng, 0, z_top, 0, 8), X, Z)
    m.quad([(0, -0.5, 1.6), (L, -0.5, 1.6), (L, 0, 1.6), (0, 0, 1.6)],
           PAVE0 + rng.randrange(4), X, Y)

    # Back wall (simple ashlar)
    _ashlar_panel(m, rng, 0, L, T, 0, H, z_top, facing=1)

    # Side walls (aisle sides)
    _ashlar_panel(m, rng, 0, T, 0, 0, H, z_top, facing='x-')
    _ashlar_panel(m, rng, 0, T, L, 0, H, z_top, facing='x+')

    # Ceiling (the flat top inside the bay)
    m.quad([(0 + 0.1, 0 + 0.1, H), (L - 0.1, 0 + 0.1, H),
            (L - 0.1, T - 0.1, H), (0 + 0.1, T - 0.1, H)],
           MORTAR0 + rng.randrange(4), X, Y)

    return m


# ---------------------------------------------------------------------------
# gothic_lamppost
# ---------------------------------------------------------------------------
def _lamppost_mesh(rec):
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))

    H = float(rec.get("height", 11))
    n_sides = 8  # octagonal post

    # Stepped base (3 squares, reducing in radius)
    for step_i, (sz0, sz1, bsz) in enumerate([(0, 0.5, 1.2), (0.5, 1.0, 1.0), (1.0, 1.4, 0.8)]):
        for k in range(4):
            ang = k * math.pi / 2
            ang2 = (k + 1) * math.pi / 2
            # simplified square base panels
            px0, pz0 = bsz * math.cos(ang), bsz * math.sin(ang)
            px1, pz1 = bsz * math.cos(ang2), bsz * math.sin(ang2)
            tile = IRON0 + rng.randrange(2)
            m.quad([(px0, pz0, sz0), (px1, pz1, sz0), (px1, pz1, sz1), (px0, pz0, sz1)], tile, X, Z)

    # Octagonal fluted post
    post_base = 1.4
    post_top = H - 2.5
    post_r = 0.22
    n_flute = n_sides
    for k in range(n_flute):
        ang = 2 * math.pi * k / n_flute
        ang2 = 2 * math.pi * (k + 1) / n_flute
        a_mid = (ang + ang2) / 2
        px0, py0 = post_r * math.cos(ang), post_r * math.sin(ang)
        px1, py1 = post_r * math.cos(ang2), post_r * math.sin(ang2)
        # flute (slight inset at mid)
        pr = post_r * 0.92
        px_m, py_m = pr * math.cos(a_mid), pr * math.sin(a_mid)
        m.quad([(px0, py0, post_base), (px_m, py_m, post_base),
                (px_m, py_m, post_top), (px0, py0, post_top)], IRON0 + rng.randrange(2), X, Z)
        m.quad([(px_m, py_m, post_base), (px1, py1, post_base),
                (px1, py1, post_top), (px_m, py_m, post_top)], IRON0 + rng.randrange(2), X, Z)

    # Collar ring
    collar_z = post_top
    collar_r = post_r + 0.15
    collar_h = 0.3
    for k in range(n_flute):
        ang = 2 * math.pi * k / n_flute
        ang2 = 2 * math.pi * (k + 1) / n_flute
        px0, py0 = collar_r * math.cos(ang), collar_r * math.sin(ang)
        px1, py1 = collar_r * math.cos(ang2), collar_r * math.sin(ang2)
        m.quad([(px0, py0, collar_z), (px1, py1, collar_z),
                (px1, py1, collar_z + collar_h), (px0, py0, collar_z + collar_h)],
               IRON0 + rng.randrange(2), X, Z)

    # 4-pane lantern box
    lan_base = post_top + collar_h
    lan_top = H - 0.4
    lan_hw = 0.65  # half-width of lantern
    lantern_centre_z = (lan_base + lan_top) / 2

    for k in range(4):
        ang = k * math.pi / 2 + math.pi / 4
        ang2 = ang + math.pi / 2
        px0, py0 = lan_hw * math.cos(ang), lan_hw * math.sin(ang)
        px1, py1 = lan_hw * math.cos(ang2), lan_hw * math.sin(ang2)
        # frame edges (iron)
        m.quad([(px0, py0, lan_base), (px1, py1, lan_base),
                (px1, py1, lan_top), (px0, py0, lan_top)], IRON0, X, Z)
        # glass pane (amber, slightly inset)
        gf = 0.9
        gx0, gy0 = px0 * gf, py0 * gf
        gx1, gy1 = px1 * gf, py1 * gf
        m.quad([(gx0, gy0, lan_base + 0.15), (gx1, gy1, lan_base + 0.15),
                (gx1, gy1, lan_top - 0.1), (gx0, gy0, lan_top - 0.1)],
               GLASS0 + rng.randrange(2), X, Z)

    # Pointed cap with finial
    cap_base = lan_top
    cap_top = H
    for k in range(4):
        ang = k * math.pi / 2 + math.pi / 4
        ang2 = ang + math.pi / 2
        px0, py0 = lan_hw * math.cos(ang), lan_hw * math.sin(ang)
        px1, py1 = lan_hw * math.cos(ang2), lan_hw * math.sin(ang2)
        m.quad([(px0, py0, cap_base), (px1, py1, cap_base), (0, 0, cap_top), (0, 0, cap_top)],
               IRON0 + rng.randrange(2), X, Z)

    # finial spike
    fin_r = 0.08
    for k in range(4):
        ang = k * math.pi / 2
        ang2 = (k + 1) * math.pi / 2
        px0, py0 = fin_r * math.cos(ang), fin_r * math.sin(ang)
        px1, py1 = fin_r * math.cos(ang2), fin_r * math.sin(ang2)
        m.quad([(px0, py0, cap_top), (px1, py1, cap_top), (0, 0, cap_top + 0.6), (0, 0, cap_top + 0.6)],
               IRON0, X, Z)

    return m, lantern_centre_z


# ---------------------------------------------------------------------------
# gothic_well
# ---------------------------------------------------------------------------
def _quoin_mesh(rec):
    """one storey of one corner's quoins (kit/world/quoins.py; the corner's foot at the origin, the building in +X +Y)"""
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))
    h = float(rec.get("height", 14))
    faces = quoins.strip(h, float(rec.get("long", quoins.LONG)), float(rec.get("short", quoins.SHORT)),
                         float(rec.get("proj", quoins.PROJ)), float(rec.get("course", quoins.COURSE)))
    tiles = {}
    for pts, u, v, role in faces:
        if role == "mortar":
            tile = _mortar(rng)
        else:  # (one tile a stone: its faces read as one block; dressed stone, lighter than the wall)
            if role not in tiles:
                tiles[role] = _pick(rng, pts[0][2], h, 20, 35)
            tile = tiles[role]
        m.quad(pts, tile, np.array(u), np.array(v))
    return m


def _well_mesh(rec):
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))

    n_sides = 8
    curb_r = float(rec.get("radius", 3))
    curb_h = float(rec.get("height", 3.2))
    arch_h = 8.0

    # Octagonal stone curb
    for k in range(n_sides):
        ang = 2 * math.pi * k / n_sides + math.pi / n_sides
        ang2 = 2 * math.pi * (k + 1) / n_sides + math.pi / n_sides
        # outer face
        px0, py0 = curb_r * math.cos(ang), curb_r * math.sin(ang)
        px1, py1 = curb_r * math.cos(ang2), curb_r * math.sin(ang2)
        t = curb_r * 0.85  # inner radius
        ix0, iy0 = t * math.cos(ang), t * math.sin(ang)
        ix1, iy1 = t * math.cos(ang2), t * math.sin(ang2)
        # courses of outer face
        zs_c = _courses(0, curb_h, 1.0)
        for za, zb in zip(zs_c[:-1], zs_c[1:]):
            tile = _pick(rng, za, curb_h + 1, 10, 30)
            # outer face
            mid_tang = np.array([-math.sin((ang + ang2) / 2), math.cos((ang + ang2) / 2), 0])
            m.quad([(px0, py0, za), (px1, py1, za), (px1, py1, zb), (px0, py0, zb)], tile, X, Z)
        # chamfered coping on top
        cw = 0.15
        m.quad([(px0, py0, curb_h), (px1, py1, curb_h),
                (ix1, iy1, curb_h + cw), (ix0, iy0, curb_h + cw)],
               PAVE0 + rng.randrange(4), X, Y)
        m.quad([(ix0, iy0, curb_h + cw), (ix1, iy1, curb_h + cw),
                (ix1, iy1, curb_h + cw + 0.1), (ix0, iy0, curb_h + cw + 0.1)],
               _pick(rng, curb_h, curb_h + 1, 20, 35), X, Z)

    # Wrought iron arch over the well (two posts + arched crossbeam)
    arch_post_r = 0.18
    arch_x = curb_r * 0.7
    for sx in [-1, 1]:
        # Post
        post_x = sx * arch_x
        for ang_p in range(4):
            a0 = ang_p * math.pi / 2
            a1 = (ang_p + 1) * math.pi / 2
            px0, py0 = post_x + arch_post_r * math.cos(a0), arch_post_r * math.sin(a0)
            px1, py1 = post_x + arch_post_r * math.cos(a1), arch_post_r * math.sin(a1)
            m.quad([(px0, py0, 0), (px1, py1, 0), (px1, py1, arch_h), (px0, py0, arch_h)],
                   IRON0 + rng.randrange(2), X, Z)

    # Arch beam (semi-circular, in X-Z plane).
    # Semicircle: centre (0, 0, arch_h), radius arch_x.
    # a=0 → left post top (-arch_x, 0, arch_h); a=π → right post top (+arch_x, 0, arch_h).
    n_arch = 12
    bw = 0.15  # beam half-width in Y
    for k in range(n_arch):
        a0 = math.pi * k / n_arch
        a1 = math.pi * (k + 1) / n_arch
        ax0 = -arch_x * math.cos(a0)   # -arch_x·cos(a) sweeps -arch_x → +arch_x
        az0 = arch_h + arch_x * math.sin(a0)
        ax1 = -arch_x * math.cos(a1)
        az1 = arch_h + arch_x * math.sin(a1)
        m.quad([(ax0, -bw, az0), (ax1, -bw, az1), (ax1, bw, az1), (ax0, bw, az0)],
               IRON0 + rng.randrange(2), X, Z)

    # Pulley: short rod from arch crown, then a ring wheel.
    pul_crown_z = arch_h + arch_x     # arch crown
    rod_len = 0.6
    pul_z = pul_crown_z - rod_len     # pulley wheel centre
    pul_r = 0.32
    # hanging rod (vertical quad pair forming a thin bar)
    for dy in [-bw * 0.6, bw * 0.6]:
        m.quad([(- bw * 0.4, dy, pul_crown_z), (bw * 0.4, dy, pul_crown_z),
                (bw * 0.4, dy, pul_z + pul_r), (- bw * 0.4, dy, pul_z + pul_r)],
               IRON0, X, Z)
    # pulley ring (6 short segments, in X-Z plane at y=0)
    for k in range(6):
        a0, a1 = 2 * math.pi * k / 6, 2 * math.pi * (k + 1) / 6
        px0, pz0 = pul_r * math.cos(a0), pul_z + pul_r * math.sin(a0)
        px1, pz1 = pul_r * math.cos(a1), pul_z + pul_r * math.sin(a1)
        m.quad([(px0, -bw * 0.6, pz0), (px1, -bw * 0.6, pz1),
                (px1,  bw * 0.6, pz1), (px0,  bw * 0.6, pz0)],
               IRON0 + rng.randrange(2), X, Z)

    return m


# ---------------------------------------------------------------------------
# gothic_spire
# ---------------------------------------------------------------------------
def _spire_mesh(rec):
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))

    base_r = float(rec.get("radius", 6))
    H = float(rec.get("height", 60))
    n_sides = 8

    # Octagonal base ring (stone)
    base_h = 3.5
    for k in range(n_sides):
        ang = 2 * math.pi * k / n_sides
        ang2 = 2 * math.pi * (k + 1) / n_sides
        r_out = base_r + 0.6
        px0, py0 = r_out * math.cos(ang), r_out * math.sin(ang)
        px1, py1 = r_out * math.cos(ang2), r_out * math.sin(ang2)
        zs_b = _courses(0, base_h, 1.0)
        for za, zb in zip(zs_b[:-1], zs_b[1:]):
            m.quad([(px0, py0, za), (px1, py1, za), (px1, py1, zb), (px0, py0, zb)],
                   _pick(rng, za, H), X, Z)

    # Needle spire (tapering octagonal shaft, slated faces)
    n_rows = 36
    for row in range(n_rows):
        t0, t1 = row / n_rows, (row + 1) / n_rows
        r0 = base_r * (1 - t0)
        r1 = base_r * (1 - t1)
        z0 = base_h + H * t0
        z1 = base_h + H * t1
        for k in range(n_sides):
            ang = 2 * math.pi * k / n_sides + math.pi / n_sides
            ang2 = 2 * math.pi * (k + 1) / n_sides + math.pi / n_sides
            px0, py0 = r0 * math.cos(ang), r0 * math.sin(ang)
            px1, py1 = r0 * math.cos(ang2), r0 * math.sin(ang2)
            px2, py2 = r1 * math.cos(ang2), r1 * math.sin(ang2)
            px3, py3 = r1 * math.cos(ang), r1 * math.sin(ang)
            mid_ang = (ang + ang2) / 2
            tile = SLATE0 + rng.randrange(8)
            m.quad([(px0, py0, z0), (px1, py1, z0), (px2, py2, z1), (px3, py3, z1)], tile, X, Z)
            # stone ribs between faces (edge tiles)
            m.quad([(r0 * math.cos(ang) * 1.03, r0 * math.sin(ang) * 1.03, z0),
                    (r1 * math.cos(ang) * 1.03, r1 * math.sin(ang) * 1.03, z1),
                    (r1 * math.cos(ang) * 1.03 + 0.08, r1 * math.sin(ang) * 1.03 + 0.08, z1),
                    (r0 * math.cos(ang) * 1.03 + 0.08, r0 * math.sin(ang) * 1.03 + 0.08, z0)],
                   _edge(rng), X, Z)

    # 4 small gabled lucarnes near the base of the spire
    for k in range(4):
        luc_ang = 2 * math.pi * k / 4
        luc_r = base_r * 0.82
        luc_cx = luc_r * math.cos(luc_ang)
        luc_cy = luc_r * math.sin(luc_ang)
        luc_z0 = base_h + H * 0.08
        luc_z1 = luc_z0 + 5
        luc_w = 2.0
        # small gable (a mini pointed arch face)
        tangx, tangy = -math.sin(luc_ang), math.cos(luc_ang)
        for side_s in [-1, 1]:
            # side walls of lucarne
            m.quad([(luc_cx - luc_w / 2 * tangx, luc_cy - luc_w / 2 * tangy, luc_z0),
                    (luc_cx + luc_w / 2 * tangx, luc_cy + luc_w / 2 * tangy, luc_z0),
                    (luc_cx + luc_w / 2 * tangx, luc_cy + luc_w / 2 * tangy, luc_z1),
                    (luc_cx - luc_w / 2 * tangx, luc_cy - luc_w / 2 * tangy, luc_z1)],
                   SLATE0 + rng.randrange(8), X, Z)

    # Crockets (small ribs / stone bumps up the edges — cheap: just small stone quads)
    n_crockets = 8
    for k in range(n_sides):
        ang = 2 * math.pi * k / n_sides
        for cr in range(n_crockets):
            t = cr / n_crockets
            cr_z = base_h + H * t
            cr_r = base_r * (1 - t) + 0.2
            cr_x = cr_r * math.cos(ang)
            cr_y = cr_r * math.sin(ang)
            cr_sz = 0.3 * (1 - t * 0.5)
            m.quad([(cr_x - cr_sz, cr_y, cr_z), (cr_x + cr_sz, cr_y, cr_z),
                    (cr_x + cr_sz, cr_y, cr_z + cr_sz * 2), (cr_x - cr_sz, cr_y, cr_z + cr_sz * 2)],
                   _pick(rng, cr_z, H, 20, 40), X, Z)

    # Finial at peak
    fin_r = 0.4
    fin_z = base_h + H
    fin_top = fin_z + 2.5
    for k in range(6):
        a0, a1 = 2 * math.pi * k / 6, 2 * math.pi * (k + 1) / 6
        m.quad([(fin_r * math.cos(a0), fin_r * math.sin(a0), fin_z),
                (fin_r * math.cos(a1), fin_r * math.sin(a1), fin_z),
                (0, 0, fin_top), (0, 0, fin_top)],
               SLATE0 + rng.randrange(8), X, Z)

    return m


# ---------------------------------------------------------------------------
# gothic_turret (stair turret)
# ---------------------------------------------------------------------------
def _turret_mesh(rec):
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))

    n_sides = 8
    r = float(rec.get("radius", 5.5))
    H = float(rec.get("height", 60))
    n_slits = int(rec.get("slits", 6))
    roof_h = float(rec.get("roofHeight", 16))

    # Spiral slit positions
    slit_positions = []
    for k in range(n_slits):
        slit_ang = 2 * math.pi * k / n_slits + rng.uniform(-0.1, 0.1)
        slit_z = H * (k + 0.5) / n_slits
        slit_positions.append((slit_ang, slit_z))

    slit_w = 0.4
    slit_h = 2.5

    def in_slit(ang, z):
        for sa, sz in slit_positions:
            da = abs(((ang - sa + math.pi) % (2 * math.pi)) - math.pi)
            dz = abs(z - sz)
            if da < (slit_w / (2 * r)) + 0.1 and dz < slit_h / 2 + 0.4:
                return True
        return False

    # Octagonal shaft (stone ashlar, curved)
    n_rows = 40
    for row in range(n_rows):
        t0, t1 = row / n_rows, (row + 1) / n_rows
        z0 = H * t0
        z1 = H * t1
        for k in range(n_sides):
            ang = 2 * math.pi * k / n_sides + math.pi / n_sides
            ang2 = 2 * math.pi * (k + 1) / n_sides + math.pi / n_sides
            ang_mid = (ang + ang2) / 2
            if in_slit(ang_mid, (z0 + z1) / 2):
                # slit: skip block, add slit reveal
                px_mid_o = (r + 0.05) * math.cos(ang_mid)
                py_mid_o = (r + 0.05) * math.sin(ang_mid)
                px_mid_i = (r - 0.8) * math.cos(ang_mid)
                py_mid_i = (r - 0.8) * math.sin(ang_mid)
                m.quad([(px_mid_i, py_mid_i, z0 + 0.2), (px_mid_i, py_mid_i, z1 - 0.2),
                        (px_mid_o, py_mid_o, z1 - 0.2), (px_mid_o, py_mid_o, z0 + 0.2)],
                       MORTAR0 + rng.randrange(4), X, Z)
                continue
            px0, py0 = r * math.cos(ang), r * math.sin(ang)
            px1, py1 = r * math.cos(ang2), r * math.sin(ang2)
            tile = _pick(rng, z0, H)
            m.quad([(px0, py0, z0), (px1, py1, z0), (px1, py1, z1), (px0, py0, z1)], tile, X, Z)

    # Corbelled parapet ring
    para_r = r + 0.8
    para_h = 2.5
    para_z = H
    n_par = n_sides * 2
    for k in range(n_par):
        ang = 2 * math.pi * k / n_par
        ang2 = 2 * math.pi * (k + 1) / n_par
        px0, py0 = para_r * math.cos(ang), para_r * math.sin(ang)
        px1, py1 = para_r * math.cos(ang2), para_r * math.sin(ang2)
        tile = _pick(rng, para_z, para_z + para_h, 20, 40)
        m.quad([(px0, py0, para_z), (px1, py1, para_z),
                (px1, py1, para_z + para_h), (px0, py0, para_z + para_h)], tile, X, Z)

    # Corbel transition
    for k in range(n_par):
        ang = 2 * math.pi * k / n_par
        ang2 = 2 * math.pi * (k + 1) / n_par
        rpx0, rpy0 = r * math.cos(ang), r * math.sin(ang)
        rpx1, rpy1 = r * math.cos(ang2), r * math.sin(ang2)
        px0, py0 = para_r * math.cos(ang), para_r * math.sin(ang)
        px1, py1 = para_r * math.cos(ang2), para_r * math.sin(ang2)
        m.quad([(rpx0, rpy0, para_z - 0.6), (rpx1, rpy1, para_z - 0.6),
                (px1, py1, para_z), (px0, py0, para_z)],
               _edge(rng), X, Z)

    # Conical slate roof
    n_slate_rows = 18
    for row in range(n_slate_rows):
        t0, t1 = row / n_slate_rows, (row + 1) / n_slate_rows
        rr0 = para_r * (1 - t0)
        rr1 = para_r * (1 - t1)
        z0 = para_z + para_h + roof_h * t0
        z1 = para_z + para_h + roof_h * t1
        n_sl = max(6, int(2 * math.pi * rr0 / 1.1))
        for k in range(n_sl):
            ang = 2 * math.pi * k / n_sl
            ang2 = 2 * math.pi * (k + 1) / n_sl * 1.02
            px0, py0 = rr0 * math.cos(ang), rr0 * math.sin(ang)
            px1, py1 = rr0 * math.cos(ang2), rr0 * math.sin(ang2)
            px2, py2 = rr1 * math.cos(ang2), rr1 * math.sin(ang2)
            px3, py3 = rr1 * math.cos(ang), rr1 * math.sin(ang)
            tile = SLATE0 + rng.randrange(8)
            m.quad([(px0, py0, z0), (px1, py1, z0), (px2, py2, z1), (px3, py3, z1)], tile, X, Z)

    # Finial
    fin_z = para_z + para_h + roof_h
    fin_r = 0.5
    fin_top = fin_z + 2.0
    for k in range(6):
        a0, a1 = 2 * math.pi * k / 6, 2 * math.pi * (k + 1) / 6
        m.quad([(fin_r * math.cos(a0), fin_r * math.sin(a0), fin_z),
                (fin_r * math.cos(a1), fin_r * math.sin(a1), fin_z),
                (0, 0, fin_top), (0, 0, fin_top)],
               _pick(rng, fin_z, fin_top, 20, 40), X, Z)

    return m


# ---------------------------------------------------------------------------
# _to_object: convert Mesh -> Blender object (same as castle_blender._to_object)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# gothic_module - ONE PIECE OF A FACADE (kit/lib/worldfacade.luau: a house front split into storeys, each storey's
# wall into its openings and the plain runs between). The compiler places each module with its own origin - the
# foot of its middle, on the wall's centre line - on the wall, its front (-Y here, +Z in Roblox, as a skin's) to
# the street, STRETCHED to its place; so a module is modelled in its recipe's own box and nothing of it may
# depend on a neighbour:
#   wall     a plain run: coursed ashlar outside, plaster inside
#   window   the opening the building cuts (gap: width, height = sill + the window's own, sill): a pointed arch
#            with an arch moulding, a mullion and a transom; the wall under its sill and over its head
#   windowb  the same opening square-headed: a cross window under a label mould (a second look for a town)
#   door     the doorway (sill 0): a pointed arch, open - you walk through it
#   oriel    a window standing out of the wall on a corbel, under its own little roof
#   band     a string course along a storey's foot, proud of the wall
#   roof     a gable roof: its ridge along Y (Roblox Z), the gable to the front; slates in courses
#   chimney  a stack with a cap
# ---------------------------------------------------------------------------
def _module_mesh(rec):
    seed = int(rec.get("seed", 1))
    rng = random.Random(seed)
    m = Mesh(random.Random(seed + 1))
    module = rec.get("module")
    w, h, d = [float(v) for v in rec.get("size", [4, 14, 1.2])]
    gap = rec.get("gap") or {}

    def face(x0, x1, z0, z1, y, front, plaster=False):
        """a rectangle of the wall's outer (front) or inner face, coursed in blocks outside"""
        if x1 - x0 < 1e-6 or z1 - z0 < 1e-6:
            return
        if plaster:
            _quad_wall(m, x0, x1, y, z0, z1, _plaster(rng), facing=1)
            return
        for za, zb in zip(_courses(z0, z1, ch=2.0)[:-1], _courses(z0, z1, ch=2.0)[1:]):
            xs = [x0]
            while xs[-1] < x1 - 0.5:
                xs.append(min(x1, xs[-1] + rng.uniform(2.0, 4.0)))
            # (the last block ends on the face's edge; a face under half a stud wide is one block - it was none:
            # an oriel's piers were not there)
            if len(xs) == 1 or x1 - xs[-1] > 1e-6:
                xs.append(x1)
            for xa, xb in zip(xs[:-1], xs[1:]):
                if xb - xa > 1e-6:
                    _quad_wall(m, xa, xb, y, za, zb, _pick(rng, za, h), facing=-1 if front else 1)

    def box(x0, x1, y0, y1, z0, z1, tile, top=True, bottom=False, back=False):
        """a block: front (-Y), both sides and, as asked, its top / underside / back"""
        _quad_wall(m, x0, x1, y0, z0, z1, tile(), facing=-1)
        _quad_xwall(m, x0, y0, y1, z0, z1, tile(), facing=-1)
        _quad_xwall(m, x1, y0, y1, z0, z1, tile(), facing=1)
        if back:
            _quad_wall(m, x0, x1, y1, z0, z1, tile(), facing=1)
        if top:
            m.quad([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], tile(), X, Y)
        if bottom:
            m.quad([(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)], tile(), X, Y)

    stone = lambda: _pick(rng, h * 0.5, h)
    edge = lambda: _edge(rng)

    def toward(pts, tile, look, u=X, v=Z):
        """a face seen from the side `look` points to (Roblox draws ONE side of a face: a fresh reader found a
        window's head, an oriel's cheeks and its whole front drawn for the side nobody stands on)"""
        a, b, c = [np.array(q, float) for q in pts[:3]]
        if float(np.dot(np.cross(b - a, c - a), np.array(look, float))) < 0:
            pts = pts[::-1]
        m.quad(pts, tile, u, v)

    def both(pts, tile_a, tile_b, look, u=X, v=Z):
        """a thin thing seen from both sides: one face each way, a twentieth of a stud apart (two faces in ONE
        plane flicker in every viewer that draws both sides - the kit's own look does: the roofs came out patched)"""
        toward(pts, tile_a, look, u, v)
        size = math.sqrt(sum(c * c for c in look))
        off = [-c / size * 0.05 for c in look]
        toward([tuple(q[k] + off[k] for k in range(3)) for q in pts], tile_b, [-c for c in look], u, v)
    yf, yb = -d / 2, d / 2
    RISE = 1.3  # a lancet's head: this many half-spans over its springing

    def lancet(r, spring, n=6):
        """a pointed arch of half-span r from its springing: [(x, z)] from the left foot over the crown to the right.
        Each side is an arc centred on the springing line beyond the middle, so the two meet in a point."""
        k = (RISE * RISE - 1) / 2  # (the centre's distance past the middle, in half-spans)
        rc = r * (1 + k)
        top = math.atan2(RISE * r, r * k)  # (the angle of the crown seen from the right-hand centre)
        left = [(r * k - rc * math.cos(top * i / n), spring + rc * math.sin(top * i / n)) for i in range(n + 1)]
        left[-1] = (0.0, spring + RISE * r)
        return left + [(-x, z) for x, z in reversed(left[:-1])]

    def pointed(y0, y1, r, z0, z1, mullion, hood=True):
        """a pointed opening of half-span r through the wall from its front y0 to its back y1, its sill at z0 and
        its crown at z1: the soffit and jambs through the wall, the wall between the arch and the opening's square
        top (both faces), a sill, an arch moulding that stays inside the module, a mullion"""
        spring = z1 - RISE * r
        arch = lancet(r, spring)
        for (xa, za), (xb, zb) in zip(arch[:-1], arch[1:]):
            # the soffit (seen from below / inside the opening)
            m.quad([(xa, y0, za), (xa, y1, za), (xb, y1, zb), (xb, y0, zb)], edge(), X, Y)
            # the spandrel: front and back
            m.quad([(xa, y0, za), (xb, y0, zb), (xb, y0, z1), (xa, y0, z1)], stone(), X, Z)
            m.quad([(xb, y1, zb), (xa, y1, za), (xa, y1, z1), (xb, y1, z1)], _plaster(rng), X, Z)
        for sx in (-1, 1):
            _quad_xwall(m, sx * r, y0, y1, z0, spring, stone(), facing=-sx)
        if z0 > 0.01:
            m.quad([(-r, y0 - 0.12, z0), (r, y0 - 0.12, z0), (r, y1, z0), (-r, y1, z0)], PAVE0 + rng.randrange(4), X, Y)
        if hood:
            # an arch moulding: a roll of stone following the arch just inside its edge, a hand's breadth proud of
            # the wall (not a hood mould: it does not stand over the arch)
            inner = [(x * 0.86, spring + (z - spring) * 0.9) for x, z in arch]
            for (xa, za), (xb, zb), (ia, ja), (ib, jb) in zip(arch[:-1], arch[1:], inner[:-1], inner[1:]):
                m.quad([(ia, y0 - 0.18, ja), (ib, y0 - 0.18, jb), (xb, y0 - 0.18, zb), (xa, y0 - 0.18, za)], edge(), X, Z)
                m.quad([(ia, y0, ja), (ib, y0, jb), (ib, y0 - 0.18, jb), (ia, y0 - 0.18, ja)], edge(), X, Y)
                m.quad([(xb, y0, zb), (xa, y0, za), (xa, y0 - 0.18, za), (xb, y0 - 0.18, zb)], edge(), X, Y)
        if mullion:
            box(-0.12, 0.12, y0 + 0.05, y0 + 0.3, z0, spring + RISE * r * 0.55, edge, top=False, back=True)
            tz = z0 + (spring - z0) * 0.5
            box(-r, r, y0 + 0.05, y0 + 0.3, tz - 0.1, tz + 0.1, edge, top=True, bottom=True, back=True)

    if module == "wall":
        face(-w / 2, w / 2, 0, h, yf, True)
        face(-w / 2, w / 2, 0, h, yb, False, plaster=True)

    elif module in ("window", "windowb", "door", "oriel"):
        gw = float(gap.get("width", w))
        z0 = float(gap.get("sill", 0))
        z1 = float(gap.get("height", h * 0.6))  # (the opening's top, from the storey's foot)
        r = gw / 2
        t = d if module != "oriel" else float(rec.get("thickness", 1.2))
        if module == "oriel":
            yf, yb = -t / 2, t / 2  # (the wall's own faces: the oriel stands out in front of yf)
        # the wall under the sill and over the head, both faces
        for y, front in ((yf, True), (yb, False)):
            face(-w / 2, w / 2, 0, z0, y, front, plaster=not front)
            face(-w / 2, w / 2, z1, h, y, front, plaster=not front)
        if module == "windowb":
            # square-headed: jambs and soffit through the wall, a label mould over, a stone cross in the light
            for sx in (-1, 1):
                _quad_xwall(m, sx * r, yf, yb, z0, z1, stone(), facing=-sx)
            toward([(-r, yf, z1), (r, yf, z1), (r, yb, z1), (-r, yb, z1)], edge(), (0, 0, -1), X, Y)
            toward([(-r, yf - 0.12, z0), (r, yf - 0.12, z0), (r, yb, z0), (-r, yb, z0)],
                   PAVE0 + rng.randrange(4), (0, 0, 1), X, Y)
            lab = 0.3  # the label: a hood over the head with an end dropped down each jamb
            box(-r, r, yf - lab, yf, z1, z1 + 0.45, edge, top=True, bottom=True)
            for sx in (-1, 1):
                x0, x1 = (-r, -r + 0.35) if sx < 0 else (r - 0.35, r)
                box(x0, x1, yf - lab, yf, z1 - 1.2, z1, edge, top=False, bottom=True)
            mw = 0.14
            box(-mw, mw, yf + 0.05, yf + 0.3, z0, z1, edge, top=False, back=True)
            tz = z0 + (z1 - z0) * 0.62
            box(-r, r, yf + 0.05, yf + 0.3, tz - mw, tz + mw, edge, top=True, bottom=True, back=True)
        else:
            if module != "oriel":
                pointed(yf, yb, r, z0, z1, mullion=(module == "window"))
            else:
                # the wall's own opening behind the oriel: plain jambs and a flat head (you look out through the bay)
                for sx in (-1, 1):
                    _quad_xwall(m, sx * r, yf, yb, z0, z1, stone(), facing=-sx)
                toward([(-r, yf, z1), (r, yf, z1), (r, yb, z1), (-r, yb, z1)], edge(), (0, 0, -1), X, Y)
        if module == "oriel":
            # the bay: out to y = -d/2 ... its floor a little under the sill, its head a little over the opening
            out = -(float(rec["size"][2]) - t / 2)  # (its front face: the recipe's depth, measured from the back)
            b0, b1 = max(0.6, z0 - 0.6), min(h - 0.3, z1 + 0.5)
            # cheeks (stone outside, plaster inside), floor and ceiling (seen from the room and from the street)
            for sx in (-1, 1):
                _quad_xwall(m, sx * w / 2, out, yf, b0, b1, stone(), facing=sx)
                _quad_xwall(m, sx * (w / 2 - 0.25), out + 0.25, yf, b0, b1, _plaster(rng), facing=-sx)
            # (the floor is seen from the room only: under it stands the corbel)
            toward([(-w / 2, out, b0), (w / 2, out, b0), (w / 2, yf, b0), (-w / 2, yf, b0)], _plaster(rng), (0, 0, 1), X, Y)
            both([(-w / 2, yf, b1), (w / 2, yf, b1), (w / 2, out, b1), (-w / 2, out, b1)], _plaster(rng), edge(), (0, 0, -1), X, Y)
            # its front: a pointed light between two piers - stone to the street, plaster to the room
            fr = w / 2 - 0.45
            head = b1 - 0.4
            for x0, x1, za, zb in ((-w / 2, -fr, b0, b1), (fr, w / 2, b0, b1), (-fr, fr, b0, z0), (-fr, fr, head, b1)):
                face(x0, x1, za, zb, out, True)
                if x1 - x0 > 1e-6 and zb - za > 1e-6:
                    toward([(x0, out + 0.25, za), (x1, out + 0.25, za), (x1, out + 0.25, zb), (x0, out + 0.25, zb)],
                           _plaster(rng), (0, 1, 0))
            pointed(out, out + 0.25, fr, z0, head, mullion=True, hood=False)
            # the corbel under it (a slope back to the wall, closed at its sides) and the little roof over it
            c0 = max(0.0, b0 - 1.6)
            toward([(-w / 2, yf, c0), (w / 2, yf, c0), (w / 2, out, b0), (-w / 2, out, b0)], edge(), (0, -1, -1), X, Z)
            for sx in (-1, 1):
                toward([(sx * w / 2, yf, c0), (sx * w / 2, out, b0), (sx * w / 2, yf, b0)], edge(), (sx, 0, 0), Y, Z)
            r1 = min(h, b1 + 1.4)
            both([(-w / 2 - 0.15, out - 0.2, b1), (w / 2 + 0.15, out - 0.2, b1), (w / 2 + 0.15, yf, r1), (-w / 2 - 0.15, yf, r1)],
                 SLATE0 + rng.randrange(8), edge(), (0, -1, 1), X, Y)
            for sx in (-1, 1):
                toward([(sx * w / 2, out, b1), (sx * w / 2, yf, r1), (sx * w / 2, yf, b1)], stone(), (sx, 0, 0), Y, Z)

    elif module == "band":
        t = float(rec.get("thickness", 1.2))
        box(-w / 2, w / 2, -t / 2 - d, -t / 2, 0, h, lambda: _pick(rng, 0, 10, 20, 35), top=True, bottom=True)

    elif module == "roof":
        # ridge along Y at z = h; eaves at x = +-w/2, z = 0; slates in courses up each slope
        courses = 7
        for sx in (-1, 1):
            for k in range(courses):
                xa, xb = sx * w / 2 * (1 - k / courses), sx * w / 2 * (1 - (k + 1) / courses)
                za, zb = h * k / courses, h * (k + 1) / courses
                ys = [-d / 2]
                while ys[-1] < d / 2 - 0.5:
                    ys.append(min(d / 2, ys[-1] + rng.uniform(3.0, 5.0)))
                ys[-1] = d / 2
                for ya, yb2 in zip(ys[:-1], ys[1:]):
                    toward([(xa, ya, za), (xa, yb2, za), (xb, yb2, zb), (xb, ya, zb)], SLATE0 + rng.randrange(8),
                           (sx, 0, 1), Y, Z)
            # its underside, one face a slope (boards seen from the top storey - a gable house has no ceiling - and
            # from the street under the eaves): without it the slates were not there from below
            # (a fifth of a stud under the slates, not in their plane: there the two flickered)
            low = 0.2
            toward([(sx * w / 2 * (1 - low / h), -d / 2, 0), (sx * w / 2 * (1 - low / h), d / 2, 0), (0, d / 2, h - low),
                    (0, -d / 2, h - low)], _plaster(rng), (-sx, 0, -1), Y, Z)
        # the gable ends (the front one is the street's; behind another roof module the back one is unseen)
        for y, front in ((-d / 2, True), (d / 2, False)):
            steps = 6
            for k in range(steps):
                z0, z1 = h * k / steps, h * (k + 1) / steps
                x0 = w / 2 * (1 - k / steps)
                x1 = w / 2 * (1 - (k + 1) / steps)
                both([(-x0, y, z0), (x0, y, z0), (x1, y, z1), (-x1, y, z1)], _pick(rng, z0, h), _plaster(rng),
                     (0, -1 if front else 1, 0))
        # a ridge roll: its top and its two sides, no ends (an end lay in the gable's own plane, and between two
        # roof modules it stood inside the roof)
        toward([(-0.25, -d / 2, h), (0.25, -d / 2, h), (0.25, d / 2, h), (-0.25, d / 2, h)], edge(), (0, 0, 1), X, Y)
        for sx in (-1, 1):
            toward([(sx * 0.25, -d / 2, h - 0.3), (sx * 0.25, d / 2, h - 0.3), (sx * 0.25, d / 2, h), (sx * 0.25, -d / 2, h)],
                   edge(), (sx, 0, 0), Y, Z)

    elif module == "chimney":
        cap = 0.6
        box(-w / 2 + 0.2, w / 2 - 0.2, -d / 2 + 0.2, d / 2 - 0.2, 0, h - cap, stone, top=False, bottom=True, back=True)
        box(-w / 2, w / 2, -d / 2, d / 2, h - cap, h, edge, top=True, bottom=True, back=True)
    else:
        raise ValueError(f"gothic_module: unknown module {module!r} (wall | window | windowb | door | oriel | band | roof | chimney)")
    return m



def _to_object(m, rec, img):
    name = rec["name"]
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in m.v], [], m.f)
    me.update()
    uvl = me.uv_layers.new(name="UV")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = m.uv[me.loops[li].vertex_index]
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj, img


# ---------------------------------------------------------------------------
# Entry: build_piece(rec) → (obj, img)
# ---------------------------------------------------------------------------
def build_piece(rec):
    """kind gothic_house | gothic_module | gothic_bay | gothic_lamppost | gothic_well | gothic_spire | gothic_turret
    → (Blender object, atlas RGBA float image) — same contract as castle_blender.build_piece"""
    kind = rec.get("kind")
    seed = int(rec.get("seed", 1))
    stone = rec.get("stone", [72, 75, 79])   # mid-grey Gothic stone default
    slate = rec.get("slate", [24, 27, 33])    # dark slate roof default

    img = gothic_atlas(stone, 1024, seed, slate=slate, iron=True, with_plaster=True, with_glass=True)

    if kind == "gothic_house":
        m = _house_mesh(rec)
        return _to_object(m, rec, img)
    elif kind == "gothic_bay":
        m = _bay_mesh(rec)
        return _to_object(m, rec, img)
    elif kind == "gothic_module":
        m = _module_mesh(rec)
        return _to_object(m, rec, img)
    elif kind == "gothic_lamppost":
        m, lantern_z = _lamppost_mesh(rec)
        obj, img_out = _to_object(m, rec, img)
        # store lantern height so meshes.json can report it
        rec["_lantern_z"] = round(lantern_z, 2)
        return obj, img_out
    elif kind == "gothic_well":
        m = _well_mesh(rec)
        return _to_object(m, rec, img)
    elif kind == "gothic_quoin":
        m = _quoin_mesh(rec)
        return _to_object(m, rec, img)
    elif kind == "gothic_spire":
        m = _spire_mesh(rec)
        return _to_object(m, rec, img)
    elif kind == "gothic_turret":
        m = _turret_mesh(rec)
        return _to_object(m, rec, img)
    else:
        raise ValueError(f"gothic_blender: unknown kind {kind!r}")
