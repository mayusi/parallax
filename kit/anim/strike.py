"""strike.py — `python kit/anim/strike.py <Name>.move.json [--out <clip.json>]`: a weapon moveset clip for the R6 rig
from TECHNIQUE keys, with the weight of the weapon in the timing and the body.

The author writes what a swordsman does, not joint angles: at each key, where the GRIP is (the two hands' midpoint,
character space: x right, y up, -z forward) and which way the blade points, how the torso turns, leans and shifts,
where each foot stands (or hovers mid-step) and which foot carries the weight, where the head looks. The generator
then solves the body every frame:
  - the two R6 arms are placed so each hand (the arm's bottom face) sits on the hilt - the grip is moved the least
    amount that both one-piece arms can reach it (two-sphere solve), the arm boxes twist to face the hilt;
  - the legs point from their hip pivots at the feet; the pelvis sits where the weight-bearing leg puts its sole on
    the floor; the other planted leg slides up into the torso rather than dig in; a stepping foot hovers;
  - the head keeps the look the author gave against whatever the torso does.
Weight: each key eases toward the next (In = a wind-up gathering speed, Out = a cut that is fastest at once, InOut),
an `overshoot` carries the pose past the key and settles back (follow-through), the blade lags the body by `lag`
seconds (the hips lead, the steel follows), and the Hit lands one frame after the blade's tip is fastest unless the
author placed it. The clip is R6-native (`rig: "R6"`): `kit anim` compiles, strips and gates it like any other.
"""

import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402

FLOOR_R6 = -3.0           # the soles at rest (Torso at the root): legs hang 2 from y = -1
SOLE = {"Right Leg": np.array([-0.5, -2.0, 0.0]), "Left Leg": np.array([0.5, -2.0, 0.0])}   # pivot -> sole centre
HAND = {"Right Arm": np.array([0.5, -1.5, 0.0]), "Left Arm": np.array([-0.5, -1.5, 0.0])}   # pivot -> hand (bottom)
HIP = {"Right Leg": np.array([1.0, -1.0, 0.0]), "Left Leg": np.array([-1.0, -1.0, 0.0])}
SHOULDER = {"Right Arm": np.array([1.0, 0.5, 0.0]), "Left Arm": np.array([-1.0, 0.5, 0.0])}
HEAD_PIVOT = np.array([0.0, 1.0, 0.0])
REACH = float(np.linalg.norm(HAND["Right Arm"]))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


# ---------------------------------------------------------------- maths
def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0.0, -1.0, 0.0])


def rot_axis(axis, ang):
    axis = unit(np.asarray(axis, dtype=float))
    x, y, z = axis
    c, s, t = math.cos(ang), math.sin(ang), 1 - math.cos(ang)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def arc(a, b):
    """the shortest rotation taking direction a onto direction b"""
    a, b = unit(np.asarray(a, dtype=float)), unit(np.asarray(b, dtype=float))
    c = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if c > 1 - 1e-9:
        return np.eye(3)
    if c < -1 + 1e-9:
        perp = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(perp) < 1e-6:
            perp = np.cross(a, [0.0, 0.0, 1.0])
        return rot_axis(perp, math.pi)
    return rot_axis(np.cross(a, b), math.acos(c))


def euler(deg):
    return C.euler_mat(tuple(float(v) for v in deg))


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


EASES = {
    "Linear": lambda t: t,
    "InOut": smoothstep,
    "In": lambda t: t * t * t,                           # a wind-up: slow, gathering speed
    "Out": lambda t: 1 - (1 - t) ** 3,                   # a cut: fastest at once, then braking
    "Strike": lambda t: (1 - (1 - t) ** 2.2) if t < 0.72 else (1 - (1 - 0.72) ** 2.2) + (t - 0.72) / 0.28 * (1 - (1 - (1 - 0.72) ** 2.2)),
    "Constant": lambda t: 0.0 if t < 1 else 1.0,
}


def slerp(a, b, t):
    a, b = unit(np.asarray(a, dtype=float)), unit(np.asarray(b, dtype=float))
    c = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if c > 1 - 1e-6:
        return unit(a + (b - a) * t)
    w = math.acos(c)
    return (math.sin((1 - t) * w) * a + math.sin(t * w) * b) / math.sin(w)


# ---------------------------------------------------------------- the key track
FIELDS = {
    "grip": [0.5, 0.3, -0.6], "dir": [0.0, 0.9, -0.44],
    "yaw": 0.0, "pitch": 0.0, "roll": 0.0, "pos": [0.0, 0.0, 0.0],
    "right": [0.5, 0.0, 0.2], "left": [-0.5, 0.0, -0.2], "right_h": 0.0, "left_h": 0.0, "weight": "both",
    # a STEP in one segment (a feet track): the foot arcs up to `<side>_lift` and lands on the next key, one smooth travel
    # (a mid-air key stopped the passing foot in the air and jolted the leg)
    "right_lift": 0.0, "left_lift": 0.0,
    # the HIPS shifting over the feet (a feet track): the weight going back onto the rear foot to gather, then forward
    # onto the front foot as it lands - added to the torso and to the grip (the hands go with the body)
    "hip_shift": [0.0, 0.0, 0.0],
    "look_yaw": 0.0, "look_pitch": 0.0,
    # the ROOT travels (character space [x, 0, z]: a lunge, a dash, a teleport) - the clip's `root` track moves the
    # HumanoidRootPart in game (Anim root motion); everything else is solved in the root's frame, so a foot planted on
    # the ground is keyed as (its world spot - root). Unset everywhere = no root track (the clip as before)
    "root": [0.0, 0.0, 0.0],
    # a leg keyed OUTRIGHT (a reference's legs, kit/anim/keys_from.py): [pitch, yaw, roll] and a lift into the torso;
    # `legs: "keyed"` on a key switches the legs from the foot-target solve to these
    "right_rot": [0.0, 0.0, 0.0], "left_rot": [0.0, 0.0, 0.0], "right_off": [0.0, 0.0, 0.0], "left_off": [0.0, 0.0, 0.0],
    "legs": "solved",
    # arms keyed OUTRIGHT (a reference's arms): the blade then follows the right arm (sword.grip_pitch), one-handed
    "right_arm_rot": [0.0, 0.0, 0.0], "left_arm_rot": [0.0, 0.0, 0.0], "right_arm_off": [0.0, 0.0, 0.0],
    "left_arm_off": [0.0, 0.0, 0.0], "arms": "solved",
    # ONE-HANDED sword (`arms: "one_hand"` on every key): the right fist alone on the hilt, the blade free about it,
    # the off hand at `lhand` in the TORSO frame
    # UNARMED (`arms: "hands"`, a move's `unarmed`): each hand its own target, character space like the grip - the
    # striking fist on its path, the off hand at the guard (2026-10-25: the owner, "learning how to make combat")
    "rhand": [0.6, 0.2, -1.0], "lhand": [-0.5, 0.4, -1.0],
}


STEP_ONLY = ("right_lift", "left_lift")


def fill_keys(keys):
    """every key carries every field (held from the last key that set it - a step lift is not); times sorted; overshoots expanded"""
    state = {k: (list(v) if isinstance(v, list) else v) for k, v in FIELDS.items()}
    out = []
    for key in sorted(keys, key=lambda k: float(k["t"])):
        k = dict(key)
        for f in FIELDS:
            if f in STEP_ONLY:
                # a step's lift belongs to ITS segment (held, every later segment arced the landed foot off the floor
                # again: IronMountain's lead foot hovered 0.2 studs through the whole hold, 2026-10-25)
                k[f] = k.get(f, 0.0)
            elif f in k:
                state[f] = list(k[f]) if isinstance(k[f], list) else k[f]
            else:
                k[f] = list(state[f]) if isinstance(state[f], list) else state[f]
        k["ease"] = k.get("ease", "InOut")
        out.append(k)
    # follow-through: a key with overshoot o goes past itself by o of the way it came, then settles back
    expanded = []
    for i, k in enumerate(out):
        o = float(k.get("overshoot", 0) or 0)
        expanded.append(k)
        if o > 0 and i > 0:
            prev = out[i - 1]
            settle = float(k.get("settle", 0.25))
            over = dict(k)
            over["t"] = float(k["t"]) + settle * 0.4
            over["ease"] = "Out"
            back = dict(k)
            back["t"] = float(k["t"]) + settle
            back["ease"] = "InOut"
            for f in ("grip", "pos"):                      # the feet stay where they landed
                over[f] = [k[f][j] + o * (k[f][j] - prev[f][j]) for j in range(3)]
            for f in ("yaw", "pitch", "roll", "look_yaw", "look_pitch"):
                over[f] = k[f] + o * (k[f] - prev[f])
            over["dir"] = list(slerp(prev["dir"], k["dir"], 1 + o))
            k["ease"] = "Out"
            expanded += [over, back]
    # later keys must not sit inside a settle window: push them after it
    fixed = []
    last_t = -1.0
    for k in expanded:
        if float(k["t"]) <= last_t:
            k["t"] = last_t + 1e-3
        last_t = float(k["t"])
        fixed.append(k)
    return fixed


def sample(keys, t, smooth_steps=False):
    """the fields at time t: eased between the two keys around it (direction slerped, weight held)"""
    if t <= float(keys[0]["t"]):
        return dict(keys[0])
    if t >= float(keys[-1]["t"]):
        return dict(keys[-1])
    for i in range(len(keys) - 1):
        a, b = keys[i], keys[i + 1]
        ta, tb = float(a["t"]), float(b["t"])
        if ta <= t <= tb:
            raw = (t - ta) / max(tb - ta, 1e-9)
            u = EASES.get(a["ease"], smoothstep)(raw)
            out = {}
            for f in FIELDS:
                va, vb = a[f], b[f]
                if f == "dir":
                    out[f] = list(slerp(va, vb, u))
                elif f in ("right", "left"):
                    # a stepping foot LIFTS before it travels and arrives before it touches down
                    ha, hb = float(a[f + "_h"]), float(b[f + "_h"])
                    if ha <= 1e-3 and hb > 1e-3:
                        uu = smoothstep((raw - 0.2) / 0.8)
                    elif ha > 1e-3 and hb <= 1e-3:
                        uu = smoothstep(raw / 0.6)
                    else:
                        uu = u
                    out[f] = [va[j] + (vb[j] - va[j]) * uu for j in range(3)]
                elif f in ("right_h", "left_h"):
                    if va <= 1e-3 and vb > 1e-3:
                        # smooth_steps (a feet track): the foot eases OFF the floor (a full-speed lift-off jolted the
                        # passing leg 13-17 deg in a frame) and eases onto it
                        out[f] = vb * (smoothstep(raw) if smooth_steps else (1 - (1 - raw) ** 2))
                    elif va > 1e-3 and vb <= 1e-3:
                        out[f] = va * ((1 - smoothstep(raw)) if smooth_steps else (1 - raw) ** 1.5)
                    else:
                        out[f] = va + (vb - va) * u
                elif isinstance(va, list):
                    out[f] = [va[j] + (vb[j] - va[j]) * u for j in range(3)]
                elif isinstance(va, (int, float)):
                    out[f] = va + (vb - va) * u
                else:
                    out[f] = va if u < 0.5 else vb
            if smooth_steps:
                for side in ("right", "left"):
                    lift = float(a.get(side + "_lift", 0.0) or 0.0)
                    if lift > 1e-3:
                        uu = smoothstep(raw)
                        out[side] = [a[side][j] + (b[side][j] - a[side][j]) * uu for j in range(3)]
                        out[side + "_h"] = lift * math.sin(math.pi * raw)
            return out
    return dict(keys[-1])


