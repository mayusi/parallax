"""rbx_layers.py — A MATERIAL'S OWN LAYERS: what lies on a surface, written as a named stack (numpy only; the builder
calls it from its layering, rbx.Asset._bake_inner).

    a.material("paint", color=(0.2, 0.35, 0.25), chip=0.3, grime=0.4, layers=[
        rbx.layer("rust", where="chipped", amount=0.8),      # rust where the paint is gone
        rbx.layer("rust", where="cavities", amount=0.15),    # ... and creeping out of the seams
        rbx.layer("soot", where="low", amount=0.3, opacity=0.6),
    ])

How a texture artist builds a surface (Substance Painter's fill layers and mask generators, Mari's layer stack): the
base, then one layer per CAUSE, each a material of its own (a colour, a roughness, metal or not) shown through a
MASK that is computed from the mesh's own baked maps - curvature for edges and cavities, occlusion, the position
for "low", the world-space normal for "up" - broken up by noise. The kit's wear keys (chip, grime, dust, burnish...)
are such layers with their recipes fixed; this module is the open part: any tone, any of the sources, in the order
written.

A layer is a plain dict (so a look in kit/materials/looks.json can carry its layers):
    kind     a name from KINDS (its tone measured off a scan the kit holds), or any name with color= given
    where    which texels may take it, and which take it FIRST (SOURCES)
    amount   0..1: the share of its PLACE it covers - "rust on 15% of the cavities". A place is the room its
             source gives on the material's own texels (a texel with a faint source counts for less: FADE); the
             texels the source and the noise rank highest are covered first; the cut is found on that room, so
             the share is what was asked at any map size (the report's `eligible` is the room, `covered` what
             was laid: covered = amount x eligible, to the cut's soft edge)
    opacity  0..1: how much of the surface below still shows where it lies (a film of soot: 0.6; rust: 1)
    color / rough / metal   what it is (LINEAR colour); a kind's own unless given; None for rough / metal = left
    breakup  0..1: how much the noise decides against the source (0: the source's own contours; 1: patches)
    grain    "patches" (broad, ragged) | "fine"
    thick_mm how THICK it lies, in millimetres of the real object (0 = a stain: colour only). It becomes relief in
             the normal map: the layer's edge is a real slope and its top is uneven (RELIEF). A named layer has
             its own (rust 0.4, mud 3, moss 6, snow 12, soot 0); a layer of your own colour has 0 unless given.
             What a map can show of it depends on its texels and on the layer's shape: the report says how far
             each layer's bank and its top tilt the surface, "too flat to show" where neither reaches SHOWS_DEG
             and "too steep for this map" where the bank is at the hold (SLOPE_MAX)

Where they go in the fixed order of the kit's own layers: after the base, the occlusion's shading, the edge polish,
the paint chips and the grime - before the dust (dust settles on rust too) and before what hands rub. A layer takes
the occlusion's shading of the surface it lies on (rust in a seam is as dark as the seam).

What a layer is NOT (2026-11-13): it is one tone (a scan's own variation is not in it); its noise is drawn at each
texel's own place on the model for a new piece's bake (c43087b3: it runs on across the unwrap's seams; an older
piece's bake keeps the map-space noise it was judged with); its relief is in the normal map
only (the occlusion and the silhouette do not know of it) and is sized by the mesh group's AVERAGE texels per
millimetre (a part given more or fewer texels - a.texel - has a relief that much too flat or too steep; without
real_scale() a stud is taken as 280 mm); "low" is the lower part of its own mesh group; scratches, patterns and
stamps are drawn after it.
"""

import math
import zlib

import numpy as np

import rbx_wear

