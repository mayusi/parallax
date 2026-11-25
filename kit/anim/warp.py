"""warp.py — MOTION WARPING: edit a dense human-made clip by displacement maps instead of re-authoring it
(experiment 2026-10-12, GsRun v2). Every op works on character-space quaternion frames ([qx,qy,qz,qw,px,py,pz],
kit/anim/clip.py) and keeps the base's own dense curves; nothing is re-keyed.

    time_warp(c, factor=None, mapping=None)   new timeline, resampled at 60 fps by slerp (positions lerp). factor scales
                                              the DURATION (0.9 = 10% faster); mapping = [[t_out, t_in], ...] monotone
    amp_scale(c, joint, axis, k)              scales one character-space axis of the joint's motion about its MEAN pose
    additive(c, joint, keys, loop=None)       sparse offsets [{t, rot: [x,y,z] deg, pos: [x,y,z]}] -> a smooth cubic
                                              spline (periodic on a loop) -> applied ON TOP of every dense frame
    hold_mean(c, joint, to)                   a held offset FROM THE DATA: the joint's mean pose moved to `to`
    delay(c, joint, frames)                   the joint's curve shifted later (overlap / drag)
    hold_from(c, joint, src)                  (spec op "hold_from") a hold MINED from another clip, ground frame
    inherit_twist(c, joint, share)            the limb follows only `share` of the torso's yaw swing
    time_warp(..., contacts=1.25)             (spec) foot-contact frames get 1.25x the time of the rest
    sword_track(c, ...)                       (spec op "sword") the blade's path for the look, in the fist
    fill (spec op)                            keys kept, short gaps slerp, long gaps the motion model (motion_fill.py)
    transplant(base, donor, joints)           the donor's joints, time-warped onto the base's stride (cycle length +
                                              phase matched on the right leg's swing), replace the base's

A <Name>.warp.json spec: {"name", "base": <library id | build clip name | path>, "ops": [{"op": ...}, ...],
"loop"?, "priority"?} -> `python kit/anim/warp.py <spec> --out build/animations/<Name>.clip.json` (kit anim runs it
for every assets/animations/<Name>.warp.json). The clip is exported as dense frames: Linear easing per frame."""
import copy
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import derive as D  # noqa: E402

FPS = 60
LIB = os.path.join("_artifacts", "r6lib", "clips")
AXES = {"X": 0, "Y": 1, "Z": 2}


# ---------------------------------------------------------------- sampling
def _frames(c, j):
    return np.asarray(c["joints"][j]["frames"], float)


def _period(c):
    return float(c["times"][-1])


def sample_joint(F, times, t, loop):
    """the joint's frame at time t (slerp between the two neighbouring frames; a loop wraps)"""
    times = np.asarray(times, float)
    dur = float(times[-1])
    if loop and dur > 0:
        t = t % dur
    t = min(max(t, 0.0), dur)
    i = int(np.searchsorted(times, t, side="right") - 1)
    i = max(0, min(i, len(times) - 2))
    a, b = times[i], times[i + 1]
    u = 0.0 if b <= a else (t - a) / (b - a)
    q = C.slerp(F[i][:4], F[i + 1][:4], u)
    p = F[i][4:7] * (1 - u) + F[i + 1][4:7] * u
    return np.concatenate([q, p])


def resample(c, t_in_of_out, n_out):
    """a new clip whose frame k (time k/60) is the old clip at t_in_of_out(k/60)"""
    out = copy.deepcopy(c)
    loop = bool(c.get("loop"))
    for j in c["joints"]:
        F = _frames(c, j)
        D.set_frames(out, j, [sample_joint(F, c["times"], t_in_of_out(k / FPS), loop) for k in range(n_out)])
    out["times"] = [round(k / FPS, 6) for k in range(n_out)]
    out["duration"] = out["times"][-1]
    out["fps"] = FPS
    return out


