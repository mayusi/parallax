"""check_smooth_cases.py — fixture: a.smooth (subdivision with held edges) measured on plain boxes. Nothing is
built: the parts are made and smoothed and their volume, box and face counts printed, one line
`SMOOTH_CASES {json}`, read by kit/test/python/test_smooth.py.
  Soft     a unit box smoothed all soft: a pebble inside its own box, smaller than it
  Hard     every sharp edge held: the same box, to the last place, with 4 x 4 x 4 times the faces
  Foot     only the four edges of its foot held: the foot stays the full square, the top goes round
  Half     every sharp edge held half hard: between the two
  Pair     a box each side (a.mirror), one end's edges held by a rule on x: the mirrored one held on ITS outer end
  Row      a row of three in three sizes: each smoothed in its own size
  Two      a part of two materials: every face still has its own after smoothing
  Pod      box modelling then smoothing: a box cut, a boss pushed out, all of it smoothed
  Lid      a box with a sunk panel, every sharp edge held: the same solid to the last place, no fold at the rim's
           mitres (the first build's rim folded over the pocket's corners); and the same with only the rim's two
           outlines held by a rule is REFUSED as a fold, with nothing changed
  refusals  levels 0 and 9, too many faces, a bad crisp, a rule that answers 2, a hold of 3, a copy's name - each
            with nothing changed, to the vertex
And the faults the review of the first build found (2026-11-13):
  Holes    a box with a hole cut through it (a.cut), smoothed soft and with its edges held, at 1, 2 and 3 levels:
           no face through another (the first build let the front wall fold through the hole's)
  Notch    a box with a notch cut out, its sharp edges held: the same solid to the last place
  Holds    hold 0.25 / 0.5 / 0.75 at 1, 2 and 3 levels: each softer than the next, at every level count
  Zs       a rule on an edge's direction (d[2] > 0.9) holds all four edges along z, whichever way each runs
  NumBool  a rule that answers numpy's True is held at `hold`, like Python's
  copies   a mirrored and a varied, turned copy are the part's own points moved to their place
`--cad`: a CAD part is refused. Never "fix" this file."""

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


def points(name):
    o = next(o for o, _g in a.parts if o.name == name)
    m = np.array(BACK @ o.matrix_world, np.float64)
    co = np.empty(len(o.data.vertices) * 3, np.float32)
    o.data.vertices.foreach_get("co", co)
    return o, co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]


def stamp(name):
    """a part's mesh, to the vertex, in its own coordinates"""
    o = next(o for o, _g in a.parts if o.name == name)
    co = np.empty(len(o.data.vertices) * 3, np.float32)
    o.data.vertices.foreach_get("co", co)
    return [co.tobytes().hex(), len(co), [tuple(p.vertices) for p in o.data.polygons][:40]]


def said(name):
    o, p = points(name)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    out = {"lo": [round(float(v), 4) for v in p.min(axis=0)], "hi": [round(float(v), 4) for v in p.max(axis=0)],
           "volume": round(bm.calc_volume(signed=True), 5), "faces": len(bm.faces),
           "faults": list(rbx_poly.faults(bm)), "doubled": rbx_poly.doubled(bm), "crossing": rbx_poly.crossing(bm),
           "slots": sorted({f.material_index for f in bm.faces})}
    bm.free()
    return out


def span(name, lo, hi, axis=1):
    """the size ACROSS of a part's vertices between two places along one axis (y: its height)"""
    _o, p = points(name)
    p = p[(p[:, axis] >= lo) & (p[:, axis] <= hi)]
    rest = [i for i in range(3) if i != axis]
    return [round(float(np.ptp(p[:, i])), 4) for i in rest] if len(p) else [0.0, 0.0]


if "--cad" in sys.argv:
    a = rbx.Asset("_selftest_smooth_cad", tex=64, size=(1.0, 1.0, 1.0), ground=False)
    a.real_scale(280.0)
    a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
    a.cad("Cad", "part = Box(280, 280, 280)\n", "iron", pos=(0, 0.5, 0))
    was = stamp("Cad")
    try:
        a.smooth("Cad", levels=1)
        err = None
    except ValueError as e:
        err = str(e)
    print("SMOOTH_CASES " + json.dumps({"cad": err, "kept": was == stamp("Cad")}))
    raise SystemExit(0)

