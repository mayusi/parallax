"""foot_modes.py — WHAT EACH FOOT IS DOING (the owner's older list, AN-26: "contact modes need shared semantics across
authoring and gates. Distinguish plant, pivot, scrape, roll, airborne and intentional skid ... deliberate sliding
passes while accidental skating is caught without bespoke threshold exceptions").

Before this the build knew one thing about a foot on the floor: it may not move more than `foot_slide` studs in a
frame (kit/anim/clip.py). A move that MEANS to slide - a skid to a stop, a dash dragged along the floor, a roll -
could only pass by raising that bar for the whole clip ("gate": {"foot_slide": 10}): 424 of the clips built here do,
and with it every other frame of the clip stops being checked.

    python kit/anim/foot_modes.py <clip.json>            what each foot does, stretch by stretch
    python kit/anim/foot_modes.py survey <built clips>   how many clips raise the bar instead (read only)

THE MODES, read off the R6 clip where the world sees the feet (the clip's own travel carried), per foot, per stretch:
  airborne   the sole is more than CONTACT studs off the ground
  plant      on the ground and still (no frame moves it more than the foot_slide bar)
  pivot      on the ground, still, and the leg turns on the spot (PIVOT degrees or more over the stretch)
  slide      on the ground and moving more than the bar in a frame
  stance     an in-place locomotion clip's grounded foot (a walk, a run): it rides the ground back at the ground's
             speed, and the gate holds it to THAT (skate, skid) - it is never a slide and says none
A slide is a FAULT (skating) unless the move says it:
    "slides": [{"foot": "Right Leg" | "Left Leg" | "both", "from": seconds, "to": seconds,
                "kind": "skid" | "drag" | "scrape" | "roll"}]
in the move, the keyframe spec or the clip. Inside a said stretch that foot's slide is not judged; everywhere else it
is, at the ordinary bar. So the bar stays where it is and the exception is a stretch with a name, not a number.
A said slide must BE one, and no more than one: a stretch in which the foot does not slide ON THE FLOOR is refused
(said and not there), and so is one wider than the slide (more than SLACK frames past it, or with a planted stretch
inside) - a clip cannot switch its feet off by declaring everything, and one real slide does not excuse a second.
The bar "is it a slide" is judged at is the kit's (or the clip's own when LOWER): a clip that raises its bar and
says a slide is told the slide by the ordinary one. A recipe that changes a clip's time (`kit anim derive`: retime,
trim, hold ...) drops the slides its source said - they are seconds - and says so: say them again in the recipe. "kind" is a word for the reader (and for
the effects that follow a foot: dust on a skid); the check treats the four alike.
WHAT R6 CANNOT SHOW: a foot ROLLING heel to toe or scraping on its edge - the leg is one block, its sole is flat on
the floor or it is not. Those two words are kept so a move can say what it stands for; nothing measures them.
NOT DONE: clips already built keep their raised bars (they are not mine to rebuild); `survey` counts them."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

PIVOT = 20.0         # degrees a still foot's leg turns over a stretch for it to be a pivot
SLACK = 3            # frames a said slide may reach past where the foot slides (and stand still inside it)
KINDS = ("skid", "drag", "scrape", "roll")
FEET = ("Right Leg", "Left Leg")
WORD = {"Right Leg": "right foot", "Left Leg": "left foot"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def said(clip):
    """the slides a clip says it means -> [(foot, from, to, kind)], one row a foot ("both" is two rows).
    ValueError on one that cannot be read"""
    spec = clip.get("slides")
    if spec is None:
        return []
    shape = ('"slides" is a list of {"foot": "Right Leg" | "Left Leg" | "both", "from": seconds, "to": seconds, '
             '"kind": "skid" | "drag" | "scrape" | "roll"}')
    if not isinstance(spec, list):
        raise ValueError(shape)
    out = []
    for s in spec:
        if not isinstance(s, dict):
            raise ValueError(shape)
        foot, kind, a, b = s.get("foot"), s.get("kind"), s.get("from"), s.get("to")
        if foot not in FEET + ("both",):
            raise ValueError(f"a slide names its foot - \"Right Leg\", \"Left Leg\" or \"both\" (it says {foot!r})")
        if kind not in KINDS:
            raise ValueError(f"a slide says its kind - {', '.join(KINDS)} (it says {kind!r})")
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (a, b))
                or a < 0 or b <= a):
            raise ValueError(f"the slide of {foot}: \"from\" and \"to\" are seconds from the clip's start, the end after the start")
        for f in (FEET if foot == "both" else (foot,)):
            out.append((f, float(a), float(b), kind))
    return out


def _fps(times):
    t = np.asarray(times, float)
    return 1.0 / max(float(np.median(np.diff(t))), 1e-9) if len(t) > 1 else 30.0


def meant(clip, n, times):
    """per foot, the frames a said slide covers -> {foot: bool [n]} (a frame pair i -> i + 1 is covered when both are).
    A stretch's ends are frames: a time is taken to the nearest frame (a clip's times are rounded to six places -
    19 / 60 said as a float fell a hair before the frame it names)"""
    out = {f: np.zeros(n, bool) for f in FEET}
    t = np.asarray(times, float)
    half = 0.5 / _fps(t)
    for foot, a, b, _kind in said(clip):
        out[foot] |= (t >= a - half) & (t <= b + half)
    return out


def own_bar(clip):
    """the bar a foot is judged at: the kit's, or the clip's own when it is LOWER (a raised bar does not make a slide
    less of one)"""
    import clip as C
    g = clip.get("gate") if isinstance(clip.get("gate"), dict) else {}
    own = g.get("foot_slide")
    kit = float(C.GATES["foot_slide"])
    return min(kit, float(own)) if isinstance(own, (int, float)) and not isinstance(own, bool) and own > 0 else kit


def track(clip, rig, bar, frames=None):
    """what the build's gate itself looks at (kit/anim/clip.py), per foot -> {foot: {"contact": bool [n], "step": [n],
    "moving": bool [n], "heading": [n]}}, the ground. step[i]: the sole's move from frame i to i + 1 along the floor,
    a stepped clip's landing spread over its held frames; a blocking file's holds are not judged (they are 0)"""
    import clip as C
    frames = frames if frames is not None else C.world_frames(clip, rig)
    n = len(frames)
    feet = [f for f in FEET if n and f in frames[0]]
    if not feet:
        return {}, None
    sole = {f: np.array([0.0, -rig["sizes"][f][1] / 2, 0.0, 1.0]) for f in feet}
    pos = {f: np.array([(frames[i][f] @ sole[f])[:3] for i in range(n)]) for f in feet}
    ground = C.rest_ground(rig, C.feet_of(rig))
    if ground is None:
        ground = min(float(pos[f][:, 1].min()) for f in feet)
    holds = C.step_holds(clip)
    out = {}
    for f in feet:
        contact = pos[f][:, 1] < ground + C.CONTACT
        step = np.zeros(n)
        for i in range(n - 1):
            d = float(math.hypot(*(pos[f][i + 1] - pos[f][i])[[0, 2]]))
            if (i + 1) in holds:
                d = 0.0 if holds[i + 1] <= 1 else d / holds[i + 1]
            step[i] = d
        moving = np.zeros(n, bool)
        for i in range(n - 1):
            if contact[i] and contact[i + 1] and step[i] > bar:
                moving[i] = moving[i + 1] = True
        heading = np.degrees(np.unwrap(np.array([math.atan2(float(frames[i][f][0, 2]), float(frames[i][f][2, 2])) for i in range(n)])))
        out[f] = {"contact": contact, "step": step, "moving": moving, "heading": heading}
    return out, float(ground)


def in_place(clip):
    """an in-place locomotion clip (a walk, a run): its planted feet MOVE, at the ground's speed - they are held to
    that speed by the gate's skate and skid checks, never to "does not move" """
    loco = clip.get("locomotion")
    return isinstance(loco, dict) and bool(loco.get("speed"))


