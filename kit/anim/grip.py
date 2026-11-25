"""grip.py - THE SWORD AS ITS OWN JOINT (board task m39b, AAA gaps v2 D8; board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md).

On a default R6 a tool is WELDED to the fist (RightGrip), so the blade can only point where the rigid arm points: a
strike's own blade track (its edge flips, the underhip's turn of the sword, a wrist roll) is lost in game, and the
pose route had to bend the arms to aim the blade (kit/anim/strike_r6.py: "needs an ANIMATABLE GRIP"). Here the sword
is a joint like a limb: a Motor6D "Handle" (Part0 = Right Arm, Part1 = the sword part named Handle) whose Transform
is keyed in the clip, so the blade follows the clip's own sword path exactly.

The convention (src/kit/AnimGrip.luau builds the joint the same way):
  C0 = Roblox's RightGrip C0 (the hand: 1 stud down the arm, turned -90 deg about X)
  C1 = the Handle part's grip point (the middle of the tsuka; AnimGrip.attach takes it per weapon)
  the Handle frame: origin at the grip's middle, +Y along the blade to the tip, -X toward the edge (the katana model
  assets/models/build_katana.py and kit/anim/look.py use the same frame)
  Transform = (RightArm * C0)^-1 * Handle         per frame, [qx, qy, qz, qw, x, y, z] like every clip track
The clip's sword paths and its joints are both in character space WITHOUT the root track (the root carries both).

    python kit/anim/grip.py <clip.json> [--check]     adds clip["grip"] (or checks it round-trips) - the strike route
                                                      calls add_grip() itself
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402

# RightGrip.C0 on every R6: CFrame.new(0, -1, 0, 1, 0, 0, 0, 0, 1, 0, -1, 0)
GRIP_C0 = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, -1.0], [0.0, -1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]])


def handle_frame(tip, grip, edge):
    """the sword's 4x4 in character space: origin at the grip, +Y to the tip, -X toward the edge"""
    tip, grip, edge = (np.asarray(v, dtype=float) for v in (tip, grip, edge))
    y = tip - grip
    y /= max(np.linalg.norm(y), 1e-9)
    x = -edge - y * float(np.dot(-edge, y))
    if np.linalg.norm(x) < 1e-6:                      # no usable edge: any perpendicular
        x = np.cross(y, [0.0, 0.0, 1.0]) if abs(y[2]) < 0.9 else np.cross(y, [1.0, 0.0, 0.0])
    x /= np.linalg.norm(x)
    z = np.cross(x, y)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = x, y, z, grip
    return M


def grip_track(clip, rig=None):
    """per frame the Handle Motor6D's Transform [qx, qy, qz, qw, x, y, z]; None when the clip has no sword path"""
    sw = clip.get("sword") or {}
    tips, grips, edges = sw.get("tip"), sw.get("grip_path"), sw.get("edge")
    n = len(clip.get("times") or [])
    if not (tips and grips and edges) or not (len(tips) == len(grips) == len(edges) == n):
        return None
    rig = rig or C.load_rig("r6")
    out = []
    for i in range(n):
        A = C.fk(rig, C.character_transforms(clip, rig, i))["Right Arm"]
        T = np.linalg.inv(A @ GRIP_C0) @ handle_frame(tips[i], grips[i], edges[i])
        q = C.mat_quat(T[:3, :3])
        out.append([round(float(v), 6) for v in list(q) + list(T[:3, 3])])
    return out


def played_sword(clip, rig=None):
    """the blade the GAME plays: the Handle joint's own track (clip["grip"]) through the Right Arm, back into sword
    paths {tip, grip_path, edge} in character space - the inverse of grip_track. A pass that edits only the grip track
    (the joint the game keys) leaves clip["sword"] as designed: what is checked against the owner's poses must be what
    plays (the owner's V3 list, anim stage B.2). The tip's distance from the grip is the designed one per frame (the
    sword's length when there is none). None: no grip track as long as the clip"""
    g = clip.get("grip")
    n = len(clip.get("times") or [])
    if not isinstance(g, list) or len(g) != n or n == 0:
        return None
    sw = clip.get("sword") or {}
    tips, grips = sw.get("tip") or [], sw.get("grip_path") or []
    length = float(sw.get("length") or 4.0)
    rig = rig or C.load_rig("r6")
    out = {"tip": [], "grip_path": [], "edge": []}
    for i in range(n):
        A = C.fk(rig, C.character_transforms(clip, rig, i))["Right Arm"]
        T = np.eye(4)
        T[:3, :3] = np.array(C.quat_mat(g[i][:4]))
        T[:3, 3] = g[i][4:7]
        H = A @ GRIP_C0 @ T
        o, y, x = H[:3, 3], H[:3, 1], H[:3, 0]
        L = (float(np.linalg.norm(np.asarray(tips[i], float) - np.asarray(grips[i], float)))
             if i < len(tips) and i < len(grips) else length)
        out["grip_path"].append([round(float(v), 4) for v in o])
        out["tip"].append([round(float(v), 4) for v in o + y * L])
        out["edge"].append([round(float(v), 4) for v in -x])
    return out


