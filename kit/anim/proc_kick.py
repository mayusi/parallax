"""proc_kick.py — the KICK builder for a move dossier (moved out of diagnostics/proc_roundhouse.py, 2026-10-16; mission
04-anim 5.4). A dossier's build keys (torso yaw / lean / pitch / dip / toe, the kicking leg's abduction + swing, the
support leg's stance swing, the arms, the head) become poses, the spring engine bakes dense 60 fps curves, then:
  pivot_pass  the support leg keeps its world-upright line while the hips turn: its foot turns WITH the hips about its
              sole (heel to the target) and the torso orbits the planted sole - the foot never slides
  pin_feet    the kicking foot pinned where it stands on the floor, released lift-first
  Hit         CONTACT (the hips reach the contact key's turn), at most 3 frames after the kicking leg's speed peak -
              the foot is fastest BEFORE it lands (impact speed 41-54 % of the peak; the roundhouse dossier, plos2017)
    from proc_kick import build;  c, b = build(dossier, persona=None, keys=None, follow=None)"""
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
FOLLOW = {"Torso": 0.25, "Head": 0.45, "Right Arm": 0.6, "Left Arm": 0.55, "Right Leg": 0.4, "Left Leg": 0.4}


PHASE_OF = {"guard": "rest", "settle": "rest", "wind": "windup", "wind_hold": "windup", "toe_off": ("windup", "strike", 0.5),
            "contact": "strike", "through": "strike", "through_hold": "strike", "recoil": "after", "land": "rest",
            "step": "after"}   # the recovery step back to the guard (footage2026: 5 of 6 kicks land FORWARD, switched)
_VOCAB = None


def vocab_slides():
    """the loved R6 leg-strike clips' median slide per role and phase (kit/anim/r6_vocab.py; statistics, not poses):
    legs slide UP + FORWARD (the bent knee R6 has no joint for), arms slide DOWN out of the shoulder"""
    global _VOCAB
    if _VOCAB is None:
        import json
        p = os.path.join("assets", "animations", "calibration", "r6_vocab.json")
        _VOCAB = json.load(open(p, encoding="utf-8")).get("slides") if os.path.exists(p) else None
    return _VOCAB


def peak_scale(role):
    """the phase medians are TYPICAL slides; loved clips PEAK higher. Scale a role so its largest phase slide reaches the
    loved clips' median peak (slide_p95 p50 of the same calibration): legs ~1.2 studs, arms ~0.9"""
    import json
    p = os.path.join("assets", "animations", "calibration", "r6_vocab.json")
    d = json.load(open(p, encoding="utf-8"))
    def one(r):
        rk = {"kick_leg": "kick_leg", "support_leg": "support_leg", "kick_side_arm": "Right Arm", "other_arm": "Left Arm"}[r]
        return d["roles"][rk]["slide_p95"]["p50"] / max(max(np.linalg.norm(v) for v in d["slides"][r].values()), 1e-6)
    if role in ("kick_leg", "support_leg"):                  # ONE scale for both legs: standing, they bend alike and
        return 0.5 * (one("kick_leg") + one("support_leg"))  # both soles stay on the floor
    return one(role)


GROUNDED = {"guard", "wind", "wind_hold", "land", "settle"}
# whip targets (torso frame, a RIGHT-leg kick; x out for the kick-side arm, -x out for the other arm)
WHIPS = {"down_back": (0.3, -0.7, 0.6), "across": (-0.7, -0.1, -0.7), "up": (0.3, 0.9, -0.3), "out": (-1.0, 0.0, -0.2)}       # both feet on the floor at these keys


