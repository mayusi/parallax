"""proc_physics.py — PHYSICS PLAUSIBILITY for R6 clips with MuJoCo (Apache-2.0, vetted 2026-10-14, VETLOG). The R6 rig
(kit/anim/rigs/r6.json) becomes a 6-box MuJoCo model: the Torso a free body, Head / arms / legs on ball joints at
the rig's own C0 pivots (3 slide joints first: the limb slides), each box placed by C1^-1, mass = volume, Roblox gravity
(196.2 studs/s^2, -Y). A clip is replayed frame by frame (the joint transform = the engine's joint-space T, slide then
rotation, so every part matches kit/anim/clip.py fk exactly - checked: 0.000 studs) and MuJoCo's INVERSE DYNAMICS gives the joint torques that motion needs.
  torque_rate   per joint, the 99th percentile of |d torque / dt| (normalised by the body's weight x 1 stud): a
                physically impossible SNAP shows as a spike
  balance       on frames where a foot is planted, how often the centre of mass leaves the feet's support (their
                soles' extent + 0.25 studs)
calibrate() measures both on the owner's loved clips per category (statistics only); check() places a clip against them.
    python kit/anim/proc_physics.py calibrate        -> assets/animations/calibration/proc_physics.json
    python kit/anim/proc_physics.py check <clip.json> [--category idle]"""
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

PARTS = ["Torso", "Head", "Left Arm", "Left Leg", "Right Arm", "Right Leg"]
CAL = os.path.join("assets", "animations", "calibration", "proc_physics.json")
G = 196.2
_M = None


def wxyz(m):
    q = C.mat_quat(np.asarray(m)[:3, :3])                     # [x, y, z, w]
    return [float(q[3]), float(q[0]), float(q[1]), float(q[2])]


def mjcf(rig):
    """the R6 rig as MJCF (Y up: gravity along -Y)"""
    def box(part, frame):
        s = [x / 2 for x in rig["sizes"][part]]
        q = wxyz(frame)
        p = np.asarray(frame)[:3, 3]
        return (f'<geom name="{part}" type="box" size="{s[0]} {s[1]} {s[2]}" pos="{p[0]} {p[1]} {p[2]}" '
                f'quat="{q[0]} {q[1]} {q[2]} {q[3]}" density="1"/>')
    kids = []
    for part in PARTS[1:]:
        j = rig["joints"][part]
        c0, c1 = C.cf(j["c0"]), C.cf(j["c1"])
        q0 = wxyz(c0)
        kids.append(f'<body name="{part}" pos="{c0[0, 3]} {c0[1, 3]} {c0[2, 3]}" quat="{q0[0]} {q0[1]} {q0[2]} {q0[3]}">'
                    f'<joint name="{part}_sx" type="slide" axis="1 0 0"/><joint name="{part}_sy" type="slide" axis="0 1 0"/>'
                    f'<joint name="{part}_sz" type="slide" axis="0 0 1"/>'                     # the limb SLIDE (T's
                    f'<joint name="{part}" type="ball"/>{box(part, np.linalg.inv(c1))}</body>')   # translation), then T
    tc1 = C.cf(rig["joints"]["Torso"]["c1"])
    return (f'<mujoco><option gravity="0 {-G} 0" timestep="{1 / 60}"/><worldbody>'
            f'<body name="Torso"><freejoint name="root"/>{box("Torso", np.eye(4))}{"".join(kids)}</body>'
            f'</worldbody></mujoco>'), tc1


def model():
    global _M
    if _M is None:
        import mujoco
        rig = C.load_rig("r6")
        xml, _ = mjcf(rig)
        m = mujoco.MjModel.from_xml_string(xml)
        _M = (m, rig)
    return _M


