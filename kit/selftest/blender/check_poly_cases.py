"""check_poly_cases.py — fixture: a.inset / a.push / a.loop / a.round measured on plain boxes. Nothing is built: the
parts are made and changed and their volume, box and face counts printed, one line `POLY_CASES {json}`, read by
kit/test/python/test_poly.py.
  Flat     a 2 x 1 x 1 box, its top inset 0.2: the same volume, four rim faces more
  Sunk     the same, the panel sunk 0.1 with straight walls: 1.6 x 0.6 x 0.1 less
  Raised   the same, raised 0.1
  Boss     its +X side pushed out 0.5
  Slot     two cuts across its length and two across its depth, then the middle of its top pushed IN 0.3: a pocket
  Pair     a box on each side (a.mirror), each inset and pushed on its +X side as the PART is: the mirrored one on
           its -X side
  Row      a row of three (a.repeat, each its own size): every one inset on its own top
  Round    a sharp box rounded last: smaller by its rounds, closed
  Twice    a box cut four times across, two of its top strips pushed out: two places, and the facts say so
  Round bodies   a pocket in a cylinder's side and in a ball's top (the first build refused both)
  Painted  a zoned face pushed out: the boss's walls all take ITS material
And what must be refused with NOTHING changed, to the vertex: a pocket's floor pushed OUT (the first build laid
new walls on the pocket's own), a round wider than the part has room for, and with `--cad` a CAD part (a loop
cut is allowed on it: a cut changes no shape).
  refusals  a rule that picks nothing, a rim wider than the face, faces that look every way, a CAD-like part, a
            bad rule - each with nothing changed
Never "fix" this file."""

import json
import os
import sys

import bmesh
import numpy as np

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_poly  # noqa: E402

BACK = rbx.BL_FROM_RBX.inverted()


def stamp(name):
    """a part's mesh, to the vertex: its points, its faces' corners and materials"""
    o = next(o for o, _g in a.parts if o.name == name)
    co = np.empty(len(o.data.vertices) * 3, np.float32)
    o.data.vertices.foreach_get("co", co)
    return [co.tobytes().hex()[:64], len(co), [tuple(p.vertices) for p in o.data.polygons][:40],
            [p.material_index for p in o.data.polygons]]


def said(name):
    o = next(o for o, _g in a.parts if o.name == name)
    m = np.array(BACK @ o.matrix_world, np.float64)
    co = np.empty(len(o.data.vertices) * 3, np.float32)
    o.data.vertices.foreach_get("co", co)
    p = co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    out = {"lo": [round(float(v), 4) for v in p.min(axis=0)], "hi": [round(float(v), 4) for v in p.max(axis=0)],
           "volume": round(bm.calc_volume(signed=True), 5), "faces": len(bm.faces),
           "faults": list(rbx_poly.faults(bm)), "doubled": rbx_poly.doubled(bm),
           "slots": sorted({f.material_index for f in bm.faces})}
    bm.free()
    return out


if "--cad" in sys.argv:
    a = rbx.Asset("_selftest_poly_cad", tex=64, size=(1.0, 1.0, 1.0), ground=False)
    a.real_scale(280.0)
    a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
    a.cad("Cad", "part = Box(280, 280, 280)\n", "iron", pos=(0, 0.5, 0))
    was, tried = stamp("Cad"), {}
    for what, run in (("push", lambda: a.push("Cad", "+Y", 0.1)), ("inset", lambda: a.inset("Cad", "+Y", 0.1)),
                      ("round", lambda: a.round("Cad", 0.02))):
        try:
            run()
            tried[what] = None
        except ValueError as e:
            tried[what] = str(e)
    kept = was == stamp("Cad")
    a.loop("Cad", "Y", count=1)                     # a cut changes no shape: allowed
    print("POLY_CASES " + json.dumps({"cad": tried, "kept": kept, "after_loop": said("Cad")}))
    raise SystemExit(0)

a = rbx.Asset("_selftest_poly_cases", size=(20, 4, 20), ground=False)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
B = (2.0, 1.0, 1.0)
a.box("Flat", B, (0, 0.5, 0), "iron", bevel=0)
a.inset("Flat", "+Y", 0.2)
a.box("Sunk", B, (0, 0.5, 3), "iron", bevel=0)
a.inset("Sunk", "+Y", 0.2, depth=-0.1)
a.box("Raised", B, (0, 0.5, 6), "iron", bevel=0)
a.inset("Raised", "+Y", 0.2, depth=0.1)
a.box("Boss", B, (0, 0.5, -3), "iron", bevel=0)
a.push("Boss", "+X", 0.5)
a.box("Slot", B, (0, 0.5, -6), "iron", bevel=0)
a.loop("Slot", "X", at=[0.35, 0.65])
a.loop("Slot", "Z", count=3)
a.push("Slot", lambda c, n: n[1] > 0.9 and abs(c[0]) < 0.25 and abs(c[2] + 6) < 0.2, -0.3)
with a.mirror("X"):
    a.box("Pair", (1.0, 1.0, 1.0), (5, 0.5, 0), "iron", bevel=0)