def slide_of(k, role, b):
    """a key's slide for a role (torso frame, studs): its explicit 'slides' entry, else the vocabulary for its phase
    (scaled by the build's slide_scale), else none. x is mirrored for a LEFT-leg kick"""
    side = 1.0 if b["kick_leg"].startswith("Right") else -1.0
    if role == "kick_leg" and k.get("name") in GROUNDED and not (isinstance(k.get("slides"), dict) and role in k["slides"]):
        # a STANDING leg bends like a standing leg: before toe-off the kicking leg takes the support leg's slide (the
        # loved 'kick leg wind-up' slide is 8 frames before ITS peak - already in the air; on a planted foot it lifted
        # the sole 0.4 studs and the foot hovered)
        role = "support_leg"
    if isinstance(k.get("slides"), dict) and role in k["slides"]:
        v = np.asarray(k["slides"][role], float)
    else:
        V = vocab_slides() if b.get("slides") == "r6_vocab" else None
        ph = k.get("phase") or PHASE_OF.get(k.get("name", ""), None)
        if not V or not ph:
            return np.zeros(3)
        if isinstance(ph, (tuple, list)):                    # between two phases (toe-off: the wind-up turning into the strike)
            a, z, u = ph
            v = (1 - u) * np.asarray(V[role][a], float) + u * np.asarray(V[role][z], float)
        elif ph in V.get(role, {}):
            v = np.asarray(V[role][ph], float)
        else:
            return np.zeros(3)
        v = v * peak_scale(role) * float(k.get("slide_scale", b.get("slide_scale", 1.0)))
    return v * np.array([side, 1.0, 1.0])


def slide_ranges():
    """the loved clips' limb-slide ranges (statistics; kimodo_fold measured them, stored in the tracked calibration
    r6_vocab.json so a clean checkout has them) - the IK pins stay inside them"""
    import json
    p = os.path.join("assets", "animations", "calibration", "r6_vocab.json")
    if os.path.exists(p):
        sr = json.load(open(p, encoding="utf-8")).get("slide_ranges")
        if sr:
            return {leg: (np.asarray(sr[leg][0], float), np.asarray(sr[leg][1], float)) for leg in ("Right Leg", "Left Leg")}
    import kimodo_fold as K
    rng = K.loved_slide_ranges()
    return {leg: (np.asarray(rng[leg][0]), np.asarray(rng[leg][1])) for leg in ("Right Leg", "Left Leg")}


def key_pose(k, b):
    K, S = b["kick_leg"], b["support_leg"]
    side = 1.0 if K.startswith("Right") else -1.0
    p = DR.rest()
    p = DR.turn(p, "Torso", [-k.get("pitch", 0.0) * D2R, 0.0, 0.0])          # acting: hunch forward (+) / chest out (-)
    p = DR.turn(p, "Torso", [0.0, 0.0, side * k["lean"] * D2R])              # roll AWAY from the kick (local)
    p = DR.turn(p, "Torso", [0.0, side * k["yaw"] * D2R, 0.0])               # then the hip turn (world +Y)
    p["Torso"][5] -= k["dip"]
    abd, swing = k["kick"]
    p = DR.turn(p, K, [0.0, 0.0, side * abd * D2R])                            # out to the side, in the torso frame
    p = DR.turn(p, K, [swing * D2R, 0.0, 0.0])                                 # + forward / - back
    p = DR.turn(p, S, [k["support"] * D2R, 0.0, 0.0])
    rear, lead = ("Right", "Left") if side > 0 else ("Left", "Right")
    arms = ((f"{rear} Arm", k["rear_arm"]), (f"{lead} Arm", k["lead_arm"]))
    if k.get("arms") == "vocab":                             # both arms through the loved phase directions
        ph = k.get("phase") or PHASE_OF.get(k.get("name", ""), "rest")
        wk, wo = k.get("whip_kick_arm"), k.get("whip_other_arm", ["out", 45])
        hb = k.get("arm_habit")
        arms = ((f"{rear} Arm", {"vocab": "kick_side_arm", "phase": ph, "whip": wk, "habit": hb}),
                (f"{lead} Arm", {"vocab": "other_arm", "phase": ph, "whip": wo, "habit": hb}))
    for arm, spec in arms:
        p = DR.aim(p, arm, arm_direction(p, K, arm, spec))
    # the R6 VOCABULARY: the kicking leg and the arms SLIDE (the knee / elbow R6 does not have)
    for part, role in ((K, "kick_leg"), (f"{rear} Arm", "kick_side_arm"), (f"{lead} Arm", "other_arm")):
        p[part][4:7] = list(map(float, slide_of(k, role, b)))
    if isinstance(k.get("prior"), dict):
        # the UPPER BODY from the combat pose prior (loved R6 combat poses as a density, never a lookup): the designed
        # torso kept, head + arms = the prior's rank-th mode given that torso (round 0's hand-set arms were a clump)
        import pose_prior as PP
        p, _ = PP.nudge(p, group="combat", rank=int(k["prior"].get("rank", 0)), tau=float(k["prior"].get("tau", 0.25)),
                        seed=int(k["prior"].get("seed", 0)))
    if k.get("head_target"):
        qt, pt = np.array(p["Torso"][:4]), np.array(p["Torso"][4:7])
        tgt = P.q_rot(P.q_inv(qt), np.asarray(b["target"], float) - pt)
        p = DR.look_at(p, tgt, 0.9)
    hp, hy, hr = k.get("head", (0.0, 0.0, 0.0))                                # acting: chin down +, look left +, tilt +
    if hp or hy or hr:
        p = DR.turn(p, "Head", [-hp * D2R, hy * D2R, hr * D2R])
    return p


