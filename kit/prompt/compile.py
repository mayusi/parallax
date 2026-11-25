"""compile.py - PROMPT-X stage 4 (LIMITATIONS_FIXES_V4 9.2 row 4 / 9.3; PromptBridge arXiv:2512.01420, FormatSpread
arXiv:2310.11324, IFScale arXiv:2507.11538): the Semantic IR rendered for ONE target model, inside its token budget.

    claude  XML sections, the why behind each rule, read-only context before the directives        <= 2,500 tokens
    codex   flat concise Markdown, verify commands up front, no scripted chain of thought            <= 2,000 tokens
    gemini  grounded tables first, DO / DO NOT table, the final directive LAST, citations required  <= 2,500 tokens
    local   one focus, flat JSON, a YES/NO-or-JSON answer                                            <=   450 tokens

Over budget, the lowest-priority item goes first (a context file, then an API name ... a priority-1 rule last) and
every pruned item is listed in the packet."""

import json
import re

try:
    from . import cases, checks, clarify, expand, models, subprompts
except ImportError:
    import cases
    import checks
    import clarify
    import expand
    import models
    import subprompts

SECTIONS = ("context", "guardrails", "objective", "gates")


def resolve_model(explicit=None, env=None):
    """--model, else KIT_AI_MODEL, else the harness's own marker, else claude (said in the packet's profile field)"""
    import os

    env = env if env is not None else os.environ
    if explicit:
        m = explicit.lower()
        if m in ("gpt", "openai", "o3", "o4", "codex"):
            return "codex"
        if m in models.MODELS:
            return m
        raise ValueError(f"unknown model '{explicit}' (claude|codex|gemini|local)")
    ai = env.get("PARALLAX_AI_MODEL") or env.get("KIT_AI_MODEL")  # (the Parallax name first, the old one still read)
    if ai:
        return resolve_model(ai, {})
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if env.get("CODEX_CI") or env.get("CODEX_SANDBOX") or env.get("CODEX_HOME"):
        return "codex"
    if env.get("GEMINI_CLI"):
        return "gemini"
    return "claude"


def _items(ir, prof):
    """the IR flattened into (section, priority, text, why, lane) items"""
    local = prof["format"] == "json_micro"
    lead = ir["lead"]
    out = []

    def add(section, item, why=""):
        if local and item.get("lane") not in (lead, None):
            return  # a small model gets the lead lane only
        out.append({"section": section, "priority": item["priority"], "text": item["text"], "why": why, "lane": item.get("lane")})

    for it in ir["context"]:
        add("context", it)
    for it in ir["api"]:
        add("context", it)
    for it in ir["engine_caps"]:
        add("context", it)
    for it in ir["golden_mechanics"]:
        add("context", it)
    for it in ir["lessons"]:
        add("context", it)
    for it in ir["architectural_invariants"]:
        if local and it.get("lane") == lead:
            it = dict(it, priority=1)  # a small model keeps its one lane's rules above everything else
        add("guardrails", it, it.get("why", ""))
    kept = 0
    for it in ir["failure_preventers"]:
        if local and kept < 2 and it.get("lane") == lead and it.get("source") == "vault graveyard":
            it = dict(it, priority=0)  # a small model keeps its lane's two best-matched failure records above all
            kept += 1
        add("guardrails", it, it.get("source", ""))
    for it in ir["decisions"]:
        add("objective", it)
    for it in ir["ordered_steps"]:
        add("objective", it)
    for it in ir["done_when_commands"]:
        add("gates", it)
    return out


