"""checks.py - the PROMPT-X gates (LIMITATIONS_FIXES_V4 13.7 item 3: the six traps), shared by the unit tests
(kit/test/python/test_prompt_*.py) and `kit selftest` (kit/selftest/prompt/run.py). Each returns a list of problems;
an empty list passes."""

import re

try:
    from . import models, route
except ImportError:
    import models
    import route

# a scripted chain of thought in any spelling ("Think Step-By-Step", "let us think through it step by step",
# "work through this step by step", "chain-of-thought"): the codex / local profiles strip it, the gate fails on it
COT_RE = re.compile(
    r"(?:\blet(?:'s| us)[\s,]+)?\b(?:think|reason|work|go|walk|break|reflect)\b(?:[\s,]+[\w']+){0,4}?[\s,]+step[\s\-]+by[\s\-]+step\b"
    r"|\bchain[\s\-]+of[\s\-]+thought\b|\bshow\s+your\s+(?:reasoning|work)\b|\bstep[\s\-]+by[\s\-]+step\s+reasoning\b",
    re.I,
)


def find_cot(text):
    """every scripted chain-of-thought phrase in the text (unicode dashes read as '-')"""
    return [m.group(0) for m in COT_RE.finditer(route.normalize(text or ""))]


def strip_cot(text):
    return COT_RE.sub(" ", route.normalize(text or ""))


def negative_word_leak(text, raw=None):
    """trap 1: a FLUX.2 prompt names only what is drawn - no negation word of any form (route.NEG_TRIGGERS, '-free',
    'non-'), and none of the words the owner's raw prompt negated (unless the owner also asked for that word)"""
    t = route.normalize(text or "")
    out = []
    for w in route.NEG_TRIGGERS:
        if re.search(rf"(?<![\w']){re.escape(w)}(?![\w'])", t, flags=re.I):
            out.append(f"negative word leak: '{w}' in the FLUX.2 prompt")
    if route.NEG_AFFIX.search(t):
        out.append(f"negative word leak: '{route.NEG_AFFIX.search(t).group(0)}' in the FLUX.2 prompt")
    if raw:
        asked = set(route.words(route.strip_negated(raw)))
        for w in sorted(route.negated_words(raw) - asked - route.STOP):
            if len(w) > 2 and re.search(rf"\b{re.escape(w)}\b", t, flags=re.I):
                out.append(f"negative word leak: the owner said no '{w}' and it is in the FLUX.2 prompt")
    return out


def model_drift(packets):
    """trap 2: each profile's shape (packets: {model: packet})"""
    out = []
    c = packets.get("codex")
    if c:
        low = c["orchestrator_prompt"].lower()
        out += [f"model drift: codex keeps the chain-of-thought script '{m}'" for m in find_cot(low)]
        if not low.startswith("## objective"):
            out.append("model drift: codex does not open on ## Objective")
        if "## verify" not in low or low.index("## verify") > low.index("## hard invariants"):
            out.append("model drift: codex's verify commands are not ahead of the invariants")
    cl = packets.get("claude")
    if cl:
        t = cl["orchestrator_prompt"]
        for tag in ("<context>", "<vault_guardrails>", "<objective>", "<acceptance_gates>"):
            if tag not in t:
                out.append(f"model drift: claude lacks {tag}")
        if "(why:" not in t:
            out.append("model drift: claude's rules carry no rationale")
    g = packets.get("gemini")
    if g:
        t = g["orchestrator_prompt"]
        a, b = t.find("## Grounded File & Constraint Matrix"), t.find("## Final Execution Directive")
        if a < 0 or b < 0 or b < a:
            out.append("model drift: gemini's final directive is not after its grounded tables")
        if "cite the command output" not in t.lower():
            out.append("model drift: gemini is not asked for citations")
    return out


def token_budget(packet):
    """trap 3: inside the model's budget (2,500 frontier / 2,000 codex / 450 local)"""
    budget = models.profile(packet["target_model"])["budget"]
    n = models.count_tokens(packet["orchestrator_prompt"])
    return [] if n <= budget else [f"over budget: {n} tokens > {budget} for {packet['target_model']}"]


