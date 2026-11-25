"""gait.py — PROCEDURAL LOCOMOTION, licence-free: `python kit/anim/gait.py assets/animations/<Name>.gait.json --out <clip>`

A gait file names a kind and a few body parameters; the generator writes a looping neutral clip (R15 names) with a
real stance/swing structure: in stance the hip sweeps LINEARLY so the planted foot moves back at one constant ground
speed (the clip's `locomotion.speed`, which the runtime matches to WalkSpeed), in swing it returns on a cosine with
the knee folding; the pelvis bobs twice a cycle and rolls with the stance leg, the upper torso counter-twists, the
arms swing against the legs with a little elbow, the head stays level. Kinds: walk, jog, run, back, strafe_left,
strafe_right, idle (breathing), jump, fall, land (one-shots). Every parameter has a per-kind default; set only what
you want to change.

{ "name": "Walk", "kind": "walk", "fps": 30,
  "hip": 32, "knee": 60, "cycle": 0.5, "bounce": 0.08, "roll": 3, "twist": 6, "lean": 3, "arm": 28, "elbow": 18,
  "priority": "Movement" }
"""

import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402
import gait_curves as GC  # noqa: E402

KINDS = {
    # the human gaits (kit/anim/gait_curves.py): hip = the stride (the thigh's reach at the plant), knee = the swing's
    # peak fold, stance = the loading-response fold, style = exaggeration of the body's curves (1 = a measured human),
    # lean = trunk forward lean, sway = lateral weight shift (studs), arm / elbow = swing peaks, head = bob
    "walk":  dict(hip=30, knee=60, stance=16, cycle=0.60, style=1.15, lean=2, sway=0.06, arm=26, elbow=30, head=1, loop=True, priority="Movement"),
    "jog":   dict(hip=32, knee=80, stance=26, cycle=0.46, style=1.25, lean=5, sway=0.07, arm=36, elbow=70, head=2, loop=True, priority="Movement"),
    "run":   dict(hip=36, knee=100, stance=40, cycle=0.40, style=1.35, lean=9, sway=0.07, arm=44, elbow=92, head=3, loop=True, priority="Movement"),
    "back":  dict(hip=24, knee=45, stance=14, cycle=0.60, style=1.0, lean=-2, sway=0.05, arm=20, elbow=24, head=1, loop=True, priority="Movement"),
    # sideways and the one-shots keep the kit's first generator (a sinusoid with a knee fold)
    "strafe_left":  dict(hip=24, knee=40, stance=5, cycle=0.60, bounce=0.0, roll=5.0, twist=3, lean=2, arm=14, elbow=15, head=2, loop=True, priority="Movement"),
    "strafe_right": dict(hip=24, knee=40, stance=5, cycle=0.60, bounce=0.0, roll=5.0, twist=3, lean=2, arm=14, elbow=15, head=2, loop=True, priority="Movement"),
    "idle":    dict(hip=0, knee=0, stance=0, cycle=3.0, breathe=3, roll=0.6, twist=1.5, lean=0, arm=2, elbow=12, head=1, loop=True, priority="Idle"),
    "jump":    dict(hip=0, knee=0, stance=0, cycle=0.45, bounce=0, roll=0, twist=0, lean=6, arm=0, elbow=0, head=0, loop=False, priority="Movement"),
    "fall":    dict(hip=0, knee=0, stance=0, cycle=0.60, bounce=0, roll=0, twist=0, lean=-6, arm=0, elbow=0, head=0, loop=True, priority="Movement"),
    "land":    dict(hip=0, knee=0, stance=0, cycle=0.40, bounce=0, roll=0, twist=0, lean=10, arm=0, elbow=0, head=0, loop=False, priority="Movement"),
}
HUMAN = ("walk", "jog", "run", "back")
LAST_ROWS = None
DIRECTION = {"walk": (0, 0, -1), "jog": (0, 0, -1), "run": (0, 0, -1), "back": (0, 0, 1),
             "strafe_left": (-1, 0, 0), "strafe_right": (1, 0, 0)}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def q_euler(x=0.0, y=0.0, z=0.0):
    """CFrame.Angles(x, y, z) degrees -> [qx, qy, qz, qw]"""
    return q_mat(C.euler_mat((x, y, z)))


def q_mat(m):
    """a rotation matrix -> [qx, qy, qz, qw]"""
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    n = math.sqrt(sum(v * v for v in q)) or 1.0
    return [round(v / n, 6) for v in q]


def frame(x=0.0, y=0.0, z=0.0, pos=(0.0, 0.0, 0.0)):
    return q_euler(x, y, z) + [round(float(v), 5) for v in pos]


def frame_m(m, pos=(0.0, 0.0, 0.0)):
    return q_mat(m) + [round(float(v), 5) for v in pos]


def leg_under(pelvis_deg, h, adduct=0.0):
    """the UpperLeg joint rotation that flexes the thigh by h degrees in the CHARACTER's sagittal plane (and leans
    it `adduct` sideways) under a pelvis rotated by (tilt, yaw, roll) degrees: the pelvis's rotation is undone first,
    so a rotating, listing pelvis never swings the planted foot sideways"""
    pelvis = C.euler_mat(pelvis_deg)
    want = C.euler_mat((0.0, 0.0, adduct)) @ C.euler_mat((h, 0.0, 0.0))
    return pelvis.T @ want


