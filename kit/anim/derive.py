"""derive.py — a NEW R6 animation derived from loved ones by editing their CURVES (a recipe of operations).

    python kit/anim/derive.py <Name>.derive.json --out <clip.json>

Why (2026-10-11): the owner called a finished community sprint "an amazing running animation"; everything the kit
generated from a few poses was "bad" to "horrible". Measured, the sprint's life is in dense limb curves (15-20 keys a
limb), uneven spacing and asymmetry - things four poses per step cannot hold. So new animations start FROM such
curves and change them the way an animator edits a graph, never the way a generator fills one in. Every operation
works on the clip's joint tracks (character space, gimbal-free: rotations are scaled in the quaternion log space
about the joint's own mean pose):

- {"op": "despike"}                                  spread single-frame jolts (kit/anim/snaps.py)
- {"op": "grip", "hands": "two" | "right" | "left", "at": {"right": studs, "left": studs}, "max_slide": 2.5}
                                                     the said hands PUT ONTO the weapon: each arm turned about its
                                                     shoulder and slid to its place on the hilt; the weapon stays
                                                     where it is (kit/anim/grip_solve.py)
- {"op": "clear", "max_deg": 30, "max_slide": 0.45, "blade_deg": 25, "tilt_deg": 20}   a hand, a foot or a blade that
                                                     passes THROUGH the body is moved out by the least that does it,
                                                     inside those bounds, eased over its neighbours - or the recipe
                                                     fails, named (kit/anim/collide_repair.py)
- {"op": "retime", "duration": s} / {"speed": k}     a new length (resampled by slerp; a loop stays a loop)
- {"op": "smooth", "fps": 60}                        LAG FIX: sparse linear keys -> curves through the same keyed poses
- {"op": "amplify", "joints": [..], "by": s}         motion range about the joint's mean pose (1.2 = 20% bigger)
- {"op": "posture", "joint": J, "rot": [x,y,z] deg, "pos": [x,y,z]}   a constant bias (a lean, a guard arm, a
                                                     slouch) in the joint's character frame
- {"op": "shift", "joints": [..], "frames": n}       the drag hierarchy (a loop wraps)
- {"op": "layer", "from": Clip, "joints": [..], "weight": w}   another clip's joints over this one (upper body over
                                                     running legs); retimed to fit
- {"op": "mirror"}                                    left <-> right
- {"op": "style", "from": StyleClip, "neutral": NeutralClip, "posture": w, "dynamics": w}
                                                     STYLE TRANSFER (static / temporal split, after STyMo): the
                                                     style's constant posture bias (its mean pose vs the neutral's)
                                                     and its dynamics (each joint's motion range vs the neutral's)
- {"op": "blend", "from": Clip, "weight": w}         a whole-body blend with another clip of the same kind
- {"op": "chain", "pose": Clip, "frame": 0, "in": n, "out": n}   MOVESET COHERENCE: ease the first `in` frames
                                                     FROM and the last `out` frames TO one shared guard pose (a frame of
                                                     a clip), so every move of a set starts and ends where the next one
                                                     begins - combos chain without pops (smoothstep, quaternion blend)
- {"op": "breathe", "period": s, "torso": deg, "arms": deg, "rise": studs}   a breathing layer (idle research:
                                                     15-30 breaths a minute; the chest lifts, the arms drift a little
                                                     later): an idle that never holds dead still
- {"op": "hold", "at": s, "frames": n}               a HOLD inserted at a moment (the pose after a hit sells it)
- {"op": "hitstop", "frames": n}                     a hold just after the STRIKE (the fastest frame, found): the
                                                     research's hitstop at 60 fps is 2-4 light, 4-6 medium, 6-10 heavy
- {"op": "still", "frame": i, "duration": s}         the clip becomes one of its poses held for `duration` (an idle
                                                     built on the set's guard, then `breathe`)
- {"op": "timing", "from": Clip, "duration": s?}    TIMING TRANSFER: this clip's own path, re-spaced so its motion
                                                     accumulates exactly as the loved clip's does (where it hangs,
                                                     this hangs; where it whips, this whips) - a blocked-out move gets
                                                     a finished move's snap; the poses never change, only WHEN
- {"op": "compose", "poses": [{"clip": C, "frame": i}, ...], "times": [s, ...]?, "timing": Clip?}
                                                     a NEW move from loved POSES: the clip becomes those poses in
                                                     order (smooth quaternion interpolation; even times unless given),
                                                     then, with "timing", re-spaced like a loved strike. The key poses
                                                     of any clip: `python kit/anim/derive.py --poses <Clip>` (speed
                                                     minima: where an animator puts a pose)
- {"op": "plant", "max_shift": 1.5}                   CLEAN-UP (kit/anim/cleanup.py): planted feet that skate are held
                                                     where they stood, by moving the body over them (the root track)
- {"op": "drive", "joint": J, "by": K, "weight": w, "delay": s, "axis": [x, y, z]?}
                                                     A DRIVER (kit/anim/drivers.py): J is given w times the turn K has
                                                     made since the first frame, read s seconds late; refuses a hand
                                                     taken off the weapon, a loop that would not close
- {"op": "overlap", "joints": ["Head", "Right Arm", ...], "halflife": s, "weight": w}
                                                     FOLLOW-THROUGH / OVERLAP: a critically damped spring (Holden)
                                                     follows the torso's turning; the listed joints inherit its LAG
                                                     (defaults 0.03 s, 0.3: an 11 deg head lag on a 166 deg torso whip, 2.6 on a sprint) - when the body whips round, the head and
                                                     arms arrive a beat later and settle, never all on the same frame
- {"op": "concat", "clips": [Clip, ...], "crossfade": n}  these clips played after this one, back to back (a combo
                                                     preview); crossfade n frames: the tail of one blends into the head
                                                     of the next (smoothstep) - two REAL strikes joined without a pop
- {"op": "tempo", "anticipation": k, "recovery": k, "window": s}   a piecewise TIME WARP around the strike: the
                                                     time before it x anticipation (a wind-up that reads: longer than
                                                     the action), the strike window (+-window s about the fastest frame)
                                                     untouched, the time after it x recovery - the craft's startup /
                                                     active / recovery proportions without touching a pose
- {"op": "unhold", "start": true, "end": false, "below": deg}   cut DEAD frames (the whole body moving less than
                                                     `below` deg per 60th) from the start / end - a held first pose,
                                                     stretched by tempo, reads as a freeze before the wind-up (judged)
- {"op": "declip", "joints": ["Left Arm", "Right Arm"], "shrink": 0.2}   an arm that passes THROUGH the torso or
                                                     head (kit/anim/clipping.py) is turned out of it about its shoulder
                                                     by the smallest angle that clears it, the correction smoothed over
                                                     time (no pop) - judges dock engine_fit for every frame of it
- {"op": "trim", "start": s, "end": s}               keep only that span (a strike without its long recovery)
- {"op": "extend", "frames": n}                      hold the last pose n more frames (room for a recovery `chain`)
  chain also takes "out_pose" / "out_frame" (and "frame" may be -1: the clip's last frame) so a finisher blends IN
  from the combo's end and OUT to the guard
The recipe: {"name": N, "from": BaseClip, "loop": bool?, "priority": P?, "ops": [...]}. Clips are found as
build/animations/<Clip>.clip.json (R6). `kit anim derive <Name>` runs this, then puts the result on the owner's rig
(kit/anim/pose_from.py --reduce): assets/animations/<Name>.pose.json, editable."""
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
import snaps as SN  # noqa: E402

