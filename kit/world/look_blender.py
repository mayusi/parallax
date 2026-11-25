"""look_blender.py — the world at EYE LEVEL (runs inside Blender): kit world look <Name>.

blender -b --factory-startup -P kit/world/look_blender.py -- build/worlds/<name>.json <out_dir> [--res 1920x1080]
Builds the compiled world (parts: Block / Ball / Cylinder / Wedge with their colours + a roughness per Roblox
material; terrain ground as a mesh from the compiler's height samples; terrain balls / cylinders / blocks; water),
lights it from the world's compiled lighting (clockTime -> sun height, the atmosphere colour -> sun tint, outdoor
ambient -> sky light, haze -> mist), and renders the world's STATIONS (1920 x 1080 unless --res says otherwise):
  eye_<n>.png   from every spawn as the player sees it: Roblox's default camera 12 studs behind his R6 rig (7.5 up,
                pulled in by a wall behind), looking at the objective / the map's centre, vertical FOV 70
  view_<name>.png  the blueprint's own "views" (inside a house, down a lane)
  at_<name>.png the same camera behind the rig standing AT each objective (the first two), looking back the way he came
  over.png      an establishing shot from above a corner
and writes stations.json: every station's name, kind, title and CAMERA in Roblox's own axes (studs), so
`kit world studio` shoots the very same views in Roblox Studio (kit/world/studio_shots.py) and the pages
(kit/world/lookpages.py) can say what each one is.
Real meshes: parts with "mesh": "<name>" are imported from the world's build/worldmeshes/<name>.fbx (once each,
as hidden templates) and placed as linked duplicates scaled to match the placeholder's size.
R6 scale figure: a blocky R6 rig (5 studs tall, neutral grey) stands 4-10 studs in front of each eye camera (closer
when something is in the way), on the first surface under its head, so every eye_N.png shows the rig for scale.
Each mesh is fitted by its own box to its part's box (as Roblox fits a MeshPart) and read back: placement_error.
Roblox space (+Y up) -> Blender (+Z up): (x, y, z) -> (x, -z, y); 1 stud = 1 Blender unit.
Prints one JSON line: {status, summary, next_action, renders:[], meshes_placed, distinct_meshes, placeholders_primitive,
placement_error}.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

ROUGH = {"Metal": 0.35, "DiamondPlate": 0.4, "Glass": 0.05, "Neon": 0.5, "SmoothPlastic": 0.3, "Plastic": 0.5,
         "Ice": 0.1, "Marble": 0.25, "Granite": 0.6, "Slate": 0.75, "Concrete": 0.85, "Brick": 0.9, "Wood": 0.7,
         "WoodPlanks": 0.75, "Grass": 0.95, "Sand": 0.95, "Fabric": 0.95, "Cobblestone": 0.85, "Pebble": 0.85}
C = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))  # rbx -> blender basis
# Roblox's mesh import turns an FBX 180 deg about Y and export_fbx pre-turns the data to cancel it: undo it here
ROT_Z_180 = Matrix.Rotation(math.pi, 4, "Z")


def to_b(v):
    return Vector((v[0], -v[2], v[1]))


def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name, rgb, mat, transparency):
    key = f"{name}_{rgb}_{mat}_{transparency}"
    m = bpy.data.materials.get(key)
    if m:
        return m
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    col = [srgb_to_linear(c) for c in rgb] + [1.0]
    bsdf.inputs["Base Color"].default_value = col
    bsdf.inputs["Roughness"].default_value = ROUGH.get(mat, 0.6)
    if mat == "Metal" or mat == "DiamondPlate":
        bsdf.inputs["Metallic"].default_value = 0.8
    if mat == "Neon":
        for key2 in ("Emission Color", "Emission"):
            if key2 in bsdf.inputs:
                bsdf.inputs[key2].default_value = col
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 3.0
    if transparency and transparency > 0:
        bsdf.inputs["Alpha"].default_value = max(0.0, 1.0 - transparency)
    return m


def add_part(p):
    shape = p.get("shape") or "Block"
    sx, sy, sz = p["size"]
    if p.get("class") == "WedgePart":
        # Roblox wedge: full height at the back (+Z local), sloping to the front (-Z): profile in local y-z
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        verts = [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (hx, -hy, -hz), (hx, -hy, hz), (hx, hy, hz)]
        faces = [(0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (0, 2, 5, 3)]
        mesh = bpy.data.meshes.new(p["name"])
        mesh.from_pydata(verts, [], faces)
        obj = bpy.data.objects.new(p["name"], mesh)
        bpy.context.collection.objects.link(obj)
        local_scale = Matrix.Identity(3)
    else:
        if shape == "Ball":
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.5)
            local_scale = Matrix.Diagonal((min(sx, sy, sz),) * 3)
        elif shape == "Cylinder":
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.5, depth=1.0)
            obj = bpy.context.active_object
            # Roblox cylinders lie along local X: rotate the mesh's Z axis onto X
            obj.data.transform(Matrix.Rotation(math.radians(90), 4, "Y"))
            local_scale = Matrix.Diagonal((sx, min(sy, sz), min(sy, sz)))
        else:
            bpy.ops.mesh.primitive_cube_add(size=1.0)
            local_scale = Matrix.Diagonal((sx, sy, sz))
        obj = bpy.context.active_object
        obj.name = p["name"]
    if p.get("class") == "WedgePart":
        pass
    r = Matrix(p.get("rot") or ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
    m3 = C @ r @ local_scale @ C.inverted() if p.get("class") != "WedgePart" else C @ r @ C.inverted()
    if p.get("class") == "WedgePart":
        # the wedge's verts are already in local studs (rbx local axes): map them through C as well
        obj.data.transform(C.to_4x4())
    else:
        obj.data.transform(C.to_4x4())
    mw = m3.to_4x4()
    mw.translation = to_b(p["pos"])
    obj.matrix_world = mw
    obj.data.materials.append(material(p["name"], tuple(p.get("color") or (163, 162, 165)), p.get("material") or "Plastic", p.get("transparency") or 0))
    if any(ch.get("kind") == "light" for ch in (p.get("children") or [])) and hasattr(obj, "visible_shadow"):
        obj.visible_shadow = False  # (a lamp's head holds its own light: in Roblox its own part never blocks it)
    return obj


def _apply_texture(objs, tex_path, alpha_clip=False):
    """Replace every material on the given objects with one that uses tex_path as the base-colour
    image texture.  For foliage (alpha_clip=True) the material uses alpha-clip blend so leaf quads
    cut out correctly instead of showing as opaque magenta quads."""
    img = bpy.data.images.get(os.path.basename(tex_path))
    if img is None:
        img = bpy.data.images.load(tex_path)
    for obj in objs:
        mat = bpy.data.materials.new(obj.name + "_tex")
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        tex_node.image = img
        nt.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha_clip:
            nt.links.new(tex_node.outputs["Alpha"], bsdf.inputs["Alpha"])
            try:
                mat.blend_method = "CLIP"
                mat.shadow_method = "CLIP"
            except AttributeError:
                pass
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def _apply_trim(objs, worldmeshes_dir, sheet):
    """a W3 module (registry "trim"): its shared trim sheet's colour + normal + roughness, as the SurfaceAppearance the
    compiler gives it -> False when a map is not there (the caller falls back as for any untextured mesh)"""
    paths = {m: os.path.join(worldmeshes_dir, f"kit_trim_{sheet}_{m}.png") for m in ("color", "normal", "roughness")}
    if not all(os.path.isfile(p) for p in paths.values()):
        return False
    mat = bpy.data.materials.get(f"kit_trim_{sheet}")
    if mat is None:
        mat = bpy.data.materials.new(f"kit_trim_{sheet}")
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        for m, p in paths.items():
            node = nt.nodes.new("ShaderNodeTexImage")
            node.image = bpy.data.images.get(os.path.basename(p)) or bpy.data.images.load(p)
            if m != "color":
                node.image.colorspace_settings.name = "Non-Color"
            if m == "color":
                nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
            elif m == "roughness":
                nt.links.new(node.outputs["Color"], bsdf.inputs["Roughness"])
            else:
                nm = nt.nodes.new("ShaderNodeNormalMap")
                nt.links.new(node.outputs["Color"], nm.inputs["Color"])
                nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    for obj in objs:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    return True


def _clear_to_grey(objs):
    """Remove any materials that might show as magenta (broken image reference) and replace with
    a neutral stone grey Principled BSDF."""
    for obj in objs:
        has_broken = False
        for mat in (obj.data.materials or []):
            if mat and mat.use_nodes:
                for node in mat.node_tree.nodes:
                    if node.type == "TEX_IMAGE" and (node.image is None or not os.path.isfile(node.image.filepath)):
                        has_broken = True
                        break
        if has_broken or not obj.data.materials:
            m = bpy.data.materials.new(obj.name + "_grey")
            m.use_nodes = True
            m.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (0.42, 0.40, 0.37, 1.0)
            obj.data.materials.clear()
            obj.data.materials.append(m)


def _fbx_import(path):
    """Import an FBX and return the imported mesh objects.  The FBXes were exported with
    axis_forward='-Z', axis_up='Y' and a 180-deg pre-turn about Z (see meshes_blender.py export_fbx).
    Importing with the same axis settings undoes the coordinate mapping and brings geometry back
    to Blender Z-up space, correctly oriented."""
    before = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.fbx(filepath=path, axis_forward="-Z", axis_up="Y", use_manual_orientation=True)
    except Exception:
        # older Blender: try without use_manual_orientation
        bpy.ops.import_scene.fbx(filepath=path, axis_forward="-Z", axis_up="Y")
    return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]


def load_mesh_templates(worldmeshes_dir, mesh_names):
    """Import each distinct FBX once as a hidden template collection.
    Returns:
      templates: dict name -> (list of objects, native_size_rbx [sx, sy, sz])
      missing:   set of names whose FBX was not found
    The native_size comes from the mesh.json (Roblox-space bounding box).
    """
    reg_path = os.path.join(worldmeshes_dir, "meshes.json")
    reg = {}
    if os.path.isfile(reg_path):
        with open(reg_path, encoding="utf-8-sig") as fh:
            reg = json.load(fh)

    # a hidden collection for the template originals
    tmpl_coll = bpy.data.collections.new("_MeshTemplates")
    bpy.context.scene.collection.children.link(tmpl_coll)
    tmpl_coll.hide_viewport = True
    tmpl_coll.hide_render = True

    templates = {}
    missing = set()

    for name in sorted(set(mesh_names)):
        fbx_path = os.path.join(worldmeshes_dir, name + ".fbx")
        if not os.path.isfile(fbx_path):
            missing.add(name)
            continue

        # native size from mesh.json (Roblox space: x, y_up, z)
        mj_path = os.path.join(worldmeshes_dir, name + ".mesh.json")
        native_size = None
        if os.path.isfile(mj_path):
            with open(mj_path, encoding="utf-8-sig") as fh:
                mj = json.load(fh)
            native_size = [mj["max"][i] - mj["min"][i] for i in range(3)]
        elif name in reg:
            native_size = reg[name]["size"]  # [x, y, z] in Roblox space

        if native_size is None or min(native_size) < 1e-6:
            missing.add(name)
            continue

        objs = _fbx_import(fbx_path)
        if not objs:
            missing.add(name)
            continue

        # apply the texture PNG from the registry (the FBX may reference paths that no longer exist)
        tex_file = reg.get(name, {}).get("texture")  # e.g. "q_fern_1__Leaves.png"
        is_foliage = reg.get(name, {}).get("foliage", False)
        trim = reg.get(name, {}).get("trim")  # a W3 module: the shared trim sheet it is mapped on
        if tex_file:
            tex_path = os.path.join(worldmeshes_dir, tex_file)
            if os.path.isfile(tex_path):
                _apply_texture(objs, tex_path, alpha_clip=is_foliage)
            else:
                # texture listed but file missing: fall through to FBX materials as-is
                tex_file = None
        elif isinstance(trim, str) and _apply_trim(objs, worldmeshes_dir, trim):
            tex_file = f"kit_trim_{trim}_color.png"  # (it shows its sheet, as its SurfaceAppearance will)
        if not tex_file and name in reg and not reg[name].get("textured"):
            # explicitly non-textured (rocks, cliffs): clear any stray magenta materials
            _clear_to_grey(objs)

        # move imported objects into the template collection and hide them
        for obj in objs:
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            tmpl_coll.objects.link(obj)
            obj.hide_set(True)
            obj.hide_render = True

        if not tex_file:
            for obj in objs:  # a slot for each placed copy's own colour (place_mesh_part)
                if not obj.data.materials:
                    obj.data.materials.append(None)
        # (place_mesh_part fits the template's own box, as Roblox does; textured = it shows its texture, not a colour)
        templates[name] = (objs, native_size, bool(tex_file))

    return templates, missing


def place_mesh_part(p, templates):
    """Place linked duplicates of the mesh template for part p where Roblox puts the MeshPart: the mesh's own box
    fitted to the part's Size and centred on its CFrame. Returns the placed objects ([] = template missing: the
    caller keeps the primitive).

    The box is the template's own, as imported (Blender world space of the import, every object of the FBX): the
    FBX holds the data export_fbx pre-turned 180 deg about Z, and the registry's min is the un-turned authoring box,
    so placing by the registry put every off-centre mesh twice its offset away (SampleRegion's Erdtree root 152 studs,
    the Stormwall 24). Axes: Blender X = Roblox X, Blender Y = Roblox -Z, Blender Z = Roblox Y (C)."""
    name = p.get("mesh")
    if name not in templates:
        return []
    objs, textured = templates[name][0], templates[name][2]
    corners = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    ext, mid = hi - lo, (lo + hi) / 2
    sx, sy, sz = p["size"]  # Roblox [X, Y (height), Z] -> Blender X, Z, Y
    fit = Matrix.Diagonal(
        (
            sx / ext.x if ext.x > 1e-6 else 1.0,
            sz / ext.y if ext.y > 1e-6 else 1.0,
            sy / ext.z if ext.z > 1e-6 else 1.0,
            1.0,
        )
    )
    r_blender = C @ Matrix(p.get("rot") or ((1, 0, 0), (0, 1, 0), (0, 0, 1))) @ C.inverted()
    # ROT_Z_180 undoes export_fbx's pre-turn (Roblox's import turns the FBX back): the mesh faces as in the game
    place = Matrix.Translation(to_b(p["pos"])) @ r_blender.to_4x4() @ ROT_Z_180 @ fit @ Matrix.Translation(-mid)
    placed = []
    for tmpl_obj in objs:
        # linked duplicate: shared mesh data, its own transform
        new_obj = tmpl_obj.copy()
        if not textured:
            # as the game dresses it (src/kit/WorldMeshes.luau): an untextured mesh shows its part's Material and
            # Color - per object, the mesh data is shared
            m = material(name, tuple(p.get("color") or (163, 162, 165)), p.get("material") or "Plastic", 0)
            for slot in new_obj.material_slots:
                slot.link = "OBJECT"
                slot.material = m
        bpy.context.scene.collection.objects.link(new_obj)
        new_obj.hide_set(False)
        new_obj.hide_render = False
        new_obj.matrix_world = place @ tmpl_obj.matrix_world
        placed.append(new_obj)
    return placed


def placement_proof(placed):
    """The largest gap (studs) between a placed mesh's box, read back from Blender, and its part's box, both in the
    part's own frame: where Roblox puts the MeshPart. A look that moves a mesh is not evidence."""
    bpy.context.view_layer.update()
    worst = 0.0
    for objs, p in placed:
        r_inv = (C @ Matrix(p.get("rot") or ((1, 0, 0), (0, 1, 0), (0, 0, 1))) @ C.inverted()).inverted()
        centre = to_b(p["pos"])
        pts = [r_inv @ (o.matrix_world @ Vector(c) - centre) for o in objs for c in o.bound_box]
        sx, sy, sz = p["size"]
        half = (sx / 2, sz / 2, sy / 2)  # Blender X, Y, Z = Roblox X, Z, Y
        for i in range(3):
            worst = max(worst, abs(min(q[i] for q in pts) + half[i]), abs(max(q[i] for q in pts) - half[i]))
    return worst




