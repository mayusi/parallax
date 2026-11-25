"""cutscene_r6.py — Blender side of kit/anim/cutscene.py: renders a planned scene (scene.json) with SEVERAL copies of the
owner's R6 rig (assets/rigs/R6_IK.blend), each driven on its controllers exactly like kit/anim/look_r6.py (and held to
the same fidelity gate), plus the teleport / impact effects and the planned camera.

    blender -b assets/rigs/R6_IK.blend --disable-autoexec --python-exit-code 2 -P kit/anim/cutscene_r6.py -- <scene.json>
-> <out>/frames/00000.png ... and <out>/<name>.blend (the posed scene, to scrub or edit in Blender)"""
import json
import math
import os
import shutil
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C        # noqa: E402
import look             # noqa: E402
from look_r6 import B, CONTROL, PARTS, part_deltas  # noqa: E402

LOOKS = {
    # the classic R6 look every Roblox player reads
    "noob": {"Head": (0.96, 0.80, 0.19), "Right Arm": (0.96, 0.80, 0.19), "Left Arm": (0.96, 0.80, 0.19),
             "Torso": (0.05, 0.41, 0.67), "Right Leg": (0.64, 0.74, 0.27), "Left Leg": (0.64, 0.74, 0.27)},
    # the attacker: near-black with a violet torso (reads as a silhouette against the arena, ties to the teleport colour)
    "shadow": {"Head": (0.06, 0.06, 0.08), "Right Arm": (0.07, 0.07, 0.09), "Left Arm": (0.07, 0.07, 0.09),
               "Torso": (0.22, 0.07, 0.36), "Right Leg": (0.04, 0.04, 0.05), "Left Leg": (0.04, 0.04, 0.05)},
}
GHOST = (0.62, 0.30, 1.0)
WORLD = (0.07, 0.075, 0.10)


def solid(name, rgb):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    m.roughness = 0.55
    return m


def dup_rig(arm, tag):
    """a full second copy of the rig, APPENDED again from the rig file: the armature with its own drivers (the rig
    holds its parts with 14 object drivers - a plain object copy drops them and the parts scatter, 2026-10-12) and its
    part meshes, every reference remapped to the copy"""
    names = [arm.name] + [o.name for o in bpy.data.objects if o.parent == arm]
    before = set(bpy.data.objects)
    src_file = os.path.join(bpy.app.tempdir or os.path.dirname(bpy.data.filepath), f"rig_for_{tag}.blend")
    shutil.copyfile(bpy.data.filepath, src_file)          # Blender will not append from the open file itself
    with bpy.data.libraries.load(src_file, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in names]
    coll = arm.users_collection[0]
    new = None
    for ob in dst.objects:
        if ob is None:
            continue
        coll.objects.link(ob)
        if ob.type == "ARMATURE":
            new = ob
    for ob in set(bpy.data.objects) - before:
        if ob.parent == new and ob.type == "MESH":
            ob.name = f"{ob.name.split('.')[0]}_{tag}"
    new.name = f"{arm.name}_{tag}"
    if new.animation_data is not None:
        new.animation_data.action = None
    return new


def meshes_of(arm):
    return [o for o in bpy.data.objects if o.parent == arm and o.type == "MESH"]


def part_name(ob):
    base = ob.name.split("_")[0] if "_" in ob.name and ob.name.split("_")[0] in LOOKS["noob"] else ob.name
    return base if base in LOOKS["noob"] else None


def drive(arm, clip, rig, f0, origin, rest_local):
    """key the rig's controllers from the clip (root track included) - the look_r6 method, on this armature"""
    for side in ("SoftIK.L", "SoftIK.R"):
        pb = arm.pose.bones.get(side)
        if pb is not None and "FK" in pb.keys():
            pb["FK"] = True
    for thigh in ("Leg.R1", "Leg.L1"):
        tb = arm.pose.bones.get(thigh)
        if tb is not None and tb.constraints.get("IK") is not None:
            tb.constraints["IK"].mute = True
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions.new(clip["name"])
    deltas = part_deltas(clip, rig)
    sc = bpy.context.scene
    for i, d in enumerate(deltas):
        sc.frame_set(f0 + i)
        for part in PARTS:
            delta = d.get(part, Matrix.Identity(4))
            pb = arm.pose.bones[CONTROL[part]]
            pb.matrix = origin @ delta @ origin.inverted() @ rest_local[part]
            bpy.context.view_layer.update()
            pb.keyframe_insert("location", frame=f0 + i)
            pb.keyframe_insert("rotation_euler" if pb.rotation_mode != "QUATERNION" else "rotation_quaternion", frame=f0 + i)
    return deltas


