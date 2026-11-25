"""r6_vocab.py — the R6 ANIMATOR'S VOCABULARY, measured (owner 2026-10-16 on roundhouse round 1: "the arms poses from start
to finish look awkward, the left leg doesn't just stay there it looks horrible, the kicking leg as well ... it isnt high
quality"). R6 has no knee or elbow: pro R6 animators FAKE them by SLIDING the limbs (a leg slides up into the hip to
bend, out to extend) and keep every limb alive. This measures, per clip, what they do with each limb - statistics only:
  slide_p95     how far each limb SLIDES from its joint (studs, 95th percentile over the clip)
  slide_range   how much that slide CHANGES over the clip (studs: max - min of the slide length)
  rot_range     each limb's rotation range (deg, 95th - 5th percentile of its angle from its OWN mean orientation)
  moving        the share of frames the limb is moving (> 30 deg/s) - nothing 'just stays there'
calibrate(): the loved COMBAT clips with a fast LEG motion (a leg's angular speed peak >= 600 deg/s: knees, stomps,
slams, rolls, get-ups - NOT kicks: the library has no real kick, proc_calib.KINDS) -> per limb percentiles + min, the
other leg as the 'support' leg. It is the R6 combat vocabulary of fast leg moves, the closest data a kick has.
    python kit/anim/r6_vocab.py calibrate          -> assets/animations/calibration/r6_vocab.json
    python kit/anim/r6_vocab.py <clip.json>        -> the same measures + where they sit against the loved band"""
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_calib as PC  # noqa: E402
import proc_r6 as P  # noqa: E402

OUT = os.path.join("assets", "animations", "calibration", "r6_vocab.json")
LIMBS = ["Right Arm", "Left Arm", "Right Leg", "Left Leg"]


def measures(c, kick_leg=None):
    """-> {role: {measure: value}}; roles: the two arms, 'kick_leg' + 'support_leg' (when a leg strikes), else by name"""
    q = PC.rot_arrays(c)
    w = PC.ang_speed(q)
    T = len(q)
    out = {}
    if kick_leg is None:                                  # the leg with the strongest speed peak strikes
        kick_leg = "Right Leg" if w[:, 4].max() >= w[:, 5].max() else "Left Leg"
    for limb in LIMBS:
        k = PC.JOINTS.index(limb)
        fr = np.array([f[4:7] for f in c["joints"][limb]["frames"]], float) if limb in c["joints"] else np.zeros((T, 3))
        sl = np.linalg.norm(fr, axis=1)
        # the angle from the limb's OWN mean orientation (the motion's extent); from_rest (the angle from identity) hid
        # a raised arm's sideways whip - it keeps the same angle from identity (bug found 2026-10-16)
        qm = q[:, k] * np.where((q[:, k] @ q[0, k]) < 0, -1.0, 1.0)[:, None]
        mean = qm.mean(axis=0)
        mean = mean / np.linalg.norm(mean)
        ang = np.degrees(2 * np.arccos(np.clip(np.abs(qm @ mean), -1, 1)))
        role = limb if "Arm" in limb else ("kick_leg" if limb == kick_leg else "support_leg")
        out[role] = {"slide_p95": round(float(np.percentile(sl, 95)), 3),
                     "slide_range": round(float(sl.max() - sl.min()), 3),
                     "rot_range": round(float(np.percentile(ang, 95) - np.percentile(ang, 5)), 1),
                     "moving": round(float(np.mean(w[:, k] > 30)), 3)}
    # SNAP and DRAG: each part's peak angular speed (p99, deg/s) and how many frames its speed peak trails the
    # torso's around the strike (+ = after the torso: the drag hierarchy)
    kl = PC.JOINTS.index(kick_leg)
    pk = int(np.argmax(w[:, kl]))
    lo, hi = max(0, pk - 20), min(len(w), pk + 20)
    tpk = lo + int(np.argmax(w[lo:hi, 0]))
    for part, k in (("Torso", 0), ("Head", 1)):
        out[part] = {"peak_speed": round(float(np.percentile(w[:, k], 99)), 1)}
    for limb in LIMBS:
        k = PC.JOINTS.index(limb)
        role = limb if "Arm" in limb else ("kick_leg" if limb == kick_leg else "support_leg")
        out[role]["peak_speed"] = round(float(np.percentile(w[:, k], 99)), 1)
        out[role]["lag_frames"] = int(lo + int(np.argmax(w[lo:hi, k])) - tpk)
    out["Head"]["lag_frames"] = int(lo + int(np.argmax(w[lo:hi, 1])) - tpk)
    out["kick_leg_name"] = kick_leg
    return out


