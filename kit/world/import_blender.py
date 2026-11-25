"""kit world import — vetted CC0 models (glTF) into the world-mesh registry (run by Blender, background).

    blender -b --factory-startup --python-exit-code 2 -P kit/world/import_blender.py -- <list.json> <out_dir>

<list.json>: [{ "name": "ctree_1", "file": "<path>.gltf", "foliage": ["Leaves"] }, ...] — "foliage": material-name
fragments whose pieces are leaf cards (alpha-tested, soft light in the viewer). Options per item: "split": true = every
mesh object in the file is its own asset <name>_<k> (a photoscanned SET of rocks); "maxTris": 20000 = decimated to
fit (a Roblox MeshPart's limit; photoscans come at 60k-120k); "texRes": 1024 = textures scaled down (Roblox's
largest). Textures are always written as real PNGs (scans ship JPEGs). "scale": k = the mesh scaled by k before
anything is written (kit world scan: metres -> studs, so the FBX, the .mesh.json and the registry agree); "scan": {...}
= stamped on the asset and every piece (a scanned real thing; the compiler holds it to its size). An entry stamped
"scan" is only replaced by another scan: a plain import of that name is refused.
A Roblox MeshPart carries ONE texture, so every asset is split by material into pieces: <name>__<material>.fbx +
.png (that material's base-colour image) + .mesh.json. The asset's registry entry lists its pieces with their own
bounds in the asset's space, so the compiler places them together. Writes into <out_dir>/meshes.json (shared with
kit world meshes). One JSON verdict line. Imported files are DATA: glTF only (never .blend).
"""

import json
import math
import os
import shutil
import sys

import bpy
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def export_piece(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.data.transform(Matrix.Rotation(math.pi, 4, "Z"))  # the measured Roblox import turn (see meshes_blender.py)
    try:
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, axis_forward="-Z", axis_up="Y", apply_unit_scale=True,
                                 apply_scale_options="FBX_SCALE_UNITS", bake_anim=False, add_leaf_bones=False,
                                 path_mode="COPY", embed_textures=False)
    finally:
        obj.data.transform(Matrix.Rotation(-math.pi, 4, "Z"))


def base_image(mat):
    if not mat or not mat.use_nodes:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            link = node.inputs["Base Color"].links
            if link and link[0].from_node.type == "TEX_IMAGE":
                return link[0].from_node.image
    for node in mat.node_tree.nodes:  # any image as a fallback
        if node.type == "TEX_IMAGE" and node.image:
            return node.image
    return None


def save_png(img, path, res):
    """an image (any format) -> a real PNG at most res x res"""
    im = img.copy()
    if res and max(im.size) > res:
        im.scale(res, res)
    sc = bpy.context.scene
    # (save_render applies the scene's view transform: AgX/Filmic shifted scan colours toward teal; write as-is)
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if im.channels == 4 else "RGB"
    im.save_render(path, scene=sc)
    bpy.data.images.remove(im)


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def decimate(obj, max_tris):
    """collapse until the mesh FITS (one pass overshot: boulder_01 came out at 26,611 for a 20,000 cap); -> tris"""
    if not max_tris:
        return tri_count(obj)
    if tri_count(obj) > max_tris:
        # glTF splits vertices along every UV seam: islands the collapse cannot cross (it stalled ~30 % over the cap).
        # Weld them first (UVs live per face corner, so they survive)
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.to_mesh(obj.data)
        bm.free()
    for k in range(4):
        tris = tri_count(obj)
        if tris <= max_tris:
            return tris
        m = obj.modifiers.new("fit", "DECIMATE")
        m.ratio = max_tris / tris * 0.95
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=m.name)
    tris = tri_count(obj)
    if tris > max_tris:
        raise ValueError(f"{obj.name}: {tris} tris after decimation, over the {max_tris} cap")
    return tris


def to_base(obj):
    """the mesh's bottom-centre onto the origin (a rock cut from a scanned SET kept its place in the set: placed
    at a site it landed metres away, orbiting with its yaw)"""
    from mathutils import Vector
    vs = [v.co for v in obj.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    obj.data.transform(Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))