def fidelity(arm, deltas, f0, origin, every=15):
    sc = bpy.context.scene
    obs = {part_name(o): o for o in meshes_of(arm) if part_name(o)}
    sc.frame_set(f0)
    inv = arm.matrix_world.inverted()
    rest = {p: (origin @ deltas[0][p] @ origin.inverted()).inverted() @ (inv @ o.matrix_world) for p, o in obs.items() if p in deltas[0]}
    worst = 0.0
    for i in range(0, len(deltas), every):
        sc.frame_set(f0 + i)
        for p, o in obs.items():
            if p not in rest:
                continue
            want = origin @ deltas[i][p] @ origin.inverted() @ rest[p]
            worst = max(worst, (want.translation - (inv @ o.matrix_world).translation).length)
    return worst


def key_visible(obs, visible, f0):
    prev = None
    for i, v in enumerate(visible):
        if v != prev:
            for o in obs:
                o.hide_render = not v
                o.keyframe_insert("hide_render", frame=f0 + i)
            prev = v


def fade_material(mat, frame, frames, rgb_from, rgb_to):
    for k in range(frames + 1):
        u = k / frames
        mat.diffuse_color = (*[a + (b - a) * u for a, b in zip(rgb_from, rgb_to)], 1.0)
        mat.keyframe_insert("diffuse_color", frame=frame + k)


def show_between(ob, a, b):
    ob.hide_render = True
    ob.keyframe_insert("hide_render", frame=max(0, a - 1))
    ob.hide_render = False
    ob.keyframe_insert("hide_render", frame=a)
    ob.hide_render = True
    ob.keyframe_insert("hide_render", frame=b)


def to_bl(p, origin):
    return origin + Vector((p[0], -p[2], p[1]))


