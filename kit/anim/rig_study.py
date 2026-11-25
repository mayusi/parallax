"""rig_study.py — HOW every control of the owner's R6 rig moves the character, measured by sweeping it through its range
(the rig as built, nothing re-wired), plus labelled pictures of each state in the rig's own orientation texture.

    blender -b assets/rigs/R6_IK.blend --disable-autoexec --python-exit-code 2 -P kit/anim/rig_study.py -- <out_dir>

Writes <out_dir>/rig_study.json (every sweep, every step: the parts' positions and angles in CHARACTER terms - right,
forward, up - and what slid where) and <out_dir>/pics/*.png (one picture per state, textured, front three-quarter).
Findings are written up in assets/rigs/R6_IK.md ("How each thing moves")."""
import json
import math
import os
import sys

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
PICS = os.path.join(OUT, "pics")
os.makedirs(PICS, exist_ok=True)
rig = bpy.data.objects["Rig1"]
P = rig.pose.bones
B = rig.data.bones
sc = bpy.context.scene
if rig.animation_data:
    rig.animation_data.action = None            # the rig itself, not its rest action

# rest points (Blender world; the character faces +y, right = +x, up = +z)
LEG_TOP = {"Right Leg": Vector((0.5, 0, 2)), "Left Leg": Vector((-0.5, 0, 2))}
LEG_BOT = {"Right Leg": Vector((0.5, 0, 0)), "Left Leg": Vector((-0.5, 0, 0))}
HIP = {"Right Leg": Vector((1, 0, 2)), "Left Leg": Vector((-1, 0, 2))}
ARM_HAND = {"Right Arm": Vector((1.5, 0, 2)), "Left Arm": Vector((-1.5, 0, 2))}
SHOULDER = {"Right Arm": Vector((1, 0, 3.5)), "Left Arm": Vector((-1, 0, 3.5))}
REST = {n: (P[n].location.copy(), P[n].rotation_quaternion.copy(), P[n].rotation_euler.copy(), P[n].scale.copy(), dict(P[n].items()))
        for n in P.keys()}


def settle():
    """the rig shows a SoftIK slider change one evaluation late (a driver cycle: the slider bone is a child of the leg
    it drives) and repeated updates without a change do not re-evaluate: nudge a property the rig clamps away (the
    slider's z, Limit Location z = 0) so a second evaluation runs with the new influence"""
    bpy.context.view_layer.update()
    for side in ("SoftIK.L", "SoftIK.R"):
        P[side].location.z = 1e-5
    bpy.context.view_layer.update()
    for side in ("SoftIK.L", "SoftIK.R"):
        P[side].location.z = 0.0
    bpy.context.view_layer.update()


def reset(ik=True):
    for n, (l, q, e, s, props) in REST.items():
        P[n].location, P[n].rotation_quaternion, P[n].rotation_euler, P[n].scale = l, q, e, s
        for k, v in props.items():
            P[n][k] = v
    set_ik(2.0 if ik else 0.0, fk_box=not ik)


def set_ik(slider, fk_box):
    for side, sign in (("L", 1), ("R", -1)):
        P[f"SoftIK.{side}"]["FK"] = fk_box
        P[f"SoftIK.{side}"].location = Vector((slider * sign, 0, 0))
    settle()


def delta(name):
    return rig.matrix_world @ P[name].matrix @ B[name].matrix_local.inverted()


def r3(v):
    return [round(float(x), 3) for x in v]


def char(v):
    """Blender world vector -> character terms [right, up, forward]"""
    return r3((v.x, v.z, v.y))


def leg_state(leg):
    D = delta(leg)
    top, bot = D @ LEG_TOP[leg], D @ LEG_BOT[leg]
    axis = (top - bot).normalized()
    torso = delta("Torso")
    attached_top = torso @ LEG_TOP[leg]                   # where the leg top would be if the leg rode the torso
    pitch = math.degrees(math.atan2(axis.y, axis.z))       # + = the leg leans forward (top ahead of the foot)
    roll = math.degrees(math.atan2(axis.x, axis.z))        # + = the top leans to the character's right
    fwd = D.to_3x3() @ Vector((0, 1, 0))
    yaw = math.degrees(math.atan2(-fwd.x, fwd.y))          # + = the leg's front turned to the character's LEFT
    return {"sole": char(bot), "top": char(top), "lean_fwd_deg": round(pitch, 1), "lean_right_deg": round(roll, 1),
            "front_yaw_left_deg": round(yaw, 1), "top_off_torso_socket": char(top - attached_top),
            "top_into_torso_studs": round(float(attached_top.z - top.z) * -1, 3)}


