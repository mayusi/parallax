"""moment_clips.py — FIXTURE CLIPS FOR THE MOMENTS BETWEEN THE MOVEMENT LOOPS (the owner's older list, AN-28; S46 built
the rule that reads a start, a halt, a reversal and a turn on the spot off the body - src/kit/AnimBlend transition -
and the kit had NO clip to play for them: two sword cuts stood in).

    python kit/anim/moment_clips.py <Idle.r6.clip.json> <Walk.r6.clip.json> --out <folder>

Five R6 clips made from an idle and a walk loop, by rule (no pose is drawn here):
  start      the idle pose runs into the walk over START seconds: the walk's own frames, its cycle speeding up from
             a standstill, its weight easing in
  stop       the walk runs out into the idle pose over STOP seconds (the engine brakes a body from 16 studs a second
             in 0.40 to 0.53 s: measured in Studio, S46), its cycle slowing to nothing
  pivot      a halt at twice the pace and a start again: PIVOT seconds (the body's own turn is the engine's)
  turnLeft   on the spot, TURN seconds: one half of the walk's cycle at a third of its size over the idle - the feet
  turnRight  pick up and set down once - with the torso leaning a few degrees into the turn; the right is the
             left's mirror
Each ends where the loop it leads into begins (start: a walk frame; stop, turns: the idle pose), so the blend under
it shows no jump; each says `"moment": "<which>"` and `"match": {"pose": true}` (entered at the pose the body is in).

WHAT THESE ARE: KIT FIXTURES, so the wiring of AN-28 has real clips of the right length and shape to play. They
are blends by rule. NOBODY HAS LOOKED AT THEM as animation, and nothing here says they look right: a start, a stop
and a turn worth watching are moves to author and for the owner to judge."""
import copy
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

START, STOP, PIVOT, TURN = 0.30, 0.45, 0.50, 0.35
TURN_SIZE, TURN_LEAN = 0.33, 6.0
FPS = 60
MOMENTS = ("start", "stop", "pivot", "turnLeft", "turnRight")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def _blend(a, b, w):
    import clip as C
    q = C.slerp(a[:4], b[:4], w)
    return [float(v) for v in q] + [a[i] * (1 - w) + b[i] * w for i in (4, 5, 6)]


def _at(clip, part, phase):
    """a loop's frame at `phase` (0..1 of its cycle), between its keys; the loop's last frame is its first again"""
    frames = clip["joints"][part]["frames"]
    n = len(frames) - 1
    x = (phase % 1.0) * n
    i = int(math.floor(x))
    return _blend(frames[i], frames[min(i + 1, n)], x - i)


def _check(idle, walk):
    for c, what in ((idle, "the idle"), (walk, "the walk")):
        if not isinstance(c, dict) or c.get("rig") != "R6" or not isinstance(c.get("joints"), dict):
            raise ValueError(f"{what} is not an R6 clip")
        if len(c.get("times") or []) < 2:
            raise ValueError(f"{what} has fewer than two frames")
    if not walk.get("loop"):
        raise ValueError("the walk is not a loop")
    missing = sorted(set(walk["joints"]) ^ set(idle["joints"]))
    if missing:
        raise ValueError(f"the idle and the walk do not move the same joints ({', '.join(missing)})")


def _new(name, moment, seconds, parts):
    n = int(round(seconds * FPS))
    return {"schema": 1, "name": name, "rig": "R6", "fps": FPS, "loop": False, "priority": "Movement",
            "times": [round(i / FPS, 6) for i in range(n + 1)], "duration": round(n / FPS, 6), "events": [],
            "moment": moment, "match": {"pose": True},
            "source": {"kind": "moment", "tool": "kit/anim/moment_clips.py"},
            "joints": {p: {"frames": []} for p in parts}}, n