def _clean(text, prof, owner_prompt=False):
    """the profile's chain-of-thought ban applies everywhere; the un-measurable fluff ban only to the owner's own prompt
    (a quoted verdict keeps its words)"""
    if owner_prompt:
        for phrase in prof.get("banned_phrases", []):
            # (any spacing or hyphen: "high-quality"; the punctuation the phrase leaves behind goes with it)
            pat = r"[\s\-]+".join(re.escape(w) for w in phrase.split())
            text = re.sub(rf"\b{pat}\b\s*[:;,!.]*", " ", text, flags=re.I)
        text = re.sub(r"^[\s:;,!.\-]+", "", text)
    if prof.get("chain_of_thought") == "strip":
        text = checks.strip_cot(text)
        for phrase in prof.get("cot_phrases", []):
            text = re.sub(r"[,;.]?\s*" + re.escape(phrase) + r"[,;.]?", " ", text, flags=re.I)
        text = re.sub(r"\s+([,.;!?])", r"\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _render(ir, items, prof):
    fmt = prof["format"]
    sec = {s: [i for i in items if i["section"] == s] for s in SECTIONS}
    objective = _clean(ir["objective"], prof, owner_prompt=True)
    lanes = ", ".join(ir["lanes"])
    game = ir.get("game") or "none (the kit's home)"
    why_on = prof.get("rationale")

    def bullet(i, with_why=why_on):
        t = _clean(i["text"], prof)
        lane = f"[{i['lane']}] " if i.get("lane") else ""
        return f"- {lane}{t}" + (f" (why: {_clean(i['why'], prof)})" if with_why and i.get("why") else "")

    decision_texts = {d["text"] for d in ir["decisions"]}
    decisions = [i for i in sec["objective"] if i["text"] in decision_texts]
    steps = [i for i in sec["objective"] if i["text"] not in decision_texts]
    if fmt == "xml":
        parts = [
            "<context>",
            f"Lanes: {lanes}. Game: {game}. Read these before acting; they are facts of this repo, not suggestions.",
            *[bullet(i, False) for i in sec["context"]],
            "</context>",
            "<vault_guardrails>",
            "Rules from the owner's verdicts and the kit's gates; each says why it exists.",
            *[bullet(i) for i in sec["guardrails"]],
            "</vault_guardrails>",
            "<objective>",
            objective,
            *(["Decided:"] + [bullet(i, False) for i in decisions] if decisions else []),
            "Plan, in order:",
            *[f"{n}. [{i['lane']}] {_clean(i['text'], prof)}" for n, i in enumerate(steps, 1)],
            "</objective>",
            "<acceptance_gates>",
            "Done only when each passes and you looked at its evidence; the owner's verdict is the only quality signal.",
            *[bullet(i, False) for i in sec["gates"]],
            "</acceptance_gates>",
        ]
        return "\n".join(parts)
    if fmt == "markdown_flat":
        parts = [
            "## Objective",
            objective,
            *[f"- {_clean(i['text'], prof)}" for i in decisions],
            "## Verify (run these; exit 0 is required)",
            *[f"- `{_clean(i['text'], prof)}`" if i["text"].startswith("lune") else f"- {_clean(i['text'], prof)}" for i in sec["gates"]],
            "## Files & Contracts",
            f"- lanes: {lanes}; game: {game}",
            *[bullet(i, False) for i in sec["context"]],
            "## Hard Invariants",
            *[bullet(i, False) for i in sec["guardrails"]],
            "## Steps",
            *[f"{n}. {_clean(i['text'], prof)}" for n, i in enumerate(steps, 1)],
        ]
        return "\n".join(parts)
    if fmt == "table_first":
        root = models.root().replace("\\", "/")

        def anchor(t):
            # a repo path is anchored (file:///...) so Gemini resolves it before reading anything else
            if re.match(r"^[\w.\-]+/[\w.\-/<>]+\.\w+$", t) and "<" not in t:
                return f"[{t}](file:///{root}/{t})"
            return t

        rows = ["| lane | file / API / fact |", "|---|---|"]
        rows += [f"| {i.get('lane') or '-'} | {anchor(_clean(i['text'], prof)).replace('|', '/')} |" for i in sec["context"]]
        do = ["| DO | DO NOT (what failed when it was not done) |", "|---|---|"]
        do += [f"| {_clean(i['text'], prof).replace('|', '/')} | {(_clean(i['why'], prof) or '-').replace('|', '/')} |" for i in sec["guardrails"]]
        parts = [
            "## Grounded File & Constraint Matrix",
            f"Lanes: {lanes}. Game: {game}.",
            *rows,
            "## Acceptance",
            *[f"- {_clean(i['text'], prof)}" for i in sec["gates"]],
            "## DO / DO NOT",
            *do,
            "## Final Execution Directive",
            objective,
            *[f"- {_clean(i['text'], prof)}" for i in decisions],
            *[f"{n}. {_clean(i['text'], prof)}" for n, i in enumerate(steps, 1)],
            "Cite the command output or file:line behind every claim of done.",
        ]
        return "\n".join(parts)
    if fmt == "json_micro":
        body = {
            "task": objective,
            "decided": [_clean(i["text"], prof) for i in decisions],
            "must": [_clean(i["text"], prof) for i in sec["guardrails"]],
            "next": [_clean(i["text"], prof) for i in steps[: prof.get("max_tasks", 1)]],
            "check": [_clean(i["text"], prof) for i in sec["gates"][:1]],
            "context": [_clean(i["text"], prof) for i in sec["context"]],
            "answer": 'JSON {"done": true|false, "evidence": "<command output>"}',
        }
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    raise ValueError(f"unknown format {fmt}")


OBJECTIVE_SHARE = 0.35  # the owner's own words may take at most this share of the budget: the rules come first


def render_within_budget(ir, prof):
    items = _items(ir, prof)
    budget = prof["budget"]
    pruned = []
    cap = int(budget * OBJECTIVE_SHARE)
    if models.count_tokens(ir["objective"]) > cap:
        # a long prompt is shortened BEFORE any rule is pruned (the packet keeps it whole in raw_prompt)
        words = ir["objective"].split()
        while len(words) > 1 and models.count_tokens(" ".join(words)) > cap - 12:
            words = words[: int(len(words) * 0.9)]
        head = " ".join(words)
        if models.count_tokens(head) > cap - 12:  # (one huge token: cut by characters)
            head = head[: max(1, (cap - 12) * 4)]
        ir = dict(ir, objective=head + " … (the rest is in raw_prompt)")
        pruned.append({"section": "objective", "priority": 1, "text": f"the owner's prompt shortened to {OBJECTIVE_SHARE:.0%} of the budget"})
    text = _render(ir, items, prof)
    # among equal priorities: context goes first, then plan steps, then rules, the gates last
    prune_rank = {"context": 3, "objective": 2, "guardrails": 1, "gates": 0}
    while models.count_tokens(text) > budget and items:
        victim = max(range(len(items)), key=lambda n: (items[n]["priority"], prune_rank[items[n]["section"]], n))
        gone = items.pop(victim)
        pruned.append({"section": gone["section"], "priority": gone["priority"], "text": gone["text"][:120]})
        text = _render(ir, items, prof)
    # the owner's own prompt longer than the whole budget: its head is kept (the packet keeps it whole in raw_prompt)
    if models.count_tokens(text) > budget:
        words = ir["objective"].split()
        while words and models.count_tokens(text) > budget:
            words = words[: max(0, int(len(words) * 0.85) - 1)]
            text = _render(dict(ir, objective=" ".join(words) + " … (the rest is in raw_prompt)"), items, prof)
        pruned.append({"section": "objective", "priority": 1, "text": "the owner's prompt shortened to fit the budget"})
    if prof["format"] == "json_micro":
        # (a small model gets the lead lane only: the other lanes' items are listed, not silently gone)
        skipped = [i for i in _items(ir, dict(prof, format="xml")) if i.get("lane") not in (ir["lead"], None)]
        pruned += [{"section": i["section"], "priority": i["priority"], "text": f"(not for a small model) {i['text'][:100]}"} for i in skipped]
    return text, pruned


def _cut(text, n):
    """at most n characters, cut at a word boundary"""
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",;:") + " …"


