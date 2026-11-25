"""check_two_sided_cases.py — fixture: a.two_sided on real parts. Nothing is built: parts are made and asked, one
line `TWO_SIDED {json}`, read by kit/test/python/test_two_sided.py.
  a bent sheet of six faces, mirrored: after a.two_sided both it and its copy are closed solids (no open edge, no
  edge three faces share, none wound against its neighbour), a hair thick
  (its front points where the script put them, its back exactly the thickness BEHIND them)
  a solid box: refused (it has no border); a thickness of a modelling size: refused; a band with a half turn (one
  side only) and a sheet folded tighter than the thickness (its back would cross itself): refused; nothing changed
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

a = rbx.Asset("_selftest_two_sided_cases", size=(6, 2, 3), ground=False)
a.material("leaf", color=(0.2, 0.5, 0.2), rough=0.6)


def state(name):
    """(open edges, edges three faces share, edges between faces wound apart, points, faces, volume)"""
    obj = next(o for o, _g in a.parts if o.name == name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    t = rbx.rbx_repair.faults(rbx.rbx_repair.edge_table(*rbx._bm_arrays(bm)[1:]))
    out = [t["open"], t["fins"], t["flipped"], len(bm.verts), len(bm.faces), round(bm.calc_volume(signed=True), 6)]
    bm.free()
    return out


def refused(name, **opts):
    before = state(name)
    try:
        a.two_sided(name, **opts)
        said = "accepted"
    except ValueError as e:
        said = str(e)
    return {"said": said, "unchanged": state(name) == before}


verts = [(x * 0.3 + 1.0, 0.1 * math.sin(x), z * 0.3) for z in range(3) for x in range(4)]
faces = [(z * 4 + x, z * 4 + x + 1, (z + 1) * 4 + x + 1, (z + 1) * 4 + x) for z in range(2) for x in range(3)]
with a.mirror("X"):
    a.mesh("Leaf", verts, faces, "leaf")
before = state("Leaf")
thick = refused("Leaf", thickness=0.5)
leaf = next(o for o, _g in a.parts if o.name == "Leaf")
front = [tuple(round(c, 6) for c in v.co) for v in leaf.data.vertices]              # the sheet as it was made
normals = [tuple(v.normal) for v in leaf.data.vertices]
area = sum(p.area for p in leaf.data.polygons)
a.two_sided("Leaf", "Leaf")                                                          # (said twice: one part)
now = [tuple(round(c, 6) for c in v.co) for v in leaf.data.vertices]
front_kept = all(p in now for p in front)                                            # the front did not move
# the back: every new point lies `thickness` from a front point, BEHIND it (against the front's own normal)
behind = []
for p in now:
    if p in front:
        continue
    k = min(range(len(front)), key=lambda i: sum((p[j] - front[i][j]) ** 2 for j in range(3)))
    behind.append(round(sum((p[j] - front[k][j]) * normals[k][j] for j in range(3)), 4))

# ---- a band with a half turn in it has one side; a sheet folded tighter than the thickness would cross itself
band, band_f = [], []
for i in range(24):
    t_ = 2 * math.pi * i / 24
    for s_ in (-0.15, 0.15):
        band.append((-3 + (0.8 + s_ * math.cos(t_ / 2)) * math.cos(t_), 0.5 + s_ * math.sin(t_ / 2),
                     (0.8 + s_ * math.cos(t_ / 2)) * math.sin(t_)))
for i in range(23):
    band_f.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
band_f.append((46, 47, 0, 1))                                                        # joined with the half turn
a.mesh("Band", band, band_f, "leaf")
one_side = refused("Band")
fold = [(4 + 0.004 * math.cos(math.pi * i / 8), 0.004 * math.sin(math.pi * i / 8), z) for z in (0.0, 0.4)
        for i in range(9)]
a.mesh("Fold", fold, [(i, i + 1, 9 + i + 1, 9 + i) for i in range(8)], "leaf")
crossing = refused("Fold")
after = [state(o.name) for o, _g in a.parts if o.name.split("~")[0] == "Leaf"]
a.box("Block", (0.4, 0.4, 0.4), (-2, 0.2, 0), "leaf", bevel=0)
solid = refused("Block")

print("TWO_SIDED " + json.dumps({"before": before, "after": after, "solid": solid, "thick": thick,
                                 "facts": a.design.get("two_sided"), "front_kept": front_kept,
                                 "behind": sorted(set(behind)), "area": round(area, 5), "one_side": one_side,
                                 "crossing": crossing}))