LR = {"Right Arm": "Left Arm", "Left Arm": "Right Arm", "Right Leg": "Left Leg", "Left Leg": "Right Leg"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


# ---- quaternion helpers ([x, y, z, w]) ----
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def qinv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def qlog(q):
    q = q if q[3] >= 0 else -q
    v = q[:3]
    s = float(np.linalg.norm(v))
    if s < 1e-9:
        return np.zeros(3)
    return v / s * math.atan2(s, q[3])


def qexp(v):
    a = float(np.linalg.norm(v))
    if a < 1e-9:
        return np.array([0, 0, 0, 1.0])
    return np.concatenate([v / a * math.sin(a), [math.cos(a)]])


def qmean(Q):
    """the mean rotation (iterated in the log space about the running estimate)"""
    m = np.asarray(Q[0], float)
    for _ in range(8):
        d = np.mean([qlog(qmul(qinv(m), q)) for q in Q], axis=0)
        m = qmul(m, qexp(d))
        if np.linalg.norm(d) < 1e-7:
            break
    return m / np.linalg.norm(m)


def frames_of(clip, j):
    return np.asarray(clip["joints"][j]["frames"], dtype=float)


def set_frames(clip, j, F):
    out = []
    prev = None
    for f in F:
        q = np.asarray(f[:4], float)
        q = q / np.linalg.norm(q)
        if prev is not None and np.dot(q, prev) < 0:
            q = -q
        prev = q
        out.append([round(float(v), 6) for v in q] + [round(float(v), 5) for v in f[4:7]])
    clip["joints"][j]["frames"] = out
    clip["joints"][j].pop("keys", None)


def body_frames(clip):
    loop = bool(clip.get("loop"))
    n = len(clip["times"])
    return (n - 1 if loop and n > 2 else n), loop


def sample(F, u):
    """the track at fractional frame u (slerp / lerp)"""
    u = max(0.0, min(u, len(F) - 1.0))
    i = min(int(math.floor(u)), len(F) - 2)
    w = u - i
    return np.concatenate([C.slerp(F[i][:4], F[i + 1][:4], w), F[i][4:7] * (1 - w) + F[i + 1][4:7] * w])


def load_clip(name):
    path = name if name.endswith(".json") else os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{name}.clip.json")
    with open(path, encoding="utf-8") as fh:
        c = json.load(fh)
    if c.get("rig") not in (None, "R6"):
        raise ValueError(f"{name} is not an R6 clip")
    return c


# ---- operations ----
def op_retime(c, duration=None, speed=None, fps=None):
    fps = int(fps or c.get("fps") or 30)
    old = float(c["times"][-1])
    new = float(duration) if duration else old / float(speed)
    n = int(round(new * fps))
    times = [round(i / fps, 6) for i in range(n + 1)]
    for j in c["joints"]:
        F = frames_of(c, j)
        set_frames(c, j, [sample(F, (t / new) * (len(F) - 1)) for t in times])
    c["times"], c["fps"], c["duration"] = times, fps, times[-1]
    if c.get("locomotion"):
        c["locomotion"]["cycle"] = round(new, 4)
    return c


def op_smooth(c, fps=60):
    """LAG FIX (owner picks, 2026-10-12: 197 loved vs 40 'laggy' library clips - all linear easing; loved ones are keyed
    every frame (median key gap 0.017 s, worst 0.033 s), laggy ones every 3-6 frames (worst 0.1 s), so each limb runs
    straight then turns on the spot: speed jumps, jerk 0.88 vs 0.55). Every KEYED pose stays exactly where the animator
    put it; between keys the linear segments become a Catmull-Rom curve (quaternion components aligned to one
    hemisphere, positions alike), resampled at `fps`. A clip without key data is already dense: left alone."""
    old_fps = float(c.get("fps") or 30)
    duration = float(c["times"][-1])
    n = int(round(duration * fps))
    times = [round(i / fps, 6) for i in range(n + 1)]
    loop = bool(c.get("loop"))
    for j, jd in c["joints"].items():
        ks = sorted({round(float(k["t"]), 6) for k in (jd.get("keys") or [])} | {0.0, round(duration, 6)})
        F = frames_of(c, j)
        if len(ks) < 3:
            set_frames(c, j, [sample(F, t * old_fps) for t in times])
            continue
        V = np.array([sample(F, t * old_fps) for t in ks])
        for i in range(1, len(V)):                                 # one hemisphere, so components interpolate
            if np.dot(V[i, :4], V[i - 1, :4]) < 0:
                V[i, :4] = -V[i, :4]
        T = np.array(ks)
        m = np.zeros_like(V)                                       # Catmull-Rom tangents (non-uniform spacing)
        for i in range(len(V)):
            if 0 < i < len(V) - 1:
                m[i] = (V[i + 1] - V[i - 1]) / max(T[i + 1] - T[i - 1], 1e-6)
            elif loop and len(V) > 2:
                m[i] = (V[1] - V[-2]) / max((T[1] - T[0]) + (T[-1] - T[-2]), 1e-6)
            # a one-shot starts and ends at rest speed (m = 0): it eases out of its first pose and into its last
        out = []
        for t in times:
            i = min(max(int(np.searchsorted(T, t, side="right")) - 1, 0), len(T) - 2)
            h = max(T[i + 1] - T[i], 1e-6)
            u = (t - T[i]) / h
            h00, h10, h01, h11 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u, -2 * u**3 + 3 * u**2, u**3 - u**2
            v = h00 * V[i] + h10 * h * m[i] + h01 * V[i + 1] + h11 * h * m[i + 1]
            v[:4] = v[:4] / max(np.linalg.norm(v[:4]), 1e-9)
            out.append(v)
        set_frames(c, j, out)
    c["times"], c["fps"], c["duration"] = times, fps, times[-1]
    return c


def op_amplify(c, joints, by):
    n, loop = body_frames(c)
    for j in joints:
        if j not in c["joints"]:
            continue
        F = frames_of(c, j)
        m = qmean(F[:n, :4])
        mp = F[:n, 4:7].mean(axis=0)
        set_frames(c, j, [np.concatenate([qmul(m, qexp(qlog(qmul(qinv(m), f[:4])) * float(by))), mp + (f[4:7] - mp) * float(by)]) for f in F])
    return c


def op_posture(c, joint, rot=(0, 0, 0), pos=(0, 0, 0)):
    R = C.euler_mat(tuple(float(v) for v in rot)) if any(rot) else np.eye(3)
    dq = np.asarray(C.mat_quat(R), float)
    F = frames_of(c, joint)
    set_frames(c, joint, [np.concatenate([qmul(f[:4], dq), f[4:7] + np.asarray(pos, float)]) for f in F])
    return c


def op_shift(c, joints, frames):
    n, loop = body_frames(c)
    k = int(frames)
    for j in joints:
        if j not in c["joints"]:
            continue
        F = frames_of(c, j)
        if loop:
            body = np.roll(F[:n], k, axis=0)
            set_frames(c, j, list(body) + [body[0]])
        else:
            set_frames(c, j, [F[max(0, min(len(F) - 1, i - k))] for i in range(len(F))])
    return c


def fit_to(other, c):
    """another clip resampled to this clip's frames"""
    o = copy.deepcopy(other)
    if abs(float(o["times"][-1]) - float(c["times"][-1])) > 1e-6 or len(o["times"]) != len(c["times"]):
        op_retime(o, duration=float(c["times"][-1]), fps=c.get("fps"))
    return o


def op_layer(c, src, joints, weight=1.0):
    o = fit_to(load_clip(src), c)
    for j in joints:
        if j not in o["joints"]:
            continue
        A, B = frames_of(c, j) if j in c["joints"] else frames_of(o, j), frames_of(o, j)
        w = float(weight)
        set_frames(c, j, [np.concatenate([C.slerp(a[:4], b[:4], w), a[4:7] * (1 - w) + b[4:7] * w]) for a, b in zip(A, B)])
    return c


def op_mirror(c):
    M = np.diag([-1.0, 1.0, 1.0])
    old = {j: frames_of(c, j) for j in c["joints"]}
    for j in c["joints"]:
        F = old[LR.get(j, j)]
        out = []
        for f in F:
            R = M @ C.quat_mat(f[:4]) @ M
            out.append(np.concatenate([C.mat_quat(R), M @ f[4:7]]))
        set_frames(c, j, out)
    return c


def op_style(c, src, neutral, posture=1.0, dynamics=1.0):
    S, N = load_clip(src), load_clip(neutral)
    ns, _ = body_frames(S)
    nn, _ = body_frames(N)
    for j in c["joints"]:
        if j not in S["joints"] or j not in N["joints"]:
            continue
        FS, FN = frames_of(S, j)[:ns], frames_of(N, j)[:nn]
        ms, mn = qmean(FS[:, :4]), qmean(FN[:, :4])
        spread = lambda F, m: float(np.mean([np.linalg.norm(qlog(qmul(qinv(m), f[:4]))) for f in F]))
        ratio = spread(FS, ms) / max(spread(FN, mn), 1e-6)
        if dynamics:
            op_amplify(c, [j], 1.0 + (ratio - 1.0) * float(dynamics))
        bias = qexp(qlog(qmul(qinv(mn), ms)) * float(posture))
        dpos = (FS[:, 4:7].mean(axis=0) - FN[:, 4:7].mean(axis=0)) * float(posture)
        F = frames_of(c, j)
        set_frames(c, j, [np.concatenate([qmul(f[:4], bias), f[4:7] + dpos]) for f in F])
    return c


def smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def op_chain(c, pose, frame=0, n_in=6, n_out=10, out_pose=None, out_frame=None):
    P = load_clip(pose)
    Q = load_clip(out_pose) if out_pose else P
    fo = int(frame if out_frame is None else out_frame)
    for j in c["joints"]:
        if j not in P["joints"] or j not in Q["joints"]:
            continue
        gi = np.asarray(P["joints"][j]["frames"][int(frame)], float)
        go = np.asarray(Q["joints"][j]["frames"][fo], float)
        F = frames_of(c, j)
        n = len(F)
        out = []
        for i, f in enumerate(F):
            q, p = f[:4], f[4:7]
            if n_in and i < n_in:
                w = 1.0 - smooth(i / float(n_in))
                q, p = C.slerp(q, gi[:4], w), p * (1 - w) + gi[4:7] * w
            if n_out and i > n - 1 - n_out:
                w = smooth((i - (n - 1 - n_out)) / float(n_out))
                q, p = C.slerp(q, go[:4], w), p * (1 - w) + go[4:7] * w
            out.append(np.concatenate([q, p]))
        set_frames(c, j, out)
    return c


def motion_curve(c):
    """the clip's cumulative motion over its frames (all limbs + torso), 0..1"""
    fps = float(c.get("fps") or 30)
    tot = None
    for j in ("Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        if j in c["joints"]:
            sp = SN.speeds(c["joints"][j]["frames"], fps, False)
            tot = sp if tot is None else tot + sp
    cum = np.concatenate([[0.0], np.cumsum(tot)])
    return cum / max(float(cum[-1]), 1e-9)


def op_timing(c, src, duration=None):
    R = load_clip(src)
    fps = float(c.get("fps") or 30)
    cr = motion_curve(R)
    ct = motion_curve(c)
    # strictly increasing for inversion
    ct = ct + np.linspace(0, 1e-6, len(ct))
    dur = float(duration) if duration else float(R["times"][-1])
    n = int(round(dur * fps))
    times = [round(i / fps, 6) for i in range(n + 1)]
    xr = np.linspace(0, 1, len(cr))
    old = {j: frames_of(c, j) for j in c["joints"]}
    for j, F in old.items():
        out = []
        for t in times:
            target = float(np.interp(t / dur, xr, cr))                 # how far the loved clip has moved by now
            u = float(np.interp(target, ct, np.arange(len(ct))))     # the frame of THIS path that far along
            out.append(sample(F, u))
        set_frames(c, j, out)
    c["times"], c["duration"] = times, times[-1]
    return c


def key_poses(c, min_gap=4):
    """frames where the whole body's motion reaches a local minimum (an animator's key poses: Miura et al.), plus the
    first and last frame"""
    cur = motion_curve(c)
    sp = np.diff(cur)
    out = [0]
    for i in range(1, len(sp) - 1):
        if sp[i] <= sp[i - 1] and sp[i] <= sp[i + 1] and i - out[-1] >= min_gap:
            out.append(i)
    n = len(c["times"]) - 1
    if n - out[-1] < min_gap:
        out[-1] = n
    else:
        out.append(n)
    return out


SPEED_JOINTS = ("Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg")


def speed_limits(clips, margin=1.1):
    """per joint: the fastest the SOURCE clips ever move it (per 60th of a second) x margin - a composed move is never
    faster than the animations its poses came from"""
    lim = {}
    for cl in clips:
        fps = float(cl.get("fps") or 30)
        for j in SPEED_JOINTS:
            if j in cl["joints"]:
                lim[j] = max(lim.get(j, 0.0), float(SN.speeds(cl["joints"][j]["frames"], fps, False).max()) * margin)
    return lim


def segment_excess(c, times, lim):
    """per segment: the worst ratio of a joint's peak speed to its limit"""
    fps = float(c.get("fps") or 30)
    out = []
    for k in range(len(times) - 1):
        a, b = int(round(times[k] * fps)), int(round(times[k + 1] * fps))
        worst, who = 0.0, None
        for j in SPEED_JOINTS:
            if j in c["joints"] and j in lim and b > a:
                sp = SN.speeds(c["joints"][j]["frames"][a:b + 1], fps, False)
                r = float(sp.max()) / max(lim[j], 1e-6) if len(sp) else 0.0
                if r > worst:
                    worst, who = r, j
        out.append((worst, who))
    return out


def op_compose(c, poses, times=None, timing=None, respect_speed=True):
    """see the module doc; respect_speed lengthens any segment that would move a joint faster than the source clips
    ever do (a strike composed from two poses 108 deg apart squeezed into 3 frames whips the torso at 60 deg / frame)"""
    times = list(times) if times is not None else [0.15 * k for k in range(len(poses))]
    sources = [load_clip(p["clip"]) for p in poses]
    lim = speed_limits(sources)
    for _ in range(4):
        compose_once(c, poses, times)
        ex = segment_excess(c, times, lim)
        c["compose_speed"] = [{"segment": k, "ratio": round(r, 2), "joint": j} for k, (r, j) in enumerate(ex)]
        if not respect_speed or all(r <= 1.0 for r, _ in ex):
            break
        new = [times[0]]
        for k, (r, _j) in enumerate(ex):
            new.append(new[-1] + (times[k + 1] - times[k]) * max(1.0, r))
        times = new
    c["compose_times"] = [round(t, 4) for t in times]
    # FACING: borrowed poses whose torsos face far apart make the body spin between them (judged 33/100 on
    # 2026-10-11: "the whole body spins ~180 deg in 2-3 frames") - prefer the curves that already join them
    warn = []
    for k in range(len(poses) - 1):
        a = load_clip(poses[k]["clip"])["joints"]["Torso"]["frames"][int(poses[k].get("frame", 0))]
        b = load_clip(poses[k + 1]["clip"])["joints"]["Torso"]["frames"][int(poses[k + 1].get("frame", 0))]
        d = SN.qang(np.asarray(a[:4], float), np.asarray(b[:4], float))
        if d > 75:
            warn.append(f"poses {k}->{k + 1}: the torso turns {d:.0f} deg between borrowed poses (a facing flip; join real curves with concat + crossfade instead)")
    c["compose_warn"] = warn
    if timing:
        op_timing(c, timing, float(times[-1]))
    return c


def compose_once(c, poses, times):
    fps = float(c.get("fps") or 30)
    P = [(load_clip(p["clip"]), int(p.get("frame", 0))) for p in poses]
    dur = float(times[-1])
    n = int(round(dur * fps))
    ts = [round(i / fps, 6) for i in range(n + 1)]
    for j in c["joints"]:
        keys = [np.asarray(cl["joints"][j]["frames"][f], float) if j in cl["joints"] else None for cl, f in P]
        if any(k is None for k in keys):
            continue
        out = []
        for t in ts:
            k = max(0, min(len(times) - 2, int(np.searchsorted(times, t, side="right")) - 1))
            u = (t - times[k]) / max(times[k + 1] - times[k], 1e-9)
            w = smooth(u)
            a, b = keys[k], keys[k + 1]
            out.append(np.concatenate([C.slerp(a[:4], b[:4], w), a[4:7] * (1 - w) + b[4:7] * w]))
        set_frames(c, j, out)
    c["times"], c["duration"], c["loop"] = ts, ts[-1], False
    return c


def spring_track(V, fps, halflife, loop):
    """a critically damped spring following each component of V (n x 3) - two passes over a loop for steady state"""
    y = 2 * math.log(2) / max(float(halflife), 1e-4)
    dt = 1.0 / fps
    x, v = V[0].copy(), np.zeros(3)
    passes = 2 if loop else 1
    out = np.zeros_like(V)
    for p in range(passes):
        for i in range(len(V)):
            j0 = x - V[i]
            j1 = v + j0 * y
            e = math.exp(-y * dt)
            x = e * (j0 + j1 * dt) + V[i]
            v = e * (v - j1 * y * dt)
            if p == passes - 1:
                out[i] = x
    return out


# R6 ARM SLIDES learned from the owner's 74 LOVED attacks (8312 arm frames, 2026-10-12): the joint's translation by how far
# the arm is raised from hanging (deg) -> (out, up, back) in the torso's frame (x mirrored for the left arm). R6 animators
# drop the shoulder as the arm comes up (a fake shoulder) and slide a raised arm FORWARD (the reach); every one of the
# owner-rejected authored moves slid its arms 0.3-0.6 studs at most vs the loved 0.6-1.7
R6_SLIDE = [(15, (0.0, -0.10, 0.02)), (45, (0.05, -0.19, 0.09)), (75, (0.11, -0.29, 0.10)), (105, (0.12, -0.27, -0.25)),
            (150, (-0.02, -0.05, -0.39))]


# per MOVE TYPE (learned the same way from the loved runs / walks / idles - each slides its arms differently: the attack
# table made the greatsword run WORSE, 5 -> 10 critic misses)
R6_SLIDES = {
    "attack": R6_SLIDE,
    "run": [(15, (0.0, -0.13, 0.13)), (45, (0.02, -0.16, 0.18)), (75, (0.03, -0.32, -0.14)), (105, (0.02, -0.49, -0.33)),
            (150, (0.02, -0.42, -0.34))],
    "walk": [(15, (0.0, -0.07, 0.04)), (45, (0.10, -0.18, 0.06)), (75, (0.27, 0.14, 0.04)), (105, (0.41, -0.09, -0.04))],
    "idle": [(15, (0.07, -0.10, 0.02)), (45, (0.37, 0.01, -0.05)), (75, (0.45, 0.46, 0.01)), (105, (0.22, -0.62, -0.06)),
             (150, (-0.11, -0.54, -0.70))],
}


def r6_slide_at(angle, kind="attack"):
    table = R6_SLIDES.get(kind, R6_SLIDE)
    xs = [a for a, _ in table]
    if angle <= xs[0]:
        return np.array(table[0][1])
    for (a0, v0), (a1, v1) in zip(table, table[1:]):
        if angle <= a1:
            u = (angle - a0) / (a1 - a0)
            return np.array(v0) * (1 - u) + np.array(v1) * u
    return np.array(table[-1][1])


def op_r6slide(c, weight=1.0, joints=("Right Arm", "Left Arm"), two_handed=False, kind="attack"):
    """every arm frame gets the slide loved R6 animators use at that arm height (added to what the clip has). TWO-HANDED
    (both fists on one hilt): the left arm takes the RIGHT arm's slide unchanged (the kit's clip joint positions are in
    the torso's frame - measured: a joint-frame flip pulled the hands 2.9 studs apart) so the hands move as one"""
    if two_handed and "Right Arm" in c["joints"] and "Left Arm" in c["joints"]:
        R, L = frames_of(c, "Right Arm"), frames_of(c, "Left Arm")
        outR, outL = [], []
        for fr, fl in zip(R, L):
            down = C.quat_mat(fr[:4]) @ np.array([0.0, -1.0, 0.0])
            ang = math.degrees(math.acos(max(-1.0, min(1.0, -float(down[1])))))
            sv = r6_slide_at(ang, kind) * weight
            outR.append(np.concatenate([fr[:4], fr[4:7] + sv]))
            outL.append(np.concatenate([fl[:4], fl[4:7] + sv]))       # the clip's joint positions are torso-frame: same slide
        set_frames(c, "Right Arm", outR)
        set_frames(c, "Left Arm", outL)
        return c
    for j in joints:
        if j not in c["joints"]:
            continue
        sx = 1.0 if j.startswith("Right") else -1.0
        out = []
        for f in frames_of(c, j):
            down = C.quat_mat(f[:4]) @ np.array([0.0, -1.0, 0.0])
            ang = math.degrees(math.acos(max(-1.0, min(1.0, -float(down[1])))))
            s = r6_slide_at(ang, kind) * weight
            out.append(np.concatenate([f[:4], f[4:7] + np.array([s[0] * sx, s[1], s[2]])]))
        set_frames(c, j, out)
    return c


def op_alive(c, amp_deg=1.2, joints=("Torso", "Head", "Right Arm", "Left Arm"), seed=3):
    """NEVER DEAD STILL (loved attacks: 0% of frames with the whole body frozen; the rejected authored moves 2-9%): a
    slow smooth drift (two sines per axis, 0.6-1.4 Hz, random phases) faded in where the body is slow, so holds breathe
    and strikes are untouched; a loop's drift wraps on whole cycles"""
    rng = np.random.default_rng(seed)
    fps = float(c.get("fps") or 30)
    n = len(c["times"])
    dur = max(float(c["times"][-1]), 1e-3)
    sp = np.zeros(n)
    for j in c["joints"]:
        F = frames_of(c, j)[:, :4]
        d = np.abs(np.sum(F[1:] * F[:-1], axis=1)).clip(0, 1)
        sp[1:] += np.degrees(2 * np.arccos(d)) * fps
    calm = np.clip(1.0 - sp / max(np.percentile(sp, 70), 1e-6), 0.0, 1.0)
    calm = np.convolve(calm, np.ones(9) / 9, mode="same")
    t = np.array(c["times"], float)
    for j in joints:
        if j not in c["joints"]:
            continue
        F = frames_of(c, j)
        drift = np.zeros((n, 3))
        for ax in range(3):
            for _ in range(2):
                hz = rng.uniform(0.6, 1.4)
                if c.get("loop"):
                    hz = max(1, round(hz * dur)) / dur
                drift[:, ax] += np.sin(2 * math.pi * hz * t + rng.uniform(0, 2 * math.pi)) * 0.5
        scale = (0.5 if j == "Torso" else 1.0) * math.radians(amp_deg)
        out = []
        for i, f in enumerate(F):
            v = drift[i] * scale * calm[i]
            ang = float(np.linalg.norm(v))
            dq = np.array([0.0, 0.0, 0.0, 1.0]) if ang < 1e-9 else np.concatenate([v / ang * math.sin(ang / 2), [math.cos(ang / 2)]])
            out.append(np.concatenate([qmul(f[:4], dq), f[4:7]]))
        set_frames(c, j, out)
    return c


def polish(c, slide=2.5, overlap=0.0, alive=0.0, two_handed=None, kind="attack"):
    """the learned R6 POLISH pass on an authored move (2026-10-12; the three features every rejected authored move missed):
    learned arm slides (x2.5 lands the loved 0.6-1.7 studs), overlap (the head trails the torso; one-handed: the arms
    too), never dead still. TWO-HANDED (a sword clip): both arms take the same slide and no per-arm lag or drift, so the
    fists stay on the hilt (measured: per-arm lag / drift pulled them 1.3-2.9 studs apart)"""
    # measured on the greatsword set with the taste model: the slides alone lift P(loved) 0.65 -> 0.80 / 0.73 -> 0.81;
    # the head overlap and the drift LOWERED it (so both default off; kept as options)
    two = bool(c.get("sword")) if two_handed is None else two_handed
    if overlap:
        op_overlap(c, ("Head",) if two else ("Head", "Right Arm", "Left Arm"), 0.06, overlap)
    op_r6slide(c, slide, two_handed=two, kind=kind)
    if alive:
        op_alive(c, alive, joints=("Torso", "Head") if two else ("Torso", "Head", "Right Arm", "Left Arm"))
    return c


def op_overlap(c, joints=("Head", "Right Arm", "Left Arm"), halflife=0.03, weight=0.3):
    if "Torso" not in c["joints"]:
        return c
    fps = float(c.get("fps") or 30)
    T = frames_of(c, "Torso")[:, :4]
    m = qmean(T)
    L = np.array([qlog(qmul(qinv(m), q)) for q in T])        # the torso's turning, in the log space about its mean
    S = spring_track(L, fps, halflife, bool(c.get("loop")))
    for j in joints:
        if j not in c["joints"] or j == "Torso":
            continue
        F = frames_of(c, j)
        out = []
        for i, f in enumerate(F):
            lag = qmul(qmul(m, qexp(S[i])), qinv(qmul(m, qexp(L[i]))))    # spring pose x true pose^-1 (character space)
            lag = qexp(qlog(lag) * float(weight))
            out.append(np.concatenate([qmul(lag, f[:4]), f[4:7]]))
        set_frames(c, j, out)
    return c


def op_tempo(c, anticipation=1.0, recovery=1.0, window=0.017):
    fps = float(c.get("fps") or 30)
    n = len(c["times"])
    k = strike_index(c)
    w = int(round(float(window) * fps))
    a, b = max(0, k - w), min(n - 1, k + 1 + w)
    # new time of each old frame: piecewise linear
    knots_old = [0, a, b, n - 1]
    knots_new = [0.0, a * float(anticipation)]
    knots_new.append(knots_new[1] + (b - a))
    knots_new.append(knots_new[2] + (n - 1 - b) * float(recovery))
    total = knots_new[-1]
    m = int(round(total))
    old = {j: frames_of(c, j) for j in c["joints"]}
    for j, F in old.items():
        set_frames(c, j, [sample(F, float(np.interp(i, knots_new, knots_old))) for i in range(m + 1)])
    c["times"] = [round(i / fps, 6) for i in range(m + 1)]
    c["duration"] = c["times"][-1]
    return c


def op_unhold(c, start=True, end=False, below=1.0):
    fps = float(c.get("fps") or 30)
    tot = None
    for j in SPEED_JOINTS:
        if j in c["joints"]:
            sp = SN.speeds(c["joints"][j]["frames"], fps, False)
            tot = sp if tot is None else tot + sp
    n = len(c["times"])
    a, b = 0, n - 1
    if start:
        while a < n - 2 and tot[a] < float(below):
            a += 1
    if end:
        while b > a + 1 and tot[b - 1] < float(below):
            b -= 1
    return op_trim(c, a / fps, b / fps)


def op_declip(c, joints=("Left Arm", "Right Arm"), shrink=0.2, max_deg=60, step=3):
    import clipping as CL
    rig = C.load_rig("r6")
    n = len(c["times"])
    for j in joints:
        if j not in c["joints"]:
            continue
        others = [o for o in ("Torso", "Head") if o in c["joints"]]
        F = frames_of(c, j)

        def clear(frames_j, i):
            cc = {"name": c.get("name"), "rig": "R6", "joints": {k: {"frames": [c["joints"][k]["frames"][i]]} for k in c["joints"]}, "times": [0.0]}
            cc["joints"][j] = {"frames": [list(frames_j)]}
            w = C.world_frames(cc, rig)[0]
            return not any(CL.overlap(CL.obb(rig, j, w[j], shrink), CL.obb(rig, o, w[o], shrink)) for o in others)

        need = np.zeros(n)
        slide_of = np.zeros(n)
        axis_of = [None] * n
        for i in range(n):
            if clear(F[i], i):
                continue
            best = None
            side = 1.0 if j.startswith("Right") else -1.0
            # cheapest first: a turn about the shoulder, then a turn plus an OUTWARD slide (R6 arms slide), cost =
            # degrees + 60 x studs
            cands = []
            for ang in range(0, max_deg + 1, step):
                for sl in (0.0, 0.15, 0.3, 0.45, 0.6):
                    if ang == 0 and sl == 0.0:
                        continue
                    for ax in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0)):
                        cands.append((ang + 60 * sl, ang, sl, ax))
            for _cost, ang, sl, ax in sorted(cands, key=lambda t: t[0]):
                dq = qexp(np.asarray(ax, float) * math.radians(ang) / 2)
                cand = np.concatenate([qmul(dq, F[i][:4]), F[i][4:7] + np.array([side * sl, 0, 0])])
                if clear(cand, i):
                    best = (ang, ax, sl)
                    break
            if best:
                need[i], axis_of[i] = best[0], best[1]
                slide_of[i] = best[2]
        if not need.any() and not slide_of.any():
            continue
        side = 1.0 if j.startswith("Right") else -1.0
        dsl = np.array([slide_of[max(0, i - 3):i + 4].max() for i in range(n)])
        ssl = np.maximum(np.convolve(np.pad(dsl, 3, mode="edge"), np.ones(7) / 7, mode="valid"), slide_of)
        # one axis per contiguous span (its worst frame's), the angle dilated +-3 frames then averaged: no pops
        dil = np.array([need[max(0, i - 3):i + 4].max() for i in range(n)])
        sm = np.convolve(np.pad(dil, 3, mode="edge"), np.ones(7) / 7, mode="valid")
        sm = np.maximum(sm, need)
        out = []
        cur_ax = None
        for i in range(n):
            span_ax = next((axis_of[k] for k in range(max(0, i - 3), min(n, i + 4)) if axis_of[k] is not None), None)
            cur_ax = span_ax or cur_ax
            q = F[i][:4]
            if sm[i] > 0 and cur_ax is not None:
                q = qmul(qexp(np.asarray(cur_ax, float) * math.radians(float(sm[i])) / 2), q)
            out.append(np.concatenate([q, F[i][4:7] + np.array([side * float(ssl[i]), 0, 0])]))
        set_frames(c, j, out)
    return c


