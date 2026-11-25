"""cli.py - PROMPT-X from the command line (kit/cmd/prompt.luau runs it; prints ONE JSON line like every kit tool:
{"schema", "status", "summary", "next_action", "lines": [...], ...}).

  python kit/prompt/cli.py compile "<raw prompt>" [--model claude|codex|gemini|local] [--game <Game>|none]
                           [--answers "q1=A,q2=B"] [--lane <lane>] [--out <packet.json>] [--kickoff <Name>] [--full]
                           [--piece <name>]   (the piece it is for: the owner's later verdict on it finds this prompt)
  python kit/prompt/cli.py clarify "<raw prompt>" [--game ..] [--lane ..]
  python kit/prompt/cli.py route "<raw prompt>" [--game ..]
  python kit/prompt/cli.py evolve <packet.json> <score 0-10> "<the owner's words>" [--verify <verify.json>] [--dry]
                           (the score + words must quote a verdict `kit verdict` recorded from the owner)
  python kit/prompt/cli.py evolve --verdicts [--dry]     the loop over every owner verdict not learned from yet
  python kit/prompt/cli.py bench [--model ..]
  python kit/prompt/cli.py case <lane> "<words>"   the matched case contract + the lane's capability menu (<= 25 lines)
  python kit/prompt/cli.py sub "<text>" [--ban fire,flame]      the FLUX.2 positive substitution alone"""

import json
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from prompt import cases as caselib  # noqa: E402
from prompt import clarify, docs, evolve, models, partsrag, route, session, subprompts  # noqa: E402
from prompt import compile as comp  # noqa: E402

VALUED = ("model", "game", "answers", "lane", "out", "kickoff", "verify", "ban", "piece", "session")


def emit(status, summary, next_action, **extra):
    # (UTF-8 whatever the console's code page: on Windows a "…" went out as cp1252 byte 0x85 and `kit prompt route`
    # read as a crash - the runner decodes the JSON line as UTF-8)
    if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def parse(argv):
    args, flags = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k = a[2:]
            if k in VALUED and i + 1 < len(argv):
                flags[k] = argv[i + 1]
                i += 2
                continue
            flags[k] = True
        else:
            args.append(a)
        i += 1
    return args, flags


def copy_to_clipboard(text):
    """--copy (V4 9.5): the compiled prompt onto the clipboard with the system's own tool; False when there is none"""
    import shutil
    import subprocess

    for cmd in (["clip"], ["pbcopy"], ["xclip", "-selection", "clipboard"], ["wl-copy"]):
        if shutil.which(cmd[0]):
            try:
                # (clip.exe reads UTF-16 with a BOM; the others UTF-8)
                data = ("﻿" + text).encode("utf-16-le") if cmd[0] == "clip" else text.encode("utf-8")
                subprocess.run(cmd, input=data, check=True, timeout=10)
                return True
            except (OSError, subprocess.SubprocessError):
                return False
    return False


def kickoff_command(name, packet):
    """>= 2 lanes: the kit kickoff line that seeds board/briefs/<Name>.md and one task per lane"""
    lane_flag = {"systems": "code"}
    parts = ["lune", "run", "kit", "kickoff", name, packet["raw_prompt"]]
    briefs = packet.get("lane_briefs") or {}
    for lane in packet["lanes"]:
        parts += [f"--{lane_flag.get(lane, lane)}", briefs.get(lane) or f"the {lane} part of: {packet['raw_prompt'][:120]}"]
    return parts


