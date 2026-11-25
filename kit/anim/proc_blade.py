"""proc_blade.py — the WEAPON builder for a move dossier, a sibling of proc_kick on the same engine (the governor's
re-plan 2026-11-05, board/plans/archive/2026-11-05-gt-anim-procedural-replan.md; the owner: "make sure ur using the procedural
pipeline properly"). Weapon moves went AROUND the procedural route (proc_strike = strike.py key poses, graveyard ruling
2); here they are made like every procedural move:
  director   the move's GESTURE (assets/animations/gestures/<name>.json, kind "blade": designed by craft rules - a
             line of action, contrapposto, asymmetry, arcs, R6 exaggeration) is a BEAT SCRIPT: a thought beat (the
             head to the target first) -> the wind-up -> a ~0.2 s snap -> a MOVING hold -> the flourish / retract
  efforts    the four Laban sliders re-time and re-scale the beats (time: the segments shorter / longer; weight: the
             coil, crouch, lean and lunge deeper; space: the body carried further round past contact; flow: the
             springs' follow-through) - candidates DIFFER by these + an ARM HABIT + a WHIP, never by hand-made variants
  vocabulary the loved weapon swings' statistics (r6_vocab.json "weapon": the sword clips carry no legs, so the legs,
             torso speed and pivot come from loved full-body arm strikes): per-phase limb SLIDES (R6's missing elbow
             and knee), the free arm's k-means ARM HABITS (the mean was a T nobody makes) or the combat POSE PRIOR's
             modes given the designed torso (pose_prior.nudge), its WHIP at the strike
  engine     proc_r6 hermite tracking springs, dense 60 fps; the torso leads, head / arms DRAG 3 / 2 frames behind it
  feet       the gesture's foot schedule: soles planted, a step lifts on an arc and lands as the cut lands; the rear
             foot PIVOTS on its sole with the hips by `pivot_share` (loved arm strikes: p50 0.69, never 1.0 - a foot
             turning wholly with the hips froze the leg); legs by IK that keeps their vocabulary slide
  blade      a RIGID child of the grip hand (Roblox's RightGrip: 1 stud down the arm, the blade along the arm's -Z);
             the arm is turned square to the wanted blade and rolled to it; a beat's blade is a STAGE direction (the cut
             goes at the target wherever the torso has turned). The Hit sits on the tip's speed peak
    from proc_blade import build;  c, b = build(dossier, s, name)      (s = {time, weight, space, flow, arms})"""
import copy
import fnmatch
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import proc_director as DR  # noqa: E402
import proc_r6 as P  # noqa: E402

J = P.JOINTS
D2R = math.pi / 180
GESTURES = os.path.join("assets", "animations", "gestures")
VOCAB = os.path.join("assets", "animations", "calibration", "r6_vocab.json")
BLADE_LOCAL = np.array([0.0, 0.0, -1.0])          # RightGrip C0: the blade leaves the fist along the arm's -Z
GRIP_LOCAL = np.array([0.0, -1.0, 0.0])           # the fist: 1 stud down the arm part
DRAG_S = {"Head": 3 / 60, "Right Arm": 2 / 60, "Left Arm": 2 / 60}   # the governor's plan: head 3, arms 2 frames
FOLLOW = {"Torso": 0.3, "Head": 0.5, "Right Arm": 0.45, "Left Arm": 0.65, "Right Leg": 0.4, "Left Leg": 0.4}
SEG_TIME = {"antic": 0.15, "stroke": 0.2, "through": 0.15, "hold": 0.15, "flourish": 0.12, "settle": 0.12,
            "spin": 0.1}   # x(1 - k*time)
SPIN_STEP_DEG = 75.0     # a spin is keyed at least this often (consecutive keys < 90 deg apart: the curve never flips)
# whip targets for the FREE (left) arm, torso frame: flung down-back, out wide, up, or across the chest
WHIPS = {"down_back": (-0.4, -0.7, 0.6), "out": (-1.0, 0.0, 0.1), "up": (-0.3, 0.9, 0.2), "across": (0.6, -0.2, -0.7)}
# the free arm's source (a choice per candidate): 'habit:<h>:<whip>' = one of the loved weapon swings' ARM HABITS, or
# 'prior:<mode>:<whip>' = the combat POSE PRIOR's <mode>-th upper body given the designed torso (pose_prior.nudge: loved
# R6 combat poses as a density, never a lookup) - the sword arm always keeps its designed blade
HABITS = ("habit:0:out", "habit:1:down_back", "habit:2:up", "prior:0:down_back", "habit:0:down_back", "prior:1:out",
          "habit:1:out", "habit:2:across")
_V = None


def vocab():
    global _V
    if _V is None:
        _V = json.load(open(VOCAB, encoding="utf-8"))["weapon"]
    return _V


def gesture_for(d, name):
    """the dossier's build.gestures {clip glob: gesture name} -> the gesture spec (no match: no build - the move
    needs its own gesture designed first)"""
    for pat, g in (d["build"].get("gestures") or {}).items():
        if fnmatch.fnmatch(name.split("_r")[0], pat) or fnmatch.fnmatch(name, pat):
            return json.load(open(os.path.join(GESTURES, f"{g}.json"), encoding="utf-8"))
    raise SystemExit(f"proc_blade: no gesture for {name} in the dossier's build.gestures - design one in {GESTURES}/ first")


def unit(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-9)


# ---------------------------------------------------------------- the beat script, through the efforts
def carry(beats):
    """a beat sets only what changes; the rest carries from the beat before (torso / sword / head merged per field)"""
    out, cur = [], {}
    for b in beats:
        nb = copy.deepcopy(cur)
        for k, v in b.items():
            nb[k] = {**nb.get(k, {}), **v} if isinstance(v, dict) and isinstance(nb.get(k), dict) else copy.deepcopy(v)
        nb.pop("drift", None)
        nb.pop("stiff", None)
        if b.get("drift"):
            nb["drift"] = True
        if b.get("stiff"):
            nb["stiff"] = b["stiff"]
        out.append(nb)
        cur = {k: v for k, v in nb.items() if k not in ("seg", "drift", "stiff", "spin")}   # (a spin is its beat's own)
    return out


