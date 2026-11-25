"""strike_style.py — the SHAPE of a strike in the owner's loved R6 combat clips (statistics only, no poses; owner
2026-10-14: our dossier kick was 'not bad but not a professional animator styled kick'). Real timing (biomechanics) is
one layer; the pro-animator layer is how a strike is SHAPED: the wind-up against it, how few frames the snap takes, the
held extreme, the overshoot-and-settle, which part leads. Per strike (a joint's angular speed peak >= 600 deg/s), on the
joint's own strike axis:
  antic_ratio   wind-up travel against the strike / the strike's travel        antic_s   the wind-up's duration
  snap_frames   frames from the strike's start (speed < 15 % of peak) to its end (same)
  peak_at       where in the snap the speed peaks (0 = at once: fast-in)       amp_deg   the strike's travel
  hold_frames   frames the extreme is held (within 10 % of the travel, slow) after the snap
  overshoot     how far the extreme sits past where it settles (/ travel)     torso_lead  torso peak before the limb's (frames)
    python kit/anim/strike_style.py build            -> assets/animations/calibration/strike_style.json
    python kit/anim/strike_style.py <clip.json>...   -> the same measures for our clips, against the loved percentiles"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_calib as PC  # noqa: E402
import proc_r6 as P  # noqa: E402

OUT = os.path.join("assets", "animations", "calibration", "strike_style.json")
FPS = 60
MEASURES = ("antic_ratio", "antic_s", "snap_frames", "peak_at", "amp_deg", "hold_frames", "overshoot", "torso_lead")


def strikes(q, joints=(2, 3, 4, 5, 0), thr=600.0):
    w = PC.ang_speed(q)                                    # [T-1, 6]
    out = []
    for k in joints:
        s = w[:, k]
        peaks = [t for t in range(1, len(s) - 1) if s[t] >= thr and s[t] >= s[t - 1] and s[t] > s[t + 1]]
        taken = []
        for t in sorted(peaks, key=lambda t: -s[t]):        # strongest first, >= 0.25 s apart
            if all(abs(t - u) >= 15 for u in taken):
                m = measure(q, w, k, t)
                if m:                                         # a peak that cannot be measured must not block its
                    taken.append(t)                           # neighbours (a spin's plateau has several peaks)
                    out.append(m)
    return out


def measure(q, w, k, t):
    T = len(q)
    ax = P.q_log(P.q_mul(q[t + 1, k], P.q_inv(q[t, k])))
    if np.linalg.norm(ax) < 1e-9:
        return None
    ax = ax / np.linalg.norm(ax)
    lo, hi = max(0, t - 36), min(T, t + 40)
    s = np.array([np.degrees(2 * float(P.q_log(P.q_mul(q[f, k], P.q_inv(q[t, k]))) @ ax)) for f in range(lo, hi)])
    s = np.unwrap(s, period=360.0)                         # a spin past 180 deg wrapped (the log flips) - unwrap it
    sp = w[lo:min(hi, T - 1), k]
    pk = t - lo
    a = pk
    while a > 0 and sp[a - 1] > 0.15 * sp[pk]:
        a -= 1
    b = pk
    while b < len(sp) - 1 and sp[b + 1] > 0.15 * sp[pk]:
        b += 1
    b = min(b + 1, len(s) - 1)
    amp = s[b] - s[a]
    if amp < 20:
        return None
    pre = s[max(0, a - 30):a + 1]
    j = int(np.argmax(pre))
    antic = float(pre[j] - s[a])
    tail = s[b:b + 30]
    hold = 0
    while hold < len(tail) and abs(tail[hold] - s[b]) < 0.1 * amp:
        hold += 1
    settle = float(np.median(s[min(len(s) - 1, b + 6):min(len(s), b + 18)])) if b + 6 < len(s) else float(s[b])
    tw = w[max(0, t - 12):min(T - 1, t + 13), 0]
    lead = (12 - int(np.argmax(tw))) if k != 0 and len(tw) == 25 and tw.max() > 150 else None
    return {"joint": k, "frame": t, "antic_ratio": round(antic / amp, 3), "antic_s": round((len(pre) - 1 - j) / FPS, 3),
            "snap_frames": int(b - a), "peak_at": round((pk - a) / max(b - a, 1), 3), "amp_deg": round(float(amp), 1),
            "hold_frames": int(hold), "overshoot": round(float(s[b] - settle) / amp, 3), "torso_lead": lead}


def build():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import translate_test as TT
    allS, n = [], 0
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or lb["group"] != "combat" or re.search(r"victim|knocked", lb["text"] or "", re.I):
            continue
        c = TT.loved_clip(lb["id"])[0]
        q = PC.rot_arrays(c)
        if len(q) < 40:
            continue
        n += 1
        allS += strikes(q)
    out = {"schema": 1, "about": "loved R6 COMBAT strike shapes - statistics only (no poses), owner 2026-10-14", "clips": n,
           "strikes": len(allS), "limb": {}, "torso": {}}
    for name, sel in (("limb", [x for x in allS if x["joint"] != 0]), ("torso", [x for x in allS if x["joint"] == 0])):
        for m in MEASURES:
            v = [x[m] for x in sel if x.get(m) is not None]
            out[name][m] = PC.pct(v)
        out[name]["n"] = len(sel)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(json.dumps({"status": "pass", "summary": f"{n} loved combat clips, {len(allS)} strikes -> {OUT}"}))


def compare(c):
    cal = json.load(open(OUT, encoding="utf-8"))
    rows = []
    for x in strikes(PC.rot_arrays(c)):
        grp = cal["torso" if x["joint"] == 0 else "limb"]
        far = {m: x[m] for m in MEASURES if x.get(m) is not None and grp[m] and not (grp[m]["p10"] <= x[m] <= grp[m]["p90"])}
        rows.append({**x, "outside_loved_p10_p90": far})
    return rows


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "build":
        build()
    else:
        for p in sys.argv[1:]:
            for r in compare(json.load(open(p, encoding="utf-8"))):
                print(os.path.basename(p), PC.JOINTS[r["joint"]], json.dumps({k: r[k] for k in MEASURES}), "OUTSIDE:", r["outside_loved_p10_p90"])
