"""kit sharpen keeps an OPENING open (kit/gen/sharpen_part.py keep_open; his V3 list, 3D stage B.1: a.open_way keep-outs
before the remesh). The new skin is a voxel remesh, and a remesh closes what is narrower than about two voxels: a
bore, a strap's slot, a sight line. The fixture is a block with a thin bore through its length (1.2 voxels across):
as the remesh leaves it the bore is shut; carved with --keep-open it is open again, every line of sight down it
clear, and the skin still one closed surface with its atlas.
Prints one line SHARPEN_KEEP_OPEN {json}. Run by kit/test/python/test_sharpen_keep_open_blender.py."""
import json
import os
import sys

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gen"))
import sharpen_part as S  # noqa: E402

VOXEL = 0.01
BORE = 0.012                       # across: 1.2 voxels - a remesh shuts it
WAY = ((0.0, 0.5, 0.5), (1.0, 0.5, 0.5), BORE / 1.0)   # along x, through the middle (fractions of the box)


def block():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    b = bpy.context.active_object
    b.scale = (1.0, 0.3, 0.3)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=BORE / 2, depth=1.2, rotation=(0.0, 1.5707963, 0.0))
    cut = bpy.context.active_object
    mod = b.modifiers.new("Bore", "BOOLEAN")
    mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", cut
    bpy.context.view_layer.objects.active = b
    bpy.ops.object.modifier_apply(modifier="Bore")
    bpy.data.objects.remove(cut, do_unlink=True)
    return b


def world_way(obj):
    import numpy as np  # noqa: PLC0415

    co = np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
    lo, hi = co.min(axis=0), co.max(axis=0)
    span = hi - lo
    p0, p1, w = WAY
    return [(lo + span * np.asarray(p0), lo + span * np.asarray(p1), w * float(span.max()))]


def closed(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    out = {"open": sum(1 for e in bm.edges if e.is_boundary), "pinched": sum(1 for e in bm.edges if len(e.link_faces) > 2)}
    bm.free()
    return out


src = block()
as_made = S.ways_clear(src, world_way(src))[0]
skin, _facts = S.new_skin(src, VOXEL)
shut = S.ways_clear(skin, world_way(skin))[0]
_world, after = S.keep_open(skin, [WAY], unwrap=True)
print("SHARPEN_KEEP_OPEN " + json.dumps({"lines": 17, "as_made": as_made, "remeshed": shut, "kept": after[0],
                                         **closed(skin), "uv": bool(skin.data.uv_layers)}))
