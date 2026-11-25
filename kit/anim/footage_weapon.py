"""footage_weapon.py — DOSSIER NUMBERS for a WEAPON move from real footage (the governor's re-plan 2026-11-05, the owner:
"make sure ur using the procedural pipeline properly": the character-action drill and the sword tricks were eyeballed, never
measured). The same MediaPipe landmarks file as footage_measure.py (a kick); numbers only, never a pose.
  swing (--kind swing): every STROKE of the faster wrist (the sword hand) - its speed peaks over half the clip's top
        speed, at least 0.2 s apart. Per stroke:
          antic_s       the wind-up: from the wrist's last slow moment before the stroke to the stroke's start
          stroke_s      the stroke: the wrist above 40 % of its peak speed around the peak
          hold_s        the MOVING hold after it: the wrist under 25 % of the peak (it drifts, it does not stop)
          wrist_peak_m_s, reach  (the wrist's distance from its shoulder at the peak / the arm's length: 1 = straight)
          chest_turn_deg + chest_peak_deg_s   the shoulder line's yaw over the stroke and its peak turn speed
          hip_turn_deg  the hip line's yaw over the stroke; chest_lead_s how long the chest's turn peak leads the wrist's
          crouch        the hips' drop under their standing height (the clip's 90th percentile; a jump is not the stand) / the leg's length (0 = standing tall)
          lean_deg      the trunk's tilt off vertical at the peak
          stance        the ankles' distance at the peak / the leg's length (a wide, staggered stance > 0.6)
  spin  (--kind spin):  the shoulder line's yaw, unwrapped: turns_per_s (fastest 0.25 s window), turns, and over the
        spin frames (turning at >= half that) both wrists' horizontal REACH from the body's centre / the arm's length
        (the blade arm out at arm's length ~1; the other arm: where it goes) and their height against the shoulders
    python kit/anim/footage_weapon.py <landmarks.json> --kind swing|spin [--start S --end S]  -> the numbers (JSON)"""
import json
import math
import sys

import numpy as np

L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK = 23, 24, 25, 26, 27, 28


def fill(frames):
    """gaps (None frames) linearly filled from their neighbours -> [T, 33, 3]"""
    ok = [i for i, f in enumerate(frames) if f is not None]
    if len(ok) < 4:
        raise SystemExit("footage_weapon: fewer than 4 frames with a body")
    X = np.full((len(frames), 33, 3), np.nan)
    for i in ok:
        X[i] = np.asarray(frames[i], float)
    t = np.arange(len(frames))
    for a in range(33):
        for k in range(3):
            X[:, a, k] = np.interp(t, ok, X[ok, a, k])
    return X


def smooth(x, w=2):
    if len(x) <= 2 * w:
        return x
    pad = np.concatenate([x[:1].repeat(w, 0), x, x[-1:].repeat(w, 0)])
    k = np.ones(2 * w + 1) / (2 * w + 1)
    return np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 0, pad)


def yaw_of(a, b):
    v = b - a
    return np.unwrap(np.arctan2(v[:, 2], v[:, 0]))


def lengths(X):
    arm = float(np.median(np.linalg.norm(X[:, R_SH] - X[:, R_EL], axis=1) + np.linalg.norm(X[:, R_EL] - X[:, R_WR], axis=1)))
    leg = float(np.median(np.linalg.norm(X[:, R_HIP] - X[:, R_KNEE], axis=1) + np.linalg.norm(X[:, R_KNEE] - X[:, R_ANK], axis=1)))
    return max(arm, 1e-3), max(leg, 1e-3)


def swing(X, fps):
    X = smooth(X)
    T = len(X)
    arm, leg = lengths(X)
    sp = {w: np.r_[0.0, np.linalg.norm(np.diff(X[:, w], axis=0), axis=1) * fps] for w in (L_WR, R_WR)}
    wr = max(sp, key=lambda w: np.percentile(sp[w], 95))
    sh = R_SH if wr == R_WR else L_SH
    s = sp[wr]
    top = float(s.max())
    peaks = [i for i in range(1, T - 1) if s[i] >= s[i - 1] and s[i] > s[i + 1] and s[i] >= 0.5 * top]
    keep = []
    for i in sorted(peaks, key=lambda i: -s[i]):              # the strongest first, then any 0.2 s clear of them
        if all(abs(i - j) >= 0.2 * fps for j in keep):
            keep.append(i)
    chest = yaw_of(X[:, L_SH], X[:, R_SH])
    hips = yaw_of(X[:, L_HIP], X[:, R_HIP])
    cw = np.r_[0.0, np.abs(np.diff(chest))] * fps
    hipc = 0.5 * (X[:, L_HIP] + X[:, R_HIP])
    shc = 0.5 * (X[:, L_SH] + X[:, R_SH])
    hip_h = hipc[:, 1] - np.minimum(X[:, L_ANK, 1], X[:, R_ANK, 1])
    out = []
    for pk in sorted(keep):
        a = pk
        while a > 0 and s[a - 1] >= 0.4 * s[pk]:
            a -= 1
        z = pk
        while z < T - 1 and s[z + 1] >= 0.4 * s[pk]:
            z += 1
        w0 = a                                             # the wind-up: back to the last slow frame (< 15 % of the peak)
        while w0 > 0 and s[w0 - 1] >= 0.15 * s[pk] and a - w0 < fps:
            w0 -= 1
        h0 = z                                             # past the slow-down (25-40 %), then the hold under 25 %
        while h0 < T - 1 and s[h0 + 1] >= 0.25 * s[pk] and h0 - z < 0.2 * fps:
            h0 += 1
        h = h0
        while h < T - 1 and s[h + 1] < 0.25 * s[pk]:
            h += 1
        lo, hi = max(0, a - int(0.15 * fps)), min(T - 1, z + int(0.1 * fps))
        trunk = shc[pk] - hipc[pk]
        out.append({
            "at_s": round(pk / fps, 3), "antic_s": round((a - w0) / fps, 3), "stroke_s": round((z - a + 1) / fps, 3),
            "hold_s": round((h - h0) / fps, 3), "wrist_peak_m_s": round(float(s[pk]), 2),
            "reach": round(float(np.linalg.norm(X[pk, wr] - X[pk, sh]) / arm), 2),
            "chest_turn_deg": round(math.degrees(abs(chest[hi] - chest[lo])), 1),
            "chest_peak_deg_s": round(math.degrees(float(cw[lo:hi + 1].max())), 0),
            "hip_turn_deg": round(math.degrees(abs(hips[hi] - hips[lo])), 1),
            "chest_lead_s": round((pk - (lo + int(np.argmax(cw[lo:hi + 1])))) / fps, 3),
            "crouch": round(float(max(0.0, np.percentile(hip_h, 90) - hip_h[pk]) / leg), 2),
            "lean_deg": round(math.degrees(math.atan2(math.hypot(trunk[0], trunk[2]), abs(trunk[1]))), 1),
            "stance": round(float(np.linalg.norm(X[pk, L_ANK] - X[pk, R_ANK]) / leg), 2)})
    return {"kind": "swing", "hand": "right" if wr == R_WR else "left", "strokes": out,
            "median": {k: round(float(np.median([o[k] for o in out])), 3) for k in out[0] if k != "at_s"} if out else {}}