def calibrate():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import translate_test as TT
    rows = []
    PH = ("rest", "windup", "strike", "after")
    ROLE = ("kick_leg", "support_leg", "kick_side_arm", "other_arm")
    phase = {r: {p: [] for p in PH} for r in ROLE}
    aim = {r: {p: [] for p in PH} for r in ("kick_side_arm", "other_arm")}
    traj = []                                              # per clip: both arms' directions at the four phases
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or lb["group"] != "combat" or re.search(r"victim|knocked", lb["text"] or "", re.I):
            continue
        c = TT.loved_clip(lb["id"])[0]
        q = PC.rot_arrays(c)
        if len(q) < 30:
            continue
        w = PC.ang_speed(q)
        if max(w[:, 4].max(), w[:, 5].max()) < 600:     # no leg strike in this clip
            continue
        rows.append(measures(c))
        # WHERE each limb slides per phase (torso frame, as if the RIGHT leg kicks): rest / 8 frames before the leg's
        # speed peak (wind-up) / the peak (strike) / 10 frames after
        kl = 4 if w[:, 4].max() >= w[:, 5].max() else 5
        kick = PC.JOINTS[kl]
        sup = "Left Leg" if kick == "Right Leg" else "Right Leg"
        karm, oarm = ("Right Arm", "Left Arm") if kick == "Right Leg" else ("Left Arm", "Right Arm")
        pk = int(np.argmax(w[:, kl]))
        flip = np.array([-1.0 if kick == "Left Leg" else 1.0, 1.0, 1.0])
        one = []
        for r, j in zip(ROLE, (kick, sup, karm, oarm)):
            if j not in c["joints"]:
                continue
            S = np.array([f[4:7] for f in c["joints"][j]["frames"]], float) * flip
            for ph, i in zip(PH, (0, max(0, pk - 8), pk, min(len(S) - 1, pk + 10))):
                phase[r][ph].append(S[i])
                if r in aim:                                   # where the arm POINTS (torso frame, shoulder -> hand)
                    qa = np.asarray(c["joints"][j]["frames"][i][:4], float)
                    # the SHOULDER-PIVOT -> HAND line (what proc_director.aim aims), not the part's own down axis:
                    # on R6 the pivot sits at the shoulder's top corner, ~18 deg off (the first try flared the arms)
                    import proc_director as DR
                    v = DR.geom()[j][1]
                    d = P.q_rot(qa / np.linalg.norm(qa), v)
                    d = d / np.linalg.norm(d) * flip
                    aim[r][ph].append(d)
                    one.append(d)
        if len(one) == 8:
            traj.append(np.concatenate(one))                   # kick-side arm x4 phases, other arm x4 phases
    out = {"schema": 1, "about": "what loved R6 COMBAT clips with a LEG strike do with each limb - statistics only (r6_vocab.py)",
           "clips": len(rows), "roles": {}}
    for role in ("kick_leg", "support_leg", "Right Arm", "Left Arm", "Torso", "Head"):
        ms = [m for m in ("slide_p95", "slide_range", "rot_range", "moving", "peak_speed", "lag_frames") if m in rows[0][role]]
        out["roles"][role] = {m: {"min": round(float(min(r[role][m] for r in rows)), 3),
                                  **{f"p{p}": round(float(np.percentile([r[role][m] for r in rows], p)), 3) for p in (10, 25, 50, 75, 90)}}
                              for m in ms}
    out["slides"] = {"about": "median slide per role and phase (studs, torso frame: x right, y up, z back; a RIGHT-leg kick) - "
                              "legs slide UP + FORWARD (the R6 bent knee), arms slide DOWN out of the shoulder",
                     **{r: {ph: [round(float(v), 3) for v in np.median(np.array(phase[r][ph]), axis=0)] for ph in PH} for r in ROLE}}
    def mean_dir(V):
        m = np.mean(np.array(V), axis=0)
        return [round(float(x), 3) for x in m / max(np.linalg.norm(m), 1e-9)]
    out["arm_aim"] = {"about": "the mean direction each arm POINTS per phase (torso frame, shoulder -> hand, a RIGHT-leg kick; "
                               "statistics over every loved leg-strike clip, never one clip's pose) + how tightly they agree (|mean| 0..1)",
                      **{r: {ph: {"dir": mean_dir(aim[r][ph]),
                                  "agree": round(float(np.linalg.norm(np.mean(np.array(aim[r][ph]), axis=0))), 3)} for ph in PH}
                         for r in aim}}
    # ARM HABITS: the mean of all clips' arms is a pose nobody makes (both arms straight out like a T at the wind-up -
    # seen 2026-10-16); cluster each clip's whole arm choreography instead -> each centroid a habit many loved clips share
    from sklearn.cluster import KMeans
    X = np.array(traj)
    km = KMeans(4, n_init=20, random_state=0).fit(X)
    habits = []
    for h in range(4):
        C = km.cluster_centers_[h].reshape(8, 3)
        C = C / np.linalg.norm(C, axis=1, keepdims=True)
        habits.append({"clips": int(np.sum(km.labels_ == h)),
                       "kick_side_arm": {ph: [round(float(x), 3) for x in C[i]] for i, ph in enumerate(PH)},
                       "other_arm": {ph: [round(float(x), 3) for x in C[4 + i]] for i, ph in enumerate(PH)}})
    habits.sort(key=lambda x: -x["clips"])
    out["arm_habits"] = {"about": "k-means (4) over each loved leg-strike clip's arm choreography (both arms, rest / wind-up / "
                                  "strike / after, torso frame, a RIGHT-leg kick): each a habit shared by `clips` loved clips",
                         "habits": habits}
    json.dump(out, open(OUT, "w", encoding="utf-8", newline=""), indent=1)
    return out