def expand_spins(beats):
    """a beat with `spin` {turns, to} turns the body from its yaw to the next beat's (which the gesture sets turns x 360
    away) by keys every <= SPIN_STEP_DEG - the director's job; the keys in between carry the beat's pose and its frame"""
    out = []
    for i, b in enumerate(beats):
        out.append(b)
        sp = b.get("spin")
        if not sp or i + 1 >= len(beats):
            continue
        nb = beats[i + 1]
        y0, y1 = float(b["torso"]["yaw"]), float(nb["torso"]["yaw"])
        k = max(1, int(math.ceil(abs(y1 - y0) / SPIN_STEP_DEG)))
        for j in range(1, k):
            u = j / k
            mid = copy.deepcopy(b)
            mid.pop("spin", None)
            mid.update(name=f"{b['name']}_{j}", t=round(b["t"] + u * (nb["t"] - b["t"]), 5), seg="spin")
            mid["torso"]["yaw"] = y0 + u * (y1 - y0)
            out.append(mid)
        nb["seg"] = "spin"
    return out


def spin_layer(beats):
    """a SPIN as its own yaw layer (2026-11-05: five turns keyed as joint rotations broke the engine's log-space curve -
    30-radian rotation vectors turn a tiny axis tilt into a whole-turn whip at the stop): -> (S(t) degrees, the beats
    with S taken out of their torso yaw). A spin segment = the beat before the first `seg: spin` beat .. the last of
    them; S ramps through their yaws (eased in over its first turn's worth of keys, linear into the dead stop) and holds
    after; the keys keep only the residual yaw, the springs work in that de-spun frame, apply_spin puts S back"""
    segs, i = [], 0
    while i < len(beats):
        if beats[i].get("seg") == "spin" and i > 0:
            a = i - 1
            while i < len(beats) and beats[i].get("seg") == "spin":
                i += 1
            segs.append((a, i - 1))
        else:
            i += 1
    if not segs:
        return (lambda t: 0.0), beats
    knots_t, knots_s = [beats[0]["t"]], [0.0]
    acc = 0.0
    for a, z in segs:
        y0 = float(beats[a]["torso"]["yaw"])
        knots_t.append(beats[a]["t"])
        knots_s.append(acc)
        for j in range(a + 1, z + 1):
            knots_t.append(beats[j]["t"])
            knots_s.append(acc + float(beats[j]["torso"]["yaw"]) - y0)
        acc = knots_s[-1]
    T, Sv = np.array(knots_t, float), np.array(knots_s, float)
    # each spin: from rest, a constant acceleration over its first ~quarter (<= 0.3 s), then a constant rate into the
    # dead stop - the rate solved so the turns still end on the stop beat: A = rate x (span - ramp / 2)
    runs = []
    for a, z in segs:
        t0, t1 = beats[a]["t"], beats[z]["t"]
        s0, s1 = float(np.interp(t0, T, Sv)), float(np.interp(t1, T, Sv))
        e = min(0.25 * (t1 - t0), 0.3)
        runs.append((t0, t1, s0, s1, e, (s1 - s0) / max(t1 - t0 - e / 2, 1e-6)))

    def S(t):
        for t0, t1, s0, s1, e, rate in runs:
            if t0 <= t <= t1:
                tau = t - t0
                return s0 + (0.5 * rate * tau * tau / e if tau < e else 0.5 * rate * e + rate * (tau - e))
        return float(np.interp(t, T, Sv))
    out = copy.deepcopy(beats)
    for b in out:
        b["torso"]["yaw"] = float(b["torso"]["yaw"]) - float(np.interp(b["t"], T, Sv))
    return S, out


def apply_spin(c, S):
    """the spin layer back on: the torso (and its offset) turned by S(t) about the vertical, every frame"""
    q, p = DR.arrays(c)
    for t in range(len(q)):
        r = P.q_exp(np.array([0.0, S(t / 60) * D2R, 0.0]))
        q[t, 0] = P.q_mul(r, q[t, 0])
        p[t, 0] = P.q_rot(r, p[t, 0])
    for t in range(1, len(q)):                              # one hemisphere along the clip
        if np.dot(q[t, 0], q[t - 1, 0]) < 0:
            q[t, 0] = -q[t, 0]
    return DR.set_arrays(c, q, p)


