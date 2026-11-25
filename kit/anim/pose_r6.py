"""pose_r6.py — an R6 animation AUTHORED ON THE OWNER'S RIG, the way an animator keys it.

    blender -b assets/rigs/R6_IK.blend --disable-autoexec --python-exit-code 2 -P kit/anim/pose_r6.py --
        <Name>.pose.json --out <clip.json> [--save <Name>.r6.blend]

The owner's rig (assets/rigs/R6_IK.blend) is a Roblox Blender-Animations rig with an animator's control layer: the
part meshes ride deform bones that sit on the Roblox joint pivots (Torso, Head, Right Arm, ...), and those follow
CONTROLLER bones - Body (the torso, pivot at the root), Head.001, Arm.R / Arm.L (shoulders), and IK legs: Foot.R /
Foot.L on the floor, the rigid leg pinned at the foot and aimed at the hip anchor (a lowered body sinks over legs that
stay vertical; a wide stance comes from the feet; the SoftIK.* slider = 2 and its FK flag off; assets/rigs/R6_IK.md). This tool keys THOSE
controllers from key poses, with IK on, so the motion is exactly what the rig produces when an animator poses it.

The key poses (<Name>.pose.json), in STAGE coordinates: x right, y up FROM THE FLOOR, z FORWARD (the character
stands at the origin facing +z; rest: torso centre (0, 3, 0), right hand (1.5, 2, 0), feet (+-0.5, 0, 0)):
    {"name": ..., "fps": 60, "loop": false, "priority": "Action",
     "sword": {"blade": 4.2, "grip_pitch": 0, "spacing": 0.75},      # optional: a greatsword in the right hand
              # (+ "kind": "katana" | "pistol", "grip": "animated": the weapon turns in the fist - keyed in game as the
              #  Handle Motor6D, kit/anim/grip.py - and a key's right_arm "edge": [x, y, z] rolls it, e.g. a pistol's grip down)
     "only": ["Right Arm", "Left Arm"],                              # optional: export only these joints (a layer)
     "events": [{"name": "Hit", "f": 24}],                           # frames at fps (or "t" seconds)
     "offsets": {"arms": 2, "head": 3},                              # the drag hierarchy: frames each group trails
     "keys": [{"f": 0, "ease": "bezier",                             # the easing of the segment FROM this key
               "body": {"pos": [dx, dy, dz], "lean": 10, "turn": -30, "tilt": 0},   # lean + = forward,
                                                                     # turn + = to the character's right, tilt + = right shoulder down
               "head": {"look": [x, y, z], "tilt": 0},              # a direction in stage axes (kept on target)
               "right_arm": {"hand": [x, y, z], "blade": [x, y, z]},  # the hand's stage position, the blade's direction
               "left_arm": "hilt" | {"on_blade": d} | {"hand": [x, y, z]} | {"aim": [x, y, z]},
               "right_foot": {"at": [x, z], "lift": 0, "turn": 0}, "left_foot": {...}}, ...]}
Fields a key leaves out are held from the key before (key 0 from the rest pose), field by field - an arm key with only
"blade" keeps its held hand; a new "hand" / "aim" / "rot" replaces the held placement. An arm aims its hand at "hand"
(R6 reach is 1.58 studs from the shoulder pivot; up to 0.5 more is closed by sliding the arm, as R6 animators do)
and twists so the blade comes as close as the grip allows to "blade" (the blade leaves the fist perpendicular to the
arm, turned toward it by grip_pitch). "left_arm": "hilt" solves the left hand onto the hilt EVERY frame (spacing
studs below the right hand), so a two-handed grip holds through the swing. Easing names: bezier (Blender's auto
handles), linear, constant, and <sine|quad|cubic|quart|quint|expo|circ|back|elastic|bounce>_<in|out|inout>.

Out: the neutral clip (R6 joint transforms per frame, read off the evaluated deform bones exactly as the engine
plays them; the sword path for the look and the Hit metric) - and, with --save, the owner's rig with the motion as an
action on its controllers, IK on, and the greatsword on the right hand: open it in Blender, scrub it, edit it
(`kit anim edit <Name>` makes the edited file the source). The bake is checked: every part's position recomputed
from the clip must match the evaluated rig within 0.01 studs on every frame, or the tool fails."""
import hashlib
import json
import math
import os
import sys

import numpy as np

try:                                   # inside Blender; the pose maths (solve_arm, merged_keys, ...) import without it
    import bpy
    from mathutils import Matrix, Quaternion, Vector
except ImportError:                    # pragma: no cover - the python tests
    bpy = Matrix = Quaternion = Vector = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clip as C  # noqa: E402  (the kit's FK: the bake is checked against what the engine will play)

PARTS = ["HumanoidRootPart", "Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
CONTROLLERS = ["Main Controller", "Body", "Head.001", "Arm.R", "Arm.L", "Foot.R", "Foot.L"]
# Blender world: x right, y forward (the character faces +y), z up. Roblox: x right, y up, -z forward.
P3 = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])   # Roblox vector -> Blender vector
HRP = np.array([0.0, 0.0, 3.0])                            # the root's rest (Blender), three studs over the floor
# rest points (Blender): joint pivots and the hand points at the bottom of each arm
PIVOT = {"Right Arm": np.array([1.0, 0, 3.5]), "Left Arm": np.array([-1.0, 0, 3.5]), "Head": np.array([0, 0, 4.0]),
         "Right Leg": np.array([1.0, 0, 2.0]), "Left Leg": np.array([-1.0, 0, 2.0]),
         "Torso": np.array([0, 0, 3.0])}
HAND = {"Right Arm": np.array([1.5, 0, 2.0]), "Left Arm": np.array([-1.5, 0, 2.0])}
CENTRE = {"Torso": np.array([0, 0, 3.0]), "Head": np.array([0, 0, 4.5]), "Right Arm": np.array([1.5, 0, 3.0]),
          "Left Arm": np.array([-1.5, 0, 3.0]), "Right Leg": np.array([0.5, 0, 1.0]), "Left Leg": np.array([-0.5, 0, 1.0])}
FOOT_REST = {"Foot.R": np.array([0.5, 0, 0.0]), "Foot.L": np.array([-0.5, 0, 0.0])}
REACH = float(np.linalg.norm(HAND["Right Arm"] - PIVOT["Right Arm"]))   # 1.581
STRETCH = 0.5                                                            # how far an arm may slide toward a hand target
EASES = {"sine": "SINE", "quad": "QUAD", "cubic": "CUBIC", "quart": "QUART", "quint": "QUINT", "expo": "EXPO",
         "circ": "CIRC", "back": "BACK", "elastic": "ELASTIC", "bounce": "BOUNCE"}
EASE_DIR = {"in": "EASE_IN", "out": "EASE_OUT", "inout": "EASE_IN_OUT"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def stage(v):
    """stage (x right, y up from the floor, z forward) -> Blender world"""
    return np.array([float(v[0]), float(v[2]), float(v[1])])


def unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


def rot_axis(axis, deg):
    a = math.radians(deg)
    x, y, z = unit(np.asarray(axis, dtype=float))
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def arc(a, b):
    """the shortest rotation taking direction a to direction b"""
    a, b = unit(a), unit(b)
    v = np.cross(a, b)
    s, c = float(np.linalg.norm(v)), float(np.dot(a, b))
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        perp = unit(np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0]))
        return rot_axis(perp, 180.0)
    return rot_axis(v, math.degrees(math.atan2(s, c)))


def m4(R=None, t=None):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    if t is not None:
        M[:3, 3] = t
    return M


def about(pivot, R, move=None):
    """a rotation about a pivot, then a move (armature space, 4x4)"""
    move = np.zeros(3) if move is None else move
    return m4(None, pivot + move) @ m4(R) @ m4(None, -pivot)


def body_rot(b):
    """lean + = forward, turn + = to the character's right, tilt + = right shoulder down (Blender axes)"""
    return (rot_axis([0, 0, 1.0], -float(b.get("turn", 0))) @ rot_axis([1.0, 0, 0], -float(b.get("lean", 0)))
            @ rot_axis([0, 1.0, 0], float(b.get("tilt", 0))))


def grip_dir(pitch):
    """the blade at rest (arm hanging, Blender axes): out of the fist forward, turned down toward the arm by pitch"""
    a = math.radians(pitch)
    return np.array([0.0, math.cos(a), -math.sin(a)])


def blade_cone(h0, grip_pitch):
    """the fixed angle between an arm (pivot -> hand) and its blade: an R6 arm has no wrist"""
    g = grip_dir(grip_pitch)
    return math.acos(max(-1.0, min(1.0, float(np.dot(unit(h0), g)))))


def solve_arm(side, D_body, target, blade=None, grip_pitch=0.0, aim=None, lock="blade", edge=None):
    """an arm's torso-relative rotation and slide. With a blade and lock "blade" (the default): the blade points
    EXACTLY along blade, and the arm is the one on that blade's cone (the grip's fixed arm-blade angle) nearest the
    hand target - the blade is what reads, the hands follow it. Otherwise the hand aims at the target and the blade
    comes as close as the twist allows. With an edge too (a sword spec's "twist": "edge"), the twist is the best fit
    of BOTH the blade and the edge: a pistol held out points almost along the arm, so the blade alone barely decides
    the twist and the arm spun (GunSwitch's swing, 2026-10-26: 54 deg in one frame)"""
    Rb, piv = D_body[:3, :3], (D_body @ np.append(PIVOT[side], 1.0))[:3]
    h0 = HAND[side] - PIVOT[side]
    if aim is not None:
        want, dist = unit(aim), REACH
    else:
        v = target - piv
        dist = float(np.linalg.norm(v))
        want = unit(v)
    if blade is not None and lock == "blade":
        B = unit(blade)
        phi = blade_cone(h0, grip_pitch)
        side_dir = want - np.dot(want, B) * B
        if np.linalg.norm(side_dir) < 1e-6:
            side_dir = np.cross(B, [0, 0, 1.0]) if abs(B[2]) < 0.9 else np.cross(B, [1.0, 0, 0])
        want = unit(math.cos(phi) * B + math.sin(phi) * unit(side_dir))
        dist = float(np.dot(target - piv, want)) if target is not None else REACH
    R = arc(h0, want)
    err = None
    if blade is not None:
        g = R @ grip_dir(grip_pitch)
        u = g - np.dot(g, want) * want
        w = unit(blade) - np.dot(unit(blade), want) * want
        if edge is not None:
            # the fist's own edge: the one that reads "down" with the arm held straight forward
            e_ref = arc(h0, Rb @ stage([0, 0, 1.0])).T @ (Rb @ stage([0, -1.0, 0]))
            ue = R @ e_ref
            ue = ue - np.dot(ue, want) * want
            we = unit(edge) - np.dot(unit(edge), want) * want
            sn = float(np.dot(np.cross(u, w), want) + np.dot(np.cross(ue, we), want))
            cs = float(np.dot(u, w) + np.dot(ue, we))
            if abs(sn) + abs(cs) > 1e-9:
                R = rot_axis(want, math.degrees(math.atan2(sn, cs))) @ R
        elif np.linalg.norm(u) > 1e-6 and np.linalg.norm(w) > 1e-6:
            ang = math.degrees(math.atan2(float(np.dot(np.cross(u, w), want)), float(np.dot(u, w))))
            R = rot_axis(want, ang) @ R
        got = R @ grip_dir(grip_pitch)
        err = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(unit(got), unit(blade)))))))
    slide = want * min(max(dist - REACH, 0.0), STRETCH)
    gap = max(dist - REACH - STRETCH, 0.0)
    return Rb.T @ R, Rb.T @ slide, err, gap


