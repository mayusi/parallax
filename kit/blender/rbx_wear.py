"""rbx_wear.py — wear a DARK finish shows without turning into bare metal (numpy only: tested without Blender).

    burnish(color, rough, rub)                  rubbed edges -> a worn satin grey, smoother
    smudge(color, rough, blobs, flat, amount)   handling marks -> roughness broken up on the open flats

Why: the bake's edge polish lifts a non-metal by 22 % of its OWN colour (wood and plastic must not turn into steel)
— on a black coating (0.04) that is +0.01, nothing; and chips swap in BARE METAL (the PBR floor: 150+ sRGB), which
fresh judges read on a black slide as bake artifacts ("bright white streaks along the slide edges", the Glock,
2026-10-09) while scoring its surface story 2-3 / 10 ("no wear anywhere"). A rubbed black nitride slide or polymer
frame does neither: its edges polish to a satin grey and its flats carry the hand's marks. The bake calls these
where a material asks (a.material(..., burnish=, smudge=, rub=)).

THE COLOUR IS sRGB-ENCODED: the bake's colour image holds sRGB values (a 0.028 linear black is 0.18 there, 47/255).
The tones below are LINEAR and converted (to_srgb) before they meet it: compared raw, the burnish's 0.16 linear
satin grey was 41/255 against a black slide's 47 — 'only ever lighter' never fired, and no dark finish ever showed
its burnished edges (eight fresh judges in a row: 'no wear at all', the Glock, 2026-10-10).
"""

import numpy as np

BURNISH_TONE = 0.16   # LINEAR (~111 sRGB): what a rubbed dark coating / polymer edge reads as — a worn satin grey
BURNISH_SMOOTH = 0.28  # its roughness drops this much at the most-rubbed edge (rubbing polishes)
SMUDGE_ROUGH = 0.12    # handling marks move the roughness this much either way (oily: smoother, dusty: duller)
SMUDGE_LIFT = 0.06     # ...and lift the colour this fraction where dull (a dry print reads a touch lighter)


def to_srgb(v):
    """a linear value -> its sRGB encoding (0..1): the space the bake's colour image holds"""
    v = max(0.0, float(v))
    return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1.0 / 2.4) - 0.055


