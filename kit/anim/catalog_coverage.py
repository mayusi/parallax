"""catalog_coverage.py — WHAT THE CATALOGUE COVERS, AND WHAT IT DOES NOT (the owner's older list, AN-08: "measure coverage
by weapon, rig, stance, attack direction, locomotion state and interaction. A coverage report identifies unsupported
requests; performance is reported separately for familiar and unseen families").

The kit's numbers (tempo, holds, the loved pose space) come from the R6 clips the owner rated (kit/anim/motion_lib.py:
the catalogue, every clip with MEASURED tags). proc_calib.coverage counted loved clips for a category. Nothing said,
for a move somebody ASKS for, whether the catalogue has ever seen its like - a greatsword thrust, a left-handed
kick in the air - so a move with no data behind it was built with the same confidence as one with fifty.

    python kit/anim/catalog_coverage.py report                       the catalogue, axis by axis, and the thin and empty cells
    python kit/anim/catalog_coverage.py ask "two handed overhead greatsword slam"     one request: familiar, thin or unseen
    python kit/anim/catalog_coverage.py verdicts                     the owner's verdicts on BUILT clips, familiar against unseen

THE AXES (a clip's place on each is read off its measured tags, its kind and the words of its name and pack):
  kind         attack, m1/combo, ability, defence, reaction, dash, jump, run, walk, idle, dance, other
  weapon       sword, greatsword, katana, knife, heavy (axe, hammer, mace), polearm, gun, unarmed (a punch, a kick, a
               fist in its words - or a FIGHTING clip whose words name no weapon and that kicks), unsaid. The clip's
               own NAME first; its pack's name only for a fighting clip (a sword pack's walk is not a sword move)
  hands        twohanded, righthand, lefthand, botharms, none
  direction    downward, upward, horizontal, diagonal, thrust - of a FIGHTING clip's strike (attack, m1/combo,
               ability: a dance's fast arm is measured as a "strike" too, and is not one), else none
  state        airborne, crouch, spin, lunge, backstep, sidestep, stride - every one the clip has - else grounded
  interaction  reaction (it is struck), defence (it blocks), paired (a grab, a throw, a victim), solo
  rig          R6 - the catalogue holds nothing else, by the owner's ruling (R6 only)
A CLIP COUNTS when the owner LOVED it and its licence lets a game use it. A cell (one value of an axis, or a
pairing of two) is FAMILIAR at 10 such clips or more (proc_calib's own bar), THIN at 1 to 9, UNSEEN at none.
A REQUEST is put on the axes by its words (motion_lib's own synonyms); what it does not say is not held against
it. Its verdict is its WORST cell and the clips that have ALL it asks for: none of those = UNSUPPORTED, said with
the pairing that is missing.
PERFORMANCE: the owner's verdicts on built clips (assets/animations/verdicts.json), each clip put on the axes by
its NAME's words, split by whether its family was familiar, thin or unseen. A reading of a small table, not a law.
WHAT THE WORDS CANNOT KNOW: 271 counted clips name no weapon (some are plainly fist fights by their pack); a
built clip is placed by its name only, and a name says the weapon and little else - so "unsupported" among the
verdicts means, nearly always, "a sword, katana or greatsword move".
NOT DONE: a built clip placed by its own motion or its dossier; stance beyond the tags above (a guard,
a low stance) is not an axis - no tag measures it; the catalogue lives outside git (_artifacts/r6lib): a machine
without it gets a refusal, not a guess."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

FAMILIAR = 10
_SINGLE = {"kick", "punch", "sword", "pistol", "gun", "slash", "dagger", "knife", "fist", "combo", "strike", "dance",
           "swing", "stab", "axe", "hammer", "spear", "blade", "jab", "hook", "dash", "roll", "block", "katana"}
WEAPONS = {
    "greatsword": ("greatsword", "claymore", "zweihander", "gs"),
    "katana": ("katana",),
    "sword": ("sword", "blade"),
    "knife": ("knife", "dagger"),
    "heavy": ("axe", "hammer", "mace", "club"),
    "polearm": ("spear", "staff", "scythe", "lance"),
    "gun": ("gun", "pistol", "rifle", "reload", "shoot"),
    "unarmed": ("punch", "kick", "fist", "jab", "hook", "uppercut", "brawl", "brawler", "boxing", "boxer", "martial"),
}
DIRECTIONS = ("downward", "upward", "horizontal", "diagonal", "thrust")
HANDS = ("twohanded", "righthand", "lefthand", "botharms")
STATES = ("airborne", "crouch", "spin", "lunge", "backstep", "sidestep", "stride")
PAIRED = ("victim", "grab", "throw", "finisher", "execution", "takedown")
AXES = ("kind", "weapon", "hands", "direction", "state", "interaction")
FIGHTING = ("attack", "m1/combo", "ability")
SCORE = {"loved": 1.0, "love": 1.0, "good": 0.75, "ok": 0.5, "bad": 0.25, "horrible": 0.0}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _words(text):
    """a name's words: CamelCase and ACRONYMCase split (GSCraftDiagonal -> gs craft diagonal), a letter-and-number
    token kept whole when it is ONE letter (M1 -> m1; Spin4 -> spin 4), plurals made single, "great sword" one word"""
    import re
    t = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", str(text or ""))
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", t)
    out = []
    for w in re.findall(r"(?<![a-z])[a-z]\d+|[a-z]+|\d+", t.lower()):
        if len(w) > 3 and w.endswith("es") and w[:-2] in _SINGLE:
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and w[:-1] in _SINGLE:
            w = w[:-1]
        if out and out[-1] == "great" and w == "sword":
            out[-1] = "greatsword"
            continue
        out.append(w)
    return out


def _weapon_in(words):
    return next((w for w, keys in WEAPONS.items() if set(words) & set(keys)), None)


def place(row):
    """a catalogue clip -> {axis: value}; "state" is a tuple: every state the clip has"""
    tags = row.get("tags")
    tags = set(tags) if isinstance(tags, (list, tuple, set)) else set()
    name, pack = _words(row.get("name")), _words(row.get("pack"))
    kind = str(row.get("kind") or "other")
    fights = kind in FIGHTING
    weapon = _weapon_in(name) or ((_weapon_in(pack) if fights or kind in ("defence", "reaction") else None))
    if weapon is None:
        weapon = "unarmed" if (fights and "strike" in tags and "legup" in tags) else "unsaid"
    return {
        "kind": kind,
        "weapon": weapon,
        "hands": next((h for h in HANDS if h in tags), "none"),
        "direction": next((d for d in DIRECTIONS if d in tags), "none") if (fights and "strike" in tags) else "none",
        "state": tuple(s for s in STATES if s in tags) or ("grounded",),
        "interaction": ("reaction" if kind == "reaction" else "defence" if kind == "defence"
                        else "paired" if set(name + pack) & set(PAIRED) else "solo"),
    }


def _has(p, axis, value):
    return value in p[axis] if axis == "state" else p[axis] == value


def counts_for(row):
    return row.get("verdict") == "love" and row.get("licence") == "game"


def status(n):
    return "familiar" if n >= FAMILIAR else "thin" if n >= 1 else "unseen"


def table(catalog):
    """-> {"clips", "counted", "axes": {axis: {value: {n, loved, counted, status}}}, "placed": [(row, place)]}"""
    axes = {a: {} for a in AXES}
    placed = []
    for row in catalog:
        p = place(row)
        placed.append((row, p))
        for a in AXES:
            for v in (p[a] if a == "state" else (p[a],)):
                c = axes[a].setdefault(v, {"n": 0, "loved": 0, "counted": 0})
                c["n"] += 1
                c["loved"] += 1 if row.get("verdict") == "love" else 0
                c["counted"] += 1 if counts_for(row) else 0
    for a in AXES:
        for c in axes[a].values():
            c["status"] = status(c["counted"])
    return {"clips": len(catalog), "counted": sum(1 for r in catalog if counts_for(r)), "axes": axes, "placed": placed}


def strikes(t):
    """the weapon x direction cells of the strikes: every weapon the catalogue has a counted strike of, against every
    direction -> [{weapon, direction, counted, status}] (thin and unseen first)"""
    got = {}
    for row, p in t["placed"]:
        if counts_for(row) and p["direction"] != "none":
            got[(p["weapon"], p["direction"])] = got.get((p["weapon"], p["direction"]), 0) + 1
    weapons = sorted(set(WEAPONS))                           # (a strike that names no weapon is on no weapon's row)
    rows = [{"weapon": w, "direction": d, "counted": got.get((w, d), 0), "status": status(got.get((w, d), 0))}
            for w in weapons for d in DIRECTIONS]
    rows.sort(key=lambda r: (r["counted"], r["weapon"], r["direction"]))
    return rows


def wanted(text):
    """a request's words -> {axis: value}: only what it SAYS"""
    import motion_lib as ML
    words = _words(text)
    raw = set(words)
    toks = []
    for w in words:
        toks.append(w)
        toks += ML.SYN.get(w, "").split()
    want = {}
    named = _weapon_in(words) or next((w for w in WEAPONS if w in raw and w != "heavy"), None)   # ("heavy" is a weight)
    if named:
        want["weapon"] = named
    handed = raw & {"hand", "handed", "hands", "arm"}
    if raw & {"twohanded"} or ("two" in raw and handed) or ("both" in raw and handed):
        want["hands"] = "twohanded"
    elif "left" in raw and handed:                           # ("from the left" is where a blow comes from, not a hand)
        want["hands"] = "lefthand"
    elif "right" in raw and handed:
        want["hands"] = "righthand"
    for d in DIRECTIONS:
        if d in toks and not (d == "thrust" and "throw" in raw and not raw & {"thrust", "stab", "spear", "jab"}):
            want["direction"] = d
            break
    for s in STATES:
        if s in toks or s in raw:
            want["state"] = s
            break
    if raw & {"air", "aerial", "midair", "jumping"}:
        want["state"] = "airborne"
    if raw & {"crouching", "low", "ducking"}:
        want.setdefault("state", "crouch")
    kinds = {"m1/combo": ("combo", "m1", "m2", "m3", "m4", "m5"),
             "attack": ("attack", "strike", "slash", "swing", "cut", "slam", "stab", "kick", "punch"),
             "defence": ("block", "parry", "guard", "defence"), "reaction": ("reaction", "hurt", "stagger", "flinch", "knockback"),
             "dash": ("dash", "dodge", "roll"), "jump": ("jump", "leap"), "run": ("run", "sprint"), "walk": ("walk",),
             "idle": ("idle", "stance"), "dance": ("dance", "emote"), "ability": ("ability", "skill", "ultimate")}
    for k, keys in kinds.items():
        if raw & set(keys):
            want["kind"] = k
            break
    if raw & set(PAIRED):
        want["interaction"] = "paired"
    elif want.get("kind") in ("reaction", "defence"):
        want["interaction"] = want["kind"]
    return want


