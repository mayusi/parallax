"""fast_turns.py — A JOINT THAT TURNS FASTER THAN THE FRAMES CAN CARRY (found by the clip budget, S54, 2026-11-15).

A clip is a pose a frame, and the game plays the SHORTEST turn between two poses. A joint that turns more than a
quarter of a circle between two frames is past what that can carry: near half a circle the short way round and
the long way are the same length, so which way the arm goes is not defined; and at 60 frames a second it is a
turn of 5400 degrees a second or more.
The pop gate (kit/anim/clip.py) does not see these: it looks for ONE big step beside calm ones, and a swing that
steps 85 then 177 degrees is two big steps side by side.
What the clips say (2026-11-15): the seven loved cuts of the kit's fixtures never turn a joint more than 31
degrees between two frames (the three rejected fixtures: 35); among ALL the clips the owner loved the most is 76
(HqM1b, an imported clip at 60 frames a second) - so the limit stands 14 degrees above the fastest loved turn, not
far above it. Forty-four built clips turn a joint over 90; seven of those have a verdict of the owner's, and all
seven are "bad" or "horrible".
PER STORED FRAME, and what that means: the limit is about the turn between two poses the clip HOLDS, whatever its
frame rate - it is the shortest-turn question, not a speed limit. So a 30-a-second clip fails at half the speed a
60-a-second one does (nine of the 44 are 30-a-second clips, 2900 to 4600 degrees a second; the loved HqM1b turns
4578 a second and passes at 60). A clip keyed at 30 a second that swings this fast wants more frames there.

    python kit/anim/fast_turns.py <clip.json>                       one clip: its fastest turn, joint by joint
    python kit/anim/fast_turns.py table <folder of built clips>     every clip over the limit, the worst first
    python kit/anim/fast_turns.py freeze <folder> --out <anims>/blocks/_fast_turn_before.json

THE RULE: no joint - and not the weapon's own joint (`grip`, `grip_left`) - turns more than LIMIT degrees between
two frames. A stepped clip's declared steps (strike.py `step`: limited animation holds a pose and jumps on
purpose) are not judged.
THE GATE (kit/anim/metrics.py, in every build): a clip over the limit FAILS, named, with the joint and the frame;
a clip made before the rule (frozen once: <anims>/blocks/_fast_turn_before.json) is said, never failed.
NOT DONE: a repair (a turn this fast is the move's own keys: ease the swing over more frames, or - when a snap is
meant - declare the step). This is a fact about what frames can carry, not a judgement of the look."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

LIMIT = 90.0         # degrees between two frames
BEFORE = "_fast_turn_before.json"


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def read(clip):
    """-> {"worst": {joint, frame, t, deg} | None, "over": [{joint, frame, t, deg}], "limit"}"""
    import clip as C
    if not isinstance(clip, dict) or not isinstance(clip.get("joints"), dict):
        raise ValueError("it is not a clip")
    fps = float(clip.get("fps") or 30)
    intended = C.step_frames(clip)
    tracks = {name: j.get("frames") for name, j in clip["joints"].items() if isinstance(j, dict)}
    for key, name in (("grip", "the weapon"), ("grip_left", "the left weapon")):
        if isinstance(clip.get(key), list):
            tracks[name] = clip[key]
    worst, over = None, []
    for name, fr in tracks.items():
        if not isinstance(fr, list) or len(fr) < 2:
            continue
        for i in range(1, len(fr)):
            if i in intended:
                continue
            a, b = fr[i - 1], fr[i]
            if not (isinstance(a, list) and isinstance(b, list) and len(a) >= 4 and len(b) >= 4):
                continue
            deg = C.quat_angle(a[:4], b[:4])
            if deg != deg:
                continue
            row = {"joint": name, "frame": i, "t": round(i / fps, 4), "deg": round(float(deg), 1)}
            if worst is None or deg > worst["deg"]:
                worst = row
            if deg > LIMIT:
                over.append(row)
    over.sort(key=lambda r: -r["deg"])
    return {"worst": worst, "over": over, "limit": LIMIT}


def words(name, r):
    w = r["over"][0]
    more = f" (+{len(r['over']) - 1} more frame(s))" if len(r["over"]) > 1 else ""
    return (f"{name}: {w['joint']} turns {w['deg']:g} degrees between frames {w['frame'] - 1} and {w['frame']} "
            f"({w['t']:.2f} s){more} - over {LIMIT:g} a frame the way round is not the frames' to carry")


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


def gate(clip, listed=True):
    """what the build's motion gates add (kit/anim/metrics.py) -> (the reading or None, the problem or None)"""
    if not isinstance(clip, dict) or clip.get("prop"):
        return None, None
    try:
        r = read(clip)
    except Exception as e:                                   # noqa: BLE001 (a reading never breaks a build by raising)
        return {"error": f"{type(e).__name__}: {e}"}, None
    out = {"worst": r["worst"], "over": r["over"][:5], "limit": LIMIT}
    if not r["over"]:
        return out, None
    name = str(clip.get("name"))
    src = (clip.get("source") or {}).get("file") if isinstance(clip.get("source"), dict) else None
    anims = os.path.dirname(src) if isinstance(src, str) and src else os.path.join("assets", "animations")
    try:
        old = before(os.path.join(anims, "blocks", BEFORE)) if listed else set()
    except (ValueError, OSError) as e:                       # (a list that cannot be read excuses nobody)
        return out, f"the list of clips made before the fast-turn rule could not be read ({e})"
    if name in old:
        out["made_before_the_rule"] = True
        return out, None
    return out, (words(name, r) + " - ease the swing over more frames, or, if a snap is meant, declare it "
                 "(the move's `step`: a stepped clip's own jumps are not judged)"
                 + _no_list(anims, listed, "fast_turns"))