def to60(c):
    if int(round(float(c.get("fps") or 30))) == FPS and np.allclose(np.diff(c["times"]), 1 / FPS, atol=1e-4):
        return copy.deepcopy(c)
    dur = _period(c)
    return resample(c, lambda t: t, int(round(dur * FPS)) + 1)


# ---------------------------------------------------------------- ops
def time_warp(c, factor=None, mapping=None):
    """factor: the new duration = factor x the old (resampled at 60 fps). mapping: [[t_out, t_in], ...] piecewise
    linear and monotone (the last t_out is the new duration)"""
    dur = _period(c)
    if mapping:
        mp = np.asarray(mapping, float)
        if np.any(np.diff(mp[:, 0]) <= 0) or np.any(np.diff(mp[:, 1]) < 0):
            raise ValueError("time_warp mapping must be monotone")
        new = float(mp[-1, 0])
        f = lambda t: float(np.interp(t, mp[:, 0], mp[:, 1]))  # noqa: E731
    else:
        factor = float(factor)
        new = dur * factor
        f = lambda t: t / factor  # noqa: E731
    return resample(c, f, int(round(new * FPS)) + 1)


def amp_scale(c, joint, axis, k):
    """scale the joint's rotation about ONE character-space axis (or "all") by k, measured from its mean pose (the motion grows or
    shrinks; the average pose stays)"""
    F = _frames(c, joint)
    mean = D.qmean([f[:4] for f in F])
    axes = [0, 1, 2] if str(axis).lower() == "all" else [AXES[axis.upper()]]
    out = []
    for f in F:
        d = D.qlog(D.qmul(f[:4], D.qinv(mean)))          # the frame's offset from the mean, in character axes
        for ax in axes:
            d[ax] *= float(k)
        q = D.qmul(D.qexp(d), mean)
        out.append(np.concatenate([q, f[4:7]]))
    D.set_frames(c, joint, out)
    return c


def additive(c, joint, keys, loop=None, counter=()):
    """offsets keyed sparsely ({t, rot [x,y,z] deg, pos [x,y,z] studs}) -> a smooth cubic spline through them (periodic
    on a loop: the seam stays closed) -> each dense frame pre-multiplied by the offset rotation, its position shifted"""
    from scipy.interpolate import CubicSpline
    loop = bool(c.get("loop")) if loop is None else loop
    ks = sorted(keys, key=lambda k: float(k["t"]))
    T = [float(k["t"]) for k in ks]
    R = np.array([[math.radians(v) for v in k.get("rot", [0, 0, 0])] for k in ks])
    P = np.array([list(k.get("pos", [0, 0, 0])) for k in ks], float)
    dur = _period(c)
    if loop:
        # periodic: the curve closes on itself at the clip's length
        if not T or T[-1] < dur - 1e-6:
            T, R, P = T + [T[0] + dur], np.vstack([R, R[:1]]), np.vstack([P, P[:1]])
        bc = "periodic"
    else:
        bc = "natural"
    if len(T) == 1:
        rot_at = lambda t: R[0]  # noqa: E731
        pos_at = lambda t: P[0]  # noqa: E731
    else:
        sr, sp = CubicSpline(T, R, bc_type=bc), CubicSpline(T, P, bc_type=bc)

        def rot_at(t):
            return sr(((t - T[0]) % (T[-1] - T[0])) + T[0] if loop else min(max(t, T[0]), T[-1]))

        def pos_at(t):
            return sp(((t - T[0]) % (T[-1] - T[0])) + T[0] if loop else min(max(t, T[0]), T[-1]))
    F = _frames(c, joint)
    out, offs = [], []
    for t, f in zip(c["times"], F):
        e = rot_at(float(t))
        O = C.euler_mat([math.degrees(v) for v in e])
        offs.append(O)
        q = C.mat_quat(O @ C.quat_mat(f[:4]))
        out.append(np.concatenate([q, f[4:7] + pos_at(float(t))]))
    # counter: children that must keep their WORLD orientation while the parent turns (the legs under a leaning torso:
    # R6 legs are the torso's children). With R_t' = O R_t, the child's world turn R_t R_c K stays when
    # R_c' = R_t^-1 O^-1 R_t R_c (kit/anim/clip.py fk: the root's C0 and C1 rotations cancel)
    for ch in counter:
        G = _frames(c, ch)
        res = []
        for f_t, O, g in zip(F, offs, G):
            Rt = C.quat_mat(f_t[:4])
            Rc = Rt.T @ O.T @ Rt @ C.quat_mat(g[:4])
            res.append(np.concatenate([C.mat_quat(Rc), g[4:7]]))
        D.set_frames(c, ch, res)
    D.set_frames(c, joint, out)
    return c


