"""kimodo_fold.py — a Kimodo SOMA motion (the NPZ `posed_joints` [T, 77, 3], metres, Y up; nv-tlabs/kimodo) folded onto R6
(owner brief 2026-10-12). Positions only, frame by frame, in the character's own frame:
  ROOT     the hips on the floor (x, z) + the heading of the hip line -> the clip's `root` track (travel + turning)
  TORSO    up = hips -> chest, right = left shoulder -> right shoulder; its height change -> the Torso offset (bob / crouch)
  HEAD     up = neck -> head, right = left eye -> right eye
  ARMS     the R6 arm points shoulder -> hand; the ELBOW BEND (shoulder->hand shorter than upper arm + forearm) becomes a
  LEGS     SLIDE of the R6 limb back along itself (the R6 way to fake a bend), same for hip -> foot and the KNEE
           every slide clamped per axis to the 1st..99th percentile of that joint's offset in the owner's LOVED clips
SOMA and Roblox are both right-handed with Y up, so no axis flip is needed (the facing comes from the body itself); the
scale is the R6 leg (2 studs) over the SOMA leg (hip -> foot at its longest), so steps match the R6 legs.
    python kit/anim/kimodo_fold.py <motion.npz> --names <somaskel77.json> --out <clip.json> [--fps 30]"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

R6 = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
LIMBS = {"Right Arm": ("RightArm", "RightForeArm", "RightHand"), "Left Arm": ("LeftArm", "LeftForeArm", "LeftHand"),
         "Right Leg": ("RightLeg", "RightShin", "RightFoot"), "Left Leg": ("LeftLeg", "LeftShin", "LeftFoot")}
_RANGES = None


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def frame(right, up):
    """a rotation with columns x = right, y = up, z = x × y (back), re-orthogonalised on `up`"""
    y = unit(up)
    x = unit(right - np.dot(right, y) * y)
    return np.stack([x, y, np.cross(x, y)], axis=1)


def shortest_arc(a, b):
    """the smallest rotation taking unit vector a onto unit vector b (no twist about either)"""
    a, b = unit(a), unit(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -0.999999:                                       # opposite: half turn about any axis perpendicular to a
        ax = unit(np.cross(a, [1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.cross(a, [0.0, 0.0, 1.0]))
        return 2.0 * np.outer(ax, ax) - np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1.0 + c)


def loved_slide_ranges():
    """per joint and axis: the 1st..99th percentile of the joint OFFSET over the owner's loved, game-safe clips"""
    global _RANGES
    if _RANGES is not None:
        return _RANGES
    labels = [json.loads(s) for s in open(os.path.join("_artifacts", "r6data", "labels.jsonl"), encoding="utf-8") if '"augmentation": null' in s]
    z = np.load(os.path.join("_artifacts", "r6data", "clips.npz"))
    P = np.concatenate([z[f"{l['id']}/pos"] for l in labels if l["owner_verdict"] == "love" and l["licence"] == "game"])
    _RANGES = {j: (np.percentile(P[:, k], 1, 0), np.percentile(P[:, k], 99, 0)) for k, j in enumerate(R6)}
    return _RANGES


def rest_pose(npz, names, parents):
    """Kimodo's REST pose (every joint position with all rotations identity), measured from the motion itself: a bone's
    offset in its parent's frame (global_rot_mats) is constant, so rest = the offsets summed down the tree"""
    X, G = np.asarray(npz["posed_joints"], float), np.asarray(npz["global_rot_mats"], float)
    J = {n: i for i, n in enumerate(names)}
    rest = np.zeros((len(names), 3))
    for i, n in enumerate(names):                         # parents come before children in the skeleton list
        p = parents[i]
        if p:
            off = np.einsum("tba,tb->ta", G[:, J[p]], X[:, i] - X[:, J[p]]).mean(0)
            rest[i] = rest[J[p]] + off
    return rest


