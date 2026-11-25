"""kit vfx style - a game's VFX STYLE GUIDE, the pros' "source of truth" (GDC 2023 VFX roundtable; Riot: every effect in a
game shares one harmonious style; board/plans/archive/aaa-vfx-research.md). A guide is assets/effects/styles/<style>.json; a preset
opts in with a top-level "style": "<style>".

  lune run kit vfx style <preset>                       check a preset against its guide
  lune run kit vfx style derive <style> --from a,b,c    write a guide measured from presets the owner liked

A guide (every field optional):
  "palette":     { "<name>": [r, g, b], ... }   every colour an effect uses must sit near one of these
  "tolerance":   70                             RGB distance that still counts as "near" (0-441)
  "additive":    [0.3, 0.8]                     the share of sprite layers that glow (lightEmission >= 0.5)
  "maxLifetime": 1.2                            the longest particle life (s): the game's tempo
  "materials":   ["Neon", "SmoothPlastic"]      mesh materials allowed
  "bans":        ["Glass", "kn_smoke_*"]        materials / textures / layer kinds never used (globs)
  "about":       "..."                          the words: what this game's effects look and feel like
Prints one JSON line {status, summary, next_action, ...}; a check fails on any ban or off-guide colour.
"""
import fnmatch
import json
import math
import os
import subprocess
import sys

STYLES = os.path.join("assets", "effects", "styles")


def out(status, summary, next_action, **extra):
    print(json.dumps(dict(status=status, summary=summary, next_action=next_action, **extra)))
    sys.exit(0 if status in ("pass", "warn") else 1)


def expand(name):
    r = subprocess.run(["lune", "run", "kit", "vfx", "expand", name], capture_output=True, text=True, encoding="utf-8", timeout=300)
    t = r.stdout
    if "{" not in t:
        return None
    return json.loads(t[t.index("{"):t.rindex("}") + 1])


def colours(P):
    """every colour a layer uses: [(layer name, field, [r, g, b])], palette names resolved"""
    pal = P.get("palette") or {}
    found = []

    def add(name, field, c):
        if isinstance(c, str):
            c = pal.get(c)
        if isinstance(c, list) and len(c) == 3 and all(isinstance(x, (int, float)) for x in c):
            found.append((name, field, [float(x) for x in c]))

    for el in P.get("layers", []):
        if not isinstance(el, dict):
            continue
        for field in ("color", "tint", "fogColor", "sky", "accent", "hot", "ink", "paper"):
            v = el.get(field)
            if isinstance(v, list) and v and isinstance(v[0], list):  # keyframes [[t, colour], ...]
                for kv in v:
                    if len(kv) >= 2:
                        add(el.get("name"), field, kv[1])
            else:
                add(el.get("name"), field, v)
    return found


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def near(c, palette, tol):
    if lum(c) < 24 or (max(c) - min(c) < 18 and lum(c) > 235):  # near-black ink and near-white cores are neutral
        return True, 0.0
    best = min(math.dist(c, p) for p in palette.values()) if palette else 0.0
    return best <= tol, best


def stats(P):
    sprites = [el for el in P.get("layers", []) if isinstance(el, dict) and el.get("kind") == "sprite"]
    glow = sum(1 for el in sprites if float(el.get("lightEmission") or 0) >= 0.5)
    lives = []
    for el in sprites:
        lt = el.get("lifetime", 1)
        lives.append(float(max(lt)) if isinstance(lt, list) else float(lt))
    mats = sorted({el.get("material", "Neon") for el in P.get("layers", []) if isinstance(el, dict) and el.get("kind") == "mesh"})
    return {"sprites": len(sprites), "additive": round(glow / len(sprites), 2) if sprites else None,
            "maxLifetime": round(max(lives), 2) if lives else None, "materials": mats}