def op_trim(c, start=0.0, end=None):
    fps = float(c.get("fps") or 30)
    a = int(round(float(start) * fps))
    b = len(c["times"]) - 1 if end is None else int(round(float(end) * fps))
    n = len(c["times"])
    for j in c["joints"]:
        set_frames(c, j, list(frames_of(c, j)[a:b + 1]))
    # the per-frame tracks that ride with the joints (a sword's tip / grip / edge, the root's travel) are cut the same
    # way, and the events move with the cut (a trimmed sword clip drew its blade from the untrimmed frames, 2026-10-24)
    sw = c.get("sword")
    if isinstance(sw, dict):
        for k in ("tip", "grip_path", "edge"):
            if isinstance(sw.get(k), list) and len(sw[k]) == n:
                sw[k] = sw[k][a:b + 1]
    if isinstance(c.get("root"), list) and len(c["root"]) == n:
        c["root"] = c["root"][a:b + 1]
    if isinstance(c.get("events"), list):
        c["events"] = [({**e, "t": round(float(e["t"]) - a / fps, 6)} if isinstance(e, dict) and "t" in e else e)
                       for e in c["events"]
                       if not (isinstance(e, dict) and "t" in e)
                       or a / fps - 1e-9 <= float(e["t"]) <= b / fps + 1e-9]
    c["times"] = [round(i / fps, 6) for i in range(b - a + 1)]
    c["duration"] = c["times"][-1]
    c["loop"] = False
    return c