def arm_direction(p, kick_leg, arm, spec):
    """an arm key: [forward_deg, across_deg] (proc_director.arm_dir) or a POSE CHOICE relative to the kicking leg
    (owner 2026-10-16: round 0's extremes were a clump - arms folded over the torso, no line through the pose):
      {"along": deg}    the arm PARALLEL to the kicking leg, lifted `deg` (the stylized round kick: the front arm
                        extends along the leg - one long line through the pose; slynyrd pixelblog 53)
      {"against": deg}  the arm pointing OPPOSITE the kicking leg, dropped `deg` (the counter-line)"""
    if isinstance(spec, dict) and "vocab" in spec:
        # where loved R6 leg-strike clips point this arm in this phase (r6_vocab arm_aim; the mean over every clip)
        import json
        full = json.load(open(os.path.join("assets", "animations", "calibration", "r6_vocab.json"), encoding="utf-8"))
        ph = spec.get("phase")
        role = spec["vocab"]
        if spec.get("habit") is not None:
            # an ARM HABIT: a k-means centroid of loved clips' whole arm choreographies (the plain mean was a T-pose
            # nobody makes); used as a coherent set through the phases
            H = full["arm_habits"]["habits"][int(spec["habit"])][role]
            cal = {role: {x: {"dir": H[x]} for x in H}}
        else:
            cal = full["arm_aim"]
        if isinstance(ph, (tuple, list)):
            a, z, u = ph
            d = (1 - u) * np.asarray(cal[role][a]["dir"]) + u * np.asarray(cal[role][z]["dir"])
        else:
            d = np.asarray(cal[role][ph or "rest"]["dir"], float)
        # the MEAN of many clips' arms swings less than any one loved clip does (diverse directions average toward
        # the middle): swing each phase direction away from rest by the gain that brings the arm's range toward the
        # loved per-clip median rot_range (capped 1.6x)
        rest = np.asarray(cal[role]["rest"]["dir"], float)
        rest = rest / np.linalg.norm(rest)
        span = max(math.degrees(math.acos(float(np.clip(np.asarray(cal[role][x]["dir"]) @ rest / np.linalg.norm(cal[role][x]["dir"]), -1, 1)))) for x in cal[role])
        rk = "Right Arm" if role == "kick_side_arm" else "Left Arm"
        want = full["roles"][rk]["rot_range"]["p50"]
        # a habit is ALREADY one coherent choreography (no gain); the plain mean is pulled to the middle (gain <= 1.6)
        gain = 1.0 if spec.get("habit") is not None else float(np.clip(want / max(span, 1e-6), 1.0, 1.6))
        d = d / np.linalg.norm(d)
        ax = np.cross(rest, d)
        ang = math.atan2(np.linalg.norm(ax), float(rest @ d))
        if np.linalg.norm(ax) > 1e-9:
            d = P.q_rot(P.q_exp(ax / np.linalg.norm(ax) * ang * gain), rest)
        # THE WHIP (loved leg strikes: each arm swings ~45 deg in the 10 frames around the strike at ~1,200-1,500
        # deg/s; the kick-side arm's direction is the animator's choice, the other arm flings OUT): at the strike / after
        # phases the arm is turned `deg` toward its whip target
        whip = spec.get("whip")
        if whip and (ph in ("strike", "after") or (isinstance(ph, (tuple, list)) and False)):
            target = np.asarray(WHIPS[whip[0]], float)
            target = target / np.linalg.norm(target)
            ax = np.cross(d, target)
            if np.linalg.norm(ax) > 1e-9:
                full = math.atan2(np.linalg.norm(ax), float(d @ target))
                d = P.q_rot(P.q_exp(ax / np.linalg.norm(ax) * min(full, math.radians(whip[1]))), d)
        side = 1.0 if kick_leg.startswith("Right") else -1.0
        return d * np.array([side, 1.0, 1.0])
    if isinstance(spec, dict):
        c0, v = DR.geom()[kick_leg]
        leg = P.q_rot(np.array(p[kick_leg][:4]), v)
        leg = leg / np.linalg.norm(leg)
        d = leg if "along" in spec else -leg
        tilt = (spec.get("along") if "along" in spec else -spec.get("against", 0.0)) * D2R
        up = np.array([0.0, 1.0, 0.0])
        axis = np.cross(d, up)
        if np.linalg.norm(axis) > 1e-6 and tilt:
            d = P.q_rot(P.q_exp(axis / np.linalg.norm(axis) * tilt), d)
        return d
    return DR.arm_dir(arm.split()[0], *spec)