def add_r6_figure(eye_b, target_b, terrain_z_at, scene=None, at=None):
    """Build a blocky R6-proportioned figure (5 studs tall) in neutral grey, standing on the
    terrain about 10 studs in front of the eye camera and a little to one side, facing the camera.

    eye_b    — eye position in Blender space
    target_b — camera target in Blender space
    terrain_z_at — callable(bx, by) -> terrain Z (Roblox Y height) at that Blender XY position.

    Proportions (studs, 1 stud = 1 Blender unit):
      Leg L/R  1.0 × 1.0 × 2.0  (Blender: width × depth × height); bottom of leg = feet (z=0)
      Torso    2.0 × 1.0 × 2.0  bottom at z=2.0
      Arm L/R  1.0 × 1.0 × 2.0  beside torso; bottom at z=2.0
      Head     1.2 × 1.2 × 1.2  bottom at z=4.0
    Total height ≈ 5.2 studs.
    """
    grey_mat = material("R6ScaleGrey", (160, 160, 160), "SmoothPlastic", 0)

    # forward direction in Blender XY plane (from eye toward target)
    fwd = target_b - eye_b
    fwd_xy = Vector((fwd.x, fwd.y, 0.0))
    if fwd_xy.length < 0.1:
        fwd_xy = Vector((1.0, 0.0, 0.0))
    fwd_xy = fwd_xy.normalized()

    # place figure: start 10 studs forward, 2.5 studs to the right; step closer if
    # a scene raycast hits geometry before reaching that distance (a wall in the way).
    right = Vector((-fwd_xy.y, fwd_xy.x, 0.0))
    dist = 10.0
    if scene is not None:
        # cast a ray from the eye in the forward direction; if it hits something within
        # 11 studs, place the figure 1 stud in front of the hit point (clamped 4–10)
        ray_origin = eye_b
        ray_dir = Vector((fwd_xy.x, fwd_xy.y, 0.0))
        hit, hit_loc, _, _, _, _ = scene.ray_cast(bpy.context.view_layer.depsgraph,
                                                   ray_origin, ray_dir, distance=12.0)
        if hit:
            # 1 stud in front of the hit, clamped to [4, 10]
            dist = max(4.0, min(10.0, (hit_loc - ray_origin).length - 1.0))
    foot_bx = eye_b.x + fwd_xy.x * dist + right.x * 2.5
    foot_by = eye_b.y + fwd_xy.y * dist + right.y * 2.5
    if at is not None:  # (third person: the rig stands where the player stands - the spawn)
        foot_bx, foot_by = at.x, at.y

    # Foot height: the first surface below the figure's own head height (cast from 6 studs over the eye: an
    # overhanging canopy is not its floor, and on a slope down it stands on the ground, not at the camera's feet);
    # where nothing is hit, the terrain grid, never below the camera's own feet (R6 eye: 4.5 studs over them)
    foot_bz = at.z if at is not None else None
    if scene is not None and at is None:
        hit_dn, hit_loc_dn, _, _, _, _ = scene.ray_cast(bpy.context.view_layer.depsgraph,
                                                          Vector((foot_bx, foot_by, eye_b.z + 6.0)),
                                                          Vector((0.0, 0.0, -1.0)), distance=200.0)
        if hit_dn:
            foot_bz = hit_loc_dn.z
    if foot_bz is None:
        foot_bz = max(terrain_z_at(foot_bx, foot_by), eye_b.z - 4.5)

    # yaw: figure faces back toward the camera; atan2 gives Z-rotation in Blender
    face_dx = eye_b.x - foot_bx
    face_dy = eye_b.y - foot_by
    yaw = math.atan2(face_dy, face_dx) - math.pi / 2  # -pi/2: cube's local Y → face direction

    def add_box(sx, sy, sz, local_x_offset, bottom_z_offset):
        """Place a box (sx wide, sy deep, sz tall) in Blender units.
        local_x_offset: across-body offset in the figure's rotated XY plane.
        bottom_z_offset: height of the box's bottom above foot_bz (Blender Z, straight up).
        Uses location/scale/rotation_euler directly — no matrix math — to avoid any
        matrix ordering confusion."""
        # create a fresh cube mesh (no ops to avoid context-state issues)
        # Build a box mesh directly in local space.  Z is Blender up: the box goes from
        # -sz/2 to +sz/2 in Z so the object stands upright regardless of rotation_euler.
        me = bpy.data.meshes.new("R6Scale")
        hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
        verts = [
            (-hx, -hy, -hz), ( hx, -hy, -hz), ( hx,  hy, -hz), (-hx,  hy, -hz),  # bottom
            (-hx, -hy,  hz), ( hx, -hy,  hz), ( hx,  hy,  hz), (-hx,  hy,  hz),  # top
        ]
        faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
        me.from_pydata(verts, [], faces)
        me.update()
        obj = bpy.data.objects.new("R6Scale", me)
        bpy.context.scene.collection.objects.link(obj)

        # world position: rotate the across-body offset by yaw, add foot + vertical offset
        # center of this box in world space
        cx = foot_bx + local_x_offset * math.cos(yaw)
        cy = foot_by + local_x_offset * math.sin(yaw)
        cz = foot_bz + bottom_z_offset + sz / 2.0

        # Set location directly — no matrix math.  rotation_euler is a Z-only yaw so Z stays up.
        obj.location = (cx, cy, cz)
        obj.rotation_euler = (0.0, 0.0, yaw)
        obj.data.materials.append(grey_mat)
        return obj

    created = []

    def _add_box(sx, sy, sz, local_x_offset, bottom_z_offset):
        obj = add_box(sx, sy, sz, local_x_offset, bottom_z_offset)
        created.append(obj)

    # R6 body parts stacked from feet upward (Blender Z = up = Roblox Y)
    # legs: two 1×1×2 boxes, side by side across body (local X offsets ±0.5)
    _add_box(1.0, 1.0, 2.0, -0.5, 0.0)
    _add_box(1.0, 1.0, 2.0, +0.5, 0.0)
    # torso: 2×1×2 centred at x=0, bottom at z=2.0
    _add_box(2.0, 1.0, 2.0, 0.0, 2.0)
    # arms: 1×1×2 each, beside the torso (local X ±1.5), bottom at z=2.0
    _add_box(1.0, 1.0, 2.0, -1.5, 2.0)
    _add_box(1.0, 1.0, 2.0, +1.5, 2.0)
    # head: 1.2×1.2×1.2, centred at x=0, bottom at z=4.0
    _add_box(1.2, 1.2, 1.2, 0.0, 4.0)
    return created


