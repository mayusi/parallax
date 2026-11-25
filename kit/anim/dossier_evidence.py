"""dossier_evidence.py — WHAT EACH PHASE OF A MOVE RESTS ON (the owner's older list, AN-06: "extend dossiers with
visibility / uncertainty for anticipation, contact, recovery and the required gameplay view ... each phase
distinguishes measured, inferred and owner-directed motion, with unsupported critical phases visible").

A dossier (assets/animations/dossiers/<move>.json, kit/anim/proc_dossier.py) had to have sources, phases and checks,
and - since 2026-10-18 - one measured source and real timings. It did not say, PHASE BY PHASE, whether what is
written there was measured, worked out, or told by the owner: a wind-up measured off footage and a recovery
guessed from a coaching page looked the same.

    python kit/anim/dossier_evidence.py <move>            one dossier, phase by phase
    python kit/anim/dossier_evidence.py table [<folder>]  every dossier: how many phases rest on what

A PHASE'S BASIS - said by the phase (`"evidence": {"basis": ..., "from": ..., "note": ...}`), else worked out here
from what the dossier already holds:
  measured   its real timing is numbers ([lo, hi] seconds, 0 or more, under a minute, hi > lo - a contact's
             instant may be lo = hi) AND it names where they were measured: a `real_s_from` with numbers in it (not
             "unknown", "n/a", "TODO"), or a source of its own whose `measured` holds numbers
  told       it rests on the owner's word: a source of its own named "owner" or "owner_<what>" (said: "from":
             "owner" and a "note" with the words)
  inferred   anything else: written from reading, from another move, from how the R6 has to do it
  still      a phase that does not move (the start pose): nothing to evidence
SEEN FROM: the views of the reference frames kept for the phase (`reference_frames`: player / side / top / front);
none kept is said. The game's camera is behind the player: a phase with frames and none from `player` says so.
THE CRITICAL PHASES of a strike: its contact and the moving phase that leads into it (the anticipation).
The contact is the phase that says `"contact": true`; unsaid, a COMBAT dossier's is the one proc_dossier.hit_phase
names (a zero-length "contact" phase, else the last phase named for the blow; a "drive" or a "riposte" when it
knows none). A GUN's blow is its shot (a phase named shot / fire): the recoil after it - "kick" - is not a contact.
A dossier of another category (locomotion, idle, reaction) has none unless a phase says so - the one review found the name words calling a
run's "swing through", a wall "kick-off" and a pistol's recoil "kick" contacts. The anticipation is looked for
only in the contact's own stretch of the timeline (a dossier of several clips starts its times again).
One of them resting on `inferred` is UNSUPPORTED - listed first, in every report. A contact that is an instant is
judged like any phase, by its own timing and evidence (it is not "still").

THE RULE (proc_dossier.require, for a dossier of schema 3 - what `kit anim dossier new` now writes): every phase
that moves SAYS its basis; a `measured` one must be measurable as above; a `told` one names "owner" and quotes the
words; an unsupported critical phase is allowed only with the phase's own `"accept": "<why it stands>"`. Older
dossiers (schema 1, 2) are read, never refused: `table` shows what they rest on.
NOT DONE: whether a measured number is RIGHT (the dossier's checks on the built clip do that); asking for more
footage by itself; the recovery as a critical phase (a strike's recovery is its own game timing: the owner's
budgets, not footage)."""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

BASES = ("measured", "inferred", "told")
SCHEMA = 3           # the schema from which a phase must SAY its basis


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _ids(phase):
    s = phase.get("source")
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip()]
    return [x.strip() for x in str(s).split(",") if x.strip()] if isinstance(s, str) else []


def _numbers(x):
    return isinstance(x, str) and any(ch.isdigit() for ch in x)


LONGEST = 60.0       # seconds: no phase of a move is timed longer
NOT_A_PLACE = ("unknown", "n/a", "todo", "tbd", "none", "guess")


def _span(x, instant=False):
    if not (isinstance(x, (list, tuple)) and len(x) == 2):
        return False
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and 0 <= v <= LONGEST for v in x):
        return False
    return float(x[1]) >= float(x[0]) if instant else float(x[1]) > float(x[0])


def _owner(source_id):
    """a source that is the owner's word: "owner", or "owner_<what>" / "owner-<what>" (not "ownership_doc")"""
    i = str(source_id).strip().lower()
    return i == "owner" or i.startswith(("owner_", "owner-", "owner "))


def _traced(text):
    return _numbers(text) and not any(w in text.lower() for w in NOT_A_PLACE)


def _moves(phase):
    g = phase.get("game_s")
    return (isinstance(g, (list, tuple)) and len(g) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == v for v in g) and float(g[1]) > float(g[0]))


def measurable(d, phase, instant=False):
    """can this phase be called measured? -> (yes, where from in words)"""
    if not _span(phase.get("real_s"), instant):
        return False, "no real timing in numbers (seconds, 0 or more, [lo, hi])"
    if _traced(phase.get("real_s_from")):
        return True, str(phase["real_s_from"])
    by = {str(s.get("id")): s for s in d.get("sources") or [] if isinstance(s, dict)}
    for i in _ids(phase):
        if _traced((by.get(i) or {}).get("measured")):
            return True, f"source {i}"
    return False, "its timing names nowhere it was measured"