def root_delta(k):
    """the whole character (the rig's Main Controller: body AND feet) turned about the vertical through the origin
    and moved; every stage target of the key is in this frame (a spin turns the root, the poses ride it)"""
    r = k.get("root") or {}
    return about(np.zeros(3), rot_axis([0, 0, 1.0], -float(r.get("turn", 0))), stage(r.get("pos", [0, 0, 0])))


def at_root(D_root, v):
    return (D_root @ np.append(stage(v), 1.0))[:3]


def head_rot(D_body, h, D_root=None):
    look = h.get("look")
    if look is None:
        return np.eye(3)
    d = unit((D_root[:3, :3] if D_root is not None else np.eye(3)) @ stage(look))
    yaw = math.degrees(math.atan2(-d[0], d[1]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, d[2]))))
    R = rot_axis([0, 0, 1.0], yaw) @ rot_axis([1.0, 0, 0], pitch) @ rot_axis([0, 1.0, 0], float(h.get("tilt", 0)))
    return D_body[:3, :3].T @ R


PLACEMENT = ("hand", "aim", "rot", "swing", "on_blade")   # how an arm is placed (one of them); "blade" and "lock" ride along


def held(a):
    """the left hand rides the sword every frame: "hilt" (spacing studs below the right fist) or {"on_blade": d}
    (d studs from the right fist along the blade: a palm braced on the flat for a block, a half-sword thrust)"""
    return a == "hilt" or (isinstance(a, dict) and "on_blade" in a)


def along(a, spacing):
    return -spacing if a == "hilt" else float(a["on_blade"])
SWING_FIELDS = ("swing", "out", "twist", "slide")


def limb_rot(side, l):
    """a limb's rotation from its joint, torso-relative (Blender axes): twist about its own (rest) axis first, then
    SWING (+ = forward / up, 90 = straight ahead), then OUT (+ = away from the body sideways, for either side)"""
    sign = 1.0 if side.startswith("Left") else -1.0
    return (rot_axis([0, 1.0, 0], sign * float(l.get("out", 0))) @ rot_axis([1.0, 0, 0], float(l.get("swing", 0)))
            @ rot_axis([0, 0, 1.0], float(l.get("twist", 0))))


def merged_keys(spec, fps):
    """every key with the fields it left out held from the key before; times in frames"""
    rest = {"root": {"pos": [0, 0, 0], "turn": 0},
            "body": {"pos": [0, 0, 0], "lean": 0, "turn": 0, "tilt": 0}, "head": {"look": [0, 0, 1], "tilt": 0},
            "right_arm": {"aim": [0.316, -0.949, 0]}, "left_arm": {"aim": [-0.316, -0.949, 0]},   # the R6 rest
            "right_foot": {"at": [0.5, 0], "lift": 0, "turn": 0}, "left_foot": {"at": [-0.5, 0], "lift": 0, "turn": 0},
            "right_leg": {"swing": 0, "out": 0, "twist": 0, "slide": [0, 0, 0]},
            "left_leg": {"swing": 0, "out": 0, "twist": 0, "slide": [0, 0, 0]},
            "ease": "bezier"}
    out, prev = [], rest
    for k in sorted(spec["keys"], key=lambda k: float(k["f"]) if "f" in k else float(k["t"]) * fps):
        cur = json.loads(json.dumps(prev))
        for field, value in k.items():
            if field in ("f", "t"):
                continue
            if isinstance(value, dict) and isinstance(cur.get(field), dict) and field in ("root", "body", "head", "right_foot", "left_foot", "right_leg", "left_leg"):
                cur[field].update(value)
            elif isinstance(value, dict) and isinstance(cur.get(field), dict) and field in ("right_arm", "left_arm"):
                if any(f in value for f in PLACEMENT):          # a new placement replaces the held one
                    for f in PLACEMENT + SWING_FIELDS:
                        cur[field].pop(f, None)
                cur[field].update(value)                          # a blade / lock alone keeps the held placement
            else:
                cur[field] = value
        for once in ("plant", "clear"):                   # per-key solves, never held to the next key
            if once not in (k.get("body") or {}):
                cur["body"].pop(once, None)
        cur["f"] = float(k["f"]) if "f" in k else float(k["t"]) * fps
        cur["_set"] = sorted(f for f in k if f not in ("f", "t", "ease"))   # what THIS key poses (others interpolate)
        out.append(cur)
        prev = cur
    return out


# per-AXIS offsets (the professional figure-8: the torso's lean, twist and tilt, and the head's, lag by different
# frames). Body and Head.001 then key euler channels in the order their poses are built (ZXY: tilt, lean, turn):
# Body local x = character LEFT (lean), y = up (turn), z = forward (tilt); Head.001 x = right (nod), y = up (turn), z = back
AXIS_CHANNELS = {"body.lean": ("Body", "rotation_euler", 0), "body.turn": ("Body", "rotation_euler", 1),
                 "body.tilt": ("Body", "rotation_euler", 2), "body.bob": ("Body", "location", 1),
                 "head.nod": ("Head.001", "rotation_euler", 0), "head.turn": ("Head.001", "rotation_euler", 1),
                 "head.tilt": ("Head.001", "rotation_euler", 2)}


def setup(arm, legs="ik", euler=()):
    """the legs' mode on the rig's own switch (IK: slider 2, FK box off; FK: slider 0, FK box on - as shipped), every
    controller a quaternion, a fresh action"""
    P = arm.pose.bones
    for side, sign in (("L", 1.0), ("R", -1.0)):
        sk = P.get(f"SoftIK.{side}")
        if sk is not None:
            sk["FK"] = legs != "ik"
            sk.location = Vector(((2.0 * sign) if legs == "ik" else 0.0, 0, 0))
    for name in CONTROLLERS + ["FKLeg.R", "FKLeg.L"]:
        pb = P[name]
        pb.rotation_mode = "ZXY" if name in euler else "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    if arm.animation_data is None:
        arm.animation_data_create()


def evaluate():
    """the rig has a driver cycle (SoftIK drives its own parent's IK influence): two updates settle it"""
    bpy.context.view_layer.update()
    bpy.context.view_layer.update()


def settle_switch(arm):
    """a CHANGE of the SoftIK slider / checkbox shows one evaluation late and repeated updates do not catch up: nudge
    the slider's z (clamped to 0 by the rig) and evaluate again (assets/rigs/R6_IK.md)"""
    P = arm.pose.bones
    evaluate()
    for side in ("SoftIK.L", "SoftIK.R"):
        P[side].location.z = 1e-5
    evaluate()
    for side in ("SoftIK.L", "SoftIK.R"):
        P[side].location.z = 0.0
    evaluate()


LEG_BOX = {"Right Leg": [np.array([0.5 + x, y, z]) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (0.0, 2.0)],
           "Left Leg": [np.array([-0.5 + x, y, z]) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (0.0, 2.0)]}


def lowest(arm, leg):
    D = delta(arm, leg)
    return min(float((D @ np.append(c, 1.0))[2]) for c in LEG_BOX[leg])


def delta(arm, name):
    pb, b = arm.pose.bones[name], arm.data.bones[name]
    return np.array(pb.matrix) @ np.linalg.inv(np.array(b.matrix_local))


def set_matrix(arm, name, M_delta):
    """a controller's armature-space delta from rest -> its pose (the parents' poses are read as evaluated)"""
    pb, b = arm.pose.bones[name], arm.data.bones[name]
    pb.matrix = Matrix((M_delta @ np.array(b.matrix_local)).tolist())
    evaluate()


def key_bone(arm, name, frame, prev_q):
    pb = arm.pose.bones[name]
    if pb.rotation_mode != "QUATERNION":                  # an axis-offset controller: euler channels, kept continuous
        e = pb.rotation_euler.copy()
        if prev_q.get(name) is not None:
            e.make_compatible(prev_q[name])
            pb.rotation_euler = e
        prev_q[name] = e.copy()
        pb.keyframe_insert("location", frame=frame)
        pb.keyframe_insert("rotation_euler", frame=frame)
        return
    q = pb.rotation_quaternion.copy()
    if prev_q.get(name) is not None and q.dot(prev_q[name]) < 0:      # the short way round between keys
        q.negate()
        pb.rotation_quaternion = q
    prev_q[name] = q.copy()
    pb.keyframe_insert("location", frame=frame)
    pb.keyframe_insert("rotation_quaternion", frame=frame)


