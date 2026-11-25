"""contact.py — WHEN A STRIKE MEETS ITS TARGET, from the geometry (the owner's limitations list 2026-11-15, A-R06 /
AN-25: "automatic event inference still uses motion-speed peaks ... a speed peak is not necessarily physical contact
and has no target-derived confidence").

    python kit/anim/contact.py <clip.json>            the reading: every contact found, with its confidence
    python kit/anim/contact.py freeze <built clips folder> --out <anims>/blocks/_contact_before.json

THE TARGET is a body standing where the kit's own motion warp leaves it: its chest 3 studs ahead of where the move
began (-Z; of the farthest place the body gets to, the way it faces there, when the move travels), at the height of
the mover's own chest - or where the clip says: "target": [x, y, z] (the space the move
starts in). THE STRIKER is the weapon's line (grip to tip) when the clip carries one, else the limb the event names
("by") or the limb whose end moves fastest (its line: the block's middle to its end).

A CONTACT is a frame at which the striker's line comes NEAREST the target's chest, while it is striking (its end has
moved at 40% of its top speed within 4 frames: a blade resting in a guard that points at the target is not a hit).
Every such frame is a contact (a combo has several). THREE KINDS OF EVIDENCE give its confidence:
    0.5   geometry    the line passes within REACH of the chest at that frame (it meets the body)
    0.25  speed       a peak of the striker's speed lies within 3 frames (the old method agrees)
    0.25  authored    an event the author placed lies within 2 frames
(frames counted at 60 a second: the same stretch of time at any other rate). A Hit's OWN confidence is the geometry
and the speed of the contact that backs it (0.75 at most: its own event is no evidence for itself), 0 when none does.
A contact is an ARRIVAL: the line was further from the chest the frame before, and it is the first frame of a hold.
A speed peak with no geometry behind it is still listed (0.25, plus 0.25 when authored): "fastest there, but the
striker does not reach the target" - that is what the old inference called a Hit.

MEASURED 2026-11-15 on the five loved cuts whose Hit the owner's move files AUTHOR (the labelled examples): the
nearest-the-chest frame is the authored frame within 2 frames on all five (0, 0, -2, 0, -2); the speed peak is 0, 0,
-7, -8 and -4 frames off - on the overhead, the underhip and the makko the blade is fastest well before it arrives.

THE GATE (kit/anim/metrics.py, in every build): a Hit that a BUILDER INFERRED from a speed peak (the clip says
"hit_inferred") and that the geometry puts more than OFF frames elsewhere FAILS, named - author the Hit ("events") or
name the target. An AUTHORED Hit that the geometry does not back is said (the author's word stands), never failed. A
clip made before the rule (frozen once: <anims>/blocks/_contact_before.json) is said, never failed.
A weapon's inferred Hit with NO contact at all fails too (fastest somewhere, never at the target). The builders say
which Hits they placed by their times ("hit_inferred": [seconds]); kit/anim/proc_blade.py and learn_compose.py do
not yet (their Hits read as authored). A Hit moved onto the contact can trip the older gate (kit/anim/clip.py: a Hit
0..3 frames after a speed peak) when the two are more than about 6 frames apart: such a clip needs its target named.
NOT BUILT: a strike read per Hit with its own striker (a clip's first "by" is used for all), hit REACTIONS told from
strikes (their "Hit" is read against a target ahead), a target that moves, a target other than a standing body (a low sweep's shin, a thrown thing), a move
that passes THROUGH its target (a dash-through cut: say its "target")."""
import datetime
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BEFORE = "_contact_before.json"
AHEAD = 3.0          # studs ahead of the mover the target's chest stands (src/kit/AnimLayers.warpFor's contact distance)
REACH = 1.2          # studs from the striker's line to the chest for it to meet the body (a torso is 2 wide, 1 deep)
STRIKING = 0.4       # the share of its top speed the striker's end reached nearby for a near pass to be a strike
NEAR = 4             # frames either side "nearby" means
SPEED_AGREES = 3     # frames between a contact and a speed peak for the two to agree
AUTHOR_AGREES = 2    # frames between a contact and an authored event for the two to agree
OFF = 3              # frames an inferred Hit may be from the geometry's contact
HIT_NAMES = ("hit", "impact", "strike", "slam", "punch", "kick")
LIMBS = {"Right Arm": "RightHand", "Left Arm": "LeftHand", "Right Leg": "RightFoot", "Left Leg": "LeftFoot"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _seg_point(a, b, p):
    d = b - a
    u = float(np.clip(np.dot(p - a, d) / max(float(np.dot(d, d)), 1e-12), 0.0, 1.0))
    return float(np.linalg.norm(a + u * d - p))


def _peaks(speed, share):
    """the local peaks of a speed track that reach `share` of its top -> [index into speed]"""
    if len(speed) == 0 or float(speed.max()) <= 0.5:
        return []
    top, out = float(speed.max()), []
    for i in range(len(speed)):
        before = speed[i - 1] if i > 0 else -1.0
        after = speed[i + 1] if i + 1 < len(speed) else -1.0
        if speed[i] >= share * top and speed[i] >= before and speed[i] > after:
            out.append(i)
    return out


def target_of(clip):
    """the target's chest in the space the move starts in -> np [3]; raises ValueError on a target that is not one"""
    said = clip.get("target")
    if said is None:
        # a move that TRAVELS (a lunge, a dash-in) is warped to end 3 studs short of its target: the target stands
        # 3 studs ahead of the farthest place the body gets to, the way it faces there
        root = clip.get("root")
        if isinstance(root, list) and len(root) > 1 and all(isinstance(r, list) and len(r) == 7 for r in root):
            # (only the travel UP TO the strike counts: the warp's window ends there; a step back or a run-on
            # after the Hit is not where the target stood)
            fps = float(clip.get("fps") or 30)
            upto = len(root) - 1
            warp = clip.get("warp")
            ends = [float(e["t"]) for e in clip.get("events") or [] if isinstance(e, dict) and isinstance(e.get("t"), (int, float))
                    and str(e.get("name", "")).lower() in HIT_NAMES]
            if isinstance(warp, dict) and isinstance(warp.get("to"), (int, float)):
                upto = int(round(float(warp["to"]) * fps))
            elif ends:
                upto = int(round(max(ends) * fps))
            upto = max(1, min(len(root) - 1, upto))
            far = max(root[: upto + 1], key=lambda r: r[4] * r[4] + r[6] * r[6])
            if far[4] * far[4] + far[6] * far[6] > 0.05 * 0.05:
                yaw = 2.0 * math.atan2(far[1], far[3])
                return np.array([far[4] - AHEAD * math.sin(yaw), 0.0, far[6] - AHEAD * math.cos(yaw)])
        return np.array([0.0, 0.0, -AHEAD])
    if (not isinstance(said, list) or len(said) != 3
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e4 for v in said)):
        raise ValueError("\"target\" is [x, y, z]: where the target's chest is, in the space the move starts in (-Z ahead)")
    return np.array([float(v) for v in said])


