"""finish.py — ONE FINISHING CONTRACT for every route (the owner's limitations list 2026-11-15, A-R09 / AN-10: "curve
tools do not establish one finishing contract across every route ... imported, keyed and procedural work can still
receive different finishing treatment").

Any source the build knows - a move, a keyframe spec, a gait, an import, a pose file, a bake - may say

    "finish": {"filter":   {"hz": 8, "joints": ["Head"], "keep": [0.43], "soften": false},      (kit/anim/curves.py)
               "velocity": {"max_deg_s": 1400, "joints": ["Right Arm"]},
               "handles":  [{"from": 0.20, "to": 0.43, "out": [0.6, 0.0], "in": [0.2, 1.0]}],   (kit/anim/curves.py)
               "overshoot": {"max_deg": 12}}

and the build applies it at ONE place, to the R6 clip (a keyed or imported clip: its fold to R6), after the route
has made its clip and before anything reads it (kit/cmd/anim.luau
AnimCmd.finish -> `python kit/anim/finish.py apply`), always in this order: filter, velocity, handles, then the checks.

    python kit/anim/finish.py apply <clip.json> --out <clip.json>      the clip's own "finish", applied and stamped
    python kit/anim/finish.py measure <clip.json>                      what every route's clip is measured by

THE CONTRACT (what a finish may never do, whatever the route; a finish that breaks it is REFUSED, named):
  - the clip keeps its length, its frame count and every event at its time;
  - the pose at the first frame, the last frame, EVERY event, the edges of every contact the clip means
    ("contact") and every time its filter keeps is exactly what the route made (to 1e-6);
  - no hand ends further from the weapon than the route had it, measured against the route's own clip after ALL the
    controls (not one control at a time);
  - what kit/anim/curves.py refuses stays refused (a hand taken off the weapon, a tenth off the cut, a stepped clip
    filtered, a Hit inside a re-timed stretch, a stretch made more than twice as fast).
THE CONTROLS:
  filter     a signal filter with the kept moments exact (curves.op_filter)
  velocity   no named joint (default: every joint) turns faster than max_deg_s: the joints over it are filtered,
             gently first (14, 11, 8, 6, 4 times a second) until they are under it; a joint that is still over it
             (its fastest frame is a kept moment) refuses the finish
  handles    the timing of a stretch along a bezier (curves.op_handles): the spacing
  overshoot  an ENVELOPE, checked last: after its last Hit no joint may swing back out further than max_deg from the
             pose it settles in once it has arrived there (within 5 degrees); over it refuses the finish
THE SAME NUMBERS FOR EVERY ROUTE (`measure`, and the build's metrics for every clip): each joint's fastest turn
(degrees a second), its roughness (curves.roughness) and its overshoot after the last Hit.

THE GATE (kit/anim/metrics.py): a clip that ASKS for a finish and does not carry its stamp fails - a route can never
quietly skip it. A stamped clip is not finished twice; a clip stamped for ANOTHER ask says so (build the clip again).
NOT BUILT: adding overshoot or anticipation where a route made none (the envelope only limits), per-joint spacing
other than one stretch's handles, a finish on a prop's clip."""
import copy
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