def ask(t, text):
    """-> {"wants", "cells": [{axis, value, counted, status}], "all": counted clips with everything asked,
    "verdict": familiar | thin | unseen | unsupported | unplaced, "missing": words}"""
    want = wanted(text)
    if not want:
        return {"wants": {}, "cells": [], "all": None, "verdict": "unplaced",
                "missing": "none of its words is on an axis (a weapon, a hand, a direction, a state, a kind)"}
    cells = []
    for a, v in want.items():
        c = (t["axes"][a].get(v) or {}).get("counted", 0)
        cells.append({"axis": a, "value": v, "counted": c, "status": status(c)})
    both = sum(1 for row, p in t["placed"] if counts_for(row) and all(_has(p, a, v) for a, v in want.items()))
    worst = min(cells, key=lambda c: c["counted"])
    verdict, missing = status(min(worst["counted"], both)), None
    if both == 0:
        verdict = "unsupported"
        if worst["counted"] == 0:
            missing = f"the catalogue has no loved, game-usable clip that is {worst['axis']} = {worst['value']}"
        else:
            keys = list(want.items())
            pair = next(((a, b) for i, a in enumerate(keys) for b in keys[i + 1:]
                         if not any(counts_for(r) and _has(p, *a) and _has(p, *b) for r, p in t["placed"])), None)
            missing = (f"it has clips that are {pair[0][0]} = {pair[0][1]} and clips that are {pair[1][0]} = {pair[1][1]}, "
                       "and none that is both" if pair else "no one clip has everything it asks for")
    return {"wants": want, "cells": cells, "all": both, "verdict": verdict, "missing": missing}


