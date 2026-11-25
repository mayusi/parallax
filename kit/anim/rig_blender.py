"""rig_blender.py — the kit's ANIMATION RIG in Blender, built from the engine's own data (kit/anim/rigs/<rig>.json):
    blender -b --factory-startup --python-exit-code 2 -P kit/anim/rig_blender.py -- <rig> <out.blend>

One deform bone per Roblox part, named exactly as the part, its head on the engine-read joint pivot (the rig attachment
/ Motor6D C0 in root space), pointing down the limb toward the next pivot; the body as one box mesh (every part a box
of its engine size) skinned to the bones with vertex groups, so the rig deforms as the avatar does and exports as a
skinned mesh. IK on the arms and legs: a target bone per hand and foot (IK_<part>) with a pole, switched per limb
through the armature's custom properties (ik_RightHand .. = 1 IK, 0 FK). Roblox axes (x right, y up, -z forward) map
to Blender's (x, -z, y) exactly as the 3D pipeline's rbx.py does (BL_FROM_RBX).
kit/anim/bake.py reads this rig's pose back into a clip; nothing here is typed by hand.
"""

import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

# Roblox -> Blender: (x, y, z) -> (x, -z, y)
BL_FROM_RBX = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
IK_CHAINS = {  # effector part -> (chain root part, pole offset in Roblox axes: knees forward, elbows back)
    "RightHand": ("RightUpperArm", (0, 0, 1.5)), "LeftHand": ("LeftUpperArm", (0, 0, 1.5)),
    "RightFoot": ("RightUpperLeg", (0, 0, -1.5)), "LeftFoot": ("LeftUpperLeg", (0, 0, -1.5)),
    "Right Arm": (None, None), "Left Arm": (None, None), "Right Leg": (None, None), "Left Leg": (None, None),
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def cf(c):
    m = np.eye(4)
    m[:3, 3] = c[:3]
    m[:3, :3] = np.array(c[3:], dtype=float).reshape(3, 3)
    return m


def to_bl(m4):
    """a root-space Roblox 4x4 -> a Blender matrix"""
    return BL_FROM_RBX @ Matrix(m4.tolist()) @ BL_FROM_RBX.inverted()


def load_rig(name):
    path = os.path.join("kit", "anim", "rigs", str(name).lower() + ".json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def rest_world(rig):
    """every part's rest CFrame in root space (the engine's offsets) + every joint's pivot (parent * C0)"""
    world = {part: cf(rig["rest"][part]) for part in rig["rest"]}
    pivots = {}
    for part in rig["order"]:
        j = rig["joints"][part]
        pivots[part] = (world[j["parent"]] @ cf(j["c0"]))[:3, 3]
    return world, pivots


def children_of(rig):
    kids = {}
    for part in rig["order"]:
        kids.setdefault(rig["joints"][part]["parent"], []).append(part)
    return kids


def build(rig_name, out_path):
    rig = load_rig(rig_name)
    world, pivots = rest_world(rig)
    kids = children_of(rig)
    root = rig["root"]
    sc = bpy.context.scene
    for o in list(sc.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    # ---------------------------------------------------------------- armature
    arm_data = bpy.data.armatures.new(f"{rig['rig']}_rig")
    arm = bpy.data.objects.new(f"{rig['rig']}_rig", arm_data)
    sc.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    heads = {}
    # the root bone: at the root part's centre, pointing up
    rb = eb.new(root)
    rp = Vector(world[root][:3, 3].tolist())
    rb.head = BL_FROM_RBX @ rp
    rb.tail = BL_FROM_RBX @ (rp + Vector((0, 0.5, 0)))
    heads[root] = rp
    for part in rig["order"]:
        b = eb.new(part)
        head = Vector(pivots[part].tolist())
        centre = Vector(world[part][:3, 3].tolist())
        child = [c for c in kids.get(part, []) if c in pivots]
        if len(child) == 1:
            tail = Vector(pivots[child[0]].tolist())
        else:
            d = centre - head
            if d.length < 0.15:
                d = Vector((0, rig["sizes"][part][1] / 2, 0))
            else:
                d = d.normalized() * max(d.length * 2, 0.25)
            tail = head + d
        if (tail - head).length < 0.05:
            tail = head + Vector((0, 0.25, 0))
        b.head = BL_FROM_RBX @ head
        b.tail = BL_FROM_RBX @ tail
        b.parent = eb[rig["joints"][part]["parent"]]
        b.use_connect = False
        b.use_deform = True
        try:
            b.align_roll(Vector((0, -1, 0)))  # the bone's Z toward the character's back (cosmetic: the bake uses matrices)
        except Exception:  # noqa: BLE001
            pass
        heads[part] = head
    # IK targets: a free bone at each hand / foot, a pole bone in front of the knee / behind the elbow
    ik_made = []
    for eff, (chain_root, pole_off) in IK_CHAINS.items():
        if eff not in rig["joints"] or chain_root is None:
            continue
        mid = rig["joints"][eff]["parent"]  # the lower arm / leg
        if rig["joints"][mid]["parent"] != chain_root:
            continue
        t = eb.new(f"IK_{eff}")
        p = Vector(pivots[eff].tolist())
        t.head = BL_FROM_RBX @ p
        t.tail = BL_FROM_RBX @ (p + Vector((0, -0.3, 0)))
        t.use_deform = False
        pl = eb.new(f"POLE_{eff}")
        q = Vector(pivots[mid].tolist()) + Vector(pole_off)
        pl.head = BL_FROM_RBX @ q
        pl.tail = BL_FROM_RBX @ (q + Vector((0, 0.25, 0)))
        pl.use_deform = False
        ik_made.append(eff)
    bpy.ops.object.mode_set(mode="POSE")
    for eff in ik_made:
        mid = rig["joints"][eff]["parent"]
        pb = arm.pose.bones[mid]
        con = pb.constraints.new("IK")
        con.target = arm
        con.subtarget = f"IK_{eff}"
        con.pole_target = arm
        con.pole_subtarget = f"POLE_{eff}"
        con.chain_count = 2
        con.use_tail = True
        prop = f"ik_{eff}"
        arm[prop] = 0.0  # FK by default: the bake and the spec drive FK; an animator flips it to 1
        drv = con.driver_add("influence").driver
        drv.type = "SCRIPTED"
        var = drv.variables.new()
        var.name = "ik"
        var.type = "SINGLE_PROP"
        var.targets[0].id = arm
        var.targets[0].data_path = f'["{prop}"]'
        drv.expression = "ik"
    bpy.ops.object.mode_set(mode="OBJECT")
    arm["kit_rig"] = rig["rig"]
    arm["kit_root"] = root
    arm.show_in_front = True
    # ---------------------------------------------------------------- the body: one box per part, skinned
    verts, faces, groups = [], [], {}
    for part in [root] + rig["order"]:
        if part not in rig["sizes"]:
            continue
        sx, sy, sz = (s / 2 for s in rig["sizes"][part])
        m = to_bl(world[part])
        base = len(verts)
        for x in (-sx, sx):
            for y in (-sy, sy):
                for z in (-sz, sz):
                    v = m @ (BL_FROM_RBX @ Vector((x, y, z)) - BL_FROM_RBX @ Vector((0, 0, 0)))
                    verts.append(v)
        groups[part] = list(range(base, base + 8))
        faces += [[base + a for a in f] for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))]
    mesh = bpy.data.meshes.new("Body")
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    body = bpy.data.objects.new("Body", mesh)
    sc.collection.objects.link(body)
    for part, idx in groups.items():
        vg = body.vertex_groups.new(name=part)
        vg.add(idx, 1.0, "REPLACE")
    body.parent = arm
    mod = body.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    body["kit_rig"] = rig["rig"]
    sc.render.fps = 30
    sc.frame_start, sc.frame_end = 1, 30
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path), compress=True)
    return rig, ik_made


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(a) < 2:
        return emit("fail", "rig_blender: needs <rig> <out.blend>", "lune run kit anim rig r15 --blend")
    rig, ik = build(a[0], a[1])
    return emit("pass", f"rig {rig['rig']}: {len(rig['order'])} deform bones from the engine's pivots, IK on {', '.join(ik) or 'nothing'} -> {a[1]}",
                f"open {a[1]} in Blender to animate (ik_<Hand|Foot> = 1 for IK), or: lune run kit anim bake <Name> --spec",
                blend=a[1], bones=rig["order"], ik=ik)


if __name__ == "__main__":
    sys.exit(main())