def op_concat(c, other, crossfade=0):
    o = load_clip(other) if isinstance(other, str) else other
    fps = float(c.get("fps") or 30)
    if float(o.get("fps") or 30) != fps:
        o = copy.deepcopy(o)
        op_retime(o, duration=float(o["times"][-1]), fps=fps)
    k = int(crossfade)
    for j in c["joints"]:
        A = list(frames_of(c, j))
        B = list(frames_of(o, j)) if j in o["joints"] else [A[-1]] * len(o["times"])
        if k > 0 and len(A) > k and len(B) > k:
            mid = []
            for i in range(k):
                w = smooth((i + 1) / float(k + 1))
                a, b = A[len(A) - k + i], B[i]
                mid.append(np.concatenate([C.slerp(a[:4], b[:4], w), a[4:7] * (1 - w) + b[4:7] * w]))
            set_frames(c, j, A[: len(A) - k] + mid + B[k:])
        else:
            set_frames(c, j, A + B[1:])
    n = len(next(iter(c["joints"].values()))["frames"])
    c["times"] = [round(i / fps, 6) for i in range(n)]
    c["duration"] = c["times"][-1]
    c["loop"] = False
    return c


def op_still(c, frame=0, duration=2.0):
    fps = float(c.get("fps") or 30)
    n = int(round(float(duration) * fps))
    for j in c["joints"]:
        f = frames_of(c, j)[int(frame)]
        set_frames(c, j, [f] * (n + 1))
    c["times"] = [round(i / fps, 6) for i in range(n + 1)]
    c["duration"] = c["times"][-1]
    c["events"] = []
    return c


