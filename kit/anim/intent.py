"""intent.py — a move's INTENT as a first-class input of the generator (the owner, 2026-11-10, loving the roundhouse
round 5: "depending on what the intention of the animation you want it to be, there's aggressive, there's calm, there is
proper, and from what I'm looking at, this is just a calm roundhouse kick").

The loved R6 library carries no intent labels (its names say slash / dash / kick / combo), so an intent is MEASURED: every
loved R6 combat limb strike that snaps (strike_style.strikes, a snap of <= SNAP_MAX frames - the loved limb strikes'
interquartile span the dossiers' snap checks already use; slower limb moves are guards and drifts, not strikes;
statistics only, never a pose) gets its TEMPO, the degrees its limb turns per second through the snap
(amp_deg / snap_frames), and the loved strikes split into thirds by it (2026-11-10, 651 strikes of 117 clips):
  calm        the slowest third (<= ~840 deg/s): a ~16-frame snap of ~95 deg
  proper      the middle third: a ~8-frame snap of ~170 deg
  aggressive  the fastest third (> ~1,750 deg/s): a ~3-frame snap of ~190 deg
Validated on the owner's own reading: the Roundhouse round 5 he called "just a calm roundhouse kick" reads calm on all
20 candidates (451-726 deg/s).
Each intent keeps its own loved bands (snap frames, anticipation, hold, overshoot), and a candidate's own main strike is
read the same way, so `kit anim candidates --intent <i>` can aim a move at an intent and refuse a candidate that reads as
another (proc_candidates). A hypothesis until the owner's verdict on an intent's sheet says otherwise.
    python kit/anim/intent.py calibrate                  -> assets/animations/calibration/intent.json
    python kit/anim/intent.py read <clip.json> ...        -> each clip's main strike and the intent it reads as"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OUT = os.path.join("assets", "animations", "calibration", "intent.json")
INTENTS = ("calm", "proper", "aggressive")
STATS = ("snap_frames", "antic_s", "antic_ratio", "hold_frames", "overshoot", "amp_deg")
SNAP_MAX = 26            # frames: a slower "strike" is a guard shift or a drift (the dossiers' snap_leg range [5, 26])
_CAL = None


def tempo(x):
    """a strike's tempo: degrees its limb turns per second through the snap"""
    return float(x["amp_deg"]) / max(int(x["snap_frames"]), 1) * 60.0


def loved_strikes():
    """every loved, game-licensed R6 combat clip's LIMB strikes (the set strike_style calibrates on: no victims, no
    knockdowns), read from the labels and the library's own clips"""
    import motion_vocab as MV
    import proc_calib as PC
    import strike_style as SS
    out, n = [], 0
    for s in open(os.path.join("_artifacts", "r6data", "labels.jsonl"), encoding="utf-8"):
        if '"augmentation": null' not in s:
            continue
        lb = json.loads(s)
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or lb["group"] != "combat" \
                or re.search(r"victim|knocked", lb["text"] or "", re.I):
            continue
        try:
            q = PC.rot_arrays(MV.load_clip(lb["id"]))
        except (OSError, ValueError, KeyError):
            continue
        if len(q) < 40:
            continue
        n += 1
        out += [{**x, "clip": lb["id"]} for x in SS.strikes(q) if x["joint"] != 0 and x["snap_frames"] <= SNAP_MAX]
    return out, n


def band(v):
    v = [float(x) for x in v if x is not None]
    return {f"p{p}": round(float(np.percentile(v, p)), 3) for p in (25, 50, 75)} if v else {}


