"""build_moulding.py — fixture for A MOULDING (H4, a.moulding) LAID INTO A TRIM SHEET BY ITS OWN LENGTH: a panel 3 x 2
studs framed by a moulding that follows its front face's outline (four mitred corners), and a curved rail (a half
circle on the panel's face, smooth), both laid into the trim sheet fixture's 1-stud "edge" band. Needs build_trim_sheet.py built first,
in the same build folder.
After the build one line `MOULD {json}`:
  frame_jumps / rail_jumps   corners of the swept faces where two faces meeting at one point disagree on U (the
                             band would jump there) - 0, but for the loop's one closing point (the frame)
  frame_u / rail_u           how far along the band each runs (its length / the sheet's studs)
  v_in_band                  every swept corner's V inside the band
  mitred                     for each of the panel's four corners: how many of the frame's points lie on its
                             bisector there (the frame-maker's 45 degrees: the section's points, every one)
  section_points             the profile's point count (what `mitred` should read at each corner)
Used by kit/test/python/test_moulding.py. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import math  # noqa: E402

import rbx  # noqa: E402

PROFILE = [(-0.04, 0.0), (0.28, 0.0), (0.28, 0.06), (0.18, 0.16), (0.06, 0.2), (-0.04, 0.12)]   # (~0.9 round)
a = rbx.Asset("_selftest_moulding", tex=64, size=(3.08, 2.08, 0.4), ground=False)
a.material("any", color=(0.5, 0.5, 0.5), rough=0.7)
a.box("Panel", (3.0, 2.0, 0.2), (0, 0, 0), "any", bevel=0, group="panel")
a.moulding("Frame", PROFILE, "Panel", "any", facing="-Z", group="frame")
arc = [(0.6 * math.cos(t), 0.6 * math.sin(t) - 0.3, -0.1) for t in [math.pi * k / 16 for k in range(17)]]
a.moulding("Rail", PROFILE, arc, "any", facing="-Z", mitre=False, group="frame")
a.trim("Frame", "_selftest_trim_sheet", "edge")
a.trim("Rail", "_selftest_trim_sheet", "edge", start=0.0)
a.build()

import bpy  # noqa: E402

man = json.load(open(os.path.join(rbx.BUILD, "models", "_selftest_trim_sheet.manifest.json"), encoding="utf-8"))
band = man["trim_sheet"]["bands"]["edge"]
studs = man["trim_sheet"]["studs"]
out = {"section_points": len(PROFILE)}
for o in bpy.data.objects:
    if o.type != "MESH" or "frame" not in o.name:
        continue
    names, attr = list(o.get("kit_parts") or []), o.data.attributes.get("kit_part")
    back = rbx.BL_FROM_RBX.inverted() @ o.matrix_world
    uv = o.data.uv_layers.active.data
    on = o.data.attributes.get(rbx.STRIP_ON)
    v_ok = True
    for part in ("Frame", "Rail"):
        idx = names.index(part)
        at = {}
        top = 0.0
        for poly in o.data.polygons:
            if attr.data[poly.index].value != idx or not on.data[poly.index].value:
                continue
            for li, vi in zip(poly.loop_indices, poly.vertices):
                u_, v_ = uv[li].uv
                top = max(top, u_)
                at.setdefault(vi, set()).add(round(u_, 4))
                v_ok &= band["v0"] - 1e-4 <= v_ <= band["v1"] + 1e-4
        out[f"{part.lower()}_jumps"] = sum(1 for us in at.values() if max(us) - min(us) > 1e-3)
        out[f"{part.lower()}_u"] = round(top, 4)
    out["v_in_band"] = bool(v_ok)
    pts = [back @ o.data.vertices[v].co for poly in o.data.polygons
           if attr.data[poly.index].value == names.index("Frame") for v in poly.vertices]
    pts = {tuple(round(c, 5) for c in p) for p in pts}
    mitred = []
    for cx, cy in ((-1.5, -1.0), (1.5, -1.0), (1.5, 1.0), (-1.5, 1.0)):
        sx, sy = (1 if cx > 0 else -1), (1 if cy > 0 else -1)
        near = [p for p in pts if abs(p[0] - cx) < 0.35 and abs(p[1] - cy) < 0.35]
        mitred.append(sum(1 for p in near if abs((p[0] - cx) * sx - (p[1] - cy) * sy) < 1e-4))
    out["mitred"] = mitred
print("MOULD " + json.dumps(out))
