"""proc_director.py — the DIRECTOR for procedural R6 FROM SCRATCH (plan: board/plans/archive/2026-10-13-proc-from-scratch-plan.md,
step 3). An intent becomes a timed BEAT SCRIPT; each beat is a GESTURE from the library (assets/animations/gestures/*.json,
R6 angles from the craft research); the director turns beats into key poses + layers, the engine (proc_r6 hermite +
tracking springs) makes the motion. No pose comes from a clip.
  acting rules   a THOUGHT beat first (the head glances toward the target 0.2-0.5 s before the arm moves - acting is
                 reacting); prep -> a fast stroke (loved R6 idles: ~0.2 s rises) -> a MOVING hold (keeps drifting) ->
                 retract; beats under 1.5 s apart CHAIN (no drop to rest between them - returning to rest every time
                 reads nervous); arm gestures recruit the torso + head (arm-only reads robotic); the R6 no-elbow rule:
                 the head goes to the hand, chest-height gestures cap the arm at ~70 deg
  stance         contrapposto: weight over one leg, that shoulder lower, the free foot forward + turned out, head
                 counter-tilted, arms not mirrored
  life           breathing (inhale 40 % / exhale 60 %), smoothed Ornstein-Uhlenbeck sway on torso / head / arms,
                 seamless over the loop; feet re-planted by IK
    from proc_director import idle   (see diagnostics/proc_idle_v4.py)"""
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
import proc_r6 as P  # noqa: E402

J = P.JOINTS
LIB = os.path.join("assets", "animations", "gestures")
D2R = math.pi / 180
_G = None


def geom():
    global _G
    if _G is None:
        r = C.load_rig("r6")
        _G = {j: (np.asarray(r["joints"][j]["c0"][:3], float), np.array([0.0, -1.0, 0.0]) - np.asarray(r["joints"][j]["c1"][:3], float))
              for j in ("Right Arm", "Left Arm", "Right Leg", "Left Leg")}
    return _G


def gesture(name):
    return json.load(open(os.path.join(LIB, f"{name}.json"), encoding="utf-8"))


