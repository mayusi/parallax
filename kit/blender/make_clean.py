"""make_clean.py — a generated mesh made sound before `kit make` paints and builds it:

    blender -b --factory-startup -P kit/blender/make_clean.py -- <in.glb> <out.glb> [--denoise] [--faces 300000]
        [--inner-wall]   (faces no ray from outside reaches dropped, the rims capped: a generator's thick hollow shell)
        [--round]        (its ROUND slices made truly round — rbx_lathe.true_round: a barrel, an extinguisher's body)
        [--staves N]     (with --round, a body >= 60% round: N stave grooves pressed in — a wooden barrel, a cask)

Generators hand back meshes with split seams, loose specks, open holes and faces wound the wrong way (the kit's build
gates name them: manifold, inside_out — and a face wound inward renders black). This joins the pieces, welds what
coincides, drops specks under 0.5% of the object's size, fills the small holes, and turns every face outward. The
shape is not resampled (no remesh): what the generator made stays, only made consistent. --denoise (a hard-surface
object): the surface's noise filtered out with its edges kept, its big flat faces made dead flat (rbx_denoise: guided
normal filtering, planarize). Prints one JSON
line with what it fixed and how crisp the surface is (flat faces, real edges: rbx_denoise.crispness).
"""

import json
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rbx_denoise  # noqa: E402
import rbx_lathe  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = os.path.abspath(argv[0]), os.path.abspath(argv[1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
size = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))

bm = bmesh.new()
for o in objs:
    me = o.data.copy()
    me.transform(o.matrix_world)
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
facts = {"faces_in": len(bm.faces)}
n_verts = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=size * 1e-5)  # (returns None: the count is the vertices it merged)
facts["welded"] = n_verts - len(bm.verts)
# specks: connected islands smaller than 0.5% of the object
bm.verts.ensure_lookup_table()
seen, islands = set(), []
for f in bm.faces:
    if f.index in seen:
        continue
    stack, isl = [f], []
    seen.add(f.index)
    while stack:
        g = stack.pop()
        isl.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen:
                    seen.add(h.index)
                    stack.append(h)
    islands.append(isl)
specks = []
for isl in islands:
    vs = {v for f in isl for v in f.verts}
    lo = [min(v.co[i] for v in vs) for i in range(3)]
    hi = [max(v.co[i] for v in vs) for i in range(3)]
    if max(hi[i] - lo[i] for i in range(3)) < size * 0.005:
        specks += isl
bmesh.ops.delete(bm, geom=specks, context="FACES")
facts["specks_dropped"] = len(specks)


def hidden_faces(bm, size, n_random=40, seed=0):
    """faces no ray from outside reaches (26 axis / diagonal directions + n_random random ones; a face counts as seen
    when a ray from outside the object hits IT first) — Pixal3D hands back THICK hollow shells: the made barrel and
    extinguisher were 52% inner wall, which the AO bake reads as buried (the colour x 0.25: dark maroon, black
    blotches; owner 0 / 2 out of 10). -> [faces]"""
    from mathutils.bvhtree import BVHTree  # noqa: PLC0415

    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    rng = np.random.default_rng(seed)
    dirs = [Vector((x, y, z)).normalized() for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1) if x or y or z]
    dirs += [Vector(v / np.linalg.norm(v)) for v in rng.normal(size=(n_random, 3))]
    reach = size * 4.0
    out, seen_from = [], {}
    for f in bm.faces:
        c = f.calc_center_median()
        for d in dirs:
            hit = tree.ray_cast(c + d * (size * 2.0), -d, reach)
            if hit[2] == f.index:
                seen_from[f.index] = d   # (the outside it faces: its normal must point this way)
                break
        else:
            out.append(f)
    return out, seen_from


hidden, seen_from = (hidden_faces(bm, size) if len(bm.faces) and "--inner-wall" in argv   # (opt-in: ~85 s on 280k
                     else ([], {}))   # faces — kit make runs it on the tournament's WINNER only, never every candidate)
# (only when it is a real inner wall — a sizable share; a handful of unseen faces in a deep crease stay)
if len(hidden) > 0.05 * max(len(bm.faces), 1):
    # (orientation: the faces keep the one they had — the input is the candidate's own clean, its normals made
    #  consistent while the shell was still CLOSED, which is reliable; reorienting the open shell by the ray that saw
    #  each face turned faces seen through an opening from inside inward: the made barrel's black rectangle)
    bmesh.ops.delete(bm, geom=hidden, context="FACES")
    facts["inner_wall_dropped"] = len(hidden)
