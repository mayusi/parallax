"""check_repeat_cases.py — fixture: a.repeat's corner cases, each one a fault the review of the first build found
(card nkjm, 2026-11-13). Nothing is built: the parts are made and their places printed, one line
`REPEAT_CASES {json}`, read by kit/test/python/test_repeat.py.
  Turned    a row opened OUTSIDE a turned a.frame: the row runs where the block was opened (along x), not along
            the turned frame's own x
  Orbit     a ring opened outside a moved a.frame: round the block's centre, not round the frame's own origin
  Inside    a row opened INSIDE a turned a.frame: its step is the frame's
  Wheel     a ring inside a row: two whole rings, the second a row's step from the first
  Lump      a part whose geometry is far from its own origin, every copy another size: each stays on its place
            (it differs about its own middle, not about the origin)
  Rail      a row along x inside a.mirror("X"): the mirror of the whole row, not a row of the mirror
  Tip       a.zone on a repeated and mirrored part: every copy zoned on the half the part is
  Slot      a repeated cutter, used up by its cut: no longer a repeated PART
  refusals  512 passed by nesting (said at the block), a stamp inside a block, a row given a ring's option
`--pair`: on the high-and-low route, a CAD part repeated with vary= - its detailed and game versions get the same
copies (the game copy is baked from its own detailed one). Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

BACK = rbx.BL_FROM_RBX.inverted()


def box_of(o):
    cs = [BACK @ (o.matrix_world @ rbx.Vector(c)) for c in o.bound_box]
    lo = [min(c[i] for c in cs) for i in range(3)]
    hi = [max(c[i] for c in cs) for i in range(3)]
    return {"mid": [round((p + q) / 2, 4) for p, q in zip(lo, hi)], "size": [round(q - p, 4) for p, q in zip(lo, hi)]}


if "--pair" in sys.argv:
    a = rbx.Asset("_selftest_repeat_pair", tex=64, size=(3.0, 0.6, 0.6), ground=False, low=15000)
    a.real_scale(280.0)
    a.material("steel", (0.56, 0.57, 0.58), metal=1.0, rough=0.35)
    with a.repeat(5, step=(0.5, 0, 0), vary={"size": 0.3, "turn": 25}):
        a.cad("Lug", """
            part = Box(40, 70, 30)
            part = fillet(part.edges(), 5)
            """, "steel", pos=(-1.0, 0, 0))
    print("REPEAT_CASES " + json.dumps({
        "parts": {o.name: box_of(o) for o, _g in a.parts},
        "highs": {o.name: box_of(o) for o, _g in a._high_parts},
        "said": sorted(a._repeat_facts)}))
    raise SystemExit(0)

a = rbx.Asset("_selftest_repeat_cases", size=(12, 3, 12), ground=False)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("paint", color=(0.55, 0.2, 0.15), rough=0.6)
a.box("Slab", (10.0, 0.2, 10.0), (0, -0.2, 0), "iron")

with a.repeat(4, step=(1, 0, 0)):
    with a.frame(rot=(0, 90, 0)):
        a.box("Turned", (0.2, 0.2, 0.6), (0, 0.5, 0), "iron")
with a.repeat(4, around="Y", centre=(0, 0, 0)):
    with a.frame((2, 0, 0)):
        a.box("Orbit", (0.2, 0.2, 0.2), (0.5, 0.5, 0), "iron")
with a.frame((0, 0, 3), rot=(0, 90, 0)):
    with a.repeat(3, step=(1, 0, 0)):
        a.box("Inside", (0.2, 0.2, 0.2), (0, 0.5, 0), "iron")
with a.repeat(2, step=(4, 0, 0)):
    with a.repeat(4, around="Y", centre=(-4, 0, -3)):
        a.box("Wheel", (0.2, 0.2, 0.2), (-3, 0.5, -3), "iron")
V = [(3.0, 1.0, 3.0), (3.2, 1.0, 3.0), (3.2, 1.2, 3.0), (3.0, 1.2, 3.0),
     (3.0, 1.0, 3.2), (3.2, 1.0, 3.2), (3.2, 1.2, 3.2), (3.0, 1.2, 3.2)]
F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]
with a.repeat(6, step=(0, 0, 0.4), vary={"size": 0.4}):
    a.mesh("Lump", V, F, "iron")
with a.mirror("X"):
    with a.repeat(3, step=(0.5, 0, 0)):
        a.box("Rail", (0.2, 0.2, 0.2), (1, 0.5, 4.5), "iron")
with a.mirror("X"):
    with a.repeat(3, step=(0, 0, 0.5), vary={"turn": 30}):
        a.box("Tip", (0.4, 0.4, 0.2), (4, 0.5, -4.5), "iron")
# the half of the tip TOWARD the model's middle (x under 4), cut straight along x = 4 first
a.zone("Tip", "paint", lambda c, nrm: c[0] < 4.0 - 1e-6, split=[((4.0, 0, 0), (1, 0, 0))])
with a.repeat(3, step=(0.5, 0, 0)):
    cutter = a.box("Slot", (0.1, 0.4, 0.1), (-4, -0.2, 4), "paint")
a.cut("Slab", cutter)

zones = {}
for o, _g in a.parts:
    if o.name.split("~")[0] != "Tip":
        continue
    slot = next((i for i, m in enumerate(o.data.materials) if m == a._mat("paint")), None)
    hit = [p for p in o.data.polygons if p.material_index == slot] if slot is not None else []
    mids = [BACK @ (o.matrix_world @ p.center) for p in hit]
    whole = box_of(o)["mid"]
    zones[o.name] = {"faces": len(hit), "of": len(o.data.polygons),
                     # where the zoned faces lie from the copy's own middle, along x (the part: toward -x)
                     "side_x": round(sum(m.x for m in mids) / max(len(mids), 1) - whole[0], 4)}

errors = {}
try:
    with a.repeat(30, step=(1, 0, 0)):
        with a.repeat(20, step=(0, 1, 0)):
            pass
    errors["nested"] = None
except ValueError as e:
    errors["nested"] = str(e)
try:
    with a.repeat(3, step=(1, 0, 0)):
        a.stamp("rivets", at=(0, 0, 0), facing="+Y", size=(0.1, 0.1))
    errors["stamp"] = None
except ValueError as e:
    errors["stamp"] = str(e)
try:
    with a.repeat(3, step=(1, 0, 0), angle=90):
        pass
    errors["option"] = None
except ValueError as e:
    errors["option"] = str(e)
try:
    with a.mirror("X"), a.mirror("Z"), a.repeat(200, step=(0.01, 0, 0)):
        a.box("TooMany", (0.1, 0.1, 0.1), (0, 2, 0), "iron")
    errors["mirrors"] = None
except ValueError as e:
    errors["mirrors"] = str(e)

print("REPEAT_CASES " + json.dumps({
    "parts": {o.name: box_of(o) for o, _g in a.parts},
    "zones": zones,
    "zone_fact": next((z for z in a.design.get("zones", []) if z["part"] == "Tip"), None),
    "said": sorted(a._repeat_facts),
    "live": sorted(n for n in a._repeat_facts if n in a._copies),
    "errors": errors,
    "open_after": len(a._repeats),
}))
