"""anim_plan.py — `kit anim plan <Name> [--dossier <move>]`: where ONE action stands in the route (mission 04-anim 5.12)
and at most five commands per stage. Stages, in order, each locked until the one before is done:
  1 dossier   the move researched: assets/animations/dossiers/<move>.json complete (proc_dossier.require)
  2 author    candidates made from scratch: assets/animations/candidates/<Name>/round_K.json with >= 4 gate-clean
  3 gates     every candidate passed the engine / proc / vocab / dossier / physics gates (the round's rejected list)
  4 picks     the owner picked from the round's sheet (kit verdict anim <Name>/rK/cN ... --tag pick)
  5 studio    the picked one played in Studio on the owner's character (build/candidates/<Name>/studio/*)
  6 verdict   the owner's verdict on it in Studio (kit verdict anim <Name> ...)
Reads files only; never builds."""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_dossier as DS  # noqa: E402

VERDICTS = os.path.join("kit", "knowledge", "vault", "anim", "verdicts")


def rerun(name, move, man):
    """the same round rebuilt ON PURPOSE (too few gate-clean): --overwrite (a round's manifest is never replaced by
    accident) + how it was made - bred from its parents, or fresh with its stated change"""
    k = man["round"]
    how = (f" --parents {','.join(man['parents'])}" if man.get("parents")
           else f" --fresh --change \"{man['change']}\"" if k > 0 else "")
    return f"lune run kit anim candidates {name} --dossier {move} --n 8 --round {k}{how} --overwrite"


def verdicts_for(name):
    out = []
    for f in glob.glob(os.path.join(VERDICTS, "*.md")):
        base = os.path.basename(f).lower()
        if base.startswith(name.lower() + "-"):             # 'roundhouse-...' never 'roundhouseleft-...'
            out.append(base)
    return sorted(out)


def round_rejected(name, k):
    """the owner rejected round k as a whole (a verdict on '<Name>/r<k>' tagged rejected, or scored <= 3)"""
    import re
    for v in verdicts_for(name):
        if v.startswith(f"{name.lower()}-r{k}--"):
            text = open(os.path.join(VERDICTS, v), encoding="utf-8").read()
            m = re.search(r"^score:\s*([\d.]+)", text, re.M)
            if "rejected" in text.split("---")[1] or (m and float(m.group(1)) <= 3):
                return v
    return None


def plan(name, move=None):
    if move is None:                                       # the dossier the action's rounds were made from
        rs = sorted(glob.glob(os.path.join("assets", "animations", "candidates", name, "round_*.json")))
        if rs:
            move = json.load(open(rs[0], encoding="utf-8")).get("dossier")
    move = move or DS.snake(name)
    stages = []
    try:
        d = DS.require(move)
        stages.append(("dossier", True, f"{move}: {len(d['sources'])} sources, {len(d['checks'])} checks", []))
    except SystemExit as e:
        stages.append(("dossier", False, str(e)[:160], [f"lune run kit anim dossier new {move} --category combat",
                                                        f"lune run kit anim dossier check {move}"]))
        return stages
    rounds = sorted(glob.glob(os.path.join("assets", "animations", "candidates", name, "round_*.json")),
                    key=lambda p: int(p.rsplit("_", 1)[1].split(".")[0]))
    if not rounds:
        stages.append(("author", False, "no candidate round yet", [f"lune run kit anim candidates {name} --dossier {move} --n 8"]))
        return stages
    man = json.load(open(rounds[-1], encoding="utf-8"))
    k = man["round"]
    clean = len(man["candidates"])
    stages.append(("author", clean >= 4, f"round {k}: {clean} gate-clean candidates ({man['change'][:90]})",
                   [] if clean >= 4 else [rerun(name, move, man)]))
    stages.append(("gates", clean >= 4, f"{len(man['rejected'])} rejected by the gates in round {k}"
                   + (f" (first: {man['rejected'][0]['why'][0][:70]})" if man["rejected"] else ""),
                   [f"lune run kit anim judge build/candidates/{name}/round_{k}/c<N>.clip.json"]))
    sheet = os.path.join("build", "candidates", name, f"round_{k}", "picks.html")
    picks = [v for v in verdicts_for(name) if v.startswith(f"{name.lower()}-r{k}-c")]   # candidate picks, not the round
    if not os.path.exists(sheet):
        stages.append(("picks", False, "no pick sheet for this round", [f"lune run kit anim picks {name} --round {k}"]))
        return stages
    rej = round_rejected(name, k)
    if rej:
        stages.append(("picks", False, f"the owner REJECTED round {k} ({rej}) - author a NEW round with a stated structural change "
                                       "(never breed without a pick); read his words in that verdict first",
                       [f"lune run kit anim candidates {name} --dossier {move} --round {k + 1} --fresh --change \"<what is different>\"",
                        "lune run kit verdict list anim"]))
        return stages
    if not picks:
        stages.append(("picks", False, f"sheet ready ({sheet}) - waiting for the owner's pick",
                       [f'lune run kit verdict anim {name}/r{k}/c<N> <0-10> "<words>" --tag pick']))
        return stages
    stages.append(("picks", True, f"picked: {', '.join(p.split('--')[0] for p in picks)}",
                   [f"lune run kit anim candidates {name} --dossier {move} --round {k + 1} --parents <picked ids>"]))
    studio = glob.glob(os.path.join("build", "candidates", name, "studio", "*"))
    stages.append(("studio", bool(studio), f"{len(studio)} Studio capture(s)" if studio else "not played in Studio yet",
                   [] if studio else ["lune run kit anim play <the picked clip> (Studio open, the owner's character)"]))
    final = [v for v in verdicts_for(name) if "-r" not in v]
    stages.append(("verdict", bool(final), final[-1] if final else "no final verdict",
                   [] if final else [f'lune run kit verdict anim {name} <0-10> "<the owner\'s words in Studio>"']))
    return stages


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    name = a[0]
    st = plan(name, a[a.index("--dossier") + 1] if "--dossier" in a else None)
    for i, (stage, done, what, cmds) in enumerate(st, 1):
        print(f"  {i} {stage:8s} [{'done' if done else 'TODO'}] {what}")
        for cmd in cmds[:5]:
            print(f"        {cmd}")
    nxt = next(((s, c) for s, d, _, c in st if not d), None)
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"plan {name}: " + " > ".join(f"{s}{'' if d else '*'}" for s, d, _, _ in st),
                      "next_action": (f"improve: {nxt[0]} - {nxt[1][0]}" if nxt and nxt[1] else "none - proceed")}))