def verdicts(t, book):
    """the owner's verdicts on built clips, by the family's standing -> {standing: {n, mean, clips: [(name, verdict)]}}"""
    out = {}
    for name, rows in (book.get("verdicts") or {}).items():
        if not isinstance(rows, list) or not rows or not isinstance(rows[-1], dict):
            continue
        v = rows[-1].get("verdict")
        if v not in SCORE:
            continue
        a = ask(t, name)
        g = out.setdefault(a["verdict"], {"n": 0, "sum": 0.0, "clips": []})
        g["n"] += 1
        g["sum"] += SCORE[v]
        g["clips"].append([name, v])
    for g in out.values():
        g["mean"] = round(g.pop("sum") / g["n"], 2)
    return out


def line(text, t=None):
    """one sentence for a move's words, for the dossier commands and the build (never raises: a machine without the
    catalogue, or words that cannot be placed, are said). t: the table already made (the build asks for many moves)"""
    try:
        a = ask(t if t is not None else table(load()), text)
    except Exception as e:                                   # noqa: BLE001
        return f"catalogue: not read ({type(e).__name__}: {str(e)[:80]})"
    if a["verdict"] == "unplaced":
        return "catalogue: its name says no weapon, hand, direction or kind - ask in words: python kit/anim/catalog_coverage.py ask \"...\""
    said = ", ".join(f"{c['value']} {c['counted']}" for c in a["cells"])
    if a["verdict"] == "unsupported":
        return f"catalogue: UNSUPPORTED ({a['missing']}; {said}) - every number of this move must come from its own sources"
    return f"catalogue: {a['verdict']} ({a['all']} loved, game-usable clip(s) have all of it; {said})"