def read(clip, rig=None, bar=None, frames=None):
    """-> {"ground", "bar", "feet": {foot: [{"mode", "from", "to", "studs", "worst", "turn_deg", "said"}]}} - every
    foot's clip cut into stretches of one mode (frames inclusive). worst: the most it moves in one frame.
    An in-place locomotion clip's grounded stretches are "stance" (the foot rides the ground back): never a slide"""
    import clip as C
    rig = rig or C.load_rig("r6")
    if clip.get("rig") != "R6":
        raise ValueError(f"it is a {clip.get('rig')} clip - the feet are read on the R6 clip")
    bar = float(bar if bar is not None else own_bar(clip))
    tr, ground = track(clip, rig, bar, frames)
    if not tr:
        return {"ground": None, "bar": bar, "feet": {}}
    n = len(next(iter(tr.values()))["contact"])
    times = clip.get("times") if isinstance(clip.get("times"), list) and len(clip["times"]) == n else list(range(n))
    covered = meant(clip, n, times)
    loco = in_place(clip)
    out = {}
    for f, t in tr.items():
        step = t["step"]
        state = ["airborne" if not t["contact"][i] else "stance" if loco else "slide" if t["moving"][i] else "plant" for i in range(n)]
        rows, i = [], 0
        while i < n:
            j = i
            while j + 1 < n and state[j + 1] == state[i]:
                j += 1
            mode = state[i]
            turn = float(abs(t["heading"][j] - t["heading"][i]))
            if mode == "plant" and turn >= PIVOT:
                mode = "pivot"
            rows.append({"mode": mode, "from": i, "to": j,
                         "studs": round(float(step[i:j].sum()), 3), "worst": round(float(step[i:j].max()) if j > i else 0.0, 3),
                         "turn_deg": round(turn, 1), "said": bool(covered[f][i:j + 1].all()) if mode == "slide" else False})
            i = j + 1
        out[f] = rows
    return {"ground": round(float(ground), 3), "bar": bar, "feet": out}


