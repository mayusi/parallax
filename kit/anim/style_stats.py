"""style_stats.py — locomotion STYLE statistics from the 100STYLE dataset (Mason, Starke, Komura 2022, CC BY 4.0,
zenodo.org/records/8127870, doi 10.1145/3522618 - vetted 2026-10-14, VETLOG). Mission 2026-10-14: free tools that raise
quality. Only NUMBERS are kept (no motion is copied): per style, the walk's cycle period, leg / arm swing, torso twist,
lean and bob - the same quantities the from-scratch gait profiles (kit/anim/proc_gait.py GAITS) are made of, measured on
the chords R6 can show (hip -> ankle, shoulder -> wrist: R6 has no knee or elbow).
    python kit/anim/style_stats.py <100STYLE folder>   -> assets/animations/calibration/style_stats.json"""
import glob
import json
import math
import os
import re
import sys

import numpy as np

OUT = os.path.join("assets", "animations", "calibration", "style_stats.json")
ATTRIBUTION = "100STYLE dataset - Ian Mason, Sebastian Starke, Taku Komura (2022), CC BY 4.0, doi 10.1145/3522618"


def parse_bvh(path):
    """-> (joint names, parents, offsets [J,3], channel layout per joint, frame time, motion [F, C])"""
    names, parents, offsets, chans = [], [], [], []
    stack = []
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    i = 0
    while i < len(lines):
        t = lines[i].split()
        if not t:
            i += 1
            continue
        if t[0] in ("ROOT", "JOINT"):
            names.append(t[1])
            parents.append(stack[-1] if stack else -1)
            offsets.append(None)
            chans.append([])
        elif t[0] == "End":
            names.append(names[stack[-1]] + "_end")
            parents.append(stack[-1])
            offsets.append(None)
            chans.append([])
        elif t[0] == "{":
            stack.append(len(names) - 1)
        elif t[0] == "}":
            stack.pop()
        elif t[0] == "OFFSET":
            offsets[stack[-1]] = [float(x) for x in t[1:4]]
        elif t[0] == "CHANNELS":
            chans[stack[-1]] = t[2:]
        elif t[0] == "MOTION":
            break
        i += 1
    nf = int(lines[i + 1].split()[1])
    ft = float(lines[i + 2].split()[2])
    data = np.array([[float(x) for x in l.split()] for l in lines[i + 3:i + 3 + nf] if l.strip()])
    return names, parents, np.array(offsets), chans, ft, data


def rot(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return {"X": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "Y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "Z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


def fk(names, parents, offsets, chans, data, every=2):
    """world joint positions [F, J, 3] and rotations [F, J, 3, 3] (every 2nd frame)"""
    F = data[::every]
    J = len(names)
    P = np.zeros((len(F), J, 3))
    Rw = np.zeros((len(F), J, 3, 3))
    for f, row in enumerate(F):
        k = 0
        for j in range(J):
            R = np.eye(3)
            p = offsets[j].copy()
            for ch in chans[j]:
                v = row[k]
                k += 1
                if ch.endswith("position"):
                    p[{"X": 0, "Y": 1, "Z": 2}[ch[0]]] = v
                else:
                    R = R @ rot(ch[0], v)
            if parents[j] < 0:
                Rw[f, j], P[f, j] = R, p
            else:
                Rw[f, j] = Rw[f, parents[j]] @ R
                P[f, j] = P[f, parents[j]] + Rw[f, parents[j]] @ p
    return P, Rw


def find(names, *pats):
    for pat in pats:
        for i, n in enumerate(names):
            if re.fullmatch(pat, n, re.I):
                return i
    raise KeyError(pats)


def stats(path):
    names, parents, offsets, chans, ft, data = parse_bvh(path)
    P, Rw = fk(names, parents, offsets, chans, data)
    dt = ft * 2
    hips = find(names, r"hips", r"pelvis", r"root")
    lup, lfoot = find(names, r"left_?up_?leg", r"lefthip", r"l_?thigh"), find(names, r"left_?foot", r"leftankle", r"l_?foot")
    rup, rfoot = find(names, r"right_?up_?leg", r"righthip", r"r_?thigh"), find(names, r"right_?foot", r"rightankle", r"r_?foot")
    lsh, lhand = find(names, r"left_?arm", r"leftshoulder", r"l_?upperarm"), find(names, r"left_?hand", r"leftwrist", r"l_?hand")
    neck = find(names, r"neck", r"spine2", r"spine1", r"chest")
    up = np.array([0, 1.0, 0])
    # facing: the hip line's perpendicular, smoothed; everything measured in a frame that turns with the body
    hip_line = P[:, rup] - P[:, lup]
    fwd = np.cross(hip_line, up)
    fwd[:, 1] = 0
    fwd /= np.linalg.norm(fwd, axis=1, keepdims=True) + 1e-9
    side = np.cross(up, fwd)

    def pitch(a, b):                                    # the chord a->b swing angle in the sagittal plane (deg)
        v = P[:, b] - P[:, a]
        return np.degrees(np.arctan2(np.einsum("fi,fi->f", v, fwd), -v[:, 1]))
    legL = pitch(lup, lfoot)
    armL = pitch(lsh, lhand)
    sh_line = P[:, find(names, r"right_?arm", r"rightshoulder", r"r_?upperarm")] - P[:, lsh]
    twist = np.degrees(np.arctan2(np.einsum("fi,fi->f", sh_line, fwd), np.einsum("fi,fi->f", sh_line, side + 1e-9)))
    trunk = P[:, neck] - P[:, hips]
    lean = np.degrees(np.arctan2(np.einsum("fi,fi->f", trunk, fwd), trunk[:, 1]))
    leg_len = float(np.median(np.linalg.norm(P[:, lfoot] - P[:, lup], axis=1)))
    bob = float(np.percentile(P[:, hips, 1], 95) - np.percentile(P[:, hips, 1], 5)) / max(leg_len, 1e-6)
    # cycle period: the dominant frequency of the left leg's swing
    s = legL - legL.mean()
    spec = np.abs(np.fft.rfft(s))
    fr = np.fft.rfftfreq(len(s), dt)
    k = 1 + int(np.argmax(spec[1:]))
    period = 1.0 / fr[k] if fr[k] > 0 else None
    rng = lambda x: float(np.percentile(x, 95) - np.percentile(x, 5))  # noqa: E731
    return {"period": round(period, 3) if period else None, "leg": round(rng(legL), 1), "arm": round(rng(armL), 1),
            "twist": round(rng(twist), 1), "lean": round(float(np.median(lean)), 1), "bob_per_leg": round(bob, 3),
            "speed_rel": round(float(np.linalg.norm(np.diff(P[:, hips, [0, 2]], axis=0), axis=1).mean() / dt / max(leg_len, 1e-6)), 2)}


def main(root):
    out = {"schema": 1, "attribution": ATTRIBUTION, "about": "per-style locomotion STATISTICS only (R6 chords); no motion kept",
           "styles": {}}
    files = sorted(glob.glob(os.path.join(root, "**", "*_FW.bvh"), recursive=True))      # forward walks
    for f in files:
        style = os.path.basename(f).rsplit("_", 1)[0]
        try:
            out["styles"][style] = stats(f)
        except Exception as e:
            out["styles"][style] = {"error": str(e)[:120]}
        print(style, out["styles"][style], flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"style stats: {len(out['styles'])} styles -> {OUT}"}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