def make(idle, walk, prefix="Moment"):
    """-> {moment: clip}"""
    _check(idle, walk)
    parts = sorted(walk["joints"])
    rest = {p: idle["joints"][p]["frames"][0] for p in parts}
    out = {}

    # START: the cycle's phase is the integral of a pace that eases from 0 to the walk's own
    c, n = _new(prefix + "Start", "start", START, parts)
    cycle = float(walk["times"][-1])
    for i in range(n + 1):
        u = i / n
        phase = (START / cycle) * (u * u * u - u * u * u * u / 2)       # pace = smoothstep(u): its integral
        for p in parts:
            c["joints"][p]["frames"].append(_blend(rest[p], _at(walk, p, phase), _smooth(u)))
    end = (START / cycle) * 0.5
    c["leads_into"] = {"loop": "walk", "phase": round(end % 1.0, 4)}
    out["start"] = c

    # STOP: the walk from its first frame, its pace easing to nothing, its weight easing out
    c, n = _new(prefix + "Stop", "stop", STOP, parts)
    for i in range(n + 1):
        u = i / n
        phase = (STOP / cycle) * (u - u * u * u + u * u * u * u / 2)    # pace = 1 - smoothstep(u): its integral
        for p in parts:
            c["joints"][p]["frames"].append(_blend(_at(walk, p, phase), rest[p], _smooth(u)))
    out["stop"] = c

    # PIVOT: a halt in half the time, then a start in half the time
    c, n = _new(prefix + "Pivot", "pivot", PIVOT, parts)
    half = n // 2
    for i in range(n + 1):
        if i <= half:
            u = i / half
            phase = (PIVOT / 2 / cycle) * (u - u * u * u + u * u * u * u / 2)
            w = _smooth(u)
            for p in parts:
                c["joints"][p]["frames"].append(_blend(_at(walk, p, phase), rest[p], w))
        else:
            u = (i - half) / (n - half)
            phase = (PIVOT / 2 / cycle) * (u * u * u - u * u * u * u / 2)
            for p in parts:
                c["joints"][p]["frames"].append(_blend(rest[p], _at(walk, p, phase), _smooth(u)))
    c["leads_into"] = {"loop": "walk", "phase": round(((PIVOT / 2 / cycle) * 0.5) % 1.0, 4)}
    out["pivot"] = c

    # TURN on the spot: half a cycle of the walk at a third of its size, a lean into the turn, out and back
    import clip as C
    for side, sign in (("turnLeft", 1.0), ("turnRight", -1.0)):
        c, n = _new(prefix + ("TurnLeft" if sign > 0 else "TurnRight"), side, TURN, parts)
        for i in range(n + 1):
            u = i / n
            bell = math.sin(math.pi * u) ** 2                                  # 0 .. 1 .. 0
            phase = 0.5 * u + (0.0 if sign > 0 else 0.5)                       # (the other foot leads the other way)
            for p in parts:
                f = _blend(rest[p], _at(walk, p, phase), TURN_SIZE * bell)
                if p == "Torso":
                    a = math.radians(TURN_LEAN * bell * sign) / 2
                    lean = [0.0, 0.0, math.sin(a), math.cos(a)]                # about Z: + leans to the body's left
                    q = C.mat_quat(C.quat_mat(lean) @ C.quat_mat(f[:4]))
                    f = [float(v) for v in q] + f[4:]
                c["joints"][p]["frames"].append(f)
        out[side] = c
    return out


def step(clip):
    """the most any joint turns between two frames (degrees) and slides (studs): a jump would show here"""
    import clip as C
    deg, studs = 0.0, 0.0
    for j in clip["joints"].values():
        fr = j["frames"]
        for a, b in zip(fr, fr[1:]):
            deg = max(deg, C.quat_angle(a[:4], b[:4]))
            studs = max(studs, math.dist(a[4:7], b[4:7]))
    return deg, studs


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) < 4 or "--out" not in argv:
        print(__doc__)
        return 2
    try:
        with open(argv[0], encoding="utf-8") as fh:
            idle = json.load(fh)
        with open(argv[1], encoding="utf-8") as fh:
            walk = json.load(fh)
        out = argv[argv.index("--out") + 1]
        clips = make(idle, walk)
        os.makedirs(out, exist_ok=True)
        said = []
        for moment in MOMENTS:
            c = clips[moment]
            with open(os.path.join(out, c["name"] + ".clip.json"), "w", encoding="utf-8", newline="\n") as fh:
                json.dump(c, fh)
            d, s = step(c)
            said.append(f"{moment} {c['duration']:g} s (at most {d:.1f} deg a frame)")
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim moments: {type(e).__name__}: {e}", "python kit/anim/moment_clips.py <Idle.r6.clip.json> <Walk.r6.clip.json> --out <folder>")
    return emit("pass", "anim moments: " + ", ".join(said) + f" -> {out.replace(os.sep, '/')}",
                "fixtures by rule: nobody has looked at them as animation", folder=out.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
