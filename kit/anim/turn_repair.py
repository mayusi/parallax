"""turn_repair.py — THE REPAIR FOR A JOINT THAT TURNS FASTER THAN THE FRAMES CAN CARRY (kit/anim/fast_turns.py's
"NOT DONE"; LIMITATIONS_FIXES_V3 Stage E / card gtut: the 44 clips frozen over 90 degrees a frame, "breakdown keys
(<= 76 deg/f)").

fast_turns.py fails a clip whose joint turns more than 90 degrees between two stored frames: near half a circle
the short way and the long way are the same length, so the engine's way round is not defined, and at 60 frames a
second it is a turn of 5400 degrees a second. Two repairs, in this order, and nothing else:
  1. FRAMES BETWEEN (a clip stored at under 60 a second): one frame between every two, its duration kept - the
     engine already plays the in-between, so the motion seen does not change, except that a near-half-turn step now
     goes the way the joint was turning (below). Nine of the 44 are 30-a-second clips.
  2. EASED OVER MORE FRAMES (a turn still over TARGET): the step is spread over k frames (k = the turn / TARGET,
     rounded up) and the clip grows by (k - 1) frames there; every event, beat, stepped window and the duration
     after it move with it. The poses the clip had are all still in it, at the same order; only time is added.
WHICH WAY ROUND: a step is taken the way the joint was turning in the frames on either side of it (the sum of its
turns before and after, as rotation vectors in the parent's space): mostly the short way; when the neighbours
turn the other way, the long way - said in the reading (`long_way`), since it is what changes the look.
TARGET is the fastest turn among all the clips the owner loved (76, HqM1b), not the gate's 90.
HELD TO EVERY OTHER GATE: the repaired copy is read by the build's whole motion gates (kit/anim/metrics.py) beside
the clip as it was, and each problem the repair ADDED is said (`added`). Measured 2026-11-17 on the 44 frozen clips
(copies in a scratch folder): 42 repaired under the limit; 22 of them clean, 20 with something added - the weapon
out of the off hand for 1 to 13 frames (a two-handed grip: each arm and the weapon eased on its own path do not
stay together), a one-frame pop beside the eased step, a hand into a leg or a leg under the ground. Those want the
in-betweens SOLVED (the hands to the weapon: grip_solve; the body clear: collide_repair - V3 §9.6), not eased.
NOT a judgement of the look, and not run on any built clip by itself: `python kit/anim/turn_repair.py <clip>
--out <file>` writes a repaired copy; the build keeps its clips as they are. (A stepped clip's declared steps are
not judged by the gate and not repaired here.)

    python kit/anim/turn_repair.py <clip.json> [--out <repaired.clip.json>]
    python kit/anim/turn_repair.py table <folder> <name>... [--out <dir>]     several, read only unless --out"""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import fast_turns as FT  # noqa: E402

TARGET = 76.0        # degrees between two frames after the repair (the fastest loved turn)
NEAR = 150.0         # degrees from which a step may be the long way round (short of it, the short way is the move)
SIDE = 10.0          # degrees the joint's turns on either side must add up to, to say which way it was turning
FPS = 60             # a clip stored slower than this is first given frames between


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _rotvec(qa, qb):
    """the turn from a to b in the parent's space as a rotation vector (axis * radians, the short way)"""
    R = C.quat_mat(qb) @ C.quat_mat(qa).T
    q = np.asarray(C.mat_quat(R), float)
    if q[3] < 0:
        q = -q
    s = float(np.linalg.norm(q[:3]))
    if s < 1e-12:
        return np.zeros(3)
    return q[:3] / s * 2.0 * math.atan2(s, float(q[3]))


def _turn(qa, v, u):
    """a turned by the fraction u of the rotation vector v (parent's space) -> a quaternion"""
    ang = float(np.linalg.norm(v)) * u
    if ang < 1e-12:
        return list(qa)
    ax = v / np.linalg.norm(v)
    h = ang / 2
    dq = [*(ax * math.sin(h)), math.cos(h)]
    return list(C.mat_quat(C.quat_mat(dq) @ C.quat_mat(qa)))


