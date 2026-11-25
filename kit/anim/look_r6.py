"""look_r6.py — the R6 look on the OWNER'S rig (assets/rigs/R6_IK.blend, a Roblox-plugin export: deform bones named
like the parts, meshes bone-parented, IK/FK controllers on top). Run by `kit anim look <Name> --rig R6`:

    blender -b assets/rigs/R6_IK.blend --disable-autoexec --python-exit-code 2 -P kit/anim/look_r6.py -- <Name>
        --clip <r6 clip.json> --out <dir> [--views N] [--every N] [--size PX]

The clip (R6 joint names, the kit's neutral clip) is turned into every part's CFrame per frame with the kit's own
forward kinematics (kit/anim/clip.py on the engine-read R6 rig), the delta from rest is applied to the rig's deform
bones (their controllers' constraints muted - the rig is DRIVEN, not solved), the parts get the classic colours, and
the same cameras / floor / Workbench look as look.py render every frame; kit/anim/look_sheet.py then makes the gif +
sheet. The rig file is never written."""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C      # noqa: E402  (the kit's clip sampler + FK; Blender's Python has numpy)
import look           # noqa: E402  (floor, cameras, weapon, emit)
import pose_sheet as PS   # noqa: E402  (the sheet's plan, its cameras and view directions: pure numpy)

PARTS = ["HumanoidRootPart", "Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
# the rig as the owner built it (assets/rigs/R6_IK.blend, a Roblox Blender-Animations rig with an IK/FK layer): the
# part meshes hang off deform bones named like the parts, and those are driven by CHILD_OF / COPY_LOCATION
# constraints from CONTROLLER bones - the bones an animator keys (the rig's own action keys exactly these). The clip
# is keyed on the controllers; the constraints and the meshes stay untouched. Each controller's head sits on its
# part's joint pivot (Body at the root, Arm.R at the shoulder, FKLeg.R at the hip, Head.001 at the neck), so a
# part's world delta applied to its controller moves the part exactly. The legs run in FK (SoftIK.*["FK"] = True
# in the file: the IK chain's influence is 0 while SoftIK stays at rest).
CONTROL = {"HumanoidRootPart": "Main Controller", "Torso": "Body", "Head": "Head.001", "Right Arm": "Arm.R",
           "Left Arm": "Arm.L", "Right Leg": "FKLeg.R", "Left Leg": "FKLeg.L"}
# the classic look: a face-less yellow head, blue torso, green legs - what every Roblox player reads as R6
COLOURS = {"Head": (0.96, 0.80, 0.19), "Right Arm": (0.96, 0.80, 0.19), "Left Arm": (0.96, 0.80, 0.19),
           "Torso": (0.05, 0.41, 0.67), "Right Leg": (0.64, 0.74, 0.27), "Left Leg": (0.64, 0.74, 0.27)}
# Roblox (x right, y up, -z forward) -> Blender (x right, z up, +y back): (x, y, z) -> (x, -z, y)
B = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
B_INV = B.inverted()


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"name": None, "clip": None, "out": None, "views": 2, "every": 1, "size": 360, "posed": False, "arcs": False,
           "mark": False, "fp": False, "tp": False, "also": None, "dark_blade": False, "frame_reach": False, "sheet": None}
    i = 0
    while i < len(a):
        k = a[i]
        if k in ("--posed", "--flat", "--arcs", "--mark", "--fp", "--tp", "--dark-blade", "--frame-reach"):  # posed: pose_r6's file; flat: classic colours;
            #   frame-reach: the still cameras centred on the ROOT and wide enough for the weapon's whole sweep (a drill's
            #   blade disc IS the move - 2026-11-05);
            #   arcs: trails; mark: an orange disc where the body began; fp: FIRST PERSON - the eye's view of a game whose
            #   camera sits in the head and shows only the arms (Sample Game's R6 arms, 2026-10-25); tp: Sample Game's
            #   THIRD-PERSON camera over the right shoulder (2026-11-04)
            out[k[2:].replace("-", "_")] = True
            i += 1
            continue
        if k in ("--out", "--views", "--every", "--size", "--clip", "--also", "--sheet") and i + 1 < len(a):   # also: with --tp, one more view (e.g. three-quarter)
            #   sheet: a plan (kit/anim/pose_sheet.py plan): ONLY its key poses and strip frames are rendered, each framed
            #   on what it shows, into <out>/frames/ with every camera written to <out>/render.json (sheet_shots below)
            out[k[2:]] = a[i + 1]
            i += 2
            continue
        if not k.startswith("--") and out["name"] is None:
            out["name"] = k
        i += 1
    out["views"], out["every"], out["size"] = int(out["views"]), int(out["every"]), int(out["size"])
    return out


