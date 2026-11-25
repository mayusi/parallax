"""bake.py — a Blender action on the kit rig -> the neutral clip (build/animations/<Name>.clip.json):
    blender -b --factory-startup --python-exit-code 2 -P kit/anim/bake.py -- <Name> --rig <rig.blend> --out <clip.json>
        [--blend <animated.blend>]   the animator's file (the kit rig + its action; markers = events)
        [--spec <spec.json>]         no animator: the spec's keys applied to the rig in Blender, then baked
        [--clip <clip.json>]         a built clip (a gait's, a bake's) keyed on the rig frame by frame: an animator's
                                     starting point for a generated motion (open it, refine it, kit anim bakes it)

What is baked, per frame and per deform bone, is the ENGINE's joint transform: with the part riding its bone, the
part's rotation since rest is P = pose * rest^-1 (armature space); the joint's character-space rotation is then
parent_P^-1 * P, and its offset the pivot's drift from where the parent's motion alone would carry it — turned from
Blender's axes into Roblox's (BL_FROM_RBX). IK, constraints and the NLA are all evaluated (the scene is sampled), so
whatever the animator did, the clip holds what the engine will play. Timeline markers become events ("Hit"), markers
named beat:<name> span beats, the root bone's motion is the clip's root track.
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
import clip as C  # noqa: E402  (the kit's sampler: what the engine will interpolate, for the round-trip check)

BL_FROM_RBX = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
P3 = np.array(BL_FROM_RBX.to_3x3())        # Roblox vectors -> Blender vectors
R6_TO_R15 = {"Torso": "LowerTorso", "Head": "Head", "Right Arm": "RightUpperArm", "Left Arm": "LeftUpperArm",
             "Right Leg": "RightUpperLeg", "Left Leg": "LeftUpperLeg"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"name": a[0] if a else None, "rig": None, "out": None, "blend": None, "spec": None, "clip": None, "fps": None, "save": None}
    i = 1
    while i < len(a):
        k = a[i]
        if k in ("--rig", "--out", "--blend", "--spec", "--clip", "--fps", "--save") and i + 1 < len(a):
            out[k[2:]] = a[i + 1]
            i += 2
        else:
            i += 1
    return out


def euler_mat(deg):
    x, y, z = (math.radians(v) for v in deg)
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rx @ ry @ rz


def mat_quat(m):
    """3x3 (rows) -> [x, y, z, w]"""
    m = np.asarray(m, dtype=float)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    n = math.sqrt(sum(v * v for v in q)) or 1.0
    return [round(v / n, 6) for v in q]


def find_rig():
    for o in bpy.data.objects:
        if o.type == "ARMATURE" and o.get("kit_rig"):
            return o
    return None


def apply_spec(arm, spec, fps):
    """the spec's character-space keys -> bone-local keys on the rig (Blender's own interpolation between them)"""
    sc = bpy.context.scene
    sc.render.fps = fps
    rest = {b.name: np.array(b.matrix_local.to_3x3()) for b in arm.data.bones}
    arm.animation_data_clear()
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    last = 0.0
    for key in spec["keys"]:
        frame = 1 + float(key["t"]) * fps                 # exact (a fractional frame is fine: the scene is sampled)
        last = max(last, float(key["t"]))
        for part, value in (key.get("pose") or {}).items():
            name = part if part in arm.pose.bones else R6_TO_R15.get(part)
            if name is None or name not in arm.pose.bones:
                continue
            rot = value["rot"] if isinstance(value, dict) else value
            pos = value.get("pos", [0, 0, 0]) if isinstance(value, dict) else [0, 0, 0]
            # character space (Roblox axes) -> Blender axes -> the bone's own frame
            R_bl = P3 @ euler_mat(rot) @ P3.T
            Rb = rest[name].T @ R_bl @ rest[name]
            pb = arm.pose.bones[name]
            pb.rotation_quaternion = Matrix(Rb.tolist()).to_quaternion()
            pb.location = Vector((rest[name].T @ (P3 @ np.array(pos, dtype=float))).tolist())
            pb.keyframe_insert("rotation_quaternion", frame=frame)
            pb.keyframe_insert("location", frame=frame)
    sc.frame_start, sc.frame_end = 1, 1 + int(math.ceil(last * fps - 1e-6))
    sc["kit_duration"] = last
    # the spec's easing on every key (Blender's per-key modes match: a key's mode shapes the segment to the next key)
    modes = {"Linear": "LINEAR", "Constant": "CONSTANT", "Cubic": "CUBIC", "CubicV2": "CUBIC", "Elastic": "ELASTIC",
             "Bounce": "BOUNCE"}
    dirs = {"In": "EASE_IN", "Out": "EASE_OUT", "InOut": "EASE_IN_OUT"}
    by_frame = {round(1 + float(k["t"]) * fps, 4): (modes.get(k.get("ease", "Cubic"), "CUBIC"), dirs.get(k.get("dir", "InOut"), "EASE_IN_OUT"))
                for k in spec["keys"]}
    if arm.animation_data and arm.animation_data.action:
        try:
            from bpy_extras.anim_utils import action_get_channelbag_for_slot
            bag = action_get_channelbag_for_slot(arm.animation_data.action, arm.animation_data.action_slot)
            curves = bag.fcurves if bag else []
        except Exception:  # noqa: BLE001  (older API)
            curves = arm.animation_data.action.fcurves
        for fc in curves:
            for kp in fc.keyframe_points:
                mode, easing = by_frame.get(round(float(kp.co[0]), 4), ("CUBIC", "EASE_IN_OUT"))
                kp.interpolation = mode
                if mode not in ("LINEAR", "CONSTANT"):
                    kp.easing = easing
    for ev in spec.get("events") or []:  # markers for the animator (a value rides in the name as Name:value)
        label = ev["name"] + (f":{ev['value']}" if ev.get("value") else "")
        sc.timeline_markers.new(label, frame=int(round(1 + float(ev["t"]) * fps)))


def apply_clip(arm, clip, fps):
    """a clip's frames (character-space joint transforms on the kit's own time grid) -> a key on every frame of
    every moving bone, linear between them (the engine plays the same frames): the generated motion, editable"""
    sc = bpy.context.scene
    sc.render.fps = fps
    rest = {b.name: np.array(b.matrix_local.to_3x3()) for b in arm.data.bones}
    arm.animation_data_clear()
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    times = clip["times"]
    for name, joint in clip["joints"].items():
        bone = name if name in arm.pose.bones else R6_TO_R15.get(name)
        if bone is None or bone not in arm.pose.bones or not joint.get("frames"):
            continue
        pb = arm.pose.bones[bone]
        for i, f in enumerate(joint["frames"]):
            if i >= len(times):
                break
            R_bl = P3 @ C.quat_mat(f[:4]) @ P3.T
            Rb = rest[bone].T @ R_bl @ rest[bone]
            pb.rotation_quaternion = Matrix(Rb.tolist()).to_quaternion()
            pb.location = Vector((rest[bone].T @ (P3 @ np.array(f[4:7], dtype=float))).tolist())
            frame = 1 + float(times[i]) * fps
            pb.keyframe_insert("rotation_quaternion", frame=frame)
            pb.keyframe_insert("location", frame=frame)
    last = float(times[-1]) if times else 0.0
    sc.frame_start, sc.frame_end = 1, 1 + int(round(last * fps))
    sc["kit_duration"] = last
    if arm.animation_data and arm.animation_data.action:
        try:
            from bpy_extras.anim_utils import action_get_channelbag_for_slot
            bag = action_get_channelbag_for_slot(arm.animation_data.action, arm.animation_data.action_slot)
            curves = bag.fcurves if bag else []
        except Exception:  # noqa: BLE001  (older API)
            curves = arm.animation_data.action.fcurves
        for fc in curves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
    for ev in clip.get("events") or []:
        label = ev["name"] + (f":{ev['value']}" if ev.get("value") else "")
        sc.timeline_markers.new(label, frame=int(round(1 + float(ev["t"]) * fps)))


def time_grid(sc, fps, duration=None):
    """the kit's sample times: 0, 1/fps, ... and the exact end (a spec's duration), else the scene's whole frames"""
    if duration is None:
        return [round((f - sc.frame_start) / fps, 6) for f in range(sc.frame_start, sc.frame_end + 1)]
    n = int(math.floor(duration * fps + 1e-6))
    times = [round(i / fps, 6) for i in range(n + 1)]
    if times[-1] < duration - 1e-6:
        times.append(round(duration, 6))
    return times