def _terrain_height_lookup(terr):
    """Return a callable(bx, by) -> bz that approximates the terrain's Z at a Blender XY position,
    by sampling the nearest grid cell of every ground patch there and keeping the top one."""
    patches = (terr or {}).get("ground", [])
    if not patches:
        return lambda bx, by: 0.0

    def lookup(bx, by):
        # Blender: bx=Roblox X, by=Roblox-Z negated, bz=Roblox Y
        # Reverse: Roblox X = bx, Roblox Z = -by
        rx, rz = bx, -by
        best_z = None
        for g in patches:
            nx_g, nz_g, step = g["nx"], g["nz"], g["step"]
            x0, z0 = g["x0"], g["z0"]
            hs = g["heights"]
            ix = int(round((rx - x0) / step))
            iz = int(round((rz - z0) / step))
            if 0 <= ix < nx_g and 0 <= iz < nz_g:
                h = hs[ix * nz_g + iz]  # Roblox Y (height) -> Blender Z
                # the TOP patch: a far ring runs on under the map (SampleRegion: -95 under a meadow at 20)
                best_z = h if best_z is None else max(best_z, h)
        return best_z if best_z is not None else 0.0

    return lookup


def night_sky(scene, L, clock):
    """Night as Roblox shows it (the compiled lighting, e.g. the "night" preset): the moon is the directional light
    (opposite the day sun, its height from the clock), the sky a deep gradient toward the atmosphere's colour, the
    shadows lit by the world's outdoor ambient (a Light Path mix: the camera sees the sky, surfaces get the ambient),
    the preset's exposure."""
    mclock = (clock + 12.0) % 24.0
    elev = max(8.0, 90 * (1 - abs(mclock - 12) / 6.5)) if 5.5 < mclock < 18.5 else 8.0
    tint = (L.get("colorCorrection") or {}).get("tint", (202, 216, 255))
    moon = bpy.data.objects.new("Moon", bpy.data.lights.new("Moon", "SUN"))
    scene.collection.objects.link(moon)
    moon.data.energy = 0.6 * float(L.get("brightness", 1))
    moon.data.color = [c / 255 for c in tint]
    moon.data.angle = math.radians(0.6)
    moon.rotation_euler = (math.radians(90 - elev), 0, math.radians(35 + 180))
    world = bpy.data.worlds.new("Night")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    hor = [srgb_to_linear(c) * 0.55 for c in ((L.get("atmosphere") or {}).get("color", (62, 72, 102)))]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*hor, 1)
    els[1].position, els[1].color = 0.6, (0.004, 0.006, 0.014, 1)
    mid = els.new(0.15)
    mid.color = (hor[0] * 0.35, hor[1] * 0.35, hor[2] * 0.45, 1)
    amb = [srgb_to_linear(c) * 1.6 for c in L.get("outdoorAmbient", (44, 54, 84))]
    try:  # the camera sees the sky; diffuse light comes from the ambient
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        a = next(i for i in mix.inputs if i.name == "A" and i.type == "RGBA")
        b = next(i for i in mix.inputs if i.name == "B" and i.type == "RGBA")
        out = next(o for o in mix.outputs if o.type == "RGBA")
        a.default_value = (*amb, 1)
        nt.links.new(ramp.outputs["Color"], b)
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Factor"])
        nt.links.new(out, bg.inputs["Color"])
    except Exception:  # noqa: BLE001 - an older Blender: the gradient alone
        nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    scene.view_settings.exposure = float(L.get("exposure", 0.0))


