"""build_cad_ok.py — POSITIVE fixture: hard-surface parts made in code CAD (a.cad, build123d on OpenCASCADE), at
1 stud = 280 mm. A receiver block (100 x 60 x 240 mm, its four long edges filleted r 6, a 20 mm bore through it
front to back, the bore's front mouth chamfered 2 mm), a barrel revolved from its profile (a 700 mm tube, 18 mm outer
radius, 5 mm wall, a flared muzzle at the front) from a code file written at run time with its sizes as params, and
a grip on each side (`with a.mirror()`). Must NOT be named: cad_solid, manifold, wire_edges, loose_verts,
degenerate_faces, inside_out, floating_parts. The receiver's volume must equal the one worked out by hand (the
fixture checks that itself and stops with an error if not). Used by `lune run kit selftest`.
"""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
barrel_py = os.path.join(out, "_cad_barrel.py")
with open(barrel_py, "w", encoding="utf-8") as fh:
    # the profile on Plane.YZ — its first coordinate is y (the radius), its second z (along the barrel: 0 = the
    # muzzle, the front) — revolved about the z axis
    fh.write("r, w, L = P['r'], P['wall'], P['L']\n"
             "with BuildPart() as part:\n"
             "    with BuildSketch(Plane.YZ):\n"
             "        Polygon((r - w, 0), (r + 6, 0), (r + 6, 20), (r, 60), (r, L), (r - w, L), align=None)\n"
             "    revolve(axis=Axis.Z)\n")

MM = 280.0
a = rbx.Asset("_selftest_cad_ok", tex=64, size=(0.36, 0.63, 3.36), ground=False)
a.real_scale(MM)
a.material("steel", (0.56, 0.57, 0.58), metal=1.0, rough=0.35)
a.material("polymer", (0.08, 0.08, 0.09), rough=0.6)
a.cad("Receiver", """
    with BuildPart() as part:
        Box(100, 60, 240)
        fillet(part.edges().filter_by(Axis.Z), 6)
        with Locations((0, 0, 120)):             # the back face; a Hole cuts down from it, right through
            Hole(10)
        mouth = [e for e in part.edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[0] if abs(e.radius - 10) < 1e-6]
        chamfer(mouth, 2)                        # the bore's front mouth (not the fillets' quarter-circle ends)
    """, "steel")
a.cad("Barrel", barrel_py, "steel", pos=(0, 0, -(120 + 700) / MM), params={"r": 18, "wall": 5, "L": 700})
with a.mirror("X"):
    a.cad("Grip", """
        part = Box(30, 120, 50)
        part = fillet(part.edges(), 4)
        """, "polymer", pos=(35 / MM, -85 / MM, 40 / MM))

# the receiver as built: the box, minus the waste of its four 240 mm fillets, minus the bore, minus the chamfer ring
# (its c x c / 2 triangle swept round the bore at r + c/3)
r_f, r_b, c = 6.0, 10.0, 2.0
want = (100 * 60 * 240 - 4 * (r_f ** 2 - math.pi * r_f ** 2 / 4) * 240 - math.pi * r_b ** 2 * 240
        - math.pi * c * c * (r_b + c / 3))
rec = next(c_ for c_ in a.design["cad"] if c_["part"] == "Receiver")
if abs(rec["volume_mm3"] - want) > 0.05:
    raise SystemExit(f"cad_ok: the receiver measured {rec['volume_mm3']} mm3, by hand {want:.3f}")
a.build()