def impact_index(c):
    """the IMPACT: the first frame after the strike where the whole body's motion has dropped below a third of the
    strike's - freezing there is a hitstop; freezing at the strike's peak speed makes every moving joint pop"""
    fps = float(c.get("fps") or 30)
    tot = None
    for j in ("Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        if j in c["joints"]:
            sp = SN.speeds(c["joints"][j]["frames"], fps, False)
            tot = sp if tot is None else tot + sp
    k = strike_index(c)
    peak = float(tot[min(k, len(tot) - 1)])
    for i in range(k + 1, len(tot)):
        if tot[i] < peak / 3.0:
            return i
    return min(k + 2, len(tot))


def strike_index(c):
    fps = float(c.get("fps") or 30)
    best, at = -1.0, 0
    for j in ("Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        if j in c["joints"]:
            s = SN.speeds(c["joints"][j]["frames"], fps, bool(c.get("loop")))
            if s.max() > best:
                best, at = float(s.max()), int(np.argmax(s))
    return at


def op_breathe(c, period=3.0, torso=1.6, arms=2.5, rise=0.03):
    fps = float(c.get("fps") or 30)
    T = float(c["times"][-1])
    cycles = max(1, round(T / float(period)))           # a whole number of breaths: a loop stays a loop
    for j, deg, lag in (("Torso", torso, 0.0), ("Head", -torso * 0.6, 0.08), ("Right Arm", arms, 0.15), ("Left Arm", -arms, 0.15)):
        if j not in c["joints"]:
            continue
        F = frames_of(c, j)
        out = []
        for i, f in enumerate(F):
            ph = 2 * math.pi * cycles * ((i / fps) / T - lag / float(period))
            a = math.sin(ph)
            axis = (1, 0, 0) if j in ("Torso", "Head") else (0, 0, 1)
            dq = C.mat_quat(C.euler_mat(tuple(float(deg) * a * k for k in axis)))
            pos = f[4:7] + (np.array([0, float(rise) * a, 0]) if j == "Torso" else 0)
            out.append(np.concatenate([qmul(f[:4], np.asarray(dq, float)), pos]))
        set_frames(c, j, out)
    return c


def op_hold(c, at, frames):
    fps = float(c.get("fps") or 30)
    i = int(round(float(at) * fps))
    k = int(frames)
    for j in c["joints"]:
        F = list(frames_of(c, j))
        i0 = max(0, min(i, len(F) - 1))
        set_frames(c, j, F[: i0 + 1] + [F[i0]] * k + F[i0 + 1:])
    n = len(next(iter(c["joints"].values()))["frames"])
    c["times"] = [round(t / fps, 6) for t in range(n)]
    c["duration"] = c["times"][-1]
    for e in c.get("events") or []:
        if float(e.get("t", 0)) > float(at):
            e["t"] = round(float(e["t"]) + k / fps, 6)
    return c


def derive(recipe):
    c = copy.deepcopy(load_clip(recipe["from"]))
    c["name"] = recipe["name"]
    for k in ("loop", "priority"):
        if k in recipe:
            c[k] = recipe[k]
    log = []
    # the SLIDES a source says are seconds of ITS clip (kit/anim/foot_modes.py): a recipe that changes the clip's time
    # would leave them on the wrong frames - they are dropped, said, and the recipe says its own ("slides": [...])
    TIMED = {"retime", "trim", "hold", "hitstop", "tempo", "unhold", "timing", "concat", "extend", "still", "compose",
             "handles", "smooth"}
    if c.get("slides") is not None and any(o.get("op") in TIMED for o in recipe.get("ops", [])):
        c.pop("slides")
        log.append("slides: the source's said slides are dropped (the recipe changes the clip's time) - say them in the recipe")
    if "slides" in recipe:
        c["slides"] = recipe["slides"]
    for o in recipe.get("ops", []):
        kind = o["op"]
        if kind == "despike":
            c, fixed = SN.fix(c)
            log.append(f"despike {fixed}")
        elif kind == "smooth":
            op_smooth(c, o.get("fps", 60))
            log.append(f"smooth: linear key segments -> curves at {c['fps']} fps")
        elif kind == "filter":                               # (kit/anim/curves.py: a signal filter, the kept moments exact)
            import curves as CV
            log.append(CV.op_filter(c, o.get("hz", 8.0), o.get("joints"), o.get("keep", ()), o.get("ease", CV.EASE_S),
                                    bool(o.get("soften"))))
        elif kind == "handles":                              # (kit/anim/curves.py: tangent handles on one stretch's timing)
            import curves as CV
            log.append(CV.op_handles(c, o["from"], o["to"], o.get("out", (1 / 3, 1 / 3)), o.get("in", (2 / 3, 2 / 3))))
        elif kind == "clear":                                # (kit/anim/collide_repair.py: what passes through the body, moved out)
            import collide_repair as CR
            log.append(CR.op_clear(c, o.get("max_deg", CR.MAX_DEG), o.get("max_slide", CR.MAX_SLIDE), o.get("blade_deg", CR.BLADE_DEG),
                                    o.get("tilt_deg", CR.TILT_DEG)))
        elif kind == "grip":                                 # (kit/anim/grip_solve.py: the said hands put onto the weapon)
            import grip_solve as GS
            log.append(GS.op_grip(c, o.get("hands"), o.get("at"), o.get("max_slide", GS.MAX_SLIDE)))
        elif kind == "plant":                                # (kit/anim/cleanup.py: feet that skate held where they stood)
            import cleanup as CL
            log.append(CL.op_plant(c, o.get("max_shift", 1.5), o.get("travel", False)))
        elif kind == "gaps":                                 # (kit/anim/cleanup.py: frames the capture did not see, re-made and said)
            import cleanup as CL
            log.append(CL.op_gaps(c, o.get("min", CL.MIN_CONF), o.get("max_gap", CL.MAX_GAP_S), o.get("dropped", False)))
        elif kind == "drive":                                # (kit/anim/drivers.py: one joint's turning follows another's)
            import drivers as DR
            log.append(DR.op_drive(c, o["joint"], o["by"], o.get("weight", 0.5), o.get("delay", 0.0), o.get("axis")))
        elif kind == "retime":
            op_retime(c, o.get("duration"), o.get("speed"), o.get("fps"))
            log.append(f"retime -> {c['times'][-1]:.3f} s")
        elif kind == "amplify":
            op_amplify(c, o["joints"], o["by"])
            log.append(f"amplify {o['joints']} x{o['by']}")
        elif kind == "posture":
            op_posture(c, o["joint"], o.get("rot", (0, 0, 0)), o.get("pos", (0, 0, 0)))
            log.append(f"posture {o['joint']}")
        elif kind == "shift":
            op_shift(c, o["joints"], o["frames"])
            log.append(f"shift {o['joints']} {o['frames']}f")
        elif kind == "layer":
            op_layer(c, o["from"], o["joints"], o.get("weight", 1.0))
            log.append(f"layer {o['from']} {o['joints']}")
        elif kind == "mirror":
            op_mirror(c)
            log.append("mirror")
        elif kind == "style":
            op_style(c, o["from"], o["neutral"], o.get("posture", 1.0), o.get("dynamics", 1.0))
            log.append(f"style of {o['from']} (vs {o['neutral']})")
        elif kind == "blend":
            op_layer(c, o["from"], list(c["joints"]), o.get("weight", 0.5))
            log.append(f"blend {o['from']} {o.get('weight', 0.5)}")
        elif kind == "overlap":
            op_overlap(c, o.get("joints", ("Head", "Right Arm", "Left Arm")), o.get("halflife", 0.03), o.get("weight", 0.3))
            log.append(f"overlap {o.get('joints', 'head + arms')} halflife {o.get('halflife', 0.03)}")
        elif kind == "tempo":
            op_tempo(c, o.get("anticipation", 1.0), o.get("recovery", 1.0), o.get("window", 0.017))
            log.append(f"tempo anticipation x{o.get('anticipation', 1.0)} recovery x{o.get('recovery', 1.0)}")
        elif kind == "unhold":
            n0 = len(c["times"])
            op_unhold(c, o.get("start", True), o.get("end", False), o.get("below", 1.0))
            log.append(f"unhold: {n0 - len(c['times'])} dead frame(s) cut")
        elif kind == "declip":
            op_declip(c, o.get("joints", ("Left Arm", "Right Arm")), o.get("shrink", 0.2), o.get("max_deg", 60))
            log.append("declip " + ", ".join(o.get("joints", ("Left Arm", "Right Arm"))))
        elif kind == "trim":
            op_trim(c, o.get("start", 0.0), o.get("end"))
            log.append(f"trim {o.get('start', 0.0)}..{o.get('end')} s")
        elif kind == "compose":
            op_compose(c, o["poses"], o.get("times"), o.get("timing"), o.get("respect_speed", True))
            log.append(f"compose {len(o['poses'])} poses at {c.get('compose_times')}" + (f" with the timing of {o['timing']}" if o.get("timing") else ""))
        elif kind == "timing":
            op_timing(c, o["from"], o.get("duration"))
            log.append(f"timing of {o['from']}")
        elif kind == "concat":
            for other in o["clips"]:
                op_concat(c, other, o.get("crossfade", 0))
            log.append(f"concat {o['clips']}")
        elif kind == "still":
            op_still(c, o.get("frame", 0), o.get("duration", 2.0))
            log.append(f"still frame {o.get('frame', 0)} for {o.get('duration', 2.0)} s")
        elif kind == "extend":
            fps = float(c.get("fps") or 30)
            op_hold(c, float(c["times"][-1]) + 1.0 / fps, o["frames"])
            log.append(f"extend {o['frames']}f")
        elif kind == "hitstop":
            fps = float(c.get("fps") or 30)
            at = impact_index(c) / fps
            op_hold(c, at, o["frames"])
            log.append(f"hitstop {o['frames']}f at {at:.3f} s")
        elif kind == "chain":
            op_chain(c, o["pose"], o.get("frame", 0), o.get("in", 6), o.get("out", 10), o.get("out_pose"), o.get("out_frame"))
            log.append(f"chain to {o['pose']}[{o.get('frame', 0)}] in {o.get('in', 6)} / out {o.get('out', 10)}")
        elif kind == "breathe":
            op_breathe(c, o.get("period", 3.0), o.get("torso", 1.6), o.get("arms", 2.5), o.get("rise", 0.03))
            log.append(f"breathe {o.get('period', 3.0)} s")
        elif kind == "hold":
            op_hold(c, o["at"], o["frames"])
            log.append(f"hold {o['frames']}f at {o['at']} s")
        else:
            raise ValueError(f"unknown op {kind!r}")
    c["derived"] = {"from": recipe["from"], "ops": log, "tool": "kit/anim/derive.py"}
    c.pop("source", None)
    return c, log


def main(argv):
    if argv and argv[0] == "--poses":
        c = load_clip(argv[1])
        k = key_poses(c)
        return emit("pass", f"key poses of {argv[1]}: frames {k} (of {len(c['times'])}; speed minima)",
                    'compose a move from them: {"op": "compose", "poses": [{"clip": "' + argv[1] + '", "frame": ' + str(k[1] if len(k) > 1 else 0) + '}, ...], "timing": "<a loved strike>"}', frames=k)
    if not argv or "--out" not in argv:
        return emit("fail", "derive: needs <Name>.derive.json --out <clip.json>", "lune run kit anim derive <Name>")
    with open(argv[0], encoding="utf-8") as fh:
        recipe = json.load(fh)
    try:
        c, log = derive(recipe)
    except (ValueError, KeyError, FileNotFoundError) as e:
        return emit("fail", f"derive {recipe.get('name')}: {e}", "fix the recipe (ops: despike retime amplify posture shift layer mirror style blend chain breathe hold)")
    out = argv[argv.index("--out") + 1]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(c, fh, indent=1)
    left = SN.find(c)
    return emit("pass", f"derive {c['name']}: from {recipe['from']} - " + "; ".join(log) + f" -> {out}"
                + (f" (snaps left: {sum(len(v) for v in left.values())})" if left else ""),
                f"python kit/anim/pose_from.py {out} --as {c['name']} --reduce 2", ops=log)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