# THE NAMED LAYERS. Tones measured 2026-11-13 off the CC0 scans in the kit's cache (~/.cache/roblox-kit/materials,
# ambientCG; _scratch/layers/measure_scans.py: the colour map's mean in LINEAR light, the roughness map's mean) -
# never typed from memory. soot has no scan: carbon black, the darkest albedo a real surface has (0.04 linear:
# Adobe's PBR guide, vol. 2), as rough as a deposit is.
# thick_mm is NOT measured: a labelled ESTIMATE of how thick each lies on an object (no scan carries a real height,
# and a search found no table: a protective rust film is micrometres - no relief; these are the thick kinds).
KINDS = {
    "rust": {"color": (0.266, 0.074, 0.022), "rough": 0.78, "metal": 0.0, "where": "cavities", "opacity": 1.0,
             "source": "Rust009", "thick_mm": 0.4, "thick_source": "estimate: laminated, flaking rust scale"},
    "moss": {"color": (0.074, 0.139, 0.011), "rough": 0.61, "metal": 0.0, "where": "cavities", "opacity": 1.0,
             "source": "Moss002", "thick_mm": 6.0, "thick_source": "estimate: a low moss cushion"},
    "snow": {"color": (0.576, 0.582, 0.586), "rough": 0.51, "metal": 0.0, "where": "up", "opacity": 1.0,
             "source": "Snow006", "thick_mm": 12.0, "thick_source": "estimate: a dusting that has settled"},
    "mud": {"color": (0.211, 0.167, 0.107), "rough": 0.74, "metal": 0.0, "where": "low", "opacity": 0.9,
            "source": "Ground108 (colour), Ground111 (dry: its roughness)", "thick_mm": 3.0,
            "thick_source": "estimate: dried splashes"},
    "soot": {"color": (0.04, 0.04, 0.04), "rough": 0.9, "metal": 0.0, "where": "all", "opacity": 0.75,
             "source": "carbon black: the PBR albedo floor", "thick_mm": 0.0, "thick_source": "a film: no relief"},
}

# WHERE a layer may lie: each a field 0..1 over the map, from the maps the bake already has (field()).
SOURCES = {
    "all": "anywhere on the material (the noise alone picks the patches)",
    "edges": "convex edges and a little way into the face, where nothing covers them (what gets knocked)",
    "cavities": "inside corners, seams and recesses (curvature and occlusion: where water and dirt stay)",
    "flats": "the open faces away from every edge",
    "up": "faces that look up (the world-space normal: what settles from the air)",
    "low": "the lower part of the mesh group (what splashes up and what runs down)",
    "chipped": "where this material's paint has chipped off (chip=): what happens to the metal under it",
    "radial": "by distance from an axis (axis=): most at it, none at the farthest texel - brake dust from a hub",
    "radial_out": "by distance from an axis (axis=): most at the farthest texel - what is flung outward",
}
PLACES = {"all": "anywhere", "up": "on up faces", "low": "low down", "chipped": "where chipped", "edges": "on edges",
          "cavities": "in cavities", "flats": "on flats", "radial": "near the axis", "radial_out": "out from the axis"}
NEEDS = {"up": "upmask", "low": "lowmask"}      # the helper pass a source reads (baked only where one asks)
# a layer's noise: (octaves, cells across the map, weight) fields summed. "patches": broad shapes with a RAGGED
# contour (the broad field alone drew smooth blobs - camouflage, not a deposit: the kit's first test piece,
# 2026-11-13; the paint chips' own score mixes a broad and a fine field the same way); "fine": small ones
GRAINS = {"patches": ((4, 6, 0.62), (3, 28, 0.38)), "fine": ((3, 28, 1.0),)}
SOFT = 0.06          # the cut's soft edge, as a share of the score's spread (the chips' own: ragged, not a ramp)
TIE = 0.02           # the least say the noise has (breakup 0 on a flat source: something must pick the texels)
FADE = 0.25          # under this much source a layer thins out with it (no hard line where a ramp ends)
ELIGIBLE = 0.02      # a texel with less source than this never takes the layer
ROUGH_MIN = 0.05     # the roughness floor every step of the layering keeps
BINS = 4096          # the cut is read off a histogram of the scores, weighed by each texel's room
# RELIEF: a layer's height is its mask times its thickness, its top uneven by UNEVEN of that (a second, finer noise
# whose broad lumps are TOP_WIDE times the thickness across, with a ripple half that size on them - a deposit's
# lumps are about as wide as it is thick, at any map size - and never under TOP_PX texels, where the map cannot
# draw them) - a deposit is no flat sticker. The slope (mm of height per mm of surface: the height's step from
# texel to texel times the map's texels per mm) tilts the tangent-space normal in the normal's OWN frame (raised:
# a layer on a bevel leans from the bevel, not from the flat); its size is held to SLOPE_MAX (a 63 degree face:
# a steeper normal is noise at a texel's scale).
# Its BANK: the colour's mask fades over a soft edge many texels wide, but a deposit is not a dome - it reaches its
# thickness within a narrow bank and is thin only at its feathered rim: the height is full where the mask passes
# BANK, which makes the edge three times as steep as the fade (the layer's TOP tilts by its lumps, whatever the
# bank does: a report that takes one number over the whole layer cannot tell a bank from a dome - tilts() says
# both).
UNEVEN = 0.35
TOP_WIDE = 2.0
TOP_PX = 3.0
BANK = 0.35
SLOPE_MAX = 2.0
THICK_MAX = 50.0     # mm: more than this is geometry, not a layer
SHOWS_DEG = 2.0      # a layer whose bank and top both tilt the surface less than this is too flat to show (2 degrees
#                      moves a diffuse surface's light by some 2% under a 45 degree light: the least that reads)
MOVES = 0.004        # a slope under this (0.23 degrees: half a level of an 8-bit normal map) moves no texel
HELD_DEG = 62.0      # a bank at this (its 95th percentile: SLOPE_MAX is 63.4) is the hold, not the layer's own slope
PLACED = "mask:"     # where="mask:<name>": a mask the build script PLACED (a picture or a rule: a.mask), not a source
KEYS = ("kind", "where", "amount", "opacity", "color", "rough", "metal", "breakup", "grain", "thick_mm")