a = rbx.Asset("_selftest_smooth_cases", size=(20, 4, 20), ground=False)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("brass", color=(0.72, 0.55, 0.25), metal=1.0, rough=0.35)
U = (1.0, 1.0, 1.0)
a.box("Soft", U, (0, 0.5, 0), "iron", bevel=0)
a.smooth("Soft", levels=3)
a.box("Hard", U, (0, 0.5, 3), "iron", bevel=0)
a.smooth("Hard", levels=3, crisp="sharp")
a.box("Foot", U, (0, 0.5, 6), "iron", bevel=0)
a.smooth("Foot", levels=3, crisp=lambda c, d: c[1] < 0.01)
a.box("Half", U, (0, 0.5, 9), "iron", bevel=0)
a.smooth("Half", levels=3, crisp="sharp", hold=0.5)
with a.mirror("X"):
    a.box("Pair", (2.0, 1.0, 1.0), (5, 0.5, 0), "iron", bevel=0)
a.smooth("Pair", levels=2, crisp=lambda c, d: c[0] > 5.99)        # the part's OUTER end (x = 6) stays square
with a.repeat(3, step=(0, 0, 2.5), vary={"size": 0.3, "turn": 20}):
    a.box("Row", U, (-5, 0.5, -2), "iron", bevel=0)
a.smooth("Row", levels=2, crisp=lambda c, d: c[1] < 0.01 and c[0] < -5.2)   # one edge of its foot: lopsided


def off_its_place(part, copy):
    """how far a copy's points are from the part's own points moved to the copy's place (the worst one)"""
    _o, p = points(part)
    _c, q = points(copy)
    m = np.array(a._copy_place[copy], np.float64)
    moved = p @ m[:3, :3].T + m[:3, 3]                 # (a mirrored mesh lists its points in another order:
    gaps = np.linalg.norm(moved[:, None, :] - q[None, :, :], axis=2)   # each to the nearest, both ways)
    return round(float(max(gaps.min(axis=1).max(), gaps.min(axis=0).max())), 6) if len(p) == len(q) else 9.0


a.box("Two", U, (0, 0.5, 12), "iron", bevel=0)
a.zone("Two", "brass", lambda c, n: n[1] > 0.9)
a.smooth("Two", levels=2, crisp="sharp")
two = next(o for o, _g in a.parts if o.name == "Two")
brass = next(i for i, m in enumerate(two.data.materials) if m == a._mat("brass"))
two_top = sorted({p.material_index for p in two.data.polygons
                  if (BACK.to_3x3() @ two.matrix_world.to_3x3() @ p.normal).y > 0.9})
two_rest = sorted({p.material_index for p in two.data.polygons
                   if (BACK.to_3x3() @ two.matrix_world.to_3x3() @ p.normal).y < 0.5})
a.box("Pod", (2.0, 1.0, 1.0), (0, 0.5, -4), "iron", bevel=0)
a.loop("Pod", "X", at=[0.35, 0.65])
a.push("Pod", lambda c, n: n[1] > 0.9 and abs(c[0]) < 0.25, 0.3)
a.smooth("Pod", levels=2)

a.box("Lid", (1.6, 0.8, 1.1), (5, 0.4, -4), "iron", bevel=0)
a.inset("Lid", "+Y", 0.14, depth=-0.08)
a.smooth("Lid", levels=2, crisp="sharp")
a.box("Fold", (1.6, 0.8, 1.1), (5, 0.4, -7), "iron", bevel=0)
a.inset("Fold", "+Y", 0.14, depth=-0.08)
fold0 = stamp("Fold")
try:   # every edge that is not flat held BY A RULE: the rim's four mitres stay soft, and fold
    a.smooth("Fold", levels=2, crisp=lambda c, d: not (abs(c[1] - 0.8) < 1e-6 and abs(d[0]) > 0.1 and abs(d[2]) > 0.1))
    fold_error = None
except ValueError as e:
    fold_error = str(e)
holes, k = {}, 0
for crisp in (None, "sharp"):
    for lv in (1, 2, 3):
        k += 1
        name = f"Hole{k}"
        a.box(name, (1.5, 1.0, 1.0), (12 + 3 * k, 0.5, 0), "iron", bevel=0)
        a.cut(name, a.cylinder(name + "c", 0.25, 3, (12.3 + 3 * k, 0.5, 0), "brass", axis="Z", bevel=0))
        was = said(name)["volume"]
        a.smooth(name, levels=lv, crisp=crisp)
        holes[f"{crisp} x{lv}"] = [was, said(name)]
a.box("Notch", (1.5, 1.0, 1.0), (12, 0.5, 4), "iron", bevel=0)
a.cut("Notch", a.box("Notchc", (0.3, 0.4, 3), (12, 0.9, 4), "brass", bevel=0))
notch0 = said("Notch")["volume"]
a.smooth("Notch", levels=2, crisp="sharp")
holds, k = {}, 0
for lv in (1, 2, 3):
    row = []
    for hold in (0.0, 0.25, 0.5, 0.75, 1.0):
        k += 1
        a.box(f"Hold{k}", U, (12 + 2 * k, 0.5, 8), "iron", bevel=0)
        a.smooth(f"Hold{k}", levels=lv, crisp="sharp", hold=hold)
        row.append(said(f"Hold{k}")["volume"])
    holds[str(lv)] = row
