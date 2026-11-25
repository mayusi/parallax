"""blocking.py — BLOCKING THE OWNER APPROVES FROM A PICTURE (the animation studio route's A2, board/plans/
2026-11-11-anim-studio-route-plan.md; the owner's method lists 2026-11-13: pose-to-pose, stepped / blocking animation;
the audit: board/plans/archive/2026-11-13-anim-methods-audit.md). A studio blocks a move in STEPPED keys - its key poses held,
no in-betweens - and the director says yes or "pose 3: lower" before anybody animates between them. The kit had the
blocking only as WORK for the owner (kit anim block: open the .blend, move the rig, the kit reads it back); the cheap
version was missing: LOOK at the held poses at their real rhythm, say it in words, and have the words held against the
next picture.

    make <Name> --out <dir> (--clip <clip.json> | --from-move <move.json> | --dossier <move> [--gesture <gesture>])
         [--move <move.json>] [--at t,t,...] [--anims <dir>]
        -> <dir>/blocking.clip.json   the move's key poses HELD at the move's own timing (a stepped clip: each pose
                                      stays until the next one's frame; the blade, the events and the length kept)
           <dir>/blocking.move.json   the poses' times, so the sheet (kit/anim/pose_sheet.py) shows exactly these
           <dir>/blocking.json        every pose (its frame, how long it is held, its joints), the blocking's id, the
                                      owner's notes and whether each was answered, his yes and whether it still holds
    note <Name> <pose> "<the owner's words>" [--by owner] [--anims <dir>] --out <dir>
        his words on ONE pose, kept with the pose as he saw it. The next `make` finds that pose again by its authored
        key (so poses added or dropped before it do not move the note to another pose) and says ANSWERED when ITS OWN
        key was changed or retimed, OPEN while it is as it was - also when it only changed with its neighbours, when
        the source is a clip (no keys to tell a correction from a ripple), or when the pose is gone
    approve <Name> "<the owner's words>" --by owner --id <the blocking's id on the sheet he saw> [--anims <dir>] --out <dir>
        his yes to THAT blocking: the poses he saw are stored with it, so a later change to any of them (a key moved,
        retimed, added, dropped) makes the yes STALE and says which pose changed and by how much. Refused when the id
        is not the blocking made last, or the move changed since it was made (he must be shown what is on disk)
    state <Name> --out <dir> [--anims <dir>] [--need approved]
        where the blocking stands (waiting / notes open / answered / approved / stale); --need approved fails otherwise
    gif <dir>   the held poses played at their real timing from the player's camera (the sheet's own renders)
    kept <Name> --clip <the finished clip.json> [--anims <dir>] [--tol-deg 10] [--tol-studs 0.25] [--tol-tip 1.25]
         [--window 0.05]
        THE FINISHED CLIP HELD TO THE POSES HE APPROVED (the studio route's A4): every approved pose is looked for in
        the clip AT ITS OWN MOMENT (his yes was to the rhythm too: a retimed or slowed clip is no longer it), `window`
        seconds either side for a limb's drag, between frames as well (a stepped build is read on its smooth motion,
        a 30-a-second clip between its samples). A pose the clip never comes within the tolerance of - a limb's
        turn or slide, the blade's direction, its tip - is named with what is off and how far. No approved blocking
        = nothing to hold it to (passes, and says so); a yes given to a procedural GESTURE's neutral blocking is not
        held as a gate (a pick's efforts re-pose the gesture by design): the differences are said, the build passes

    lock <Name>=move=<its .move.json> | <Name>=blade=<move dossier>[=<gesture>] ... [--anims <dir>]
        THE LOCK (the owner, 2026-11-13: every method "enforced in the terms of being used"; the studio route's A2):
        POSES FIRST, MOTION AFTER. A move made AFTER the rule, on a route whose key poses can be shown before any
        motion exists - a strike move's keys, a dossier built on a strike move file, a procedural sword move's
        gesture, a kick or unarmed strike keyed in its dossier - is not made, at ANY build, unless the owner's yes
        stands for its key poses AS THEY ARE NOW.
        Made before the rule = named in <anims>/blocks/_before_blocking.json (frozen once, `freeze`): never asked.
        His yes counts only when the record says it was his, holds the poses he saw and its id is those poses' id
        (a record typed by hand without them is no yes). A hit reaction (simulated from an impulse: no key poses)
        and a sword dossier that names no gesture are free, and the lock says so.
    lock <Name>=pose=<its .pose.json>: a HAND-POSED file (2026-11-14). Its poses come out of the rig's own solver, so
        they are shown from a clip the rig posed (`kit anim block <Name> --sheet` does it, into the blocking's folder);
        his yes is to the sheet made from the file AS IT WAS: any change to the file since makes it stale. Made
        before that rule = named in <anims>/blocks/_before_blocking_posed.json (`freeze --posed`).
    freeze [--anims <dir>]
        write <anims>/blocks/_before_blocking.json: every strike move and dossier pick the folder holds today (once:
        refused when the list exists - it is never extended)

The owner's words and his yes live in <anims>/blocks/<Name>.blocking.json (tracked); everything else is in build/.
What a pose IS: the six R6 joints (rotation + slide) and the blade's grip and tip at its frame. Two poses differ when
any joint turned ANGLE_TOL degrees or slid SLIDE_TOL studs, or the tip moved TIP_TOL studs - under that a rebuild's
rounding is not a change."""
import datetime
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ANGLE_TOL = 1.0     # degrees a joint must turn for a pose to count as changed
SLIDE_TOL = 0.02    # studs a joint must slide
TIP_TOL = 0.05      # studs the blade's tip must move
JOINTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")
# fields of an authored key that say nothing about its pose: editing one is no correction of the pose
WORDY = ("note", "notes", "name", "comment", "why", "label", "source")
GIF_WIDTH = 720
GIF_PAUSE_MS = 700  # the last frame stays this much longer before the loop starts again
# a finished clip KEEPS an approved pose when, near that pose's moment, every joint is within these of it. Measured on
# the kit's fixtures 2026-11-13: a move rebuilt from unchanged keys is 0.0 deg from its blocking; turning ONE key of
# the loved kesa 15 deg puts the clip 16.6 deg from the approved pose 3 (and 4.2 / 8.7 from poses 4 / 5, carried along)
KEPT_DEG = 10.0         # a joint's turn, and the blade's direction
KEPT_STUDS = 0.25       # a joint's slide
KEPT_TIP = 1.25         # the blade's tip: what a body and an arm inside the two bars above can carry it (0.25 studs + a
#                         5.6-stud arm-and-blade turned 10 deg); a blade moved in the hand goes past it
KEPT_WINDOW_S = 0.05
KEPT_SUB = 4            # looked for between frames too: this many steps a frame


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def fps_of(clip):
    return float(clip.get("fps") or round(1.0 / (clip["times"][1] - clip["times"][0])))


# ---------------------------------------------------------------- the poses
def key_frames(clip, move=None, at=None):
    """the frames that are the move's key poses, in order: the times named (`at`), else the move's own keys (a move
    keyed densely for its solver names its poses in `block_keys`), else what the sheet looks at (the clip's marks and
    the moments it nearly stops). Two moments within two frames are one pose; the first frame is always a pose (the
    blocking holds something from 0 s on)"""
    import pose_sheet as PS
    import thumbs as T
    if at:
        ts = T.key_times(clip, {"keys": [{"t": float(t)} for t in at]}, limit=10 ** 6)
    elif (move or {}).get("block_keys"):
        ts = T.key_times(clip, {"keys": [{"t": float(t)} for t in move["block_keys"]]}, limit=10 ** 6)
    elif any(isinstance(k, dict) and "t" in k for k in (move or {}).get("keys", [])):
        ts = T.key_times(clip, move, limit=10 ** 6)          # EVERY authored key (a sheet thins to ten; a blocking never)
    else:
        ts = PS.key_moments(clip, move)
    frames = sorted({PS.frame_of(clip, t) for t in ts})
    if not frames or frames[0] != 0:
        frames = [0] + frames
    out = []
    for f in frames:
        if not out or f - out[-1] >= 2:
            out.append(f)
    return out


def _canon(q):
    """a quaternion and its negative are one rotation: w >= 0 (then the first non-zero part positive)"""
    q = [float(x) for x in q]
    for x in (q[3], q[0], q[1], q[2]):
        if abs(x) > 1e-9:
            return q if x > 0 else [-v for v in q]
    return q