def missing_grounding(packet):
    """trap 4: the lead lane's golden / graveyard records, engine facts and API names were hydrated (records are asked
    for where the project's vault pages HOLD rows - route.filed_records counts them from the files: a lane with none
    has nothing to hydrate)"""
    g = packet.get("repo_grounding") or {}
    filed = g.get("filed")  # (absent: a packet from before route.py said which lanes hold records - all are asked for)
    out = []
    for key in ("graveyard_bans", "golden_refs", "engine_caps", "api_docs"):
        kind = {"graveyard_bans": "graveyard", "golden_refs": "golden"}.get(key)
        if kind and filed is not None and not filed.get(kind):
            continue
        if not g.get(key):
            out.append(f"missing repo grounding: {key} is empty")
    out += [f"missing repo grounding: API {p}" for p in g.get("api_problems", [])]
    # hydrated is not enough: the records must reach the RENDERED prompt (a long prompt once pruned them all away)
    text = (packet.get("orchestrator_prompt") or "").lower()
    if g.get("graveyard_bans") and not any(f"graveyard '{b['tried'].lower()}" in text for b in g["graveyard_bans"]):
        out.append("missing repo grounding: graveyard records were found but none reached the prompt")
    lead = packet["lanes"][0] if packet["lanes"] else None
    lead_filed = filed is None or lead in filed.get("graveyard", [])
    if lead and lead_filed and not any(b.get("lane") == lead for b in g.get("graveyard_bans", [])) and lead not in ("sfx", "systems"):
        out.append(f"missing repo grounding: no {lead} graveyard record")
    return out


def parts_grounding(packet):
    """the Parts RAG (partsrag.py over kit parts' libraries): the lead lane's own library answered, every card handed
    over its mechanics with the look hidden unless the owner allowed it, and a frontier model's prompt carries the cards"""
    g = packet.get("repo_grounding") or {}
    cards = g.get("parts") or []
    lead = packet["lanes"][0] if packet.get("lanes") else None
    out = []
    if not cards:
        why = g.get("parts_note") or "no card from any library"
        return [f"missing repo grounding: parts ({why})"]
    if lead and not any(c.get("lane") == lead for c in cards):
        out.append(f"missing repo grounding: parts - no card from the {lead} library")
    text = packet.get("orchestrator_prompt") or ""
    for c in cards:
        if c.get("look_reuse") and c.get("look") != "allowed by the owner":
            out.append(f"parts look leak: {c.get('id')} hands over its look without the owner's look-allow")
        if not c.get("look_reuse") and f"`{c.get('id')}`" in text and "LOOK REUSE" in _card_line(text, c.get("id")):
            out.append(f"parts look leak: {c.get('id')} reached the prompt with its look")
    if models.profile(packet["target_model"])["budget"] >= 2000 and not any(f"`{c.get('id')}`" in text for c in cards):
        out.append("missing repo grounding: parts cards were found but none reached the prompt")
    return out


def _card_line(text, ident):
    i = text.find(f"`{ident}`")
    j = text.find("\n", i)
    return text[i : j if j >= 0 else None]


def api_signatures(packet):
    """the API grounding (docs.py): every verified member carries its exact Luau signature from the type file, and a
    frontier model's prompt carries them (a model that guesses a signature writes code the engine refuses)"""
    g = packet.get("repo_grounding") or {}
    rows = [r for r in g.get("api_detail") or [] if r.get("verified") and r.get("kind") == "member"]
    out = [f"API signature missing: {r['name']} (the kit's type file does not declare it: code typed against it fails "
           "the types gate)" for r in rows if not r.get("signature")]
    text = packet.get("orchestrator_prompt") or ""
    sigs = [r["signature"] for r in rows if r.get("signature")]
    if sigs and models.profile(packet["target_model"])["budget"] >= 2000 and not any(s in text for s in sigs):
        out.append("API signature missing: signatures were found but none reached the prompt")
    return out


def replay(result):
    """trap 6: evolve.evaluate()'s result over the historical prompts - every one carries its guardrail"""
    if not result.get("n"):
        return ["historical replay: no cases"]
    return [f"historical replay MISSED {f['id']}: {f['missing']}" for f in result["failed"]]
