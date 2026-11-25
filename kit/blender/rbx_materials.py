"""rbx_materials.py — REAL materials: measured albedo, metalness and roughness of 86 materials (physicallybased.info,
CC0 — kit/materials/physicallybased.json, vetted 2026-10-06 in VETLOG.md). Plain python, no bpy.

    a.material("brass", **rbx.real("Brass"), wear=0.3)     # measured brass, machined finish
    a.material("tire", **rbx.real("Tire", rough=0.8))      # any value can be overridden
    find("rubber")  -> ["Tire"]                            # by name, tag or category
    lune run kit materials [query]                         # the list, with values

Colours are LINEAR, what Principled BSDF's Base Color takes (the grey card is 0.18). A measured metal is a polished
mirror (roughness 0) and nothing in a game is one: real() gives a measured 0 the roughness of a machined surface (0.3)
unless rough= says otherwise (brushed ~0.45, cast / worn ~0.6). The critic uses check() to warn when a material NAMED
like a real one (gold, brass, copper, chrome, tyre, concrete ...) looks nothing like it: yellow plastic "gold"
reads as a toy.
"""

import json
import math
import os
import re

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "materials", "physicallybased.json")
MACHINED = 0.3  # the roughness real() gives a measured perfect mirror

# material NAMES that promise a real look -> the library entry they promise. Only surfaces whose look IS the substance:
# "steel" / "iron" / "plastic" / "wood" are left out (a steel part is as often painted, blued or parkerised)
PROMISES = {"gold": "Gold", "golden": "Gold", "brass": "Brass", "copper": "Copper", "silver": "Silver",
            "chrome": "Chromium", "chromium": "Chromium", "chromed": "Chromium", "aluminum": "Aluminum",
            "aluminium": "Aluminum", "tire": "Tire", "tyre": "Tire", "concrete": "Concrete"}  # (rubber comes in colours)
# ... unless the name says the surface is something else on top
COVERED = {"paint", "painted", "coat", "coated", "dark", "black", "worn", "dirty", "rust", "rusty", "oxidized",
           "oxidised", "patina", "anodized", "anodised", "blued", "tinted", "stained", "plastic", "fake", "toy",
           "glow", "emissive", "light", "decal", "label", "text", "stripe", "stripes", "trim"}
DE_WARN = 25.0  # Lab difference above which a named material is "nothing like" the real one

_cache = {}


def load():
    """{name: entry} — the database (read once)"""
    if not _cache:
        with open(DATA, encoding="utf-8") as fh:
            for m in json.load(fh):
                _cache[m["name"]] = m
    return _cache


def _entry(name):
    lib = load()
    if name in lib:
        return lib[name]
    low = {k.lower(): k for k in lib}
    if name.lower() in low:
        return lib[low[name.lower()]]
    hits = find(name)
    if len(hits) == 1:
        return lib[hits[0]]
    raise KeyError(f'real: no material "{name}"' + (f" — did you mean {', '.join(hits[:6])}?" if hits else
                                                     " (lune run kit materials lists them)"))


def real(name, rough=None):
    """the measured material as material() keywords: {"color": linear rgb (<= 1), "metal": 0..1, "rough": 0..1}"""
    m = _entry(name)
    color = tuple(round(min(1.0, max(0.0, float(c))), 4) for c in (m.get("color") or [0.5, 0.5, 0.5])[:3])
    metal = float(m.get("metalness") or 0.0)
    measured = m.get("roughness")
    if rough is None:
        # a measured 0 is a lab mirror: a METAL gets a machined 0.3 (a game's mirror-metal reads black); a non-metal
        # (glass, water, a lacquer) keeps its smoothness — 0.05, a hair off perfect
        smooth = measured is None or float(measured) <= 0.0
        rough = (MACHINED if metal >= 0.5 else 0.05) if smooth else float(measured)
    return {"color": color, "metal": metal, "rough": float(rough)}


def find(query):
    """library names whose name, tags or category contain the query (case-insensitive), best (name) matches first"""
    q = (query or "").strip().lower()
    lib = load()
    if not q:
        return sorted(lib)
    by_name = [n for n in lib if q in n.lower()]
    by_tag = [n for n, m in lib.items() if n not in by_name and any(q in str(t).lower() for t in
                                                                   (m.get("tags") or []) + (m.get("category") or []))]
    return sorted(by_name) + sorted(by_tag)


def _lab(rgb):
    """linear sRGB (D65) -> CIE Lab"""
    r, g, b = (min(1.0, max(0.0, float(c))) for c in rgb[:3])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def promise(material_name):
    """the library entry a material's NAME promises ("gold_trim" -> None: trim; "Gold" -> "Gold"), or None"""
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", material_name or "").lower()
    tokens = [t for t in re.split(r"[^a-z]+", words) if t]
    if any(t in COVERED for t in tokens):
        return None
    for t in tokens:
        if t in PROMISES:
            return PROMISES[t]
    return None


def check(material_name, color, metal):
    """-> None, or why a material NAMED like a real one looks nothing like it (colour in Lab, metal or not)"""
    target = promise(material_name)
    if not target:
        return None
    ref = real(target)
    de = math.dist(_lab(color), _lab(ref["color"]))
    metal_wrong = (float(metal) >= 0.5) != (ref["metal"] >= 0.5)
    if de <= DE_WARN and not metal_wrong:
        return None
    what = []
    if de > DE_WARN:
        what.append(f"colour {de:.0f} Lab units from measured {target.lower()}")
    if metal_wrong:
        what.append(f"metal {float(metal):.1f} where {target.lower()} is {'a metal' if ref['metal'] >= 0.5 else 'not a metal'}")
    return (f"{material_name}: {', '.join(what)} — use rbx.real(\"{target}\") (color {ref['color']}, metal "
            f"{ref['metal']:.0f}) or name the surface it really has (painted_..., worn_...)")


def _main(argv):
    query = " ".join(a for a in argv if not a.startswith("--"))
    names = find(query)
    rows = []
    for n in names:
        v = real(n)
        m = load()[n]
        rows.append({"name": n, **v, "category": (m.get("category") or [""])[0],
                     "measured_rough": m.get("roughness")})
    lines = [f"{r['name']:22s} color ({r['color'][0]:.3f}, {r['color'][1]:.3f}, {r['color'][2]:.3f})  metal "
             f"{r['metal']:.0f}  rough {r['rough']:.2f}  [{r['category']}]" for r in rows]
    print("\n".join(lines))
    print(json.dumps({"schema": 1, "status": "pass" if rows else "fail",
                      "summary": f"materials: {len(rows)} real material(s)" + (f' matching "{query}"' if query else "")
                      + " (physicallybased.info, CC0; linear colours)",
                      "next_action": ('a.material("<name>", **rbx.real("' + rows[0]["name"] + '"), wear=0.3)')
                      if rows else "lune run kit materials   (the whole list)", "materials": rows}))
    return 0 if rows else 1


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv[1:]))