def calibrate():
    rows, n = loved_strikes()
    if len(rows) < 30:
        raise SystemExit(f"intent calibrate: only {len(rows)} loved limb strikes")
    t = np.array([tempo(x) for x in rows])
    cuts = [float(np.percentile(t, 100 / 3)), float(np.percentile(t, 200 / 3))]
    out = {"schema": 1, "about": "the loved R6 combat limb strikes split into thirds by TEMPO (deg/s through the snap) - "
                                 "calm / proper / aggressive; statistics only (kit/anim/intent.py)",
           "clips": n, "strikes": len(rows), "tempo_cuts_deg_s": [round(c, 1) for c in cuts], "intents": {}}
    for i, name in enumerate(INTENTS):
        lo, hi = ([-1.0] + cuts)[i], (cuts + [1e9])[i]
        sel = [x for x, v in zip(rows, t) if lo < v <= hi]
        out["intents"][name] = {"n": len(sel), "tempo_deg_s": band([tempo(x) for x in sel]),
                                **{s: band([x.get(s) for x in sel]) for s in STATS}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    return out


def cal():
    global _CAL
    if _CAL is None:
        _CAL = json.load(open(OUT, encoding="utf-8"))
    return _CAL


def blade_strike(c, frame):
    """a WEAPON's strike, read on the BLADE (its Hit is by "Blade"): the blade line's sweep through its snap - the frames
    around its fastest turn near the Hit while it turns at > 15 % of that (strike_style's snap rule), its amplitude the
    angle swept. A two-handed cut turns the blade with the hips and both sliding arms while the arm joints barely
    rotate (2026-11-11, the katana: arm-joint tempi read 60-825 deg/s on cuts that swept the blade fast); one-handed,
    the blade turns with the arm, so the loved limb strikes' scale holds for both"""
    sw = c.get("sword") or {}
    tip, grip = np.asarray(sw.get("tip") or [], float), np.asarray(sw.get("grip_path") or [], float)
    if len(tip) < 8 or len(tip) != len(grip):
        return None
    d = tip - grip
    d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    w = np.degrees(np.arccos(np.clip(np.sum(d[1:] * d[:-1], axis=1), -1.0, 1.0))) * 60.0
    lo, hi = max(0, frame - 18), min(len(w), frame + 12)
    if hi <= lo:
        return None
    pk = lo + int(np.argmax(w[lo:hi]))
    a = pk
    while a > 0 and w[a - 1] > 0.15 * w[pk]:
        a -= 1
    b = pk
    while b < len(w) - 1 and w[b + 1] > 0.15 * w[pk]:
        b += 1
    amp = float(np.degrees(np.arccos(np.clip(float(d[a] @ d[b + 1]), -1.0, 1.0))))
    if amp < 20:
        return None
    return {"joint": "Blade", "frame": pk, "snap_frames": int(b + 1 - a), "amp_deg": round(amp, 1),
            "antic_s": None, "antic_ratio": None, "hold_frames": None, "overshoot": None}


def main_strike(c):
    """the clip's own main strike: its Hit's striker (events 'by'), the strike of that joint nearest the Hit - a
    weapon's (by "Blade"), the blade's own sweep (blade_strike)"""
    import proc_calib as PC
    import strike_style as SS
    hit = next((e for e in c.get("events", []) if e.get("name") == "Hit"), None)
    joint = (hit or {}).get("by")
    if joint == "Blade" and hit is not None:
        x = blade_strike(c, int(round(float(hit["t"]) * 60)))
        if x is not None:
            return x
    k = PC.JOINTS.index(joint) if joint in PC.JOINTS else None
    ss = [x for x in SS.strikes(PC.rot_arrays(c)) if x["joint"] != 0 and (k is None or x["joint"] == k)]
    if not ss:
        return None
    f = int(round(float(hit["t"]) * 60)) if hit else None
    return min(ss, key=lambda x: abs(x["frame"] - f)) if f is not None else max(ss, key=tempo)


def classify(x):
    """the intent a strike reads as: the third of the loved tempi it falls in"""
    lo, hi = cal()["tempo_cuts_deg_s"]
    v = tempo(x)
    return "calm" if v <= lo else ("proper" if v <= hi else "aggressive")


def read(c):
    x = main_strike(c)
    if x is None:
        return {"intent": None}
    return {"intent": classify(x), "tempo_deg_s": round(tempo(x), 1), **{s: x.get(s) for s in STATS}}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    cmd = a[0] if a else "help"
    if cmd == "calibrate":
        o = calibrate()
        print(json.dumps({"status": "pass", "summary": f"intent: {o['strikes']} loved limb strikes of {o['clips']} clips, "
                          f"tempo cuts {o['tempo_cuts_deg_s']} deg/s -> {OUT}", "next_action": "none - proceed"}))
    elif cmd == "read":
        for p in a[1:]:
            print(json.dumps({"clip": p, **read(json.load(open(p, encoding="utf-8")))}))
    else:
        print(__doc__)
