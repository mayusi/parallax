"""evolve.py - PROMPT-X stage 6 (LIMITATIONS_FIXES_V4 9.2 row 6 / 9.4 stage 4): learn from what happened to a compiled
prompt, in small itemized steps that never rewrite the playbook wholesale.

  TextGrad (arXiv:2406.07496)  a "textual gradient": the owner's verdict words and the failed gates' summaries are
                               matched against each lane's failure lexicon; a rule the packet did NOT carry is blamed,
                               and a failed gate that states its measured bound ("2f > 1f") blames that bound. Each blame
                               names where it points (V4 9.4): template:<lane> (the rule was never compiled) or
                               profile:<model> (compiled, then pruned for that model's budget).
  ACE (arXiv:2510.04618)       the fix is an itemized delta (at most 3 rules added, a rule removed only when its harmful
                               count beats its helpful count by 2); each learned rule keeps helpful / harmful counters.
  GEPA (arXiv:2507.19457)      at most 5 candidates per (lane, model) kept on a Pareto frontier of held-out cases passed
                               (per INSTANCE: a candidate that alone passes some case stays), verdict fixes carried and
                               tokens (lower).
  A delta is accepted ONLY if the held-out benchmark (kit/prompt/benchmarks.json: real owner prompts and the guardrail
  words each must carry) loses no case the current best passed, scores at least the current best and at least 90%,
  inside every token budget.

The verdicts are the OWNER's, from the record only (evolve_from_verdicts: every `kit verdict` note by the owner, matched to
the prompt compiled for that piece with --piece; recorded(): a verdict typed on the command line must quote one) - a
session never invents a verdict to move the playbook.
What was learned lives in kit/knowledge/vault/prompt/{pareto_frontier,changelog,consumed}.json (KIT_PROMPT_VAULT moves it);
the per-compile traces are working data in build/prompt/traces.json (git-ignored: compiling never dirties the tree)."""

import datetime
import hashlib
import json
import os
import re
import time

try:
    from . import models
except ImportError:
    import models

MAX_ADD = 3
MAX_FRONTIER = 5
MIN_ACCURACY = 0.9
_OVERRIDE = {}  # (lane, model) -> rules: a candidate under evaluation


def vault_dir():
    return os.environ.get("KIT_PROMPT_VAULT") or os.path.join(models.root(), "kit", "knowledge", "vault", "prompt")


def _path(name):
    return os.path.join(vault_dir(), f"{name}.json")


def _load(name, empty):
    p = _path(name)
    if not os.path.isfile(p):
        return empty
    try:
        return models.load_json(p)
    except (OSError, ValueError):
        return empty