def add_grip(clip, rig=None):
    g = grip_track(clip, rig)
    if g is not None:
        clip["grip"] = g
    return clip


# THE LEFT HAND'S WEAPON (Sample Game's Onyx, 2026-10-26: the owner, 1/10 - "u having even done the black gun as proper
# as the silver"). The game builds a Motor6D on the Left Arm with this C0 (Config.DualWield.LeftGrip: the gun along the
# arm, +Y down the arm to the muzzle) - so a clip that leaves the left gun alone (identity Transform) holds it exactly
# as before. A pose spec aims it per key with a top-level "left_gun": {"blade": [x, y, z], "edge": [x, y, z]} in stage
# axes (x right, y up, z forward; "edge" = the grip-down side, left out = upright); between keys the turn is slerped on
# the key's own easing, and the grip stays in the fist (the joint's origin) - unless a key gives "at": [x, y, z], a
# stage point the gun flies through OUT of the hand (a toss, a catch: the generator keys the arc densely); between two
# keys the position blends from each key's point (its "at", or the fist on that frame) so a release and a catch hand
# over without a jump. Exported as a "Handle" pose under the Left Arm (kit/lib/anim.luau), like the right hand's.
LEFT_C0 = np.array([[0.0, 0.0, -1.0, 0.0], [0.0, -1.0, 0.0, -0.95], [-1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]])

_EASE_FAMILIES = {"sine": "Sine", "quad": "Quad", "cubic": "Cubic", "quart": "Quart", "quint": "Quint", "expo": "Exponential",
                  "circ": "Circular", "back": "Back", "elastic": "Elastic", "bounce": "Bounce"}
_EASE_DIRS = {"in": "In", "out": "Out", "inout": "InOut"}


def _ease_in(fam, t):
    """Blender's easing curves (Robert Penner's equations, as its F-curve SINE ... BOUNCE interpolation), the In half.
    (clip.ease is Roblox's pose easing - Linear / Cubic / Elastic / Bounce only - so a sine or quad key read there
    came out LINEAR: the left gun turned on straight lines while the arm around it eased, 2026-10-27)"""
    if fam == "sine":
        return 1 - math.cos(t * math.pi / 2)
    if fam in ("quad", "cubic", "quart", "quint"):
        return t ** {"quad": 2, "cubic": 3, "quart": 4, "quint": 5}[fam]
    if fam == "expo":
        return 0.0 if t <= 0 else 2 ** (10 * (t - 1))
    if fam == "circ":
        return 1 - math.sqrt(max(0.0, 1 - t * t))
    if fam == "back":
        s = 1.70158                                    # Blender's default "back" amount
        return t * t * ((s + 1) * t - s)
    return C.ease(_EASE_FAMILIES[fam], "In", t)       # elastic, bounce


def _alpha(ease_name, t):
    """a pose key's easing name (kit/anim/pose_r6.py: bezier, linear, constant, <family>_<in|out|inout>) at t"""
    t = min(1.0, max(0.0, t))
    name = str(ease_name or "bezier").lower()
    if name == "linear":
        return t
    if name == "constant":
        return 0.0 if t < 1 else 1.0
    fam, _, d = name.partition("_")
    if fam not in _EASE_FAMILIES or d not in _EASE_DIRS:
        fam, d = "sine", "inout"                      # bezier (Blender's auto handles) reads as an S-curve
    if d == "in":
        return _ease_in(fam, t)
    if d == "out":
        return 1 - _ease_in(fam, 1 - t)
    return _ease_in(fam, 2 * t) / 2 if t < 0.5 else 1 - _ease_in(fam, 2 - 2 * t) / 2


def _stage_dir(v):
    """a stage direction (x right, y up, z forward) in character space (x right, y up, -z forward)"""
    v = np.asarray(v, dtype=float)
    return np.array([v[0], v[1], -v[2]])


def _stage_point(p):
    """a stage point (y up from the floor, z forward) in character space (the root at the origin, -z forward)"""
    p = np.asarray(p, dtype=float)
    return np.array([p[0], p[1] - 3.0, -p[2]])


