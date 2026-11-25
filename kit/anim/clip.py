"""clip.py — the neutral clip (build/animations/<Name>.clip.json, written by `kit anim`) and the engine-read rigs
(kit/anim/rigs/<rig>.json) in Python: forward kinematics exactly as the engine does it (part = parent * C0 * T * C1^-1),
MOTION METRICS over time (how fast every joint and hand moves and when, where a Hit lands against the fastest frame,
whether planted feet slide, one-frame snaps, loop seams, the beats of an attack) and the GATES on them.
strip.py draws with it, metrics.py gates with it, the tests in kit/test/python check it. Pure numpy.

Clip joints are in CHARACTER SPACE (R15 names; a custom rig keeps its own): frame = [qx, qy, qz, qw, px, py, pz].
"""

import hashlib
import json
import math
import os
import re

import numpy as np

RIG_DIR = os.path.join("kit", "anim", "rigs")

EFFECTORS = {"R15": ["RightHand", "LeftHand", "RightFoot", "LeftFoot", "Head"],
             "R6": ["Right Arm", "Left Arm", "Right Leg", "Left Leg", "Head"]}
FEET = {"R15": ["RightFoot", "LeftFoot"], "R6": ["Right Leg", "Left Leg"]}


def effectors_of(rig):
    """the parts whose paths matter: the humanoid lists, else every leaf part of the rig"""
    if rig["rig"] in EFFECTORS:
        return [e for e in EFFECTORS[rig["rig"]] if e in rig["joints"]]
    parents = {j["parent"] for j in rig["joints"].values()}
    return [p for p in rig["order"] if p not in parents]


def feet_of(rig):
    """the parts that stand on the ground: the humanoid lists, else the leaves whose rest bottom is the lowest"""
    if rig["rig"] in FEET:
        return [f for f in FEET[rig["rig"]] if f in rig["joints"]]
    leaves = effectors_of(rig)
    if not leaves:
        return []
    bottoms = {p: rig["rest"][p][1] - rig["sizes"][p][1] / 2 for p in leaves if p in rig["rest"] and p in rig["sizes"]}
    if not bottoms:
        return []
    lowest_y = min(bottoms.values())
    return [p for p, y in bottoms.items() if y < lowest_y + 0.3]


def rest_ground(rig, feet):
    """where the feet's soles stand in the rest pose: the floor every clip is measured against"""
    ys = [rig["rest"][f][1] - rig["sizes"][f][1] / 2 for f in feet if f in rig["rest"] and f in rig["sizes"]]
    return min(ys) if ys else None
HIT_NAMES = ("hit", "impact", "strike", "slam", "punch", "kick")

# the bars (a spec may override any of them under "gate": {...})
GATES = {
    "foot_slide": 0.1,     # studs a planted foot may move in one frame
    "foot_skate": 0.15,    # locomotion: studs/frame a planted foot may deviate from the clip's ground speed
    "pop_deg": 15.0,       # a one-frame step this big, with both neighbours 3x smaller, is a snap
    "loop_seam_deg": 2.0,  # a looping clip's last frame vs its first
    "hit_before": 1,       # a Hit may land this many frames before the fastest motion ...
    "hit_after": 3,        # ... or this many after it
    "penetration": 0.08,   # studs a part may dip below the floor (a blocky shin's corner does this at 30 degrees)
    "switch_arm_deg_s": 1200.0,  # a switch / swap / to-hand clip: fastest arm joint must reach this peak deg/s —
                                 # calibrated against rejected GunSwitch/GunSideSwitch (973 deg/s peak, owner:
                                 # "transitions are in slow motion ... arms aren't doing anything to actually
                                 # transition", 2026-10-26) and passing draws (GunDrawHips 1451, GunDrawDual 2438)
}

# clips that existed before this gate was added (2026-11-10) and already fail it: they warn, not block,
# so the board is not bricked — a full rebuild re-certifies them (owner approval re-opens the clock).
# Grandfathering is by CONTENT HASH (sha1 of json.dumps(clip_data, sort_keys=True)) so only the exact
# committed clip gets a warning; a rebuilt clip with different content must pass the floor or fail.
# Hashes captured 2026-11-10 from build/animations/{GunSwitch,GunSideSwitch}.clip.json; re-pinned 2026-11-18 over
# the MOTION only, with the owner's go-ahead ("Yes, re-pin them"): the same two clips (their 2026-11-10 whole-file
# hashes 3b556f5d / 8e128c5e matched on main first). The "source" block names the rig by its absolute checkout path
# and the rig / tool sha, so the same clip rebuilt in another checkout (the committed-tree proof's sandbox) missed
# its pin and test_anim_switch_speed failed there.
_SWITCH_GATE_GRANDFATHERED = {
    "0af32fd164cd19366dc8ddf09d39b0a174df4167",  # GunSwitch (2026-11-10, motion only)
    "d37df2e5ac55024fe158a8f4be241871e089d6f1",  # GunSideSwitch (2026-11-10, motion only)
}


