"""gmr_r6.py — GMR (General Motion Retargeting, Ze et al., ICRA 2026, MIT; github.com/YanjieZe/GMR @ bb1bbe40, VETLOG
2026-10-13) with R6 as the ROBOT: Kimodo's SOMA motion -> whole-body IK (mink on MuJoCo) -> an R6 clip. The baseline that
replaces our hand fold. Runs in its own venv (~/.venvs/gmr: mujoco, mink, daqp, qpsolvers, scipy); GMR's retarget class
is loaded from the clone with a bare package shim (its viewer / video / smplx deps are not needed or installed).

R6 ROBOT (MJCF, z-up, metres = studs x 0.3, built from the rig's own C0 / C1 numbers):
  Torso (free joint, its centre 0.9 m up) - Head (ball at the neck) - Right / Left Arm (ball at the shoulder pivots)
  - Right / Left Leg (ball at the hip pivots); end frames HeadTop, RightHand, LeftHand, RightFoot, LeftFoot (no joint)
  axes: MJ = (R6 x, -R6 z, R6 y), so R6 forward (-Z) is MJ +y; Kimodo (y-up, facing +Z) is turned to match
IK TABLES (GMR format: robot frame -> [human body, position cost, rotation cost, local position offset, rotation offset]):
  table 1  Torso <- Hips (pos 100, rot 10; offset up to the R6 torso centre), feet ends <- feet (pos 50),
           hand ends <- hands (pos 30)
           Head <- Head (rot 2), arms <- upper arms (rot 1), legs <- thighs (rot 1)
  table 2  the same targets, head rot 5, limbs rot 2 (GMR applies table 1's offsets to every body)
  rotation offsets from SOMA's REST pose (its arms rest out, R6's hang): the R6 limb's pivot -> end direction is turned
  onto the human limb's rest direction; scales (GMR's human_scale_table, about the root) from rest-pose lengths:
  feet / hips by hip height, hands / head by shoulder-to-hand reach
    <gmr venv> python kit/anim/gmr_r6.py <kimodo.npz> --out <clip.json>"""
import importlib
import json
import math
import os
import sys
import types

import numpy as np
from scipy.spatial.transform import Rotation as Rot

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
GMR_DIR = os.path.join(ROOT, "_downloads", "GMR")
OUT = os.path.join(ROOT, "_artifacts", "gmr_r6")
S = 0.3                                   # metres per stud
M = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])     # R6 / Kimodo (y-up) -> MuJoCo (z-up)
RZ180 = np.diag([-1.0, -1.0, 1.0])
LIMBS = {"RightArm": ("Right Arm", "RightArm", "RightHand"), "LeftArm": ("Left Arm", "LeftArm", "LeftHand"),
         "RightLeg": ("Right Leg", "RightLeg", "RightFoot"), "LeftLeg": ("Left Leg", "LeftLeg", "LeftFoot")}


def gmr_class():
    pkg = types.ModuleType("general_motion_retargeting")
    pkg.__path__ = [os.path.join(GMR_DIR, "general_motion_retargeting")]
    sys.modules["general_motion_retargeting"] = pkg
    return importlib.import_module("general_motion_retargeting.motion_retarget")


def r6_numbers():
    import clip as C
    r = C.load_rig("r6")
    j = lambda p: (np.asarray(r["joints"][p]["c0"][:3], float), np.asarray(r["joints"][p]["c1"][:3], float))  # noqa: E731
    return {p: j(p) for p in ("Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")}


def mj(v):
    return M @ np.asarray(v, float) * S


def build_mjcf(path):
    n = r6_numbers()
    fmt = lambda v: " ".join(f"{x:.4f}" for x in v)  # noqa: E731

    def limb(name, part, end_name, rgba):
        c0, c1 = n[part]
        centre = -c1                                       # the part centre, from its pivot (part axes = torso axes at rest)
        end = centre + np.array([0.0, -1.0, 0.0])
        return (f'<body name="{name}" pos="{fmt(mj(c0))}"><joint name="{name}_ball" type="ball"/>'
                f'<geom type="box" size="{fmt(np.abs(M @ np.array([0.5, 1.0, 0.5])) * S)}" pos="{fmt(mj(centre))}" rgba="{rgba}"/>'
                f'<body name="{end_name}" pos="{fmt(mj(end))}"/></body>')
    xml = f"""<mujoco model="r6">
  <option timestep="0.02"/>
  <worldbody>
    <geom name="floor" type="plane" size="10 10 0.1" rgba="0.5 0.5 0.5 1"/>
    <body name="Torso" pos="0 0 0.9">
      <freejoint name="root"/>
      <geom type="box" size="{fmt(np.abs(M @ np.array([1.0, 1.0, 0.5])) * S)}" rgba="0.2 0.4 0.8 1"/>
      <body name="Head" pos="{fmt(mj(n['Head'][0]))}"><joint name="Head_ball" type="ball"/>
        <geom type="box" size="{fmt(np.abs(M @ np.array([0.5, 0.5, 0.5])) * S)}" pos="{fmt(mj(-n['Head'][1]))}" rgba="0.9 0.8 0.2 1"/>
        <body name="HeadTop" pos="{fmt(mj(-n['Head'][1] + np.array([0, 0.5, 0])))}"/></body>
      {limb("RightArm", "Right Arm", "RightHand", "0.9 0.8 0.2 1")}
      {limb("LeftArm", "Left Arm", "LeftHand", "0.9 0.8 0.2 1")}
      {limb("RightLeg", "Right Leg", "RightFoot", "0.3 0.7 0.3 1")}
      {limb("LeftLeg", "Left Leg", "LeftFoot", "0.3 0.7 0.3 1")}
    </body>
  </worldbody>
</mujoco>"""
    open(path, "w", encoding="utf-8").write(xml)
    return n


