"""footage_measure.py — DOSSIER NUMBERS from real footage of a move (mission 04-anim 5.2 / 7: `kit anim dossier measure`
from video; MediaPipe Pose Landmarker -> 33 body landmarks per frame in WORLD coordinates, metres, y up). Numbers
only - phase timings, speeds, turns, heights - never a pose (the owner: get more data on the move; never copy poses).
The landmark extraction (mediapipe, PROPOSED in VETLOG, waits for the owner's yes) writes a landmarks file; this
measures it, so it is testable without mediapipe.
  landmarks file: {"fps": 30, "frames": [[[x, y, z] x 33], ...]}  (MediaPipe's pose_world_landmarks order)
Measures for a KICK (the leg that travels furthest is the kicking leg):
  toe_off_s   the kicking ankle leaves the floor (rises 8 cm above its start)
  peak_s      the kicking ankle's speed peak (and its speed, m/s)
  extend_s    full extension: the kicking ankle furthest OUT from the hip centre over the ground (x/z)
  land_s      the kicking ankle back within 5 cm of the floor after the extension
  hip_turn    the hip line's yaw from its start at extension (deg) + its peak turn speed (deg/s)
  ankle_height_at_extend  relative to the hip centre (m; + = above)
  and on a whole MediaPipe body - the BODY around the leg, what the owner's rejected rounds got wrong (arms, the
  support leg): the support foot's pivot (heel->toe yaw change, deg), the torso's lean AWAY from the kick at extension
  (deg, from its start), how long the hips' turn-speed peak leads the foot's (s), the kicking-side wrist below its
  shoulder (m: the counter-swing down and back) and the guard wrist below the nose (m: the hand stays at the face)
    python kit/anim/footage_measure.py <landmarks.json>   -> the numbers + a dossier 'phases' suggestion"""
import json
import sys

import numpy as np

L_HIP, R_HIP, L_ANKLE, R_ANKLE = 23, 24, 27, 28
NOSE, L_SH, R_SH, L_WRIST, R_WRIST = 0, 11, 12, 15, 16
L_HEEL, R_HEEL, L_FOOT, R_FOOT = 29, 30, 31, 32


def measure(lm, fps):
    X = np.asarray(lm, float)                               # [T, 33, 3]
    T = len(X)
    hips = 0.5 * (X[:, L_HIP] + X[:, R_HIP])
    travel = {a: float(np.linalg.norm(X[:, a] - X[0, a], axis=1).max()) for a in (L_ANKLE, R_ANKLE)}
    kick = max(travel, key=travel.get)
    ank = X[:, kick]
    floor = float(np.percentile(np.minimum(X[:, L_ANKLE, 1], X[:, R_ANKLE, 1]), 5))
    up = ank[:, 1] - floor
    sp = np.r_[0.0, np.linalg.norm(np.diff(ank, axis=0), axis=1) * fps]
    reach = np.linalg.norm((ank - hips)[:, [0, 2]], axis=1)  # OUT from the hips over the ground: a standing straight
    #                                                         leg is as far from the hip centre as a kick, never as far out
    toe_off = next((t for t in range(T) if up[t] > up[0] + 0.08), 0)
    peak = int(np.argmax(sp))
    extend = toe_off + int(np.argmax(reach[toe_off:]))
    land = next((t for t in range(extend, T) if up[t] < up[0] + 0.05), T - 1)
    hl = X[:, R_HIP] - X[:, L_HIP]
    yaw = np.degrees(np.unwrap(np.arctan2(hl[:, 2], hl[:, 0])))
    turn = yaw - yaw[0]
    turn_speed = np.abs(np.r_[0.0, np.diff(yaw)]) * fps
    out = {}
    if X.shape[1] > R_FOOT and np.abs(X[:, NOSE]).sum() > 0:  # a full MediaPipe body (the 2-landmark fixtures skip this)
        sup = L_ANKLE if kick == R_ANKLE else R_ANKLE
        heel, toe = (L_HEEL, L_FOOT) if sup == L_ANKLE else (R_HEEL, R_FOOT)
        fv = X[:, toe] - X[:, heel]
        fyaw = np.degrees(np.unwrap(np.arctan2(fv[:, 2], fv[:, 0])))
        sh = 0.5 * (X[:, L_SH] + X[:, R_SH])
        spine = sh - hips
        out_dir = (ank - hips)[extend, [0, 2]]            # AWAY = opposite where the kicking foot is at extension, over
        out_dir = out_dir / max(float(np.linalg.norm(out_dir)), 1e-6)  # the ground (the hip line tilts as the hips turn over)
        lean = np.degrees(np.arctan2(-(spine[:, [0, 2]] @ out_dir), spine[:, 1]))
        k_sh, k_wr = (R_SH, R_WRIST) if kick == R_ANKLE else (L_SH, L_WRIST)
        g_wr = L_WRIST if kick == R_ANKLE else R_WRIST
        sl = X[:, R_SH] - X[:, L_SH]
        syaw = np.degrees(np.unwrap(np.arctan2(sl[:, 2], sl[:, 0])))
        tilt = np.degrees(np.arctan2(hl[:, 1], np.linalg.norm(hl[:, [0, 2]], axis=1)))
        out = {"shoulder_turn_at_extend_deg": round(float(abs(syaw[extend] - syaw[0])), 1),  # the CHEST (what an R6
               #                                       torso shows): it lags the hips - the hip line tilts as they turn over,
               "hip_line_tilt_at_extend_deg": round(float(abs(tilt[extend])), 1),  # so the hips' yaw alone over-reads it
               "view_side": round(abs(float(out_dir[0])), 2),  # 1 = the kick goes ACROSS the picture, 0 = at the camera:
               #                                                  MediaPipe's depth (z) is its weakest axis - leans read then
               "support_foot_yaw_change_deg": round(float(abs(fyaw[extend] - fyaw[0])), 1),
               "torso_lean_away_deg": round(float(lean[extend] - lean[0]), 1),
               "hip_lead_s": round((peak - int(np.argmax(turn_speed[:peak + 1]))) / fps, 3),
               "kick_arm_wrist_below_shoulder_m": round(float(X[extend, k_sh, 1] - X[extend, k_wr, 1]), 3),
               "guard_wrist_below_nose_m": round(float(X[extend, NOSE, 1] - X[extend, g_wr, 1]), 3)}
    return {**out, "kick_leg": "right" if kick == R_ANKLE else "left", "fps": fps,
            "toe_off_s": round(toe_off / fps, 3), "peak_s": round(peak / fps, 3), "peak_foot_speed_m_s": round(float(sp[peak]), 2),
            "extend_s": round(extend / fps, 3), "land_s": round(land / fps, 3),
            "hip_turn_at_extend_deg": round(float(abs(turn[extend])), 1), "hip_turn_peak_deg_s": round(float(turn_speed.max()), 1),
            "ankle_height_at_extend_m": round(float(ank[extend, 1] - hips[extend, 1]), 3),
            "swing_s": round((extend - toe_off) / fps, 3), "recoil_s": round((land - extend) / fps, 3)}


