"""cases.py - the CASE CONTRACTS and CAPABILITY MENUS (PARALLAX_ENFORCEMENT_AND_ROUTING_SPEC §3): which production case
of a lane a prompt is (3d:hybrid_hero vs 3d:static_prop ...), and the lane's full menu of tools + escalation ladder.

    kit/knowledge/cases/<lane>.json         {"schema", "lane", "default_case", "cases": [{case_id, triggers, ...}]}
    kit/knowledge/capabilities/<lane>.json  {"schema", "lane", "menu": [{tool, when}], "ladder": [{from, to, when}],
                                             "floor": [...]}

Read by PROMPT-X (route.py attaches the contracts + the lead lane's menu; compile.py renders them), by
kit/scripts/parallax_guard.py (anti-patterns, the session's contracts) and by kit/mcp/server.py (parallax_case).
Standard library only: parallax_guard imports it on the hook's fast path.

THE MATCHING RULE (the registries' examples are written to it): lowercase the prompt; a case scores the number of its
distinct trigger keywords found in the prompt as substrings; a case with requires_both is eligible only when every
group has a word in the prompt (then +2); the highest score wins, ties go to the case listed first, and with no
score at all the lane's default_case.
"""

import json
import os
import re

CASE_LANES = ("3d", "vfx", "anim", "world", "ui", "sfx", "code", "qa")
MENU_LINES = 25  # a lane's capability menu, rendered, is at most this many lines (§3.3)
CASE_KEYS = ("case_id", "label", "triggers", "tier", "budget_minutes", "required_tools_ordered", "v4_upgrade_tools",
             "forbidden_tools", "mandatory_gates", "owner_stops", "capability_policy", "anti_patterns_regex", "examples")
TIERS = ("simple", "prop", "complex", "hero", "system")  # (the spec's §4 tier column uses simple too)