def effort(g, s, intent=None):
    """the gesture's beats -> this candidate's: (beats, feet, end). intent (INTENT_BLADE): the stroke + follow-through
    segments x k inside the same retime (the feet keep step with them) and the torso leading into the cut"""
    t, w, sp = (float(s.get(k, 0.0)) for k in ("time", "weight", "space"))
    beats = expand_spins(carry(g["beats"]))
    aim = INTENT_BLADE.get(intent) if intent else None      # (no intent asked: the gesture exactly as designed)
    u = (float(np.clip(t, -1.0, 1.0)) + 1.0) / 2.0
    kk = (aim["k"][1] - u * (aim["k"][1] - aim["k"][0])) if aim else 1.0
    old = [b["t"] for b in beats]
    new = [old[0]]
    segs = tuple((aim or {}).get("segs") or ("stroke", "through"))
    dur = [(z - a) * (1.0 - SEG_TIME.get(b.get("seg"), 0.2) * t) for b, a, z in zip(beats[1:], old, old[1:])]
    scaled = [x * (kk if b.get("seg") in segs else 1.0) for x, b in zip(dur, beats[1:])]
    if aim and aim.get("pay"):
        # the time an intent added or took is paid back by its `pay` segments (never under a tenth of their length)
        extra = sum(scaled) - sum(dur)
        pay = [i for i, b in enumerate(beats[1:]) if b.get("seg") == aim["pay"]]
        room = sum(scaled[i] for i in pay)
        if pay and room > 0:
            for i in pay:
                scaled[i] = max(0.1 * scaled[i], scaled[i] - extra * scaled[i] / room)
    for x in scaled:
        new.append(new[-1] + x)
    ph_at = {b["name"]: i for i, b in enumerate(beats)}
    strike_i = next((i for i, b in enumerate(beats) if b.get("phase") == "strike"), len(beats) // 2)
    for i, b in enumerate(beats):
        b["t"] = round(new[i], 4)
        to = b["torso"]
        to["crouch"] = round(min(0.75, to.get("crouch", 0.0) * (1 + 0.22 * w)), 3)
        if to.get("pitch", 0) > 0:
            to["pitch"] = round(to["pitch"] * (1 + 0.3 * w), 2)
        if b.get("phase") == "windup":
            to["yaw"] = round(to["yaw"] - 14 * w, 2)                 # a deeper coil
        if i > strike_i and b.get("phase") not in ("rest",):
            to["yaw"] = round(to["yaw"] + 22 * sp, 2)                # carried further round past contact
        if i >= strike_i:
            to["z"] = round(to.get("z", 0.0) * (1 + 0.25 * w), 3)    # a longer lunge
    first = next((i for i, b in enumerate(beats) if b.get("seg") == "stroke"), None)
    if aim and first is not None and first != strike_i:
        # the hips drive the cut: at the stroke's first beat the torso is already `lead` of the way to the strike's turn
        lead = aim["lead"][0] + u * (aim["lead"][1] - aim["lead"][0])
        a0, a1 = beats[first]["torso"], beats[strike_i]["torso"]
        a0["yaw"] = round(a0["yaw"] + lead * (a1["yaw"] - a0["yaw"]), 2)
    retime = lambda x: float(np.interp(x, old, new)) if x <= old[-1] else x - old[-1] + new[-1]  # noqa: E731
    feet = {}
    for leg, steps in g["feet"].items():
        if leg == "about":
            continue
        out = []
        for st in steps:
            at = list(st["at"])
            if st.get("lift") and at[1] < -0.8:                   # a forward step: weight = a longer lunge
                at[1] = round(at[1] * (1 + 0.15 * w), 3)
            out.append({**st, "t": round(retime(st["t"]), 4), "at": at})
        feet[leg] = out
    return beats, feet, retime(g["end"]), ph_at


# ---------------------------------------------------------------- poses
def blade_dir(pose, arm):
    return unit(P.q_rot(np.array(pose[arm][:4]), BLADE_LOCAL))


def blade_arm(pose, arm, arm_spec, blade, slide=0.0):
    """aim the sword arm, then roll it so the welded blade lies along the wanted one. On R6 the blade always lies
    square to the shoulder -> hand line, so one of the two gives: the BLADE wins (the arm moved the least that makes
    it reachable) unless the wanted blade runs near the arm's own line (|cos| >= 0.6) - squaring the arm to it there
    threw the arm down (a 280 studs/s flip) - where the ARM wins and the blade is laid square to it"""
    side = arm.split()[0]
    u = unit(DR.arm_dir(side, *arm_spec) if len(arm_spec) == 2 else arm_spec)
    b0 = unit(blade)
    if abs(float(u @ b0)) < 0.6:
        u = unit(u - float(u @ b0) * b0)
    p = DR.aim(pose, arm, u)
    a = unit(P.q_rot(np.array(p[arm][:4]), DR.geom()[arm][1]))
    b = unit(blade)
    b = b - float(b @ a) * a
    b = unit(b if np.linalg.norm(b) > 1e-3 else blade_dir(p, arm))
    best = None
    for k in range(72):                                            # the roll: the 5-degree step nearest, then refined
        th = k * 5.0
        a = blade_dir(DR.roll(p, arm, th), arm)
        if best is None or a @ b > best[1]:
            best = (th, float(a @ b))
    th = best[0]
    for step in (2.5, 1.0, 0.25):
        th = max((th - step, th, th + step), key=lambda x: float(blade_dir(DR.roll(p, arm, x), arm) @ b))
    p = DR.roll(p, arm, th)
    p[arm][4:7] = list(map(float, np.asarray(p[arm][4:7]) + unit(P.q_rot(np.array(p[arm][:4]), DR.geom()[arm][1])) * slide))
    return p


def phase_vec(table, ph):
    if isinstance(ph, (list, tuple)):
        a, z, u = ph
        return (1 - u) * np.asarray(table[a], float) + u * np.asarray(table[z], float)
    return np.asarray(table[ph or "rest"], float)


def free_arm_dir(ph, habit, whip, pose=None, free="Left Arm"):
    """the free arm: an ARM HABIT (k-means centroid of loved weapon swings' choreographies) through the phases - or,
    for a ('prior', mode) source, the combat pose prior's mode given the key's torso - turned `whip` degrees toward
    its whip target at the strike / after (loved free arms whip 53-129 deg, p25-p75)"""
    if isinstance(habit, tuple) and habit[0] == "prior":
        import pose_prior as PP
        nz, _ = PP.nudge(pose, group="combat", rank=int(habit[1]), tau=0.25, seed=int(habit[1]))
        d = unit(P.q_rot(np.array(nz[free][:4]), DR.geom()[free][1]))
    else:
        H = vocab()["arm_habits"][int(habit) % len(vocab()["arm_habits"])]["free_arm"]
        d = unit(phase_vec(H, ph))
    p0 = ph[1] if isinstance(ph, (list, tuple)) else ph
    if whip and p0 == "windup":                              # the counter: loaded AWAY from the whip first
        tgt = unit(WHIPS[whip[0]])
        ax = np.cross(tgt, d)
        if np.linalg.norm(ax) > 1e-9:
            d = P.q_rot(P.q_exp(unit(ax) * 0.35 * whip[1] * D2R), d)
    if whip and p0 in ("strike", "after"):
        tgt = unit(WHIPS[whip[0]])
        ax = np.cross(d, tgt)
        if np.linalg.norm(ax) > 1e-9:
            ang = min(math.atan2(np.linalg.norm(ax), float(d @ tgt)), whip[1] * D2R)
            if isinstance(ph, (list, tuple)) and ph[1] == "after" and ph[0] == "strike":
                ang *= 0.5 + 0.5 * ph[2]
            d = P.q_rot(P.q_exp(unit(ax) * ang), d)
    return d


def on_socket(p, arm, role):
    """the arm stays ON its shoulder: its sideways slide OUT of the socket held to the loved median (r6_vocab weapon
    slide_outward p50; loved arms slide up / forward, little outward). 2026-11-05 drill r2 ('OK BUT WHY IS THE SWORD AND
    HANDS WEIRD MAN'): a reach slid along an arm held out sideways floated it 0.8 studs off the shoulder - a visible gap"""
    cap = float(vocab()["slide_outward"][role]["p50"])
    s = 1.0 if arm.startswith("Right") else -1.0
    if s * p[arm][4] > cap:
        p[arm][4] = s * cap
    return p


def clear_of_body(p, arm, bar, role=None):
    """the arm OUT of the torso and the head until its box sinks no more than `bar` (strike.arm_in_body; the loved
    full-body strikes: worst sink p50 0.15): the free arm TURNED out from the body about the torso's forward axis (5 deg
    steps, up to 60); the sword arm (`role` given: its turn is the blade's line) SLID out instead, never past its
    socket cap (on_socket)"""
    import strike as SK
    s = 1.0 if arm.startswith("Right") else -1.0
    cap = float(vocab()["slide_outward"][role]["p50"]) if role else 0.0
    for _ in range(12):
        if SK.arm_in_body(arm, C.quat_mat(p[arm][:4]), p[arm][4:7]) <= bar:
            break
        if role:
            if s * p[arm][4] >= cap:
                break
            p[arm][4] = s * min(cap, s * p[arm][4] + 0.05)
        else:
            q = P.q_mul(P.q_exp(np.array([0.0, 0.0, s * 5.0 * D2R])), np.array(p[arm][:4]))
            p[arm][:4] = list(map(float, q / np.linalg.norm(q)))
    return p


ARM_CLEAR_BAR = 0.15     # the loved full-body arm strikes' worst arm sink, median (blade_measure 2026-11-05)


def two_hand(p, reach, blade, g, facing=None):
    """BOTH hands on the hilt (a katana, a greatsword - the gesture's `two_hand`), torso frame: the grip centre where the
    beat's `reach` points the sword arm, moved the least that both one-piece R6 arms reach it (strike.solve_grip - the
    solve of the loved katana and greatsword chains), each arm turned to put its fist on the hilt (strike.arm_rotation:
    the box faces the hilt) and slid along itself the rest of the way, at most `arm_slide` (loved R6 sword animators
    slide the arms 1.2-3.2 studs); a grip that sinks an arm into the body is pushed forward first. The sword hand is the
    upper one (near the guard), the free hand the lower (the pommel end), `grip_spacing` apart. `facing` (a dict, kept
    across the keys): each arm box's facing carried from the key before, turned at most ~30 deg a key - solved key by key
    alone, a box flipped between two keys and the quickened cut spun it in one frame (4,398 deg/s, 2026-11-11)"""
    import strike as SK
    I3, O = np.eye(3), np.zeros(3)
    spacing, slide = float(g.get("grip_spacing", 0.5)), float(g.get("arm_slide", 1.2))
    d = unit(blade)
    G0 = SK.SHOULDER["Right Arm"] + unit(reach) * SK.REACH
    best = None
    for push in np.arange(0.0, 1.21, 0.15):
        G, _ = SK.solve_grip(G0 + np.array([0.0, 0.0, -push]), d, I3, O, spacing, slide)
        arms = {}
        for arm, off in ((g["hand"], spacing / 2), (g["free"], -spacing / 2)):
            R, x = SK.arm_rotation(arm, G + off * d, I3, O, d, (facing or {}).get(arm))
            v = G + off * d - SK.SHOULDER[arm]
            arms[arm] = (R, unit(v) * max(-slide, min(slide, float(np.linalg.norm(v)) - SK.REACH)), x)
        sink = max(SK.arm_in_body(a, R, sl) for a, (R, sl, _) in arms.items())
        if best is None or sink < best[0] - 1e-9:
            best = (sink, arms)
        if sink <= ARM_CLEAR_BAR:
            break
    for arm, (R, sl, x) in best[1].items():
        p[arm] = list(map(float, C.mat_quat(R))) + list(map(float, sl))
        if facing is not None:
            facing[arm] = x
    return p


def designed_blade(beats, n):
    """the blade LINE the gesture designs, per frame (character space): a Catmull-Rom curve through each beat's stage
    blade - two-handed, the cut keeps its plane whatever the arms' springs lag (2026-11-11 lab: a blade taken from the
    lagging lower fist smeared 85-103 deg off the cut plane once the stroke was quickened), and it passes through a
    beat still MOVING (eased to a stop at every beat, the kesa's tip peaked in the forward drop, 59 deg off its
    down-left cut at the Hit)"""
    ts = [b["t"] for b in beats if b.get("sword", {}).get("blade") is not None]
    ds = [unit(b["sword"]["blade"]) for b in beats if b.get("sword", {}).get("blade") is not None]
    pts = [ds[0]] + ds + [ds[-1]]
    out = []
    for f in range(n):
        tt = f / 60
        i = max(0, min(len(ts) - 2, int(np.searchsorted(ts, tt, side="right")) - 1))
        u = float(np.clip((tt - ts[i]) / max(ts[i + 1] - ts[i], 1e-6), 0.0, 1.0))
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        v = 0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3)
        out.append(unit(v) if np.linalg.norm(v) > 1e-6 else unit(p1))
    return out