def layer(kind, where=None, amount=0.25, opacity=None, color=None, rough=None, metal=None, breakup=0.5,
          grain="patches", thick_mm=None, axis=None):
    """one layer of a material's stack -> a plain dict (a.material(layers=[...]); see the module's words).
    Raises ValueError with what is allowed: a typed layer is checked where it is written, not at the bake."""
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("layer: its first argument is its name (one of %s, or your own with color=)" % ", ".join(KINDS))
    known = KINDS.get(kind)
    if known is None and color is None:
        raise ValueError(f'layer "{kind}": not a named layer ({", ".join(KINDS)}) - give its own color=(r, g, b) '
                         "in linear light (and rough=, metal=)")
    where = where if where is not None else (known or {}).get("where", "all")
    placed = isinstance(where, str) and where.startswith(PLACED) and len(where) > len(PLACED)
    if where not in SOURCES and not placed:
        raise ValueError(f'layer "{kind}": where="{where}" - one of {", ".join(SOURCES)}, or "mask:<name>" (a '
                         "mask the build script placed: a.mask)")
    if grain not in GRAINS:
        raise ValueError(f'layer "{kind}": grain="{grain}" - one of {", ".join(GRAINS)}')
    opacity = opacity if opacity is not None else (known or {}).get("opacity", 1.0)
    rough = rough if rough is not None else (known or {}).get("rough")
    metal = metal if metal is not None else (known or {}).get("metal")
    thick_mm = thick_mm if thick_mm is not None else (known or {}).get("thick_mm", 0.0)
    try:
        if not 0.0 <= float(thick_mm) <= THICK_MAX:
            raise ValueError(f'layer "{kind}": thick_mm={thick_mm} - 0..{THICK_MAX:g} millimetres (0 = a stain; '
                             "thicker than that is geometry)")
        for k_, v_ in (("amount", amount), ("opacity", opacity), ("breakup", breakup)):
            if not 0.0 <= float(v_) <= 1.0:
                raise ValueError(f'layer "{kind}": {k_}={v_} - 0..1')
        color = tuple(float(c) for c in (color if color is not None else known["color"]))
        if len(color) != 3 or not all(0.0 <= c <= 1.0 for c in color):
            raise ValueError(f'layer "{kind}": color={color} - three numbers 0..1, linear light')
        if rough is not None and not ROUGH_MIN <= float(rough) <= 1.0:
            raise ValueError(f'layer "{kind}": rough={rough} - {ROUGH_MIN}..1 (or leave it: the surface\'s own stays)')
        if metal is not None and not 0.0 <= float(metal) <= 1.0:
            raise ValueError(f'layer "{kind}": metal={metal} - 0..1 (or leave it: the surface\'s own stays)')
    except TypeError:
        raise ValueError(f'layer "{kind}": amount, opacity, breakup, thick_mm, rough and metal are numbers, color '
                         "three of them") from None
    if where in ("radial", "radial_out"):
        rbx_wear.axis_of(axis)   # (validates it; None: the model's up through its origin)
    elif axis is not None:
        raise ValueError(f'layer "{kind}": axis= is read by where="radial" / "radial_out" only')
    extra = {"axis": axis} if axis is not None else {}   # (only when given: every other layer's dict, its key, unchanged)
    return {**extra, "kind": kind, "where": where, "amount": float(amount), "opacity": float(opacity), "color": color,
            "rough": None if rough is None else float(rough), "metal": None if metal is None else float(metal),
            "breakup": float(breakup), "grain": grain, "thick_mm": float(thick_mm)}