a.inset("Pair", "+X", 0.2)
a.push("Pair", lambda c, n: n[0] > 0.9 and abs(c[1] - 0.5) < 0.31 and abs(c[2]) < 0.31, 0.25)
with a.repeat(3, step=(0, 0, 2.0), vary={"size": 0.3, "turn": 20}):
    a.box("Row", (1.0, 1.0, 1.0), (-5, 0.5, -2), "iron", bevel=0)
a.inset("Row", "+Y", 0.2, depth=-0.1)
a.box("Round", B, (0, 0.5, 9), "iron", bevel=0)
a.round("Round", 0.05)
a.box("Twice", B, (0, 0.5, 12), "iron", bevel=0)
a.loop("Twice", "X", at=[0.2, 0.4, 0.6, 0.8])
a.push("Twice", lambda c, n: n[1] > 0.9 and 0.2 < abs(c[0]) < 0.6, 0.1)      # the second and the fourth strip
a.cylinder("Drum", 0.5, 2.0, (5, 1.0, 6), "iron", axis="Y", segments=16)
drum0 = said("Drum")["volume"]
a.loop("Drum", "Y", at=[0.3, 0.7])
a.inset("Drum", lambda c, n: n[0] > 0.9 and abs(c[1] - 1.0) < 0.3, 0.05, depth=-0.05)   # a pocket in its side
a.sphere("Ball", 0.5, (5, 0.5, 9), "iron", segments=16, rings=8)
ball0 = said("Ball")["volume"]
a.inset("Ball", lambda c, n: n[1] > 0.9, 0.03, depth=-0.03)                    # a pocket in its top
a.material("brass", color=(0.72, 0.55, 0.25), metal=1.0, rough=0.35)
a.box("Painted", B, (5, 0.5, 12), "iron", bevel=0)
a.zone("Painted", "brass", lambda c, n: n[1] > 0.9)
a.push("Painted", "+Y", 0.2)
painted = next(o for o, _g in a.parts if o.name == "Painted")
brass = next(i for i, m in enumerate(painted.data.materials) if m == a._mat("brass"))
walls = [p.material_index for p in painted.data.polygons
         if abs((BACK.to_3x3() @ painted.matrix_world.to_3x3() @ p.normal).y) < 0.1
         and (BACK @ (painted.matrix_world @ p.center)).y > 1.0]
a.box("Halves", B, (0, 0.5, 15), "iron", bevel=0)
a.loop("Halves", "X", at=[0.5], start=0.5, stop=1.0)                           # half way along its SECOND half
halves_x = sorted({round(float(v.co.x), 4) for v in next(o for o, _g in a.parts if o.name == "Halves").data.vertices})

errors = {}
plain = a.box("Plain", B, (8, 0.5, 8), "iron", bevel=0)
before = said("Plain")
plain_kept = stamp("Plain")
for what, run in (
        ("none", lambda: a.inset("Plain", lambda c, n: False, 0.1)),
        ("wide", lambda: a.inset("Plain", "+Y", 0.6)),
        ("every_way", lambda: a.push("Plain", lambda c, n: True, 0.1)),
        ("to_the_edge", lambda: a.push("Plain", "+Y", -0.2)),
        ("rule", lambda: a.inset("Plain", "up", 0.1)),
        ("unknown", lambda: a.push("Nobody", "+Y", 0.1)),
        ("copy", lambda: a.inset("Pair~m1", "+X", 0.05)),
        ("loop", lambda: a.loop("Plain", "X", at=[0.5, 1.5])),
        ("round", lambda: a.round("Plain", -1)),
        ("round_wide", lambda: a.round("Plain", 0.6)),
        ("segments", lambda: a.round("Plain", 0.05, segments=0)),
        ("count0", lambda: a.loop("Plain", "X", count=0)),
):
    try:
        run()
        errors[what] = None
    except ValueError as e:
        errors[what] = str(e)

# a pocket's floor pushed OUT: the new walls would lie on the pocket's own
a.box("Pocket", B, (8, 0.5, 11), "iron", bevel=0)
a.inset("Pocket", "+Y", 0.2, depth=-0.2)
pocket0 = stamp("Pocket")
try:
    a.push("Pocket", lambda c, n: n[1] > 0.9 and c[1] < 0.9, 0.1)
    errors["floor_out"] = None
except ValueError as e:
    errors["floor_out"] = str(e)

print("POLY_CASES " + json.dumps({
    "parts": {n: said(n) for n in ("Flat", "Sunk", "Raised", "Boss", "Slot", "Pair", "Pair~m1", "Row", "Row~m1",
                                   "Row~m2", "Round", "Twice", "Drum", "Ball", "Painted")},
    "plain": [before, said("Plain")], "errors": errors, "facts": a.design.get("modelled"),
    "kept": {"plain": plain_kept == stamp("Plain"), "pocket": pocket0 == stamp("Pocket"),
             },
    "round_bodies": {"drum": [drum0, said("Drum")["volume"]], "ball": [ball0, said("Ball")["volume"]]},
    "painted_walls": [walls, brass], "halves_x": halves_x,
    "row_scales": [1.0] + [round(abs(a._copy_place[n].to_3x3().determinant()) ** (1 / 3), 5)
                           for n in ("Row~m1", "Row~m2")],
}))