def stance_hip(x, k, lengths, sideways=False):
    """the hip angle (deg) that puts the ankle at ground position x (studs, + = forward or + = right) with the knee
    bent k degrees: thigh sin h + shin sin(h - k) = x (forward), or sin z (thigh + shin cos k) = x (sideways)"""
    thigh, shin = lengths
    if sideways:
        return math.degrees(math.asin(max(-1.0, min(1.0, x / (thigh + shin * math.cos(math.radians(k)))))))
    lo, hi = -89.0, 89.0
    for _ in range(40):                                    # bisection: f is monotonic over the leg's range
        mid = (lo + hi) / 2
        f = thigh * math.sin(math.radians(mid)) + shin * math.sin(math.radians(mid - k)) - x
        if f < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


CLEAR = 0.06  # studs every in-air swing frame keeps over the floor (above the gates' 0.04 contact band and the
# R6 fold's 0.05 standing threshold); the natural arc clears far more mid-swing


def swing_ik(x, v, lengths, sideways=False):
    """the hip and knee angles (deg) that put the ankle x forward (or sideways) and v below the hip pivot: a planar
    two-link IK with the knee forward (forward gait: thigh h, shin h - k; sideways: the leg leans z, the knee folds
    k forward, reaching (thigh + shin cos k) along the lean). Out of reach -> the straight leg points at the target."""
    thigh, shin = lengths
    d = math.hypot(x, v)
    phi = math.degrees(math.atan2(x, v))                   # the hip->ankle line, from vertical
    if d >= (thigh + shin) * 0.9999:
        return phi, 0.0
    if sideways:
        k = math.degrees(math.acos(max(-1.0, min(1.0, (d - thigh) / shin))))
        return phi, k
    cos_a = (thigh * thigh + d * d - shin * shin) / (2 * thigh * d)
    cos_g = (thigh * thigh + shin * shin - d * d) / (2 * thigh * shin)
    alpha = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
    k = 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos_g))))
    return phi + alpha, k


def swing_pose(u, hip, knee, lift=1.3, straighten=1.25):
    """the swing's natural pose at u (0 = lift-off, 1 = the plant): the thigh returns -hip -> +hip on a cosine, the
    knee folds early (`lift` shapes it) and is straight before the plant (`straighten` > 1). (thigh, knee) degrees."""
    h = -hip * math.cos(math.pi * u)
    k = knee * max(0.0, math.sin(math.pi * min(1.0, u * straighten))) ** lift
    return h, k


def leg_reach(h, k, lengths, sideways=False):
    """(x, down): where the ankle sits from the hip pivot for thigh h / knee k (deg), studs"""
    thigh, shin = lengths
    if sideways:                                          # the leg leans h, the knee folds k forward
        reach = thigh + shin * math.cos(math.radians(k))
        return reach * math.sin(math.radians(h)), reach * math.cos(math.radians(h))
    x = thigh * math.sin(math.radians(h)) + shin * math.sin(math.radians(h - k))
    down = thigh * math.cos(math.radians(h)) + shin * math.cos(math.radians(h - k))
    return x, down


THIGH_LIFT_X = 1.0  # studs of ankle lead beyond which a swing lifts entirely by swinging further, not by the knee
MIN_FRAMES = 20     # frames per cycle a locomotion gait needs (10 per step): a human knee folds and unfolds fast,
# and a run's flight is a few percent of the cycle - coarser grids snap (the engine keys at any time)


def grid_fps(kind, cycle, fps):
    """the fps a cycle is sampled at: the file's, or finer when the cycle is too short for MIN_FRAMES (a 0.3 s
    sprint at 30 fps would get 8 frames and snap; it gets 40 fps instead - the engine keys at any time)"""
    if kind in ("idle", "jump", "fall", "land"):
        return fps
    return max(fps, int(math.ceil(MIN_FRAMES / max(cycle, 1e-3))))


def swing_bump(u):
    """the shape of the lift that keeps a swing over the floor: a sine hump, zero at lift-off and the plant"""
    return max(0.0, math.sin(math.pi * u))


def leg_cycle(phase, hip, knee, stance=0.0, lift=1.3, lengths=(0.92, 1.01), sideways=False, straighten=1.25,
              pelvis=0.0, raise_=0.0):
    """one leg over a cycle: phase 0..1 (0 = foot planted in front). Stance = first half: the ankle's GROUND position
    runs linearly from +S to -S (S = what a straight leg at `hip` reaches; one constant ground speed under the foot),
    the knee bending the kind's stance bend mid-stance, the sole flat. Swing = second half: the natural pose
    (`swing_pose`: a run's heel kicks up behind, a walk's barely folds), its ankle lifted by `raise_` studs (the kind's
    smooth clearance bump, sized by `locomotion` so every in-air frame clears CLEAR under the pelvis as it stands
    that frame - `pelvis` = the hip pivot's height change) and the hip + knee re-solved for that ankle. Returns
    (hip_x, knee_x, ankle_x, in_stance) degrees, positive = the limb forward (or to the right, sideways)."""
    p = phase % 1.0
    thigh, shin = lengths
    stride = (thigh + shin) * math.sin(math.radians(hip))
    if p < 0.5:
        u = p / 0.5
        k = stance * math.sin(math.pi * u)                # absorbs mid-stance, straight at heel-strike and toe-off
        h = stance_hip(stride * (1 - 2 * u), k, lengths, sideways)
        return h, -k, -(h - k), True
    u = (p - 0.5) / 0.5
    h, k = swing_pose(u, hip, knee, lift, straighten)
    if raise_ > 0:
        x, down = leg_reach(h, k, lengths, sideways)
        # a leg reaching ahead lifts its foot by swinging a little further (the knee stays as planned: no late
        # re-fold, no thigh overshoot at the plant); a leg under the hip cannot (swinging only moves its foot), so
        # there the knee folds (IK at the same ankle lead) - blended by how far ahead the ankle is
        t = max(0.0, min(1.0, x / THIGH_LIFT_X))
        if t > 0:
            rho, phi = math.hypot(x, down), math.atan2(x, down)
            phi2 = math.acos(max(-1.0, min(1.0, math.cos(phi) - t * raise_ / rho)))
            h += math.degrees(phi2 - phi)
            x, down = rho * math.sin(phi2), rho * math.cos(phi2)
        if t < 1:
            h, k = swing_ik(x, down - (1 - t) * raise_, lengths, sideways)
    ankle = -(h - k)                                      # the foot stays level: clears by the knee, lands flat
    return h, -k, ankle, False


