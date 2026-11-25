"""clarify.py - PROMPT-X stage 2 (LIMITATIONS_FIXES_V4 9.2 row 2; ClarifyGPT arXiv:2310.10996, IPC arXiv:2402.03099):
what the repo already decides is filled in silently; ONLY an open taste, originality or destructive-scope fork becomes a
question, at most 3 crisp multiple-choice questions with a starred default (*A).

Each lane template lists its slots ({id, kind: taste|scope, weight, resolved_by[], question, options[]}); a slot is
resolved when the raw prompt says one of its words. The ambiguity score is the weighted share of open slots,
averaged over the lanes (the lead lane counts double)."""

try:
    from . import models, route
except ImportError:
    import models
    import route

MAX_QUESTIONS = 3


def _resolved(raw_lower, slot):
    return [w for w in slot.get("resolved_by", []) if route._has(raw_lower, w.strip()) or (w.endswith(" ") and w in raw_lower)]


def audit_ambiguity(routed):
    """-> {score, questions[{id, lane, kind, question, options}], resolved{}, auto_filled{}}"""
    raw = routed["raw_prompt"]
    raw_lower = raw.lower()
    asked = route.strip_negated(raw).lower()  # a slot is resolved by what IS asked ("not calm" resolves nothing)
    lanes = routed["lanes"]
    auto, resolved, open_slots = {}, {}, []
    total_w = open_w = 0.0
    for rank, lane in enumerate(lanes):
        t = models.template(lane)
        for inv in t.get("invariants", []):
            if not inv.get("when") or any(route._has(raw_lower, w) for w in inv["when"]):
                auto[f"{lane}.{inv['id']}"] = inv["value"]
        lane_w = 2.0 if rank == 0 else 1.0
        coupled = any(c["lane"] == lane for c in routed.get("xp_coupling", []))
        for slot in t.get("slots", []):
            w = float(slot.get("weight", 0.3)) * lane_w
            hits = _resolved(asked, slot)
            if coupled:
                # a lane pulled in by coupling follows the lead lane's decisions: its forks are never asked
                resolved[f"{lane}.{slot['id']}"] = "follows the lead lane"
                continue
            total_w += w
            if hits:
                resolved[f"{lane}.{slot['id']}"] = ", ".join(sorted(set(h.strip() for h in hits)))
            else:
                open_w += w
                open_slots.append((w, rank, lane, slot))
    if routed.get("entities", {}).get("destructive"):
        # replacing existing work is never guessed
        open_slots.append(
            (
                99.0,
                -1,
                lanes[0] if lanes else "systems",
                {
                    "id": "destructive",
                    "kind": "scope",
                    "question": f"The prompt says '{routed['entities']['destructive'][0]}': what happens to the existing work?",
                    "options": ["*A Keep it and build the new version beside it", "B Replace it (the old files are kept in git)"],
                },
            )
        )
        total_w += 1.0
        open_w += 1.0
    open_slots.sort(key=lambda s: (-s[0], s[1]))
    questions, asked = [], set()
    for _w, _rank, lane, slot in open_slots:
        key = slot["id"] if slot["kind"] == "scope" else f"{lane}.{slot['id']}"
        if key in asked:
            continue  # one scope question covers every lane
        asked.add(key)
        questions.append(
            {
                "id": f"q{len(questions) + 1}",
                "slot": f"{lane}.{slot['id']}",
                "lane": lane,
                "kind": slot["kind"],
                "question": slot["question"],
                "options": list(slot["options"]),
            }
        )
        if len(questions) >= MAX_QUESTIONS:
            break
    score = round(open_w / total_w, 2) if total_w else 0.0
    return {"score": score, "questions": questions, "resolved": resolved, "auto_filled": auto}


def parse_answers(text):
    """'q1=A,q2=B' (or 'q1:A q2:B') -> {'q1': 'A', 'q2': 'B'}"""
    out = {}
    for part in (text or "").replace(";", ",").replace(" ", ",").split(","):
        if "=" in part or ":" in part:
            k, v = part.replace(":", "=").split("=", 1)
            if k.strip() and v.strip():
                out[k.strip().lower()] = v.strip().upper()[:1]
    return out


def decisions(clarified, answers):
    """each question's chosen option: the owner's answer, else the starred default (said so: never silently)"""
    out = []
    for q in clarified["questions"]:
        letter = (answers or {}).get(q["id"])
        chosen, how = None, "answered"
        for opt in q["options"]:
            body = opt.lstrip("*").strip()
            if letter and body.upper().startswith(letter + " "):
                chosen = body[2:].strip()
        if chosen is None:
            default = next((o for o in q["options"] if o.startswith("*")), q["options"][0])
            chosen, how = default.lstrip("*").strip()[2:].strip(), "default (not answered)"
        out.append({"id": q["id"], "slot": q["slot"], "lane": q["lane"], "chose": chosen, "how": how})
    return out
