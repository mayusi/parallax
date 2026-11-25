"""r6_rig_model.py — the owner's R6 rig (assets/rigs/R6_IK.blend) as MATHEMATICS: every body part's transform from the
control values, in closed form, no Blender. Validated against the rig itself by kit/anim/rig_model_check.py
(random poses; residuals reported in assets/rigs/R6_IK.md).

Notation (Blender armature space = world: x right, y forward, z up; the character faces +y):
- a control's REST matrix L (4x4, its bone's matrix_local, from assets/rigs/R6_IK.rig.json) and its BASIS
  B = T(loc) R(rot) (the values an animator keys: location in the bone's own axes, rotation quaternion or euler).
- the control's DELTA (its motion from rest, in world terms):  D = D_parent · L · B · L⁻¹
  (a rotation about the bone's head, a translation along the bone's own axes, carried by the parent's delta).

The rig, equation by equation:
  D_main  = L_m B_m L_m⁻¹                                  Main Controller (no parent)
  D_body  = D_main · L_b B_b L_b⁻¹                         Body
  D_arm   = D_body · L_a B_a L_a⁻¹                         Arm.R / Arm.L
  D_head  : pivot = D_body·(h + L_h.rot·loc_h), turn = L_h.rot R_h L_h.rot⁻¹   Head.001 - inherit rotation OFF: its
                                                            pivot (and its own slide) ride the body's whole motion,
                                                            its turn is ONLY its own (no Body, no Main Controller turn)
  D_foot  = clampZ( D_main · L_f B_f L_f⁻¹ )               Foot.R / Foot.L; Limit Location: the foot point z >= 0
  D_uleg  = D_body · L_u B_u L_u⁻¹ ;  H = D_uleg · H₀      the IK hip ANCHOR H (Uleg head, rest H₀ = (±0.5, 0, 2))
  F = D_foot · F₀ (the foot point, rest (±0.5, 0, 0)),  ŷ = D_foot.rot · y₅ (the foot-pinned bone's axis)
  K       = H + 0.118·(cos φ(d)·û + sin φ(d)·p̂)            the inner IK joint: û = unit(F − H), p̂ = the knee pole's
                                                            direction ⊥ û, φ(d) the measured swing (d = |F − H|)
  D_ik    = T(F) · arc(ŷ, unit(K − F)) · T(−F) · D_foot     IK LEG: rigid, pinned at the foot, aimed at K (the hip
                                                            anchor, nudged ≤ 4° toward the knee pole)
  D_fk    = D_body · L_k B_k L_k⁻¹                         FKLeg.R / FKLeg.L (euler XYZ)
  D_world = D_main · L_w B_w L_w⁻¹                         Leg.R / Leg.L, the "Unparented" FK leg
  D_leg   = blend( FKbox ? D_fk : D_world ,  D_ik ,  w = |SoftIK.x| / 2 )   (location lerp, rotation slerp)
Parts: Torso = D_body, Head = D_head, arms = D_arm, legs = D_leg, HumanoidRootPart = identity."""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# the rig's rest data (bone matrix_local, the measured IK knee swing) lives beside the rig: kit/anim/rigs/ holds ENGINE
# rigs only (every JSON there is loaded as one)
RIG_DATA = os.path.join(HERE, "..", "..", "assets", "rigs", "R6_IK.rig.json")
_REST = None
_DOC = None


def rest_doc():
    global _DOC
    if _DOC is None:
        with open(RIG_DATA, encoding="utf-8") as fh:
            _DOC = json.load(fh)
    return _DOC


def rest():
    global _REST
    if _REST is None:
        with open(RIG_DATA, encoding="utf-8") as fh:
            _REST = {k: {**v, "L": np.array(v["matrix_local"], dtype=float)} for k, v in json.load(fh)["bones"].items()}
    return _REST


def quat_mat(q):
    """[w, x, y, z] -> 3x3"""
    w, x, y, z = (float(v) for v in q)
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def euler_xyz(e):
    """Blender euler XYZ (radians) -> 3x3 (R = Rz · Ry · Rx)"""
    x, y, z = (float(v) for v in e)
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rz @ ry @ rx


def m4(R=None, t=None):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    if t is not None:
        M[:3, 3] = t
    return M


def basis(c):
    """a control's keyed values {loc, quat | euler} -> B = T(loc) R"""
    c = c or {}
    R = euler_xyz(c["euler"]) if "euler" in c else quat_mat(c.get("quat", (1, 0, 0, 0)))
    return m4(R, np.array(c.get("loc", (0, 0, 0)), dtype=float))


def local_delta(name, c):
    L = rest()[name]["L"]
    return L @ basis(c) @ np.linalg.inv(L)


def unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


def arc(a, b):
    """the shortest rotation taking direction a to direction b (Blender's Damped Track)"""
    a, b = unit(a), unit(b)
    v = np.cross(a, b)
    s, c = float(np.linalg.norm(v)), float(np.dot(a, b))
    if s < 1e-12:
        return np.eye(3) if c > 0 else -np.eye(3)
    k = v / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    ang = math.atan2(s, c)
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)


