"""expand.py - PROMPT-X stage 3 (LIMITATIONS_FIXES_V4 9.2 row 3; RaR arXiv:2311.04205, Self-Discover
arXiv:2402.03620, Meta-Prompting arXiv:2401.12954): the raw one-liner -> a model-neutral Semantic IR

    {objective, decisions, architectural_invariants, failure_preventers, ordered_steps, done_when_commands, context}

Every item carries a priority (1 = never pruned ... 6 = first to go) so compile.py can hold a token budget without
losing a hard-won rule (ACE arXiv:2510.04618: context collapse). Deterministic and offline."""

import re

try:
    from . import clarify, docs, evolve, models, partsrag, route
except ImportError:
    import clarify
    import docs
    import evolve
    import models
    import partsrag
    import route

FILLER = [
    r"\byo\b", r"\bpls\b", r"\bplease\b", r"\bbasically\b", r"\bkinda\b", r"\bsorta\b", r"\bgenuinely\b", r"\blike,",
    r"\bu\b", r"\bur\b", r"\bsmh\b", r"\blol\b", r"\bbro\b", r"\bman\b", r"\bdude\b", r"\bok so\b", r"\bso yeah\b",
]


def applies(inv, raw_lower):
    """a rule with `when` words guards only the prompts that touch its topic (terrain rules for terrain asks)"""
    return not inv.get("when") or any(route._has(raw_lower, w) for w in inv["when"])


def clean_objective(raw):
    text = (raw or "").strip()
    for pat in FILLER:
        text = re.sub(pat, " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,.")
    if text:
        text = text[0].upper() + text[1:]
    return text


def build_ir(routed, clarified=None, answers=None, target_model="claude"):
    clarified = clarified or clarify.audit_ambiguity(routed)
    chosen = clarify.decisions(clarified, answers or {})
    lanes = routed["lanes"]
    lead = lanes[0] if lanes else None
    coupled = {c["lane"] for c in routed.get("xp_coupling", [])}
    raw_lower = routed["raw_prompt"].lower()
    g = routed["repo_grounding"]

    invariants, preventers, steps, done, context = [], [], [], [], []
    for lane in lanes:
        t = models.template(lane)
        base = 1 if lane == lead else (3 if lane in coupled else 2)
        for i, inv in enumerate(t.get("invariants", [])):
            if not applies(inv, raw_lower):
                continue
            invariants.append({"lane": lane, "id": inv["id"], "text": inv["value"], "why": inv.get("why", ""), "priority": base if i < 4 else base + 1})
        # the owner's own complaint words name the failure to prevent (heavy, floaty, slop ...)
        for word, rule in t.get("failure_lexicon", {}).items():
            if route._has(raw_lower, word):
                preventers.append({"lane": lane, "text": rule, "source": f"the prompt says '{word}'", "priority": 1 if lane in (lead,) or lane not in coupled else 2})
        if lane in coupled:
            steps.append({"lane": lane, "text": f"{t['start']}: " + next(c["why"] for c in routed["xp_coupling"] if c["lane"] == lane), "priority": 3})
        else:
            for j, s in enumerate(t.get("steps", [])):
                steps.append({"lane": lane, "text": s, "priority": 2 if lane == lead else 3 if j < 3 else 4})
        for cmd in t.get("done_when", []):
            if cmd not in [d["text"] for d in done]:
                done.append({"lane": lane, "text": cmd, "priority": 1 if lane == lead else 3})
        for f in t.get("context_files", []):
            context.append({"lane": lane, "text": f, "priority": 3 if lane == lead else 6})
    for b in g.get("graveyard_bans", []):
        preventers.append(
            {
                "lane": b["lane"],
                "text": f"graveyard '{b['tried']}': {b['rule']}",
                "source": "vault graveyard",
                "priority": 1 if b.get("matched") else 3,
            }
        )
    for rule in evolve.learned_rules(lanes, target_model):
        preventers.append({"lane": rule["lane"], "text": rule["text"], "source": "learned (evolve)", "priority": 2})
    golden = [
        {"lane": r["lane"], "text": f"golden '{r['piece']}' ({r['score_10']:g}/10): {r['mechanic']}", "priority": 2 if r.get("matched") else 4}
        for r in g.get("golden_refs", [])
    ]
    lessons = [{"lane": r["lane"], "text": f"lesson {r['date']}: {r['text']}", "priority": 4} for r in g.get("lessons_top5", [])]
    caps = [{"lane": c["lane"], "text": c["text"], "priority": 3 if c["lane"] == lead else 5} for c in g.get("engine_caps", [])]
    # the Roblox API with its exact Luau signature (docs.py); a name the owner's words asked for in the lead lane's
    # scope ranks above the template's standing list
    detail = {a["name"]: a for a in g.get("api_detail", [])}
    api = []
    anchored = False
    for a in g.get("api_docs", []):
        row = detail.get(a) or {"name": a}
        prio = 4 if str(row.get("scope", "")).startswith(("prompt", "family")) and row.get("lane") == lead else 5
        if not anchored and row.get("lane") == lead and row.get("signature"):
            prio, anchored = 2, True  # (one exact signature of the lead lane survives any budget: IFScale keeps a floor)
        api.append({"lane": None, "text": "API " + docs.line(row), "priority": prio})
    # past parts by kind (partsrag.py over kit parts' libraries): their MECHANICS are reused, never their look; a card
    # the owner rejected is a guardrail, not context
    card_anchored = False
    for p in g.get("parts", []):
        if not p.get("id"):
            continue
        if p.get("avoid"):
            preventers.append({"lane": p["lane"], "text": partsrag.line(p), "source": f"kit parts {p.get('library', p['lane'])} (the owner rejected it)", "priority": 3 if p["lane"] == lead else 4})
        else:
            prio = 4 if p["lane"] == lead else 5
            if not card_anchored and p["lane"] == lead:
                prio, card_anchored = 2, True  # (the lead lane's best past part survives any budget)
            api.append({"lane": p["lane"], "text": partsrag.line(p), "priority": prio})
    decisions = [
        {"lane": d["lane"], "text": f"{d['slot']}: {d['chose']} ({d['how']})", "priority": 1}
        for d in chosen
    ]
    objective = clean_objective(routed["raw_prompt"])
    return {
        "objective": objective,
        "lanes": lanes,
        "lead": lead,
        "game": g.get("game"),
        "decisions": decisions,
        "architectural_invariants": invariants,
        "failure_preventers": preventers,
        "golden_mechanics": golden,
        "lessons": lessons,
        "engine_caps": caps,
        "api": api,
        "ordered_steps": steps,
        "done_when_commands": done,
        "context": context,
        "coupling": routed.get("xp_coupling", []),
    }