def snapshot(clip, frame):
    """ONE pose of a clip as plain numbers: each joint's [qx, qy, qz, qw, px, py, pz] and the blade's grip and tip"""
    joints = {}
    for j in JOINTS:
        if j in clip.get("joints", {}):
            row = clip["joints"][j]["frames"][frame]
            joints[j] = [round(v, 5) for v in _canon(row[:4]) + [float(x) for x in row[4:7]]]
    sw = clip.get("sword") or {}
    blade = None
    if sw.get("tip") and sw.get("grip_path"):
        blade = {"grip": [round(float(v), 4) for v in sw["grip_path"][frame]],
                 "tip": [round(float(v), 4) for v in sw["tip"][frame]]}
    return {"frame": int(frame), "t": round(float(clip["times"][frame]), 4), "joints": joints, "blade": blade}


def pose_id(snap):
    """a short name for a pose's SHAPE (its timing is not in it): the same numbers give the same id"""
    body = json.dumps([snap["joints"].get(j) for j in JOINTS] + [snap.get("blade")], separators=(",", ":"))
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:10]


def pose_delta(a, b):
    """how far pose b is from pose a: the joint that TURNED most (degrees), the joint that SLID most (studs), the
    blade tip's move (studs; None when either pose has no blade)"""
    deg, studs, dj, sj = 0.0, 0.0, None, None
    for j in JOINTS:
        qa, qb = a["joints"].get(j), b["joints"].get(j)
        if qa is None or qb is None:
            if qa is not qb:                                   # a joint one pose has and the other lacks: all of it
                deg, dj = 180.0, j
            continue
        d = abs(float(np.dot(qa[:4], qb[:4]))) / (np.linalg.norm(qa[:4]) * np.linalg.norm(qb[:4]) + 1e-12)
        ang = math.degrees(2.0 * math.acos(min(1.0, d)))
        if ang > deg:
            deg, dj = ang, j
        sl = float(np.linalg.norm(np.asarray(qa[4:7]) - np.asarray(qb[4:7])))
        if sl > studs:
            studs, sj = sl, j
    tip, blade_deg = None, None
    if a.get("blade") and b.get("blade"):
        tip = float(np.linalg.norm(np.asarray(a["blade"]["tip"]) - np.asarray(b["blade"]["tip"])))
        da = np.asarray(a["blade"]["tip"], float) - np.asarray(a["blade"]["grip"], float)
        db = np.asarray(b["blade"]["tip"], float) - np.asarray(b["blade"]["grip"], float)
        na, nb = float(np.linalg.norm(da)), float(np.linalg.norm(db))
        if na > 1e-9 and nb > 1e-9:                            # (an R6 arm cannot show a blade turned in the fist)
            blade_deg = math.degrees(math.acos(max(-1.0, min(1.0, float(da @ db) / (na * nb)))))
    elif bool(a.get("blade")) != bool(b.get("blade")):
        tip = float("inf")
    return {"deg": round(deg, 2), "joint": dj if deg > 1e-6 else None, "studs": round(studs, 3),
            "slide_joint": sj if studs > 1e-9 else None,
            "tip": None if tip is None else (tip if tip == float("inf") else round(tip, 3)),
            "blade_deg": None if blade_deg is None else round(blade_deg, 2)}


def changed(delta):
    return (delta["deg"] >= ANGLE_TOL or delta["studs"] >= SLIDE_TOL
            or (delta["tip"] is not None and delta["tip"] >= TIP_TOL))


def delta_words(delta):
    """a pose's change in plain words: 'Right Arm turned 14.2 deg, Torso slid 0.31 studs, the blade tip moved 0.80'"""
    bits = []
    if delta["deg"] >= ANGLE_TOL:
        bits.append(f"{delta['joint']} turned {delta['deg']:.1f} deg")
    if delta["studs"] >= SLIDE_TOL:
        bits.append(f"{delta['slide_joint']} slid {delta['studs']:.2f} studs")
    if delta["tip"] is not None and delta["tip"] >= TIP_TOL:
        bits.append("the blade came or went" if delta["tip"] == float("inf") else f"the blade tip moved {delta['tip']:.2f} studs")
    return ", ".join(bits) or "unchanged"


def key_ids(clip, authored):
    """frame -> a short id of the AUTHORED key that makes the pose at that frame (a strike move's key, a gesture's
    beat: the numbers a person typed; its time and its words - WORDY - are not in the id). A generator spreads one
    key's change into its neighbours' poses (overlap, drag: the loved kesa's pose 5 turns 8.7 degrees when pose 3's
    key is turned 15) - the key's id says whether a pose was CORRECTED or only carried along, and finds a pose again
    after keys were added or dropped before it"""
    import pose_sheet as PS
    out = {}
    for k in authored or []:
        if isinstance(k, dict) and "t" in k:
            body = json.dumps({a: b for a, b in k.items() if a != "t" and a not in WORDY and not str(a).startswith(("_", "why_"))},
                              sort_keys=True, separators=(",", ":"), default=str)
            out[PS.frame_of(clip, k["t"])] = hashlib.sha1(body.encode("utf-8")).hexdigest()[:10]
    return out


def poses_of(clip, frames, authored=None):
    """every key pose: its number (1-based, as the sheet numbers it), frame, time, how long it is HELD, its shape, and
    (`authored`: the move's keys / the gesture's beats) the id of the authored key behind it"""
    end = float(clip["times"][-1])
    step = 1.0 / fps_of(clip)
    keyed = key_ids(clip, authored)
    out = []
    for i, f in enumerate(frames):
        s = snapshot(clip, f)
        nxt = float(clip["times"][frames[i + 1]]) if i + 1 < len(frames) else end + step
        out.append({"k": i + 1, **s, "hold_s": round(nxt - s["t"], 4), "id": pose_id(s), "key": keyed.get(int(f))})
    return out


def blocking_id(poses):
    """the blocking's id: every pose's shape AND its frame (a retimed blocking is another blocking)"""
    body = json.dumps([[p["frame"], p["id"]] for p in poses], separators=(",", ":"))
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]


def held(clip, frames, name):
    """the STEPPED clip: every frame shows the latest key pose at or before it (constant interpolation, as a blocking
    pass is keyed); the blade is held with its pose; the length, the events and the beats stay the move's own"""
    n = len(clip["times"])
    src = np.zeros(n, int)
    for f in frames:
        src[f:] = f
    out = {k: v for k, v in clip.items() if k not in ("joints", "sword", "source", "name")}
    out["name"] = f"{name}Blocking"
    out["loop"] = False
    out["joints"] = {j: {"frames": [list(tr["frames"][src[i]]) for i in range(n)]} for j, tr in clip["joints"].items()}
    sw = clip.get("sword")
    if sw:
        # (a per-frame track may be a frame short - an edge measured between frames: held on its last entry then)
        out["sword"] = {k: ([v[min(src[i], len(v) - 1)] for i in range(n)]
                            if isinstance(v, list) and n - 1 <= len(v) <= n and v and isinstance(v[0], (list, tuple)) else v)
                        for k, v in sw.items()}
    out["source"] = {"kind": "blocking", "of": name, "frames": [int(f) for f in frames]}
    return out


# ---------------------------------------------------------------- the record (the owner's words and his yes)
def record_path(anims, name):
    return os.path.join(anims, "blocks", f"{name}.blocking.json")


def load_record(anims, name):
    path = record_path(anims, name)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except ValueError as e:
                raise ValueError(f"the blocking record {path.replace(os.sep, '/')} is not valid JSON ({e}) - it holds the "
                                 "owner's words: repair it by hand, never delete it") from e
    return {"schema": 1, "move": name, "notes": [], "approved": None, "history": []}


def save_record(anims, name, rec):
    path = record_path(anims, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1)
        fh.write("\n")
    return path


def _slim(p):
    return {k: p[k] for k in ("k", "frame", "t", "hold_s", "id", "key", "joints", "blade") if k in p}


def pose_change(then, now):
    """what changed in ONE pose between two blockings, in words ('' = nothing): its shape and its timing"""
    bits = []
    d = pose_delta(then, now)
    if changed(d):
        bits.append(delta_words(d))
    if then["frame"] != now["frame"]:
        bits.append(f"moved from {then['t']:.2f} s to {now['t']:.2f} s")
    if abs(float(then.get("hold_s", 0.0)) - float(now.get("hold_s", 0.0))) > 1e-6 and then["frame"] == now["frame"]:
        bits.append(f"held {now['hold_s']:.2f} s (it was {then['hold_s']:.2f} s)")
    return "; ".join(bits)


