"""partsrag.py - PROMPT-X's Parts RAG (LIMITATIONS_FIXES_V4 9.2 row 1: route.py "queries kit parts <lane> find/plan
(P0-P8, respecting look-allow vs mechanics-only!)"; 9.5: every pipeline's PromptPacket carries its `kit parts <lane>`
hits). The engine and the eight libraries are kit/tools/parts.py's (board/plans/archive/2026-11-09-parts-libraries-plan.md);
this module only asks them, the way `kit parts <lane> plan` does, and turns the answers into prompt lines.

  P0  the engine: each lane's own index (build/parts/<lane>/), BM25 words + kind + the owner's evidence
  P1-P7  each lane's OWN library and kinds axes - 3D form/role/finish, animation limb/phase/timing, VFX role/beat/
      technique, UI component/screen/route, world generator/purpose/play, sound role/source/event, code job/layer and
      (P7, "each on its own") QA's area/bug/test library beside code's for the systems lane
  plan  the piece broken into PARTS by the lane's adapter when a piece is named (a move's dossier phases, an effect's
      scene breakdown, a brief's parts list), else the prompt's own clauses; each part looked up BY KIND
  AVOID  a card the owner rejected (the graveyard's, a verdict <= 3) becomes a guardrail, with the owner's words
  know-how  the helpers / recipes that already do that kind of part's job (the plan's playbooks)
  P8  upkeep applied to what is shown: a duplicate text takes one place, a recipe whose file is gone is never handed
      over, a card with no owner evidence says "unjudged"
Cards hand over MECHANICS only (timing, sizes, settings: the engine's `mech`); the LOOK stays hidden unless the owner
allowed this piece to reuse that past piece's look (`kit parts <lane> look-allow`). Sample Game is never handed over.
KIT_PROMPT_PARTS=0 turns the look-up off (the packet then says so and the parts gate fails)."""

import os
import re

try:
    from . import models
except ImportError:
    import models

LIBRARIES = {"systems": ("code", "qa")}  # a PROMPT-X lane -> its parts libraries (the others: the lane's own)
QA_WORDS = {"test", "tests", "spec", "specs", "qa", "bug", "bugs", "regression", "mutation", "fuzz", "playtest", "exploit", "audit"}
LEAD_PARTS, OTHER_PARTS = 3, 1  # the lead lane's piece is looked up part by part (at most 3), another lane's as a whole
CARDS_TOTAL = 8
POOL = 6
AVOID_POOL = 24
_ENG = {"engine": None, "idx": {}}


def engine():
    """kit/tools/parts.py, loaded by path under its own module name"""
    if _ENG["engine"] is None:
        import importlib.util

        path = os.path.join(models.root(), "kit", "tools", "parts.py")
        spec = importlib.util.spec_from_file_location("kit_prompt_parts_engine", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ENG["engine"] = mod
    return _ENG["engine"]


def library_index(lib):
    eng = engine()
    idx = _ENG["idx"].get(lib)
    if idx is None:
        idx = eng.load_index(models.root(), lib)
        _ENG["idx"][lib] = idx
    return idx


def libraries(lane, raw, lane_hint=None):
    """the parts libraries a lane asks: its own; the systems lane asks code's, and QA's when the prompt is about tests
    (or the session started in the qa lane)"""
    libs = LIBRARIES.get(lane, (lane,))
    if lane == "systems":
        words = set(re.findall(r"[a-z]+", (raw or "").lower()))
        if not (words & QA_WORDS or lane_hint == "qa"):
            libs = ("code",)
        elif lane_hint == "qa":
            libs = ("qa", "code")
    return libs


def _short(text, n):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _stale(idx, d):
    """P8 upkeep: a recipe whose file (or line) is gone is never handed over"""
    if d.get("type") != "recipe" or not d.get("src"):
        return False
    path, _sep, line = str(d["src"]).split(" ")[0].partition(":")
    full = os.path.join(idx.root, path)
    if not os.path.isfile(full):
        return True
    if line.isdigit():
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f) < int(line)
        except OSError:
            return True
    return False


