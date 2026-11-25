"""retopo_part.py — a GENERATED part's game mesh: a clean QUAD surface at a face budget, its colour baked across, and
the generator's dense surface kept beside it as the part's HIGH (the bake source of the high-and-low route).

    blender -b --factory-startup --python-exit-code 2 -P kit/gen/retopo_part.py -- <in.glb> <out.glb>
        [--quads 3000] [--remesher instant|quadriflow] [--voxel 0.0042] [--size 2048]

<in.glb>: a generator's part (kit gen / TRELLIS.2: a dense triangle crust with its own colour map). Writes:
  <out.glb>        the LOW: quads only (Instant Meshes' pure-quad extraction, or Blender's QuadriFlow), its own UV
                   atlas, the generator's colour baked onto it
  <out>_high.glb   the HIGH: one watertight skin of the same shape (sharpen's voxel skin: the generator's crust folds
                   through itself and pinches) with the colour baked across - a.import_mesh(low, high=...) bakes its
                   relief into the low's normal map
  <out>.json       what was made (below); the same JSON is the last line printed
Both files keep <in.glb>'s own frame (nothing is moved): the build places the high exactly where it places the low.

Why quads (LIMITATIONS_FIXES_V4 3D-X, 13.2; the Roblox accessory specs: "use quads whenever possible"): a decimated
generator mesh is triangle soup - slivers, smooth shading smeared across them, no edge loops round the form (the
Hero outfit: 100% triangles, 970-2,800 slivers a piece). A field-aligned quad remesh lays loops along the form.

The remesher: Instant Meshes (BSD-3, wjakob/instant-meshes, built from source on this machine: VETLOG) when its
binary is found (KIT_INSTANT_MESHES, else ~/.cache/roblox-kit/src/instant-meshes/build/Release/Instant Meshes.exe),
else Blender's own QuadriFlow - said in the facts, never silently.

Facts: remesher, quads / polygons (the quad share), triangles (as the game counts them: a quad is two), open edges,
pinched edges (3+ faces), the low's distance from the high (p95 and worst, as a share of the part's longest side, both
ways: the low's points to the high, the high's points to the low), seconds."""

import json
import os
import subprocess
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sharpen_part as S  # noqa: E402

INSTANT_BUILD = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "src", "instant-meshes", "build")
# where a source build puts the binary: Windows (Visual Studio: Release/), a single-config build (Linux), macOS's bundle
INSTANT_DEFAULT = os.path.join(INSTANT_BUILD, "Release", "Instant Meshes.exe")
INSTANT_CANDIDATES = (INSTANT_DEFAULT, os.path.join(INSTANT_BUILD, "Instant Meshes"),
                      os.path.join(INSTANT_BUILD, "Instant Meshes.app", "Contents", "MacOS", "Instant Meshes"))
SAMPLES = 20000   # points each way for the distance between the low and the high
HIGH_TRIS = 200000   # the high (the bake source) thinned to this: a 4096 map has 16M texels, 200k faces is ~80 a face


def instant_meshes():
    """the Instant Meshes binary, or None: KIT_INSTANT_MESHES, else the source build (any OS's layout), else a binary
    named instant-meshes / Instant Meshes on PATH"""
    forced = os.environ.get("KIT_INSTANT_MESHES")
    if forced:
        return forced if os.path.isfile(forced) else None
    for p in INSTANT_CANDIDATES:
        if os.path.isfile(p):
            return p
    import shutil  # noqa: PLC0415 - (this script runs inside Blender's Python; only needed here)

    return shutil.which("instant-meshes") or shutil.which("Instant Meshes")


def write_obj(obj, path):
    me = obj.data
    with open(path, "w", encoding="ascii") as f:
        for v in me.vertices:
            f.write("v %.7f %.7f %.7f\n" % tuple(v.co))
        for p in me.polygons:
            f.write("f " + " ".join(str(i + 1) for i in p.vertices) + "\n")


