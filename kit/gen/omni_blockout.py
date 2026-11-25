"""omni_blockout.py — a kit build -> the blockout Hunyuan3D-Omni is steered by (Blender, headless; kit gen omni).

    blender -b --factory-startup build/models/<asset>.blend --python-exit-code 2 -P kit/gen/omni_blockout.py -- \
        <asset> <out.npz> [--group <g>] [--picture <out.png>] [--size <px>]

Writes <out.npz>: `verts` (float32, studs, ROBLOX space — x right, y up, -Z front: the space build scripts author in,
where the asset stands) and `faces` (triangles) of the build's mesh objects: every group (<asset>, <asset>_<group>),
or one (--group main = <asset> itself). The modifiers are applied, as the build exported them.
--picture also renders the asset from its FRONT (a camera on -Z, 10 degrees above, a long lens, on white) — a clean
picture to test the pipeline with (kit/gen/README.md: the smoke test).
"""

import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

# Roblox (x, y, z) -> Blender (x, -z, y): the same matrix as kit/blender/rbx.py's BL_FROM_RBX
BL_FROM_RBX = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def objects(asset, group):
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons)]
    if group in (None, ""):
        return [o for o in meshes if o.name == asset or o.name.startswith(asset + "_")]
    name = asset if group == "main" else f"{asset}_{group}"
    return [o for o in meshes if o.name == name]


def triangles(objs):
    """the evaluated meshes' triangles in Roblox space (studs)"""
    dg = bpy.context.evaluated_depsgraph_get()
    to_rbx = BL_FROM_RBX.inverted()
    verts, faces, base = [], [], 0
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        m = to_rbx @ o.matrix_world
        co = np.array([(m @ v.co)[:] for v in me.vertices], dtype=np.float64)
        tri = np.array([t.vertices[:] for t in me.loop_triangles], dtype=np.int64).reshape(-1, 3)
        verts.append(co)
        faces.append(tri + base)
        base += len(co)
        ev.to_mesh_clear()
    return np.concatenate(verts), np.concatenate(faces)


def picture(path, objs, verts, px):
    """the asset from its front, on white (Cycles, CPU, a few samples: a test picture, not a beauty shot)"""
    sc = bpy.context.scene
    for o in bpy.data.objects:
        o.hide_render = o not in objs
    lo, hi = verts.min(0), verts.max(0)
    focus = BL_FROM_RBX.to_3x3() @ Vector(((lo + hi) / 2).tolist())
    direction = (BL_FROM_RBX.to_3x3() @ Vector((0.0, math.tan(math.radians(10)), -1.0))).normalized()
    rad = float(np.linalg.norm(hi - lo)) / 2
    cam = bpy.data.objects.new("OmniCam", bpy.data.cameras.new("OmniCam"))
    sc.collection.objects.link(cam)
    cam.data.lens = 85
    cam.location = focus + direction * (rad / (18 / 85) * 1.15)  # (half the 36 mm sensor over the lens: fits rad)
    cam.rotation_euler = (focus - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    for name, rot, energy in (("Key", (math.radians(50), 0, math.radians(-30)), 4.0),
                              ("Fill", (math.radians(60), 0, math.radians(140)), 1.5)):
        sun = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
        sun.data.energy = energy
        sun.rotation_euler = rot
        sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("OmniWhite")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sc.world = world
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = False
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.render.resolution_x = sc.render.resolution_y = px
    sc.render.filepath = os.path.abspath(path)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    bpy.ops.render.render(write_still=True)


def main(argv):
    if len(argv) < 2:
        return emit("fail", "omni_blockout: usage: -- <asset> <out.npz> [--group g] [--picture out.png]",
                    "lune run kit gen omni <name> --image <picture> --from-asset <asset>")
    asset, out = argv[0], argv[1]
    group = argv[argv.index("--group") + 1] if "--group" in argv else None
    objs = objects(asset, group)
    if not objs:
        have = sorted(o.name for o in bpy.data.objects if o.type == "MESH")
        return emit("fail", f"omni_blockout: no mesh for {asset}{f' group {group}' if group else ''} in this build "
                            f"(it has: {', '.join(have) or 'none'})",
                    f"check the group name (main, or one of the build's groups); rebuild: lune run kit asset {asset}")
    verts, faces = triangles(objs)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    np.savez_compressed(out, verts=verts.astype(np.float32), faces=faces.astype(np.int32),
                        objects=np.array([o.name for o in objs]))
    size = (verts.max(0) - verts.min(0)).round(3).tolist()
    extra = {"out": out, "objects": [o.name for o in objs], "triangles": int(len(faces)), "size_studs": size,
             "min_studs": verts.min(0).round(3).tolist()}
    if "--picture" in argv:
        pic = argv[argv.index("--picture") + 1]
        picture(pic, objs, verts, int(argv[argv.index("--size") + 1]) if "--size" in argv else 768)
        extra["picture"] = pic
    return emit("pass", f"omni_blockout: {asset} — {len(faces)} triangles from {len(objs)} object(s), "
                        f"{size[0]} x {size[1]} x {size[2]} studs", "lune run kit gen omni <name> --image <picture> "
                        f"--from-asset {asset}", **extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