def _clip_hash(clip):
    """sha1 of the clip's MOTION as it was loaded (json.dumps, sorted keys, its "source" provenance left out: a
    checkout path and the tools' sha are where it was made, not what it is) — used for grandfathering"""
    motion = {k: v for k, v in clip.items() if k != "source"} if isinstance(clip, dict) else clip
    return hashlib.sha1(json.dumps(motion, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------- loading
def rig_path(name, root="."):
    return os.path.join(root, RIG_DIR, str(name).lower() + ".json")


def load_rig(name, root="."):
    with open(rig_path(name, root), encoding="utf-8") as fh:
        return json.load(fh)


def load_clip(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- maths
def cf(components):
    """a Roblox CFrame (12 components: x y z, then the rotation rows) -> 4x4"""
    m = np.eye(4)
    m[:3, 3] = components[:3]
    m[:3, :3] = np.array(components[3:], dtype=float).reshape(3, 3)
    return m


def quat_mat(q):
    """{x, y, z, w} -> 3x3 rotation (rows)"""
    x, y, z, w = (float(v) for v in q[:4])
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def quat_angle(a, b):
    """the angle between two rotations, degrees (4 atan2(|a - b|, |a + b|): exact near 0, where acos is not)"""
    qa, qb = np.array(a[:4], dtype=float), np.array(b[:4], dtype=float)
    if float(np.dot(qa, qb)) < 0:
        qb = -qb
    return math.degrees(4 * math.atan2(float(np.linalg.norm(qa - qb)), float(np.linalg.norm(qa + qb))))


CONTACT = 0.04  # studs above the floor within which a foot counts as planted


def euler_mat(deg):
    """CFrame.Angles(x, y, z) in degrees -> 3x3 (Rx * Ry * Rz)"""
    x, y, z = (math.radians(v) for v in deg)
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rx @ ry @ rz


# ---------------------------------------------------------------- the sampler (mirrors kit/lib/anim.luau)
def _bounce_out(t):
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def _ease_in(style, t):
    if style in ("Cubic", "CubicV2"):
        return t * t * t
    if style == "Elastic":
        if t <= 0:
            return 0.0
        if t >= 1:
            return 1.0
        p = 0.3
        return -(2 ** (10 * (t - 1))) * math.sin((t - 1 - p / 4) * (2 * math.pi) / p)
    if style == "Bounce":
        return 1 - _bounce_out(1 - t)
    return t


def ease(style, direction, t):
    """the eased alpha of a Roblox EasingStyle / EasingDirection at t (0..1): In = slow start, Out = fast start"""
    t = min(1.0, max(0.0, t))
    if style == "Constant":
        if direction == "In":
            return 1.0 if t >= 1 else 0.0
        if direction == "Out":
            return 1.0 if t > 0 else 0.0
        return 0.0 if t < 0.5 else 1.0
    if direction == "In":
        return _ease_in(style, t)
    if direction == "Out":
        return 1 - _ease_in(style, 1 - t)
    if t < 0.5:
        return _ease_in(style, 2 * t) / 2
    return 1 - _ease_in(style, 2 - 2 * t) / 2


def mat_quat(m):
    """3x3 (rows) -> [x, y, z, w]"""
    m = np.asarray(m, dtype=float)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s_ = math.sqrt(tr + 1) * 2
        q = [(m[2, 1] - m[1, 2]) / s_, (m[0, 2] - m[2, 0]) / s_, (m[1, 0] - m[0, 1]) / s_, 0.25 * s_]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s_ = math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s_, (m[0, 1] + m[1, 0]) / s_, (m[0, 2] + m[2, 0]) / s_, (m[2, 1] - m[1, 2]) / s_]
    elif m[1, 1] > m[2, 2]:
        s_ = math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s_, 0.25 * s_, (m[1, 2] + m[2, 1]) / s_, (m[0, 2] - m[2, 0]) / s_]
    else:
        s_ = math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s_, (m[1, 2] + m[2, 1]) / s_, 0.25 * s_, (m[1, 0] - m[0, 1]) / s_]
    n_ = math.sqrt(sum(v * v for v in q)) or 1.0
    return [v / n_ for v in q]


def slerp(a, b, t):
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + (b - a) * t
        return (q / np.linalg.norm(q)).tolist()
    th0 = math.acos(max(-1.0, min(1.0, d)))
    th = th0 * t
    s0 = math.cos(th) - d * math.sin(th) / math.sin(th0)
    s1 = math.sin(th) / math.sin(th0)
    q = s0 * a + s1 * b
    return (q / np.linalg.norm(q)).tolist()