def calibrate_categories():
    """the same limb measures for EVERY category (no strike roles: the limbs by name) - the vocab gate for any clip
    (proc_gates.check 'vocab'): a frozen arm or a pole leg in an idle or a walk too"""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import translate_test as TT
    by = {}
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or re.search(r"victim|knocked", lb["text"] or "", re.I):
            continue
        c = TT.loved_clip(lb["id"])[0]
        if len(c["times"]) < 30:
            continue
        m = measures(c, kick_leg="Right Leg")
        row = {"Right Arm": m["Right Arm"], "Left Arm": m["Left Arm"], "Right Leg": m["kick_leg"], "Left Leg": m["support_leg"]}
        by.setdefault(lb["group"], []).append(row)
    d = json.load(open(OUT, encoding="utf-8"))
    d["categories"] = {}
    for g, rows in by.items():
        d["categories"][g] = {"clips": len(rows)}
        for limb in LIMBS:
            d["categories"][g][limb] = {mm: {"min": round(float(min(r[limb][mm] for r in rows)), 3),
                                             **{f"p{q}": round(float(np.percentile([r[limb][mm] for r in rows], q)), 3) for q in (10, 50, 90)}}
                                        for mm in ("slide_p95", "rot_range")}
    json.dump(d, open(OUT, "w", encoding="utf-8", newline=""), indent=1)
    return d["categories"]