SHOT_WORDS = ("shot", "fire", "shoot", "break", "trigger")     # ("break": the trigger's break - a pistol's shot instant)
RECOIL_WORDS = ("kick", "recoil")
MORE_HIT_WORDS = ("drive", "riposte")


def criticals(d):
    """-> [the anticipation's name?, the contact's name] of a strike, else []"""
    import proc_dossier as PD
    phases = [p for p in d.get("phases") or [] if isinstance(p, dict) and isinstance(p.get("name"), str)]
    names = [p["name"] for p in phases]
    said = [p["name"] for p in phases if p.get("contact") is True]
    hit = said[-1] if said else None
    if hit is None and d.get("category") in ("combat", "gun"):
        import re
        low = [n.lower() for n in names]
        # (whole words: "shotgun pump" is no shot, "kick-off" no recoil - the one review)
        toks = [re.findall(r"[a-z]+", l) for l in low]
        shots = [n for n, t in zip(names, toks) if set(t) & set(SHOT_WORDS)]
        if d.get("category") == "combat":
            hit = PD.hit_phase(d)
            if hit is None:                                  # (a blow the name words do not know: a drive, a riposte)
                more = [n for n, l in zip(names, low) if any(w in l for w in MORE_HIT_WORDS)]
                hit = more[-1] if more else None
        # a gun's blow is its SHOT: the recoil after it ("kick") is not a contact, and a gun dossier with no shot has none
        # a recoil is only read as one in a GUN's dossier or beside a shot: a combat dossier whose blow is a real
        # kick keeps its "kick" (the one review: it lost its contact)
        first = (re.findall(r"[a-z]+", hit.lower()) or [""])[0] if hit is not None else ""
        recoil = first in RECOIL_WORDS and (d.get("category") == "gun" or bool(shots))
        if shots and (hit is None or recoil):
            hit = shots[-1]
        elif d.get("category") == "gun":                     # (a gun dossier with no shot phase has no contact to evidence)
            hit = None
    if hit not in names:
        return []
    i = names.index(hit)
    lead = None
    start = _start(phases[i])
    for j in range(i - 1, -1, -1):
        s = _start(phases[j])
        g = phases[j].get("game_s")
        # (the times start again, or the phase before runs past this one's start: another clip's stretch)
        if s is None or start is None or s > start + 1e-9 or float(g[1]) > start + 1e-9:
            break
        if _moves(phases[j]):
            lead = names[j]
            break
        start = s
    return ([lead] if lead else []) + [hit]


def _start(phase):
    g = phase.get("game_s")
    if isinstance(g, (list, tuple)) and len(g) == 2 and all(isinstance(v, (int, float)) and v == v for v in g):
        return float(g[0])
    return None


def basis(d, phase, contact=False):
    """-> (basis, why, said: True when the phase says it itself). contact: the phase is the strike's contact - an
    instant is judged, not skipped as still"""
    if not _moves(phase) and not contact:
        return "still", "it does not move", False
    ev = phase.get("evidence")
    if isinstance(ev, dict) and ev.get("basis") in BASES:
        return ev["basis"], str(ev.get("from") or ev.get("note") or "said by the phase"), True
    yes, where = measurable(d, phase, instant=contact)
    if yes:
        return "measured", where, False
    if any(_owner(i) for i in _ids(phase)):
        return "told", "an owner source", False
    return "inferred", where, False


def read(d):
    """-> {"phases": [{name, basis, why, said, critical, seen_from, note}], "counts": {...}, "unsupported": [names],
    "critical": [names]}"""
    phases = [p for p in d.get("phases") or [] if isinstance(p, dict) and isinstance(p.get("name"), str)]
    names = [p["name"] for p in phases]
    critical = criticals(d)
    contact = critical[-1] if critical else None
    views = {}
    for r in d.get("reference_frames") or []:
        if isinstance(r, dict) and r.get("phase") in names:
            views.setdefault(r["phase"], [])
            v = r.get("view") or "unsaid"
            if v not in views[r["phase"]]:
                views[r["phase"]].append(v)
    rows, counts, unsupported = [], {b: 0 for b in BASES + ("still",)}, []
    for p in phases:
        b, why, said = basis(d, p, contact=p["name"] == contact)
        counts[b] += 1
        seen = views.get(p["name"], [])
        note = None
        if b != "still":
            if not seen:
                note = "no reference frame kept for it"
            elif "player" not in seen:
                note = "frames kept, none from the player's camera (" + ", ".join(seen) + " only)"
        crit = p["name"] in critical
        if crit and b == "inferred" and not (isinstance(p.get("accept"), str) and p["accept"].strip()):
            unsupported.append(p["name"])
        rows.append({"name": p["name"], "basis": b, "why": why, "said": said, "critical": crit, "seen_from": seen, "note": note})
    return {"phases": rows, "counts": counts, "unsupported": unsupported, "critical": critical}