def locate(seen, poses):
    """the pose a note was given on, among the poses as they are NOW -> (pose or None, how). By its authored key first
    ("key": the same key is the same pose wherever it was renumbered or retimed to - of several alike, the nearest in
    time); a key that was edited is no longer found, so then by its moment ("moment": the pose at the frame he saw it
    at); neither = "gone" (dropped, or edited and moved)"""
    if seen.get("key"):
        same = [p for p in poses if p.get("key") == seen["key"]]
        if same:
            return min(same, key=lambda p: abs(int(p["frame"]) - int(seen["frame"]))), "key"
    for p in poses:
        if int(p["frame"]) == int(seen["frame"]):
            return p, "moment"
    return None, "gone"


def settle(rec, poses, today=None):
    """every OPEN note against the poses as they are now -> True when a note changed. A note is ANSWERED only when
    the pose he said it on was itself corrected: its own authored key edited (and the pose with it), or that key
    retimed. It stays OPEN - and says what it saw - when the pose only changed with its neighbours or its hold
    (`carried`), when the source has no keys to tell the two apart (`unsure`: a clip), and when the pose is no longer
    in the blocking (`gone`). A note's pose NUMBER follows the pose (`pose_said` keeps the number he used)"""
    today = today or datetime.date.today().isoformat()
    moved = False
    for n in rec.get("notes", []):
        if n.get("state") != "open":
            continue
        before = json.dumps([n.get(k) for k in ("pose", "gone", "carried", "unsure")])
        seen = n["seen"]
        now, how = locate(seen, poses)
        if now is None:
            n["gone"], n["carried"], n["unsure"] = True, None, None
        else:
            n["gone"], n["pose"] = None, int(now["k"])
            what = pose_change(seen, now)
            retimed = how == "key" and int(now["frame"]) != int(seen["frame"])
            rekeyed = how == "moment" and bool(seen.get("key")) and bool(now.get("key"))
            if what and (retimed or rekeyed):
                n["state"] = "answered"
                n["answered"] = {"date": today, "changed": what, "id": now["id"]}
                n["carried"] = n["unsure"] = None
            elif what and how == "key":
                n["carried"], n["unsure"] = what, None        # its own key is as he saw it: carried along, or its hold
            elif what:
                n["carried"], n["unsure"] = None, what        # no keys on one side: a correction or a ripple, unknown
            else:
                n["carried"] = n["unsure"] = None
        if n["state"] != "open" or json.dumps([n.get(k) for k in ("pose", "gone", "carried", "unsure")]) != before:
            moved = True
    return moved


def note_why(n):
    """why an open note is open, in the reader's words"""
    if n.get("gone"):
        return (f"the pose he said it on is no longer in the blocking (it was pose {n.get('pose_said', n.get('pose'))} at "
                f"{float(n['seen']['t']):.2f} s: dropped, or re-keyed and moved)")
    if n.get("carried"):
        return f"that pose only changed with its neighbours ({n['carried']}); its own key is as he saw it"
    if n.get("unsure"):
        return f"that pose changed ({n['unsure']}), but a clip has no keys to tell a correction from a pose carried along"
    return "that pose is as he saw it"


def note_words(n):
    """one note as the sheet prints it: his words, and where they stand"""
    who, said = f"THE OWNER, {n.get('date')}", f"\"{n.get('words')}\""
    if n.get("state") == "answered":
        a = n.get("answered") or {}
        return f"{who}: {said} - ANSWERED {a.get('date')}: {a.get('changed')}"
    if n.get("state") == "closed":
        return f"{who}: {said} - closed by his yes"
    return f"{who} - NOT ANSWERED ({note_why(n)}; only a change to this pose's own key, or his yes, answers it): {said}"


def approval_drift(rec, poses):
    """his yes against the poses as they are now -> [words] of every difference (none = the yes still holds)"""
    ap = rec.get("approved")
    if not ap:
        return []
    then = ap.get("poses") or []
    out = []
    if len(then) != len(poses):
        out.append(f"he approved {len(then)} pose(s), there are {len(poses)} now")
    for a, b in zip(then, poses):
        what = pose_change(a, b)
        if what:
            out.append(f"pose {b['k']}: {what}")
    return out


def state_of(rec, poses):
    """-> {state, words, open: [notes], drift: [words]}. waiting = shown, nothing said yet; notes open = his words not
    yet answered by a changed pose; answered = every note answered, his yes not given; approved; stale = approved,
    then a pose changed"""
    open_notes = [n for n in rec.get("notes", []) if n.get("state") == "open"]
    ap = rec.get("approved")
    if ap:
        drift = approval_drift(rec, poses)
        if drift:
            return {"state": "stale", "open": open_notes, "drift": drift,
                    "words": f"the owner's yes ({ap['date']}: \"{ap['words']}\") was to another blocking - " + "; ".join(drift[:3])
                             + (f" (+{len(drift) - 3} more)" if len(drift) > 3 else "")}
        return {"state": "approved", "open": open_notes, "drift": [],
                "words": f"approved by the owner {ap['date']}: \"{ap['words']}\" (blocking {ap['id']})"}
    if open_notes:
        first = open_notes[0]
        where = "a pose that is gone" if first.get("gone") else f"pose {first['pose']}"
        return {"state": "notes open", "open": open_notes, "drift": [],
                "words": f"{len(open_notes)} of the owner's note(s) not answered - {where}: \"{first['words']}\" "
                         f"({first['date']}): {note_why(first)}"}
    if rec.get("notes"):
        return {"state": "answered", "open": [], "drift": [],
                "words": f"every one of the owner's {len(rec['notes'])} note(s) is answered by a changed pose; his yes is not given yet"}
    return {"state": "waiting", "open": [], "drift": [], "words": "the owner has not seen or answered this blocking yet"}


def add_note(rec, k, words, poses, by="owner", today=None):
    """his words on pose k, with the pose as it is now. A note after his yes reopens the blocking (the yes moves to
    the history: it was to poses he has now corrected)"""
    if not (1 <= k <= len(poses)):
        raise ValueError(f"there is no pose {k} (the blocking has {len(poses)})")
    if not str(words).strip():
        raise ValueError("a note needs the owner's words")
    today = today or datetime.date.today().isoformat()
    if rec.get("approved"):
        rec.setdefault("history", []).append({**rec["approved"], "ended": today, "why": f"a note on pose {k}"})
        rec["approved"] = None
    rec.setdefault("notes", []).append({"pose": int(k), "pose_said": int(k), "t": poses[k - 1]["t"],
                                        "words": str(words).strip(), "by": by, "date": today,
                                        "seen": _slim(poses[k - 1]), "state": "open"})
    return rec


def approve(rec, words, poses, by, today=None, timing=None, source=None, made_from_sha256=None, pose_sha256=None):
    """his yes to the blocking as it is now (only the owner's: a proposal is no approval). Notes still open are closed
    by it - he saw those poses again and said yes"""
    if by != "owner":
        raise ValueError("only the owner approves a blocking: --by owner, with his own words")
    if not str(words).strip():
        raise ValueError("an approval needs the owner's words")
    today = today or datetime.date.today().isoformat()
    if rec.get("approved"):
        rec.setdefault("history", []).append({**rec["approved"], "ended": today, "why": "approved again"})
    for n in rec.get("notes", []):
        if n.get("state") == "open":
            n["state"] = "closed"
            n["closed"] = {"date": today, "why": "the owner approved the blocking with this pose as it was"}
    rec["approved"] = {"words": str(words).strip(), "by": by, "date": today, "id": blocking_id(poses),
                       "timing": timing or None, "source": source, "poses": [_slim(p) for p in poses],
                       **({"made_from_sha256": made_from_sha256} if made_from_sha256 else {}),
                       **({"pose_sha256": pose_sha256} if pose_sha256 else {})}
    return rec


# ---------------------------------------------------------------- the finished clip held to the approved poses
def hit_of(clip):
    """the clip's first Hit, in seconds (None = it has none)"""
    import clip as C
    for e in clip.get("events") or []:
        if "t" in e and str(e.get("name", "")).lower() in C.HIT_NAMES:
            return float(e["t"])
    return None


