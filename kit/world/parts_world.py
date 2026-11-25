"""parts_world.py - the world lane's adapter for the parts libraries (kit/tools/parts.py; board/plans/
2026-11-09-parts-libraries-plan.md, P0). A world part is a GENERATOR STEP (stairs, a tower, a path, a forest, a wall,
spawns...), a ROOM by purpose with its real size, or a placed FIXTURE with its size in studs. P0 files, each card with its
kinds:
  - every blueprint (games/*/assets/worlds/**/*.json and assets/worlds/** with a `build` list): the whole world (the
    owner's verdict lands in full) and each generator step with its MECHANICS (size, steps, rise, run, radius, count,
    segments...); its material and palette are the look. The primitive `part` / `fit` steps (10,908 + 593, most of
    them one large city) are counted on the world's card, never filed one by one;
  - every house layout's rooms (games/*/assets/worlds/**/layouts/*.layout.json): purpose, why and size in metres;
  - every fixture of a catalogue (games/*/assets/models/**/catalogue.json): what it is, where it goes, its size in studs.
"""

import glob
import json
import os
import re

LANE = "world"
PRIMITIVE = {"part", "fit"}
GEN = {"stairs", "spawn", "path", "tower", "forest", "building", "rocks", "arch", "grace", "crosswalk", "ruin", "mesh",
       "scatter", "breakable", "horizon", "wall", "row", "story", "floor", "ring", "room", "tree", "bridge", "city",
       "cover", "peak", "palisade", "cliffs", "ziggurat", "falls"}
ALIAS = {"crosswalk": "path", "row": "city", "story": "building", "tree": "forest", "peak": "rocks", "cliffs": "rocks",
         "palisade": "wall", "ziggurat": "terrain", "falls": "terrain"}
LOOK = ("mat", "color", "material", "texture", "checker", "particles", "light", "style")
BRIEF_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _short(v):
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, (list, dict)):
        s = json.dumps(v)
        return s if len(s) <= 36 else s[:33] + "..."
    return v


def _bases(root):
    return [os.path.join(root, "assets", "worlds")] + sorted(glob.glob(os.path.join(root, "games", "*", "assets",
                                                                                  "worlds")))


def blueprint_files(root):
    out = []
    for b in _bases(root):
        out += glob.glob(os.path.join(b, "*.json")) + glob.glob(os.path.join(b, "checks", "*.json"))
    return sorted(out)


def sources(root):
    pats = []
    for b in _bases(root):
        pats += [os.path.join(b, "*.json"), os.path.join(b, "checks", "*.json"), os.path.join(b, "*.brief.md"),
                 os.path.join(b, "**", "layouts", "*.layout.json")]
    return pats + [os.path.join(root, "games", "*", "assets", "models", "**", "catalogue.json")]


def homes(root):
    return _bases(root)


def home(root, piece):
    game = os.environ.get("KIT_GAME")
    if game and os.path.isdir(os.path.join(root, "games", game, "assets", "worlds")):
        return os.path.join(root, "games", game, "assets", "worlds")
    for b in _bases(root):
        if os.path.isfile(os.path.join(b, f"{piece}.json")) or os.path.isfile(os.path.join(b, f"{piece}.brief.md")):
            return b
    return os.path.join(root, "assets", "worlds")


