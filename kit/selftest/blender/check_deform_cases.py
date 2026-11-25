"""check_deform_cases.py — fixture: a.bend / a.twist / a.taper / a.conform measured on plain parts. Nothing is
built: the parts are made and deformed and their places printed, one line `DEFORM_CASES {json}`, read by
kit/test/python/test_deform.py.
  Bar     a square bar 2 studs tall, bent 90 degrees toward +X: a quarter circle of radius 2 / (pi / 2)
  Hook    a bar on each side (a.mirror), bent toward +X: the mirrored one curls toward -X
  Drill   a bar twisted 90 degrees: its top section is the bottom one turned a quarter
  Spike   a bar tapered to a fifth; Vase a bar given a belly by a profile
  Teeth   a row of four (a.repeat), tapered: every tooth tapered about its own middle
  Plate   a flat plate above a dome, laid onto it with a gap: its underside a gap off the dome, its thickness kept
  Tab     a plate half past the dome's edge: the part past it carries on level, the share is said
  refusals  an unknown part, a part onto itself, nothing under the part, a bend too tight (and nothing was sliced)
And the faults the review of the first build found (2026-11-13):
  HalfTaper / HalfBend   a deform that starts HALF WAY up a plain bar: sliced there, the lower half untouched
  Prism     an off-centre three-sided bar twisted: its top is where the maths says (the way it turns)
  Hook~m1   naming a COPY is refused and moves nothing
  Patch     a floater is deformed like any part
  Pad       a mirrored pad laid onto a sloping ramp: each side lies on the ramp where IT stands
  Inset     a part already sunk in a block is brought back out onto its top, not through to its underside
  Tab10     a tab a tenth past a deck's edge: the share said is a tenth
`--pair`: on the high-and-low route a CAD bar, bent: its detailed and game versions are one shape, and its own
normals turned with it. Never "fix" this file."""

import json
import os
import sys

import numpy as np

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

BACK = rbx.BL_FROM_RBX.inverted()


def points(o):
    m = np.array(BACK @ o.matrix_world, np.float64)
    co = np.empty(len(o.data.vertices) * 3, np.float32)
    o.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]


def box_of(o):
    p = points(o)
    lo, hi = p.min(axis=0), p.max(axis=0)
    return {"lo": [round(float(v), 4) for v in lo], "hi": [round(float(v), 4) for v in hi], "verts": len(p)}


def off_normals(o):
    """how far a part's own corner normals stand from its faces' normals, degrees -> (mean, worst)"""
    mesh = o.data
    ln = np.empty(len(mesh.loops) * 3, np.float32)
    mesh.corner_normals.foreach_get("vector", ln)
    ln = ln.reshape(-1, 3)
    out = []
    for poly in mesh.polygons:
        n = np.array(poly.normal)
        for i in poly.loop_indices:
            out.append(float(np.degrees(np.arccos(np.clip(float(ln[i] @ n), -1.0, 1.0)))))
    return round(float(np.mean(out)), 3), round(float(np.max(out)), 3)


if "--pair" in sys.argv:
    a = rbx.Asset("_selftest_deform_pair", tex=64, size=(1.0, 1.0, 0.3), ground=False, low=15000)
    a.real_scale(280.0)
    a.material("steel", (0.56, 0.57, 0.58), metal=1.0, rough=0.35)
    low = a.cad("Bar", """
        part = Box(30, 200, 30)
        part = fillet(part.edges().filter_by(Axis.Y), 6)
        """, "steel", pos=(0, 0, 0))
    high = next(o for o, _g in a._high_parts if o.name == "Bar~high")
    before = {"low": off_normals(low), "high": off_normals(high)}
    a.bend("Bar", along="Y", toward="X", angle=60)
    print("DEFORM_CASES " + json.dumps({
        "low": box_of(low), "high": box_of(high), "before": before,
        "after": {"low": off_normals(low), "high": off_normals(high)},
        "brep": [bool(low.get("kit_brep_normals")), bool(high.get("kit_brep_normals"))],
        "facts": a.design.get("deforms")}))
    raise SystemExit(0)

a = rbx.Asset("_selftest_deform_cases", size=(12, 4, 12), ground=False)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.box("Bar", (0.2, 2.0, 0.2), (0, 1.0, 0), "iron", bevel=0.0)
a.bend("Bar", along="Y", toward="X", angle=90)
with a.mirror("X"):
    a.box("Hook", (0.2, 1.0, 0.2), (3, 0.5, 0), "iron", bevel=0.0)
