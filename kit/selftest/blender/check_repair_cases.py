"""check_repair_cases.py — fixture: a part that is not closed, REPAIRED (a.repair, rbx_repair) and a map CHECKED
(rbx.Asset._uv_check, rbx_uvcheck). Nothing is built: parts are made and asked, one line `REPAIR_CASES {json}`,
read by kit/test/python/test_repair.py and test_uvcheck.py.
  a bin (a box with no top): one flat hole, capped - a closed solid again
  a shell of six faces that share no point: its seams welded - closed, eight points left
  a tube with no ends, mirrored: both ends capped, on the copy too
  one flat sheet; a tube with three wall panels torn out; the bin with cap=False: REFUSED, said what is open, the
  part as it was
  a closed box: nothing to do, nothing said; a weld of a modelling distance: refused
  a thick pipe's open end (a ring): filled as ONE face with its hole; three cards on one spine: not welded into
  an edge of three faces; two holes that share a point: two holes, both capped
  two faces given one piece of the map: found; a copy the unwrap's own record names: not; two faces on the very
  same place with no such record: found; a face given a long thin piece of the map: stretched
Never "fix" this file."""

import json
import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bmesh  # noqa: E402
import rbx  # noqa: E402

CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def at(points, dx, s=0.6):
    return [(x * s + dx, y * s, z * s) for x, y, z in points]


def tube(n=16, r=0.3, h=0.8, dx=0.0):
    ring = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    verts = [(x + dx, 0.0, z) for x, z in ring] + [(x + dx, h, z) for x, z in ring]
    return verts, [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]


def state(a, name):
    """(open edges, faces of no area, points, faces) of a part"""
    obj = next(o for o, _g in a.parts if o.name == name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    out = (*rbx._mesh_faults(bm), len(bm.verts), len(bm.faces))
    bm.free()
    return out


def refused(a, name, **opts):
    before = state(a, name)
    try:
        a.repair(name, **opts)
        said = "accepted"
    except ValueError as e:
        said = str(e)
    return {"said": said, "unchanged": state(a, name) == before, "open": before[0]}


a = rbx.Asset("_selftest_repair_cases", size=(8, 2, 3), ground=False, require_manifold=False)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)

# ---- a bin: no top
a.mesh("Bin", at(CUBE, -3.0), FACES[:1] + FACES[2:], "iron")
bin_before = state(a, "Bin")
a.repair("Bin")
bin_after = state(a, "Bin")

# ---- six faces that share no point
verts, faces = [], []
for f in FACES:
    faces.append(tuple(range(len(verts), len(verts) + 4)))
    verts += [at(CUBE, -2.0)[v] for v in f]
a.mesh("Shell", verts, faces, "iron")
shell_before = state(a, "Shell")
a.repair("Shell")
shell_after = state(a, "Shell")

# ---- a tube with no ends, and its mirror copy
with a.mirror("X"):
    a.mesh("Pipe", *tube(dx=1.2), "iron")
pipe_before = state(a, "Pipe")
a.repair("Pipe")
pipe_after = [state(a, o.name) for o, _g in a.parts if o.name.split("~")[0] == "Pipe"]

# ---- a thick pipe with its top ring of faces missing: ONE opening with a hole in it, not two discs
def thick(n=16, ro=0.3, ri=0.2, h=0.8, dx=0.0):
    ring = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
    v = [(ro * x + dx, 0.0, ro * z) for x, z in ring] + [(ro * x + dx, h, ro * z) for x, z in ring] \
        + [(ri * x + dx, 0.0, ri * z) for x, z in ring] + [(ri * x + dx, h, ri * z) for x, z in ring]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f += [(i, j, n + j, n + i), (2 * n + j, 2 * n + i, 3 * n + i, 3 * n + j), (j, i, 2 * n + i, 2 * n + j)]
    return v, f                                                             # outer wall, bore, bottom ring: no top