def linear_of(c):
    """sRGB-encoded values (the bake's colour buffer) -> linear light, array-wise (the standard sRGB curve)"""
    c = np.maximum(np.asarray(c, np.float32), 0.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def srgb_of(v):
    """linear light -> its sRGB encoding, array-wise (to_srgb for a whole map)"""
    v = np.maximum(np.asarray(v, np.float32), 0.0)
    return np.where(v <= 0.0031308, 12.92 * v, 1.055 * v ** (1.0 / 2.4) - 0.055).astype(np.float32)


# a.material(wear=): THE MOTTLE of a used surface. A noise (Blender's Noise Texture in the object's own space,
# WEAR_NOISE) says where: under WEAR_LO the colour is (1 - WEAR_DARK x wear) of itself, over WEAR_HI untouched, a
# straight ramp between (in LINEAR light); the roughness rises by WEAR_ROUGH x wear where the noise is 0, by nothing
# where it is 1 (never past 1). It was a colour ramp and a map range in the material's nodes; the same arithmetic
# on the baked passes lets wear - and the life word that sets it - change without a bake.
WEAR_NOISE = {"Scale": 6.0, "Detail": 8.0}
WEAR_LO, WEAR_HI, WEAR_DARK, WEAR_ROUGH = 0.35, 0.75, 0.55, 0.25
# A colour pass is a byte image: it stops at 1. A scan or a wood grain can lift a bright colour past 1 (its variation
# runs to 2.4 x its mean), and the nodes darkened THAT before it was clipped: min(1, keep x colour). So what lies
# over 1 is baked too - (colour - 1) / WEAR_OVER, its own pass - and put back before the mottle multiplies.
WEAR_OVER = 4.0


def mottle_rougher(rough, wear):
    """how much rougher a material of this roughness gets where the wear noise is 0 -> float >= 0"""
    return max(0.0, min(1.0, float(rough) + WEAR_ROUGH * float(wear)) - float(rough))


def mottle(color, rough, fac, wear, rougher, over=None):
    """the wear mottle on the passes. color: (N, 3) sRGB-encoded; rough: (N, k); fac: (N,) the noise; wear: (N,) how
    much each texel's material wears; rougher: (N,) mottle_rougher of it; over: (N, 3) the pass of what the colour
    had over 1, (colour - 1) / WEAR_OVER, sRGB-encoded (None: nothing was over) -> (color, rough), the same shapes"""
    fac = np.clip(np.asarray(fac, np.float32), 0.0, 1.0)
    keep = 1.0 - WEAR_DARK * np.asarray(wear, np.float32) * (1.0 - np.clip((fac - WEAR_LO) / (WEAR_HI - WEAR_LO), 0.0, 1.0))
    lin = linear_of(color)
    if over is not None:   # (where the pass stopped at 1, the colour was 1 + what lay over it)
        lin = lin + WEAR_OVER * linear_of(over)
    out_c = srgb_of(np.clip(lin * keep[:, None], 0.0, 1.0))
    out_r = np.clip(np.asarray(rough, np.float32) + (np.asarray(rougher, np.float32) * (1.0 - fac))[:, None], 0.0, 1.0)
    return out_c, out_r


def burnish(color, rough, rub):
    """color (H, W, 3) sRGB-ENCODED (as the bake's colour image holds it), rough (H, W, C), rub (H, W, 1) 0..1: how
    rubbed each pixel is (the edge mask, already scaled by the material's burnish) -> (color, rough). Colour moves
    toward BURNISH_TONE (linear, encoded here) and only ever LIGHTER (a surface already lighter than it keeps its own);
    roughness drops, never below 0.05."""
    rub = np.clip(rub, 0.0, 1.0)
    lift = np.clip(to_srgb(BURNISH_TONE) - color, 0.0, None)
    color = color + lift * rub * 0.85
    rough = np.clip(rough - BURNISH_SMOOTH * rub, 0.05, 1.0)
    return color, rough


def smudge(color, rough, blobs, flat, amount):
    """blobs (H, W, 1) 0..1: mid-scale noise (finger-sized patches), flat (H, W, 1) 0..1: the open flats (not the
    edges, not the crevices), amount (H, W, 1) 0..1: the material's smudge -> (color, rough): roughness +-SMUDGE_ROUGH
    (below-mid blobs smoother, above duller), the colour a touch lighter where dull. Zero amount = unchanged."""
    m = np.clip(flat, 0.0, 1.0) * np.clip(amount, 0.0, 1.0)
    d = (np.clip(blobs, 0.0, 1.0) - 0.5) * 2.0
    rough = np.clip(rough + d * SMUDGE_ROUGH * m, 0.05, 1.0)
    color = color * (1.0 + np.clip(d, 0.0, 1.0) * SMUDGE_LIFT * m)
    return color, rough


DUST_TONE = (0.36, 0.33, 0.29)   # LINEAR (~160 / 155 / 146 sRGB): household / workshop dust — a light grey-beige,
#   the grime a dark finish can show (a.material(grime_tone="dust")); the default dirt is an sRGB dark brown
STAIN_TONE = (0.16, 0.095, 0.035)   # LINEAR (~111 / 87 / 53 sRGB): an ochre-brown that SOAKS into porous recesses
#   — aged bone and ivory, unglazed clay, old plaster, raw wood's end grain (a.material(grime_tone="stain")): darker
#   than dust, warmer and lighter than the default dirt, so a pale finish ages instead of looking dirty
RUB_TONE = 0.12        # LINEAR (~97 sRGB): a dark finish worn on its FLATS (holster rub, a hand's grip) — a satin
RUB_SMOOTH = 0.22      #  grey a step under the edges' burnish, and smoother (rubbing polishes)


def rub(color, rough, amount):
    """color sRGB-encoded (as burnish), amount (H, W, 1) 0..1: how worn each pixel's flat is (the material's rub x
    broad patches x exposure) ->
    (color, rough): toward RUB_TONE (only ever lighter) and smoother. The WORN FLATS a dark gun shows at a glance — a
    holstered slide's front flanks, a grip polished where the hand holds: an edge band 1-2 mm wide is ~4-10 px where
    judges look, and eight fresh judges in a row read the Glock "factory-new, no wear at all" (2026-10-10)."""
    a = np.clip(amount, 0.0, 1.0)
    color = color + np.clip(to_srgb(RUB_TONE) - color, 0.0, None) * a * 0.7
    rough = np.clip(rough - RUB_SMOOTH * a, 0.05, 1.0)
    return color, rough


def patches(noise, lo=0.48, hi=0.72):
    """broad noise (H, W, 1) 0..1 -> 0..1 PATCHES: none under lo, full over hi, smooth between (wear comes in
    patches where a holster or a hand bears, not as an even film)"""
    t = np.clip((np.asarray(noise, dtype=np.float32) - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def box_blur(a, r):
    """(H, W) -> a separable box blur of radius r (numpy only; the edges held)"""
    r = int(r)
    if r < 1:
        return a.astype(np.float32)
    out = a.astype(np.float32)
    for axis in (0, 1):
        pad = [(r + 1, r) if k == axis else (0, 0) for k in range(2)]
        c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis)
        n = out.shape[axis]
        # (two slices of the running sum: the same numbers np.take(range) picked, without the gather)
        hi = c[2 * r + 1:2 * r + 1 + n] if axis == 0 else c[:, 2 * r + 1:2 * r + 1 + n]
        lo = c[0:n] if axis == 0 else c[:, 0:n]
        out = (hi - lo) / (2 * r + 1)
    return out


def fbm(n, rng, octaves=4, cells=6):
    """n x n fractal value noise in 0..1 (bilinear-interpolated random grids); `cells` = the coarsest grid. The
    layering's noise fields (rbx._fbm). Each grid row is interpolated along x ONCE (cells + 1 rows of n values) and
    two of those rows are mixed along y for every texel row - the same arithmetic on every texel as four gathers of
    n x n (the same bits: test_wear), a quarter of the time at 4096."""
    out = np.zeros((n, n), dtype=np.float32)
    amp, total = 1.0, 0.0
    for _ in range(octaves):
        grid = rng.random((cells + 1, cells + 1)).astype(np.float32)
        t = np.linspace(0, cells, n, endpoint=False, dtype=np.float32)
        i = t.astype(np.int32)
        f = t - i
        f = f * f * (3 - 2 * f)
        fx, fy = f[None, :], f[:, None]
        rows = grid[:, i] * (1 - fx) + grid[:, i + 1] * fx
        lay = rows[i] * (1 - fy)
        lay += rows[i + 1] * fy
        lay *= amp
        out += lay
        total += amp
        amp *= 0.5
        cells *= 2
    return out / total


def one_channel(a):
    """a baked pass (H, W, 4) -> its values without the alpha: ONE channel (H, W, 1) when its three are the same (a
    roughness or metalness map: every step of the layering did the same sum three times), else (H, W, 3), contiguous"""
    if np.array_equal(a[..., 1], a[..., 0]) and np.array_equal(a[..., 2], a[..., 0]):
        return a[..., :1].copy()
    return np.ascontiguousarray(a[..., :3])


def edge_band(convex, px_per_mm=None, width_mm=1.0):
    """convex (H, W) 0..1 (the curvature's convex part: a line a few px wide along each edge) -> (H, W) 0..1: a
    band `width_mm` either side of each edge at the map's MEASURED density (px of map per mm of surface), 1 at the
    edge, fading into the faces — rubbing reaches 1-2 mm into a slide's flats, at any texture size. A fixed 3 px
    reach was 0.3 mm on a 4K map: in the renders the wear was a hairline no judge saw. No density: 3 px."""
    r = int(np.clip(round(width_mm * px_per_mm), 1, 32)) if px_per_mm else 3
    b = box_blur(np.clip(convex, 0.0, 1.0), r)
    live = b > 1e-4
    top = float(np.percentile(b[live], 98)) if live.any() else 1.0
    return np.clip(b / max(top, 1e-6), 0.0, 1.0) ** 0.7


# ---- colour variation inside one material (a.material(..., vary=)): no real surface is one flat colour — a board's
# tone drifts along it, a casting's oxide mottles, paint goes on thicker here and thinner there. Two object-space noise
# fields (baked: seamless across UV islands) move the colour's VALUE about its own mean, and nudge its hue warm / cool
VARY_LO = 0.16    # value moved up to +-16% by the broad field (~120 mm features)
VARY_MID = 0.08   # ...and +-8% by the finer one (~25 mm)
VARY_HUE = 0.03   # warm / cool drift: red up and blue down (or the reverse) by up to 3%


def vary(color, lo, mid, amount, mask=None):
    """color (H, W, 3) sRGB-encoded, lo / mid (H, W, 1) noise 0..1 (object space), amount (H, W, 1) 0..1 the
    material's vary -> color. Each noise is centred on its own mean over the varied texels, so the material's average
    colour stays where its measured value put it; only the spread changes."""
    a = np.clip(amount, 0.0, 1.0)
    on = (a[..., 0] > 0) if mask is None else (mask & (a[..., 0] > 0))
    if not on.any():
        return color
    lo_c = lo - float(lo[on].mean())
    mid_c = mid - float(mid[on].mean())
    sd_lo, sd_mid = float(lo_c[on].std()) or 1.0, float(mid_c[on].std()) or 1.0
    k = 1.0 + a * (VARY_LO * np.clip(lo_c / (2.0 * sd_lo), -1, 1) + VARY_MID * np.clip(mid_c / (2.0 * sd_mid), -1, 1))
    out = color * k
    warm = a[..., 0] * VARY_HUE * np.clip(mid_c[..., 0] / (2.0 * sd_mid), -1, 1)
    out[..., 0] *= 1.0 + warm
    out[..., 2] *= 1.0 - warm
    return np.where(on[..., None], np.clip(out, 0.0, 1.0), color)


def dust_mask(up, concave, convex, noise):
    """where dust settles (a.material(dust=)): the world-space normal's up (a face looking at the sky) as a soft ramp
    from ~40 deg off level (up 0.75) to flat (1.0), more in recesses (concave), wiped off the edges (convex), broken by
    noise (never a painted band). All (H, W, 1) 0..1 -> (H, W, 1) 0..1"""
    import numpy as np  # noqa: PLC0415

    ramp = np.clip((up - 0.72) / 0.25, 0, 1) ** 1.5
    return np.clip(ramp * (0.55 + 0.6 * concave) * (1 - 0.75 * convex) * (0.35 + 0.85 * noise), 0, 1)


DRIP_TONE = (0.075, 0.05, 0.03)   # LINEAR (~77 / 63 / 49 sRGB): what runs DOWN from a fitting, a seam or a bolt — water
#   carrying rust and grime, dried into streaks (a.contact("drip", ...)): darker and browner than dust, and dull
DRIP_DULL = 0.12   # its residue is a little rougher than the finish it runs over...
DRIP_DEMETAL = 0.6  # ...and on bare metal it is a film, no longer metal (the streak reads as a stain, not a tint)


def drip(color, rough, metal, mask):
    """streaks from a.contact("drip") -> (color, rough, metal): toward DRIP_TONE (encoded for the sRGB colour buffer),
    duller, less metallic, by the mask (0..1, the bake's streak field). Arrays (..., 3); mask (..., 1)"""
    m = np.clip(mask, 0.0, 1.0)
    tone = np.array([to_srgb(c) for c in DRIP_TONE], dtype=np.float32)
    color = color * (1 - 0.6 * m) + tone * 0.6 * m
    rough = np.clip(rough + DRIP_DULL * m, 0.0, 1.0)
    metal = metal * (1 - DRIP_DEMETAL * m)
    return color, rough, metal


def box_from_points(points, pad=0.0):
    """the box round points (N x 3, the model's frame) grown by pad on every side -> (centre, size) tuples: a.contact
    (..., part=) takes the box of the part it names — use follows the part, never a box typed by hand"""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    lo, hi = p.min(axis=0) - pad, p.max(axis=0) + pad
    return tuple(float(v) for v in (lo + hi) / 2), tuple(float(v) for v in np.maximum(hi - lo, 1e-4))


SPEC_OCC = 1.0          # specular occlusion (the owner, 2026-11-17: "New pieces only"): a new piece's crevices reflect
SPEC_OCC_OPEN = 0.85    # less - from where the occlusion map reads below this (open faces read 0.9+)...
SPEC_OCC_SPAN = 0.6     # ...to full at this much below it: there the roughness rises by SPEC_OCC_ROUGH and the
SPEC_OCC_ROUGH = 0.3    # metalness falls by SPEC_OCC_METAL of itself (Roblox has no specular-occlusion input: a
SPEC_OCC_METAL = 0.5    # bright environment reflection deep inside a slot or under a guard reads as a light leak)


def spec_occlusion(rough, metal, occ, strength):
    """-> (rough, metal, cavity): rougher and less metallic where the occlusion map `occ` (1 open .. 0 buried) is dark.
    `cavity` (0..strength, one channel) is how much each texel was taken down. An occlusion map of all 1 (skipped or
    untrusted) and strength 0 change nothing"""
    cav = np.clip((SPEC_OCC_OPEN - np.asarray(occ, np.float32)) / SPEC_OCC_SPAN, 0, 1) * float(strength)
    rough = np.clip(rough + SPEC_OCC_ROUGH * cav, 0.05, 1)
    metal = np.clip(metal * (1 - SPEC_OCC_METAL * cav), 0, 1)
    return rough, metal, cav


def built_before(name, repo):
    """(True, why) for a piece built or scripted before 2026-11-17 (kit/blender/spec_occ_before.json - the owner on
    that day's bake changes: "New pieces only") or a kit fixture (_selftest*, _probe*): it bakes as before, byte for
    byte; (False, why) for a new piece. A game version (<name>_game) follows its master"""
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415

    base = name[:-5] if name.endswith("_game") else name
    if base.startswith(("_selftest", "_probe")):
        return True, "a kit fixture (built before 2026-11-17's bake changes)"
    try:
        with open(os.path.join(repo, "kit", "blender", "spec_occ_before.json"), encoding="utf-8") as fh:
            before = set(json.load(fh).get("names") or [])
    except (OSError, ValueError):
        before = set()
    if base in before:
        return True, 'built before 2026-11-17 (kit/blender/spec_occ_before.json: the owner, "New pieces only")'
    return False, 'a new piece (the owner, 2026-11-17: "New pieces only")'


def spec_occ_default(name, repo):
    """(strength, where it came from) for a script that names no spec_occlusion=: off for a piece built before
    2026-11-17 and for the kit's fixtures (built_before), SPEC_OCC for a new piece"""
    old, why = built_before(name, repo)
    if old and why.startswith("a kit fixture"):
        return 0.0, "a kit fixture (built before specular occlusion)"
    return (0.0, why) if old else (SPEC_OCC, why)


# --- noise in the model's own 3D space (H6, his limitations review V3: "3D object-space noise"; new pieces only) ---
# A map-space field (fbm above) is drawn across the texture: where the unwrap cuts the surface into islands, the
# field jumps at every seam (a patch of wear ends in a straight line along an island's edge). Evaluated at each
# texel's own place on the model, the same field runs on across every seam.
FBM3_SPREAD = 0.135 / 0.24   # the 3D field's spread (perlin fbm: ~0.24 about 0) onto the map field's (~0.135 about 0.5)


UV_PAD = 16   # texels: each island's places carried out into its margin (what the bake's padding and sampling read)


def uv_positions(uv, pos, n, pad=UV_PAD):
    """each texel's place on the model: triangles in the map (uv (T, 3, 2), 0..1) with their corners' places (pos
    (T, 3, 3), mm) -> (positions (n, n, 3) float32, inside (n, n) bool); rows run with v (Blender's pixel order:
    row 0 the map's bottom), a texel inside a triangle when its centre is. The `pad` texels round each island take
    the place of the island texel next to them (and count as inside): the margin the bake pads and a sampler reads
    across an island's edge then holds the island's own field - left at the middle of the field, every seam drew
    a hairline"""
    out = np.zeros((n, n, 3), np.float32)
    inside = np.zeros((n, n), bool)
    for t, p in zip(np.asarray(uv, np.float64) * n, np.asarray(pos, np.float64)):
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, n - 1), min(y1, n - 1)
        if x1 < x0 or y1 < y0:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = t
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / d
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / d
        l3 = 1.0 - l1 - l2
        hit = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
        if not hit.any():
            continue
        ys, xs = np.nonzero(hit)
        w = np.stack([l1[hit], l2[hit], l3[hit]], axis=1)
        out[ys + y0, xs + x0] = (w @ p).astype(np.float32)
        inside[ys + y0, xs + x0] = True
    have = inside.copy()
    for _ in range(int(pad)):   # (grow: an empty texel takes a filled neighbour's place, one ring at a time)
        if have.all():
            break
        grown = out.copy()
        took = have.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src = np.roll(have, (dy, dx), axis=(0, 1))
            if dy == 1:
                src[0, :] = False
            elif dy == -1:
                src[-1, :] = False
            elif dx == 1:
                src[:, 0] = False
            else:
                src[:, -1] = False
            new = src & ~took
            grown[new] = np.roll(out, (dy, dx), axis=(0, 1))[new]
            took |= new
        out, have = grown, took
    return out, have


def mm_per_texel(positions, inside):
    """the map's sharpness on the model: the median distance (mm) between neighbouring texels of one island"""
    a = positions
    m = inside
    d = []
    for dy, dx in ((0, 1), (1, 0)):
        both = m[: m.shape[0] - dy, : m.shape[1] - dx] & m[dy:, dx:]
        step = np.linalg.norm(a[dy:, dx:] - a[: a.shape[0] - dy, : a.shape[1] - dx], axis=2)[both]
        d.append(step)
    d = np.concatenate(d) if d else np.zeros(0)
    d = d[d > 0]
    return float(np.median(d)) if len(d) else 0.0


def fbm3(positions, inside, seed, octaves=4, period_mm=50.0):
    """the 3D field at each texel's place -> (n, n) float32 0..1, centred and spread as the map field (fbm): a
    feature `period_mm` across (the coarsest octave's lattice), texels off the model 0.5"""
    import rbx_sculpt  # noqa: PLC0415  (its perlin: seeded, numpy only)

    out = np.full(inside.shape, 0.5, np.float32)
    if inside.any():
        q = positions[inside] / float(max(period_mm, 1e-6))
        if q.shape[-1] == 4:   # (a tile's places on its flat torus: 4D noise repeats both ways - wrap_xz)
            f = fbm4(q, octaves=int(octaves), seed=int(seed))
        else:
            f = rbx_sculpt.fbm(q, octaves=int(octaves), seed=int(seed))
        out[inside] = np.clip(0.5 + f * FBM3_SPREAD, 0.0, 1.0)
    return out


# --- patterns in the model's own space (H6 / S3: "lathe_rings, brushed, car_paint, radial_dust" on world_pos) -----
PATTERNS3 = ("lathe", "flake")   # material patterns that only exist on the model (a.material(pattern=, pattern_axis=))


def axis_of(axis):
    """a.material(pattern_axis=) / rbx.layer(axis=): "X" | "Y" | "Z" or (that, (x, y, z) a point on it, mm) ->
    (unit direction, centre mm) in the kit's frame (x right, y up, z back)"""
    if axis is None:
        return np.array([0.0, 1.0, 0.0]), np.zeros(3)
    if isinstance(axis, str):
        name, centre = axis, (0.0, 0.0, 0.0)
    else:
        name, centre = axis
    d = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}.get(str(name).upper().lstrip("+"))
    if d is None:
        raise ValueError(f'axis "{name}": "X", "Y" or "Z" (or that with a point on it: ("Z", (x, y, z)) in mm)')
    return np.array(d), np.array([float(c) for c in centre], np.float64)


