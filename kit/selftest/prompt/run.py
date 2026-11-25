"""kit/selftest/prompt/run.py - PROMPT-X's gates on a good compile and six broken ones (LIMITATIONS_FIXES_V4 13.7, the
six mandatory traps). `kit selftest` runs each case: `good` must pass, every other case must FAIL for its own reason.

  good       the V4 worked example on claude / codex / gemini / local: positive FLUX words, each profile's shape, every
             budget, the grounding hydrated, and the 10 historical owner prompts each carrying their guardrail
  leak       a FLUX.2 prompt that kept the owner's "no fire" (trap 1)
  cot        a codex prompt that kept a "think step by step" script (trap 2)
  budget     the six-lane ask rendered for the local model with the pruning skipped (trap 3)
  grounding  a packet whose repo grounding was never hydrated (trap 4)
  collapse   evolve handed a wholesale rewrite of the playbook (trap 5; a temporary vault, nothing kept)
  replay     the lane templates with their hard-won rules dropped (trap 6)
  parts      a packet compiled with the Parts RAG skipped (V4 Phase 2: kit parts' libraries wired into PROMPT-X)
  docs       a packet whose API names lost their exact Luau signatures (V4 9.2 row 1: docs.py signatures)
  regress    evolve handed a delta that trades one held-out case for another at the same average (V4 9.4 stage 4)
Prints one JSON line {"status", "summary", "next_action"}."""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit"))
os.environ["KIT_GAME"] = "none"
from prompt import checks, evolve, expand, models, route, subprompts  # noqa: E402
from prompt import compile as comp  # noqa: E402

V4_RAW = "yo make a fire katana slash ultimate like tanjiro water and fire, make it feel heavy not floaty and make the ui clean not slop"
COT_VARIANTS = ["Think Step-By-Step", "think through it step by step", "work through this step by step", "Let us think step by step", "use chain-of-thought"]
NEG_VARIANTS = [
    "a gold katana, never, ever glowing", "a gold katana, it shouldn't have any fire", "a katana, don’t add text",
    "a fire-free katana", "a non-glowing blade", "a katana w/o fire", "a katana (no fire) with a gold hilt",
]
BIG = V4_RAW + " with a 3d sword model, a gothic courtyard world, footsteps sound set and a shop menu"


def emit(problems, ok_summary, case):
    if problems:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"prompt {case}: " + "; ".join(problems[:3]), "next_action": "fix kit/prompt (never the fixture)"}))
        return 1
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"prompt {case}: {ok_summary}", "next_action": "none - proceed"}))
    return 0


def pk(raw, model):
    return comp.compile_packet(route.route_intent(raw, "none"), {}, model)


