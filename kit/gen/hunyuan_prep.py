"""hunyuan_prep.py — (Blender) a kit asset or a mesh file -> one triangulated, UV-unwrapped GLB for `kit gen paint`.

    blender -b --factory-startup -P kit/gen/hunyuan_prep.py -- <asset.blend | mesh.glb/.gltf/.obj/.fbx> <out.glb>
        [--faces 100000]

- an asset's FULL build (build/models/<name>.blend) is read, never its upload FBX (that one is pre-turned half a turn
  for Roblox's importer); every visible mesh is joined with its world placement;
- the frame is kept: the GLB's coordinates are Roblox's (x right, y up, front -Z), as a.import_mesh reads them;
- more faces than --faces: reduced (Blender's collapse decimation) — the texture is for the surface, not the edges;
- a fresh UV layout (Smart UV Project, one island per flat-ish region) that Hunyuan3D-2 Paint bakes into; one
  plain material (the paint replaces it).
Prints one JSON line (faces, extents in studs).
"""

import json
import math
import os
import sys

import bmesh
import bpy


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def load(src):
    ext = os.path.splitext(src)[1].lower()
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(src))
        return
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=os.path.abspath(src), merge_vertices=True)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=os.path.abspath(src))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=os.path.abspath(src))
    else:
        raise ValueError(f"hunyuan_prep: {ext} — use an asset name or a .glb / .gltf / .obj / .fbx")


def joined(name):
    """every visible mesh, evaluated (modifiers applied) and placed in the world, as one triangulated mesh"""
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    count = 0
    for o in bpy.data.objects:
        if o.type != "MESH" or o.hide_render or not len(o.data.polygons):
            continue
        ev = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev)
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        count += 1
    # one connected surface: a flat-shaded glTF arrives as loose triangles (its exporter splits every vertex per
    # face), and a collapse decimation of loose triangles shreds the mesh (the 2026-10-09 Glock: 102k open edges of
    # 150k — a see-through "pencil sketch" in every render)
    if bm.verts:
        xs = [v.co for v in bm.verts]
        span = max(max(c[i] for c in xs) - min(c[i] for c in xs) for i in range(3))
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(span, 1e-9) * 1e-6)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for uv in list(me.uv_layers):
        me.uv_layers.remove(uv)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj, count


def main(argv):
    if len(argv) < 2:
        return emit("fail", "hunyuan_prep: usage: -- <asset.blend | mesh> <out.glb> [--faces N]",
                    "lune run kit gen paint <asset-or-mesh> --image <picture>")
    src, out = argv[0], argv[1]
    cap = int(argv[argv.index("--faces") + 1]) if "--faces" in argv else 100000
    load(src)
    obj, parts = joined("paint_mesh")
    if not parts:
        return emit("fail", f"hunyuan_prep: {src} has no visible mesh",
                    "check the asset built: lune run kit asset <name>")
    faces_in = len(obj.data.polygons)
    if faces_in > cap:
        mod = obj.modifiers.new("reduce", "DECIMATE")
        mod.ratio = cap / faces_in
        mod.use_collapse_triangulate = True
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
        obj.modifiers.remove(mod)
        old = obj.data
        obj.data = me
        bpy.data.meshes.remove(old)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.data.uv_layers.new(name="paint_uv")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    # one plain material: a glTF primitive without one loses its UVs in trimesh (the runner's reader)
    obj.data.materials.append(bpy.data.materials.new("paint_base"))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(out), export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=True)
    xs = [v.co for v in obj.data.vertices]
    lo = [min(c[i] for c in xs) for i in range(3)]
    hi = [max(c[i] for c in xs) for i in range(3)]
    ext = [round(hi[0] - lo[0], 4), round(hi[2] - lo[2], 4), round(hi[1] - lo[1], 4)]  # Blender -> Roblox x, y, z
    reduced = f" (reduced from {faces_in})" if faces_in > cap else ""
    return emit("pass", f"hunyuan_prep: {out} — {len(obj.data.polygons)} faces from {parts} mesh(es){reduced}, "
                        f"{ext[0]} x {ext[1]} x {ext[2]} studs",
                "paint it: hunyuan_run.py paint", out=out, faces=len(obj.data.polygons), faces_in=faces_in,
                extents=ext)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sys.exit(main(args))
