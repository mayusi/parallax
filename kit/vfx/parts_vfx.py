"""parts_vfx.py - the VFX lane's adapter for the parts libraries (kit/tools/parts.py; board/plans/
2026-11-09-parts-libraries-plan.md, P0). A VFX part is a LAYER: its technique (the layer's own `kind`), its role in the
effect (core, ring, sparks, smoke, flash, beam ... from its name) and its beat (charge, release, impact, dissipate). P0
files, each card with its kinds:
  - every effect (assets/effects/**, games/*/assets/effects/**; not the measured refs, judge or evolve folders): the
    whole effect (the owner's verdict on it lands in full) and each of its layers, with the layer's MECHANICS (when, how
    long, shape, count, speed) - its look (texture, colour, material, palette) is hidden unless the owner allowed it;
  - every part preset (assets/effects/parts/*.json, "part": true): a recipe;
  - the library's textures and meshes (library/vfx/index.json): look assets, indexed only so today's library search can
    be scored - never handed over as a card.
`today_lib` is today's library search (kit/vfx/vault.py cmd_find), ported as it is: the baseline P3 must beat.
"""

import glob
import json
import os
import re

LANE = "vfx"
SKIP = {"refs_measured", "judge", "evolve", "meshes", "seq", "stages"}
TECHS = ("mesh", "sprite", "debris", "sound", "light", "shake", "screen", "fov", "highlight", "impact", "decal", "beam",
         "swarm", "world", "lens", "glow", "crater", "trail")
MECH = ("at", "life", "lifetime", "shape", "count", "rate", "speed", "spread", "drag", "gravity", "copies", "width")
LOOK = ("texture", "color", "material", "brightness", "lightEmission", "bloom", "tint")
BEAT_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _bases(root):
    return [os.path.join(root, "assets", "effects")] + sorted(glob.glob(os.path.join(root, "games", "*", "assets",
                                                                                   "effects")))


def effect_files(root):
    out = []
    for base in _bases(root):
        for p in glob.glob(os.path.join(base, "**", "*.json"), recursive=True):
            sub = os.path.relpath(p, base).split(os.sep)
            if os.path.basename(p).startswith("_") or any(s in SKIP for s in sub[:-1]):
                continue
            out.append(p)
    return sorted(out)


def sources(root):
    return [os.path.join(b, "**", "*.json") for b in _bases(root)] + [
        os.path.join(root, "library", "vfx", "index.json"), os.path.join(root, "assets", "effects", "briefs", "*.md")]


def homes(root):
    return [os.path.join(root, "assets", "effects", "briefs")]


def home(root, piece):
    return os.path.join(root, "assets", "effects", "briefs")


def _short(v):
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, (list, dict)):
        s = json.dumps(v)
        return s if len(s) <= 40 else s[:37] + "..."
    return v


def collect(root):
    pieces, docs = [], []
    for p in effect_files(root):
        d = _load(p)
        if not isinstance(d, dict) or not isinstance(d.get("layers"), list):
            continue
        name = os.path.splitext(os.path.basename(p))[0]
        rel = _rel(root, p)
        about = str(d.get("about") or "")
        layers = [L for L in d["layers"] if isinstance(L, dict)]
        names = ", ".join(f"{L.get('name', '?')} ({L.get('kind', '?')})" for L in layers[:40])
        is_part = d.get("part") is True or "/parts/" in rel
        pieces.append({"name": name, "kind": "part" if is_part else "effect", "about": about[:200]})
        docs.append({"id": f"vfx/{'recipe' if is_part else 'effect'}/{name}", "type": "recipe" if is_part else "effect",
                     "piece": name, "whole": True, "title": f"{name}: {about[:90]}",
                     "text": f"{about} Layers: {names}", "src": rel,
                     "mech": {"layers": len(layers), "duration": d.get("duration"), "hitstop": _short(d.get("hitstop"))},
                     "look": {"palette": _short(d.get("palette"))} if d.get("palette") else None})
        for i, L in enumerate(layers):
            kind = str(L.get("kind") or "")
            params = L.get("params") if isinstance(L.get("params"), dict) else {}
            bits = [str(L.get("name") or ""), kind, str(L.get("shape") or ""), str(L.get("orientation") or "")]
            bits += [f"{k} {_short(v)}" for k, v in params.items() if k in ("arc", "rings", "segments", "taper", "radius")]
            if isinstance(L.get("flipbook"), dict):
                bits.append("flipbook")
            mech = {k: _short(L[k]) for k in MECH if k in L}
            look = {k: _short(L[k]) for k in LOOK if k in L}
            docs.append({"id": f"vfx/layer/{name}/{i}", "type": "part", "piece": name,
                         "title": f"{name}: {L.get('name', i)} ({kind})", "text": " ".join(b for b in bits if b),
                         "src": f"{rel} layers[{i}]", "kinds": {f"tech_{kind}": 1.0} if kind in TECHS else {},
                         "mech": dict(kind=kind, **mech), "look": look or None})
    lib = _load(os.path.join(root, "library", "vfx", "index.json"))
    if isinstance(lib, dict):
        have = {d["id"] for d in docs}
        for kind, typ in (("effects", "effect"), ("parts", "recipe"), ("textures", "texture"), ("meshes", "mesh")):
            for n, e in (lib.get(kind) or {}).items():
                cid = f"vfx/{typ}/{n}"
                if cid in have or not isinstance(e, dict):
                    continue
                about = str(e.get("about") or "")
                docs.append({"id": cid, "type": typ, "piece": n, "whole": typ in ("effect", "recipe"),
                             "title": f"{n}: {about[:90]}", "text": about,
                             "src": f"library/vfx/{kind}/{n}",
                             "look": {"asset": n} if typ in ("texture", "mesh") else None})
    return {"pieces": pieces, "docs": docs}


def today_lib(root, words, k):
    """today's library search, as kit/vfx/vault.py cmd_find scores it (word counts over each entry's name and JSON)"""
    lib = _load(os.path.join(root, "library", "vfx", "index.json")) or {}
    ws = [w.lower() for w in re.findall(r"\w+", words or "")]
    hits = []
    for kind, typ in (("effects", "effect"), ("parts", "recipe"), ("textures", "texture"), ("meshes", "mesh")):
        for n, e in (lib.get(kind) or {}).items():
            hay = (n + " " + json.dumps(e)).lower()
            score = sum(hay.count(w) for w in ws)
            if score:
                hits.append((score, kind, n, typ))
    hits.sort(reverse=True)
    return [f"vfx/{typ}/{n}" for _s, _k, n, typ in hits[:k]]


def _brief_path(root, piece):
    for base in _bases(root):
        p = os.path.join(base, "briefs", f"{piece}.md")
        if os.path.isfile(p):
            return p
    return None


def brief(root, piece):
    p = _brief_path(root, piece)
    if p:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    return None


def breakdown(root, piece, text):
    """the brief's Beats table (Beat | Time | What happens | Technique): one part per beat; the impact beats are the
    hero parts. No table: None (the engine splits the words)"""
    parts = []
    for line in (text or "").splitlines():
        m = BEAT_ROW.match(line.strip())
        if not m or m.group(1).lower() in ("beat",) or set(m.group(1)) <= set("-: "):
            continue
        beat, when, what, tech = m.groups()
        hero = bool(re.search(r"impact|hit|key|climax|burst|explo", f"{beat} {what}", re.I))
        parts.append({"title": f"{beat} ({when})"[:90], "words": f"{beat}: {what} ({tech})", "hero": hero})
    return parts or None