def pose_at(clip, x):
    """the clip's pose at a moment BETWEEN two frames (x in frames): joints turned and slid part of the way (slerp /
    lerp), the blade's grip and tip with them - a key that falls between a 30-a-second clip's samples is still found"""
    import clip as C
    n = len(clip["times"])
    i = int(min(n - 1, max(0, math.floor(x))))
    w = float(x) - i
    if w < 1e-6 or i >= n - 1:
        return snapshot(clip, i)
    a, b = snapshot(clip, i), snapshot(clip, i + 1)
    out = {"frame": i, "t": float(clip["times"][i]) * (1 - w) + float(clip["times"][i + 1]) * w, "joints": {}, "blade": None}
    for j, qa in a["joints"].items():
        qb = b["joints"].get(j)
        if qb is None:
            continue
        out["joints"][j] = [float(v) for v in C.slerp(qa[:4], qb[:4], w)] + [qa[k] * (1 - w) + qb[k] * w for k in range(4, 7)]
    if a.get("blade") and b.get("blade"):
        out["blade"] = {k: [a["blade"][k][c] * (1 - w) + b["blade"][k][c] * w for c in range(3)] for k in ("grip", "tip")}
    return out


def kept(clip, rec, tol_deg=KEPT_DEG, tol_studs=KEPT_STUDS, window_s=KEPT_WINDOW_S, tol_tip=KEPT_TIP):
    """a finished clip against the poses the owner approved -> {state, rows, lost, length}. state: none (no approved
    blocking: nothing to hold it to) / kept / drifted. A row per approved pose: the moment of the clip that comes
    nearest it within `window_s` of ITS OWN moment, and how far that is - the limb that turned most, the one that
    slid most, the blade's direction and its tip. `length`: the clip's and the approved blocking's, when they differ
    (his yes was to the rhythm: a clip retimed or stretched is no longer the blocking he approved)"""
    if min(tol_deg, tol_studs, tol_tip) <= 0 or window_s < 0:
        raise ValueError("a tolerance is a positive number (and the window is not negative)")
    ap = rec.get("approved")
    if not ap or not ap.get("poses"):
        return {"state": "none", "rows": [], "lost": [], "length": None}
    import clip as C
    import grip as GR
    # THE BLADE THAT PLAYS (the owner's V3 list, anim stage B.2): the game keys the weapon by the clip's grip track,
    # not by its designed sword paths - both are held to his poses, the worse of the two counts (a pass that edited
    # only the grip track was not seen). Read before the destep, then destepped the same way as the clip
    sw_play = GR.played_sword(clip) if clip.get("sword") else None
    played = C.destep({**clip, "sword": {**clip["sword"], **sw_play}}) if sw_play else None
    clip = C.destep(clip)                                  # (a stepped build: its smooth motion - steps are presentation)
    fps = fps_of(clip)
    n = len(clip["times"])
    end = float(clip["times"][-1])
    rows, lost = [], []
    for p in ap["poses"]:
        t = float(p["t"])
        row = {"pose": p["k"], "approved_t": p["t"]}
        if t > end + window_s + 1e-9:                      # the clip is over before this pose
            row.update(nearest_t=None, deg=None, joint=None, studs=None, slide_joint=None, tip=None, blade_deg=None,
                       blade_gone=False, past_end=round(end, 4), kept=False)
            rows.append(row)
            lost.append(row)
            continue
        x0 = t * fps                                       # its own moment, in this clip's frames: ON a frame when it
        if abs(x0 - round(x0)) < 0.02:                     # is one (a stored time is rounded to 0.1 ms), so an unchanged
            x0 = float(round(x0))                          # clip is found exactly, not a hair beside itself
        reach = int(math.floor(window_s * fps * KEPT_SUB + 1e-9))
        xs = sorted({min(float(n - 1), max(0.0, x0 + k / KEPT_SUB)) for k in range(-reach, reach + 1)})
        best = None
        for x in xs:
            d = pose_delta(p, pose_at(clip, x))
            if played is not None:                         # (the blade the game plays: the worse reading counts)
                dp = pose_delta(p, pose_at(played, x))
                if (dp["blade_deg"] or 0.0) > (d["blade_deg"] or 0.0):
                    d["blade_deg"], d["played"] = dp["blade_deg"], True
                if dp["tip"] is not None and (d["tip"] is None or (dp["tip"] > d["tip"] and d["tip"] != float("inf"))):
                    d["tip"], d["played"] = dp["tip"], True
            gone = d["tip"] == float("inf")
            score = max(d["deg"] / tol_deg, d["studs"] / tol_studs, (d["blade_deg"] or 0.0) / tol_deg,
                        0.0 if (d["tip"] is None or gone) else d["tip"] / tol_tip)
            if best is None or score < best[0] - 1e-12:
                best = (score, x, d)
        _, x, d = best
        gone = d["tip"] == float("inf")
        ok = (d["deg"] <= tol_deg and d["studs"] <= tol_studs and not gone
              and (d["blade_deg"] is None or d["blade_deg"] <= tol_deg) and (d["tip"] is None or gone or d["tip"] <= tol_tip))
        row.update(nearest_t=round(x / fps, 4), deg=d["deg"], joint=d["joint"], studs=d["studs"], slide_joint=d["slide_joint"],
                   tip=None if (d["tip"] is None or gone) else d["tip"], blade_deg=d["blade_deg"], blade_gone=gone,
                   past_end=None, kept=ok, played=bool(d.get("played")))
        rows.append(row)
        if not ok:
            lost.append(row)
    dur = (ap.get("timing") or {}).get("duration")
    length = None
    if dur is not None and abs(end - float(dur)) > window_s + 1.0 / fps:
        length = {"clip_s": round(end, 4), "approved_s": round(float(dur), 4)}
    return {"state": "drifted" if (lost or length) else "kept", "rows": rows, "lost": lost, "length": length,
            "id": ap.get("id"), "source": ap.get("source"), "tol_deg": tol_deg, "tol_studs": tol_studs, "tol_tip": tol_tip,
            "window_s": window_s}


def lost_bits(row, tol_deg=KEPT_DEG, tol_studs=KEPT_STUDS, tol_tip=KEPT_TIP):
    """what is off in one drifted pose -> [(what moved, the words)], the worst first as the reader should fix it"""
    if row.get("past_end") is not None:
        return [("the clip's length", f"the clip ends at {row['past_end']:.2f} s, before this pose")]
    bits = []
    if row["deg"] > tol_deg:
        bits.append((row["joint"], f"{row['joint']} is {row['deg']:.1f} deg from the pose he approved ({tol_deg:g} allowed)"))
    if row["studs"] > tol_studs:
        bits.append((row["slide_joint"], f"{row['slide_joint']} sits {row['studs']:.2f} studs off ({tol_studs:g} allowed)"))
    if row.get("blade_gone"):
        bits.append(("the blade", "the blade is there in one and not in the other"))
    else:
        how = " as the game plays it (its grip track)" if row.get("played") else ""
        if row.get("blade_deg") is not None and row["blade_deg"] > tol_deg:
            bits.append(("the blade", f"the blade points {row['blade_deg']:.1f} deg off{how} ({tol_deg:g} allowed)"))
        if row.get("tip") is not None and row["tip"] > tol_tip:
            bits.append(("the blade", f"the blade's tip is {row['tip']:.2f} studs away{how} ({tol_tip:g} allowed)"))
    return bits


def lost_words(row, tol_deg=KEPT_DEG, tol_studs=KEPT_STUDS, tol_tip=KEPT_TIP):
    """one drifted pose in plain words: which pose, what is off, how far, against what is allowed"""
    where = (f"approved at {row['approved_t']:.2f} s" if row.get("nearest_t") is None
             else f"approved at {row['approved_t']:.2f} s, nearest in the clip at {row['nearest_t']:.2f} s")
    return f"pose {row['pose']} ({where}): " + ", ".join(w for _, w in lost_bits(row, tol_deg, tol_studs, tol_tip))


# ---------------------------------------------------------------- where a move's poses come from
def posed_keys(pose_path, fps):
    """a hand-posed file's keys (kit/anim/pose_r6.py: "f" frames at its fps, or "t" seconds) -> its keys with "t" """
    with open(pose_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    if not isinstance(spec, dict) or not isinstance(spec.get("keys"), list) or not spec["keys"]:
        raise ValueError(f"{pose_path} has no keyed poses")
    rate = float(spec.get("fps") or fps)
    keys = []
    for k in spec["keys"]:
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)      # noqa: E731
        if not isinstance(k, dict) or not (num(k.get("f")) or num(k.get("t"))):
            raise ValueError(f"{pose_path}: a key has no frame (f) or time (t)")
        t = float(k["f"]) / rate if num(k.get("f")) else float(k["t"])      # (as kit/anim/pose_r6.py reads it: f first)
        keys.append({**{x: v for x, v in k.items() if x != "f"}, "t": round(t, 6)})
    return sorted(keys, key=lambda k: k["t"])