def add_fx(sc, scene, rigs, origin, f0):
    made = 0
    for e in scene["fx"]:
        f = f0 + int(e["frame"])
        n = int(e.get("frames", 6))
        if e["type"] == "afterimage":
            arm = rigs[e["actor"]]
            sc.frame_set(f)
            for lag, shade in ((0, 1.0), (3, 0.6)):
                sc.frame_set(max(f0, f - lag))
                for o in meshes_of(arm):
                    g = bpy.data.objects.new(f"Ghost_{made}", o.data.copy())
                    sc.collection.objects.link(g)
                    g.matrix_world = o.matrix_world.copy()
                    m = solid(f"GhostMat_{made}", GHOST)
                    g.data.materials.clear()
                    g.data.materials.append(m)
                    fade_material(m, f, n, tuple(c * shade + w * (1 - shade) for c, w in zip(GHOST, WORLD)), WORLD)
                    show_between(g, f + 1, f + n)
                    made += 1
        elif e["type"] in ("flash", "impact", "streak"):
            loc = to_bl(e["pos"], origin)
            size = float(e.get("size", 1.0))
            if e["type"] == "streak":
                bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.6, depth=9.0, location=loc + Vector((0, 0, 2.5)))
                ob = bpy.context.active_object
                ob.name = f"FX_streak_{made}"
                m = solid(f"Streak_{made}", (0.92, 0.85, 1.0))
                ob.data.materials.append(m)
                for k, s in ((0, 1.0), (2, 0.55), (n, 0.02)):
                    ob.scale = (s, s, 1.0)
                    ob.keyframe_insert("scale", frame=f + k)
                fade_material(m, f, n, (0.95, 0.9, 1.0), GHOST)
                show_between(ob, f, f + n)
            else:
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=loc)
                ob = bpy.context.active_object
                ob.name = f"FX_burst_{made}"
                core = (1.0, 0.97, 0.82) if e["type"] == "impact" else (0.92, 0.85, 1.0)
                m = solid(f"Burst_{made}", core)
                ob.data.materials.append(m)
                # a quick hot spark, not a ball: it must never hide the contact (a 1.4-stud core did, 2026-10-12)
                keys = ((0, 0.15 * size), (1, 0.45 * size), (3, 0.3 * size)) if e["type"] == "impact" else ((0, 0.2 * size), (2, 0.8 * size), (n, 1.1 * size))
                for k, s in keys:
                    ob.scale = (s, s, s)
                    ob.keyframe_insert("scale", frame=f + k)
                fade_material(m, f, n, core, (1.0, 0.45, 0.15) if e["type"] == "impact" else GHOST)
                show_between(ob, f, f + (4 if e["type"] == "impact" else n))
                if e["type"] == "impact":
                    # anime impact spikes: thin bars radiating from the contact, flung out over the first frames
                    for s_ in range(8):
                        bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
                        sp = bpy.context.active_object
                        sp.name = f"FX_spike_{made}_{s_}"
                        sp.rotation_euler = (math.radians(30 * (s_ % 3)), math.radians(45 * s_), math.radians(22.5 * s_))
                        sp.data.materials.append(m)
                        for k, (L, w) in ((0, (0.3, 0.08)), (2, (3.2 * size, 0.07)), (n, (4.0 * size, 0.0))):
                            sp.scale = (w, w, L)
                            sp.keyframe_insert("scale", frame=f + k)
                        show_between(sp, f, f + n)
                    # a white ring flat on the floor
                    bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.05, location=(loc.x, loc.y, origin.z - 2.95))
                    ring = bpy.context.active_object
                    ring.name = f"FX_ring_{made}"
                    ring.data.materials.append(m)
                    for k, s in ((0, 0.3), (n, 4.0 * size)):
                        ring.scale = (s, s, 1.0)
                        ring.keyframe_insert("scale", frame=f + k)
                    show_between(ring, f, f + n)
            made += 1
    return made