# ---------------------------------------------------------------- the body solve
def solve_grip(G, d, torso_m, torso_p, spacing, slide=0.0):
    """move the grip the least so both hands reach it; returns (G, residual). slide: how far an arm may SLIDE along
    itself (studs) - loved R6 sword animators extend the one-piece arms 1.2-3.2 studs out of the shoulder (measured
    2026-10-17) instead of pulling the hilt in; a hand within REACH +- slide is reached without moving the grip"""
    d = unit(np.asarray(d, dtype=float))
    G = np.asarray(G, dtype=float).copy()
    piv = {arm: torso_p + torso_m @ SHOULDER[arm] for arm in ("Right Arm", "Left Arm")}
    off = {"Right Arm": +spacing / 2, "Left Arm": -spacing / 2}
    for _ in range(40):
        J, r = [], []
        for arm in ("Right Arm", "Left Arm"):
            h = G + off[arm] * d
            v = h - piv[arm]
            n = np.linalg.norm(v)
            r.append(max(0.0, n - REACH - slide) + min(0.0, n - REACH + slide))
            J.append(v / max(n, 1e-9))
        J, r = np.array(J), np.array(r)
        if np.abs(r).max() < 1e-4:
            break
        step = np.linalg.lstsq(J, -r, rcond=None)[0]
        G += step
    res = max(max(0.0, abs(np.linalg.norm(G + off[a] * d - piv[a]) - REACH) - slide) for a in ("Right Arm", "Left Arm"))
    return G, res


def arm_rotation(arm, hand_target, torso_m, torso_p, d, prev_x=None, twist_rate=None):
    """the arm's joint rotation (torso frame) putting its hand at the target: built from a FRAME, never from a
    shortest arc (an arc flips as the hand passes straight up); the arm box faces the hilt when the blade is not
    along the arm, else keeps last frame's facing; a box is the same every half turn; the facing turns at most
    ~30 degrees a frame. Returns (R_local, facing) - pass the facing back next frame.
    twist_rate (degrees a frame, a move's `arm_twist_rate`): the facing BLENDS toward the blade as the blade leaves the
    arm's line (no switch at a threshold) and turns at most that much a frame - the owner saw 'quick flashes' in the
    greatsword combo (2026-10-18): the switch + the 30 degree cap spun a box 28-37 degrees a frame for three frames"""
    piv = torso_p + torso_m @ SHOULDER[arm]
    v = hand_target - piv
    u = unit(v)
    h0 = unit(HAND[arm])
    x0 = unit(np.array([1.0, 0.0, 0.0]) - h0[0] * h0)
    z0 = np.cross(h0, x0)
    perp = float(np.linalg.norm(d - np.dot(d, u) * u))
    if twist_rate is not None and prev_x is not None:
        px0 = prev_x - np.dot(prev_x, u) * u
        bx = d - np.dot(d, u) * u
        if np.linalg.norm(px0) > 1e-6 and np.linalg.norm(bx) > 1e-6:
            px0, bx = unit(px0), unit(bx)
            if np.dot(bx, px0) < 0:
                bx = -bx
            wb = smoothstep((perp - 0.1) / 0.3)          # 0 along the arm (keep the facing) .. 1 well off it (face the hilt)
            w = (1.0 - wb) * px0 + wb * bx
        else:
            w = prev_x
    else:
        w = d if perp > 0.15 else (prev_x if prev_x is not None else np.array([0.0, 0.0, -1.0]))
    x = unit(w - np.dot(w, u) * u)
    if prev_x is not None:
        px = prev_x - np.dot(prev_x, u) * u
        if np.linalg.norm(px) > 1e-6:
            px = unit(px)
            if np.dot(x, px) < 0:
                x = -x
            ang = math.atan2(float(np.dot(np.cross(px, x), u)), float(np.dot(px, x)))
            cap = math.radians(twist_rate) if twist_rate is not None else 0.52
            ang = max(-cap, min(cap, ang))
            x = unit(rot_axis(u, ang) @ px)
    z = np.cross(u, x)
    R_world = np.column_stack([u, x, z]) @ np.column_stack([h0, x0, z0]).T
    return torso_m.T @ R_world, x


def leg_solve(leg, foot_xz, foot_h, torso_m, torso_p, planted, turn=None):
    """the leg's rotation (torso frame) pointing at the foot; returns (R_local, sole_y_at_torso_p, hip_world).
    turn: a world rotation the leg starts from (legs 'with_body': the body's yaw, so the leg turns WITH the torso and
    only its pitch / roll are solved - a shortest arc from rest twisted the leg by the whole turn)"""
    hip = torso_p + torso_m @ HIP[leg]
    target = np.array([foot_xz[0], FLOOR_R6 + foot_h, foot_xz[1]])
    v = target - hip
    horiz = math.hypot(v[0], v[2])
    L = float(np.linalg.norm(SOLE[leg]))
    if planted and horiz < L * 0.999:
        v = np.array([v[0], -math.sqrt(L * L - horiz * horiz), v[2]])   # the straight leg lands the sole there
    if turn is not None:
        R = arc(turn @ SOLE[leg], v) @ turn
    else:
        R = arc(SOLE[leg], v)
    sole = hip + R @ SOLE[leg]
    return torso_m.T @ R, sole, hip


def frame_of(m, p=(0.0, 0.0, 0.0)):
    q = C.mat_quat(np.asarray(m, dtype=float))
    return [round(float(x), 6) for x in q] + [round(float(x), 5) for x in p]


ARM_CENTRE = {"Right Arm": np.array([0.5, -0.5, 0.0]), "Left Arm": np.array([-0.5, -0.5, 0.0])}   # pivot -> box centre
_AG = np.linspace(-0.45, 0.45, 4)
ARM_PTS = np.array([[x * 0.5, y, z * 0.5] for x in _AG for y in np.linspace(-0.95, 0.95, 7) for z in _AG])


def arm_in_body(arm, R_local, slid):
    """the share of an arm box inside the torso or the head (torso frame; the head ~1.2 studs round on the neck)"""
    pts = SHOULDER[arm] + np.asarray(slid, dtype=float) + (R_local @ (ARM_CENTRE[arm] + ARM_PTS).T).T
    torso = np.all(np.abs(pts) < np.array([0.95, 0.95, 0.45]), axis=1)
    head = np.all(np.abs(pts - np.array([0.0, 1.5, 0.0])) < 0.55, axis=1)
    return float(np.mean(torso | head))


FEEL_PRESETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feel_presets.json")


def resolve_feel(feel):
    """a move's `feel`: a TIER name ("light" / "medium" / "heavy", kit/anim/feel_presets.json) or {tier, ...overrides}
    -> the numbers; a plain dict without a tier passes through unchanged (AAA plan #7)"""
    tier = feel if isinstance(feel, str) else (feel.get("tier") if isinstance(feel, dict) else None)
    if tier is None:
        return feel
    tiers = json.load(open(FEEL_PRESETS, encoding="utf-8"))["tiers"]
    if tier not in tiers:
        raise SystemExit(f"feel tier '{tier}' unknown: {sorted(tiers)} (kit/anim/feel_presets.json)")
    out = dict(tiers[tier], tier=tier)
    if isinstance(feel, dict):
        out.update({k: v for k, v in feel.items() if k != "tier"})
    return out


def apply_arm_poses(keys, times, J, tips, grips):
    """the OWNER's ARM POSES (2026-10-19: "THE ARMS LOOK AT HOW THE ARMS ARE LIKE ROTATEED AND POSED TOO ITS THE POSES"
    - rebuilt from his hilt path alone, the solver chose its own arm rotations and lost his). A key's `arms_pose`
    {"Right Arm": joint frame, "Left Arm": joint frame, "grip_local", "tip_local"} (torso-relative Motor6D frames + the
    sword in the right arm part's frame, read from his own file - kit/anim/block.py arms) REPLACES the solved arms at
    that key; between two keys the arms are slerped from one pose to the next with the key's ease, a key without a pose
    standing for the solved arms (so the move blends in and out of his poses - no jump at a seam); the sword rides in
    the right hand as it sat in his file"""
    if not any(k.get("arms_pose") for k in keys):
        return
    n = len(times)
    rig = C.load_rig("r6")
    solved = {"name": "arm_poses", "rig": "R6", "times": times,
              "joints": {k: {"frames": [list(f) for f in v]} for k, v in J.items()}}
    W0 = C.world_frames(solved, rig)
    loc0 = []
    for i in range(n):
        inv = np.linalg.inv(W0[i]["Right Arm"])
        loc0.append(((inv @ np.append(grips[i], 1.0))[:3], (inv @ np.append(tips[i], 1.0))[:3]))
    touched = []
    for i in range(n):
        t = times[i]
        if t <= float(keys[0]["t"]) or t >= float(keys[-1]["t"]):
            a = b = keys[0] if t <= float(keys[0]["t"]) else keys[-1]
            u = 0.0
        else:
            j = max(k for k in range(len(keys) - 1) if float(keys[k]["t"]) <= t)
            a, b = keys[j], keys[j + 1]
            raw = (t - float(a["t"])) / max(float(b["t"]) - float(a["t"]), 1e-9)
            u = EASES.get(a.get("ease", "InOut"), smoothstep)(raw)
        pa, pb = a.get("arms_pose"), b.get("arms_pose")
        if not pa and not pb:
            continue
        touched.append(i)
        for arm in ("Right Arm", "Left Arm"):
            A = pa[arm] if pa else J[arm][i]
            B = pb[arm] if pb else J[arm][i]
            q = C.slerp(A[:4], B[:4], u)
            J[arm][i] = [round(float(v), 6) for v in q] + [round(float(A[k]) * (1 - u) + float(B[k]) * u, 5) for k in range(4, 7)]
        ga = np.asarray(pa["grip_local"], float) if pa else loc0[i][0]
        gb = np.asarray(pb["grip_local"], float) if pb else loc0[i][0]
        ta = np.asarray(pa["tip_local"], float) if pa else loc0[i][1]
        tb = np.asarray(pb["tip_local"], float) if pb else loc0[i][1]
        loc0[i] = (ga * (1 - u) + gb * u, ta * (1 - u) + tb * u)
    if not touched:
        return
    W1 = C.world_frames({"name": "arm_poses", "rig": "R6", "times": times,
                         "joints": {k: {"frames": v} for k, v in J.items()}}, rig)
    for i in touched:
        RA = W1[i]["Right Arm"]
        g, tp = loc0[i]
        grips[i] = (RA @ np.append(g, 1.0))[:3]
        d = (RA @ np.append(tp, 1.0))[:3] - grips[i]
        tips[i] = grips[i] + d * (float(np.linalg.norm(tips[i] - grips[i])) / max(1e-9, float(np.linalg.norm(d))))