def smooth(X, k=3):
    """a k-frame moving average per landmark (MediaPipe jitters a few cm frame to frame; speeds from raw frames spike)"""
    if k <= 1 or len(X) < k:
        return X
    pad = np.concatenate([X[:1].repeat(k // 2, 0), X, X[-1:].repeat(k // 2, 0)])
    return np.stack([pad[i:i + len(X)] for i in range(k)]).mean(0)


def kicks(frames, fps, high=-0.35, planted=-0.62, pad_s=0.5, hold_s=0.6):
    """the kick EVENTS in a long clip (an instructional video: talk, a demo, a held pose, another demo): a stretch where
    one ankle rises above `high` (m, relative to the hip centre, y up: about hip height) while the other stays below
    `planted` (a whole body, standing - not a close-up). Held poses (the foot up longer than `hold_s`: the coach showing
    the extension) and windows with missing frames are dropped - their timing is not the move's. Returns (start, end,
    leg) frame windows padded by `pad_s` each side."""
    T, out, t = len(frames), [], 0
    pad = int(pad_s * fps)
    while t < T:
        fr = frames[t]
        leg = None
        if fr is not None:
            for a, b in ((R_ANKLE, L_ANKLE), (L_ANKLE, R_ANKLE)):
                if fr[a][1] > high and fr[b][1] < planted:
                    leg = a
        if leg is None:
            t += 1
            continue
        u = t
        while u + 1 < T and frames[u + 1] is not None and frames[u + 1][leg][1] > high:
            u += 1
        s, e = max(0, t - pad), min(T - 1, u + pad)
        if (u - t + 1) / fps <= hold_s and all(frames[i] is not None for i in range(s, e + 1)):
            out.append((s, e, "right" if leg == R_ANKLE else "left"))
        t = u + max(pad, 1)
    return out


def measure_clip(d):
    """every clean kick in a landmarks file, measured (smoothed), plus the median of each number"""
    fps = float(d.get("fps", 30))
    per = []
    for s, e, leg in kicks(d["frames"], fps):
        m = measure(smooth(np.asarray(d["frames"][s:e + 1], float)), fps)
        if m["kick_leg"] != leg or m["swing_s"] <= 0 or m["recoil_s"] <= 0:
            continue                                        # the window's furthest-travelling ankle is not the raised one
        m["at_s"] = round(d.get("start_s", 0.0) + s / fps, 2)
        per.append(m)
    keys = [k for k in (per[0] if per else {}) if isinstance(per[0][k], float) and k not in ("fps", "at_s")]
    med = {k: round(float(np.median([m[k] for m in per])), 3) for k in keys}
    return per, med


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    if any(f is None for f in d["frames"]) or len(d["frames"]) > 5 * float(d.get("fps", 30)):
        per, m = measure_clip(d)                            # a long / gappy clip: find the kicks in it first
        for k in per:
            print(f"  kick at {k['at_s']} s ({k['kick_leg']}): swing {k['swing_s']} s, recoil {k['recoil_s']} s, "
                  f"foot {k['peak_foot_speed_m_s']} m/s, hips {k['hip_turn_at_extend_deg']} deg, ankle {k['ankle_height_at_extend_m']} m")
        if not per:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "no clean kick found (none, all held, or cut off)",
                              "next_action": "try another clip, or --start/--end around one kick in footage_landmarks"}))
            sys.exit(1)
        print(json.dumps({"median": m, "kicks": len(per)}, indent=1))
    else:
        m = measure(d["frames"], float(d.get("fps", 30)))
        print(json.dumps(m, indent=1))
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"footage: toe-off {m['toe_off_s']} s, foot peak {m['peak_s']} s ({m['peak_foot_speed_m_s']} m/s), "
                                 f"extension {m['extend_s']} s, land {m['land_s']} s, hips turned {m['hip_turn_at_extend_deg']} deg",
                      "next_action": "improve: put these into the move's dossier phases (real_s) with the footage as a source"}))