def lane_briefs(ir):
    """each lane's part of the work in one line (kit kickoff's --<lane> text): the objective and the lane's first real
    stage; a coupled lane says why it is pulled in"""
    out = {}
    coupled = {c["lane"]: c["why"] for c in ir.get("coupling", [])}
    # the board text is cleaned like a codex prompt: no fluff, no scripted chain of thought
    obj = _cut(_clean(ir["objective"], models.profile("codex"), owner_prompt=True), 110)
    for lane in ir["lanes"]:
        if lane in coupled:
            out[lane] = _cut(f"{obj} - {coupled[lane]}", 220)
            continue
        steps = [s["text"] for s in ir["ordered_steps"] if s["lane"] == lane and "kit start" not in s["text"]]
        out[lane] = _cut(f"{obj} - first: {steps[0]}" if steps else obj, 220)
    return out


def _ir_lane(case_lane):
    """a registry lane -> PROMPT-X's (code and qa are its systems lane)"""
    return "systems" if case_lane in ("code", "qa") else case_lane


def add_cases(ir, routed):
    """the CASE CONTRACTS into the guardrails (priority 1, compact: the case, its first floor steps, the forbidden
    routes, the owner stops) and the lead lane's CAPABILITY MENU into the objective at priority 4 - the first thing a
    tight budget drops, before the repo's API signatures and past parts (`parallax case <lane> "<words>"` prints the
    whole menu any time) - PARALLAX spec §3.2-3.3, inside the model's budget"""
    for c in routed.get("case_contracts") or []:
        floor = c.get("required_tools") or []
        text = (f"case {c['case_id']}: floor " + " -> ".join(floor[:4]) + (" -> ..." if len(floor) > 4 else "")
                + (f" | forbidden: {', '.join(c['forbidden_tools'])}" if c.get("forbidden_tools") else "")
                + (f" | owner stops: {', '.join(c['owner_stops'])}" if c.get("owner_stops") else "")
                + (f" | won with before: {', '.join(c['learned_tools'])}" if c.get("learned_tools") else ""))
        ir["architectural_invariants"].append({"priority": 1, "text": text, "why": f"case contract {c['case_id']}",
                                               "lane": _ir_lane(c["lane"])})
    menu = routed.get("capability_menu") or []
    lane = routed.get("capability_lane")
    if menu and lane:
        ir["ordered_steps"].append({
            "priority": 4,
            "lane": _ir_lane(lane),
            "text": f"after the refs: choose per part / beat from the {lane} capability menu and write "
                    f"<piece>.plan.json (part_or_beat_tools, considered_and_skipped) before any heavy build: "
                    + " ".join(menu),
        })