def pose_key(arm, k, sword, legs="ik"):
    """one key pose onto the controllers (not the left arm when it holds the hilt); returns a report. With FK legs and
    body "plant" ("right" / "left" / "both"), the body height is solved so that leg's lowest point is ON the floor"""
    report = pose_key_once(arm, k, sword, legs)
    plant = k["body"].get("plant")
    if legs == "fk" and plant:
        sides = {"right": ["Right Leg"], "left": ["Left Leg"], "both": ["Right Leg", "Left Leg"]}[plant]
        clear = float(k["body"].get("clear", 0.0))       # a flight key: the legs' lowest point this far off the floor
        for _ in range(3):                                # the body moves the legs rigidly: one correction converges
            low = min(lowest(arm, leg) for leg in sides) - clear
            if abs(low) < 1e-4:
                break
            k = json.loads(json.dumps(k))
            pos = list(k["body"].get("pos", [0, 0, 0]))
            pos[1] = float(pos[1]) - low
            k["body"]["pos"] = pos
            report = pose_key_once(arm, k, sword, legs)
        report["body.planted_dy"] = round(float(k["body"]["pos"][1]), 3)
    return report


pending_grip = [None]
pending_edge = [None]
pending_toss = [None]


def blade_world(sword_ob, fallback):
    """the blade's world direction: the sword object's own +y (it may turn in the fist: an animated grip)"""
    if sword_ob is None:
        return fallback
    return unit(np.array(sword_ob.matrix_world)[:3, 1])


def turn_grip(sword_ob, want, edge=None):
    """turn the sword about the fist (its origin) so its blade points along want - the animated grip; with `edge` (a
    key's right_arm.edge) it also ROLLS about the blade until its edge (the object's -z: a pistol's grip, a sword's
    edge) faces that way - without it the roll is whatever the shortest turn leaves (a pistol canted with the arm)"""
    if sword_ob is None or (want is None and edge is None):
        return
    evaluate()
    M = np.array(sword_ob.matrix_world)
    cur = unit(M[:3, 1])
    if want is None:                                  # an edge alone: roll about the blade where it points now
        want = cur
    Q = arc(cur, unit(want))
    if edge is not None:
        y = unit(want)
        have = Q @ -M[:3, 2]
        have = have - y * float(np.dot(have, y))
        goal = np.asarray(edge, dtype=float) - y * float(np.dot(edge, y))
        if np.linalg.norm(have) > 1e-6 and np.linalg.norm(goal) > 1e-6:
            have, goal = unit(have), unit(goal)
            ang = math.degrees(math.atan2(float(np.dot(np.cross(have, goal), y)), float(np.dot(have, goal))))
            Q = rot_axis(y, ang) @ Q
    o = M[:3, 3]
    new = m4(None, o) @ m4(Q) @ m4(None, -o) @ M
    sword_ob.matrix_world = Matrix(new.tolist())
    evaluate()


def lock_grip(arm, sword_ob, lock):
    """THE WRIST-PLANE LOCK (LIMITATIONS_FIXES_V4 4.4 / 13.4.2): the weapon's turn in the fist keyed at EVERY frame the
    pose file's sword "lock" names - each its blade direction and edge (stage axes, root-relative), from the frame the
    arm is actually at. Keyed only where the right arm is keyed, the turn in the fist and the arm's own turn were
    interpolated apart, and the blade the bake drew left its source between the keys (the loved kesa through
    pose_from -> this rig: 15.6 degrees at frame 8, its left hand 0.14 studs off the hilt line there). The keys are
    straight lines frame to frame; the arm's keys are not touched -> the frames locked"""
    sc = bpy.context.scene
    prev = None
    done = []
    left = []                                                # (frame, the left arm controller's corrected delta)
    for e in lock:
        f = float(e["f"])
        sc.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
        evaluate()
        R_root = delta(arm, "Main Controller")[:3, :3]
        want = R_root @ stage(e["blade"])
        edge = R_root @ stage(e["edge"]) if e.get("edge") is not None else None
        turn_grip(sword_ob, want, edge)
        q = sword_ob.rotation_quaternion.copy()
        if prev is not None and q.dot(prev) < 0:             # (one hemisphere: the short way between two frames)
            q.negate()
            sword_ob.rotation_quaternion = q
        prev = q.copy()
        sword_ob.keyframe_insert("rotation_quaternion", frame=f)
        done.append(round(f, 3))
        if isinstance(e.get("left"), (int, float)) and not isinstance(e.get("left"), bool):
            # the LEFT HAND back on the line where the source had it ("left": studs from the right fist along the
            # blade): the arm its keys give, turned about its own (slid) shoulder by the least that takes the hand
            # there, and slid along the difference - read off the keys as they are, keyed after this pass
            fist = (delta(arm, "Right Arm") @ np.append(HAND["Right Arm"], 1.0))[:3]
            target = fist + unit(blade_world(sword_ob, want)) * float(e["left"])
            Dc = delta(arm, "Arm.L")
            piv = (Dc @ np.append(PIVOT["Left Arm"], 1.0))[:3]
            hand = (delta(arm, "Left Arm") @ np.append(HAND["Left Arm"], 1.0))[:3]
            if float(np.linalg.norm(hand - target)) > 1e-4:
                Q = arc(hand - piv, target - piv)
                D = m4(None, piv) @ m4(Q) @ m4(None, -piv) @ Dc
                gap = float(np.linalg.norm(target - piv) - np.linalg.norm(hand - piv))
                left.append((f, m4(None, gap * unit(target - piv)) @ D))
    prev_q = {}
    for f, D in left:
        sc.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
        evaluate()
        set_matrix(arm, "Arm.L", D)
        key_bone(arm, "Arm.L", f, prev_q)
    if left:
        for fc in controller_curves(arm, "Arm.L"):
            for kp in fc.keyframe_points:
                if left[0][0] - 1e-6 <= float(kp.co[0]) <= left[-1][0] + 1e-6:
                    kp.interpolation = "LINEAR"
            fc.update()
    ad = sword_ob.animation_data
    try:
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        bag = action_get_channelbag_for_slot(ad.action, ad.action_slot)
        curves = list(bag.fcurves) if bag else []
    except Exception:  # noqa: BLE001  (older API)
        curves = list(ad.action.fcurves)
    lo, hi = (min(done), max(done)) if done else (0.0, -1.0)
    for fc in curves:
        if fc.data_path == "rotation_quaternion":
            for kp in fc.keyframe_points:
                if lo - 1e-6 <= float(kp.co[0]) <= hi + 1e-6:
                    kp.interpolation = "LINEAR"
            fc.update()
    return done


def pose_key_once(arm, k, sword, legs="ik"):
    b = k["body"]
    D_root = root_delta(k)
    set_matrix(arm, "Main Controller", D_root)
    D_body = D_root @ about(PIVOT["Torso"], body_rot(b), stage(b.get("pos", [0, 0, 0])))
    set_matrix(arm, "Body", D_body)
    D_body = delta(arm, "Body")
    report = {}
    R = head_rot(D_body, k["head"], D_root)
    set_matrix(arm, "Head.001", D_body @ about(PIVOT["Head"], R))
    gp = float(sword.get("grip_pitch", 0)) if sword else 0.0
    for side, field, ctrl in (("Right Arm", "right_arm", "Arm.R"), ("Left Arm", "left_arm", "Arm.L")):
        a = k[field]
        if held(a):
            continue
        if isinstance(a, dict) and "swing" in a:          # a limb swing (torso-relative), with a slide
            Rr, slide = limb_rot(side, a), stage(a.get("slide", [0, 0, 0]))
        elif isinstance(a, dict) and "rot" in a:
            Rr, slide = C.euler_mat(tuple(float(v) for v in a["rot"])), np.zeros(3)
            Rr = P3 @ Rr @ P3.T
        else:
            target = at_root(D_root, a["hand"]) if "hand" in a else None
            aim = D_root[:3, :3] @ stage(a["aim"]) if "aim" in a and target is None else None
            blade = D_root[:3, :3] @ stage(a["blade"]) if (side == "Right Arm" and sword and "blade" in a) else None
            grip_anim = side == "Right Arm" and sword is not None and str(sword.get("grip", "")) == "animated"
            lock = "hand" if grip_anim else str(a.get("lock", "blade"))
            # the ARM's roll follows the weapon's edge ("twist": "edge") - or a key's own "arm_edge": a gun twirled in the
            # fist must not roll the whole arm with it (GunTwirlR, 2026-10-26: the arm sank 31% into the chest)
            arm_edge = a.get("arm_edge", a.get("edge"))
            edge = (D_root[:3, :3] @ stage(arm_edge) if blade is not None and arm_edge is not None
                    and str(sword.get("twist", "")) == "edge" else None)
            # "arm_twist": false - the arm takes its natural swing (as a hand-only arm does) while the weapon still turns
            # in the fist from this key's blade / edge (Sample Game's hip holsters, 2026-10-27: a gun hanging ALONG the
            # arm made the twist fit degenerate - the arm flipped ~100 deg a frame and sank 0.3-0.47 into the torso)
            no_twist = grip_anim and a.get("arm_twist") is False
            Rr, slide, err, gap = solve_arm(side, D_body, target, None if no_twist else blade, gp, aim, lock,
                                            None if no_twist else edge)
            if grip_anim:
                report[f"{field}.grip_turn_deg"] = round(err or 0.0, 1)
                err = 0.0                                 # the sword turns in the fist to the blade (keyed below)
            if err is not None and err > 0.5:
                report[f"{field}.blade_err_deg"] = round(err, 1)
            if target is not None:
                landed = (D_body @ np.append(PIVOT[side], 1.0))[:3] + D_body[:3, :3] @ (slide + Rr @ (HAND[side] - PIVOT[side]))
                off = float(np.linalg.norm(landed - target))
                if off > 0.25:
                    report[f"{field}.hand_off"] = round(off, 2)
            if gap > 0.05:
                report[f"{field}.hand_short_by"] = round(gap, 2)
        set_matrix(arm, ctrl, D_body @ about(PIVOT[side], Rr, slide))
        if side == "Right Arm" and sword is not None and str(sword.get("grip", "")) == "animated" and isinstance(a, dict):
            pending_grip[0] = D_root[:3, :3] @ stage(a["blade"]) if "blade" in a else None
            pending_edge[0] = D_root[:3, :3] @ stage(a["edge"]) if "edge" in a else None
            pending_toss[0] = D_root[:3, :3] @ stage(a["toss"]) if "toss" in a else None
    if legs == "fk":                                      # the FK legs swing from the hips, carried by the body
        for side, field, ctrl in (("Right Leg", "right_leg", "FKLeg.R"), ("Left Leg", "left_leg", "FKLeg.L")):
            l = k[field]
            set_matrix(arm, ctrl, D_body @ about(PIVOT[side], limb_rot(side, l), stage(l.get("slide", [0, 0, 0]))))
        return report
    for field, ctrl in (("right_foot", "Foot.R"), ("left_foot", "Foot.L")):
        f = k[field]
        at = np.array([float(f["at"][0]), float(f["at"][1]), float(f.get("lift", 0))])
        R = rot_axis([0, 0, 1.0], -float(f.get("turn", 0)))
        set_matrix(arm, ctrl, D_root @ about(FOOT_REST[ctrl], R, at - FOOT_REST[ctrl]))
    return report