def spin(X, fps):
    X = smooth(X)
    T = len(X)
    arm, _ = lengths(X)
    chest = yaw_of(X[:, L_SH], X[:, R_SH])
    w = max(1, int(round(0.25 * fps)))
    rate = np.abs(chest[w:] - chest[:-w]) / (w / fps) / (2 * math.pi) if T > w else np.zeros(1)
    peak = float(rate.max()) if len(rate) else 0.0
    h = max(1, int(round(0.05 * fps)))
    inst = np.array([abs(chest[min(T - 1, i + h)] - chest[max(0, i - h)]) / ((min(T - 1, i + h) - max(0, i - h)) / fps)
                     / (2 * math.pi) for i in range(T)])
    on = np.where(inst >= 0.5 * peak)[0]
    ctr = 0.5 * (X[:, L_HIP] + X[:, R_HIP] + X[:, L_SH] + X[:, R_SH]) / 2
    shy = 0.5 * (X[:, L_SH, 1] + X[:, R_SH, 1])
    reach = {n: np.linalg.norm((X[:, i] - ctr)[:, [0, 2]], axis=1) / arm for n, i in (("left", L_WR), ("right", R_WR))}
    blade = max(reach, key=lambda n: float(np.median(reach[n][on])) if len(on) else 0.0)
    other = "left" if blade == "right" else "right"
    wi = {"left": L_WR, "right": R_WR}
    return {"kind": "spin", "turns_per_s": round(peak, 2), "turns": round(float(abs(chest[-1] - chest[0]) / (2 * math.pi)), 2),
            "spin_s": round(len(on) / fps, 3), "blade_hand": blade,
            "blade_reach": round(float(np.median(reach[blade][on])), 2) if len(on) else None,
            "other_reach": round(float(np.median(reach[other][on])), 2) if len(on) else None,
            "blade_height_m": round(float(np.median((X[:, wi[blade], 1] - shy)[on])), 2) if len(on) else None,
            "other_height_m": round(float(np.median((X[:, wi[other], 1] - shy)[on])), 2) if len(on) else None}


def run(path, kind, start=None, end=None):
    d = json.load(open(path, encoding="utf-8"))
    fps = float(d.get("fps", 30))
    fr = d["frames"]
    a = int(round((start or 0) * fps)) if start is not None else 0
    z = int(round(end * fps)) if end is not None else len(fr)
    X = fill(fr[a:z])
    m = swing(X, fps) if kind == "swing" else spin(X, fps)
    m["source"] = d.get("source") or path
    m["window_s"] = [round((d.get("start_s") or 0) + a / fps, 3), round((d.get("start_s") or 0) + z / fps, 3)]
    return m


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    opt = lambda k: float(a[a.index(k) + 1]) if k in a else None  # noqa: E731
    kind = a[a.index("--kind") + 1] if "--kind" in a else "swing"
    m = run(a[0], kind, opt("--start"), opt("--end"))
    print(json.dumps(m, indent=1))
    ok = bool(m.get("strokes")) if kind == "swing" else m["turns_per_s"] > 0.5
    print(json.dumps({"schema": 1, "status": "pass" if ok else "fail",
                      "summary": (f"footage ({kind}): {len(m['strokes'])} stroke(s), median {m['median']}" if kind == "swing"
                                  else f"footage (spin): {m['turns_per_s']} turns/s, {m['turns']} turns, blade reach {m['blade_reach']}, other arm {m['other_reach']}"),
                      "next_action": "improve: put these into the move's dossier (sources[].measured + checks)" if ok
                      else "no stroke / spin found: cut the clip round one move (--start/--end)"}))
    sys.exit(0 if ok else 1)