def _path(frames, i):
    """the rotation vector for the step frames[i-1] -> frames[i]: the short way, or the long way when the joint's
    turns on either side of it go that way"""
    a, b = frames[i - 1][:4], frames[i][:4]
    v = _rotvec(a, b)
    ang = float(np.linalg.norm(v))
    if ang < math.radians(NEAR):
        return v, False
    side = np.zeros(3)
    if i >= 2:
        side += _rotvec(frames[i - 2][:4], a)
    if i + 1 < len(frames):
        side += _rotvec(b, frames[i + 1][:4])
    if float(np.linalg.norm(side)) < math.radians(SIDE) or float(np.dot(side, v)) >= 0:
        return v, False
    return -(v / ang) * (2 * math.pi - ang), True


def _between(f0, f1, v, u):
    """a frame u of the way from f0 to f1 along the rotation vector v; its place in a straight line"""
    q = _turn(f0[:4], v, u)
    p = [f0[4 + k] + (f1[4 + k] - f0[4 + k]) * u for k in range(3)] if len(f0) >= 7 else []
    return [round(float(x), 6) for x in list(q) + p]


def _tracks(clip):
    """the per-frame turn tracks a clip carries -> [(label, list)]"""
    out = [(name, j["frames"]) for name, j in (clip.get("joints") or {}).items()
           if isinstance(j, dict) and isinstance(j.get("frames"), list)]
    for key in ("root", "grip", "grip_left"):
        if isinstance(clip.get(key), list):
            out.append((key, clip[key]))
    for name, pr in (clip.get("props") or {}).items():
        if isinstance(pr, dict) and isinstance(pr.get("frames"), list):
            out.append((f"props.{name}", pr["frames"]))
    return out


def _points(clip):
    """the per-frame POINT lists (the sword's paths) -> [(label, list)]"""
    sw = clip.get("sword") if isinstance(clip.get("sword"), dict) else {}
    # (a per-frame list of points or turns; one vector for the whole clip - sword.dir_local - is not a path; the
    # lengths are checked once, before anything is eased)
    return [(f"sword.{k}", v) for k, v in sw.items() if isinstance(v, list) and v and all(isinstance(x, list) for x in v)]


def _insert(clip, at, k, paths):
    """put k-1 frames between frames at-1 and at (paths: label -> rotation vector for that step) -> the long-way labels"""
    longs = []
    for label, fr in _tracks(clip) + _points(clip):    # (their lengths were checked once, before any was eased)
        f0, f1 = fr[at - 1], fr[at]
        if label.startswith("sword.") and len(f0) == 4:            # a turn (grip_rot): slerped, not lerped
            new = [[round(float(x), 6) for x in C.slerp(f0, f1, j / k)] for j in range(1, k)]
        elif label.startswith("sword."):
            new = [[float(f0[c]) + (float(f1[c]) - float(f0[c])) * j / k for c in range(len(f0))] for j in range(1, k)]
        else:
            v, long_way = paths.get(label) or (_rotvec(f0[:4], f1[:4]), False)
            if long_way:
                longs.append(label)
            new = [_between(f0, f1, v, j / k) for j in range(1, k)]
        fr[at:at] = new
    return longs