def hold_mean(c, joint, to, frame="parent"):
    """a HELD offset computed from the data: every frame of the joint pre-multiplied by (target x mean^-1), so its
    average pose becomes `to` ([x, y, z] deg, CFrame.Angles order) and its motion rides on top. frame "parent": `to`
    is relative to the parent (the torso), as clip frames are; "world": `to` is the limb's turn relative to the
    character's root - the parent's MEAN turn is taken out (an arm 'hanging back' under a torso leaning 38 deg forward
    must be held 38 deg further back than in the torso's frame; GsRunV3, 2026-10-12)"""
    F = _frames(c, joint)
    mean = D.qmean([f[:4] for f in F])
    target = C.euler_mat(to)
    if frame == "world":
        pm = D.qmean([f[:4] for f in _frames(c, "Torso")])
        target = C.quat_mat(pm).T @ target                # world arm turn = R_torso R_arm (kit/anim/clip.py fk)
    O = target @ C.quat_mat(mean).T
    D.set_frames(c, joint, [np.concatenate([C.mat_quat(O @ C.quat_mat(f[:4])), f[4:7]]) for f in F])
    return c


def world_mean(c, joint):
    """the joint's mean turn RELATIVE TO THE ROOT (character space: R_torso R_joint for a torso child, kit/anim/clip.py
    fk; the R6 root's C0 and C1 rotations cancel) as a 3x3"""
    F = _frames(c, joint)
    if joint == "Torso":
        return C.quat_mat(D.qmean([f[:4] for f in F]))
    T = _frames(c, "Torso")
    qs = [C.mat_quat(C.quat_mat(t[:4]) @ C.quat_mat(f[:4])) for t, f in zip(T, F)]
    return C.quat_mat(D.qmean([np.asarray(q) for q in qs]))


def hold_from(c, joint, src, frame="world"):
    """a HOLD MINED from another clip: the joint's mean pose becomes the source clip's mean pose of that joint - in the
    ground (root) frame by default, so a carry keeps its angle to the ground under a leaning torso - its own motion rides
    on top (hold_mean underneath)"""
    if frame == "world":
        target = world_mean(src, joint)
        to = [math.degrees(v) for v in _euler(target)]
    else:
        to = [math.degrees(v) for v in _euler(C.quat_mat(D.qmean([f[:4] for f in _frames(src, joint)])))]
    return hold_mean(c, joint, to, frame)


def _euler(m):
    """3x3 -> (x, y, z) radians in CFrame.Angles order (Rx Ry Rz)"""
    sy = max(-1.0, min(1.0, float(m[0, 2])))
    y = math.asin(sy)
    if abs(sy) < 0.999999:
        return math.atan2(-m[1, 2], m[2, 2]), y, math.atan2(-m[0, 1], m[0, 0])
    return math.atan2(m[2, 1], m[1, 1]), y, 0.0


def torso_yaw(f):
    fw = C.quat_mat(f[:4]) @ np.array([0.0, 0.0, -1.0])
    return math.degrees(math.atan2(-fw[0], -fw[2]))