def qpos_frames(clip):
    """per frame: MuJoCo qpos (torso world pose from fk + each ball joint's joint-space rotation T)"""
    import mujoco
    m, rig = model()
    W = C.world_frames(clip, rig)
    out = []
    for i, w in enumerate(W):
        tr = C.character_transforms(clip, rig, i)
        q = np.zeros(m.nq)
        tw = np.asarray(w["Torso"])
        q[:3] = tw[:3, 3]
        q[3:7] = wxyz(tw)
        for part in PARTS[1:]:
            adr = m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, part)]
            R, p = tr.get(part, (np.eye(3), np.zeros(3)))
            tj, pj = C.joint_space(rig, part, R, p)
            m4 = np.eye(4)
            m4[:3, :3] = tj
            q[adr:adr + 4] = wxyz(m4)
            for ax, name in enumerate(("_sx", "_sy", "_sz")):
                q[m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, part + name)]] = pj[ax]
        out.append(q)
    return np.array(out), W


def analyse(clip, band=0.06):
    import mujoco
    m, rig = model()
    d = mujoco.MjData(m)
    Q, W = qpos_frames(clip)
    n = len(Q)
    dt = 1.0 / clip.get("fps", 60)
    if n < 5:
        return None
    V = np.zeros((n, m.nv))
    for i in range(1, n):
        mujoco.mj_differentiatePos(m, V[i], dt, Q[i - 1], Q[i])
    V[0] = V[1]
    A = np.gradient(V, dt, axis=0)
    tau = np.zeros((n, m.nv))
    com = np.zeros((n, 3))
    for i in range(n):
        d.qpos[:] = Q[i]
        d.qvel[:] = V[i]
        d.qacc[:] = A[i]
        mujoco.mj_inverse(m, d)
        tau[i] = d.qfrc_inverse
        com[i] = d.subtree_com[1]
    weight = float(m.body_subtreemass[1]) * G
    out = {"torque_rate": {}}
    for part in PARTS[1:]:
        dof = m.jnt_dofadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, part)]
        t = np.linalg.norm(tau[:, dof:dof + 3], axis=1) / weight
        out["torque_rate"][part] = round(float(np.percentile(np.abs(np.gradient(t, dt)), 99)), 3)
    # balance: frames with a planted foot - is the centre of mass inside the planted soles' extent (+0.25)?
    sole = {leg: np.array([(np.asarray(w[leg]) @ np.array([0.0, -1.0, 0.0, 1.0]))[:3] for w in W]) for leg in ("Right Leg", "Left Leg")}
    floor = min(s[:, 1].min() for s in sole.values())
    planted = 0
    outside = 0
    for i in range(n):
        feet = [sole[l][i] for l in sole if sole[l][i][1] <= floor + band]
        if not feet:
            continue
        planted += 1
        F = np.array(feet)
        lo, hi = F[:, [0, 2]].min(0) - 0.25 - 0.5, F[:, [0, 2]].max(0) + 0.25 + 0.5   # a sole is ~1 stud wide
        c = com[i, [0, 2]]
        if np.any(c < lo) or np.any(c > hi):
            outside += 1
    out["balance_outside"] = round(outside / planted, 3) if planted else None
    return out


def calibrate():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import translate_test as TT
    per = {}
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or re.search(r"victim|knocked", lb["text"] or "", re.I):
            continue
        c = TT.loved_clip(lb["id"])[0]
        if c.get("rig") != "R6":
            continue
        try:
            a = analyse(c)
        except Exception:
            continue
        if a:
            per.setdefault(lb["group"], []).append(a)
    cal = {}
    for g, rows in per.items():
        tr = {p: [r["torque_rate"][p] for r in rows] for p in PARTS[1:]}
        bal = [r["balance_outside"] for r in rows if r["balance_outside"] is not None]
        cal[g] = {"clips": len(rows), "torque_rate_p95": {p: round(float(np.percentile(v, 95)), 3) for p, v in tr.items()},
                  "balance_outside_p90": round(float(np.percentile(bal, 90)), 3) if bal else None}
    os.makedirs(os.path.dirname(CAL), exist_ok=True)
    json.dump({"schema": 1, "about": "loved-clip physics STATISTICS (MuJoCo inverse dynamics) - no poses", "categories": cal}, open(CAL, "w"), indent=1)
    return cal