def stale(clip, rig=None, bar=None, frames=None):
    """what is wrong with the slides a clip says -> [words]. A said slide must BE one, and no more than one:
    the foot slides ON THE FLOOR inside it (a foot in the air is not sliding), and the stretch is the slide - one
    that reaches SLACK frames past where the foot slides, or holds a second planted stretch, is refused (it would
    excuse whatever else the foot does in there). An in-place locomotion clip says none: its feet are held to the
    ground's speed"""
    import clip as C
    rig = rig or C.load_rig("r6")
    rows = said(clip)
    if not rows:
        return []
    if in_place(clip):
        return ["it is an in-place locomotion clip: its feet are held to the ground's speed (skate, skid), not to "
                "\"slides\" - take them out"]
    bar = min(float(bar), own_bar(clip)) if bar is not None else own_bar(clip)
    tr, _ground = track(clip, rig, bar, frames)
    times = np.asarray(clip["times"], float)
    n = len(times)
    half = 0.5 / _fps(times)
    out = []
    for foot, a, b, kind in rows:
        if foot not in tr:
            out.append(f"a {kind} is said for the {foot} and the clip has no such leg")
            continue
        idx = [i for i in range(n) if a - half <= times[i] <= b + half]
        if len(idx) < 2:
            out.append(f"the {kind} said for the {WORD[foot]} from {a:g} to {b:g} s covers no two frames of the clip "
                       f"(it is {times[-1]:.2f} s long)")
            continue
        moving = tr[foot]["moving"]
        slid = [i for i in idx if moving[i]]
        if not slid:
            worst = max(float(tr[foot]["step"][i]) for i in idx[:-1] if tr[foot]["contact"][i] and tr[foot]["contact"][i + 1]) \
                if any(tr[foot]["contact"][i] and tr[foot]["contact"][i + 1] for i in idx[:-1]) else 0.0
            out.append(f"the {kind} said for the {WORD[foot]} from {a:g} to {b:g} s is not there: on the floor the foot "
                       f"moves {worst:.2f} studs a frame at the most ({bar:g} is a planted foot's bar) - take it out")
            continue
        first, last = slid[0], slid[-1]
        gaps = [i for i in range(first, last + 1) if not moving[i]]
        if first - idx[0] > SLACK or idx[-1] - last > SLACK or len(gaps) > SLACK:
            out.append(f"the {kind} said for the {WORD[foot]} from {a:g} to {b:g} s (frames {idx[0]}-{idx[-1]}) is wider "
                       f"than the slide: the foot slides over frames {first}-{last}"
                       + (f", with {len(gaps)} frame(s) in between where it does not" if len(gaps) > SLACK else "")
                       + f" - say that stretch ({times[first]:.3f} to {times[last]:.3f} s), one slide a row")
    return out