def torso_frame(g, t, src):
    """the torso's orientation from the SOMA joints: 'current' = shoulder line + hips -> chest; 'pelvis' = hip line +
    hips -> spine; 'chest' = shoulder line + chest -> neck; 'blend' = halfway (slerp) between pelvis and chest"""
    if src == "pelvis":
        return frame(g("RightLeg")[t] - g("LeftLeg")[t], g("Spine1")[t] - g("Hips")[t])
    if src == "chest":
        return frame(g("RightArm")[t] - g("LeftArm")[t], g("Neck1")[t] - g("Chest")[t])
    if src == "blend":
        a, b = torso_frame(g, t, "pelvis"), torso_frame(g, t, "chest")
        return C.quat_mat(C.slerp(C.mat_quat(a), C.mat_quat(b), 0.5))
    return frame(g("RightArm")[t] - g("LeftArm")[t], g("Chest")[t] - g("Hips")[t])


def fold(posed, names, fps=30, name="kimodo", face_forward=True, rest=None, opts=None):
    """rest: Kimodo's rest pose (rest_pose()); the head's rest lean against the torso is taken out (SOMA's neck -> head
    line leans 17 deg forward at rest: read literally it pitched every R6 head down).
    opts (the 2-segment -> 1-piece limb ablation, owner brief 2026-10-13; the defaults = the fold as it was):
      leg_alpha / arm_alpha  0..1: the R6 limb aims from the start -> end line toward the UPPER segment (hip -> knee,
                             shoulder -> elbow) by alpha x the joint's bend (0 straight .. 1 at a 30% shortening)
      torso                  'current' | 'pelvis' | 'chest' | 'blend' (torso_frame)
      crouch                 'a' = the torso drops with the hips; 'b' = 40% drop, the rest taken by spreading the legs
                             outward (same leg length); 'c' = 25% drop + a forward lean (up to 30 deg), the legs
                             straightened to reach where the feet are"""
    o = {"leg_alpha": 0.0, "arm_alpha": 0.0, "torso": "current", "crouch": "a", **(opts or {})}
    J = {n: i for i, n in enumerate(names)}
    X = np.asarray(posed, float)
    T = len(X)
    g = lambda n: X[:, J[n]]  # noqa: E731
    leg_len = np.max(np.linalg.norm(g("RightFoot") - g("RightLeg"), axis=1))
    s = 2.0 / max(leg_len, 1e-6)                           # studs per metre
    hips = g("Hips")
    stand = np.percentile(hips[:, 1], 90)
    # root heading from the hip line (right = left hip -> right hip), unwrapped + lightly smoothed
    rh = g("RightLeg") - g("LeftLeg")
    yaw = np.unwrap(np.arctan2(-rh[:, 2], rh[:, 0]))
    yaw = np.convolve(np.pad(yaw, 2, mode="edge"), np.ones(5) / 5, mode="valid")
    if face_forward:
        # the first frame faces the character's forward (-Z): Kimodo's motions face +Z in their own world, which turned
        # every fold around (the first render showed the back). The whole path is turned with it, about the first hips.
        R0 = C.euler_mat([0.0, math.degrees(-yaw[0]), 0.0])
        X = (X - np.array([X[0, J["Hips"], 0], 0.0, X[0, J["Hips"], 2]])) @ R0.T
        g = lambda n: X[:, J[n]]  # noqa: E731
        hips = g("Hips")
        rh = g("RightLeg") - g("LeftLeg")
        yaw = np.unwrap(np.arctan2(-rh[:, 2], rh[:, 0]))
        yaw = np.convolve(np.pad(yaw, 2, mode="edge"), np.ones(5) / 5, mode="valid")
    rng = loved_slide_ranges()
    rig = C.load_rig("r6")
    H0 = np.eye(3)
    src_fix = np.eye(3)
    if rest is not None:
        rr = lambda n: rest[J[n]]  # noqa: E731
        Rt0 = torso_frame(lambda n: rest[None, J[n]], 0, "current")
        # every torso source is aligned to the same rest orientation, so a source changes how the torso MOVES, not a
        # constant tilt (SOMA's chest -> neck line leans forward even at rest)
        src_fix = torso_frame(lambda n: rest[None, J[n]], 0, o["torso"]).T @ Rt0
        Rh0 = frame(rr("RightEye") - rr("LeftEye"), rr("Head") - rr("Neck1"))
        H0 = Rt0.T @ Rh0                                   # the head in the torso at rest: R6 wants identity
    pivot = {p: np.asarray(rig["joints"][p]["c0"][:3], float) for p in LIMBS}                  # in the torso
    # the R6 limb turns about a pivot that is NOT on its long axis (C1 = the pivot in the limb): the pivot -> end
    # vector leans 18 deg (arms) / 14 deg (legs) off the limb's -Y. Aiming -Y at the target pushed every limb outward
    # (the 'arms stuck out sideways' of the first Kimodo folds); the limb is now turned so pivot -> end hits the target.
    v_local = {p: np.array([0.0, -1.0, 0.0]) - np.asarray(rig["joints"][p]["c1"][:3], float) for p in LIMBS}
    reach = {p: float(np.linalg.norm(v)) for p, v in v_local.items()}
    # upper-body positions are read relative to the torso centre, scaled by the torso's height (hip line -> neck = the
    # R6 torso's 2 studs), so hands held at the face stay at the face (R6 shoulders are wider than a human's)
    hipmid = (g("RightLeg") + g("LeftLeg")) / 2
    torso_h = np.median(np.linalg.norm(g("Neck1") - hipmid, axis=1))
    st = 2.0 / max(torso_h, 1e-6)
    leg_s = s
    frames = {j: [] for j in R6}
    root = []
    slides = {j: [] for j in LIMBS}
    targets = {j: [] for j in LIMBS}                       # the normalised hand / foot place, torso frame (studs)
    for t in range(T):
        Ry = C.euler_mat([0.0, math.degrees(yaw[t]), 0.0])
        root.append(list(C.mat_quat(Ry)) + [float(hips[t, 0] * s), 0.0, float(hips[t, 2] * s)])
        Rt = torso_frame(g, t, o["torso"]) @ src_fix
        drop = float((hips[t, 1] - stand) * s)             # <= 0 when the hips are low (a crouch)
        lean = np.eye(3)
        if o["crouch"] == "b":
            y_torso = 0.4 * drop
        elif o["crouch"] == "c":
            y_torso = 0.25 * drop
            beta = min(30.0, 30.0 * max(0.0, -drop))       # 1 stud of crouch -> 30 deg forward (top toward -Z)
            lean = C.euler_mat([-beta, 0.0, 0.0])
        else:
            y_torso = drop
        Rt_c = Ry.T @ Rt @ lean
        frames["Torso"].append(list(C.mat_quat(Rt_c)) + [0.0, y_torso, 0.0])
        Rh = frame(g("RightEye")[t] - g("LeftEye")[t], g("Head")[t] - g("Neck1")[t])
        frames["Head"].append(list(C.mat_quat(Rt.T @ Rh @ H0.T)) + [0.0, 0.0, 0.0])
        centre = (hipmid[t] + g("Neck1")[t]) / 2
        for part, (a, b, c) in LIMBS.items():
            A, Bm, Cc = g(a)[t], g(b)[t], g(c)[t]
            if "Arm" in part:                                # the hand's place in the torso, R6-scaled
                target = Rt.T @ (Cc - centre) * st
            else:                                            # the foot from its own hip, by the leg's scale
                target = pivot[part] + Rt.T @ (Cc - A) * leg_s
            alpha = o["arm_alpha"] if "Arm" in part else o["leg_alpha"]
            if alpha:                                        # aim toward the upper segment, by the bend
                k_ = np.linalg.norm(Cc - A) / max(np.linalg.norm(Bm - A) + np.linalg.norm(Cc - Bm), 1e-9)
                w = alpha * float(np.clip((1.0 - k_) / 0.3, 0.0, 1.0))
                tp = target - pivot[part]
                d_up = unit(Rt.T @ (Bm - A))
                target = pivot[part] + unit((1 - w) * unit(tp) + w * d_up) * np.linalg.norm(tp)
            if "Leg" in part and o["crouch"] in ("b", "c") and drop < 0:
                tp = target - pivot[part]
                if o["crouch"] == "b":                       # the drop not taken by the torso: legs spread outward
                    y2 = min(0.0, tp[1] + 0.6 * -drop)
                    side = 1.0 if pivot[part][0] > 0 else -1.0
                    x2 = side * math.sqrt(max(tp[0] ** 2, float(tp @ tp) - y2 ** 2 - tp[2] ** 2))
                    tp = np.array([x2, y2, tp[2]])
                else:                                        # the torso stays higher: the legs reach further down
                    tp = tp + np.array([0.0, -0.75 * -drop, 0.0])
                target = pivot[part] + tp
            if "Leg" in part:                                # a leaned torso: the feet stay where they were
                target = lean.T @ target
            targets[part].append(target)
            to = target - pivot[part]
            dist = float(np.linalg.norm(to))
            d_t = to / max(dist, 1e-9)                       # pivot -> target, torso frame
            # twist: a bent elbow sticks out of the shoulder->hand line toward the arm's BACK (+Z), a bent knee toward
            # the leg's FRONT (-Z). A straight limb carries no twist information: it gets the shortest turn from rest
            # (no twist), never a fixed axis (a fixed 'back' flips the arm whenever it points forward)
            line = Cc - A
            off = (Bm - A) - np.dot(Bm - A, unit(line)) * unit(line)
            ly = -unit(v_local[part])
            if np.linalg.norm(off) > 0.05 * np.linalg.norm(line):
                z_ref = Rt.T @ unit(off) * (1.0 if "Arm" in part else -1.0)
                lz = unit(np.array([0.0, 0.0, 1.0]) - ly[2] * ly)
                L = np.stack([np.cross(ly, lz), ly, lz], axis=1)
                wy = -d_t
                wz = unit(z_ref - np.dot(z_ref, wy) * wy)
                Wm = np.stack([np.cross(wy, wz), wy, wz], axis=1)
                Ra_t = Wm @ L.T                              # the limb's turn in the torso frame
            else:
                Ra_t = shortest_arc(-ly, d_t)
            v = d_t * (dist - reach[part])                   # what the turn cannot reach: a SLIDE along the limb
            lo, hi = rng[part]
            v = np.clip(v, lo, hi)
            slides[part].append(float(np.linalg.norm(v)))
            frames[part].append(list(C.mat_quat(Ra_t)) + [float(x) for x in v])
    clip = {"schema": 1, "name": name, "rig": "R6", "fps": fps, "loop": False, "priority": "Action",
            "times": [round(i / fps, 6) for i in range(T)], "events": [], "root": root,
            "joints": {j: {"frames": frames[j]} for j in R6},
            "source": {"kind": "kimodo_fold", "studs_per_metre": round(s, 3)}}
    info = {"frames": T, "studs_per_metre": round(s, 3), "max_slide_studs": {j: round(max(v), 3) for j, v in slides.items()},
            "targets": {j: np.array(v) for j, v in targets.items()},
            "positions": X, "yaw": np.asarray(yaw)}            # the SOMA joints after face_forward (metres), heading
    return clip, info


def main(argv):
    npz = np.load(argv[0])
    names = json.load(open(argv[argv.index("--names") + 1], encoding="utf-8"))["names"]
    out = argv[argv.index("--out") + 1]
    fps = int(argv[argv.index("--fps") + 1]) if "--fps" in argv else 30
    sk = json.load(open(argv[argv.index("--names") + 1], encoding="utf-8"))
    clip, info = fold(npz["posed_joints"], names, fps, os.path.splitext(os.path.basename(out))[0],
                      rest=rest_pose(npz, names, sk["parents"]) if "global_rot_mats" in npz else None)
    json.dump(clip, open(out, "w", encoding="utf-8"))
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"folded {argv[0]} -> {out}: { {k: v for k, v in info.items() if k not in ('targets', 'positions', 'yaw')} }", "next_action": "render it"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