def apply_overlap(move, J, tips, grips, fps):
    """SUCCESSIVE BREAKING (AAA plan #4; pros offset each part - the hips lead, the chest follows, the arms drag, the
    head and the blade settle last; we eased the whole pose at once): `move.overlap` {"arms": frames, "head": frames}
    delays those parts' motion RELATIVE TO THE TORSO by that many frames (fractional ok). The arms hold the hilt, so the
    arms and the sword drag TOGETHER in the torso's frame - the blade path is carried by the torso's turn since then:
    grip'(t) = torso(t) . torso(t-d)^-1 . grip(t-d) - the hands never leave the tsuka. Legs never drag (planted feet)"""
    ov = move.get("overlap") or {}
    if not ov:
        return
    n = len(J["Torso"])

    def sample(F, u):
        u = max(0.0, min(n - 1.0, u))
        i = int(math.floor(u))
        j = min(n - 1, i + 1)
        w = u - i
        q = C.slerp(F[i][:4], F[j][:4], w)
        p = [F[i][k] * (1 - w) + F[j][k] * w for k in range(4, len(F[i]))]
        return [round(float(v), 6) for v in q] + [round(float(v), 5) for v in p]

    def torso_m(u):
        f = sample(J["Torso"], u)
        M = np.eye(4)
        M[:3, :3] = C.quat_mat(f[:4])
        M[:3, 3] = f[4:7]
        return M

    d_head = float(ov.get("head", 0.0))
    if d_head > 0:
        F = [list(x) for x in J["Head"]]
        J["Head"] = [sample(F, i - d_head) for i in range(n)]
    d_arm = float(ov.get("arms", 0.0))
    if d_arm > 0:
        for arm in ("Right Arm", "Left Arm"):
            F = [list(x) for x in J[arm]]
            J[arm] = [sample(F, i - d_arm) for i in range(n)]
        T0, G0 = [np.array(t, float) for t in tips], [np.array(g, float) for g in grips]

        def at(P, u):
            u = max(0.0, min(n - 1.0, u))
            i = int(math.floor(u))
            j = min(n - 1, i + 1)
            w = u - i
            return P[i] * (1 - w) + P[j] * w

        for i in range(n):
            u = i - d_arm
            X = torso_m(i) @ np.linalg.inv(torso_m(u))
            g, t = at(G0, u), at(T0, u)
            grips[i] = (X @ np.append(g, 1.0))[:3]
            tips[i] = (X @ np.append(t, 1.0))[:3]


def apply_key_edits(keys, ed):
    """the OWNER's blocking edits (kit/anim/block.py read: assets/animations/blocks/<Move>.edits.json) on the keys -
    per key the hilt moved, the blade turned, the torso's yaw / pitch / roll and height, the feet; deltas, so the
    authored keys stay the source and his changes ride on them through every rebuild. None = the keys as they are"""
    if not ed or not ed.get("keys"):
        return keys
    out = [json.loads(json.dumps(k)) for k in keys]
    # a key that INHERITS a field (fill_keys holds it from the last key that set it) gets the delta on the inherited
    # value, written explicitly - never a delta read as an absolute, never an edit dropped
    state = {f: (list(v) if isinstance(v, list) else v) for f, v in FIELDS.items()}
    held = [None] * len(out)
    for j in sorted(range(len(out)), key=lambda j: float(out[j]["t"])):
        for f in FIELDS:
            if f in out[j]:
                state[f] = list(out[j][f]) if isinstance(out[j][f], list) else out[j][f]
        held[j] = {f: (list(v) if isinstance(v, list) else v) for f, v in state.items()}
    for i, e in ed["keys"].items():
        i = int(i)
        if not 0 <= i < len(out):
            continue
        k = out[i]
        for f in ("grip", "dir", "yaw", "pitch", "roll", "pos", "right", "left"):
            if f not in k and any(x in e for x in ((f,) if f != "pos" else ("pos_y",))):
                k[f] = held[i][f]
        if "grip" in e and k.get("grip") is not None:
            k["grip"] = [round(float(a) + float(b), 4) for a, b in zip(k["grip"], e["grip"])]
        if "dir" in e and k.get("dir") is not None:
            d = unit(np.asarray(k["dir"], float) + np.asarray(e["dir"], float))
            k["dir"] = [round(float(x), 4) for x in d]
        for f in ("yaw", "pitch", "roll"):
            if f in e:
                k[f] = round(float(k.get(f, 0.0)) + float(e[f]), 3)
        if "pos_y" in e:
            p = list(k.get("pos") or [0.0, 0.0, 0.0])
            p[1] = round(float(p[1]) + float(e["pos_y"]), 4)
            k["pos"] = p
        for f in ("right", "left"):
            if f in e and k.get(f) is not None:
                v = list(k[f])
                v[0], v[2] = round(float(v[0]) + float(e[f][0]), 4), round(float(v[2]) + float(e[f][1]), 4)
                k[f] = v
    return out


def apply_push(keys, move):
    """EXAGGERATION (AAA gaps v2 B1; gamedev12: exaggerate past reference, consistently): `move.push` (or a key's own
    `push`) scales every key's offset from the OPENING key (the guard) - the torso's yaw / pitch / roll and height, the
    hilt, the blade's direction, the feet - so the extremes go further and the guard stays put. 1.0 = nothing; capped
    at 1.5. A key carrying the OWNER's own arm poses (`arms_pose`) is never pushed: his poses are copied exactly"""
    base = float(move.get("push", 1.0))
    if base == 1.0 and not any("push" in k for k in keys):
        return keys
    g = keys[0]
    out = []
    for i, k in enumerate(keys):
        k = json.loads(json.dumps(k))
        s = min(1.5, max(0.5, float(k.get("push", base))))
        if i == 0 or s == 1.0 or k.get("arms_pose"):
            out.append(k)
            continue
        for f in ("yaw", "pitch", "roll"):
            k[f] = round(float(g[f]) + (float(k[f]) - float(g[f])) * s, 3)
        for f in ("grip", "pos", "right", "left"):
            if k.get(f) is not None and g.get(f) is not None:
                k[f] = [round(float(a) + (float(b) - float(a)) * s, 4) for a, b in zip(g[f], k[f])]
        if k.get("dir") is not None and g.get("dir") is not None:
            d = unit(np.asarray(g["dir"], float) + (np.asarray(k["dir"], float) - np.asarray(g["dir"], float)) * s)
            k["dir"] = [round(float(x), 4) for x in d]
        out.append(k)
    return out


def apply_impact_dip(keys, move):
    """the SQUASH an R6 can do (AAA gaps v2 B8: rigid parts cannot squash): `move.impact_dip` {"key": i, "dy": -0.12}
    sinks the body at that key (its `pos` height) - solved like any key, so the legs bend the R6 way and the feet stay
    planted (a dip added after the solve sank the feet: R6 legs hang off the torso)"""
    d = move.get("impact_dip")
    if not d:
        return keys
    out = [json.loads(json.dumps(k)) for k in keys]
    i = int(d.get("key", -1))
    if 0 <= i < len(out):
        p = list(out[i].get("pos") or [0.0, 0.0, 0.0])
        p[1] = round(float(p[1]) + float(d.get("dy", -0.1)), 4)
        out[i]["pos"] = p
    return out


def apply_swing(keys, move, fps):
    """A3, THE SWING AS A WHIP (kit/anim/swing_mechanics.py, LIMITATIONS_FIXES_V4 13.4.1, card x9gk): `move.swing`
    {"kind": horizontal|diagonal|overhead|rising|thrust, "intent": calm|proper|aggressive, "weight": light|heavy,
    "drop": true} RETIMES the authored keys - never adds to them (adding turned the body twice): between the wind-up
    and the Hit each group reads the same keys AHEAD of the clock by the chain's lead and then waits at its Hit pose -
    the hips (pos) 6 frames, the torso (yaw / pitch / roll) 4, the hands (grip) 1, the blade (dir) on the Hit, so the
    body finishes first and the blade snaps last (an R6 torso is one piece: its hips are the body's position). Then the
    body sinks AT LEAST the solver's pelvis drop below its opening height (a move that already sinks deeper keeps its
    own; solved like impact_dip: the R6 legs bend, the feet stay planted),
    the Hit pose is HELD for the solver's 2..4 frames (the events after it move with it), and the feet track's steps
    land 3 frames earlier (the lead foot still >= 2 frames before the Hit). -> (keys, move): new dense keys at 60 fps and
    a copy of the move. Unset: (keys, move) unchanged. Refused: a move with no Hit event, or keys carrying the owner's
    own arm poses (copied exactly, never retimed)"""
    sw = move.get("swing")
    if not sw:
        return keys, move
    import swing_mechanics as SM  # noqa: PLC0415

    hit = next((float(e["t"]) for e in move.get("events") or [] if e.get("name") == "Hit"), None)
    if hit is None:
        raise ValueError("swing: the move has no Hit event - the chain is timed to it")
    if any(k.get("arms_pose") for k in keys):
        raise ValueError("swing: a key carries the owner's own arm poses (arms_pose) - copied exactly, never retimed")
    dur = float(keys[-1]["t"])
    plan = SM.solve_swing({"hit": hit, "duration": dur, "kind": sw.get("kind", "horizontal"),
                           "weight": sw.get("weight", "light")}, intent=sw.get("intent", "proper"))
    F = float(SM.FPS)
    windup = float(plan["beats"]["windup"][0])
    ramp = max(1.0 / F, plan["peaks"]["pelvis"] / F - windup)
    hold = plan["params"]["hold"] / F
    drop = plan["channels"]["pelvis_y"] if sw.get("drop", True) else None
    y0 = float((keys[0].get("pos") or [0.0, 0.0, 0.0])[1])   # the opening (guard) height the drop is measured from
    LEADS = ((("pos", "hip_shift"), 6), (("yaw", "pitch", "roll"), 4), (("grip", "rhand", "lhand"), 1))
    out = []
    n = int(round((dur + hold) * F))
    for i in range(n + 1):
        t_out = i / F
        t = t_out if t_out <= hit else max(hit, t_out - hold)   # the Hit pose held `hold`, the rest after it
        k = sample(keys, t)
        if windup <= t <= hit:
            r = smoothstep(min(1.0, (t - windup) / ramp))
            for fields, lead in LEADS:
                s = sample(keys, min(hit, t + r * lead / F))
                for f in fields:
                    if f in s:
                        k[f] = s[f]
        if drop is not None:   # (AT LEAST the plan's depth below the opening height: a move that already sinks enough
            j = min(len(drop) - 1, int(round(t * F)))   # keeps its own - two drops added sank the body twice)
            p = list(k.get("pos") or [0.0, 0.0, 0.0])
            p[1] = round(min(float(p[1]), y0 + float(drop[j])), 5)
            k["pos"] = p
        k["t"] = round(t_out, 6)
        k["ease"] = "Linear"
        out.append(k)
    m = dict(move)
    m["events"] = [dict(e, t=round(float(e["t"]) + (hold if float(e["t"]) > hit + 1e-9 else 0.0), 6))
                   for e in move.get("events") or []]
    if move.get("feet"):
        feet = []
        for fk in move["feet"]:
            fk = dict(fk)
            ft = float(fk["t"])
            if windup < ft <= hit:
                ft = max(windup, ft - 3.0 / F)   # (the steps land before the cut: the lead foot still >= 2 f pre-Hit)
            elif ft > hit:
                ft += hold
            fk["t"] = round(ft, 6)
            feet.append(fk)
        m["feet"] = feet
    m["swing_plan"] = {"beats": plan["beats"], "peaks": plan["peaks"], "params": plan["params"]}
    return out, m