def compile_packet(routed, answers=None, target_model="claude"):
    """routed (route.route_intent) + the owner's answers -> the PromptPacket v1 as a dict"""
    model = resolve_model(target_model)
    prof = models.profile(model)
    if not routed["lanes"]:
        raise ValueError("no lane matched these words: name what to make (a model, an effect, an animation, a map, a screen, a sound, a system) or pass --lane")
    clarified = clarify.audit_ambiguity(routed)
    ir = expand.build_ir(routed, clarified, answers or {}, model)
    add_cases(ir, routed)
    text, pruned = render_within_budget(ir, prof)
    tools = subprompts.build(routed, ir)
    packet = models.PromptPacket(
        raw_prompt=routed["raw_prompt"],
        target_model=model,
        profile=prof["name"],
        lanes=list(routed["lanes"]),
        ambiguity={"score": clarified["score"], "questions": clarified["questions"]},
        answers=dict(answers or {}),
        auto_filled=clarified["auto_filled"],
        repo_grounding=routed["repo_grounding"],
        orchestrator_prompt=text,
        tool_subprompts=tools,
        lane_briefs=lane_briefs(ir),
        done_when=[d["text"] for d in ir["done_when_commands"]],
        token_count=models.count_tokens(text),
        pruned=pruned,
    )
    out = packet.to_dict()
    out["case_contracts"] = list(routed.get("case_contracts") or [])
    out["capability_lane"] = routed.get("capability_lane")
    out["capability_menu"] = list(routed.get("capability_menu") or [])
    return out