def swing_height(u, hip, knee, lift, straighten, lengths, sideways, pelvis):
    """how far the natural swing pose's ankle is over the floor at u, under a pelvis `pelvis` studs from rest"""
    thigh, shin = lengths
    _, down = leg_reach(*swing_pose(u, hip, knee, lift, straighten), lengths, sideways)
    return thigh + shin + pelvis - down


def leg_lengths(rig):
    """(thigh, shin) studs: hip pivot -> knee pivot -> ankle pivot. With a level foot, a stance pose (hip h, knee k)
    reaches thigh cos h + shin cos(h - k) down, and the pelvis drops by what that lacks of the straight leg"""
    hip = rig["rest"]["LowerTorso"][1] + rig["joints"]["RightUpperLeg"]["c0"][1]
    knee = rig["rest"]["RightUpperLeg"][1] + rig["joints"]["RightLowerLeg"]["c0"][1]
    ankle = rig["rest"]["RightLowerLeg"][1] + rig["joints"]["RightFoot"]["c0"][1]
    return hip - knee, knee - ankle


def pelvis_drop(lengths, h, k):
    """how far the pelvis must drop for a level foot to stay on the floor at hip h / knee bend k (degrees)"""
    thigh, shin = lengths
    reach = thigh * math.cos(math.radians(h)) + shin * math.cos(math.radians(h - k))
    return -(thigh + shin - reach)