def collect(root):
    pieces, docs = [], []
    for p in blueprint_files(root):
        d = _load(p)
        if not isinstance(d, dict) or not isinstance(d.get("build"), list):
            continue
        name = str(d.get("name") or os.path.splitext(os.path.basename(p))[0])
        rel = _rel(root, p)
        counts = {}
        for s in d["build"]:
            if isinstance(s, dict):
                for k in s:
                    counts[k] = counts.get(k, 0) + 1
        prim = sum(n for k, n in counts.items() if k in PRIMITIVE)
        about = str(d.get("_about") or d.get("about") or "")
        pieces.append({"name": name, "steps": len(d["build"])})
        docs.append({"id": f"world/world/{name}", "type": "world", "piece": name, "whole": True,
                     "title": f"{name}: {about[:90]}",
                     "text": f"{about} Generators: " + ", ".join(f"{k} x{n}" for k, n in sorted(counts.items())),
                     "src": rel, "mech": {"steps": len(d["build"]), "primitive parts": prim,
                                          "terrain": bool(d.get("terrain"))},
                     "look": {"palette": _short(d.get("palette")), "lighting": _short(d.get("lighting"))}})
        for i, s in enumerate(d["build"]):
            if not isinstance(s, dict) or len(s) != 1:
                continue
            kind, params = next(iter(s.items()))
            if kind in PRIMITIVE or not isinstance(params, dict):
                continue
            gen = ALIAS.get(kind, kind)
            label = str(params.get("name") or kind)
            spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", label)
            mech = {k: _short(v) for k, v in params.items() if k not in LOOK and k not in ("name", "about")}
            look = {k: _short(params[k]) for k in LOOK if k in params}
            docs.append({"id": f"world/step/{name}/{i}", "type": "part", "piece": name,
                         "title": f"{name}: {label} ({kind})",
                         "text": f"{kind} {spaced} {params.get('about', '')} " +
                                 " ".join(f"{k} {mech[k]}" for k in list(mech)[:8]),
                         "src": f"{rel} build[{i}]", "kinds": {f"gen_{gen}": 1.0} if gen in GEN | {"terrain"} else {},
                         "mech": dict(list(mech.items())[:8]), "look": look or None})
    for b in _bases(root):
        for p in sorted(glob.glob(os.path.join(b, "**", "layouts", "*.layout.json"), recursive=True)):
            d = _load(p)
            if not isinstance(d, dict):
                continue
            lname = os.path.basename(p).split(".")[0]
            rel = _rel(root, p)
            for fl in d.get("floors") or []:
                if not isinstance(fl, dict):
                    continue
                for r in fl.get("rooms") or []:
                    if not isinstance(r, dict) or not r.get("name"):
                        continue
                    rect = r.get("rect") if isinstance(r.get("rect"), list) and len(r["rect"]) == 4 else None
                    size = (f"{abs(rect[2] - rect[0]):.1f} x {abs(rect[3] - rect[1]):.1f} m" if rect and all(
                        isinstance(x, (int, float)) for x in rect) else "")
                    docs.append({"id": f"world/room/{lname}/{fl.get('name')}/{r['name']}", "type": "room",
                                 "piece": lname, "title": f"{lname}: {r['name']} ({r.get('purpose', '')}, {size})",
                                 "text": f"{r.get('purpose', '')} room {r['name']} on the {fl.get('name')} floor, "
                                         f"{size}: {r.get('why', '')}",
                                 "src": rel, "kinds": {"gen_room": 1.0},
                                 "mech": {"size": size, "floor": fl.get("name"), "purpose": r.get("purpose")}})
    for p in sorted(glob.glob(os.path.join(root, "games", "*", "assets", "models", "**", "catalogue.json"),
                              recursive=True)):
        d = _load(p)
        if not isinstance(d, dict) or not isinstance(d.get("fixtures"), dict):
            continue
        rel = _rel(root, p)
        for fid, f in d["fixtures"].items():
            if not isinstance(f, dict):
                continue
            docs.append({"id": f"world/fixture/{fid}", "type": "fixture", "piece": f.get("asset") or fid,
                         "title": f"{f.get('name', fid)} ({f.get('kind', '')})",
                         "text": f"{f.get('name', '')} {f.get('kind', '')}: {f.get('where', '')}; {str(f.get('era', ''))[:120]}",
                         "src": rel, "kinds": {"gen_mesh": 1.0},
                         "mech": {"size_studs": _short(f.get("size_studs")), "height_m": f.get("height_m"),
                                  "tiers": _short(f.get("tiers")), "status": f.get("status")}})
    return {"pieces": pieces, "docs": docs}


def _brief_path(root, piece):
    for b in _bases(root):
        p = os.path.join(b, f"{piece}.brief.md")
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
    """the brief's parts plan table (Piece | Generator | Notes): one part per row. None without one"""
    parts, on = [], False
    for line in (text or "").splitlines():
        s = line.strip()
        if s.lower().startswith("## parts plan"):
            on = True
            continue
        if on and s.startswith("## "):
            break
        m = BRIEF_ROW.match(s) if on else None
        if not m or m.group(1).lower() == "piece" or set(m.group(1)) <= set("-: "):
            continue
        what, gen, notes = m.groups()
        parts.append({"title": what[:90], "words": f"{what}: {gen.replace('`', '')} {notes}", "hero": False})
    return parts or None
