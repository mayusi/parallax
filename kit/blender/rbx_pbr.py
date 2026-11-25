"""rbx_pbr.py — PHYSICALLY BASED values: could a real surface have this base colour, metalness and roughness? Plain
python + numpy, no bpy (kit/test/python/test_pbr.py).

    judge("frame", (0.05, 0.05, 0.055), metal=1.0, rough=0.3)   # -> [problem]: a metal at 66 sRGB is no metal
    a.material("frame", **rbx.finish("gunmetal_parkerized"), wear=0.3)  # the right values for a dark gun finish
    rbx.finish("painted_metal", color=(0.30, 0.05, 0.04))       # a coating takes any colour (metal 0)
    a.material("slide", **rbx.finish("nitride", life="used"))  # + what a life does to it (the Glock's, 85/100)
    a.material("wall", **rbx.real("Brick"), life="used")           # any material: its class from its own values

The rules (the critic's `pbr_values` check):
- METALNESS is 0 or 1. A real surface is a bare metal or it is not (paint, oxide, plastic); a value between is a
  deliberate satin / silk look: a.material(..., satin=True).
- A METAL's base colour IS its reflectance: 180-255 sRGB. Below ~150 sRGB nothing is a bare metal — the dark
  "gunmetal" of a real gun is a COATING (parkerizing, bluing, paint, anodizing: all non-metals) over the steel. A
  darker bare metal (cast iron, tool steel: 150-180 sRGB) reads right only when it is rough (>= 0.45).
- A NON-METAL's base colour is 30-240 sRGB (strict, aaa: 50): charcoal measures 39, fresh snow 237. Blacker or
  whiter than that reads as a hole or a lamp.
A colour this close to a MEASURED material (rbx_materials, physicallybased.info) is that material: its value stands.

Roughness VARIATION (the critic's `roughness_variation`, measured on the baked roughness map): real surfaces are
never one roughness — smudges, wear, grime, machining marks. rough_zones() measures every material's zone of the map
at three scales (fine: a few texels; mid: tens; coarse: the zone's large patches); judge_variation() names a material
that covers a real share of the surface and is flat at two of them.
"""

import math
import re

import numpy as np

import rbx_materials

# ---- base colour, as the sRGB 0-255 value of a grey with the same luminance (what a colour picker shows)
# METALS: Allegorithmic / Adobe "The PBR Guide" vol. 2 — raw metal reflectance is 70-100% specular, 180-255 sRGB;
# physicallybased.info's measured metals (kit/materials/physicallybased.json) run from 159 (silicon) to 254 (silver)
METAL_SRGB = (180, 255)
METAL_FLOOR_SRGB = 150  # below this no bare metal exists: it is a coating (a dielectric), so metal 0
DARK_METAL_ROUGH = 0.45  # 150-180 sRGB is a darker bare metal (cast, worn, tool steel) only when it is this rough
# NON-METALS: The PBR Guide — 30-240 sRGB, 50 the strict floor (charcoal measures 39 sRGB, fresh snow 237)
NONMETAL_SRGB = (30, 240)
NONMETAL_STRICT_SRGB = 50
# METALNESS: Roblox's SurfaceAppearance docs — metalness 0 or 1; partial only for a deliberate satin / silk look.
# Within this of 0 or of 1 counts as 0 or 1
METAL_BINARY = 0.15
MATCH_DE = 3.0  # Lab units (~ a just-noticeable difference): this close to a measured material IS that material
# the measured metals a fix suggests (things are made of these; silicon or caesium is no answer for a gun frame)
SUGGEST_METALS = ("Iron", "Stainless Steel", "Titanium", "Aluminum", "Chromium", "Nickel", "Zinc", "Copper", "Brass",
                  "Gold", "Silver")

# ---- roughness variation, measured on the baked map (p10-p90 spread of the roughness within a material's zone)
MEASURE = 1  # the version of zone_map + rough_zones: part of the bake cache key — bump it when they change
FLAT_SPREAD = 0.02  # less than 2% of the roughness range between the 10th and 90th percentile: flat, at that scale
FLAT_SHARE = 0.05  # a material covering under 5% of the baked surface is detail: not judged
SCALES = ("fine", "mid", "coarse")


