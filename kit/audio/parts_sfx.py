"""parts_sfx.py - the sound lane's adapter for the parts libraries (kit/tools/parts.py; board/plans/
2026-11-09-parts-libraries-plan.md, P0). A sound part is a LAYER by role (transient, body, sub, mechanical, tail,
sweetener, air), made from a source (noise, click, modal, string, tone, a library recording). P0 files, each card with
its kinds:
  - every sound spec (assets/sounds/*.json, games/*/assets/sounds/*.json) and every member of a set
    (assets/sounds/sets/*.json): the whole sound (the owner's verdict on it lands in full) and each layer, with its
    MECHANICS (role, source, filter, envelope, gain, delay); the exact recordings it uses are its signature and stay
    hidden unless the owner allowed it;
  - every set's DNA layers (the shared base layers): recipes;
  - every library recording (library/sfx/index.json): its words and its ears (loudness, brightness, tail).
`today_lib` is today's library search (kit/audio/sfxlib.py word_rank), used as it is: the baseline P6 must beat.
"""

import glob
import json
import os
import sys

LANE = "sfx"
HERE = os.path.dirname(os.path.abspath(__file__))
ROLES = ("transient", "body", "sub", "mechanical", "tail", "sweetener", "air")
SOURCES = {"noise": "src_noise", "click": "src_click", "modal": "src_modal", "string": "src_string", "sine": "src_tone",
           "square": "src_tone", "saw": "src_tone", "sawtooth": "src_tone", "triangle": "src_tone"}


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _bases(root):
    return [os.path.join(root, "assets", "sounds")] + sorted(glob.glob(os.path.join(root, "games", "*", "assets",
                                                                                  "sounds")))


def sources(root):
    pats = []
    for b in _bases(root):
        pats += [os.path.join(b, "*.json"), os.path.join(b, "sets", "*.json")]
    return pats + [os.path.join(root, "library", "sfx", "index.json")]


def homes(root):
    return [os.path.join(root, "assets", "sounds")]


def home(root, piece):
    return os.path.join(root, "assets", "sounds")


def _short(v):
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, (list, dict)):
        s = json.dumps(v)
        return s if len(s) <= 40 else s[:37] + "..."
    return v


def _layer_doc(root, rel, piece, i, L, kind="part", lid=None):
    role = str(L.get("role") or "")
    src = str(L.get("source") or ("sample" if L.get("sample") else ""))
    kinds = {}
    if role in ROLES:
        kinds[f"role_{role}"] = 1.0
    if src in SOURCES:
        kinds[SOURCES[src]] = 1.0
    if L.get("sample"):
        kinds["src_sample"] = 1.0
    filt = L.get("filter") if isinstance(L.get("filter"), dict) else {}
    env = L.get("env") if isinstance(L.get("env"), dict) else {}
    text = (f"{role} layer from {src}" + (f", {filt.get('type')} filter at {filt.get('cutoff')} Hz" if filt else "") +
            # (the envelope as numbers only: its words - attack, decay, release - are other roles' words)
            (f", envelope {env.get('attack')}/{env.get('decay')}/{env.get('release')} s" if env else "")
            + (f", {L.get('color')} noise" if L.get("color") else ""))
    mech = {k: _short(L[k]) for k in ("role", "source", "gain", "delay", "drive", "freq", "length") if k in L}
    if filt:
        mech["filter"] = _short(filt)
    if env:
        mech["env"] = _short(env)
    return {"id": lid or f"sfx/layer/{piece}/{i}", "type": kind, "piece": piece,
            "title": f"{piece}: {role or src or 'layer'} layer ({src})", "text": text, "src": f"{rel} layers[{i}]",
            "kinds": kinds, "mech": mech, "look": {"sample": _short(L.get("sample"))} if L.get("sample") else None}


