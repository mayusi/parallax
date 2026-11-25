"""proc_calib.py — the CALIBRATION PACK for procedural R6 (plan: board/plans/archive/2026-10-13-proc-from-scratch-plan.md, step 1).
The owner's loved clips are used ONLY as measurement here: how fast, how long, how lagged, how lively loved R6 motion
is, per category. No pose is stored. The director, the springs and the gates read this file.

Per category (the label group of the loved, game-licensed clips: idle, locomotion, combat, dance_emote, other):
  gesture      arm raise events (>= 40 deg from the clip's low baseline): rise / hold / return seconds, amplitude,
               peak speed - percentiles (p10 p25 p50 p75 p90)
  head_turn    head events (>= 15 deg): duration and peak speed
  lag          how many frames each joint's angular-speed signal trails the torso's (cross-correlation peak in +-20
               frames; + = later than the torso), per clip, percentiles
  ease         transitions between speed minima of an arm (>= 15 deg): the time-normalised speed curve (20 samples, peak 1)
               - the mean curve, the peak position percentiles
  body_motion  the six joints' mean speeds summed per clip: n, min, max, percentiles (the style_band gate)
  life         per joint: mean / p95 angular speed (deg/s) and the share of speed energy in bands
               (<1 Hz, 1-3, 3-6, >6 Hz) - percentiles over clips
    python kit/anim/proc_calib.py build   -> assets/animations/calibration/proc_calib.json
    from proc_calib import load"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OUT = os.path.join("assets", "animations", "calibration", "proc_calib.json")
JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
PCT = (10, 25, 50, 75, 90, 95)
FPS = 60


def pct(x):
    x = np.asarray(x, float)
    return {f"p{p}": round(float(np.percentile(x, p)), 3) for p in PCT} if len(x) else None


def rot_arrays(c):
    """quats [T, 6, 4] in JOINTS order (missing joints = identity)"""
    T = len(c["times"])
    q = np.zeros((T, 6, 4))
    q[..., 3] = 1.0
    for k, j in enumerate(JOINTS):
        if j in c["joints"]:
            q[:, k] = np.array([f[:4] for f in c["joints"][j]["frames"]], float)
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def ang_speed(q):
    """[T-1, 6] deg/s between consecutive frames"""
    d = np.abs(np.einsum("tki,tki->tk", q[1:], q[:-1]))
    return np.degrees(2 * np.arccos(np.clip(d, -1, 1))) * FPS


def from_rest(q, k):
    return np.degrees(2 * np.arccos(np.clip(np.abs(q[:, k, 3]), -1, 1)))


def gesture_events(q, k, thr=40.0):
    a = from_rest(q, k)
    base = np.percentile(a, 10)
    n, t, ev = len(a), 0, []
    while t < n:
        if a[t] - base > thr:
            s = t
            while s > 0 and a[s - 1] - base > 10:
                s -= 1
            e = t
            while e < n - 1 and a[e + 1] - base > 10:
                e += 1
            if s > 0 and e < n - 1:
                seg = a[s:e + 1] - base
                peak = seg.max()
                hi = np.where(seg > 0.85 * peak)[0]
                sp = np.abs(np.diff(a[s:e + 1])) * FPS
                ev.append({"rise": hi[0] / FPS, "hold": (hi[-1] - hi[0]) / FPS, "ret": (len(seg) - 1 - hi[-1]) / FPS,
                           "amp": float(peak), "peak_speed": float(sp.max()) if len(sp) else 0.0})
            t = e + 1
        else:
            t += 1
    return ev


def lags(w):
    """frames each joint's speed trails the torso's (cross-correlation peak, +-20)"""
    out = {}
    a = w[:, 0] - w[:, 0].mean()
    if a.std() < 1e-6:
        return out
    for k in range(1, 6):
        b = w[:, k] - w[:, k].mean()
        if b.std() < 1e-6:
            continue
        best, arg = -9, 0
        for L in range(-20, 21):
            x, y = (a[:len(a) - L], b[L:]) if L >= 0 else (a[-L:], b[:len(b) + L])
            if len(x) < 20:
                continue
            r = float(np.corrcoef(x, y)[0, 1])
            if r > best:
                best, arg = r, L
        if best > 0.3:
            out[JOINTS[k]] = arg
    return out


def ease_curves(w, k):
    s = w[:, k]
    mins = [t for t in range(1, len(s) - 1) if s[t] <= s[t - 1] and s[t] <= s[t + 1]]
    curves = []
    for a, b in zip(mins[:-1], mins[1:]):
        if b - a < 6 or s[a:b].sum() / FPS < 15:
            continue
        seg = s[a:b + 1]
        x = np.interp(np.linspace(0, len(seg) - 1, 20), np.arange(len(seg)), seg)
        curves.append(x / max(x.max(), 1e-9))
    return curves


def shake(q):
    """frame-to-frame shake of torso + head: the RMS of the angular speed around its own smoothed curve (Gaussian,
    sigma 3 frames) over the mean speed, the larger of the two. Fast but SMOOTH moves score low; zigzag scores high"""
    w = ang_speed(q)[:, :2]
    out = [0.0]
    g = np.exp(-0.5 * (np.arange(-9, 10) / 3.0) ** 2)
    g /= g.sum()
    for k in range(2):
        s = w[:, k]
        if len(s) < 12 or s.mean() < 1:
            continue
        sm = np.convolve(np.pad(s, 9, mode="edge"), g, "valid")
        out.append(float(np.sqrt(np.mean((s - sm) ** 2)) / max(s.mean(), 10.0)))   # >= 10 deg/s: on a nearly still
        # clip a small SMOOTH motion (a 0.7-deg nod per foot tap) divided by a tiny mean speed read as violent shake
    return max(out)


def bands(w, k):
    s = w[:, k] - w[:, k].mean()
    if len(s) < 32:
        return None
    P = np.abs(np.fft.rfft(s)) ** 2
    f = np.fft.rfftfreq(len(s), 1 / FPS)
    tot = P[1:].sum()
    if tot <= 0:
        return None
    return [float(P[(f >= lo) & (f < hi)].sum() / tot) for lo, hi in ((0.01, 1), (1, 3), (3, 6), (6, 31))]


def build():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import translate_test as TT
    cats = {}
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or re.search(r"victim|knocked", lb["text"] or "", re.I):
            continue
        c = TT.loved_clip(lb["id"])[0]
        q = rot_arrays(c)
        if len(q) < 40:
            continue
        w = ang_speed(q)
        if w.sum() < 1:
            continue
        g = cats.setdefault(lb["group"], {"clips": 0, "gesture": [], "head": [], "lag": {}, "ease": [], "shake": [], "body": [],
                                          "life": {j: [] for j in JOINTS}})
        g["clips"] += 1
        g["shake"].append(shake(q))
        g["body"].append(float(w.mean(axis=0).sum()))        # whole-body motion: the six joints' mean speeds summed
        for k in (2, 3):
            g["gesture"] += gesture_events(q, k)
            g["ease"] += ease_curves(w, k)
        g["head"] += [e for e in gesture_events(q, 1, 15.0)]
        for j, L in lags(w).items():
            g["lag"].setdefault(j, []).append(L)
        for k, j in enumerate(JOINTS):
            b = bands(w, k)
            g["life"][j].append([float(w[:, k].mean()), float(np.percentile(w[:, k], 95))] + (b or [np.nan] * 4))
    out = {"schema": 1, "about": "loved-clip STATISTICS only (no poses) - plan 2026-10-13 step 1", "categories": {}}
    for name, g in cats.items():
        ge = g["gesture"]
        E = np.array(g["ease"]) if g["ease"] else np.zeros((0, 20))
        life = {}
        for j, rows in g["life"].items():
            R = np.array(rows, float)
            life[j] = {"mean_deg_s": pct(R[:, 0]), "p95_deg_s": pct(R[:, 1]),
                       "bands": [round(float(np.nanmedian(R[:, 2 + i])), 3) for i in range(4)]}
        out["categories"][name] = {
            "clips": g["clips"],
            "gesture": {"n": len(ge), **{key: pct([e[key] for e in ge]) for key in ("rise", "hold", "ret", "amp", "peak_speed")}} if ge else None,
            "head_turn": {"n": len(g["head"]), "rise": pct([e["rise"] for e in g["head"]]), "peak_speed": pct([e["peak_speed"] for e in g["head"]])} if g["head"] else None,
            "lag_frames": {j: pct(v) for j, v in g["lag"].items()},
            "ease": {"n": len(E), "mean_curve": [round(float(x), 3) for x in E.mean(0)] if len(E) else None,
                     "peak_at": pct(E.argmax(1) / 19.0) if len(E) else None},
            "life": life,
            "shake": pct(g["shake"]),
            # the whole-body motion band (proc_gates.style_band): min / max kept - a gate inside them never fails a loved clip
            "body_motion": {"n": len(g["body"]), "min": round(float(min(g["body"])), 2), "max": round(float(max(g["body"])), 2),
                            **(pct(g["body"]) or {})},
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    return out


_C = None


def load():
    global _C
    if _C is None:
        _C = json.load(open(OUT, encoding="utf-8"))
    return _C


# what the loved library holds per MOVE KIND inside a category (measured 2026-10-16; the text labels are unreliable -
# 'kick' matches dances like the Kazotsky Kick and dash descriptions - so a kind is counted only when verified)
KINDS = {
    "kick": {"loved": 0, "note": "no real kick: by motion, the loved combat clips with a foot up near the hip are rolls, slams, "
                                 "knockdowns and get-ups - the MOVE DOSSIER carries the kick's numbers (real footage, biomechanics)"},
    "knee": {"loved": 0, "note": "no real knee strike in the loved library - the dossier carries the numbers"},
    "sword": {"loved": 8, "note": "8 loved sword clips (slashes) in the combat group, by label"},
    "punch": {"loved": 5, "note": "5 loved clips named as punches; most loved combat strikes are unnamed m1 combos (strike_style measures all 1066 strikes)"},
}
COVERAGE_MIN = 10


def coverage(category, kind=None):
    """-> (line, warn): how many loved clips back the calibration for this category (+ kind)"""
    cal = load()["categories"].get(category)
    n = (cal or {}).get("clips", 0)
    line = f"calibration: {category} {n} loved clips"
    warn = n < COVERAGE_MIN
    if kind:
        k = KINDS.get(kind)
        if k is None:
            line += f"; kind '{kind}': not measured yet (count it before trusting the category numbers for it)"
            warn = True
        else:
            line += f"; kind '{kind}': {k['loved']} loved - {k['note']}"
            warn = warn or k["loved"] < COVERAGE_MIN
    return line, warn


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["coverage"]:
        a = sys.argv[2:]
        line, warn = coverage(a[0], a[a.index("--kind") + 1] if "--kind" in a else None)
        print(json.dumps({"schema": 1, "status": "pass", "summary": line + (" (UNDER 10: thin data)" if warn else ""),
                          "next_action": ("improve: the numbers for this come from its MOVE DOSSIER (lune run kit anim dossier new <move>)"
                                          if warn else "none - proceed"), "warn": warn}))
        sys.exit(0)
    if sys.argv[1:2] == ["build"]:
        o = build()
        for name, g in o["categories"].items():
            ge = g["gesture"] or {}
            print(name, g["clips"], "clips | gesture n", ge.get("n"), "rise", (ge.get("rise") or {}).get("p50"), "hold", (ge.get("hold") or {}).get("p50"),
                  "| lag", {j: v["p50"] for j, v in g["lag_frames"].items()}, "| ease peak", (g["ease"]["peak_at"] or {}).get("p50"),
                  "| torso mean", g["life"]["Torso"]["mean_deg_s"]["p50"], "head", g["life"]["Head"]["mean_deg_s"]["p50"])
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"calibration pack: {len(o['categories'])} categories -> {OUT}"}))
