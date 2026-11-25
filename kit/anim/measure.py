"""measure.py — what an animation DOES, in numbers a generator can be held to.

    python kit/anim/measure.py <clip.json> [--vs <other clip.json>] [--out <measure.json>]

For an R6 clip (a finished Roblox animation imported as it is, or the kit's own): per joint the character-space
pitch / yaw / roll and position over the cycle (24 phase samples), their ranges, where in the cycle each peaks, the
phase relations that make a gait read (head against torso yaw, arm against the same side's leg, torso yaw against
the leg), the pelvis's travel, and - with --vs - the distance per joint between two clips (the fit score: mean
absolute degrees over the cycle after the best phase shift). A loop is sampled over its cycle; a one-shot over its
duration. The owner's reference animations are measured first; the kit's gaits are then fitted to those numbers
(kit/anim/fit_r6.py)."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C   # noqa: E402

PARTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
SAMPLES = 24


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def pyr(m):
    """3x3 -> (pitch, yaw, roll) degrees: the CFrame.Angles order the kit keys in"""
    return (math.degrees(math.atan2(-m[1, 2], m[2, 2])), math.degrees(math.asin(max(-1.0, min(1.0, m[0, 2])))),
            math.degrees(math.atan2(-m[0, 1], m[0, 0])))


def curves(clip):
    """{part: (SAMPLES x 6) [pitch, yaw, roll, x, y, z]} resampled over the clip's cycle (a loop: its last frame
    is its first; the samples are 0 .. 1 - 1/SAMPLES)"""
    times = np.array(clip["times"], dtype=float)
    T = float(times[-1]) if len(times) > 1 else 1.0
    out = {}
    for part in PARTS:
        j = clip["joints"].get(part)
        if not j or not j.get("frames"):
            continue
        fr = j["frames"]
        rows = np.array([list(pyr(C.quat_mat(f[:4]))) + list(f[4:7]) for f in fr], dtype=float)
        # unwrap the angles so a swing through +-180 does not fold
        for k in range(3):
            rows[:, k] = np.degrees(np.unwrap(np.radians(rows[:, k])))
        qs = np.linspace(0.0, 1.0, SAMPLES, endpoint=False) * T
        out[part] = np.array([[np.interp(q, times, rows[:, k]) for k in range(6)] for q in qs])
    return out, T


def corr(a, b):
    a, b = a - a.mean(), b - b.mean()
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / d) if d > 1e-9 else 0.0


def describe(clip):
    cv, T = curves(clip)
    rec = {"name": clip.get("name"), "loop": bool(clip.get("loop")), "cycle_s": round(T, 4), "frames": len(clip["times"]),
           "joints": {}, "relations": {}}
    for part, a in cv.items():
        rec["joints"][part] = {
            "pitch": [round(float(a[:, 0].min()), 1), round(float(a[:, 0].max()), 1)],
            "yaw": [round(float(a[:, 1].min()), 1), round(float(a[:, 1].max()), 1)],
            "roll": [round(float(a[:, 2].min()), 1), round(float(a[:, 2].max()), 1)],
            "pos_y": [round(float(a[:, 4].min()), 2), round(float(a[:, 4].max()), 2)],
            "pos_z": [round(float(a[:, 5].min()), 2), round(float(a[:, 5].max()), 2)],
            "pitch_peak_phase": round(float(np.argmax(a[:, 0])) / SAMPLES, 2),
            "pitch_curve": [round(float(v)) for v in a[:, 0]],
            "pos_y_curve": [round(float(v), 2) for v in a[:, 4]],
            "pos_z_curve": [round(float(v), 2) for v in a[:, 5]],
        }
    if "Torso" in cv and "Head" in cv:
        rec["relations"]["head_yaw_vs_torso_yaw"] = round(corr(cv["Head"][:, 1], cv["Torso"][:, 1]), 2)
        rec["relations"]["head_pitch_vs_torso_pitch"] = round(corr(cv["Head"][:, 0], cv["Torso"][:, 0]), 2)
    if "Right Arm" in cv and "Right Leg" in cv:
        rec["relations"]["right_arm_vs_right_leg"] = round(corr(cv["Right Arm"][:, 0], cv["Right Leg"][:, 0]), 2)
    if "Torso" in cv and "Right Leg" in cv:
        rec["relations"]["torso_yaw_vs_right_leg"] = round(corr(cv["Torso"][:, 1], cv["Right Leg"][:, 0]), 2)
        rec["relations"]["torso_lean_mean"] = round(float(cv["Torso"][:, 0].mean()), 1)
        rec["relations"]["torso_drop_mean"] = round(float(cv["Torso"][:, 4].mean()), 2)
    if "Right Leg" in cv and "Left Leg" in cv:
        # the legs' half-cycle offset: the left leg's curve shifted by half a cycle should match the right's
        r, l = cv["Right Leg"][:, 0], np.roll(cv["Left Leg"][:, 0], SAMPLES // 2)
        rec["relations"]["legs_half_cycle_symmetry"] = round(corr(r, l), 2)
    return rec, cv


def distance(cv_a, cv_b, shift=True, loop=True):
    """per joint: the mean absolute difference (deg for angles, studs x 30 for positions) over the cycle, after
    the phase shift that best aligns the RIGHT LEG's pitch (a gait is judged pose for pose, not frame for frame)"""
    best, best_k = None, 0
    # a one-shot is judged from its start (rolling it would wrap the end onto the beginning); a loop finds its phase
    if shift and loop and "Right Leg" in cv_a and "Right Leg" in cv_b:
        for k in range(SAMPLES):
            d = float(np.abs(cv_a["Right Leg"][:, 0] - np.roll(cv_b["Right Leg"][:, 0], k)).mean())
            if best is None or d < best:
                best, best_k = d, k
    out = {}
    for part in PARTS:
        if part in cv_a and part in cv_b:
            a, b = cv_a[part], np.roll(cv_b[part], best_k, axis=0)
            ang = float(np.abs(a[:, :3] - b[:, :3]).mean())
            pos = float(np.abs(a[:, 3:] - b[:, 3:]).mean())
            out[part] = {"angles_deg": round(ang, 1), "pos_studs": round(pos, 3), "score": round(ang + 30.0 * pos, 1)}
    total = round(float(np.mean([v["score"] for v in out.values()])), 1) if out else None
    return {"shift": best_k, "per_joint": out, "total": total}