def part_state(part, point):
    D = delta(part)
    fwd = D.to_3x3() @ Vector((0, 1, 0))
    up = D.to_3x3() @ Vector((0, 0, 1))
    return {"point": char(D @ point), "front_dir": char(fwd), "up_dir": char(up),
            "yaw_left_deg": round(math.degrees(math.atan2(-fwd.x, fwd.y)), 1)}


def snapshot():
    settle()
    return {"Right Leg": leg_state("Right Leg"), "Left Leg": leg_state("Left Leg"),
            "Torso": part_state("Torso", Vector((0, 0, 3))), "Head": part_state("Head", Vector((0, 0, 4.5))),
            "Right Arm": part_state("Right Arm", ARM_HAND["Right Arm"]), "Left Arm": part_state("Left Arm", ARM_HAND["Left Arm"])}


# ---------------------------------------------------------------- pictures
keep = {"Rig1", "Head", "Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg", "Plane"}
for ob in bpy.data.objects:
    ob.hide_render = ob.name not in keep
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light, sh.color_type = "STUDIO", "TEXTURE"
sh.show_object_outline = True
sc.render.resolution_x, sc.render.resolution_y = 300, 340
sc.render.image_settings.file_format = "PNG"
cd = bpy.data.cameras.new("StudyCam")
cam = bpy.data.objects.new("StudyCam", cd)
sc.collection.objects.link(cam)
cd.lens = 42
sc.camera = cam


def shoot(tag, view="three"):
    pos = {"three": Vector((7.0, 8.5, 4.2)), "side": Vector((11.0, 0.0, 2.8)), "front": Vector((0.0, 11.0, 3.0)),
           "lside": Vector((-11.0, 0.0, 2.8)),
           "top": Vector((0.01, 0.0, 13.0))}[view]
    cam.location = pos
    cam.rotation_euler = (Vector((0, 0, 2.2)) - pos).to_track_quat("-Z", "Y").to_euler()
    settle()
    sc.render.filepath = os.path.join(PICS, f"{tag}.png")
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------- the study
study = {"axes": {}, "sweeps": {}, "notes": []}
for n in ("Main Controller", "Body", "Head.001", "Arm.R", "Arm.L", "Foot.R", "Foot.L", "Knee.R", "Knee.L", "Uleg.R", "Uleg.L",
          "FKLeg.R", "FKLeg.L", "SoftIK.R", "SoftIK.L", "HumanoidRootPart"):
    m = B[n].matrix_local.to_3x3()
    study["axes"][n] = {"local_x": char(m.col[0]), "local_y": char(m.col[1]), "local_z": char(m.col[2]),
                        "rotation_mode": P[n].rotation_mode, "head": char(B[n].head_local), "parent": B[n].parent.name if B[n].parent else None,
                        "inherit_rotation": B[n].use_inherit_rotation}


def sweep(name, values, apply, ik=True, pics=(), view="three"):
    rows = []
    for v in values:
        reset(ik)
        apply(v)
        s = snapshot()
        s["value"] = v
        rows.append(s)
        if v in pics:
            shoot(f"{name}__{v}", view)
    study["sweeps"][name] = rows
    return rows


def loc(bone, axis, v):
    l = Vector(REST[bone][0])
    l[axis] += v
    P[bone].location = l


def rot(bone, axis, deg):
    e = [0.0, 0.0, 0.0]
    e[axis] = math.radians(deg)
    if P[bone].rotation_mode == "QUATERNION":
        P[bone].rotation_quaternion = REST[bone][1] @ Euler(e).to_quaternion()
    else:
        P[bone].rotation_euler = Euler([REST[bone][2][i] + e[i] for i in range(3)], P[bone].rotation_mode)