def resolve(layers, material="?"):
    """a.material(layers=) as given - a list of layer() dicts, plain dicts off a look, or names - -> the checked
    tuple of dicts (every key of KEYS). A name alone ("rust") is that named layer as it is."""
    if layers is None:
        return ()
    if isinstance(layers, (str, bytes, dict)) or not hasattr(layers, "__iter__"):
        raise ValueError(f'material "{material}": layers= is a LIST of layers - [rbx.layer("rust", where=..., '
                         "amount=...), ...]")
    out = []
    for i, d in enumerate(layers):
        if isinstance(d, str):
            d = {"kind": d}
        if not isinstance(d, dict) or "kind" not in d:
            raise ValueError(f'material "{material}": layers[{i}] is not a layer - use rbx.layer("rust", where=..., '
                             "amount=...) or a dict with its kind")
        extra = sorted(set(d) - set(KEYS) - {"axis"})   # (axis: only where="radial" / "radial_out" reads it)
        if extra:
            raise ValueError(f'material "{material}": layers[{i}] ("{d["kind"]}") has no {", ".join(extra)} - '
                             f'a layer has {", ".join(KEYS)}')
        try:
            out.append(layer(d["kind"], **{k: v for k, v in d.items() if k != "kind"}))
        except ValueError as e:
            raise ValueError(f'material "{material}": {e}') from None
    return tuple(out)


def needs(layers):
    """the helper passes these layers' sources read -> a sorted list of channel names (upmask, lowmask)"""
    return sorted({NEEDS[d["where"]] for d in layers or () if d["where"] in NEEDS})


def seeds(obj, material, layers):
    """each layer's own noise seed -> a list, one a layer. The same on every build (crc32, never hash()) and its
    layer's OWN: from what the layer is and where it lies (and which one of several alike it is) - never from its
    place in the list, so a layer added, taken out or moved leaves every other layer's patches where they were
    (and the kit's own wear: it draws from another generator)"""
    seen, out = {}, []
    for d in layers:
        k = (d["kind"], d["where"])
        out.append(zlib.crc32(f"{obj}/{material}/{d['kind']}/{d['where']}/{seen.get(k, 0)}".encode()))
        seen[k] = seen.get(k, 0) + 1
    return out


def noise(n, rng, grain="patches", places=None, px_per_mm=None):
    """a layer's noise field -> (n, n) float32 0..1 (GRAINS: the fields of its grain, weighed). places=(positions,
    inside) with px_per_mm (rbx_wear.uv_positions): the same fields at each texel's place on the model - a feature
    as many mm across as it was texels / px_per_mm - so it runs on across the unwrap's seams (a new piece's bake)"""
    out = np.zeros((n, n), np.float32)
    for octaves, cells, weight in GRAINS[grain]:
        if places is not None and px_per_mm:
            f = rbx_wear.fbm3(places[0], places[1], int(rng.integers(1 << 30)), octaves, (n / cells) / px_per_mm)
        else:
            f = rbx_wear.fbm(n, rng, octaves=octaves, cells=cells)
        out += np.float32(weight) * f
    return out