a.bend("Hook", along="Y", toward="X", angle=90)
a.box("Drill", (0.4, 2.0, 0.1), (0, 1.0, 3), "iron", bevel=0.0)
a.twist("Drill", along="Y", angle=90)
a.box("Spike", (0.5, 2.0, 0.5), (0, 1.0, -3), "iron", bevel=0.0)
a.taper("Spike", along="Y", end=0.2)
a.box("Vase", (0.5, 2.0, 0.5), (2, 1.0, -3), "iron", bevel=0.0)
a.taper("Vase", along="Y", profile=[(0, 1), (0.5, 2), (1, 0.5)])
with a.repeat(4, step=(0.5, 0, 0)):
    a.box("Teeth", (0.2, 0.6, 0.2), (-5, 0.3, -3), "iron", bevel=0.0)
a.taper("Teeth", along="Y", end=0.25)
a.sphere("Dome", 1.0, (-4, 0, 3), "iron", segments=48, rings=24)
a.box("Plate", (1.0, 0.05, 1.0), (-4, 1.5, 3), "iron", bevel=0.0)
a.conform("Plate", "Dome", toward="-Y", gap=0.02, pitch=0.1)
a.box("Tab", (1.0, 0.05, 0.4), (-3.0, 1.5, 3), "iron", bevel=0.0)       # x from -3.5 to -2.5: the dome ends at x = -3
a.conform("Tab", "Dome", toward="-Y", gap=0.0, pitch=0.05)

a.box("HalfTaper", (0.4, 2.0, 0.4), (6, 1.0, 0), "iron", bevel=0.0)
a.taper("HalfTaper", along="Y", end=0.2, start=0.5)
a.box("HalfBend", (0.2, 2.0, 0.2), (8, 1.0, 0), "iron", bevel=0.0)
a.bend("HalfBend", along="Y", toward="X", angle=90, start=0.5)
PRISM = [(10.0, 0.0, 0.0), (10.4, 0.0, 0.0), (10.0, 0.0, 0.2), (10.0, 2.0, 0.0), (10.4, 2.0, 0.0), (10.0, 2.0, 0.2)]
a.mesh("Prism", PRISM, [(0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)], "iron")
a.twist("Prism", along="Y", angle=90)
with a.floaters():
    a.box("Patch", (0.6, 0.02, 0.4), (0, 2.02, 0), "iron", bevel=0.0)
a.taper("Patch", along="X", end=0.5)
a.box("Ramp", (6.0, 0.2, 1.0), (0, 3.0, -6), "iron", rot=(0, 0, 10), bevel=0.0)
with a.mirror("X"):
    a.box("Pad", (0.4, 0.05, 0.4), (2, 4.2, -6), "iron", bevel=0.0)
a.conform("Pad", "Ramp", toward="-Y", gap=0.0, pitch=0.1)
a.box("Block", (1.0, 1.0, 1.0), (6, 0.5, 6), "iron", bevel=0.0)
a.box("Inset", (0.4, 0.1, 0.4), (6, 0.7, 6), "iron", bevel=0.0)        # wholly inside the block
a.conform("Inset", "Block", toward="-Y", gap=0.0, pitch=0.2)
a.box("Deck", (2.0, 0.2, 2.0), (10, 0.1, 6), "iron", bevel=0.0)         # x from 9 to 11
a.box("Tab10", (1.0, 0.05, 0.4), (10.6, 1.0, 6), "iron", bevel=0.0)     # x from 10.1 to 11.1: a tenth past it
a.conform("Tab10", "Deck", toward="-Y", gap=0.0, pitch=0.05)

plate = points(next(o for o, _g in a.parts if o.name == "Plate"))
# how far above the dome (a true sphere; its mesh lies up to 0.002 inside it) each of the plate's vertices is, along y
above = plate[:, 1] - np.sqrt(np.maximum(1.0 - (plate[:, 0] + 4.0) ** 2 - (plate[:, 2] - 3.0) ** 2, 0.0))
tab = points(next(o for o, _g in a.parts if o.name == "Tab"))
over = tab[tab[:, 0] > -2.95]                                  # the half past the dome's edge

