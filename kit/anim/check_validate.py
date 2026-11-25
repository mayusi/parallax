"""Do the animation gates' warnings catch what the owner rejected, and spare what the owner picked?

The owner, 2026-11-08: gates tighten "where rejecting at the loved 10th percentile would have caught what you
rejected and spared what you loved"; they "only ever get stricter from your verdicts, never looser".

Reads every round manifest (assets/animations/candidates/<Move>/round_K.json: each shown candidate's kit warnings,
written when a limb or the blade moves less than the loved clips' 10th percentile), the owner's OWN anim verdicts
(kit/knowledge/vault/anim/verdicts, a guessed number never counts) that reject a round ("round K" with "all" /
"every", or the candidate ids they name), and the owner's picks (a round's `parents`: the candidates the next round
was bred from). Per warned measure it counts the rejected candidates that carried it (caught, had it failed at p10)
and the picked candidates that carried it (wrongly dropped). A measure is proven only when it caught at least
MIN_CAUGHT rejections, at least MIN_PICKS picks were measured with warnings switched on, and none of them carried it.

A report, never a gate: it changes nothing, writes .verify/checks-anim.json and prints one JSON line last.
usage: python kit/anim/check_validate.py [--root <repo>]
"""

import glob
import json
import os
import re
import sys

MIN_CAUGHT = 3
MIN_PICKS = 3
WARN = re.compile(r"^(?P<key>.+?) (?P<value>-?[\d.]+) < loved p10 (?P<p10>-?[\d.]+)")