def read(clip, by=None):
    """-> {"frames", "fps", "striker", "target", "contacts": [{"frame", "t", "studs", "confidence", "evidence": [...]}],
    "hits": [{"name", "frame", "nearest", "off_frames", "confidence", "backed"}], "ambiguous": [words]}.
    Raises ValueError on a clip that cannot be read"""
    import clip as C
    import pose_sheet as PS
    if clip.get("rig") != "R6":
        raise ValueError(f"it is a {clip.get('rig')} clip - a contact is read on the R6 clip")
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    n = len(W)
    root = clip.get("root")
    if isinstance(root, list) and root and len(root) != n:
        raise ValueError(f"its root track has {len(root)} frame(s) and the clip {n}")
    fps = C.clip_fps(clip)
    # (the tolerances are times: counted in frames at 60 a second, the same stretch at any other rate)
    near, speed_agrees, author_agrees, off_by = (max(1, int(round(k * fps / 60.0))) for k in (NEAR, SPEED_AGREES, AUTHOR_AGREES, OFF))
    chest = target_of(clip)
    paths = PS.paths(clip, W)
    events = [e for e in clip.get("events") or [] if isinstance(e, dict) and isinstance(e.get("t"), (int, float))]
    hits = [e for e in events if str(e.get("name", "")).lower() in HIT_NAMES]
    if by is None:
        by = next((e["by"] for e in hits if e.get("by") in LIMBS), None)
    if by is not None and by not in LIMBS:
        raise ValueError(f"the striker {by} is no limb of this body ({', '.join(LIMBS)})")
    if by is None and "Grip" in paths and "BladeTip" in paths:
        striker, a, b = "weapon", paths["Grip"], paths["BladeTip"]
    else:
        if by is None:
            by = max(LIMBS, key=lambda limb: float(np.linalg.norm(np.diff(paths[LIMBS[limb]], axis=0), axis=1).max()) if n > 1 else 0.0)
        striker, a, b = by, np.array([W[i][by][:3, 3] for i in range(n)]), paths[LIMBS[by]]
    dist = np.array([_seg_point(a[i], b[i], chest) for i in range(n)])
    speed = np.linalg.norm(np.diff(b, axis=0), axis=1) * fps if n > 1 else np.zeros(0)
    top = float(speed.max()) if len(speed) else 0.0
    peak_frames = [i + 1 for i in _peaks(speed, STRIKING)]       # (the frame AFTER the fastest step: where a Hit is put)

    def striking(i):
        lo, hi = max(0, i - near - 1), min(len(speed), i + near)
        return top > 0.5 and hi > lo and float(speed[lo:hi].max()) >= STRIKING * top

    placed = clip.get("hit_inferred")
    guessed = (lambda e: True) if placed is True else (lambda e: any(abs(float(e["t"]) - float(t)) < 1e-4 for t in placed)) \
        if isinstance(placed, list) else (lambda e: False)
    authored = [int(round(float(e["t"]) * fps)) for e in hits if not guessed(e)]
    contacts = []
    for i in range(n):
        if dist[i] > REACH or not striking(i):
            continue
        if i == 0:
            continue                                             # (where it STARTS is no arrival: a guard, a stab held out)
        after = dist[i + 1] if i + 1 < n else np.inf
        if dist[i] < dist[i - 1] - 1e-9 and dist[i] <= after:    # it came nearer, and gets no nearer: the arrival
            contacts.append({"frame": i, "studs": float(dist[i]), "evidence": ["geometry"]})
    for c in contacts:
        if any(abs(c["frame"] - p) <= speed_agrees for p in peak_frames):
            c["evidence"].append("speed")
    for p in peak_frames:                                        # a speed peak with no geometry behind it is still said
        if not any(abs(c["frame"] - p) <= speed_agrees for c in contacts if "geometry" in c["evidence"]):
            contacts.append({"frame": p, "studs": float(dist[min(p, n - 1)]), "evidence": ["speed"]})
    for c in contacts:
        if any(abs(c["frame"] - h) <= author_agrees for h in authored):
            c["evidence"].append("authored")
        c["confidence"] = round((0.5 if "geometry" in c["evidence"] else 0.0) + 0.25 * ("speed" in c["evidence"])
                                + 0.25 * ("authored" in c["evidence"]), 2)
        c["t"] = round(c["frame"] / fps, 4)
        c["studs"] = round(c["studs"], 3)
    contacts.sort(key=lambda c: c["frame"])
    met = [c for c in contacts if "geometry" in c["evidence"]]
    out_hits, ambiguous = [], []
    for e in hits:
        f = int(round(float(e["t"]) * fps))
        rec = {"name": e.get("name"), "frame": f, "nearest": None, "off_frames": None, "confidence": 0.0, "backed": False,
               "inferred": bool(guessed(e))}
        if met:
            by_it = min(met, key=lambda c: abs(c["frame"] - f))
            backed = abs(f - by_it["frame"]) <= off_by
            rec.update(nearest=by_it["frame"], off_frames=f - by_it["frame"], backed=backed,
                       confidence=(0.5 + 0.25 * ("speed" in by_it["evidence"])) if backed else 0.0)
        out_hits.append(rec)
    if hits and not met:
        ambiguous.append(f"the {striker} never comes within {REACH:g} studs of the target's chest while it strikes "
                         f"(nearest {float(dist.min()):.2f}): no contact the geometry can see")
    if len(met) > len(hits) and hits:
        ambiguous.append(f"{len(met)} contacts (frames {', '.join(str(c['frame']) for c in met)}) and {len(hits)} Hit event(s): "
                         "a pass with no event")
    for c in contacts if not met else []:                        # (beside a real contact, a fast wind-up is just a wind-up)
        if c["evidence"] == ["speed"]:
            ambiguous.append(f"fastest at frame {c['frame']}, but the {striker} is {c['studs']:.2f} studs from the target there: "
                             "a speed peak, not a contact")
    return {"frames": n, "fps": fps, "striker": striker, "target": [round(float(v), 3) for v in chest], "contacts": contacts,
            "hits": out_hits, "ambiguous": ambiguous}