def field(where, maps, axis=None):
    """where a layer may lie -> (H, W, 1) float32 0..1. maps: the layering's arrays, each (H, W, 1) 0..1 -
    convex, concave, occ, exposed, reach (always), up / low (when baked), chipped (when the group has chips);
    a source whose map is missing is 0 everywhere (the layer then says it found nowhere to lie)."""
    one = np.ones_like(maps["convex"], dtype=np.float32)
    zero = np.zeros_like(one)
    if where == "all":
        return one
    if where == "edges":
        return np.clip(maps["reach"] * maps["exposed"], 0, 1).astype(np.float32)
    if where == "cavities":   # (the grime's own source: curvature's inside corners and where occlusion is deep)
        return np.clip(maps["concave"] * 1.1 + (1 - maps["occ"]) * 1.6, 0, 1).astype(np.float32)
    if where == "flats":
        return ((1 - np.clip(maps["convex"] * 2.0, 0, 1)) * (1 - np.clip(maps["concave"] * 2.0, 0, 1))
                * maps["exposed"]).astype(np.float32)
    if where in ("up", "low", "chipped"):
        m = maps.get(where)
        return zero if m is None else np.clip(m, 0, 1).astype(np.float32)
    if where in ("radial", "radial_out"):   # (each texel's place on the model: maps["places"], rbx_wear.uv_positions)
        at = maps.get("places")
        if at is None:
            return zero
        return rbx_wear.radial_field(at[0], at[1], axis, outward=where == "radial_out")[..., None]
    if isinstance(where, str) and where.startswith(PLACED):   # a mask the build script placed (a.mask; rbx_mask)
        m = (maps.get("masks") or {}).get(where[len(PLACED):])
        return zero if m is None else np.clip(m, 0, 1).astype(np.float32)
    raise ValueError(f'where="{where}" - one of {", ".join(SOURCES)}')


def mask(src, noise, cov, amount, breakup=0.5):
    """one layer's mask on one material -> ((H, W, 1) float32 0..1, {"eligible", "covered"}: shares of the
    material's texels).
    src: (H, W, 1) the source field; noise: (H, W) or (H, W, 1) 0..1, or a function giving it (called only when
    the layer has somewhere to lie); cov: (H, W, 1) how much of each texel this material covers.
    The texels that may take the layer are the material's own (cov > 0.5) with some source (> ELIGIBLE); what each
    can take - its ROOM - is its coverage, less where the source is faint (FADE). `eligible` is the room, as a
    share of the material. `amount` of the room is covered, those texels first whose score - the source and the
    noise, weighed by `breakup` - is highest (the noise always has a last word, TIE: a flat source's texels are
    all the same); the cut is read off the scores' histogram weighed by room (BINS) and has a soft edge (SOFT of
    the scores' spread)."""
    src = np.nan_to_num(np.asarray(src, np.float32), nan=0.0, posinf=1.0, neginf=0.0)
    own = cov > 0.5
    can = own & (src > ELIGIBLE)
    n_own = int(own.sum())
    room = (np.clip(src / FADE, 0, 1) * np.clip(cov, 0, 1)).astype(np.float32)
    total = float(room[can].sum(dtype=np.float64))
    facts = {"eligible": round(total / n_own, 4) if n_own else 0.0, "covered": 0.0}
    if amount <= 0.0 or total <= 0.0:
        return np.zeros(src.shape, np.float32), facts
    if amount >= 1.0:
        m = can.astype(np.float32)
    else:
        if callable(noise):
            noise = noise()
        noise = noise[..., None] if noise.ndim == 2 else noise
        b = max(float(breakup), TIE)
        score = (src * (1.0 - b) + noise * b).astype(np.float32)
        s = score[can]
        lo, hi = (float(v) for v in np.percentile(s, [2.0, 98.0]))
        hist, edges = np.histogram(s, bins=BINS, weights=room[can].astype(np.float64))
        top = np.cumsum(hist[::-1])                      # the room taken, from the highest score down
        want = amount * total
        c = min(int(np.searchsorted(top, want)) + 1, BINS)   # that many bins from the top hold it
        j = BINS - c                                     # ... down to this bin, and this far into it:
        over = float(top[c - 1]) - want
        cut = float(edges[j]) + (over / float(hist[j]) if hist[j] > 0 else 0.0) * float(edges[j + 1] - edges[j])
        m = np.clip((score - cut) / max(SOFT * (hi - lo), 1e-6) + 0.5, 0, 1) * can
    m = (m * room).astype(np.float32)
    facts["covered"] = round(float(m[own].sum(dtype=np.float64)) / n_own, 4) if n_own else 0.0
    return m, facts


