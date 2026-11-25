"""EVERYTHING in the owner's R6 rig file, as data: scenes, collections, objects, meshes, materials, armatures, every
bone (rest, roll, flags, collections, custom shapes), every pose bone (channels, locks, limits, custom props with UI
data), every constraint with ALL its RNA properties, every driver (expression, variables, validity), every action
(slots, fcurves, every keyframe), NLA, cameras, text blocks, the Roblox plugin's metadata - then a FUNCTIONAL probe:
each control moved / turned, and which part bones follow and how.

    blender -b "<rig.blend>" --disable-autoexec --python-exit-code 2 -P kit/anim/rig_dump.py -- <out_dir>

Written for the owner's R6 rig (its findings: assets/rigs/R6_IK.md); the static dump works on any rig, the functional
probe expects the part bones (HumanoidRootPart, Torso, Head, arms, legs) and the SoftIK switch of that rig.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
os.makedirs(OUT, exist_ok=True)
PARTS = ["HumanoidRootPart", "Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]


def r(v, n=4):
    if isinstance(v, float):
        return round(v, n)
    return v


def vec(v, n=4):
    return [round(float(x), n) for x in v]


def mat(m, n=4):
    return [vec(row, n) for row in m]


def rna(obj, skip=()):
    """every non-pointer RNA property of a datablock / struct, pointers by name"""
    out = {}
    for p in obj.bl_rna.properties:
        k = p.identifier
        if k in ("rna_type",) or k in skip:
            continue
        try:
            v = getattr(obj, k)
        except Exception:  # noqa: BLE001
            continue
        if p.type == "POINTER":
            out[k] = getattr(v, "name", None) if v is not None else None
        elif p.type == "COLLECTION":
            try:
                out[k] = [getattr(x, "name", str(x)) for x in v][:50]
            except Exception:  # noqa: BLE001
                pass
        elif p.type in ("FLOAT", "INT", "BOOLEAN") and getattr(p, "array_length", 0):
            try:
                out[k] = [r(float(x)) if p.type == "FLOAT" else x for x in v]
            except Exception:  # noqa: BLE001
                out[k] = str(v)
        elif p.type == "FLOAT":
            out[k] = r(v)
        else:
            out[k] = v if isinstance(v, (int, bool, str)) or v is None else str(v)
    return out


def idprops(owner):
    out = {}
    for k in owner.keys():
        v = owner[k]
        try:
            ui = owner.id_properties_ui(k).as_dict()
        except Exception:  # noqa: BLE001
            ui = None
        if hasattr(v, "to_dict"):
            v = v.to_dict()
        elif hasattr(v, "to_list"):
            v = v.to_list()
        out[k] = {"value": v if isinstance(v, (int, float, str, bool, list, dict)) else str(v), "ui": ui}
    return out


def drivers_of(idblock):
    ad = getattr(idblock, "animation_data", None)
    if not ad:
        return []
    out = []
    for fc in ad.drivers:
        d = fc.driver
        out.append({"data_path": fc.data_path, "index": fc.array_index, "type": d.type, "expression": d.expression,
                    "is_valid": d.is_valid, "is_simple_expression": d.is_simple_expression, "use_self": d.use_self,
                    "fcurve_valid": fc.is_valid, "modifiers": [m.type for m in fc.modifiers],
                    "keyframes": [vec(k.co) for k in fc.keyframe_points],
                    "variables": [{"name": v.name, "type": v.type, "is_name_valid": v.is_name_valid,
                                   "targets": [{"id": t.id.name if t.id else None, "id_type": t.id_type, "data_path": t.data_path,
                                                "bone_target": t.bone_target, "transform_type": t.transform_type,
                                                "transform_space": t.transform_space, "rotation_mode": t.rotation_mode}
                                               for t in v.targets]} for v in d.variables]})
    return out


def fcurves_of_action(act):
    curves = []
    try:
        for layer in act.layers:
            for strip in layer.strips:
                for slot in act.slots:
                    bag = strip.channelbag(slot)
                    if bag:
                        curves += [(slot.name_display, fc) for fc in bag.fcurves]
    except Exception:  # noqa: BLE001  (legacy actions)
        curves = [("", fc) for fc in act.fcurves]
    return curves


data = {"file": bpy.data.filepath, "version_saved": list(bpy.data.version), "blender": bpy.app.version_string}
sc = bpy.context.scene
data["scenes"] = [{"name": s.name, "fps": s.render.fps, "fps_base": r(s.render.fps_base), "frame_start": s.frame_start,
                   "frame_end": s.frame_end, "frame_current": s.frame_current, "camera": s.camera.name if s.camera else None,
                   "unit_system": s.unit_settings.system, "scale_length": r(s.unit_settings.scale_length),
                   "length_unit": s.unit_settings.length_unit, "render_engine": s.render.engine,
                   "resolution": [s.render.resolution_x, s.render.resolution_y],
                   "markers": [(m.name, m.frame) for m in s.timeline_markers], "idprops": idprops(s),
                   "view_layers": [v.name for v in s.view_layers]} for s in bpy.data.scenes]


def coll_tree(c):
    return {"name": c.name, "hide_viewport": c.hide_viewport, "hide_render": c.hide_render,
            "objects": [o.name for o in c.objects], "children": [coll_tree(ch) for ch in c.children]}


data["collections"] = coll_tree(sc.collection)
data["objects"] = []
for o in bpy.data.objects:
    rec = {"name": o.name, "type": o.type, "data": o.data.name if o.data else None,
           "parent": o.parent.name if o.parent else None, "parent_type": o.parent_type, "parent_bone": o.parent_bone,
           "location": vec(o.location), "rotation_mode": o.rotation_mode, "rotation_euler": vec(o.rotation_euler),
           "rotation_quaternion": vec(o.rotation_quaternion), "scale": vec(o.scale), "matrix_world": mat(o.matrix_world),
           "matrix_parent_inverse": mat(o.matrix_parent_inverse), "hide_viewport": o.hide_viewport, "hide_render": o.hide_render,
           "hide_select": o.hide_select, "display_type": o.display_type, "show_in_front": o.show_in_front,
           "empty_display_type": o.empty_display_type if o.type == "EMPTY" else None,
           "empty_display_size": r(o.empty_display_size) if o.type == "EMPTY" else None,
           "collections": [c.name for c in o.users_collection], "idprops": idprops(o),
           "modifiers": [rna(m) for m in o.modifiers], "constraints": [rna(c) for c in o.constraints],
           "drivers": drivers_of(o),
           "action": o.animation_data.action.name if o.animation_data and o.animation_data.action else None,
           "nla": [{"track": t.name, "mute": t.mute, "strips": [(s.name, s.action.name if s.action else None, vec((s.frame_start, s.frame_end)))
                                                                 for s in t.strips]} for t in (o.animation_data.nla_tracks if o.animation_data else [])]}
    if o.type == "MESH":
        me = o.data
        ws = [o.matrix_world @ v.co for v in me.vertices]
        rec["mesh"] = {"verts": len(me.vertices), "faces": len(me.polygons), "edges": len(me.edges),
                       "local_bounds": [vec([min(v.co[i] for v in me.vertices) for i in range(3)]), vec([max(v.co[i] for v in me.vertices) for i in range(3)])] if me.vertices else None,
                       "world_bounds": [vec([min(w[i] for w in ws) for i in range(3)]), vec([max(w[i] for w in ws) for i in range(3)])] if ws else None,
                       "uv_layers": [u.name for u in me.uv_layers], "vertex_groups": [g.name for g in o.vertex_groups],
                       "materials": [m.name if m else None for m in me.materials], "shape_keys": [k.name for k in me.shape_keys.key_blocks] if me.shape_keys else [],
                       "idprops": idprops(me)}
    if o.type == "CAMERA":
        cd = o.data
        rec["camera"] = {"type": cd.type, "lens": r(cd.lens), "sensor_width": r(cd.sensor_width), "sensor_fit": cd.sensor_fit,
                         "angle_deg": r(math.degrees(cd.angle)), "angle_y_deg": r(math.degrees(cd.angle_y)), "clip": [r(cd.clip_start), r(cd.clip_end)],
                         "drivers": drivers_of(cd), "idprops": idprops(cd)}
    if o.type == "ARMATURE":
        arm = o.data
        rec["armature"] = {"display_type": arm.display_type, "pose_position": arm.pose_position, "show_axes": arm.show_axes,
                           "idprops": idprops(arm), "drivers": drivers_of(arm),
                           "collections": [{"name": c.name, "is_visible": c.is_visible, "is_solo": getattr(c, "is_solo", None),
                                            "parent": c.parent.name if c.parent else None, "bones": [b.name for b in c.bones]}
                                           for c in arm.collections_all]}
        bones = []
        for b in arm.bones:
            pb = o.pose.bones[b.name]
            bones.append({
                "name": b.name, "parent": b.parent.name if b.parent else None, "children": [c.name for c in b.children],
                "head_local": vec(b.head_local), "tail_local": vec(b.tail_local), "length": r(b.length),
                "matrix_local": mat(b.matrix_local),
                "roll_axes": {"x": vec(b.matrix_local.col[0][:3]), "y": vec(b.matrix_local.col[1][:3]), "z": vec(b.matrix_local.col[2][:3])},
                "use_deform": b.use_deform, "use_connect": b.use_connect, "use_inherit_rotation": b.use_inherit_rotation,
                "inherit_scale": b.inherit_scale, "use_local_location": b.use_local_location, "use_relative_parent": b.use_relative_parent,
                "hide": b.hide, "bbone_segments": b.bbone_segments, "envelope_distance": r(b.envelope_distance),
                "collections": [c.name for c in b.collections], "bone_idprops": idprops(b),
                "pose": {"rotation_mode": pb.rotation_mode, "location": vec(pb.location), "rotation_quaternion": vec(pb.rotation_quaternion),
                         "rotation_euler": vec(pb.rotation_euler), "scale": vec(pb.scale),
                         "lock_location": list(pb.lock_location), "lock_rotation": list(pb.lock_rotation), "lock_rotation_w": pb.lock_rotation_w,
                         "lock_scale": list(pb.lock_scale), "lock_rotations_4d": pb.lock_rotations_4d,
                         "custom_shape": pb.custom_shape.name if pb.custom_shape else None,
                         "custom_shape_scale": vec(pb.custom_shape_scale_xyz), "custom_shape_translation": vec(pb.custom_shape_translation),
                         "custom_shape_rotation": vec(pb.custom_shape_rotation_euler), "custom_shape_transform": pb.custom_shape_transform.name if pb.custom_shape_transform else None,
                         "use_custom_shape_bone_size": pb.use_custom_shape_bone_size,
                         "ik": {"lock": [pb.lock_ik_x, pb.lock_ik_y, pb.lock_ik_z], "stiffness": [r(pb.ik_stiffness_x), r(pb.ik_stiffness_y), r(pb.ik_stiffness_z)],
                                "use_limit": [pb.use_ik_limit_x, pb.use_ik_limit_y, pb.use_ik_limit_z],
                                "limits_deg": [[r(math.degrees(pb.ik_min_x)), r(math.degrees(pb.ik_max_x))], [r(math.degrees(pb.ik_min_y)), r(math.degrees(pb.ik_max_y))],
                                               [r(math.degrees(pb.ik_min_z)), r(math.degrees(pb.ik_max_z))]], "stretch": r(pb.ik_stretch)},
                         "idprops": idprops(pb), "color_palette": getattr(pb.color, "palette", None) if hasattr(pb, "color") else None,
                         "constraints": [rna(c) for c in pb.constraints]}})
        rec["bones"] = bones
    data["objects"].append(rec)
data["actions"] = []
for act in bpy.data.actions:
    curves = []
    for slot_name, fc in fcurves_of_action(act):
        curves.append({"slot": slot_name, "data_path": fc.data_path, "index": fc.array_index, "group": fc.group.name if fc.group else None,
                       "extrapolation": fc.extrapolation, "modifiers": [m.type for m in fc.modifiers],
                       "keys": [{"co": vec(k.co), "interp": k.interpolation, "easing": k.easing, "hl": vec(k.handle_left), "hr": vec(k.handle_right)}
                                for k in fc.keyframe_points]})
    data["actions"].append({"name": act.name, "users": act.users, "fake_user": act.use_fake_user, "frame_range": vec(act.frame_range),
                            "slots": [s.name_display for s in getattr(act, "slots", [])], "fcurves": curves, "idprops": idprops(act)})
data["texts"] = [{"name": t.name, "lines": len(t.lines), "use_module": t.use_module, "body": t.as_string()[:4000]} for t in bpy.data.texts]
data["materials"] = [{"name": m.name, "users": m.users, "diffuse": vec(m.diffuse_color), "use_nodes": m.use_nodes,
                      "nodes": [n.bl_idname for n in m.node_tree.nodes] if m.use_nodes and m.node_tree else []} for m in bpy.data.materials]
data["images"] = [{"name": i.name, "filepath": i.filepath, "size": list(i.size), "packed": bool(i.packed_file)} for i in bpy.data.images]
data["worlds"] = [w.name for w in bpy.data.worlds]
data["library_counts"] = {k: len(getattr(bpy.data, k)) for k in ("objects", "meshes", "armatures", "actions", "materials", "images", "texts",
                                                                  "node_groups", "cameras", "lights", "collections", "scenes", "libraries", "worlds")}
with open(os.path.join(OUT, "rig_full.json"), "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=1, default=str)

# ------------------------------------------------------------------ the FUNCTIONAL probe
rig = bpy.data.objects["Rig1"]
P = rig.pose.bones


def settle():
    bpy.context.view_layer.update()
    bpy.context.view_layer.update()


def snapshot():
    settle()
    out = {}
    for n in PARTS:
        m = rig.matrix_world @ P[n].matrix
        out[n] = m.copy()
    for ob in bpy.data.objects:
        if ob.parent == rig and ob.type == "MESH":
            out["mesh:" + ob.name] = ob.matrix_world.copy()
    return out


def diff(a, b):
    res = {}
    for k in a:
        dt = (b[k].translation - a[k].translation)
        q = a[k].to_quaternion().rotation_difference(b[k].to_quaternion())
        ang = math.degrees(q.angle)
        if dt.length > 1e-4 or ang > 0.01:
            axis = vec(q.axis, 3) if ang > 0.01 else None
            res[k] = {"move": vec(dt, 3), "turn_deg": round(ang, 2), "axis_world": axis}
    return res


rest_state = {}
for n in P.keys():
    rest_state[n] = (P[n].location.copy(), P[n].rotation_quaternion.copy(), P[n].rotation_euler.copy(), P[n].scale.copy(), dict(P[n].items()))
if rig.animation_data:
    rig.animation_data.action = None          # the probe sees the rig itself, not the file's own action


def reset():
    for n, (l, q, e, s, props) in rest_state.items():
        P[n].location, P[n].rotation_quaternion, P[n].rotation_euler, P[n].scale = l, q, e, s
        for k, v in props.items():
            P[n][k] = v
    settle()


def set_mode(ik):
    for side, sign in (("L", 1), ("R", -1)):
        P[f"SoftIK.{side}"]["FK"] = not ik
        P[f"SoftIK.{side}"].location = Vector((2.0 * sign if ik else 0.0, 0, 0))
    settle()


probe = {"modes": {}}
controls = [b.name for b in rig.data.bones if not any(c.name in ("Layer 24", "Layer 2") for c in b.collections) and b.name not in PARTS]
for mode in ("FK", "IK"):
    reset()
    set_mode(mode == "IK")
    base = snapshot()
    res = {}
    for name in controls:
        pb = P[name]
        for kind, axis, amount in (("loc", 0, 0.5), ("loc", 1, 0.5), ("loc", 2, 0.5), ("rot", 0, 30), ("rot", 1, 30), ("rot", 2, 30)):
            reset()
            set_mode(mode == "IK")
            if kind == "loc":
                v = Vector((0, 0, 0))
                v[axis] = amount
                pb.location = pb.location + v
            else:
                e = [0.0, 0.0, 0.0]
                e[axis] = math.radians(amount)
                q = Euler(e).to_quaternion()
                if pb.rotation_mode == "QUATERNION":
                    pb.rotation_quaternion = pb.rotation_quaternion @ q
                elif pb.rotation_mode == "AXIS_ANGLE":
                    continue
                else:
                    pb.rotation_euler = Euler([pb.rotation_euler[i] + e[i] for i in range(3)], pb.rotation_mode)
            d = diff(base, snapshot())
            parts = {k: v for k, v in d.items() if k in PARTS}
            res[f"{name} {kind} local-{'xyz'[axis]} {amount}"] = parts
    probe["modes"][mode] = res
# what the switches do
reset()
switch = {}
for side in ("L", "R"):
    for fk in (True, False):
        for slider in (0.0, 1.0, 2.0):
            reset()
            P[f"SoftIK.{side}"]["FK"] = fk
            P[f"SoftIK.{side}"].location = Vector((slider * (1 if side == "L" else -1), 0, 0))
            P["Body"].location = Vector((0, -0.6, 0))           # a crouch: what the legs do under it
            settle()
            leg = "Left Leg" if side == "L" else "Right Leg"
            m = rig.matrix_world @ P[leg].matrix
            l1 = P[f"Leg.{side}1"]
            switch[f"SoftIK.{side} FK={fk} slider={slider}"] = {
                "leg_pivot": vec(m.translation, 3), "leg_rot_deg_xyz": [round(math.degrees(a), 1) for a in m.to_euler("XYZ")],
                "Leg1_constraints": [(c.name, c.enabled, round(c.influence, 3)) for c in l1.constraints]}
probe["switches_under_crouch_0.6"] = switch
reset()
with open(os.path.join(OUT, "rig_probe.json"), "w", encoding="utf-8") as fh:
    json.dump(probe, fh, indent=1, default=str)
print("RIG_DUMP_DONE", OUT)