def calibrate_locomotion(bins=8):
    """WHERE loved R6 walk / run limbs slide through the stride (2026-10-16: our gaits slid arms 0.0 and legs 0.2-0.5
    vs the loved 0.6 / 1.1-1.2 - the same missing knee as the kick). Per loved locomotion clip: the stride period from
    the right leg's forward swing (autocorrelation), phase 0 = the right leg furthest forward, each limb's slide (torso
    frame) median per phase bin; walks (period >= 0.8 s) and runs separately. Statistics only."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import translate_test as TT
    acc = {"walk": {l: [[] for _ in range(bins)] for l in LIMBS}, "run": {l: [[] for _ in range(bins)] for l in LIMBS}}
    n = {"walk": 0, "run": 0}
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or lb["group"] != "locomotion":
            continue
        c = TT.loved_clip(lb["id"])[0]
        q = PC.rot_arrays(c)
        T = len(q)
        if T < 16 or "Right Leg" not in c["joints"]:
            continue
        fwd = np.array([-P.q_rot(q[t, 4], np.array([0.0, -1.0, 0.0]))[2] for t in range(T)])
        x = fwd - fwd.mean()
        if np.abs(x).max() < 0.15:                         # no stride (a stand, a slide)
            continue
        ac = np.correlate(x, x, "full")[T - 1:]
        lag = next((k for k in range(8, T - 1) if ac[k] > ac[k - 1] and ac[k] >= ac[k + 1] and ac[k] > 0.2 * ac[0]), T)
        period = lag if lag < T else T
        kind = "walk" if period / 60.0 >= 0.8 else "run"
        f0 = int(np.argmax(x[:period]))
        n[kind] += 1
        for limb in LIMBS:
            if limb not in c["joints"]:
                continue
            S = np.array([f[4:7] for f in c["joints"][limb]["frames"]], float)
            for t in range(T):
                b = int(((t - f0) % period) / period * bins) % bins
                acc[kind][limb][b].append(S[t])
    d = json.load(open(OUT, encoding="utf-8"))
    d["locomotion_slides"] = {"about": "median slide per stride phase bin (phase 0 = the right leg furthest forward; torso "
                                       "frame x right, y up, z back), loved walks (period >= 0.8 s) and runs - r6_vocab",
                              "bins": bins, "clips": n,
                              **{k: {l: [[round(float(v), 3) for v in np.median(np.array(acc[k][l][b]), axis=0)] if acc[k][l][b] else [0, 0, 0]
                                          for b in range(bins)] for l in LIMBS} for k in acc}}
    json.dump(d, open(OUT, "w", encoding="utf-8", newline=""), indent=1)
    return d["locomotion_slides"]


WEAPON_RE = r"^\s*(slash|swing|strike)\b"     # a loved clip's own name: a one-handed weapon swing (Sword Fox, CHAIN, ...)
WPH = ("rest", "windup", "strike", "after")
WROLE = ("sword_arm", "free_arm", "lead_leg", "rear_leg")


def weapon_clips(legs=False):
    """the loved, game-licensed COMBAT clips named as a weapon swing -> [(id, clip)] (statistics only; proc_blade).
    Every one of them is UPPER BODY only (measured 2026-11-05: 8 of 8 have no leg track - the game layers the legs), so
    legs=True gives the LEG source instead: loved combat ARM strikes whose legs really move (an arm the fastest
    striker, a leg sliding >= 0.15 studs; no victims / knockdowns)"""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import translate_test as TT
    out = []
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or lb["group"] != "combat":
            continue
        if legs and re.search(r"victim|knocked|reaction|block|grip", lb["text"] or "", re.I):
            continue
        if not legs and not re.search(WEAPON_RE, (lb["text"] or "").split("|")[0], re.I):
            continue
        c = TT.loved_clip(lb["id"])[0]
        if len(c["times"]) < 20 or not all(j in c["joints"] for j in PC.JOINTS):
            continue
        if legs:
            w = PC.ang_speed(PC.rot_arrays(c))
            sl = max(float(np.linalg.norm(np.array([f[4:7] for f in c["joints"][j]["frames"]], float), axis=1).max())
                     for j in ("Right Leg", "Left Leg"))
            if max(w[:, 2].max(), w[:, 3].max()) < 600 or max(w[:, 2].max(), w[:, 3].max()) < max(w[:, 4].max(), w[:, 5].max()) or sl < 0.15:
                continue
        out.append((lb["id"], c))
    return out


def weapon_row(c, pk=None):
    """one loved swing's numbers, MIRRORED so the sword hand is the right one: the striking arm (the faster arm), its
    speed peak = the strike; phases rest / 8 frames before / the peak / 10 after; the LEAD leg = the one whose foot is
    further forward at the strike"""
    import proc_director as DR
    q = PC.rot_arrays(c)
    w = PC.ang_speed(q)
    T = len(q)
    sa = 2 if w[:, 2].max() >= w[:, 3].max() else 3
    pk = int(np.argmax(w[:, sa])) if pk is None else min(int(pk), len(w) - 1)   # pk given: the clip's own strike (a Hit)
    flip = np.array([1.0 if sa == 2 else -1.0, 1.0, 1.0])
    arms = {"sword_arm": PC.JOINTS[sa], "free_arm": PC.JOINTS[5 - sa]}
    import clip as C
    W = C.world_frames(c, C.load_rig("R6"))
    fz = {lg: float((W[pk][lg] @ np.array([0.0, -1.0, 0.0, 1.0]))[2]) for lg in ("Right Leg", "Left Leg")}
    lead = min(fz, key=fz.get)                              # -Z is forward
    legs = {"lead_leg": lead, "rear_leg": "Left Leg" if lead == "Right Leg" else "Right Leg"}
    idx = dict(zip(WPH, (0, max(0, pk - 8), pk, min(T - 1, pk + 10))))
    row = {"slides": {}, "aim": {}, "whip": {}, "swing": {}, "outward": {}}
    for r, j in {**arms, **legs}.items():
        S = np.array([f[4:7] for f in c["joints"][j]["frames"]], float) * flip
        row["slides"][r] = {ph: S[i] for ph, i in idx.items()}
        if r in arms:
            # how far the arm slides OUT from its socket, sideways (2026-11-05: the drill's arm slid 0.8 studs off the
            # shoulder - 'the sword and hands weird'; loved arms slide up / forward, little outward)
            row["outward"][r] = float(np.percentile(S[:, 0] if r == "sword_arm" else -S[:, 0], 90))
        k = PC.JOINTS.index(j)
        lo, hi = max(0, pk - 15), min(T - 1, pk + 15)
        qm = q[lo:hi + 1, k] * np.where((q[lo:hi + 1, k] @ q[lo, k]) < 0, -1.0, 1.0)[:, None]
        mean = qm.mean(axis=0) / np.linalg.norm(qm.mean(axis=0))
        ang = np.degrees(2 * np.arccos(np.clip(np.abs(qm @ mean), -1, 1)))
        row["swing"][r] = float(ang.max() - ang.min())       # how far the limb swings around the strike
        if r in arms:
            v = DR.geom()[j][1]
            row["aim"][r] = {ph: (lambda d: d / np.linalg.norm(d) * flip)(P.q_rot(q[i, k], v)) for ph, i in idx.items()}
            a, b = q[max(0, pk - 5), k], q[min(T - 1, pk + 5), k]
            row["whip"][r] = float(np.degrees(2 * np.arccos(min(1.0, abs(float(a @ b))))))
    lo, hi = max(0, pk - 10), min(len(w), pk + 10)
    row["torso_peak_deg_s"] = float(w[lo:hi, 0].max())
    tpk = lo + int(np.argmax(w[lo:hi, 0]))
    row["lag"] = {r: int(lo + int(np.argmax(w[lo:hi, PC.JOINTS.index(j)])) - tpk) for r, j in (("head", "Head"), ("sword_arm", arms["sword_arm"]), ("free_arm", arms["free_arm"]))}
    # the PIVOT: the rear leg's turn about the vertical (world) around the strike, against the torso's
    def yaw(M):
        f = M[:3, :3] @ np.array([0.0, 0.0, -1.0])
        return math.atan2(-f[0], -f[2])
    a, z = max(0, pk - 15), min(T - 1, pk + 15)
    ty = abs(math.degrees((yaw(W[z]["Torso"]) - yaw(W[a]["Torso"]) + math.pi) % (2 * math.pi) - math.pi))
    ly = abs(math.degrees((yaw(W[z][legs["rear_leg"]]) - yaw(W[a][legs["rear_leg"]]) + math.pi) % (2 * math.pi) - math.pi))
    row["torso_turn_deg"] = ty
    row["pivot_share"] = ly / ty if ty > 10 else None
    return row


def calibrate_weapon(habits_k=3):
    """the loved WEAPON swings' R6 vocabulary (the governor's re-plan 2026-11-05: proc_blade is calibrated by loved
    sword clips as STATISTICS - never a pose): per role and phase the median slide, each arm's phase directions as
    k-means ARM HABITS (the mean is a T nobody makes), the whip (deg turned in the 10 frames around the strike), the
    torso's speed at the strike, the legs' swing, the rear leg's partial pivot, the drag (frames behind the torso)"""
    rows = [(cid, weapon_row(c)) for cid, c in weapon_clips()]
    if len(rows) < 4:
        raise SystemExit(f"calibrate weapon: only {len(rows)} loved weapon clips")
    R = [r for _, r in rows]
    lrows = [(cid, weapon_row(c)) for cid, c in weapon_clips(legs=True)]
    L = [r for _, r in lrows]
    band = lambda xs: {"n": len(xs), "min": round(float(min(xs)), 3), **{f"p{p}": round(float(np.percentile(xs, p)), 3) for p in (10, 25, 50, 75, 90)}}  # noqa: E731
    out = {"about": "loved R6 WEAPON swings (combat clips named slash / swing / strike), the sword hand mirrored to the RIGHT; "
                    "torso frame x right, y up, z back - statistics only (r6_vocab.calibrate_weapon, proc_blade)",
           "clips": [cid for cid, _ in rows],
           "leg_clips": [cid for cid, _ in lrows],
           "legs_from": "the weapon clips carry no legs: legs, torso speed and the pivot from `leg_clips` (loved full-body ARM strikes)",
           "slides": {r: {ph: [round(float(v), 3) for v in np.median(np.array([x["slides"][r][ph] for x in (R if "arm" in r else L)]), axis=0)] for ph in WPH} for r in WROLE},
           "slide_p95": {r: band([float(np.percentile([np.linalg.norm(x["slides"][r][ph]) for ph in WPH], 95)) for x in (R if "arm" in r else L)]) for r in WROLE},
           "slide_outward": {r: band([x["outward"][r] for x in R + L]) for r in ("sword_arm", "free_arm")},
           "swing_deg": {r: band([x["swing"][r] for x in (R if "arm" in r else L)]) for r in WROLE},
           "whip_deg": {r: band([x["whip"][r] for x in R]) for r in ("sword_arm", "free_arm")},
           "torso_peak_deg_s": band([x["torso_peak_deg_s"] for x in R + L]),
           "torso_turn_deg": band([x["torso_turn_deg"] for x in R + L]),
           "pivot_share": band([x["pivot_share"] for x in L if x["pivot_share"] is not None]),
           "lag_frames": {r: band([x["lag"][r] for x in R]) for r in ("head", "sword_arm", "free_arm")}}
    from sklearn.cluster import KMeans
    X = np.array([np.concatenate([x["aim"][r][ph] for r in ("sword_arm", "free_arm") for ph in WPH]) for x in R])
    km = KMeans(habits_k, n_init=20, random_state=0).fit(X)
    hab = []
    for h in range(habits_k):
        Cc = km.cluster_centers_[h].reshape(8, 3)
        Cc = Cc / np.linalg.norm(Cc, axis=1, keepdims=True)
        hab.append({"clips": int(np.sum(km.labels_ == h)),
                    "sword_arm": {ph: [round(float(v), 3) for v in Cc[i]] for i, ph in enumerate(WPH)},
                    "free_arm": {ph: [round(float(v), 3) for v in Cc[4 + i]] for i, ph in enumerate(WPH)}})
    hab.sort(key=lambda x: -x["clips"])
    out["arm_habits"] = hab
    d = json.load(open(OUT, encoding="utf-8"))
    d["weapon"] = out
    json.dump(d, open(OUT, "w", encoding="utf-8", newline=""), indent=1)
    return out