KEYS = ("filter", "velocity", "handles", "overshoot")
LADDER = (14.0, 11.0, 8.0, 6.0, 4.0)     # the filters a velocity cap tries, gentlest first (times a second)
ARRIVED = 5.0                            # degrees from its settle pose at which a joint has arrived
EXACT = 1e-6


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def stamp(ask):
    """the mark a finished clip carries for the ask that finished it"""
    return hashlib.sha256(json.dumps(ask, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def check(ask):
    """a finish that can be read, or ValueError naming what is wrong with it"""
    if not isinstance(ask, dict) or not ask:
        raise ValueError("\"finish\" is {\"filter\": {...}, \"velocity\": {\"max_deg_s\": n}, \"handles\": [...], \"overshoot\": {\"max_deg\": n}}")
    for k in ask:
        if k not in KEYS:
            raise ValueError(f"\"finish\" has no \"{k}\" (it has: {', '.join(KEYS)})")
    if "filter" in ask and not isinstance(ask["filter"], dict):
        raise ValueError("\"finish\".\"filter\" is {\"hz\": n, \"joints\": [...], \"keep\": [seconds], \"soften\": bool}")
    v = ask.get("velocity")
    if "velocity" in ask and not (isinstance(v, dict) and isinstance(v.get("max_deg_s"), (int, float)) and not isinstance(v["max_deg_s"], bool)
                                  and v["max_deg_s"] == v["max_deg_s"] and v["max_deg_s"] > 0):
        raise ValueError("\"finish\".\"velocity\" is {\"max_deg_s\": a number above 0, \"joints\": [...]}")
    h = ask.get("handles")
    if "handles" in ask and not (isinstance(h, list) and h and all(isinstance(x, dict) and "from" in x and "to" in x for x in h)):
        raise ValueError("\"finish\".\"handles\" is a list of {\"from\": s, \"to\": s, \"out\": [x, y], \"in\": [x, y]}")
    o = ask.get("overshoot")
    if "overshoot" in ask and not (isinstance(o, dict) and isinstance(o.get("max_deg"), (int, float)) and not isinstance(o["max_deg"], bool)
                                   and o["max_deg"] == o["max_deg"] and o["max_deg"] >= 0):
        raise ValueError("\"finish\".\"overshoot\" is {\"max_deg\": a number, 0 or more}")
    return ask


def _quats(clip, joint):
    q = np.array([f[:4] for f in clip["joints"][joint]["frames"]], float)
    return q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)


def _angle(a, b):
    return np.degrees(2.0 * np.arccos(np.clip(np.abs(np.sum(a * b, axis=-1)), 0.0, 1.0)))


def _hits(clip, fps, n):
    return sorted({min(n - 1, max(0, int(round(float(e["t"]) * fps)))) for e in clip.get("events") or []
                   if isinstance(e, dict) and e.get("name") == "Hit" and isinstance(e.get("t"), (int, float))})


def _moments(clip):
    """the times a finish keeps exact besides the two ends: EVERY event, the edges of every contact the clip means,
    and the times its own filter keeps -> [seconds]"""
    out = [float(e["t"]) for e in clip.get("events") or [] if isinstance(e, dict) and isinstance(e.get("t"), (int, float))]
    for c in clip.get("contact") or []:
        if isinstance(c, dict):
            out += [float(c[k]) for k in ("from", "to") if isinstance(c.get(k), (int, float)) and math.isfinite(c[k])]
    ask = clip.get("finish") if isinstance(clip.get("finish"), dict) else {}
    f = ask.get("filter") if isinstance(ask.get("filter"), dict) else {}
    out += [float(t) for t in (f.get("keep") or []) if isinstance(t, (int, float))]
    return sorted({t for t in out if 0.0 <= t <= float(clip["times"][-1]) + 1e-9})


def measure(clip):
    """the numbers every route's clip is measured by -> {"fps", "joints": {joint: {"peak_deg_s", "peak_frame",
    "roughness", "overshoot_deg"}}, "peak_deg_s", "overshoot_deg"}"""
    import clip as C
    import curves as CV
    fps = C.clip_fps(clip)
    n = len(clip["times"])
    hits = _hits(clip, fps, n)
    out = {}
    for j, jd in clip["joints"].items():
        if not jd.get("frames") or len(jd["frames"]) != n:
            continue
        q = _quats(clip, j)
        turn = _angle(q[1:], q[:-1]) * fps if n > 1 else np.zeros(0)
        over = 0.0
        if hits and hits[-1] < n - 1:
            away = _angle(q[hits[-1]:], q[-1][None, :])          # how far from its settle pose, from the last Hit on
            there = np.nonzero(away <= ARRIVED)[0]
            if len(there):
                over = float(away[there[0]:].max())
        out[j] = {"peak_deg_s": round(float(turn.max()) if len(turn) else 0.0, 1),
                  "peak_frame": int(np.argmax(turn)) + 1 if len(turn) else 0,
                  "roughness": round(float(CV.roughness(clip, j)), 3) if n > 2 else 0.0,
                  "overshoot_deg": round(over, 2)}
    return {"fps": fps, "joints": out, "peak_deg_s": max([v["peak_deg_s"] for v in out.values()] or [0.0]),
            "overshoot_deg": max([v["overshoot_deg"] for v in out.values()] or [0.0])}


def kept(before, after):
    """THE CONTRACT: what a finish may never change -> None, or the words for what it changed"""
    if len(after["times"]) != len(before["times"]) or any(abs(a - b) > EXACT for a, b in zip(after["times"], before["times"])):
        return "it changed the clip's length or its frames' times"
    ea = [(e.get("name"), round(float(e.get("t", 0)), 6)) for e in after.get("events") or [] if isinstance(e, dict)]
    eb = [(e.get("name"), round(float(e.get("t", 0)), 6)) for e in before.get("events") or [] if isinstance(e, dict)]
    if ea != eb:
        return "it moved or lost an event"
    import clip as C
    n = len(before["times"])
    fps = C.clip_fps(before)
    held = sorted({0, n - 1, *[min(n - 1, max(0, int(math.floor(t * fps + 0.5)))) for t in _moments(before)]})
    for j, jd in before["joints"].items():
        if not jd.get("frames"):
            continue
        A, B = np.array(after["joints"][j]["frames"], float), np.array(jd["frames"], float)
        for i in held:
            same = np.allclose(A[i], B[i], atol=EXACT) or (np.allclose(A[i][:4], -B[i][:4], atol=EXACT) and np.allclose(A[i][4:], B[i][4:], atol=EXACT))
            if not same:
                what = "first frame" if i == 0 else "last frame" if i == n - 1 else f"kept moment at frame {i}"
                return f"it changed {j}'s pose at the {what}"
    return None


def apply(clip):
    """the clip with its own "finish" applied, stamped ("finished", "finish_log") -> a new clip. Raises ValueError
    naming a finish that cannot be read, one a control refuses, or one that breaks the contract"""
    import curves as CV
    ask = check(clip.get("finish"))
    mark = stamp(ask)
    if clip.get("finished") == mark:
        return clip                                              # (finished for this very ask: never twice)
    if clip.get("finished"):
        raise ValueError("it was finished for another \"finish\" than it asks for now: build the clip again from its "
                         "source (a finish cannot be taken back out)")
    if clip.get("prop"):
        raise ValueError("a prop's clip is not finished (its parts move only as its joints allow)")
    if clip.get("rig") != "R6":
        raise ValueError(f"a finish is applied to the R6 clip (this one is {clip.get('rig')}: the build finishes its fold)")
    before = clip
    c = copy.deepcopy(clip)
    log = []

    def listed(v):                                               # (an empty list comes back from Lune as an empty map)
        return None if v is None or v == {} or v == [] else v
    keep = tuple(_moments(clip))
    if "filter" in ask:
        f = ask["filter"]
        log.append(CV.op_filter(c, f.get("hz", 8.0), listed(f.get("joints")), keep, f.get("ease", CV.EASE_S), bool(f.get("soften"))))
    if "velocity" in ask:
        cap = float(ask["velocity"]["max_deg_s"])
        names = listed(ask["velocity"].get("joints")) or [j for j, jd in c["joints"].items() if jd.get("frames")]
        unknown = [j for j in names if j not in c["joints"]]
        if unknown:
            raise ValueError(f"\"finish\".\"velocity\" names {unknown[0]}, which this clip does not key")
        was = measure(c)["joints"]
        over = [j for j in names if was[j]["peak_deg_s"] > cap]
        fast, used, start = list(over), None, c
        for hz in LADDER:
            if not fast:
                break
            # (each rung filters the clip as it was BEFORE this control, with the filter's own refusals standing: a
            # rung laid on the last one would be judged against that one, and a hand could leave the weapon by steps)
            c = copy.deepcopy(start)
            CV.op_filter(c, hz, over, keep, CV.EASE_S, bool(ask["velocity"].get("soften")))
            used = hz
            now = measure(c)["joints"]
            fast = [j for j in over if now[j]["peak_deg_s"] > cap]
        if fast:
            now = measure(c)["joints"]
            j = max(fast, key=lambda x: now[x]["peak_deg_s"])
            raise ValueError(f"velocity: {j} still turns {now[j]['peak_deg_s']:.0f} degrees a second at frame {now[j]['peak_frame']} "
                             f"(at most {cap:g}) after the strongest filter - a filter takes out shake, not a fast smooth "
                             "motion or a kept moment: re-time that stretch (handles), or raise the cap")
        log.append(f"velocity: no joint over {cap:g} degrees a second" + (f" (filtered down to {used:g} a second)" if used else " (none was)"))
    for h in ask.get("handles") or []:
        log.append(CV.op_handles(c, h["from"], h["to"], h.get("out", (1 / 3, 1 / 3)), h.get("in", (2 / 3, 2 / 3))))
    broke = kept(before, c)
    if broke:
        raise ValueError(f"the finish breaks the contract: {broke}")
    # against the ROUTE's clip, after every control: no hand further from the weapon, no named joint over its cap
    off = CV._further(CV._hands_off_frames(before), CV._hands_off_frames(c)) if isinstance(before.get("sword"), dict) else None
    if off:
        raise ValueError(f"the finish breaks the contract: it takes the {off[0]} from {off[1]:.2f} to {off[2]:.2f} studs off the "
                         f"weapon at frame {off[3]} (all its controls together; the blade is not finished: it is what the hands hold)")
    if "velocity" in ask:
        cap = float(ask["velocity"]["max_deg_s"])
        now = measure(c)["joints"]
        names = listed(ask["velocity"].get("joints")) or list(now)
        fast = [j for j in names if j in now and now[j]["peak_deg_s"] > cap + 1e-6]
        if fast:
            j = max(fast, key=lambda x: now[x]["peak_deg_s"])
            raise ValueError(f"velocity: after the handles {j} turns {now[j]['peak_deg_s']:.0f} degrees a second at frame "
                             f"{now[j]['peak_frame']} (at most {cap:g}): the re-timed stretch is too fast for the cap")
    if "overshoot" in ask:
        m = measure(c)
        most = float(ask["overshoot"]["max_deg"])
        j = max(m["joints"], key=lambda x: m["joints"][x]["overshoot_deg"]) if m["joints"] else None
        if j and m["joints"][j]["overshoot_deg"] > most:
            raise ValueError(f"overshoot: {j} swings back out {m['joints'][j]['overshoot_deg']:.1f} degrees from where it settles "
                             f"after the last Hit (at most {most:g})")
        log.append(f"overshoot: within {most:g} degrees (the most: {m['overshoot_deg']:.1f})")
    c["finished"] = mark
    c["finish_log"] = [str(x) for x in log]
    return c


def gate(clip):
    """what the build's motion gates add for this clip (kit/anim/metrics.py) -> (the reading for metrics.json, the
    problem or None): the same numbers for every route's clip, and a clip that asks for a finish it does not carry"""
    if clip.get("prop") or not isinstance(clip.get("joints"), dict) or not clip.get("times"):
        return None, None
    try:
        m = measure(clip)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {"error": f"{type(e).__name__}: {e}"}, None
    out = {"peak_deg_s": m["peak_deg_s"], "overshoot_deg": m["overshoot_deg"], "joints": m["joints"],
           "applied": clip.get("finish_log") if clip.get("finished") else None}
    ask = clip.get("finish")
    if ask is None or clip.get("rig") != "R6":                   # (the finish is the R6 clip's: a keyed or imported
        return out, None                                         # clip is finished as its fold)
    try:
        mark = stamp(check(ask))
    except ValueError as e:
        return out, str(e)
    if clip.get("finished") != mark:
        return out, ("it asks for a finish (\"finish\") and does not carry it - "
                     + ("it was finished for another ask: build the clip again from its source" if clip.get("finished")
                        else "its route did not apply one: every route's clip is finished by the build (kit/anim/finish.py)"))
    return out, None


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if len(argv) < 2 or argv[0] not in ("apply", "measure"):
        print(__doc__)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            clip = json.load(fh)
        if argv[0] == "measure":
            m = measure(clip)
            return emit("pass", f"{clip.get('name')}: fastest turn {m['peak_deg_s']:.0f} degrees a second, overshoot after the "
                        f"last Hit {m['overshoot_deg']:.1f} degrees", "none", reading=m)
        out = flag(argv, "--out")
        if not out:
            return emit("fail", "finish apply: --out <clip.json>", "python kit/anim/finish.py")
        done = apply(clip)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"finish: {e}", "fix the \"finish\" named, or the clip")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(done, fh)
    os.replace(tmp, out)
    return emit("pass", f"finish {clip.get('name')}: " + "; ".join(done.get("finish_log") or ["nothing to do"]), "none", clip=out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