def pose_hash(pose_path):
    """a posed file's CONTENT (its JSON, keys sorted): the same on every checkout (git may rewrite line endings) -> sha256
    or None when it cannot be read"""
    try:
        with open(pose_path, encoding="utf-8") as fh:
            body = json.dumps(json.load(fh), sort_keys=True, ensure_ascii=False)
    except (OSError, ValueError):
        return None
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def source_clip(name, clip_path=None, from_move=None, dossier=None, gesture=None, pose=None):
    """-> (clip, move or None, the files it was made from). A built clip; a strike move generated here (no build, so
    no clock starts on the piece); or a move dossier's own build at neutral efforts, by its builder: a procedural
    weapon gesture (its beats = its poses), a kick or unarmed strike keyed in the dossier (build.keys = its poses),
    a dossier built on a strike move file (that file's keys). A hit reaction is simulated: it has no key poses"""
    if clip_path and pose:
        # a HAND-POSED file (<Name>.pose.json): the clip is what the owner's rig makes of its keys (posed by the rig's
        # own solver in Blender, into the blocking's folder - never the build's clip); the poses are the file's keys
        with open(clip_path, encoding="utf-8") as fh:
            clip = json.load(fh)
        src = clip.get("source") if isinstance(clip.get("source"), dict) else {}
        with open(pose, "rb") as fh:
            raw = hashlib.sha256(fh.read()).hexdigest()
        if src.get("kind") != "pose" or src.get("sha256") != raw:
            raise ValueError(f"{clip_path} is not what the owner's rig posed from {pose} as it is now (pose it again: "
                             f"lune run kit anim block {name} --sheet)")
        keys = posed_keys(pose, fps_of(clip))
        return clip, {"keys": keys, "block_keys": [k["t"] for k in keys]}, [pose]
    if clip_path:
        with open(clip_path, encoding="utf-8") as fh:
            return json.load(fh), None, [clip_path]
    if from_move:
        import strike as S
        with open(from_move, encoding="utf-8") as fh:
            move = json.load(fh)
        gen = dict(move)
        gen.pop("step", None)                                # (stepping is presentation: the blocking holds the poses itself)
        clip, _ = S.generate(gen)
        return clip, move, [from_move]
    if dossier:
        import proc_blade as PB
        import proc_dossier as DS
        try:
            d = DS.require(dossier)
        except SystemExit as e:                              # (the dossier loader refuses by exiting: said as a refusal here)
            raise ValueError(str(e)) from e
        builder = d["build"].get("builder", "proc_kick")
        if not gesture and builder in STRIKE_BUILDERS and isinstance(d["build"].get("move_file"), str):
            return source_clip(name, None, d["build"]["move_file"], None)      # its key poses are its move file's
        if not gesture and builder == "proc_react":
            raise ValueError(f"the dossier {dossier} makes a hit reaction: it is simulated from an impulse and has no key "
                             "poses to block")
        if not gesture and builder not in BLADE_BUILDERS:
            # a kick or an unarmed strike keyed in the dossier (kit/anim/proc_kick.py): its keys ARE its poses
            import proc_kick as PK
            if not isinstance(d["build"].get("keys"), list) or len(d["build"]["keys"]) < 2:
                raise ValueError(f"the dossier {dossier} has no keyed poses (build.keys)")
            keys = PK.carry(d["build"]["keys"])
            clip, _ = PK.build(d, keys=keys, name=name)
            return (clip, {"keys": keys, "block_keys": [float(k["t"]) for k in keys], "dossier": dossier},
                    [os.path.join(DS.DIR, f"{dossier}.json")])
        if gesture:
            # the dossier's move on the procedural weapon route from a craft gesture, as `kit anim candidates <Name>
            # --blade <gesture>` makes it (kit/anim/proc_candidates.py make): that gesture for every clip, its sword
            mf = d["build"].get("move_file")
            sw = d["build"].get("sword")
            if not sw and mf and os.path.isfile(mf):
                with open(mf, encoding="utf-8") as fh:
                    sw = json.load(fh).get("sword")
            d = {**d, "build": {**d["build"], "gestures": {"*": gesture}, "sword": sw or {}}}
        try:
            g = PB.gesture_for(d, name)
        except SystemExit as e:
            raise ValueError(str(e)) from e
        except OSError as e:
            raise ValueError(f"no gesture file for {name} ({e})") from e
        clip, _ = PB.build(d, {}, name)
        beats, _, _, _ = PB.effort(g, {"time": 0.0, "weight": 0.0, "space": 0.0, "flow": 0.0}, None)
        files = [os.path.join(DS.DIR, f"{dossier}.json"),
                 os.path.join(PB.GESTURES, f"{g.get('name')}.json")]
        return (clip, {"block_keys": [float(b["t"]) for b in beats], "beats": beats, "dossier": dossier},
                [p for p in files if os.path.isfile(p)])
    raise ValueError("name the poses' source: --clip <clip.json>, --from-move <move.json> or --dossier <move>")


def sources_hash(paths):
    """one sha256 over the files a blocking was made from (None = one of them is gone): a blocking on disk is the
    move AS IT IS only while this still matches - his note and his yes are taken on nothing older"""
    h = hashlib.sha256()
    for p in paths:
        if not os.path.isfile(p):
            return None
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def out_of_date(m):
    """-> why the blocking on disk is no longer the move as it is ('' = it is)"""
    made = m.get("made_from") or []
    now = sources_hash(made)
    if now is None:
        return "a file it was made from is gone (" + ", ".join(p for p in made if not os.path.isfile(p)) + ")"
    return "" if now == m.get("made_from_sha256") else "the move changed since it was made (" + ", ".join(made) + ")"


def poses_now(name, from_move=None, dossier=None, gesture=None):
    """the key poses of a move AS IT IS on disk, with no build and nothing written (the lock reads these)"""
    clip, move, _ = source_clip(name, None, from_move, dossier, gesture)
    frames = key_frames(clip, move, None)
    return poses_of(clip, frames, (move or {}).get("keys") or (move or {}).get("beats"))


BLADE_BUILDERS = ("fp_weapon", "proc_blade")    # (kit/anim/proc_candidates.py: the procedural weapon route)
STRIKE_BUILDERS = ("strike",)                   # (... a dossier built on a strike move file: build.move_file)
BEFORE = "_before_blocking.json"


def before_path(anims):
    return os.path.join(anims, "blocks", BEFORE)


def before_rule(anims):
    """the moves made BEFORE the rule (frozen 2026-11-13; a project that has no list has no such moves) -> {names}"""
    path = before_path(anims)
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        try:
            d = json.load(fh)
        except ValueError as e:
            raise ValueError(f"{path.replace(os.sep, '/')} is not valid JSON ({e}): repair it by hand, never delete it "
                             "(without it every move made before the rule is asked for a blocking)") from e
    moves = d.get("moves") if isinstance(d, dict) else None
    if not isinstance(moves, list):
        raise ValueError(f"{path.replace(os.sep, '/')} has no list of moves")
    return {m for m in moves if isinstance(m, str)}


POSED_BEFORE = "_before_blocking_posed.json"


def posed_before(anims):
    """the hand-posed files made before THEIR rule (2026-11-14; frozen once) -> {names}"""
    path = os.path.join(anims, "blocks", POSED_BEFORE)
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        try:
            d = json.load(fh)
        except ValueError as e:
            raise ValueError(f"{path.replace(os.sep, '/')} is not valid JSON ({e}): repair it by hand, never delete it") from e
    moves = d.get("moves") if isinstance(d, dict) else None
    if not isinstance(moves, list):
        raise ValueError(f"{path.replace(os.sep, '/')} has no list of moves")
    return {m for m in moves if isinstance(m, str)}


def freeze_posed(anims, today=None):
    path = os.path.join(anims, "blocks", POSED_BEFORE)
    if os.path.exists(path):
        raise ValueError(f"{path.replace(os.sep, '/')} exists: the list is frozen once and never extended")
    names = sorted({f[:-len(".pose.json")] for f in (os.listdir(anims) if os.path.isdir(anims) else [])
                    if f.endswith(".pose.json") and not f.startswith("_")})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"about": "The hand-posed files (<Name>.pose.json) made BEFORE the blocking lock reached them (kit/anim/"
                            "blocking.py lock, kind pose; 2026-11-14). They build as they always did. FROZEN: never add a "
                            "name here to get a move built.",
                   "frozen": today or datetime.date.today().isoformat(), "moves": names}, fh, indent=1)
        fh.write("\n")
    return path, names