def main(case):
    tmp = tempfile.mkdtemp()
    os.environ["KIT_PROMPT_VAULT"] = os.path.join(tmp, "vault")
    os.environ["KIT_PROMPT_TRACES"] = os.path.join(tmp, "traces.json")
    try:
        if case == "good":
            packets = {m: pk(V4_RAW, m) for m in ("claude", "codex", "gemini", "local")}
            problems = checks.negative_word_leak(packets["claude"]["tool_subprompts"]["flux2"], V4_RAW)
            problems += checks.model_drift(packets)
            # the producing code on hard inputs: every chain-of-thought spelling through codex, every negation form
            # through the FLUX substitution
            problems += checks.model_drift({"codex": pk(V4_RAW + ". " + ". ".join(COT_VARIANTS), "codex")})
            for raw in NEG_VARIANTS:
                problems += checks.negative_word_leak(subprompts.flux2("3d", raw), raw)
            problems += [p for m in packets for p in checks.token_budget(packets[m])]
            problems += [p for m in ("claude",) for p in checks.token_budget(pk(BIG, m))]
            problems += checks.missing_grounding(packets["claude"])
            # the Phase 2 wiring: every profile carries the parts libraries' cards and the API's exact signatures
            problems += [p for m in packets for p in checks.parts_grounding(packets[m])]
            problems += [p for m in packets for p in checks.api_signatures(packets[m])]
            r = evolve.evaluate()
            problems += checks.replay(r)
            guarded = f"{r['n']}/{r['n']} historical prompts guarded" + (
                f" ({len(r['unfiled'])} by their guardrail words and lane only: their own graveyard records are not in this vault)"
                if r.get("unfiled") else "")
            return emit(problems, f"four profiles in shape and budget, grounding hydrated (parts cards + API signatures), {guarded}", case)
        if case == "leak":
            return emit(checks.negative_word_leak("studio product photography: a katana, side view, no fire, without blur"), "", case)
        if case == "cot":
            bad = pk(V4_RAW, "codex")
            bad["orchestrator_prompt"] += "\nThink step by step before you answer."
            return emit(checks.model_drift({"codex": bad}), "", case)
        if case == "budget":
            prof = models.profile("local")
            ir = expand.build_ir(route.route_intent(BIG, "none"))
            text = comp._render(ir, comp._items(ir, prof), prof)  # the pruning skipped
            return emit(checks.token_budget({"target_model": "local", "orchestrator_prompt": text}), "", case)
        if case == "grounding":
            bad = pk(V4_RAW, "claude")
            bad["repo_grounding"] = {"graveyard_bans": [], "golden_refs": [], "engine_caps": [], "api_docs": []}
            return emit(checks.missing_grounding(bad), "", case)
        if case == "collapse":
            p = pk("a katana swing animation", "claude")
            rewrite = [f"rule {n}: be excellent at everything" for n in range(6)]
            r = evolve.reflect_and_propose(p, {"score": 2, "words": "bad"}, proposed_rules=rewrite)
            kept = os.path.isfile(os.path.join(tmp, "vault", "pareto_frontier.json"))
            problems = [f"evolve refused it: {r.get('reason')}"] if r["status"] == "rejected" and not kept else []
            return emit(problems, "evolve ACCEPTED a wholesale rewrite (the gate is broken)", case)
        if case == "parts":
            os.environ["KIT_PROMPT_PARTS"] = "0"  # the Parts RAG skipped
            try:
                bad = pk("a katana swing animation", "claude")
            finally:
                os.environ.pop("KIT_PROMPT_PARTS", None)
            return emit(checks.parts_grounding(bad), "", case)
        if case == "docs":
            from prompt import docs

            if docs.index() is None:
                return emit(["API signature missing: no Roblox API reference on this machine to build the case from"], "", case)
            saved = docs._REF["types"]
            docs._REF["types"] = {}  # the type file never read: names without their signatures
            try:
                bad = pk("a katana swing animation", "codex")
            finally:
                docs._REF["types"] = saved
            return emit(checks.api_signatures(bad), "", case)
        if case == "regress":
            # a delta that fixes one held-out case by breaking another: the average stays at 95%
            ids = [f"c{i}" for i in range(19)]
            evals = [{"accuracy": 0.95, "tokens": 900, "failed": [], "passed": ids + ["x"], "n": 20},
                     {"accuracy": 0.95, "tokens": 900, "failed": [], "passed": ids + ["y"], "n": 20}]
            real = evolve.evaluate
            evolve.evaluate = lambda cases=None, model=None: evals.pop(0)
            try:
                r = evolve.reflect_and_propose(pk("a katana swing animation", "claude"), {"score": 3, "words": "bad"},
                                               proposed_rules=["the blade arrives on the hit frame with a three frame snap hold"])
            finally:
                evolve.evaluate = real
            problems = [f"evolve refused it: {r.get('reason')}"] if r["status"] == "rejected" else []
            return emit(problems, "evolve ACCEPTED a delta that lost a held-out case (the gate is broken)", case)
        if case == "replay":
            tdir = os.path.join(tmp, "templates")
            os.makedirs(tdir)
            for lane in models.LANES:
                t = models.template(lane)
                t["invariants"] = t["invariants"][:1]
                with open(os.path.join(tdir, f"{lane}.json"), "w", encoding="utf-8") as f:
                    json.dump(t, f)
            os.environ["KIT_PROMPT_TEMPLATES"] = tdir
            return emit(checks.replay(evolve.evaluate()), "", case)
        print(json.dumps({"schema": 1, "status": "error", "summary": f"unknown case {case}", "next_action": "good|leak|cot|budget|grounding|collapse|replay|parts|docs|regress"}))
        return 2
    finally:
        os.environ.pop("KIT_PROMPT_TEMPLATES", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "good"))
