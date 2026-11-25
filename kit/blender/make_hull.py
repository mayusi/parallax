"""make_hull.py — a REAL object's shape built from its traced photos (`kit make`'s traced_hull candidate):

    blender -b --factory-startup -P kit/blender/make_hull.py -- <side.trace.json> <front.trace.json> <out.glb>
        [--relief <a side's trace.json> <its relief.npz>] ... [--mirror]   (the parts layer: press_reliefs)

The side outline (with its holes: a trigger guard's opening) extruded across the object, INTERSECTED with the front
outline extruded along it: the visual hull of the two photos — the exact photographed silhouette, flat flanks, crisp
edges — for slab-sided objects (a pistol, a knife, a tool, a cabinet) the shape a generator melts. No CAD loop and no
hand: seconds. Written like a generator's output (glTF: y up, the front toward -Z, its length 1) so the tournament,
the clean-up, the paint and the build take it as one more candidate. Prints one JSON line.
"""

import json
import os
import sys

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
side_path, front_path, out = (os.path.abspath(a) for a in argv[:3])
side, front = (json.load(open(p, encoding="utf-8")) for p in (side_path, front_path))
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# the box in the side outline's units (its length 1): height from its own frame, width from the front's proportions
hr_side = float(side.get("height_ratio", 0.3))
hr_front = float(front.get("height_ratio", 1.0))
height = hr_side
width = height / max(hr_front, 1e-6)