def infer(clip, by=None):
    """the Hit frames a builder may place: the contacts the geometry sees (each with its confidence), or - when it
    sees none - the old speed peaks, said as such -> [(frame, confidence, evidence)]"""
    r = read(dict(clip, events=[]), by)
    met = [c for c in r["contacts"] if "geometry" in c["evidence"]]
    return [(c["frame"], c["confidence"], c["evidence"]) for c in (met or r["contacts"])]


def off(r, every=False):
    """the Hits the BUILD placed (every: any Hit) that the geometry puts elsewhere - or, for a weapon, sees no contact
    for at all (fastest somewhere, never at the target: what a speed peak alone cannot know) -> [hit record]"""
    return [h for h in r["hits"] if (h["inferred"] or every) and not h["backed"]
            and (h["nearest"] is not None or r["striker"] == "weapon")]


def words(r, name):
    if not r["hits"]:
        return f"{name}: no Hit to read" + (f" ({len(r['contacts'])} contact(s) the geometry sees)" if r["contacts"] else "")
    said = []
    for h in r["hits"]:
        if h["nearest"] is None:
            said.append(f"{h['name']} at frame {h['frame']}: the {r['striker']} never arrives within {REACH:g} studs of the "
                        "target's chest - no contact the geometry can see")
        elif h["backed"]:
            said.append(f"{h['name']} at frame {h['frame']} is where the {r['striker']} meets the target "
                        f"(nearest at {h['nearest']}, confidence {h['confidence']:g})")
        else:
            said.append(f"{h['name']} is at frame {h['frame']} and the {r['striker']} meets the target at frame {h['nearest']} "
                        f"({abs(h['off_frames'])} frame(s) {'later' if h['off_frames'] < 0 else 'earlier'})")
    return f"{name}: " + "; ".join(said)