def m4(np_mat):
    return Matrix([[float(v) for v in row] for row in np_mat])


def part_deltas(clip, rig):
    """per frame {part: 4x4 Blender delta from the part's rest, about the rig's HumanoidRootPart}"""
    rest = C.fk(rig)
    frames = C.world_frames(clip, rig)        # a `root` track (a lunge's travel) is composed in
    out = []
    for w in frames:
        d = {}
        for part in PARTS:
            if part in w and part in rest:
                delta = m4(w[part]) @ m4(rest[part]).inverted()
                d[part] = B @ delta @ B_INV
        out.append(d)
    return out


def sheet_shots(a, sc, arm, clip, rig, hrp_rest, f0, body_meshes, fidelity, posed):
    """THE SHEET'S PICTURES (kit/anim/pose_sheet.py, the animation studio route's A0): only the plan's frames - each key
    pose from the player's camera, the side and above, the strip's 12 frames a second - on the same rig, floor and
    Workbench look as every other look, but each picture framed on WHAT IT SHOWS (the body and its weapon on that
    frame: pose_sheet.camera_fit) instead of a sphere round the whole clip, and no flash ball on the tip. A strip
    keeps ONE camera per view (its paths must not jump) unless the body travels over 2 studs. Every camera is
    written to <out>/render.json, so the pages can draw on the renders (the blade's path, the weight over the
    feet) with the kit's own FK; two numbers say whether that is honest: how far the kit's FK sits from the rig's
    meshes, and the kit's projection from Blender's own."""
    import time
    from bpy_extras.object_utils import world_to_camera_view
    t0 = time.time()
    with open(a["sheet"], encoding="utf-8") as fh:
        pl = json.load(fh)
    out_dir = os.path.abspath(a["out"])
    fdir = os.path.join(out_dir, "frames")
    os.makedirs(fdir, exist_ok=True)
    origin = [hrp_rest.x, hrp_rest.y, hrp_rest.z]
    W = C.world_frames(clip, rig)
    n = len(W)
    weapons = [ob for ob in bpy.data.objects if ob.type == "MESH"
               and ob.name.startswith(("LookGreatsword", "LookKatana", "LookPistol"))]

    def shown(i, weapon=True):
        """the corners of the body's (and the weapon's) boxes on clip frame i (world); the scene is left on that frame"""
        sc.frame_set(f0 + i)
        return [list(ob.matrix_world @ Vector(c)) for ob in body_meshes + (weapons if weapon else []) for c in ob.bound_box]

    cam_data = bpy.data.cameras.new("LookCamSheet")
    cam = bpy.data.objects.new("LookCamSheet", cam_data)
    sc.collection.objects.link(cam)
    cam_data.sensor_fit, cam_data.sensor_width = "AUTO", 36.0
    cam_data.clip_start, cam_data.clip_end = 0.05, 2000.0
    sc.camera = cam
    worst = {"px": 0.0, "fk": 0.0}

    def aim(fit, pts, size):
        m = Matrix((Vector(fit["right"]), Vector(fit["up"]), Vector(fit["back"]))).transposed().to_4x4()
        m.translation = Vector(fit["loc"])
        cam.matrix_world = m
        cam_data.type = "ORTHO" if fit.get("ortho") else "PERSP"
        if fit.get("ortho"):
            cam_data.ortho_scale = 2.0 * max(fit["tan"])       # (sensor fit AUTO: the scale spans the larger side)
        else:
            cam_data.lens = PS.lens_of(fit, cam_data.sensor_width)
        bpy.context.view_layer.update()
        pix, _ = PS.project(fit, pts[:8], size)                # the kit's projection against Blender's own
        for p, q in zip(pts[:8], pix):
            v = world_to_camera_view(sc, cam, Vector(p))
            worst["px"] = max(worst["px"], abs(v.x * size[0] - float(q[0])), abs((1.0 - v.y) * size[1] - float(q[1])))

    def shoot(path):
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)

    boxes = [p for p in ("Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg") if bpy.data.objects.get(p) is not None]
    kh = int(pl.get("key_height", PS.KEY_SIZE))
    key_frames = [min(int(key["frame"]), n - 1) for key in pl["keys"]]
    key_pts = {i: shown(i) for i in key_frames}
    # a view's pane: `kh` px high and as wide as its WIDEST key pose needs (a blade held out sideways), one size for
    # the view so the sheet's columns line up; each pose is then framed on itself inside it
    key_size = {v: PS.pane_size(PS.VIEW_DIRS[v], key_pts.values(), kh, PS.KEY_ASPECT) for v in pl["key_views"]}
    key_cams = {v: {} for v in pl["key_views"]}
    for i in key_frames:
        pts = key_pts[i]
        sc.frame_set(f0 + i)
        for part in boxes:                                     # the kit's FK against the rig's own meshes, here
            ob = bpy.data.objects[part]
            centre = sum((ob.matrix_world @ Vector(c) for c in ob.bound_box), Vector((0.0, 0.0, 0.0))) / 8
            worst["fk"] = max(worst["fk"], (centre - Vector(PS.to_blender(W[i][part][:3, 3], origin))).length)
        for view in pl["key_views"]:
            kw = key_size[view][0]
            sc.render.resolution_x, sc.render.resolution_y = kw, kh
            fit = PS.camera_fit(PS.VIEW_DIRS[view], pts, kw / kh, ortho=view in PS.VIEW_ORTHO)
            aim(fit, pts, (kw, kh))
            shoot(os.path.join(fdir, f"key_{view}_{i:04d}.png"))
            key_cams[view][str(i)] = fit
    strip = None
    sframes = [min(int(i), n - 1) for i in pl.get("strip_frames") or []]
    if sframes and pl.get("strip_views"):
        pth = PS.paths(clip, W)
        drawn = [list(p) for k in PS.PATH_COLOUR if k in pth for p in PS.to_blender(pth[k], origin)]
        per = {i: shown(i) for i in sframes}
        body = [p for i in sframes for p in shown(i, weapon=False)]
        travel = max(float(np.linalg.norm(W[i]["Torso"][:3, 3] - W[sframes[0]]["Torso"][:3, 3])) for i in sframes)
        follow = travel > 2.0
        strip = {"size": {}, "cams": {}, "follow": follow}
        high = int(pl.get("strip_height", PS.STRIP_SIZE))
        for view in pl["strip_views"]:
            # the frame takes the motion's own shape: `high` px tall, as wide as the body and its paths need
            held = None if follow else PS.strip_points(PS.VIEW_DIRS[view], body, drawn)
            sw, sh = [int(round(high * 0.8 / 2)) * 2, high] if follow else PS.strip_size(PS.VIEW_DIRS[view], held, high)
            sc.render.resolution_x, sc.render.resolution_y = sw, sh
            fixed = None if follow else PS.camera_fit(PS.VIEW_DIRS[view], held, sw / sh, margin=1.08)
            cams = {}
            for i in sframes:
                fit = fixed or PS.camera_fit(PS.VIEW_DIRS[view], per[i], sw / sh)
                sc.frame_set(f0 + i)
                aim(fit, per[i], (sw, sh))
                shoot(os.path.join(fdir, f"strip_{view}_{i:04d}.png"))
                cams[str(i)] = fit
            strip["size"][view] = [sw, sh]
            strip["cams"][view] = cams
    secs = round(time.time() - t0, 1)
    with open(os.path.join(out_dir, "render.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "name": pl["name"], "origin": origin, "f0": f0, "posed": bool(posed), "fidelity": fidelity,
                   "overlay_error_studs": round(worst["fk"], 4), "projection_error_px": round(worst["px"], 3),
                   "key": {"size": key_size, "cams": key_cams}, "strip": strip, "seconds": secs}, fh)
    return look.emit("pass", f"sheet {pl['name']}: {len(pl['keys'])} key pose(s) x {len(pl['key_views'])} view(s) {kh} px high + "
                             f"{len(sframes)} strip frame(s) x {len(pl.get('strip_views') or [])} view(s) on the owner's R6 rig in "
                             f"{secs} s (the kit's FK within {worst['fk']:.3f} studs of its meshes) -> {fdir}",
                     f"python -I kit/anim/pose_sheet.py pages {out_dir}", dir=out_dir, seconds=secs)