def set_easing(arm, frames_ease):
    ad = arm.animation_data
    try:
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        bag = action_get_channelbag_for_slot(ad.action, ad.action_slot)
        curves = list(bag.fcurves) if bag else []
    except Exception:  # noqa: BLE001  (older API)
        curves = list(ad.action.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            ease = frames_ease.get(round(float(kp.co[0]), 3))
            if ease is None:                     # a per-frame key (the left hand on the hilt): straight lines
                kp.interpolation = "LINEAR"
                continue
            kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
            if ease == "bezier":
                kp.interpolation = "BEZIER"
            elif ease in ("linear", "constant"):
                kp.interpolation = ease.upper()
            else:
                kind, _, way = ease.partition("_")
                kp.interpolation = EASES.get(kind, "BEZIER")
                if kp.interpolation != "BEZIER":
                    kp.easing = EASE_DIR.get(way, "AUTO")
        fc.update()


def weapon_easing(sword_ob, frames_ease):
    """the animated grip's turn between keys: every quaternion component on the SAME eased curve, so the turn stays on
    the short arc - Blender's auto-bezier handles bend each component through its neighbours (GunReload's roll
    wobbled 23 -> 9 -> 38 deg into a 40 deg key and overshot to 59 past one), and back / elastic / bounce would throw
    the weapon past its key (a hand's slam bounce is not a gun's spin): those turn as sine"""
    ad = sword_ob.animation_data
    if ad is None or ad.action is None:
        return
    try:
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        bag = action_get_channelbag_for_slot(ad.action, ad.action_slot)
        curves = list(bag.fcurves) if bag else []
    except Exception:  # noqa: BLE001  (older API)
        curves = list(ad.action.fcurves)
    for fc in curves:
        if fc.data_path != "rotation_quaternion":
            continue
        for kp in fc.keyframe_points:
            ease = frames_ease.get(round(float(kp.co[0]), 3), "bezier")
            kind, _, way = ease.partition("_")
            if ease in ("linear", "constant"):
                kp.interpolation = ease.upper()
                continue
            kp.interpolation = "SINE" if ease == "bezier" or kind in ("back", "elastic", "bounce") else EASES.get(kind, "SINE")
            kp.easing = EASE_DIR.get(way, "EASE_IN_OUT")
        fc.update()


def gun_mode(k):
    g = k.get("gun")
    return str(g.get("mode", "right")) if isinstance(g, dict) else "right"


def weapon_frame(at, blade, edge):
    """a weapon pose (Blender world 4x4) from a key's stage numbers: origin `at` (where the fist would hold it - the
    pistol's `hold` is added on top), +y along `blade`, the edge (-z) toward `edge`"""
    y = unit(stage(blade))
    e = stage(edge)
    e = e - y * float(np.dot(e, y))
    z = -unit(e) if np.linalg.norm(e) > 1e-6 else unit(np.cross([1.0, 0, 0], y))
    x = unit(np.cross(y, z))
    z = np.cross(x, y)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = x, y, z, stage(at)
    return M


def _quat(R):
    """a 3x3 rotation -> a unit quaternion (w, x, y, z)"""
    t = R[0, 0] + R[1, 1] + R[2, 2]
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = [(R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s]
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = [(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = [(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s]
    q = np.array(q, float)
    return q / np.linalg.norm(q)


def _quat_matrix(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _slerp_pose(A, B, u):
    """position lerp + rotation slerp (the short way, one hemisphere) between two 4x4 poses; a scale on either (an
    object scaled in Blender) is taken off before the turn is read and blended back on after"""
    sa, sb = np.linalg.norm(A[:3, :3], axis=0), np.linalg.norm(B[:3, :3], axis=0)
    qa, qb = _quat(A[:3, :3] / sa), _quat(B[:3, :3] / sb)
    d = float(np.dot(qa, qb))
    if d < 0:
        qb, d = -qb, -d
    if d > 0.9995:
        q = qa + (qb - qa) * u
    else:
        th = math.acos(min(1.0, d))
        q = (math.sin((1 - u) * th) * qa + math.sin(u * th) * qb) / math.sin(th)
    M = np.eye(4)
    M[:3, :3] = _quat_matrix(q / np.linalg.norm(q)) * (sa * (1 - u) + sb * u)
    M[:3, 3] = A[:3, 3] * (1 - u) + B[:3, 3] * u
    return M


def grip_keyed(k, keys):
    """whether key k keys the weapon's turn in the hand: where it sets the right arm or the weapon's mode (the weapon
    track takes over there: unkeyed, the frame before it blended toward a later key's turn), and at the ends (a key
    with no "_set" record keys it, as before)"""
    st = k.get("_set", ["right_arm"])
    return k is keys[0] or k is keys[-1] or "right_arm" in st or "gun" in st


def weapon_keys(keys):
    """the keys that SAY where the weapon is (a "gun" field) - the weapon's mode holds until one of them changes it. An
    arm-only key in a flight (the catching hand reaching out) read as "back in the right hand" cut the flight short:
    the gun hung in the air, then dropped into the fist in one frame (GunSwitch's hand-back, owner 2026-10-26: "it
    kind of cuts off in a weird way where the gun just ... goes under")"""
    out = []
    prev_f = None                                     # the frame of the key just before (any key)
    for k in keys:
        g = k.get("gun")
        # held keys (merged_keys carries every field forward, and records what the author set in "_set") repeat the
        # last "gun": a held copy is not a new weapon key (it pinned the weapon to the earlier pose, then it jumped to
        # the hand in one frame). An author's own repeat stays (a deliberate hold); with no "_set", equality decides.
        own = ("gun" in k["_set"]) if "_set" in k else not (out and out[-1].get("gun") == g)
        if isinstance(g, dict) and own:
            # a straight hand -> posed flight: the hand keeps the weapon up to the key before the throw (dropping the
            # arm-only keys between, it drifted out of the fist from the stretch's start)
            if (gun_mode(k) == "free" and "at" in g and out and gun_mode(out[-1]) == "right"
                    and prev_f is not None and prev_f > out[-1]["f"]):
                out.append({"f": prev_f, "gun": {"mode": "right"}})
            out.append(k)
        prev_f = k["f"]
    if not out or out[0]["f"] > 0:
        out = [{"f": 0, "gun": {"mode": "right"}}] + out
    return out


def _axis_rot(axis, ang):
    x, y, z = unit(np.asarray(axis, float))
    c, s, t = math.cos(ang), math.sin(ang), 1 - math.cos(ang)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def throw_pose(A, B, u, T, g, cen, spin_axis=(1.0, 0.0, 0.0), turns=0.0, up=(0.0, 0.0, 1.0)):
    """the weapon THROWN from pose A to pose B in T seconds (u = 0..1 through the flight), as a real throw reads:
    its centre (`cen`, in the weapon's own frame, studs) flies a ballistic arc under gravity `g` (studs/s^2 along
    -`up`), it spins at a CONSTANT rate - `turns` extra full turns about `spin_axis` (its own frame) on top of the
    shortest turn from A's attitude to B's - and it lands exactly on B. (Owner 2026-10-26: a gun keyed through points
    and pulled into the hand "looks like the gun is jumping ... throw it in the air and then catch it".)"""
    sa, sb = np.linalg.norm(A[:3, :3], axis=0), np.linalg.norm(B[:3, :3], axis=0)
    RA, RB = A[:3, :3] / sa, B[:3, :3] / sb
    cen = np.asarray(cen, float)
    cA, cB = A[:3, 3] + RA @ cen, B[:3, 3] + RB @ cen
    gv = -g * unit(np.asarray(up, float))
    v0 = (cB - cA - 0.5 * gv * T * T) / T
    t = u * T
    c = cA + v0 * t + 0.5 * gv * t * t
    I4, Rel = np.eye(4), np.eye(4)
    Rel[:3, :3] = RA.T @ RB
    R = RA @ _axis_rot(spin_axis, 2 * math.pi * turns * u) @ _slerp_pose(I4, Rel, u)[:3, :3]
    M = np.eye(4)
    M[:3, :3] = R * (sa * (1 - u) + sb * u)
    M[:3, 3] = c - R @ cen
    return M


def throw_speeds(A, B, T, g, cen, up=(0.0, 0.0, 1.0)):
    """the centre's velocity leaving A and arriving at B (studs/s) - what the throwing and catching hands must match"""
    RA, RB = A[:3, :3] / np.linalg.norm(A[:3, :3], axis=0), B[:3, :3] / np.linalg.norm(B[:3, :3], axis=0)
    cen = np.asarray(cen, float)
    gv = -g * unit(np.asarray(up, float))
    v0 = (B[:3, 3] + RB @ cen - A[:3, 3] - RA @ cen - 0.5 * gv * T * T) / T
    return v0, v0 + gv * T


def ride(fist_f, fist0, fist1, A, B, u):
    """the weapon RIDING a moving fist (the "rhand" mode): A (at fist0) and B (at fist1) are taken into the fist's own
    frame, interpolated there, and carried by the fist where it is now (fist_f) - the arm moves the weapon"""
    return fist_f @ _slerp_pose(np.linalg.inv(fist0) @ A, np.linalg.inv(fist1) @ B, u)


def weapon_track(arm, sword_ob, keys, f_end):
    """THE WEAPON OFF THE HAND (Sample Game's switcharoo / coin flick / finger spins, 2026-10-26). A key's "gun" sets
    where the weapon is, held until a key changes it:
      {"mode": "right"}                         in the right fist (the animated grip: blade / edge / toss keys)
      {"mode": "free", "at": [x,y,z], "blade": [..], "edge": [..]}   flying its own path in stage space
      {"mode": "left", "at": .., "blade": .., "edge": ..}   CAUGHT by the left fist at this key's pose, then rigid to it
      {"mode": "rhand", "at": .., "blade": .., "edge": ..}  RIDING the right fist off the grip (a finger spin): the
                                                pose is stored in the fist's own frame and interpolated there, so the
                                                arm carries the weapon every frame (owner 2026-10-26: "it looks like
                                                the gun is moving by itself. Who's moving it? A ghost?"); no "at" =
                                                where the weapon is at that key (it leaves the grip from there)
    Every frame of a free / left / rhand stretch is keyed: positions lerp (smoothstep, or straight for an "ease":
    "linear" key), turns slerp (one hemisphere); a stretch's ends meet the right hand's own pose where it hands over.
    -> frames keyed"""
    if not any(gun_mode(k) != "right" for k in keys):
        return 0
    keys = weapon_keys(keys)
    sc = bpy.context.scene
    rest = {s: np.array(arm.data.bones[s].matrix_local) for s in ("Left Arm", "Right Arm")}

    def fist(side, f):
        D = np.array(arm.pose.bones[side].matrix) @ np.linalg.inv(rest[side])
        M = np.eye(4)
        M[:3, :3] = D[:3, :3]
        M[:3, 3] = (D @ np.append(HAND[side], 1.0))[:3]
        return np.array(arm.matrix_world) @ M

    # 1: where the right hand alone puts the weapon on every frame (before anything below rewrites it)
    right_pose = {}
    fists = {}
    rfists = {}
    for f in range(0, f_end + 1):
        sc.frame_set(f)
        evaluate()
        right_pose[f] = np.array(sword_ob.matrix_world)
        fists[f] = fist("Left Arm", f)
        rfists[f] = fist("Right Arm", f)
    # 2: each key's own pose where it has one; the left grip's rigid offset from its catch key
    key_pose = {}
    for i, k in enumerate(keys):
        g = k.get("gun")
        if isinstance(g, dict) and gun_mode(k) != "right" and "at" in g:
            key_pose[i] = weapon_frame(g["at"], g.get("blade", [0, 0, 1]), g.get("edge", [0, -1, 0]))
            if gun_mode(k) == "left" and (i == 0 or gun_mode(keys[i - 1]) != "left"):
                # a CATCH lands in the left fist where the rig really put it (a target out of reach left the gun
                # hanging off the fist on a lever: every small turn of the arm swung it - a ghost)
                key_pose[i][:3, 3] = fists[int(round(k["f"]))][:3, 3]
    target = {}
    held_L = None
    # frame -> where the weapon IS at a stretch's first frame: the end the stretch before reached there (its B, or the
    # left fist's grip carried to that frame); a stretch after the right hand starts from the right hand's own pose.
    # (Taken from the frame before, one frame of hand travel stayed baked into a riding stretch: the gun slipped.)
    ends = {}
    for f in range(0, f_end + 1):
        j = max([i for i, k in enumerate(keys) if k["f"] <= f] or [0])
        j1 = min(j + 1, len(keys) - 1)
        mj, mj1 = gun_mode(keys[j]), gun_mode(keys[j1])
        if mj == "left":
            if held_L is None or (int(round(keys[j]["f"])) == f and j in key_pose):
                kf = int(round(keys[j]["f"]))
                start = key_pose.get(j, ends.get(kf, right_pose[kf]))
                held_L = np.linalg.inv(fists[kf]) @ start
            target[f] = fists[f] @ held_L
            continue
        if held_L is not None:
            ends.setdefault(f, fists[f] @ held_L)     # the left hand lets go here: the next stretch starts from it
        held_L = None
        if mj == "throw":
            # THROWN (a ballistic arc, a constant spin) from where the weapon is at this key to where the next key
            # puts it: the right hand's grip, the left fist's catch pose, or a riding / free pose
            g_ = keys[j]["gun"]
            f0, f1 = int(round(keys[j]["f"])), int(round(keys[j1]["f"]))
            A = ends.get(f0, right_pose[f0])
            if mj1 == "right":
                B = right_pose[f1]
            elif mj1 == "left":
                B = key_pose.get(j1, fists[f1] @ (np.linalg.inv(fists[f0]) @ A))
            elif mj1 == "rhand":
                B = key_pose.get(j1, rfists[f1] @ (np.linalg.inv(rfists[f0]) @ A))
            else:
                B = key_pose.get(j1, A)                   # a throw / free key with no pose of its own: lands where it left
            if j1 == j or f1 <= f0:
                target[f] = A                             # (a throw must be caught: a last key holds it where it left)
                continue
            ends.setdefault(f1, B)
            T = (f1 - f0) / (float(sc.render.fps) / float(sc.render.fps_base))
            turns = float(round(float(g_.get("turns", 0.0))))   # whole turns only: a part-turn would miss B
            target[f] = throw_pose(A, B, (f - f0) / (f1 - f0), T, float(g_.get("g", 35.0)),
                                   [0.0] + [float(x) for x in g_.get("pivot", [0.0, 0.0])],
                                   g_.get("axis", [1.0, 0.0, 0.0]), turns, stage([0, 1, 0]))
            continue
        if mj == "rhand":
            # riding the right fist: both ends in the fist's frame, interpolated there, then carried by the fist
            f0, f1 = int(round(keys[j]["f"])), int(round(keys[j1]["f"]))
            A = key_pose.get(j, ends.get(f0, right_pose[f0]))
            if j1 == j or f1 <= f0:
                target[f] = ride(rfists[f], rfists[f0], rfists[f0], A, A, 0.0)
                continue
            if mj1 == "right":
                B = right_pose[f1]
            elif mj1 == "left":
                B = key_pose.get(j1, fists[f1] @ (np.linalg.inv(fists[f0]) @ A))
            else:
                B = key_pose.get(j1, rfists[f1] @ (np.linalg.inv(rfists[f0]) @ A))
            ends.setdefault(f1, B)
            u = (f - f0) / (f1 - f0)
            if str(keys[j].get("ease", "bezier")).lower() != "linear":
                u = u * u * (3 - 2 * u)
            target[f] = ride(rfists[f], rfists[f0], rfists[f1], A, B, u)
            continue
        if mj != "free" and not (mj1 == "free" and j1 in key_pose):
            continue                                  # the right hand's own keys play (a left -> right hand-back
                                                      # stretch is the key BEFORE: a "free" key in between); a free
                                                      # key with no pose is a RELEASE: the hand holds the weapon up
                                                      # to it (interpolated pose -> same pose froze the gun mid-throw)
        f0, f1 = int(round(keys[j]["f"])), int(round(keys[j1]["f"]))
        A = key_pose.get(j) if mj == "free" else None
        if A is None:
            # a free key with no pose of its own starts where the weapon IS (out of the left hand, off a riding fist,
            # mid-flight) - not the right hand's grip (GunSwitch's hand-back jumped hands in one frame)
            A = ends.get(f0, right_pose[f0])
        if mj1 == "free":
            B = key_pose.get(j1, A)
        elif mj1 == "rhand":
            B = key_pose.get(j1, right_pose[f1])
        elif mj1 == "left":
            B = key_pose.get(j1, fists[f1] @ (np.linalg.inv(fists[f0]) @ A))
        else:
            B = right_pose[f1]
        if j1 == j or f1 <= f0:
            target[f] = A
            continue
        ends.setdefault(f1, B)
        u = (f - f0) / (f1 - f0)
        if str(keys[j].get("ease", "bezier")).lower() != "linear":
            u = u * u * (3 - 2 * u)
        target[f] = _slerp_pose(A, B, u)
    # 3: key them (straight lines between per-frame keys, one quaternion hemisphere)
    prev = None
    keyed = sorted(target)
    for f in keyed:
        if f > 0 and (f - 1) not in target:
            # a stretch starts: its first key goes on the hemisphere of the hand's own key just before (compared only
            # with the stretch's own keys, the frame between blended q into -q: GunTrick's twirl, 2026-10-26)
            sc.frame_set(f - 1)
            evaluate()
            prev = sword_ob.rotation_quaternion.copy()
        sc.frame_set(f)
        evaluate()
        sword_ob.matrix_world = Matrix(target[f].tolist())
        q = sword_ob.rotation_quaternion.copy()
        if prev is not None and q.dot(prev) < 0:
            q.negate()
            sword_ob.rotation_quaternion = q
        prev = q.copy()
        sword_ob.keyframe_insert("location", frame=f)
        sword_ob.keyframe_insert("rotation_quaternion", frame=f)
    ad = sword_ob.animation_data
    try:
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        bag = action_get_channelbag_for_slot(ad.action, ad.action_slot)
        curves = list(bag.fcurves) if bag else []
    except Exception:  # noqa: BLE001  (older API)
        curves = list(ad.action.fcurves)
    fs = set(keyed)
    for fc in curves:
        for kp in fc.keyframe_points:
            if int(round(kp.co[0])) in fs:
                kp.interpolation = "LINEAR"
        fc.update()
    return len(keyed)


CONTROLLER_FIELDS = {"Main Controller": ("root",), "Body": ("body",), "Head.001": ("head",),
                     "Arm.R": ("right_arm",), "Arm.L": ("left_arm",), "Foot.R": ("right_foot",), "Foot.L": ("left_foot",),
                     "FKLeg.R": ("right_leg",), "FKLeg.L": ("left_leg",)}
OFFSET_GROUPS = {"arms": ["Arm.R", "Arm.L"], "right_arm": ["Arm.R"], "left_arm": ["Arm.L"], "head": ["Head.001"],
                 "legs": ["FKLeg.R", "FKLeg.L"], "body": ["Body"], "feet": ["Foot.R", "Foot.L"]}


def controller_curves(arm, name):
    ad = arm.animation_data
    from bpy_extras.anim_utils import action_get_channelbag_for_slot
    bag = action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return [fc for fc in (bag.fcurves if bag else []) if fc.data_path.startswith(f'pose.bones["{name}"]')]


def apply_offsets(arm, offsets, legs, loop, f0, f1):
    """shift a group's keys `frames` later (the drag hierarchy). A loop's shifted curves repeat (a Cycles modifier over
    the key range), so the seam stays exact and Blender plays what the bake reads; a one-shot holds its first key."""
    done = {}
    for group, frames in offsets.items():
        if group in AXIS_CHANNELS:                        # one channel of one controller
            name, path, index = AXIS_CHANNELS[group]
            for fc in controller_curves(arm, name):
                if fc.data_path.endswith(path) and fc.array_index == index:
                    for kp in fc.keyframe_points:
                        kp.co.x += float(frames)
                        kp.handle_left.x += float(frames)
                        kp.handle_right.x += float(frames)
                    if loop and not any(m.type == "CYCLES" for m in fc.modifiers):
                        fc.modifiers.new("CYCLES")
                    fc.update()
                    done[group] = float(frames)
            continue
        names = OFFSET_GROUPS.get(group, [group])
        for name in names:
            if legs == "fk" and name.startswith("Foot."):
                continue
            if legs != "fk" and name.startswith("FKLeg."):
                continue
            curves = controller_curves(arm, name)
            for fc in curves:
                for kp in fc.keyframe_points:
                    kp.co.x += float(frames)
                    kp.handle_left.x += float(frames)
                    kp.handle_right.x += float(frames)
                if loop and not any(m.type == "CYCLES" for m in fc.modifiers):
                    fc.modifiers.new("CYCLES")
                fc.update()
            if curves:
                done[name] = float(frames)
    evaluate()
    return done


def left_on_hilt(arm, keys, sword, f_end):
    """the left arm keyed every frame: on the hilt where its keys say "hilt", blended to its own keyed pose elsewhere"""
    sc = bpy.context.scene
    spacing = float(sword.get("spacing", 0.75)) if sword else 0.75
    gp = float(sword.get("grip_pitch", 0)) if sword else 0.0
    explicit = {}
    for i, k in enumerate(keys):              # the left arm's own key values (torso-relative), where it has one
        if not held(k["left_arm"]):
            sc.frame_set(int(k["f"]))
            evaluate()
            D_body = delta(arm, "Body")
            a = k["left_arm"]
            D_root = root_delta(k)
            if "rot" in a:
                R, s = P3 @ C.euler_mat(tuple(float(v) for v in a["rot"])) @ P3.T, np.zeros(3)
            elif "swing" in a:                    # a torso-relative swing (an off-hand let go of the hilt)
                R, s = limb_rot("Left Arm", a), stage(a.get("slide", [0, 0, 0]))
            else:
                R, s, _, _ = solve_arm("Left Arm", D_body, at_root(D_root, a["hand"]) if "hand" in a else None, None, 0.0,
                                       D_root[:3, :3] @ stage(a["aim"]) if "aim" in a and "hand" not in a else None)
            explicit[i] = (R, s)
    worst_gap, prev_q = 0.0, {}
    for f in range(0, f_end + 1):
        sc.frame_set(f)
        evaluate()
        D_body = delta(arm, "Body")
        j = max([i for i, k in enumerate(keys) if k["f"] <= f] or [0])
        j1 = min(j + 1, len(keys) - 1)
        u = 0.0 if j1 == j else (f - keys[j]["f"]) / max(keys[j1]["f"] - keys[j]["f"], 1e-9)
        u = min(1.0, max(0.0, u))
        u = u * u * (3 - 2 * u)
        need_hilt = held(keys[j]["left_arm"]) or held(keys[j1]["left_arm"])
        if not need_hilt:                     # both ends keyed by the author: Blender's own keys and easing play
            continue
        if need_hilt:
            D_ra = delta(arm, "Right Arm")
            hand = (D_ra @ np.append(HAND["Right Arm"], 1.0))[:3]
            blade = blade_world(bpy.data.objects.get("Greatsword"), D_ra[:3, :3] @ grip_dir(gp))
        ends = []
        for idx in (j, j1):
            if held(keys[idx]["left_arm"]):
                Rh, sh, _, gap = solve_arm("Left Arm", D_body, hand + unit(blade) * along(keys[idx]["left_arm"], spacing))
                worst_gap = max(worst_gap, gap)
                ends.append((Rh, sh))
            else:
                ends.append(explicit[idx])
        qa = Quaternion(Matrix(ends[0][0].tolist()).to_quaternion())
        qb = Quaternion(Matrix(ends[1][0].tolist()).to_quaternion())
        R = np.array(qa.slerp(qb, u).to_matrix())
        s = ends[0][1] * (1 - u) + ends[1][1] * u
        set_matrix(arm, "Arm.L", D_body @ about(PIVOT["Left Arm"], R, s))
        key_bone(arm, "Arm.L", f, prev_q)
    return worst_gap


def add_sword(arm, sword):
    """a greatsword in the right fist (child of the Right Arm part): guard just over the hand, a two-hand grip below"""
    blade, gp = float(sword.get("blade", 4.2)), float(sword.get("grip_pitch", 0))
    verts, faces = [], []

    def box(x0, x1, y0, y1, z0, z1):
        b = len(verts)
        verts.extend([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
        faces.extend([(b, b + 1, b + 2, b + 3), (b + 4, b + 7, b + 6, b + 5), (b, b + 4, b + 5, b + 1), (b + 1, b + 5, b + 6, b + 2),
                      (b + 2, b + 6, b + 7, b + 3), (b + 3, b + 7, b + 4, b)])

    # local: origin at the right fist, +y along the blade, the blade's width along z (the edge faces where the fist's
    # knuckles point), thickness along x
    if str(sword.get("kind", "")) == "pistol":
        # a PISTOL (Sample Game's Pearl, 2026-10-25; measured off its mesh at the game's half scale): the barrel along
        # +y, the slide over the grip, the grip hanging toward -z (the "edge" a key aims). `hold` = [up, forward]
        # studs from the fist to the grip point: an R6 arm is a 1-stud block, so a pistol AT the fist hides inside the
        # arm's end in first person - sample() bakes the offset into the grip path, so the game's Handle Transform
        # carries it (the Handle part sits at the gun's grip, C1 identity)
        # `scale` = the game's Config.R6Weapons.Gun.Scale (the mesh's own numbers, measured off its vertices, times it)
        up, fwd = (float(v) for v in (sword.get("hold") or [0.0, 0.0]))
        s = float(sword.get("scale", 0.5))
        box(-0.18 * s, 0.18 * s, fwd - 0.315 * s, fwd + 0.31 * s, up - 0.42 * s, up + 0.4 * s)    # grip
        box(-0.19 * s, 0.19 * s, fwd - 0.315 * s, fwd + 2.175 * s, up + 0.4 * s, up + 0.87 * s)   # slide + barrel
        box(-0.06 * s, 0.06 * s, fwd + 0.31 * s, fwd + 0.83 * s, up - 0.04 * s, up + 0.4 * s)     # trigger guard
        sections = []
    elif str(sword.get("kind", "")) == "katana":
        # a KATANA (the owner's katana set, 2026-10-18 - a blocking file showed a greatsword): a narrow STRAIGHT blade
        # (the curve read as 'bent'), a small round-ish tsuba, a wrapped tsuka for a close two-hand grip
        box(-0.06, 0.06, -0.62, 0.08, -0.045, 0.045)  # tsuka
        box(-0.035, 0.035, 0.08, 0.14, -0.2, 0.2)     # tsuba
        box(-0.2, 0.2, 0.08, 0.14, -0.035, 0.035)
        sections = [(0.14, 0.085, 0.03), (blade - 0.2, 0.085, 0.03), (blade + 0.1, 0.05, 0.02), (blade + 0.36, 0.0, 0.0)]
    else:
        # a GREATSWORD reads at R6 scale (arms 1 stud thick): a broad blade, a heavy guard, a long two-hand grip
        box(-0.13, 0.13, -1.15, -0.88, -0.15, 0.15)   # pommel
        box(-0.09, 0.09, -0.9, 0.2, -0.09, 0.09)      # grip (two hands)
        box(-0.14, 0.14, 0.2, 0.4, -0.8, 0.8)         # cross guard
        sections = [(0.4, 0.46, 0.11), (1.0, 0.48, 0.11), (blade - 1.0, 0.42, 0.09), (blade - 0.3, 0.26, 0.06), (blade + 0.36, 0.0, 0.0)]
    ring = None
    for y, w, t in sections:
        b0 = len(verts)
        verts.extend([(0.0, y, -w), (t, y, 0.0), (0.0, y, w), (-t, y, 0.0)])
        if ring is not None:
            for q in range(4):
                faces.append((ring + q, ring + (q + 1) % 4, b0 + (q + 1) % 4, b0 + q))
        ring = b0
    mesh = bpy.data.meshes.new("Greatsword")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new("Greatsword", mesh)
    ob["kit_blade"], ob["kit_spacing"], ob["kit_grip_pitch"] = blade, float(sword.get("spacing", 0.75)), gp
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("Greatsword")
    mat.diffuse_color = (0.86, 0.88, 0.93, 1.0)      # bright steel: it must read against the floor in any look
    mat.roughness = 0.35
    mat.metallic = 0.0
    mesh.materials.append(mat)
    evaluate()                                        # the rest pose; parent with the world placement kept
    rest_world = m4(rot_axis([1.0, 0, 0], -gp), HAND["Right Arm"])
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = "Right Arm"
    evaluate()
    ob.matrix_world = Matrix(rest_world.tolist())
    evaluate()
    return ob


def sample(arm, f_end, fps, sword_ob, sword):
    """per frame: the R6 joint transforms (the engine's) off the evaluated deform bones + the sword path"""
    sc = bpy.context.scene
    rest = {n: np.array(arm.data.bones[n].matrix_local) for n in PARTS}
    parent = {n: (arm.data.bones[n].parent.name if arm.data.bones[n].parent else None) for n in PARTS}
    frames = {n: [] for n in PARTS if n != "HumanoidRootPart"}
    times, tips, grips, centres, rots, grip_q, edges = [], [], [], [], [], [], []
    blade = float(sword.get("blade", 4.2)) if sword else 0.0
    spacing = float(sword.get("spacing", 0.75)) if sword else 0.75
    gp = float(sword.get("grip_pitch", 0)) if sword else 0.0
    for f in range(0, f_end + 1):
        sc.frame_set(f)
        evaluate()
        pose = {n: np.array(arm.pose.bones[n].matrix) for n in PARTS}
        dl = {n: pose[n][:3, :3] @ rest[n][:3, :3].T for n in PARTS}
        times.append(round(f / fps, 6))
        cen, rot = {}, {}
        for n in frames:
            par = parent[n]
            dp = dl[par]
            R_bl = dp.T @ dl[n]
            predicted = pose[par][:3, 3] + dp @ (rest[n][:3, 3] - rest[par][:3, 3])
            off_bl = dp.T @ (pose[n][:3, 3] - predicted)
            R = P3.T @ R_bl @ P3
            p = P3.T @ off_bl
            frames[n].append(C.mat_quat(R) + [round(float(v), 6) for v in p])
            D = pose[n] @ np.linalg.inv(rest[n])
            cen[n] = (D @ np.append(CENTRE[n], 1.0))[:3]
            rot[n] = D[:3, :3]
        centres.append(cen)
        rots.append(rot)
        if sword_ob is not None:
            D_ra = pose["Right Arm"] @ np.linalg.inv(rest["Right Arm"])
            hand = (D_ra @ np.append(HAND["Right Arm"], 1.0))[:3]
            d = blade_world(sword_ob, unit(D_ra[:3, :3] @ grip_dir(gp)))
            # the GRIP TRACK: the sword's rotation relative to the Right Arm (what a Motor6D "Handle" would carry)
            Ms = np.array(sword_ob.matrix_world)[:3, :3]
            if sword.get("_tossed"):                           # a clip with a toss: the weapon is where it IS
                hand = np.array(sword_ob.matrix_world)[:3, 3]  # (its origin = the fist whenever it is held)
            if sword.get("hold"):                              # a pistol held ahead of the fist (add_sword): its grip
                up, fwd = (float(v) for v in sword["hold"])
                hand = hand + unit(Ms[:, 2]) * up + d * fwd
            g = hand - d * spacing / 2                         # the grip's middle (between the hands)
            grip_q.append(C.mat_quat(P3.T @ (D_ra[:3, :3].T @ Ms) @ P3))
            tip = hand + d * (blade + 0.36)
            grips.append([round(float(v), 4) for v in P3.T @ (g - HRP)])
            tips.append([round(float(v), 4) for v in P3.T @ (tip - HRP)])
            # the edge (the object's -z, a direction): with tip + grip it fixes the weapon's whole rotation, so
            # kit/anim/grip.py can key the game's Handle joint from it
            edges.append([round(float(v), 4) for v in P3.T @ unit(-Ms[:, 2])])
    sample.grip_q = grip_q
    sample.edges = edges
    return times, frames, centres, rots, tips, grips


def check(clip, centres, rots):
    """the clip through the kit's own FK (the engine's maths) against the evaluated rig: every part's centre AND its
    rotation (a centre alone is blind to head yaw, an arm's twist, the torso's turn); returns the worst of
    studs and degrees/100 (0.01 = a hundredth of a stud or a degree)"""
    rig = C.load_rig("r6")
    worst, at = 0.0, None
    for i, w in enumerate(C.world_frames(clip, rig)):
        for n, want in centres[i].items():
            got = P3 @ w[n][:3, 3] + HRP
            e = float(np.linalg.norm(got - want))
            Rg = P3 @ w[n][:3, :3] @ P3.T                    # the part's rotation from rest (R6 rests are unrotated)
            c = (np.trace(Rg.T @ rots[i][n]) - 1) / 2
            deg = math.degrees(math.acos(max(-1.0, min(1.0, c))))
            e = max(e, deg / 100)
            if e > worst:
                worst, at = e, f"{n} at frame {i}"
    return worst, at


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def sha256_of_many(paths):
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def main():
    global STRETCH
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv or "--out" not in argv:
        return emit("fail", "pose_r6: needs <Name>.pose.json --out <clip.json> [--save <Name>.r6.blend]", "lune run kit anim <Name>")
    spec_path, out = argv[0], argv[argv.index("--out") + 1]
    save = argv[argv.index("--save") + 1] if "--save" in argv else None
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    if spec.get("arm_stretch") is not None:      # a strike move's arms slide further (its arm_slide): a block keeps it
        STRETCH = float(spec["arm_stretch"])
    name = spec.get("name") or os.path.basename(spec_path).split(".")[0]
    arm = bpy.data.objects.get("Rig1")
    if arm is None or arm.type != "ARMATURE":
        return emit("fail", "pose_r6: the open file holds no armature Rig1 (the owner's R6 rig)", "run it on assets/rigs/R6_IK.blend")
    missing = [n for n in PARTS + CONTROLLERS if n not in arm.pose.bones]
    if missing:
        return emit("fail", f"pose_r6: the rig lacks bones {missing}", "check assets/rigs/R6_IK.blend")
    fps = int(spec.get("fps", 60))
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = fps, 1.0
    legs = str(spec.get("legs", "ik")).lower()
    if legs not in ("ik", "fk"):
        return emit("fail", f"pose_r6 {name}: legs must be ik or fk, not {legs}", f"fix {spec_path}")
    euler = sorted({AXIS_CHANNELS[g][0] for g in (spec.get("offsets") or {}) if g in AXIS_CHANNELS})
    setup(arm, legs, euler)
    settle_switch(arm)                                    # the switch shows one evaluation late otherwise
    arm.animation_data.action = bpy.data.actions.new(name)
    keys = merged_keys(spec, fps)
    if not keys:
        return emit("fail", f"pose_r6 {name}: no keys", f"add keys to {spec_path}")
    sword = spec.get("sword")
    sword_ob = add_sword(arm, sword) if sword else None
    # 1: the key poses onto the controllers (the left arm on the hilt comes after, frame by frame)
    reports, prev_q, frames_ease = {}, {}, {}
    prev_grip_q = [None]                                  # the weapon's last keyed turn (kept on one hemisphere)
    for k in keys:
        f = k["f"]
        sc.frame_set(int(math.floor(f)))
        evaluate()
        pending_grip[0] = pending_edge[0] = pending_toss[0] = None
        r = pose_key(arm, k, sword, legs)
        if r:
            reports[f"f{f:g}"] = r
        # the weapon's turn in the hand is keyed where the RIGHT ARM is (like its controller): keyed on a key that only
        # moved the left arm, it held its old turn while the arm rolled toward the next key, then caught up in two
        # frames (GunSwitch's wind-up, 2026-10-26: a 90 deg roll onto its side and back, found by the grip-roll measure)
        if sword_ob is not None and str(sword.get("grip", "")) == "animated" and grip_keyed(k, keys):
            sword_ob.rotation_mode = "QUATERNION"
            if pending_toss[0] is not None:
                # a TOSS (Sample Game's reload spin, 2026-10-26): the weapon leaves the fist - its origin sits `toss`
                # (stage axes) from the fist this key; [0, 0, 0] catches it again. The game's Handle joint carries
                # it (the grip track is read from the weapon's own origin, sample())
                evaluate()
                fist = (np.array(arm.matrix_world) @ np.array(arm.pose.bones["Right Arm"].matrix)
                        @ np.linalg.inv(np.array(arm.data.bones["Right Arm"].matrix_local)) @ np.append(HAND["Right Arm"], 1.0))[:3]
                M = np.array(sword_ob.matrix_world)
                M[:3, 3] = fist + pending_toss[0]
                sword_ob.matrix_world = Matrix(M.tolist())
                evaluate()
            if pending_grip[0] is not None or pending_edge[0] is not None:
                turn_grip(sword_ob, pending_grip[0], pending_edge[0])
            # ONE HEMISPHERE: q and -q are the same turn, but Blender interpolates the keyed components - a sign flip
            # between two keys spun the weapon the long way round (GunReload, 2026-10-25: ~270 deg through
            # upside-down between the seat and the slap, found by the grip-roll measure)
            q = sword_ob.rotation_quaternion.copy()
            if prev_grip_q[0] is not None and q.dot(prev_grip_q[0]) < 0:
                q.negate()
                sword_ob.rotation_quaternion = q
            prev_grip_q[0] = q.copy()
            sword_ob.keyframe_insert("rotation_quaternion", frame=f)
            sword_ob.keyframe_insert("location", frame=f)
        anchor = k is keys[0] or k is keys[-1]            # the ends key everything (a loop's seam, the rest)
        for ctrl in CONTROLLERS + (["FKLeg.R", "FKLeg.L"] if legs == "fk" else []):
            if ctrl == "Arm.L" and held(k["left_arm"]):
                continue
            if legs == "fk" and ctrl in ("Foot.R", "Foot.L"):
                continue
            # a controller is keyed only where the key sets it: a field left out INTERPOLATES (a held value keyed on
            # every key froze the limbs between keys); hold on purpose by repeating the value
            if not anchor and not any(f in k["_set"] for f in CONTROLLER_FIELDS[ctrl]):
                continue
            key_bone(arm, ctrl, f, prev_q)
        frames_ease[round(f, 3)] = str(k.get("ease", "bezier")).lower()
    for side in ("SoftIK.L", "SoftIK.R"):           # the IK switch keyed, so the saved file opens in IK
        arm.pose.bones[side].keyframe_insert("location", frame=keys[0]["f"])
        arm.pose.bones[side].keyframe_insert('["FK"]', frame=keys[0]["f"])
    set_easing(arm, frames_ease)
    if sword_ob is not None and str(sword.get("grip", "")) == "animated":
        weapon_easing(sword_ob, frames_ease)
    f_end = int(math.ceil(keys[-1]["f"] - 1e-6))
    # 1b: the DRAG HIERARCHY - groups of controllers trail the body by frames, so nothing starts and stops together
    lagged = apply_offsets(arm, spec.get("offsets") or {}, legs, bool(spec.get("loop")), keys[0]["f"], keys[-1]["f"])
    # 1c: the wrist-plane lock - the weapon's turn in the fist at every frame its sword "lock" names (pose_from writes
    # the source's), from where the arm now is (after the drag offsets): the left hand below rides the true blade
    if (sword_ob is not None and str(sword.get("grip", "")) == "animated" and isinstance(sword.get("lock"), list)
            and sword["lock"]):
        lock_grip(arm, sword_ob, sword["lock"])
    # 2: the left arm, every frame, on the hilt where its keys hold it
    gap = 0.0
    if any(held(k["left_arm"]) for k in keys):
        gap = left_on_hilt(arm, keys, sword, f_end)
        for fc in controller_curves(arm, "Arm.L"):        # the per-frame hilt keys: straight lines between frames
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            fc.update()
    # (no second easing pass: the drag offsets moved keys off their frames, and a pass by frame number would flatten
    # every shifted key to linear - the arms of RigRun2 v1 glided at constant speed because of it)
    # 2b: the weapon off the hand (free flight, caught by the left fist), every frame, once the arms are final
    gun_frames = 0
    if sword_ob is not None and str(sword.get("grip", "")) == "animated":
        gun_frames = weapon_track(arm, sword_ob, keys, f_end)
    sc.frame_start, sc.frame_end = 0, f_end
    # events (frames or seconds) -> markers in the file, times in the clip
    events = []
    for e in spec.get("events") or []:
        t = float(e["f"]) / fps if "f" in e else float(e["t"])
        events.append({"name": e["name"], "t": round(t, 6), **({"value": e["value"]} if "value" in e else {})})
        sc.timeline_markers.new(e["name"], frame=int(round(t * fps)))
    # 3: the bake, then its proof
    if sword_ob is not None and (gun_frames or any(isinstance(k.get("right_arm"), dict) and "toss" in k["right_arm"] for k in keys)):
        sword = dict(sword, _tossed=True)
    times, frames, centres, rots, tips, grips = sample(arm, f_end, fps, sword_ob, sword)
    joints = {n: {"frames": fr} for n, fr in frames.items()
              if any(abs(f[3]) < 0.9999999 or any(abs(v) > 1e-4 for v in f[4:7]) for f in fr)}
    if spec.get("only"):
        # an UPPER-BODY layer (Sample Game's first-person arms, 2026-10-25): only these joints are exported, so the
        # character's own walk / run keeps the rest (the rig's IK feet leave tiny leg turns that would override it)
        joints = {n: j for n, j in joints.items() if n in set(spec["only"])}
    clip = {"schema": 1, "name": name, "rig": "R6", "fps": fps, "duration": times[-1], "loop": bool(spec.get("loop", False)),
            "priority": spec.get("priority", "Action"), "joints": joints, "times": times, "events": events,
            "feel": spec.get("feel"), "gate": spec.get("gate"),
            # a BLOCKING file (kit/anim/block.py): every key held, every change a snap ON PURPOSE (the pop gates skip them)
            **({"stepped": [[0.0, round(float(times[-1]), 4), 1]]} if spec.get("blocking") else {}),
            # an in-place LOCOMOTION cycle (a run keyed on the rig, 2026-10-26): its planted feet sweep back at the ground
            # speed on purpose - declared, the foot gate checks them against that speed instead of calling it a slide
            **({"locomotion": spec["locomotion"]} if isinstance(spec.get("locomotion"), dict) else {}),
            "source": {"kind": "pose", "file": spec_path, "sha256": sha256_of(spec_path),
                       "tool_sha256": sha256_of_many([os.path.abspath(__file__), C.__file__]),
                       "rig_sha256": sha256_of(C.rig_path("r6")), "owner_rig": bpy.data.filepath,
                       "owner_rig_sha256": sha256_of(bpy.data.filepath), "blend": save}}
    if sword_ob is not None:
        clip["sword"] = {"length": float(sword.get("blade", 4.2)) + 0.36 + float(sword.get("spacing", 0.75)) / 2,
                         "grip": float(sword.get("spacing", 0.75)), "tip": tips, "grip_path": grips}
        clip["sword"]["edge"] = sample.edges
        if sword.get("kind"):
            clip["sword"]["kind"] = str(sword["kind"])
        if str(sword.get("grip", "")) == "animated":
            # the sword turns in the fist: its rotation relative to the Right Arm per frame (a Motor6D "Handle")
            clip["sword"]["grip_rot"] = [[round(float(v), 6) for v in q] for q in sample.grip_q]
            # ... and the game's Handle joint keyed from it (kit/anim/grip.py; src/kit/AnimGrip.luau builds the joint):
            # without this track the turn in the fist was baked here and lost in game
            import grip as G
            G.add_grip(clip)
    # the LEFT hand's weapon (Sample Game's Onyx): a key's "left_gun" aims it - keyed as the Left Arm's Handle joint
    if any(isinstance(k.get("left_gun"), dict) for k in spec.get("keys") or []):
        import grip as G
        G.add_grip_left(clip, spec["keys"])
    # THE LEFT HAND ON THE BLADE where the keys put it ({"on_blade": d}: a palm braced on the flat for a block, a
    # half-sword thrust) is SAID in the clip, as a move's "on_blade" is carried into its clip (kit/anim/in_hand.py's
    # on-the-hilt rule lets through only what a clip says): from the first key of each run of such keys to the key
    # after it (the hand travels back to the hilt there), or the clip's end. A pose file's own "on_blade" is carried
    # as it is. Before this the bake dropped it and a block keyed on the flat read as a hand slid up the blade
    if sword_ob is not None:
        said_blade = spec.get("on_blade")
        if said_blade is None:
            runs, start = [], None
            for k in spec.get("keys") or []:
                on = isinstance(k.get("left_arm"), dict) and "on_blade" in k["left_arm"]
                if on and start is None:
                    start = float(k["f"]) / fps
                elif not on and start is not None:
                    runs.append([round(start, 6), round(float(k["f"]) / fps, 6)])
                    start = None
            if start is not None:
                runs.append([round(start, 6), round(float(times[-1]), 6)])
            said_blade = {"left": runs} if runs else None
        if said_blade is not None:
            clip["on_blade"] = said_blade
    worst, at = check(clip, centres, rots)
    if worst > 0.01:
        return emit("fail", f"pose_r6 {name}: the baked clip does not reproduce the rig - {worst:.3f} studs off on {at}",
                    "the bake maths (kit/anim/pose_r6.py sample) or the rig's evaluation is wrong, not the poses", worst=worst)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    if save:
        sc.frame_set(0)
        arm["kit_rig"] = "R6"                         # kit/anim/bake.py bakes an owner-edited copy of this file
        arm["kit_root"] = "HumanoidRootPart"
        arm["kit_parts"] = ",".join(PARTS)
        arm["kit_loop"] = bool(spec.get("loop", False))      # what a spec would say, kept for an edited copy's bake
        arm["kit_priority"] = str(spec.get("priority", "Action"))
        if spec.get("gate"):
            arm["kit_gate"] = json.dumps(spec["gate"])
        if spec.get("blocking"):
            arm["kit_blocking"] = True                      # a blocking file (kit/anim/block.py): held keys, snaps on purpose
        os.makedirs(os.path.dirname(os.path.abspath(save)), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save), copy=True, compress=True)
    notes = [f"{f}: " + ", ".join(f"{k} {v}" for k, v in r.items()) for f, r in reports.items()]
    return emit("pass", f"pose {name}: {len(keys)} key poses on the owner's rig ({legs.upper()} legs) -> {len(times)} frames at {fps} fps, "
                f"bake within {worst:.4f} studs of the rig" + (f", left hand short of the hilt by {gap:.2f} at worst" if gap > 0.05 else "")
                + (f", drag: " + ", ".join(f"{k} +{v:g}f" for k, v in lagged.items()) if lagged else "")
                + (f"; {len(notes)} key(s) with notes" if notes else ""),
                f"lune run kit anim look {name} --rig R6" + (f" (or open {save} in Blender)" if save else ""),
                notes=notes, bake_err=round(worst, 5), blend=save)


def check_spec(spec):
    """without Blender: per key, where the right fist lands, the blade, how far the left hand is from the hilt, the
    tip's height - what to fix in the numbers before a render"""
    sw = spec.get("sword") or {}
    gp, spacing, blade_len = float(sw.get("grip_pitch", 0)), float(sw.get("spacing", 0.75)), float(sw.get("blade", 4.2))
    rows = []
    for k in merged_keys(spec, int(spec.get("fps", 60))):
        b, Dr = k["body"], root_delta(k)
        D = Dr @ about(PIVOT["Torso"], body_rot(b), stage(b.get("pos", [0, 0, 0])))
        a = k["right_arm"]
        row = {"f": k["f"]}
        for side in ("right_arm", "left_arm"):
            if isinstance(k[side], dict) and not any(f in k[side] for f in PLACEMENT):
                row[f"{side}_error"] = "no hand / aim / rot"
        if isinstance(a, dict) and "hand" in a:
            R, sl, err, gap = solve_arm("Right Arm", D, at_root(Dr, a["hand"]),
                                        Dr[:3, :3] @ stage(a["blade"]) if "blade" in a and sw else None, gp, None, a.get("lock", "blade"))
            Rw = D[:3, :3] @ R
            hand = (D @ np.append(PIVOT["Right Arm"], 1.0))[:3] + D[:3, :3] @ sl + Rw @ (HAND["Right Arm"] - PIVOT["Right Arm"])
            bl = Rw @ grip_dir(gp)
            row.update({"hand": [round(float(v), 2) for v in (hand[0], hand[2], hand[1])],
                        "hand_off": round(float(np.linalg.norm(hand - at_root(Dr, a["hand"]))), 2), "blade_err": err,
                        "tip_y": round(float((hand + bl * (blade_len + 0.36))[2]), 2)})
            if held(k["left_arm"]):
                row["hilt_gap"] = round(solve_arm("Left Arm", D, hand + bl * along(k["left_arm"], spacing))[3], 2)
        rows.append(row)
    return rows


if __name__ == "__main__" and bpy is None and "--check" in sys.argv:
    with open(sys.argv[sys.argv.index("--check") + 1], encoding="utf-8") as fh:
        for r in check_spec(json.load(fh)):
            print(json.dumps(r))
    sys.exit(0)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        sys.exit(emit("fail", f"pose_r6 crashed: {e}", "read the traceback above"))
