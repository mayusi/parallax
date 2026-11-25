"""parts_anim.py - the animation lane's adapter for the parts libraries (kit/tools/parts.py; board/plans/
2026-11-09-parts-libraries-plan.md, P0). A move is a grid of CELLS - six limbs with their roles (the striking and the
support leg, the sword and the free arm) x four phases (wind-up, strike, follow-through, settle) - with the weapon and
timing alongside. P0 files, each card with its kinds:
  - every dossier phase: the real move's timing (real_s, game_s) and what the body does. Research, not a build: the
    owner's verdicts on builds never land on it;
  - every dossier mistake (the real move's known faults);
  - every owner rejection quoted in a dossier, with what changed after it: AVOID cards;
  - every gesture beat: the settings that drive a cell (the torso's yaw, pitch and crouch, the sword's reach and blade,
    the free arm's guard) - recipes;
  - every candidate built (assets/animations/candidates/<Move>/round_K.json): its efforts and per-limb warnings, judged by
    the owner's verdicts on it (Move/rK/cN), on its round (Move/rK) or on its move;
  - every library clip the owner rated (assets/animations/library/owner_picks.json): love / ok / bad. Statistics, never
    a shape to copy (the owner's rule), so a clip's poses are its look and stay hidden;
  - the lane's checks (the owner's recurring words: kit/knowledge/vault/anim/checks.json) as rules.
"""

import fnmatch
import glob
import json
import os
import re

LANE = "anim"
A = os.path.join("assets", "animations")
# R6 joints and the roles the code names them by -> the limb kinds (kinds.json)
ROLES = {"torso": "torso", "head": "head", "right arm": "arms", "left arm": "arms", "right leg": "legs",
         "left leg": "legs", "sword_arm": "sword_arm", "free_arm": "free_arm", "lead_leg": "lead_leg",
         "rear_leg": "support_leg", "kick_leg": "lead_leg", "support_leg": "support_leg", "pivot_leg": "support_leg",
         "kick_side_arm": "sword_arm", "other_arm": "free_arm"}
PHASES = {"rest": "stance", "windup": "windup", "strike": "strike", "after": "follow_through"}
SEGS = {"antic": "windup", "stroke": "strike", "through": "follow_through", "hold": "hold", "flourish": "settle",
        "settle": "settle", "spin": "spin"}
BEAT_LIMBS = {"torso": "torso", "sword": "sword_arm", "free": "free_arm", "head": "head", "feet": "feet",
              "legs": "legs", "gun": "sword_arm"}