def carry(keys):
    """an acting key sets only what CHANGES: every other field carries forward from the key before it"""
    out, cur = [], {}
    for k in keys:
        cur = {**cur, **{f: v for f, v in k.items() if f != "stiff"}}
        out.append({**cur, "stiff": k.get("stiff", 1.0)})
    return out


def smooth_track(ts, vs, n, w=4):
    x = np.interp(np.arange(n) / 60, ts, vs)
    pad = np.r_[x[:1].repeat(w), x, x[-1:].repeat(w)]
    return np.convolve(pad, np.ones(2 * w + 1) / (2 * w + 1), "valid")


def pivot_pass(c, b):
    """the support leg keeps its world-upright line (yaw with the hips + its stance swing), so the foot turns WITH the
    hips about its sole; the torso is placed so that sole never leaves its spot (plus the toe rise / dip)"""
    S = b["support_leg"]
    ss = J.index(S)
    q, p = DR.arrays(c)
    n = len(q)
    ts = [k["t"] for k in b["keys"]]
    sup = smooth_track(ts, [k["support"] for k in b["keys"]], n)
    toe = smooth_track(ts, [k["toe"] for k in b["keys"]], n)
    dip = smooth_track(ts, [k["dip"] for k in b["keys"]], n)
    sup_sl = np.stack([smooth_track(ts, [slide_of(k, "support_leg", b)[i] for k in b["keys"]], n) for i in range(3)], axis=1)
    pivot, vloc = P._rig()
    spot = P.sole_char(q[0, 0], p[0, 0], q[0, ss], p[0, ss], S)
    spot[1] = P.FLOOR
    for t in range(n):
        qt = q[t, 0]
        f = P.q_rot(qt, np.array([0.0, 0.0, -1.0]))
        yaw = math.atan2(-f[0], -f[2])
        if t == 0:
            yaw0 = yaw
        # the support foot pivots LESS than the hips (pivot_share): loved leg strikes swing the support leg ~34 deg
        # against the torso in the strike window; turning it 100 % with the hips froze it (owner: "the left leg doesnt
        # just stay there"). The sole stays planted either way.
        share = float(b.get("pivot_share", 1.0))
        yaw = yaw0 + share * (((yaw - yaw0 + math.pi) % (2 * math.pi)) - math.pi)
        qw = P.q_mul(P.q_exp(np.array([0.0, yaw, 0.0])), P.q_exp(np.array([sup[t] * D2R, 0.0, 0.0])))
        q[t, ss] = P.q_mul(P.q_inv(qt), qw)
        p[t, ss] = sup_sl[t] + P.q_rot(P.q_inv(qt), np.array([0.0, dip[t], 0.0]))
        want = spot + np.array([0.0, toe[t], 0.0])
        p[t, 0] = want - P.q_rot(qt, pivot[S] + p[t, ss] + P.q_rot(q[t, ss], vloc[S]))
    return DR.set_arrays(c, q, p)