def locomotion_sideways(kind, p, fps, lengths, hip_offset=(0.5, -0.2)):
    """the kit's first generator (a thigh sinusoid with a knee fold): the strafes and the idle"""
    n = 2 * max(2, int(round(p["cycle"] * fps / 2)))        # even: both steps get the same frames
    times = [round(i / fps, 6) for i in range(n + 1)]
    sign = -1.0 if kind == "back" else 1.0
    J = {k: [] for k in ("LowerTorso", "UpperTorso", "Head", "RightUpperLeg", "RightLowerLeg", "RightFoot",
                         "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperArm", "RightLowerArm",
                         "LeftUpperArm", "LeftLowerArm")}
    strafe = {"strafe_left": -1.0, "strafe_right": 1.0}.get(kind)
    lift, straighten = (0.7, 1.05) if strafe else (1.3, 1.25)   # a sideways swing clears at once, lands late
    hx, hy = hip_offset
    rows = []
    for i in range(n + 1):
        ph = (i % n) / n                                   # the last frame equals the first: a seamless loop
        if kind == "idle":
            rows.append(None)
            continue
        r_stance = ph < 0.5
        s_ph, w_ph = (ph, ph + 0.5) if r_stance else (ph + 0.5, ph)
        sh, sk, sa, _ = leg_cycle(s_ph, p["hip"], p["knee"], p["stance"], lift, lengths, strafe is not None, straighten)
        if strafe:  # the leg leans sideways by sh and bends forward by sk: both shorten the vertical reach
            thigh, shin = lengths
            reach = thigh * math.cos(math.radians(sh)) + shin * math.cos(math.radians(sh)) * math.cos(math.radians(sk))
            drop = -(thigh + shin - reach)
        else:
            drop = pelvis_drop(lengths, sh, -sk)                        # the pelvis follows the stance leg down
        bounce = p["bounce"] * (1 - math.cos(4 * math.pi * ph)) / 2   # a little lift at mid-stance on top
        roll = p["roll"] * math.sin(2 * math.pi * ph)                 # the pelvis drops on the swing side
        # the roll lifts the stance-side hip (0.5 studs out, 0.2 down from the pelvis centre): take it out of the drop
        side = 1.0 if r_stance else -1.0
        drop -= side * hx * math.sin(math.radians(roll)) + hy * (math.cos(math.radians(roll)) - 1)
        # the swing leg hangs from the pelvis as it now stands (its hip is on the low side of the roll)
        swing_hip = drop + bounce - side * hx * math.sin(math.radians(roll)) + hy * (math.cos(math.radians(roll)) - 1)
        rows.append((ph, r_stance, sh, sk, sa, w_ph, drop, bounce, roll, side, swing_hip))
    # the swing's natural pose scuffs where the stance knee and the roll lower the pelvis: ONE smooth bump (sized
    # here, over the whole cycle) lifts its ankle so every in-air frame clears CLEAR - never a per-frame clamp,
    # which snaps the knee where the lift starts or stops
    bump = 0.0
    for row in rows:
        if row is None:
            continue
        u = (row[5] % 1.0 - 0.5) / 0.5
        if 0.0 < u < 1.0:
            need = CLEAR + 0.005 - swing_height(u, p["hip"], p["knee"], lift, straighten, lengths, strafe is not None, row[10])
            if need > 0:
                bump = max(bump, need / swing_bump(u))
    for i in range(n + 1):
        ph = (i % n) / n
        if kind == "idle":
            b = math.sin(2 * math.pi * ph)
            # the body breathes by a small knee bend (the feet stay on the floor; the pelvis follows the legs down)
            kb = p["breathe"] * (1 - math.cos(2 * math.pi * ph)) / 2
            hb = kb / 2
            J["LowerTorso"].append(frame(0, 0, p["roll"] * b, (0, pelvis_drop(lengths, hb, kb), 0)))
            J["UpperTorso"].append(frame(1.5 * (1 - math.cos(2 * math.pi * ph)) / 2 + p["lean"], p["twist"] * b, 0))
            J["Head"].append(frame(-p["head"] * b, 0, 0))
            J["RightUpperArm"].append(frame(p["arm"] * b, 0, 2))
            J["LeftUpperArm"].append(frame(-p["arm"] * b, 0, -2))
            J["RightLowerArm"].append(frame(p["elbow"], 0, 0))
            J["LeftLowerArm"].append(frame(p["elbow"], 0, 0))
            for side in ("Right", "Left"):
                J[f"{side}UpperLeg"].append(frame(hb, 0, -p["roll"] * b))
                J[f"{side}LowerLeg"].append(frame(-kb, 0, 0))
                J[f"{side}Foot"].append(frame(-(hb - kb), 0, 0))
            continue
        ph, r_stance, sh, sk, sa, w_ph, drop, bounce, roll, side, swing_hip = rows[i]
        u = (w_ph % 1.0 - 0.5) / 0.5
        wh, wk, wa, _ = leg_cycle(w_ph, p["hip"], p["knee"], p["stance"], lift, lengths, strafe is not None, straighten,
                                  swing_hip, bump * swing_bump(u))
        (rh, rk, ra), (lh, lk, la) = ((sh, sk, sa), (wh, wk, wa)) if r_stance else ((wh, wk, wa), (sh, sk, sa))
        # the legs counter the pelvis roll (they hang from it), so a stance sweep stays what leg_cycle planned
        if strafe:  # legs swing sideways (about Z), the body faces forward; the knee folds forward to clear
            J["RightUpperLeg"].append(frame(0, 0, strafe * rh - roll))
            J["LeftUpperLeg"].append(frame(0, 0, strafe * lh - roll))
            J["RightLowerLeg"].append(frame(rk, 0, 0))
            J["LeftLowerLeg"].append(frame(lk, 0, 0))
            J["RightFoot"].append(frame(-rk, 0, -strafe * rh))
            J["LeftFoot"].append(frame(-lk, 0, -strafe * lh))
        else:
            J["RightUpperLeg"].append(frame(sign * rh, 0, -roll))
            J["LeftUpperLeg"].append(frame(sign * lh, 0, -roll))
            J["RightLowerLeg"].append(frame(sign * rk, 0, 0))
            J["LeftLowerLeg"].append(frame(sign * lk, 0, 0))
            J["RightFoot"].append(frame(sign * ra, 0, 0))
            J["LeftFoot"].append(frame(sign * la, 0, 0))
        J["LowerTorso"].append(frame(0, 0, roll, (0, drop + bounce, 0)))
        J["UpperTorso"].append(frame(p["lean"], -p["twist"] * math.sin(2 * math.pi * ph), -roll * 0.6))
        J["Head"].append(frame(-p["lean"] * 0.5 + p["head"] * math.sin(4 * math.pi * ph), p["twist"] * 0.4 * math.sin(2 * math.pi * ph), 0))
        # arms against the legs: the right arm is back when the right leg is forward
        a = math.cos(2 * math.pi * ph)
        J["RightUpperArm"].append(frame(-p["arm"] * a * sign, 0, 4))
        J["LeftUpperArm"].append(frame(p["arm"] * a * sign, 0, -4))
        J["RightLowerArm"].append(frame(p["elbow"] * (0.6 + 0.4 * max(0.0, -a)), 0, 0))
        J["LeftLowerArm"].append(frame(p["elbow"] * (0.6 + 0.4 * max(0.0, a)), 0, 0))
    return times, J


def foot_geometry(rig):
    """(sole depth below the ankle pivot, half length) of the rig's foot: what a pitched sole needs to clear"""
    f, size = rig["joints"]["RightFoot"], rig["sizes"]["RightFoot"]
    return f["c1"][1] + size[1] / 2, size[2] / 2


def foot_lift(geo, phi_deg):
    """how much higher the ankle pivot sits for a sole pitched phi degrees (toes up +, heel up -) with its lowest
    edge on the floor, vs the flat foot"""
    cy, hz = geo
    a = math.radians(abs(phi_deg))
    return cy * (math.cos(a) - 1) + hz * math.sin(a)