def main(argv):
    if not argv:
        return emit("fail", "measure: needs <clip.json> [--vs <clip.json>] [--out <file>]", "lune run kit anim measure <Name>")
    path = argv[0]
    other = argv[argv.index("--vs") + 1] if "--vs" in argv else None
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    with open(path, encoding="utf-8") as fh:
        clip = json.load(fh)
    if clip.get("rig") != "R6":
        return emit("fail", f"measure: {path} is a {clip.get('rig')} clip; measure the R6 clip (<Name>.r6.clip.json or an R6-native one)", "lune run kit anim <Name>")
    rec, cv = describe(clip)
    summary = [f"{rec['name']}: cycle {rec['cycle_s']} s"]
    for part in ("Right Leg", "Right Arm", "Torso", "Head"):
        j = rec["joints"].get(part)
        if j:
            summary.append(f"{part} pitch {j['pitch'][0]}..{j['pitch'][1]} y {j['pos_y'][0]}..{j['pos_y'][1]} z {j['pos_z'][0]}..{j['pos_z'][1]}")
    rel = rec["relations"]
    if rel:
        summary.append("head/torso yaw " + str(rel.get("head_yaw_vs_torso_yaw")) + ", arm/leg " + str(rel.get("right_arm_vs_right_leg")) + ", torso yaw/leg " + str(rel.get("torso_yaw_vs_right_leg")) + f", lean {rel.get('torso_lean_mean')}, drop {rel.get('torso_drop_mean')}")
    if other:
        with open(other, encoding="utf-8") as fh:
            clip_b = json.load(fh)
        rec_b, cv_b = describe(clip_b)
        rec["vs"] = {"name": rec_b["name"], "distance": distance(cv, cv_b, loop=bool(clip.get("loop")) and bool(clip_b.get("loop"))), "other": rec_b}
        dist = rec["vs"]["distance"]
        summary.append(f"vs {rec_b['name']}: distance {dist['total']} (" + ", ".join(f"{p} {v['score']}" for p, v in dist["per_joint"].items()) + ")")
    out = out or os.path.splitext(path)[0].replace(".clip", "") + ".measure.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    return emit("pass", "; ".join(summary), f"read {out}: the curves per joint (24 phase samples) are what a generator must reproduce", file=out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