def apply_moving_holds(move, J, tips, grips, fps):
    """MOVING HOLDS (AAA gaps v2 B2; owner 2026-10-19: "so static"): `move.moving_hold` {"min": s, "drift": deg,
    "breath": deg, "still": deg/s}: wherever the body is near still for `min` seconds (every upper-body joint turning
    under `still` deg/s), the torso keeps settling (a slow bow of up to `drift` degrees, eased) and the head breathes
    (a slow `breath` degree nod), so a held pose never reads as a frozen 3D model. The torso carries the arms and the
    sword: the blade paths turn with it about the torso, so the hands never leave the hilt"""
    mh = move.get("moving_hold")
    if not mh:
        return []
    n = len(J["Torso"])
    still = math.radians(float(mh.get("still", 25.0))) / fps
    min_n = max(2, int(round(float(mh.get("min", 0.15)) * fps)))
    drift = math.radians(float(mh.get("drift", 1.5)))
    breath = math.radians(float(mh.get("breath", 1.0)))

    def ang(a, b):
        return math.radians(C.quat_angle(a[:4], b[:4]))

    quiet = [False] * n
    for i in range(1, n):
        quiet[i] = all(ang(J[p][i - 1], J[p][i]) < still for p in ("Torso", "Head", "Right Arm", "Left Arm"))
    runs, i = [], 1
    while i < n:
        if quiet[i]:
            j = i
            while j + 1 < n and quiet[j + 1]:
                j += 1
            if j - i + 1 >= min_n:
                runs.append((i, j))
            i = j + 1
        else:
            i += 1
    for i0, i1 in runs:
        L = i1 - i0 + 1
        for i in range(i0, i1 + 1):
            u = (i - i0) / max(L - 1, 1)
            env = math.sin(math.pi * u)                   # in and out of the hold without a step
            a = drift * smoothstep(min(1.0, 2 * u)) * env
            R = rot_axis(np.array([1.0, 0.0, 0.0]), -a)    # a slow forward settle about the character's X
            Rt = C.quat_mat(J["Torso"][i][:4])
            pt = np.asarray(J["Torso"][i][4:7], float)
            J["Torso"][i] = frame_of(R @ Rt, tuple(pt))
            for P in (tips, grips):
                v = np.asarray(P[i], float)
                P[i] = pt + R @ (v - pt)
            b = breath * math.sin(2 * math.pi * (i - i0) / max(fps * 1.2, 1)) * env
            Rh = rot_axis(np.array([1.0, 0.0, 0.0]), b) @ C.quat_mat(J["Head"][i][:4])
            J["Head"][i] = frame_of(Rh, tuple(J["Head"][i][4:7]))
    return [[round(i0 / fps, 4), round(i1 / fps, 4)] for i0, i1 in runs]


MARKERS = ("Swing", "ActiveStart", "Hit", "ActiveEnd")


def camera_keys(keys):
    """an authored camera track (D9): [{t, loc: [x,y,z], target: [x,y,z], fov?}] in the character's starting root
    space (Roblox: x right, y up, -z forward) -> checked + sorted; a bad key is an error, not a silent skip"""
    out = []
    for k in keys:
        loc, tgt = k.get("loc"), k.get("target")
        if not (isinstance(loc, list) and len(loc) == 3 and isinstance(tgt, list) and len(tgt) == 3):
            raise ValueError(f"camera key {k}: needs loc [x,y,z] and target [x,y,z]")
        if np.linalg.norm(np.subtract(loc, tgt)) < 1e-3:
            raise ValueError(f"camera key at t={k.get('t')}: loc and target are the same point")
        row = {"t": round(float(k["t"]), 4), "loc": [float(v) for v in loc], "target": [float(v) for v in tgt]}
        if k.get("fov") is not None:
            row["fov"] = float(min(120.0, max(1.0, k["fov"])))
        out.append(row)
    return sorted(out, key=lambda r: r["t"])


def add_markers(clip, move, speeds, fps):
    """THE MARKER CONTRACT (AAA gaps v2 D11): every strike carries the same markers the game reads - Swing (the blade
    gets going: 40 % of its peak speed, the swing sound / trail cue), ActiveStart (a frame before the Hit), Hit,
    ActiveEnd (the blade slowed under 30 % of its peak, at most 0.15 s after the Hit) - unless the author placed them.
    Also the MOTION-WARP window (C5: the travel the game may scale / turn toward a target; `move.warp` or, when the
    clip travels, its start to the Hit) and the CAMERA KICK (D9: along the blade's direction at the Hit, its size from
    the feel tier's camera shake)"""
    ev = clip["events"]
    have = {e.get("name") for e in ev}
    hit = next((float(e["t"]) for e in ev if e.get("name") == "Hit"), None)
    if hit is None or not speeds:
        return
    times = clip["times"]
    hi = min(len(speeds) - 1, int(round(hit * fps)))
    peak = max(speeds)
    if "Swing" not in have:
        # walked back from this cut's own speed PEAK before the Hit (the slam's fastest frame is 3 frames before its
        # contact: walking back from the Hit stopped at once)
        lo = max(0, hi - int(round(0.4 * fps)))
        i = lo + int(np.argmax(speeds[lo:hi + 1]))
        p_local = speeds[i]
        while i > 0 and speeds[i - 1] > 0.4 * p_local:
            i -= 1
        ev.append({"name": "Swing", "t": round(times[i], 4)})
    if "ActiveStart" not in have:
        ev.append({"name": "ActiveStart", "t": round(times[max(0, hi - 1)], 4)})
    if "ActiveEnd" not in have:
        j, last = hi, min(len(speeds) - 1, hi + int(round(0.15 * fps)))
        while j < last and speeds[j] > 0.3 * peak:
            j += 1
        ev.append({"name": "ActiveEnd", "t": round(times[min(len(times) - 1, j + 1)], 4)})
    sm = move.get("smear")
    if sm and "Smear" not in have:
        # SMEARS (AAA gaps v2 B6): an R6 part cannot stretch, so on the blade's FASTEST frames the runtime lays motion
        # slabs (each part stretched from where it was a frame ago to where it is) - opt-in per move: a look change
        opts = sm if isinstance(sm, dict) else {}
        lo = max(0, hi - int(round(0.25 * fps)))
        i = lo + int(np.argmax(speeds[lo:hi + 2]))
        dur = float(opts.get("s", 0.05))
        start = max(0, i - int(round(dur * fps / 2)))
        ev.append({"name": "Smear", "t": round(times[start], 4),
                   "value": f"{opts.get('parts', 'Right Arm')};{dur:g}"})
    ev.sort(key=lambda e: float(e.get("t", 0)))
    if clip.get("root"):
        w = move.get("warp") or {"from": 0.0, "to": hit}
        end = float(times[-1])
        try:
            w_from, w_to = float(w.get("from", 0.0)), float(w.get("to", hit))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("warp: it is {\"from\": seconds, \"to\": seconds} (the window in which the travel is scaled "
                             "and turned toward a target)") from None
        if not (w_from == w_from and w_to == w_to) or w_from < 0 or w_to < w_from or w_to > end + 1e-6:
            raise ValueError(f"warp: its window runs from {w_from:g} s to {w_to:g} s - it starts at 0 or later, ends at or "
                             f"after its start and inside the clip ({end:g} s; \"to\" is the Hit, {hit:g} s, when it is "
                             "not said)")
        clip["warp"] = {"from": w_from, "to": w_to}
        if isinstance(w, dict) and w.get("pace") is True:
            # TIMING THAT FOLLOWS THE DISTANCE (src/kit/AnimWarp pace, AN-14): the game plays the standing part and
            # the travelling part of the window at rates that follow how far the warp reaches; opt-in per move
            clip["warp"]["pace"] = True
    sw = clip.get("sword") or {}
    tips = sw.get("tip") or []
    if len(tips) > hi + 1:
        d = np.asarray(tips[hi + 1], float) - np.asarray(tips[max(0, hi - 1)], float)
        if np.linalg.norm(d) > 1e-6:
            amp = float((clip.get("feel") or {}).get("camera_shake", 0.4)) * 0.5
            clip["camera_kick"] = {"t": round(hit, 4), "dir": [round(float(x), 4) for x in unit(d)], "amp": round(amp, 3)}