def read_obj(path):
    verts, faces = [], []
    with open(path, encoding="ascii", errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                verts.append(tuple(float(x) for x in line.split()[1:4]))
            elif line.startswith("f "):
                faces.append(tuple(int(x.split("/")[0]) - 1 for x in line.split()[1:]))
    return verts, faces


def remesh_instant(skin, quads, work, exe):
    """the skin through Instant Meshes -> the new object. Its pure-quad mode extracts a quad-dominant mesh and
    subdivides it once (each face into four): it is asked for a quarter of the budget"""
    src, dst = os.path.join(work, "skin.obj"), os.path.join(work, "quads.obj")
    write_obj(skin, src)
    cmd = [exe, src, "-o", dst, "-f", str(max(16, int(quads) // 4)), "-d", "-r", "4", "-p", "4"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if res.returncode != 0 or not os.path.isfile(dst):
        raise RuntimeError(f"Instant Meshes failed ({res.returncode}): {(res.stderr or res.stdout)[-400:]}")
    verts, faces = read_obj(dst)
    me = bpy.data.meshes.new("low")
    me.from_pydata(verts, [], faces)
    me.validate()
    low = bpy.data.objects.new("low", me)
    bpy.context.scene.collection.objects.link(low)
    return low


def remesh_quadriflow(skin, quads):
    """the skin through Blender's QuadriFlow (pure quads at about the budget) -> the new object"""
    low = skin.copy()
    low.data = skin.data.copy()
    low.name = "low"
    bpy.context.scene.collection.objects.link(low)
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.quadriflow_remesh(target_faces=int(quads), mode="FACES", seed=0, use_mesh_symmetry=False,
                                     use_preserve_sharp=False, use_preserve_boundary=False, smooth_normals=False)
    return low


def tidy(low):
    """small holes the extraction left are closed (a boundary loop of up to 8 edges), loose bits go, faces outward
    -> (open edges before, after)"""
    bm = bmesh.new()
    bm.from_mesh(low.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    before = sum(1 for e in bm.edges if e.is_boundary)
    if before:
        bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=8)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bm.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    after = sum(1 for e in bm.edges if e.is_boundary)
    bm.to_mesh(low.data)
    bm.free()
    for p in low.data.polygons:
        p.use_smooth = True
    return before, after


def topology(obj):
    me = obj.data
    sides = np.array([len(p.vertices) for p in me.polygons])
    bm = bmesh.new()
    bm.from_mesh(me)
    open_ = sum(1 for e in bm.edges if e.is_boundary)
    pinched = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bm.free()
    return {"polygons": int(len(sides)), "quads": int((sides == 4).sum()),
            "quad_share": round(float((sides == 4).mean()) if len(sides) else 0.0, 4),
            "triangles": int((sides - 2).sum()), "open_edges": int(open_), "pinched_edges": int(pinched)}


def _samples(obj, n, rng):
    """n points spread over obj's surface by area"""
    me = obj.data
    me.calc_loop_triangles()
    co = S.coords(me)
    tri = np.zeros(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tri)
    t = co[tri.reshape(-1, 3)]
    area = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
    pick = rng.choice(len(t), size=n, p=area / area.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    w = np.stack([1 - s, s * (1 - r2), s * r2], axis=1)
    return (t[pick] * w[:, :, None]).sum(axis=1)


def distance(a, b, span):
    """how far each surface lies from the other: points of a to b and of b to a -> {p95, worst} as a share of span"""
    rng = np.random.default_rng(0)
    out = {}
    for key, (x, y) in {"low_to_high": (a, b), "high_to_low": (b, a)}.items():
        tree = BVHTree.FromObject(y, bpy.context.evaluated_depsgraph_get())
        d = []
        for q in _samples(x, SAMPLES // 2, rng):
            hit = tree.find_nearest(Vector(q))[0]
            d.append((Vector(q) - hit).length if hit is not None else span)
        d = np.array(d)
        out[key] = {"p95": round(float(np.percentile(d, 95)) / span, 5), "worst": round(float(d.max()) / span, 5)}
    return out


def with_colour(obj, path, name):
    """obj's only material: an image texture (path) as its base colour"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    bsdf.inputs["Metallic"].default_value = 0.0
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def unwrap(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.002)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.002)
    bpy.ops.object.mode_set(mode="OBJECT")


def export(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)


def main(argv):
    t0 = time.time()
    if len(argv) < 2:
        return S.emit("fail", "retopo_part: <in.glb> <out.glb> [--quads N] [--remesher instant|quadriflow]",
                      "give the generated part and where its game mesh goes")
    src, dst = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    quads = S.opt(argv, "--quads", 3000)
    want = S.opt(argv, "--remesher", "instant")
    size = S.opt(argv, "--size", 2048)
    base = dst[:-4] if dst.lower().endswith(".glb") else dst
    work = base + "_work"
    os.makedirs(work, exist_ok=True)
    obj = S.load_glb(src)
    img = None
    for mat in list(obj.data.materials):
        if mat and mat.use_nodes:
            for link in mat.node_tree.links:
                if link.to_socket.name == "Base Color" and link.from_node.type == "TEX_IMAGE" and link.from_node.image:
                    img = link.from_node.image
    if img is None or not obj.data.uv_layers:
        return S.emit("fail", f"retopo: {os.path.basename(src)} has no colour map of its own (or no UVs)",
                      "retopologise a generator's GLB (kit gen writes one with its own map)")
    co = S.coords(obj.data)
    span = float(np.max(co.max(axis=0) - co.min(axis=0)))
    voxel = span * S.opt(argv, "--voxel", 0.0042)
    skin, skin_facts = S.new_skin(obj, voxel)
    high_tris = S.opt(argv, "--high-tris", HIGH_TRIS)
    if skin_facts["triangles"] > high_tris:   # (the bake source: finer than any map it bakes into, never 500k+)
        dec = skin.modifiers.new("thin", "DECIMATE")
        dec.ratio = high_tris / skin_facts["triangles"]
        bpy.context.view_layer.objects.active = skin
        bpy.ops.object.modifier_apply(modifier=dec.name)
        skin_facts["voxel_triangles"], skin_facts["triangles"] = skin_facts["triangles"], len(skin.data.polygons)
    exe = instant_meshes()
    said = None
    if want == "instant" and exe:
        try:
            low = remesh_instant(skin, quads, work, exe)
            remesher = "instant_meshes"
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            said = f"Instant Meshes failed ({e}); QuadriFlow instead"
            low, remesher = remesh_quadriflow(skin, quads), "quadriflow"
    else:
        if want == "instant":
            said = "no Instant Meshes binary (KIT_INSTANT_MESHES): QuadriFlow instead"
        low, remesher = remesh_quadriflow(skin, quads), "quadriflow"
    holes_before, holes_after = tidy(low)
    topo = topology(low)
    unwrap(low)
    gap = distance(low, skin, span)
    # the colour across: the generator's own surface onto the low's atlas, and onto the high's (its skin's) atlas
    low_px = S.bake_across(obj, low, img, voxel, size)
    S.save_image(S.M.linear_to_srgb(low_px[..., :3]), os.path.join(work, "low_colour.png"))
    high_px = S.bake_across(obj, skin, img, voxel, size)
    S.save_image(S.M.linear_to_srgb(high_px[..., :3]), os.path.join(work, "high_colour.png"))
    bpy.data.objects.remove(obj, do_unlink=True)
    with_colour(low, os.path.join(work, "low_colour.png"), "retopo_low")
    with_colour(skin, os.path.join(work, "high_colour.png"), "retopo_high")
    export(low, dst)
    export(skin, base + "_high.glb")
    facts = {"source": src.replace("\\", "/"), "low": dst.replace("\\", "/"),
             "high": (base + "_high.glb").replace("\\", "/"), "remesher": remesher, "asked_quads": int(quads),
             **topo, "holes_closed": int(holes_before - holes_after), "high_triangles": skin_facts["triangles"],
             "distance": gap, "span": round(span, 6), "seconds": round(time.time() - t0, 1)}
    if said:
        facts["said"] = said
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=1)
    S.emit("pass", f"retopo: {topo['quads']:,} of {topo['polygons']:,} faces quads ({remesher}), "
                   f"{topo['triangles']:,} triangles, {topo['open_edges']} open edges; the low within "
                   f"{gap['low_to_high']['p95']:.2%} of the part's size of the high (p95)"
                   + (f"; {said}" if said else ""),
           "a.import_mesh(<low>, high=<high>) in an Asset(low=...) build", **facts)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