def repair(clip, target=TARGET):
    """-> (the repaired copy, the reading {"upsampled", "eased": [...], "long_way": [...], "longer_by", "before", "after"})"""
    if not isinstance(clip, dict) or not isinstance(clip.get("times"), list) or len(clip["times"]) < 2:
        raise ValueError("it is not a clip")
    c = copy.deepcopy(clip)
    before = FT.read(c)
    fps = float(c.get("fps") or 30)
    n0 = len(c["times"])
    for label, fr in _tracks(c) + _points(c):
        if len(fr) != n0:
            raise ValueError(f"{label} has {len(fr)} frame(s) and the clip {n0}: it cannot be eased with them")
    if c.get("handoff") is not None or c.get("props"):
        raise ValueError("a clip that hands an object between parents (handoff / props): repair the body, then solve "
                         "its handoff again on the repaired clip (kit/anim/handoff.py --write)")
    intended = C.step_frames(c)
    if intended:
        raise ValueError("a stepped clip (its declared steps snap on purpose): not repaired here")
    reading = {"upsampled": False, "eased": [], "long_way": [], "longer_by": 0.0,
               "before": before["worst"], "after": None}
    # 1. frames between, the duration kept
    if fps < FPS - 1e-6:
        n = len(c["times"])
        for i in range(n - 1, 0, -1):
            paths = {label: _path(fr, i) for label, fr in _tracks(c)}
            reading["long_way"] += [{"frame": i, "joint": lb} for lb in _insert(c, i, 2, paths)]
        old = [float(t) for t in clip["times"]]
        c["times"] = [round(x, 6) for i in range(n) for x in ([old[i]] if i == 0 else [(old[i - 1] + old[i]) / 2, old[i]])]
        c["fps"] = int(round(2 * fps))
        fps = 2 * fps
        reading["upsampled"] = True
    # 2. a step still over the target: eased over more frames, time added there
    i = 1
    while i < len(c["times"]):
        worst, who = 0.0, None
        paths = {}
        for label, fr in _tracks(c):
            v, lw = _path(fr, i)
            paths[label] = (v, lw)
            deg = math.degrees(float(np.linalg.norm(v)))
            if deg > worst:
                worst, who = deg, label
        if worst <= target:
            i += 1
            continue
        k = int(math.ceil(worst / target - 1e-9))
        t_at = float(c["times"][i])
        dt = t_at - float(c["times"][i - 1])
        add = (k - 1) * dt
        longs = _insert(c, i, k, paths)
        reading["long_way"] += [{"frame": i, "joint": lb} for lb in longs]
        reading["eased"].append({"frame": i, "t": round(t_at, 4), "joint": who, "deg": round(worst, 1), "frames": k})
        old = c["times"]
        c["times"] = ([*old[:i]] + [round(float(old[i - 1]) + j * dt, 6) for j in range(1, k)]
                      + [round(float(t) + add, 6) for t in old[i:]])
        _shift(c, t_at, add)
        reading["longer_by"] = round(reading["longer_by"] + add, 6)
        i += k
    c["duration"] = c["times"][-1]
    after = FT.read(c)
    reading["after"] = after["worst"]
    reading["over_after"] = len(after["over"])
    c.setdefault("source", {})
    if isinstance(c["source"], dict):
        c["source"]["turn_repair"] = {k: reading[k] for k in ("upsampled", "eased", "long_way", "longer_by")}
    return c, reading


def gates(clip):
    """the build's motion gates on a clip, as kit/anim/metrics.py runs them -> [problem] (written to a scratch folder,
    nothing beside the clip)"""
    import contextlib
    import io as _io
    import tempfile
    import metrics as M
    with tempfile.TemporaryDirectory() as d:
        src = clip.get("source") if isinstance(clip.get("source"), dict) else {}
        path = os.path.join(d, f"{clip.get('name', 'clip')}.clip.json")
        # (the frozen lists are found by source.file, a path from the working folder: kept as it is. The fold check -
        # an .r6 clip against its R15 source beside it - does not run on the copy, nor on the clip it is read beside)
        del src
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(clip, fh)
        with contextlib.redirect_stdout(_io.StringIO()):
            M.main([path])
        mpath = path[:-len(".clip.json")] + ".metrics.json"
        if not os.path.isfile(mpath):
            return ["the motion gates wrote no reading"]
        with open(mpath, encoding="utf-8") as fh:
            return [str(p) for p in json.load(fh).get("problems") or []]


def _kind(p):
    """a problem with its numbers left out, whole (its joints kept): the same fault on the same joints at another
    frame or by another amount is the same; a list of joints that grew OR shrank reads as added - said rather than
    hidden"""
    import re
    return re.sub(r"[-0-9.]+", "#", p)