def shortest_arc(a, b):
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(a @ b)
    if c < -0.999999:
        ax = np.cross(a, [1.0, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 0, 1.0])
        return Rot.from_rotvec(ax / np.linalg.norm(ax) * math.pi)
    return Rot.from_rotvec(v / max(np.linalg.norm(v), 1e-12) * math.atan2(np.linalg.norm(v), c))


def human_frames(npz, names):
    """Kimodo NPZ -> per frame {body: [pos (MJ, metres), quat wxyz]} turned to face R6's forward"""
    X, G = np.asarray(npz["posed_joints"], float), np.asarray(npz["global_rot_mats"], float)
    A = RZ180 @ M
    out = []
    for t in range(len(X)):
        d = {}
        for i, nm in enumerate(names):
            p = A @ X[t, i]
            Rm = A @ G[t, i] @ A.T
            d[nm] = [p, Rot.from_matrix(Rm).as_quat(scalar_first=True)]
        out.append(d)
    return out


def config(npz, names, parents, n6, path):
    """the GMR ik_config for SOMA -> R6, scales and rest offsets measured from SOMA's rest pose"""
    import kimodo_fold as K
    rest = K.rest_pose(npz, names, parents)
    J = {nm: i for i, nm in enumerate(names)}
    A = RZ180 @ M
    rp = lambda nm: A @ rest[J[nm]]  # noqa: E731
    floor_h = min(rp("RightFoot")[2], rp("LeftFoot")[2])
    hip_h = (rp("RightLeg")[2] + rp("LeftLeg")[2]) / 2 - floor_h
    r6_hip_h = 2.0 * S                                      # the R6 hip pivots stand 2 studs above the sole
    s_leg = r6_hip_h / hip_h
    arm_h = np.linalg.norm(rp("RightHand") - rp("RightArm")) + (rp("RightArm")[2] - (rp("RightLeg")[2] + rp("LeftLeg")[2]) / 2)
    r6_arm = (np.linalg.norm(-n6["Right Arm"][1] + np.array([0, -1, 0])) + (n6["Right Arm"][0][1] - n6["Right Leg"][0][1])) * S
    s_arm = r6_arm / arm_h

    def off(nm_h, part):
        c0, c1 = n6[part]
        d_r6 = mj(-c1 + np.array([0, -1.0, 0]))           # R6 pivot -> end at rest
        child = {"RightArm": "RightHand", "LeftArm": "LeftHand", "RightLeg": "RightFoot", "LeftLeg": "LeftFoot"}[nm_h]
        d_h = rp(child) - rp(nm_h)                         # the human limb at rest (its whole line)
        return list(shortest_arc(d_r6, d_h).as_quat(scalar_first=True))
    up = [0.0, 0.0, 1.0 * S]                               # hips (the R6 hip pivots) -> the torso centre, 1 stud up
    ident = [1.0, 0.0, 0.0, 0.0]
    # GMR applies the offsets of TABLE 1 to every body (and only for bodies table 1 weights): all bodies live in both
    t1 = {"Torso": ["Hips", 100, 10, up, ident], "RightFoot": ["RightFoot", 50, 0, [0, 0, 0], ident],
          "LeftFoot": ["LeftFoot", 50, 0, [0, 0, 0], ident], "RightHand": ["RightHand", 30, 0, [0, 0, 0], ident],
          "LeftHand": ["LeftHand", 30, 0, [0, 0, 0], ident], "Head": ["Head", 0, 2, [0, 0, 0], ident],
          "RightArm": ["RightArm", 0, 1, [0, 0, 0], off("RightArm", "Right Arm")],
          "LeftArm": ["LeftArm", 0, 1, [0, 0, 0], off("LeftArm", "Left Arm")],
          "RightLeg": ["RightLeg", 0, 1, [0, 0, 0], off("RightLeg", "Right Leg")],
          "LeftLeg": ["LeftLeg", 0, 1, [0, 0, 0], off("LeftLeg", "Left Leg")]}
    t2 = {k: list(v) for k, v in t1.items()}
    t2["Head"][2] = 5
    for k in ("RightArm", "LeftArm", "RightLeg", "LeftLeg"):
        t2[k][2] = 2
    cfg = {"robot_root_name": "Torso", "human_root_name": "Hips", "ground_height": 0.0, "human_height_assumption": 1.8,
           "use_ik_match_table1": True, "use_ik_match_table2": True,
           "human_scale_table": {"Hips": s_leg, "RightFoot": s_leg, "LeftFoot": s_leg, "RightLeg": s_leg, "LeftLeg": s_leg,
                                 "Head": s_arm, "RightArm": s_arm, "LeftArm": s_arm, "RightHand": s_arm, "LeftHand": s_arm},
           "ik_match_table1": t1, "ik_match_table2": t2}
    json.dump(cfg, open(path, "w", encoding="utf-8"), indent=1)
    return cfg, floor_h


