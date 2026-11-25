"""look.py — run INSIDE Blender by `kit anim look <Name>`:
    blender -b <preview.blend> --factory-startup --python-exit-code 2 -P kit/anim/look.py -- <Name> --out <dir> [--views 2] [--every 1]
The preview .blend (kit anim blend <Name> --preview: the clip keyed frame by frame on the kit rig) is rendered the way
a person judges motion: a SHADED body (Workbench: studio light, cavity, outline, a soft shadow on a gridded floor),
from the THREE-QUARTER front and the SIDE, every frame -> build/animations/<Name>.look.gif (the two views side by
side, at the clip's own rate) and <Name>.look.png (a sheet of every Nth frame with its time). No Studio needed, and
the frames are files: anything that measures pictures can read them.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

PALETTE = {  # the kit's strip colours, so a strip and a look read the same body
    "Head": (0.93, 0.80, 0.55), "Torso": (0.31, 0.47, 0.85), "UpperTorso": (0.31, 0.47, 0.85), "LowerTorso": (0.26, 0.40, 0.75),
    "HumanoidRootPart": (0.3, 0.3, 0.3),
    "Right Arm": (0.90, 0.35, 0.30), "RightUpperArm": (0.90, 0.35, 0.30), "RightLowerArm": (0.85, 0.30, 0.25), "RightHand": (0.80, 0.28, 0.22),
    "Left Arm": (0.95, 0.60, 0.25), "LeftUpperArm": (0.95, 0.60, 0.25), "LeftLowerArm": (0.90, 0.55, 0.22), "LeftHand": (0.85, 0.50, 0.20),
    "Right Leg": (0.35, 0.72, 0.45), "RightUpperLeg": (0.35, 0.72, 0.45), "RightLowerLeg": (0.30, 0.65, 0.40), "RightFoot": (0.25, 0.58, 0.35),
    "Left Leg": (0.55, 0.42, 0.80), "LeftUpperLeg": (0.55, 0.42, 0.80), "LeftLowerLeg": (0.50, 0.38, 0.72), "LeftFoot": (0.45, 0.34, 0.65),
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"name": a[0] if a else None, "out": None, "views": 2, "every": 1, "size": 420, "clip": None}
    i = 1
    while i < len(a):
        k = a[i]
        if k in ("--out", "--views", "--every", "--size", "--clip") and i + 1 < len(a):
            out[k[2:]] = a[i + 1]
            i += 2
        else:
            i += 1
    out["views"], out["every"], out["size"] = int(out["views"]), int(out["every"]), int(out["size"])
    return out


BL_FROM_RBX = ((1, 0, 0), (0, 0, -1), (0, 1, 0))   # Roblox (x, y, z) -> Blender (x, -z, y)


def bl(v):
    return Vector((v[0], -v[2], v[1]))


def _mesh_object(name, verts, faces, rgb, rough=0.5):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)
    mat.roughness = rough
    mesh.materials.append(mat)
    return ob


def build_greatsword(length, grip):
    """a greatsword along +Y from the pommel (y=0): grip, cross guard, a tapered blade with a fuller; returns the
    object and the pommel->hilt-centre distance"""
    half = grip / 2
    pommel = 0.0
    guard_y = grip + 0.15
    tip_y = guard_y + (length - half)
    verts, faces = [], []

    def box(x0, x1, y0, y1, z0, z1):
        b = len(verts)
        verts.extend([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
        faces.extend([(b, b + 1, b + 2, b + 3), (b + 4, b + 7, b + 6, b + 5), (b, b + 4, b + 5, b + 1), (b + 1, b + 5, b + 6, b + 2), (b + 2, b + 6, b + 7, b + 3), (b + 3, b + 7, b + 4, b)])

    box(-0.09, 0.09, pommel, pommel + 0.22, -0.09, 0.09)                  # pommel
    box(-0.07, 0.07, pommel + 0.2, guard_y - 0.03, -0.07, 0.07)           # grip
    box(-0.55, 0.55, guard_y - 0.03, guard_y + 0.1, -0.08, 0.08)          # cross guard
    # the blade: a flat diamond section tapering to the tip, built as a strip of quads
    sections = [(guard_y + 0.1, 0.3, 0.06), (guard_y + 0.5, 0.32, 0.06), (tip_y - 1.0, 0.26, 0.05), (tip_y - 0.35, 0.18, 0.035), (tip_y, 0.0, 0.0)]
    ring0 = None
    for y, w, t in sections:
        b = len(verts)
        verts.extend([(-w, y, 0.0), (0.0, y, t), (w, y, 0.0), (0.0, y, -t)])
        if ring0 is not None:
            for k in range(4):
                faces.append((ring0 + k, ring0 + (k + 1) % 4, b + (k + 1) % 4, b + k))
        ring0 = b
    ob = _mesh_object("LookGreatsword", verts, faces, (0.86, 0.88, 0.93), 0.35)
    return ob, half


def _built_katana():
    """the 3D lane's built katana (lune run kit asset katana -> build/models/katana.blend: one baked mesh, kashira at
    the origin, the blade up Roblox +Y, the edge at -X - the same frame as the stand-in below), as LookKatana in the
    look's local frame; None when it is not built (or KIT_LOOK_STANDIN=1): the stand-in is drawn instead"""
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    path = os.path.join(root, "build", "models", "katana.blend")   # (KIT_BUILD read C:\build inside the look's Blender)
    if os.environ.get("KIT_LOOK_STANDIN") == "1" or not os.path.isfile(path):
        return None
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n == "katana"]
    if not dst.objects or dst.objects[0] is None:
        return None
    ob = dst.objects[0]
    ob.name = "LookKatana"
    bpy.context.scene.collection.objects.link(ob)
    # its mesh in Blender axes (x, y, z) = Roblox (x, -z, y) -> the look's local frame = Roblox axes
    mesh = ob.data.copy()
    mesh.transform(Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1))) @ ob.matrix_world)
    ob.data = mesh
    ob.matrix_world = Matrix.Identity(4)
    return ob