def encoded(color):
    """a layer's LINEAR colour as the bake's sRGB colour buffer holds it -> float32 (3,)"""
    c = np.asarray(color, np.float64)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0.0), 1 / 2.4) - 0.055).astype(np.float32)


def apply(color, rough, metal, m, lay, shade=None):
    """lay one layer through its mask -> (color, rough, metal), new arrays. color: (H, W, 3) the sRGB-encoded
    buffer; rough / metal: (H, W, 1) or (H, W, 3); m: (H, W, 1). shade: (H, W, 1) what the occlusion left of the
    surface's colour (1 = open): the layer's tone is darkened by it as the surface below was - rust in a seam is
    as dark as the seam, not a flat patch brighter than the paint round it. A layer without a roughness /
    metalness of its own leaves the surface's."""
    a = (m * np.float32(lay["opacity"])).astype(np.float32)
    tone = encoded(lay["color"])
    color = color * (1 - a) + (tone if shade is None else tone * shade) * a
    if lay.get("rough") is not None:
        rough = rough * (1 - a) + np.float32(max(lay["rough"], ROUGH_MIN)) * a
    if lay.get("metal") is not None:
        metal = metal * (1 - a) + np.float32(lay["metal"]) * a
    return color, rough, metal


def height(m, thick_mm, top):
    """a layer's height over the surface -> (H, W) float32, millimetres. m: (H, W, 1) its mask; top: (H, W) 0..1
    the finer noise that makes its top uneven (UNEVEN of the thickness). Full where the mask passes BANK"""
    body = np.clip(m[..., 0] / BANK, 0, 1)
    body = body * body * (3 - 2 * body)          # (a rounded bank: no crease at its foot or its shoulder)
    return (body * np.float32(thick_mm) * (1.0 - UNEVEN + UNEVEN * top)).astype(np.float32)


def top_noise(n, rng, thick_mm=0.0, px_per_mm=1.0, places=None):
    """the noise of a layer's uneven top -> (n, n) float32 0..1: bumps TOP_WIDE times its thickness across (in
    texels: times the map's texels per mm), TOP_PX texels at the least. places: at each texel's place (noise)"""
    bump = max(TOP_PX, TOP_WIDE * float(thick_mm) * float(px_per_mm))
    cells = max(4, int(round(n / bump)))
    if places is not None and px_per_mm:
        return rbx_wear.fbm3(places[0], places[1], int(rng.integers(1 << 30)), 2, (n / cells) / float(px_per_mm))
    return rbx_wear.fbm(n, rng, octaves=2, cells=cells)


def slopes(height_mm, px_per_mm, own=None):
    """a height field's slope -> (gx, gy), each (H, W) float32: mm of height per mm of surface along the map's x
    and y (rows run bottom-up, +V: the same np.gradient the kit's patterns take). NOT held: hold() does that, once,
    on the layers' slopes together.
    own: (H, W) or (H, W, 1) bool, the texels of the material the layer lies on. A layer that reaches its material's
    border - a UV seam, the next material - does not END there: the height is carried one texel over the border
    before the slope is taken, and there is no slope outside. Without it every seam a layer crossed was drawn as
    a cliff of the layer's whole thickness (3 mm of mud: a 49 degree ridge along each border)."""
    h = height_mm.astype(np.float32)
    o = None
    if own is not None:
        o = own[..., 0] if own.ndim == 3 else own
        p = np.pad(np.where(o, h, -np.inf).astype(np.float32), 1, constant_values=-np.inf)
        near = np.maximum.reduce([p[1:-1, :-2], p[1:-1, 2:], p[:-2, 1:-1], p[2:, 1:-1],
                                  p[:-2, :-2], p[:-2, 2:], p[2:, :-2], p[2:, 2:]])
        h = np.where(o, h, np.where(np.isfinite(near), near, 0.0)).astype(np.float32)
    gy, gx = np.gradient(h)
    k = np.float32(px_per_mm)
    gx, gy = (gx * k).astype(np.float32), (gy * k).astype(np.float32)
    if o is not None:
        gx, gy = np.where(o, gx, np.float32(0.0)), np.where(o, gy, np.float32(0.0))
    return gx, gy