def root():
    """where the registries live: the kit's own checkout (PARALLAX_CASES_ROOT overrides it), never the project a hook
    is looking at - a game or a test's temporary repo has no kit/knowledge of its own"""
    return os.environ.get("PARALLAX_CASES_ROOT") or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _load(kind, lane, base=None):
    path = os.path.join(base or root(), "kit", "knowledge", kind, f"{lane}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def registry(lane, base=None):
    """the lane's case registry, or None"""
    return _load("cases", lane, base)


def capabilities(lane, base=None):
    """the lane's capability menu + ladder, or None"""
    return _load("capabilities", lane, base)


def case_lanes_for(lane, raw=""):
    """PROMPT-X's lane names -> the registries': systems is code, and qa too when the words are about testing"""
    if lane == "systems":
        low = (raw or "").lower()
        out = ["code"]
        if any(w in low for w in ("playtest", "test", "audit", "fuzz", "qa", "perf", "exploit", "regression")):
            out.append("qa")
        return out
    return [lane] if lane in CASE_LANES else []


def score_case(case, raw):
    low = (raw or "").lower()
    trig = case.get("triggers") or {}
    hits = {k for k in trig.get("keywords") or [] if k and k.lower() in low}
    score = len(hits)
    groups = trig.get("requires_both") or []
    if groups:
        if not all(any(w.lower() in low for w in g) for g in groups):
            return 0
        score += 2
    return score


def match(lane, raw, base=None):
    """the case a prompt is in this lane -> (case dict, score) or (None, 0) with no registry"""
    reg = registry(lane, base)
    if not reg or not reg.get("cases"):
        return None, 0
    best, best_score = None, 0
    for c in reg["cases"]:
        s = score_case(c, raw)
        if s > best_score:
            best, best_score = c, s
    if best is None:
        best = next((c for c in reg["cases"] if c.get("case_id") == reg.get("default_case")), reg["cases"][0])
    return best, best_score


def find_case(case_id, base=None):
    lane = (case_id or "").split(":", 1)[0]
    reg = registry(lane, base) if lane in CASE_LANES else None
    for c in (reg or {}).get("cases", []):
        if c.get("case_id") == case_id:
            return c
    return None


def learned(case_id, base=None, k=6):
    """the tools the owner's wins of this case were made with (kit/prompt/evolve.py ingest_plan files them in
    vault/prompt/tool_plans.json) -> [tool], most wins first"""
    path = os.path.join(base or root(), "kit", "knowledge", "vault", "prompt", "tool_plans.json")
    try:
        with open(path, encoding="utf-8") as fh:
            rows = (json.load(fh).get("cases") or {}).get(case_id) or []
    except (OSError, ValueError, AttributeError):
        return []
    wins = {}
    for r in rows:
        if float(r.get("score") or 0) >= 7:
            for t in r.get("tools") or []:
                wins[t] = wins.get(t, 0) + 1
    return [t for t, _ in sorted(wins.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def _tool_text(t):
    return t if isinstance(t, str) else (t.get("pattern") or t.get("id") or t.get("path") or "")


def contract(case, lane, piece=None, base=None):
    """the compact contract a session carries (.verify/parallax_session.json case_contracts)"""
    b = base or root()
    upgrades = [u.get("path") for u in case.get("v4_upgrade_tools") or [] if isinstance(u, dict) and u.get("path")]
    return {
        "lane": lane,
        "case_id": case["case_id"],
        "label": case.get("label", ""),
        "piece": piece,
        "required_tools": list(case.get("required_tools_ordered") or []),
        "v4_upgrade_tools": upgrades,
        # (only the upgrades that exist on disk are enforced; an unbuilt one never blocks P0)
        "v4_upgrade_tools_present": [p for p in upgrades if os.path.exists(os.path.join(b, p))],
        "forbidden_tools": [_tool_text(f) for f in case.get("forbidden_tools") or []],
        "owner_stops": list(case.get("owner_stops") or []),
        "mandatory_gates": list(case.get("mandatory_gates") or []),
        "learned_tools": learned(case["case_id"], b),
    }


def contracts_for(lanes, raw, piece=None, base=None):
    """every routed lane's matched case as a contract (systems -> code [+ qa])"""
    out, seen = [], set()
    for lane in lanes:
        for cl in case_lanes_for(lane, raw):
            if cl in seen:
                continue
            seen.add(cl)
            case, _ = match(cl, raw, base)
            if case:
                out.append(contract(case, cl, piece, base))
    return out


def render_menu(lane, base=None):
    """the lane's capability menu in at most MENU_LINES lines (one per tool, one per ladder rung, one floor line)"""
    cap = capabilities(lane, base)
    if not cap:
        return []
    lines = [f"- {m['tool']}: {m['when']}" for m in cap.get("menu") or []]
    lines += [f"- ladder: {r['from']} -> {r['to']} ({r['when']})" for r in cap.get("ladder") or []]
    if cap.get("floor"):
        lines.append("- floor: " + "; ".join(cap["floor"]))
    return lines[:MENU_LINES]


def render_contract(c):
    """a contract in a few lines (PROMPT-X guardrails, parallax case)"""
    lines = [f"case {c['case_id']} ({c.get('label', '')})"]
    if c.get("required_tools"):
        lines.append("floor (in order): " + " -> ".join(c["required_tools"]))
    if c.get("forbidden_tools"):
        lines.append("forbidden: " + ", ".join(c["forbidden_tools"]))
    if c.get("owner_stops"):
        lines.append("owner stops: " + ", ".join(c["owner_stops"]))
    if c.get("learned_tools"):
        lines.append("won with before (owner >= 7): " + ", ".join(c["learned_tools"]))
    if c.get("v4_upgrade_tools_present"):
        lines.append("mandatory upgrades (present): " + ", ".join(c["v4_upgrade_tools_present"]))
    lines.append("extra non-forbidden tools are always allowed; an edge-case skip: --skip-tool <tool> --why \"<reason>\"")
    return lines


def anti_patterns(lane, base=None):
    """every case's anti-pattern rows of a lane (with their case_id)"""
    out = []
    for c in (registry(lane, base) or {}).get("cases", []):
        for a in c.get("anti_patterns_regex") or []:
            out.append(dict(a, case_id=c.get("case_id")))
    return out


def _glob_re(glob):
    """a path glob (** any depth, * one segment) -> a regex over forward-slash paths"""
    out, i = "", 0
    while i < len(glob):
        ch = glob[i]
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if glob.startswith("**", i):
            out += ".*"
            i += 2
            continue
        out += "[^/]*" if ch == "*" else re.escape(ch)
        i += 1
    return re.compile("^(?:games/[^/]+/)?" + out + "$")


def path_matches(path, glob):
    return bool(_glob_re(glob).match(path.replace("\\", "/").lstrip("./")))


def scan_text(path, text, lanes=None, base=None):
    """the anti-patterns of the registries that hit this file's text -> [{case_id, severity, message, regex}]"""
    hits = []
    rel = path.replace("\\", "/")
    for lane in lanes or CASE_LANES:
        for a in anti_patterns(lane, base):
            glob = a.get("file_glob")
            if not glob or not path_matches(rel, glob):
                continue
            try:
                found = re.search(a["regex"], text) is not None
            except re.error:
                continue
            if found and a.get("requires_absent") and a["requires_absent"] in text:
                found = False
            if found:
                hits.append({"case_id": a.get("case_id"), "severity": a.get("severity", "warn"),
                             "message": a.get("message", ""), "regex": a["regex"]})
    return hits


def validate_case(c, lane):
    """-> [problems] for one case against the §3.2 schema"""
    p = []
    for k in CASE_KEYS:
        if k not in c:
            p.append(f"{c.get('case_id', '?')}: no {k}")
    cid = c.get("case_id", "")
    if not cid.startswith(f"{lane}:"):
        p.append(f"{cid}: case_id must start with '{lane}:'")
    if c.get("tier") not in TIERS:
        p.append(f"{cid}: tier {c.get('tier')!r} not one of {TIERS}")
    if not isinstance(c.get("budget_minutes"), int):
        p.append(f"{cid}: budget_minutes must be an int")
    if not c.get("required_tools_ordered"):
        p.append(f"{cid}: required_tools_ordered is empty")
    if not c.get("examples"):
        p.append(f"{cid}: no example prompt (every case needs >= 1 routing test)")
    for f in c.get("forbidden_tools") or []:
        if not (isinstance(f, dict) and f.get("pattern") and f.get("why")):
            p.append(f"{cid}: forbidden tool without pattern + why: {f}")
    for a in c.get("anti_patterns_regex") or []:
        try:
            re.compile(a.get("regex", ""))
        except re.error as e:
            p.append(f"{cid}: bad regex {a.get('regex')!r}: {e}")
        if a.get("severity") not in ("block", "warn"):
            p.append(f"{cid}: anti-pattern severity must be block|warn")
    if "Full-capability" not in (c.get("capability_policy") or ""):
        p.append(f"{cid}: capability_policy is not the full-capability policy")
    return p


def validate_all(base=None):
    """-> (cases counted, [problems]) over every lane's registry + capability menu"""
    problems, n, ids = [], 0, set()
    for lane in CASE_LANES:
        reg = registry(lane, base)
        if not reg:
            problems.append(f"{lane}: no kit/knowledge/cases/{lane}.json")
            continue
        if reg.get("lane") != lane:
            problems.append(f"{lane}: the registry says lane {reg.get('lane')!r}")
        for c in reg.get("cases") or []:
            n += 1
            problems += validate_case(c, lane)
            if c.get("case_id") in ids:
                problems.append(f"{c.get('case_id')}: duplicate case_id")
            ids.add(c.get("case_id"))
            for ex in c.get("examples") or []:
                got, _ = match(lane, ex, base)
                if not got or got.get("case_id") != c.get("case_id"):
                    problems.append(f"{c.get('case_id')}: its example {ex!r} routes to {got and got.get('case_id')}")
        if reg.get("default_case") not in ids:
            problems.append(f"{lane}: default_case {reg.get('default_case')!r} is not one of its cases")
        cap = capabilities(lane, base)
        if not cap:
            problems.append(f"{lane}: no kit/knowledge/capabilities/{lane}.json")
        else:
            rendered = len(cap.get("menu") or []) + len(cap.get("ladder") or []) + (1 if cap.get("floor") else 0)
            if rendered > MENU_LINES:
                problems.append(f"{lane}: capability menu renders {rendered} lines > {MENU_LINES}")
            if not cap.get("menu") or not cap.get("ladder"):
                problems.append(f"{lane}: capability menu needs a menu and a ladder")
    return n, problems
