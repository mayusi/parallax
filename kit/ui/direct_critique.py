"""direct_critique.py — a BLIND critique round for a direction board (v8.3). The author is the worst judge of their own
originality; a fresh reviewer who sees the directions numbered in a random order - no titles, no recommendation -
ranks them, names each one's CLICHE (what a lazy version of it already is), says what they would remember tomorrow,
and gives each a stronger version. The answers go into the brief and onto the board; the owner still picks.

    python kit/ui/direct_critique.py <brief> [--game G] [--seed 5]                  the packet
        -> build/judge/ui/directions/<game>/<brief>/ brief.md + <n>.jpg (each direction's moment strip or frame) + key.json
    python kit/ui/direct_critique.py <brief> --record <answers.json> [--judge "<who>"]
        answers.json: {"ranking": [n, ...], "notes": {"<n>": {"cliche": "", "remember": "", "stronger": ""}}}
"""
import argparse
import json
import os
import random
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import direct  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def packet(name, d, seed=5, force=False):
    dirs = [x for x in d.get("directions") or [] if str(x.get("title") or "").strip()]
    order = list(range(len(dirs)))
    random.Random(seed).shuffle(order)
    out = direct.out_dir(d, "judge")
    if os.path.isfile(os.path.join(out, "answers.json")) and not force:
        return None, None  # (a reviewer's answers not recorded yet: never wipe them)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    src = direct.out_dir(d)
    key, blocks = {}, []
    for n, i in enumerate(order, 1):
        x = dirs[i]
        key[str(n)] = x["key"]
        pic = next((p for p in (os.path.join(src, f"{x['key']}.strip.jpg"), os.path.join(src, f"{x['key']}.jpg")) if os.path.isfile(p)), None)
        if pic:
            shutil.copyfile(pic, os.path.join(out, f"{n}.jpg"))
        beats = "; ".join(f"{b[0]}s {b[1]}" for b in (x.get("signature_moment") or {}).get("beats") or [] if isinstance(b, (list, tuple)) and len(b) >= 2)
        blocks.append(f"### {n}\n- the idea: {x.get('big_idea')}\n- how it moves: {x.get('verb')}\n- its moment: {beats}\n"
                      f"- picture: `{n}.jpg`" + (" (six frames across the moment)" if pic and pic.endswith("strip.jpg") else ""))
    ask = d.get("ask")
    doc = f"""# Blind critique: {len(dirs)} directions for one screen

The ask was: "{ask}" (a Roblox game; the pictures are SKETCHES of each direction on the game's world, not finished art).
You see the directions numbered in a random order; their names and the author's favourite are hidden.

{chr(10).join(blocks)}

## Answer (write `answers.json` beside this file)
```
{{"ranking": [<most original first, by number>],
  "notes": {{"<n>": {{"cliche": "what a lazy version of this already is (name the game or trope)",
                    "remember": "the one thing you would remember tomorrow (or 'nothing')",
                    "stronger": "one change that would make it unforgettable"}}}}}}
```
Rank by ORIGINALITY and how memorable the moment is, not by polish (they are sketches). Be blunt: a cliché named is
worth more than praise. Do not open key.json.
"""
    with open(os.path.join(out, "brief.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    with open(os.path.join(out, "key.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(key, fh, indent=1)
    return out, key


def record(name, d, p, answers_path, judge, round_=None):
    out = direct.out_dir(d, "judge")
    with open(os.path.join(out, "key.json"), encoding="utf-8") as fh:
        key = json.load(fh)
    with open(answers_path, encoding="utf-8") as fh:
        ans = json.load(fh)
    rank = [key[str(n)] for n in ans.get("ranking") or [] if str(n) in key]
    if sorted(rank) != sorted(key.values()):
        return None, f"the ranking must name every direction once (got {ans.get('ranking')})"
    notes = {key[str(n)]: v for n, v in (ans.get("notes") or {}).items() if str(n) in key}
    entry = {"judge": judge, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ranking": rank, "notes": notes}
    if round_ is not None:
        entry["round"] = str(round_)
    d.setdefault("critiques", []).append(entry)
    direct.save(p, d)
    if os.path.abspath(answers_path) == os.path.abspath(os.path.join(out, "answers.json")):
        os.replace(answers_path, os.path.join(out, f"answers.recorded-{len(d['critiques'])}.json"))
    return entry, ""


def standing(entries):
    """each direction's mean place across the judges of one round, as a share of the field (1 = top, 0 = bottom)"""
    acc = {}
    for c in entries:
        r = c["ranking"]
        for i, k in enumerate(r):
            acc.setdefault(k, []).append(1 - i / max(1, len(r) - 1))
    return {k: sum(v) / len(v) for k, v in acc.items()}


def rounds(critiques):
    """critiques grouped by round (an entry without one is its own round, in order)"""
    out = {}
    for i, c in enumerate(critiques):
        out.setdefault(c.get("round", f"#{i + 1}"), []).append(c)
    return list(out.values())


def movement(critiques):
    """how each direction moved between the last two ROUNDS (each round averaged over its judges), as a share of the
    field: 'B up 0.75' = from the bottom to near the top. One judge per round is noisy (the Veil went last, 2nd, last
    over three single-judge rounds): the summary says how many judges stand behind each round"""
    rs = rounds(critiques)
    if len(rs) < 2:
        return ""
    a, b = standing(rs[-2]), standing(rs[-1])
    out = []
    for k in sorted(b, key=lambda k: -b[k]):
        if k not in a:
            out.append(f"{k} new")
        elif abs(b[k] - a[k]) >= 0.2:
            out.append(f"{k} {'up' if b[k] > a[k] else 'down'} {abs(b[k] - a[k]):.2f}")
    judges = f" ({len(rs[-2])} vs {len(rs[-1])} judge(s){' - noisy: add judges' if min(len(rs[-2]), len(rs[-1])) < 2 else ''})"
    return (", ".join(out) or "no real movement") + judges


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--game", default=None)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--record", default=None)
    ap.add_argument("--judge", default="a fresh reviewer")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--round", default=None, help="several judges of one round share a label: their ranks are averaged")
    a = ap.parse_args(argv)
    try:
        p, d = direct.load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct critique: {e}", f"lune run kit ui direct new {a.name} --ask \"...\"")
    if a.record:
        entry, err = record(a.name, d, p, a.record, a.judge, a.round)
        if not entry:
            return emit("fail", f"direct critique {a.name}: {err}", "fix answers.json")
        top = entry["ranking"][0]
        cl = (entry["notes"].get(top) or {}).get("stronger", "")
        moved = movement(d.get("critiques") or [])
        return emit("pass", f"direct critique {a.name}: recorded ({a.judge}) - most original {top}; ranking {' > '.join(entry['ranking'])}"
                    + (f"; since the last round: {moved}" if moved else ""),
                    f"act on the clichés named, then lune run kit ui direct board {a.name} (the board shows the critique)"
                    + (f"; their idea for {top}: {cl}" if cl else ""), ranking=entry["ranking"])
    out, key = packet(a.name, d, a.seed, a.force)
    if out is None:
        return emit("fail", f"direct critique {a.name}: answers.json is waiting in the packet - record it first",
                    f"lune run kit ui direct critique {a.name} --record <answers.json> (or --force to start a new packet)")
    return emit("pass", f"direct critique {a.name}: blind packet ({len(key)} directions, random order) -> {out.replace(chr(92), '/')}",
                f"give brief.md + the numbered pictures (NOT key.json) to a FRESH reviewer, then: lune run kit ui direct critique {a.name} --record <answers.json> --judge \"<who>\"",
                packet=out.replace(chr(92), "/"))


if __name__ == "__main__":
    sys.exit(main())
