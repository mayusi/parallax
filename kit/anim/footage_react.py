"""footage_react.py — HIT REACTION numbers from real footage (mission 04-anim, the second action: the head hook). A fight
clip's MediaPipe TRACKS (footage_landmarks.py --poses 2) -> every sudden head snap RELATIVE TO THE TORSO, measured:
  head_peak_deg       the head's rotation from its pre-hit pose (relative to the torso frame) at its peak
  to_peak_s           onset (the snap's speed crosses 25 % of its peak) -> the peak rotation
  peak_speed_deg_s    the snap's peak angular speed
  recover_s           peak -> the head back within half its peak rotation
  torso_follow_deg    the shoulders' turn relative to the hips over the same window (the body follows the head)
  torso_lag_s         the head's peak -> the torso's peak
  yaw / roll / pitch  the snap split into turn (no), tilt (ear to shoulder) and nod (chin up / down) at the peak
Relative to the torso, so a camera cut or a whole-body turn is not a snap (and the PUNCHER's head, which turns WITH his
torso, rarely is); events need the face visible and a calm head before. Numbers only, never poses.
    python kit/anim/footage_react.py <tracks.landmarks.json> [<more> ...] [--min-speed 250] [--slowmo]"""
import json
import math
import sys

import numpy as np

NOSE, L_EAR, R_EAR, L_SH, R_SH, L_HIP, R_HIP = 0, 7, 8, 11, 12, 23, 24


def _frame(x, y_hint):
    """an orthonormal frame from an x axis and a rough y (rows of the matrix = axes)"""
    x = x / max(np.linalg.norm(x), 1e-9)
    y = y_hint - x * (y_hint @ x)
    y = y / max(np.linalg.norm(y), 1e-9)
    return np.stack([x, y, np.cross(x, y)])


def head_rel(X):
    """per frame: the head's rotation matrix in the torso frame (head: ear line + up from the ears' midpoint away from
    the nose; torso: shoulder line + the spine) -> [T, 3, 3]"""
    out = []
    for f in X:
        sh = f[R_SH] - f[L_SH]
        spine = 0.5 * (f[L_SH] + f[R_SH]) - 0.5 * (f[L_HIP] + f[R_HIP])
        tor = _frame(sh, spine)
        ear = f[R_EAR] - f[L_EAR]
        mid = 0.5 * (f[L_EAR] + f[R_EAR])
        face = f[NOSE] - mid
        up = np.cross(ear, face)                                # ear line x facing -> up (right-handed)
        hd = _frame(ear, up)
        out.append(tor @ hd.T)                                  # the head's axes in torso coordinates
    return np.asarray(out)


def ang(Ra, Rb):
    c = (np.trace(Ra @ Rb.T) - 1) / 2
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def euler_split(Rrel):
    """the head's turn (about the torso's up), tilt (about forward) and nod (about the ear line), degrees"""
    x, y, z = Rrel[:, 0], Rrel[:, 1], Rrel[:, 2]                 # the head's axes (columns) in torso coordinates
    yaw = math.degrees(math.atan2(-x[2], x[0]))
    roll = math.degrees(math.asin(max(-1.0, min(1.0, x[1]))))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -z[1]))))
    return yaw, roll, pitch


def torso_turn(X):
    sh = X[:, R_SH] - X[:, L_SH]
    hp = X[:, R_HIP] - X[:, L_HIP]
    a = np.unwrap(np.arctan2(sh[:, 2], sh[:, 0]) - np.arctan2(hp[:, 2], hp[:, 0]))
    return np.degrees(a)