def hilt_pass(c, g, line=None):
    """two-handed: the hands NEVER leave the tsuka (2026-11-11 lab: the springs move each arm on its own between the keys
    and left the fists 0.64-0.91 studs off their 0.5 spacing - the strike route holds the grip every frame, so does
    this): every frame the free arm is turned and slid so its fist sits `grip_spacing` below the sword fist on the
    blade's line - the gesture's designed line (designed_blade, character space) when given, else the line the two
    fists hold (strike.arm_rotation, its facing carried frame to frame at the move's twist rate)"""
    import strike as SK
    rig = C.load_rig("r6")
    q, p = DR.arrays(c)
    k = J.index(g["free"])
    spacing, slide = float(g.get("grip_spacing", 0.5)), float(g.get("arm_slide", 1.2))
    I3, O = np.eye(3), np.zeros(3)
    facing = None
    for t in range(len(q)):
        F = C.fk(rig, C.character_transforms(c, rig, t))
        T = F["Torso"]
        hi = (F[g["hand"]] @ np.r_[GRIP_LOCAL, 1.0])[:3]
        lo = (F[g["free"]] @ np.r_[GRIP_LOCAL, 1.0])[:3]
        Ti = np.linalg.inv(T)
        d = unit(Ti[:3, :3] @ (line[t] if line is not None and t < len(line) else unit(hi - lo)))
        tgt = (Ti @ np.r_[hi, 1.0])[:3] - d * spacing
        R, facing = SK.arm_rotation(g["free"], tgt, I3, O, d, facing, float(g.get("arm_twist_rate", 12)))
        v = tgt - SK.SHOULDER[g["free"]]
        q[t, k] = C.mat_quat(R)
        p[t, k] = unit(v) * max(-slide, min(slide, float(np.linalg.norm(v)) - SK.REACH))
    for t in range(1, len(q)):                                # one hemisphere along the clip
        if np.dot(q[t, k], q[t - 1, k]) < 0:
            q[t, k] = -q[t, k]
    return DR.set_arrays(c, q, p)


