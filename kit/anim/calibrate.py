"""calibrate.py - a dossier's ranges taught by the OWNER's loved clips (2026-10-24). The lane calibrates every range to
loved data (+-10 %); when the owner rates a candidate the dossier did not cover (the reaction matrix's side hits: no
loved side hit existed), this widens each check just enough to hold that clip's measured value, citing his verdict.
It refuses any clip without the owner's OWN score >= 7 (an inferred score, or mine, never teaches a range).

    python kit/anim/calibrate.py <dossier> --from <Clip>[,<Clip>...]            (a dry run: what would change)
    python kit/anim/calibrate.py <dossier> --from <Clip>[,<Clip>...] --apply    (writes the dossier)
A clip is build/animations/<Clip>.clip.json, or a candidate spec <Clip>.dossier.json anywhere under
assets/animations/candidates/ (emitted to build/candidates/ first).
"""
import datetime
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proc_dossier as DS  # noqa: E402

VERDICTS = os.path.join("kit", "knowledge", "vault", "anim", "verdicts")
LOVED = 7.0
TIME_MEASURES = {"head_to_peak_s", "torso_lag_s", "parry_hold_s", "riposte_s", "main_arm_hold_s", "bottom_pause_s",
                 "lead_time_s", "toe_off_to_hit_s", "hit_to_land_s", "clip_seconds",
                 "stamp_lead_s", "hit_time_s"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def front_of(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def owner_score(name, folder=VERDICTS):
    """the owner's OWN latest score on `name` (the vault's rule, kit/lib/vault.luau ownersOwn: not inferred, or his own
    word; by owner) -> (score, date, word) or None"""
    best = None
    for f in glob.glob(os.path.join(folder, "*.md")):
        fr = front_of(open(f, encoding="utf-8").read())
        if fr.get("name", "").lower() != name.lower() or not fr.get("by", "").startswith("owner"):
            continue
        if fr.get("source") == "inferred" and not fr.get("word"):
            continue
        try:
            score = float(fr.get("score", "nan"))
        except ValueError:
            continue
        if math.isnan(score):
            continue
        if best is None or fr.get("date", "") > best[1]:
            best = (score, fr.get("date", ""), fr.get("word", ""))
    return best


def widen(rng, value, measure):
    """a range widened just enough to hold `value` with a margin (10 %, at least one frame for a time) - or as is"""
    lo, hi = float(rng[0]), float(rng[1])
    margin = max(abs(value) * 0.1, 1 / 60 if measure in TIME_MEASURES else 0.0)
    if lo <= value <= hi:
        return [lo, hi]
    return [round(min(lo, value - margin), 3), round(max(hi, value + margin), 3)]


def clip_of(name):
    path = os.path.join("build", "animations", f"{name}.clip.json")
    if os.path.isfile(path):
        return json.load(open(path, encoding="utf-8"))
    specs = glob.glob(os.path.join("assets", "animations", "candidates", "**", f"{name}.dossier.json"), recursive=True)
    if specs:
        import proc_candidates as PC
        out = os.path.join("build", "candidates", f"{name}.clip.json")
        PC.emit(specs[0], out)
        return json.load(open(out, encoding="utf-8"))
    raise FileNotFoundError(f"no clip {path} and no candidate spec {name}.dossier.json")


def main(argv):
    if not argv or "--from" not in argv:
        return emit("fail", "calibrate: needs <dossier> --from <Clip>[,<Clip>]", "lune run kit anim calibrate katana_hit_heavy --from KatanaHitReactionBackHeavy")
    dossier, names = argv[0], [n for n in argv[argv.index("--from") + 1].split(",") if n]
    d = DS.require(dossier)
    refused = [(n, owner_score(n)) for n in names]
    refused = [f"{n} ({'no score of his own' if s is None else f'his {s[0]:g}/10'})" for n, s in refused if s is None or s[0] < LOVED]
    if refused:
        return emit("fail", f"calibrate {dossier}: only the owner's LOVED clips (his own score >= {LOVED:g}) teach a range - not {', '.join(refused)}",
                    "show him the clip; record his score: lune run kit verdict anim <Clip> <0-10> \"<his words>\"")
    changes = []
    today = datetime.date.today().isoformat()
    for n in names:
        score = owner_score(n)
        r = DS.check(clip_of(n), d)
        for ck in d["checks"]:
            v = (r["checks"].get(ck["id"]) or {}).get("value")
            if not isinstance(v, (int, float)) or (isinstance(v, float) and math.isnan(v)):
                continue
            new = widen(ck["range"], float(v), ck["measure"])
            if new != [float(x) for x in ck["range"]]:
                changes.append({"check": ck["id"], "from": ck["range"], "to": new, "clip": n, "value": round(float(v), 3)})
                ck["range"] = new
                ck["why"] = f"{ck.get('why', '')} | widened {today} to hold the owner's {score[0]:g}/10 {n} ({float(v):.3f}) +- 10 %"
    if not changes:
        return emit("pass", f"calibrate {dossier}: every check already holds {', '.join(names)}", "none - proceed", changes=[])
    if "--apply" in argv:
        path = os.path.join("assets", "animations", "dossiers", f"{dossier}.json")
        json.dump(d, open(path, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
        return emit("pass", f"calibrate {dossier}: {len(changes)} range(s) widened to the owner's loved {', '.join(names)} -> {path}",
                    "move the candidate spec(s) into assets/animations/ and build: lune run kit anim <Clip>", changes=changes)
    return emit("pass", f"calibrate {dossier} (dry run): {len(changes)} range(s) would widen - {changes[0]['check']} {changes[0]['from']} -> {changes[0]['to']}",
                f"apply: lune run kit anim calibrate {dossier} --from {','.join(names)} --apply", changes=changes)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
