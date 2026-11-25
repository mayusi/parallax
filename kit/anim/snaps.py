"""snaps.py — find and fix SNAPS: single frames where a joint jumps much further than its neighbours.

    python kit/anim/snaps.py <clip.json> [--fix --out <clip.json>] [--ratio 2.2] [--floor 9]

Why (2026-10-11): the owner loved a community sprint on their rig "but the legs sometimes snap". Measured at its
native 60 fps, the right leg turned 15, then 37, then 4 degrees in three frames: one frame carried the motion of
three. An animator fixes that in the graph editor by SPACING, not by moving the pose: the path stays, the jump is
spread over the frames around it. That is what this does:
- per joint, the per-frame motion = rotation (degrees) + translation (studs x 30, so a 1-stud slide weighs like 30
  degrees), normalised to 60 fps;
- a SNAP = a frame whose motion is above `ratio` x the median of its neighbourhood (a Hampel test on the speed) and
  above `floor` degrees per 60th of a second;
- the FIX keeps every pose's path and re-spaces a window around the snap so the speed follows the neighbourhood's
  median profile (same total motion, same end poses): the joint arrives at the same place, without the jolt.
Fast motion that is fast for several frames (a real strike) is not a snap: only isolated spikes are."""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

POS_WEIGHT = 30.0


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def qang(a, b):
    """the angle between two rotations (degrees), robust to unnormalised / rounded quaternions: 2 atan2(|v|, |w|) of
    the relative rotation (acos of a dot product reads rounding to 6 decimals as ~0.1 deg)"""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    w = a[3] * b[3] + a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    v = a[3] * b[:3] - b[3] * a[:3] - np.cross(a[:3], b[:3])
    return math.degrees(2 * math.atan2(float(np.linalg.norm(v)), abs(float(w))))


def speeds(frames, fps, loop):
    """per-step motion (frame i -> i+1), degrees-equivalent per 60th of a second"""
    F = np.asarray(frames, dtype=float)
    n = len(F)
    out = []
    for i in range(n - 1):
        out.append(qang(F[i, :4], F[i + 1, :4]) + POS_WEIGHT * float(np.linalg.norm(F[i + 1, 4:7] - F[i, 4:7])))
    return np.array(out) * (fps / 60.0)


def find(clip, ratio=2.2, floor=9.0, win=3):
    """{joint: [(step index, speed, local median)]}"""
    fps = float(clip.get("fps") or 30)
    loop = bool(clip.get("loop"))
    out = {}
    # a stepped clip snaps there ON PURPOSE (limited animation); the frames beside a step compare against held
    # (still) neighbours, so they are not judged either
    intended = {k for f in C.step_frames(clip) for k in range(f - win, f + win + 1)}
    for j, d in clip["joints"].items():
        s = speeds(d["frames"], fps, loop)
        n = len(s)
        hits = []
        for i in range(n):
            idx = [(i + k) % n if loop else i + k for k in range(-win, win + 1) if k != 0]
            idx = [k for k in idx if 0 <= k < n]
            med = float(np.median(s[idx])) if idx else 0.0
            if s[i] > floor and s[i] > ratio * max(med, 1.0) and (i + 1) not in intended:
                hits.append((i, round(float(s[i]), 1), round(med, 1)))
        if hits:
            out[j] = hits
    return out


def interp(F, u):
    """the joint's pose at fractional frame u along its own path (slerp + lerp between samples)"""
    i = int(math.floor(u))
    i = max(0, min(i, len(F) - 2))
    w = u - i
    q = C.slerp(F[i][:4], F[i + 1][:4], w)
    p = np.asarray(F[i][4:7], dtype=float) * (1 - w) + np.asarray(F[i + 1][4:7], dtype=float) * w
    return [float(v) for v in q] + [float(v) for v in p]