def _text_key(d):
    return " ".join(d.get("toks", [])[:60]) or d.get("id")


def card(idx, lib, lane, d, part, piece=None, know_how=False):
    """one card for the packet: mechanics, kinds, the owner's evidence; the look only when the owner allowed it"""
    eng = engine()
    kmap = idx.kinds.get("_map", {})
    kinds = list((d.get("kinds") or {}).keys())
    axes = {}
    for k in kinds:
        axes.setdefault(kmap.get(k, {}).get("axis", "kind"), []).append(k)
    mech = d.get("mech") or {}
    allow = eng.look_allowed(idx.allows, piece, d.get("piece")) if (piece and d.get("look")) else None
    out = {
        "lane": lane,
        "library": lib,
        "id": d.get("id"),
        "type": d.get("type"),
        "piece": d.get("piece"),
        "title": _short(d.get("title"), 100),
        "part": _short(part, 80),
        "kinds": kinds[:6],
        "axes": axes,
        "avoid": bool(d.get("avoid")),
        "evidence": eng.evidence_note(d) or "",
        "mechanics": "; ".join(f"{k}={_short(v, 40)}" for k, v in [(k, v) for k, v in mech.items() if v not in (None, "", [], {})][:4]),
        "know_how": know_how,
        "look": "hidden (mechanics only)" if d.get("look") and not allow else ("" if not d.get("look") else "allowed by the owner"),
    }
    if allow:
        out["look_reuse"] = {"words": _short(allow.get("words"), 60), "look": "; ".join(f"{k}={v}" for k, v in list(d["look"].items())[:4])}
    return out


