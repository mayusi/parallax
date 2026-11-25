"""catalog.py — check the sound EVENTS catalog (assets/sounds/_events.json, read by ReplicatedStorage.kit.Sfx).

Usage: python kit/audio/catalog.py [--events FILE] [--sounds DIR] [--ids FILE]   (normally: lune run kit sfx catalog)
Errors: an event naming a sound that no recipe or set makes; an unknown bus; a blend key that is not a number;
        a switch without cases / a default that is not one of the cases; a duck on an unknown bus.
Warnings (next_action "improve"): sounds made but not uploaded yet (assets/ids.json has no id: the game would
        warn and stay silent) — upload them with `lune run kit upload`.
"""

import json
import os
import sys

BUSES = {"sfx", "ui", "music", "ambience", "voice"}


def made_sounds(sounds_dir):
    names = {f[:-5] for f in os.listdir(sounds_dir) if f.endswith(".json") and not f.startswith("_") and "." not in f[:-5]}
    sets_dir = os.path.join(sounds_dir, "sets")
    if os.path.isdir(sets_dir):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import sets  # noqa: E402

        for f in os.listdir(sets_dir):
            if f.endswith(".json"):
                with open(os.path.join(sets_dir, f), encoding="utf-8") as fh:
                    names |= set(sets.resolve(json.load(fh)))
    return names


def names_in(e):
    out = []
    for case in [e] + list((e.get("cases") or {}).values()):
        if isinstance(case, str):
            out.append(case)
        elif isinstance(case, dict):
            if isinstance(case.get("sound"), str):
                out.append(case["sound"])
            for s in (case.get("sounds") or {}).values():
                out.append(s)
    return out


def main(argv):
    opts = {"--events": os.path.join("assets", "sounds", "_events.json"), "--sounds": os.path.join("assets", "sounds"), "--ids": os.path.join("assets", "ids.json")}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            i += 1
    if not os.path.isfile(opts["--events"]):
        print(json.dumps({"status": "fail", "summary": f"no {opts['--events']}", "next_action": "lune run kit init writes an empty one; shape: src/kit/SfxRules.luau"}))
        return 1
    with open(opts["--events"], encoding="utf-8") as fh:
        cat = json.load(fh)
    made = made_sounds(opts["--sounds"])
    ids = {}
    if os.path.isfile(opts["--ids"]):
        with open(opts["--ids"], encoding="utf-8") as fh:
            ids = json.load(fh).get("sounds", {})
    buses = BUSES | set((cat.get("buses") or {}).keys())
    errors, unuploaded = [], set()
    for name, e in (cat.get("events") or {}).items():
        if not isinstance(e, dict):
            errors.append(f"{name}: an event is an object")
            continue
        if e.get("bus", "sfx") not in buses:
            errors.append(f"{name}: unknown bus {e.get('bus')!r} (buses: {', '.join(sorted(buses))})")
        if e.get("switch"):
            cases = e.get("cases") or {}
            if not cases:
                errors.append(f"{name}: switch {e['switch']!r} without cases")
            if "default" in e and str(e["default"]) not in cases:
                errors.append(f"{name}: default {e['default']!r} is not one of its cases ({', '.join(cases)})")
        for case in [e] + list((e.get("cases") or {}).values()):
            if isinstance(case, dict):
                for k in (case.get("sounds") or {}):
                    try:
                        float(k)
                    except ValueError:
                        errors.append(f"{name}: blend key {k!r} is not a number")
        duck = e.get("duck")
        if isinstance(duck, dict) and duck.get("bus") not in buses:
            errors.append(f"{name}: duck on unknown bus {duck.get('bus')!r}")
        listed = names_in(e)
        if not listed:
            errors.append(f"{name}: names no sound (sound / sounds / cases)")
        for s in listed:
            if s not in made:
                errors.append(f"{name}: sound {s!r} — no recipe or set makes it (kit new sound {s}, or add it to a set)")
            elif s not in ids:
                unuploaded.add(s)
    n = len(cat.get("events") or {})
    if errors:
        print(json.dumps({"status": "fail", "summary": f"{len(errors)} problem(s) in {n} event(s): {errors[0]}", "next_action": f"fix {opts['--events']}: {errors[0]}", "errors": errors}))
        return 1
    nxt = f"improve: upload {len(unuploaded)} sound(s) the events use (the game stays silent on them): lune run kit upload — {', '.join(sorted(unuploaded)[:6])}" if unuploaded else "none — proceed"
    print(json.dumps({"status": "pass", "summary": f"{n} event(s) valid; {len(unuploaded)} sound(s) not uploaded yet", "next_action": nxt, "not_uploaded": sorted(unuploaded)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