def _cell_hash(ix, iy, iz, k=0):
    """a repeatable 0..1 value for each integer cell (a 32-bit integer hash; the same on every build)"""
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791) \
        ^ (k * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return ((h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)).astype(np.float32)


def pattern3(kind, positions, inside, pitch_mm, axis=None):
    """a material's micro-relief at each texel's place on the model -> (n, n) float32 0..1 (1 the top, 0 a
    groove; texels off the model 1): the bake turns it into normal-map slopes along the map's own directions.
        lathe    turning marks: rings round the axis every pitch_mm (a turned face, a wheel's lip)
        flake    car paint: a flake every pitch_mm, each tilted its own way (the sparkle under a clear coat)
        brushed  streaks running ALONG the axis, a streak about pitch_mm across and 60 times as long"""
    out = np.ones(inside.shape, np.float32)
    if not inside.any():
        return out
    d, c = axis_of(axis)
    p = positions[inside].astype(np.float64) - c
    pitch = float(max(pitch_mm, 1e-6))
    if kind == "lathe":
        along = p @ d
        r = np.linalg.norm(p - np.outer(along, d), axis=1)
        h = 0.5 + 0.5 * np.cos(2 * np.pi * r / pitch)
    elif kind == "flake":
        q = p / pitch
        i = np.floor(q)
        local = q - i - 0.5
        rv = np.stack([_cell_hash(i[:, 0], i[:, 1], i[:, 2], k) * 2 - 1 for k in (1, 2, 3)], axis=1)
        rv /= np.linalg.norm(rv, axis=1, keepdims=True) + 1e-9
        h = np.clip(0.5 + 1.2 * np.einsum("ij,ij->i", local, rv), 0, 1)   # (each flake a little plane, its own tilt)
    elif kind == "brushed":
        import rbx_sculpt  # noqa: PLC0415

        along = p @ d
        across = p - np.outer(along, d)
        q = across / pitch + np.outer(along / (pitch * 60.0), d) + (0.371, 0.613, 0.137)   # (off perlin's lattice: 0 there)
        h = np.clip(0.75 + 0.25 * (0.5 + 1.6 * rbx_sculpt.fbm(q, octaves=2, seed=7)), 0, 1)
    else:
        raise ValueError(f'pattern3: "{kind}" - lathe, flake or brushed')
    out[inside] = h.astype(np.float32)
    return out


def radial_field(positions, inside, axis=None, outward=False):
    """0..1 over the map by distance from an axis (rbx.layer(where="radial", axis=)): 1 at the axis falling to 0 at
    the farthest texel (brake dust from the hub out); outward=True the other way round. Off the model 0"""
    out = np.zeros(inside.shape, np.float32)
    if not inside.any():
        return out
    d, c = axis_of(axis)
    p = positions[inside].astype(np.float64) - c
    r = np.linalg.norm(p - np.outer(p @ d, d), axis=1)
    k = r / max(float(r.max()), 1e-9)
    out[inside] = (k if outward else 1.0 - k).astype(np.float32)
    return out


def wrap_x(positions, period):
    """places along x laid round a loop `period` long (a trim sheet's width): x -> a point on a circle of that
    circumference, (R cos, R sin, z) - a field drawn at these places repeats along x with that period exactly, and
    keeps its scale (an arc's length is the x it stood for). positions (..., 3) -> (..., 3)"""
    p = np.asarray(positions, np.float64)
    r = float(period) / (2 * np.pi)
    a = p[..., 0] / r
    return np.stack([r * np.cos(a), r * np.sin(a), p[..., 2]], axis=-1).astype(np.float32)


def texel_area(positions, inside):
    """each texel's patch of the model's surface (the area its square covers, in the positions' units squared):
    |d(place)/dx x d(place)/dy| from its neighbours in its own island; a texel with none beside it takes the median
    -> (n, n), 0 off the model"""
    p = np.asarray(positions, np.float64)
    m = np.asarray(inside, bool)
    dx = np.zeros_like(p)
    dy = np.zeros_like(p)
    okx = np.zeros(m.shape, bool)
    oky = np.zeros(m.shape, bool)
    fwd = m[:, :-1] & m[:, 1:]
    dx[:, :-1][fwd] = (p[:, 1:] - p[:, :-1])[fwd]
    okx[:, :-1] |= fwd
    back = m[:, 1:] & m[:, :-1] & ~okx[:, 1:]
    dx[:, 1:][back] = (p[:, 1:] - p[:, :-1])[back]
    okx[:, 1:] |= back
    fwd = m[:-1] & m[1:]
    dy[:-1][fwd] = (p[1:] - p[:-1])[fwd]
    oky[:-1] |= fwd
    back = m[1:] & m[:-1] & ~oky[1:]
    dy[1:][back] = (p[1:] - p[:-1])[back]
    oky[1:] |= back
    area = np.linalg.norm(np.cross(dx, dy), axis=2)
    good = m & okx & oky & (area > 0)
    med = float(np.median(area[good])) if good.any() else 0.0
    out = np.where(good, area, med)
    return np.where(m, out, 0.0)


# --- 4D noise: a TILE repeats both ways (card s4wc: "a tile's fade smears a patterned finish") ----------------------
# A square that repeats along x AND z has its places on a FLAT TORUS - each axis round its own circle - which only
# fits whole in four dimensions (the Clifford torus): noise drawn there repeats both ways exactly at an even scale.
_G4 = np.array([(a, b, c, d) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1) for d in (0,)] +
               [(a, b, d, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1) for d in (0,)] +
               [(a, d, b, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1) for d in (0,)] +
               [(d, a, b, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1) for d in (0,)], np.float32)   # 32


