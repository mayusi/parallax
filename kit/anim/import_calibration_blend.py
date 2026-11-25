"""import_calibration_blend.py — run INSIDE Blender by kit/anim/frame_contract.py (the import route's calibration):
    blender -b --factory-startup --python-exit-code 2 -P kit/anim/import_calibration_blend.py -- <out.glb> [--mirror] [--scale S]

A small humanoid skeleton with the Unreal mannequin's bone names (one of the families kit/anim/retarget.py knows),
standing in Blender's own convention (Z up, facing -Y, its right on -X), arms hanging, toes ahead, and five poses one
a frame (frames 1..5) whose result can be said by hand:
  1  rest
  2  the right upper arm lifted 90 degrees ahead
  3  the left upper arm lifted 90 degrees out to the LEFT
  4  the head turned 90 degrees to the left
  5  the pelvis 0.2 up, the right thigh 45 degrees ahead
Written as a .glb (the route's own import path), its action named "Calibration".
  --mirror   the left and right bones' NAMES swapped (a skeleton whose labels lie): the route cannot know, and the
             calibration must say the result is wrong
  --scale S  every length times S (a centimetre file: 100): the route measures the body's height and must not care
  --turn D   the whole skeleton turned D degrees about the vertical (it faces another way in its file): the route
             finds "ahead" from the toes and must not care
  --splay D  each foot turned D degrees OUT (a body standing toe-out, as real mocap stands): must not matter
  --tpose    the arms built straight out to the sides (a T-posed rig); the poses then aim the arms at the same
             places (ahead, out to the left) - the route lowers a T rest to hanging by itself"""
import math
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
MIRROR = "--mirror" in argv
SCALE = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 1.0
TURN = float(argv[argv.index("--turn") + 1]) if "--turn" in argv else 0.0
SPLAY = float(argv[argv.index("--splay") + 1]) if "--splay" in argv else 0.0
TPOSE = "--tpose" in argv

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps, sc.render.fps_base = 30, 1.0

# (name, head, tail, parent) in metres; the character's RIGHT is -X, AHEAD is -Y
R, L = -1.0, 1.0
BONES = [
    ("pelvis", (0, 0, 0.95), (0, 0, 1.10), None),
    ("spine_03", (0, 0, 1.10), (0, 0, 1.50), "pelvis"),
    ("Head", (0, 0, 1.55), (0, 0, 1.75), "spine_03"),
    # (an end bone at the head's top: a .glb keeps no bone lengths, and the importer guesses a leaf bone's - the
    # head came back twice as long and the body 0.2 m taller)
    ("head_end", (0, 0, 1.75), (0, 0, 1.80), "Head"),
]
for side, sx in (("r", R), ("l", L)):
    sp = math.radians(SPLAY) * (-sx)                      # (a foot turned OUT: the right's toes toward -X, the left's +X)
    toe = (0.10 * sx - 0.12 * math.sin(sp), -0.12 * math.cos(sp), 0.02)
    tip = (0.10 * sx - 0.20 * math.sin(sp), -0.20 * math.cos(sp), 0.02)
    if TPOSE:
        BONES += [
            (f"upperarm_{side}", (0.20 * sx, 0, 1.45), (0.50 * sx, 0, 1.45), "spine_03"),
            (f"lowerarm_{side}", (0.50 * sx, 0, 1.45), (0.77 * sx, 0, 1.45), f"upperarm_{side}"),
            (f"hand_{side}", (0.77 * sx, 0, 1.45), (0.87 * sx, 0, 1.45), f"lowerarm_{side}"),
        ]
    else:
        BONES += [
            (f"upperarm_{side}", (0.20 * sx, 0, 1.45), (0.20 * sx, 0, 1.15), "spine_03"),
            (f"lowerarm_{side}", (0.20 * sx, 0, 1.15), (0.20 * sx, 0, 0.88), f"upperarm_{side}"),
            (f"hand_{side}", (0.20 * sx, 0, 0.88), (0.20 * sx, 0, 0.78), f"lowerarm_{side}"),
        ]
    BONES += [
        (f"thigh_{side}", (0.10 * sx, 0, 0.95), (0.10 * sx, 0, 0.52), "pelvis"),
        (f"calf_{side}", (0.10 * sx, 0, 0.52), (0.10 * sx, 0, 0.10), f"thigh_{side}"),
        (f"foot_{side}", (0.10 * sx, 0, 0.10), toe, f"calf_{side}"),
        (f"ball_{side}", toe, tip, f"foot_{side}"),
    ]


def named(n):
    """--mirror: the right bones carry the left names and the other way round"""
    if not MIRROR:
        return n
    if n.endswith("_r"):
        return n[:-2] + "_l"
    if n.endswith("_l"):
        return n[:-2] + "_r"
    return n


data = bpy.data.armatures.new("Calibration")
arm = bpy.data.objects.new("Calibration", data)
sc.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
for name, head, tail, parent in BONES:
    eb = data.edit_bones.new(named(name))
    eb.head = Vector(head) * SCALE
    eb.tail = Vector(tail) * SCALE
    if parent:
        eb.parent = data.edit_bones[named(parent)]
        eb.use_connect = False
bpy.ops.object.mode_set(mode="POSE")

act = bpy.data.actions.new("Calibration")
arm.animation_data_create()
arm.animation_data.action = act


def turn(bone, world):
    """give the pose bone a turn that is `world` in the armature's axes (about the bone's own head)"""
    pb = arm.pose.bones[named(bone)]
    B = arm.data.bones[named(bone)].matrix_local.to_3x3()
    local = B.inverted() @ world @ B
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = local.to_quaternion()


def aim(bone, target):
    """turn the bone (the shortest way) so it points at the world direction `target` - the same place whatever its
    rest (hanging or a T)"""
    b = arm.data.bones[named(bone)]
    v = (b.tail_local - b.head_local).normalized()
    turn(bone, v.rotation_difference(Vector(target).normalized()).to_matrix())


def rest_all():
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)


def key(frame):
    for pb in arm.pose.bones:
        pb.keyframe_insert("rotation_quaternion", frame=frame)
        pb.keyframe_insert("location", frame=frame)


POSES = [
    lambda: None,
    lambda: aim("upperarm_r", (0, -1, 0)) if TPOSE else turn("upperarm_r", Matrix.Rotation(math.radians(-90), 3, "X")),
    lambda: aim("upperarm_l", (1, 0, 0)) if TPOSE else turn("upperarm_l", Matrix.Rotation(math.radians(-90), 3, "Y")),
    lambda: turn("Head", Matrix.Rotation(math.radians(90), 3, "Z")),            # facing -Y -> its left +X
    None,
]


def pose5():
    pb = arm.pose.bones["pelvis"]
    B = arm.data.bones["pelvis"].matrix_local.to_3x3()
    pb.location = B.inverted() @ Vector((0, 0, 0.2 * SCALE))                    # (a pose bone's location is in its own axes)
    turn("thigh_r", Matrix.Rotation(math.radians(-45), 3, "X"))                 # hanging -Z -> 45 degrees ahead


POSES[4] = pose5
for i, pose in enumerate(POSES):
    rest_all()
    pose()
    key(i + 1)
for fc in getattr(act, "fcurves", []) or []:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"
sc.frame_start, sc.frame_end = 1, len(POSES)
bpy.ops.object.mode_set(mode="OBJECT")
arm.rotation_euler = (0, 0, math.radians(TURN))
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_animations=True)
print(f"calibration skeleton written: {OUT} (mirror={MIRROR}, scale={SCALE}, turn={TURN}, splay={SPLAY}, tpose={TPOSE})")
