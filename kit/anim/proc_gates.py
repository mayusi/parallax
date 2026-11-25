"""proc_gates.py — the GATES for procedural R6 (plan: board/plans/archive/2026-10-13-proc-from-scratch-plan.md, step 2). Each gate
names the failure the owner saw; together they FILTER (they never rank - the owner ranks). Thresholds come from the
calibration pack (kit/anim/proc_calib.py, loved-clip statistics) and the craft research.
  readable     every arm gesture moves the hand >= 8 px at the default camera (12 studs, 70 deg FOV, 1080p: 1 stud ~ 64
               px) - 1-degree nods and 9-degree taps were invisible
  statue       frozen: no joint turns more than 3 deg over the whole clip (loved breathing idles move 3.5-10 deg)
  face         'the prop brought to the face': the hand above the upper chest (torso frame y > 0.55, in front) while the
               head looks at it (R6 has no elbow - bring the HEAD to the hand; the watch belongs at the lower chest)
  floaty       arm gesture rises slower than the loved category's p90 (loved R6: snap ~0.2 s, then hold)
  robot_arm    an arm gesture with (almost) no torso / head motion during its rise (< 8 % of the arm's turn)
  jitter       torso / head frame-to-frame shake above the loved category's p95 (proc_calib.shake)
  frozen_limb  a limb that neither slides nor turns (both below the loved category's MIN; below p10 = a warning) - the R6
               vocabulary (owner: 'the left leg doesnt just stay there', 'the arms awkward'). A limb some loved clip
               holds perfectly still (combat legs: punch combos; dance legs; idle) is listed as UNGATED, not checked -
               kicks are guarded by the leg-motion vocab gate in proc_candidates instead
  style_band   whole-body motion outside the loved category's band (loved min x 0.8 .. max x 1.25; categories with
               >= 30 loved clips; idle / other report only) - sluggish or frantic
  copy_floor   FROM SCRATCH, proven: no moving 1.5 s window (every joint, 95th percentile of the angle) lies closer to a loved clip's window than the 10th
               percentile of the distances BETWEEN different loved clips (re-uploaded twins < 2 deg left out: 15.3 deg);
               near-rest windows are exempt
    python kit/anim/proc_gates.py bank                      -> _artifacts/r6lib/proc_windows.npz (loved windows + floor)
    python kit/anim/proc_gates.py check <clip.json> [--category idle]
    from proc_gates import check"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import proc_calib as PC  # noqa: E402

BANK = os.path.join("_artifacts", "r6lib", "proc_windows.npz")
J = PC.JOINTS
PX_PER_STUD = 64.0
WIN, STRIDE, SUB = 90, 15, 5
MOVING = 15.0                                                # deg: the most-moving joint turns this much in the window


def rig_geom():
    r = C.load_rig("r6")
    out = {}
    for j in ("Right Arm", "Left Arm"):
        c0 = np.asarray(r["joints"][j]["c0"][:3], float)
        out[j] = (c0, np.array([0.0, -1.0, 0.0]) - np.asarray(r["joints"][j]["c1"][:3], float))
    return out


def arrays(c):
    T = len(c["times"])
    q = PC.rot_arrays(c)
    p = np.zeros((T, 6, 3))
    for k, j in enumerate(J):
        if j in c["joints"]:
            p[:, k] = np.array([f[4:7] for f in c["joints"][j]["frames"]], float)
    return q, p


def qrot(q, v):
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    u = np.stack([x, y, z], -1)
    t = 2 * np.cross(u, v)
    return v + w[..., None] * t + np.cross(u, t)


def hands(q, p, G):
    return {j: G[j][0] + p[:, J.index(j)] + qrot(q[:, J.index(j)], G[j][1]) for j in ("Right Arm", "Left Arm")}


def rotvec(q):
    q = q * np.where(q[..., 3:4] < 0, -1, 1)
    s = np.linalg.norm(q[..., :3], axis=-1, keepdims=True)
    ang = 2 * np.arctan2(s, q[..., 3:4])
    return np.where(s > 1e-9, q[..., :3] / np.maximum(s, 1e-9) * ang, 0.0)


def windows(q, stride=STRIDE, loop=False):
    """[W, 18, 6, 4] quats: every 1.5 s window (18 samples, every 5th frame) - a loop is tiled first so a short cycle
    still gives windows; plus how much each window moves (the most-moving joint's angle range, deg)"""
    if loop:
        q = np.concatenate([q] * max(2, int(np.ceil(2 * WIN / max(len(q), 1)))))
    out, mov = [], []
    for a in range(0, max(1, len(q) - WIN + 1), stride):
        w = q[a:a + WIN:SUB]
        if len(w) < WIN // SUB:
            continue
        ref = w[0]
        d = np.degrees(2 * np.arccos(np.clip(np.abs(np.einsum("sjk,jk->sj", w, ref)), -1, 1)))
        out.append(w)
        mov.append(float(d.max()))
    return np.array(out), np.array(mov)


def wdist(Wb, w):
    """a COPY matches on every joint at nearly every moment: the 95th percentile of the per-(sample, joint) angle"""
    d = np.degrees(2 * np.arccos(np.clip(np.abs(np.einsum("nsjk,sjk->nsj", Wb, w)), -1, 1)))
    return np.percentile(d.reshape(len(Wb), -1), 95, axis=1)


def build_bank():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import translate_test as TT
    Ws, owner = [], []
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or re.search(r"victim|knocked", lb["text"] or "", re.I):
            continue
        c = TT.loved_clip(lb["id"])[0]
        W, mov = windows(PC.rot_arrays(c), stride=5, loop=bool(c.get("loop")))   # 5: a fast cycle stays aligned
        for w, m in zip(W, mov):
            if m > MOVING:
                Ws.append(w)
                owner.append(lb["id"])
    Ws = np.array(Ws, np.float32)
    owner = np.array(owner)
    rs = np.random.default_rng(0)
    idx = rs.choice(len(Ws), size=min(500, len(Ws)), replace=False)
    d = []
    for i in idx:                                            # nearest window of a DIFFERENT loved clip
        m = owner != owner[i]
        d.append(float(wdist(Ws[m], Ws[i]).min()))
    d = np.array(d)
    # a COPY sits much closer than distinct loved clips ever do: half their 10th percentile (re-uploaded twins < 2 deg
    # left out). Measured: re-animated loved key poses (run v3) land at ~12 deg; from-scratch idles at ~26 deg, which is
    # where distinct loved clips sit from each other (p10 27.4) - similar, not copied
    floor = 0.5 * float(np.percentile(d[d >= 2.0], 10))
    os.makedirs(os.path.dirname(BANK), exist_ok=True)
    np.savez(BANK, W=Ws, owner=owner, floor=floor, between=d)
    return len(Ws), floor, np.percentile(d, 50)


def gesture_events(q, k, thr=20.0):
    a = PC.from_rest(q, k)
    base = np.percentile(a, 10)
    ev, t, n = [], 0, len(a)
    while t < n:
        if a[t] - base > thr:
            s = t
            while s > 0 and a[s - 1] - base > 5:
                s -= 1
            e = t
            while e < n - 1 and a[e + 1] - base > 5:
                e += 1
            seg = a[s:e + 1] - base
            pk = int(np.argmax(seg))
            hi = np.where(seg > 0.85 * seg.max())[0]
            ev.append({"start": s, "peak": s + pk, "end": e, "rise_s": hi[0] / 60.0, "amp": float(seg.max())})
            t = e + 1
        else:
            t += 1
    return ev


STYLE_MIN_CLIPS = 30          # a band from fewer loved clips is too thin to fail anything (idle: 10, one loved at 1.1 deg/s)


def style_band(w, cal):
    """the WHOLE-BODY motion (the six joints' mean angular speeds summed, deg/s) inside the loved category's band.
    Filters, never ranks: the band is the loved MIN x 0.8 .. MAX x 1.25, so no loved clip can fail it - it catches a
    sluggish near-statue walk or a frantic flail. Measured 2026-10-16: curve-texture measures (acc flips, detail, onset
    sync, ease dips) do NOT separate loved clips from machine-eased copies per clip (AUC 0.32-0.70) - not gated."""
    body = float(w.mean(axis=0).sum())
    b = cal.get("body_motion") or {}
    if (b.get("n") or 0) < STYLE_MIN_CLIPS:
        return {"pass": True, "body_deg_s": round(body, 1), "report_only": f"only {b.get('n', 0)} loved clips in this category"}
    lo, hi = 0.8 * b["min"], 1.25 * b["max"]
    return {"pass": lo <= body <= hi, "body_deg_s": round(body, 1), "band": [round(lo, 1), round(hi, 1)],
            "loved_p50": b.get("p50"), "why": None if lo <= body <= hi else ("sluggish" if body < lo else "frantic")}


def frozen_limb(c, category):
    """the R6 vocabulary for any clip: a limb that neither SLIDES nor TURNS (both below the loved category's p10;
    kit/anim/r6_vocab.py categories) is frozen - the owner's 'the left leg doesnt just stay there' / 'the arms awkward'.
    Categories with < 30 loved clips report only"""
    import r6_vocab as RV
    try:
        cal = json.load(open(RV.OUT, encoding="utf-8")).get("categories", {}).get(category)
    except (OSError, ValueError):
        cal = None
    if not cal or cal.get("clips", 0) < 30:
        return {"pass": True, "report_only": f"{(cal or {}).get('clips', 0)} loved clips in {category}"}
    m = RV.measures(c, kick_leg="Right Leg")
    limbs = {"Right Arm": m["Right Arm"], "Left Arm": m["Left Arm"], "Right Leg": m["kick_leg"], "Left Leg": m["support_leg"]}
    # FAIL below the loved MINIMUM on both (no loved clip can fail - p10 failed 8-9 % of them, measured 2026-10-16);
    # below p10 on both is a warning
    frozen = [{"limb": l, "slide": v["slide_p95"], "turn": v["rot_range"], "loved_min": [cal[l]["slide_p95"]["min"], cal[l]["rot_range"]["min"]]}
              for l, v in limbs.items()
              if v["slide_p95"] < cal[l]["slide_p95"]["min"] and v["rot_range"] < cal[l]["rot_range"]["min"]]
    stiff = [l for l, v in limbs.items()
             if v["slide_p95"] < cal[l]["slide_p95"]["p10"] and v["rot_range"] < cal[l]["rot_range"]["p10"]]
    # a limb some loved clip keeps perfectly still (min 0 on both: the legs of a punch combo, an idle) cannot be gated
    # this way - said out loud, never passed as if checked (review 2026-10-16: combat legs were silently ungateable)
    ungated = [l for l in limbs if cal[l]["slide_p95"]["min"] <= 0 and cal[l]["rot_range"]["min"] <= 0]
    return {"pass": not frozen, "frozen": frozen, "warn_below_loved_p10": stiff, "ungated": ungated}


def check(c, category="idle", allow=()):
    """allow: gates a gesture spec deliberately waives (e.g. 'face' for think / scratch_head - a hand at the chin or on
    the head IS the gesture); waived gates are still reported, marked 'waived'"""
    cal = PC.load()["categories"].get(category) or PC.load()["categories"]["idle"]
    q, p = arrays(c)
    G = rig_geom()
    H = hands(q, p, G)
    w = PC.ang_speed(q)
    res = {}
    # readable + floaty + robot_arm, per arm gesture
    small, floaty, robot, face = [], [], [], []
    rise_p90 = (cal.get("gesture") or {}).get("rise", {}).get("p90", 0.9) if cal.get("gesture") else 0.9
    for k, arm in ((2, "Right Arm"), (3, "Left Arm")):
        for e in gesture_events(q, k):
            s, pk = e["start"], e["peak"]
            if s == 0 and pk - s < 3:                        # up from the first frame and never rising: a held pose
                continue
            travel = float(np.linalg.norm(H[arm][s:pk + 1] - H[arm][s], axis=1).max()) * PX_PER_STUD
            if travel < 8:
                small.append({"arm": arm, "t": round(s / 60, 2), "px": round(travel, 1)})
            if e["rise_s"] > rise_p90 and e["amp"] >= 40:
                floaty.append({"arm": arm, "t": round(s / 60, 2), "rise_s": round(e["rise_s"], 2), "loved_p90": rise_p90})
            if pk > s + 2:
                body = float(np.degrees(np.linalg.norm(rotvec(q[pk, :2]) - rotvec(q[s, :2]), axis=-1)).sum())
                if body < 0.08 * e["amp"]:
                    robot.append({"arm": arm, "t": round(s / 60, 2), "arm_deg": round(e["amp"], 1), "torso_head_deg": round(body, 1)})
        # the prop to the face: the HAND at face height (above the upper chest, y > 0.55 in the torso frame) while the
        # head looks at it. (Measured on the hand, not the arm's total turn: a wrist roll is not a raised arm.)
        face_dir = qrot(q[:, 1], np.array([0.0, 0.0, -1.0]))
        to_hand = H[arm] - np.array([0.0, 1.5, 0.0])
        cosang = np.einsum("ti,ti->t", face_dir, to_hand) / np.maximum(np.linalg.norm(to_hand, axis=1), 1e-9)
        near = np.linalg.norm(to_hand, axis=1) < 1.4          # a POINT reaches past the face: not a prop to the face
        bad = np.where((H[arm][:, 1] > 0.55) & (H[arm][:, 2] < -0.3) & near & (cosang > np.cos(np.radians(30))))[0]
        if len(bad) >= 6 and category not in ("combat", "dance_emote"):   # a gesture rule, not a fighting one
            face.append({"arm": arm, "t": round(bad[0] / 60, 2), "frames": int(len(bad)), "max_hand_y": round(float(H[arm][bad, 1].max()), 2)})
    res["readable"] = {"pass": not small, "small": small[:6]}
    res["floaty"] = {"pass": not floaty, "events": floaty[:6]}
    res["robot_arm"] = {"pass": not robot, "events": robot[:6]}
    res["face"] = {"pass": not face, "events": face}
    # statue
    lf = cal["life"]
    tm, hm = float(w[:, 0].mean()), float(w[:, 1].mean())
    # frozen: no joint ever turns more than 3 degrees (the loved breathing idles move 3.5-10 deg - subtle IS the loved
    # base-idle style; a near-frozen generated clip moved 2.4, a held pose 1.2). The old rule (below 0.5x the loved p10
    # speed) never fired: some loved idles are frozen, so their p10 is ~0
    # how far each joint ever turns from its OWN first pose (angle-from-rest missed arms swinging at a constant
    # distance from rest: the fall's 112 <-> 130 deg flail read as frozen)
    span = max(float(np.degrees(2 * np.arccos(np.clip(np.abs(np.einsum("tk,k->t", q[:, k], q[0, k])), -1, 1))).max()) for k in range(6))
    st = span < 3.0                                          # (a speed-percentile clause judged a calm fall loop
    # against locomotion's runs and called it frozen - removed)
    res["statue"] = {"pass": not st, "max_joint_span_deg": round(span, 1), "torso_deg_s": round(tm, 2), "head_deg_s": round(hm, 2),
                     "loved_p10": [lf["Torso"]["mean_deg_s"]["p10"], lf["Head"]["mean_deg_s"]["p10"]]}
    # jitter
    # frame-to-frame SHAKE (speed zigzagging around its own smoothed curve) above the loved category's p95 - the old
    # >6 Hz energy rule flagged fast but smooth one-shots (a 0.1 s takeoff)
    sh, lim = PC.shake(q), (cal.get("shake") or {}).get("p95", 1.3)
    res["jitter"] = {"pass": sh <= lim, "shake": round(sh, 3), "loved_p95": lim}
    res["style_band"] = style_band(w, cal)
    res["frozen_limb"] = frozen_limb(c, category)
    # copy floor
    if os.path.exists(BANK):
        bank = np.load(BANK)
        Wb, floor = bank["W"], float(bank["floor"])
        qq = q if c.get("loop") or len(q) >= WIN else np.concatenate([q, np.repeat(q[-1:], WIN - len(q), 0)])  # a short
        W, mov = windows(qq, stride=3, loop=bool(c.get("loop")))       # one-shot is held on its last frame to a window   # dense offsets: a phase-shifted copy can't slip through
        close = []
        for i, (x, m) in enumerate(zip(W, mov)):
            if m <= MOVING:                                  # near-still windows look alike everywhere: not a copy
                continue
            dd = wdist(Wb, x)
            j = int(dd.argmin())
            if dd[j] < floor:
                close.append({"t": round(i * 3 / 60, 2), "dist": round(float(dd[j]), 2), "loved": str(bank["owner"][j])})
        moving = int((mov > MOVING).sum())
        # a copy lines up with its source every few windows (the bank steps 5 frames): any 2 aligned windows = a copy
        res["copy_floor"] = {"pass": len(close) < 2, "floor": round(floor, 2), "moving_windows": moving,
                             "too_close": len(close), "examples": close[:4]}
    # allow: names (waive that gate for the whole clip) or {name: [(t0, t1, arm), ...]} - only events INSIDE a
    # window on that arm are waived (review: a whole-clip waiver let a real failure in another beat pass)
    wins = allow if isinstance(allow, dict) else {a: None for a in allow}
    for a, w in wins.items():
        if a not in res or res[a]["pass"]:
            continue
        if w is None:
            res[a] = {**res[a], "pass": True, "waived": True}
            continue
        left = [e for e in res[a].get("events", []) if not any(t0 <= e["t"] <= t1 and (arm is None or e.get("arm") == arm) for t0, t1, arm in w)]
        res[a] = {**res[a], "events": left, "pass": not left, "waived": len(left) < len(res[a].get("events", []))}
    res["pass"] = all(v["pass"] for v in res.values() if isinstance(v, dict))
    return res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["bank"]:
        n, floor, med = build_bank()
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"loved window bank: {n} moving windows, copy floor {floor:.2f} deg (between-clip median {med:.2f})"}))
    elif sys.argv[1:2] == ["check"]:
        cat = sys.argv[sys.argv.index("--category") + 1] if "--category" in sys.argv else "idle"
        r = check(json.load(open(sys.argv[2], encoding="utf-8")), cat)
        print(json.dumps(r, indent=1))