def sample(arm, fps, root_name, duration=None):
    """every kit time -> {bone: (R 3x3 Roblox character space, p Roblox)} + the root's world track"""
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    # the owner's R6 rig marks every bone deform (controllers too): its parts are named on the armature (kit_parts)
    parts = [p for p in str(arm.get("kit_parts", "")).split(",") if p]
    bones = [b for b in arm.data.bones if b.use_deform and (not parts or b.name in parts)]
    rest = {b.name: np.array(b.matrix_local) for b in bones}
    parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
    frames, times, root_track = {b.name: [] for b in bones if b.name != root_name}, [], []
    for t in time_grid(sc, fps, duration):
        f = sc.frame_start + t * fps
        sc.frame_set(int(math.floor(f + 1e-9)), subframe=float(f - math.floor(f + 1e-9)))
        dg.update()
        dg.update()                    # a rig with a driver cycle (the owner's SoftIK switch) settles on the second
        pose = {b.name: np.array(arm.pose.bones[b.name].matrix) for b in bones}
        delta = {n: pose[n][:3, :3] @ rest[n][:3, :3].T for n in pose}  # the part's rotation since rest (armature space)
        times.append(t)
        for n in pose:
            if n == root_name:
                R = P3.T @ delta[n] @ P3
                p = P3.T @ (pose[n][:3, 3] - rest[n][:3, 3])
                root_track.append(mat_quat(R) + [round(float(v), 5) for v in p])
                continue
            par = parent[n]
            dp = delta[par] if par in delta else np.eye(3)
            R_bl = dp.T @ delta[n]
            # the pivot's drift from where the parent's motion alone carries it
            head_rest, par_head_rest = rest[n][:3, 3], rest[par][:3, 3] if par in rest else np.zeros(3)
            par_now = pose[par][:3, 3] if par in pose else np.zeros(3)
            predicted = par_now + dp @ (head_rest - par_head_rest)
            off_bl = dp.T @ (pose[n][:3, 3] - predicted)
            R = P3.T @ R_bl @ P3
            p = P3.T @ off_bl
            frames[n].append(mat_quat(R) + [round(float(v), 5) for v in p])
    return times, frames, root_track