def main():
    sp = sys.argv[sys.argv.index("--") + 1]
    scene = json.load(open(sp, encoding="utf-8"))
    rig = C.load_rig("r6")
    base = bpy.data.objects.get("Rig1")
    if base is None:
        return look.emit("fail", "cutscene_r6: no armature Rig1 in the rig file", "check assets/rigs/R6_IK.blend")
    sc = bpy.context.scene
    hrp_rest = base.data.bones["HumanoidRootPart"].matrix_local.translation.copy()
    origin = Matrix.Translation(hrp_rest)
    rest_local = {part: base.data.bones[CONTROL[part]].matrix_local.copy() for part in PARTS}
    names = list(scene["actors"])
    rigs = {names[0]: base}
    for nm in names[1:]:
        rigs[nm] = dup_rig(base, nm)
    # every copy must stand EXACTLY like the original before it is driven (the per-frame fidelity check below is
    # relative to frame 0, so a copy whose parts start scattered would pass it - the first render did, 2026-10-12)
    bpy.context.view_layer.update()
    ref = {part_name(o): o.matrix_world.translation.copy() for o in meshes_of(base)}
    for nm, arm in rigs.items():
        for o in meshes_of(arm):
            off = (o.matrix_world.translation - ref[part_name(o)]).length
            if off > 0.02:
                return look.emit("fail", f"cutscene_r6: the copy for {nm} has {o.name} {off:.2f} studs off the original at rest", "the rig copy lost a driver or constraint")
    f0 = 0
    sc.frame_start, sc.frame_end = f0, f0 + scene["frames"] - 1
    sc.render.fps = int(scene["fps"])
    worst = {}
    for nm in names:
        a = scene["actors"][nm]
        clip = json.load(open(a["clip"], encoding="utf-8"))
        arm = rigs[nm]
        cols = LOOKS.get(a.get("look", "noob"), LOOKS["noob"])
        for o in meshes_of(arm):
            p = part_name(o)
            if p:
                o.data.materials.clear()
                o.data.materials.append(solid(f"{nm}_{p}", cols[p]))
        deltas = drive(arm, clip, rig, f0, origin, rest_local)
        worst[nm] = round(fidelity(arm, deltas, f0, origin), 4)
        key_visible(meshes_of(arm), a["visible"], f0)
        # the actor's SWORD (cutscene.py composes a held blade from the kit's strike clips): the same weapon the
        # look draws, carried by the actor's world root
        sw = clip.get("sword")
        root = clip.get("root")
        if isinstance(sw, dict) and sw.get("tip") and isinstance(root, list) and len(root) == len(sw["tip"]):
            sw = dict(sw)
            for key in ("tip", "grip_path"):
                sw[key] = [list((Matrix(C.quat_mat(r[:4]).tolist()) @ Vector(p)) + Vector(r[4:7])) for p, r in zip(sw[key], root)]
            if sw.get("edge") and len(sw["edge"]) == len(root):
                sw["edge"] = [list(Matrix(C.quat_mat(r[:4]).tolist()) @ Vector(e)) for e, r in zip(sw["edge"], root)]
            blade = look.add_weapon(sc, {"sword": sw, "events": []}, f0, int(scene["fps"]), origin=Vector(hrp_rest))
            if blade is not None:                              # hidden with its actor (a teleport's gap, a vanish)
                key_visible([blade] + list(blade.children_recursive), a["visible"], f0)
    if max(worst.values()) > 0.02:
        return look.emit("fail", f"cutscene_r6: a rig does not reproduce its clip ({worst} studs)", "check the rig's constraints")
    fxn = add_fx(sc, scene, rigs, Vector(hrp_rest), f0)
    keep = set()
    for arm in rigs.values():
        keep |= {arm.name} | {o.name for o in meshes_of(arm)}
    keep |= {o.name for o in bpy.data.objects if o.name.startswith(("Ghost_", "Look", "FX_"))}
    for ob in bpy.data.objects:
        if ob.name not in keep and ob.type != "CAMERA":
            ob.hide_render = True
            ob.hide_viewport = True
    floor = look.floor_and_lights(sc, Vector((hrp_rest.x, hrp_rest.y, 0)), 7.0)
    floor.location.z = hrp_rest.z - 3.0 - 0.002
    floor.data.materials[0].diffuse_color = (0.16, 0.17, 0.20, 1.0)
    for ob in bpy.data.objects:
        if ob.name.startswith("Plane") and ob.active_material and ob.active_material.name.startswith("LookGrid"):
            ob.active_material.diffuse_color = (0.24, 0.25, 0.30, 1.0)
            ob.location.z = floor.location.z + 0.002
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "Standard"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_object_outline = True
    sh.object_outline_color = (0.0, 0.0, 0.0)
    sh.show_shadows = True
    sh.shadow_intensity = 0.5
    sc.display.light_direction = (0.35, -0.5, 0.8)
    if sc.world is None:
        sc.world = bpy.data.worlds.new("CutWorld")
    sc.world.color = WORLD
    cam_data = bpy.data.cameras.new("CutCam")
    cam = bpy.data.objects.new("CutCam", cam_data)
    sc.collection.objects.link(cam)
    cam_data.lens = 32
    sc.camera = cam
    for i, k in enumerate(scene["camera"]):
        loc, tgt = to_bl(k["loc"], Vector(hrp_rest)), to_bl(k["target"], Vector(hrp_rest))
        cam.location = loc
        cam.rotation_euler = (tgt - loc).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f0 + i)
        cam.keyframe_insert("rotation_euler", frame=f0 + i)
    out = os.path.abspath(scene["out"])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{scene['name']}.blend"), copy=True)
    sc.render.resolution_x, sc.render.resolution_y = scene["size"]
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    fdir = os.path.join(out, "frames")
    os.makedirs(fdir, exist_ok=True)
    for old in os.listdir(fdir):
        os.remove(os.path.join(fdir, old))
    for f in range(sc.frame_start, sc.frame_end + 1, max(1, int(scene.get("every", 1)))):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(fdir, f"{f - f0:05d}.png")
        bpy.ops.render.render(write_still=True)
    return look.emit("pass", f"{scene['frames']} frames, {len(rigs)} rigs (rig = clip within {worst} studs), {fxn} effects", "encode the frames",
                     fidelity=worst)


if __name__ == "__main__":
    sys.exit(main())