def foot_pitch_for_lift(geo, lift):
    """the heel-up pitch (<= 0) that lifts the ankle by `lift` (0 when nothing is needed): bisection"""
    if lift <= 1e-6:
        return 0.0
    lo, hi = 0.0, 80.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if foot_lift(geo, mid) < lift:
            lo = mid
        else:
            hi = mid
    return -(lo + hi) / 2


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def locomotion(kind, p, fps, lengths, hip_offset=(0.5, -0.2), rig=None):
    """a looping cycle: the human gaits (walk jog run back) from the normative curves, the rest from the first
    generator"""
    if kind not in HUMAN or rig is None:
        return locomotion_sideways(kind, p, fps, lengths, hip_offset)
    times, J = locomotion_human("walk" if kind == "back" else kind, p, fps, lengths, hip_offset, rig)
    if kind == "back":  # walking backwards is the walk played backwards: the toe lands first, the heel leaves last
        J = {k: list(reversed(v)) for k, v in J.items()}
    return times, J


def locomotion_human(kind, p, fps, lengths, hip_offset, rig):
    """a walk / jog / run with a human body's timing (kit/anim/gait_curves.py): the stance leg's ankle sweeps the
    ground at ONE speed while its knee absorbs at loading response and straightens by mid-stance; the sole strikes
    toes-up and rolls flat, the heel rises before toe-off; the pelvis rides on the LEADING stance leg (its height is
    what that leg reaches: the body's bounce), the trailing foot's heel-rise is solved so both feet keep the floor
    through double support; the swing follows the curves' shape (a run's heel kicks up behind) blended into the exact
    lift-off and plant poses; the pelvis rotates and lists, the trunk counters it, the arms swing against the legs
    with the elbow flexing as the arm comes forward, the head stays level; a run flies between stances."""
    thigh, shin = lengths
    cv = GC.blended(GC.family(kind)[1])
    S = cv["support"]
    style = p["style"]
    n = 2 * max(2, int(round(p["cycle"] * fps / 2)))
    times = [round(i / fps, 6) for i in range(n + 1)]
    geo = foot_geometry(rig)
    ankle_rest = geo[0]
    hip0 = thigh + shin + ankle_rest                       # the hip pivot's height over the floor at rest
    hx, hy = hip_offset
    k_st = p["stance"] / max(GC.peak(cv["knee"], 0.0, 0.35), 1.0)   # the loading-response fold, not the pre-swing rise
    k_sw = p["knee"] / max(GC.peak(cv["knee"], S, 1.0), 1.0)
    h_sw = p["hip"] / max(GC.peak(cv["hip"], S, 1.0), 1.0)
    # the ground path: from where the curves' plant pose puts the ankle to where the toe-off pose leaves it (a human's
    # trailing leg extends further back than the leading leg reaches ahead) - the swing lands and lifts exactly there
    x_front = leg_reach(h_sw * GC.sample(cv["hip"], 0.0), k_st * GC.sample(cv["knee"], 0.0), lengths)[0]

    def knee_at(q):
        q %= 1.0
        w = smoothstep((q - (S - 0.05)) / 0.1) * (1 - smoothstep((q - 0.95) / 0.05))
        return GC.sample(cv["knee"], q) * ((1 - w) * k_st + w * k_sw)

    x_back = leg_reach(h_sw * GC.sample(cv["hip"], S), knee_at(S - 1e-6), lengths)[0]

    def reach_of(h, k):
        return thigh * math.cos(math.radians(h)) + shin * math.cos(math.radians(h - k))

    # pass 1: the pelvis's own motion and each leg's stance geometry on the ground path
    rows = []
    for i in range(n + 1):
        qR = (i % n) / n
        yaw = style * GC.sample(cv["pelvis_rot"], qR)
        obl = style * GC.sample(cv["pelvis_obl"], qR)
        sway = p["sway"] * style * math.sin(2 * math.pi * (qR - 0.05))
        legs = {}
        for side, off, sgn in (("R", 0.0, 1.0), ("L", 0.5, -1.0)):
            q = (qR + off) % 1.0
            hip_fwd = sgn * hx * math.sin(math.radians(yaw))           # the hip pivot, forward, from the rotation
            hip_up = sgn * hx * math.sin(math.radians(obl)) + hy * (math.cos(math.radians(obl)) - 1)
            leg = dict(q=q, hip_fwd=hip_fwd, hip_up=hip_up, stance=q < S)
            if q < S:
                u = q / S
                leg["x"] = x_front + (x_back - x_front) * u
                leg["k"] = knee_at(q)
                leg["h"] = stance_hip(leg["x"] - hip_fwd, leg["k"], lengths)
                leg["reach"] = reach_of(leg["h"], leg["k"])
            legs[side] = leg
        rows.append(dict(qR=qR, yaw=yaw, obl=obl, sway=sway, legs=legs))

    # pass 2: the pelvis height - the leading stance leg carries it (heel-strike roll included); a leg that must
    # fit under that pelvis raises its heel (at least as much as the curves say) and folds its knee for the rest, so
    # its foot keeps the floor; in the last part of a single support the pelvis already descends toward the coming
    # strike (a body does not drop at the instant a foot lands); flight frames fly a parabola
    plant = rows[0]["legs"]["R"]
    drop_strike = foot_lift(geo, GC.sample(cv["foot"], 0.0)) + plant["reach"] - (thigh + shin)
    win = 0.12

    def fit_under(T, drop):
        """a stance leg under a pelvis `drop` from rest: the knee stays on its curve and the heel rises by exactly
        what the pelvis leaves (this rig's foot is long, so a few degrees lift the ankle a lot); only a leg too long
        even flat-footed folds its knee further"""
        want = hip0 + drop + T["hip_up"] - ankle_rest             # the reach + lift this leg must have
        lift = want - T["reach"]
        if lift >= 0:
            T["lift"], T["phi"] = lift, foot_pitch_for_lift(geo, lift)
            return
        lo, hi = T["k"], 90.0
        for _ in range(30):
            mid = (lo + hi) / 2
            h = stance_hip(T["x"] - T["hip_fwd"], mid, lengths)
            if reach_of(h, mid) > want:
                lo = mid
            else:
                hi = mid
        T["k"] = (lo + hi) / 2
        T["h"] = stance_hip(T["x"] - T["hip_fwd"], T["k"], lengths)
        T["reach"] = reach_of(T["h"], T["k"])
        T["lift"], T["phi"] = 0.0, 0.0

    for row in rows:
        stance = [sd for sd in ("R", "L") if row["legs"][sd]["stance"]]
        row["drop"] = None
        if not stance:
            continue
        lead = min(stance, key=lambda sd: row["legs"][sd]["q"])
        L = row["legs"][lead]
        L["phi"] = GC.sample(cv["foot"], L["q"])
        L["lift"] = foot_lift(geo, L["phi"])
        demand = L["lift"] + L["reach"] - (thigh + shin) - L["hip_up"]
        if len(stance) == 1 and S > 0.5 and L["q"] > 0.5 - win:
            w = smoothstep((L["q"] - (0.5 - win)) / win)
            row["drop"] = demand * (1 - w) + drop_strike * w
            fit_under(L, row["drop"])
        else:
            row["drop"] = demand
        for sd in stance:
            if sd != lead:
                fit_under(row["legs"][sd], row["drop"])
    # flight: between the last frame of a stance and the first of the next
    i = 0
    while i <= n:
        if rows[i]["drop"] is None:
            j = i
            while j <= n and rows[j]["drop"] is None:
                j += 1
            before = rows[i - 1]["drop"] if i > 0 else rows[n - 1]["drop"]
            after = rows[j]["drop"] if j <= n else rows[(j) % n]["drop"]
            if before is None:
                before = after
            if after is None:
                after = before
            span = j - i + 1
            F = style * cv["flight"] * min(1.0, span / fps / 0.12)   # a flight's rise grows with its duration
            for k, idx in enumerate(range(i, j)):
                t = (k + 1) / span
                rows[idx]["drop"] = before + (after - before) * t + F * 4 * t * (1 - t)
            i = j
        else:
            i += 1
    for row in rows:
        if row["drop"] is None:
            row["drop"] = 0.0
    rows[n]["drop"] = rows[0]["drop"]

    # pass 3: the swing legs - the curves' pose, blended (in the hip's own frame: ankle lead and drop below the hip
    # pivot, so a leg in flight is never stretched toward the floor before the pelvis comes down) into the exact
    # lift-off pose it left with and the plant pose the stance begins with
    phi_hs = GC.sample(cv["foot"], 0.0)
    plant = rows[0]["legs"]["R"]
    end = (x_front, plant["reach"], phi_hs)
    toe = {}                                               # per leg: the pose it left the floor with (the last stance frame)
    for sd in ("R", "L"):
        last = max((row["legs"][sd] for row in rows[:-1] if row["legs"][sd]["stance"]), key=lambda leg: leg["q"])
        toe[sd] = (last["x"] - last["hip_fwd"], last["reach"], last.get("phi", 0.0))
    swing_rows = []
    for row in rows:
        for sd in ("R", "L"):
            leg = row["legs"][sd]
            if leg["stance"]:
                continue
            u = (leg["q"] - S) / (1 - S)
            hc, kc = h_sw * GC.sample(cv["hip"], leg["q"]), knee_at(leg["q"])
            xc, downc = leg_reach(hc, kc, lengths)
            curve = (xc, downc, GC.sample(cv["foot"], leg["q"]))
            start = toe[sd]
            w0, w1 = 1 - smoothstep(u / 0.15), smoothstep((u - 0.65) / 0.35)
            wc = 1 - w0 - w1
            leg["rel"] = [curve[c] * wc + start[c] * w0 + end[c] * w1 for c in range(2)]
            # the sole's pitch eases out of the heel-rise it left with over a longer window (a pitch is cheap to
            # change in position, costly in angle per frame)
            p0 = 1 - smoothstep(u / 0.35)
            leg["rel"].append(curve[2] * (1 - p0 - w1) + start[2] * p0 + end[2] * w1)
            leg["u"], leg["hip_y"] = u, hip0 + row["drop"] + leg["hip_up"]
            swing_rows.append(leg)
    # a clearance bump: the pitched foot's lowest edge stays CLEAR over the floor through the middle of the swing
    bump = 0.0
    for leg in swing_rows:
        xr, down, phi = leg["rel"]
        low = leg["hip_y"] - down - (geo[0] * math.cos(math.radians(phi)) + geo[1] * abs(math.sin(math.radians(phi))))
        need = CLEAR + 0.005 - low
        if 0.2 <= leg["u"] <= 0.85 and need > 0:
            bump = max(bump, need / swing_bump(leg["u"]))
    for leg in swing_rows:
        xr, down, phi = leg["rel"]
        leg["h"], leg["k"] = swing_ik(xr, down - bump * swing_bump(leg["u"]), lengths)
        leg["phi"] = phi

    global LAST_ROWS
    LAST_ROWS = rows                                       # for diagnostics (kit/test, scratch dumps)
    # pass 4: the joints
    J = {k: [] for k in ("LowerTorso", "UpperTorso", "Head", "RightUpperLeg", "RightLowerLeg", "RightFoot",
                         "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperArm", "RightLowerArm",
                         "LeftUpperArm", "LeftLowerArm")}
    arm_scale = p["arm"] / max(GC.peak(cv["arm"]), 1.0)
    elbow_scale = p["elbow"] / max(GC.peak(cv["elbow"]), 1.0)
    lag = 0.03                                             # the arms and head trail the legs a little (overlap)
    for row in rows:
        qR, yaw, obl, sway, d = row["qR"], row["yaw"], row["obl"], row["sway"], row["drop"]
        tip = -style * 1.2 * math.cos(4 * math.pi * (qR - 0.04))   # the trunk tips forward right after each strike
        tilt = -0.8 * style * (1 - math.cos(4 * math.pi * qR)) / 2
        J["LowerTorso"].append(frame(tilt, yaw, obl, (sway, d, 0)))
        J["UpperTorso"].append(frame(-p["lean"] + tip, -1.8 * yaw, -0.5 * obl))
        head_yaw = 0.24 * style * GC.sample(cv["pelvis_rot"], qR - 0.04)
        J["Head"].append(frame(p["lean"] * 0.5 - tip * 0.5 + p["head"] * math.sin(4 * math.pi * qR), head_yaw, 0.3 * obl))
        for side, prefix in (("R", "Right"), ("L", "Left")):
            leg = row["legs"][side]
            sgn = 1.0 if side == "R" else -1.0
            # the pelvis sways over the stance foot; the legs angle sideways by that much so the feet stay put, and
            # the thigh flexes in the CHARACTER's sagittal plane whatever the pelvis does (leg_under)
            reach = reach_of(leg["h"], leg["k"])
            adduct = -math.degrees(math.asin(max(-1.0, min(1.0, sway / max(reach, 0.5)))))
            J[f"{prefix}UpperLeg"].append(frame_m(leg_under((tilt, yaw, obl), leg["h"], adduct)))
            J[f"{prefix}LowerLeg"].append(frame(-leg["k"], 0, 0))
            J[f"{prefix}Foot"].append(frame(leg["phi"] - (leg["h"] - leg["k"]), 0, 0))
            qa = (qR + (0.0 if side == "R" else 0.5) - lag) % 1.0
            J[f"{prefix}UpperArm"].append(frame(arm_scale * GC.sample(cv["arm"], qa), 0, sgn * 4))
            J[f"{prefix}LowerArm"].append(frame(elbow_scale * GC.sample(cv["elbow"], qa), 0, 0))
    return times, J