def held(clip, fixed):
    """the problems the repair ADDED -> [problem]"""
    old = {_kind(p) for p in gates(clip)}
    return [p for p in gates(fixed) if _kind(p) not in old]


def _shift(c, at, add):
    """every time at or after `at` moves on by `add` seconds"""
    eps = 1e-6
    for e in c.get("events") or []:
        if isinstance(e, dict) and isinstance(e.get("t"), (int, float)) and e["t"] >= at - eps:
            e["t"] = round(float(e["t"]) + add, 6)
    kick = c.get("camera_kick")
    if isinstance(kick, dict) and isinstance(kick.get("t"), (int, float)) and kick["t"] >= at - eps:
        kick["t"] = round(float(kick["t"]) + add, 6)
    beats = c.get("beats")
    if isinstance(beats, dict):
        for name, span in beats.items():
            if isinstance(span, list):
                beats[name] = [round(float(x) + add, 6) if isinstance(x, (int, float)) and x >= at - eps else x for x in span]
    if isinstance(c.get("stepped"), list):
        c["stepped"] = [[(t0 + add if t0 >= at - eps else t0), (t1 + add if t1 >= at - eps else t1), on]
                        for t0, t1, on in c["stepped"]]


def main(argv):
    if not argv:
        return emit("fail", "turn_repair: no clip given", "python kit/anim/turn_repair.py <clip.json> [--out <file>]")
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else None
    if argv[0] == "table":
        folder, names = argv[1], [a for a in argv[2:] if a != "--out" and a != out_dir]
        rows = []
        for name in names:
            path = os.path.join(folder, f"{name}.clip.json")
            if not os.path.isfile(path):
                rows.append({"clip": name, "error": "no built clip"})
                continue
            try:
                clip = C.load_clip(path)
                fixed, r = repair(clip)
            except ValueError as e:
                rows.append({"clip": name, "error": str(e)})
                continue
            added = held(clip, fixed)
            rows.append({"clip": name, "before": (r["before"] or {}).get("deg"), "after": (r["after"] or {}).get("deg"),
                         "over_after": r["over_after"], "upsampled": r["upsampled"], "eased": len(r["eased"]),
                         "longer_by": r["longer_by"], "long_way": len(r["long_way"]), "added": [a[:140] for a in added]})
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
                with open(os.path.join(out_dir, f"{name}.clip.json"), "w", encoding="utf-8") as fh:
                    json.dump(fixed, fh)
        ok = sum(1 for r in rows if r.get("over_after") == 0)
        clean = sum(1 for r in rows if r.get("over_after") == 0 and not r.get("added"))
        return emit("pass" if clean == len(rows) else "fail",
                    f"turn_repair: {ok} of {len(rows)} clip(s) under the limit after, {clean} with nothing added by the repair",
                    "read the rows: what each repair added", rows=rows)
    try:
        fixed, r = repair(C.load_clip(argv[0]))
    except ValueError as e:
        return emit("fail", f"turn_repair: {e}", "see the header")
    if out_dir:
        with open(out_dir, "w", encoding="utf-8") as fh:
            json.dump(fixed, fh)
    added = held(C.load_clip(argv[0]), fixed)
    if added:
        return emit("fail", f"turn_repair {fixed.get('name')}: under the limit, but the repair added: {added[0]}"
                    + (f" (+{len(added) - 1} more)" if len(added) > 1 else ""),
                    "the in-betweens want solving (grip_solve / collide_repair), not easing", added=added)
    return emit("pass" if r["over_after"] == 0 else "fail",
                f"turn_repair {fixed.get('name')}: fastest {r['before'] and r['before']['deg']} -> "
                f"{r['after'] and r['after']['deg']} deg a frame, {r['longer_by']} s longer, {len(r['long_way'])} step(s) the long way",
                "look at the repaired copy before anything builds it", **{k: r[k] for k in ("eased", "long_way", "longer_by")})


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