a.box("Zs", U, (12, 0.5, 12), "iron", bevel=0)
a.smooth("Zs", levels=2, crisp=lambda c, d: d[2] > 0.9)
a.box("PyBool", U, (15, 0.5, 12), "iron", bevel=0)
a.smooth("PyBool", levels=2, crisp=lambda c, d: c[1] < 0.01, hold=0.3)
a.box("NumBool", U, (18, 0.5, 12), "iron", bevel=0)
a.smooth("NumBool", levels=2, crisp=lambda c, d: np.bool_(c[1] < 0.01), hold=0.3)
errors = {}
a.box("Plain", U, (8, 0.5, 8), "iron", bevel=0)
plain0 = stamp("Plain")
for what, run in (
        ("levels0", lambda: a.smooth("Plain", levels=0)),
        ("levels9", lambda: a.smooth("Plain", levels=9)),
        ("crisp", lambda: a.smooth("Plain", crisp="hard")),
        ("answer", lambda: a.smooth("Plain", crisp=lambda c, d: 2.0)),
        ("hold", lambda: a.smooth("Plain", crisp="sharp", hold=3)),
        ("copy", lambda: a.smooth("Pair~m1")),
        ("unknown", lambda: a.smooth("Nobody")),
        ("levels_true", lambda: a.smooth("Plain", levels=True)),
        ("levels_float", lambda: a.smooth("Plain", levels=2.0)),
        ("levels_text", lambda: a.smooth("Plain", levels="1")),
        ("answer_text", lambda: a.smooth("Plain", crisp=lambda c, d: "0.5")),
        ("angle", lambda: a.smooth("Plain", crisp="sharp", angle=float("nan"))),
        ("round_after", lambda: a.round("Soft", 0.02)),
        ("ngons", lambda: (a.cylinder("Big", 0.5, 1.0, (8, 0.5, 14), "iron", segments=400, bevel=0),
                           a.smooth("Big", levels=4))),
):
    try:
        run()
        errors[what] = None
    except ValueError as e:
        errors[what] = str(e)
a.box("Dense", U, (8, 0.5, 11), "iron", bevel=0)
a.smooth("Dense", levels=4)                                        # 6 faces -> 1,536
try:
    a.smooth("Dense", levels=4)                                    # ... -> 393,216: more than a build can carry
    errors["faces"] = None
except ValueError as e:
    errors["faces"] = str(e)

print("SMOOTH_CASES " + json.dumps({
    "parts": {n: said(n) for n in ("Hard", "Foot", "Half", "Pair", "Pair~m1", "Row", "Row~m1", "Row~m2", "Two", "Pod",
                                   "Lid")},
    "fold": [fold_error, fold0 == stamp("Fold")],
    "soft": said("Soft"),
    "foot": {"at_foot": span("Foot", -0.001, 0.001), "at_top": span("Foot", 0.9, 2.0)},
    "pair": {"outer": span("Pair", 5.99, 9.0, axis=0), "inner": span("Pair", 0.0, 4.2, axis=0),
             "twin_outer": span("Pair~m1", -9.0, -5.99, axis=0), "twin_inner": span("Pair~m1", -4.2, 0.0, axis=0)},
    "row_scales": [1.0] + [round(abs(a._copy_place[n].to_3x3().determinant()) ** (1 / 3), 5)
                           for n in ("Row~m1", "Row~m2")],
    "two": [two_top, two_rest, brass], "errors": errors, "kept": plain0 == stamp("Plain"),
    "holes": holes, "notch": [notch0, said("Notch")], "holds": holds,
    "bools": [said("PyBool")["volume"], said("NumBool")["volume"]],
    "copies": {"mirror": off_its_place("Pair", "Pair~m1"), "row": off_its_place("Row", "Row~m1")},
    "left_behind": {"temp": sorted(d.name for d in list(rbx.bpy.data.objects) + list(rbx.bpy.data.meshes)
                                   if d.name.startswith("_kit_subd")),
                    "creases": sorted(n for n in next(o for o, _g in a.parts if o.name == "Foot").data.attributes.keys()
                                      if n.startswith("crease"))},
    "bevel_after": float(next(o for o, _g in a.parts if o.name == "Soft").get("kit_bevel", -1.0)),
    "facts": a.design.get("modelled"),
}))
