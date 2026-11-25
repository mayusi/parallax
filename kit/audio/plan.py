"""plan.py — `kit sfx plan <set>`: ONE sound set's route, stage by stage, from its own files (mission 07 5.9).

    python kit/audio/plan.py <set>       (cwd = the repo, or KIT_GAME / games/.active's folder for game sets)

Stages: [direction ->] refs -> identity -> design -> match -> sheet -> booth -> av -> runtime -> upload. Each is done / partly done /
to do with what is missing; the first stage not done gets its exact commands (at most five). Reads only; prints one
JSON verdict line. The owner's ears are the only quality signal: booth verdicts >= 7 make the booth stage done.
"""

import glob
import json
import os
import sys

RECIPES = os.path.join("assets", "sounds")
BUILD = os.path.join("build", "sounds")


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def rendered(member):
    """the member's rendered files (weight variants and takes: <member>.ogg, <member>_light.ogg, <member>_2.ogg ...)"""
    return [f for f in glob.glob(os.path.join(BUILD, f"{member}*.ogg"))
            if os.path.basename(f)[len(member):][:1] in ("", ".", "_")]


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: plan.py <set>", "next_action": "lune run kit sfx plan <set>"}))
        return 2
    name = argv[0]
    # a game's own set lives in its folder (KIT_GAME / games/.active), the project's at the root
    global RECIPES, BUILD
    g = os.environ.get("KIT_GAME")
    if not g or g == "none":
        ap = os.path.join("games", ".active")
        g = open(ap, encoding="utf-8").read().strip() if os.path.isfile(ap) else ""
    groot = os.path.join("games", g) if g and g != "none" else None
    if groot and os.path.isfile(os.path.join(groot, "assets", "sounds", "sets", f"{name}.json")):
        RECIPES, BUILD = os.path.join(groot, "assets", "sounds"), os.path.join(groot, "build", "sounds")
    s = load(os.path.join(RECIPES, "sets", f"{name}.json"))
    if not s:
        print(json.dumps({"status": "fail", "summary": f"no set assets/sounds/sets/{name}.json", "next_action": "write the set (shared DNA + members): the parallax-sfx skill"}))
        return 1
    members = list((s.get("members") or {}).keys())
    stages = []

    def stage(key, title, status, missing, commands):
        stages.append({"key": key, "title": title, "status": status, "missing": missing, "commands": commands[:5]})

    # 0 direction: EVERY set names its direction doc ("direction": "<Piece>", in the game's sounds/direction/), picked
    # by the owner before the set is designed (the owner, 2026-10-24). A set that names none is told to, first
    # (LIMITATIONS_FIXES_V4 SFX-X B: "kit sfx plan omits the direction gate" - it was only shown when one was named)
    if s.get("direction"):
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import direction as directionlib  # noqa: E402

        doc = os.path.join(RECIPES, "direction", f"{s['direction']}.md")
        st_ = directionlib.check(doc, "sfx")[0] if os.path.isfile(doc) else "missing"
        stage("direction", f"the sound direction picked by the owner ({s['direction']})", "done" if st_ == "picked" else ("partial" if st_ in ("ready", "draft") else "to do"),
              [] if st_ == "picked" else [f"{s['direction']}: {st_}"],
              [f"lune run kit sfx direction {s['direction']}" + (" --new" if st_ == "missing" else ""), "lune run kit sfx board"])
    else:
        piece = "".join(w[:1].upper() + w[1:] for w in name.replace("-", "_").split("_") if w) or "<Piece>"
        stage("direction", "the sound direction picked by the owner (none named)", "to do",
              [f"the set names no direction doc (\"direction\": \"<Piece>\" in sets/{name}.json)"],
              [f"lune run kit sfx direction {piece} --new", "lune run kit sfx board (the owner picks one of its three)",
               f"name it in {os.path.join(RECIPES, 'sets', name + '.json')}: \"direction\": \"{piece}\""])

    # 1 references the owner chose
    refs = load(os.path.join(RECIPES, "references.json")) or {}
    classes = {k: v for k, v in refs.items() if isinstance(v, list) and v}
    st = "done" if len(classes) >= 3 else ("partial" if classes else "to do")
    stage("refs", "references the owner chose", st,
          [f"{3 - len(classes)} more class(es) with references (>= 3)"] if st != "done" else [],
          [f"lune run kit sfx find \"<words>\" (candidates)", "lune run kit sfx listen <candidates> (the owner picks <= 3 per class)",
           "record the picks in assets/sounds/references.json"])

    # 2 identity derived from those references
    ident_id = s.get("identity")
    ident = load(os.path.join(RECIPES, "identities", f"{ident_id}.json")) if ident_id else None
    from_refs = bool(ident and (ident.get("derived_from") or ident.get("from_refs")))
    st = "done" if ident and from_refs else ("partial" if ident else "to do")
    stage("identity", "the sonic identity (from the references)", st,
          ([] if ident else [f"identity {ident_id or '(none named)'}"]) + ([] if from_refs or not ident else ["derived from the owner's references"]),
          [f"lune run kit sfx identity {ident_id or '<id>'} --from <reference files> --class hit"])

    # 3 design: every member rendered; real recordings in the layers
    missing_r = [m for m in members if not rendered(m)]
    samples = any(isinstance(layer, dict) and layer.get("source") == "sample"
                  for part in [s.get("dna") or {}] + list((s.get("members") or {}).values())
                  for layer in (part.values() if isinstance(part, dict) else []))
    st = "done" if not missing_r and samples else ("partial" if len(missing_r) < len(members) else "to do")
    stage("design", "the set designed (one DNA, real sample layers)", st,
          ([f"{len(missing_r)} member(s) not rendered: {', '.join(missing_r[:3])}"] if missing_r else [])
          + ([] if samples else ["no real recording in the layers (synth-only reads as 'middling')"]),
          [f"lune run kit sfx set {name}", "add \"sample\": \"lib:<id>\" layers from kit sfx find (CC0 / royalty-free)"])

    # 4 match: members matched to a reference
    matched = [m for m in members if (load(os.path.join(RECIPES, f"{m}.json")) or {}).get("_matched")
               or os.path.isfile(os.path.join(RECIPES, f"{m}.matched.json"))]
    st = "done" if members and len(matched) == len(members) else ("partial" if matched else "to do")
    stage("match", "matched to the references (one edit per role)", st,
          [f"{len(members) - len(matched)} member(s) not matched"] if st != "done" else [],
          [f"lune run kit sfx match {members[0] if members else '<name>'} --to <reference>"])

    # 5 sheets beside the references
    sheets = [m for m in members if glob.glob(os.path.join(BUILD, "sheets", f"{m}*.png"))]
    st = "done" if members and len(sheets) == len(members) else ("partial" if sheets else "to do")
    stage("sheet", "sound sheets (LOOK beside the references)", st,
          [f"{len(members) - len(sheets)} member(s) without a sheet"] if st != "done" else [],
          [f"lune run kit sfx sheet {members[0] if members else '<name>'} --ref <reference>"])

    # 6 the owner's booth verdicts
    scores = {}
    for m in members:
        v = load(os.path.join(RECIPES, f"{m}.verdict.json"))
        if v and v.get("history"):
            scores[m] = v["history"][-1].get("score")
    good = [m for m, sc in scores.items() if isinstance(sc, (int, float)) and sc >= 7]
    st = "done" if members and len(good) == len(members) else ("partial" if scores else "to do")
    stage("booth", "the owner's booth (>= 7 each)", st,
          ([f"latest scores: {', '.join(f'{m} {sc}' for m, sc in scores.items())}"] if scores else ["no booth verdicts"]),
          [f"lune run kit sfx listen {' '.join(members[:4])}"])

    # 7 in sync, in the engine's picture
    av = [m for m in members if glob.glob(os.path.join(BUILD, "av", f"{m}*.mp4"))]
    st = "done" if members and len(av) == len(members) else ("partial" if av else "to do")
    stage("av", "in sync on the hit (kit sfx av)", st,
          [f"{len(members) - len(av)} member(s) without an AV clip"] if st != "done" else [],
          [f"lune run kit sfx av {members[0] if members else '<name>'} --video <the SampleDojo capture> --at <Hit>"])

    # 8 the Sfx runtime proven by a playtest
    runtime = any("Sfx" in open(f, encoding="utf-8", errors="ignore").read()
                  for f in glob.glob(os.path.join("games", "*", "build", "playtests", "*", "result.json")))
    stage("runtime", "the Sfx runtime proven in a playtest", "done" if runtime else "to do",
          [] if runtime else ["no playtest result names the Sfx runtime"],
          ["lune run kit playtest run combat --game SampleDojo (Studio open on the SampleDojo)"])

    # 9 uploaded (ids for every rendered file)
    ids = load(os.path.join("assets", "ids.json")) or {}
    sids = ids.get("sounds") or {}
    files = [os.path.splitext(os.path.basename(f))[0] for m in members for f in rendered(m)]
    up = [f for f in files if f in sids]
    st = "done" if files and len(up) == len(files) else ("partial" if up else "to do")
    stage("upload", "uploaded (moderation passed)", st,
          [f"{len(files) - len(up)} of {len(files)} file(s) not uploaded"] if st != "done" else [],
          ["lune run kit upload (the owner's yes)", "lune run kit upload --status"])

    # how the masking check counts for this set (kit/audio/sets.py masking_mode): an error for sets made since the gate
    # or declaring "masking": "enforce", a warning for the older ones - said here so the plan never hides it
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import sets as setslib  # noqa: E402

        mlevel, mwhy = setslib.masking_mode(s, os.path.join(RECIPES, "sets", f"{name}.json"))
    except Exception as exc:  # (matplotlib missing etc.: the plan still prints)
        mlevel, mwhy = "unknown", f"{type(exc).__name__}: {exc}"
    masking = {"level": mlevel, "why": mwhy}

    first = next((x for x in stages if x["status"] != "done"), None)
    done = sum(1 for x in stages if x["status"] == "done")
    print(json.dumps({
        "status": "pass",
        "summary": f"sfx plan {name}: {done}/{len(stages)} stages done" + (f"; next: {first['title']} ({first['status']})" if first else "")
        + f"; layer masking counts as {'an ERROR' if mlevel == 'error' else ('a warning' if mlevel == 'warn' else 'unknown')} for this set ({mwhy})",
        "masking": masking,
        "next_action": first["commands"][0] if first else "done: the owner's next class",
        "stages": stages,
        "next": first["key"] if first else None,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