def inherit_twist(c, joint, share=0.5):
    """the limb follows only `share` of the torso's yaw swing about its mean (a carried blade swaying with half the
    body's twist): world turn R_t R_j -> Ry(-(1 - share) dyaw) R_t R_j, i.e. R_j' = R_t^T Ry(...) R_t R_j"""
    T, F = _frames(c, "Torso"), _frames(c, joint)
    yaws = np.degrees(np.unwrap(np.radians([torso_yaw(t) for t in T])))
    mean = float(np.mean(yaws))
    out = []
    for t, f, yw in zip(T, F, yaws):
        Rt = C.quat_mat(t[:4])
        Ry = C.euler_mat([0.0, -(1.0 - float(share)) * (yw - mean), 0.0])
        out.append(np.concatenate([C.mat_quat(Rt.T @ Ry @ Rt @ C.quat_mat(f[:4])), f[4:7]]))
    D.set_frames(c, joint, out)
    return c


def delay(c, joint, frames):
    """the joint's curve shifted LATER by n frames (a loop wraps; a one-shot holds its first frame)"""
    F = list(_frames(c, joint))
    n = int(frames)
    if c.get("loop"):
        body = F[:-1]                                     # the last frame repeats the first on a closed loop
        body = body[-n:] + body[:-n] if n else body
        F = body + [body[0]]
    else:
        F = [F[0]] * n + F[:len(F) - n]
    D.set_frames(c, joint, F)
    return c


def contact_mask(c, rig=None, tol=0.12):
    """per frame: is either foot on the ground (its lowest point within tol studs of the lowest it gets)"""
    rig = rig or C.load_rig("r6")
    Wf = C.world_frames(c, rig)
    low = {p: np.array([C.lowest(rig, p, np.asarray(w[p])) for w in Wf]) for p in ("Right Leg", "Left Leg") if p in Wf[0]}
    if not low:
        return np.zeros(len(Wf), bool)
    floor = min(v.min() for v in low.values())
    return np.any([v <= floor + tol for v in low.values()], axis=0)


def contact_mapping(c, factor, contact=1.25, rig=None):
    """a time map: the clip lasts factor x longer, and the frames with a foot on the ground get `contact` x the
    time of the others -> ([[t_out, t_in], ...], share of contact frames) for time_warp"""
    m = contact_mask(c, rig)
    w = np.where(m[:-1], float(contact), 1.0)             # the weight of each frame interval
    dur_in = _period(c)
    dt = np.diff(np.asarray(c["times"], float))
    out = np.concatenate([[0.0], np.cumsum(w * dt)])
    out *= dur_in * float(factor) / out[-1]
    return [[float(a), float(b)] for a, b in zip(out, c["times"])], float(np.mean(m))


def sword_track(c, joint="Right Arm", dir_local=(0.0, -0.39, 0.92), length=4.6, grip=0.75, tip_height=None):
    """the weapon's path for the look renderer (look.add_weapon): the grip in the fist (the arm's end), the blade along
    dir_local in the ARM's frame (x right, y up the arm, z back) - (0, -0.39, 0.92) trails back and down"""
    rig = C.load_rig("r6")
    Wf = C.world_frames(c, rig)
    d0 = np.asarray(dir_local, float)
    d0 = d0 / np.linalg.norm(d0)
    if tip_height is not None:
        # aim the blade (fixed in the fist): at the arm's MEAN pose it points straight back and down; the slope is
        # solved so the tip's LOWEST point over the cycle sits tip_height studs above the R6 floor (3 studs under the
        # root) - the body's bob and pitch swing a 4.6-stud blade, so aiming the MEAN at the floor put the tip 1.9
        # studs through it (GsRunV3a, 2026-10-12)
        Rm = C.quat_mat(D.qmean([C.mat_quat(np.asarray(w[joint])[:3, :3]) for w in Wf]))
        mats = [np.asarray(w[joint]) for w in Wf]
        grips_ = [m[:3, :3] @ np.array([0.0, -1.0, 0.0]) + m[:3, 3] for m in mats]

        def lowest_tip(dy):
            d_root = np.array([0.0, dy, math.sqrt(max(0.0, 1 - dy * dy))])
            dl = Rm.T @ d_root
            return min(float((g + m[:3, :3] @ dl * length)[1]) for g, m in zip(grips_, mats)) + 3.0, dl

        lo, hi = -0.95, 0.3                                 # lowest_tip grows with dy: bisect
        for _ in range(40):
            mid = (lo + hi) / 2
            if lowest_tip(mid)[0] < float(tip_height):
                lo = mid
            else:
                hi = mid
        d0 = lowest_tip(hi)[1]
    tips, grips = [], []
    for w in Wf:
        m = np.asarray(w[joint])
        g = m[:3, :3] @ np.array([0.0, -1.0, 0.0]) + m[:3, 3]
        d = m[:3, :3] @ d0
        grips.append([float(v) for v in g])
        tips.append([float(v) for v in g + d * length])
    c["sword"] = {"tip": tips, "grip_path": grips, "length": length, "grip": grip, "dir_local": list(d0)}
    return c