def main(argv):
    if not argv:
        return emit("fail", "prompt: which sub-command? compile | clarify | route | evolve | bench | sub", 'lune run kit prompt compile "<your words>"')
    sub, rest = argv[0], argv[1:]
    args, flags = parse(rest)
    game = flags.get("game") if isinstance(flags.get("game"), str) else None
    try:
        if sub in ("compile", "clarify", "route"):
            if not args:
                return emit("fail", f"prompt {sub}: what is the prompt?", f'lune run kit prompt {sub} "make a heavy katana slash"')
            raw = " ".join(args)
            piece = flags.get("piece") if isinstance(flags.get("piece"), str) else None
            routed = route.route_intent(raw, game, flags.get("lane") if isinstance(flags.get("lane"), str) else None, piece=piece)
            if sub == "route":
                g = routed["repo_grounding"]
                lines = [f"lanes: {', '.join(routed['lanes'])} (scores {routed['scores']})", f"entities: {routed['entities']}"]
                lines += [f"coupled: {c['lane']} - {c['why']}" for c in routed["xp_coupling"]]
                lines += [f"graveyard [{b['lane']}] {b['tried']}: {b['rule']}" for b in g["graveyard_bans"]]
                lines += [f"golden [{r['lane']}] {r['piece']} {r['score_10']:g}/10" for r in g["golden_refs"]]
                # the Roblox API scoped to (lane, family, game) with signatures, and the parts libraries' cards
                lines += [f"api [{a.get('lane')}|{a.get('scope')}] {docs.line(a)}" for a in g.get("api_detail", [])]
                lines += [f"api problem: {p}" for p in g.get("api_problems", [])]
                for lib in g.get("parts_libraries", []):
                    lines.append(f"parts library {lib['library']} (lane {lib['lane']}): " + (lib.get("error") or f"{lib['cards']} cards; parts {lib['parts']}; kinds {lib['kinds']}"))
                lines += [f"parts [{c['lane']}] {partsrag.line(c)}" for c in g.get("parts", [])]
                if g.get("parts_note"):
                    lines.append(f"parts: {g['parts_note']}")
                return emit("pass", f"prompt route: {len(routed['lanes'])} lane(s): {', '.join(routed['lanes'])}", "lune run kit prompt compile with the same words", lines=lines, routed=routed)
            if sub == "clarify":
                cl = clarify.audit_ambiguity(routed)
                lines = [f"ambiguity {cl['score']:.2f}; auto-filled {len(cl['auto_filled'])} repo rules silently"]
                for q in cl["questions"]:
                    lines.append(f"{q['id']} [{q['lane']}] {q['question']}")
                    lines += [f"     {o}" for o in q["options"]]
                nxt = 'answer with --answers "q1=A,q2=B" on kit prompt compile (unanswered = the starred default)' if cl["questions"] else "nothing to ask: lune run kit prompt compile"
                return emit("pass", f"prompt clarify: {len(cl['questions'])} question(s), ambiguity {cl['score']:.2f}", nxt, lines=lines, clarified=cl)
            answers = clarify.parse_answers(flags.get("answers") if isinstance(flags.get("answers"), str) else "")
            model = comp.resolve_model(flags.get("model") if isinstance(flags.get("model"), str) else None)
            packet = comp.compile_packet(routed, answers, model)
            if isinstance(flags.get("piece"), str):
                packet["piece"] = flags["piece"]
            out = flags.get("out") if isinstance(flags.get("out"), str) else os.path.join(models.root(), "build", "prompt", "last.json")
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                json.dump(packet, f, indent=1, ensure_ascii=False)
            evolve.record_trace(packet)
            sha = evolve.save_packet(packet)
            budget = models.profile(model)["budget"]
            unanswered = [q for q in packet["ambiguity"]["questions"] if q["id"] not in answers]
            lines = [
                f"profile {packet['profile']} ({model}); lanes {', '.join(packet['lanes'])}; {packet['token_count']} / {budget} tokens; {len(packet['pruned'])} item(s) pruned",
                f"packet {sha} (after the owner's verdict: lune run kit prompt evolve {sha} <0-10> \"<their words>\")",
            ]
            g = packet["repo_grounding"]
            api_rows, cards = g.get("api_detail", []), g.get("parts", [])
            lines.append(
                f"grounding: {len(api_rows)} API ({sum(1 for a in api_rows if a.get('signature'))} with signatures, "
                f"{sum(1 for a in api_rows if a.get('scope', 'template') != 'template')} from the prompt's words); "
                f"{len(cards)} past part(s) from {', '.join(sorted({c['library'] for c in cards})) or 'no library'} "
                f"({sum(1 for c in cards if c.get('avoid'))} AVOID, {sum(1 for c in cards if c.get('know_how'))} know-how)"
            )
            for q in unanswered:
                default = next((o for o in q["options"] if o.startswith("*")), q["options"][0])
                lines.append(f"{q['id']} (default taken: {default.lstrip('*')}) {q['question']}")
            if flags.get("full"):
                lines += ["", *packet["orchestrator_prompt"].splitlines()]
                for tool, text in packet["tool_subprompts"].items():
                    if isinstance(text, str):
                        lines.append(f"[{tool}] {text}")
            extra = {"packet_path": out, "packet_sha": sha, "token_count": packet["token_count"], "lanes": packet["lanes"], "profile": packet["profile"]}
            # the SESSION TOKEN (PARALLAX spec §2.2 D): the hooks and the CLI gate unlock pipeline work with it
            if not flags.get("no-session"):
                sess = session.stamp(packet, out, sha, lane=flags.get("lane") if isinstance(flags.get("lane"), str) else None,
                                     model=model, session_id=flags.get("session") if isinstance(flags.get("session"), str) else None)
                extra["session"] = {"path": session.REL.replace("\\", "/"), "lane": sess["lane"],
                                    "case_ids": [c["case_id"] for c in sess["case_contracts"]]}
                lines.append(f"session {session.REL} (lane {sess['lane']}; cases {', '.join(extra['session']['case_ids']) or 'none'}; 4 h)")
            for c in packet.get("case_contracts") or []:
                lines.append(f"case {c['case_id']}: floor {len(c['required_tools'])} step(s), forbidden {', '.join(c['forbidden_tools']) or 'none'}")
            if flags.get("copy"):
                extra["copied"] = copy_to_clipboard(packet["orchestrator_prompt"])
                lines.append("the prompt is on the clipboard" if extra["copied"] else "--copy: no clipboard tool found (clip / pbcopy / xclip)")
            if isinstance(flags.get("kickoff"), str):
                extra["kickoff"] = kickoff_command(flags["kickoff"], packet)
                extra["kickoff_args"] = extra["kickoff"][4:]  # what kit kickoff itself reads: <Name> "<brief>" --lane ...
            if packet["token_count"] > budget:
                return emit("fail", f"prompt compile: {packet['token_count']} tokens over the {model} budget {budget}", "a priority-1 rule set too large for this model: read the packet's pruned list", lines=lines, **extra)
            nxt = f"answer {len(unanswered)} question(s) with --answers, or use the packet: {out}" if unanswered else f"the prompt is in {out} (orchestrator_prompt); --full prints it"
            return emit("pass", f"prompt compile: {len(packet['lanes'])} lane(s), {packet['token_count']} tokens for {model}", nxt, lines=lines, **extra)
        if sub == "evolve" and flags.get("verdicts"):
            r = evolve.evolve_from_verdicts(apply=not flags.get("dry"))
            lines = [f"{r['matched']} owner verdict(s) learned from; {len(r['unmatched'])} with no prompt compiled for their piece (left for later)"]
            lines += [f"  {x['verdict']} ({x['score']:g}): {x['status']}" + (f" - {x['reason']}" if x.get("reason") else "") for x in r["results"]]
            bad = [x for x in r["results"] if x["status"] == "rejected"]
            return emit("pass", f"prompt evolve --verdicts: {r['matched']} verdict(s), " + ", ".join(f"{k} {sum(1 for x in r['results'] if x['status'] == k)}" for k in ("accepted", "kept", "rejected")),
                        "lune run kit prompt bench" if any(x["status"] == "accepted" for x in r["results"]) else
                        ("compile prompts with --piece <name> so the owner's next verdict finds them" if not r["matched"] else "nothing changed in the playbook"),
                        lines=lines, loop={k: v for k, v in r.items()}, rejected=len(bad))
        if sub == "evolve":
            if len(args) < 2:
                return emit("fail", "prompt evolve: <packet.json> <score> \"<the owner's words>\"", "lune run kit prompt evolve build/prompt/last.json 4 \"still floaty\"")
            verdict = {"score": float(args[1]), "words": " ".join(args[2:])}
            # never an invented verdict: the score and words must quote one the owner gave (kit verdict recorded it)
            rec = evolve.recorded(verdict["score"], verdict["words"])
            if rec is None:
                return emit("fail", f"prompt evolve: no recorded owner verdict says {verdict['score']:g} \"{verdict['words'][:60]}\" - the playbook learns from the owner's record only",
                            "record the owner's verdict first (lune run kit verdict <kind> <name> <0-10> \"<their words>\"), then quote it here or run: lune run kit prompt evolve --verdicts")
            r = evolve.reflect_and_propose(args[0], verdict, flags.get("verify") if isinstance(flags.get("verify"), str) else None, apply=not flags.get("dry"))
            lines = [f"gradient: {len(r['gradient']['blame'])} missing rule(s) named"] + [f"  [{b['lane']}] '{b['word']}' -> {b['missing']}" for b in r["gradient"]["blame"]]
            lines += [f"  {c}" for c in r.get("counters", [])]
            if r.get("delta"):
                lines += [f"delta +{len(r['delta']['add'])} -{len(r['delta']['remove'])}; benchmark {r['base']['accuracy']:.0%} -> {r['candidate']['accuracy']:.0%}"]
            status = "pass" if r["status"] in ("accepted", "kept") else "fail"
            return emit(status, f"prompt evolve: {r['status']}" + (f" ({r['reason']})" if r.get("reason") else ""), "lune run kit prompt bench" if r["status"] == "accepted" else "nothing changed in the playbook", lines=lines, result={k: v for k, v in r.items() if k != "gradient"})
        if sub == "bench":
            model = comp.resolve_model(flags.get("model") if isinstance(flags.get("model"), str) else "claude")
            cases = [dict(c, model=model) for c in evolve.benchmark_cases()]
            r = evolve.evaluate(cases)
            lines = [f"{r['n']} real owner prompts replayed for {model}: {r['accuracy']:.0%} carry their guardrail; longest {r['tokens']} tokens"]
            lines += [f"  MISSED {f['id']}: {f['missing']} ({f['tokens']} tokens)" for f in r["failed"]]
            if r.get("unfiled"):
                lines.append(f"  {len(r['unfiled'])} case(s) judged on their guardrail and lane only - their own graveyard record is not "
                             f"in this project's vault (checked once it is filed): {', '.join(str(i) for i in r['unfiled'])}")
            ok = r["accuracy"] >= 1.0
            return emit("pass" if ok else "fail", f"prompt bench: {r['accuracy']:.0%} of {r['n']} historical prompts carry the guardrail that would have prevented their failure", "none - proceed" if ok else "fix the template or grounding the missed case names (never its must_contain)", lines=lines, bench=r)
        if sub == "case":
            if len(args) < 2 or args[0] not in caselib.CASE_LANES:
                return emit("fail", f"prompt case: <lane> \"<words>\" (lane one of {', '.join(caselib.CASE_LANES)})",
                            'lune run parallax case 3d "make a gothic sword"')
            lane, raw = args[0], " ".join(args[1:])
            case, score = caselib.match(lane, raw)
            if not case:
                return emit("fail", f"prompt case: no case registry for {lane} (kit/knowledge/cases/{lane}.json)", "author the lane's registry")
            c = caselib.contract(case, lane, flags.get("piece") if isinstance(flags.get("piece"), str) else None)
            head = caselib.render_contract(c)
            menu = caselib.render_menu(lane)
            lines = (head + ["menu:"] + menu)[:caselib.MENU_LINES]
            return emit("pass", f"prompt case: {c['case_id']} (score {score}{', the default' if not score else ''})",
                        f'lune run parallax start {lane} --prompt "{raw}"', lines=lines, contract=c)
        if sub == "sub":
            bans = flags.get("ban").split(",") if isinstance(flags.get("ban"), str) else None
            text = subprompts.positive_substitute(" ".join(args), bans)
            return emit("pass", "prompt sub: positive words only", "none - proceed", lines=[text], text=text)
        return emit("fail", f"prompt: unknown sub-command '{sub}'", "compile | clarify | route | evolve | bench | sub")
    except ValueError as e:
        return emit("fail", f"prompt {sub}: {e}", "read the message above")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