def build(d, persona=None, keys=None, follow=None, name=None, rng=None):
    """-> (clip, the build used). keys: explicit (already carried) keys - a candidate's; persona: an acting persona's"""
    b = dict(d["build"])
    if keys is not None:
        b["keys"] = keys
    elif persona:
        b["keys"] = carry(d["acting"]["personas"][persona]["keys"])
    rng = rng or slide_ranges()
    poses = [{"pose": key_pose(k, b), "t": k["t"], "stiff": k.get("stiff", 1.0), "name": k["name"]} for k in b["keys"]]
    pr = {"follow": {**FOLLOW, **(follow or {})}, "lean_v": 0.0, "lean_a": 0.0}
    c = P.sim(poses, poses[-1]["t"], pr, plant=False, slide_range=rng,
              name=name or f"{d['name']}{'_' + persona if persona else ''}", interp="hermite")
    c["loop"] = False
    c = pivot_pass(c, b)
    c = DR.pin_feet(c, rng, legs=(b["kick_leg"],))
    q, _ = DR.arrays(c)
    side = 1.0 if b["kick_leg"].startswith("Right") else -1.0
    kc = next(k for k in b["keys"] if k["name"] == "contact")
    yaw = np.degrees(np.unwrap([math.atan2(-f[0], -f[2]) for f in (P.q_rot(qq, np.array([0.0, 0.0, -1.0])) for qq in q[:, 0])])) * side
    t_hit = next((i for i in range(len(yaw)) if i / 60 >= kc["t"] - 0.1 and yaw[i] >= kc["yaw"] - 5), int(kc["t"] * 60)) / 60
    # (no clamp to the leg's GLOBAL speed peak here: a strong kick has two - toe-off and contact - and when the toe-off
    # one is the larger, that clamp dragged the Hit back to toe-off + 3 frames, before the body had turned (every
    # slider variant of the footage-corrected roundhouse: 67-80 deg turned at the Hit, the foot 21-44 deg short).
    # Contact comes after its strike and within 3 frames of it: settled below against the NEAREST peak.)
    c["events"] = [{"t": round(t_hit, 6), "name": "Hit", "by": b["kick_leg"]}]
    # the engine judges the Hit against the NEAREST local speed peak of its striker (a strong kick has two): ask it,
    # and settle the Hit 0..3 frames after THAT peak
    ev = (C.metrics(c, C.load_rig("r6")).get("events") or [{}])[0]
    if ev.get("peak_t") is not None:
        # in WHOLE FRAMES on the clip's own time grid: the engine reports the peak rounded to 4 decimals (0.3167 for
        # frame 19) and the clip stores times to 6 - 'peak + 3/60' landed 3.002 (or 3.00002) frames after the real
        # peak, over the engine's 3, and rejected every clamped candidate
        pkf = int(round(float(ev["peak_t"]) * 60))
        f = min(max(int(round(t_hit * 60)), pkf), pkf + 3, len(c["times"]) - 1)
        c["events"][0]["t"] = float(c["times"][f])
    c["dossier"] = d["name"]
    import clip_beats as CB                                  # (its own beats in the clip: the sheet poses them, j6x7)
    c["beats"] = CB.from_keys([(k["t"], k.get("name")) for k in b["keys"]], float(c["times"][-1]))
    return c, b