reset(True)
shoot("rest_ik")
shoot("rest_ik_side", "side")
reset(False)
shoot("rest_fk_as_shipped")
# 1. the body's height with the feet planted (IK): where the legs go
sweep("body_down_ik", [0.3, 0.0, -0.3, -0.6, -0.9, -1.2, -1.5, -1.8], lambda v: loc("Body", 1, v), pics=(0.0, -0.6, -1.2, -1.8))
sweep("body_down_fk", [0.0, -0.6, -1.2], lambda v: loc("Body", 1, v), ik=False, pics=(-1.2,))
# 2. the body forward / sideways
sweep("body_forward_ik", [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5], lambda v: loc("Body", 2, v), pics=(1.0,), view="side")
sweep("body_right_ik", [-1.0, 0.0, 1.0], lambda v: loc("Body", 0, -v), pics=(1.0,), view="front")
# 3. the body's turn / lean / tilt with the feet planted
sweep("body_turn_ik", [-90, -45, 0, 45, 90], lambda v: rot("Body", 1, v), pics=(45, 90), view="three")
sweep("body_lean_ik", [-30, 0, 30, 60], lambda v: rot("Body", 0, -v), pics=(30, 60), view="side")
sweep("body_tilt_ik", [-30, 30], lambda v: rot("Body", 2, v), pics=(30,), view="front")
# 4. a foot: forward / back, sideways, lift, turn
sweep("foot_L_forward", [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0], lambda v: loc("Foot.L", 1, v), pics=(-1.0, 1.0, 2.0), view="lside")
sweep("foot_L_out", [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5], lambda v: loc("Foot.L", 0, -v), pics=(1.0, -0.5), view="front")
sweep("foot_L_lift", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0], lambda v: loc("Foot.L", 2, v), pics=(1.0, 2.0, 3.0), view="lside")
sweep("foot_L_turn", [-60, -30, 0, 30, 60], lambda v: rot("Foot.L", 2, v), pics=(60,), view="three")
sweep("foot_L_below_floor", [0.0, -0.5], lambda v: loc("Foot.L", 2, v))
# 5. the knee pole, with the leg bent (body down 1.0, foot forward 0.8) and straight
for tag, prep in (("bent", lambda: (loc("Body", 1, -1.0),)), ("straight", lambda: None)):
    sweep(f"knee_L_side_{tag}", [-2.0, -1.0, 0.0, 1.0, 2.0],
          lambda v, prep=prep: (prep() if prep else None, loc("Knee.L", 0, -v)), pics=(2.0,) if tag == "bent" else (), view="front")
    sweep(f"knee_L_back_{tag}", [-3.0, -1.0, 0.0, 1.0],
          lambda v, prep=prep: (prep() if prep else None, loc("Knee.L", 1, v)))
# 6. the hip anchor Uleg
sweep("uleg_L_out", [-0.5, 0.0, 0.5, 1.0], lambda v: loc("Uleg.L", 0, -v), pics=(1.0,), view="front")
sweep("uleg_L_forward", [-0.5, 0.0, 0.5, 1.0], lambda v: loc("Uleg.L", 2, v), pics=(1.0,), view="lside")
sweep("uleg_L_up", [-0.5, 0.0, 0.5], lambda v: loc("Uleg.L", 1, v))
# 7. the soft IK slider: FK leg swung forward 40, IK foot back 1 - the leg between them
def soft(v):
    rot("FKLeg.L", 0, 40)
    loc("Foot.L", 1, -1.0)
    set_ik(v, fk_box=True)
sweep("softik_L_blend", [0.0, 0.5, 1.0, 1.5, 2.0], soft, pics=(0.0, 1.0, 2.0), view="lside")
# 8. the FK checkbox off with the slider at 0: the "Unparented" world leg, body moved
def unparented(v):
    set_ik(0.0, fk_box=False)
    loc("Body", 2, v)
sweep("unparented_body_forward", [0.0, 1.0], unparented, ik=False, pics=(1.0,), view="lside")
# 9. the head with the body turned (Head.001 does not inherit rotation)
sweep("head_body_turn", [0, 45, 90], lambda v: rot("Body", 1, v), pics=(90,), view="three")
# 10. the arm channels
for a in ("Arm.R",):
    for axis, lab in ((0, "x"), (1, "y"), (2, "z")):
        sweep(f"{a}_rot_{lab}", [-90, -45, 0, 45, 90], lambda v, a=a, axis=axis: rot(a, axis, v), pics=(90,) if axis != 1 else (), view="three")
    sweep(f"{a}_slide_y", [0.0, 0.5], lambda v, a=a: loc(a, 1, v))
# 11. the head channels
for axis, lab in ((0, "x"), (1, "y"), (2, "z")):
    sweep(f"Head.001_rot_{lab}", [-45, 0, 45], lambda v, axis=axis: rot("Head.001", axis, v))
# 12. the main controller
sweep("main_turn", [0, 90], lambda v: rot("Main Controller", 1, v), pics=(90,), view="three")
sweep("main_move_forward", [0, 2], lambda v: loc("Main Controller", 2, -v))
# 13. FK leg channels (shipped mode)
for axis, lab in ((0, "x"), (1, "y"), (2, "z")):
    sweep(f"FKLeg.L_rot_{lab}", [-45, 0, 45], lambda v, axis=axis: rot("FKLeg.L", axis, v), ik=False)
reset(True)
with open(os.path.join(OUT, "rig_study.json"), "w", encoding="utf-8") as fh:
    json.dump(study, fh, indent=1)
print("RIG_STUDY_DONE", OUT)