def add_part_lights(p):
    """the part's PointLight / SpotLight children (a lamp, a hearth, a window's glow) as Blender point lights: a
    Roblox light of brightness b reaches `range` studs, so the energy grows with range^2 (b at half range)"""
    n = 0
    for ch in p.get("children") or []:
        if ch.get("kind") != "light":
            continue
        sp = ch.get("spec") or {}
        rng, br = float(sp.get("range", 16)), float(sp.get("brightness", 1))
        ld = bpy.data.lights.new("PartLight", "POINT")
        ld.energy = math.pi * rng * rng * br
        ld.color = [c / 255 for c in sp.get("color", (255, 220, 180))]
        ld.shadow_soft_size = 0.3
        if hasattr(ld, "use_custom_distance"):
            ld.use_custom_distance = True
            ld.cutoff_distance = rng
        lo = bpy.data.objects.new("PartLight", ld)
        lo.location = to_b(p["pos"])
        bpy.context.scene.collection.objects.link(lo)
        n += 1
    return n


def write_labels(scene, cam, labels, path):
    """project the blueprint's labels ("at" in studs, Roblox axes) into this shot; a point off the picture or behind
    something (a ray-cast from the camera) is "not in view" - kit/world/frame_labels.py draws them"""
    from bpy_extras.object_utils import world_to_camera_view

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    w_px, h_px = scene.render.resolution_x, scene.render.resolution_y
    out = []
    for lb in labels:
        if not isinstance(lb, dict) or "at" not in lb or "text" not in lb:
            continue
        p = to_b(lb["at"])
        v = world_to_camera_view(scene, cam, p)
        seen = v.z > 0 and 0.0 <= v.x <= 1.0 and 0.0 <= v.y <= 1.0
        if seen:
            d = p - cam.location
            hit, loc, _, _, _, _ = scene.ray_cast(dg, cam.location, d.normalized(), distance=d.length)
            seen = not hit or (loc - cam.location).length >= d.length - 1.0
        out.append({"text": str(lb["text"]), "px": [round(v.x * w_px, 1), round((1.0 - v.y) * h_px, 1)],
                    "seen": bool(seen)})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"size": [w_px, h_px], "labels": out}, fh, indent=1)