def front_and_body(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    front = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    front[k.strip()] = v.strip().strip('"')
            body = text[end + 4 :]
    return front, body


def owners_own(front):
    # kit/lib/vault.luau Vault.ownersOwn: the owner's unless a model inferred it - except a word the owner gave
    return front.get("source") != "inferred" or bool(front.get("word"))


def warning_key(text):
    m = WARN.match(text.strip())
    return m.group("key") if m else re.sub(r"[-\d.]+", "#", text.strip())


def load_rounds(root):
    rounds = []
    for path in sorted(glob.glob(os.path.join(root, "assets", "animations", "candidates", "*", "round_*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                man = json.load(f)
        except (OSError, ValueError):
            continue
        move = os.path.basename(os.path.dirname(path))
        rnd = man.get("round")
        if rnd is None:
            m = re.search(r"round_(\d+)\.json$", path)
            rnd = int(m.group(1)) if m else -1
        rounds.append({"move": move, "round": int(rnd), "parents": man.get("parents") or [],
                       "candidates": man.get("candidates") or []})
    return rounds


NAMED = re.compile(r"^(.+?)/r(\d+)(?:/c(\d+))?$")


def verdict_targets(name, text, moves):
    """the rounds (and the candidate, if one) a verdict note is about: a note named "<Move>/rK" or "<Move>/rK/cN", or a
    note named "<Move>" whose words say "round K" (every round they name) -> [(move, K, "cN" or None)]"""
    m = NAMED.match(name.strip())
    if m and m.group(1).lower() in moves:
        return [(moves[m.group(1).lower()], int(m.group(2)), f"c{m.group(3)}" if m.group(3) else None)]
    move = moves.get(name.strip().lower())
    if not move:
        return []
    return [(move, int(k), None) for k in sorted(set(re.findall(r"round (\d+)", text.lower())), key=int)]


def owner_rejections(root, rounds):
    """{(move, round): {"ids": set or None (all), "words": str, "score": float, "date": str}}"""
    moves = {r["move"].lower(): r["move"] for r in rounds}
    out = {}
    for path in glob.glob(os.path.join(root, "kit", "knowledge", "vault", "anim", "verdicts", "*.md")):
        front, body = front_and_body(path)
        if not owners_own(front):
            continue
        # a rejection: 3 or less, or the owner's Redo (kit/lib/vault.luau Vault.polarity)
        try:
            score = float(front.get("score", ""))
        except ValueError:
            score = 0.0 if front.get("direction") == "redo" else None
        if score is None or score > 3:
            continue
        low = body.lower()
        said = "Redo" if front.get("direction") == "redo" else f"{score:g}/10"
        for move, rnd, cand in verdict_targets(str(front.get("name", "")), body, moves):
            ids = {cand[1:]} if cand else set(re.findall(r"\bc(\d+)\b", low))
            every = not cand and any(w in low for w in ("all bad", "every one", "every candidate", "all of them", "all 8"))
            prev = out.get((move, rnd))
            if prev and prev["ids"] is not None and ids and not every:
                ids = ids | prev["ids"]
            out[(move, rnd)] = {"ids": None if every or not ids else ids, "words": " ".join(body.split())[:120],
                                "score": score, "said": said, "date": front.get("date", "")}
    return out


def validate(root):
    rounds = load_rounds(root)
    rejected = owner_rejections(root, rounds)
    picked = set()
    for r in rounds:
        for p in r["parents"]:
            if isinstance(p, str) and "/r" in p:
                picked.add(p)
    measures = {}
    report_rounds = []
    picked_measured = 0
    rejected_candidates = rejected_warned = 0
    shown_candidates = shown_warned = 0
    for r in rounds:
        cands = r["candidates"]
        warned_round = any(c.get("warnings") for c in cands)
        rej = rejected.get((r["move"], r["round"]))
        n_rej = 0
        for c in cands:
            cid = str(c.get("id", ""))
            num = cid.rsplit("/c", 1)[-1] if "/c" in cid else ""
            is_rej = rej is not None and (rej["ids"] is None or num in rej["ids"])
            is_pick = cid in picked
            n_rej += 1 if is_rej else 0
            shown_candidates += 1
            shown_warned += 1 if c.get("warnings") else 0
            if is_rej:
                rejected_candidates += 1
                rejected_warned += 1 if c.get("warnings") else 0
            if is_pick and warned_round:
                picked_measured += 1
            for w in c.get("warnings") or []:
                k = warning_key(str(w))
                m = measures.setdefault(k, {"rejected_with": 0, "picked_with": 0, "shown_with": 0})
                m["shown_with"] += 1
                if is_rej:
                    m["rejected_with"] += 1
                if is_pick:
                    m["picked_with"] += 1
        owner = (f"rejected {n_rej} ({rej['said']}, {rej['date']}): {rej['words']}" if rej
                 else "no owner verdict on this round")
        report_rounds.append({"move": r["move"], "round": r["round"], "shown": len(cands),
                              "warned": sum(1 for c in cands if c.get("warnings")), "owner": owner,
                              "picks_from_it": sorted(p for p in picked if p.startswith(f"{r['move']}/r{r['round']}/"))})
    proven = sorted(k for k, m in measures.items()
                    if m["rejected_with"] >= MIN_CAUGHT and m["picked_with"] == 0 and picked_measured >= MIN_PICKS)
    caught = sum(1 for rr in report_rounds if rr["owner"].startswith("rejected"))
    return {
        "rounds": report_rounds,
        "measures": dict(sorted(measures.items(), key=lambda kv: -kv[1]["rejected_with"])),
        "picked_measured": picked_measured,
        "rejected_rounds": caught,
        "rejected_candidates": rejected_candidates,
        "rejected_warned": rejected_warned,
        "shown_candidates": shown_candidates,
        "shown_warned": shown_warned,
        "proven": proven,
        "why": ("proven: these warnings caught the owner's rejections and no measured pick carried them"
                if proven else
                f"not proven: {picked_measured} owner-picked candidate(s) were measured with warnings on "
                f"(need {MIN_PICKS}) - tightening could drop what the owner would pick, so nothing tightens"),
    }


def main(argv):
    root = argv[argv.index("--root") + 1] if "--root" in argv else "."
    res = validate(root)
    for rr in res["rounds"]:
        if rr["warned"] or rr["owner"].startswith("rejected"):
            print(f"  {rr['move']} round {rr['round']}: {rr['warned']} of {rr['shown']} shown carry warnings; "
                  f"owner: {rr['owner'][:110]}")
    for k, m in list(res["measures"].items())[:8]:
        print(f"  {k}: on {m['rejected_with']} rejected, {m['picked_with']} picked ({m['shown_with']} shown)")
    print(f"  {res['why']}")
    if "--dry" not in argv:  # a dry run writes nothing, not even this report
        out_dir = os.path.join(root, ".verify")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "checks-anim.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
    print(json.dumps({"rejected_rounds": res["rejected_rounds"], "picked_measured": res["picked_measured"],
                      "rejected_candidates": res["rejected_candidates"], "rejected_warned": res["rejected_warned"],
                      "shown_candidates": res["shown_candidates"], "shown_warned": res["shown_warned"],
                      "proven": res["proven"], "measures": len(res["measures"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
