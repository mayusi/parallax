"""kit sharpen's new skin is SOLID (kit/gen/sharpen_part.py, new_skin). A generator's mesh is a thin crust - an outer
wall and an inner one a voxel behind it - and where the crust has a gap the two are one surface: the remesh kept
both, so half the skin's triangles and half its colour map went to an inside nobody sees (the launcher's nose wolf:
446,224 triangles, 98.5% of them a double wall). The fixture is such a crust: a ball's shell 0.03 thick with a hole
at its top. As the remesh leaves it (solid=False) it is hollow - the fixture still shows the fault; the new skin
sheds the inner wall and closes the gap. The hollow is measured here on its own: from a sample of faces a ray goes
inward, and a thin wall meets its far side at once.
And the cap itself (cap_loops) on a rim that TOUCHES ITSELF: a sheet with two holes that share one corner. One fan
through that corner twice pinches an edge (the real nose wolf: 12 pinched edges, which a build's closed-surface gate
refuses); each ring gets its own fan.
Prints one line SHARPEN_SKIN {json}. Run by kit/test/python/test_sharpen_skin_blender.py."""
import json
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gen"))
import sharpen_part as S  # noqa: E402

VOXEL = 0.01


def crust():
    """a ball's shell, 0.03 thick, with a hole round its top: outer wall, inner wall and the hole's rim, one surface"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=0.4)
    ball = bpy.context.active_object
    bm = bmesh.new()
    bm.from_mesh(ball.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z > 0.393], context="FACES")
    bm.to_mesh(ball.data)
    bm.free()
    shell = ball.modifiers.new("Crust", "SOLIDIFY")
    shell.thickness, shell.offset, shell.use_rim = 0.03, -1.0, True
    bpy.ops.object.modifier_apply(modifier="Crust")
    return ball


def measured(obj):
    """-> (triangles, open edges, the share of faces whose inward ray meets the far side within 0.06, UV map)"""
    me = obj.data
    tree = BVHTree.FromPolygons([v.co for v in me.vertices], [p.vertices[:] for p in me.polygons])
    rng = np.random.default_rng(2)
    pick = rng.choice(len(me.polygons), size=min(3000, len(me.polygons)), replace=False)
    thin = met = 0
    for i in pick:
        p = me.polygons[int(i)]
        hit = tree.ray_cast(p.center - p.normal * 1e-4, -p.normal)
        if hit[0] is not None:
            met += 1
            thin += hit[3] < 0.06
    bm = bmesh.new()
    bm.from_mesh(me)
    opened = sum(1 for e in bm.edges if e.is_boundary)
    bm.free()
    return sum(len(p.vertices) - 2 for p in me.polygons), opened, round(thin / max(met, 1), 4), bool(me.uv_layers)


def figure_eight():
    """a 4 x 4 sheet of quads with two holes that share one corner -> (rings closed, edges left open, pinched edges,
    hole edges still open)"""
    bm = bmesh.new()
    grid = [[bm.verts.new((x, y, 0.0)) for x in range(5)] for y in range(5)]
    quads = {(x, y): bm.faces.new((grid[y][x], grid[y][x + 1], grid[y + 1][x + 1], grid[y + 1][x]))
             for x in range(4) for y in range(4)}
    border = {e for e in bm.edges if e.is_boundary}
    bmesh.ops.delete(bm, geom=[quads[(1, 1)], quads[(2, 2)]], context="FACES_ONLY")
    rim = {e for e in bm.edges if e.is_boundary and e not in border}
    closed, left = S.cap_loops(bm, rim)
    out = (closed, left, sum(1 for e in bm.edges if len(e.link_faces) > 2),
           sum(1 for e in bm.edges if e.is_boundary and e not in border))
    bm.free()
    return out


eight = figure_eight()
ball = crust()
left, facts_left = S.new_skin(ball, VOXEL, solid=False)
tris_hollow, open_hollow, thin_hollow, _ = measured(left)
skin, facts = S.new_skin(ball, VOXEL)
tris, opened, thin, uv = measured(skin)
print("SHARPEN_SKIN " + json.dumps({
    "figure_eight": {"closed": eight[0], "left": eight[1], "pinched": eight[2], "open": eight[3]},
    "as_remeshed": {"triangles": tris_hollow, "open": open_hollow, "thin": thin_hollow, "said_hollow": facts_left["hollow"],
                    "removed": facts_left["inner_faces_removed"]},
    "solid": {"triangles": tris, "open": opened, "thin": thin, "uv": uv, "said_hollow": facts["hollow"],
              "removed": facts["inner_faces_removed"], "said_after": facts["hollow_after"],
              "pinched": facts["pinched_edges"], "wound": facts["opposite_windings"]}}))
