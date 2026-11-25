"""proc_audit.py — the STYLE AUDIT of procedural clips against the owner's loved clips (statistics from the calibration
pack kit/anim/proc_calib.py; no pose is compared). Per clip and per measure, where it sits in the loved category's
distribution: below p10 / inside / above p90 -> the list of what to improve next, ranked by how far outside it is.
  measures   torso / head / arm mean speed (life), arm gesture rise + hold (snap & hold), the ease peak position
             (where in a move its top speed falls), frame-to-frame shake
    python kit/anim/proc_audit.py <clip.json>... [--category idle]   (or: from proc_audit import audit)"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_calib as PC  # noqa: E402


def where(x, pc):
    """position of x against a percentile dict: 0 inside p10..p90, else how many 'p10-p90 widths' outside (signed)"""
    if not pc or x is None:
        return None
    lo, hi = pc["p10"], pc["p90"]
    w = max(hi - lo, 1e-6)
    return 0.0 if lo <= x <= hi else round((x - hi) / w if x > hi else (x - lo) / w, 2)


def audit(c, category):
    cal = PC.load()["categories"][category]
    q = PC.rot_arrays(c)
    w = PC.ang_speed(q)
    out = {}
    for k, j in ((0, "Torso"), (1, "Head"), (2, "Right Arm"), (3, "Left Arm")):
        out[f"{j} speed"] = (round(float(w[:, k].mean()), 1), where(float(w[:, k].mean()), cal["life"][j]["mean_deg_s"]))
    ev = PC.gesture_events(q, 2) + PC.gesture_events(q, 3)
    if ev and cal.get("gesture"):
        r = float(np.median([e["rise"] for e in ev]))
        h = float(np.median([e["hold"] for e in ev]))
        out["gesture rise s"] = (round(r, 2), where(r, cal["gesture"]["rise"]))
        out["gesture hold s"] = (round(h, 2), where(h, cal["gesture"]["hold"]))
    curves = PC.ease_curves(w, 2) + PC.ease_curves(w, 3)
    if curves and cal["ease"]["peak_at"]:
        pk = float(np.median([np.argmax(cv) / 19.0 for cv in curves]))
        out["ease peak"] = (round(pk, 2), where(pk, cal["ease"]["peak_at"]))
    sh = PC.shake(q)
    out["shake"] = (round(sh, 3), where(sh, cal.get("shake")))
    flags = sorted(((abs(v[1]), k, v) for k, v in out.items() if v[1]), reverse=True)
    return {"measures": out, "outside": [f"{k}: {v[0]} ({'above' if v[1] > 0 else 'below'} loved by {abs(v[1])} widths)" for _, k, v in flags]}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cat = sys.argv[sys.argv.index("--category") + 1] if "--category" in sys.argv else "idle"
    for p in [a for a in sys.argv[1:] if a.endswith(".json")]:
        r = audit(json.load(open(p, encoding="utf-8")), cat)
        print(os.path.basename(p), json.dumps(r["outside"]))