def before(path):
    """the clips made before the rule (frozen; a project with no list has none) -> {names}"""
    if not path or not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        try:
            d = json.load(fh)
        except ValueError as e:
            raise ValueError(f"{path.replace(os.sep, '/')} is not valid JSON ({e}): repair it by hand, never delete it") from e
    clips = d.get("clips") if isinstance(d, dict) else None
    if not isinstance(clips, list):
        raise ValueError(f"{path.replace(os.sep, '/')} has no list of clips")
    return {c for c in clips if isinstance(c, str)}



def _no_list(anims, listed, tool):
    """a project that has never frozen this rule's list (the kit installed into a game that already has clips): the
    failure says how to freeze it once, so an OLD clip is not failed as if it were new"""
    path = os.path.join(anims or os.path.join("assets", "animations"), "blocks", BEFORE)
    if not listed or os.path.isfile(path):
        return ""
    return (f" [this project has no list of clips made before this rule. If THIS clip is an old one, freeze the list "
            f"ONCE - python kit/anim/{tool}.py freeze <the built clips folder> --out {path.replace(os.sep, '/')} - and "
            "read it: it takes every clip that fails today, so a NEW clip among them must be taken out of it by hand]")


def gate(clip, every=False, listed=True):
    """what the build's motion gates add for this clip (kit/anim/metrics.py) -> (the reading for metrics.json, the
    problem or None). Only an R6 character's one-shot with a Hit is read. every: judge an authored Hit too (the
    freeze: a clip built before the builders said which Hits they inferred)"""
    if clip.get("rig") != "R6" or clip.get("prop") or clip.get("loop"):
        return None, None
    if not any(isinstance(e, dict) and str(e.get("name", "")).lower() in HIT_NAMES for e in clip.get("events") or []):
        return None, None
    name = str(clip.get("name"))
    try:
        r = read(clip)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {"error": f"{type(e).__name__}: {e}"}, f"where the strike meets its target could not be read ({e})"
    out = {"striker": r["striker"], "target": r["target"], "contacts": r["contacts"], "hits": r["hits"], "ambiguous": r["ambiguous"],
           "inferred": any(h["inferred"] for h in r["hits"])}
    wrong = off(r, every)
    if not wrong:
        return out, None
    src = (clip.get("source") or {}).get("file") if isinstance(clip.get("source"), dict) else None
    anims = os.path.dirname(src) if isinstance(src, str) and src else os.path.join("assets", "animations")
    try:
        old = before(os.path.join(anims, "blocks", BEFORE)) if listed else set()
    except (ValueError, OSError) as e:                       # (a list that cannot be read excuses nobody)
        return out, f"the list of clips made before the contact rule could not be read ({e})"
    if name in old:
        out["made_before_the_rule"] = True
        return out, None
    return out, (words(dict(r, hits=wrong), name) + " - the Hit was placed by the build at a speed peak: author it (\"events\": [{\"name\": \"Hit\", "
                 "\"t\": seconds}]) where the strike lands, or say where the target is (\"target\": [x, y, z])"
                 + _no_list(anims, listed, "contact"))


