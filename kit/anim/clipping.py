"""clipping.py — where an R6 clip's parts pass THROUGH each other (an arm through the head, a fist through the chest).

    python kit/anim/clipping.py <clip.json> [--shrink 0.2]

Why (2026-10-11): fresh judges docked three Brawler moves for "the right arm passes through the head / torso"
(engine_fit). On R6 the parts are boxes, so it is exact: every frame, every pair that is not jointed together is
tested with the separating-axis theorem on the two oriented boxes, each SHRUNK by `shrink` studs per side (an arm
resting against the torso's side is contact, not clipping); a limb against the torso is tested on its far 1.4 studs
only (the shoulder end overlaps the torso at the joint whenever the arm swings across - a two-handed grip always does). Reported as spans: the pair, the
first and last time, and the frames - a sentence the author can act on."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

PAIRS = [("Right Arm", "Head"), ("Left Arm", "Head"), ("Right Arm", "Torso"), ("Left Arm", "Torso"),
         ("Right Arm", "Left Arm"), ("Right Leg", "Left Leg"), ("Right Arm", "Right Leg"), ("Left Arm", "Left Leg"),
         ("Right Arm", "Left Leg"), ("Left Arm", "Right Leg")]


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


# what the eye sees: an R6 Head PART is a 2 x 1 x 1 box, but the head you see is its mesh (~1.25 studs a side)
VISIBLE = {"Head": (1.25, 1.25, 1.25)}


def obb(rig, part, m, shrink, distal=None):
    """a part's box (shrunk); distal = keep only the far `distal` studs of a limb (the hand / foot side) - the
    shoulder / hip end overlaps the torso at the joint itself whenever the limb swings across the body, which is
    the rig, not a clip"""
    size = np.asarray(VISIBLE.get(part, rig["sizes"][part]), float)
    h = np.maximum(size / 2.0 - shrink, 0.05)
    c = m[:3, 3].copy()
    if distal is not None and size[1] > distal:
        h[1] = max(distal / 2.0 - shrink, 0.05)
        c = c + m[:3, :3] @ np.array([0.0, -(size[1] - distal) / 2.0, 0.0])
    return c, m[:3, :3].copy(), h


def overlap(a, b):
    """separating-axis test for two oriented boxes (centre, axes as columns, half sizes)"""
    ca, Ra, ha = a
    cb, Rb, hb = b
    d = cb - ca
    axes = [Ra[:, i] for i in range(3)] + [Rb[:, i] for i in range(3)]
    for i in range(3):
        for j in range(3):
            x = np.cross(Ra[:, i], Rb[:, j])
            if np.linalg.norm(x) > 1e-6:
                axes.append(x / np.linalg.norm(x))
    for ax in axes:
        ra = sum(ha[i] * abs(float(np.dot(Ra[:, i], ax))) for i in range(3))
        rb = sum(hb[i] * abs(float(np.dot(Rb[:, i], ax))) for i in range(3))
        if abs(float(np.dot(d, ax))) > ra + rb:
            return False
    return True


def find(clip, shrink=0.2):
    rig = C.load_rig("r6")
    frames = C.world_frames(clip, rig)
    times = clip["times"]
    spans = []
    two_hands = bool(clip.get("sword"))                   # both hands on one hilt: the arms meet by design
    for p, q in PAIRS:
        if p not in frames[0] or q not in frames[0]:
            continue
        if two_hands and {p, q} == {"Right Arm", "Left Arm"}:
            continue
        dist = 1.4 if q == "Torso" else None              # a limb against its own torso: only its far end
        hit = [i for i, f in enumerate(frames) if overlap(obb(rig, p, f[p], shrink, dist), obb(rig, q, f[q], shrink))]
        if not hit:
            continue
        start = prev = hit[0]
        for i in hit[1:] + [None]:
            if i is None or i != prev + 1:
                spans.append({"pair": f"{p} through {q}", "from_s": round(float(times[start]), 3), "to_s": round(float(times[prev]), 3),
                              "frames": prev - start + 1})
                if i is not None:
                    start = i
            if i is not None:
                prev = i
    return spans


def main(argv):
    if not argv:
        return emit("fail", "clipping: needs <clip.json>", "python kit/anim/clipping.py build/animations/<Name>.clip.json")
    with open(argv[0], encoding="utf-8") as fh:
        clip = json.load(fh)
    shrink = float(argv[argv.index("--shrink") + 1]) if "--shrink" in argv else 0.2
    spans = find(clip, shrink)
    if not spans:
        return emit("pass", f"clipping {clip.get('name')}: no part passes through another", "none - proceed", spans=[])
    text = "; ".join(f"{s['pair']} {s['from_s']}-{s['to_s']} s ({s['frames']} f)" for s in spans)
    return emit("pass", f"clipping {clip.get('name')}: {text}", "move the limb's path around the body (posture / layer ops, or re-key that span)", spans=spans)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