# ---------------------------------------------------------------- pose helpers (character space)
def rest():
    return {j: [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for j in J}


def turn(pose, joint, rv):
    p = copy.deepcopy(pose)
    p[joint][:4] = list(map(float, P.q_mul(P.q_exp(np.asarray(rv, float)), np.array(p[joint][:4]))))
    return p


def end(pose, limb):
    c0, v = geom()[limb]
    return c0 + np.array(pose[limb][4:7]) + P.q_rot(np.array(pose[limb][:4]), v)


def aim(pose, limb, direction, frac=1.0):
    """turn a limb (shortest arc) so pivot -> end points along `direction` (torso frame)"""
    c0, v = geom()[limb]
    cur = P.q_rot(np.array(pose[limb][:4]), v)
    a, b = cur / np.linalg.norm(cur), np.asarray(direction, float) / np.linalg.norm(direction)
    ax = np.cross(a, b)
    if np.linalg.norm(ax) < 1e-9:
        return copy.deepcopy(pose)
    ang = math.atan2(np.linalg.norm(ax), float(a @ b)) * frac
    return turn(pose, limb, ax / np.linalg.norm(ax) * ang)


def roll(pose, limb, deg):
    c0, v = geom()[limb]
    a = P.q_rot(np.array(pose[limb][:4]), v)
    return turn(pose, limb, a / np.linalg.norm(a) * deg * D2R)


def look_at(pose, target, frac=1.0):
    q = np.array(pose["Head"][:4])
    face = P.q_rot(q, np.array([0.0, 0.0, -1.0]))
    want = np.asarray(target, float) - np.array([0.0, 1.5, 0.0])
    a, b = face / np.linalg.norm(face), want / np.linalg.norm(want)
    ax = np.cross(a, b)
    if np.linalg.norm(ax) < 1e-9:
        return copy.deepcopy(pose)
    return turn(pose, "Head", ax / np.linalg.norm(ax) * math.atan2(np.linalg.norm(ax), float(a @ b)) * frac)


def arm_dir(side, forward_deg, across_deg):
    """the arm's pivot -> hand direction: forward_deg up from hanging (90 = horizontal forward), across_deg toward the
    body's midline. side 'Left' (the arm at -X, midline is +X) / 'Right'"""
    f, a = forward_deg * D2R, across_deg * D2R
    inward = 1.0 if side == "Left" else -1.0
    return np.array([inward * math.sin(a) * math.sin(f), -math.cos(f), -math.cos(a) * math.sin(f)])


def stance(side):
    """contrapposto. side +1: weight over the RIGHT leg (+X), -1: over the left"""
    p = rest()
    p["Torso"][4] += 0.10 * side
    p["Torso"][5] -= 0.04
    p = turn(p, "Torso", [-0.025, 0.04 * side, -0.035 * side])
    p = turn(p, "Head", [-0.04, -0.05 * side, 0.045 * side])
    sup, free = ("Right", "Left") if side > 0 else ("Left", "Right")
    s = 1 if sup == "Right" else -1
    p = turn(p, f"{sup} Arm", [0.05, 0.0, 0.05 * s])
    p = turn(p, f"{free} Arm", [0.11, 0.03 * s, -0.07 * s])
    p = turn(p, f"{free} Leg", [0.13, 0.14 * s, -0.07 * s])
    p = turn(p, f"{sup} Leg", [-0.03, 0.0, 0.02 * s])
    return p


# ---------------------------------------------------------------- gestures -> keys
def watch_check(base, t0, g=None, solver=None):
    """solver(base, arm, hand_target) -> pose: a learned pose prior (kit/anim/pose_prior.solve) decides the torso, head
    and other arm around the hand target instead of the spec's hand-set angles"""
    g = g or gesture("watch_check")
    side = g["arm"]["side"]
    arm = f"{side} Arm"
    other = "Right Arm" if side == "Left" else "Left Arm"
    ph = g["phases"]
    tw = g["torso"]["twist_toward_arm_deg"] * (1 if side == "Left" else -1)        # yaw + turns the face to -X (left)
    up = aim(base, arm, arm_dir(side, g["arm"]["forward_deg"], g["arm"]["across_deg"]))
    up = roll(up, arm, g["arm"]["roll_deg"])
    up = turn(up, "Torso", [g["torso"]["pitch_deg"] * D2R, tw * D2R, 0.0])
    up = turn(up, other, [g["other_arm"]["forward_deg"] * D2R, 0.0, 0.0])
    hand = end(up, arm)
    if solver is not None:                                   # the same hand target; the prior poses the rest
        up = roll(solver(base, arm, hand, end(base, other)), arm, g["arm"]["roll_deg"])   # one solver form everywhere
        up = look_at(up, hand, g["head"]["frac"])            # the R6 rule still holds: the head goes to the hand
    up = look_at(up, hand, g["head"]["frac"])
    thought = look_at(base, hand, g["thought"]["frac"])
    prep = turn(thought, arm, [-0.06, 0.0, 0.0])                                      # a small dip back before it rises
    mid = roll(aim(prep, arm, arm_dir(side, g["arm"]["forward_deg"] * 0.55, g["arm"]["across_deg"] * 0.5)), arm, g["arm"]["roll_deg"] * 0.4)
    drift = turn(roll(up, arm, g["moving_hold"]["roll_deg"]), "Head", [g["moving_hold"]["head_pitch_deg"] * D2R, 0, 0])
    t_th = t0 - g["thought"]["lead_s"]
    s0 = t0 + ph["prep_s"]
    keys = [{"pose": thought, "t": t_th + 0.25}, {"pose": prep, "t": t0 + ph["prep_s"] * 0.8},
            {"pose": mid, "t": s0 + ph["stroke_s"] * 0.5}, {"pose": up, "t": s0 + ph["stroke_s"]},
            {"pose": drift, "t": s0 + ph["stroke_s"] + ph["hold_s"]}]
    t_end = s0 + ph["stroke_s"] + ph["hold_s"]
    return keys, t_end, {"hand_torso_frame": [round(float(x), 2) for x in hand]}


def retract(base, t, g_ret=0.45):
    return [{"pose": base, "t": t + g_ret}], t + g_ret


def glance(base, t0, direction=1, g=None):
    g = g or gesture("glance")
    ph = g["phases"]
    yaw = g["head"]["yaw_deg"] * D2R * direction
    look = turn(base, "Head", [g["head"]["pitch_deg"] * D2R, yaw, 0.0])
    body = turn(look, "Torso", [0.0, g["torso"]["yaw_deg"] * D2R * direction, 0.0])
    s0 = t0 + ph["prep_s"]
    keys = [{"pose": look, "t": s0 + ph["stroke_s"]}, {"pose": body, "t": s0 + ph["stroke_s"] + g["torso"]["delay_s"]},
            {"pose": turn(body, "Head", [-0.02, -0.04 * direction, 0.0]), "t": s0 + ph["stroke_s"] + ph["hold_s"]}]
    return keys, s0 + ph["stroke_s"] + ph["hold_s"] + ph["retract_s"], ph["retract_s"]


def sigh(base, t0, g=None):
    g = g or gesture("sigh")
    i, e = g["inhale"], g["exhale"]
    up = turn(base, "Torso", [i["torso_pitch_deg"] * D2R, 0, 0])
    up["Torso"][5] += i["rise_studs"]
    down = turn(turn(base, "Torso", [e["torso_pitch_deg"] * D2R, 0, 0]), "Head", [e["head_pitch_deg"] * D2R, 0, 0])
    down["Torso"][5] -= e["sink_studs"]
    for arm, s in (("Right Arm", 1), ("Left Arm", -1)):
        down = turn(down, arm, [0, 0, -e["arms_in_deg"] * D2R * s])
    return [{"pose": up, "t": t0 + i["s"]}, {"pose": down, "t": t0 + i["s"] + e["s"]}, {"pose": base, "t": t0 + i["s"] + e["s"] + 0.7}], \
        t0 + i["s"] + e["s"] + 0.7


def weight_shift(frm, to, t0, g=None):
    g = g or gesture("weight_shift")
    mid = copy.deepcopy(frm)
    for j in J:
        a, b = np.array(frm[j][:4]), np.array(to[j][:4])
        mid[j][:4] = list(map(float, P.q_mul(P.q_exp(0.5 * P.q_log(P.q_mul(b, P.q_inv(a)))), a)))
        mid[j][4:7] = list((np.array(frm[j][4:7]) + np.array(to[j][4:7])) / 2)
    mid["Torso"][5] -= g["dip_studs"]
    ph = g["phases"]
    return [{"pose": mid, "t": t0 + ph["stroke_s"] * 0.5}, {"pose": to, "t": t0 + ph["stroke_s"]}], t0 + ph["stroke_s"] + ph["settle_s"]


# ---------------------------------------------------------------- layers
def ou(n, rs, sigma, tau, fps=60, smooth=0.25):
    x = np.zeros((n + fps, 3))
    a = np.exp(-1.0 / (tau * fps))
    for t in range(1, len(x)):
        x[t] = a * x[t - 1] + np.sqrt(1 - a * a) * rs.standard_normal(3)
    y = x[fps:].copy()
    w = np.linspace(0, 1, fps)[:, None]
    y[n - fps:] = (1 - w) * y[n - fps:] + w * x[:fps]
    s = smooth * fps
    r = int(3 * s)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    y = np.stack([np.convolve(np.r_[y[-r:, i], y[:, i], y[:r, i]], k, "valid") for i in range(3)], 1)
    return sigma * y / max(float(y.std()), 1e-9)


def arrays(c):
    T = len(c["times"])
    q = np.array([[c["joints"][j]["frames"][t][:4] for j in J] for t in range(T)], float)
    p = np.array([[c["joints"][j]["frames"][t][4:7] for j in J] for t in range(T)], float)
    return q, p


def set_arrays(c, q, p):
    c = copy.deepcopy(c)
    for k, j in enumerate(J):
        c["joints"][j] = {"frames": [list(map(float, q[t, k])) + list(map(float, p[t, k])) for t in range(len(q))]}
    c["times"] = [round(t / 60, 6) for t in range(len(q))]
    return c


def life(c, rng, rs, seconds, amp):
    q, p = arrays(c)
    n = len(q)
    soles = {leg: [P.sole_char(q[t, 0], p[t, 0], q[t, k], p[t, k], leg) for t in range(n)] for k, leg in ((4, "Right Leg"), (5, "Left Leg"))}
    nb = max(1, int(round(seconds / amp["period"])))
    noise = {j: ou(n, rs, amp[j], tau) for j, tau in (("Torso", 1.6), ("Head", 0.9), ("Right Arm", 1.2), ("Left Arm", 1.3))}
    # the R6 VOCABULARY in an idle: loved idles' limbs never sit at a frozen slide - each wobbles ~0.035-0.04 studs (std;
    # 12 loved idles, r6_vocab 2026-10-16) and ours were exactly 0. Arms drift slowly and rise a touch with each breath
    slide_noise = {arm: ou(n, rs, amp.get("arm_slide", 0.035), tau) for arm, tau in (("Right Arm", 1.7), ("Left Arm", 1.9))}
    for t in range(n):
        ph = (t / n * nb) % 1.0
        b = math.sin(math.pi * ph / 0.4 / 2) ** 2 if ph < 0.4 else math.cos(math.pi * (ph - 0.4) / 0.6 / 2) ** 2
        q[t, 0] = P.q_mul(P.q_exp(np.array([amp["breath"] * b, 0.0, 0.0]) + noise["Torso"][t] * [0.4, 1.0, 0.7]), q[t, 0])
        p[t, 0] += [0.0, amp["rise"] * b, 0.0]
        q[t, 1] = P.q_mul(P.q_exp(noise["Head"][t] * [0.7, 1.0, 0.6] - np.array([amp["breath"] * 0.5 * b, 0, 0])), q[t, 1])
        for k, arm, s in ((2, "Right Arm", 1), (3, "Left Arm", -1)):
            q[t, k] = P.q_mul(P.q_exp(noise[arm][t] * [1.0, 0.3, 0.6] + np.array([0.0, 0.0, amp["arm_breath"] * b * s])), q[t, k])
            p[t, k] = p[t, k] + slide_noise[arm][t] * np.array([0.6, 1.0, 0.6]) + np.array([0.0, 0.02 * b, 0.0])
        for k, leg in ((4, "Right Leg"), (5, "Left Leg")):
            q[t, k], p[t, k] = leg_ik_keep(q[t, 0], p[t, 0], q[t, k], p[t, k], leg, soles[leg][t], *rng[leg])
    return set_arrays(c, q, p)


def foot_taps(c, windows, rs, g=None):
    """gentle toe taps of the free foot: raised-cosine lifts (a one-piece R6 leg: tilt + a small slide up, tilt alone
    lifted the sole 0.003 studs), a little timing jitter (soft, not a metronome), a tiny head nod on each tap"""
    g = g or gesture("foot_tap")
    tp = g["tap"]
    q, p = arrays(c)
    n = len(q)
    for t0, t1, leg in windows:
        k = J.index(leg)
        beat, t = [], t0
        while t < t1:
            beat.append(t)
            t += (1.0 / tp["rate_hz"]) * (1 + rs.uniform(-tp["jitter"], tp["jitter"]))
        dur = tp["up_share"] / tp["rate_hz"]
        for f in range(int(t0 * 60), min(n, int(t1 * 60) + 1)):
            tt = f / 60.0
            bump = 0.0
            for b in beat:
                if 0 <= tt - b < dur:
                    bump = 0.5 - 0.5 * math.cos(2 * math.pi * (tt - b) / dur)
            env = min(1.0, (tt - t0) / 0.35, (t1 - tt) / 0.35)
            env = max(0.0, env)
            q[f, k] = P.q_mul(P.q_exp(np.array([tp["pitch_deg"] * D2R * bump * env, 0.0, 0.0])), q[f, k])
            p[f, k] = p[f, k] + [0.0, tp["lift_studs"] * bump * env, 0.0]
            q[f, 1] = P.q_mul(P.q_exp(np.array([-g["head"]["nod_deg"] * D2R * bump * env, 0.0, 0.0])), q[f, 1])
    return set_arrays(c, q, p)


# ---------------------------------------------------------------- combat: a kick from scratch
def ready_stance(g):
    r = g["ready"]
    p = rest()
    p = turn(p, "Torso", [r["lean_deg"] * D2R, -r["blade_deg"] * D2R, 0.0])
    p = turn(p, "Head", [0.03, r["blade_deg"] * 0.8 * D2R, 0.0])                 # eyes stay on the target
    p = turn(p, g["support_leg"], [r["lead_foot_deg"] * D2R, 0.0, 0.0])
    p = turn(p, g["kick_leg"], [r["rear_foot_deg"] * D2R, 0.0, 0.06])
    for side in ("Left", "Right"):
        p = aim(p, f"{side} Arm", arm_dir(side, r["guard"]["forward_deg"], r["guard"]["across_deg"]))
    return p


def front_kick(g=None):
    """-> keys, ready pose, the strike time (s). Legs: +X turns a leg forward (the same convention as an arm)"""
    g = g or gesture("front_kick")
    K, S = g["kick_leg"], g["support_leg"]
    base = ready_stance(g)
    sh = g["shift"]
    shift = turn(base, "Torso", [sh["torso_back_deg"] * D2R, 0.0, 0.0])
    shift["Torso"][4] += sh["torso_x_studs"] if K == "Right Leg" else -sh["torso_x_studs"]   # over the support foot
    shift["Torso"][5] -= sh["dip_studs"]

    def leg_up(p, deg, lift=0.0):
        p = aim(p, K, [0.0, -math.cos(deg * D2R), -math.sin(deg * D2R)])
        p[K][5] += lift
        return p
    ch = g["chamber"]
    cham = leg_up(turn(shift, "Torso", [ch["torso_back_deg"] * D2R, 0.0, 0.0]), ch["leg_deg"], ch["leg_lift_studs"])
    st = g["strike"]
    strike = leg_up(turn(shift, "Torso", [st["torso_back_deg"] * D2R, 0.0, 0.0]), st["leg_deg"], ch["leg_lift_studs"])
    strike = turn(strike, "Head", [st["head_counter_deg"] * D2R, 0.0, 0.0])
    rear, lead = ("Right", "Left") if K == "Right Leg" else ("Left", "Right")
    strike = aim(strike, f"{rear} Arm", arm_dir(rear, st["rear_arm"]["forward_deg"], st["rear_arm"]["across_deg"]))
    strike = aim(strike, f"{lead} Arm", arm_dir(lead, st["lead_arm"]["forward_deg"], st["lead_arm"]["across_deg"]))
    hold = leg_up(strike, g["hold"]["leg_deg"], ch["leg_lift_studs"])
    ret = leg_up(turn(shift, "Torso", [ch["torso_back_deg"] * D2R, 0.0, 0.0]), g["retract"]["leg_deg"], ch["leg_lift_studs"] * 0.6)
    keys = [{"pose": base, "t": 0.0}, {"pose": shift, "t": sh["t"]}, {"pose": cham, "t": ch["t"]},
            {"pose": strike, "t": st["t"]}, {"pose": hold, "t": g["hold"]["t"]}, {"pose": ret, "t": g["retract"]["t"]},
            {"pose": base, "t": g["recover"]["t"]}, {"pose": base, "t": g["end_s"]}]
    return keys, base, st["t"]


def slowmo_beat(c, f, n=4):
    """an impact beat without a pop: the step from frame f to f+1 played over n extra eased frames"""
    q, p = arrays(c)
    us = np.linspace(0, 1, n + 2)[1:-1] ** 1.6
    iq = [np.array([P.q_mul(P.q_exp(u * P.q_log(P.q_mul(q[f + 1, k], P.q_inv(q[f, k])))), q[f, k]) for k in range(6)]) for u in us]
    ip = [p[f] + u * (p[f + 1] - p[f]) for u in us]
    return set_arrays(c, np.concatenate([q[:f + 1], np.array(iq), q[f + 1:]]), np.concatenate([p[:f + 1], np.array(ip), p[f + 1:]]))


# ---------------------------------------------------------------- generic POSE GESTURES (data-driven)
def pose_from(base, spec, solver=None):
    """a gesture's pose from its spec: hand targets (torso frame, or "rest" = where the stance has it), solved by the
    learned prior when given (both hands as constraints) else aimed directly; then the R6 compensations: torso
    offsets, shoulder lifts (slides), arm rolls, the head's look + tilt"""
    tg = spec.get("targets", {})
    pts = {a: (end(base, a) if v == "rest" else np.asarray(v, float)) for a, v in tg.items()}
    pose = copy.deepcopy(base)
    moving = [a for a, v in tg.items() if v != "rest"]
    if solver is not None and moving:
        lead = moving[0]
        other = "Right Arm" if lead == "Left Arm" else "Left Arm"
        pose = solver(base, lead, pts[lead], pts.get(other, end(base, other)))
        # the STANCE owns the torso: the prior brought its own (a 0.5-stud crouch + 24 deg tilt for the phone - hands
        # low in front mostly occur in crouched dance / fight poses in its data); keep the stance's position and let the
        # prior turn the torso at most `prior_torso_max_deg` (a little lean into the gesture, as in idle v4b)
        pose["Torso"][4:7] = list(base["Torso"][4:7])
        qb, qp = np.array(base["Torso"][:4]), np.array(pose["Torso"][:4])
        d = P.q_log(P.q_mul(qp, P.q_inv(qb)))
        lim = spec.get("prior_torso_max_deg", 8.0) * D2R
        if np.linalg.norm(d) > lim:
            d = d / np.linalg.norm(d) * lim
        pose["Torso"][:4] = list(map(float, P.q_mul(P.q_exp(d), qb)))
        for a in moving[1:]:
            c0, _ = geom()[a]
            pose = aim(pose, a, pts[a] - c0 - np.array(pose[a][4:7]))
    else:
        for a in moving:
            c0, _ = geom()[a]
            pose = aim(pose, a, pts[a] - c0 - np.array(pose[a][4:7]))
    to = spec.get("torso", {})
    pose = turn(pose, "Torso", [to.get("pitch_deg", 0) * D2R, to.get("yaw_deg", 0) * D2R, to.get("roll_deg", 0) * D2R])
    pose["Torso"][4] += to.get("dx", 0.0)
    pose["Torso"][5] += to.get("dy", 0.0)
    for a, dy in spec.get("lift", {}).items():
        pose[a][5] += dy
    for a, deg in spec.get("roll", {}).items():
        pose = roll(pose, a, deg)
    hd = spec.get("head", {})
    look = hd.get("look")
    if look:
        tgt = end(pose, look) if look in ("Left Arm", "Right Arm") else np.asarray(look, float)
        pose = look_at(pose, tgt, hd.get("frac", 0.8))
    pose = turn(pose, "Head", [hd.get("pitch_deg", 0) * D2R, hd.get("yaw_deg", 0) * D2R, hd.get("roll_deg", 0) * D2R])
    return pose


def pose_gesture(base, t0, spec, solver=None):
    """-> keys, t_end, layer windows. thought beat (the head toward the target first) -> prep -> stroke -> a MOVING hold
    (drift) -> retract (unless spec 'stay': the pose becomes the new base, e.g. an idle that holds crossed arms)"""
    ph = spec["phases"]
    pose = pose_from(base, spec, solver)
    if spec.get("amp", 1.0) != 1.0:                         # effort weight: over / under-drive the pose about the base
        pose = interp_pose(base, pose, spec["amp"])
    # SECONDARY MOTION (whole-body engagement; the audit found one-shots ~0.1 widths too calm in the free arm / torso /
    # head): an arm the spec leaves at rest reacts to the gesturing one - a small lift and outward drift - and the torso
    # turns a little toward the gesturing hand; skipped when the spec sets "secondary": 0
    sec = spec.get("secondary", 1.0)
    tg = spec.get("targets", {})
    active = [a for a, v in tg.items() if v != "rest"]
    if sec and len(active) == 1:
        lead = active[0]
        free = "Left Arm" if lead == "Right Arm" else "Right Arm"
        sgn = 1.0 if free == "Right Arm" else -1.0
        pose = turn(pose, free, [0.10 * sec, 0.0, 0.08 * sec * sgn])
        toward = -1.0 if lead == "Right Arm" else 1.0       # yaw - turns the face to +X (right)
        pose = turn(pose, "Torso", [0.0, toward * 0.05 * sec, 0.0])
    keys = []
    if spec.get("thought"):
        hd = spec.get("head", {})
        look = hd.get("look")
        tgt = end(pose, look) if look in ("Left Arm", "Right Arm") else (np.asarray(look, float) if look else None)
        s0_ = t0 + ph.get("prep_s", 0.15)
        if tgt is not None:                                  # at least 0.06 s BEFORE the stroke starts: a fast effort
            t_th = min(t0 - spec["thought"].get("lead_s", 0.25) + 0.2, s0_ - 0.06)   # put it ON the stroke pin -> a
            keys.append({"pose": look_at(base, tgt, spec["thought"].get("frac", 0.35)), "t": t_th})   # zero-length spike
    s0 = t0 + ph.get("prep_s", 0.15)
    start = keys[-1]["pose"] if keys else base
    keys.append({"pose": start, "t": s0, "stiff": spec.get("stroke_stiff", 1.0)})   # the stroke starts HERE (sim applies a
    # key's stiffness to the segment AFTER it, so the effort's 'direct' snap belongs on this pin; review: without the pin it
    mid = interp_pose(start, pose, 0.45)                   # began rising at the previous key, 0.8 s instead of 0.3)
    keys.append({"pose": mid, "t": s0 + ph["stroke_s"] * 0.5})
    keys.append({"pose": pose, "t": s0 + ph["stroke_s"]})
    d = spec.get("drift", {})
    drift = turn(turn(pose, "Torso", [d.get("torso_pitch_deg", 0.8) * D2R, d.get("torso_yaw_deg", 0.6) * D2R, 0]),
                 "Head", [d.get("head_pitch_deg", -1.0) * D2R, d.get("head_yaw_deg", 1.5) * D2R, 0])
    if sec and len(active) == 1:                           # the free arm keeps drifting in the hold (never frozen)
        drift = turn(drift, free, [-0.05 * sec, 0.0, 0.0])
    t_hold = s0 + ph["stroke_s"] + ph.get("hold_s", 0.0)
    if ph.get("hold_s", 0) > 0.3 or spec.get("stay"):
        keys.append({"pose": drift, "t": max(t_hold, s0 + ph["stroke_s"] + 0.05)})
    layers = []
    for o in spec.get("osc", []):
        layers.append({**o, "t0": s0 + ph["stroke_s"] + o.get("delay_s", 0.0), "t1": t_hold})
    if spec.get("stay"):
        return keys, t_hold, layers, drift
    keys.append({"pose": base, "t": t_hold + ph.get("retract_s", 0.4)})
    return keys, t_hold + ph.get("retract_s", 0.4), layers, base


def interp_pose(a, b, u):
    out = copy.deepcopy(a)
    for j in J:
        qa, qb = np.array(a[j][:4]), np.array(b[j][:4])
        out[j][:4] = list(map(float, P.q_mul(P.q_exp(u * P.q_log(P.q_mul(qb, P.q_inv(qa)))), qa)))
        out[j][4:7] = list((1 - u) * np.array(a[j][4:7]) + u * np.array(b[j][4:7]))
    return out


def oscillate(c, layers):
    """additive oscillation (a wave, a scratch, typing thumbs): joint turned about a character-space axis by
    deg x sin(2 pi hz t), eased in / out over 0.15 s inside its window"""
    q, p = arrays(c)
    n = len(q)
    for o in layers:
        k = J.index(o["joint"])
        ax = np.asarray(o["axis"], float)
        ax /= np.linalg.norm(ax)
        for f in range(max(0, int(o["t0"] * 60)), min(n, int(o["t1"] * 60))):
            t = f / 60.0 - o["t0"]
            env = max(0.0, min(1.0, t / 0.15, (o["t1"] - f / 60.0) / 0.15))
            a = o["deg"] * D2R * math.sin(2 * math.pi * o["hz"] * t + o.get("phase", 0.0)) * env
            q[f, k] = P.q_mul(P.q_exp(ax * a), q[f, k])
    return set_arrays(c, q, p)


def leg_ik_keep(qt, pt, ql, pl, leg, goal, lo, hi):
    """leg IK that KEEPS the leg's own slide (the R6 bent knee: legs slide up + forward) and adds only the extra slide
    along the leg the goal needs. proc_r6.leg_ik REPLACED the slide with an along-leg one: on a leg that slides (the
    roundhouse with the R6 vocabulary) the slide jumped 1.15 studs in one frame when the pin let go (2026-10-16).
    With pl = 0 it is exactly leg_ik."""
    pivot, vloc = P._rig()
    g = P.q_rot(P.q_inv(qt), goal - pt) - pivot[leg] - pl
    cur = P.q_rot(ql, vloc[leg])
    a, b = cur / np.linalg.norm(cur), g / max(np.linalg.norm(g), 1e-9)
    ax = np.cross(a, b)
    ang = math.atan2(np.linalg.norm(ax), float(a @ b))
    turn_q = P.q_exp(ax / max(np.linalg.norm(ax), 1e-12) * ang) if np.linalg.norm(ax) > 1e-9 else np.array([0, 0, 0, 1.0])
    reach = float(np.linalg.norm(vloc[leg]))
    return P.q_mul(turn_q, ql), np.clip(pl + b * (np.linalg.norm(g) - reach), lo, hi)


def pin_feet(c, rng, legs=("Right Leg", "Left Leg"), touch=0.06, release=4):
    """grounded feet stay where they touched down (jumps, landings, kicks): per leg, every span where the simulated
    sole is within `touch` of the floor is pinned at the span's FIRST contact point; when the foot leaves, it is
    released LIFT-FIRST over `release` frames (the height follows the leg at once, the floor position eases over - a
    release that slid along the floor was what the gates caught on the kick); then the body is lifted wherever a pinned
    sole would dig in"""
    q, p = arrays(c)
    n = len(q)
    for leg in legs:
        k = J.index(leg)
        sole = np.array([P.sole_char(q[t, 0], p[t, 0], q[t, k], p[t, k], leg) for t in range(n)])
        down = sole[:, 1] <= P.FLOOR + touch
        t = 0
        while t < n:
            if not down[t]:
                t += 1
                continue
            s = t
            while t < n and down[t]:
                t += 1
            spot = sole[s].copy()
            spot[1] = P.FLOOR
            for f in range(s, t):
                q[f, k], p[f, k] = leg_ik_keep(q[f, 0], p[f, 0], q[f, k], p[f, k], leg, spot, *rng[leg])
            for i, f in enumerate(range(t, min(n, t + release))):
                u = 1.0 - (i + 1) / (release + 1)
                u = u * u * (3 - 2 * u)
                goal = np.array([spot[0] * u + sole[f, 0] * (1 - u), max(sole[f, 1], P.FLOOR), spot[2] * u + sole[f, 2] * (1 - u)])
                q[f, k], p[f, k] = leg_ik_keep(q[f, 0], p[f, 0], q[f, k], p[f, k], leg, goal, *rng[leg])
    dig = np.array([max(0.0, P.FLOOR - min(P.sole_char(q[f, 0], p[f, 0], q[f, kk], p[f, kk], lg)[1] for kk, lg in ((4, "Right Leg"), (5, "Left Leg")))) for f in range(n)])
    if dig.max() > 0:
        lift = np.array([dig[max(0, f - 2):f + 3].max() for f in range(n)])
        p[:, 0, 1] += np.maximum(np.convolve(np.r_[lift[:1].repeat(2), lift, lift[-1:].repeat(2)], np.ones(5) / 5, "valid"), dig)
    return set_arrays(c, q, p)


# ---------------------------------------------------------------- EFFORT (Laban) - the owner's knobs
EFFORTS = {   # named moods -> the four Laban efforts, each -1 .. +1
    "neutral": {"time": 0.0, "weight": 0.0, "flow": 0.0, "space": 0.0},
    "impatient": {"time": 0.8, "weight": 0.3, "flow": -0.6, "space": 0.7},     # sudden, firm, bound, direct
    "calm": {"time": -0.7, "weight": -0.5, "flow": 0.6, "space": -0.3},        # sustained, light, free
    "confident": {"time": 0.2, "weight": 0.7, "flow": 0.3, "space": 0.8},      # big, direct
    "tired": {"time": -0.9, "weight": -0.8, "flow": 0.5, "space": -0.6},       # slow, small, loose
}


def effort(spec, e):
    """-> (the spec re-timed / re-scaled, engine overrides) for an effort {time, weight, flow, space} or a mood name.
    time   sudden (+) shortens prep / stroke (x0.6 at +1) and the hold; sustained (-) lengthens them (x1.6)
    weight strong (+) overdrives the pose past its key (amp up to 1.25), light (-) under-drives it (0.75)
    flow   free (+) loosens the springs (more follow-through), bound (-) tightens them
    space  direct (+) makes the stroke snappier (stiff on the stroke-start key); indirect adds nothing (the engine has
           no softer-than-default stiffness)
    flow   0 = follow 0.45 (the gesture builders' default), free +1 = 0.75, bound -1 = 0.15"""
    e = EFFORTS[e] if isinstance(e, str) else e
    s = copy.deepcopy(spec)
    tk = 0.6 ** max(e["time"], 0) * 1.6 ** max(-e["time"], 0)
    ph = s.get("phases", {})
    for k in ("prep_s", "stroke_s", "retract_s"):
        if k in ph:
            ph[k] = round(ph[k] * tk, 3)
    if "hold_s" in ph:
        ph["hold_s"] = round(ph["hold_s"] * (0.8 if e["time"] > 0 else 1.0 + 0.4 * max(-e["time"], 0)), 3)
    s["amp"] = 1.0 + 0.25 * e["weight"]
    for o in s.get("osc", []):
        o["hz"] = o["hz"] * (1.0 + 0.25 * e["time"])
        o["deg"] = o["deg"] * (1.0 + 0.2 * e["weight"])
    follow = float(np.clip(0.45 + 0.3 * e["flow"], 0.1, 0.9))
    over = {"follow": {j: follow for j in J}, "stroke_stiff": 1.0 + 0.6 * max(e["space"], 0)}
    return s, over


def lock_feet_inplace(c, rng, axis, speed=None, band=0.06, release=3):
    """GROUND-SPEED foot locking for an IN-PLACE cycle (the game moves the character): inside every floor contact the
    planted foot follows a straight line on the floor moving OPPOSITE the travel axis at exactly the ground speed
    (the line's offset fitted to the foot's own path, least squares), reached by IK; contact edges are released /
    caught lift-first over `release` frames. speed: studs/s (None = the median measured from the clip's own contacts)
    -> the clip, the speed used. A LOOP is locked on three tiled cycles and the middle one kept, so a contact that
    crosses the seam is one span and the result repeats exactly"""
    if c.get("loop") and not c.get("_tiled"):
        # a loop clip may END on a copy of its first frame (the closed seam): tile the CORE cycle only, then re-append
        # the copy (tiling the copy too advanced the lock line across a duplicate frame - sprint seam 2.36, review)
        qa, _ = arrays(c)
        dup = len(qa) > 2 and all(abs(float(np.dot(qa[0, k], qa[-1, k]))) > 0.99995 for k in range(6))
        core = len(qa) - 1 if dup else len(qa)
        fps = c.get("fps", 60)
        t3 = copy.deepcopy(c)
        for j in J:
            t3["joints"][j]["frames"] = c["joints"][j]["frames"][:core] * 3
        t3["times"] = [i / fps for i in range(3 * core)]
        t3["_tiled"] = True
        out, sp = lock_feet_inplace(t3, rng, axis, speed, band, release)
        for j in J:
            mid = out["joints"][j]["frames"][core:2 * core]
            out["joints"][j]["frames"] = mid + ([mid[0]] if dup else [])
        out["times"] = list(c["times"])
        out.pop("_tiled", None)
        return out, sp
    q, p = arrays(c)
    n = len(q)
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    soles = {}
    for leg in ("Right Leg", "Left Leg"):
        k = J.index(leg)
        soles[leg] = np.array([P.sole_char(q[t, 0], p[t, 0], q[t, k], p[t, k], leg) for t in range(n)])
    floor = P.FLOOR
    if speed is None:
        v = []
        for s in soles.values():
            st = s[:, 1] <= floor + band
            d = -(np.diff(s, axis=0) @ a) * 60
            v += list(d[st[1:] & st[:-1]])
        speed = float(np.median(v)) if v else 0.0
    for leg in ("Right Leg", "Left Leg"):
        k = J.index(leg)
        s = soles[leg]
        down = s[:, 1] <= floor + band
        if down.all() or not down.any():                     # never lifts (or never lands): nothing to lock - one
            continue                                         # span over the 3 tiles would drag it 3 cycles
        t = 0
        written = 0                                          # frames already owned by an earlier span of this leg
        while t < n:
            if not down[t]:
                t += 1
                continue
            s0 = t
            while t < n and down[t]:
                t += 1
            fr = np.arange(s0, t)
            # the line: x(f) = x0 - a * speed * f / 60 ; x0 fitted (least squares) to the span's own sole positions
            x0 = (s[fr] + np.outer(fr / 60.0 * speed, a)).mean(0)
            # CATCH IN THE AIR: the foot is steered onto the line during its last frames BEFORE touchdown (height left
            # free), so it lands exactly on it - a catch on the floor either snapped the leg (hard, 22-28 deg) or slid the
            # planted foot (eased, skate 0.22-0.30)
            c0_ = max(written, s0 - 2 * release)            # never overwrite an earlier span's frames
            for i, f in enumerate(range(c0_, s0)):
                u = (i + 1 + (2 * release - (s0 - c0_))) / (2 * release + 1)
                u = u * u * (3 - 2 * u)
                lock = x0 - a * speed * f / 60.0
                goal = np.array([s[f, 0] * (1 - u) + lock[0] * u, max(s[f, 1], floor), s[f, 2] * (1 - u) + lock[2] * u])
                q[f, k], p[f, k] = leg_ik_keep(q[f, 0], p[f, 0], q[f, k], p[f, k], leg, goal, *rng[leg])
            for f in fr:
                goal = x0 - a * speed * f / 60.0
                goal[1] = floor
                q[f, k], p[f, k] = leg_ik_keep(q[f, 0], p[f, 0], q[f, k], p[f, k], leg, goal, *rng[leg])
            written = min(n, t + release)
            for i, f in enumerate(range(t, min(n, t + release))):          # lift-first release
                u = 1.0 - (i + 1) / (release + 1)
                u = u * u * (3 - 2 * u)
                lock = x0 - a * speed * f / 60.0
                goal = np.array([lock[0] * u + s[f, 0] * (1 - u), max(s[f, 1], floor), lock[2] * u + s[f, 2] * (1 - u)])
                q[f, k], p[f, k] = leg_ik_keep(q[f, 0], p[f, 0], q[f, k], p[f, k], leg, goal, *rng[leg])
    return set_arrays(c, q, p), speed