def collect(root):
    pieces, docs = [], []
    for b in _bases(root):
        for p in sorted(glob.glob(os.path.join(b, "*.json"))):
            base = os.path.basename(p)
            if base.startswith("_") or base.endswith(".verdict.json"):
                continue
            d = _load(p)
            if not isinstance(d, dict) or not isinstance(d.get("layers"), list):
                continue
            name, rel = os.path.splitext(base)[0], _rel(root, p)
            pieces.append({"name": name})
            docs.append({"id": f"sfx/sound/{name}", "type": "sound", "piece": name, "whole": True,
                         "title": f"{name}: {str(d.get('about') or '')[:80]}",
                         "text": f"{name} {d.get('about') or ''} " + ", ".join(str(L.get("role") or L.get("source"))
                                                                              for L in d["layers"] if isinstance(L, dict)),
                         "src": rel, "mech": {"layers": len(d["layers"]), "duration": d.get("duration")}})
            for i, L in enumerate(d["layers"]):
                if isinstance(L, dict):
                    docs.append(_layer_doc(root, rel, name, i, L))
        for p in sorted(glob.glob(os.path.join(b, "sets", "*.json"))):
            d = _load(p)
            if not isinstance(d, dict):
                continue
            sname, rel = os.path.splitext(os.path.basename(p))[0], _rel(root, p)
            members = d.get("members") if isinstance(d.get("members"), dict) else {}
            pieces.append({"name": sname, "members": len(members)})
            docs.append({"id": f"sfx/set/{sname}", "type": "set", "piece": sname, "whole": True,
                         "title": f"set {sname}: {str(d.get('about') or '')[:80]}",
                         "text": f"{d.get('about') or ''} members: {', '.join(members)}; DNA: "
                                 f"{', '.join((d.get('dna') or {}).keys())}", "src": rel,
                         "mech": {"members": len(members), "loudness": d.get("loudness")}})
            for dn, L in (d.get("dna") or {}).items():
                if isinstance(L, dict):
                    doc = _layer_doc(root, rel, sname, 0, L, kind="recipe", lid=f"sfx/dna/{sname}/{dn}")
                    doc["title"] = f"set {sname} DNA layer '{dn}' ({doc['mech'].get('role', '')})"
                    doc["src"] = f"{rel} dna.{dn}"
                    docs.append(doc)
            for mn, m in members.items():
                if not isinstance(m, dict):
                    continue
                use = m.get("use") or {}
                uses = [str(u) for u in (use.keys() if isinstance(use, dict) else use if isinstance(use, list) else [])]
                docs.append({"id": f"sfx/sound/{mn}", "type": "sound", "piece": mn, "whole": True,
                             "title": f"{mn} ({m.get('class', '')}, set {sname})",
                             "text": f"{mn} {m.get('class', '')} sound of the {sname} set; uses DNA "
                                     f"{', '.join(uses)}", "src": f"{rel} members.{mn}",
                             "mech": {"duration": m.get("duration"), "loudness": m.get("loudness")}})
                for i, L in enumerate(m.get("layers") or []):
                    if isinstance(L, dict):
                        doc = _layer_doc(root, rel, mn, i, L)
                        doc["src"] = f"{rel} members.{mn}.layers[{i}]"
                        docs.append(doc)
    lib = _load(os.path.join(root, "library", "sfx", "index.json"))
    for e in ((lib or {}).get("entries") or {}).values():
        if not isinstance(e, dict) or not e.get("id"):
            continue
        ears = e.get("ears") if isinstance(e.get("ears"), dict) else {}
        docs.append({"id": f"sfx/sample/{e['id']}", "type": "sample", "piece": f"sample:{e['id']}",
                     "title": f"{e['id']} ({e.get('licence', '')})",
                     "text": " ".join(e.get("words") or []) + f"; {ears.get('lufs')} LUFS, {ears.get('brightness_hz')} Hz, "
                             f"tail {ears.get('tail_ms')} ms",
                     "src": str(e.get("file") or ""),
                     "mech": {k: ears.get(k) for k in ("lufs", "brightness_hz", "tail_ms", "attack_ms") if k in ears}})
    return {"pieces": pieces, "docs": docs}


def today_lib(root, words, k):
    """today's library search (kit/audio/sfxlib.py word_rank, imported: the very function `kit sfx find` runs)"""
    sys.path.insert(0, HERE)
    try:
        import sfxlib  # noqa: PLC0415
    finally:
        sys.path.remove(HERE)
    lib = _load(os.path.join(root, "library", "sfx", "index.json")) or {}
    entries = [e for e in (lib.get("entries") or {}).values() if isinstance(e, dict)]
    return [f"sfx/sample/{e['id']}" for _s, e in sfxlib.word_rank(words, entries)[:k]]


def brief(root, piece):
    """a sound that exists: its own spec as the brief (what it is, its layers by role); a set member: its set's"""
    for b in _bases(root):
        d = _load(os.path.join(b, f"{piece}.json"))
        if isinstance(d, dict) and isinstance(d.get("layers"), list):
            roles = ", ".join(f"{L.get('role') or L.get('source') or 'layer'} layer" for L in d["layers"]
                              if isinstance(L, dict))
            return f"{piece}: {d.get('about') or piece.replace('_', ' ')}; {roles}"
        for p in glob.glob(os.path.join(b, "sets", "*.json")):
            s = _load(p)
            m = ((s or {}).get("members") or {}).get(piece) if isinstance(s, dict) else None
            if isinstance(m, dict):
                return f"{piece}: a {m.get('class', '')} sound of the {os.path.basename(p)[:-5]} set; {s.get('about', '')}"
    return None


def breakdown(root, piece, text):
    """a sound that exists: one part per layer (its role first). None otherwise"""
    for b in _bases(root):
        d = _load(os.path.join(b, f"{piece}.json"))
        if isinstance(d, dict) and isinstance(d.get("layers"), list):
            return [{"title": f"{L.get('role') or L.get('source') or 'layer'} {i}", "hero": L.get("role") == "transient",
                     "words": f"{L.get('role', '')} layer {L.get('source', '')}"}
                    for i, L in enumerate(d["layers"]) if isinstance(L, dict)] or None
    return None