def main():
    a = args()
    if not a["name"] or not a["out"] or not a["clip"]:
        return look.emit("fail", "look_r6: needs <Name> --clip <clip.json> --out <dir>", "lune run kit anim look <Name> --rig R6")
    with open(a["clip"], encoding="utf-8") as fh:
        clip = json.load(fh)
    clip_read = clip                                         # as it is on disk (the sword's path root-local)
    if clip.get("rig") != "R6":
        return look.emit("fail", f"look_r6: {a['clip']} is a {clip.get('rig')} clip - the R6 look wants the R6 fold", "lune run kit anim <Name>")
    rig = C.load_rig("r6")
    arm = bpy.data.objects.get("Rig1")
    if arm is None or arm.type != "ARMATURE":
        return look.emit("fail", "look_r6: the rig file holds no armature named Rig1", "check assets/rigs/R6_IK.blend")
    sc = bpy.context.scene
    for part, ctrl in CONTROL.items():
        if arm.pose.bones.get(ctrl) is None:
            return look.emit("fail", f"look_r6: the rig has no controller bone {ctrl} (for {part})", "check assets/rigs/R6_IK.blend")
    posed = a["posed"]
    if not posed:
        for side in ("SoftIK.L", "SoftIK.R"):               # the legs in FK: the clip keys FKLeg.*
            pb = arm.pose.bones.get(side)
            if pb is not None and "FK" in pb.keys():
                pb["FK"] = True
        # the thighs (Leg.R1 / Leg.L1) end in a COPY_TRANSFORMS "IK" whose influence a driver should hold at 0 in FK; in a
        # headless run it stays at 1.0 and the legs follow the IK chain to the planted foot controllers, not the clip -
        # every driven render's legs were up to 7.7 studs / 115 deg off (measured 2026-10-11; the in-place sprint hid
        # it). The driven look is FK: those copies are muted (the saved file says so; unmute them to animate in IK)
        for thigh in ("Leg.R1", "Leg.L1"):
            tb = arm.pose.bones.get(thigh)
            if tb is not None and tb.constraints.get("IK") is not None:
                tb.constraints["IK"].mute = True
        # the rig carries an action of its own: a fresh one holds the clip (the owner scrubs it in the saved .blend)
        if arm.animation_data is None:
            arm.animation_data_create()
        arm.animation_data.action = bpy.data.actions.new(a["name"][:-3] if a["name"].endswith(".r6") else a["name"])
    # the rig's OWN material is kept: an orientation-template texture (FRONT / BACK / L / R / UP / DOWN on every face,
    # a face on the head - assets/rigs/R6_IK.md) that says which way every part faces; flat colours only with --flat
    for ob in bpy.data.objects:
        if a.get("flat") and ob.parent == arm and ob.type == "MESH" and ob.name in COLOURS:
            mat = bpy.data.materials.new(f"look_{ob.name}")
            mat.diffuse_color = (*COLOURS.get(ob.name, (0.7, 0.7, 0.7)), 1.0)
            mat.roughness = 0.6
            ob.data = ob.data.copy()
            ob.data.materials.clear()
            ob.data.materials.append(mat)
    hrp_rest = arm.data.bones["HumanoidRootPart"].matrix_local.translation.copy()
    origin = Matrix.Translation(hrp_rest)
    rest_local = {part: arm.data.bones[CONTROL[part]].matrix_local.copy() for part in PARTS}
    deltas = [] if posed else part_deltas(clip, rig)
    fps = int(round(clip.get("fps") or 30))
    sc.render.fps = fps
    if posed:                                                # the file's own action, IK legs, sword: render it as it is
        f0 = sc.frame_start
    else:
        f0 = 1
        sc.frame_start, sc.frame_end = f0, f0 + len(deltas) - 1
    for i, d in enumerate(deltas):
        frame = f0 + i
        sc.frame_set(frame)
        for part in PARTS:                                   # parents first (PARTS is in hierarchy order)
            delta = d.get(part, Matrix.Identity(4))
            target = origin @ delta @ origin.inverted() @ rest_local[part]
            pb = arm.pose.bones[CONTROL[part]]
            pb.matrix = target                               # armature space; the parent's pose is read as evaluated
            bpy.context.view_layer.update()                  # so the child's basis is solved against the moved parent
            pb.keyframe_insert("location", frame=frame)
            pb.keyframe_insert("rotation_euler" if pb.rotation_mode != "QUATERNION" else "rotation_quaternion", frame=frame)
    # FIDELITY: every part MESH on the owner's rig must land where the clip's FK puts it (the rig is driven, never
    # trusted) - a rig constraint that fights the keys fails the look instead of rendering a wrong animation
    fidelity = None
    if not posed and deltas:
        sc.frame_set(f0)
        meshes = {p: bpy.data.objects.get(p) for p in PARTS if p != "HumanoidRootPart"}
        meshes = {p: ob for p, ob in meshes.items() if ob is not None and p in deltas[0]}
        inv = arm.matrix_world.inverted()
        mesh_rest = {p: (origin @ deltas[0][p] @ origin.inverted()).inverted() @ (inv @ ob.matrix_world) for p, ob in meshes.items()}
        worst = (0.0, 0.0, None, None)
        for i, d in enumerate(deltas):
            sc.frame_set(f0 + i)
            for p, ob in meshes.items():
                want = origin @ d[p] @ origin.inverted() @ mesh_rest[p]
                have = inv @ ob.matrix_world
                dp = (want.translation - have.translation).length
                q = (want.to_3x3().normalized().inverted() @ have.to_3x3().normalized()).to_quaternion()
                ang = math.degrees(2 * math.acos(min(1.0, abs(q.w))))
                if dp + ang / 90 > worst[0] + worst[1] / 90:
                    worst = (dp, ang, p, i)
        fidelity = {"studs": round(worst[0], 4), "deg": round(worst[1], 2), "part": worst[2], "frame": worst[3]}
        if worst[0] > 0.02 or worst[1] > 1.0:
            return look.emit("fail", f"look_r6 {a['name']}: the rig does not reproduce the clip - {worst[2]} is {worst[0]:.3f} studs / {worst[1]:.1f} deg off at frame {worst[3]} (a rig constraint fights the keys)",
                             "find the constraint on that part's chain (IK / Child Of / Copy Transforms) and mute it for the driven look", fidelity=fidelity)
    # a weapon path (strike / rearm clips): drawn in the kit's character frame, moved up onto the rig's floor; a
    # `root` track (a lunge's travel) carries the blade with the body
    root = clip.get("root")
    if not posed and isinstance(clip.get("sword"), dict) and isinstance(root, list) and len(root) == len(deltas):
        sw = dict(clip["sword"])
        for key in ("tip", "grip_path"):
            if sw.get(key) and len(sw[key]) == len(root):
                sw[key] = [list((Matrix(C.quat_mat(r[:4]).tolist()) @ Vector(p)) + Vector(r[4:7])) for p, r in zip(sw[key], root)]
        if sw.get("edge") and len(sw["edge"]) == len(root):          # a direction: turned with the root, not moved
            sw["edge"] = [list(Matrix(C.quat_mat(r[:4]).tolist()) @ Vector(e)) for e, r in zip(sw["edge"], root)]
        clip = dict(clip)
        clip["sword"] = sw
    base = a["name"][:-3] if a["name"].endswith(".r6") else a["name"]
    blend_out = os.path.join(os.path.abspath(a["out"]), f"{base}.r6.blend")
    if posed:
        blend_out = bpy.data.filepath                        # the posed file IS the owner's file; it is not rewritten
    else:
        look.add_weapon(sc, clip, f0, fps, origin=Vector(hrp_rest))
        if a.get("dark_blade"):
            # (a pick sheet's white backdrop: the light steel stand-in vanished edge-on from behind - drawn dark steel so
            # the cut reads; the look only, 2026-11-04)
            for ob in bpy.data.objects:
                if ob.name.startswith(("LookGreatsword", "LookKatana")):
                    for m in ob.data.materials:
                        m.diffuse_color = (0.12, 0.13, 0.16, 1.0)
    if clip.get("grip_left"):
        # ONYX (Sample Game's LEFT gun, its own Handle track - kit/anim/grip.py): drawn black from its path, posed or
        # driven alike (2026-10-27: every preview showed the right gun only - Onyx's motion was never looked at)
        import grip as G
        sw = clip.get("sword") or {}
        ln = (float(np.linalg.norm(np.asarray(sw["tip"][0]) - np.asarray(sw["grip_path"][0])))
              if sw.get("tip") and sw.get("grip_path") else 1.85)
        onyx = look.add_weapon(sc, {"sword": G.left_paths(clip, ln, rig)}, f0, fps, origin=Vector(hrp_rest))
        if onyx is not None:
            onyx.name = "LookPistolL"
            for m in onyx.data.materials:
                m.diffuse_color = (0.07, 0.07, 0.08, 1.0)
    if a.get("arcs"):
        # ARCS + SPACING (AAA plan #3): the hands' and the blade tip's paths, a tick on every frame (gaps = speed)
        W = C.world_frames(clip, rig)
        hand = lambda part: [list((f[part] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]) for f in W]
        paths = [("RightHand", (0.85, 0.2, 0.2), hand("Right Arm")), ("LeftHand", (0.2, 0.35, 0.9), hand("Left Arm"))]
        if isinstance(clip.get("sword"), dict) and clip["sword"].get("tip"):
            paths.append(("BladeTip", (0.95, 0.8, 0.1), clip["sword"]["tip"]))
        look.add_trails(paths, origin=Vector(hrp_rest))
    if a.get("sheet"):
        # a sheet shows POSES: the flash ball add_weapon puts on the tip at each Hit covered the blade's end on the
        # very pose that matters most (looked at 2026-11-12); a sheet's pictures carry none
        for ob in [ob for ob in bpy.data.objects if ob.name.startswith("LookFlash")]:
            bpy.data.objects.remove(ob, do_unlink=True)
    if not posed and not a.get("sheet"):
        # the posed rig, saved as the owner's own file with the clip as its action: open it, scrub the controllers
        os.makedirs(os.path.dirname(blend_out), exist_ok=True)
        sc.frame_set(f0)
        bpy.ops.wm.save_as_mainfile(filepath=blend_out, copy=True)
    # only the character and the weapon render: the rig file's camera rig, guide planes and helpers stay out
    keep = {arm.name} | {ob.name for ob in bpy.data.objects if ob.parent == arm and ob.type == "MESH"}
    keep |= {ob.name for ob in bpy.data.objects if ob.name.startswith("Look")}
    for ob in bpy.data.objects:
        ob.hide_render = ob.name not in keep
        if ob.name not in keep:
            ob.hide_viewport = True
    # the character's extent over the clip, from its BODY parts' boxes (a sword's sweep would frame the character tiny;
    # the blade may leave the frame at the top of a wind-up, the body never does)
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    per_frame = {}                                          # frame -> (lo, hi) of the body alone
    body_meshes = [ob for ob in bpy.data.objects if ob.parent == arm and ob.type == "MESH" and ob.name in COLOURS]
    for f in range(sc.frame_start, sc.frame_end + 1):
        sc.frame_set(f)
        flo, fhi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
        for ob in body_meshes:
            for corner in ob.bound_box:
                w = ob.matrix_world @ Vector(corner)
                flo = Vector((min(flo.x, w.x), min(flo.y, w.y), min(flo.z, w.z)))
                fhi = Vector((max(fhi.x, w.x), max(fhi.y, w.y), max(fhi.z, w.z)))
        per_frame[f] = (flo, fhi)
        lo = Vector((min(lo.x, flo.x), min(lo.y, flo.y), min(lo.z, flo.z)))
        hi = Vector((max(hi.x, fhi.x), max(hi.y, fhi.y), max(hi.z, fhi.z)))
    centre = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1.0) * 1.05
    floor = look.floor_and_lights(sc, centre, radius)
    # a clip that TRAVELS (a root track: a lunge, the katana combo's stamps, a teleport - 2026-10-18) is followed: the
    # cameras keep the character's size and move with its body, instead of framing the whole journey (a speck)
    centres = {f: (a + b) / 2 for f, (a, b) in per_frame.items()}
    travel = max(((c - centres[sc.frame_start]).length for c in centres.values()), default=0.0)
    follow = travel > 2.0
    if follow:
        # SMOOTHED: the body's box shifts every frame an arm swings - a camera on it jittered (the owner's katana v1
        # 'looks really bad'); a half-second moving average follows the travel, not the limbs
        fr = sorted(centres)
        win = max(1, int(fps * 0.25))
        sm = {}
        for i, f in enumerate(fr):
            seg = [centres[fr[j]] for j in range(max(0, i - win), min(len(fr), i + win + 1))]
            sm[f] = sum(seg, Vector((0.0, 0.0, 0.0))) / len(seg)
        # ALONG the floor only: a jump must read as height against a still floor (the katana finisher's 5-stud leap
        # looked flat when the camera rose with it)
        mid_z = (lo.z + hi.z) / 2
        centres = {f: Vector((c.x, c.y, mid_z)) for f, c in sm.items()}
        radius = 1.0
        for f, (p_lo, p_hi) in per_frame.items():
            for corner in (p_lo, p_hi, Vector((p_lo.x, p_lo.y, p_hi.z)), Vector((p_hi.x, p_hi.y, p_lo.z))):
                radius = max(radius, (corner - centres[f]).length)
        radius *= 1.05
        centre = centres[sc.frame_start]
    elif a.get("frame_reach"):
        # ON THE ROOT + THE REACH (2026-11-05: a drill's three-quarter sat at the frame's edge, its 3.35-stud blade disc
        # cut off - the body's box leans with the bend and the sword's sweep was left out): centred over the root, the
        # radius every body part AND the weapon reach over the clip
        reach = body_meshes + [ob for ob in bpy.data.objects if ob.type == "MESH"
                               and ob.name.startswith(("LookGreatsword", "LookKatana", "LookPistol"))]
        centre = Vector((hrp_rest.x, hrp_rest.y, (lo.z + hi.z) / 2))
        radius = 1.0
        for f in range(sc.frame_start, sc.frame_end + 1):
            sc.frame_set(f)
            for ob in reach:
                for corner in ob.bound_box:
                    radius = max(radius, ((ob.matrix_world @ Vector(corner)) - centre).length)
        radius *= 1.05
    floor.location.z = hrp_rest.z - 3.0 - 0.002             # the R6 floor: three studs under the root
    if a.get("mark") and per_frame:
        # the START SPOT (2026-10-24): a step under 2 studs is not followed, and a plain grid gives the eye nothing to
        # measure it against (the dodge / block directions' steps did not read) - an orange disc where the body began
        s_lo, s_hi = per_frame[min(per_frame)]
        sp = (s_lo + s_hi) / 2
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.9, depth=0.01,
                                            location=(sp.x, sp.y, floor.location.z + 0.006))
        disc = bpy.context.active_object
        disc.name = "LookStartSpot"
        dm = bpy.data.materials.new("LookStart")
        dm.diffuse_color = (0.95, 0.55, 0.1, 1.0)
        disc.data.materials.append(dm)
    sc.render.engine = "BLENDER_WORKBENCH"
    if os.environ.get("LOOK_ENGINE") == "CYCLES":            # fallback when the GL context can't be made (the NVIDIA GL
        sc.render.engine = "CYCLES"                          # driver crashes with the desktop locked / the GPU shared):
        sc.cycles.device = "CPU"                             # CPU path tracing needs no GL
        sc.cycles.samples = 8
        sc.cycles.use_denoising = False
    sc.view_settings.view_transform = "Standard"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL" if a.get("flat") else "TEXTURE"
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_object_outline = True
    sh.object_outline_color = (0.06, 0.06, 0.07)
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    sc.display.light_direction = (0.35, -0.5, 0.8)
    if sc.world is None:
        sc.world = bpy.data.worlds.new("LookWorld")
    sc.world.color = (0.88, 0.89, 0.92)
    size = a["size"]
    sc.render.resolution_x, sc.render.resolution_y = size, int(size * 1.25)
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False
    aspect = sc.render.resolution_x / sc.render.resolution_y
    # the rig faces +y (Roblox -z forward -> Blender +y; the right arm at +x): cameras IN FRONT of the character.
    # (Until 2026-10-11 these sat at -y and every R6 look showed the character from behind.)
    # "game": Roblox's default camera - BEHIND the player and above (the view a player actually sees; added 2026-10-12
    # when the follow-throughs read from the front-right but the owner's players look from behind)
    if a.get("sheet"):
        return sheet_shots(a, sc, arm, clip_read, rig, hrp_rest, f0, body_meshes, fidelity, posed)
    views = [("three-quarter", (0.72, 0.78, 0.38)), ("game", PS.VIEW_DIRS["player"]), ("side", PS.VIEW_DIRS["side"]),
             ("front", PS.VIEW_DIRS["front"])][: max(1, a["views"])]
    cams = [(label, look.camera_for(sc, dv, centre, radius, aspect)) for label, dv in views]
    tp_root0 = None
    if a.get("fp"):
        # FIRST PERSON: the game's camera at the centre of the head (the root + 1.5 studs), looking straight ahead, a
        # 70 degree VERTICAL field of view on a 16:9 screen (Roblox's FieldOfView is vertical); the head, torso and
        # legs hidden as the game hides them (LocalTransparencyModifier) - only the arms and the weapon show
        for ob in bpy.data.objects:
            if ob.parent == arm and ob.type == "MESH" and ob.name in ("Head", "Torso", "Right Leg", "Left Leg"):
                ob.hide_render = True
        sc.render.resolution_x, sc.render.resolution_y = int(size * 16 / 9), size
        cam_data = bpy.data.cameras.new("LookCamFP")
        cam_data.sensor_fit = "VERTICAL"
        cam_data.angle_y = math.radians(70.0)
        cam_data.clip_start = 0.05
        fp = bpy.data.objects.new("LookCamFP", cam_data)
        sc.collection.objects.link(fp)
        fp.location = arm.matrix_world @ (hrp_rest + Vector((0.0, 0.0, 1.5)))
        fp.rotation_euler = Vector((0.0, 1.0, 0.0)).to_track_quat("-Z", "Z").to_euler()   # the rig faces +y
        cams = [("fp", fp)]
        follow = False
    elif a.get("tp"):
        # THIRD PERSON (the governor 2026-11-04: judge the swings from the player's camera): Sample Game's
        # Config.ThirdPerson.Offset (2.2 right, 0.9 up, 9 back) from the eye (the root + Config.Camera.EyeHeight 1.5),
        # level, looking where the player aims, Config.FOV.Base 70 degrees VERTICAL on 16:9; the whole body shows. Fixed
        # to the root as the game's camera is (no follow: a lunge leaves it as it would in play)
        sc.render.resolution_x, sc.render.resolution_y = int(size * 16 / 9), size
        cam_data = bpy.data.cameras.new("LookCamTP")
        cam_data.sensor_fit = "VERTICAL"
        cam_data.angle_y = math.radians(70.0)
        cam_data.clip_start = 0.1
        tp = bpy.data.objects.new("LookCamTP", cam_data)
        sc.collection.objects.link(tp)
        tp.location = arm.matrix_world @ (hrp_rest + Vector((2.2, -9.0, 1.5 + 0.9)))   # the rig faces +y: back = -y
        tp.rotation_euler = Vector((0.0, 1.0, 0.0)).to_track_quat("-Z", "Z").to_euler()
        extra = [(label, cam) for label, cam in cams if label == a.get("also")]
        cams = [("tp", tp)] + extra
        follow = False
        # the game's camera rides the root: a Step version's travel (the root track, composed into the rig) is followed
        # exactly, along the floor (the rig's HumanoidRootPart bone as posed each frame)
        sc.frame_set(sc.frame_start)
        tp_root0 = (arm.matrix_world @ arm.pose.bones["HumanoidRootPart"].head).copy() if "HumanoidRootPart" in arm.pose.bones else None
    cam_base = {label: cam.location.copy() for label, cam in cams}
    out_dir = os.path.abspath(a["out"])
    frames_dir = os.path.join(out_dir, f"{a['name']}.look")
    os.makedirs(frames_dir, exist_ok=True)
    rendered = []
    step = max(1, int(a["every"])) if posed else 1
    hit_frames = {f0 + int(round(float(e.get("t", 0)) * fps)) for e in (clip.get("events") or []) if str(e.get("name", "")).lower() == "hit"}
    # a TELEPORT (the owner's katana set, 2026-10-18): between a "Vanish" and the next "Appear" event the character is
    # gone - in game a script fades it on those markers (Anim.vanish); here the body and the blade are not rendered
    evs = sorted((float(e.get("t", 0)), str(e.get("name", ""))) for e in (clip.get("events") or []))
    gone, t_v, hazes, t_h = [], None, [], None
    for t_e, nm in evs:
        if nm == "Haze" and t_h is None:
            t_h = t_e
        elif nm == "Vanish" and t_v is None:
            t_v = t_e
            if t_h is not None:
                hazes.append((t_h, t_e))
                t_h = None
        elif nm == "Appear" and t_v is not None:
            gone.append((t_v, t_e))
            t_v = None
    # the HAZE (Haze .. Vanish): in game the body flickers between two see-through levels every 0.04 s (Anim.luau
    # HAZE_STEP); here it blinks on that rhythm
    for h0, h1 in hazes:
        gone += [(h0 + k * 0.04, h0 + (k + 1) * 0.04) for k in range(1, int((h1 - h0) / 0.04) + 1, 2)]
    body = [ob for ob in bpy.data.objects if (ob.parent == arm and ob.type == "MESH") or ob.name.startswith(("LookKatana", "LookGreatsword"))]
    for f in sorted(set(range(sc.frame_start, sc.frame_end + 1, step)) | {h for h in hit_frames if sc.frame_start <= h <= sc.frame_end}):
        sc.frame_set(f)
        if gone:
            t_f = (f - f0) / fps
            hidden = any(v <= t_f < ap for v, ap in gone)
            for ob in body:
                ob.hide_render = hidden or ob.name not in keep and not ob.name.startswith("Look")
        row = []
        for label, cam in cams:
            if label == "tp" and tp_root0 is not None:
                now_root = arm.matrix_world @ arm.pose.bones["HumanoidRootPart"].head
                cam.location = cam_base[label] + Vector((now_root.x - tp_root0.x, now_root.y - tp_root0.y, 0.0))
            if follow:
                # the last body centre SEEN (a vanished body has no box worth following: hold where it went)
                cam.location = cam_base[label] + (centres.get(f, centre) - centre)
            sc.camera = cam
            path = os.path.join(frames_dir, f"{label}_{f:04d}.png")
            sc.render.filepath = path
            bpy.ops.render.render(write_still=True)
            row.append(path)
        rendered.append((f, row))
    with open(os.path.join(frames_dir, "look.json"), "w", encoding="utf-8") as fh:
        # the Hit frames and the feel's hitstop: the sheet holds the GIF there (an impact freeze reads as weight)
        hits = [f0 + int(round(float(e.get("t", 0)) * fps)) for e in (clip.get("events") or []) if str(e.get("name", "")).lower() == "hit"]
        feel = clip.get("feel") if isinstance(clip.get("feel"), dict) else {}
        stop = feel.get("hitstop")
        stop_frames = int(stop.get("frames", 3)) if isinstance(stop, dict) else (int(round(float(stop) * fps)) if isinstance(stop, (int, float)) else 3)
        json.dump({"name": a["name"], "rig": "R6", "fps": fps, "views": [label for label, _ in cams],
                   "frames": [f for f, _ in rendered], "body": os.environ.get("PARALLAX_R6_RIG") or "assets/rigs/R6_IK.blend", "blend": blend_out,
                   "hits": hits, "hitstop_frames": stop_frames}, fh)
    fid_text = f"; rig = clip within {fidelity['studs']} studs / {fidelity['deg']} deg" if fidelity else ""
    return look.emit("pass", f"look {a['name']}: {len(rendered)} frames x {len(cams)} views on the owner's R6 rig (its controllers keyed{fid_text}) -> {frames_dir}; the posed rig: {blend_out}",
                     f"python kit/anim/look_sheet.py {frames_dir}", frames=len(rendered), dir=frames_dir, blend=blend_out, fidelity=fidelity)


if __name__ == "__main__":
    sys.exit(main())