def add_ground(g, mat, rock=None, rock_slope=38.0):
    nx, nz, step = g["nx"], g["nz"], g["step"]
    hs = g["heights"]
    verts, faces = [], []
    for ix in range(nx):
        for iz in range(nz):
            x, z = g["x0"] + ix * step, g["z0"] + iz * step
            verts.append(tuple(to_b((x, hs[ix * nz + iz], z))))
    for ix in range(nx - 1):
        for iz in range(nz - 1):
            a = ix * nz + iz
            faces.append((a, a + nz, a + nz + 1, a + 1))
    mesh = bpy.data.meshes.new("Ground")
    mesh.from_pydata(verts, [], faces)
    mesh.shade_smooth() if hasattr(mesh, "shade_smooth") else None
    obj = bpy.data.objects.new("Ground", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    if rock is not None:
        # slopes steeper than rockSlope render as rock, as the game paints them (src/kit/Environment.luau)
        obj.data.materials.append(rock)
        limit = math.cos(math.radians(rock_slope))
        for poly in mesh.polygons:
            poly.material_index = 1 if abs(poly.normal.z) < limit else 0  # (the y/z flip makes faces point down)


def look_at(cam, target):
    d = (target - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def main(argv):
    # absolute: Blender resolves a relative render path against its own folder, not the project
    path, out_dir = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    # 1920 x 1080 (960 x 540 until 2026-11-12: a station was 520 px wide on the sheet the session looked at)
    res = (1920, 1080)
    if "--res" in argv:
        w, h = argv[argv.index("--res") + 1].split("x")
        res = (int(w), int(h))
    with open(path, encoding="utf-8-sig") as fh:
        w = json.load(fh)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.film_transparent = False

    # --- real meshes: load FBX templates from the world's worldmeshes directory ---
    # The worldmeshes folder is at <world_build_dir>/../worldmeshes relative to the JSON file.
    # E.g. games/SampleRegion/build/worlds/SampleRegion.json -> games/SampleRegion/build/worldmeshes/
    build_dir = os.path.dirname(os.path.dirname(path))  # games/<Game>/build/
    worldmeshes_dir = os.path.join(build_dir, "worldmeshes")

    all_parts = w["parts"]
    mesh_part_names = [p["mesh"] for p in all_parts if p.get("mesh")]
    templates, missing_meshes = {}, set()
    if mesh_part_names and os.path.isdir(worldmeshes_dir):
        templates, missing_meshes = load_mesh_templates(worldmeshes_dir, mesh_part_names)

    # --- place all parts ---
    meshes_placed = 0
    placeholders_primitive = 0
    placed_meshes = []  # (objects, part): the placement proof below
    # mesh placeholder parts have transparency=1 (the runtime replaces them with real MeshParts):
    # include them here so we can substitute the real FBX mesh.  Non-mesh parts at transparency=1
    # are still invisible and skipped.
    parts = [p for p in all_parts if (p.get("transparency") or 0) < 1 or p.get("mesh")]
    for p in parts:
        if p.get("mesh"):
            placed = place_mesh_part(p, templates)
            if placed:
                meshes_placed += 1
                placed_meshes.append((placed, p))
            else:
                placeholders_primitive += 1
                # the placeholder was invisible (transparency=1); only add a primitive if we have one
                if (p.get("transparency") or 0) < 1:
                    add_part(p)
        else:
            add_part(p)
    distinct_meshes = len(templates)
    lights_placed = sum(add_part_lights(p) for p in all_parts)
    # every placed mesh read back against its part's box (where Roblox puts the MeshPart): a look that moves a
    # mesh is not evidence
    placement_error = placement_proof(placed_meshes)
    if placement_error > 0.1:
        print(json.dumps({"status": "fail",
                          "summary": f"world look: a mesh sits {placement_error:.2f} studs off its part's box (where Roblox puts it)",
                          "next_action": "fix place_mesh_part in kit/world/look_blender.py before showing these renders"}))
        return 1

    terr = w.get("terrain") or {}
    grass = material("ground", (106, 127, 63), "Grass", 0)
    rock_mat = material("rockface", (112, 108, 102), "Slate", 0)
    for g in terr.get("ground", []):
        add_ground(g, grass, rock_mat if g.get("rock") else None, float(g.get("rockSlope") or 38))
    rock = material("rock", (102, 108, 111), "Slate", 0)
    for op in terr.get("solids", []):
        s = op["spec"]
        if op["kind"] == "ball":
            o = add_part({"name": "TerrainBall", "size": [2 * s["radius"]] * 3, "pos": s["center"], "shape": "Ball", "color": (102, 108, 111), "material": "Slate"})
        elif op["kind"] == "cylinder":
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=s["radius"], depth=s["height"], location=to_b(s["center"]))
            o = bpy.context.active_object
            o.data.materials.append(rock)
        elif op["kind"] == "block":
            add_part({"name": "TerrainBlock", "size": s["size"], "pos": s["center"], "color": (102, 108, 111), "material": "Slate"})
    water = material("water", (40, 90, 120), "Glass", 0.3)
    for wv in terr.get("water", []):
        add_part({"name": "Water", "size": wv["size"], "pos": wv["center"], "color": (40, 90, 120), "material": "Glass", "transparency": 0.3})
    _ = water
    # light from the compiled lighting
    L = w.get("lighting") or {}
    clock = float(L.get("clockTime", 14))
    night = not (5.5 < clock < 18.5)
    elev = max(4.0, 90 * (1 - abs(clock - 12) / 6.5)) if 5.5 < clock < 18.5 else 4.0
    atm = L.get("atmosphere") or {}
    if night:  # (the sun's sunset branch below painted a night world as a low-sun dusk)
        night_sky(scene, L, clock)
    sun_col = [c / 255 for c in atm.get("color", (255, 244, 230))]
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    if night:
        sun = None
    else:
        scene.collection.objects.link(sun)
    if not night:
        sun.data.energy = 2.2 * float(L.get("brightness", 2)) / 2
        sun.data.color = sun_col
        sun.rotation_euler = (math.radians(90 - elev), 0, math.radians(35))
        world = bpy.data.worlds.new("Sky")
        scene.world = world
        world.use_nodes = True
        nt = world.node_tree
        bg = nt.nodes.get("Background")
        amb = L.get("outdoorAmbient", (128, 140, 160))
        # a PHYSICAL sky from the same sun (the ambient colour alone painted the sky mud-brown); the ambient tints it
        sky = None
        try:
            sky = nt.nodes.new("ShaderNodeTexSky")
            types = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
            for t in ("NISHITA", "MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "HOSEK_WILKIE", "PREETHAM"):
                if t in types:
                    sky.sky_type = t
                    break
            if hasattr(sky, "sun_elevation"):
                sky.sun_elevation = math.radians(elev)
                sky.sun_rotation = math.radians(35)
            elif hasattr(sky, "sun_direction"):
                sky.sun_direction = (math.cos(math.radians(elev)) * math.sin(math.radians(35)), -math.cos(math.radians(elev)) * math.cos(math.radians(35)), math.sin(math.radians(elev)))
            if hasattr(sky, "sun_disc"):
                sky.sun_disc = False
            nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
            bg.inputs["Strength"].default_value = 0.35
        except Exception:  # noqa: BLE001 — an older Blender: the flat ambient colour, as before
            sky = None
        if sky is None:
            bg.inputs["Color"].default_value = [srgb_to_linear(c) for c in amb] + [1]
            bg.inputs["Strength"].default_value = 0.8
    scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    # cameras
    pts = [to_b(p["pos"]) for p in w["parts"] if not p.get("backdrop")]
    for g in [g for g in terr.get("ground", []) if not g.get("backdrop")]:  # the shot frames the terrain too, not just the parts
        hs = g["heights"]
        pts += [to_b((g["x0"], min(hs), g["z0"])), to_b((g["x0"] + (g["nx"] - 1) * g["step"], max(hs), g["z0"] + (g["nz"] - 1) * g["step"]))]
    lo = Vector((min(v.x for v in pts), min(v.y for v in pts), min(v.z for v in pts)))
    hi = Vector((max(v.x for v in pts), max(v.y for v in pts), max(v.z for v in pts)))
    centre = (lo + hi) / 2
    objectives = w.get("objectives") or []
    target_r = objectives[0]["pos"] if objectives else None
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):  # (a last run's labels and unlabelled copies: this run writes its own)
        if f.endswith(".labels.json") or f.endswith(".raw.png"):
            os.remove(os.path.join(out_dir, f))
    renders = []
    stations = []  # every shot's camera in Roblox's own axes: kit world studio shoots the very same views in Studio

    def rbx(v):  # (Blender -> Roblox axes, studs)
        return [round(v.x, 3), round(v.z, 3), round(-v.y, 3)]

    # terrain height lookup for grounding the R6 figure
    terrain_z = _terrain_height_lookup(terr)

    def shoot(name, loc, target, fov=70, extra_labels=None, own_labels=None, kind="view", title=None, about=None,
              rig=None):
        base, k = name, 2
        while name in [s["name"] for s in stations]:  # (two views or objectives whose names come out the same
            name, k = f"{base}_{k}", k + 1           # as a file name: each keeps its own picture)
        cam_data = bpy.data.cameras.new(name)
        cam_data.sensor_fit = "VERTICAL"
        cam_data.angle_y = math.radians(fov)
        cam_data.clip_end = 5000
        cam = bpy.data.objects.new(name, cam_data)
        scene.collection.objects.link(cam)
        cam.location = loc
        look_at(cam, target)
        scene.camera = cam
        scene.render.filepath = os.path.join(out_dir, name + ".png")
        bpy.ops.render.render(write_still=True)
        renders.append(os.path.relpath(scene.render.filepath).replace("\\", "/"))
        # the blueprint's plain-word labels for this shot (kit world look draws them); a named view carries its own
        labels = own_labels if own_labels is not None else (list(w["labels"]) + list(extra_labels or []) if w.get("labels") else [])
        if labels:
            write_labels(scene, cam, labels, os.path.join(out_dir, name + ".labels.json"))
        stations.append({"name": name, "kind": kind, "title": title or name, "about": about or "",
                         "file": name + ".png", "cam": rbx(cam.location), "target": rbx(target), "fov": fov,
                         "rig": rbx(rig) if rig is not None else None})

    spawns = [p for p in w["parts"] if p.get("spawn")]
    dg = bpy.context.evaluated_depsgraph_get()

    def behind_rig(name, feet, toward, kind, title, about):
        # what the player sees: Roblox's default camera, 12 studs behind his R6 rig standing at `feet` and 7.5 up,
        # pulled in when a wall stands behind it (as the game's camera is); the owner, 2026-11-11, on a frame from
        # nowhere: "I don't know what I'm exactly looking at"
        head = feet + Vector((0, 0, 4.5))
        tgt = toward
        if (tgt - head).length < 4:
            tgt = head + Vector((0, 20, 0))
        fwd = Vector((tgt.x - feet.x, tgt.y - feet.y, 0.0))
        fwd = fwd.normalized() if fwd.length > 1e-6 else Vector((0.0, 1.0, 0.0))
        dist = 12.0
        hit, loc, _, _, _, _ = scene.ray_cast(dg, head, -fwd, distance=dist)
        if hit:
            dist = (loc - head).length - 0.6
        if dist < 2.0:
            # a wall at his back: Roblox's camera closes in until it is his own eyes. (Held 2 studs behind him
            # regardless, the camera sat INSIDE that wall and the picture was the wall's inside.)
            eye = head + fwd * 0.4
            shoot(name, eye, eye + fwd * 40.0, kind=kind, title=title + " (through his eyes: a wall is at his back)",
                  about=about)
            return
        cam = feet - fwd * dist + Vector((0.0, 0.0, 7.5))
        # Roblox's camera stays level on the character: aim 40 studs ahead at 6 up, not up at a far objective (the
        # GothicCourtyard look tilted up at its terrace and cut the rig off the bottom of the picture)
        tgt = feet + fwd * 40.0 + Vector((0.0, 0.0, 6.0))
        # place R6 figure in this shot; delete it right after so it does not appear in later shots
        fig_objs = add_r6_figure(cam, tgt, terrain_z, scene=scene, at=feet)
        you = [{"at": [feet.x, feet.z + 5.6, -feet.y], "text": "you (your R6 rig, 5 studs tall)"}]
        shoot(name, cam, tgt, extra_labels=you, kind=kind, title=title, about=about, rig=feet)
        for fo in (fig_objs or []):
            bpy.data.objects.remove(fo, do_unlink=True)

    first_spawn = None
    for i, s in enumerate(spawns[:6]):
        feet = to_b((s["pos"][0], s["pos"][1] + s["size"][1] / 2, s["pos"][2]))
        first_spawn = feet if first_spawn is None else first_spawn
        if target_r:
            tgt = to_b((target_r[0], target_r[1] + 3, target_r[2]))
        else:
            tgt = Vector((centre.x, centre.y, feet.z + 4.5))
        toward = f"toward {objectives[0].get('name', 'the objective')}" if target_r else "toward the middle of the map"
        behind_rig(f"eye_{i + 1}", feet, tgt, "spawn", f"spawn {i + 1}",
                   f"what a player sees first at spawn {i + 1}: Roblox's own camera behind the R6 rig, looking {toward}")
    for v in w.get("views") or []:  # the blueprint's own camera views (inside a house, down a lane)
        if isinstance(v, dict) and v.get("at") and v.get("target"):
            nm = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(v.get("name", "view")))
            shoot(f"view_{nm}", to_b(v["at"]), to_b(v["target"]), fov=float(v.get("fov", 70)),
                  own_labels=list(v.get("labels") or []), kind="view",
                  title=str(v.get("name", "view")).replace("_", " "),
                  about=str(v.get("shows") or "a view the blueprint names (its \"views\")"))
    # AT each objective (the first two), looking back the way the player came: the web tour (kit world shots) has
    # always stood there; the eye-level look only ever looked AT it from the spawns
    for o in [o for o in objectives if isinstance(o, dict) and o.get("pos")][:2]:
        p = to_b(o["pos"])
        back = first_spawn if first_spawn is not None else Vector((centre.x, centre.y, p.z))
        # he stands 6 studs short of the objective on the way he came (an objective's point is often ON the thing -
        # against the wall, inside the shrine), on the first floor under that spot; no floor there (the step leaves
        # a ledge): on the objective's own spot
        way = Vector((back.x - p.x, back.y - p.y, 0.0))
        way = way.normalized() if way.length > 1e-6 else Vector((0.0, -1.0, 0.0))
        feet = None
        for spot in (p + way * 6.0, p):
            hit, loc, _, _, _, _ = scene.ray_cast(dg, spot + Vector((0.0, 0.0, 3.0)), Vector((0.0, 0.0, -1.0)), distance=12.0)
            if hit:
                feet = Vector((spot.x, spot.y, loc.z))
                break
        if feet is None:
            feet = Vector((p.x, p.y, max(terrain_z(p.x, p.y), p.z)))
        nm = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(o.get("name", "objective")))
        behind_rig(f"at_{nm}", feet, Vector((back.x, back.y, feet.z + 4.5)), "objective",
                   f"at {o.get('name', 'the objective')}",
                   f"standing at {o.get('name', 'the objective')}, looking back "
                   + ("toward spawn 1" if first_spawn is not None else "over the map"))
    span = max((hi - lo).x, (hi - lo).y, 40)
    shoot("over", Vector((lo.x - span * 0.25, lo.y - span * 0.25, hi.z + span * 0.55)), Vector((centre.x, centre.y, lo.z)), fov=50,
          kind="over", title="the whole place from above", about="an establishing shot from above one corner (no player here)")
    for f in os.listdir(out_dir):  # (a station a last run made and this one did not: its picture would lie)
        stem = f[:-4] if f.endswith(".png") and not f.endswith(".raw.png") else None
        if stem and stem.split("_")[0] in ("eye", "view", "at", "over") and stem not in [s["name"] for s in stations]:
            os.remove(os.path.join(out_dir, f))
    with open(os.path.join(out_dir, "stations.json"), "w", encoding="utf-8") as fh:
        json.dump({"world": w["name"], "res": list(res), "night": bool(night),
                   "lit_by": "Blender (EEVEE) from the world's compiled lighting: a stand-in for Roblox's light",
                   "stations": stations}, fh, indent=1)
    print(json.dumps({"status": "pass",
                      "summary": f"{len(renders)} render(s) of {w['name']}; {meshes_placed} mesh(es) placed ({distinct_meshes} distinct FBX), {placeholders_primitive} primitive placeholder(s) (missing FBX); every mesh on its part's box to {placement_error:.3f} studs",
                      "next_action": f"look at {out_dir}",
                      "renders": renders,
                      "meshes_placed": meshes_placed,
                      "distinct_meshes": distinct_meshes,
                      "placeholders_primitive": placeholders_primitive,
                      "placement_error": round(placement_error, 4),
                      "lights": lights_placed, "night": bool(night),
                      "res": list(res), "stations": [s["name"] for s in stations]}))
    return 0


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    try:
        sys.exit(main(argv))
    except Exception as exc:  # noqa: BLE001 — one JSON verdict line, even on a crash
        import traceback

        traceback.print_exc()
        print(json.dumps({"status": "fail", "summary": f"look crashed: {exc}", "next_action": "read the traceback above"}))
        sys.exit(2)