def leg_swing(c, joint="Right Leg"):
    """the leg's forward swing per frame (deg): the angle of the leg's down axis toward -Z in the torso's frame"""
    out = []
    for f in _frames(c, joint):
        d = C.quat_mat(f[:4]) @ np.array([0.0, -1.0, 0.0])
        out.append(math.degrees(math.atan2(-d[2], -d[1])))
    return np.asarray(out)


def transplant(base, donor, joints, align="stride"):
    """the donor's joints on the base. align "stride": the donor's cycle is stretched to the base's (both loops) and
    shifted so its right-leg swing lines up with the base's (circular cross-correlation); "none": cut at the start.
    Returns (clip, info)."""
    base, donor = to60(base), to60(donor)
    n = len(base["times"])
    db, dd = _period(base), _period(donor)
    info = {"base_period_s": round(db, 3), "donor_period_s": round(dd, 3), "scale": round(dd / db, 4), "shift_s": 0.0}
    if align == "stride" and donor.get("loop") and base.get("loop") and db > 0 and dd > 0:
        stretched = resample(donor, lambda t: t * dd / db, n)          # one donor cycle over one base cycle
        sb, sd = leg_swing(base)[:-1], leg_swing(stretched)[:-1]
        sb, sd = sb - sb.mean(), sd - sd.mean()
        cc = [float(np.dot(sb, np.roll(sd, -s))) for s in range(len(sb))]
        shift = int(np.argmax(cc))
        info.update(shift_s=round(shift / FPS, 3), swing_corr=round(cc[shift] / max(1e-9, np.linalg.norm(sb) * np.linalg.norm(sd)), 3))
        warped = resample(donor, lambda t: ((t + shift / FPS) % db) * dd / db, n)
    else:
        warped = resample(donor, lambda t: min(t, dd), n)
    out = copy.deepcopy(base)
    for k in ("finish", "finished", "finish_log"):               # (the base's finish is the base's: kit/anim/finish.py)
        out.pop(k, None)
    for j in joints:
        out["joints"][j] = {"frames": copy.deepcopy(warped["joints"][j]["frames"])}
    return out, info


# ---------------------------------------------------------------- specs
def load_ref(ref):
    """a library id, a built clip name, or a path"""
    if os.path.isfile(ref):
        return json.load(open(ref, encoding="utf-8")), ref
    p = os.path.join(LIB, f"{ref}.clip.json")
    if os.path.isfile(p):
        return json.load(open(p, encoding="utf-8")), p
    p = os.path.join("build", "animations", f"{ref}.clip.json")
    if os.path.isfile(p):
        return json.load(open(p, encoding="utf-8")), p
    raise FileNotFoundError(f"warp: no clip '{ref}' (library id, build clip name or path)")