def hold(gx, gy):
    """a slope held to SLOPE_MAX by its SIZE (not each axis on its own: a diagonal slope of 2 and 2 is 2.83, a 70
    degree face) -> (gx, gy), its direction kept"""
    f = np.minimum(1.0, SLOPE_MAX / np.maximum(np.hypot(gx, gy), 1e-9)).astype(np.float32)
    return gx * f, gy * f


def tilts(gx, gy, m):
    """how far a layer's relief tilts the surface -> {"bank": degrees, "top": degrees}: the 95th percentile of the
    slope's angle over its BANK (where it rises: the mask under BANK) and over its TOP (the rest: its lumps). Two
    numbers, because they answer different questions - a broad flat deposit shows by its bank, a lumpy one by its
    top - and one number over the whole layer is the top's alone. 0.0 where there is none"""
    s, mm = np.hypot(gx, gy), m[..., 0]

    def deg(sel):
        return round(float(np.degrees(np.arctan(np.percentile(s[sel], 95.0)))), 1) if sel.any() else 0.0

    return {"bank": deg((mm > 0.02 * BANK) & (mm < 0.98 * BANK)), "top": deg(mm >= 0.98 * BANK)}


def raised(nrm, gx, gy):
    """a tangent-space normal map tilted by a relief's slope -> (H, W, 3) float32 0..1 (encoded as it came).
    nrm: (H, W, 3+) the map 0..1. The relief's own normal (-gx, -gy, 1) is turned into the FRAME of the normal
    that is there (reoriented normal mapping, Barre-Brisebois and Hill 2012): on a flat texel it is that normal;
    on a bevel's tilted one it leans from the bevel - taking the slope off x and y there turned a 63 degree bank
    117 degrees from the bevel's normal. A texel with no slope to speak of (MOVES: a layer's faint rim) is left as
    it was, to the bit (its baked value is not made unit length on the way)."""
    base = nrm[..., :3].astype(np.float32)
    n = base * 2 - 1
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
    d = np.stack([-gx, -gy, np.ones_like(gx)], axis=-1).astype(np.float32)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    t = n + np.array([0.0, 0.0, 1.0], np.float32)
    u = d * np.array([-1.0, -1.0, 1.0], np.float32)
    r = t * ((t * u).sum(-1, keepdims=True) / np.maximum(t[..., 2:3], 1e-4)) - u
    r /= np.linalg.norm(r, axis=-1, keepdims=True) + 1e-6
    moved = (np.hypot(gx, gy) > MOVES)[..., None]
    return np.where(moved, r * 0.5 + 0.5, base).astype(np.float32)


def said(row):
    """a laid layer's row of the report (facts.layers) in a few words: what, where, the share of its place that
    was asked -> the share of the MATERIAL it covers: `rust where chipped 80% -> 5%` (two layers of a kind are told
    apart by their place; asking for more than 100% of a small place is no use: the second number says so); a
    layer whose relief was laid says its thickness, and when the map cannot show it - `, 0.4 mm thick (too flat to
    show: 0.6 deg)` where neither its bank nor its top tilts the surface SHOWS_DEG, `, 12 mm thick (too steep for
    this map: its bank is held at 63 deg)` where the bank is at the hold"""
    where = row["where"]
    place = (f'on the mask "{where[len(PLACED):]}"' if str(where).startswith(PLACED) else PLACES[where])
    out = f'{row["layer"]} {place} {row["asked"]:.0%} -> {row["covered"]:.0%}'
    if row.get("not_laid"):
        return out + " (not laid)"
    if not row["eligible"] and row["asked"]:
        return out + " (nowhere)"
    if row.get("thick_mm") and row.get("covered") and row.get("tilt_deg") is not None:
        out += f', {row["thick_mm"]:g} mm thick'
        if row["tilt_deg"] < SHOWS_DEG:
            out += f' (too flat to show: {row["tilt_deg"]:g} deg)'
        elif row.get("bank_deg", 0.0) >= HELD_DEG:
            out += f' (too steep for this map: its bank is held at {math.degrees(math.atan(SLOPE_MAX)):.0f} deg)'
    return out