def spec_duration(spec):
    return max(float(k["t"]) for k in spec["keys"])


def sha256_of_many(paths):
    """one hash over several files' bytes in order (the baker AND the module it checks with)"""
    h = hashlib.sha256()
    for path in paths:
        with open(path, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def sha256_of(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def main():
    a = args()
    if not a["name"] or not a["out"]:
        return emit("fail", "bake: needs <Name> --rig <rig.blend> --out <clip.json> [--blend <file> | --spec <spec.json>]",
                    "lune run kit anim bake <Name>")
    src = a["blend"] or a["rig"]
    if not src or not os.path.isfile(src):
        return emit("fail", f"bake: no rig file {src}", "lune run kit anim rig r15 --blend")
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(src))
    arm = find_rig()
    if arm is None:
        return emit("fail", f"bake: {src} holds no kit rig (an armature with kit_rig)", "lune run kit anim rig r15 --blend")
    sc = bpy.context.scene
    fps = int(a["fps"]) if a["fps"] else int(round(sc.render.fps / sc.render.fps_base))
    spec = None
    source_clip = None
    if a["spec"]:
        with open(a["spec"], encoding="utf-8") as fh:
            spec = json.load(fh)
        apply_spec(arm, spec, fps)
    elif a["clip"]:
        with open(a["clip"], encoding="utf-8") as fh:
            source_clip = json.load(fh)
        fps = int(source_clip.get("fps") or fps)
        apply_clip(arm, source_clip, fps)
    if (a["spec"] or a["clip"]) and a["save"]:
        os.makedirs(os.path.dirname(os.path.abspath(a["save"])), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a["save"]), compress=True)
    root_name = arm.get("kit_root", "HumanoidRootPart")
    duration = float(spec_duration(spec)) if spec else (float(source_clip["duration"]) if source_clip else None)
    times, frames, root_track = sample(arm, fps, root_name, duration)
    if source_clip:  # the round trip of a clip: every keyed frame must come back as it went in
        worst, worst_at = 0.0, None
        for name, joint in source_clip["joints"].items():
            if name not in frames:
                continue
            for i, want in enumerate(joint["frames"]):
                if i >= len(frames[name]):
                    break
                err = C.quat_angle(want, frames[name][i])
                if err > worst:
                    worst, worst_at = err, f"{name} at {times[i]:.3f} s"
        if worst > 1.0:
            return emit("fail", f"bake {a['name']}: the rig does not reproduce the clip - {worst:.2f} degrees off on {worst_at}",
                        "the rig's bone maths or axes are wrong (kit/anim/rig_blender.py / bake.py), not the clip", worst_deg=round(worst, 3))
    # the round trip: EVERY frame of the bake against the kit's own sampler of the spec (what the engine will play);
    # Blender's cubic/elastic/bounce easings are the same curves, its quaternion lerp is within a degree of slerp
    worst, worst_at = 0.0, None
    if spec:
        expected = C.spec_frames(spec, times, R6_TO_R15)
        for name, fr in expected.items():
            if name not in frames:
                continue
            for i, want in enumerate(fr):
                if i >= len(frames[name]):
                    break
                err = C.quat_angle(want, frames[name][i])
                if err > worst:
                    worst, worst_at = err, f"{name} at {times[i]:.3f} s"
        # Blender interpolates quaternion COMPONENTS (then normalises); the kit and the engine slerp: on a 150-degree
        # swing that is a few degrees mid-segment. Beyond 6 the rig, its axes or the easing are wrong.
        if worst > 6.0:
            return emit("fail", f"bake {a['name']}: the rig does not reproduce the spec - {worst:.2f} degrees off on {worst_at}",
                        "the rig's bone maths, axes or easing are wrong (kit/anim/rig_blender.py / bake.py), not the spec", worst_deg=round(worst, 3))
    rig_name = arm.get("kit_rig", "R15")
    joints = {}
    for n, fr in frames.items():
        # only bones that move (a rest bone would pin its joint): any frame off rest by > 0.01 deg or 0.001 studs
        moving = any(abs(f[3]) < 0.9999999 or any(abs(v) > 1e-3 for v in f[4:7]) for f in fr)
        if moving:
            joints[n] = {"frames": fr}
    events = []
    beats = {}
    for m in sc.timeline_markers:
        t = round((m.frame - sc.frame_start) / fps, 6)
        if m.name.startswith("beat:"):
            beats.setdefault(m.name[5:], []).append(t)
        else:
            name, _, value = m.name.partition(":")
            events.append({"t": t, "name": name, "value": value})
    beats = {k: [min(v), max(v)] for k, v in beats.items() if len(v) >= 2}
    if spec and spec.get("events"):
        events = spec["events"]  # the spec's exact times, not the frame-rounded markers
    clip = {"schema": 1, "name": a["name"], "rig": rig_name, "fps": fps, "duration": times[-1] if times else 0,
            "loop": bool(spec.get("loop")) if spec else False, "priority": (spec or {}).get("priority", "Action"),
            "joints": joints, "times": times, "events": events, "beats": (spec or {}).get("beats") or beats or None,
            "feel": (spec or {}).get("feel"), "source": {"kind": "blender", "file": src, "spec": a["spec"],
                                                          "sha256": sha256_of(a["blend"] or a["spec"] or src),
                                                          "tool_sha256": sha256_of_many([__file__, C.__file__]),
                                                          "rig_sha256": sha256_of(C.rig_path(rig_name))}}
    sword = bpy.data.objects.get("Greatsword")
    if sword is not None and sword.get("kit_blade") is not None and rig_name == "R6":
        # the owner's posed rig with its greatsword (kit/anim/pose_r6.py's file, edited): the sword path for the look and
        # the Hit metric, and the look renders this file as it is
        blade, spacing = float(sword["kit_blade"]), float(sword.get("kit_spacing", 0.75))
        hrp = np.array(arm.data.bones[root_name].matrix_local.translation) if root_name in arm.data.bones else np.zeros(3)
        dg = bpy.context.evaluated_depsgraph_get()
        tips, grips = [], []
        for t in times:
            f = sc.frame_start + t * fps
            sc.frame_set(int(math.floor(f + 1e-9)), subframe=float(f - math.floor(f + 1e-9)))
            dg.update()
            dg.update()
            M = np.array(sword.matrix_world)
            hand, d = M[:3, 3], M[:3, 1] / max(np.linalg.norm(M[:3, 1]), 1e-9)
            grips.append([round(float(v), 4) for v in P3.T @ (hand - d * spacing / 2 - hrp)])
            tips.append([round(float(v), 4) for v in P3.T @ (hand + d * (blade + 0.36) - hrp)])
        clip["sword"] = {"length": blade + 0.36 + spacing / 2, "grip": spacing, "tip": tips, "grip_path": grips}
        clip["source"]["posed"] = True
        clip["source"]["blend"] = src
    if not spec and arm.get("kit_priority") is not None:      # an edited posed file keeps its loop / priority / gates
        clip["loop"] = bool(arm.get("kit_loop", False))
        clip["priority"] = str(arm["kit_priority"])
        if arm.get("kit_gate"):
            clip["gate"] = json.loads(str(arm["kit_gate"]))
    if arm.get("kit_blocking"):                             # the owner's BLOCKING file: every change is a held snap
        clip["stepped"] = [[0.0, round(float(clip["times"][-1]), 4), 1]]
    moving_root = any(abs(f[3]) < 0.9999999 or any(abs(v) > 1e-3 for v in f[4:7]) for f in root_track)
    if moving_root:
        clip["root"] = root_track
    os.makedirs(os.path.dirname(os.path.abspath(a["out"])), exist_ok=True)
    with open(a["out"], "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    return emit("pass", f"baked {a['name']}: {len(joints)} joint(s) x {len(times)} frames at {fps} fps, {len(events)} event(s)"
                + (", root motion" if moving_root else "") + (f", every frame within {worst:.2f} deg of the kit's sampler" if spec else "")
                + f" -> {a['out']}",
                f"lune run kit anim {a['name']} compiles it; look at the strip", clip=a["out"], joints=sorted(joints),
                worst_deg=round(worst, 3), saved=a["save"])


if __name__ == "__main__":
    sys.exit(main())