def check(name):
    raw_path = os.path.join("assets", "effects", f"{name}.json")
    if not os.path.isfile(raw_path):
        out("fail", f"vfx style: no preset {raw_path}", "check the name")
    raw = json.load(open(raw_path, encoding="utf-8"))
    style = raw.get("style")
    if not style:
        out("warn", f"vfx style: {name} names no style guide", f'add "style": "<game>" to {raw_path} (guides: {", ".join(listed()) or "none yet - lune run kit vfx style derive <style> --from <liked presets>"})')
    gpath = os.path.join(STYLES, f"{style}.json")
    if not os.path.isfile(gpath):
        out("fail", f"vfx style: no guide {gpath}", f"lune run kit vfx style derive {style} --from <presets the owner liked>")
    G = json.load(open(gpath, encoding="utf-8"))
    P = expand(name)
    if P is None:
        out("fail", f"vfx style: could not expand {name}", f"lune run kit vfx expand {name}")
    problems, notes = [], []
    tol = float(G.get("tolerance", 70))
    off = {}
    for lname, field, c in colours(P):
        ok, d = near(c, G.get("palette") or {}, tol)
        if not ok:
            key = tuple(int(x) for x in c)
            off.setdefault(key, []).append(lname)
    for c, layers in sorted(off.items(), key=lambda kv: -len(kv[1]))[:6]:
        problems.append(f"colour {list(c)} is off the guide's palette ({', '.join(sorted(set(layers))[:3])})")
    s = stats(P)
    lo_hi = G.get("additive")
    if lo_hi and s["additive"] is not None and not (lo_hi[0] - 1e-6 <= s["additive"] <= lo_hi[1] + 1e-6):
        notes.append(f"{int(s['additive'] * 100)} % of sprites glow; the guide says {int(lo_hi[0] * 100)}-{int(lo_hi[1] * 100)} %")
    if G.get("maxLifetime") and s["maxLifetime"] and s["maxLifetime"] > float(G["maxLifetime"]) * 1.15:
        notes.append(f"particles live up to {s['maxLifetime']} s; the guide's tempo is <= {G['maxLifetime']} s")
    allowed = G.get("materials")
    if allowed:
        for m in s["materials"]:
            if m not in allowed:
                problems.append(f"mesh material {m} is not in the guide ({', '.join(allowed)})")
    for ban in G.get("bans", []):
        for el in P.get("layers", []):
            if not isinstance(el, dict):
                continue
            for v in (el.get("material"), el.get("texture"), el.get("kind")):
                if isinstance(v, str) and fnmatch.fnmatch(v, ban):
                    problems.append(f"{el.get('name')}: {v} is banned by the guide ({ban})")
    extra = dict(style=style, stats=s, problems=problems, notes=notes)
    if problems:
        out("fail", f"vfx style: {name} vs {style}: {len(problems)} problem(s): " + "; ".join(problems[:3]),
            "recolour from the guide's palette / drop the banned material or texture, or extend the guide on purpose", **extra)
    if notes:
        out("warn", f"vfx style: {name} vs {style}: on palette; " + "; ".join(notes), "tempo / glow drift from the guide - intended?", **extra)
    out("pass", f"vfx style: {name} speaks {style} (palette, materials, bans, tempo)", "none", **extra)


def listed():
    return sorted(f[:-5] for f in os.listdir(STYLES) if f.endswith(".json")) if os.path.isdir(STYLES) else []


def derive(style, names):
    """a guide measured from presets: their colours clustered into a palette, the additive share and tempo range"""
    cols, adds, lives, mats = [], [], [], set()
    for n in names:
        P = expand(n)
        if P is None:
            out("fail", f"vfx style derive: could not expand {n}", f"lune run kit vfx expand {n}")
        cols += [c for _, _, c in colours(P)]
        s = stats(P)
        if s["additive"] is not None:
            adds.append(s["additive"])
        if s["maxLifetime"]:
            lives.append(s["maxLifetime"])
        mats.update(s["materials"])
    cols = [c for c in cols if not (lum(c) < 24 or (max(c) - min(c) < 18 and lum(c) > 235))]
    palette = {}
    for c in sorted(cols, key=lum):  # greedy clustering: a colour joins the first swatch within 45, else starts one
        for k, p in palette.items():
            if math.dist(c, p[0]) <= 45:
                p[1].append(c)
                break
        else:
            palette[f"c{len(palette) + 1}"] = [c, [c]]
    swatches = {k: [round(sum(x[i] for x in v[1]) / len(v[1])) for i in range(3)] for k, v in palette.items()}
    G = {"about": f"measured from {', '.join(names)} - edit the words: what this game's effects look and feel like",
         "palette": swatches, "tolerance": 70,
         "additive": [round(max(0.0, min(adds) - 0.1), 2), round(min(1.0, max(adds) + 0.1), 2)] if adds else None,
         "maxLifetime": round(max(lives), 2) if lives else None, "materials": sorted(mats) or None, "bans": []}
    G = {k: v for k, v in G.items() if v is not None}
    os.makedirs(STYLES, exist_ok=True)
    path = os.path.join(STYLES, f"{style}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(G, fh, indent=1)
    out("pass", f"vfx style derive: {path} - {len(swatches)} swatches, additive {G.get('additive')}, tempo <= {G.get('maxLifetime')} s",
        f'write the guide\'s "about" in words, then add "style": "{style}" to the game\'s presets and run lune run kit vfx style <preset>')


def main(argv):
    if not argv:
        out("fail", "vfx style: name a preset (or: derive <style> --from a,b)", "lune run kit vfx style <preset>")
    if argv[0] == "derive":
        if len(argv) < 2 or "--from" not in argv:
            out("fail", "vfx style derive: needs <style> --from a,b,c", "lune run kit vfx style derive <style> --from <presets>")
        names = [n for n in argv[argv.index("--from") + 1].split(",") if n]
        derive(argv[1], names)
    check(argv[0])


if __name__ == "__main__":
    main(sys.argv[1:])