def mat_quat(R):
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1) * 2
        q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = [(R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s]
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = [(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s]
    else:
        s = math.sqrt(1 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = [(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s]
    return np.array(q)


def blend(A, B, w):
    """COPY_TRANSFORMS with influence w over A: location lerp, rotation slerp (unit scale)"""
    if w <= 1e-9:
        return A
    if w >= 1 - 1e-9:
        return B
    qa, qb = mat_quat(A[:3, :3]), mat_quat(B[:3, :3])
    if np.dot(qa, qb) < 0:
        qb = -qb
    d = float(np.clip(np.dot(qa, qb), -1, 1))
    th = math.acos(d)
    q = qa if th < 1e-9 else (math.sin((1 - w) * th) * qa + math.sin(w * th) * qb) / math.sin(th)
    return m4(quat_mat(q), A[:3, 3] * (1 - w) + B[:3, 3] * w)


SIDES = {"R": ("Right Leg", "Foot.R", "Uleg.R", "FKLeg.R", "Leg.R", "Bone.006", "SoftIK.R"),
         "L": ("Left Leg", "Foot.L", "Uleg.L", "FKLeg.L", "Leg.L", "Bone.005", "SoftIK.L")}


def knee_point(H, T, pole, a):
    """the 2-bone IK chain's joint (Uleg.*.001's head): on a circle of radius a (0.118) about the hip anchor H, swung
    from the H->foot line TOWARD the knee pole by an angle that depends only on the hip-foot distance d - measured on
    the rig (assets/rigs/R6_IK.rig.json ik_knee_swing): 0 deg beyond 2.3 studs, 90 deg at ~1.69, 180 deg (folded back)
    below ~1.06. The visible leg aims from the foot at this point, so the pole tilts the leg by at most ~4 degrees."""
    table = rest_doc()["ik_knee_swing"]["d_phi"]
    v = T - H
    d = float(np.linalg.norm(v))
    u = v / d if d > 1e-9 else np.array([0, 0, -1.0])
    ds = [x[0] for x in table]
    phs = [x[1] for x in table]
    phi = math.radians(float(np.interp(d, ds, phs)))
    p = pole - H
    side = p - np.dot(p, u) * u
    side = unit(side) if np.linalg.norm(side) > 1e-9 else unit(np.cross(u, [1.0, 0, 0]))
    return H + a * (math.cos(phi) * u + math.sin(phi) * side)


def parts(ctrl):
    """ctrl: {control name: {"loc": [..], "quat": [w,x,y,z]} | {"euler": [..]}, "SoftIK.L": {"loc": [x,0,0], "FK": bool}}
    -> {part: 4x4 world delta from rest}"""
    R = rest()
    D_main = local_delta("Main Controller", ctrl.get("Main Controller"))
    D_body = D_main @ local_delta("Body", ctrl.get("Body"))
    out = {"HumanoidRootPart": np.eye(4), "Torso": D_body}
    for arm, c in (("Right Arm", "Arm.R"), ("Left Arm", "Arm.L")):
        out[arm] = D_body @ local_delta(c, ctrl.get(c))
    # inherit rotation OFF: the head's pivot rides the body's NECK POINT (the body's whole motion, lever included), its
    # turn is only its own - no ancestor's rotation (not the Body's, not the Main Controller's)
    # (its own slide, though, is carried WITH the body's turn: the pivot is D_body applied to the slid neck point)
    Lh = R["Head.001"]["L"]
    hc = ctrl.get("Head.001") or {}
    slide = Lh[:3, :3] @ np.array(hc.get("loc", (0, 0, 0)), dtype=float)
    pivot = (D_body @ np.append(Lh[:3, 3] + slide, 1.0))[:3]
    Rh = Lh[:3, :3] @ basis({k: v for k, v in hc.items() if k != "loc"})[:3, :3] @ Lh[:3, :3].T
    out["Head"] = m4(Rh, pivot - Rh @ Lh[:3, 3])
    for side, (leg, foot, uleg, fkleg, world, pinned, soft) in SIDES.items():
        D_foot = D_main @ local_delta(foot, ctrl.get(foot))
        F0 = R[foot]["L"][:3, 3]
        F = (D_foot @ np.append(F0, 1.0))[:3]
        if F[2] < 0:                                       # Limit Location: z >= 0 for the foot's head
            D_foot = m4(None, np.array([0, 0, -F[2]])) @ D_foot
            F = (D_foot @ np.append(F0, 1.0))[:3]
        D_uleg = D_body @ local_delta(uleg, ctrl.get(uleg))
        H = (D_uleg @ np.append(R[uleg]["L"][:3, 3], 1.0))[:3]
        y5 = R[pinned]["L"][:3, 1]
        knee = ("Knee.R" if side == "R" else "Knee.L")
        D_knee = D_foot @ local_delta(knee, ctrl.get(knee))
        Kp = (D_knee @ np.append(R[knee]["L"][:3, 3], 1.0))[:3]
        K = knee_point(H, F, Kp, R[uleg]["length"])
        A = arc(D_foot[:3, :3] @ y5, K - F)
        D_ik = m4(None, F) @ m4(A) @ m4(None, -F) @ D_foot
        s = ctrl.get(soft) or {}
        w = min(1.0, max(0.0, abs(float((s.get("loc") or (0, 0, 0))[0])) / 2.0))
        fk_box = bool(s.get("FK", True))
        D_base = (D_body @ local_delta(fkleg, ctrl.get(fkleg))) if fk_box else (D_main @ local_delta(world, ctrl.get(world)))
        Lg = R["Leg.R1" if side == "R" else "Leg.L1"]["L"]
        # COPY_TRANSFORMS blends the bones' WORLD matrices (heads lerped, rotations slerped), not their deltas
        out[leg] = blend(D_base @ Lg, D_ik @ Lg, w) @ np.linalg.inv(Lg)
    return out
