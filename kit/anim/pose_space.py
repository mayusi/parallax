"""pose_space.py — the LEARNED SPACE of loved R6 poses (owner-approved plan v3, 2026-10-12: "every generated pose lives
inside the space human R6 animators use" - my hand-posed moves were rejected every round).

    python kit/anim/pose_space.py build      -> _artifacts/r6lib/pose_space.npz (+ a validation line)
    from pose_space import load, encode, decode, project, distance

A pose = all six R6 joints of one frame: each joint's rotation as its 6D form (the first two columns of the matrix,
continuous - no quaternion sign flips) + its slide (position) = 54 numbers. Data: every frame of every LOVED native R6
clip (assets/animations/library/owner_picks.json; dances out), each also MIRRORED left <-> right. A PCA (centred,
per-dimension scaled) keeps the components that explain 99% of the variance: encode() -> the latent coordinates,
decode() -> a valid pose (rotations re-orthonormalised), project() = decode(encode()) snaps any pose onto the space,
distance() = how far a pose sits from it (the reconstruction error, degrees per joint)."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import derive as D  # noqa: E402

LIB = os.path.join("_artifacts", "r6lib")
OUT = os.path.join(LIB, "pose_space.npz")
JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
VAR = 0.99


def to_vec(frames):
    """{joint: [qx,qy,qz,qw,px,py,pz]} -> 54 numbers"""
    v = []
    for j in JOINTS:
        f = frames.get(j, [0, 0, 0, 1, 0, 0, 0])
        R = C.quat_mat(np.asarray(f[:4], float))
        v += list(R[:, 0]) + list(R[:, 1]) + list(f[4:7])
    return np.array(v, float)


def from_vec(v):
    out = {}
    for i, j in enumerate(JOINTS):
        a, b, p = v[i * 9:i * 9 + 3], v[i * 9 + 3:i * 9 + 6], v[i * 9 + 6:i * 9 + 9]
        x = a / max(np.linalg.norm(a), 1e-9)
        y = b - np.dot(b, x) * x
        y = y / max(np.linalg.norm(y), 1e-9)
        z = np.cross(x, y)
        R = np.stack([x, y, z], axis=1)
        out[j] = list(C.mat_quat(R)) + [float(t) for t in p]
    return out


def clip_vectors(c):
    n = len(c["times"])
    return np.array([to_vec({j: c["joints"][j]["frames"][i] for j in c["joints"] if j in JOINTS}) for i in range(n)])


def build():
    picks = json.load(open(os.path.join("assets", "animations", "library", "owner_picks.json"), encoding="utf-8"))["picks"]
    loved = [r for r in picks if r["verdict"] == "love" and not r["laggy"] and r["kind"] != "dance"]
    rng = np.random.default_rng(0)
    rng.shuffle(loved)
    held = {r["id"] for r in loved[: max(5, len(loved) // 10)]}            # held out: the validation set
    X, Xh = [], []
    for r in loved:
        p = os.path.join(LIB, "clips", f"{r['id']}.clip.json")
        if not os.path.isfile(p):
            continue
        c = json.load(open(p, encoding="utf-8"))
        if not all(j in c["joints"] for j in ("Torso", "Right Arm", "Left Arm")):
            continue
        m = D.op_mirror(D.copy.deepcopy(c))
        for cc in (c, m):
            (Xh if r["id"] in held else X).append(clip_vectors(cc))
    X, Xh = np.vstack(X), np.vstack(Xh)
    mean = X.mean(0)
    scale = np.maximum(X.std(0), 1e-3)
    Z = (X - mean) / scale
    U, S, Vt = np.linalg.svd(Z[:: max(1, len(Z) // 40000)], full_matrices=False)
    var = (S ** 2) / np.sum(S ** 2)
    k = int(np.searchsorted(np.cumsum(var), VAR) + 1)
    np.savez(OUT, mean=mean, scale=scale, comps=Vt[:k], sv=S[:k], frames=len(X), held=len(Xh))
    return k, len(X), Xh


_SPACE = None


def load():
    global _SPACE
    if _SPACE is None:
        d = np.load(OUT)
        _SPACE = {k: d[k] for k in d.files}
    return _SPACE


def encode(v):
    s = load()
    return ((np.asarray(v) - s["mean"]) / s["scale"]) @ s["comps"].T


def decode_vec(z):
    s = load()
    return (np.asarray(z) @ s["comps"]) * s["scale"] + s["mean"]


def decode(z):
    return from_vec(decode_vec(z))


def project_vec(v):
    return decode_vec(encode(v))


def distance(frames):
    """how far a pose sits from the loved pose space: mean joint rotation error (deg) + slide error (studs x 30)"""
    v = to_vec(frames)
    r = from_vec(project_vec(v))
    err = 0.0
    for j in JOINTS:
        if j not in frames:
            continue
        qa, qb = np.asarray(frames[j][:4]), np.asarray(r[j][:4])
        err += np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(qa, qb)))))) + 30 * float(np.linalg.norm(np.asarray(frames[j][4:7]) - np.asarray(r[j][4:7])))
    return err / len(JOINTS)


def clip_distance(c):
    return [distance({j: c["joints"][j]["frames"][i] for j in c["joints"] if j in JOINTS}) for i in range(len(c["times"]))]


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        k, n, Xh = build()
        held = [distance(from_vec(v)) for v in Xh[:: max(1, len(Xh) // 3000)]]
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"pose space: {k} components (99% of variance) from {n} loved frames (mirrored); held-out loved poses sit {np.median(held):.2f} from it (median, p90 {np.percentile(held, 90):.2f})",
                          "next_action": "compare: python kit/anim/pose_space.py check <clip.json>"}))
    elif sys.argv[1:2] == ["check"]:
        c = json.load(open(sys.argv[2], encoding="utf-8"))
        d = clip_distance(c)
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"{c.get('name')}: distance from the loved pose space median {np.median(d):.2f}, p90 {np.percentile(d, 90):.2f}", "next_action": "-"}))