def _save(name, data):
    os.makedirs(vault_dir(), exist_ok=True)
    with open(_path(name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def frontier():
    return _load("pareto_frontier", {"schema": 1, "frontiers": {}})


# ---- the LIVING TOOL-PLAN loop (PARALLAX spec §3.3 stage 3): a verdict on a piece also teaches which tools its case
# won with. assets/plans/<piece>.plan.json (the tools chosen per part / beat + the escalations) is filed with the
# owner's score under its case_id (vault/prompt/tool_plans.json); cases.contract() puts a case's past winners in front
# of the next first pass.
WIN = 7  # an owner score at or above this is a win (the golden set's line)


def plan_path(piece, root=None):
    """the piece's plan: assets/plans/<piece>.plan.json at the root or in a game -> path or None"""
    base = root or models.root()
    cands = [os.path.join(base, "assets", "plans", f"{piece}.plan.json")]
    games = os.path.join(base, "games")
    if os.path.isdir(games):
        cands += [os.path.join(games, g, "assets", "plans", f"{piece}.plan.json") for g in sorted(os.listdir(games))]
    return next((c for c in cands if os.path.isfile(c)), None)


def ingest_plan(piece, score, apply=True, root=None):
    """file the piece's plan with the owner's score -> the record (None: no piece, no plan, or no case_id)"""
    if not piece:
        return None
    path = plan_path(piece, root)
    if not path:
        return None
    try:
        plan = models.load_json(path)
    except (OSError, ValueError):
        return None
    case_id = plan.get("case_id")
    if not case_id:
        return None
    tools = []
    for row in plan.get("part_or_beat_tools") or []:
        for t in (row or {}).get("tools") or []:
            if t not in tools:
                tools.append(t)
    for e in plan.get("escalations") or []:
        for t in (e or {}).get("tools") or ([e.get("to")] if isinstance(e, dict) and e.get("to") else []):
            if t not in tools:
                tools.append(t)
    rec = {"piece": piece, "revision": plan.get("revision"), "score": float(score), "tools": tools,
           "escalations": len(plan.get("escalations") or []), "prompt_sha": plan.get("prompt_sha"),
           "at": time.strftime("%Y-%m-%d")}
    if apply:
        store = _load("tool_plans", {"schema": 1, "cases": {}})
        rows = [r for r in store["cases"].get(case_id, []) if r.get("piece") != piece]
        rows.append(rec)
        store["cases"][case_id] = rows
        _save("tool_plans", store)
    return dict(rec, case_id=case_id)


def winning_tools(case_id, k=6):
    """a case's tools ranked by the owner's wins they were in -> [(tool, wins)]"""
    rows = _load("tool_plans", {"schema": 1, "cases": {}})["cases"].get(case_id, [])
    wins = {}
    for r in rows:
        if r.get("score", 0) >= WIN:
            for t in r.get("tools") or []:
                wins[t] = wins.get(t, 0) + 1
    return sorted(wins.items(), key=lambda kv: (-kv[1], kv[0]))[:k]


def best_rules(lane, model):
    if (lane, model) in _OVERRIDE:
        return _OVERRIDE[(lane, model)]
    cands = frontier()["frontiers"].get(f"{lane}|{model}") or []
    return cands[0]["rules"] if cands else []


def learned_rules(lanes, model):
    """the rules the best candidate of each lane's frontier adds (a rule the evidence calls harmful is left out)"""
    out = []
    for lane in lanes:
        for r in best_rules(lane, model):
            if r.get("harmful", 0) <= r.get("helpful", 0) + 1:
                out.append({"lane": lane, "text": r["text"]})
    return out


def trace_path():
    """the traces are working data (every compile adds one): build/prompt/traces.json, git-ignored, so compiling never
    dirties the tree; the vault keeps only what was LEARNED (pareto_frontier, changelog)"""
    return os.environ.get("KIT_PROMPT_TRACES") or os.path.join(models.root(), "build", "prompt", "traces.json")


def record_trace(packet):
    """compile appends a short trace (the last 200 kept): what was asked, for which model, how long the prompt was"""
    tp = trace_path()
    traces = {"schema": 1, "traces": []}
    if os.path.isfile(tp):
        try:
            traces = models.load_json(tp)
        except (OSError, ValueError):
            pass
    sha = hashlib.sha1(packet["orchestrator_prompt"].encode("utf-8")).hexdigest()[:12]
    traces["traces"].append(
        {
            "when": datetime.datetime.now().isoformat(timespec="seconds"),
            "raw": packet["raw_prompt"][:300],
            "model": packet["target_model"],
            "lanes": packet["lanes"],
            "tokens": packet["token_count"],
            "prompt_sha": sha,
        }
    )
    traces["traces"] = traces["traces"][-200:]
    os.makedirs(os.path.dirname(tp), exist_ok=True)
    with open(tp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(traces, f, indent=1, ensure_ascii=False)
    return sha


# ---------------------------------------------------------------------------------------------- the gradient
def _verdict(verdict):
    if isinstance(verdict, dict):
        return float(verdict.get("score", 5)), str(verdict.get("words", ""))
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(.*)$", str(verdict or ""), re.S)
    return (float(m.group(1)), m.group(2)) if m else (5.0, str(verdict or ""))


def _failure_text(verify_json):
    if not verify_json:
        return ""
    data = verify_json
    if isinstance(verify_json, str) and os.path.isfile(verify_json):
        data = models.load_json(verify_json)
    texts = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("ok") is False or o.get("status") == "fail":
                for k in ("summary", "tail", "next_action"):
                    if isinstance(o.get(k), str):
                        texts.append(o[k])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return "\n".join(texts)


# a lexicon word that names a VIRTUE is a complaint only when negated ("not heavy enough", "not clean"); every other
# lexicon word names a FAULT and is a complaint only when said ("still floaty"; "finally not floaty" is praise)
VIRTUES = {"heavy", "clean", "cool"}
PASS_SCORE = 6  # above this the verdict is praise: counters only, nothing is blamed


def textual_gradient(packet, verdict, verify_json=None):
    """-> {score, words, blame: [{lane, word, missing}]} the rules the failure names that the packet did not carry"""
    try:
        from . import route
    except ImportError:
        import route
    score, words = _verdict(verdict)
    text = words + "\n" + _failure_text(verify_json)
    blame = []
    if score > PASS_SCORE:
        return {"score": score, "words": words, "blame": blame}
    said = route.strip_negated(text).lower()
    refused = route.negated_words(text)
    prompt = packet["orchestrator_prompt"].lower()
    model = packet.get("target_model", "claude")
    pruned = " ".join(str(p.get("text", "")) for p in packet.get("pruned") or []).lower()
    for lane in packet["lanes"]:
        t = models.template(lane)
        for word, rule in t.get("failure_lexicon", {}).items():
            complaint = (word in refused) if word in VIRTUES else bool(re.search(rf"\b{re.escape(word)}", said))
            if complaint and rule.lower()[:60] not in prompt:
                blame.append({"lane": lane, "word": word, "missing": rule, "target": _target(rule, pruned, lane, model)})
    # a failed gate that states its bound ("arrival 2f > 1f", "hold 0.23 s < 0.73 s") names the number the prompt
    # should have carried: the bound itself is blamed on the lead lane (V4 9.4: vfx dailies' arrival latency)
    lead = packet["lanes"][0] if packet["lanes"] else None
    if lead:
        for line in _failure_text(verify_json).splitlines():
            line = " ".join(line.split())
            if BOUND.search(line) and line.lower()[:60] not in prompt and not any(b["missing"].endswith(line[:160]) for b in blame):
                rule = f"hold the gate's measured bound: {line[:160]}"
                blame.append({"lane": lead, "word": "gate", "missing": rule, "target": _target(line, pruned, lead, model)})
    return {"score": score, "words": words, "blame": blame}


# a measured bound in a gate's words: "2f > 1f", "0.23s < 0.73s", ">= 0.73 s", "41 ms > 16.6 ms"
BOUND = re.compile(r"\d+(?:\.\d+)?\s*(?:f|s|ms|%|st|px|db)?\s*(?:[<>]=?|≥|≤)\s*\d+(?:\.\d+)?", re.I)


def _target(rule, pruned, lane, model):
    """where the gradient points (V4 9.4: templates/<lane>.json vs profiles/<model>.json): a rule the compile HAD and
    pruned for this model's budget is the profile's fault; a rule it never had is the lane template's"""
    return f"profile:{model}" if rule.lower()[:60] in pruned else f"template:{lane}"


# ---------------------------------------------------------------------------------------------- the benchmark
def benchmark_cases():
    p = os.path.join(models.HERE, "benchmarks.json")
    return models.load_json(p)["cases"] if os.path.isfile(p) else []


def evaluate(cases=None, model=None):
    """the share of held-out cases whose compiled prompt carries every guardrail word, inside its budget (model: every
    case compiled for that model - a codex delta is judged on codex prompts)"""
    try:  # (late: compile imports this module through expand)
        from . import compile as comp
        from . import route
    except ImportError:
        import compile as comp
        import route

    cases = cases if cases is not None else benchmark_cases()
    if model:
        cases = [dict(c, model=model) for c in cases]
    if not cases:
        return {"accuracy": 0.0, "tokens": 0, "failed": [], "passed": [], "n": 0, "unfiled": []}
    passed, tokens, failed, passed_ids, unfiled, filed = 0, 0, [], [], [], None
    for c in cases:
        model = c.get("model", "claude")
        # routed from the owner's words alone (no lane hint): the replay is the prompt as it was given
        routed = route.route_intent(c["raw_prompt"], "none")
        pk = comp.compile_packet(routed, {}, model)
        text = pk["orchestrator_prompt"].lower()
        budget = models.profile(pk["target_model"])["budget"]
        miss = [k for k in c["must_contain"] if k.lower() not in text]
        if c.get("lane") and (not routed["lanes"] or routed["lanes"][0] != c["lane"]):
            miss.append(f"lead lane {routed['lanes'][:1]} != {c['lane']}")
        # prompt-specific grounding: the case's own graveyard record, found from its words, reached the prompt. A record
        # this project never filed is not its history (the kit ships none of its author's): the case still counts for its
        # guardrail words and its lane, and its record is checked from the day the project's graveyard holds it
        if c.get("graveyard") and filed is None:
            filed = route.filed_graveyard()
        if c.get("graveyard") and not any(t.startswith(c["graveyard"].lower()) for t in filed):
            unfiled.append(c.get("id"))
        elif c.get("graveyard"):
            mine = [b for b in routed["repo_grounding"]["graveyard_bans"] if b["tried"].lower().startswith(c["graveyard"].lower())]
            # two words of its own at least: one stray word ("terrain", "hud") is not grounding
            if not mine or mine[0].get("matched", 0) < 2:
                miss.append(f"its own graveyard record '{c['graveyard']}' not matched by its words")
            elif f"graveyard '{c['graveyard'].lower()}" not in text:
                # a 450-token local prompt holds its lane's TWO best-matched records (compile.py): there the record
                # must be found by its words and the lane's best record must reach the prompt; frontier models carry it
                top = [b for b in routed["repo_grounding"]["graveyard_bans"] if b["lane"] == routed["lanes"][0]][:1]
                if pk["target_model"] != "local" or not top or f"graveyard '{top[0]['tried'].lower()}" not in text:
                    miss.append(f"its own graveyard record '{c['graveyard']}' did not reach the prompt")
        tokens = max(tokens, pk["token_count"])
        if not miss and pk["token_count"] <= budget:
            passed += 1
            passed_ids.append(c.get("id") or f"case{len(passed_ids) + len(failed)}")
        else:
            failed.append({"id": c.get("id"), "missing": miss, "tokens": pk["token_count"]})
    return {"accuracy": round(passed / len(cases), 3), "tokens": tokens, "failed": failed, "passed": passed_ids, "n": len(cases),
            "unfiled": unfiled}


def regressions(base_eval, cand_eval):
    """the held-out cases the base passed and the candidate fails (GEPA keeps the frontier per INSTANCE: a delta that
    fixes one case by breaking another is not progress, whatever the average says)"""
    lost = set(base_eval.get("passed") or []) - set(cand_eval.get("passed") or [])
    return sorted(lost)


# ---------------------------------------------------------------------------------------------- the delta
def _validate_delta(base, candidate):
    """ACE: an itemized delta, never a wholesale rewrite"""
    base_t = {r["text"] for r in base}
    cand_t = {r["text"] for r in candidate}
    added, removed = cand_t - base_t, base_t - cand_t
    if len(added) > MAX_ADD:
        return f"context collapse: {len(added)} rules added at once (at most {MAX_ADD})"
    for r in base:
        if r["text"] in removed and r.get("harmful", 0) < r.get("helpful", 0) + 2:
            return f"context collapse: removes a rule the evidence does not call harmful ('{r['text'][:60]}')"
    grown = sum(models.count_tokens(t) for t in added) - sum(models.count_tokens(t) for t in removed)
    if grown > 300:
        return f"token growth {grown} > 300 in one delta"
    for t in added:
        problem = lint_rule(t)
        if problem:
            return problem
    return None


UNMEASURABLE = ("be excellent", "be amazing", "make it good", "make it nice", "make it cool", "make it better", "high quality", "high-quality", "amazing", "awesome", "perfect", "best possible")


def lint_rule(text):
    """a learned rule must say something checkable: no fluff, at least 5 content words"""
    low = (text or "").lower()
    for p in UNMEASURABLE:
        if p in low:
            return f"un-measurable rule ('{p}'): '{text[:60]}'"
    content = [w for w in re.findall(r"[a-z0-9][a-z0-9'\-.]*", low) if len(w) > 2]
    if len(content) < 5:
        return f"rule too vague (under 5 content words): '{text[:60]}'"
    return None


def _fixes(c):
    return sum(1 for r in c.get("rules", []) if str(r.get("source", "")).startswith("verdict"))


def _covers(o, c):
    """o does at least as well as c on the held-out set: per INSTANCE when both know their passed cases (GEPA's
    instance-wise frontier: a candidate that alone passes some case is never dropped), else by the average"""
    if o.get("passed") is not None and c.get("passed") is not None:
        return set(o["passed"]) >= set(c["passed"])
    return o["accuracy"] >= c["accuracy"]


def _pareto(cands):
    """GEPA's frontier on three objectives: held-out cases passed (a superset, per instance), verdict fixes carried
    (more), tokens (fewer); the head is the most accurate, then the one carrying the most fixes, then the shortest"""

    def better_eq(o, c):
        return _covers(o, c) and _fixes(o) >= _fixes(c) and o["tokens"] <= c["tokens"]

    keep = []
    for c in cands:
        dominated = any(o is not c and better_eq(o, c) and not better_eq(c, o) for o in cands)
        if not dominated:
            keep.append(c)
    keep.sort(key=lambda c: (-c["accuracy"], -_fixes(c), c["tokens"]))
    return keep[:MAX_FRONTIER]


def packets_dir():
    return os.path.join(os.path.dirname(trace_path()), "packets")


def save_packet(packet):
    """every compiled packet by its prompt's sha (build/prompt/packets/<sha>.json): a verdict that comes later finds it"""
    sha = hashlib.sha1(packet["orchestrator_prompt"].encode("utf-8")).hexdigest()[:12]
    # the day it was compiled: only a verdict given on or after it can be about this prompt (evolve_from_verdicts)
    packet.setdefault("compiled", datetime.date.today().isoformat())
    os.makedirs(packets_dir(), exist_ok=True)
    with open(os.path.join(packets_dir(), f"{sha}.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(packet, f, indent=1, ensure_ascii=False)
    return sha


def load_packet(ref):
    """a packet's file path, or the sha `kit prompt compile` printed"""
    if isinstance(ref, dict):
        return ref
    if os.path.isfile(ref):
        return models.load_json(ref)
    p = os.path.join(packets_dir(), f"{ref}.json")
    if re.fullmatch(r"[0-9a-f]{6,40}", ref or "") and os.path.isfile(p):
        return models.load_json(p)
    raise ValueError(f"no packet '{ref}' (a packet file, or the sha kit prompt compile printed)")


def reflect_and_propose(trace_path, verdict, verify_json=None, proposed_rules=None, apply=True, cases=None):
    """a compiled packet (its JSON file or sha) + what happened -> {status: accepted|rejected|kept, gradient, delta}"""
    packet = load_packet(trace_path)
    model = packet["target_model"]
    grad = textual_gradient(packet, verdict, verify_json)
    lead = packet["lanes"][0] if packet["lanes"] else None
    changes = []
    fr = frontier()
    # helpful / harmful counters on the rules that were in the prompt
    for lane in packet["lanes"]:
        key = f"{lane}|{model}"
        for cand in fr["frontiers"].get(key, [])[:1]:
            for r in cand["rules"]:
                if r["text"].lower()[:60] in packet["orchestrator_prompt"].lower():
                    if grad["score"] >= 7:
                        r["helpful"] = r.get("helpful", 0) + 1
                        changes.append(f"helpful+1 {lane}: {r['text'][:60]}")
                    elif grad["score"] <= 3:
                        r["harmful"] = r.get("harmful", 0) + 1
                        changes.append(f"harmful+1 {lane}: {r['text'][:60]}")
    def done(res):
        # the counter bumps are kept whatever the delta's fate (accepted saves the whole frontier below)
        if apply and changes and res.get("status") != "accepted":
            _save("pareto_frontier", fr)
        # the piece's tool plan learns from the same verdict, whatever the rules' fate (§3.3 stage 3)
        res["tool_plan"] = ingest_plan(packet.get("piece"), grad["score"], apply=apply)
        return res

    if lead is None:
        return done({"status": "kept", "reason": "no lane", "gradient": grad, "counters": changes})
    # the base is the IN-MEMORY head (it carries this verdict's counter bumps)
    head = fr["frontiers"].get(f"{lead}|{model}") or []
    base = [dict(r) for r in head[0]["rules"]] if head else []
    if proposed_rules is not None:
        # (a proposed rule - an LLM critique's delta - counts as a fix on the frontier once it passes the lint)
        candidate = [dict(r) if isinstance(r, dict) else {"text": r} for r in proposed_rules]
        known = {r["text"] for r in base}
        for r in candidate:
            if r["text"] not in known:
                r.setdefault("source", "verdict-proposed")
    else:
        candidate = [dict(r) for r in base if r.get("harmful", 0) < r.get("helpful", 0) + 2]
        for b in grad["blame"]:
            if b["lane"] == lead and b["missing"] not in [r["text"] for r in candidate]:
                candidate.append({"text": b["missing"], "helpful": 0, "harmful": 0, "source": f"verdict {grad['score']:g}: '{b['word']}'"})
    for r in candidate:
        r.setdefault("helpful", 0)
        r.setdefault("harmful", 0)
    result = {"gradient": grad, "counters": changes, "lane": lead, "model": model}
    if [r["text"] for r in candidate] == [r["text"] for r in base]:
        return done(result | {"status": "kept", "reason": "the verdict names nothing the prompt lacked"})
    problem = _validate_delta(base, candidate)
    if problem:
        return done(result | {"status": "rejected", "reason": problem})
    # held out on the delta's OWN model (a codex rule is judged on codex prompts)
    _OVERRIDE[(lead, model)] = base
    try:
        base_eval = evaluate(cases, model)
    finally:
        _OVERRIDE.pop((lead, model), None)
    _OVERRIDE[(lead, model)] = candidate
    try:
        cand_eval = evaluate(cases, model)
    finally:
        _OVERRIDE.pop((lead, model), None)
    result |= {"delta": {"add": [r["text"] for r in candidate if r["text"] not in [b["text"] for b in base]], "remove": [b["text"] for b in base if b["text"] not in [r["text"] for r in candidate]]}, "base": base_eval, "candidate": cand_eval}
    over = [f for f in cand_eval["failed"] if f["missing"] == []]
    lost = regressions(base_eval, cand_eval)
    if lost:
        return done(result | {"status": "rejected", "reason": f"held-out regression: the delta breaks {len(lost)} case(s) the base passed ({', '.join(lost[:3])})"})
    if cand_eval["accuracy"] < base_eval["accuracy"]:
        return done(result | {"status": "rejected", "reason": f"held-out benchmark fell {base_eval['accuracy']:.0%} -> {cand_eval['accuracy']:.0%}"})
    if cand_eval["n"] and cand_eval["accuracy"] < MIN_ACCURACY:
        return done(result | {"status": "rejected", "reason": f"held-out benchmark {cand_eval['accuracy']:.0%} < {MIN_ACCURACY:.0%}"})
    if over:
        return done(result | {"status": "rejected", "reason": f"{len(over)} benchmark prompt(s) over their token budget"})
    key = f"{lead}|{model}"
    cands = list(fr["frontiers"].get(key, []))
    if not cands:  # (the empty playbook is the first point on the frontier)
        cands.append({"id": "base", "rules": base, "accuracy": base_eval["accuracy"], "tokens": base_eval["tokens"], "passed": base_eval.get("passed", []), "added": datetime.date.today().isoformat()})
    entry = {"id": hashlib.sha1(json.dumps([r["text"] for r in candidate]).encode()).hexdigest()[:10], "rules": candidate, "accuracy": cand_eval["accuracy"], "tokens": cand_eval["tokens"], "passed": cand_eval.get("passed", []), "added": datetime.date.today().isoformat()}
    cands.append(entry)
    new_front = _pareto(cands)
    if not new_front or new_front[0] is not entry:
        return done(result | {"status": "kept", "reason": "the delta did not beat the frontier's head (dominated)"})
    if apply:
        fr["frontiers"][key] = new_front
        _save("pareto_frontier", fr)
        log = _load("changelog", {"schema": 1, "entries": []})
        log["entries"].append({"when": datetime.datetime.now().isoformat(timespec="seconds"), "lane": lead, "model": model, "verdict": grad["score"], "words": grad["words"][:200], "delta": result["delta"], "targets": sorted({b.get("target", "") for b in grad["blame"] if b["lane"] == lead}), "accuracy": [base_eval["accuracy"], cand_eval["accuracy"]]})
        _save("changelog", log)
    return result | {"status": "accepted"}


# ---------------------------------------------------------------------------------------------- the owner's record
# The loop learns ONLY from verdicts the owner gave and `kit verdict` recorded (kit/knowledge/vault/<area>/verdicts/
# <piece>--<date>.md, by: owner). A verdict a session reconstructed from its memory notes (source: inferred) is not the
# owner's record and never drives a delta; neither does a score typed on the command line that the record does not hold.
AREA_LANE = {"code": "systems", "qa": "systems"}  # vault areas whose lane PROMPT-X names differently
TRUSTED_SOURCES = ("owner", "quoted")


def verdict_root():
    return os.environ.get("KIT_VERDICT_VAULT") or os.path.join(models.root(), "kit", "knowledge", "vault")


def _frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        m = re.match(r"\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip('"')
    return meta, text[end + 4:].strip()


def owner_verdicts(root=None):
    """every recorded verdict the OWNER gave, oldest first -> [{id, lane, area, name, score, date, words}]"""
    root = root or verdict_root()
    out = []
    if not os.path.isdir(root):
        return out
    for area in sorted(os.listdir(root)):
        vdir = os.path.join(root, area, "verdicts")
        if not os.path.isdir(vdir):
            continue
        for fname in sorted(os.listdir(vdir)):
            if not fname.endswith(".md"):
                continue
            try:
                with open(os.path.join(vdir, fname), encoding="utf-8") as f:
                    meta, body = _frontmatter(f.read())
            except (OSError, UnicodeDecodeError):
                continue
            if meta.get("kind", "verdict") != "verdict" or meta.get("by") != "owner" or meta.get("source") not in TRUSTED_SOURCES:
                continue
            try:
                score = float(meta.get("score", ""))
            except ValueError:
                continue  # (a direction without a number: nothing to put on the frontier)
            out.append({"id": f"{area}/verdicts/{fname[:-3]}", "area": area, "lane": AREA_LANE.get(area, area),
                        "name": meta.get("name", ""), "score": score, "date": meta.get("date", ""),
                        "words": " ".join(body.split())[:600]})
    out.sort(key=lambda v: (v["date"], v["id"]))
    return out


def _norm(s):
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def recorded(score, words, lane=None, root=None):
    """the owner's recorded verdict this (score, words) quotes, or None: the same score, and the words found in the
    record's own text (a paraphrase or an invented complaint matches nothing)"""
    w = _norm(words)
    for v in reversed(owner_verdicts(root)):
        if abs(v["score"] - float(score)) < 1e-9 and (lane is None or v["lane"] == lane) and w and w in _norm(v["words"]):
            return v
    return None


def _packets_by_piece():
    out = {}
    d = packets_dir()
    if not os.path.isdir(d):
        return out
    for fname in os.listdir(d):
        if not fname.endswith(".json"):
            continue
        try:
            p = models.load_json(os.path.join(d, fname))
        except (OSError, ValueError):
            continue
        if isinstance(p, dict) and p.get("piece"):
            out.setdefault(str(p["piece"]).lower(), []).append(p)
    for lst in out.values():
        lst.sort(key=lambda p: p.get("compiled", ""))
    return out


def evolve_from_verdicts(apply=True, cases=None, root=None):
    """THE LOOP over the owner's record: every owner verdict not consumed yet whose piece has a prompt compiled for it
    (kit prompt compile ... --piece <name>) on or before the verdict's day, in the verdict's lane -> one
    reflect_and_propose step (TextGrad blame -> an ACE delta -> the GEPA frontier, held out on the benchmark). A verdict
    is consumed once (vault/prompt/consumed.json), whatever the step's fate; a verdict with no prompt behind it is left
    for later and listed. -> {matched, unmatched, results}"""
    done = _load("consumed", {"schema": 1, "ids": []})
    seen = set(done["ids"])
    by_piece = _packets_by_piece()
    results, unmatched = [], []
    for v in owner_verdicts(root):
        if v["id"] in seen:
            continue
        cands = [p for p in by_piece.get(v["name"].lower(), [])
                 if v["lane"] in p.get("lanes", []) and p.get("compiled", "9999") <= (v["date"] or "0000")]
        if not cands:
            unmatched.append(v["id"])
            continue
        packet = cands[-1]  # (the latest prompt compiled for the piece before the owner judged it)
        r = reflect_and_propose(packet, {"score": v["score"], "words": v["words"]}, apply=apply, cases=cases)
        results.append({"verdict": v["id"], "score": v["score"], "status": r["status"], "reason": r.get("reason"),
                        "delta": r.get("delta"), "blamed": [b["word"] for b in r["gradient"]["blame"]]})
        if apply:
            done["ids"].append(v["id"])
            seen.add(v["id"])
    if apply and results:
        _save("consumed", done)
    return {"matched": len(results), "unmatched": unmatched, "results": results}