def sample_keys(keys, times):
    """character-space keys [{t, rot (deg), pos, ease, dir}] -> frames [qx, qy, qz, qw, px, py, pz] at `times`
    (a key's ease/dir shape the segment to the next key; hold beyond the last)"""
    qs = [mat_quat(euler_mat(k["rot"])) for k in keys]
    out = []
    for t in times:
        if t <= keys[0]["t"]:
            q, p = qs[0], keys[0]["pos"]
        elif t >= keys[-1]["t"]:
            q, p = qs[-1], keys[-1]["pos"]
        else:
            q, p = qs[-1], keys[-1]["pos"]
            for k in range(len(keys) - 1):
                a, b = keys[k], keys[k + 1]
                if a["t"] <= t < b["t"]:
                    al = ease(a.get("ease", "Cubic"), a.get("dir", "InOut"), (t - a["t"]) / (b["t"] - a["t"]))
                    q = slerp(qs[k], qs[k + 1], al)
                    p = [a["pos"][i] + (b["pos"][i] - a["pos"][i]) * al for i in range(3)]
                    break
        out.append([round(float(v), 6) for v in q] + [round(float(v), 5) for v in p])
    return out


def spec_frames(spec, times, r15_from_r6=None):
    """what kit/lib/anim.luau makes of a spec, sampled on `times`: {R15 joint: frames}. Every joint keyed at every
    spec key time (hold of its last value, rest before its first), each key's ease/dir shaping the segment after it."""
    r15_from_r6 = r15_from_r6 or {"Torso": "LowerTorso", "Head": "Head", "Right Arm": "RightUpperArm",
                                  "Left Arm": "LeftUpperArm", "Right Leg": "RightUpperLeg", "Left Leg": "LeftUpperLeg"}
    r15 = load_rig("r15")
    key_times = []
    per_joint = {}
    for key in spec["keys"]:
        t = float(key["t"])
        ease_, dir_ = key.get("ease", "Cubic"), key.get("dir", "InOut")
        key_times.append((t, ease_, dir_))
        direct = {part for part in (key.get("pose") or {}) if part in r15["joints"]}
        for part, value in (key.get("pose") or {}).items():
            name = part if part in r15["joints"] else r15_from_r6.get(part)
            if name is None or (name != part and name in direct):
                continue
            rot = value["rot"] if isinstance(value, dict) else value
            pos = value.get("pos", [0, 0, 0]) if isinstance(value, dict) else [0, 0, 0]
            per_joint.setdefault(name, {})[t] = {"t": t, "rot": list(rot), "pos": list(pos), "ease": ease_, "dir": dir_}
    out = {}
    for name, by_t in per_joint.items():
        keys, prev = [], None
        for t, ease_, dir_ in key_times:
            k = by_t.get(t)
            if k is None:
                k = {"t": t, "rot": list(prev["rot"]) if prev else [0, 0, 0], "pos": list(prev["pos"]) if prev else [0, 0, 0],
                     "ease": ease_, "dir": dir_}
            keys.append(k)
            prev = k
        out[name] = sample_keys(keys, times)
    return out


# ---------------------------------------------------------------- the clip on a rig
def character_transforms(clip, rig, i):
    """frame i -> {part: (R 3x3, p) in character space}: a clip is in its rig's own names (the R6 version of an
    R15 clip is Anim.foldToR6's clip, written by kit anim as <Name>.r6.clip.json)"""
    if clip.get("rig") != rig["rig"]:
        raise ValueError(f"clip {clip.get('name')} is in {clip.get('rig')} joint names: it does not fit {rig['rig']}")
    out = {}
    for name, j in clip["joints"].items():
        if not j.get("frames") or name not in rig["joints"]:
            continue
        f = j["frames"][min(i, len(j["frames"]) - 1)]
        out[name] = (quat_mat(f[:4]), np.array(f[4:7], dtype=float))
    return out


def joint_space(rig, part, R, p):
    """a character-space rotation/offset at a joint -> the joint-space Pose transform (what Motor6D.Transform holds)"""
    c0 = cf(rig["joints"][part]["c0"])[:3, :3]
    return c0.T @ R @ c0, c0.T @ p


def fk(rig, transforms=None):
    """{part: 4x4 CFrame relative to the root} for character-space transforms {part: (R, p)} (missing = rest)"""
    world = {rig["root"]: np.eye(4)}
    for part in rig["order"]:
        j = rig["joints"][part]
        t4 = np.eye(4)
        if transforms and part in transforms:
            R, p = transforms[part]
            tj, pj = joint_space(rig, part, R, p)
            t4[:3, :3] = tj
            t4[:3, 3] = pj
        world[part] = world[j["parent"]] @ cf(j["c0"]) @ t4 @ np.linalg.inv(cf(j["c1"]))
    return world