def import_one(it, name, objs, out, reg, MB, done):
    """objs (already imported) -> one asset `name` split by material into pieces"""
    if (reg.get(name) or {}).get("scan") and not it.get("scan"):
        raise ValueError(f"{name} is a scanned real thing (kit world scan): a plain import may not replace it - "
                         "name the import another way")
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if it.get("scale"):
        obj.data.transform(Matrix.Scale(float(it["scale"]), 4))
    decimate(obj, it.get("maxTris"))
    if it.get("split") or it.get("recentre"):
        to_base(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="MATERIAL")
    bpy.ops.object.mode_set(mode="OBJECT")
    pieces = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    lo, hi, parts, tris = [1e9] * 3, [-1e9] * 3, [], 0
    for k, o in enumerate(pieces):
        mat = o.data.materials[0] if o.data.materials else None
        mname = (mat.name if mat else f"part{k}").replace(".", "_").replace(" ", "_")
        pname = f"{name}__{mname}"[:60]
        foliage = any(s.lower() in mname.lower() for s in it.get("foliage", ["Leaves", "Leaf", "Foliage", "Needle"]))
        img = base_image(mat)
        tex = None
        if img is not None:
            try:
                save_png(img, os.path.join(out, pname + ".png"), it.get("texRes", 1024))
                tex = pname + ".png"
            except Exception:  # noqa: BLE001 — a texture that will not save leaves the piece untextured
                tex = None
        data = MB.mesh_json(o, os.path.join(out, pname + ".mesh.json"), True)
        export_piece(o, os.path.join(out, pname + ".fbx"))
        size = [round(data["max"][i] - data["min"][i], 4) for i in range(3)]
        reg[pname] = {"kind": "piece", "tris": data["tris"], "size": size, "min": data["min"], "textured": tex is not None,
                      "foliage": foliage, "fbx": pname + ".fbx", "texture": tex, "of": name}
        if it.get("scan"):
            reg[pname]["scan"] = it["scan"]
        parts.append(pname)
        tris += data["tris"]
        for i in range(3):
            lo[i], hi[i] = min(lo[i], data["min"][i]), max(hi[i], data["max"][i])
    reg[name] = {"kind": "import", "parts": parts, "tris": tris, "size": [round(hi[i] - lo[i], 4) for i in range(3)],
                 "min": lo, "source": os.path.basename(it["file"])}
    if it.get("scan"):
        reg[name]["scan"] = it["scan"]
    done.append(f"{name} ({len(parts)} piece(s), {tris} tris)")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    items = json.load(open(argv[0], encoding="utf-8"))
    out = os.path.abspath(argv[1])
    os.makedirs(out, exist_ok=True)
    import meshes_blender as MB  # (its mesh_json writer; importing runs nothing: main() is guarded below)
    reg_path = os.path.join(out, "meshes.json")
    reg = json.load(open(reg_path, encoding="utf-8")) if os.path.isfile(reg_path) else {}
    done, errors = [], []
    for it in items:
        name, f = it["name"], os.path.abspath(os.path.expanduser(it["file"]))
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if not f.lower().endswith((".gltf", ".glb")):
            errors.append(f"{name}: only glTF is imported (got {os.path.basename(f)})")
            continue
        bpy.ops.import_scene.gltf(filepath=f)
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        if not objs:
            errors.append(f"{name}: no mesh in {f}")
            continue
        try:
            import_item(it, name, objs, out, reg, MB, done)
        except ValueError as e:  # (one asset over its cap: reported, the rest of the list still lands)
            errors.append(f"{name}: {e}")
    json.dump(reg, open(reg_path, "w", encoding="utf-8"), indent=1)
    ok = not errors
    print(json.dumps({"status": "pass" if ok else "fail",
                      "summary": f"{len(done)} imported: {', '.join(done)}" + (f"; {errors[0]}" if errors else ""),
                      "next_action": "use them by name in forest / tree / scatter \"meshes\"" if ok else errors[0]}))
    sys.exit(0 if ok else 1)


def import_item(it, name, objs, out, reg, MB, done):
    """one list item -> its asset(s); a scanned SET with "split" becomes one asset per rock, each on its own base"""
    if it.get("split") and len(objs) > 1:
        objs.sort(key=lambda o: o.name)
        for k, o in enumerate(objs):
            for other in objs:
                other.hide_set(other is not o)
            bpy.context.view_layer.update()
            import_one(it, f"{name}_{k + 1}", [o], out, reg, MB, done)
    else:
        import_one(it, name, objs, out, reg, MB, done)


if __name__ == "__main__":
    main()
