"""build_flow.py - fixture for EDGE FLOW, MOVED (a.flow, rbx_flow; the 3D methods audit's PARTLY "a tool that moves
vertices or slides a loop to redistribute flow"). A panel with four loops bunched at one end; a rod (16 sides) with
three rings bunched at one end, MIRRORED (its copy has free vertices: it must move the mirrored way, vertex by
vertex); a second rod with rings a hair from its end cap flowed in TWO passes (review 2026-11-17: the ring
collapsed onto the cap - every vertex on the surface, the shape gone; now each vertex keeps to its own smooth
region); a plain box (all corners) and a CAD part refused. Prints FLOW {...}: per part how even before / after, how
far off its surface, how far its box moved, the most any face turned. Used by kit/test/python/test_flow_build.py.
Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import numpy as np  # noqa: E402
import rbx  # noqa: E402

a = rbx.Asset("_selftest_flow", tex=256, size=(5.0, 2.4, 1.0), ground=False)
a.material("paint", (0.5, 0.5, 0.52), rough=0.6)
a.box("Panel", (2.0, 0.1, 1.0), (0.0, 0.5, 0.0), "paint", bevel=0)
with a.mirror("X"):
    a.cylinder("Rod", 0.2, 2.0, (1.4, 1.5, 0.0), "paint", axis="X", segments=16, bevel=0)
a.cylinder("Ring", 0.2, 2.0, (0.0, 2.1, 0.0), "paint", axis="X", segments=16, bevel=0)
a.box("Plain", (0.3, 0.3, 0.3), (0.0, 0.0, 0.0), "paint", bevel=0)
a.cad("Cad", """
    part = Box(40, 40, 40)
    """, "paint", pos=(-2.0, 0.2, 0.0))
a.loop("Panel", "X", at=[0.02, 0.04, 0.06, 0.08, 0.5])
a.loop("Rod", "X", at=[0.03, 0.06, 0.09, 0.5])
a.loop("Ring", "X", at=[0.002, 0.004, 0.006, 0.5])


def normals(part):
    o, p = a._part_points(part, "fixture")
    f = [list(pl.vertices) for pl in o.data.polygons]
    n = []
    for vs in f:
        q = p[vs]
        c = np.cross(q[1] - q[0], q[2] - q[0])
        n.append(c / max(np.linalg.norm(c), 1e-30))
    return np.array(n)


out = {}
for part, kw in (("Panel", {}), ("Rod", {}), ("Ring", {"iterations": 2})):
    _o, before = a._part_points(part, "fixture")
    lo, hi = before.min(axis=0), before.max(axis=0)
    n0 = normals(part)
    rec = a.flow(part, **kw)
    _o, after = a._part_points(part, "fixture")
    n1 = normals(part)
    turn = float(np.degrees(np.arccos(np.clip((n0 * n1).sum(1), -1, 1))).max())
    out[part] = {**{k: rec[k] for k in ("moved", "spread_before", "spread_after", "off_mm")},
                 "box_moved": round(float(max(np.abs(after.min(axis=0) - lo).max(),
                                              np.abs(after.max(axis=0) - hi).max())), 6),
                 "face_turn_deg": round(turn, 3)}
# the rod's mirrored copy moved the mirrored way, VERTEX BY VERTEX (its points mirrored back are the rod's, in order)
copy = a._copies.get("Rod", [])
if copy:
    m = np.array(rbx.BL_FROM_RBX.inverted() @ copy[0].matrix_world, np.float64)
    co = np.empty(len(copy[0].data.vertices) * 3, np.float32)
    copy[0].data.vertices.foreach_get("co", co)
    cp = co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]
    _o, rp = a._part_points("Rod", "fixture")
    out["copy_off"] = round(float(np.abs(cp * np.array([-1.0, 1.0, 1.0]) - rp).max()), 6)
for refused in ("Plain", "Cad"):
    try:
        a.flow(refused)
        out[refused] = "moved"
    except ValueError as e:
        out[refused] = str(e)[:140]
a.build()
print("FLOW " + json.dumps(out))