def check(c, category):
    cal = json.load(open(CAL, encoding="utf-8"))["categories"][category]
    a = analyse(c)
    snaps = {p: v for p, v in a["torque_rate"].items() if v > 1.5 * cal["torque_rate_p95"][p]}
    bal = a["balance_outside"]
    unbal = bal is not None and cal["balance_outside_p90"] is not None and bal > max(cal["balance_outside_p90"], 0.05)
    return {"pass": not snaps and not unbal, "snaps": snaps, "balance_outside": bal, "loved_balance_p90": cal["balance_outside_p90"],
            "torque_rate": a["torque_rate"]}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["calibrate"]:
        cal = calibrate()
        print(json.dumps({k: {"clips": v["clips"], "balance_p90": v["balance_outside_p90"]} for k, v in cal.items()}))
    elif sys.argv[1:2] == ["check"]:
        cat = sys.argv[sys.argv.index("--category") + 1] if "--category" in sys.argv else "idle"
        print(json.dumps(check(json.load(open(sys.argv[2], encoding="utf-8")), cat), indent=1))


def to_clip(Q, template):
    """MuJoCo qpos frames -> a clip in the rig's character space (the inverse of qpos_frames): the free torso's world
    pose -> the Torso joint's transform under the root (no root track), each ball + slide -> R = C0 T C0^T, p = C0 p_j"""
    import copy
    import mujoco
    m, rig = model()
    c = copy.deepcopy(template)
    tj0 = rig["joints"]["Torso"]
    C0t, C1t = C.cf(tj0["c0"]), C.cf(tj0["c1"])
    frames = {j: [] for j in PARTS}
    for q in Q:
        wt = np.eye(4)
        wt[:3, :3] = C.quat_mat([q[4], q[5], q[6], q[3]])
        wt[:3, 3] = q[:3]
        T = np.linalg.inv(C0t) @ wt @ C1t                      # world_torso = C0 @ T @ C1^-1 (root = identity)
        c0r = C0t[:3, :3]
        R, p = c0r @ T[:3, :3] @ c0r.T, c0r @ T[:3, 3]
        frames["Torso"].append(list(C.mat_quat(R)) + [float(x) for x in p])
        for part in PARTS[1:]:
            j = rig["joints"][part]
            c0r = C.cf(j["c0"])[:3, :3]
            adr = m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, part)]
            tj = C.quat_mat([q[adr + 1], q[adr + 2], q[adr + 3], q[adr]])
            pj = np.array([q[m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, part + s)]] for s in ("_sx", "_sy", "_sz")])
            R, p = c0r @ tj @ c0r.T, c0r @ pj
            frames[part].append(list(C.mat_quat(R)) + [float(x) for x in p])
    for j in PARTS:
        c["joints"][j] = {"frames": frames[j]}
    c["times"] = [round(i / c.get("fps", 60), 6) for i in range(len(Q))]
    c.pop("root", None)
    return c


def simulate(clip, hits=(), neck_deg=None, **kw):
    """_simulate with a NECK: the Head's ball joint limited to a `neck_deg` cone (from the joint's zero; an idle that
    holds its head turned adds its offset) and the head-arm contacts off, for the run. Without it the head was stopped
    only by COLLIDING with the arms / torso - in a guard stance the gloves sit by the face, so a head hook bounced off
    them (the jitter gate: shake 2.2 vs the loved 1.8), and with those contacts gone the head spun 130-176 deg.
    neck_deg=None (the default): neither - an opt-in (proc_react's dossiers), so other reactions keep their physics.
    EVERYTHING the run changes on the shared cached model is restored after (the neck, the contacts, and _simulate's
    own timestep / integrator / damping / armature): inverse dynamics - the physics gate - read a model a simulate had
    left damped, and its torque rates depended on whether a reaction had run first in the process (review 2026-10-16)."""
    import mujoco
    m, _ = model()
    jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "Head")
    old = (int(m.jnt_limited[jid]), m.jnt_range[jid].copy())
    old_c = (m.geom_contype.copy(), m.geom_conaffinity.copy())
    old_o = (m.opt.timestep, m.opt.integrator, m.dof_damping.copy(), m.dof_armature.copy())
    if neck_deg is not None:
        m.jnt_limited[jid] = 1
        m.jnt_range[jid] = [0.0, np.radians(neck_deg)]
        # the head no longer collides with the ARMS (Roblox never collides a character's own parts; the neck is the
        # limit now): a head hook in a guard stance bounced off the gloves - shake 2.2 -> 1.1 (loved reactions 0.9-1.3)
        for g in range(m.ngeom):
            nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g)
            m.geom_contype[g] = m.geom_conaffinity[g] = {"Head": 2, "Torso": 3}.get(nm, 1)
    try:
        return _simulate(clip, hits=hits, **kw)
    finally:
        m.jnt_limited[jid], m.jnt_range[jid] = old[0], old[1]
        m.geom_contype[:], m.geom_conaffinity[:] = old_c
        m.opt.timestep, m.opt.integrator = old_o[0], old_o[1]
        m.dof_damping[:], m.dof_armature[:] = old_o[2], old_o[3]