def sha256_of(paths):
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def build(spec_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    base, base_path = load_ref(spec["base"])
    if base.get("rig") != "R6":
        raise ValueError(f"warp: base {spec['base']} is a {base.get('rig')} clip; warp edits R6 clips")
    c = to60(base)
    if "loop" in spec:
        c["loop"] = bool(spec["loop"])
    log, inputs = [], [base_path]
    for op in spec.get("ops", []):
        kind = op["op"]
        if kind == "transplant":
            donor, dpath = load_ref(op["donor"])
            inputs.append(dpath)
            c, info = transplant(c, donor, op["joints"], op.get("align", "stride"))
            log.append({"op": kind, "donor": op["donor"], "joints": op["joints"], **info})
        elif kind == "time_warp":
            if op.get("contacts"):
                mapping, share = contact_mapping(c, op.get("factor", 1.0), op["contacts"])
                c = time_warp(c, mapping=mapping)
                log.append({"op": kind, "factor": op.get("factor"), "contacts": op["contacts"], "contact_share": round(share, 3)})
            else:
                c = time_warp(c, op.get("factor"), op.get("mapping"))
                log.append({"op": kind, "factor": op.get("factor"), "mapping": op.get("mapping")})
        elif kind == "hold_mean":
            hold_mean(c, op["joint"], op["to"], op.get("frame", "parent"))
            log.append(dict(op))
        elif kind == "hold_from":
            src, spath = load_ref(op["clip"])
            inputs.append(spath)
            hold_from(c, op["joint"], to60(src), op.get("frame", "world"))
            log.append(dict(op))
        elif kind == "inherit_twist":
            inherit_twist(c, op["joint"], op.get("share", 0.5))
            log.append(dict(op))
        elif kind == "fill":
            # the HYBRID FILL (kit/anim/motion_fill.py): keys kept; short gaps slerp, long gaps the motion model
            import motion_fill as MF
            keys = op.get("keys") or [round(float(t) * FPS) for t in op.get("keys_s", [])]
            c, info = MF.fill(c, keys, op.get("model", "medium_v3"), op.get("k", 4), op.get("short", 30), op.get("long", 45),
                              op.get("group", "locomotion"), op.get("tags"), op.get("quality", 0))
            log.append({"op": kind, **info})
        elif kind == "delay":
            delay(c, op["joint"], op["frames"])
            log.append(dict(op))
        elif kind == "sword":
            sword_track(c, op.get("joint", "Right Arm"), op.get("dir_local", (0.0, -0.39, 0.92)), op.get("length", 4.6),
                        tip_height=op.get("tip_height"))
            log.append(dict(op))
        elif kind == "amp_scale":
            amp_scale(c, op["joint"], op["axis"], op["k"])
            log.append(dict(op))
        elif kind == "additive":
            additive(c, op["joint"], op["keys"], op.get("loop"), op.get("counter", ()))
            log.append({"op": kind, "joint": op["joint"], "keys": len(op["keys"])})
        else:
            raise ValueError(f"warp: unknown op '{kind}'")
    c["name"] = spec["name"]
    c["rig"] = "R6"
    c["priority"] = spec.get("priority", base.get("priority", "Movement"))
    c.pop("keys", None)
    for j in c["joints"]:
        c["joints"][j].pop("keys", None)                  # dense frames only: the export writes them Linear
    c["events"] = spec.get("events", [])
    c["gate"] = spec.get("gate", base.get("gate"))
    c["warp_log"] = log
    here = os.path.abspath(__file__)
    c["source"] = {"kind": "warp", "file": spec_path, "sha256": sha256_of([spec_path]),
                   "data_sha256": sha256_of(inputs), "inputs": inputs,
                   "tool_sha256": sha256_of([here, C.__file__]), "rig_sha256": sha256_of([C.rig_path("r6")])}
    return c


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    try:
        c = build(argv[0])
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"warp {argv[0]}: {e}", "next_action": "fix the .warp.json"}))
        return 1
    out = out or os.path.join("build", "animations", f"{c['name']}.clip.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(c, open(out, "w", encoding="utf-8"))
    seams = [C.quat_angle(c["joints"][j]["frames"][0], c["joints"][j]["frames"][-1]) for j in c["joints"]]
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"warp {c['name']}: {len(c['times'])} frames at 60 fps ({c['times'][-1]:.3f} s), ops {[o['op'] for o in c['warp_log']]}, max loop seam {max(seams):.2f} deg -> {out}",
                      "next_action": f"lune run kit anim {c['name']}", "log": c["warp_log"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
