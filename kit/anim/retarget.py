"""retarget.py — run INSIDE Blender by `kit anim import`:
    blender -b --factory-startup --python-exit-code 2 -P kit/anim/retarget.py -- <Name>.import.json --out <clip.json>
A REAL animation (a mocap or a professionally keyed clip in a glTF / GLB / FBX / BVH file, on any humanoid skeleton the
bone map covers) becomes a kit clip on the R15 rig: for every mapped bone, its WORLD rotation each frame relative to
its rest, differenced against its mapped parent's — so the result is "how much this part turns away from its parent",
which is what the kit's clip holds, and what the R15's axis-aligned joints play. Rest poses are aligned first (a
T-posed source gets its arms lowered to the R15's hanging rest, chain by chain), axes are mapped from the source's
world (detected from the feet: the toes point forward) to Roblox's (x right, y up, -z forward), the pelvis's height
rides on LowerTorso (scaled to the R15's size), root travel is removed and measured as `locomotion.speed` for loops,
and an attack gets its Hit one frame after the fastest hand. The source stays what it is: the clip's `source` holds
the import file, the data file's hash, the tool's and the rig's.

<Name>.import.json: {"file": "<motion file>", "clip": "<animation name>", "fps": 30, "loop": false,
                     "priority": "Action", "map": {optional R15 part -> bone overrides}, "arms": "T" | "A" | "down",
                     "hit": "auto" | <seconds> | null, "trim": [start_s, end_s] | null, "mirror": false}
"""

import hashlib
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402

# the R15 part -> source bone, per skeleton family (detected from the bones present); an explicit "map" in the
# import file overrides any entry
SKELETONS = {
    "rigify": {  # Blender Rigify DEF bones: Quaternius Universal Animation Library 1, most Blender-made rigs
        "LowerTorso": "DEF-hips", "UpperTorso": "DEF-spine.003", "Head": "DEF-head",
        "RightUpperArm": "DEF-upper_arm.R", "RightLowerArm": "DEF-forearm.R", "RightHand": "DEF-hand.R",
        "LeftUpperArm": "DEF-upper_arm.L", "LeftLowerArm": "DEF-forearm.L", "LeftHand": "DEF-hand.L",
        "RightUpperLeg": "DEF-thigh.R", "RightLowerLeg": "DEF-shin.R", "RightFoot": "DEF-foot.R",
        "LeftUpperLeg": "DEF-thigh.L", "LeftLowerLeg": "DEF-shin.L", "LeftFoot": "DEF-foot.L",
        "_toes": ["DEF-toe.R", "DEF-toe.L"],
    },
    "ue_mannequin": {  # Unreal mannequin names: Quaternius Universal Animation Library 2, many UE-targeted packs
        "LowerTorso": "pelvis", "UpperTorso": "spine_03", "Head": "Head",
        "RightUpperArm": "upperarm_r", "RightLowerArm": "lowerarm_r", "RightHand": "hand_r",
        "LeftUpperArm": "upperarm_l", "LeftLowerArm": "lowerarm_l", "LeftHand": "hand_l",
        "RightUpperLeg": "thigh_r", "RightLowerLeg": "calf_r", "RightFoot": "foot_r",
        "LeftUpperLeg": "thigh_l", "LeftLowerLeg": "calf_l", "LeftFoot": "foot_l",
        "_toes": ["ball_r", "ball_l"],
    },
    "mixamo": {  # Adobe Mixamo (FBX downloaded by a person; mixamorig: prefix)
        "LowerTorso": "mixamorig:Hips", "UpperTorso": "mixamorig:Spine2", "Head": "mixamorig:Head",
        "RightUpperArm": "mixamorig:RightArm", "RightLowerArm": "mixamorig:RightForeArm", "RightHand": "mixamorig:RightHand",
        "LeftUpperArm": "mixamorig:LeftArm", "LeftLowerArm": "mixamorig:LeftForeArm", "LeftHand": "mixamorig:LeftHand",
        "RightUpperLeg": "mixamorig:RightUpLeg", "RightLowerLeg": "mixamorig:RightLeg", "RightFoot": "mixamorig:RightFoot",
        "LeftUpperLeg": "mixamorig:LeftUpLeg", "LeftLowerLeg": "mixamorig:LeftLeg", "LeftFoot": "mixamorig:LeftFoot",
        "_toes": ["mixamorig:RightToeBase", "mixamorig:LeftToeBase"],
    },
    "bandai_bvh": {  # Bandai Namco Research Motiondataset (BVH, 30 fps; professional actors; CC BY-NC: reference only)
        "LowerTorso": "Hips", "UpperTorso": "Chest", "Head": "Head",
        "RightUpperArm": "UpperArm_R", "RightLowerArm": "LowerArm_R", "RightHand": "Hand_R",
        "LeftUpperArm": "UpperArm_L", "LeftLowerArm": "LowerArm_L", "LeftHand": "Hand_L",
        "RightUpperLeg": "UpperLeg_R", "RightLowerLeg": "LowerLeg_R", "RightFoot": "Foot_R",
        "LeftUpperLeg": "UpperLeg_L", "LeftLowerLeg": "LowerLeg_L", "LeftFoot": "Foot_L",
        "_toes": ["Toes_R", "Toes_L"],
    },
    "kevin_iglesias": {  # Kevin Iglesias' hand-keyed packs (Human Melee / Basic Motions; Asset Store EULA): B- bones
        "LowerTorso": "B-hips", "UpperTorso": "B-chest", "Head": "B-head",
        "RightUpperArm": "B-upperArm.R", "RightLowerArm": "B-forearm.R", "RightHand": "B-hand.R",
        "LeftUpperArm": "B-upperArm.L", "LeftLowerArm": "B-forearm.L", "LeftHand": "B-hand.L",
        "RightUpperLeg": "B-thigh.R", "RightLowerLeg": "B-shin.R", "RightFoot": "B-foot.R",
        "LeftUpperLeg": "B-thigh.L", "LeftLowerLeg": "B-shin.L", "LeftFoot": "B-foot.L",
        "_toes": ["B-toe.R", "B-toe.L"],
    },
    "cmu_bvh": {  # the CMU motion capture database as BVH (cgspeed conversions)
        "LowerTorso": "Hips", "UpperTorso": "Spine1", "Head": "Head",
        "RightUpperArm": "RightArm", "RightLowerArm": "RightForeArm", "RightHand": "RightHand",
        "LeftUpperArm": "LeftArm", "LeftLowerArm": "LeftForeArm", "LeftHand": "LeftHand",
        "RightUpperLeg": "RightUpLeg", "RightLowerLeg": "RightLeg", "RightFoot": "RightFoot",
        "LeftUpperLeg": "LeftUpLeg", "LeftLowerLeg": "LeftLeg", "LeftFoot": "LeftFoot",
        "_toes": ["RightToeBase", "LeftToeBase"],
    },
}