def compare(c):
    cal = json.load(open(OUT, encoding="utf-8"))["roles"]
    m = measures(c)
    rows = []
    for role, vals in m.items():
        if role == "kick_leg_name":
            continue
        for k, v in vals.items():
            b = cal[role][k]
            where = "below loved p10" if v < b["p10"] else ("above loved p90" if v > b["p90"] else "inside")
            rows.append((role, k, v, b["p10"], b["p50"], b["p90"], where))
    return rows


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:3] == ["calibrate", "weapon"]:
        o = calibrate_weapon()
        print(json.dumps({"clips": len(o["clips"]), "leg_clips": len(o["leg_clips"]), "slide_p95": o["slide_p95"], "torso_peak_deg_s": o["torso_peak_deg_s"], "whip_deg": o["whip_deg"],
                          "pivot_share": o["pivot_share"], "swing_deg": o["swing_deg"], "habits": [h["clips"] for h in o["arm_habits"]]}))
    elif sys.argv[1:3] == ["calibrate", "locomotion"]:
        o = calibrate_locomotion()
        print(json.dumps({"clips": o["clips"], **{k: {l: o[k][l] for l in ("Right Leg", "Right Arm")} for k in ("walk", "run")}}))
    elif sys.argv[1:3] == ["calibrate", "categories"]:
        o = calibrate_categories()
        print(json.dumps({g: {"clips": v["clips"], **{l: {m: v[l][m]["p10"] for m in v[l]} for l in LIMBS}} for g, v in o.items()}))
    elif sys.argv[1] == "calibrate":
        o = calibrate()
        print(json.dumps({"clips": o["clips"], **{r: {m: v["p50"] for m, v in d.items()} for r, d in o["roles"].items()}}))
    else:
        for row in compare(json.load(open(sys.argv[1], encoding="utf-8"))):
            print(f"{row[0]:12s} {row[1]:12s} {row[2]:>8} | loved p10 {row[3]:>7} p50 {row[4]:>7} p90 {row[5]:>7} | {row[6]}")