def freeze(anims, today=None):
    """write the list of the moves made before the rule -> (path, [names]); refused when it exists"""
    path = before_path(anims)
    if os.path.exists(path):
        raise ValueError(f"{path.replace(os.sep, '/')} exists: the list is frozen once and never extended")
    names = sorted({f[:-len(ext)] for f in (os.listdir(anims) if os.path.isdir(anims) else [])
                    for ext in (".move.json", ".dossier.json") if f.endswith(ext) and not f.startswith("_")})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"about": "The strike moves and dossier picks made BEFORE the blocking lock (kit/anim/blocking.py lock; the "
                            "owner 2026-11-13: every method enforced in use). They build as they always did. FROZEN: a move "
                            "added after this list needs the owner's yes to its key poses before it is made - never add a "
                            "name here to get a move built.",
                   "frozen": today or datetime.date.today().isoformat(), "moves": names}, fh, indent=1)
        fh.write("\n")
    return path, names


def his_yes(ap):
    """a recorded approval counts only as the owner's own, with the poses he saw, under those poses' id -> why not
    ('' = it counts). A record typed by hand without them is no yes"""
    if not isinstance(ap, dict):
        return "no yes is recorded"
    if ap.get("by") != "owner":
        return "the recorded yes is not the owner's (--by owner, with his words)"
    poses = ap.get("poses")
    if not isinstance(poses, list) or not poses or any(not isinstance(p, dict) or "frame" not in p or "id" not in p for p in poses):
        return "the recorded yes holds no poses: it was not made by --approve on a sheet he saw"
    if ap.get("id") != blocking_id(poses):
        return "the recorded yes does not match the poses stored with it: it was edited by hand"
    return ""


def lock_one(name, kind, where, gesture, anims, before):
    """-> (held, words, how). held = this move may not be made; words say why, or why it is free; how = the
    (kind, where, gesture) its blocking is shown from"""
    how = (kind, where, gesture)
    if name in before.get("pose" if kind == "pose" else "move", ()):       # (each list excuses its own kind only)
        return False, (f"it was made before the rule (blocks/{POSED_BEFORE if kind == 'pose' else BEFORE}): never asked"), how
    dossier = None
    if kind == "blade":
        import proc_blade as PB
        import proc_dossier as DS
        dossier = where or DS.snake(name)
        how = (kind, dossier, gesture)
        try:
            d = DS.require(dossier)
        except SystemExit as e:
            return False, f"its move dossier cannot be read ({e}): the dossier gate says what it needs", how
        builder = d["build"].get("builder", "proc_kick")
        if not gesture and builder in STRIKE_BUILDERS and isinstance(d["build"].get("move_file"), str):
            kind, where, dossier = "move", d["build"]["move_file"], None       # its key poses are its move file's
            how = (kind, where, None)
        elif not gesture and builder == "proc_react":
            return False, "it is a hit reaction, simulated from an impulse: it has no key poses to show before its motion", how
        elif not gesture and builder not in BLADE_BUILDERS and not isinstance(d["build"].get("keys"), list):
            return False, f"its dossier ({builder}) holds no keyed poses: nothing to show before its motion", how
        elif not gesture:
            if builder in BLADE_BUILDERS:
                try:
                    PB.gesture_for(d, name)
                except (SystemExit, OSError):
                    return False, "its dossier names no sword gesture for it: nothing to show before its motion", how
    rec = load_record(anims, name)
    if not isinstance(rec, dict):
        raise ValueError("its blocking record is not a record")
    ap = rec.get("approved")
    if not ap:
        if rec.get("notes"):
            return True, state_of(rec, [])["words"], how
        return True, "the owner has not been shown its key poses, or has not said yes to them", how
    why = his_yes(ap)
    if why:
        return True, why, how
    if kind == "pose":
        # its poses come out of the rig's own solver (Blender): not re-posed here. His yes was to the sheet made
        # from THIS file: any change to the file since makes it stale (show him the sheet again)
        if ap.get("source") != "pose" or not ap.get("pose_sha256"):
            return True, "his yes was not given on a blocking of this posed file", how
        if pose_hash(where) != ap["pose_sha256"]:
            return True, (f"the owner's yes ({ap.get('date')}: \"{ap.get('words')}\") was to this posed file as it was; "
                          "the file changed since"), how
        keys = posed_keys(where, 60.0)
        with open(where, encoding="utf-8") as fh:
            rate = float(json.load(fh).get("fps") or 60)
        want = sorted({int(round(k["t"] * rate)) for k in keys} | {0})
        seen = sorted(int(p["frame"]) for p in ap["poses"])
        if any(min(abs(f - g) for g in seen) > 2 for f in want) or len(seen) > len(want):
            return True, "the poses stored with his yes are not this file's keys: the record was edited by hand", how
        return False, f"approved by the owner {ap.get('date')}: \"{ap.get('words')}\" (blocking {ap.get('id')})", how
    if kind == "blade" and ap.get("source") == "clip":
        # his yes on a pick's own poses holds the BUILD (kept); the yes before any motion is the gesture's, and it
        # stands when an earlier yes of his to the gesture as it is now was only superseded by this one
        ap = next((h for h in reversed(rec.get("history") or []) if isinstance(h, dict) and h.get("source") == "gesture"
                   and h.get("why") == "approved again" and not his_yes(h)), None)
        if ap is None:
            return True, ("his yes is to the poses of a clip of this move; the yes that comes before any motion is to "
                          "its gesture's key poses, and none is recorded"), how
    poses = poses_now(name, where if kind == "move" else None, dossier, gesture)
    st = state_of({**rec, "approved": ap}, poses)
    return st["state"] != "approved", st["words"], how


def lock(pairs, anims):
    """[(name, kind, where, gesture)] -> {"held": {name: words}, "free": {name: words}, "how": {name: [kind, where,
    gesture]}}"""
    out = {"held": {}, "free": {}, "how": {}}
    before = {"move": before_rule(anims), "pose": posed_before(anims)}
    for name, kind, where, gesture in pairs:
        how = (kind, where, gesture)
        try:
            held_, words, how = lock_one(name, kind, where, gesture, anims, before)
        except (OSError, ValueError, KeyError, IndexError, TypeError, StopIteration, AttributeError, SystemExit) as e:
            # a move whose poses cannot even be read is not a move anybody said yes to
            held_, words = True, f"its key poses could not be read ({type(e).__name__}: {e})"
        out["held" if held_ else "free"][name] = words
        out["how"][name] = list(how)
    return out


def how_to_block(name, kind, where, gesture):
    src = ("" if kind == "pose" else f"--move {where}" if kind == "move" else
           f"--proc {where or '<its move dossier>'}" + (f" --blade {gesture}" if gesture else ""))
    return (f"lune run kit anim block {name} --sheet {src}   -> show the owner {name}'s sheet and blocking.gif -> his words on "
            f"a pose: lune run kit anim block {name} --note <pose> \"<his words>\"; his yes: lune run kit anim block {name} "
            f"--approve \"<his words>\" --by owner --id <the id on the sheet he saw>")