def detect_skeleton(arm):
    names = {b.name for b in arm.data.bones}
    best, score = None, 0
    for family, m in SKELETONS.items():
        hit = sum(1 for k, v in m.items() if not k.startswith("_") and v in names)
        if hit > score:
            best, score = family, hit
    return best, score
R15_PARENT = {"LowerTorso": None, "UpperTorso": "LowerTorso", "Head": "UpperTorso",
              "RightUpperArm": "UpperTorso", "RightLowerArm": "RightUpperArm", "RightHand": "RightLowerArm",
              "LeftUpperArm": "UpperTorso", "LeftLowerArm": "LeftUpperArm", "LeftHand": "LeftLowerArm",
              "RightUpperLeg": "LowerTorso", "RightLowerLeg": "RightUpperLeg", "RightFoot": "RightLowerLeg",
              "LeftUpperLeg": "LowerTorso", "LeftLowerLeg": "LeftUpperLeg", "LeftFoot": "LeftLowerLeg"}
ARM_CHAINS = {"R": ["RightUpperArm", "RightLowerArm", "RightHand"], "L": ["LeftUpperArm", "LeftLowerArm", "LeftHand"]}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"import": a[0] if a else None, "out": None}
    i = 1
    while i < len(a):
        if a[i] == "--out" and i + 1 < len(a):
            out["out"] = a[i + 1]
            i += 2
        else:
            i += 1
    return out


