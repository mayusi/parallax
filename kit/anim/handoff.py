"""handoff.py — AN OBJECT HANDED FROM ONE PARENT TO ANOTHER ("Child Of" phases), AND TOSSED BETWEEN THEM
(LIMITATIONS_FIXES_V3 §4 Stage D item 2: "Implement Contact-Space Socket Handoff (Child Of Phases) ... GunReload:
[0..0.15s] Mag in Receiver -> [0.15..0.55s] Mag parented to Left Arm ... -> [0.55..0.85s] Mag re-latched in
Receiver ... GunSwitch / SwapSwordToGuns: Explicit Holster -> Parabolic Toss (y(t) = v0*t - 0.5*g*t^2) -> Catch
windows (0.00 st hand/weapon catch seam)").

A magazine, a gun, a sword, a coin is carried by one thing at a time: the gun's receiver, a hand, the hip, the air.
The kit could key a weapon's own joint (kit/anim/grip.py) and throw the left gun on an arc (grip.py "throw"), but
nothing said WHO carries an object when, nothing held the object still on its carrier while it is carried, and
nothing measured the moment one parent takes it from another. This does, from a PLAN on the clip:

    clip["handoff"] = {"object": "Mag", "carrier": "Torso",
                       "phases": [{"t": 0.0,  "parent": "Handle", "at": {"pos": [0, -0.35, 0.1]}},
                                  {"t": 0.15, "parent": "Left Arm"},
                                  {"t": 0.55, "parent": "Handle", "at": {"pos": [0, -0.35, 0.1]}}]}

  parent   who carries it from `t` to the next phase: a part of the rig ("Left Arm", "Torso", ...), "Handle" /
           "HandleLeft" (the weapon's own joint: the clip's grip / grip_left track), or "body" (still in the
           character's space: set down, hung on the hip)
  at       where it sits on that parent ({"pos": [x, y, z] studs, "rot": [x, y, z] degrees} in the parent's space): a
           SOCKET. Left out, the new parent takes it where it IS (Child Of: its place at that frame, kept)
  toss     {"t": t, "toss": {"g": 35, "turns": 1, "axis": [0, 0, -1]}}: nobody carries it - it flies a BALLISTIC
           arc under g (studs/s^2, down) from where it was let go and lands EXACTLY in the next phase's socket (that
           phase must have an `at`), spinning `turns` whole extra turns about `axis` (its own space)
  hold     the point on a hand parent that takes it (default: an arm's hand, [0, -1, 0]); "grab": the point on the
           object it is taken by (default its origin)

THE CHECKS (each named with the phase and the frame):
  REACH    a hand that takes an object (a phase with no `at`, carried by an arm) is at it: its hold point within
           REACH studs of the object's grab point - else the object would jump to the hand, or be carried by a hand
           that never touched it
  SEAM     an object put into a socket (a phase WITH `at`, after a carried phase) arrives there: where its last
           carrier left it and the socket within SEAM studs and SEAM_DEG degrees - the re-latch, the catch
  a toss's seams are 0 by construction (it is solved to land in the socket); it is said with its launch speed and
  how high it rises, and refused when g is not above 0 or no socket waits for it
WHAT IT WRITES: the object's track as the Transform of ONE joint on its carrier (a Motor6D the game builds:
src/kit/AnimProp.luau AnimProp.socket), so the engine plays exactly the solved path with no parent switch at run time:
  object "Handle" on carrier "Right Arm" -> clip["grip"] (the weapon's own joint, grip.py's C0)
  object "HandleLeft" on "Left Arm"      -> clip["grip_left"]
  any other                               -> clip["props"][object] = {"carrier", "c0", "frames"}
plus clip["handoff_read"]: the seams, the reaches and the tosses. A WEAPON's toss (object Handle / HandleLeft) also
moves its paths (clip.sword tip / grip_path / edge: what the in-hand, collide and contact gates read) with it, and
says Toss and Catch as events at the release and the catch.
THE GATE judges what the GAME plays: the track written on the clip, against the plan solved on the clip as it is now
(an arm re-baked after the plan was written leaves the object where the hand no longer is: refused, "write it again").
A toss is held too: whole extra turns only (a half turn would snap at the catch), at least MIN_TOSS frames in the
air, and with a root track its arc is under gravity in the WORLD, not in the turning body's space.
A phase with no `at` is taken by a HAND only: anything else takes an object into a socket (an object left where it
was, carried by the torso, would float).

    python kit/anim/handoff.py <clip.json> [--write <out.clip.json>]

G: a hand toss at character scale. Roblox's own workspace gravity (196.2 studs/s^2) is 9.81 m/s^2 at 5 cm a stud;
an R6 body is about 5 studs tall (a stud ~ 0.28 m for it), where 9.81 m/s^2 is ~35 studs/s^2: grip.py's thrown gun
uses 35 too.
NOT HERE: who decides the plan (the move's author); the hand's own release speed against the toss's launch speed
(said, not judged); an object that collides with anything on its way."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import grip as GR  # noqa: E402

G = 35.0             # studs/s^2: 9.81 m/s^2 at an R6 body's scale
REACH = 0.3          # studs a taking hand's hold point may be from the object's grab point (an R6 hand is 1 stud)
SEAM = 0.01          # studs an object may arrive off its socket (a re-latch, a catch)
SEAM_DEG = 2.0       # degrees
HAND = (0.0, -1.0, 0.0)
MIN_TOSS = 2         # frames an object is in the air at least (one frame is a teleport, not a throw)
WRITTEN = 0.01       # studs / (x 100) degrees the track the game plays may differ from the plan solved now
ARMS = ("Left Arm", "Right Arm")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _vec(v, n=3):
    return (isinstance(v, (list, tuple)) and len(v) == n
            and all(not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x) for x in v))


def _at(at):
    """{"pos", "rot"} -> 4x4 (rot: degrees, the kit's Euler as kit/lib/animrig.luau angles: X, then Y, then Z)"""
    M = np.eye(4)
    if at.get("rot") is not None:
        rx, ry, rz = (math.radians(float(a)) for a in at["rot"])
        cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
        X = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        Y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        Z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
        M[:3, :3] = X @ Y @ Z
    if at.get("pos") is not None:
        M[:3, 3] = at["pos"]
    return M


def _axis_turn(axis, deg):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    q = [*(a * math.sin(math.radians(deg) / 2)), math.cos(math.radians(deg) / 2)]
    return C.quat_mat(q)


def problems(plan):
    """what makes a plan not one -> [words]"""
    if not isinstance(plan, dict) or not isinstance(plan.get("phases"), list) or not plan["phases"]:
        return ['a handoff is {"object", "carrier", "phases": [{"t", "parent" | "toss", "at"?}, ...]}']
    out = []
    if not isinstance(plan.get("object"), str) or not plan["object"].replace("_", "").isalnum():
        out.append("the object has no name (letters, digits, underscores)")
    if not isinstance(plan.get("carrier"), str):
        out.append("it names no carrier (the part whose joint plays the object's path in game)")
    last = None
    for k, ph in enumerate(plan["phases"]):
        if not isinstance(ph, dict) or isinstance(ph.get("t"), bool) or not isinstance(ph.get("t"), (int, float)):
            out.append(f"phase {k}: it has no time t")
            continue
        if last is not None and ph["t"] <= last:
            out.append(f"phase {k}: its time {ph['t']} is not after the one before ({last})")
        last = ph["t"]
        toss, parent = ph.get("toss"), ph.get("parent")
        if (toss is None) == (parent is None):
            out.append(f"phase {k}: it is carried by a parent or tossed, one of the two")
        if ph.get("at") is not None and (not isinstance(ph["at"], dict)
                                          or (ph["at"].get("pos") is not None and not _vec(ph["at"]["pos"]))
                                          or (ph["at"].get("rot") is not None and not _vec(ph["at"]["rot"]))):
            out.append(f"phase {k}: its socket `at` is {{\"pos\": [x, y, z], \"rot\": [x, y, z]}}")
        if toss is not None:
            if toss.get("at") is not None or ph.get("at") is not None:
                out.append(f"phase {k}: a toss has no socket of its own - it lands in the next phase's")
            g = toss.get("g", G) if isinstance(toss, dict) else None
            if not isinstance(toss, dict) or isinstance(g, bool) or not isinstance(g, (int, float)) or not g > 0:
                out.append(f"phase {k}: a toss is {{\"g\": studs/s^2 above 0, \"turns\", \"axis\"}}")
            elif toss.get("axis") is not None and (not _vec(toss["axis"]) or np.linalg.norm(toss["axis"]) < 1e-9):
                out.append(f"phase {k}: a toss's spin axis is [x, y, z]")
            turns = toss.get("turns", 0) if isinstance(toss, dict) else 0
            if isinstance(turns, bool) or not isinstance(turns, (int, float)) or float(turns) != int(turns):
                out.append(f"phase {k}: a toss turns whole extra turns only (a part turn would snap at the catch)")
            if k == 0:
                out.append("phase 0: a toss needs something to be thrown from")
            nxt = plan["phases"][k + 1] if k + 1 < len(plan["phases"]) else None
            if not isinstance(nxt, dict) or nxt.get("at") is None or nxt.get("toss") is not None:
                out.append(f"phase {k}: a toss lands in a socket - the next phase must be carried, with its `at`")
    if isinstance(plan["phases"][0], dict) and plan["phases"][0].get("at") is None:
        out.append("phase 0: where the object starts is a socket - the first phase needs its `at`")
    if isinstance(plan["phases"][0], dict) and plan["phases"][0].get("t") not in (0, 0.0):
        out.append("phase 0: it starts the clip (t 0) - the object is somewhere from the first frame")
    return out


def _parents(clip, rig):
    """per frame: name -> 4x4 in character space for every part, and the weapon joints the clip keys"""
    n = len(clip["times"])
    out = []
    for i in range(n):
        W = C.fk(rig, C.character_transforms(clip, rig, i))
        d = {name: np.asarray(M, float) for name, M in W.items()}
        for key, arm, c0, name in (("grip", "Right Arm", GR.GRIP_C0, "Handle"), ("grip_left", "Left Arm", GR.LEFT_C0, "HandleLeft")):
            tr = clip.get(key)
            if isinstance(tr, list) and len(tr) == n:
                T = np.eye(4)
                T[:3, :3] = C.quat_mat(tr[i][:4])
                T[:3, 3] = tr[i][4:7]
                d[name] = d[arm] @ c0 @ T
        d["body"] = np.eye(4)
        out.append(d)
    return out


def solve(clip, plan, rig=None):
    """the plan on the clip -> {"world": [4x4 a frame], "track": [7 numbers a frame], "c0", "seams", "reaches",
    "tosses", "faults"}; raises ValueError for a plan that is not one"""
    bad = problems(plan)
    if bad:
        raise ValueError(bad[0] + (f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""))
    rig = rig or C.load_rig(str(clip.get("rig", "R6")).lower())
    times = [float(t) for t in clip["times"]]
    n = len(times)
    P = _parents(clip, rig)
    phases = plan["phases"]
    starts = [min(range(n), key=lambda i: abs(times[i] - float(ph["t"]))) for ph in phases]
    for k in range(1, len(starts)):
        if starts[k] <= starts[k - 1]:
            raise ValueError(f"phase {k}: it starts on the same frame as the phase before (the clip's frames are too far apart)")
    faults, seams, reaches, tosses = [], [], [], []
    world = [None] * n
    local = None                                             # the object in its parent's space, this phase
    for k, ph in enumerate(phases):
        i0 = starts[k]
        i1 = starts[k + 1] if k + 1 < len(phases) else n
        if ph.get("toss") is not None:
            continue                                         # (solved once the socket it lands in is known)
        parent = ph["parent"]
        if parent not in P[0]:
            raise ValueError(f"phase {k}: its parent '{parent}' is not a part of the rig nor a weapon joint the clip keys")
        prev_toss = k > 0 and phases[k - 1].get("toss") is not None
        if ph.get("at") is not None:
            local = _at(ph["at"])
            here = P[i0][parent] @ local
            if k > 0 and not prev_toss:
                # where its last carrier has it at this frame (that carrier's hold, kept one frame more)
                was = P[i0][phases[k - 1]["parent"]] @ prev_local
                d = float(np.linalg.norm(was[:3, 3] - here[:3, 3]))
                a = float(C.quat_angle(C.mat_quat(was[:3, :3]), C.mat_quat(here[:3, :3])))
                seams.append({"phase": k, "frame": i0, "t": round(times[i0], 4), "studs": round(d, 4), "deg": round(a, 2)})
                if d > SEAM or a > SEAM_DEG:
                    faults.append({"phase": k, "frame": i0, "what": f"arrives {d:.3f} studs / {a:.1f} deg off its socket on "
                                   f"{parent} (from {phases[k - 1]['parent']}) - bring the carrier to the socket"})
        else:
            if prev_toss:
                raise ValueError(f"phase {k}: after a toss the object lands in a socket - it needs its `at`")
            was = P[i0][phases[k - 1]["parent"]] @ prev_local     # Child Of: taken where it is
            local = np.linalg.inv(P[i0][parent]) @ was
            if parent not in ARMS:
                faults.append({"phase": k, "frame": i0, "what": f"{parent} is no hand: it takes the object only into a "
                               "socket (give the phase its `at`)"})
            else:
                hold = np.asarray(ph.get("hold", HAND), float)
                grab = np.asarray(ph.get("grab", (0.0, 0.0, 0.0)), float)
                hand = (P[i0][parent] @ np.array([*hold, 1.0]))[:3]
                obj = (was @ np.array([*grab, 1.0]))[:3]
                d = float(np.linalg.norm(hand - obj))
                reaches.append({"phase": k, "frame": i0, "t": round(times[i0], 4), "parent": parent, "studs": round(d, 4)})
                if d > REACH:
                    faults.append({"phase": k, "frame": i0, "what": f"{parent} takes it {d:.2f} studs from where it is - the "
                                   "hand must reach it first"})
        for i in range(i0, i1):
            world[i] = P[i][parent] @ local
        prev_local = local
    # the tosses: from where the last carrier let it go to the next phase's socket
    for k, ph in enumerate(phases):
        if ph.get("toss") is None:
            continue
        i0, i1 = starts[k], starts[k + 1]
        if i1 - i0 < MIN_TOSS:
            raise ValueError(f"phase {k}: a toss is in the air {i1 - i0} frame(s) - at least {MIN_TOSS} (one is a teleport)")
        start = P[i0][phases[k - 1]["parent"]] @ _local_of(phases, k - 1, starts, P, world)
        end = world[i1]
        toss = ph["toss"]
        g = float(toss.get("g", G))
        T = times[i1] - times[i0]
        # the arc is under gravity in the WORLD: a clip that travels (its root track) carries the body, not the object
        roots = [_root(clip, i) for i in range(n)]
        start_w, end_w = roots[i0] @ start, roots[i1] @ end
        acc = np.array([0.0, -g, 0.0])
        v0 = (end_w[:3, 3] - start_w[:3, 3] - 0.5 * acc * T * T) / T
        turns = float(toss.get("turns", 0))
        axis = toss.get("axis", (0.0, 0.0, -1.0))
        q0, q1 = C.mat_quat(start_w[:3, :3]), C.mat_quat(end_w[:3, :3])
        for i in range(i0, i1):
            tau = times[i] - times[i0]
            u = tau / T
            M = np.eye(4)
            M[:3, :3] = C.quat_mat(C.slerp(q0, q1, u)) @ _axis_turn(axis, 360.0 * turns * u)
            M[:3, 3] = start_w[:3, 3] + v0 * tau + 0.5 * acc * tau * tau
            world[i] = np.linalg.inv(roots[i]) @ M
        rise = max(0.0, float(v0[1]) ** 2 / (2 * g)) if v0[1] > 0 else 0.0
        tosses.append({"phase": k, "from": round(times[i0], 4), "to": round(times[i1], 4), "g": g,
                       "launch": [round(float(v), 3) for v in v0], "speed": round(float(np.linalg.norm(v0)), 3),
                       "rises": round(rise, 3), "turns": turns})
    carrier = plan["carrier"]
    if carrier not in P[0] or carrier in ("Handle", "HandleLeft", "body"):
        raise ValueError(f"the carrier '{carrier}' is not a part of the rig")
    c0 = GR.GRIP_C0 if (plan["object"], carrier) == ("Handle", "Right Arm") else \
        GR.LEFT_C0 if (plan["object"], carrier) == ("HandleLeft", "Left Arm") else _at(plan.get("c0") or {})
    track = []
    for i in range(n):
        Tm = np.linalg.inv(P[i][carrier] @ c0) @ world[i]
        track.append([round(float(v), 6) for v in list(C.mat_quat(Tm[:3, :3])) + list(Tm[:3, 3])])
    return {"world": world, "track": track, "c0": c0, "seams": seams, "reaches": reaches, "tosses": tosses,
            "faults": faults, "starts": starts}


def _root(clip, i):
    """the clip's root track at frame i as a 4x4 (identity when it has none)"""
    M = np.eye(4)
    r = clip.get("root")
    if isinstance(r, list) and i < len(r) and isinstance(r[i], list) and len(r[i]) >= 7:
        M[:3, :3] = C.quat_mat(r[i][:4])
        M[:3, 3] = r[i][4:7]
    return M


def _local_of(phases, k, starts, P, world):
    """the object in phase k's parent's space (that phase is carried; its first frame's world over its parent)"""
    i0 = starts[k]
    return np.linalg.inv(P[i0][phases[k]["parent"]]) @ world[i0]


def write(clip, plan, rig=None):
    """solve and put the track where the game plays it -> the solved reading (clip changed in place)"""
    r = solve(clip, plan, rig)
    obj, carrier = plan["object"], plan["carrier"]
    if (obj, carrier) in (("Handle", "Right Arm"), ("HandleLeft", "Left Arm")):
        old = _parents(clip, rig or C.load_rig(str(clip.get("rig", "R6")).lower()))
        clip["grip" if obj == "Handle" else "grip_left"] = r["track"]
        sw = clip.get("sword") if obj == "Handle" and isinstance(clip.get("sword"), dict) else None
        n = len(clip["times"])
        if sw is not None and obj in old[0]:
            # the weapon's paths ride its new place: each point where it was on the weapon, on the weapon now
            for key, is_dir in (("tip", False), ("grip_path", False), ("edge", True)):
                pts = sw.get(key)
                if not isinstance(pts, list) or len(pts) != n:
                    continue
                for i in range(n):
                    rel = np.linalg.inv(old[i][obj])
                    v = np.array([*pts[i], 0.0 if is_dir else 1.0])
                    sw[key][i] = [round(float(x), 6) for x in (r["world"][i] @ (rel @ v))[:3]]
        for t in r["tosses"]:
            ev = clip.setdefault("events", [])
            for name, at in (("Toss", t["from"]), ("Catch", t["to"])):
                if not any(isinstance(e, dict) and e.get("name") == name and abs(float(e.get("t", -9)) - at) < 1e-6 for e in ev):
                    ev.append({"name": name, "t": at})
            ev.sort(key=lambda e: float(e.get("t", 0)) if isinstance(e, dict) else 0)
    else:
        c0 = r["c0"]
        clip.setdefault("props", {})[obj] = {
            "carrier": carrier, "frames": r["track"],
            "c0": [round(float(v), 6) for v in list(c0[:3, 3]) + list(c0[:3, :3].reshape(9))]}
    clip["handoff_read"] = {k: r[k] for k in ("seams", "reaches", "tosses", "faults")}
    return r


def gate(clip, rig=None):
    """what the build's motion gates add (kit/anim/metrics.py) -> (reading or None, problem or None): a clip that
    carries a plan is held to it"""
    plan = clip.get("handoff") if isinstance(clip, dict) else None
    if plan is None:
        return None, None
    try:
        r = solve(clip, plan, rig)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {"error": str(e)}, f"its handoff plan cannot be solved on the clip ({e})"
    reading = {k: r[k] for k in ("seams", "reaches", "tosses")}
    obj, carrier = plan["object"], plan["carrier"]
    played = (clip.get("grip") if (obj, carrier) == ("Handle", "Right Arm") else
              clip.get("grip_left") if (obj, carrier) == ("HandleLeft", "Left Arm") else
              ((clip.get("props") or {}).get(obj) or {}).get("frames"))
    if not isinstance(played, list) or len(played) != len(r["track"]):
        return reading, (f"{obj}: its plan was never written as the track the game plays (python kit/anim/handoff.py "
                         "<clip> --write) - nothing carries it in game")
    off = max(max(float(np.linalg.norm(np.subtract(a[4:7], b[4:7]))), C.quat_angle(a[:4], b[:4]) / 100.0)
              for a, b in zip(played, r["track"]))
    reading["played_off"] = round(off, 4)
    if off > WRITTEN:
        return reading, (f"{obj}: the track the game plays is not its plan on the clip as it is now ({off:.3f} studs / "
                         "x100 deg off: the body was changed after it was written) - write it again")
    if not r["faults"]:
        return reading, None
    f = r["faults"][0]
    return reading, (f"{plan['object']}: phase {f['phase']} (frame {f['frame']}) {f['what']}"
                     + (f" (+{len(r['faults']) - 1} more)" if len(r["faults"]) > 1 else ""))


def main(argv):
    if not argv:
        return emit("fail", "handoff: no clip given", "python kit/anim/handoff.py <clip.json> [--write <out.clip.json>]")
    clip = C.load_clip(argv[0])
    if clip.get("handoff") is None:
        return emit("fail", f"handoff: {argv[0]} carries no handoff plan", "add clip[\"handoff\"] (see this file's header)")
    try:
        r = write(clip, clip["handoff"]) if "--write" in argv else solve(clip, clip["handoff"])
    except ValueError as e:
        return emit("fail", f"handoff: {e}", "fix the plan")
    if "--write" in argv:
        out = argv[argv.index("--write") + 1]
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(clip, fh)
    said = {k: r[k] for k in ("seams", "reaches", "tosses", "faults")}
    if r["faults"]:
        return emit("fail", f"handoff {clip.get('name')}: {r['faults'][0]['what']}", "bring the carrier to it", **said)
    return emit("pass", f"handoff {clip.get('name')}: {len(r['seams'])} seam(s), {len(r['reaches'])} take(s), "
                f"{len(r['tosses'])} toss(es) - all within the bars", "build it", **said)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