def to_srgb(c):
    """linear 0..1 -> sRGB 0..1 (the IEC 61966-2-1 curve)"""
    c = min(1.0, max(0.0, float(c)))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def to_linear(s):
    """sRGB 0..1 -> linear"""
    s = min(1.0, max(0.0, float(s)))
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def luminance(color):
    r, g, b = (float(c) for c in tuple(color)[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def srgb(color):
    """a linear colour's brightness, 0-255: the sRGB value of the grey with the same luminance"""
    return round(255 * to_srgb(luminance(color)))


def scale_to(color, srgb_value):
    """the same hue at another brightness (sRGB 0-255 of its luminance); channels stay <= 1"""
    y = max(luminance(color), 1e-6)
    k = to_linear(srgb_value / 255.0) / y
    if all(float(c) <= 1e-6 for c in tuple(color)[:3]):
        v = to_linear(srgb_value / 255.0)
        return (round(v, 3),) * 3
    return tuple(round(min(1.0, float(c) * k), 3) for c in tuple(color)[:3])


def _measured(metal):
    """[(name, linear colour)] of the measured metals (metal=True) or the measured non-metals whose own base colour
    is inside the non-metal range (lab coatings like Musou Black, and clear things like glass, are no paint target)"""
    out = []
    for name in rbx_materials.load():
        v = rbx_materials.real(name)
        if (v["metal"] >= 0.5) != metal:
            continue
        if not metal and not (NONMETAL_SRGB[0] <= srgb(v["color"]) <= NONMETAL_SRGB[1]):
            continue
        out.append((name, v["color"]))
    return out


def nearest(color, metal, lightness_weight=1.0, among=None):
    """-> (name, linear colour, Lab distance) of the measured material closest to `color` (metals or non-metals;
    `among`: only these names). lightness_weight < 1 ranks by hue and saturation first (a too-dark metal's nearest
    REAL metal of its tint)."""
    lab = rbx_materials._lab(color)
    best = None
    for name, c in _measured(metal):
        if among is not None and name not in among:
            continue
        ref = rbx_materials._lab(c)
        d = math.sqrt((lightness_weight * (lab[0] - ref[0])) ** 2 + (lab[1] - ref[1]) ** 2 + (lab[2] - ref[2]) ** 2)
        if best is None or d < best[2]:
            best = (name, c, d)
    return best


def _is_measured(color, metal):
    hit = nearest(color, metal)
    return hit is not None and hit[2] <= MATCH_DE


def _fmt(color):
    return "(" + ", ".join(f"{float(c):.3f}".rstrip("0").rstrip(".") if float(c) else "0" for c in color[:3]) + ")"


def _coating(color, strict=False):
    """the material's own colour as a COATING (metal 0), brought inside the non-metal range"""
    lo = NONMETAL_STRICT_SRGB if strict else NONMETAL_SRGB[0]
    v = srgb(color)
    c = scale_to(color, lo + 8) if v < lo else scale_to(color, NONMETAL_SRGB[1]) if v > NONMETAL_SRGB[1] else color
    return f"make it a painted / coated finish: metal 0, base ~{_fmt(c)} ({srgb(c)} sRGB)"


def _bare(color):
    name, c, _ = nearest(color, True, among=SUGGEST_METALS)
    return f'a bare metal: **rbx.real("{name}") ({srgb(c)} sRGB)'


def _problem(name, what, fix):
    return {"material": name, "what": what, "fix": fix}


def say(problem):
    """one problem as a line: '<material>: <what> — <fix>'"""
    return f"{problem['material']}: {problem['what']} — {problem['fix']}"


def judge(name, color, metal, rough, satin=False, strict=False, glow=False, clear=False):
    """-> [problem] ({"material", "what", "fix"}) — what about this material no real surface has, each with its fix
    (the nearest measured material, or the coating it really is). satin=True: a partial metalness is meant (a satin /
    silk look). strict (aaa): a non-metal no darker than 50 sRGB. glow / clear: the base colour is a light or a tint
    (an emissive, a see-through material) — only its metalness is judged."""
    color = tuple(float(c) for c in tuple(color)[:3])
    m, r, v = float(metal), float(rough), srgb(color)
    out = []
    if METAL_BINARY < m < 1 - METAL_BINARY and not satin:
        out.append(_problem(name, f"metal {m:.2f} is half a metal (base {v} sRGB)",
                            f"metalness is 0 or 1 — {_coating(color, strict)} (**rbx.finish(\"painted_metal\", "
                            f"color=...)), or {_bare(color)}; a satin / silk look on purpose: "
                            "a.material(..., satin=True)"))
        return out
    if glow or clear:
        return out
    # (a measured match excuses only the soft bands: the darker-metal band and the strict non-metal floor — every
    # measured metal is 159+ sRGB and every measured opaque non-metal inside 30-240, so the hard bounds need none)
    if m >= 0.5:
        if v < METAL_FLOOR_SRGB:
            out.append(_problem(name, f"a metal at {v} sRGB (real metals are {METAL_SRGB[0]}-{METAL_SRGB[1]})",
                                f"this dark a finish is a coating, not the metal — {_coating(color, strict)} "
                                "(**rbx.finish(\"gunmetal_parkerized\") / \"blued_steel\" / \"black_anodized\"), or "
                                f"{_bare(color)}"))
        elif v < METAL_SRGB[0] and r < DARK_METAL_ROUGH and not _is_measured(color, True):
            out.append(_problem(name, f"a darker metal ({v} sRGB) polished to rough {r:.2f}",
                                f"a darker bare metal (cast iron, tool steel: {METAL_FLOOR_SRGB}-{METAL_SRGB[0]} sRGB) "
                                f"is rough: rough >= {DARK_METAL_ROUGH} (**rbx.finish(\"dark_steel\")), or "
                                f"{_bare(color)}"))
        return out
    lo = NONMETAL_STRICT_SRGB if strict else NONMETAL_SRGB[0]
    if v < NONMETAL_SRGB[0] or (v < lo and not _is_measured(color, False)):
        out.append(_problem(name, f"a non-metal at {v} sRGB (real ones are {lo}-{NONMETAL_SRGB[1]}; charcoal is 39)",
                            f"blacker than any paint or natural surface (only a lab light-trap is) — base "
                            f"~{_fmt(scale_to(color, lo + 8))} ({lo + 8} sRGB); black rubber: **rbx.real(\"Tire\"), "
                            'black polymer: **rbx.finish("polymer")'))
    elif v > NONMETAL_SRGB[1]:
        out.append(_problem(name, f"a non-metal at {v} sRGB (real ones are {lo}-{NONMETAL_SRGB[1]}; fresh snow is "
                                  "237)",
                            f"whiter than any opaque surface (a see-through one: alpha < 1) — base "
                            f"~{_fmt(scale_to(color, NONMETAL_SRGB[1] - 5))} ({NONMETAL_SRGB[1] - 5} sRGB); white "
                            "paint: **rbx.finish(\"enamel\")"))
    return out


def judge_under(name, under):
    """chip > 0 wears paint through to `under`, which the bake makes a bare METAL (metal 1): it must be one"""
    v = srgb(under)
    if v >= METAL_FLOOR_SRGB:
        return []
    return [_problem(name, f"chips show under={_fmt(under)} as bare metal at {v} sRGB",
                     f"what paint wears through to is bare metal ({METAL_SRGB[0]}+ sRGB): under=(0.56, 0.57, 0.6) "
                     f'(the default: bare steel) or rbx.real("Iron")["color"]; a dark primer is no metal — '
                     "lower chip= instead")]


# ---- finishes: the right values for the surfaces a model asks for most (built on measured entries where they exist)
def _mix(a, b, t, k=1.0):
    ca, cb = rbx_materials.real(a)["color"], rbx_materials.real(b)["color"]
    return tuple(round(k * ((1 - t) * x + t * y), 3) for x, y in zip(ca, cb))


FINISHES = {
    # COATINGS on metal (dielectrics: metal 0 — the dark look IS the coating, the steel is under it)
    "gunmetal_parkerized": ((0.045, 0.046, 0.048), 0.0, 0.65,
                            "manganese-phosphate parkerizing: matte grey-black, ~60 sRGB"),
    "blued_steel": ((0.032, 0.036, 0.05), 0.0, 0.3, "hot / rust bluing: a thin black oxide, blue-black, oiled sheen"),
    "black_anodized": ((0.04, 0.04, 0.042), 0.0, 0.35, "anodized aluminium: a dyed oxide layer, satin black"),
    "nitride": ((0.033, 0.033, 0.034), 0.0, 0.2,
                "black nitride / nDLC on steel (a pistol slide): near-black with a slick sheen — the owner-rated Glock's "
                "slide (85/100, 2026-10-10: 0.028 there, 47 sRGB; the preset sits at the strict 50 floor)"),
    "painted_metal": ((0.18, 0.18, 0.18), 0.0, 0.5, "paint on metal: any colour (color=...), mid-gloss"),
    "enamel": ("Porcelain", 0.0, 0.12, "vitreous / enamel paint: glossy, porcelain-white unless color=..."),
    "pearl_paint": ("Pearl", 0.0, 0.25, "pearlescent paint: nacre-white, glossy clear coat"),
    "polymer": ((0.05, 0.05, 0.052), 0.0, 0.6, "black polymer (glass-filled nylon): a gun frame, a grip"),
    "rubber": ("Tire", 0.0, 0.85, "black rubber: grips, pads, tyres (measured tyre)"),
    # BARE metals (metal 1, measured base colours; the roughness is the finish)
    "machined_steel": ("Stainless Steel", 1.0, 0.3, "bare machined steel"),
    "dark_steel": (lambda: _mix("Iron", "Iron", 0, 0.78), 1.0, 0.55,
                   "a darker bare steel (cast, tool steel, worn): ~170 sRGB, rough — the darkest a bare metal goes"),
    "brushed_aluminium": ("Aluminum", 1.0, 0.45, "brushed aluminium"),
    "chrome": ("Chromium", 1.0, 0.08, "polished chrome plate"),
    "polished_brass": ("Brass", 1.0, 0.2, "polished brass"),
    "cast_bronze": (lambda: _mix("Copper", "Brass", 0.4, 0.85), 1.0, 0.55,
                    "cast bronze (copper + tin: between measured copper and brass, a cast surface)"),
}


# LIFE — what an object's life does to ITS SURFACE, for any material: a.material(name, ..., life="used") or
# a.material(name, **rbx.finish("nitride", life="used")) — as a.material's wear keys (wear, grime, burnish, burnish_mm,
# smudge, rub, chip), each one you also give a.material yourself winning (life="used", rub=0.8: a holster zone).
# The class comes from the material itself (life_class): a bare metal, a dark coating, a dark polymer / rubber, paint
# (under= given, or a paint finish), or a lighter non-metal (wood, stone, fabric, a light plastic).
# "used" is the owner-rated Glock's (85/100, 2026-10-10, a pistol carried in a holster): the slide's nDLC (a dark
# COATING: edges burnished to a satin grey 2.5 mm wide, flats rubbed in patches, handling smudges, dust in the
# serrations) and the frame's polymer (the same story, softer). Fresh judges read anything less on a dark finish as
# "no wear at all" (eight in a row at a 1 mm burnish). "light" (kept indoors, used) is half of it, "heavy" (a hard
# life) half again more. Chips are for PAINT only: on a black gun they read as bake artifacts.
LIFE_LEVELS = {"new": 0.0, "light": 0.5, "used": 1.0, "heavy": 1.5}
LIFE_ALIASES = {"handled": "light", "carried": "used", "worn": "heavy"}   # (the words the Glock's were tuned in)
_BURNISH_MM = {"new": 0.4, "light": 0.6, "used": 1.0, "heavy": 1.25}   # (x the class's band width)
WEAR_KEYS = ("wear", "chip", "grime", "burnish", "burnish_mm", "smudge", "rub")
WEAR_DEFAULTS = {"wear": 0.0, "chip": 0.0, "grime": 0.0, "burnish": 0.0, "burnish_mm": 1.0, "smudge": 0.0, "rub": 0.0}
LIFE_CLASS = {  # each class's keys at "used"
    "coating": dict(wear=0.6, grime=0.35, burnish=0.9, burnish_mm=2.5, smudge=0.5, rub=0.3),   # the Glock's slide
    "polymer": dict(wear=0.2, grime=0.25, burnish=0.55, burnish_mm=2.0, smudge=0.3, rub=0.15),  # its frame
    "paint": dict(wear=0.3, grime=0.25, chip=0.35, smudge=0.3),
    "bare": dict(wear=0.4, grime=0.2, smudge=0.5),
    # a LIGHTER non-metal (wood, stone, fabric, leather, a light plastic): dirt in its recesses and handling marks —
    # no burnish (it only ever lightens: nothing to lift a light surface toward) and no chips (nothing painted)
    "dielectric": dict(wear=0.35, grime=0.35, smudge=0.3),
}
FINISH_CLASS = {"gunmetal_parkerized": "coating", "blued_steel": "coating", "black_anodized": "coating",
                "nitride": "coating", "polymer": "polymer", "rubber": "polymer", "painted_metal": "paint",
                "enamel": "paint", "pearl_paint": "paint"}   # (the other finishes: bare metals)


def life_class(color, metal, rough, finish=None, painted=False):
    """which life story a surface has: a named finish's own, else from its values — a metal is bare; a painted one
    (under= given) chips; a dark non-metal (DARK_SRGB) burnishes, smooth (a coating) or rough (a polymer, a rubber);
    anything lighter gathers dirt and handling marks"""
    if finish in FINISH_CLASS:
        return FINISH_CLASS[finish]
    if finish in FINISHES or float(metal) >= 0.5:
        return "bare"
    if painted:
        return "paint"
    if srgb(color) <= DARK_SRGB:
        return "coating" if float(rough) <= 0.45 else "polymer"
    return "dielectric"


def life_of(level, color, metal, rough, finish=None, painted=False):
    """a surface's wear keys at a life level (LIFE_LEVELS, or an alias) -> {wear, grime, burnish, ...}"""
    level = LIFE_ALIASES.get(level, level)
    if level not in LIFE_LEVELS:
        raise KeyError(f'life "{level}" — use one of {", ".join(LIFE_LEVELS)} (or {", ".join(LIFE_ALIASES)})')
    k = LIFE_LEVELS[level]
    out = {}
    for key, v in LIFE_CLASS[life_class(color, metal, rough, finish, painted)].items():
        out[key] = round(v * _BURNISH_MM[level], 2) if key == "burnish_mm" else round(min(1.0, v * k), 3)
    return out


def resolve_life(given, life, color, metal, rough, finish=None, painted=False):
    """a.material's wear keys resolved: each one GIVEN (not None) stands; the rest come from the life level, else
    their defaults (WEAR_DEFAULTS) -> {key: float} for every WEAR_KEYS"""
    lived = life_of(life, color, metal, rough, finish, painted) if life is not None else {}
    return {k: float(given[k]) if given.get(k) is not None else float(lived.get(k, WEAR_DEFAULTS[k]))
            for k in WEAR_KEYS}


def finish(name, color=None, rough=None, life=None):
    """a finish's material() keywords: {"color": linear rgb, "metal": 0 or 1, "rough"} — color= / rough= override
    (a coating takes any colour; the critic still judges what you give it). life="new" | "light" | "used" | "heavy":
    passed on to a.material, which wears it as THIS finish's class (LIFE_CLASS) — any wear key you give a.material
    yourself wins: a.material("slide", **rbx.finish("nitride", life="used"), rub=0.8)"""
    if name not in FINISHES:
        raise KeyError(f'finish "{name}" — use one of {", ".join(FINISHES)}')
    base, metal, r, _about = FINISHES[name]
    if callable(base):
        base = base()
    elif isinstance(base, str):
        base = rbx_materials.real(base)["color"]
    c = tuple(float(x) for x in (color if color is not None else base)[:3])
    out = {"color": c, "metal": float(metal), "rough": float(r if rough is None else rough)}
    if life is not None:
        life_of(life, c, metal, out["rough"], name)   # (an unknown level fails HERE, at the line that named it)
        out.update({"life": life, "finish": name})
    return out


def finishes():
    """[(name, kwargs, about)] — every finish with its values"""
    return [(n, finish(n), FINISHES[n][3]) for n in FINISHES]


# ---- dark finishes (the critic's `dark_finishes`): what the Glock taught (owner 85/100, 2026-10-10). Its polymer frame
# at 57 sRGB beside its 47 sRGB slide: two fresh judges read both "the same blue-navy" — one mass; at 73 / 47 they were
# two materials (and 86 / 47 is the build the owner rated). And a dark finish with no edge wear read as "no wear at
# all" to eight judges in a row.
DARK_SRGB = 90     # a dark finish: at most this bright (the sRGB grey of its luminance)
DARK_STEP = 15     # two big dark materials closer than this read as ONE mass under a studio light
DARK_MAIN = 0.12   # "big": at least this share of the model's VISIBLE surface


def dark_story(rows, worn=False):
    """rows: [{"name", "color" (linear), "metal", "area" (visible), "burnish", "rub", "emit"}] -> {"main": [(name,
    share, srgb)], "alike": [(a, b, srgb_a, srgb_b)], "unworn": [name]}. alike: two big dark non-metals within
    DARK_STEP of each other. unworn (only when worn=True: a hero, seen up close): a big dark non-metal with no
    burnish, rub or chips (a.material(..., life="used") gives its class's)."""
    total = sum(max(0.0, float(r.get("area") or 0.0)) for r in rows) or 1.0
    big = [r for r in rows if (r.get("area") or 0.0) / total >= DARK_MAIN and not r.get("emit")]
    main = [(r["name"], round(r["area"] / total, 3), srgb(r["color"])) for r in big]
    dark = sorted((r for r in big if float(r.get("metal") or 0.0) < 0.5 and srgb(r["color"]) <= DARK_SRGB),
                  key=lambda r: -r["area"])
    alike = []
    for i, a in enumerate(dark):
        for b in dark[i + 1:]:
            va, vb = srgb(a["color"]), srgb(b["color"])
            if abs(va - vb) < DARK_STEP:
                alike.append((a["name"], b["name"], va, vb))
    unworn = [r["name"] for r in dark if worn and not any(float(r.get(k) or 0.0) for k in ("burnish", "rub", "chip"))]
    return {"main": main, "alike": alike, "unworn": unworn}


# ---- roughness variation on the baked map
def _blur(a, r):
    """two box passes of radius r (~ a gaussian), edge-padded (as rbx._blur)"""
    out = a
    k = 2 * r + 1
    for _ in range(2):
        c = np.cumsum(np.pad(out, ((0, 0), (r + 1, r)), mode="edge"), axis=1)
        out = (c[:, k:] - c[:, :-k]) / k
        c = np.cumsum(np.pad(out, ((r + 1, r), (0, 0)), mode="edge"), axis=0)
        out = (c[k:, :] - c[:-k, :]) / k
    return out


def _runs(n):
    """0..n[i]-1 for every i, concatenated (the offsets inside each run of np.repeat(..., n))"""
    return np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)


def zone_map(tri_uv, tri_zone, size, rows_per_pass=2000000):
    """UV triangles -> (size, size) int32 map of the zone (material slot) whose triangle covers each texel CENTRE —
    the texels a bake writes — and -1 where none does. tri_uv: (n, 3, 2) UVs 0..1; row 0 is v = 0 (Blender's pixel
    order). Scanline, all triangles at once: every texel row a triangle crosses gets the span between its edges."""
    uv = np.asarray(tri_uv, dtype=np.float64).reshape(-1, 3, 2) * size
    zones = np.asarray(tri_zone, dtype=np.int32).reshape(-1)
    out = np.full((size, size), -1, dtype=np.int32)
    y0 = np.clip(np.ceil(uv[:, :, 1].min(axis=1) - 0.5), 0, size).astype(np.int64)  # first row whose centre is in
    y1 = np.clip(np.floor(uv[:, :, 1].max(axis=1) - 0.5), -1, size - 1).astype(np.int64)
    rows = np.maximum(0, y1 - y0 + 1)
    end = np.cumsum(rows)
    start = 0
    while start < len(uv):  # (in passes of ~rows_per_pass rows: memory stays bounded on a 2048 master)
        stop = max(start + 1, int(np.searchsorted(end, end[start] - rows[start] + rows_per_pass, "right")))
        t = np.repeat(np.arange(start, stop), rows[start:stop])
        yc = (y0[t] + _runs(rows[start:stop])).astype(np.float64) + 0.5
        lo, hi = np.full(len(t), np.inf), np.full(len(t), -np.inf)
        for i, j in ((0, 1), (1, 2), (2, 0)):
            p, q = uv[t, i], uv[t, j]
            dy = q[:, 1] - p[:, 1]
            on = (np.minimum(p[:, 1], q[:, 1]) <= yc) & (yc <= np.maximum(p[:, 1], q[:, 1])) & (dy != 0)
            x = p[:, 0] + (yc - p[:, 1]) / np.where(dy != 0, dy, 1.0) * (q[:, 0] - p[:, 0])
            lo, hi = np.where(on, np.minimum(lo, x), lo), np.where(on, np.maximum(hi, x), hi)
        x0 = np.clip(np.ceil(lo - 0.5), 0, size).astype(np.int64)
        x1 = np.clip(np.floor(hi - 0.5), -1, size - 1).astype(np.int64)
        n = np.where(np.isfinite(lo), np.maximum(0, x1 - x0 + 1), 0)
        row = np.repeat((yc - 0.5).astype(np.int64), n)
        out[row, np.repeat(x0, n) + _runs(n)] = np.repeat(zones[t], n)
        start = stop
    return out


def _spread(x, n_min=24):
    """p10..p90 of the values (None when too few to say)"""
    x = np.asarray(x).ravel()
    if len(x) < n_min:
        return None
    lo, hi = np.percentile(x, (10, 90))
    return round(float(hi - lo), 4)


def one_zone(zone, r):
    """the texels whose whole (4r + 1)-texel square is ONE zone (the map's border counts as another) -> bool map.
    A square is one zone exactly when no two neighbours inside it differ: the zone map's horizontal and vertical
    steps, counted over each square with two summed-area tables - the same map as comparing all (4r + 1)^2 shifted
    copies with the centre (289 passes over a 4096 map: 2.1 s of every bake's roughness check; 0.55 s this way)"""
    size = zone.shape[0]
    k = 4 * r
    pad = np.pad(zone, 2 * r, mode="constant", constant_values=-2)
    p = size + k
    eh = np.zeros((p + 1, p), np.int32)        # the steps between x and x + 1
    np.cumsum(pad[:, 1:] != pad[:, :-1], axis=1, dtype=np.int32, out=eh[1:, 1:])
    np.cumsum(eh[1:, 1:], axis=0, out=eh[1:, 1:])
    ev = np.zeros((p, p + 1), np.int32)        # the steps between y and y + 1
    np.cumsum(pad[1:, :] != pad[:-1, :], axis=0, dtype=np.int32, out=ev[1:, 1:])
    np.cumsum(ev[1:, 1:], axis=1, out=ev[1:, 1:])
    # the square of texel (y, x) spans pad rows y .. y + k and columns x .. x + k
    h = eh[k + 1:k + 1 + size, k:k + size] - eh[0:size, k:k + size] - eh[k + 1:k + 1 + size, 0:size] + eh[0:size, 0:size]
    v = ev[k:k + size, k + 1:k + 1 + size] - ev[0:size, k + 1:k + 1 + size] - ev[k:k + size, 0:size] + ev[0:size, 0:size]
    return (h == 0) & (v == 0)


def rough_zones(rough, zone, names):
    """the roughness map's variation inside each material's zone, at three scales -> {name: {"texels", "of" (all the
    map's baked texels), "share", "fine", "mid", "coarse"}} (p10-p90 spreads, roughness units; None: the zone is too
    small to measure that scale).
    rough: (size, size) 0..1; zone: zone_map(); names[i]: the material of zone i (None: not judged).
      fine   — texel-level: scratches, machining, a pattern's cells (the map minus its ~2-texel blur)
      mid    — blotches tens of texels across (4-texel blocks minus their ~16-texel neighbourhood)
      coarse — the zone's large patches and gradients (the ~16-texel neighbourhood across the whole zone)
    Each is measured inside the zone only (masked averages): a neighbouring material's roughness never counts."""
    rough = np.asarray(rough, dtype=np.float32)
    zone = np.asarray(zone)
    size = rough.shape[0]
    covered = max(1, int((zone >= 0).sum()))
    # fine: the map minus its blur (radius 1 texel at 1024, 2 at 2048: the kit's patterns scale with the map), only
    # where the blur's whole reach (2 radii) is the same zone
    r = max(1, size // 1024)
    same = one_zone(zone, r)
    fine_band = rough - _blur(rough, r)
    # mid / coarse on a grid of blocks (4 texels at 1024: the same share of the map at any size)
    f = max(1, size // 256)
    n = size // f
    out = {}
    for z, name in enumerate(names):
        if name is None:
            continue
        m = zone == z
        count = int(m.sum())
        if count == 0:
            continue
        mf = m[:n * f, :n * f].astype(np.float32)
        w = mf.reshape(n, f, n, f).mean(axis=(1, 3))
        rs = (rough[:n * f, :n * f] * mf).reshape(n, f, n, f).mean(axis=(1, 3))
        avg = rs / np.maximum(w, 1e-6)  # each block's own roughness (its texels of this zone only)
        wb = _blur(w, 4)
        near = _blur(rs, 4) / np.maximum(wb, 1e-6)  # the zone's roughness around it (~16 texels at 1024)
        full = (w > 0.75) & (wb > 0.25)
        out[name] = {"texels": count, "of": covered, "share": round(count / covered, 4),
                     "fine": _spread(fine_band[m & same]),
                     "mid": _spread((avg - near)[full]),
                     "coarse": _spread(near[full])}
    return out


def merge_zones(per_map):
    """rough_zones() of several maps (one per mesh group) -> one entry per material: texels summed, every scale the
    texel-weighted mean of the maps that measured it, the share of all the maps' baked texels"""
    covered = sum(max((v["of"] for v in zones.values()), default=0) for zones in per_map) or 1
    out = {}
    for zones in per_map:
        for name, v in zones.items():
            o = out.setdefault(name, {"texels": 0, **{s: [0.0, 0] for s in SCALES}})
            o["texels"] += v["texels"]
            for s in SCALES:
                if v.get(s) is not None:
                    o[s][0] += v[s] * v["texels"]
                    o[s][1] += v["texels"]
    return {name: {"texels": o["texels"], "share": round(o["texels"] / covered, 4),
                   **{s: (round(o[s][0] / o[s][1], 4) if o[s][1] else None) for s in SCALES}}
            for name, o in out.items()}


_SCAN_HINTS = (("leather", "Leather"), ("bark", "Bark"), ("moss", "Bark013"), ("wood", "Wood"), ("plank", "Wood"),
               ("stone", "Concrete"), ("concrete", "Concrete"), ("rock", "Rock"), ("brick", "Bricks"),
               ("rust", "Rust"), ("burlap", "Fabric061"), ("hessian", "Fabric061"), ("sack", "Fabric061"),
               ("wool", "Fabric019"), ("fabric", "Fabric"), ("cloth", "Fabric"), ("cotton", "Fabric"),
               ("plastic", "Plastic"), ("polymer", "Plastic"), ("grip", "Plastic"))   # (the specific before the general)
# a METAL's words: rust streaks / oxide on steel (a scan whose own metal map says where it is not metal)
_METAL_HINTS = (("rust", "Metal021"), ("old", "Metal021"), ("brass", "Metal048C"), ("blued", "Metal063"))
_ENDINGS = ("s", "es", "y", "ed", "en", "ty")


def scan_for(name, metal, available=None):
    """a scanned surface (rbx_scans) that suits a material, from the scans this machine has — or None"""
    if available is None:
        import rbx_scans  # noqa: PLC0415

        available = rbx_scans.available()
    words = re.sub(r"[^a-z]+", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", name or "").lower()).split()

    def said(w):   # a whole word, the word with a plain ending ("rusty", "planks", "wooden", "mossy"), or the end of a
        # compound ("hardwood", "plywood", "cobblestone": hints of 4+ letters) — never "gold" for "old", "rocket" for "rock"
        return any(t == w or (t.startswith(w) and t[len(w):] in _ENDINGS) or (len(w) >= 4 and t.endswith(w))
                   for t in words)

    wants = ([p for w, p in _METAL_HINTS if said(w)] + ["Metal"] if metal >= 0.5
             else [p for w, p in _SCAN_HINTS if said(w)] + ["Plastic"])
    for prefix in wants:
        hits = [s for s in available if s.startswith(prefix)]
        if hits:
            return hits[0]
    return None


def judge_variation(zones, spec_of, available=None):
    """zones: merge_zones() -> [problem] for every material covering FLAT_SHARE+ of the baked surface whose roughness
    is flat (spread < FLAT_SPREAD) at two of the three scales. spec_of(name) -> its material() settings (metal, wear,
    grime, pattern, scan): the fix names what it does not have yet."""
    out = []
    for name, z in sorted(zones.items(), key=lambda kv: -kv[1]["share"]):
        if z["share"] < FLAT_SHARE:
            continue
        flat = [s for s in SCALES if z.get(s) is not None and z[s] < FLAT_SPREAD]
        if len(flat) < 2:
            continue
        spec = spec_of(name) or {}
        if spec.get("scan") and "fine" not in flat and z.get("fine") is not None:
            # (a SCANNED surface varying at the fine scale is the real one's grain: a new wooden chair is even at
            #  mid / coarse scale — the kit make chair the owner liked failed here on 100% of builds; flat at
            #  every scale, or with no scan, is still plastic)
            continue
        metal = float(spec.get("metal") or 0.0)
        scan = None if spec.get("scan") else scan_for(name, metal, available)
        cures = [f'scan="{scan}" (a real surface\'s roughness at every scale)'] if scan else []
        if "fine" in flat and not spec.get("pattern"):
            cures.append(f'pattern="{"brushed" if metal >= 0.5 else "coat"}" (fine)')
        if "mid" in flat or "coarse" in flat:
            more = [f"{k}=0.4" for k in ("wear", "grime") if float(spec.get(k) or 0.0) < 0.4]
            if more:
                cures.append(" + ".join(more) + " (mid and coarse)")
        if spec.get("scan"):
            cures.append("more of its scan (scan_mix toward 1)")
        said = " / ".join(f"{z[s]:.3f}" if z.get(s) is not None else "-" for s in SCALES)
        out.append(_problem(name, f"{z['share']:.0%} of the surface at one roughness ({said} fine / mid / coarse, "
                                  f"flat under {FLAT_SPREAD})",
                            "flat roughness reads as plastic — give it " + ", or ".join(cures or ["wear / grime"])))
    return out