def world_frames(clip, rig):
    """every frame's {part: 4x4}; a clip with a `root` track (the character's own travel, [qx, qy, qz, qw, x, y, z]
    per frame: a lunge, a roll, a knockback) has it composed in, so planted feet are judged where the WORLD sees them"""
    out = [fk(rig, character_transforms(clip, rig, i)) for i in range(len(clip["times"]))]
    root = clip.get("root")
    if isinstance(root, list) and len(root) == len(out):
        for i, frames in enumerate(out):
            f = root[i]
            t4 = np.eye(4)
            t4[:3, :3] = quat_mat(f[:4])
            t4[:3, 3] = f[4:7]
            for part in list(frames):
                frames[part] = t4 @ frames[part]
    return out


def corners(rig, part, m):
    sx, sy, sz = (s / 2 for s in rig["sizes"][part])
    pts = np.array([[x, y, z, 1.0] for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)])
    return (m @ pts.T).T[:, :3]


def lowest(rig, part, m):
    return float(corners(rig, part, m)[:, 1].min())


# ---------------------------------------------------------------- metrics
def _phases(speed, times):
    """anticipation / action / recovery from a speed curve: the action is the run around the peak at >= half of it"""
    if len(speed) == 0:
        return None
    k = int(np.argmax(speed))
    half = speed[k] * 0.5
    a0, a1 = k, k
    while a0 > 0 and speed[a0 - 1] >= half:
        a0 -= 1
    while a1 < len(speed) - 1 and speed[a1 + 1] >= half:
        a1 += 1
    # speed[i] is the step between frames i and i+1
    return {"anticipation": [0, a0], "action": [a0, a1 + 1], "recovery": [a1 + 1, len(times) - 1],
            "anticipation_s": round(float(times[a0]), 3), "action_s": round(float(times[a1 + 1] - times[a0]), 3),
            "recovery_s": round(float(times[-1] - times[a1 + 1]), 3)}


def step_frames(clip):
    """the frames a STEPPED clip (strike.py `step`, limited animation) snaps on on purpose: each held pose's next
    frame inside a declared window, and the frame the window hands back to smooth motion - the pop gates skip them"""
    out = set()
    fps = float(clip.get("fps") or 30)
    for t0, t1, on in clip.get("stepped") or []:
        i0, i1, on = int(round(t0 * fps)), int(round(t1 * fps)), int(on)
        out.update(range(i0 + on, i1 + 1, on))
        out.add(i1 + 1)
    return out


def step_holds(clip):
    """{frame: N} - a stepped clip's snap frames and how many frames each held pose stands for (1 = a blocking file)"""
    out = {}
    fps = float(clip.get("fps") or 30)
    for t0, t1, on in clip.get("stepped") or []:
        i0, i1, on = int(round(t0 * fps)), int(round(t1 * fps)), int(on)
        for f in list(range(i0 + on, i1 + 1, on)) + [i1 + 1]:
            out[f] = on
    return out


def destep(clip):
    """a STEPPED clip's smooth motion back: inside each declared window the held poses are exact samples of the
    smooth solve every N frames - the frames between are slerped / lerped from them (joints, blade tip / grip / edge,
    root), so the research measures (speeds, holds) read the motion, not the snaps. A clip with no steps comes back
    as it is. A window ending on the LAST frame keeps its final hold (no sample after it to aim at) - the build gate
    therefore checks the move generated without its steps"""
    if not clip.get("stepped"):
        return clip
    import copy
    c = copy.deepcopy(clip)
    fps = float(c.get("fps") or 30)
    n = len(c["times"])
    tracks = [j["frames"] for j in c["joints"].values()]
    sw = c.get("sword") or {}
    vec = [sw[k] for k in ("grip_path",) if sw.get(k)] + ([c["root"]] if c.get("root") else [])
    T, G, E = sw.get("tip"), sw.get("grip_path"), sw.get("edge")

    def sph(a, b, w):                                   # a direction swung round the sphere (a blade turns, it
        a, b = np.asarray(a, float), np.asarray(b, float)   # does not cut the corner of its arc)
        a, b = a / max(1e-9, np.linalg.norm(a)), b / max(1e-9, np.linalg.norm(b))
        om = math.acos(max(-1.0, min(1.0, float(a @ b))))
        if om < 1e-6:
            return a
        return (math.sin((1 - w) * om) * a + math.sin(w * om) * b) / math.sin(om)
    for t0, t1, on in c["stepped"]:
        i0, i1, on = int(round(t0 * fps)), min(n - 1, int(round(t1 * fps))), int(on)
        keys = list(range(i0, i1 + 1, on))
        nxt = keys[1:] + [min(n - 1, i1 + 1)]
        for a, b in zip(keys, nxt):
            if b <= a:
                continue
            for i in range(a + 1, min(b, i1 + 1)):
                w = (i - a) / (b - a)
                for F in tracks:
                    F[i] = [float(v) for v in slerp(F[a][:4], F[b][:4], w)] + [
                        float(F[a][k] * (1 - w) + F[b][k] * w) for k in range(4, len(F[a]))]
                for V in vec:
                    V[i] = [float(V[a][k] * (1 - w) + V[b][k] * w) for k in range(len(V[a]))]
                if T and G:
                    da, db = np.subtract(T[a], G[a]), np.subtract(T[b], G[b])
                    L = float(np.linalg.norm(da)) * (1 - w) + float(np.linalg.norm(db)) * w
                    T[i] = [float(x) for x in np.asarray(G[i], float) + sph(da, db, w) * L]
                if E:
                    E[i] = [float(x) for x in sph(E[a], E[b], w)]
    return c