def one_shot(kind, p, fps, lengths):
    """jump / fall / land: a short pose sequence sampled smoothly; a crouch drops the pelvis by what the bent legs
    lack of their straight reach, so the feet stay on the floor"""
    n = max(4, int(round(p["cycle"] * fps)))
    times = [round(i / fps, 6) for i in range(n + 1)]
    keys = {
        "jump": [(0.0, dict(crouch=0.0, arms=0.0)), (0.3, dict(crouch=1.0, arms=-0.3)), (0.6, dict(crouch=-0.2, arms=1.0)), (1.0, dict(crouch=-0.1, arms=0.8))],
        "fall": [(0.0, dict(crouch=-0.1, arms=0.8)), (0.5, dict(crouch=-0.2, arms=1.0)), (1.0, dict(crouch=-0.1, arms=0.8))],
        "land": [(0.0, dict(crouch=0.0, arms=0.8)), (0.35, dict(crouch=1.0, arms=0.2)), (1.0, dict(crouch=0.0, arms=0.0))],
    }[kind]

    def at(u, k):
        for (t0, a), (t1, b) in zip(keys, keys[1:]):
            if t0 <= u <= t1:
                w = (u - t0) / max(t1 - t0, 1e-9)
                w = w * w * (3 - 2 * w)
                return a[k] + (b[k] - a[k]) * w
        return keys[-1][1][k]

    J = {k: [] for k in ("LowerTorso", "UpperTorso", "Head", "RightUpperLeg", "RightLowerLeg", "RightFoot",
                         "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperArm", "RightLowerArm",
                         "LeftUpperArm", "LeftLowerArm")}
    for i in range(n + 1):
        u = i / n
        c, a = at(u, "crouch"), at(u, "arms")
        hip, knee = 40 * max(c, 0.0), -70 * max(c, 0.0)
        J["LowerTorso"].append(frame(0, 0, 0, (0, pelvis_drop(lengths, hip, -knee) + 0.15 * max(-c, 0.0), 0)))
        J["UpperTorso"].append(frame(p["lean"] + 12 * c, 0, 0))
        J["Head"].append(frame(-6 * c, 0, 0))
        for side in ("Right", "Left"):
            J[f"{side}UpperLeg"].append(frame(hip, 0, 0))
            J[f"{side}LowerLeg"].append(frame(knee, 0, 0))
            J[f"{side}Foot"].append(frame(-(hip + knee), 0, 0))
        J["RightUpperArm"].append(frame(-20 * c + 150 * a, 0, 15 * a + 4))
        J["LeftUpperArm"].append(frame(-20 * c + 150 * a, 0, -15 * a - 4))
        J["RightLowerArm"].append(frame(25 * (1 - a), 0, 0))
        J["LeftLowerArm"].append(frame(25 * (1 - a), 0, 0))
    return times, J


