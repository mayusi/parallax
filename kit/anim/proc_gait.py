"""proc_gait.py — WALK / RUN cycles made FROM SCRATCH (mission 2026-10-14). Run v3 was built from the loved Run V4's own
poses and the copy floor (kit/anim/proc_gates.py) flags it; this designs the cycle from gait mechanics + the loved
clips' STATISTICS only (measured 2026-10-14 over the loved walks / runs, medians):
          period   leg swing   arm swing   torso twist   lean    bob
  walk    1.0 s    62 deg      47 deg      14 deg        9 deg   0.20 studs
  run     0.67 s   137 deg     160 deg     35 deg        24 deg  0.29 studs
(loved R6 runs swing far beyond a human's - that exaggeration IS the style).
Keys per half cycle (the second half is the mirror): CONTACT (legs split, arms opposite, shoulders counter-twisted),
DOWN (the walk's lowest point just after contact / the run's mid-stance compression), PASSING (legs together, the
swing foot lifted by a slide - R6 has no knee), UP (the walk's highest point at passing+ / the run's flight). The walk's
bob is highest at passing, the run's lowest at mid-stance (the bob REVERSES between gaits). Lateral sway over the
stance foot; the head counter-turns the torso's twist (a stable gaze); arms swing a little outward.
    from proc_gait import keys    (diagnostics/proc_gait_v1.py builds, gates and renders them)"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_director as DR  # noqa: E402

D2R = math.pi / 180
GAITS = {
    "walk": {"period": 1.0, "leg": 62, "arm": 47, "twist": 14, "lean": 9, "bob": 0.20, "lift": 0.22, "sway": 0.05,
             "roll": 2.0, "arm_out": 4, "head_hold": 0.7},
    "run": {"period": 0.667, "leg": 120, "arm": 130, "twist": 30, "lean": 22, "bob": 0.28, "lift": 0.55, "sway": 0.04,
            "roll": 3.0, "arm_out": 7, "head_hold": 0.6},
    "jog": {"period": 0.8, "leg": 92, "arm": 85, "twist": 22, "lean": 14, "bob": 0.24, "lift": 0.38, "sway": 0.045,
            "roll": 2.5, "arm_out": 6, "head_hold": 0.65, "base": "run"},
    "sprint": {"vocab": False, "period": 0.56, "leg": 140, "arm": 150, "twist": 34, "lean": 30, "bob": 0.3, "lift": 0.7, "sway": 0.035,
               "roll": 3.0, "arm_out": 6, "head_hold": 0.55, "base": "run"},
    "sneak": {"period": 1.4, "leg": 44, "arm": 18, "twist": 8, "lean": 18, "bob": 0.08, "lift": 0.16, "sway": 0.07,
              "roll": 2.5, "arm_out": 14, "head_hold": 0.8, "base": "walk", "crouch": 0.35, "arm_bias": 35},
}
# (run: leg 120 / arm 130, a little under the loved medians 137 / 160 - the springs' follow-through adds ~6-13 %)


def _pose(g, legR, legL, liftR, liftL, armR, armL, twist, y, x, roll):
    p = DR.rest()
    p = DR.turn(p, "Torso", [-g["lean"] * D2R, twist * D2R, roll * D2R])
    p["Torso"][4] += x
    p["Torso"][5] += y - g.get("crouch", 0.0)               # sneak: a lower body (the legs split / slide to reach)
    armR, armL = armR + g.get("arm_bias", 0.0), armL + g.get("arm_bias", 0.0)   # sneak: arms carried forward
    p = DR.turn(p, "Head", [g["lean"] * 0.6 * D2R, -twist * g["head_hold"] * D2R, -roll * 0.6 * D2R])   # eyes level
    for leg, a, lift in (("Right Leg", legR, liftR), ("Left Leg", legL, liftL)):
        p = DR.turn(p, leg, [(a + g.get("leg_lean", 0.0)) * D2R, 0.0, 0.0])
        p[leg][5] += lift
    for arm, a, s in (("Right Arm", armR, 1), ("Left Arm", armL, -1)):
        p = DR.turn(p, arm, [a * D2R, 0.0, g["arm_out"] * D2R * s])
    return p


def half(g, kind, side=+1):
    """the four keys of a half cycle with the RIGHT foot leading (side +1) or the left (-1): (pose, phase 0..0.5)"""
    L, A, Tw, B, Lf = g["leg"] / 2, g["arm"] / 2, g["twist"] / 2, g["bob"], g["lift"]
    walk = g.get("base", kind) == "walk"
    # leading leg angle, trailing leg angle, the trailing / swing foot's lift, torso height, phase
    if walk:
        rows = [("contact", L, -L, 0.0, -0.25 * B, 0.0), ("down", 0.7 * L, -0.85 * L, 0.05, -0.5 * B, 0.12),
                ("passing", -0.1 * L, 0.15 * L, Lf, 0.5 * B, 0.25), ("up", -0.55 * L, 0.6 * L, 0.4 * Lf, 0.3 * B, 0.37)]
    else:
        rows = [("contact", 0.75 * L, -L, 0.1 * Lf, -0.1 * B, 0.0), ("down", 0.35 * L, -0.7 * L, 0.6 * Lf, -0.5 * B, 0.09),
                ("passing", -0.35 * L, 0.2 * L, Lf, 0.15 * B, 0.2), ("up", -0.9 * L, 0.85 * L, 0.5 * Lf, 0.5 * B, 0.33)]
    out = []
    for name, lead, trail, lift, y, ph in rows:
        arm_lead = -A * (lead / L)                           # the arm opposite the leg swings with it
        arm_trail = -A * (trail / L)
        twist = -Tw * (lead / L)                             # shoulders counter-rotate the legs
        x = g["sway"] * (1 if name in ("down", "passing") else 0.5)
        roll = g["roll"] * (1 if name == "down" else 0.4)
        # each arm swings OPPOSITE its own-side leg (the right arm back while the right leg is forward). (Review
        # 2026-10-14: the first build passed them the other way round - a pacing 'robot' walk the span gates can't see)
        if side > 0:
            p = _pose(g, lead, trail, 0.0, lift, arm_lead, arm_trail, twist, y, x, -roll)
        else:
            p = _pose(g, trail, lead, lift, 0.0, arm_trail, arm_lead, -twist, y, -x, roll)
        out.append((name, p, ph))
    return out


def direct(pose, direction):
    """orientation warping for R6: 'back' - the cycle mirrored front <-> back (a backpedal: legs / arms swing the other
    way, the torso leans back a little); 'left' / 'right' - the legs swing SIDEWAYS (their forward swing turned into a
    swing about the forward axis) while the torso keeps facing forward"""
    if direction == "forward":
        return pose
    import copy
    p = copy.deepcopy(pose)
    for j in ("Right Leg", "Left Leg", "Right Arm", "Left Arm", "Torso", "Head"):
        rv = DR.P.q_log(np.array(p[j][:4]))
        if direction == "back":                              # front <-> back mirror of a rotation vector (a
            # pseudovector under z -> -z): (-x, -y, z). Flipping x alone left the torso / head TWIST un-mirrored, so the
            # shoulders twisted against the arm swing (review 2026-10-14); the torso's lean is damped to a slight lean back
            rv = np.array([-rv[0], -rv[1], rv[2]]) if j != "Torso" else np.array([-rv[0] * 0.3, -rv[1], rv[2]])
        else:
            s_ = 1.0 if direction == "right" else -1.0
            if j in ("Right Leg", "Left Leg"):
                rv = np.array([rv[0] * 0.25, rv[1], -s_ * rv[0] * 0.8])      # (EXPERIMENTAL: legs cross - a real strafe spreads and closes them; skate 0.16, not shipped)
            elif j == "Torso":
                rv = np.array([rv[0] * 0.3, rv[1] * 0.5, rv[2] + s_ * 0.05])
        p[j][:4] = list(map(float, DR.P.q_exp(rv)))
    return p


def keys(kind, direction="forward"):
    g = GAITS[kind]
    T = g["period"]
    ks = []
    for side, off in ((+1, 0.0), (-1, 0.5)):
        for name, p, ph in half(g, kind, side):
            ks.append({"pose": p, "t": (ph + off) * T, "name": f"{name}{'R' if side > 0 else 'L'}"})
    ks.append({"pose": half(g, kind, +1)[0][1], "t": T, "name": "contactR"})
    # (the SPRINT keeps its slides off: with them its legs exceed the MuJoCo torque-rate limit by 12-26 pct at a 0.56 s
    # stride - scaling or smoothing the slides did not fix it, 2026-10-16; backward / sideways strides were not measured)
    if direction == "forward" and g.get("vocab", True):
        for k in ks:                                       # the R6 VOCABULARY: limbs slide through the stride
            for limb in ("Right Leg", "Left Leg", "Right Arm", "Left Arm"):
                v = loco_slide(kind, limb, k["t"] / T)
                k["pose"][limb][4:7] = [float(k["pose"][limb][4 + i] + v[i]) for i in range(3)]
    for k in ks:
        k["pose"] = direct(k["pose"], direction)
    return ks, g


_LOCO = None


def loco_slide(kind, limb, phase):
    """the loved R6 walk / run slide of a limb at a stride phase (0 = the right leg furthest forward; r6_vocab
    locomotion_slides, statistics only): legs ride forward + up (the bent knee), a run's legs slide back as they push
    off and its arms pump forward. Our gaits slid arms 0.0 and legs 0.2-0.5 vs the loved 0.6 / 1.1-1.2 (2026-10-16).
    The per-bin medians are used as they are (no gain to the loved peak - that doubled every phase)"""
    global _LOCO
    if _LOCO is None:
        import json
        p = os.path.join("assets", "animations", "calibration", "r6_vocab.json")
        d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        _LOCO = (d.get("locomotion_slides"), (d.get("categories") or {}).get("locomotion"))
    L, cat = _LOCO
    if not L:
        return np.zeros(3)
    gait = "run" if (GAITS[kind].get("base", kind) in ("run", "jog", "sprint")) else "walk"
    B = np.array(L[gait][limb], float)
    nb = len(B)
    # a stride is PERIODIC: the bins as a smooth curve, their first two harmonics (the run's forward -> back flip
    # between two bins, interpolated linearly, was a corner the sprint's legs could not follow - MuJoCo torque snap)
    F = np.fft.rfft(B, axis=0)
    F[3:] = 0
    k = np.arange(F.shape[0])[:, None]
    ang = 2 * np.pi * k * (phase % 1.0)
    coef = np.where(k == 0, 1.0, 2.0) / nb
    v = (coef * (F.real * np.cos(ang) - F.imag * np.sin(ang))).sum(axis=0)
    # NO gain: the median stride curve IS the typical slide. Scaling it so its top reached the loved PEAK (slide_p95)
    # doubled every phase - the legs rode a stud forward into the torso mid-stride, squat and detached (seen 2026-10-16)
    return v


def strafe_keys(side="right", period=0.75, spread=26.0, lift=0.16):   # 2.4 studs/s with ground-speed foot locking (free: 26 deg skid 0.19)
    """an in-place SIDE-STEP (strafe) that spreads and closes - legs never cross (the forward cycle turned sideways
    crossed them): spread (feet apart) -> the lead foot holds while the trail foot swings in, lifted -> close (feet
    together under the body) -> the trail foot holds while the lead foot lifts and swings out. Each planted foot slides
    opposite the travel, the torso keeps facing forward, the arms counter a little. side 'right' = travel +X"""
    s = 1.0 if side == "right" else -1.0
    lead, trail = ("Right Leg", "Left Leg") if s > 0 else ("Left Leg", "Right Leg")
    out = lambda leg, deg: deg * (1.0 if leg == "Right Leg" else -1.0)   # + = away from the body  # noqa: E731

    def pose(dl, dt, ll, lt, y, roll, arm):
        p = DR.rest()
        p = DR.turn(p, "Torso", [-4 * D2R, 0.0, roll * D2R])
        p["Torso"][5] += y
        p = DR.turn(p, "Head", [2 * D2R, 0.0, -roll * 0.7 * D2R])
        for leg, d, lf in ((lead, dl, ll), (trail, dt, lt)):
            p = DR.turn(p, leg, [0.0, 0.0, out(leg, d) * D2R])
            p[leg][5] += lf
        for a, sgn in (("Right Arm", 1), ("Left Arm", -1)):
            p = DR.turn(p, a, [6 * D2R, 0.0, (arm * sgn + 4 * sgn) * D2R])
        return p
    spreadp = pose(spread, spread, 0.0, 0.0, -0.06, 0.0, 4)
    trail_in = pose(spread * 0.5, -spread * 0.2, 0.0, lift, 0.02, 2.5 * s, -2)
    close = pose(-2.0, -2.0, 0.0, 0.0, 0.03, 0.0, -3)
    lead_out = pose(spread * 0.3, spread * 0.55, lift, 0.0, 0.0, -2.5 * s, 2)
    ks = [{"pose": spreadp, "t": 0.0, "name": "spread"}, {"pose": trail_in, "t": 0.25 * period, "name": "trail_in"},
          {"pose": close, "t": 0.5 * period, "name": "close"}, {"pose": lead_out, "t": 0.75 * period, "name": "lead_out"},
          {"pose": spreadp, "t": period, "name": "spread"}]
    return ks, {"period": period, "leg": 0, "arm": 0, "twist": 0, "bob": 0.09}


def style_profile(style, base="walk"):
    """a WALK in a 100STYLE style (statistics: assets/animations/calibration/style_stats.json, CC BY 4.0 - Mason,
    Starke, Komura 2022): our loved-R6-calibrated walk scaled by the style's ratio to the dataset's own Neutral walk
    (period, leg / arm swing, twist, bob; clamped 0.3-3x), lean shifted by the style's lean difference (the dataset
    measures forward lean as negative). So 'proud' changes what proud changes vs a neutral walk - on top of the owner's
    R6 style, never replacing it. -> the profile name (added to GAITS)"""
    import json
    stats = json.load(open(os.path.join("assets", "animations", "calibration", "style_stats.json"), encoding="utf-8"))["styles"]
    s, n, g = stats[style], stats["Neutral"], dict(GAITS[base])
    r = lambda k: float(np.clip(s[k] / max(n[k], 1e-6), 0.3, 3.0))  # noqa: E731
    g.update({"period": round(g["period"] * r("period"), 3), "leg": round(g["leg"] * r("leg"), 1),
              "arm": round(g["arm"] * r("arm"), 1), "twist": round(g["twist"] * r("twist"), 1),
              "bob": round(g["bob"] * r("bob_per_leg"), 3), "lean": round(g["lean"] - (s["lean"] - n["lean"]), 1),
              "base": base, "style": style})
    # a strong hunch (Old: 32 deg) tilted the legs back WITH the torso: the centre of mass sat 1.36 studs in front of the
    # planted feet (MuJoCo balance 1.0). R6 has no hip-flex-plus-knee, so the legs swing forward under the lean instead
    g["leg_lean"] = round(max(0.0, g["lean"] - 15.0), 1)
    name = f"style-{style.lower()}"
    GAITS[name] = g
    return name