def to_clip(qpos_list, mjm, name, fps=30):
    """MuJoCo qpos per frame -> an R6 clip (60 fps): torso world turn + height, limbs in the torso, travel = root track"""
    import clip as C
    import warp as W
    import mujoco
    adr = {}
    for jn in ("root", "Head_ball", "RightArm_ball", "LeftArm_ball", "RightLeg_ball", "LeftLeg_ball"):
        adr[jn] = mjm.jnt_qposadr[mujoco.mj_name2id(mjm, mujoco.mjtObj.mjOBJ_JOINT, jn)]
    frames = {j: [] for j in ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")}
    root = []
    for q in qpos_list:
        a = adr["root"]
        p, qt = q[a: a + 3], q[a + 3: a + 7]
        Rt = M.T @ Rot.from_quat(qt, scalar_first=True).as_matrix() @ M
        pr = M.T @ p / S                                   # studs, R6 axes; HRP rest = torso centre 3 studs up
        root.append([0.0, 0.0, 0.0, 1.0, float(pr[0]), 0.0, float(pr[2])])
        frames["Torso"].append(list(C.mat_quat(Rt)) + [0.0, float(pr[1] - 3.0), 0.0])
        for jn, part in (("Head_ball", "Head"), ("RightArm_ball", "Right Arm"), ("LeftArm_ball", "Left Arm"),
                         ("RightLeg_ball", "Right Leg"), ("LeftLeg_ball", "Left Leg")):
            b = adr[jn]
            Rl = M.T @ Rot.from_quat(q[b: b + 4], scalar_first=True).as_matrix() @ M
            frames[part].append(list(C.mat_quat(Rl)) + [0.0, 0.0, 0.0])
    T = len(qpos_list)
    clip = {"schema": 1, "name": name, "rig": "R6", "fps": fps, "loop": False, "priority": "Action",
            "times": [round(i / fps, 6) for i in range(T)], "events": [], "root": root,
            "joints": {j: {"frames": f} for j, f in frames.items()}, "source": {"kind": "gmr_r6"}}
    c60 = W.to60(clip)
    c60["root"] = [root[min(T - 1, int(round(i / 2)))] for i in range(len(c60["times"]))]
    return c60


def retarget(npz_path, name="gmr_r6"):
    import mujoco
    os.makedirs(OUT, exist_ok=True)
    sk = json.load(open(os.path.join(ROOT, "_artifacts", "kimodo", "somaskel77.json"), encoding="utf-8"))
    npz = np.load(npz_path)
    xml = os.path.join(OUT, "r6.xml")
    cfgp = os.path.join(OUT, "soma_to_r6.json")
    n6 = build_mjcf(xml)
    cfg, floor_h = config(npz, sk["names"], sk["parents"], n6, cfgp)
    mr = gmr_class()
    mr.ROBOT_XML_DICT["r6"] = xml
    mr.IK_CONFIG_DICT.setdefault("soma", {})["r6"] = cfgp
    g = mr.GeneralMotionRetargeting("soma", "r6", verbose=False)
    frames = human_frames(npz, sk["names"])
    # the human stands where SOMA's feet are: shift so the rest-pose floor is 0
    qs = []
    for d in frames:
        dd = {k: [v[0] - np.array([0, 0, floor_h]), v[1]] for k, v in d.items()}
        qs.append(g.retarget(dd))
    return to_clip(qs, g.model, name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    src = sys.argv[1]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(OUT, "out.clip.json")
    c = retarget(src, os.path.splitext(os.path.basename(out))[0])
    json.dump(c, open(out, "w", encoding="utf-8"))
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"GMR retargeted {src} -> {out} ({len(c['times'])} frames at 60 fps)",
                      "next_action": "evaluate + render it (diagnostics/translate_test.py)"}))