def ground_speed(times, J, rig):
    """the planted foot's constant backward ground speed over a cycle (the clip's natural speed, studs/s)"""
    clipd = {"rig": "R15", "joints": {k: {"frames": v} for k, v in J.items()}, "times": times, "fps": 1}
    frames = C.world_frames(clipd, rig)
    speeds = []
    ground = C.rest_ground(rig, ["RightFoot", "LeftFoot"])
    for f in ("RightFoot", "LeftFoot"):
        sole = np.array([0.0, -rig["sizes"][f][1] / 2, 0.0, 1.0])
        pos = np.array([(w[f] @ sole)[:3] for w in frames])
        bottoms = pos[:, 1]                                 # the sole's centre, as the metrics measure it
        for i in range(len(times) - 1):
            if bottoms[i] < ground + 0.012 and bottoms[i + 1] < ground + 0.012:   # flat on the floor, not rolling
                dt = times[i + 1] - times[i]
                if dt > 0:
                    speeds.append(np.linalg.norm(pos[i + 1, [0, 2]] - pos[i, [0, 2]]) / dt)
    return float(np.median(speeds)) if speeds else 0.0


def parameter_hint(kind, p, fps, n, problems):
    """which gait parameter to change for the FIRST gate problem (the one the summary names)"""
    text = problems[0] if problems else ""
    if kind in HUMAN and p["knee"] < 0.6 * KINDS[kind]["knee"]:
        return f"raise knee (now {p['knee']}, default {KINDS[kind]['knee']}): the swing foot cannot clear the floor"
    if "penetration" in text and ("LowerLeg" in text or "Foot" in text):
        return f"lower hip (now {p['hip']}): a straight leg that steep digs its shin's corner into the floor"
    if "penetration" in text:
        return f"lower style (now {p.get('style', p.get('roll'))}) or stance (now {p['stance']}): the pelvis sinks a part into the floor"
    if "pops" in text:
        return (f"raise fps (now {fps}: {n} frames per cycle) or cycle (now {p['cycle']} s), or move knee toward "
                f"the kind's default (now {p['knee']}, default {KINDS[kind]['knee']})")
    if "skate" in text or "skid" in text:
        return (f"lower stance (now {p['stance']}, default {KINDS[kind]['stance']}) or hip (now {p['hip']}): the "
                f"planted foot cannot follow one ground speed")
    return "change the parameter the problem names"


