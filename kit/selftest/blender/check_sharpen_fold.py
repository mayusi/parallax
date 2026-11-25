"""kit sharpen's fold step (kit/gen/sharpen_part.py) on a fixture: a ball of a head with two slabs of wings parting
behind it, one closed skin with its own UV atlas (the fold step's own new_skin), written as a GLB - which splits the
vertices along every UV seam. Each result is read back the way a build's a.import_mesh reads a GLB (merged at the
seams, welded at span * 1e-6).

THIN (--faces): thinned as a GLB is read, the two sides of each seam move apart (the fixture still shows the fault:
the launcher's second wolf came out with 38,201 open edges and its build's closed-surface gate refused it 11 minutes
later); the fold step welds the seams first.

DROP (--drop): the same shape with a thin rod along its top, between the wings (the launcher's heel wolf came out of
the generator with one, read off its picture's back edge): the box is cut away, the cut capped, the skin still closed;
a box that holds nothing of the part is refused.

Prints one line SHARPEN_FOLD {json}. Run by kit/test/python/test_sharpen_fold_blender.py."""
import contextlib
import io
import json
import math
import os
import shutil
import sys
import tempfile

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gen"))
import sharpen_part as S  # noqa: E402

BUDGET = 6000
ROD_BOX = "0.42,0.58,0.34,0.86,0.81,1.0"          # (fractions of the fixture's own box: across, from the nose, up)


def in_rod(c):
    """a face's centre in the rod's place: on the middle line, above the wings, behind the head"""
    return abs(c[0]) < 0.04 and c[2] > 0.16 and -0.20 < c[1] < 0.40


def as_a_build_reads(path):
    """a GLB's surface the way a.import_mesh takes it -> (triangles, open edges, pinched edges, has a UV map,
    faces in the rod's place)"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path, merge_vertices=True)
    obj = next(o for o in bpy.context.scene.objects if o.type == "MESH")
    obj.data.transform(obj.matrix_world)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(max(obj.dimensions), 1e-9) * 1e-6)
    out = (sum(len(f.verts) - 2 for f in bm.faces), sum(1 for e in bm.edges if e.is_boundary),
           sum(1 for e in bm.edges if len(e.link_faces) > 2), bool(obj.data.uv_layers),
           sum(1 for f in bm.faces if in_rod(f.calc_center_median())))
    bm.free()
    return out


def fixture(path, rod=False):
    """a ball of a head, nose to -Y, and two slabs of wings parting behind it; one skin, its own atlas. rod: a thin
    bar from the head's crown back over the gap between the wings"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.24, location=(0.0, -0.42, 0.0))
    parts = [bpy.context.active_object]
    for sign in (-1.0, 1.0):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(sign * 0.21, 0.18, 0.0),
                                        rotation=(0.0, 0.0, -sign * math.radians(18.0)))
        wing = bpy.context.active_object
        wing.scale = (0.11, 0.86, 0.26)
        parts.append(wing)
    if rod:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.02, 0.20))
        bar = bpy.context.active_object
        bar.scale = (0.05, 0.68, 0.05)
        parts.append(bar)
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    skin, facts = S.new_skin(bpy.context.active_object, 0.012)
    bpy.ops.object.select_all(action="DESELECT")
    skin.select_set(True)
    bpy.context.view_layer.objects.active = skin
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
    return facts


def thinned_as_read(src, dst, ratio):
    """the fault: the same collapse on the GLB as it is read (its seams split)"""
    obj = S.load_glb(src)
    dec = obj.modifiers.new("Budget", "DECIMATE")
    dec.decimate_type, dec.ratio = "COLLAPSE", ratio
    thin = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    obj.modifiers.remove(dec)
    obj.data = thin
    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB")


def fold(args):
    """the fold step, its closing line -> {status, summary, ...}"""
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        S.step_fold(args)
    line = next((ln for ln in reversed(said.getvalue().splitlines()) if ln.startswith("{")), "{}")
    return json.loads(line)


work = tempfile.mkdtemp(prefix="kit_sharpen_fold_")
try:
    src, out, bad, rod, cut, none = (os.path.join(work, n) for n in ("in.glb", "out.glb", "as_read.glb", "rod.glb",
                                                                     "cut.glb", "none.glb"))
    # ---- THIN
    fixture(src)
    tris_in, open_in, pinched_in, _, _ = as_a_build_reads(src)
    step = fold([src, out, "--faces", str(BUDGET)])
    tris_out, open_out, pinched_out, uv_out, _ = as_a_build_reads(out) if os.path.isfile(out) else (0, -1, -1, False, 0)
    thinned_as_read(src, bad, BUDGET / float(tris_in))
    _, open_bad, _, _, _ = as_a_build_reads(bad)
    # ---- DROP
    fixture(rod, rod=True)
    _, rod_open_in, _, _, rod_in = as_a_build_reads(rod)
    dropped = fold([rod, cut, "--drop", ROD_BOX])
    _, cut_open, cut_pinched, cut_uv, rod_out = as_a_build_reads(cut) if os.path.isfile(cut) else (0, -1, -1, False, -1)
    nothing = fold([rod, none, "--drop", "0.0,0.02,0.0,0.02,0.98,1.0"])     # (a corner of its box, in the air)
    print("SHARPEN_FOLD " + json.dumps({
        "budget": BUDGET, "tris_in": tris_in, "open_in": open_in, "pinched_in": pinched_in,
        "status": step.get("status"), "summary": step.get("summary", "")[:240],
        "tris_out": tris_out, "open_out": open_out, "pinched_out": pinched_out, "uv_out": uv_out,
        "open_thinned_as_read": open_bad,
        "rod_open_in": rod_open_in, "rod_faces_in": rod_in, "drop_status": dropped.get("status"),
        "drop_summary": dropped.get("summary", "")[:240], "rod_faces_out": rod_out, "drop_open_out": cut_open,
        "drop_pinched_out": cut_pinched, "drop_uv_out": cut_uv, "nothing_status": nothing.get("status"),
        "nothing_summary": nothing.get("summary", "")[:160], "nothing_written": os.path.isfile(none)}))
finally:
    shutil.rmtree(work, ignore_errors=True)