# INTENT on a blade (kit/anim/intent.py, proc_candidates.INTENT_KICK - the owner, 2026-11-10: "there's aggressive,
# there's calm, there is proper"): the cut's stroke + follow-through segments x k (sudden = the short end) and the torso
# already turned `lead` of the way into the cut at the stroke's first beat (the hips drive it); k > 1 stretches it. Tuned
# on the kit home's katana kesa cut (lab 2026-11-11, _scratch/anim-intent/)
INTENT_BLADE = {"calm": {"k": (1.15, 1.3), "lead": (0.0, 0.05), "segs": ("antic", "stroke", "through"), "pay": "hold"},
                "proper": {"k": (0.72, 0.85), "lead": (0.05, 0.15), "segs": ("antic", "stroke", "through"), "pay": "hold"},
                "aggressive": {"k": (0.42, 0.5), "lead": (0.15, 0.3), "segs": ("antic", "stroke", "through"),
                               "pay": "hold"}}   # read on the BLADE's own sweep (intent.blade_strike):
# the kesa as designed reads PROPER (920 deg/s, an 11-frame snap) - calm slows the whole action (the raise, the swing over
# AND the cut, so the cut stays its fastest moment and the Hit its down-left sweep) and takes the time back out of the
# held zanshin (`pay`: the clip keeps its length, inside the dossier's 1.1 s); aggressive quickens the whole action to
# ~half and holds the zanshin longer (quickening the cut alone smeared its sweep into the slower raise: 1,200-1,700 deg/s)


def slide_of(role, ph, scale=1.0):
    """the loved weapon vocabulary's median slide for a role at a phase (torso frame), scaled so the role's biggest
    phase slide reaches the loved median slide_p95"""
    V = vocab()
    tab = V["slides"][role]
    big = max(np.linalg.norm(v) for v in tab.values())
    k = V["slide_p95"][role]["p50"] / max(big, 1e-6)
    return phase_vec(tab, ph) * k * scale


def key_pose(b, g, arms, feet=None, rng=None, yaw_of=None, facing=None):
    habit, whip = arms
    p = DR.rest()
    to = b["torso"]
    p = DR.turn(p, "Torso", [-to.get("pitch", 0.0) * D2R, 0.0, 0.0])
    p = DR.turn(p, "Torso", [0.0, 0.0, to.get("roll", 0.0) * D2R])
    p = DR.turn(p, "Torso", [0.0, to.get("yaw", 0.0) * D2R, 0.0])
    p["Torso"][4] += to.get("x", 0.0)
    p["Torso"][5] -= to.get("crouch", 0.0)
    p["Torso"][6] += to.get("z", 0.0)
    sw = b["sword"]
    hand, free = g["hand"], g["free"]
    ph = b.get("phase", "rest")
    # the blade's LINE is the stage's (the cut goes at the target, wherever the torso has turned): stage -> torso frame;
    # so is a `reach` (the shoulder -> hand direction on the stage); an `arm` is the torso-frame [forward, across]
    # (a sword with `frame: torso` rides the body; `frame: heading` turns with the body's YAW only - a spin carries the
    # blade round with it while it stays level whatever the bend: a flat disc, not a cone)
    qt = np.array(p["Torso"][:4])
    if sw.get("frame") == "torso":
        qi = np.array([0.0, 0.0, 0.0, 1.0])
    elif sw.get("frame") == "heading":
        qi = P.q_mul(P.q_inv(qt), P.q_exp(np.array([0.0, to.get("yaw", 0.0) * D2R, 0.0])))
    else:
        qi = P.q_inv(qt)
    bt = P.q_rot(qi, unit(sw["blade"]))
    if g.get("two_hand"):                                    # both fists on the hilt: no free arm to habit
        p = two_hand(p, P.q_rot(qi, unit(sw["reach"])), bt, g, facing)
    else:
        p = blade_arm(p, hand, P.q_rot(qi, unit(sw["reach"])) if "reach" in sw else sw["arm"], bt, sw.get("slide", 0.0))
        p[hand][4:7] = list(map(float, np.asarray(p[hand][4:7]) + float(g.get("sword_arm_vocab", 0.35)) * slide_of("sword_arm", ph)))
        fd = free_arm_dir(ph, habit, whip, p, free)
        if b.get("free"):
            # the beat's GUARD for the free arm (torso frame): a spin's fist tucked in / up, not a swing habit's fling
            # held through a whole turn (drill r2: the free arm folded across the chest, then stuck out low, sinking
            # in); the candidate's habit stays in it by 1 - w
            w = float(b["free"].get("w", 0.7))
            fd = unit((1.0 - w) * fd + w * unit(b["free"]["dir"]))
        p = DR.aim(p, free, fd)
        p[free][4:7] = list(map(float, slide_of("free_arm", ph)))
        p = on_socket(on_socket(p, hand, "sword_arm"), free, "free_arm")
        p = clear_of_body(clear_of_body(p, free, ARM_CLEAR_BAR), hand, ARM_CLEAR_BAR, "sword_arm")
    for leg, role in ((g["lead_leg"], "lead_leg"), (g["rear_leg"], "rear_leg")):
        p[leg][4:7] = list(map(float, slide_of(role, ph, float(g.get("leg_slide", 1.0)))))
        if feet and rng:
            # the key's legs ON its feet (the sim lifts the body wherever a straight key leg would go through the floor -
            # that erased the hang's crouch): stood upright, then reached to the beat's soles, the vocabulary slide kept
            s = sole_at(feet[leg], b["t"], yaw_of)
            qt = np.array(p["Torso"][:4])
            ql = P.q_inv(qt)
            ql, pl = DR.leg_ik_keep(qt, np.array(p["Torso"][4:7]), ql, np.array(p[leg][4:7]), leg,
                                    np.array([s[0], P.FLOOR + s[1], s[2]]), *rng[leg])
            p[leg] = list(map(float, ql)) + list(map(float, pl))
    hd = b.get("head", {})
    if hd.get("look"):
        qt, pt = np.array(p["Torso"][:4]), np.array(p["Torso"][4:7])
        p = DR.look_at(p, P.q_rot(P.q_inv(qt), np.asarray(g["target"], float) - pt), hd["look"])
    if hd.get("tilt"):
        p = DR.turn(p, "Head", [0.0, 0.0, hd["tilt"] * D2R])
    if b.get("drift"):                                       # the MOVING hold: it keeps settling, never a statue
        p = DR.turn(p, "Torso", [0.6 * D2R, 1.5 * D2R, 0.0])
        p = DR.turn(p, "Head", [-1.0 * D2R, 2.0 * D2R, 0.0])
    return p