def _left_rot(lg):
    """the left gun's 3x3 in character space from a key's {"blade", "edge"} (Handle frame: +Y blade, -X edge)"""
    y = _stage_dir(lg["blade"])
    y /= max(np.linalg.norm(y), 1e-9)
    if lg.get("edge") is not None:
        edge = _stage_dir(lg["edge"])
    else:                                             # upright: the grip down, as far as the barrel allows
        up = np.array([0.0, 1.0, 0.0])
        edge = -(up - y * float(np.dot(up, y)))
    return handle_frame(y, np.zeros(3), edge)[:3, :3]


# THROWN (Sample Game style v4, 2026-10-27 - Onyx as good as Pearl: the right gun's "throw" mode, kit/anim/pose_r6.py):
# a key's "left_gun" with "throw": {"turns": n, "g": 35, "axis": [x, y, z], "pivot": [x, y, z]} lets the gun go there -
# from where it is at that key (in the fist, or its "at") it flies a BALLISTIC arc under g (studs/s^2, down), spinning
# at a constant rate (n whole extra turns about "axis", the gun's own Handle frame: +Y barrel, +X top; default -Z, an
# end-over-end flip in the gun's own plane, the barrel rising over the top first like the right gun's default) about
# its centre ("pivot", Handle frame, studs) and lands EXACTLY on the
# next key's pose (in a fist on that frame, or its "at"). Only whole turns, so it lands on the pose.
LEFT_PIVOT = (0.19, 0.54, 0.0)


def _left_pose(lg, q, J):
    """the left gun's 4x4 in character space at a key: its turn q, in the fist J or at its "at" """
    M = np.eye(4)
    M[:3, :3] = C.quat_mat(q)
    M[:3, 3] = _stage_point(lg["at"]) if "at" in lg else J[:3, 3]
    return M


def grip_left_track(clip, keys, rig=None):
    """per frame the Left Arm's Handle Transform [qx, qy, qz, qw, x, y, z]; None when no key aims the left gun"""
    aims = [(float(k["f"]), str(k.get("ease", "bezier")), k["left_gun"]) for k in keys if isinstance(k.get("left_gun"), dict)]
    times = clip.get("times") or []
    if not aims or not times:
        return None
    rig = rig or C.load_rig("r6")
    fps = float(clip.get("fps", 60))
    quats = [C.mat_quat(_left_rot(lg)) for _, _, lg in aims]
    n = len(times)

    def fist(f):
        i = min(n - 1, max(0, int(round(f))))
        return C.fk(rig, C.character_transforms(clip, rig, i))["Left Arm"] @ LEFT_C0
    throws = {}
    for j in range(len(aims) - 1):
        th = aims[j][2].get("throw")
        if isinstance(th, dict):
            fa, fb = aims[j][0], aims[j + 1][0]
            throws[j] = (_left_pose(aims[j][2], quats[j], fist(fa)), _left_pose(aims[j + 1][2], quats[j + 1], fist(fb)),
                         max(fb - fa, 1e-9) / fps, th)
    out = []
    for i, t in enumerate(times):
        f = float(t) * fps
        j = max([m for m in range(len(aims)) if aims[m][0] <= f] or [0])
        if j in throws and aims[j][0] <= f < aims[j + 1][0]:
            import pose_r6 as PR
            A, B, T, th = throws[j]
            u = (f - aims[j][0]) / (aims[j + 1][0] - aims[j][0])
            H = PR.throw_pose(A, B, u, T, float(th.get("g", 35.0)), th.get("pivot", LEFT_PIVOT),
                              th.get("axis", [0.0, 0.0, -1.0]), float(round(float(th.get("turns", 0.0)))), (0.0, 1.0, 0.0))
            J = C.fk(rig, C.character_transforms(clip, rig, i))["Left Arm"] @ LEFT_C0
            T4 = np.linalg.inv(J) @ H
            qt = C.mat_quat(T4[:3, :3] / np.linalg.norm(T4[:3, :3], axis=0))
            out.append([round(float(v), 6) for v in list(qt) + list(T4[:3, 3])])
            continue
        if f <= aims[0][0]:
            q = quats[0]
        elif f >= aims[-1][0]:
            q = quats[-1]
        else:
            j = max(n for n in range(len(aims)) if aims[n][0] <= f)
            fa, ease_a, _ = aims[j]
            fb = aims[j + 1][0]
            w = _alpha(ease_a, (f - fa) / max(fb - fa, 1e-9))
            q = C.slerp(quats[j], quats[j + 1], w)
        A = C.fk(rig, C.character_transforms(clip, rig, i))["Left Arm"]
        J = A @ LEFT_C0
        H = np.eye(4)
        H[:3, :3] = C.quat_mat(q)
        # where the grip is: in the fist, or a key's "at" (out of the hand), blended between the two keys around f
        if f <= aims[0][0] or f >= aims[-1][0]:
            lg = aims[0][2] if f <= aims[0][0] else aims[-1][2]
            H[:3, 3] = _stage_point(lg["at"]) if "at" in lg else J[:3, 3]
        else:
            pa = _stage_point(aims[j][2]["at"]) if "at" in aims[j][2] else J[:3, 3]
            pb = _stage_point(aims[j + 1][2]["at"]) if "at" in aims[j + 1][2] else J[:3, 3]
            # a free stretch moves straight between its points (the generator keys the arc densely); in the fist, both
            # ends ARE the fist and this is the fist
            H[:3, 3] = pa + (pb - pa) * (w if ("at" in aims[j][2]) != ("at" in aims[j + 1][2]) else (f - fa) / max(fb - fa, 1e-9))
        T = np.linalg.inv(J) @ H
        qt = C.mat_quat(T[:3, :3])
        out.append([round(float(v), 6) for v in list(qt) + list(T[:3, 3])])
    return out