open_before = sum(1 for e in bm.edges if e.is_boundary)
# (small holes only: capping EVERY loop after an inner wall was dropped fanned huge flat triangles across its rims —
#  black and white panels on the made barrel, inward facets on the extinguisher; the rims stay open, said by manifold)
bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=12)
facts["open_edges"] = [open_before, sum(1 for e in bm.edges if e.is_boundary)]
if not facts.get("inner_wall_dropped"):   # (an open shell keeps the orientation its sight gave: recalc guesses wrong)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
if "--round" in argv and len(bm.verts):
    # a round object's slices trued onto their fitted circles (a generator's barrel is ±5-15% lumpy per slice, its
    # texture smearing a hoop into blotches: owner 2026-10-16 "still bad"); appendages and square slices untouched
    bm.verts.ensure_lookup_table()
    V0 = np.array([v.co[:] for v in bm.verts], np.float64)
    V1, facts["round"] = rbx_lathe.true_round(V0, up=2)
    if "--staves" in argv and facts["round"].get("round_share", 0) >= 0.6:
        # a round WOODEN body (kit make passes it for wood words): its staves pressed in
        V1, facts["round"]["staves"] = rbx_lathe.staves(V1, facts["round"].get("profile"), up=2,
                                                       n=int(argv[argv.index("--staves") + 1]))
    for v, p in zip(bm.verts, V1):
        v.co = p
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])   # (the filled holes: fans)
# at most --faces (a collapse decimation, welded first: safe): Hunyuan gave a treasure chest 1.6M faces — its
# denoise, paint and build all ran out of a prop's 10 minutes
cap = int(argv[argv.index("--faces") + 1]) if "--faces" in argv else 300000
if len(bm.faces) > cap:
    tmp = bpy.data.meshes.new("cap")
    bm.to_mesh(tmp)
    bm.free()
    ob_cap = bpy.data.objects.new("cap", tmp)
    bpy.context.scene.collection.objects.link(ob_cap)
    dec = ob_cap.modifiers.new("cap", "DECIMATE")
    dec.ratio = cap / len(tmp.polygons)
    dec.use_collapse_triangulate = True
    ev = ob_cap.evaluated_get(bpy.context.evaluated_depsgraph_get())
    bm = bmesh.new()
    bm.from_mesh(ev.to_mesh())
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob_cap, do_unlink=True)
    facts["decimated_to"] = len(bm.faces)
bm.verts.ensure_lookup_table()
bm.verts.index_update()
V = np.array([v.co[:] for v in bm.verts], np.float64)
F = np.array([[v.index for v in f.verts] for f in bm.faces], np.int64)
facts["crispness"] = rbx_denoise.crispness(V, F)
if "--denoise" in argv:
    # only a NOISY surface is filtered (over 1 deg between neighbours: Pixal3D's Glock 5.3): on an already smooth
    # one (Hunyuan's, 0.5) the filter only terraced its gentle curves
    if facts["crispness"]["noise_deg"] > 1.0:
        V = rbx_denoise.denoise(V, F)
    V, flat = rbx_denoise.planarize(V, F)   # (its flat faces dead flat: a generated slide flank is wavy)
    for v, p in zip(bm.verts, V):
        v.co = p
    facts["crispness_denoised"] = rbx_denoise.crispness(V, F)
    facts["planarized"] = {"regions": len(flat), "area_share": round(sum(x["area_share"] for x in flat), 4),
                           "eased": True, "denoised": facts["crispness"]["noise_deg"] > 1.0}
facts["faces_out"] = len(bm.faces)

me = bpy.data.meshes.new("clean")
bm.to_mesh(me)
bm.free()
# smooth-shaded: a flat-shaded mesh leaves the glTF exporter splitting every vertex per face — a triangle soup that
# whatever reads it next must weld again (the paint prep decimated the soup and shredded the Glock)
me.shade_smooth()
for m in (objs[0].data.materials if objs else []):   # (the generator's own textures ride along: a public asset keeps them)
    me.materials.append(m)
for o in objs:
    bpy.data.objects.remove(o, do_unlink=True)
ob = bpy.data.objects.new("clean", me)
bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True)
print(json.dumps({"schema": 1, "status": "pass", "summary": f"make_clean: {os.path.basename(src)} -> "
                  f"{os.path.basename(dst)}", "next_action": "none", **facts}))