# ---------------------------------------------------------------- the feet
def sole_at(steps, t, yaw_of=None):
    """-> (x, lift, z) of a foot at time t from its schedule (a step lifts on a sine arc between its two keys). An
    `orbit` step's `at` is in the BODY's frame, turned with the body's yaw (yaw_of(t), radians): a free foot riding a
    spin round the pivot foot - between two orbit steps it skims `skim` studs over the floor (it never drags), and it
    lands from that skim on the first orbit step without one; planted, it stays where it was at its own step's time"""
    yaw_of = yaw_of or (lambda _t: 0.0)

    def xz(st, at_t):
        a = np.asarray(st["at"], float)
        if not st.get("orbit"):
            return a
        y = float(yaw_of(at_t))
        return np.array([a[0] * math.cos(y) + a[1] * math.sin(y), -a[0] * math.sin(y) + a[1] * math.cos(y)])
    if t <= steps[0]["t"]:
        a = xz(steps[0], steps[0]["t"])
        return np.array([a[0], 0.0, a[1]])
    for s0, s1 in zip(steps, steps[1:]):
        if t <= s1["t"]:
            u = (t - s0["t"]) / max(s1["t"] - s0["t"], 1e-9)
            e = u * u * (3 - 2 * u)
            if s0.get("orbit") and s1.get("orbit"):
                a, z = xz(s0, t), xz(s1, t)
                h = float(s1["skim"]) if s1.get("skim") else float(s0.get("skim", 0.0)) * (1 - e)
            else:
                a, z = xz(s0, s0["t"]), xz(s1, s1["t"])
                h = float(s1.get("lift", 0.0)) * math.sin(math.pi * u) if np.linalg.norm(z - a) > 1e-6 else 0.0
            v = a + (z - a) * e
            return np.array([v[0], h, v[1]])
    a = xz(steps[-1], steps[-1]["t"])
    return np.array([a[0], 0.0, a[1]])


def feet_pass(c, g, feet, share, rng):
    """legs by IK to the schedule: each leg first stood upright facing its foot's yaw (a stepping / planted lead foot
    keeps its own; the rear foot pivots on its sole with the hips by `share`), its vocabulary slide kept"""
    q, p = DR.arrays(c)
    n = len(q)
    yaw_t = np.unwrap([math.atan2(-f[0], -f[2]) for f in (P.q_rot(qq, np.array([0.0, 0.0, -1.0])) for qq in q[:, 0])])
    q0, p0 = q.copy(), p.copy()
    legs = (g["lead_leg"], g["rear_leg"])

    def yaw_of(tt):
        return float(np.interp(tt * 60, np.arange(n), yaw_t))
    goals = {leg: np.array([[s[0], P.FLOOR + s[1], s[2]] for s in (sole_at(feet[leg], t / 60, yaw_of) for t in range(n))]) for leg in legs}
    # how much each foot turns with the hips: the stepping lead foot a little, the rear foot by the loved share; a
    # gesture may set its own (a spin: the pivot foot turns wholly on its sole, the orbiting foot rides round)
    shares = {g["lead_leg"]: 0.35, g["rear_leg"]: share, **(g.get("pivot_share") or {})}

    def solve():
        for leg in legs:
            k = J.index(leg)
            for t in range(n):
                yaw = yaw_t[0] + shares[leg] * (yaw_t[t] - yaw_t[0])
                ql = P.q_mul(P.q_inv(q[t, 0]), P.q_exp(np.array([0.0, yaw, 0.0])))
                q[t, k], p[t, k] = DR.leg_ik_keep(q[t, 0], p[t, 0], ql, p0[t, k], leg, goals[leg][t], *rng[leg])
    # a leg the slide range cannot stretch to its planted sole DRAWS THE BODY toward it (the body follows the foot,
    # never the foot the body - a short leg let the rear sole skid 0.10-0.17 studs a frame in the coil); the pull is
    # smoothed over frames so the torso never pops
    for _ in range(4):
        solve()
        pull = np.zeros((n, 3))
        for leg in legs:
            k = J.index(leg)
            for t in range(n):
                e = goals[leg][t] - P.sole_char(q[t, 0], p[t, 0], q[t, k], p[t, k], leg)
                if goals[leg][t][1] <= P.FLOOR + 1e-6 and np.linalg.norm(e) > 0.004:
                    pull[t] += e / len(legs) * 1.6
        if np.abs(pull).max() < 0.004:
            break
        w = 4
        pad = np.concatenate([pull[:1].repeat(w, 0), pull, pull[-1:].repeat(w, 0)])
        pull = np.stack([np.convolve(pad[:, i], np.ones(2 * w + 1) / (2 * w + 1), "valid") for i in range(3)], axis=1)
        p[:, 0] += pull
    solve()
    del q0
    # where a leg could not reach down (slide range) the body sinks / where a sole would dig in the body lifts
    for t in range(n):
        for leg in (g["lead_leg"], g["rear_leg"]):
            k = J.index(leg)
            s = sole_at(feet[leg], t / 60)
            err = P.sole_char(q[t, 0], p[t, 0], q[t, k], p[t, k], leg)[1] - (P.FLOOR + s[1])
            if err < 0:
                p[t, 0, 1] -= err
    return DR.set_arrays(c, q, p)