VERDICT = {"love": {"direction": "keep"}, "bad": {"direction": "redo"}, "ok": {"score": 5.0}}


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _key(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def sources(root):
    return [os.path.join(root, A, "dossiers", "*.json"), os.path.join(root, A, "gestures", "*.json"),
            os.path.join(root, A, "candidates", "*", "round_*.json"),
            os.path.join(root, A, "library", "owner_picks.json"),
            os.path.join(root, "kit", "knowledge", "vault", "anim", "checks.json")]


def homes(root):
    return [os.path.join(root, A, "direction")]


def home(root, piece):
    return os.path.join(root, A, "direction")


def _role_kinds(text):
    """the limb kinds a warning names: 'Left Arm rot_range ...' -> arms; 'vocab: whip_free_arm ...' -> free_arm, whip"""
    low = (text or "").lower()
    out = {}
    for role, kind in ROLES.items():
        if role in low:
            out[kind] = 1.0
    if "whip" in low:
        out["whip"] = 1.0
    return out


def _num(v):
    return round(v, 2) if isinstance(v, float) else v


def _strs(v):
    if isinstance(v, str):
        return [v]
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def dossiers(root):
    out = []
    for p in sorted(glob.glob(os.path.join(root, A, "dossiers", "*.json"))):
        d = _load(p)
        if isinstance(d, dict) and isinstance(d.get("phases"), list) and d["phases"]:
            d["_path"] = p
            out.append(d)
    return out


def dossier_for(root, piece):
    """the dossier of a move: by its own name, or a move its build maps to a gesture (build.gestures: 'SwordTrickCut*')"""
    key = _key(piece)
    for d in dossiers(root):
        if _key(d.get("name")) == key or _key(os.path.splitext(os.path.basename(d["_path"]))[0]) == key:
            return d
        gestures = (d.get("build") or {}).get("gestures") or {}
        if isinstance(gestures, dict) and any(fnmatch.fnmatch(piece, pat) for pat in gestures):
            return d
    return None


def collect(root):
    pieces, docs = [], []
    for d in dossiers(root):
        name = d.get("name") or os.path.splitext(os.path.basename(d["_path"]))[0]
        rel = _rel(root, d["_path"])
        pieces.append({"name": name, "kind": "dossier", "brief": (d.get("move") or "")[:300]})
        for i, ph in enumerate(d["phases"]):
            if not isinstance(ph, dict):
                continue
            title = str(ph.get("name") or f"phase {i}")
            docs.append({"id": f"anim/phase/{name}/{i}", "type": "part", "piece": name, "research": True,
                         "title": f"{name}: {title}",
                         "text": f"{title}: {ph.get('body', '')} (real {ph.get('real_s')} s, in game {ph.get('game_s')} s)",
                         "src": rel, "mech": {"real_s": ph.get("real_s"), "game_s": ph.get("game_s")}})
        for i, m in enumerate(d.get("mistakes") or []):
            text = m if isinstance(m, str) else json.dumps(m)
            docs.append({"id": f"anim/mistake/{name}/{i}", "type": "mistake", "piece": name, "research": True,
                         "title": f"{name}: {text[:80]}", "text": text, "src": rel})
        for i, r in enumerate(d.get("owner_rejections") or []):
            if not isinstance(r, dict):
                continue
            docs.append({"id": f"anim/rejected/{name}/{i}", "type": "grave", "piece": name, "avoid": True,
                         "title": f"{name} {r.get('date', '')}: \"{str(r.get('quote', ''))[:70]}\"",
                         "text": f"the owner: \"{r.get('quote', '')}\" - what changed: {r.get('changed', '')}",
                         "src": rel, "date": r.get("date", "")})
    for p in sorted(glob.glob(os.path.join(root, A, "gestures", "*.json"))):
        g = _load(p)
        if not isinstance(g, dict) or not isinstance(g.get("beats"), list):
            continue
        gname = g.get("name") or os.path.splitext(os.path.basename(p))[0]
        rel = _rel(root, p)
        legs = ", ".join(f"{k} {g[k]}" for k in ("hand", "free", "lead_leg", "rear_leg", "pivot_leg") if g.get(k))
        for i, b in enumerate(g["beats"]):
            if not isinstance(b, dict):
                continue
            kinds = {}
            for ph in _strs(b.get("phase")):  # (a beat may sit on two phases: ["strike", "after"])
                if ph in PHASES:
                    kinds[PHASES[ph]] = 1.0
            for sg in _strs(b.get("seg")):
                if sg in SEGS:
                    kinds[SEGS[sg]] = 1.0
            for key, kind in BEAT_LIMBS.items():
                if isinstance(b.get(key), dict):
                    kinds[kind] = 1.0
            torso = b.get("torso") or {}
            sword = b.get("sword") or {}
            free = b.get("free") or {}
            bits = []
            if torso:
                bits.append("torso " + " ".join(f"{k} {_num(v)}" for k, v in torso.items() if k in
                                                ("yaw", "pitch", "roll", "crouch")))
            if sword:
                bits.append(f"sword reach {sword.get('reach')} blade {sword.get('blade')} slide {sword.get('slide')}")
            if free:
                bits.append(f"free arm dir {free.get('dir')} weight {free.get('w')}")
            docs.append({"id": f"anim/recipe/{gname}/{i}", "type": "recipe", "piece": gname,
                         "title": f"{gname} beat '{b.get('name', i)}' ({b.get('phase', '?')}/{b.get('seg', '-')}) at "
                                  f"{b.get('t')} of the move",
                         "text": f"gesture {gname} ({g.get('kind', '')}; {legs}): beat {b.get('name', i)} - " +
                                 "; ".join(bits) + f". {str(g.get('about', ''))[:200]}",
                         "src": rel, "kinds": kinds,
                         "mech": {"t": b.get("t"), "phase": b.get("phase"), "seg": b.get("seg"),
                                  "crouch": torso.get("crouch"), "yaw": torso.get("yaw")}})
    for p in sorted(glob.glob(os.path.join(root, A, "candidates", "*", "round_*.json"))):
        r = _load(p)
        if not isinstance(r, dict):
            continue
        rel = _rel(root, p)
        change = str(r.get("change") or "")[:200]
        for c in r.get("candidates") or []:
            if not isinstance(c, dict) or not c.get("id"):
                continue
            warns = [str(w) for w in c.get("warnings") or []]
            kinds = {}
            for w in warns:
                kinds.update(_role_kinds(w))
            sliders = c.get("sliders") or {}
            efforts = " ".join(f"{k} {_num(v)}" for k, v in sliders.items())
            docs.append({"id": f"anim/candidate/{c['id']}", "type": "candidate", "piece": c["id"], "whole": True,
                         "title": f"{c['id']}: efforts {efforts}",
                         "text": f"candidate {c['id']} of {r.get('name', '')} ({change}); hit at {c.get('hit_t')} s of "
                                 f"{c.get('seconds')} s; warnings: " + ("; ".join(warns) or "none"),
                         "src": rel, "kinds": kinds, "mech": dict(sliders, hit_t=c.get("hit_t"))})
    picks = _load(os.path.join(root, A, "library", "owner_picks.json"))
    if isinstance(picks, dict):
        saved = str(picks.get("saved") or "")[:10]
        for c in picks.get("picks") or []:
            if not isinstance(c, dict) or c.get("verdict") not in VERDICT or not c.get("id"):
                continue
            v = dict(VERDICT[c["verdict"]], words=str(c.get("note") or ""), date=saved)
            docs.append({"id": f"anim/clip/{c['id']}", "type": "clip", "piece": f"clip:{c['id']}", "whole": True,
                         "title": f"{c.get('name', '')} ({c.get('kind', '')}; {c.get('pack', '')})"[:110],
                         "text": f"library clip {c.get('name', '')}: {c.get('kind', '')}, {c.get('topic', '')}, "
                                 f"{c.get('pack', '')}, {c.get('duration')} s, {c.get('keyframes')} keyframes; the "
                                 f"owner: {c['verdict']}" + (f" ({c.get('note')})" if c.get("note") else ""),
                         "src": "assets/animations/library/owner_picks.json", "verdicts": [v],
                         "mech": {"seconds": c.get("duration"), "keyframes": c.get("keyframes")},
                         "look": {"poses": "the clip's own poses (statistics only, never copied)"}})
    checks = _load(os.path.join(root, "kit", "knowledge", "vault", "anim", "checks.json"))
    if isinstance(checks, dict):
        for ck in checks.get("checks") or []:
            if not isinstance(ck, dict) or not ck.get("id"):
                continue
            said = "; ".join(f"\"{s.get('quote', '')}\"" for s in (ck.get("said") or [])[:3] if isinstance(s, dict))
            docs.append({"id": f"anim/check/{ck['id']}", "type": "rule", "piece": None,
                         "title": f"check {ck['id']}: {', '.join(ck.get('words') or [])}",
                         "text": f"{ck.get('about', '')} The owner said: {said}",
                         "src": "kit/knowledge/vault/anim/checks.json"})
    return {"pieces": pieces, "docs": docs}


def brief(root, piece):
    d = dossier_for(root, piece)
    if not d:
        return None
    return f"{piece}: " + "; ".join(f"{ph.get('name', '')}: {ph.get('body', '')}" for ph in d["phases"]
                                   if isinstance(ph, dict))


def breakdown(root, piece, text):
    """a move with a dossier: one part per dossier phase (the cell rows come from its words); the strike phases are the
    hero parts. Without a dossier: None (the engine splits the brief)"""
    d = dossier_for(root, piece)
    if not d:
        return None
    parts = []
    for ph in d["phases"]:
        if not isinstance(ph, dict):
            continue
        name = str(ph.get("name") or "")
        words = f"{name}: {ph.get('body', '')}"
        hero = bool(re.search(r"strike|impact|contact|hit|cut|release|burst", name, re.I))
        parts.append({"title": name[:90], "words": words, "hero": hero})
    return parts or None