def lookup(lanes, raw, piece=None, lane_hint=None, skip=None, lane_score=None):
    """the past parts a prompt should build from, per routed lane -> {cards: [...], libraries: [...], note}.
    `raw`: the owner's words with what they refused already taken out; `skip(d)`: a card never handed over (route
    passes its Sample Game test); `lane_score(lane, text)`: how much a clause is that lane's (route's keywords)"""
    if os.environ.get("KIT_PROMPT_PARTS") == "0":
        return {"cards": [], "libraries": [], "note": "the parts look-up is off (KIT_PROMPT_PARTS=0)"}
    eng = engine()
    skip = skip or (lambda d: False)
    cards, libs_info, seen_ids, seen_text = [], [], set(), set()
    for rank, lane in enumerate(lanes):
        lead = rank == 0
        for lib in libraries(lane, raw, lane_hint):
            try:
                idx = library_index(lib)
            except Exception as e:  # (the parts library is help, never a reason a prompt fails to compile)
                libs_info.append({"lane": lane, "library": lib, "error": f"{type(e).__name__}: {_short(e, 100)}"})
                continue
            ad = eng.adapter(models.root(), lib) if piece else None  # (an adapter breaks a NAMED piece into parts)
            text, source = raw, "the prompt's clauses"
            if lead and ad is not None and hasattr(ad, "brief"):
                try:  # (as `kit parts <lane> plan <piece>` does: the piece's own brief names its parts)
                    brief = ad.brief(models.root(), piece)
                except Exception:
                    brief = None
                if brief:
                    text, source = f"{brief}\n{raw}", f"{piece}'s brief"
            try:
                head, parts = eng.breakdown(idx, ad, piece or "prompt", text)
            except Exception:
                head, parts = eng.breakdown(idx, None, piece or "prompt", text)
            if not lead or not parts:
                # another lane's answer is looked up from the clause that is ITS part of the ask ("make the ui clean"
                # for the UI lane), never from the lead lane's words
                text = raw
                if lane_score and parts:
                    best = max(parts, key=lambda p: lane_score(lane, p["words"]))
                    if lane_score(lane, best["words"]) > 0:
                        text = best["words"]
                parts = [{"title": _short(text, 80), "words": text, "hero": True, "kinds": eng.query_kinds(idx.kinds, text)}]
            parts = sorted(parts, key=lambda p: (0 if p.get("hero") else 1))[: LEAD_PARTS if lead else OTHER_PARTS]
            libs_info.append({"lane": lane, "library": lib, "cards": len(idx.docs), "parts": [p["title"] for p in parts], "kinds": sorted({k for p in parts for k in p.get("kinds", [])}), "from": source if lead else "its clause of the prompt"})
            per_part = 2 if lead else 1
            for p in parts:
                found = eng.search(idx, p["words"], k=POOL, kinds=p.get("kinds") or None, exclude=piece, context=head)
                took, avoid_taken = 0, False
                for _s, d, _parts in found:
                    if skip(d) or _stale(idx, d):
                        continue
                    key = _text_key(d)
                    if d.get("id") in seen_ids or key in seen_text:
                        continue  # (P8: a duplicate takes one place)
                    if took >= per_part and not (lead and d.get("avoid") and not avoid_taken):
                        continue
                    seen_ids.add(d.get("id"))
                    seen_text.add(key)
                    cards.append(card(idx, lib, lane, d, p["title"], piece))
                    took += 1
                    avoid_taken = avoid_taken or bool(d.get("avoid"))
                    if took >= per_part + 1:
                        break
                if lead and not avoid_taken:
                    # what the owner REJECTED for this kind of part, read before building it (a wider pool: a
                    # rejection ranks under the loved cards, and it is the one a prompt must not repeat)
                    for _s, d, _x in eng.search(idx, p["words"], k=AVOID_POOL, kinds=p.get("kinds") or None, exclude=piece, context=head, cap=False):
                        if not d.get("avoid") or skip(d) or d.get("id") in seen_ids or _text_key(d) in seen_text:
                            continue
                        seen_ids.add(d.get("id"))
                        seen_text.add(_text_key(d))
                        cards.append(card(idx, lib, lane, d, p["title"], piece))
                        break
                if lead and p is parts[0]:
                    # know-how: what already does this kind of part's job (a helper, a proven recipe)
                    kinds = list(p.get("kinds") or [])
                    words = " ".join(eng.kmap_labels(idx, kinds)) or p["words"]
                    for _s, d, _x in eng.search(idx, words, k=POOL, kinds=kinds or None, types=("helper", "recipe"), exclude=piece, cap=False):
                        if skip(d) or _stale(idx, d) or d.get("id") in seen_ids or _text_key(d) in seen_text:
                            continue
                        seen_ids.add(d.get("id"))
                        seen_text.add(_text_key(d))
                        cards.append(card(idx, lib, lane, d, p["title"], piece, know_how=True))
                        break
    # the lead lane's cards first (they were added first); a whole-prompt answer stays inside the budget
    return {"cards": cards[:CARDS_TOTAL], "libraries": libs_info, "note": ""}


def line(c):
    """one card as a prompt line (mechanics only unless the owner allowed the look)"""
    kinds = ", ".join(c.get("kinds") or []) or "no kind"
    where = f"`{c['id']}`" + (f" [{c['piece']}]" if c.get("piece") else "")
    if c.get("avoid"):
        return f"AVOID past part {where} ({c['library']} library, kinds {kinds}): {c['title']} - the owner rejected it ({c['evidence'] or 'graveyard'}); read why before building '{c['part']}'"
    head = "know-how" if c.get("know_how") else "past part"
    text = f"{head} {where} ({c['type']}, {c['library']} library, kinds {kinds}) for '{c['part']}': {c['title']}"
    if c.get("mechanics"):
        text += f" - mechanics: {c['mechanics']}"
    if c.get("evidence"):
        text += f" - {c['evidence']}"
    if c.get("look_reuse"):
        text += f" - LOOK REUSE (the owner allowed it: \"{c['look_reuse']['words']}\"): {c['look_reuse']['look']}"
    else:
        text += " - reuse its mechanics, never its look"
    return text + f" (lune run kit parts {c['library']} find)"
