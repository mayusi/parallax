"""react_measure.py — the SHAPE of an R6 hit reaction in numbers (mission 04-anim, the head hook): from a clip in the
kit's R6 format, the head's rotation relative to the torso and the torso's own turn / shove, over time:
  head_peak_deg     the head's largest rotation from its starting pose (relative to the torso)
  head_to_peak_s    the head's motion onset (its speed crosses 25 % of its peak) -> its peak rotation
  head_speed_deg_s  the head's peak angular speed (relative to the torso)
  head_recover_s    the peak -> back within half the peak
  torso_peak_deg    the torso's largest rotation from its start (character space); torso_shove_studs its largest move
  torso_lag_s       the head's peak -> the torso's peak (the body follows the head when > 0)
The same numbers as kit/anim/footage_react.py takes from real footage, so a dossier can hold both: what loved R6
reactions do (statistics only, never poses) and what real heads do.
    python kit/anim/react_measure.py <clip.json> [...]"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proc_director as DR  # noqa: E402
import proc_r6 as P  # noqa: E402

J = P.JOINTS


def _ang(qa, qb):
    d = abs(float(np.dot(qa, qb)) / (np.linalg.norm(qa) * np.linalg.norm(qb)))
    return math.degrees(2 * math.acos(min(1.0, d)))


def measure(c):
    q, p = DR.arrays(c)
    fps = float(c.get("fps", 60))
    h, t0 = J.index("Head"), J.index("Torso")
    n = len(q)
    if n < 3:
        raise ValueError("react_measure: a clip needs at least 3 frames")
    hs = np.r_[0.0, [_ang(q[i, h], q[i - 1, h]) * fps for i in range(1, n)]]
    hit = next((e["t"] for e in c.get("events", []) if str(e.get("name", "")).lower() == "hit"), None)
    if hit is not None:                                        # the snap is searched AROUND the Hit (-0.1 .. +0.4 s):
        lo, hi = max(1, int((hit - 0.1) * fps)), min(n, int((hit + 0.4) * fps) + 1)   # a faster idle move or a loop
        mask = np.zeros(n, bool)                               # seam elsewhere is never taken for the hit
        mask[lo:hi] = True
        hs = np.where(mask, hs, 0.0)
    # the SNAP first (the head's fastest frame), then its peak within 0.5 s, every angle FROM THE ONSET's pose - the
    # largest angle from frame 0 in a long reaction is the idle drifting, not the hit ('1.67 s to peak')
    sp = int(np.argmax(hs))
    on = sp
    while on > 0 and hs[on - 1] > 0.25 * hs[sp]:
        on -= 1
    ref = max(0, on - 1)                                       # the last CALM pose: the onset frame has already moved
    head = np.array([_ang(q[i, h], q[ref, h]) for i in range(n)])
    tor = np.array([_ang(q[i, t0], q[ref, t0]) for i in range(n)])
    shove = np.linalg.norm(p[ref:, t0] - p[ref, t0], axis=1)
    # the snap ENDS where its speed falls back under 25 % of its peak: the peak rotation is read up to there (+2
    # frames), so a head still drifting afterwards does not slide the 'peak' to the end of the window
    end = next((k for k in range(sp + 1, n) if hs[k] < 0.25 * hs[sp]), min(n - 1, on + int(0.5 * fps)))
    win = slice(on, min(n, end + 3, on + int(0.5 * fps)))
    pk = on + int(np.argmax(head[win]))
    rec = next((k for k in range(pk, n) if head[k] < 0.5 * head[pk]), None)
    tpk = on + int(np.argmax(tor[on:min(n, on + int(1.0 * fps))]))
    # the snap's DIRECTION: the head's change from the calm pose as a rotation in the torso frame (x right, y up, z back)
    # -> nod (about x: + = chin UP, an uppercut), turn (about y), tilt (about z: ear toward the shoulder, a hook)
    qa, qb = np.asarray(q[pk, h], float), np.asarray(q[ref, h], float)
    dq = P.q_mul(qa, qb * np.array([-1.0, -1.0, -1.0, 1.0]))
    if dq[3] < 0:
        dq = -dq
    v = dq[:3]
    sv = float(np.linalg.norm(v))
    rv = v / sv * 2 * math.atan2(sv, float(dq[3])) if sv > 1e-9 else np.zeros(3)
    nod, turn, tilt = (round(math.degrees(float(x)), 1) for x in rv)
    return {"frames": n, "fps": fps, "head_peak_deg": round(float(head[pk]), 1), "head_to_peak_s": round((pk - on) / fps, 3),
            "head_speed_deg_s": round(float(hs.max()), 0),
            "head_recover_s": round((rec - pk) / fps, 3) if rec is not None else None,
            "torso_peak_deg": round(float(tor[tpk]), 1), "torso_shove_studs": round(float(shove.max()), 2),
            "torso_lag_s": round((tpk - pk) / fps, 3), "duration_s": round(n / fps, 2),
            "head_nod_deg": nod, "head_turn_deg": turn, "head_tilt_deg": tilt,
            # the share of the snap that is the chin going UP (signed: a chin-down nod is negative) - an uppercut's mark
            "head_nod_up_share": round(nod / max(1e-6, math.sqrt(nod * nod + turn * turn + tilt * tilt)), 3)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for f in sys.argv[1:]:
        print(f.replace("\\", "/").split("/")[-1], json.dumps(measure(json.load(open(f, encoding="utf-8")))))