def missing(d):
    """what proc_dossier.require refuses in a dossier of schema >= SCHEMA -> [words]"""
    try:
        if int(d.get("schema", 1)) < SCHEMA:
            return []
    except (TypeError, ValueError):
        return []
    out = []
    crit = criticals(d)
    for p in d.get("phases") or []:
        if not isinstance(p, dict) or not (_moves(p) or (crit and p.get("name") == crit[-1])):
            continue
        name = p.get("name")
        instant = bool(crit) and name == crit[-1]
        ev = p.get("evidence")
        if not isinstance(ev, dict) or ev.get("basis") not in BASES:
            out.append(f"evidence: phase {name} does not say what it rests on - \"evidence\": {{\"basis\": \"measured\" | "
                       "\"inferred\" | \"told\", \"from\": \"<where>\"}")
            continue
        if ev["basis"] == "measured":
            yes, why = measurable(d, p, instant)
            if not yes:
                out.append(f"evidence: phase {name} says measured, but {why} (real_s [lo, hi] in seconds + real_s_from, "
                           "or a source of its own with `measured` numbers)")
        elif ev["basis"] == "told":
            if str(ev.get("from") or "").strip().lower() != "owner" or sum(ch.isalpha() for ch in str(ev.get("note") or "")) < 3:
                out.append(f"evidence: phase {name} says told - \"from\": \"owner\" and \"note\": the owner's own words")
        elif not str(ev.get("from") or ev.get("note") or "").strip():
            out.append(f"evidence: phase {name} says inferred - from what? (\"from\": the reading, the other move, the R6 limit)")
    for name in read(d)["unsupported"]:
        out.append(f"evidence: phase {name} is the move's "
                   + ("contact" if name == read(d)["critical"][-1] else "anticipation")
                   + " and rests on inference - measure it (kit anim dossier footage), have the owner say it, or let it "
                   "stand with the phase's own \"accept\": \"<why>\"")
    return out


def words(name, r):
    c = r["counts"]
    parts = [f"{c[b]} {b}" for b in BASES if c[b]]
    w = f"dossier {name}: its moving phases rest on " + (", ".join(parts) if parts else "nothing (no phase moves)")
    if r["unsupported"]:
        w += "; UNSUPPORTED: " + ", ".join(r["unsupported"]) + " (critical, inferred)"
    none = [p["name"] for p in r["phases"] if p["note"] == "no reference frame kept for it"]
    blind = [p["name"] for p in r["phases"] if p["note"] and p["note"] != "no reference frame kept for it"]
    if none:
        w += f"; {len(none)} phase(s) with no reference frame kept"
    if blind:
        w += f"; {len(blind)} with frames but none from the player's camera"
    return w


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    import proc_dossier as PD
    try:
        if argv[0] == "table":
            folder = argv[1] if len(argv) > 1 else PD.DIR
            rows, total, broken = [], {b: 0 for b in BASES}, []
            for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
                if os.path.basename(path).startswith("_"):
                    continue
                try:
                    with open(path, encoding="utf-8") as fh:
                        d = json.load(fh)
                    if not isinstance(d, dict) or not d.get("phases"):
                        continue
                    r = read(d)
                except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
                    broken.append(f"{os.path.basename(path)}: {type(e).__name__}")       # (one bad file is said, not the end)
                    continue
                for b in BASES:
                    total[b] += r["counts"][b]
                rows.append({"name": os.path.basename(path)[:-5], **{b: r["counts"][b] for b in BASES},
                             "unsupported": r["unsupported"], "critical": r["critical"]})
            bad = [x["name"] for x in rows if x["unsupported"]]
            if not rows:
                return emit("fail", f"anim evidence: no dossier could be read in {folder.replace(os.sep, '/')}"
                            + (f" ({len(broken)} broken: {broken[0]})" if broken else ""), "name the dossiers' folder", broken=broken)
            strikes = [x["name"] for x in rows if x["critical"]]
            return emit("pass", f"anim evidence: {len(rows)} dossier(s), {len(strikes)} of them strikes"
                        + (f", {len(broken)} unreadable" if broken else "") + "; their phases rest on "
                        + ", ".join(f"{total[b]} {b}" for b in BASES)
                        + f"; {len(bad)} strike(s) with a critical phase that is only inferred", "look at those first",
                        rows=rows, unsupported=bad, broken=broken)
        path = argv[0] if argv[0].endswith(".json") else os.path.join(PD.DIR, f"{argv[0]}.json")
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        r = read(d)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
        return emit("fail", f"anim evidence: it could not be read ({type(e).__name__}: {e})",
                    "python kit/anim/dossier_evidence.py <move>")
    name = os.path.basename(path)[:-5]
    refused = missing(d)
    if refused:
        return emit("fail", f"anim evidence {name}: {refused[0]}" + (f" (+{len(refused) - 1} more)" if len(refused) > 1 else ""),
                    refused[0], **r)
    return emit("pass", words(name, r), "none" if not r["unsupported"] else f"measure {r['unsupported'][0]} or have the owner say it", **r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