def sha256_of(path):
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def sha256_of_many(paths):
    """one hash over several files' bytes in order (the generator AND the module it computes with)"""
    import hashlib
    h = hashlib.sha256()
    for path in paths:
        with open(path, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def main(argv):
    if not argv:
        return emit("fail", "gait: needs <Name>.gait.json [--out <clip.json>]", "lune run kit anim new Walk --gait walk")
    path = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    with open(path, encoding="utf-8") as fh:
        g = json.load(fh)
    kind = g.get("kind", "walk")
    if kind not in KINDS:
        return emit("fail", f"gait: unknown kind {kind}", f"one of: {', '.join(KINDS)}")
    p = dict(KINDS[kind])
    for k, v in g.items():
        if k in p and isinstance(v, (int, float, bool)):
            p[k] = v
    fps = int(g.get("fps") or 30)
    name = g.get("name") or os.path.basename(path).split(".")[0]
    rig = C.load_rig("r15")
    hip_off = (rig["joints"]["RightUpperLeg"]["c0"][0], rig["joints"]["RightUpperLeg"]["c0"][1])
    fps = grid_fps(kind, p["cycle"], fps)
    times, J = one_shot(kind, p, fps, leg_lengths(rig)) if kind in ("jump", "fall", "land") else locomotion(kind, p, fps, leg_lengths(rig), hip_off, rig)
    clip = {"schema": 1, "name": name, "rig": "R15", "fps": fps, "duration": times[-1], "loop": bool(p["loop"]),
            "priority": g.get("priority") or p["priority"], "joints": {k: {"frames": v} for k, v in J.items() if v},
            "times": times, "events": g.get("events") or [], "beats": g.get("beats"), "feel": g.get("feel"),
            "gate": g.get("gate"), "source": {"kind": "gait", "file": path, "gait": kind, "params": p, "sha256": sha256_of(path),
                                                "tool_sha256": sha256_of_many([__file__, C.__file__]), "rig_sha256": sha256_of(C.rig_path("r15"))}}
    if kind in DIRECTION:
        speed = ground_speed(times, J, rig)
        clip["locomotion"] = {"speed": round(speed, 2), "direction": list(DIRECTION[kind]), "cycle": round(times[-1], 4)}
    out = out or os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{name}.clip.json")
    problems = C.metrics(clip, rig, g.get("gate"))["problems"]
    if problems:  # the kit's gates would refuse it downstream; say here WHICH parameter did it, and ship nothing
        return emit("fail", f"gait {name}: {problems[0]}", f"{parameter_hint(kind, p, fps, len(times), problems)} in {path}, then: lune run kit anim {name}",
                    problems=problems)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    loco = clip.get("locomotion")
    return emit("pass", f"gait {name} ({kind}): {len(times)} frames, {p['cycle']} s cycle" + (f", natural speed {loco['speed']} studs/s" if loco else "") + f" -> {out}",
                f"lune run kit anim {name}: the strip + the motion gates (foot skate is measured against {loco['speed'] if loco else 0} studs/s)", clip=out, locomotion=loco)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