def make(name, out, anims, clip_path=None, from_move=None, dossier=None, move_path=None, at=None, today=None,
         gesture=None, pose=None):
    """the blocking artefact of a move -> its manifest (blocking.json, written)"""
    if pose and move_path:
        raise ValueError("a posed file's blocking takes its keys from the file itself: no --move with --pose")
    clip, move, made_from = source_clip(name, clip_path, from_move, dossier, gesture, pose)
    if clip.get("rig") not in (None, "R6"):
        raise ValueError(f"{name} is a {clip.get('rig')} clip - a blocking is shown on the owner's R6 rig")
    if len(clip.get("times") or []) < 2:
        raise ValueError(f"{name}: the clip has no frames")
    if move_path and os.path.isfile(move_path):
        with open(move_path, encoding="utf-8") as fh:
            move = json.load(fh)
        made_from.append(move_path)
    frames = key_frames(clip, move, at)
    poses = poses_of(clip, frames, (move or {}).get("keys") or (move or {}).get("beats"))
    os.makedirs(out, exist_ok=True)
    hc = held(clip, frames, name)
    hc["rig"] = "R6"
    with open(os.path.join(out, "blocking.clip.json"), "w", encoding="utf-8") as fh:
        json.dump(hc, fh)
    with open(os.path.join(out, "blocking.move.json"), "w", encoding="utf-8") as fh:
        json.dump({"name": f"{name}Blocking", "blocking_of": name, "dossier": (move or {}).get("dossier") or clip.get("dossier"),
                   "keys": [{"t": p["t"]} for p in poses]}, fh, indent=1)
    rec = load_record(anims, name)
    if settle(rec, poses, today):
        save_record(anims, name, rec)
    st = state_of(rec, poses)
    m = {"schema": 1, "name": name, "id": blocking_id(poses), "fps": fps_of(clip), "duration": float(clip["times"][-1]),
         "hit": hit_of(clip), "source": "pose" if pose else "clip" if clip_path else ("move" if from_move else "gesture"),
         "made_from": [p.replace(os.sep, "/") for p in made_from], "made_from_sha256": sources_hash(made_from),
         **({"pose_sha256": pose_hash(pose)} if pose else {}),
         "folder": out.replace(os.sep, "/"),
         "clip": os.path.join(out, "blocking.clip.json").replace(os.sep, "/"),
         "move": os.path.join(out, "blocking.move.json").replace(os.sep, "/"),
         "record": record_path(anims, name).replace(os.sep, "/"),
         "poses": poses, "state": st["state"], "state_words": st["words"], "drift": st["drift"],
         "notes": [{**{k: n.get(k) for k in ("pose", "pose_said", "words", "by", "date", "state", "answered", "closed",
                                              "carried", "unsure", "gone")},
                    "pose": None if n.get("gone") else n.get("pose"), "text": note_words(n)} for n in rec.get("notes", [])],
         "approved": ({k: rec["approved"][k] for k in ("words", "by", "date", "id")} if rec.get("approved") else None)}
    with open(os.path.join(out, "blocking.json"), "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=1)
    return m


def next_words(m):
    """what to do with a blocking in this state. It starts with 'look at' so the kit's runner prints it as the
    command's next_action (kit/lib/run.luau surfaces only such a hint from a passing step)"""
    name, folder = m["name"], m["folder"]
    show = (f"{folder}/pose_sheet.png and every keys/ page at full size, and {folder}/blocking.gif (the poses held at their real "
            f"timing), then show the owner; his words on a pose: lune run kit anim block {name} --note <pose> \"<his words>\"; "
            f"his yes to THIS blocking: lune run kit anim block {name} --approve \"<his words>\" --by owner --id {m.get('id')}")
    if m["state"] == "approved":
        return "none - the in-betweens may be made from these poses"
    if m["state"] == "stale":
        return f"look at what changed after his yes ({'; '.join(m.get('drift') or [])[:300]}), then at {show}"
    if m["state"] == "notes open":
        n = next(x for x in m["notes"] if x["state"] == "open")
        said = f"the owner: \"{n['words']}\""
        if n.get("gone"):
            return (f"look at the poses as they are now against his note on a pose that is gone ({said}; it was pose "
                    f"{n.get('pose_said')}): show him the sheet - only his yes closes that note")
        if n.get("carried") or n.get("unsure"):
            return (f"look at pose {n['pose']} ({said}): it changed, but not by a change to its own key ({n.get('carried') or n.get('unsure')}) - "
                    f"if that is the answer, show him the sheet (his yes closes the note); if not, change that pose's own key, "
                    f"then lune run kit anim block {name} --sheet")
        return (f"look at pose {n['pose']} ({said}) and change that pose in the move's keys, then lune run "
                f"kit anim block {name} --sheet (the note is answered when the pose's own key is no longer as he saw it)")
    return f"look at {show}"


def rhythm(poses):
    return " | ".join(f"{p['k']}: {p['t']:.2f} s, held {p['hold_s']:.2f}" for p in poses)


# ---------------------------------------------------------------- the gif (the held poses at their real timing)
def gif(folder):
    """the sheet's own renders of the blocking from the player's camera as a gif that plays in real time: EVERY pose,
    each shown for as long as it is held (a blocking's plan renders every pose's own frame, so a pose held for one
    frame is in it too). Each frame names its pose and its hold -> the gif's path"""
    from PIL import Image, ImageDraw
    import pose_sheet as PS
    with open(os.path.join(folder, "plan.json"), encoding="utf-8") as fh:
        pl = json.load(fh)
    with open(os.path.join(folder, "blocking.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    if not (pl.get("strip_frames") or []):
        raise ValueError("the sheet was made without strips: there is nothing to play")
    poses = m["poses"]
    ims, durs, carry = [], [], 0.0
    for p in poses:
        path = os.path.join(folder, "frames", f"strip_player_{int(p['frame']):04d}.png")
        if not os.path.isfile(path):
            raise ValueError(f"the render of pose {p['k']} (frame {p['frame']}) is missing ({path})")
        im = Image.open(path).convert("RGB")
        if im.width > GIF_WIDTH:
            im = im.resize((GIF_WIDTH, int(round(im.height * GIF_WIDTH / im.width))), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        PS.label(d, (0, 0), f"POSE {p['k']} of {len(poses)}   {p['t']:.2f} s   held {p['hold_s']:.2f} s", PS.font(20, True))
        # a gif counts time in hundredths of a second (and shows nothing under 20 ms): the rounding is carried on,
        # so the whole plays in real time
        want = float(p["hold_s"]) * 1000.0 + carry
        ms = max(20, int(round(want / 10.0)) * 10)
        carry = want - ms
        ims.append(im)
        durs.append(ms)
    durs[-1] += GIF_PAUSE_MS
    out = os.path.join(folder, "blocking.gif")
    # (each frame differs by its label, so none is merged away: frame k IS pose k)
    ims[0].save(out, save_all=True, append_images=ims[1:], duration=durs, loop=0)
    return out


# ---------------------------------------------------------------- the command line
def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def _manifest(out):
    path = os.path.join(out, "blocking.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except ValueError as e:
            raise ValueError(f"{path.replace(os.sep, '/')} is not valid JSON ({e}): make the blocking again") from e


def main(argv):
    """every way in ends with ONE verdict line: an input the kit cannot read is a refusal that says so, never a
    traceback (a record a person can corrupt, a clip with a short track, a pose number that is a word)"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return _main(argv)
    except (OSError, ValueError, KeyError, IndexError, TypeError, StopIteration, AttributeError, ZeroDivisionError,
            SystemExit) as e:                               # (a builder that refuses by exiting: said in one line too)
        if isinstance(e, SystemExit) and not isinstance(e.code, str):
            raise
        what = f"{argv[1]} " if len(argv) > 1 else ""
        return emit("fail", f"anim blocking {what}: it could not be read or made ({type(e).__name__}: {e})",
                    "check the move's file, its blocking record (assets/animations/blocks/) and the arguments, then lune run "
                    "kit anim block <Name> --sheet")


def _main(argv):
    cmd = argv[0] if argv else "help"
    if cmd == "gif" and len(argv) >= 2:
        try:
            path = gif(argv[1])
        except (OSError, ValueError) as e:
            return emit("fail", f"anim blocking gif: {e}", "lune run kit anim block <Name> --sheet")
        m = _manifest(argv[1]) or {}
        return emit("pass", f"anim blocking gif: {path.replace(os.sep, '/')} (the held poses at their real timing)",
                    next_words(m) if m.get("name") else "none - proceed", gif=path.replace(os.sep, "/"))
    if cmd not in ("make", "note", "approve", "state", "kept", "lock", "freeze") or (len(argv) < 2 and cmd != "freeze"):
        print(__doc__)
        return 1
    name = argv[1] if len(argv) > 1 else ""
    anims = flag(argv, "--anims", os.path.join("assets", "animations"))
    if cmd == "lock":
        pairs = []
        for a in argv[1:]:
            if a.startswith("--"):
                break
            bits = a.split("=", 2)                           # (a path may hold an "=": only the first two split)
            if len(bits) < 3 or bits[1] not in ("move", "blade", "pose") or not bits[0]:
                return emit("fail", f"anim blocking lock: '{a}' is not <Name>=move=<move.json> or <Name>=blade=<dossier>[=<gesture>]",
                            "lune run kit anim <Name>")
            where, gesture = bits[2], None
            if bits[1] == "blade":
                where, _, gesture = bits[2].partition("=")
            pairs.append((bits[0], bits[1], where, gesture or None))
        r = lock(pairs, anims)
        if not r["held"]:
            return emit("pass", f"anim blocking lock: {len(pairs)} move(s) free to be made", "none - proceed", **r)
        first = next(p[0] for p in pairs if p[0] in r["held"])
        names = ", ".join(sorted(r["held"]))
        return emit("fail", f"anim {first}: STOP - a NEW move, and its key poses do not have the owner's yes: "
                            f"{r['held'][first]}. Poses first, motion after (his method lists: pose-to-pose, blocking)"
                            + (f" - held: {names}" if len(r["held"]) > 1 else ""),
                    how_to_block(first, *r["how"][first]), **r)
    if cmd == "freeze" and "--posed" in argv:
        try:
            path, names = freeze_posed(anims)
        except ValueError as e:
            return emit("fail", f"anim blocking freeze: {e}", "none - the list stands as it is")
        return emit("pass", f"anim blocking freeze: {len(names)} hand-posed file(s) made before the rule -> {path.replace(os.sep, '/')}",
                    "none - a hand-posed move added from now on needs the owner's yes to its key poses", list=path.replace(os.sep, "/"))
    if cmd == "freeze":
        try:
            path, names = freeze(anims)
        except ValueError as e:
            return emit("fail", f"anim blocking freeze: {e}", "none - the list stands as it is")
        return emit("pass", f"anim blocking freeze: {len(names)} move(s) made before the rule -> {path.replace(os.sep, '/')}",
                    "none - a strike or sword move added from now on needs the owner's yes to its key poses", list=path.replace(os.sep, "/"))
    if cmd == "kept":
        clip_path = flag(argv, "--clip")
        if not clip_path or not os.path.isfile(clip_path):
            return emit("fail", f"anim kept {name}: no finished clip at {clip_path}", f"lune run kit anim {name}")
        try:
            with open(clip_path, encoding="utf-8") as fh:
                clip = json.load(fh)
            rec = load_record(anims, name)
            tol_deg = float(flag(argv, "--tol-deg", KEPT_DEG))
            tol_studs = float(flag(argv, "--tol-studs", KEPT_STUDS))
            tol_tip = float(flag(argv, "--tol-tip", KEPT_TIP))
            r = kept(clip, rec, tol_deg, tol_studs, float(flag(argv, "--window", KEPT_WINDOW_S)), tol_tip)
        except (OSError, ValueError, KeyError, IndexError, TypeError, ZeroDivisionError) as e:
            return emit("fail", f"anim kept {name}: the clip or the blocking record could not be read ({e})",
                        f"lune run kit anim block {name} --state")
        if r["state"] == "none":
            return emit("pass", f"anim kept {name}: the owner has approved no blocking of this move - nothing to hold the clip to",
                        "none - proceed", state="none")
        if r["state"] == "kept":
            worst = max(r["rows"], key=lambda x: x["deg"])
            return emit("pass", f"anim kept {name}: the clip keeps the {len(r['rows'])} pose(s) the owner approved, each at its own "
                                f"moment (blocking {r['id']}; the furthest: pose {worst['pose']}, {worst['joint'] or 'no limb'} "
                                f"{worst['deg']:.1f} deg)", "none - proceed", state="kept", rows=r["rows"])
        said = [lost_words(x, tol_deg, tol_studs, tol_tip) for x in r["lost"][:3]]
        if r["length"]:
            said.insert(0, f"the clip is {r['length']['clip_s']:.2f} s long and the blocking he approved {r['length']['approved_s']:.2f} s "
                           "(its rhythm is part of his yes)")
        more = f" (+{len(r['lost']) - 3} more pose(s))" if len(r["lost"]) > 3 else ""
        if r.get("source") == "gesture":
            # his yes was to the GESTURE at neutral efforts; a pick's efforts re-pose it by design: said, never a gate
            return emit("pass", f"anim kept {name}: NOT HELD AS A GATE - the owner's yes ({r['id']}) was to the gesture's blocking at "
                                f"neutral efforts, and this clip differs from it on {len(r['lost'])} of {len(r['rows'])} pose(s) - "
                                + "; ".join(said) + more,
                        f"improve the record: show him THIS clip's own poses (lune run kit anim block {name} --sheet --clip <this clip>) "
                        "and take his yes on that - then every build is held to it", state="differs", rows=r["rows"])
        first = r["lost"][0] if r["lost"] else None
        culprit = lost_bits(first, tol_deg, tol_studs, tol_tip)[0][0] if first else "the clip's length"
        return emit("fail", f"anim kept {name}: the clip DRIFTS from the blocking the owner approved ({r['id']}) on {len(r['lost'])} of "
                            f"{len(r['rows'])} pose(s) - " + "; ".join(said) + more,
                    (f"bring pose {first['pose']} back to what he approved (the pass that moved {culprit})" if first
                     else "give the clip back the length he approved")
                    + f", or show him the new blocking: lune run kit anim block {name} --sheet", state="drifted", rows=r["rows"])
    out = flag(argv, "--out", os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{name}.blocking"))
    if cmd == "make":
        at = [float(x) for x in flag(argv, "--at", "").split(",") if x.strip()] or None
        try:
            m = make(name, out, anims, flag(argv, "--clip"), flag(argv, "--from-move"), flag(argv, "--dossier"),
                     flag(argv, "--move"), at, gesture=flag(argv, "--gesture"), pose=flag(argv, "--pose"))
        except (OSError, ValueError, KeyError, StopIteration) as e:
            return emit("fail", f"anim blocking {name}: {e}", f"lune run kit anim block {name} --sheet")
        return emit("pass", f"anim blocking {name}: {len(m['poses'])} key pose(s) held at the move's own timing ({rhythm(m['poses'])}) "
                            f"-> {m['clip']}; blocking {m['id']}: {m['state_words']}",
                    next_words(m), id=m["id"], state=m["state"], folder=m["folder"], clip=m["clip"], move=m["move"])
    m = _manifest(out)
    if m is None:
        return emit("fail", f"anim blocking {name}: no blocking was made yet ({out}/blocking.json)",
                    f"lune run kit anim block {name} --sheet")
    rec = load_record(anims, name)
    poses = m["poses"]
    old = out_of_date(m)
    if old:
        # what is in build/ is not the move as it is: no state is read off it, no note and no yes are taken on it
        return emit("fail", f"anim blocking {name}: blocking {m['id']} in {out} is OUT OF DATE - {old}",
                    f"lune run kit anim block {name} --sheet, then look at THAT sheet (and show the owner that one)",
                    state="out of date")
    if cmd == "state":
        st = state_of(rec, poses)
        need = flag(argv, "--need")
        ok = need is None or st["state"] == need
        return emit("pass" if ok else "fail", f"anim blocking {name} ({m['id']}): {st['state']} - {st['words']}",
                    next_words({**m, "state": st["state"], "notes": rec.get("notes", []), "drift": st["drift"]}),
                    state=st["state"], drift=st["drift"])
    by = flag(argv, "--by", "")
    try:
        if cmd == "note":
            if len(argv) < 3 or not argv[2].lstrip("-").isdigit():
                raise ValueError(f"a note names its pose by its number on the sheet (1 to {len(poses)}), then his words")
            k = int(argv[2])
            rec = add_note(rec, k, argv[3] if len(argv) > 3 and not argv[3].startswith("--") else "", poses, by or "owner")
            what = f"the owner's note on pose {k} is kept with the pose as he saw it: \"{rec['notes'][-1]['words']}\""
            nxt = (f"look at pose {k} and change it in the move's keys, then lune run kit anim block {name} --sheet: the next "
                   "sheet says whether the note is answered")
        else:
            saw = flag(argv, "--id")
            if by == "owner" and not saw:
                raise ValueError("name the blocking he said yes to: --id <the id in the first line of the sheet he saw>")
            if by == "owner" and saw != m["id"]:
                raise ValueError(f"his yes was to blocking {saw}, and the blocking made last is another one: show him the "
                                 "sheet as it is now")
            rec = approve(rec, argv[2] if len(argv) > 2 and not argv[2].startswith("--") else "", poses, by,
                          timing={"duration": m.get("duration"), "hit": m.get("hit")}, source=m.get("source"),
                          made_from_sha256=m.get("made_from_sha256"), pose_sha256=m.get("pose_sha256"))
            what = f"the owner's yes to blocking {m['id']} ({len(poses)} pose(s)) is recorded: \"{rec['approved']['words']}\""
            nxt = "none - the in-betweens may be made from these poses; a pose that changes later makes this yes stale"
    except (ValueError, IndexError) as e:
        return emit("fail", f"anim blocking {name}: {e}",
                    f"lune run kit anim block {name} --note <pose> \"<his words>\"   |   --approve \"<his words>\" --by owner "
                    "--id <the blocking's id on the sheet he saw>")
    path = save_record(anims, name, rec)
    return emit("pass", f"anim blocking {name}: {what} ({path.replace(os.sep, '/')})", nxt, record=path.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
