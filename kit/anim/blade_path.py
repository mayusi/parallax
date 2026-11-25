"""blade_path.py — A PATH DRAWN FOR THE BLADE (the owner's method lists 2026-11-13: motion path / curve animation; the
audit: board/plans/archive/2026-11-13-anim-methods-audit.md). The kit drew the blade's path on the pose sheet for the eye and
ran a two-handed cut along a designed line, but nobody could DRAW a path and have the motion held to it. A move may
now state the points its blade tip passes through:

    "blade_path": {"tol": 0.5, "points": [{"t": 0.30, "tip": [1.2, 2.0, -1.5]}, {"tip": [-1.8, -0.4, -2.2]}]}

in the move's own space (the keys' space: x right, y up from the torso's centre, -z forward; studs). A point with a
time is passed AT that time (within WINDOW seconds either side); a point with no time is passed at some moment, and
the points are passed IN ORDER. `tol` (studs, default TOL) is how near "passes through" is.

    python kit/anim/blade_path.py <clip.json> [--move <move.json>]
    python kit/anim/blade_path.py draw <clip.json> [--every 0.1]     the clip's own path as points to edit

The build's motion gates (kit/anim/metrics.py) run it on every clip whose source file states a blade_path: a point
the finished clip's tip never comes within tol of - a spring, a feel or a polish pass pulled the blade off the drawn
line - FAILS, named with its number, how far and when; so does a point timed past the clip's end. A clip built from
another clip (a feel pass, a re-arm, a warp) is held to the path its BASE move draws. A move that draws no path is
held to nothing. `tol` is 1 stud at most.
A PATH DRAWN FOR A HAND OR A FOOT (2026-11-15: the blade was the only thing a path could be drawn for - a kick's
foot, a punch's fist, a reaching hand had none). A move or a pose file may also state

    "paths": {"RightFoot": {"tol": 0.5, "points": [{"t": 0.30, "at": [x, y, z]}, {"at": [x, y, z]}]}}

for RightHand, LeftHand, RightFoot, LeftFoot: the far end of that R6 limb (the hand; the sole's centre), in the
space the clip STARTS in, with the clip's own travel AND turn carried (a step, a lunge, a spin: where the world sees
the foot; the pose sheet draws the same) - not the keys' space the blade's path is in: a clip that travels holds its
blade and its hands in two different spaces. An R15 clip is not held (neither path): its R6 version is. The same rules: timed points at their moment, untimed ones in order, tol 1 stud
at most. The points off a clip's own path: `python kit/anim/blade_path.py draw <clip.json> --of RightFoot`.
The build's gates hold a clip to every path its source (or its base move) draws; a name that is no hand or foot of
the R6 body is a problem, never skipped.
KNOWN LIMITS (card r66z): the blade's path is in the keys' space, so the body's travel (a step, a dash) is not part of it;
ten points a tenth of a second apart at 0.5 studs do not catch a key's blade turned 30 degrees (0.2 studs).
Measured on the kit's fixtures (the loved kesa, ten points off its own path): the clip passes through them at 0.00
studs; with any one key turned 15 degrees it stays within 0.4 (a turn of the body barely moves the blade); with the
grip of two keys raised one stud it misses two points, the worst by 1.02."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TOL = 0.5            # studs: how near the tip must come to a drawn point
TOL_MAX = 1.0        # studs: the widest a path may ask for (a wider "path" holds nothing)
WINDOW = 0.05        # seconds either side of a timed point's own moment
SUB = 4              # looked for between frames too


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


# the hands and feet a path may be drawn for: the far end of that one-piece R6 limb (kit/anim/pose_sheet.py limb_end)
EFFECTORS = {"RightHand": "Right Arm", "LeftHand": "Left Arm", "RightFoot": "Right Leg", "LeftFoot": "Left Leg"}
SAID = {"RightHand": "right hand", "LeftHand": "left hand", "RightFoot": "right foot", "LeftFoot": "left foot"}


def parse(spec, of=None):
    """a move's blade_path (of None), or the path drawn for a hand or a foot (of = its name) -> (tol, [(t or None,
    point)]); ValueError says what is wrong with it"""
    what = "blade_path" if of is None else f"path of {of}"
    key = "tip" if of is None else "at"
    if not isinstance(spec, dict) or not isinstance(spec.get("points"), list) or not spec["points"]:
        raise ValueError(f'a {what} is {{"points": [{{"t": seconds (optional), "{key}": [x, y, z]}}, ...], "tol": studs}}')
    tol = spec.get("tol", TOL)
    if isinstance(tol, bool) or not isinstance(tol, (int, float)) or not np.isfinite(tol) or not 0 < tol <= TOL_MAX:
        raise ValueError(f"a {what}'s tol is a positive number of studs, {TOL_MAX:g} at most")
    pts, last_t = [], None
    for i, p in enumerate(spec["points"]):
        tip = p.get(key) if isinstance(p, dict) else None
        if (not isinstance(tip, list) or len(tip) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) for v in tip)):
            raise ValueError(f"point {i + 1} of the {what} has no {key} [x, y, z]")
        t = p.get("t")
        if t is not None:
            if isinstance(t, bool) or not isinstance(t, (int, float)) or not np.isfinite(t) or t < 0:
                raise ValueError(f"point {i + 1} of the {what}: its t is seconds from the clip's start")
            if last_t is not None and t < last_t:
                raise ValueError(f"point {i + 1} of the {what} comes before the timed point ahead of it: the points are in order")
            last_t = float(t)
        pts.append((None if t is None else float(t), np.array(tip, float)))
    return float(tol), pts


def track(clip, of=None):
    """the path the check reads, [n, 3]: the blade's tip (of None; the keys' space) or a hand's / a foot's (of = its
    name; the character's space, the clip's travel carried). A stepped clip is read on its smooth motion"""
    import clip as C
    if clip.get("stepped"):
        clip = C.destep(clip)
    if of is None:
        sw = clip.get("sword") if isinstance(clip.get("sword"), dict) else {}
        if not sw.get("tip") or len(sw["tip"]) < 2:
            raise ValueError("the clip has no blade tip to hold to a path")
        return np.array(sw["tip"], float)
    if of not in EFFECTORS:
        raise ValueError(f"{of!r} is no hand or foot of the R6 body - a path is drawn for {', '.join(EFFECTORS)}")
    if clip.get("rig") not in (None, "R6"):
        raise ValueError(f"it is a {clip.get('rig')} clip - a hand's or a foot's path is read on the R6 clip")
    import pose_sheet as PS
    W = C.world_frames(clip, C.load_rig("r6"))
    if len(W) < 2 or EFFECTORS[of] not in W[0]:
        raise ValueError(f"the clip has no {EFFECTORS[of]} to hold to a path")
    return np.array([PS.limb_end(w, EFFECTORS[of]) for w in W], float)


def tip_at(tip, x):
    i = int(np.floor(x))
    if i >= len(tip) - 1:
        return tip[-1]
    f = x - i
    return tip[i] * (1.0 - f) + tip[i + 1] * f


def read(clip, spec, of=None):
    """-> {tol, rows: [{point, t, at_s, studs, ok}], missed: [rows]}. Each point is looked for after the moment the
    point before it was passed (in order); a timed one only round its own moment. of: None = the blade's tip, else
    the hand or foot the path is drawn for"""
    tol, pts = parse(spec, of)
    tip = track(clip, of)                                    # (a stepped build is read on its smooth motion)
    fps = float(clip.get("fps") or 30)
    last = len(tip) - 1
    rows, start = [], 0.0
    for k, (t, want) in enumerate(pts):
        why = None
        if t is not None and t * fps > last + WINDOW * fps:
            why = f"its moment {t:.2f} s is past the clip's end ({last / fps:.2f} s)"
        elif t is not None and (t + WINDOW) * fps < start:
            why = f"its moment {t:.2f} s lies before point {k} was passed ({start / fps:.2f} s): the points are in order"
        if why:
            rows.append({"point": k + 1, "t": t, "at_s": round(min(t, last / fps), 3), "studs": None, "ok": False, "why": why})
            continue
        if t is not None:
            lo, hi = max(start, (t - WINDOW) * fps), min(last, (t + WINDOW) * fps)
        else:
            lo, hi = min(start, float(last)), float(last)
        xs = np.unique(np.r_[np.arange(lo, hi + 1e-9, 1.0 / SUB), hi])
        d = np.array([float(np.linalg.norm(tip_at(tip, x) - want)) for x in xs])
        near = np.where(d <= tol)[0]
        if t is not None or not len(near):
            j = int(np.argmin(d))                            # a timed point: its nearest moment in its own window
        else:
            j = int(near[0])                                 # an untimed one: the FIRST pass through it (the points are
            while j + 1 < len(d) and d[j + 1] < d[j]:        # in order), at that pass's nearest moment
                j += 1
        ok = bool(d[j] <= tol)
        rows.append({"point": k + 1, "t": t, "at_s": round(float(xs[j]) / fps, 3), "studs": round(float(d[j]), 2), "ok": ok})
        if ok:                                               # the next point is passed AFTER this one (one pass, one point)
            start = float(xs[j]) + (1.0 / SUB if t is None else 0.0)
    return {"tol": tol, "rows": rows, "missed": [r for r in rows if not r["ok"]]}


def words(r, name, of=None):
    n = len(r["rows"])
    who = "blade" if of is None else SAID.get(of, str(of))
    if not r["missed"]:
        far = max(r["rows"], key=lambda x: x["studs"])
        return (f"the {who} of {name} passes through the {n} point(s) drawn for it, {r['tol']:g} studs allowed (the furthest: "
                f"point {far['point']}, {far['studs']} studs, at {far['at_s']:.2f} s)")
    m = r["missed"][0]
    more = f" (+{len(r['missed']) - 1} more)" if len(r["missed"]) > 1 else ""
    if m.get("why"):
        return f"the {who} of {name} MISSES {len(r['missed'])} of the {n} point(s) drawn for it - point {m['point']}: {m['why']}{more}"
    when = (f"at its moment {m['t']:.2f} s" if m["t"] is not None else "after the point before it" if m["point"] > 1
            else "anywhere in the clip")
    it = "the tip" if of is None else "it"
    return (f"the {who} of {name} MISSES {len(r['missed'])} of the {n} point(s) drawn for it - point {m['point']}: {it} "
            f"comes no nearer than {m['studs']} studs ({r['tol']:g} allowed), {when} (nearest at {m['at_s']:.2f} s){more}")


def _source(path):
    if not isinstance(path, str) or not path.lower().endswith(".json") or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        try:
            d = json.load(fh)
        except ValueError:
            return None                                      # (an unreadable source is said by the build itself)
    return d if isinstance(d, dict) else None


def spec_of(clip, move=None, key="blade_path"):
    """the path drawn for this clip: the move given, else its source file's; a clip built FROM another clip (a feel
    pass, a re-arm, a warp: source.from) is held to the path its base move draws -> (spec or None, where it was read).
    key: "blade_path" (the blade's), or "paths" (the hands' and feet's: {name: path})"""
    if isinstance(move, dict):
        return move.get(key), "the move given"
    src = clip.get("source") if isinstance(clip.get("source"), dict) else {}
    path = src.get("file")
    d = _source(path)
    if d is not None and d.get(key) is not None:
        return d[key], path
    base = src.get("from") or (d or {}).get("from")
    if isinstance(base, str) and isinstance(path, str):
        for ext in (".move.json", ".pose.json"):
            there = os.path.join(os.path.dirname(path), base + ext)
            b = _source(there)
            if b is not None and b.get(key) is not None:
                return b[key], there
    return None, (path if d is not None else None)


def gate_paths(clip, move=None):
    """the paths drawn for hands and feet, held: what the build's motion gates add beside the blade's (kit/anim/
    metrics.py) -> ({name: reading} or None, the problem(s) or None). No "paths" in the source: held to nothing; one
    that cannot be read, or a name that is no hand or foot, is a problem"""
    if clip.get("rig") != "R6":
        return None, None
    specs, where = spec_of(clip, move, "paths")
    if specs is None:
        return None, None
    name = str(clip.get("name"))
    if not isinstance(specs, dict) or not specs:
        return {"error": "not a table"}, (f'the "paths" drawn in {where} cannot be held (it is {{"RightFoot": {{"points": '
                                          f'[...]}}, ...}}: a path for each hand or foot named)')
    out, problems = {}, []
    for of in sorted(specs, key=str):
        try:
            if of not in EFFECTORS:                          # (the name first: a wrong name with a wrong shape says the name)
                raise ValueError(f"{of!r} is no hand or foot of the R6 body - a path is drawn for {', '.join(EFFECTORS)}")
            r = read(clip, specs[of], of)
        except (ValueError, KeyError, IndexError, TypeError) as e:
            out[str(of)] = {"error": str(e)}
            problems.append(f"the path drawn for {of} in {where} cannot be held ({e})")
            continue
        out[of] = {"tol": r["tol"], "rows": r["rows"]}
        if r["missed"]:
            problems.append(words(r, name, of) + f" - bring the {SAID[of]} back onto the drawn line (the pass that moved "
                            "it: a key, springs, a feel or polish pass, a foot plant), or draw the path again and show it; "
                            "never widen tol to pass")
    return out, ("; ".join(problems) if problems else None)


def gate(clip):
    """what the build's motion gates add (kit/anim/metrics.py) -> (the reading for metrics.json or None, the problem
    or None). A source that draws no path is held to nothing; a path that cannot be read is a problem"""
    if clip.get("rig") != "R6":
        return None, None
    spec, where = spec_of(clip)
    if spec is None:
        return None, None
    name = str(clip.get("name"))
    try:
        r = read(clip, spec)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {"error": str(e)}, f"the blade_path drawn in {where} cannot be held ({e})"
    out = {"tol": r["tol"], "rows": r["rows"]}
    if not r["missed"]:
        return out, None
    return out, (words(r, name) + " - bring the blade back onto the drawn line (the pass that moved it: springs, a feel or "
                 "polish pass, a key), or draw the path again and show it; never widen tol to pass")


def draw(clip, every=0.1, of=None):
    """the clip's own tip path as points to edit -> a blade_path; of = a hand or a foot: its path -> one of "paths" """
    tip = np.array(clip["sword"]["tip"], float) if of is None else track(clip, of)
    fps = float(clip.get("fps") or 30)
    step = max(1, int(round(every * fps)))
    idx = sorted(set(list(range(0, len(tip), step)) + [len(tip) - 1]))
    key = "tip" if of is None else "at"
    return {"tol": TOL, "points": [{"t": round(i / fps, 4), key: [round(float(v), 3) for v in tip[i]]} for i in idx]}


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "draw":
            with open(argv[1], encoding="utf-8") as fh:
                c = json.load(fh)
            of = flag(argv, "--of")
            path = draw(c, float(flag(argv, "--every", "0.1")), of)
            if of:
                return emit("pass", f"anim path: {len(path['points'])} point(s) off the {SAID[of]}'s own path of {c.get('name')}",
                            "edit the points (move one, drop the times you do not mean) and put them in the move as "
                            f'"paths": {{"{of}": ...}}', paths={of: path})
            return emit("pass", f"anim path: {len(path['points'])} point(s) off the blade's own path of {c.get('name')}",
                        "edit the points (move one, drop the times you do not mean) and put them in the move as \"blade_path\"",
                        blade_path=path)
        with open(argv[0], encoding="utf-8") as fh:
            c = json.load(fh)
        move = None
        if flag(argv, "--move"):
            with open(flag(argv, "--move"), encoding="utf-8") as fh:
                move = json.load(fh)
        spec, where = spec_of(c, move)
        name = str(c.get("name"))
        others, off = gate_paths(dict(c, rig=c.get("rig") or "R6"), move)
        if off and spec is None:
            return emit("fail", f"anim path: {off}", "bring it back onto the drawn line, or draw the path again and show "
                        "it; never widen tol to pass", paths=others)
        if spec is None:
            if others:
                return emit("pass", f"anim path {name}: passes through the path(s) drawn for {', '.join(others)}",
                            "none - proceed", paths=others)
            return emit("pass", f"anim path {name}: no path is drawn for its blade - nothing to hold it to", "none - proceed")
        r = read(c, spec)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim path: it could not be read ({type(e).__name__}: {e})",
                    "python kit/anim/blade_path.py <clip.json> [--move <move.json>]")
    more = {"paths": others} if others else {}
    if r["missed"] or off:                                   # (the blade's miss AND a hand's or a foot's: both said at once)
        said = "; ".join(x for x in (words(r, name) if r["missed"] else None, off) if x)
        return emit("fail", f"anim path: {said}",
                    "bring it back onto the drawn line, or draw the path again and show it; never widen tol to pass",
                    rows=r["rows"], **more)
    also = f"; and through the path(s) drawn for {', '.join(others)}" if others else ""
    return emit("pass", f"anim path: {words(r, name)}{also}", "none - proceed", rows=r["rows"], **more)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