def sha256_of(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def sha256_of_many(paths):
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def load_motion(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".gltf", ".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".bvh":
        # the scene's fps follows the file's frame time (Blender leaves 24 otherwise: a 30 fps capture ran 25% slow)
        bpy.ops.import_anim.bvh(filepath=path, update_scene_fps=True, update_scene_duration=True)
    else:
        raise ValueError(f"unsupported motion file {ext}")
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not arms:
        raise ValueError("no armature in the motion file")
    return arms[0]


def axis_map(arm, bone_map):
    """the matrix taking the source's world axes to Roblox's: right = the right arm's side (right hand from the
    hips), up = +Z (Blender), forward = where the toes point from the feet (fallback: up x right)"""
    def head(name):
        b = arm.data.bones.get(name)
        return (arm.matrix_world @ b.head_local) if b else None
    up = Vector((0, 0, 1))
    rh, lh = head(bone_map["RightHand"]), head(bone_map["LeftHand"])
    right = (rh - lh) if (rh and lh) else Vector((-1, 0, 0))
    right = (right - right.dot(up) * up).normalized()
    fwds = []
    for foot_part, toe_name in (("RightFoot", bone_map.get("_toes", [None, None])[0]), ("LeftFoot", bone_map.get("_toes", [None, None])[1])):
        foot, toe = arm.data.bones.get(bone_map[foot_part]), (arm.data.bones.get(toe_name) if toe_name else None)
        if foot and toe:
            v = (arm.matrix_world @ toe.head_local) - (arm.matrix_world @ foot.head_local)
            v = v - v.dot(up) * up
            if v.length > 1e-6:
                fwds.append(v.normalized())
        elif foot:  # no toe bone: the foot bone itself points along the foot
            v = (arm.matrix_world @ foot.tail_local) - (arm.matrix_world @ foot.head_local)
            v = v - v.dot(up) * up
            if v.length > 1e-6:
                fwds.append(v.normalized())
    # AHEAD is where BOTH feet point, together (the last foot alone - the left - set it: a body standing toe-out,
    # as most real mocap stands, came in turned by the left foot's splay; the frame contract's calibration, 2026-11-16:
    # 10 degrees toe-out put the arms 6 degrees off)
    fwd = sum(fwds, Vector((0, 0, 0))) if fwds else None
    if fwd is None or fwd.length < 1e-6:
        fwd = up.cross(right).normalized()
    else:
        fwd = fwd.normalized()
    # the right is then ahead x up - always: a frame of three square axes, never a skewed one
    toes_right = fwd.cross(up).normalized()
    global AXES_DISAGREE
    AXES_DISAGREE = toes_right.dot(right) < 0
    if AXES_DISAGREE:
        # the hands say the right is the other way from what the toes do: a skeleton whose left / right labels are
        # swapped, or toes that point back. The hands are trusted (as before) - and it is SAID, not hidden
        fwd = -fwd
    right = fwd.cross(up).normalized()
    # Roblox: x = right, y = up, z = -forward
    return np.array([[right.x, right.y, right.z], [up.x, up.y, up.z], [-fwd.x, -fwd.y, -fwd.z]], dtype=float)


AXES_DISAGREE = False


def standing_height(arm, bone_map):
    """the source body's standing height from its BONES, not its pose: the chain from the pelvis up to the head's top
    (each bone's head to the next one's) plus a leg (the hip's drop under the pelvis, the thigh, the shin, the ankle
    over the sole). A pose that never stands - a crouch, a crawl, a body lying down - reads as tall as it is (the
    frame contract's review, 2026-11-16: a crouch-hop read 33% big, a body lying down 3.5 times)"""
    bones = arm.data.bones
    head = bones[bone_map["Head"]]
    pelvis = bones[bone_map["LowerTorso"]]
    upper, b = head.length, head
    while b is not None and b.name != pelvis.name:
        parent = b.parent
        if parent is None:
            break
        upper += (b.head_local - parent.head_local).length
        b = parent
    leg = 0.0
    for side in ("Right", "Left"):
        thigh, shin, foot = (bones[bone_map[f"{side}{p}"]] for p in ("UpperLeg", "LowerLeg", "Foot"))
        drop = max(pelvis.head_local.z - thigh.head_local.z, 0.0)
        ankle = max(foot.head_local.z - min(foot.tail_local.z, foot.head_local.z), 0.0)
        leg = max(leg, drop + (shin.head_local - thigh.head_local).length + (foot.head_local - shin.head_local).length + ankle)
    scale = arm.matrix_world.to_scale()
    return (upper + leg) * float(abs(scale.z))


def rot_of(m):
    """the pure rotation of a 3x3 (the nearest orthonormal matrix): an FBX armature carries its unit scale (0.01 for
    a centimetre file) in matrix_world, and a scaled 'rotation' collapsed every joint to no turn (2026-10-11)"""
    r = np.array([[m[i][j] for j in range(3)] for i in range(3)], dtype=float)
    u, _, vt = np.linalg.svd(r)
    q = u @ vt
    if np.linalg.det(q) < 0:                         # never a mirror
        u[:, -1] = -u[:, -1]
        q = u @ vt
    return q


def main():
    a = args()
    if not a["import"] or not a["out"]:
        return emit("fail", "retarget: needs <Name>.import.json --out <clip.json>", "lune run kit anim import <file> --clip <Anim> --as <Name>")
    with open(a["import"], encoding="utf-8") as fh:
        spec = json.load(fh)
    src = spec["file"]
    if not os.path.isfile(src):
        return emit("fail", f"retarget: no motion file {src}", "check the path in the .import.json")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = load_motion(os.path.abspath(src))
    family, score = detect_skeleton(arm)
    bone_map = dict(SKELETONS[family]) if family else {}
    bone_map.update(spec.get("map") or {})
    toes = bone_map.pop("_toes", [None, None])
    missing = [p for p, b in bone_map.items() if b not in arm.data.bones]
    if missing:
        return emit("fail", f"retarget: the armature has no bone for {missing} (bones: {[b.name for b in arm.data.bones][:20]}...)",
                    "add a 'map' of R15 part -> bone name to the .import.json")
    act = bpy.data.actions.get(spec["clip"])
    if act is None:
        return emit("fail", f"retarget: no animation named {spec['clip']}", f"one of: {sorted(x.name for x in bpy.data.actions)}")
    if arm.animation_data is None:
        arm.animation_data_create()
    for t in arm.animation_data.nla_tracks:
        t.mute = True
    arm.animation_data.action = act
    # Blender 5 slotted actions: re-assigning an action can leave no slot bound and NOTHING plays (an FBX pack
    # imported as 5 still joints, 2026-10-11) - bind the action's own slot for this object
    if getattr(arm.animation_data, "action_slot", None) is None and len(getattr(act, "slots", [])):
        arm.animation_data.action_slot = act.slots[0]
    sc = bpy.context.scene
    src_fps = sc.render.fps / sc.render.fps_base
    f0, f1 = act.frame_range
    if spec.get("trim"):
        f0, f1 = f0 + spec["trim"][0] * src_fps, min(f1, f0 + spec["trim"][1] * src_fps)
    duration = max((f1 - f0) / src_fps, 1 / src_fps)
    fps = int(spec.get("fps") or 30)
    n = max(1, int(round(duration * fps)))
    times = [round(i / fps, 6) for i in range(n + 1)]
    M = axis_map(arm, dict(bone_map, _toes=toes))            # source world -> Roblox character axes
    # rests: world rotation of every mapped bone at rest, the arms lowered to the R15's hanging rest if T/A-posed
    rest = {}
    for part, bone in bone_map.items():
        rest[part] = rot_of((arm.matrix_world @ arm.data.bones[bone].matrix_local).to_3x3())
    arms_pose = spec.get("arms", "auto")
    if arms_pose == "auto":
        up_r = arm.data.bones[bone_map["RightUpperArm"]]
        v = (arm.matrix_world @ up_r.tail_local) - (arm.matrix_world @ up_r.head_local)
        drop = -v.normalized().z                             # 1 = hanging, 0 = horizontal
        arms_pose = "down" if drop > 0.85 else ("A" if drop > 0.35 else "T")
    for side, chain in ARM_CHAINS.items():
        up_b = arm.data.bones[bone_map[chain[0]]]
        v = (arm.matrix_world @ up_b.tail_local) - (arm.matrix_world @ up_b.head_local)
        v = v.normalized()
        down = Vector((0, 0, -1))
        if arms_pose != "down" and v.dot(down) < 0.98:
            axis = v.cross(down)
            if axis.length < 1e-6:
                axis = Vector((0, 1, 0))
            A = rot_of(Matrix.Rotation(math.acos(max(-1.0, min(1.0, v.dot(down)))), 3, axis.normalized()))
            for part in chain:
                rest[part] = A @ rest[part]
    # the R15 size for the pelvis's travel: the source's height vs the kit rig's
    r15 = C.load_rig("r15")
    # measured on the POSED body across the clip (a BVH's rest hierarchy is a zero pose laid along axes, not a
    # standing figure): the tallest head-over-feet is the standing height, the lowest foot point the floor
    # the source's height from its BONES (standing_height): the clip's highest head over its lowest foot read a body
    # that rises as taller (a 0.2 m rise of a 1.73 m body came in 10% short), and head over feet in one frame read a
    # body that never stands as shorter (the frame contract's import calibration and its review, 2026-11-16)
    feet = None
    for k in range(13):
        fk = f0 + (f1 - f0) * k / 12
        sc.frame_set(int(math.floor(fk)), subframe=float(fk - math.floor(fk)))
        ht = (arm.matrix_world @ arm.pose.bones[bone_map["Head"]].matrix @ Vector((0, arm.data.bones[bone_map["Head"]].length, 0))).z
        ft = min((arm.matrix_world @ arm.pose.bones[bone_map[f]].matrix @ Vector((0, arm.data.bones[bone_map[f]].length, 0))).z
                 for f in ("RightFoot", "LeftFoot"))
        feet = ft if feet is None else min(feet, ft)
    src_height = max(standing_height(arm, bone_map), 1e-3)
    r15_height = (r15["rest"]["Head"][1] + r15["sizes"]["Head"][1] / 2) - (r15["rest"]["RightFoot"][1] - r15["sizes"]["RightFoot"][1] / 2)
    scale = r15_height / src_height
    hips_bone = bone_map["LowerTorso"]
    hips_rest = np.array(arm.matrix_world @ arm.data.bones[hips_bone].head_local)
    frames = {p: [] for p in bone_map}
    hips_path = []
    hands = {"RightHand": [], "LeftHand": []}
    src_floor = feet                                         # the source's lowest foot point in the clip: its floor
    src_low = []                                             # the source's lowest foot point per frame (its own planted-ness)
    for i, t in enumerate(times):
        f = f0 + t * src_fps
        sc.frame_set(int(math.floor(f)), subframe=float(f - math.floor(f)))
        world = {}
        for part, bone in bone_map.items():
            pb = arm.pose.bones[bone]
            W = arm.matrix_world @ pb.matrix
            delta = rot_of(W.to_3x3()) @ rest[part].T        # the bone's turn away from its (aligned) rest, world
            world[part] = M @ delta @ M.T                     # in Roblox axes
            if part in hands:
                hands[part].append(M @ (np.array(W.translation) * scale))
        hips_now = np.array(arm.matrix_world @ arm.pose.bones[hips_bone].matrix.translation)
        hips_path.append(M @ ((hips_now - hips_rest) * scale))
        # the source body's lowest point (any mapped bone's ends): a foot on the floor, a knee, a body lying down
        low = min((arm.matrix_world @ arm.pose.bones[b].matrix @ Vector((0, b_len, 0))).z
                  for b in bone_map.values() for b_len in (0.0, arm.data.bones[b].length))
        src_low.append(low - src_floor)
        for part in bone_map:
            parent = R15_PARENT[part]
            local = (world[parent].T @ world[part]) if parent else world[part]
            q = C.mat_quat(local)
            frames[part].append([round(float(v), 6) for v in q] + [0.0, 0.0, 0.0])
    # the pelvis: its height rides on LowerTorso; horizontal travel is root motion - removed, and for a loop measured
    hp = np.array(hips_path)
    travel = hp[-1] - hp[0]
    speed = float(math.hypot(travel[0], travel[2]) / duration) if duration > 0 else 0.0
    loop_wanted = bool(spec.get("loop", False))
    root_track = None
    if loop_wanted:
        # a loop plays in place: its travel is removed linearly and becomes locomotion.speed (the runtime rate-matches)
        for i in range(len(times)):
            u = i / max(len(times) - 1, 1)
            inplace = hp[i] - np.array([travel[0] * u, 0.0, travel[2] * u])
            frames["LowerTorso"][i][4:7] = [round(float(inplace[0]), 5), round(float(inplace[1]), 5), round(float(inplace[2]), 5)]
    else:
        # a one-shot (a lunge, a roll, a knockback) keeps its travel as a ROOT track: the pelvis stays over the root,
        # the root moves - the gates judge feet in the world, the game applies the travel (Meta carries it)
        root_track = []
        for i in range(len(times)):
            frames["LowerTorso"][i][4:7] = [0.0, round(float(hp[i][1]), 5), 0.0]
            root_track.append([0.0, 0.0, 0.0, 1.0, round(float(hp[i][0] - hp[0][0]), 5), 0.0, round(float(hp[i][2] - hp[0][2]), 5)])
    # the floor fit: the R15's legs are not the source's; wherever the source had a foot on its floor, the R15's
    # lowest foot point is put on the kit's floor (the pelvis moves), elsewhere the pelvis keeps the source's height
    clip_tmp = {"rig": "R15", "fps": fps, "times": times, "joints": {p: {"frames": fr} for p, fr in frames.items()}}
    world_frames = C.world_frames(clip_tmp, r15)
    floor = C.rest_ground(r15, ["RightFoot", "LeftFoot"])
    shifts = []
    for i in range(len(times)):
        low = min(C.lowest(r15, part, world_frames[i][part]) for part in bone_map)   # whatever is lowest: a foot, a body
        planted = src_low[i] < 0.05                          # 5 cm over the source floor: something is on the floor
        shifts.append((floor - low) if planted else None)
    # fill the in-air frames by interpolation (a jump keeps the source's rise over the last planted height)
    known = [i for i, v in enumerate(shifts) if v is not None]
    if known:
        for i in range(len(shifts)):
            if shifts[i] is None:
                before = max((k for k in known if k < i), default=None)
                after = min((k for k in known if k > i), default=None)
                if before is None:
                    shifts[i] = shifts[after]
                elif after is None:
                    shifts[i] = shifts[before]
                else:
                    u = (i - before) / (after - before)
                    shifts[i] = shifts[before] * (1 - u) + shifts[after] * u
        for i in range(len(times)):
            frames["LowerTorso"][i][5] = round(float(frames["LowerTorso"][i][5] + shifts[i]), 5)
    loop = bool(spec.get("loop", False))
    if loop and len(times) > 4:
        # a library loop rarely closes to the degree: its last frames ease into a copy of its first (a crossfade
        # over the final tenth), so the seam gate and the engine's loop see one continuous cycle
        k = max(2, len(times) // 10)
        for part, fr in frames.items():
            first = np.array(fr[0], dtype=float)
            for j in range(k):
                i = len(times) - 1 - (k - 1 - j)
                w = (j + 1) / k
                cur = np.array(fr[i], dtype=float)
                q0, q1 = cur[:4], first[:4]
                if float(np.dot(q0, q1)) < 0:
                    q1 = -q1
                q = q0 * (1 - w) + q1 * w
                q = q / max(float(np.linalg.norm(q)), 1e-9)
                pos = cur[4:7] * (1 - w) + first[4:7] * w
                fr[i] = [round(float(v), 6) for v in q] + [round(float(v), 5) for v in pos]
    # an in-place loop's ground speed is what its planted feet do (kit/anim/gait.py reads it the same way)
    if loop and speed <= 0.5:
        clip_tmp["joints"]["LowerTorso"]["frames"] = frames["LowerTorso"]
        wf = C.world_frames(clip_tmp, r15)
        contact = {}                                         # per foot: its lowest corner per frame (the contact point:
        for f in ("RightFoot", "LeftFoot"):                  # a heel, a flat sole or a toe - a jog lands on the ball)
            pts = []
            for w in wf:
                cs = C.corners(r15, f, w[f])
                pts.append(cs[int(np.argmin(cs[:, 1]))])
            contact[f] = np.array(pts)
        # the ground speed is what the feet DO over a whole plant: each contact span's travel of the foot's centre
        # over its duration (the lowest corner flips heel to toe inside a span - its per-frame steps overshoot),
        # the spans weighted by their frames; a keyed library foot that lands slow and leaves fast averages out
        spans = []                                           # (travel xz, frames)
        for f in ("RightFoot", "LeftFoot"):
            centre = np.array([w[f][:3, 3] for w in wf])
            down = [contact[f][i, 1] - floor < 0.03 for i in range(len(times))]
            i = 0
            while i < len(times):
                if down[i]:
                    j = i
                    while j + 1 < len(times) and down[j + 1]:
                        j += 1
                    if j > i:
                        spans.append((centre[j, [0, 2]] - centre[i, [0, 2]], j - i))
                    i = j + 1
                else:
                    i += 1
        if len(spans) >= 1 and sum(n for _, n in spans) >= 3:
            total = sum(n for _, n in spans)
            v = sum(d for d, _ in spans) / total * fps        # studs per second, xz
            speed = float(np.hypot(v[0], v[1]))
            travel = np.array([-v[0], 0.0, -v[1]])            # the body goes the other way from its planted feet
    joints = {}
    for part, fr in frames.items():
        moving = any(abs(f[3]) < 0.9999 or any(abs(v) > 1e-3 for v in f[4:7]) for f in fr)
        if moving:
            joints[part] = {"frames": fr}
    events = list(spec.get("events") or [])
    hit = spec.get("hit", "auto" if not loop else None)
    hit_inferred = []
    if hit == "auto":
        # one Hit per strike: every local peak of the faster hand's speed that reaches half the clip's fastest
        # (a combo swings three times), the frame after each peak; peaks closer than 4 frames are one strike
        speed_of = None
        for hand, path in hands.items():
            sp = np.array([float(np.linalg.norm(path[i] - path[i - 1])) * fps for i in range(1, len(path))])
            if speed_of is None or sp.max() > speed_of.max():
                speed_of = sp
        if speed_of is not None and speed_of.max() > 1.0:
            top = float(speed_of.max())
            last = -10
            for i in range(len(speed_of)):
                before = speed_of[i - 1] if i > 0 else -1.0
                after = speed_of[i + 1] if i + 1 < len(speed_of) else -1.0
                if speed_of[i] >= 0.5 * top and speed_of[i] >= before and speed_of[i] > after and i - last >= 4:
                    events.append({"name": "Hit", "t": round(times[min(i + 2, len(times) - 1)], 4)})
                    last = i
                    hit_inferred.append(events[-1]["t"])  # (placed at a speed peak: kit/anim/contact.py holds it to the geometry)
    elif isinstance(hit, (int, float)):
        events.append({"name": "Hit", "t": float(hit)})
    name = spec.get("name") or os.path.basename(a["import"]).split(".")[0]
    clip = {"schema": 1, "name": name, "rig": "R15", "fps": fps, "duration": times[-1], "loop": loop,
            "priority": spec.get("priority", "Movement" if loop else "Action"), "joints": joints, "times": times,
            "events": events, "beats": spec.get("beats"), "feel": spec.get("feel"), "gate": spec.get("gate"),
            "source": {"kind": "import", "file": a["import"], "data": src, "clip": spec["clip"], "sha256": sha256_of(a["import"]),
                       "data_sha256": sha256_of(src), "tool_sha256": sha256_of_many([__file__, C.__file__]),
                       "rig_sha256": sha256_of(C.rig_path("r15"))}}
    if hit_inferred:
        clip["hit_inferred"] = hit_inferred
    if root_track is not None and any(abs(f[4]) > 1e-3 or abs(f[6]) > 1e-3 for f in root_track):
        clip["root"] = root_track
    if loop and speed > 0.5:
        d = np.array([travel[0], 0.0, travel[2]])
        if np.linalg.norm(d) < 1e-6:
            d = np.array([0.0, 0.0, -1.0])
        d = d / max(np.linalg.norm(d), 1e-9)
        clip["locomotion"] = {"speed": round(speed, 2), "direction": [round(float(v), 3) for v in d], "cycle": round(duration, 4)}
    os.makedirs(os.path.dirname(os.path.abspath(a["out"])), exist_ok=True)
    with open(a["out"], "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    return emit("pass", f"import {name}: {spec['clip']} from {os.path.basename(src)} -> {len(joints)} joint(s) x {len(times)} frames at {fps} fps"
                + (f", travels {speed:.2f} studs/s (made in-place)" if speed > 0.5 else "") + f", {family} skeleton, arms were {arms_pose}-posed, scale x{scale:.2f} -> {a['out']}"
                + ("; WARNING: its hands and its toes disagree on which way is right - a skeleton whose left / right "
                   "labels are swapped, or toes that point back: the hands were trusted, look at it" if AXES_DISAGREE else ""),
                f"lune run kit anim {name}: the strip + the gates, then kit anim look {name}", clip=a["out"], speed=round(speed, 2),
                scale=round(scale, 3), axes_disagree=AXES_DISAGREE)


if __name__ == "__main__":
    sys.exit(main())