def prism(rings, to_xyz, along, depth, name):
    """rings (the outline, then holes) of 2D points -> a prism of them, `depth` long along the unit axis `along`"""
    bm = bmesh.new()
    for ring in rings:
        vs = [bm.verts.new(to_xyz(p) - along * (depth / 2)) for p in ring]
        for k in range(len(vs)):
            if (vs[k - 1].co - vs[k].co).length > 1e-9:
                bm.edges.new((vs[k - 1], vs[k]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    faces = [f for f in bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=bm.edges[:])["geom"]
             if isinstance(f, bmesh.types.BMFace)]
    ex = bmesh.ops.extrude_face_region(bm, geom=faces)
    bmesh.ops.translate(bm, vec=along * depth, verts=[e for e in ex["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    return ob


def rings_of(t):
    return [t["outline"]] + [h for h in t.get("holes", []) if len(h) >= 3]


# Blender space: x right, y = the FRONT (glTF -Z after export), z up. A side outline's design units: u 0 back .. 1
# front whichever way its picture faced, h up — in lengths
side_ob = prism(rings_of(side), lambda p: Vector((0.0, p[0] - 0.5, p[1])), Vector((1, 0, 0)), width * 1.6, "side")
# a front outline: u across its picture (the model's right on the picture's LEFT), h up — in widths (its box is the
# object's width by its height)
front_ob = prism(rings_of(front), lambda p: Vector(((0.5 - p[0]) * width, 0.0, p[1] * width)), Vector((0, 1, 0)),
                 1.6, "front")
mod = side_ob.modifiers.new("hull", "BOOLEAN")
mod.operation, mod.object, mod.solver = "INTERSECT", front_ob, "EXACT"
dg = bpy.context.evaluated_depsgraph_get()
me = bpy.data.meshes.new_from_object(side_ob.evaluated_get(dg))
side_ob.modifiers.clear()
for o in (side_ob, front_ob):
    bpy.data.objects.remove(o, do_unlink=True)
hull = bpy.data.objects.new("traced_hull", me)
sc.collection.objects.link(hull)


def box_blur(a, r):
    """a separable box blur of radius r (numpy only: Blender has no scipy)"""
    import numpy as np

    for axis in (0, 1):
        c = np.cumsum(np.pad(a, [(r + 1, r) if k == axis else (0, 0) for k in range(2)], mode="edge"), axis=axis)
        a = (np.take(c, range(2 * r + 1, c.shape[axis]), axis=axis) - np.take(c, range(0, c.shape[axis] - 2 * r - 1),
                                                                              axis=axis)) / (2 * r + 1)
    return a


def press_reliefs(obj, reliefs, amount, mirror=False):
    """THE PARTS LAYER from the photos: each traced side's relief (`kit vision relief`: MoGe-2 + Depth Anything 3 —
    its levers, panels, serrations, seams as height) pressed into that flank, registered through the trace's frame:
    its high-pass (broad form removed: the hull has it) moves every vertex the side faces squarely outward by up to
    `amount` (raised = out). mirror: each relief pressed into the opposite flank too (a 790 px photo's relief is
    blobby: the sharpest side's, mirrored, is better on a near-symmetric object). -> vertices moved"""
    import numpy as np

    me_ = obj.data
    n = len(me_.vertices)
    co = np.empty(n * 3)
    me_.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    me_.calc_normals_split() if hasattr(me_, "calc_normals_split") else None
    nrm = np.empty(n * 3)
    me_.vertices.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    moved = np.zeros(n)
    for tpath, npz in reliefs:
        t = json.load(open(tpath, encoding="utf-8"))
        fr = t["frame"]
        x0, y1, L = float(fr["x0"]), float(fr["y1"]), float(fr["length_px"])
        front_ = t.get("front", "right")
        cam = np.array([1.0 if front_ == "right" else -1.0, 0.0, 0.0])   # (front on the picture's right: its RIGHT)
        z = np.load(npz)
        h = z["height"].astype(np.float64)
        m = z["mask"].astype(np.float64)
        pic = bpy.data.images.load(t["source"] if os.path.isabs(t["source"]) else os.path.join(REPO, t["source"]))
        k = h.shape[1] / max(pic.size[0], 1)
        bpy.data.images.remove(pic)
        r = max(2, int(round(0.03 * L * k)))
        hp = (h - box_blur(h * m, r) / np.maximum(box_blur(m, r), 1e-6)) * m
        scale = max(float(np.percentile(np.abs(hp[m > 0.5]), 98)) if (m > 0.5).any() else 0.0, 1e-9)
        sig = np.tanh(hp / scale)
        u = co[:, 1] + 0.5
        X = (x0 + (u if front_ == "right" else 1 - u) * L) * k
        Y = (y1 - co[:, 2] * L) * k
        xi = np.clip(np.round(X).astype(int), 0, sig.shape[1] - 1)
        yi = np.clip(np.round(Y).astype(int), 0, sig.shape[0] - 1)
        s = sig[yi, xi] * (m[yi, xi] > 0.5)
        for c in ([cam, -cam] if mirror else [cam]):
            facing = nrm @ c
            w = np.clip((facing - 0.4) / 0.4, 0, 1) * ((co @ c) > 0)
            co = co + np.outer(amount * s * w, c)
            moved += (np.abs(s * w) > 0.05)
    me_.vertices.foreach_set("co", co.ravel())
    me_.update()
    return int((moved > 0).sum())


REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
reliefs = [(argv[i + 1], argv[i + 2]) for i in range(3, len(argv) - 2) if argv[i] == "--relief"]
mirror = "--mirror" in argv
pressed = 0
if reliefs:
    # a uniform surface to press the detail into (the hull's faces are long strips): voxels 1/400 of its length
    rm_ = hull.modifiers.new("remesh", "REMESH")
    rm_.mode, rm_.voxel_size = "VOXEL", 0.0025
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(hull.evaluated_get(dg))
    hull.modifiers.clear()
    hull.data = me2
    me = me2
    pressed = press_reliefs(hull, reliefs, amount=0.006, mirror=mirror)   # (0.6 % of its length: a Glock's 1.2 mm)
# its own UV layout (the painter re-unwraps; a.import_mesh needs one material)
mat = bpy.data.materials.new("hull")
mat.use_nodes = True
me.materials.append(mat)
bpy.context.view_layer.objects.active = hull
hull.select_set(True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True)
xs = [v.co for v in me.vertices]
size = [max(c[i] for c in xs) - min(c[i] for c in xs) for i in range(3)] if xs else [0, 0, 0]
print(json.dumps({"schema": 1, "status": "pass" if len(me.polygons) else "fail",
                  "summary": f"make_hull: {os.path.basename(out)} — {len(me.polygons)} faces, "
                             f"{size[0]:.3f} x {size[1]:.3f} x {size[2]:.3f} (x width, y length, z height)",
                  "next_action": "none", "faces": len(me.polygons), "size": [round(v, 4) for v in size],
                  "relief_vertices": pressed}))