def build_katana(length, grip):
    """a KATANA along +Y from the kashira (y=0): a dark wrapped tsuka, a round tsuba, a narrow blade with a gentle
    straight blade and a kissaki - a clip's `sword.kind: "katana"` (the owner's katana set, 2026-10-18);
    returns the blade object (the hilt parented to it) and the kashira->hilt-centre distance"""
    half = grip / 2
    real = _built_katana()
    if real is not None:
        return real, half
    tsuba_y = grip + 0.1
    tip_y = tsuba_y + (length - half)
    verts, faces = [], []

    def box(x0, x1, y0, y1, z0, z1, v, f):
        b = len(v)
        v.extend([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
        f.extend([(b, b + 1, b + 2, b + 3), (b + 4, b + 7, b + 6, b + 5), (b, b + 4, b + 5, b + 1), (b + 1, b + 5, b + 6, b + 2), (b + 2, b + 6, b + 7, b + 3), (b + 3, b + 7, b + 4, b)])

    # the blade: the edge at -x, the spine at +x
    n = 9
    ring0 = None
    blade_len = tip_y - (tsuba_y + 0.06)
    for i in range(n + 1):
        u = i / n
        y = tsuba_y + 0.06 + blade_len * u
        # STRAIGHT (the owner, 2026-10-18: "why is sword like bent wth its funny looking"): a real katana's 0.16 stud
        # curve read as a bent blade on the R6 at game scale
        sori = 0.0
        w = 0.085 if u < 0.86 else 0.085 * (1.0 - (u - 0.86) / 0.14) + 0.0
        t = 0.03 if u < 0.86 else 0.03 * (1.0 - (u - 0.86) / 0.14)
        b = len(verts)
        verts.extend([(sori - w, y, 0.0), (sori + 0.02, y, t), (sori + w, y, 0.0), (sori + 0.02, y, -t)])
        if ring0 is not None:
            for k in range(4):
                faces.append((ring0 + k, ring0 + (k + 1) % 4, b + (k + 1) % 4, b + k))
        ring0 = b
    blade_ob = _mesh_object("LookKatana", verts, faces, (0.9, 0.92, 0.96), 0.25)
    hv, hf = [], []
    box(-0.06, 0.06, 0.0, tsuba_y - 0.02, -0.045, 0.045, hv, hf)               # the tsuka (wrapped grip)
    ring = 8                                                                  # the tsuba: an octagonal disc
    for k in range(ring):
        a0, a1 = 2 * math.pi * k / ring, 2 * math.pi * (k + 1) / ring
        c = len(hv)
        r = 0.2
        hv.extend([(0.0, tsuba_y - 0.02, 0.0), (r * math.cos(a0), tsuba_y - 0.02, r * math.sin(a0)), (r * math.cos(a1), tsuba_y - 0.02, r * math.sin(a1)),
                   (0.0, tsuba_y + 0.04, 0.0), (r * math.cos(a0), tsuba_y + 0.04, r * math.sin(a0)), (r * math.cos(a1), tsuba_y + 0.04, r * math.sin(a1))])
        hf.extend([(c, c + 2, c + 1), (c + 3, c + 4, c + 5), (c + 1, c + 2, c + 5, c + 4)])
    hilt = _mesh_object("LookKatanaHilt", hv, hf, (0.1, 0.09, 0.1), 0.7)
    hilt.parent = blade_ob
    return blade_ob, half


def build_pistol(length, grip):
    """a PISTOL (a clip's `sword.kind: "pistol"`, Sample Game's Pearl, 2026-10-25) in add_weapon's frame: the origin
    0.15 behind the grip point along the barrel (+Y), the slide on top (+X: add_weapon puts the edge, the grip's
    bottom, at -X), the barrel to the muzzle at `length` from the grip; returns the object and 0 (one hand)"""
    g = 0.15
    verts, faces = [], []

    def box(x0, x1, y0, y1, z0, z1):
        b = len(verts)
        verts.extend([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
        faces.extend([(b, b + 1, b + 2, b + 3), (b + 4, b + 7, b + 6, b + 5), (b, b + 4, b + 5, b + 1), (b + 1, b + 5, b + 6, b + 2), (b + 2, b + 6, b + 7, b + 3), (b + 3, b + 7, b + 4, b)])

    box(-0.21, 0.2, g - 0.16, g + 0.16, -0.09, 0.09)              # grip
    box(0.2, 0.43, g - 0.16, g + length, -0.1, 0.1)               # slide + barrel
    box(-0.02, 0.2, g + 0.16, g + 0.42, -0.03, 0.03)              # trigger guard
    return _mesh_object("LookPistol", verts, faces, (0.82, 0.82, 0.8), 0.4), 0.0


def add_trails(paths, origin=None, tick=0.07, width=0.025):
    """MOTION TRAILS (the AAA plan #3, board/plans/archive/2026-10-18-aaa-anim-gaps.md: pros read SPACING on the motion path -
    wide gaps = fast, dense = easing - and judge ARCS before anything else): each path [(name, rgb, [character-space
    points per frame])] becomes one mesh in the scene - a thin line through the frames and a tick cube on every frame -
    visible on every frame of the look and saved in the .blend as an editable reference"""
    origin = origin or Vector((0.0, 0.0, 0.0))
    made = []
    for name, rgb, pts in paths:
        P = [bl(Vector(p)) + origin for p in pts]
        verts, faces = [], []

        def cube(c, h):
            b = len(verts)
            for dx in (-h, h):
                for dy in (-h, h):
                    for dz in (-h, h):
                        verts.append((c.x + dx, c.y + dy, c.z + dz))
            faces.extend([(b, b + 1, b + 3, b + 2), (b + 4, b + 6, b + 7, b + 5), (b, b + 4, b + 5, b + 1),
                          (b + 2, b + 3, b + 7, b + 6), (b, b + 2, b + 6, b + 4), (b + 1, b + 5, b + 7, b + 3)])

        for i, c in enumerate(P):
            cube(c, tick if i % 5 else tick * 1.6)          # every 5th frame a bigger tick: count the spacing
            if i:
                a, d = P[i - 1], c - P[i - 1]
                if d.length < 1e-6:
                    continue
                side = d.cross(Vector((0.0, 0.0, 1.0)))
                side = (side if side.length > 1e-6 else d.cross(Vector((1.0, 0.0, 0.0)))).normalized() * width
                up = d.cross(side).normalized() * width
                b = len(verts)
                for q in (a + side + up, a - side + up, a - side - up, a + side - up):
                    verts.append(tuple(q))
                for q in (c + side + up, c - side + up, c - side - up, c + side - up):
                    verts.append(tuple(q))
                for k in range(4):
                    faces.append((b + k, b + (k + 1) % 4, b + 4 + (k + 1) % 4, b + 4 + k))
        made.append(_mesh_object(f"LookArc{name}", verts, faces, rgb, 0.4))
    return made


def add_weapon(sc, clip, f0, fps, origin=None):
    """a clip that carries a weapon path (strike / rearm / keys clips: `sword`) gets a real greatsword keyed every
    frame, a motion trail (the ribbon the blade swept over the last frames, fading) and a flash at each Hit"""
    sword = clip.get("sword")
    if not sword or not sword.get("tip"):
        return None
    tips, grips = sword["tip"], sword["grip_path"]
    length = float(sword.get("length", 4.6))
    grip_half = float(sword.get("grip", 0.75)) / 2
    origin = origin or Vector((0.0, 0.0, 0.0))        # where the clip's character frame sits in this scene
    kind = str(sword.get("kind", ""))
    if kind == "pistol":
        length = (Vector(tips[0]) - Vector(grips[0])).length      # grip to muzzle (a held-ahead grip included)
    builder = {"katana": build_katana, "pistol": build_pistol}.get(kind, build_greatsword)
    blade, half = builder(length, float(sword.get("grip", 0.75)))
    hit_frames = set()
    for e in clip.get("events") or []:
        if str(e.get("name", "")).lower() in ("hit", "impact", "strike", "slam", "punch", "kick"):
            hit_frames.add(f0 + int(round(float(e.get("t", 0)) * fps)))
    world_tips, world_pommels = [], []
    edges = sword.get("edge")
    # the blade's whole ROTATION every frame (the owner, 2026-10-18: the sword 'not properly animated in alot of the
    # poses'): its line from grip to tip AND its edge (the clip's `edge`: the edge leads the cut) - the line alone left
    # the roll to a fixed up vector, the edge faced anywhere and spun. Quaternions kept on one hemisphere: no flips
    blade.rotation_mode = "QUATERNION"
    q_prev = None
    for i, (tip, grp) in enumerate(zip(tips, grips)):
        t, g = Vector(tip), Vector(grp)
        d = (t - g).normalized()
        pommel = g - d * (grip_half + 0.15)
        if edges and i < len(edges):
            y = bl(d).normalized()
            e = bl(Vector(edges[i]))
            e = (e - y * e.dot(y)).normalized()
            x = -e                                     # the models: the edge at -x (katana), the blade's width on x
            z = x.cross(y).normalized()
            q = Matrix((x, y, z)).transposed().to_quaternion()
        else:
            q = bl(d).to_track_quat("Y", "Z")
        if q_prev is not None and q.dot(q_prev) < 0:
            q.negate()
        q_prev = q
        blade.location = bl(pommel) + origin
        blade.rotation_quaternion = q
        blade.keyframe_insert("location", frame=f0 + i)
        blade.keyframe_insert("rotation_quaternion", frame=f0 + i)
        world_tips.append(bl(t) + origin)
        world_pommels.append(bl(g + d * grip_half) + origin)
    # the trail: for every frame a ribbon through the last TRAIL frames' blade segments, visible on that frame only
    TRAIL = int(os.environ.get("KIT_LOOK_TRAIL", "0"))     # off until an emissive EEVEE trail exists: the Workbench fan hid the body
    for i in range(1, len(world_tips) if TRAIL > 0 else 0):
        lo = max(0, i - TRAIL)
        if i - lo < 1:
            continue
        verts, faces = [], []
        for k in range(lo, i + 1):
            verts.append(tuple(world_pommels[k]))
            verts.append(tuple(world_tips[k]))
        for k in range(len(verts) // 2 - 1):
            a = 2 * k
            faces.append((a, a + 1, a + 3, a + 2))
        rib = _mesh_object(f"LookTrail{i:04d}", verts, faces, (0.88, 0.93, 1.0), 0.9)
        for f in (f0 + i - 1, f0 + i, f0 + i + 1):
            rib.hide_render = f != f0 + i
            rib.hide_viewport = rib.hide_render
            rib.keyframe_insert("hide_render", frame=f)
            rib.keyframe_insert("hide_viewport", frame=f)
    # the flash: a bright burst at the tip on every Hit frame
    for hf in hit_frames:
        i = hf - f0
        if 0 <= i < len(world_tips):
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.55, location=world_tips[i])
            flash = bpy.context.active_object
            flash.name = f"LookFlash{i:04d}"
            fm = bpy.data.materials.new(flash.name)
            fm.diffuse_color = (1.0, 0.95, 0.7, 1.0)
            flash.data.materials.append(fm)
            for f in (hf - 1, hf, hf + 1):
                flash.hide_render = f != hf
                flash.hide_viewport = flash.hide_render
                flash.keyframe_insert("hide_render", frame=f)
                flash.keyframe_insert("hide_viewport", frame=f)
    return blade


def find_body():
    for ob in bpy.data.objects:
        if ob.type == "MESH" and ob.vertex_groups and ob.name == "Body":
            return ob
    return None


def colour_body(body):
    """one material per part colour, assigned by vertex group: the Workbench 'MATERIAL' colour mode shows them"""
    mesh = body.data
    mats = {}
    for vg in body.vertex_groups:
        rgb = PALETTE.get(vg.name, (0.6, 0.6, 0.6))
        mat = bpy.data.materials.new(f"part_{vg.name}")
        mat.diffuse_color = (*rgb, 1.0)
        mat.roughness = 0.6
        mesh.materials.append(mat)
        mats[vg.index] = len(mesh.materials) - 1
    for poly in mesh.polygons:
        groups = {}
        for vi in poly.vertices:
            for g in mesh.vertices[vi].groups:
                groups[g.group] = groups.get(g.group, 0) + g.weight
        if groups:
            poly.material_index = mats.get(max(groups, key=groups.get), 0)


def floor_and_lights(sc, centre, radius):
    bpy.ops.mesh.primitive_plane_add(size=radius * 12, location=(centre.x, centre.y, 0.0))
    floor = bpy.context.active_object
    floor.name = "LookFloor"
    mat = bpy.data.materials.new("LookFloor")
    mat.diffuse_color = (0.80, 0.80, 0.82, 1.0)
    floor.data.materials.append(mat)
    # a grid of thin lines every stud, so steps and slides are readable
    lines = []
    n = int(radius * 6)
    for i in range(-n, n + 1):
        for horizontal in (True, False):
            bpy.ops.mesh.primitive_plane_add(size=1, location=(centre.x + (0 if horizontal else i), centre.y + (i if horizontal else 0), 0.002))
            ln = bpy.context.active_object
            ln.scale = (radius * 6, 0.012, 1) if horizontal else (0.012, radius * 6, 1)
            lm = bpy.data.materials.new("LookGrid")
            lm.diffuse_color = (0.62, 0.62, 0.65, 1.0)
            ln.data.materials.append(lm)
            lines.append(ln)
    return floor


def camera_for(sc, direction, centre, radius, aspect):
    cam_data = bpy.data.cameras.new("LookCam")
    cam = bpy.data.objects.new("LookCam", cam_data)
    sc.collection.objects.link(cam)
    d = Vector(direction).normalized()
    dist = radius * 2.6
    cam.location = centre + d * dist
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = 50
    cam_data.sensor_width = 36
    fov = 2 * math.atan(cam_data.sensor_width / (2 * cam_data.lens))
    need = radius * 1.15 / dist
    if aspect < 1:
        need = need / aspect
    if need > math.tan(fov / 2):
        cam_data.lens = cam_data.sensor_width / (2 * need)
    return cam


def main():
    a = args()
    if not a["name"] or not a["out"]:
        return emit("fail", "look: needs <Name> --out <dir>", "lune run kit anim look <Name>")
    sc = bpy.context.scene
    body = find_body()
    arm = next((ob for ob in bpy.data.objects if ob.type == "ARMATURE" and ob.get("kit_rig")), None)
    if body is None or arm is None:
        return emit("fail", "look: the preview .blend holds no kit rig body", "lune run kit anim blend <Name> --preview")
    rig_name = arm.get("kit_rig", "R15")
    colour_body(body)
    clip = None
    if a["clip"] and os.path.isfile(a["clip"]):
        with open(a["clip"], encoding="utf-8") as fh:
            clip = json.load(fh)
        add_weapon(sc, clip, sc.frame_start, sc.render.fps)
    fps = sc.render.fps
    f0, f1 = sc.frame_start, sc.frame_end
    # the body's extent over the whole clip (so the camera never crops a kick or a swing)
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for v in ev.data.vertices:
            w = ev.matrix_world @ v.co
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    centre = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1.0) * 0.8        # the body fills the frame; a long blade may clip at its tip
    ground = lo.z
    floor = floor_and_lights(sc, centre, radius)
    floor.location.z = ground - 0.002
    # Workbench: form, not lighting
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "Standard"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_object_outline = True
    sh.object_outline_color = (0.06, 0.06, 0.07)
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    sc.display.light_direction = (0.35, -0.5, 0.8)
    sc.world = bpy.data.worlds.new("LookWorld") if sc.world is None else sc.world
    sc.world.color = (0.88, 0.89, 0.92)
    size = a["size"]
    sc.render.resolution_x, sc.render.resolution_y = size, int(size * 1.25)
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False
    aspect = sc.render.resolution_x / sc.render.resolution_y
    # Blender axes here: x = Roblox x, y = Roblox -z (so the character faces -y... the rig builder maps (x,y,z)->(x,-z,y)):
    # the FRONT is -y; three-quarter front-right = (+x, -y, +z); the side (its right) = (+x, 0, small z)
    views = [("three-quarter", (0.75, -0.75, 0.42)), ("side", (1.0, 0.0, 0.12)), ("front", (0.0, -1.0, 0.15))][: max(1, a["views"])]
    cams = [(label, camera_for(sc, d, centre, radius, aspect)) for label, d in views]
    out_dir = os.path.abspath(a["out"])                # Blender resolves relative paths against the .blend, not the cwd
    frames_dir = os.path.join(out_dir, f"{a['name']}.look")
    os.makedirs(frames_dir, exist_ok=True)
    rendered = []
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        row = []
        for label, cam in cams:
            sc.camera = cam
            path = os.path.join(frames_dir, f"{label}_{f:04d}.png")
            sc.render.filepath = path
            bpy.ops.render.render(write_still=True)
            row.append(path)
        rendered.append((f, row))
    # the frames are files: kit/anim/look_sheet.py (the system Python, with PIL) makes the gif and the sheet
    with open(os.path.join(frames_dir, "look.json"), "w", encoding="utf-8") as fh:
        json.dump({"name": a["name"], "rig": rig_name, "fps": fps, "views": [label for label, _ in cams],
                   "frames": [f for f, _ in rendered]}, fh)
    return emit("pass", f"look {a['name']}: {len(rendered)} frames x {len(cams)} views rendered to {frames_dir}",
                f"python kit/anim/look_sheet.py {frames_dir}", frames=len(rendered), dir=frames_dir)


if __name__ == "__main__":
    sys.exit(main())
