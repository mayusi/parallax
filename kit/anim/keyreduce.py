"""keyreduce.py — the fewest keys that reproduce a baked clip, per joint (curve simplification).

    python kit/anim/keyreduce.py <clip.json> [--tol 3]

Why (2026-10-11): finished R6 animations are often BAKED (a keyframe every frame), which nobody can edit and which
hides how they were made. Curve simplification (Lim & Thalmann; Ramer-Douglas-Peucker on each joint's track, with
the error measured on the motion itself: degrees, plus studs x 30) keeps a key only where straight interpolation
from its neighbours would miss by more than `tol`. The result is editable and READS like the animator's plan: the
sprint the owner loved needs 7 keys on the torso and head but 15-20 on each limb - the life is in the limb curves.
Used by `kit anim pose-from <Ref> --as <Name> --reduce <tol>` and by the style book's key density."""
import json
import math
import sys

import numpy as np

POS_WEIGHT = 30.0


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


def slerp(a, b, w):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + (b - a) * w
        return q / np.linalg.norm(q)
    th = math.acos(d)
    return (math.sin((1 - w) * th) * a + math.sin(w * th) * b) / math.sin(th)


def reduce_track(frames, tol=3.0):
    """indices of the kept keys (first and last always) for one joint's [qx qy qz qw x y z] frames"""
    F = np.asarray(frames, dtype=float)
    n = len(F)
    keys = {0, n - 1}
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        worst, at = 0.0, None
        for i in range(a + 1, b):
            w = (i - a) / (b - a)
            q = slerp(F[a, :4], F[b, :4], w)
            p = F[a, 4:7] * (1 - w) + F[b, 4:7] * w
            e = qang(q, F[i, :4]) + POS_WEIGHT * float(np.linalg.norm(p - F[i, 4:7]))
            if e > worst:
                worst, at = e, i
        if worst > tol and at is not None:
            keys.add(at)
            stack += [(a, at), (at, b)]
    return sorted(keys)


def reduce_clip(clip, tol=3.0):
    return {j: reduce_track(d["frames"], tol) for j, d in clip["joints"].items()}


def main(argv):
    with open(argv[0], encoding="utf-8") as fh:
        clip = json.load(fh)
    tol = float(argv[argv.index("--tol") + 1]) if "--tol" in argv else 3.0
    k = reduce_clip(clip, tol)
    n = len(clip["times"])
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"keyreduce {clip.get('name')}: {n} frames -> " + ", ".join(f"{j} {len(v)}" for j, v in k.items()) + f" keys (tol {tol:g})",
                      "next_action": "none - proceed", "keys": k}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