def freeze(folder, out, today=None):
    """the built clips whose Hit the geometry puts elsewhere today -> the frozen list (refused when it exists)"""
    if os.path.exists(out):
        raise ValueError(f"{out.replace(os.sep, '/')} exists: the list is frozen once and never extended")
    names = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".clip.json"):
            continue
        stem = f[:-len(".clip.json")]
        if stem.endswith(".r6"):
            stem = stem[:-3]
        if "." in stem:                                       # (a preview, a tune or a polish pass: not a move's clip)
            continue
        try:
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                c = json.load(fh)
        except (OSError, ValueError):
            continue
        # (a clip built before the builders said which Hits they inferred: every Hit counts as maybe inferred)
        if isinstance(c, dict) and gate(c, every=True, listed=False)[1]:
            names.append(str(c.get("name") or stem))
    names = sorted(set(names))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"about": "Clips made BEFORE the contact check (kit/anim/contact.py; the owner's limitations list "
                            "2026-11-15, A-R06) whose Hit is more than 3 frames from where the striker meets a target "
                            "standing 3 studs ahead. They are said, never failed. FROZEN: never add a name here to get a "
                            "clip built - author its Hit, or name its target (\"target\").",
                   "frozen": today or datetime.date.today().isoformat(), "clips": names}, fh, indent=1)
        fh.write("\n")
    return names


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "freeze":
            out = flag(argv, "--out")
            if len(argv) < 2 or not os.path.isdir(argv[1]) or not out:
                return emit("fail", "contact freeze: <built clips folder> --out <anims>/blocks/" + BEFORE, "python kit/anim/contact.py")
            names = freeze(argv[1], out)
            return emit("pass", f"contact freeze: {len(names)} clip(s) made before the rule -> {out}",
                        "none - commit the list with the gate", clips=names)
        with open(argv[0], encoding="utf-8") as fh:
            clip = json.load(fh)
        r = read(clip, flag(argv, "--by"))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"contact: {e}", "fix what is named")
    wrong = off(r, True)
    return emit("fail" if wrong else "pass", words(r, str(clip.get("name"))),
                "author the Hit where the strike lands, or name the target (\"target\")" if wrong else "none", reading=r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