def volume_of(a_, name):
    obj = next(o for o, _g in a_.parts if o.name == name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    out = abs(bm.calc_volume())
    lying = rbx.rbx_poly.doubled(bm)
    bm.free()
    return lying, out


a.mesh("Ring", *thick(dx=-4.2), "iron")
ring_before = state(a, "Ring")
a.repair("Ring")
ring = [ring_before, state(a, "Ring"), *volume_of(a, "Ring")]

# ---- three cards on one spine, each with its own points: a weld would make the spine an edge of three faces
cards_v, cards_f = [], []
for ang in (0.0, 2.0944, 4.1888):
    k = len(cards_v)
    cards_v += [(-5.0, 0.0, 0.0), (-5.0, 0.6, 0.0), (-5.0 + 0.4 * math.cos(ang), 0.6, 0.4 * math.sin(ang)),
                (-5.0 + 0.4 * math.cos(ang), 0.0, 0.4 * math.sin(ang))]
    cards_f.append((k, k + 1, k + 2, k + 3))
a.mesh("Cards", cards_v, cards_f, "iron")
cards_obj = next(o for o, _g in a.parts if o.name == "Cards")
cards_bm = bmesh.new()
cards_bm.from_mesh(cards_obj.data)
t0 = rbx.rbx_repair.faults(rbx.rbx_repair.edge_table(*rbx._bm_arrays(cards_bm)[1:]))
cards_bm, cards_welded, _c, _f = rbx._repair_bm(cards_bm, 1e-5, False)
t1 = rbx.rbx_repair.faults(rbx.rbx_repair.edge_table(*rbx._bm_arrays(cards_bm)[1:]))
cards_bm.free()
cards = {"welded": cards_welded, "open": [t0["open"], t1["open"]], "fins": [t0["fins"], t1["fins"]]}

# ---- a box whose top is four squares, two of them (diagonal) missing: two holes that share one point
tw = [(x * 0.3 - 5.9, 0.0, z * 0.3) for z in range(3) for x in range(3)] \
    + [(x * 0.3 - 5.9, 0.4, z * 0.3) for z in range(3) for x in range(3)]
tw_f = [(0, 1, 4, 3), (1, 2, 5, 4), (3, 4, 7, 6), (4, 5, 8, 7)]                          # the bottom, whole
tw_f += [(9 + 1, 9 + 4, 9 + 5, 9 + 2), (9 + 3, 9 + 6, 9 + 7, 9 + 4)]                    # the top: two of four
edge = [0, 1, 2, 5, 8, 7, 6, 3]
tw_f += [(edge[i], edge[(i + 1) % 8], 9 + edge[(i + 1) % 8], 9 + edge[i]) for i in range(8)]   # the walls
a.mesh("Twin", tw, tw_f, "iron")
twin_before = state(a, "Twin")
try:
    a.repair("Twin")
except ValueError:
    pass
twin = [twin_before, state(a, "Twin")]

# ---- what no repair closes
a.mesh("Sheet", [(2.2, 0, 0), (3.0, 0, 0), (3.0, 0, 0.6), (2.2, 0, 0.6)], [(0, 1, 2, 3)], "iron")
sheet = refused(a, "Sheet")
tv, tf = tube(dx=3.8)
tv += [(3.8, 0.0, 0.0), (3.8, 0.8, 0.0)]
caps = [(i, 32, (i + 1) % 16) for i in range(16)] + [(16 + i, 16 + (i + 1) % 16, 33) for i in range(16)]
a.mesh("Torn", tv, [f for k, f in enumerate(tf) if k not in (0, 1, 2)] + caps, "iron")
torn = refused(a, "Torn")
a.mesh("Bin2", at(CUBE, 4.6), FACES[:1] + FACES[2:], "iron")
uncapped = refused(a, "Bin2", cap=False)
far = refused(a, "Bin2", weld=0.1)

# ---- nothing to do
a.box("Block", (0.5, 0.5, 0.5), (6.0, 0.25, 0), "iron", bevel=0)
block_before = state(a, "Block")
a.repair("Block")
block_after = state(a, "Block")
repaired = [{k: r[k] for k in ("part", "open_edges", "welded", "capped", "said")} for r in a.design.get("repaired") or []]

# ---- the map, checked: faces given their places by hand
u = rbx.Asset("_selftest_uv_cases", size=(8, 2, 3), ground=False, require_manifold=False)
u.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
QUAD = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]


def sq(x, y, w=0.2, h=0.2):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def checked(name):
    obj = next(o for o, _g in u.parts if o.name == name)
    facts, checks = u._uv_check(obj, 1024)
    return {"facts": facts, "checks": {c["name"]: (c["ok"], c["severity"]) for c in checks}}


two = [(x + dx, y, z) for dx in (0.0, 2.0) for x, y, z in QUAD]
u.mesh("Apart", two, [(0, 1, 2, 3), (4, 5, 6, 7)], "iron", uvs=[sq(0.1, 0.1), sq(0.5, 0.5)])
u.mesh("Crossed", [(x, y + 1, z) for x, y, z in two], [(0, 1, 2, 3), (4, 5, 6, 7)], "iron",
       uvs=[sq(0.1, 0.1), sq(0.2, 0.15)])
u.mesh("Stacked", [(x, y + 2, z) for x, y, z in two], [(0, 1, 2, 3), (4, 5, 6, 7)], "iron",
       uvs=[sq(0.1, 0.1), sq(0.1, 0.1)])
_st = next(o for o, _g in u.parts if o.name == "Stacked")                  # the unwrap's own record: face 1 is a
_st.data.attributes.new("kit_part", "INT", "FACE").data.foreach_set("value", [0, 1])   # copy laid on face 0
_st["kit_parts"], _st["kit_copies"] = ["Stacked", "Stacked~m1"], [1, 0]
u.mesh("Piled", [(x, y + 4, z) for x, y, z in two], [(0, 1, 2, 3), (4, 5, 6, 7)], "iron",
       uvs=[sq(0.1, 0.1), sq(0.1, 0.1)])                                   # the same place, and no record: an accident
u.mesh("Long", [(x * 4, y + 3, z) for x, y, z in QUAD], [(0, 1, 2, 3)], "iron", uvs=[sq(0.1, 0.1)])

print("REPAIR_CASES " + json.dumps({
    "bin": [bin_before, bin_after], "shell": [shell_before, shell_after], "pipe": [pipe_before, pipe_after],
    "sheet": sheet, "torn": torn, "uncapped": uncapped, "far": far, "block": [block_before, block_after],
    "repaired": repaired, "ring": ring, "cards": cards, "twin": twin,
    "uv": {n: checked(n) for n in ("Apart", "Crossed", "Stacked", "Piled", "Long")},
}))