# ---------------------------------------------------------------- the blade
def blade_tracks(c, length, grip=1.23, kind=None, two_hand=False, spacing=0.5):
    """the welded blade per frame from the grip arm's part frame (character space, no root): grip, tip, edge. Two-handed:
    the blade runs along the hilt the two fists hold - from the lower (free) fist through the upper one - its grip the
    point between them, its tip `length - spacing / 2` on (strike.py's two-handed sword track)"""
    rig = C.load_rig("r6")
    tips, grips, edges = [], [], []
    for i in range(len(c["times"])):
        F = C.fk(rig, C.character_transforms(c, rig, i))
        A = F["Right Arm"]
        if two_hand:
            hi, lo = (A @ np.r_[GRIP_LOCAL, 1.0])[:3], (F["Left Arm"] @ np.r_[GRIP_LOCAL, 1.0])[:3]
            d, g = unit(hi - lo), 0.5 * (hi + lo)
            grips.append(g)
            tips.append(g + d * (length - spacing / 2))
            e = -unit(A[:3, :3] @ np.array([1.0, 0.0, 0.0]))
            edges.append(unit(e - float(e @ d) * d) if np.linalg.norm(e - float(e @ d) * d) > 1e-6 else e)
            continue
        g = (A @ np.r_[GRIP_LOCAL, 1.0])[:3]
        d = unit(A[:3, :3] @ BLADE_LOCAL)
        grips.append(g)
        tips.append(g + d * length)
        edges.append(-unit(A[:3, :3] @ np.array([1.0, 0.0, 0.0])))
    out = {"length": length, "grip": grip, "tip": [[round(float(x), 4) for x in v] for v in tips],
           "grip_path": [[round(float(x), 4) for x in v] for v in grips], "edge": [[round(float(x), 4) for x in v] for v in edges]}
    if kind:
        out["kind"] = kind
    return out


def place_hit(c, a_s, z_s):
    """the Hit on the tip's speed peak inside the strike window, then within 0..3 frames after the engine's own peak"""
    tip = np.asarray(c["sword"]["tip"], float)
    sp = np.r_[np.linalg.norm(np.diff(tip, axis=0), axis=1) * 60, 0.0]
    a, z = int(a_s * 60), min(len(sp) - 1, int(z_s * 60) + 1)
    f = a + int(np.argmax(sp[a:z + 1]))
    c["events"] = [{"t": float(c["times"][f]), "name": "Hit", "by": "Blade"}]
    ev = (C.metrics(c, C.load_rig("r6")).get("events") or [{}])[0]
    if ev.get("peak_t") is not None:
        pk = int(round(float(ev["peak_t"]) * 60))
        f = min(max(f, pk), pk + 3, len(c["times"]) - 1)
        c["events"][0]["t"] = float(c["times"][f])
    return c


def parse_arms(a):
    """'habit:<h>:<whip>' -> (h, [whip, deg]); 'prior:<mode>:<whip>' -> (('prior', mode), ...); the whip's size from
    the loved free-arm whip band (its median, kept within 35-70 deg)"""
    parts = (a or HABITS[0]).split(":")
    deg = float(np.clip(vocab()["whip_deg"]["free_arm"]["p50"], 35, 70))
    src = ("prior", int(parts[1])) if parts[0] == "prior" else int(parts[1])
    return src, ([parts[2], deg] if len(parts) > 2 and parts[2] in WHIPS else None)