errors = {}
hook_copy = next(o for o, _g in a.parts if o.name == "Hook~m1")
copy_before = box_of(hook_copy)
try:
    a.twist("Hook~m1", along="Y", angle=90)
    errors["copy"] = None
except ValueError as e:
    errors["copy"] = str(e)
thick = a.box("Stub", (0.8, 0.5, 0.8), (5, 0.25, 5), "iron", bevel=0.0)
n_before = len(thick.data.vertices)
for what, run in (
        ("unknown", lambda: a.bend("Nobody", along="Y", toward="X", angle=30)),
        ("itself", lambda: a.conform("Plate", "Plate", toward="-Y")),
        ("nothing", lambda: a.conform("Stub", "Dome", toward="+Y")),
        ("tight", lambda: a.bend("Stub", along="Y", toward="X", angle=180)),
        ("along", lambda: a.twist("Stub", along="W", angle=30)),
):
    try:
        run()
        errors[what] = None
    except ValueError as e:
        errors[what] = str(e)



def section(name, y0, y1):
    """the size across (x, z) of a part's vertices between two heights"""
    p = points(next(o for o, _g in a.parts if o.name == name))
    p = p[(p[:, 1] >= y0) & (p[:, 1] <= y1)]
    if not len(p):
        return [0.0, 0.0, 0]
    return [round(float(np.ptp(p[:, 0])), 4), round(float(np.ptp(p[:, 2])), 4), len(p)]


def box_of_below(name, y):
    p = points(next(o for o, _g in a.parts if o.name == name))
    p = p[p[:, 1] <= y + 1e-6]
    return {"lo": [round(float(v), 4) for v in p.min(axis=0)], "hi": [round(float(v), 4) for v in p.max(axis=0)]}


def patch_ends():
    """the floater's width (z) at its low-x end and at its high-x end"""
    p = points(next(o for o, _g in a._floater_parts if o.name == "Patch"))
    lo, hi = p[p[:, 0] < p[:, 0].min() + 1e-4], p[p[:, 0] > p[:, 0].max() - 1e-4]
    return [round(float(np.ptp(lo[:, 2])), 4), round(float(np.ptp(hi[:, 2])), 4)]


print("DEFORM_CASES " + json.dumps({
    "parts": {o.name: box_of(o) for o, _g in a.parts},
    "sections": {"drill_top": section("Drill", 1.99, 2.01), "drill_slice4": section("Drill", 0.88, 0.90),
                 "spike_top": section("Spike", 1.99, 2.01), "spike_foot": section("Spike", -0.01, 0.01),
                 "vase_belly": section("Vase", 0.99, 1.01), "vase_top": section("Vase", 1.99, 2.01),
                 "tooth_top": section("Teeth~m2", 0.59, 0.61)},
    "plate": {"above": [round(float(above.min()), 4), round(float(above.max()), 4)],
              "under": int((above < 0.045).sum()), "top": int((above >= 0.045).sum()),
              "thick": round(float(np.ptp(plate[np.hypot(plate[:, 0] + 4.0, plate[:, 2] - 3.0) < 0.03][:, 1])), 4)},
    "tab": {"over_y": [round(float(over[:, 1].min()), 4), round(float(over[:, 1].max()), 4)]},
    "facts": a.design.get("deforms"),
    "errors": errors,
    "stub_verts": [n_before, len(thick.data.vertices)],
    "copy_kept": [copy_before, box_of(hook_copy)],
    "review": {
        "half_taper": {"foot": section("HalfTaper", -0.01, 0.01), "mid": section("HalfTaper", 0.99, 1.01),
                       "below": section("HalfTaper", 0.01, 0.99), "top": section("HalfTaper", 1.99, 2.01)},
        "half_bend": {"stem": box_of_below("HalfBend", 1.0), "ring": section("HalfBend", 0.999, 1.001)},
        "prism_top": sorted([round(float(c), 4) for c in p] for p in points(next(
            o for o, _g in a.parts if o.name == "Prism")) if p[1] > 1.99),
        "patch": {o.name: box_of(o) for o, _g in a._floater_parts if o.name == "Patch"},
        "patch_ends": patch_ends(),
        "pads": {n: box_of(next(o for o, _g in a.parts if o.name == n)) for n in ("Pad", "Pad~m1")},
        "inset": box_of(next(o for o, _g in a.parts if o.name == "Inset")),
    },
}))