def _simulate(clip, hits=(), w_joint=14.0, w_root=7.0, substeps=4, root_give=0.4, give_s=0.5, ff=True, root_kinematic=False,
              joint_give=0.4, part_give=0.1, root_rot_give=0.9):
    """FORWARD physics: the R6 body TRACKS the clip with PD control (per-dof stiffness from its own diagonal mass,
    critically damped, + inverse-dynamics feed-forward so a hit-free run follows the clip) and takes HITS:
    hits = [{"t": s, "part": "Head" | "Torso" | ..., "dir": [x, y, z] (world), "speed": studs/s change, "dur": s}].
    Around a hit the root's hold is loosened to `root_give` for `give_s` (the body gets knocked, then recovers).
    -> qpos frames"""
    import mujoco
    m, rig = model()
    d = mujoco.MjData(m)
    Qt, _ = qpos_frames(clip)
    n = len(Qt)
    fps = clip.get("fps", 60)
    dt = 1.0 / fps
    m.opt.timestep = dt / substeps
    m.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    Vt = np.zeros((n, m.nv))
    for i in range(1, n):
        mujoco.mj_differentiatePos(m, Vt[i], dt, Qt[i - 1], Qt[i])
    Vt[0] = Vt[1]
    At = np.gradient(Vt, dt, axis=0)
    # feed-forward torques along the target (inverse dynamics), per frame
    FF = np.zeros((n, m.nv))
    for i in range(n):
        d.qpos[:], d.qvel[:], d.qacc[:] = Qt[i], Vt[i], At[i]
        mujoco.mj_inverse(m, d)
        FF[i] = d.qfrc_inverse
    d.qpos[:] = Qt[0]
    d.qvel[:] = Vt[0]
    mujoco.mj_forward(m, d)
    M = np.zeros((m.nv, m.nv))
    try:
        mujoco.mj_fullM(m, d, M)                              # 3.15: (m, d, dst)
    except TypeError:
        mujoco.mj_fullM(m, M, d.qM)                           # older: (m, dst, qM)
    mdiag = np.maximum(np.diag(M), 1e-3)
    wv = np.full(m.nv, float(w_joint))
    wv[:6] = w_root
    out = [Qt[0].copy()]
    err = np.zeros(m.nv)
    # limb SLIDES are an animation offset, not a physical joint (left free they drifted tens of studs): prescribed
    sq = [m.jnt_qposadr[j] for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_SLIDE]
    sv = [m.jnt_dofadr[j] for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_SLIDE]
    m.dof_armature[sv] = 1e6                                  # and immovable: free, they ABSORBED a hit's force (a head
    # hook moved the neck 1.4 deg - the impulse went into a weightless slide, then got reset)
    bodies = {p: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, p) for p in PARTS}
    for i in range(1, n):
        t = i * dt
        w = wv.copy()
        for h in hits:                                       # a hit overpowers the 'muscles' for a moment, then they
            if 0 <= t - h["t"] < give_s:                     # firm up again; the STRUCK part's joint gives most (a
                u = (t - h["t"]) / give_s                    # soft root made a head hook turn the whole body, 7 deg,
                e_ = u * u * (3 - 2 * u)                     # and the neck 1 deg)
                w[:3] = np.minimum(w[:3], wv[:3] * (root_give + (1 - root_give) * e_))   # the body gets SHOVED
                w[3:6] = np.minimum(w[3:6], wv[3:6] * (root_rot_give + (1 - root_rot_give) * e_))   # but the planted
                # feet keep it from SPINNING (a free spin turned a head hook into a 31-deg body turn, 6 deg at the neck)
                w[6:] = np.minimum(w[6:], wv[6:] * (joint_give + (1 - joint_give) * e_))
                if h["part"] != "Torso":
                    jd = m.jnt_dofadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, h["part"])]
                    w[jd:jd + 3] = np.minimum(w[jd:jd + 3], wv[jd:jd + 3] * (part_give + (1 - part_give) * e_))
        kp, kd = mdiag * w * w, mdiag * 2 * w
        # stiff PD: the damping goes into the joints' own damping, integrated IMPLICITLY (explicit damping blew up in
        # 0.3 s); the target velocity's share of it is fed forward as a force
        m.dof_damping[:] = kd
        for _ in range(substeps):
            mujoco.mj_differentiatePos(m, err, 1.0, d.qpos, Qt[i])
            # computed-torque-lite: gravity + Coriolis compensation from the CURRENT state (qfrc_bias) + PD to the
            # target (the full inverse-dynamics feed-forward diverged open-loop within 10 frames - not used)
            d.qfrc_applied[:] = (d.qfrc_bias if ff else 0.0) + kp * err + kd * Vt[i]
            d.xfrc_applied[:] = 0
            for h in hits:
                if 0 <= t - h["t"] < h.get("dur", 0.05):
                    b = bodies[h["part"]]
                    mass = float(m.body_subtreemass[b]) if h["part"] != "Torso" else float(m.body_subtreemass[1])
                    dv = np.asarray(h["dir"], float) / np.linalg.norm(h["dir"]) * h["speed"]
                    F = mass * dv / h.get("dur", 0.05)
                    d.xfrc_applied[b, :3] = F
                    if h.get("spin", 0.0):                   # a glancing blow SPINS the part about its joint: the
                        r = d.xipos[b] - d.xanchor[m.jnt_bodyid.tolist().index(b)]   # torque the blow makes about
                        d.xfrc_applied[b, 3:6] = h["spin"] * np.cross(r, F)          # the joint, amplified
            mujoco.mj_step(m, d)
            d.qpos[sq] = Qt[i][sq]
            d.qvel[sv] = Vt[i][sv]
            if root_kinematic:
                d.qpos[:7] = Qt[i][:7]
                d.qvel[:6] = Vt[i][:6]
        out.append(d.qpos.copy())
    return np.array(out)