def build(d, s, name, rng=None, intent=None):
    """-> (clip, build) for proc_candidates: the gesture's beats through the efforts (and an intent's aim) -> key poses
    -> springs -> feet -> the blade -> the Hit"""
    import proc_kick as PK
    g = gesture_for(d, name)
    s = {"time": 0.0, "weight": 0.0, "space": 0.0, "flow": 0.0, **(s or {})}
    beats, feet, end, _ = effort(g, s, intent)
    S, keyed = spin_layer(beats)                            # a spin: its own yaw layer; the keys de-spun
    arms = parse_arms(s.get("arms"))
    rng = rng or PK.slide_ranges()
    # a beat's `stiff` (> 1) settles the springs faster on the segment after it (the finish: a snap, then STILL)
    bt_, by_ = [b["t"] for b in keyed], [float(b["torso"].get("yaw", 0.0)) * D2R for b in keyed]

    def yaw_of(tt):
        return float(np.interp(tt, bt_, by_))
    fc = {}                                                  # (two-handed: the arm boxes' facing, key to key)
    poses = [{"pose": key_pose(b, g, arms, feet, rng, yaw_of, fc), "t": b["t"], "stiff": float(b.get("stiff", 1.0)), "name": b["name"]} for b in keyed]
    for k0, k1 in zip(poses, poses[1:]):                     # each key's quaternions on the previous key's hemisphere
        for j in J:                                          # (a sign flip sent the interpolation the long way round)
            if np.dot(k0["pose"][j][:4], k1["pose"][j][:4]) < 0:
                k1["pose"][j][:4] = [-x for x in k1["pose"][j][:4]]
    fl = float(s.get("flow", 0.0))
    pr = {"follow": {j: float(np.clip(v * (1 + 0.6 * fl), 0.05, 0.9)) for j, v in FOLLOW.items()},
          "delay": dict(DRAG_S), "lean_v": 0.0, "lean_a": 0.0}
    c = P.sim(poses + [{"pose": poses[-1]["pose"], "t": end, "stiff": 1.0}], end, pr, plant=False, slide_range=rng,
              name=name, interp="hermite")
    c["loop"] = False
    c = apply_spin(c, S)
    share = float(np.clip(vocab()["pivot_share"]["p50"] + 0.15 * float(s.get("space", 0.0)), 0.2, 0.95))
    c = feet_pass(c, g, feet, share, rng)
    if g.get("two_hand"):
        stage = all((b.get("sword") or {}).get("frame") in (None, "stage") for b in beats)
        c = hilt_pass(c, g, designed_blade(beats, len(c["times"])) if stage else None)
    sw = d["build"].get("sword") or {}
    c["sword"] = blade_tracks(c, float(sw.get("length", 5.03)), float(sw.get("grip", 1.23)), sw.get("kind"),
                              two_hand=bool(g.get("two_hand")), spacing=float(g.get("grip_spacing", 0.5)))
    import grip as GR
    GR.add_grip(c)
    st = next(b for b in beats if b.get("phase") == "strike")
    prev = beats[max(0, beats.index(st) - 1)]
    c = place_hit(c, prev["t"], st["t"] + 0.06)
    if g.get("events_at"):
        # a move whose beat IS its moment (a drill's dead stop = the burst): the events on that beat's frame - the Hit
        # no later than 3 frames after the blade's last speed peak before it (the engine's rule; a dead stop comes a
        # few frames after the spin's last fastest frame)
        at = {b["name"]: b["t"] for b in beats}
        n = len(c["times"])
        tip = np.asarray(c["sword"]["tip"], float)
        sp = np.r_[0.0, np.linalg.norm(np.diff(tip, axis=0), axis=1)]
        evs = []
        for nm, bn in g["events_at"].items():
            f = min(n - 1, int(round(at[bn] * 60)))
            if nm == "Hit":
                # a strike peak as the engine counts one (clip.metrics): a local speed peak reaching 40 % of the clip's
                # top - the small bumps of the deceleration into a dead stop are not strikes (2026-11-05: counting them
                # left the Hit 4-6 frames after the engine's peak)
                top = float(sp.max())
                pk = max((i for i in range(1, f + 1) if i + 1 < n and sp[i] >= 0.4 * top and sp[i] >= sp[i - 1]
                          and sp[i] > sp[i + 1]), default=f)
                f = min(f, pk + 3)
            evs.append({"name": nm, "t": float(c["times"][f]), **({"by": "Blade"} if nm == "Hit" else {})})
        c["events"] = evs
    c["dossier"] = d["name"]
    import clip_beats as CB                                  # (its own beats in the clip: the sheet poses them, j6x7)
    c["beats"] = CB.from_keys([(b["t"], b.get("name")) for b in beats], float(c["times"][-1]))
    c["source"] = {"kind": "proc_blade", "gesture": g["name"], "efforts": {k: s[k] for k in ("time", "weight", "space", "flow")},
                   "arms": s.get("arms"), "pivot_share": round(share, 3)}
    return c, {**d["build"], "slides": "weapon_vocab", "gesture": g["name"]}


# ---------------------------------------------------------------- the vocabulary gate + the calibration numbers
def vocab_check(c):
    """-> (fails, warns, numbers): every limb against the loved weapon vocabulary. FAIL = a limb frozen below the loved
    MINIMUM on both its slide and its swing (no loved clip is); WARN = a number outside the loved p10-p90"""
    import r6_vocab as RV
    V = vocab()
    hit = next((float(e["t"]) for e in c.get("events", []) if e.get("name") == "Hit"), None)
    row = RV.weapon_row(c, pk=None if hit is None else int(round(hit * 60)))   # OUR strike is the Hit (a flourish
    # can turn the arm as fast; the loved swings' arm peak is their cut)
    nums = {"torso_peak_deg_s": row["torso_peak_deg_s"], "torso_turn_deg": row["torso_turn_deg"],
            "pivot_share": row["pivot_share"], "whip_sword_arm": row["whip"]["sword_arm"], "whip_free_arm": row["whip"]["free_arm"],
            "lag_head": row["lag"]["head"], "lag_sword_arm": row["lag"]["sword_arm"], "lag_free_arm": row["lag"]["free_arm"]}
    fails, warns = [], []
    for r in RV.WROLE:
        sl = float(np.percentile([np.linalg.norm(row["slides"][r][ph]) for ph in RV.WPH], 95))
        nums[f"slide_{r}"] = sl
        nums[f"swing_{r}"] = row["swing"][r]
        if sl < V["slide_p95"][r]["min"] and row["swing"][r] < V["swing_deg"][r]["min"]:
            fails.append(f"vocab: {r} frozen (slide {sl:.2f} < {V['slide_p95'][r]['min']}, swing {row['swing'][r]:.0f} < {V['swing_deg'][r]['min']})")
    bands = {"torso_peak_deg_s": V["torso_peak_deg_s"], "pivot_share": V["pivot_share"], "whip_free_arm": V["whip_deg"]["free_arm"],
             "whip_sword_arm": V["whip_deg"]["sword_arm"], **{f"slide_{r}": V["slide_p95"][r] for r in RV.WROLE},
             **{f"swing_{r}": V["swing_deg"][r] for r in RV.WROLE}}
    for k, bd in bands.items():
        v = nums.get(k)
        if v is not None and not (bd["p10"] <= v <= bd["p90"]):
            warns.append(f"{k} {v:.2f} outside loved p10-p90 [{bd['p10']}, {bd['p90']}]")
    return fails, warns, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in nums.items()}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import proc_dossier as DS
    a = sys.argv[1:]
    d = DS.require(a[a.index("--dossier") + 1])
    s = json.loads(a[a.index("--genome") + 1]) if "--genome" in a else {}
    c, b = build(d, s, a[0])
    out = a[a.index("--out") + 1] if "--out" in a else os.path.join("_artifacts", "gt-anim", "blade", f"{a[0]}.clip.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(c, open(out, "w", encoding="utf-8"))
    f, w, nums = vocab_check(c)
    print(json.dumps({"clip": out, "hit": c["events"], "vocab_fails": f, "vocab_warns": w, "numbers": nums}, indent=1))