def events(frames, vis, fps, min_speed=250.0, calm_s=0.25, win_s=0.6):
    """the head snaps in one track -> a list of measured reactions"""
    good = [i for i, f in enumerate(frames) if f is not None]
    if len(good) < int(fps):
        return []
    out = []
    # contiguous runs without gaps (a gap = an occlusion or a lost track: never measure across it)
    runs, s = [], good[0]
    for a, b in zip(good, good[1:] + [None]):
        if b is None or b != a + 1:
            runs.append((s, a))
            s = b
    for s, e in runs:
        if e - s + 1 < int(fps * (calm_s + win_s)):
            continue
        X = np.asarray(frames[s:e + 1], float)
        V = [vis[i] for i in range(s, e + 1)]
        X = np.stack([np.mean(X[max(0, i - 1):i + 2], axis=0) for i in range(len(X))])  # 3-frame smoothing
        R = head_rel(X)
        sp = np.r_[0.0, [ang(R[i], R[i - 1]) * fps for i in range(1, len(R))]]
        tt = torso_turn(X)
        calm, win = int(calm_s * fps), int(win_s * fps)
        i = calm
        while i < len(R) - win:
            if sp[i] < min_speed or sp[i] < sp[i - 1] or sp[i] < sp[i + 1]:
                i += 1
                continue
            pre = sp[i - calm:i - int(0.05 * fps)] if i - int(0.05 * fps) > i - calm else sp[i - calm:i]
            face = min(min(V[k][j] for j in (NOSE, L_EAR, R_EAR)) if V[k] else 0.0 for k in range(i - calm, i + win))
            if pre.mean() > 0.35 * sp[i] or face < 0.3:
                i += 1
                continue
            on = i
            while on > i - calm and sp[on - 1] > 0.25 * sp[i]:
                on -= 1
            base = R[max(0, on - int(0.1 * fps)):on + 1]
            b0 = base[len(base) // 2]
            rot = np.array([ang(R[k], b0) for k in range(on, min(len(R), on + win))])
            pk = int(np.argmax(rot))
            peak = float(rot[pk])
            rec = next((k for k in range(pk, len(rot)) if rot[k] < 0.5 * peak), None)
            Rp = b0.T @ R[on + pk]
            yaw, roll, pitch = euler_split(Rp)
            tw = tt[on:on + len(rot)] - tt[on]
            tpk = int(np.argmax(np.abs(tw)))
            out.append({"t": round((s + i) / fps, 2), "head_peak_deg": round(peak, 1), "to_peak_s": round(pk / fps, 3),
                        "peak_speed_deg_s": round(float(sp[i]), 0),
                        "recover_s": round((rec - pk) / fps, 3) if rec is not None else None,
                        "torso_follow_deg": round(float(abs(tw[tpk])), 1), "torso_lag_s": round((tpk - pk) / fps, 3),
                        "yaw": round(yaw, 1), "roll": round(roll, 1), "pitch": round(pitch, 1)})
            i = on + pk + max(1, int(0.3 * fps))
    return out


def measure_file(d, min_speed=250.0):
    fps = float(d.get("fps", 30))
    tracks = d.get("tracks") or [{"start": 0, "frames": d["frames"], "vis": d.get("vis") or [None] * len(d["frames"])}]
    ev = []
    for k, tr in enumerate(tracks):
        for e in events(tr["frames"], tr.get("vis") or [None] * len(tr["frames"]), fps, min_speed):
            e["t"] = round(e["t"] + tr["start"] / fps + d.get("start_s", 0.0), 2)
            e["track"] = k
            ev.append(e)
    return sorted(ev, key=lambda e: e["t"])


def summary(ev, keys=("head_peak_deg", "to_peak_s", "peak_speed_deg_s", "recover_s", "torso_follow_deg", "torso_lag_s")):
    out = {}
    for k in keys:
        v = [e[k] for e in ev if e.get(k) is not None]
        if v:
            out[k] = {"p10": round(float(np.percentile(v, 10)), 3), "p50": round(float(np.median(v)), 3),
                      "p90": round(float(np.percentile(v, 90)), 3), "n": len(v)}
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    ms = float(a[a.index("--min-speed") + 1]) if "--min-speed" in a else 250.0
    files = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] != "--min-speed")]
    allev = []
    for f in files:
        ev = measure_file(json.load(open(f, encoding="utf-8")), ms)
        for e in ev:
            e["clip"] = f.replace("\\", "/").split("/")[-1].split(".")[0]
        allev += ev
        print(f"{f}: {len(ev)} head snap(s)")
    print(json.dumps(summary(allev), indent=1))
    print(json.dumps({"schema": 1, "status": "pass" if allev else "fail",
                      "summary": f"{len(allev)} head snaps relative to the torso over {len(files)} clip(s)",
                      "next_action": "look at the strongest few by eye (a frame strip), then put the numbers in the dossier"}))