def _qmul_wxyz(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def react(clip, hits, **kw):
    """a PHYSICAL HIT REACTION layered on the clip: the body is simulated tracking the clip WITH and WITHOUT the hits,
    and only their difference is added to the original animation (the PD tracking lag is in both runs and cancels: a
    hit-free run returns the clip exactly). -> (clip, peak torso displacement studs)"""
    import mujoco
    m, rig = model()
    Qt, _ = qpos_frames(clip)
    Q0 = simulate(clip, **kw)
    Q1 = simulate(clip, hits=hits, **kw)
    out = Qt.copy()
    for i in range(len(Qt)):
        out[i, :3] = Qt[i, :3] + (Q1[i, :3] - Q0[i, :3])
        conj = Q0[i, 3:7] * np.array([1, -1, -1, -1])
        q = _qmul_wxyz(_qmul_wxyz(Q1[i, 3:7], conj), Qt[i, 3:7])
        out[i, 3:7] = q / np.linalg.norm(q)
        for j in range(m.njnt):
            if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_BALL:
                a = m.jnt_qposadr[j]
                conj = Q0[i, a:a + 4] * np.array([1, -1, -1, -1])
                q = _qmul_wxyz(_qmul_wxyz(Q1[i, a:a + 4], conj), Qt[i, a:a + 4])
                out[i, a:a + 4] = q / np.linalg.norm(q)
    disp = float(np.linalg.norm(Q1[:, :3] - Q0[:, :3], axis=1).max())
    return to_clip(out, clip), disp