def _clips(folder):
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
        if isinstance(c, dict):
            yield stem, c


def freeze(folder, out, today=None):
    """the built clips that fail today -> the frozen list (refused when it exists)"""
    import datetime
    if os.path.exists(out):
        raise ValueError(f"{out.replace(os.sep, '/')} exists: the list is frozen once and never extended")
    names = sorted({str(c.get("name") or stem) for stem, c in _clips(folder) if gate(c, listed=False)[1]})
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"schema": 1, "frozen": today or datetime.date.today().isoformat(),
                   "why": "clips with a joint turning over 90 degrees between two frames when the rule came "
                          "(kit/anim/fast_turns.py): said in their metrics, never failed. Frozen once, never extended.",
                   "clips": names}, fh, indent=1)
        fh.write("\n")
    return names


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "freeze":
            out = argv[argv.index("--out") + 1]
            names = freeze(argv[1], out)
            return emit("pass", f"anim fast turns: {len(names)} clip(s) made before the rule frozen in {out.replace(os.sep, '/')}",
                        "none - the list is never extended", clips=names)
        if argv[0] == "table":
            rows = []
            for stem, c in _clips(argv[1]):
                r = read(c)
                if r["over"]:
                    rows.append({"name": str(c.get("name") or stem), **r["over"][0], "frames_over": len(r["over"])})
            rows.sort(key=lambda x: -x["deg"])
            return emit("pass", f"anim fast turns: {len(rows)} clip(s) turn a joint over {LIMIT:g} degrees between two frames"
                        + (": " + ", ".join(f"{x['name']} {x['deg']:g}" for x in rows[:5]) if rows else ""),
                        "none" if not rows else "ease those swings, or declare the step", rows=rows)
        with open(argv[0], encoding="utf-8") as fh:
            c = json.load(fh)
        r = read(c)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim fast turns: it could not be read ({type(e).__name__}: {e})", "python kit/anim/fast_turns.py <clip.json>")
    name = str(c.get("name"))
    if r["over"]:
        return emit("fail", "anim fast turns " + words(name, r), "ease the swing over more frames, or declare the step", **r)
    w = r["worst"]
    return emit("pass", f"anim fast turns {name}: the fastest turn is {w['joint']} at {w['deg']:g} degrees a frame" if w
                else f"anim fast turns {name}: nothing turns", "none", **r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
