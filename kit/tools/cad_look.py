"""cad_look.py — Blender side of `kit cad check --look`: draw CAD parts (cad_run's .npz meshes) from four sides.

    blender -b --factory-startup --python kit/tools/cad_look.py -- <out.png> <part.npz> [<part.npz> ...]
        [--zoom cx,cy,cz,size]

Coordinates are the kit's (mm: x right, y up, z back — the front is -Z). Four orthographic views in one 2 x 2 sheet:
the right side, the left side, from the front-left below, from the rear-right above. Workbench, studio light with
cavity and outlines — a look at the SHAPE (fins, steps, slivers, a fillet that did not take), not the materials.
--zoom: a box (centre and size, mm) instead of the whole part.
"""

import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector


def main(argv):
    out, paths, zoom = argv[0], [], None
    i = 1
    while i < len(argv):
        if argv[i] == "--zoom":
            zoom = [float(v) for v in argv[i + 1].split(",")]
            i += 2
            continue
        paths.append(argv[i])
        i += 1
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    pts = []
    for k, p in enumerate(paths):
        d = np.load(p)
        v, t = d["verts"], d["tris"]
        bl = np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1)  # kit (x, y, z) -> Blender (x, -z, y)
        me = bpy.data.meshes.new(f"part{k}")
        me.from_pydata(bl.tolist(), [], t.tolist())
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)  # (outward, whatever the tessellator's winding)
        bm.to_mesh(me)
        bm.free()
        me.update()
        ob = bpy.data.objects.new(os.path.splitext(os.path.basename(p))[0], me)
        sc.collection.objects.link(ob)
        pts.append(bl)
    allp = np.concatenate(pts)
    if zoom:
        cx, cy, cz, size = zoom
        mid = Vector((cx, -cz, cy))
    else:
        lo, hi = allp.min(0), allp.max(0)
        mid, size = Vector(((lo + hi) / 2).tolist()), float((hi - lo).max())
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light, sh.color_type, sh.show_cavity, sh.show_object_outline = "STUDIO", "SINGLE", True, True
    sh.single_color = (0.72, 0.72, 0.74)
    sh.cavity_type, sh.curvature_ridge_factor, sh.curvature_valley_factor = "BOTH", 1.0, 1.0
    sc.display.render_aa = "8"
    sc.render.resolution_x = sc.render.resolution_y = 640
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("w")
    cd = bpy.data.cameras.new("cam")
    cd.type, cd.ortho_scale, cd.clip_end = "ORTHO", size * 1.15, size * 50
    cam = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    views = [("right", (1, 0, 0)), ("left", (-1, 0, 0)), ("front-left-below", (-0.6, 0.75, -0.45)),
             ("rear-right-above", (0.6, -0.75, 0.45))]
    tiles = []
    base = os.path.splitext(out)[0]
    for name, dvec in views:
        dvec = Vector(dvec).normalized()
        cam.location = mid + dvec * size * 4
        cam.rotation_euler = (-dvec).to_track_quat("-Z", "Y").to_euler()
        f = f"{base}_{name}.png"
        sc.render.filepath = f
        bpy.ops.render.render(write_still=True)
        tiles.append(f)
    print("CAD_LOOK " + "|".join(tiles))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