def apply_steps(move, times, J, sword_out, roots, events, fps):
    """LIMITED ANIMATION (the anime look - Arc System Works, GDC 2015: interpolation OFF, every frame a key, every bone
    touched per key to add imperfection; ours were smooth 60 fps everywhere, "more 3D"). `move.step`:
    {"on": N, "beats": ["strike", ...] | "all", "windows": [[t0, t1], ...], "imperfection": degrees}: inside the
    windows each pose is HELD N frames, then snaps to the next (the smooth solve sampled every N frames); with
    imperfection the head and arms of each held pose turn a little off the perfect path (deterministic per block) so
    no turn reads as a rigid 3D rotation. Returns [[t0, t1, N], ...] for the clip (`stepped`): the gates skip these
    intended snaps. Off (no `step`) = nothing changes"""
    st = move.get("step")
    if not st:
        return None
    on = max(2, int(st.get("on", 2)))
    wins = [list(map(float, w)) for w in st.get("windows") or []]
    beats = move.get("beats") or {}
    names = st.get("beats") or []
    if names == "all":
        wins.append([0.0, float(times[-1])])
    else:
        wins += [list(map(float, beats[b])) for b in names if b in beats]
    amp = math.radians(float(st.get("imperfection", 0.0)))
    # MIXED CADENCE (AAA gaps v2 B7; anime limited animation: the body on 2s, the blade on 1s): `step.arms_on: 1` keeps
    # the arms and the sword smooth while the body holds its poses
    arms_smooth = int(st.get("arms_on", on)) == 1
    n = len(times)
    out = []
    merged = []                                   # touching / overlapping windows are ONE run of holds (two runs
    for t0, t1 in sorted(wins):                   # sharing a beat edge held one pose 7 frames instead of 5)
        if merged and t0 <= merged[-1][1] + 0.5 / fps:
            merged[-1][1] = max(merged[-1][1], t1)
        else:
            merged.append([t0, t1])
    for t0, t1 in merged:
        i0, i1 = max(0, int(round(t0 * fps))), min(n - 1, int(round(t1 * fps)))
        for i in range(i0, i1 + 1):
            src = i0 + ((i - i0) // on) * on
            if i == src:                                     # the block's pose, before any frame of it is touched
                plain = {k: list(J[k][src]) for k in J}
                plain_sw = {key: list(sword_out[key][src]) for key in ("tip", "grip_path", "edge")}
                plain_root = list(roots[src])
            for k in J:
                if arms_smooth and k in ("Right Arm", "Left Arm"):
                    continue
                J[k][i] = list(plain[k])
            if not arms_smooth:
                for key in ("tip", "grip_path", "edge"):
                    sword_out[key][i] = list(plain_sw[key])
            roots[i] = list(plain_root)
            if amp > 0:
                # the HEAD only: the arms hold the hilt - turned on their own they left the tsuka (review 2026-10-18)
                for part in ("Head",):
                    rng = np.random.default_rng((src * 7919 + sum(map(ord, part))) & 0xFFFFFFFF)
                    ax = unit(rng.normal(size=3))
                    R = rot_axis(ax, amp * float(rng.uniform(0.4, 1.0))) @ C.quat_mat(J[part][i][:4])
                    J[part][i] = frame_of(R, tuple(J[part][i][4:7]))
        out.append([round(t0, 4), round(t1, 4), on])
        # the Hit lands on a NEW pose: the first step boundary at or after it (or the frame the window hands back
        # to smooth motion) - never inside a hold
        bounds = list(range(i0, i1 + 1, on)) + ([i1 + 1] if i1 + 1 < n else [])
        for e in events:
            if e.get("name") == "Hit" and t0 <= float(e["t"]) <= t1:
                j = int(round(float(e["t"]) * fps))
                j = next((b for b in bounds if b >= j), bounds[-1])
                e["t"] = round(times[j], 4)
    return out


TWIST_MAX = 720.0          # degrees a second: the fastest the hands roll the blade about itself


def blade_edges(tips, grips, fps, start=None, end=None):
    """the cutting EDGE's direction per frame (unit, across the blade): the owner, 2026-10-18 - 'the sword itself u have
    like not properly animated in alot of the poses' - only the blade's LINE was kept, its roll came from a fixed up
    vector, so the edge faced anywhere and spun. Set at the fastest frame (the cut: the edge LEADS the tip there), then
    carried out frame by frame both ways: the tip's sideways motion picks the side nearest last frame's edge (a wind-up
    goes spine first, never a 180 degree roll), weighted by the tip's speed; a still blade keeps its last edge.
    start: a COMBO move's first edge (the last clip's `edge_end`) - the blade turns from it to this cut's edge over the
    wind-up (each clip picking its own flipped the edge 165 degrees at a seam)
    end: the edge the clip must END on (a move's `edge_end_at`: a POOL of cuts that all start and end on one guard,
    2026-10-31 - the Swift set's Handle ended 66-161 degrees rolled from its start, a flip at every chained seam):
    the mirror of start, turned from the cut's own edge over the recovery"""
    n = len(tips)
    if n == 0:
        return []
    T = [np.asarray(t, dtype=float) for t in tips]
    D = [unit(T[i] - np.asarray(grips[i], dtype=float)) for i in range(n)]

    def side(i):
        v = T[min(n - 1, i + 1)] - T[max(0, i - 1)]
        v = v - (v @ D[i]) * D[i]
        sp = float(np.linalg.norm(v)) * fps / max(1, min(n - 1, i + 1) - max(0, i - 1))
        return (v / np.linalg.norm(v) if np.linalg.norm(v) > 1e-9 else None), sp

    sides = [side(i) for i in range(n)]
    peak = max(range(n), key=lambda i: sides[i][1])
    E = [None] * n

    def flat(i):                                     # any edge across the blade (a clip that never moves)
        a = np.array([0.0, 0.0, -1.0]) if abs(D[i][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        return unit(a - (a @ D[i]) * D[i])

    E[peak] = sides[peak][0] if sides[peak][0] is not None else flat(peak)
    for order in (range(peak + 1, n), range(peak - 1, -1, -1)):
        prev = peak
        for i in order:
            e0 = E[prev] - (E[prev] @ D[i]) * D[i]                  # last frame's edge, turned with the blade
            e0 = unit(e0) if np.linalg.norm(e0) > 1e-6 else flat(i)
            s, sp = sides[i]
            if s is not None:
                s = s if s @ e0 >= 0 else -s
                w = smoothstep((sp - 2.0) / 10.0) * 0.5              # still (< 2 studs/s): hold; fast: follow the motion
                want = unit((1.0 - w) * e0 + w * s)
                # the hands turn the blade over at most TWIST_MAX a second (the tip reversing at the top of a wind-up
                # rolled the edge 35-52 degrees in a frame: a snap)
                ang = math.acos(max(-1.0, min(1.0, float(e0 @ want))))
                cap = math.radians(TWIST_MAX) / fps
                if ang > cap:
                    perp = unit(want - (want @ e0) * e0)
                    want = math.cos(cap) * e0 + math.sin(cap) * perp
                e0 = want
            E[i] = e0
            prev = i
    if start is not None and peak > 0:
        # from the last clip's edge to this cut's: turned at an even rate over the wind-up (at least TWIST_MAX, faster
        # only when the turn could not be done by the cut otherwise), arriving on the cut's own edge
        cur = np.asarray(start, dtype=float)
        cap = math.radians(TWIST_MAX) / fps
        for i in range(peak + 1):
            cur = cur - (cur @ D[i]) * D[i]
            cur = unit(cur) if np.linalg.norm(cur) > 1e-6 else E[i]
            if i == 0:                                      # the seam frame IS the last clip's edge
                E[0] = cur
                continue
            tgt = E[i]
            ang = math.acos(max(-1.0, min(1.0, float(cur @ tgt))))
            if ang < 1e-6:
                E[i] = tgt
                continue
            step = min(ang, max(cap, ang / max(1, peak - i)))
            perp = tgt - (tgt @ cur) * cur
            if np.linalg.norm(perp) < 1e-6:                 # exactly opposite: turn through the blade's side
                perp = np.cross(D[i], cur)
            perp = unit(perp)
            cur = math.cos(step) * cur + math.sin(step) * perp
            E[i] = cur
    if end is not None and peak < n - 1:
        cur = np.asarray(end, dtype=float)
        cap = math.radians(TWIST_MAX) / fps
        for i in range(n - 1, peak - 1, -1):
            cur = cur - (cur @ D[i]) * D[i]
            cur = unit(cur) if np.linalg.norm(cur) > 1e-6 else E[i]
            if i == n - 1:                                  # the seam frame IS the guard's edge
                E[i] = cur
                continue
            tgt = E[i]
            ang = math.acos(max(-1.0, min(1.0, float(cur @ tgt))))
            if ang < 1e-6:
                E[i] = tgt
                continue
            step = min(ang, max(cap, ang / max(1, i - peak)))
            perp = tgt - (tgt @ cur) * cur
            if np.linalg.norm(perp) < 1e-6:
                perp = np.cross(D[i], cur)
            perp = unit(perp)
            cur = math.cos(step) * cur + math.sin(step) * perp
            E[i] = cur
    return E


def generate(move, _floors=None, _pushes=None):
    fps = int(move.get("fps") or 30)
    sword = move.get("sword") or {}
    spacing = float(sword.get("grip", 0.75))
    blade = float(sword.get("length", 4.6))
    grip_pitch = math.radians(float(sword.get("grip_pitch", 0.0)))
    lag = float(move.get("lag", 0.03))
    unarmed = bool(move.get("unarmed"))
    src_keys = apply_key_edits(move["keys"], move.get("key_edits"))
    if unarmed:                                                 # every key: the hands each on their own target
        src_keys = [dict(k, arms=k.get("arms", "hands")) for k in src_keys]
    keys = fill_keys(src_keys)
    keys = apply_impact_dip(apply_push(keys, move), move)       # AAA gaps v2 B1 / B8: exaggeration, the impact sink
    keys, move = apply_swing(keys, move, fps)                   # A3 (V4 13.4.1): the chain, the drop, the hold - opt-in
    # a FEET track of its own (`feet`: keys of right / left / right_h / left_h / root): real footwork steps land BEFORE
    # the cut and the back foot follows (measured on real swordsmen, 2026-10-18) - on its own clock, so a step never
    # stalls the arms the way an extra key in the arm track would
    FEET_FIELDS = ("right", "left", "right_h", "left_h", "root")
    feet_keys = fill_keys(move["feet"]) if move.get("feet") else None
    duration = float(keys[-1]["t"])
    n = int(round(duration * fps))
    times = [round(i / fps, 6) for i in range(n + 1)]
    J = {k: [] for k in ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")}
    tips, grips, residuals, roots = [], [], [], []
    twists = {"Right Arm": None, "Left Arm": None}
    # a COMBO move starts with the arm boxes facing where the previous move left them (`arm_facing_start`, written by
    # its generator from the last clip's `arm_facing_end`): each clip choosing its own spun a box 119-181 degrees at a
    # seam (the katana combo, 2026-10-18) - a flash when the game cross-fades the clips
    for arm, v in (move.get("arm_facing_start") or {}).items():
        if arm in twists and v is not None:
            twists[arm] = unit(np.asarray(v, dtype=float))
    arm_slide = float(move.get("arm_slide", 0.0))         # studs an arm may slide along itself to reach the hilt
    # the legs as the loved HQ R6 Combat pack does them (measured 2026-10-18): the pelvis sinks at most
    # `pelvis_drop_max` below its keyed height (loved 0.24-0.33) and a planted leg too short for its foot SLIDES along
    # itself up to `leg_slide` studs (loved p95 0.6-1.3) - instead of the whole body sinking a stud and more when the
    # hips turn over a split stance. Both unset = the old behaviour (the pelvis drops until a sole lands)
    leg_slide = float(move.get("leg_slide", 0.0))
    # `hip_offset` {"right": [x, y, z], "left": [...]} (torso frame, studs; needs leg_slide): where each leg's top sits
    ho_ed = (move.get("key_edits") or {}).get("hip_offset") or {}          # the owner's blocking sockets ride on top
    hip_offsets = {lg: np.asarray(v, dtype=float) + np.asarray(ho_ed.get(side, [0.0, 0.0, 0.0]), dtype=float)
                   for lg, side, v in (("Right Leg", "right", (move.get("hip_offset") or {}).get("right")),
                                       ("Left Leg", "left", (move.get("hip_offset") or {}).get("left"))) if v is not None}
    hip_offsets.update({lg: np.asarray(ho_ed[side], dtype=float) for lg, side in (("Right Leg", "right"), ("Left Leg", "left"))
                        if side in ho_ed and lg not in hip_offsets})
    leg_out = float(move.get("leg_slide_out", leg_slide))
    twist_follow = float(move.get("leg_twist_follow", 0.0))
    leg_in_max = float(move["leg_in_max"]) if move.get("leg_in_max") is not None else None   # the most a leg is pushed IN    # how far a leg may slide OUT of its hip (a gap) - in: leg_slide
    leg_cone = math.radians(float(move["leg_cone"])) if move.get("leg_cone") is not None else None
    twist_rate = move.get("arm_twist_rate")                 # degrees a frame an arm box may turn to face the hilt (unset: 30, a switch)
    drop_max = move.get("pelvis_drop_max")
    pelvis_lag = float(move.get("pelvis_lag", 0.04))       # seconds the sliding-leg pelvis trails its target (smooths it)
    pel_y = None
    floors_seen = []                                        # the raw body floor per frame (leg_in_max, pass 1)
    pushes_seen = []                                        # the grip push per frame (arm_clearance, pass 1)
    arm_clear = float(move["arm_clearance"]) if move.get("arm_clearance") is not None else None
    if arm_clear is None and move.get("arm_push_start") is not None:
        arm_clear = 1.0                 # no push of its own, but the last clip's push eases out (no jump at the seam)
    inertia = float(move.get("inertia", 0.0))               # seconds: the steel's own momentum (a one-pole lag on the
    G_f, d_f, t_prev = None, None, None                      # hilt and its direction - a whip becomes a sweep)
    for t in times:
        s = sample(keys, t)
        body_lift = 0.0
        if feet_keys:
            fs = sample(feet_keys, t, smooth_steps=True)
            s = dict(s, **{f: fs[f] for f in FEET_FIELDS})
            hs = fs["hip_shift"]
            s["pos"] = [float(s["pos"][j]) + float(hs[j]) for j in range(3)]
            s["_hip"] = [float(x) for x in hs]                 # (unarmed fists ride the hips as the grip does)
        sw = sample(keys, max(0.0, t - lag))                 # the steel trails the body
        if feet_keys:
            hs_w = sample(feet_keys, max(0.0, t - lag), smooth_steps=True)["hip_shift"]
            sw = dict(sw, grip=[float(sw["grip"][j]) + float(hs_w[j]) for j in range(3)])
        if inertia > 1e-6 and G_f is not None:
            dt = t - t_prev
            alpha = dt / (inertia + dt)
            sw = dict(sw)
            sw["grip"] = [G_f[j] + (float(sw["grip"][j]) - G_f[j]) * alpha for j in range(3)]
            sw["dir"] = list(slerp(d_f, sw["dir"], alpha))
        G_f, d_f, t_prev = [float(v) for v in sw["grip"]], list(sw["dir"]), t
        torso_m = euler((s["pitch"], s["yaw"], s["roll"]))
        torso_p = np.array(s["pos"], dtype=float)
        # legs first: the weight-bearing leg sets the pelvis height
        legs = {}
        with_body = s.get("legs") == "with_body"
        ya = math.radians(float(s["yaw"])) if with_body else 0.0
        turn_m = euler((0.0, float(s["yaw"]), 0.0)) if with_body else None
        for leg, fx, fh in (("Right Leg", s["right"], s["right_h"]), ("Left Leg", s["left"], s["left_h"])):
            planted = fh <= 1e-3
            x, z = fx[0], fx[2]
            if with_body:                            # the feet swing round WITH the body's turn (the loved R6 slashes:
                # the legs keep their place under the torso, the soles slide) - pitch / roll / crouch still solved
                dx, dz = x - s["pos"][0], z - s["pos"][2]
                x = s["pos"][0] + dx * math.cos(ya) + dz * math.sin(ya)
                z = s["pos"][2] - dx * math.sin(ya) + dz * math.cos(ya)
            legs[leg] = dict(xz=(x, z), h=fh, planted=planted)
        weight = s["weight"]
        carriers = [lg for lg in legs if legs[lg]["planted"] and (weight == "both" or weight == ("right" if lg == "Right Leg" else "left"))]
        if not carriers:
            carriers = [lg for lg in legs if legs[lg]["planted"]]
        if leg_slide > 0:
            # sliding legs reach their feet whatever the pelvis does: it follows the MEAN of the planted legs, which is
            # continuous - a carrier picked by the (stepwise) weight jumped the pelvis at every weight change
            carriers = [lg for lg in legs if legs[lg]["planted"]] or carriers
        # the pelvis: iterate the torso height so the carrier's sole lands on the floor
        for _ in range(3):
            demands = []
            for lg in carriers:
                _, sole, _ = leg_solve(lg, legs[lg]["xz"], 0.0, torso_m, torso_p, True, turn_m)
                demands.append(FLOOR_R6 - sole[1])
            if demands:
                if leg_slide > 0:
                    torso_p[1] += sum(demands) / len(demands)
                else:
                    torso_p[1] += max(demands) if weight == "both" else demands[0]
        if drop_max is not None:
            base_y, D = float(s["pos"][1]), max(1e-3, float(drop_max))
            dy = torso_p[1] - base_y
            if leg_slide > 0:
                # SOFT: the sink saturates smoothly at drop_max (a hard clamp held the pelvis, then let it jump 0.13
                # studs a frame when the hips turned past the stance), and the pelvis trails by `pelvis_lag` seconds
                # never ABOVE the keyed height: a crouch (pos y < 0) holds and the legs slide INTO the torso - the loved
                # HQ R6 legs (2026-10-18) crouch 0.3-0.6 with the legs 0.4-0.8 in; ours stood tall on legs slid OUT (stilts)
                dy = min(dy, 0.0)
                dy = -D * math.tanh(-dy / D) if dy < 0 else dy
                if leg_in_max is not None:
                    # the torso never PUSHES a planted leg shorter than its length - leg_in_max (the owner, 2026-10-18:
                    # 'the torso pushes on the legs where they look stupid like his a baby man' - a deep crouch slid the
                    # legs 1.2 studs into the torso): the crouch comes from the stance; too narrow a stance, the body rises
                    L_min = float(np.linalg.norm(SOLE["Right Leg"])) - leg_in_max
                    need = -1e9
                    for lg2 in legs:                   # planted, and a PASSING foot too: the hips rise over it, as a real
                        hip_off = torso_m @ HIP[lg2]   # walk vaults over the standing leg (a rigid leg passing under a low
                        hx, hz = torso_p[0] + hip_off[0], torso_p[2] + hip_off[2]      # hip dug 0.3 into the floor)
                        hd = math.hypot(legs[lg2]["xz"][0] - hx, legs[lg2]["xz"][1] - hz)
                        foot_y = FLOOR_R6 + legs[lg2]["h"]
                        need = max(need, foot_y + math.sqrt(max(0.0, L_min * L_min - hd * hd)) - hip_off[1])
                if pel_y is not None and pelvis_lag > 0:
                    dy = pel_y + (dy - pel_y) * (1.0 / fps) / (pelvis_lag + 1.0 / fps)
                pel_y = dy
                if leg_in_max is not None:
                    floors_seen.append(need)
                    floor_y = _floors[len(floors_seen) - 1] if _floors is not None else need
                    body_lift = max(0.0, floor_y - base_y - dy)       # the hands rise WITH the body (they stayed
                    dy = max(dy, floor_y - base_y)      # AFTER the lag: a late rise let a leg dig into the floor
                                                        # put and the arms jumped 20 deg as the shoulders rose)
                torso_p[1] = base_y + dy
            else:
                torso_p[1] = max(torso_p[1], base_y - D)
        leg_frames = {}
        for lg in legs:
            if s.get("legs") == "keyed":                            # the legs as the reference keyed them
                rot = s["right_rot"] if lg == "Right Leg" else s["left_rot"]
                off = s["right_off"] if lg == "Right Leg" else s["left_off"]
                leg_frames[lg] = frame_of(euler(tuple(rot)), tuple(off))
                continue
            R, sole, hip = leg_solve(lg, legs[lg]["xz"], legs[lg]["h"], torso_m, torso_p, legs[lg]["planted"], turn_m)
            h_off = hip_offsets.get(lg)
            if h_off is not None:
                # the OWNER's leg tops (2026-10-18, placed on his rig in KatanaFeetEdit.blend): the hip socket each leg
                # aims from, moved in the torso frame - the feet stay put, the pelvis height is not touched
                hip = hip + torso_m @ h_off
            lift = 0.0
            want = FLOOR_R6 + legs[lg]["h"]                       # a straight leg never reaches below its target
            if leg_slide > 0:                                   # planted OR in the air: one rule (a touchdown switched rules and popped the legs)
                # ONE rule for a planted leg (the R6 leg): it points AT its foot and slides along itself - out to reach
                # it, in when it is close - so nothing switches between frames (a lift-or-slide switch popped the legs
                # 18-20 degrees in a frame: the owner's 'quick flashes', 2026-10-18)
                target = np.array([legs[lg]["xz"][0], want, legs[lg]["xz"][1]])
                v = target - hip
                if leg_cone is not None:
                    # the leg stays UNDER the torso (the owner, 2026-10-18: 'the legs are like weird in some certain
                    # poses' - hips turned 90 deg over planted feet splayed a leg 64 deg back, flat along the floor):
                    # past `leg_cone` degrees from its rest line the foot gives way (it slides / pivots) to the cone's
                    # edge, at the target's height
                    rest = unit(torso_m @ SOLE[lg])
                    u = unit(v)
                    ang = math.acos(max(-1.0, min(1.0, float(u @ rest))))
                    if ang > leg_cone:
                        u = rot_axis(unit(np.cross(rest, u)), leg_cone) @ rest
                        v = u * ((target[1] - hip[1]) / u[1] if u[1] < -1e-3 else float(np.linalg.norm(v)))
                # the leg box TURNS with the hips by `leg_twist_follow` (a leg facing the world under a turned torso twisted
                # +-57 deg against it - knees and feet pivot with the hips); legs 'with_body' turn all the way
                tw = turn_m if turn_m is not None else (euler((0.0, twist_follow * float(s["yaw"]), 0.0)) if twist_follow else None)
                Rw = arc(tw @ SOLE[lg], v) @ tw if tw is not None else arc(SOLE[lg], v)
                ext = max(-(leg_in_max if leg_in_max is not None else leg_slide),
                          min(leg_out, float(np.linalg.norm(v)) - float(np.linalg.norm(SOLE[lg]))))
                slide_v = torso_m.T @ (unit(v) * ext) + (h_off if h_off is not None else 0.0)
                leg_frames[lg] = frame_of(torso_m.T @ Rw, tuple(float(x) for x in slide_v))
                continue
            if sole[1] < want - 1e-4:
                lift = (want - sole[1]) / max(0.5, float((torso_m @ np.array([0, 1, 0]))[1]))
            leg_frames[lg] = frame_of(R, (0.0, lift, 0.0))
        arms = {}
        if s.get("arms") == "keyed":
            # the arms as the reference keyed them; the hilt sits in the right hand, the blade along the arm turned
            # by sword.grip_pitch (0 = out of the fist, perpendicular to the arm; 90 = along it)
            grip_local = unit(np.array([0.0, -math.sin(grip_pitch), -math.cos(grip_pitch)]))
            ra_m = euler(tuple(s["right_arm_rot"]))
            ra_p = np.asarray(s["right_arm_off"], dtype=float)
            R_world = torso_m @ ra_m
            hand = torso_p + torso_m @ (SHOULDER["Right Arm"] + ra_p) + R_world @ HAND["Right Arm"]
            d = unit(R_world @ grip_local)
            G = hand - d * spacing / 2
            residuals.append(0.0)
            grips.append(G)
            tips.append(G + d * (blade - spacing / 2))
            arms["Right Arm"] = frame_of(ra_m, tuple(ra_p))
            arms["Left Arm"] = frame_of(euler(tuple(s["left_arm_rot"])), tuple(s["left_arm_off"]))
        elif s.get("arms") == "hands":
            # UNARMED: each arm reaches its own hand target (the hilt's two-hand solve, one hand at a time: the frame-
            # built rotation + the slide along the arm, the loved R6 way of reaching); arm_clearance pushes both
            # targets forward until the arms pass in front of the body (as it pushes the grip)
            if move.get("hands_frame") == "torso":
                # the fists keyed IN THE TORSO's frame (a guard is where the hands sit on the body): they ride the
                # solved torso - its turn, lean, sink and hip shift - with no helper placing them (IronMountain, 2026-10-25)
                targets = {"Right Arm": torso_p + torso_m @ np.asarray(s["rhand"], dtype=float),
                           "Left Arm": torso_p + torso_m @ np.asarray(s["lhand"], dtype=float)}
            else:
                lift = np.array([0.0, body_lift, 0.0]) + np.asarray(s.get("_hip", (0.0, 0.0, 0.0)), dtype=float)
                targets = {"Right Arm": np.asarray(s["rhand"], dtype=float) + lift,
                           "Left Arm": np.asarray(s["lhand"], dtype=float) + lift}
            fist = torso_m @ np.array([0.0, 1.0, 0.0])          # (the arm box's facing: no blade to face)
            fwd = torso_m @ np.array([0.0, 0.0, -1.0])
            if arm_clear is not None and _pushes is not None:
                cands = [np.asarray(_pushes[len(pushes_seen)], dtype=float)]
            elif arm_clear is not None:
                cands = sorted([np.zeros(3)] + [fwd * (0.1 * it) for it in range(1, 13)],
                               key=lambda v: float(np.linalg.norm(v)))
            else:
                cands = [np.zeros(3)]
            best, trial, need_push = None, {}, cands[0]
            for pv in cands:
                trial = {}
                for arm, tgt in targets.items():
                    R, facing = arm_rotation(arm, tgt + pv, torso_m, torso_p, fist, twists[arm], twist_rate)
                    slid = (0.0, 0.0, 0.0)
                    if arm_slide > 0:
                        v = tgt + pv - (torso_p + torso_m @ SHOULDER[arm])
                        ext = max(-arm_slide, min(arm_slide, float(np.linalg.norm(v)) - REACH))
                        slid = tuple(float(x) for x in torso_m.T @ (unit(v) * ext))
                    trial[arm] = (R, facing, slid)
                need_push = pv
                if arm_clear is None or _pushes is not None:
                    break
                sink = max(arm_in_body(a, trial[a][0], trial[a][2]) for a in trial)
                if sink <= arm_clear:
                    break
                if best is None or sink < best[0] - 1e-9:
                    best = (sink, pv, trial)
            else:
                if best is not None:
                    _, need_push, trial = best
            if arm_clear is not None:
                pushes_seen.append([float(x) for x in need_push])
            residuals.append(0.0)
            lead = "Left Arm" if str(move.get("strike_hand", "right")).lower().startswith("l") else "Right Arm"
            other = "Right Arm" if lead == "Left Arm" else "Left Arm"
            grips.append(targets[other] + need_push)             # (no blade: the striking fist is the "tip" the Hit
            tips.append(targets[lead] + need_push)               #  is timed on, the off hand the "grip")
            for arm, (R, facing, slid) in trial.items():
                twists[arm] = facing
                arms[arm] = frame_of(R, slid)
        elif s.get("arms") == "one_hand":
            # ONE-HANDED sword (2026-10-31, the owner's Swift ask: twirls, reverse-grip flicks, the off arm flung
            # wide - character-action Dance Macabre frame-stepped): the right hand alone on the hilt, where the two-hand solve puts
            # it (so the tip is unchanged), pulled onto the arm's reach; the blade turns freely about the fist (the
            # Handle joint carries it in game); the off hand reaches `lhand`, keyed IN THE TORSO's frame like a guard
            grip_in = [sw["grip"][0], sw["grip"][1] + body_lift, sw["grip"][2]] if body_lift else sw["grip"]
            d = unit(np.asarray(sw["dir"], dtype=float))
            piv = torso_p + torso_m @ SHOULDER["Right Arm"]
            hand = np.asarray(grip_in, dtype=float) + d * spacing / 2
            v = hand - piv
            dist = float(np.linalg.norm(v))
            lo, hi = max(0.0, REACH - arm_slide), REACH + arm_slide
            res = max(0.0, dist - hi) + max(0.0, lo - dist)
            if res > 0:
                hand = piv + unit(v) * min(max(dist, lo), hi)
            G = hand - d * spacing / 2
            # the off arm faces where its REST facing goes by the shortest turn onto its reach (no roll about the
            # shoulder-hand line: R6's shoulder pivot is off the arm's centre line, so a roll swings the box into the chest)
            l_tgt = torso_p + torso_m @ np.asarray(s["lhand"], dtype=float)
            h0 = unit(HAND["Left Arm"])
            x0 = unit(np.array([1.0, 0.0, 0.0]) - h0[0] * h0)
            l_face = arc(torso_m @ h0, l_tgt - (torso_p + torso_m @ SHOULDER["Left Arm"])) @ (torso_m @ x0)
            r0 = unit(HAND["Right Arm"])
            rx0 = unit(np.array([1.0, 0.0, 0.0]) - r0[0] * r0)
            r_face = arc(torso_m @ r0, hand - piv) @ (torso_m @ rx0)
            trial = {"Right Arm": (hand, r_face), "Left Arm": (l_tgt, l_face)}
            for arm, (tgt, face) in trial.items():
                # (exactly that facing each frame: the half-turn carry-over would pick the twin box inside the chest)
                R, facing = arm_rotation(arm, tgt, torso_m, torso_p, face, None, None)
                slid = (0.0, 0.0, 0.0)
                if arm_slide > 0:
                    w = tgt - (torso_p + torso_m @ SHOULDER[arm])
                    ext = max(-arm_slide, min(arm_slide, float(np.linalg.norm(w)) - REACH))
                    slid = tuple(float(x) for x in torso_m.T @ (unit(w) * ext))
                twists[arm] = facing
                arms[arm] = frame_of(R, slid)
            if arm_clear is not None:
                pushes_seen.append([0.0, 0.0, 0.0])
            residuals.append(res)
            grips.append(G)
            tips.append(G + d * (blade - spacing / 2))
        else:
            # the sword: both hands on the hilt
            grip_in = [sw["grip"][0], sw["grip"][1] + body_lift, sw["grip"][2]] if body_lift else sw["grip"]
            d = unit(np.asarray(sw["dir"], dtype=float))
            # two ways out: FORWARD (clears an arm crossing the chest) and OUTWARD toward the hilt (clears a hilt beside or
            # behind the hip - the underhip's wind-up, the flash step's gather); per frame the smaller push that clears
            up_w = torso_m @ np.array([0.0, 1.0, 0.0])
            out_v = np.asarray(grip_in, dtype=float) - torso_p
            out_v = out_v - (out_v @ up_w) * up_w
            ways = [torso_m @ np.array([0.0, 0.0, -1.0])]       # forward only: per-frame direction choices blurred into
            #                                                     pushes that cleared nothing (tried 2026-10-18)
            # ARMS CLEAR OF THE BODY (the owner, 2026-10-18: "even the arms ... started to look bad ... noticable"):
            # the left arm reaching across to the hilt sank 35-66 % of itself into the chest (loved R6 slashes <= 22 %);
            # past `arm_clearance` the grip is pushed FORWARD, away from the chest, until the arms pass in front -
            # searched in pass 1, the push smoothed and applied in pass 2 (no jump)
            if arm_clear is not None and _pushes is not None:
                cands = [np.asarray(_pushes[len(pushes_seen)], dtype=float)]          # pass 2: the smoothed push
            elif arm_clear is not None:
                cands = [np.zeros(3)] + [w * (0.1 * it) for it in range(1, 13) for w in ways]   # nearest first
                cands.sort(key=lambda v: float(np.linalg.norm(v)))
            else:
                cands = [np.zeros(3)]
            need_push = cands[0]
            trial = {}
            best = None                                      # (sink, push, trial): kept when no push clears
            for pv in cands:
                G, res = solve_grip([grip_in[j] + pv[j] for j in range(3)], sw["dir"], torso_m, torso_p, spacing,
                                    arm_slide)
                trial = {}
                for arm, off in (("Right Arm", +spacing / 2), ("Left Arm", -spacing / 2)):
                    R, facing = arm_rotation(arm, G + off * d, torso_m, torso_p, d, twists[arm], twist_rate)
                    slid = (0.0, 0.0, 0.0)
                    if arm_slide > 0:                            # the arm slides along itself: hand AT the hilt
                        v = G + off * d - (torso_p + torso_m @ SHOULDER[arm])
                        ext = max(-arm_slide, min(arm_slide, float(np.linalg.norm(v)) - REACH))
                        slid = tuple(float(x) for x in torso_m.T @ (unit(v) * ext))
                    trial[arm] = (R, facing, slid)
                need_push = pv
                if arm_clear is None or _pushes is not None:
                    break
                sink = max(arm_in_body(a, trial[a][0], trial[a][2]) for a in trial)
                if sink <= arm_clear:
                    break
                if best is None or sink < best[0] - 1e-9:
                    best = (sink, pv, trial)
            else:
                if best is not None:                         # nothing cleared: the push that sank the arms least
                    _, need_push, trial = best
            if arm_clear is not None:
                pushes_seen.append([float(x) for x in need_push])
            residuals.append(res)
            grips.append(G)
            tips.append(G + d * (blade - spacing / 2))
            for arm, (R, facing, slid) in trial.items():
                twists[arm] = facing
                arms[arm] = frame_of(R, slid)
        head_m = euler((s["look_pitch"] - 0.5 * s["pitch"], s["look_yaw"] - 0.6 * s["yaw"], -0.5 * s["roll"]))
        roots.append([0.0, 0.0, 0.0, 1.0, round(float(s["root"][0]), 5), 0.0, round(float(s["root"][2]), 5)])
        J["Torso"].append(frame_of(torso_m, torso_p))
        J["Head"].append(frame_of(head_m))
        J["Right Arm"].append(arms["Right Arm"])
        J["Left Arm"].append(arms["Left Arm"])
        J["Right Leg"].append(leg_frames["Right Leg"])
        J["Left Leg"].append(leg_frames["Left Leg"])
    apply_arm_poses(keys, times, J, tips, grips)
    apply_overlap(move, J, tips, grips, fps)
    held = apply_moving_holds(move, J, tips, grips, fps)        # AAA gaps v2 B2: holds that never die
    # events: the Hit one frame after the blade tip's fastest frame, unless the author placed it
    events = [dict(e) for e in move.get("events") or []]      # copies: apply_steps moves a Hit, never the move's
    hit_inferred = False
    speeds = [float(np.linalg.norm(tips[i + 1] - tips[i])) * fps for i in range(len(tips) - 1)]
    peak_i = int(np.argmax(speeds)) if speeds else 0
    if not any(e.get("name") == "Hit" for e in events) and speeds and max(speeds) > 1.0:
        hit_i = min(peak_i + 1, n)
        want = move.get("contact_dir")
        if want is not None:
            # CONTACT: the blade meets the target line a frame or three after the tip's speed peak (it is still turning
            # in at the peak - the tip then moves FORWARD, not across); within the engine's 0..3 frames, the frame whose
            # blade points nearest `contact_dir` (character space)
            wv = unit(np.asarray(want, dtype=float))
            cand = range(peak_i, min(peak_i + 3, n) + 1)
            hit_i = max(cand, key=lambda i: float(unit(tips[i] - grips[i]) @ wv))
        events.append({"name": "Hit", "t": round(times[hit_i], 4)})
        hit_inferred = [events[-1]["t"]]   # (placed by the build at a speed peak: kit/anim/contact.py holds it to the geometry)
    sword_out = {"length": blade, "grip": spacing, "tip": [[round(float(x), 4) for x in p] for p in tips],
                 "grip_path": [[round(float(x), 4) for x in p] for p in grips],
                 "edge": [[round(float(x), 4) for x in e] for e in blade_edges(tips, grips, fps, move.get("edge_start"),
                                                                               move.get("edge_end_at"))]}
    if sword.get("kind"):
        sword_out["kind"] = sword["kind"]          # a katana renders as a katana (it rendered as a greatsword)
    # the game joint's origin at the right hand, not the hands' midpoint (opt-in; kit/lib/anim.luau exports the
    # Handle pose from it, src/kit/AnimGrip.luau takes the half spacing in its C1): fades never pull the hand off
    if sword.get("grip_origin") == "hand":     # (the move's "sword": {"grip_origin": "hand"}; the contract reads it)
        sword_out["grip_origin"] = "hand"
    stepped = apply_steps(move, times, J, sword_out, roots, events, fps)
    clip = {"schema": 1, "name": move["name"], "rig": "R6", "fps": fps, "duration": times[-1], "loop": bool(move.get("loop", False)),
            "priority": move.get("priority", "Action"), "joints": {k: {"frames": v} for k, v in J.items()},
            "times": times, "events": events, "beats": move.get("beats"), "feel": resolve_feel(move.get("feel")), "gate": move.get("gate"),
            "sword": sword_out}
    if unarmed:
        clip.pop("sword", None)                                 # (no blade: no sword, no Handle track)
    if hit_inferred:
        clip["hit_inferred"] = [e["t"] for e in events if e.get("name") == "Hit"][:1]     # (apply_steps may have moved it)
    for said in ("target", "contact", "hands", "slides", "on_blade"):              # (where its target stands; the contacts it means:
        if move.get(said) is not None:                          # kit/anim/contact.py, kit/anim/collide.py)
            clip[said] = move[said]
    if any(abs(r[4]) > 1e-4 or abs(r[6]) > 1e-4 for r in roots):
        clip["root"] = roots
    if move.get("camera"):
        clip["camera"] = camera_keys(move["camera"])   # AAA gaps v2 D9: the finisher's own shot (Anim plays it)
    if move.get("additive"):
        clip["additive"] = move["additive"]        # AAA gaps v2 D3: also layered over any pose (Anim.additive)
    if move.get("upper") is not None:
        clip["upper"] = move["upper"]              # also built legs-free, for the game to play over the walk (kit anim)
    if move.get("match") is not None:
        clip["match"] = move["match"]              # the tables the game enters it by (kit/anim/match_tables.py `for`)
    if stepped:
        clip["stepped"] = stepped
    if held:
        clip["moving_holds"] = held
    add_markers(clip, move, speeds, fps)                         # AAA gaps v2 D11 / C5 / D9
    if move.get("mask") == "upper":
        # AN UPPER-BODY MOVE (AAA gaps v2 D4): the legs are not keyed, so in game the locomotion clip keeps driving
        # them under it (a KeyframeSequence only overrides the joints it keys) - attack while running
        for leg in ("Right Leg", "Left Leg"):
            clip["joints"].pop(leg, None)
        clip["mask"] = "upper"
    if arm_clear is not None and _pushes is None and pushes_seen:
        # pass 2: the push vectors smoothed - held at the largest nearby push (by length) then blurred - so the hands
        # never jump where the push switches on
        r = max(1, int(round(0.1 * fps)))
        P_ = np.asarray(pushes_seen, dtype=float)
        n_p = len(P_)
        dil = np.array([P_[max(0, i - r):min(n_p, i + r + 1)][np.argmax(np.linalg.norm(P_[max(0, i - r):min(n_p, i + r + 1)], axis=1))]
                        for i in range(n_p)])
        sm = np.array([dil[max(0, i - r):min(n_p, i + r + 1)].mean(axis=0) for i in range(n_p)])
        if move.get("arm_push_start") is not None:
            # a COMBO move starts on the push the previous clip ended with (`arm_push_end`) and eases into its own over
            # 0.15 s - each clip choosing its own spun an arm 30-42 degrees a frame at the seam
            p0 = np.asarray(move["arm_push_start"], dtype=float)
            n_b = max(1, int(round(0.15 * fps)))
            for i in range(min(n_b, n_p)):
                w = smoothstep(i / n_b)
                sm[i] = (1.0 - w) * p0 + w * sm[i]
        return generate(move, _floors, sm.tolist())
    if leg_in_max is not None and _floors is None and floors_seen:
        # pass 2 with the body floor LOOKED AHEAD: a max over +-r frames then a box blur of the same width (never below
        # the raw floor) - the body starts rising before a passing leg needs it, no snap where the floor switched on
        r = max(1, int(round(0.08 * fps)))
        n_f = len(floors_seen)
        dil = [max(floors_seen[max(0, i - r):min(n_f, i + r + 1)]) for i in range(n_f)]
        smooth = [sum(dil[max(0, i - r):min(n_f, i + r + 1)]) / len(dil[max(0, i - r):min(n_f, i + r + 1)]) for i in range(n_f)]
        return generate(move, [max(a, b) for a, b in zip(smooth, floors_seen)], _pushes)
    return clip, {"tip_peak": round(max(speeds), 2) if speeds else 0.0, "tip_peak_t": round(times[peak_i], 3) if speeds else 0.0,
                  "grip_moved": round(float(max(residuals)), 3),
                  "arm_facing_end": {k: ([round(float(x), 6) for x in v] if v is not None else None) for k, v in twists.items()},
                  "arm_push_end": [round(float(x), 6) for x in pushes_seen[-1]] if pushes_seen else None,
                  "edge_end": sword_out["edge"][-1] if sword_out["edge"] else None}


def arm_sink_report(clip, rig, limit):
    """the finished clip's arms against the move's `arm_clearance` (the owner, 2026-10-25: KatanaKaeshi's 'hands are kind
    of messed up' - its follow-through sank both arms 23-27 % into the chest while the solver, finding no forward push
    that cleared, silently kept its best try): the share of each arm inside the torso or the head per frame (the
    solver's own boxes, in the torso's frame) -> None when every frame is within `limit`, else
    {"worst", "from", "to"} (seconds) of the frames past it"""
    pts = np.array([[x, y, z, 1.0] for x in (-0.4, 0.0, 0.4) for y in np.linspace(-0.95, 0.95, 9) for z in (-0.4, 0.0, 0.4)])
    over = []
    for i, w in enumerate(C.world_frames(clip, rig)):
        inv = np.linalg.inv(w["Torso"])
        sink = 0.0
        for arm in ("Right Arm", "Left Arm"):
            p = (inv @ w[arm] @ pts.T).T[:, :3]
            torso = np.all(np.abs(p) < np.array([0.95, 0.95, 0.45]), axis=1)
            head = np.all(np.abs(p - np.array([0.0, 1.5, 0.0])) < 0.55, axis=1)
            sink = max(sink, float(np.mean(torso | head)))
        if sink > limit + 1e-6:
            over.append((float(clip["times"][i]), sink))
    if not over:
        return None
    return {"worst": round(max(s for _, s in over), 3), "from": round(over[0][0], 3), "to": round(over[-1][0], 3)}


def sha256_of(path):
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def sha256_of_many(paths):
    import hashlib
    h = hashlib.sha256()
    for path in paths:
        with open(path, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def main(argv):
    if not argv:
        return emit("fail", "strike: needs <Name>.move.json [--out <clip.json>]", "lune run kit anim new GreatswordHeavy --move")
    path = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    with open(path, encoding="utf-8") as fh:
        move = json.load(fh)
    if not move.get("keys"):
        return emit("fail", f"strike: {path} has no keys", "write keys: grip, dir, yaw, pitch, pos, right, left, weight, look_yaw, ease, overshoot")
    move["name"] = move.get("name") or os.path.basename(path).split(".")[0]
    try:
        clip, info = generate(move)
    except ValueError as e:                                  # (a move that cannot be made is a NAMED failure, not a traceback)
        return emit("fail", f"strike {move['name']}: {e}", f"fix the move ({path})")
    clip["source"] = {"kind": "move", "file": path, "sha256": sha256_of(path),
                      "tool_sha256": sha256_of_many([__file__, C.__file__]), "rig_sha256": sha256_of(C.rig_path("r6"))}
    rig = C.load_rig("r6")
    # the sword as its own joint (kit/anim/grip.py, board m39b): the Handle Motor6D's track, so the game's blade follows
    # this clip's own blade path instead of the welded fist
    import grip as GR
    GR.add_grip(clip, rig)
    problems = C.metrics(clip, rig, move.get("gate"))["problems"]
    if problems:
        return emit("fail", f"strike {move['name']}: {problems[0]}", f"adjust the keys in {path} (feet that must stay put, a snap between keys), then: lune run kit anim {move['name']}",
                    problems=problems, **info)
    out = out or os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{move['name']}.clip.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    sink = arm_sink_report(clip, rig, float(move["arm_clearance"])) if move.get("arm_clearance") is not None else None
    warn = (f"; WARNING the arms sink {round(sink['worst'] * 100)} % into the body at {sink['from']}-{sink['to']} s "
            f"(arm_clearance {move['arm_clearance']}): move those keys' grip FORWARD, in front of the body") if sink else ""
    return emit("pass", f"strike {move['name']}: {len(clip['times'])} frames, {'the striking fist' if move.get('unarmed') else 'blade tip'} peaks {info['tip_peak']} studs/s at {info['tip_peak_t']} s"
                + (f", grip moved {info['grip_moved']} to be reachable" if info["grip_moved"] > 0.02 else "") + f" -> {out}" + warn,
                (f"move the grip of the keys at {sink['from']}-{sink['to']} s forward in {path}, then: lune run kit anim {move['name']}"
                 if sink else f"lune run kit anim look {move['name']} --rig R6 — LOOK: does the weight read?"),
                clip=out, arm_sink=sink, **info)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