def words(r, name):
    said_n = sum(1 for rows in r["feet"].values() for x in rows if x["mode"] == "slide" and x["said"])
    faults = [(f, x) for f, rows in r["feet"].items() for x in rows if x["mode"] == "slide" and not x["said"]]
    pivots = sum(1 for rows in r["feet"].values() for x in rows if x["mode"] == "pivot")
    head = f"{name}: " + ", ".join(
        f"the {WORD[f]} " + " / ".join(f"{x['mode']} {x['from']}-{x['to']}" for x in rows) for f, rows in r["feet"].items())
    tail = f" ({pivots} pivot(s), {said_n} said slide(s))"
    if faults:
        f, x = max(faults, key=lambda p: p[1]["worst"])
        tail += (f"; SLIDES UNSAID: the {WORD[f]} moves {x['studs']:.2f} studs over frames {x['from']}-{x['to']} "
                 f"({x['worst']:.2f} in one frame; a planted foot's bar is {r['bar']:g})")
    return head + tail


def survey(folder):
    """the built clips that pass a slide by raising their own bar -> counts (read only)"""
    import glob
    import clip as C
    n = raised = off = why = saying = 0
    for path in sorted(glob.glob(os.path.join(folder, "*.clip.json"))):
        with open(path, encoding="utf-8") as fh:
            try:
                c = json.load(fh)
            except ValueError:
                continue
        if not isinstance(c, dict) or c.get("rig") != "R6":
            continue
        n += 1
        g = c.get("gate") if isinstance(c.get("gate"), dict) else {}
        bar = g.get("foot_slide")
        if isinstance(bar, (int, float)) and bar > C.GATES["foot_slide"]:
            raised += 1
            off += 1 if bar >= 1.0 else 0
            why += 1 if g.get("why_foot_slide") else 0
        saying += 1 if c.get("slides") else 0
    return {"clips": n, "raise_the_bar": raised, "to_a_stud_or_more": off, "with_a_reason": why, "say_their_slides": saying}


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "survey":
            s = survey(argv[1])
            return emit("pass", f"anim feet: of {s['clips']} built R6 clips {s['raise_the_bar']} raise their foot-slide bar "
                        f"({s['to_a_stud_or_more']} to a stud or more: the check is off; {s['with_a_reason']} give a reason); "
                        f"{s['say_their_slides']} say their slides", "a move that means to slide says so (\"slides\") and "
                        "keeps the ordinary bar", **s)
        with open(argv[0], encoding="utf-8") as fh:
            c = json.load(fh)
        r = read(c)
        old = stale(c)
        g = c.get("gate") if isinstance(c.get("gate"), dict) else {}
        theirs = g.get("foot_slide") if isinstance(g.get("foot_slide"), (int, float)) and not isinstance(g.get("foot_slide"), bool) else None
        worst = max([x["worst"] for rows in r["feet"].values() for x in rows if x["mode"] == "slide" and not x["said"]] or [0.0])
        raised = theirs is not None and theirs > r["bar"] and worst <= theirs      # (the build passes it: under its raised bar)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim feet: it could not be read ({type(e).__name__}: {e})",
                    "python kit/anim/foot_modes.py <clip.json>")
    name = str(c.get("name"))
    unsaid = [x for rows in r["feet"].values() for x in rows if x["mode"] == "slide" and not x["said"]]
    if old:
        return emit("fail", f"anim feet {name}: {'; '.join(old)}", "take the slide that is not there out of \"slides\"", feet=r["feet"])
    if unsaid and raised:                                # (the build passes it: its own bar is raised)
        return emit("pass", f"anim feet: {words(r, name)} - the build does not fail it: the clip raises its own bar to "
                    f"{c['gate']['foot_slide']:g}", "say the slide (\"slides\") and take the raised bar out of \"gate\"", feet=r["feet"])
    if unsaid:
        return emit("fail", f"anim feet: {words(r, name)}", "plant the foot there (key the body over it), or - if the move "
                    "means it - say it: \"slides\": [{\"foot\": ..., \"from\": s, \"to\": s, \"kind\": \"skid\"}]", feet=r["feet"])
    return emit("pass", f"anim feet: {words(r, name)}", "none - proceed", feet=r["feet"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