def respace(frames, step, loop, half=3):
    """re-space the steps around `step` so their speeds follow the neighbourhood median (same path, same ends)"""
    F = [list(map(float, f)) for f in frames]
    n = len(F)
    a, b = step - half, step + half + 1                   # the window's frames a..b (steps a..b-1)
    if loop:
        # work on an unrolled copy so the window can cross the seam (the seam frame repeats frame 0)
        base = F[:-1]
        m = len(base)
        idx = [(k % m) for k in range(a, b + 1)]
        W = [base[k] for k in idx]
    else:
        a, b = max(0, a), min(n - 1, b)
        idx = list(range(a, b + 1))
        W = [F[k] for k in idx]
    seg = np.array([qang(W[k][:4], W[k + 1][:4]) + POS_WEIGHT * float(np.linalg.norm(np.subtract(W[k + 1][4:7], W[k][4:7])))
                    for k in range(len(W) - 1)])
    total = float(seg.sum())
    if total < 1e-6:
        return F
    target = seg.copy()
    centre = step - a if not loop else half
    others = np.delete(seg, centre)
    target[centre] = float(np.median(others)) if len(others) else seg[centre]
    # keep the window's total: scale the target so it covers the same motion
    target *= total / max(float(target.sum()), 1e-9)
    # cumulative motion along the original path -> fractional sample index for each new frame
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    newcum = np.concatenate([[0.0], np.cumsum(target)])
    for k in range(1, len(W) - 1):
        u = float(np.interp(newcum[k], cum, np.arange(len(W))))
        pose = interp(W, u)
        if loop:
            F[idx[k]] = pose
            if idx[k] == 0:
                F[-1] = pose
        else:
            F[idx[k]] = pose
    return F


def fix(clip, ratio=2.2, floor=9.0, passes=3):
    out = copy.deepcopy(clip)
    loop = bool(out.get("loop"))
    fixed = {}
    for _ in range(passes):
        hits = find(out, ratio, floor)
        if not hits:
            break
        for j, hs in hits.items():
            for step, _s, _m in hs:
                out["joints"][j]["frames"] = [[round(v, 6) for v in f] for f in respace(out["joints"][j]["frames"], step, loop)]
                fixed[j] = fixed.get(j, 0) + 1
    return out, fixed


def main(argv):
    if not argv:
        return emit("fail", "snaps: needs <clip.json> [--fix --out <clip.json>]", "lune run kit anim snaps <Name>")
    with open(argv[0], encoding="utf-8") as fh:
        clip = json.load(fh)
    ratio = float(argv[argv.index("--ratio") + 1]) if "--ratio" in argv else 2.2
    floor = float(argv[argv.index("--floor") + 1]) if "--floor" in argv else 9.0
    hits = find(clip, ratio, floor)
    listing = "; ".join(f"{j}: " + ", ".join(f"f{i} {s} vs {m}" for i, s, m in hs) for j, hs in hits.items())
    if "--fix" not in argv:
        if not hits:
            return emit("pass", f"snaps {clip.get('name')}: none (no frame jumps over {ratio}x its neighbours)", "none - proceed", snaps={})
        return emit("pass", f"snaps {clip.get('name')}: {sum(len(h) for h in hits.values())} snap(s) - {listing}",
                    f"fix the spacing: lune run kit anim snaps {clip.get('name')} --fix", snaps={j: [list(h) for h in hs] for j, hs in hits.items()})
    fixed_clip, fixed = fix(clip, ratio, floor)
    left = find(fixed_clip, ratio, floor)
    out = argv[argv.index("--out") + 1] if "--out" in argv else argv[0]
    fixed_clip.setdefault("notes", []).append(f"snaps.py re-spaced {sum(fixed.values())} snap(s): {fixed}")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(fixed_clip, fh, indent=1)
    status = "pass" if not left else "fail"
    return emit(status, f"snaps {clip.get('name')}: re-spaced {sum(fixed.values())} snap(s) ({listing or 'none'}); left: {sum(len(h) for h in left.values())} -> {out}",
                "none - proceed" if not left else "a snap the spacing cannot hide is a pose problem: re-key that pose", fixed=fixed)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