def clip_fps(clip):
    """the clip's frames a second: what it says, else what its own times say (30 only for a clip of one frame)"""
    f = clip.get("fps")
    if isinstance(f, (int, float)) and not isinstance(f, bool) and f == f and f > 0:
        return float(f)
    t = clip.get("times") or []
    return (len(t) - 1) / float(t[-1]) if len(t) > 1 and float(t[-1]) > 0 else 30.0


def metrics(clip, rig, gates=None):
    """the motion measured over the whole clip + the problems the gates found (empty = pass)"""
    g = dict(GATES)
    g.update(clip.get("gate") or {})
    g.update(gates or {})
    times = np.array(clip["times"], dtype=float)
    n = len(times)
    fps = clip_fps(clip)                                     # (a clip with no fps: a Hit's lateness was counted in half frames)
    dt = np.maximum(np.diff(times), 1e-9) if n > 1 else np.array([])
    frames = world_frames(clip, rig)
    out = {"name": clip.get("name"), "rig": rig["rig"], "fps": fps, "duration": clip.get("duration"), "frames": n,
           "joints": {}, "effectors": {}, "events": [], "problems": [], "notes": []}
    # joints: how fast each turns, and one-frame snaps (a stepped clip's declared steps are not snaps)
    pops = []
    intended = step_frames(clip)
    for name, j in clip["joints"].items():
        fr = j.get("frames")
        if not fr or len(fr) < 2 or n < 2:
            continue
        steps = np.array([quat_angle(fr[i], fr[i + 1]) for i in range(min(n, len(fr)) - 1)])
        speed = steps / dt[:len(steps)]
        k = int(np.argmax(speed))
        found = []
        for i in range(len(steps)):
            prev = steps[i - 1] if i > 0 else 0.0
            nxt = steps[i + 1] if i + 1 < len(steps) else 0.0
            if steps[i] > g["pop_deg"] and steps[i] > 3 * max(prev, nxt, 1e-6) and (i + 1) not in intended:
                found.append({"frame": i + 1, "t": round(float(times[i + 1]), 4), "deg": round(float(steps[i]), 2)})
        out["joints"][name] = {"peak_deg_s": round(float(speed[k]), 1), "peak_t": round(float(times[k + 1]), 4),
                               "peak_frame": k + 1, "total_deg": round(float(steps.sum()), 1), "pops": found}
        pops += [(name, p) for p in found]
    # effectors: hands, feet, head — where they go and how fast; a clip carrying a weapon path (kit/anim/strike.py:
    # `sword.tip`) adds the BLADE: a cut's Hit lands where the steel is fastest, not the hand
    fastest = None
    tracks = {e: np.array([frames[i][e][:3, 3] for i in range(n)]) for e in effectors_of(rig)}
    if isinstance(clip.get("sword"), dict) and clip["sword"].get("tip") and len(clip["sword"]["tip"]) == n:
        tips = np.array(clip["sword"]["tip"], dtype=float)
        root = clip.get("root")
        if isinstance(root, list) and len(root) == n:          # the blade travels with the character's root track
            tips = np.array([quat_mat(r[:4]) @ tips[i] + np.array(r[4:7], dtype=float) for i, r in enumerate(root)])
        tracks["Blade"] = tips
    for e, pos in tracks.items():
        d = np.linalg.norm(np.diff(pos, axis=0), axis=1) if n > 1 else np.array([])
        sp = d / dt if n > 1 else np.array([])
        k = int(np.argmax(sp)) if len(sp) else 0
        rec = {"peak_studs_s": round(float(sp[k]), 2) if len(sp) else 0.0,
               "peak_t": round(float(times[k + 1]), 4) if len(sp) else 0.0, "peak_frame": k + 1 if len(sp) else 0,
               "path_studs": round(float(d.sum()), 2) if len(d) else 0.0,
               "positions": [[round(float(v), 4) for v in p] for p in pos]}
        out["effectors"][e] = rec
        if fastest is None or rec["peak_studs_s"] > out["effectors"][fastest]["peak_studs_s"]:
            fastest = e
    out["fastest"] = fastest
    if fastest and n > 1:
        pos = np.array(out["effectors"][fastest]["positions"])
        sp = np.linalg.norm(np.diff(pos, axis=0), axis=1) / dt
        out["phases"] = _phases(sp, times)
    # events against the fastest motion: a Hit lands just after the peak
    for ev in clip.get("events") or []:
        rec = {"name": ev.get("name"), "t": ev.get("t")}
        is_hit = str(ev.get("name", "")).lower() in HIT_NAMES
        if is_hit and not (fastest and out["effectors"][fastest]["peak_studs_s"] > 0.5):
            out["problems"].append(f"{ev['name']} on a clip where nothing moves faster than 0.5 studs/s — a hit needs a strike")
        if fastest and out["effectors"][fastest]["peak_studs_s"] > 0.5:
            # a multi-strike clip peaks more than once: a Hit is judged against the NEAREST strike (a local peak of
            # the fastest effector's speed reaching 40% of the clip's top), the clip's top when nothing else peaks
            peak_t = out["effectors"][fastest]["peak_t"]
            peaks = [peak_t]
            # the strikers: the blade when there is one, else the hands - a dash moves the head fastest, but the
            # hit is where the steel (or the fist) peaks; every striker's local peaks are candidates
            strikers = [e for e in out["effectors"] if e == "Blade" or "Hand" in e or "Arm" in e] or [fastest]
            lead = fastest
            if ev.get("by") in out["effectors"]:             # the event names its striker (a kick: the leg) - only
                strikers, peaks, lead = [ev["by"]], [], ev["by"]   # that limb's peaks count (2026-10-14: a hand
                # flung by the hip spin was judged as the 'strike' of a roundhouse)
            owners = [lead] * len(peaks)                    # peaks found before the strikers belong to the fastest
            for e in set(strikers) | {lead}:
                pe = np.array(out["effectors"][e]["positions"])
                se = np.linalg.norm(np.diff(pe, axis=0), axis=1) / dt
                if se.max() < 0.5:
                    continue
                for k in range(len(se)):
                    before = se[k - 1] if k > 0 else -1.0
                    after = se[k + 1] if k + 1 < len(se) else -1.0
                    if se[k] >= 0.4 * se.max() and se[k] >= before and se[k] > after:
                        peaks.append(float(times[k + 1]))
                        owners.append(e)
            near = min(peaks, key=lambda t: abs(float(ev["t"]) - t))
            rec["peak_of"] = owners[peaks.index(near)] if owners else None
            rec["peak_t"] = round(near, 4)
            delta = (float(ev["t"]) - near) * fps
            rec["delta_frames"] = round(delta, 1)
            if str(ev.get("name", "")).lower() in HIT_NAMES and (delta < -g["hit_before"] - 1e-6 or delta > g["hit_after"] + 1e-6):
                when = "before" if delta < 0 else "after"
                out["problems"].append(
                    f"{ev['name']} lands {abs(delta):.1f} frames {when} the nearest strike ({rec['peak_of']} peaks at "
                    f"{near:.2f} s) — put it 0..{g['hit_after']} frames after the peak")
        out["events"].append(rec)
    # feet: planted feet must not slide; nothing goes under the ground they stand on
    feet = feet_of(rig)
    loco = clip.get("locomotion")
    if feet and n > 1:
        # a foot stands on its SOLE's centre (a tilted box's corner dips: a one-piece R6 leg digs in at every plant)
        bottoms = {f: np.array([(frames[i][f] @ np.array([0.0, -rig["sizes"][f][1] / 2, 0.0, 1.0]))[1] for i in range(n)]) for f in feet}
        ground = rest_ground(rig, feet)
        if ground is None:
            ground = min(float(b.min()) for b in bottoms.values())
        slide_max, slide_total, contact_frames, skate_max, skid_max = 0.0, 0.0, {}, 0.0, 0.0
        # A SLIDE THE MOVE MEANS (kit/anim/foot_modes.py: "slides" in the move, the spec or the clip - a skid, a drag,
        # a roll): that foot is not judged inside its stretch, at the ordinary bar everywhere else. A said slide that
        # is not there, or cannot be read, is a problem: a clip does not switch its feet off by saying so
        import foot_modes as FM
        said_studs, covered = 0.0, {}
        if clip.get("slides") is not None and rig["rig"] != "R6":
            out["notes"].append("feet: the slides it says are read on the R6 clip (this one is " + str(rig["rig"]) + ")")
        if rig["rig"] == "R6" and clip.get("slides") is not None:
            try:
                wrong = FM.stale(clip, rig, g["foot_slide"], frames)
                out["problems"] += [f"feet: {w}" for w in wrong]
                if not FM.in_place(clip):                    # (a walk's feet are held to the ground's speed, said or not)
                    covered = FM.meant(clip, n, times)
            except (ValueError, KeyError, IndexError, TypeError) as e:
                out["problems"].append(f"feet: the slides it says cannot be read ({e})")
        # an in-place locomotion clip: a planted foot must move back at the ground speed (WalkSpeed matches it)
        v_exp = None
        if loco and loco.get("speed"):
            d = np.array(loco.get("direction") or [0, 0, -1], dtype=float)
            v_exp = -float(loco["speed"]) * d / max(np.linalg.norm(d), 1e-9)
        for f in feet:
            # the foot's contact point (bottom centre): on R6 the "foot" is the whole leg, whose centre moves half as far
            sole = np.array([0.0, -rig["sizes"][f][1] / 2, 0.0, 1.0])
            pos = np.array([(frames[i][f] @ sole)[:3] for i in range(n)])
            contact = bottoms[f] < ground + CONTACT
            contact_frames[f] = int(contact.sum())
            holds = step_holds(clip)
            for i in range(n - 1):
                if contact[i] and contact[i + 1]:
                    step = pos[i + 1] - pos[i]
                    d = float(math.hypot(step[0], step[2]))
                    if (i + 1) in holds:                 # a stepped clip: the slide of N held frames lands at once
                        if holds[i + 1] <= 1:
                            continue                     # a blocking file: the feet are the owner's to place
                        d /= holds[i + 1]
                    if f in covered and covered[f][i] and covered[f][i + 1]:
                        said_studs += d                  # (a slide the move means: said, not judged)
                        continue
                    slide_total += d
                    slide_max = max(slide_max, d)
                    # skate: inside a contact span only (touchdown and lift-off frames are transitions); a loop wraps
                    if clip.get("loop"):
                        before, after = contact[(i - 1) % (n - 1)], contact[(i + 2) % (n - 1)]
                    else:
                        before, after = (i == 0 or contact[i - 1]), (i + 2 >= n or contact[i + 2])
                    inside = before and after
                    if v_exp is not None:
                        skate = step - v_exp * dt[i]
                        if inside:
                            skate_max = max(skate_max, float(math.hypot(skate[0], skate[2])))
                        else:  # a touchdown / lift-off pair: the plant may settle, but it must not skid
                            skid_max = max(skid_max, float(math.hypot(skate[0], skate[2])))
        out["feet"] = {"ground_y": round(ground, 3), "slide_max_studs_frame": round(slide_max, 3),
                       "slide_total_studs": round(slide_total, 3), "contact_frames": contact_frames}
        if covered:
            out["feet"]["said_slide_studs"] = round(said_studs, 3)
        if rig["rig"] == "R6":                               # (what each foot does, stretch by stretch: for the reader)
            try:
                out["feet"]["modes"] = FM.read(clip, rig, g["foot_slide"], frames)["feet"]
            except (ValueError, KeyError, IndexError, TypeError):
                pass
        if v_exp is not None:
            out["feet"]["skate_max_studs_frame"] = round(skate_max, 3)
            out["feet"]["ground_speed"] = loco["speed"]
            out["feet"]["skid_max_studs_frame"] = round(skid_max, 3)
            if skate_max > g["foot_skate"]:
                out["problems"].append(f"foot skate: a planted foot deviates {skate_max:.2f} studs in one frame from the "
                                       f"clip's ground speed of {loco['speed']} studs/s (bar {g['foot_skate']}) — keep the "
                                       f"stance sweep linear, or fix locomotion.speed")
            if skid_max > g["foot_slide"]:
                out["problems"].append(f"foot skid: a foot slides {skid_max:.2f} studs in the frame it lands or lifts "
                                       f"(bar {g['foot_slide']}) — plant it where the stance sweep starts, lift it "
                                       f"where the sweep ends")
        elif slide_max > g["foot_slide"]:
            out["problems"].append(f"foot slide: a planted foot moves {slide_max:.2f} studs in one frame (bar "
                                   f"{g['foot_slide']}) — keep the feet where they stand, or key the body over them; a "
                                   "slide the move MEANS is said, not passed by a higher bar: \"slides\": [{\"foot\": "
                                   "\"Right Leg\", \"from\": s, \"to\": s, \"kind\": \"skid\"}] "
                                   "(python kit/anim/foot_modes.py <clip.json> shows the stretch)")
        # a real foot (a thin part) is judged at its lowest corner - a heel or a toe must stay on the floor; a leg that
        # IS the foot (R6: one two-stud part) at its sole's centre, since its corners dip whenever it tilts
        deep = [f for f in feet if (float(bottoms[f].min()) if rig["sizes"][f][1] > 1.0
                                    else min(lowest(rig, f, frames[i][f]) for i in range(n))) < ground - g["penetration"]]
        deep += [part for part in rig["order"] if part not in feet
                 and min(lowest(rig, part, frames[i][part]) for i in range(n)) < ground - g["penetration"]]
        if deep:
            out["problems"].append(f"ground penetration: {', '.join(deep)} go below the ground the feet stand on")
    # a loop ends where it starts
    if clip.get("loop"):
        worst, worst_j = 0.0, None
        for name, j in clip["joints"].items():
            fr = j.get("frames")
            if fr and len(fr) > 1:
                a = quat_angle(fr[0], fr[-1])
                if a > worst:
                    worst, worst_j = a, name
        out["loop_seam_deg"] = round(worst, 2)
        if worst > g["loop_seam_deg"]:
            out["problems"].append(f"loop seam: {worst_j} differs {worst:.1f} degrees between the last frame and the "
                                   f"first (bar {g['loop_seam_deg']}) — a loop must end where it starts")
    if pops:
        shown = ", ".join(f"{name} {p['deg']:.0f} deg at {p['t']:.2f} s" for name, p in pops[:3])
        out["problems"].append(f"pops: {shown} — a one-frame snap; spread it over frames or ease it")
    # switch / weapon-swap speed gate: a clip whose name matches switch|swap|to(left|right)hand
    # (case-insensitive) must have its fastest arm joint reach the floor peak speed.
    # "transition" is EXCLUDED: locomotion transitions (IdleToRunTransition) are legs and must not
    # be forced to snap the arms. Swap clips and SwordToLeftHand / SwordToRightHand are weapon switches.
    # Measure: max over all arm joints (R6 "Left Arm"/"Right Arm", R15 *UpperArm) of their peak
    # deg/s across consecutive frames — the same per-joint speed already computed in out["joints"].
    # Grandfathering by CONTENT HASH: only the exact committed clip data warns; a rebuild must pass.
    clip_name = str(clip.get("name") or "")
    if re.search(r"switch|swap|to(left|right)hand", clip_name, re.IGNORECASE):
        arm_keywords = ("arm",)  # matches "Left Arm", "Right Arm", "LeftUpperArm", "RightUpperArm"
        arm_peak = 0.0
        for jname, jinfo in out["joints"].items():
            if any(kw in jname.lower() for kw in arm_keywords):
                arm_peak = max(arm_peak, jinfo.get("peak_deg_s", 0.0))
        floor = g.get("switch_arm_deg_s", GATES["switch_arm_deg_s"])
        out["switch_arm_peak_deg_s"] = round(arm_peak, 1)
        if arm_peak < floor:
            msg = (f"switch arm speed: fastest arm peaks {arm_peak:.0f} deg/s (floor {floor:.0f}) — "
                   f"a switch/transition's throw arm must snap hard; the owner's words: "
                   f"\"transitions are in slow motion ... arms aren't doing anything to actually transition\"")
            if _clip_hash(clip) in _SWITCH_GATE_GRANDFATHERED:
                out.setdefault("warnings", []).append(f"[grandfather] {msg}")
            else:
                out["problems"].append(msg)
    out["gates"] = g
    return out