def add_grip_left(clip, keys, rig=None):
    g = grip_left_track(clip, keys, rig)
    if g is not None:
        clip["grip_left"] = g
    return clip


def left_barrels(clip, rig=None):
    """per frame the left gun's barrel direction (its Handle +Y) in character space - for checks and the aim measure"""
    rig = rig or C.load_rig("r6")
    out = []
    for i, g in enumerate(clip.get("grip_left") or []):
        A = C.fk(rig, C.character_transforms(clip, rig, i))["Left Arm"]
        T = np.eye(4)
        T[:3, :3] = C.quat_mat(g[:4])
        T[:3, 3] = g[4:7]
        out.append((A @ LEFT_C0 @ T)[:3, 1].tolist())
    return out


def left_paths(clip, length=1.85, rig=None):
    """the left gun as a weapon PATH like the right one's clip["sword"] (character space: grip, muzzle tip, the
    grip-down edge per frame) - the look draws Onyx from it (kit/anim/look_r6.py; before 2026-10-27 only the right gun
    was drawn, so no preview ever showed Onyx's motion)"""
    rig = rig or C.load_rig("r6")
    grips, tips, edges = [], [], []
    for i, g in enumerate(clip.get("grip_left") or []):
        A = C.fk(rig, C.character_transforms(clip, rig, i))["Left Arm"]
        T = np.eye(4)
        T[:3, :3] = C.quat_mat(g[:4])
        T[:3, 3] = g[4:7]
        H = A @ LEFT_C0 @ T
        grips.append(H[:3, 3].tolist())
        tips.append((H[:3, 3] + H[:3, 1] * length).tolist())
        edges.append((-H[:3, 0]).tolist())
    return {"kind": "pistol", "grip_path": grips, "tip": tips, "edge": edges}


def round_trip_error(clip, rig=None):
    """the largest distance (studs) between the clip's own blade tip and the tip the Handle joint puts it at"""
    rig = rig or C.load_rig("r6")
    sw, worst = clip["sword"], 0.0
    for i, g in enumerate(clip["grip"]):
        A = C.fk(rig, C.character_transforms(clip, rig, i))["Right Arm"]
        T = np.eye(4)
        T[:3, :3] = C.quat_mat(g[:4])
        T[:3, 3] = g[4:7]
        H = A @ GRIP_C0 @ T
        L = float(np.linalg.norm(np.asarray(sw["tip"][i]) - np.asarray(sw["grip_path"][i])))
        tip = (H @ np.array([0.0, L, 0.0, 1.0]))[:3]
        worst = max(worst, float(np.linalg.norm(tip - np.asarray(sw["tip"][i]))))
    return worst


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "fail", "summary": "grip: needs <clip.json>", "next_action": "python kit/anim/grip.py build/animations/<Name>.clip.json"}))
        sys.exit(1)
    path = sys.argv[1]
    clip = json.load(open(path, encoding="utf-8"))
    if "--check" not in sys.argv:
        add_grip(clip)
        if "grip" in clip:
            json.dump(clip, open(path, "w", encoding="utf-8"), indent=1)
    if "grip" not in clip:
        print(json.dumps({"status": "warn", "summary": f"grip: {path} has no sword path - nothing to key", "next_action": "none"}))
        sys.exit(0)
    err = round_trip_error(clip)
    ok = err < 1e-3
    print(json.dumps({"status": "pass" if ok else "fail", "summary": f"grip: {len(clip['grip'])} frames, blade tip round-trips within {err:.6f} studs",
                      "next_action": "none" if ok else "the Handle track does not reproduce the clip's blade: check GRIP_C0 / handle_frame"}))
    sys.exit(0 if ok else 1)