def load():
    import motion_lib as ML
    if not os.path.isfile(ML.CATALOG):
        raise FileNotFoundError(f"{ML.CATALOG.replace(os.sep, '/')} is not on this machine (python kit/anim/motion_lib.py build "
                                "makes it from the library's own clips)")
    return ML.load()


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        t = table(load())
        if argv[0] == "ask":
            a = ask(t, " ".join(argv[1:]))
            said = ", ".join(f"{c['axis']} {c['value']}: {c['counted']} ({c['status']})" for c in a["cells"])
            if a["verdict"] == "unplaced":
                return emit("fail", f"anim coverage: the request cannot be placed - {a['missing']}", "say the weapon, the hands, the direction")
            if a["verdict"] == "unsupported":
                return emit("fail", f"anim coverage: UNSUPPORTED - {a['missing']} ({said})",
                            "its numbers must come from its own dossier (kit anim dossier new <move>): the catalogue backs nothing here", **a)
            return emit("pass", f"anim coverage: {a['verdict']} - {a['all']} loved, game-usable clip(s) have everything it asks ({said})",
                        "none" if a["verdict"] == "familiar" else "thin data: lean on the move's own dossier", **a)
        if argv[0] == "verdicts":
            import proc_dossier as PD
            with open(PD.VERDICTS, encoding="utf-8") as fh:
                book = json.load(fh)
            v = verdicts(t, book)
            order = [k for k in ("familiar", "thin", "unseen", "unsupported", "unplaced") if k in v]
            return emit("pass", "anim coverage: the owner's verdicts on built clips - "
                        + "; ".join(f"{k}: {v[k]['n']} clip(s), mean {v[k]['mean']:.2f}" for k in order)
                        + " (1 = loved, 0 = horrible; a clip is placed by its name)", "a small table: read it, do not rule by it", groups=v)
        if argv[0] != "report":
            print(__doc__)
            return 2
        axes = {a: {v: {k: c[k] for k in ("n", "loved", "counted", "status")} for v, c in sorted(vals.items(), key=lambda x: -x[1]["counted"])}
                for a, vals in t["axes"].items()}
        cells = strikes(t)
        cells_total = len(cells)
        empty = [f"{c['weapon']} {c['direction']}" for c in cells if c["status"] == "unseen"]
        thin = [f"{c['weapon']} {c['direction']} ({c['counted']})" for c in cells if c["status"] == "thin"]
        lows = [f"{a} {v} ({c['counted']})" for a, vals in t["axes"].items() for v, c in vals.items() if c["status"] != "familiar"]
        return emit("pass", f"anim coverage: {t['clips']} clips, {t['counted']} loved and game-usable; "
                    f"{len(lows)} axis value(s) under {FAMILIAR}; strikes by weapon and direction: {len(empty)} of {cells_total} cells empty, {len(thin)} thin",
                    "ask about a move before building it: python kit/anim/catalog_coverage.py ask \"<the move in words>\"",
                    axes=axes, under=lows, strikes_empty=empty, strikes_thin=thin, strikes_cells=cells_total)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
        return emit("fail", f"anim coverage: it could not be read ({type(e).__name__}: {e})", "python kit/anim/catalog_coverage.py report")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