def perlin4(p, seed=0):
    """4D gradient noise at points p (N, 4) -> (N,) float32, about -1..1 (the sculpt's perlin, one dimension more)"""
    import rbx_sculpt  # noqa: PLC0415

    p = np.asarray(p, np.float32)
    fl = np.floor(p)
    f = p - fl
    c = fl.astype(np.int64) & 255
    P = rbx_sculpt._perm(seed)
    u = f * f * f * (f * (f * 6 - 15) + 10)
    out = np.zeros(len(p), np.float32)
    acc = {}
    for corner in range(16):
        d = [(corner >> k) & 1 for k in range(4)]
        h = P[P[P[P[c[:, 0] + d[0]] + c[:, 1] + d[1]] + c[:, 2] + d[2]] + c[:, 3] + d[3]] & 31
        g = _G4[h]
        rel = f - np.array(d, np.float32)
        acc[tuple(d)] = (g * rel).sum(axis=1)
    for k in range(4):   # (blend the 16 corners, one axis at a time)
        nxt = {}
        for key, v in acc.items():
            if key[k] == 0:
                hi = acc[key[:k] + (1,) + key[k + 1:]]
                nxt[key[:k] + (0,) + key[k + 1:]] = v + u[:, k] * (hi - v)
        acc = nxt
    out = next(iter(acc.values()))
    return out * np.float32(1.25)


def fbm4(p, octaves=4, seed=0, lacunarity=2.0, gain=0.5):
    """fractal 4D noise -> about -1..1 (rbx_sculpt.fbm, one dimension more)"""
    total, amp, norm = np.zeros(len(p), np.float32), 1.0, 0.0
    q = np.asarray(p, np.float32)
    for o in range(octaves):
        total += amp * perlin4(q, seed + 101 * o)
        norm += amp
        q = q * lacunarity
        amp *= gain
    return total / norm


def wrap_xz(positions, period_x, period_z):
    """places on a FLAT TORUS: x round one circle `period_x` long, z round another `period_z` long, in four
    dimensions -> (..., 4). A field drawn there repeats along x and along z exactly, at the places' own scale"""
    p = np.asarray(positions, np.float64)
    rx, rz = float(period_x) / (2 * np.pi), float(period_z) / (2 * np.pi)
    a, b = p[..., 0] / rx, p[..., 2] / rz
    return np.stack([rx * np.cos(a), rx * np.sin(a), rz * np.cos(b), rz * np.sin(b)], axis=-1).astype(np.float32)