def summary(m):
    """one line a model reads: the fastest thing, the Hit's timing, the feet, the snaps"""
    bits = [m.get("name") or "clip"]
    f = m.get("fastest")
    if f and m["effectors"].get(f):
        e = m["effectors"][f]
        bits.append(f"{f} peaks {e['peak_studs_s']} studs/s at {e['peak_t']:.2f} s")
    for ev in m.get("events", []):
        if "delta_frames" in ev:
            whose = f" of {ev['peak_of']} at {ev['peak_t']:.2f} s" if ev.get("peak_of") else ""
            bits.append(f"{ev['name']} {ev['delta_frames']:+.1f} frames vs the nearest peak{whose}")
    if m.get("feet"):
        if "skate_max_studs_frame" in m["feet"]:
            s = m["feet"]["skate_max_studs_frame"]
            bits.append(f"ground speed {m['feet']['ground_speed']} studs/s, skate {s:.2f} studs/frame")
        else:
            s = m["feet"]["slide_max_studs_frame"]
            bits.append("feet planted" if s <= m["gates"]["foot_slide"] else f"feet slide {s:.2f} studs/frame")
    npops = sum(len(j["pops"]) for j in m["joints"].values())
    bits.append(f"{npops} pop(s)")
    if "loop_seam_deg" in m:
        bits.append(f"loop seam {m['loop_seam_deg']:.1f} deg")
    return "; ".join(bits)
