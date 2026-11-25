"""gameplan.py — `kit game plan <Name>`: ONE game's route, stage by stage, from its own files (mission 06 5.11).

    python kit/systems/gameplan.py <Name>

Stages: brief -> world -> systems -> net -> moves -> playtests -> accept. Each is done / partly done / to do with what
is missing; the first stage not done gets its exact commands (at most five). Reads only; one JSON verdict line.
"""

import glob
import json
import os
import re
import sys


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def open_questions(game_md):
    """the brief's open questions: a '## heading' whose body still starts with TODO"""
    if not os.path.isfile(game_md):
        return ["GAME.md"]
    heading, out = None, []
    for line in open(game_md, encoding="utf-8").read().splitlines():
        m = re.match(r"^##\s+(.+)", line)
        if m:
            heading = m.group(1).strip()
        elif line.startswith("TODO") and heading:
            out.append(heading)
            heading = None
    return out


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: gameplan.py <Name>", "next_action": "lune run kit game plan <Name>"}))
        return 2
    name = argv[0]
    root = os.path.join("games", name)
    if not os.path.isdir(root):
        print(json.dumps({"status": "fail", "summary": f"no game {root}", "next_action": f"lune run kit game new {name}"}))
        return 1
    g = f" --game {name}"
    stages = []

    def stage(key, title, status, missing, commands):
        stages.append({"key": key, "title": title, "status": status, "missing": missing, "commands": commands[:5]})

    q = open_questions(os.path.join(root, "GAME.md"))
    stage("brief", "the brief (the owner's answers)", "done" if not q else "partial", [f"{len(q)} open: {', '.join(q[:4])}"] if q else [],
          [f"ASK THE OWNER: {', '.join(q[:3])} -> games/{name}/GAME.md", f"lune run kit game check {name}"])

    worlds = [os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(root, "assets", "worlds", "*.json"))]
    compiled = [w for w in worlds if os.path.isfile(os.path.join(root, "src", "world", f"{w}.model.json"))]
    st = "done" if worlds and len(compiled) == len(worlds) else ("partial" if worlds else "to do")
    stage("world", "the world (compiled, checked)", st,
          ([] if worlds else ["no world blueprint"]) + ([f"{len(worlds) - len(compiled)} not compiled"] if len(compiled) < len(worlds) else []),
          [f"lune run kit new world <Pascal> --from BattlegroundsArena{g}", f"lune run kit world{g}", f"lune run kit world check <Name>{g}"])

    rules = glob.glob(os.path.join(root, "src", "shared", "*Rules.luau"))
    specs = glob.glob(os.path.join(root, "tests", "*.spec.luau"))
    corpus = os.path.isfile(os.path.join(root, "tests", "regressions.json"))
    st = "done" if len(rules) >= 3 and len(specs) >= len(rules) and corpus else ("partial" if rules else "to do")
    stage("systems", "systems (pure Rules + hostile specs + a regression corpus)", st,
          [] if st == "done" else [f"{len(rules)} Rules module(s), {len(specs)} spec file(s)"] + ([] if corpus else ["tests/regressions.json"]),
          [f"lune run kit new system <Pascal>{g}", f"lune run kit test{g}", f"lune run kit fuzz{g}", f"lune run kit mutate{g}",
           f"lune run kit mutate --regressions{g} (tests/regressions.json: every bug found, replanted)"])

    schemas = glob.glob(os.path.join(root, "assets", "net", "*.net.json"))
    gen = [s for s in schemas if os.path.isfile(os.path.join(root, "src", "net", os.path.basename(s).replace(".net.json", "Net.luau")))]
    st = "done" if schemas and len(gen) == len(schemas) else ("partial" if schemas else "to do")
    stage("net", "remotes from schemas (audit green)", st,
          [] if st == "done" else ([f"{len(schemas) - len(gen)} schema(s) not generated"] if schemas else ["no schema"]),
          [f"write games/{name}/assets/net/<System>.net.json", f"lune run kit net{g}", f"lune run kit audit{g}"])

    sets = glob.glob(os.path.join(root, "assets", "moves", "sets", "*.json"))
    built = [s for s in sets if os.path.isfile(os.path.join(root, "src", "moves", os.path.basename(s)))]
    st = "done" if sets and len(built) == len(sets) else ("partial" if sets else "to do")
    stage("moves", "moves as data (frames from the anims)", st,
          [] if st == "done" else ([f"{len(sets) - len(built)} set(s) not compiled"] if sets else ["no move set"]),
          [f"lune run kit move{g}", f"LOOK at games/{name}/build/moves/<Set>.png"])

    scen = [os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(root, "tests", "playtest", "*.luau"))]
    passed, failed = [], []
    for s in scen:
        r = load(os.path.join(root, "build", "playtests", s, "result.json"))
        if r is None:
            continue
        ok = not r.get("errors") and all(c.get("ok") for c in r.get("checks") or [])
        (passed if ok else failed).append(s)
    st = "done" if scen and len(passed) == len(scen) else ("partial" if passed or failed else "to do")
    stage("playtests", "playtests in Studio (0 console errors)", st,
          [] if st == "done" else [f"{len(scen)} scenario(s): {len(passed)} pass, {len(failed)} fail, {len(scen) - len(passed) - len(failed)} never run"],
          [f"rojo serve games/{name}/default.project.json (Studio: connect)"] + [f"lune run kit playtest run {s}{g}" for s in scen[:4]])

    floors = glob.glob(os.path.join(root, "assets", "**", "*.accepted.json"), recursive=True)
    stage("accept", "the owner's floors (kit accept)", "done" if floors else "to do", [] if floors else ["no accepted floor"],
          [f"the owner plays it; lune run kit verdict system {name} <0-10> \"<words>\"", "lune run kit accept <kind> <name>"])

    first = next((x for x in stages if x["status"] != "done"), None)
    done = sum(1 for x in stages if x["status"] == "done")
    print(json.dumps({
        "status": "pass",
        "summary": f"game plan {name}: {done}/{len(stages)} stages done" + (f"; next: {first['title']} ({first['status']})" if first else ""),
        "next_action": first["commands"][0] if first else "done: the owner's next system",
        "stages": stages,
        "next": first["key"] if first else None,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
