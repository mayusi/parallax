"""build_tree_stump.py — tree_stump: the kit's SCULPT example (a.sculpt). Run: lune run kit asset tree_stump

DESIGN FIRST:
  what it is / where it is used: a felled tree's stump with its roots gripping the ground — a forest prop, and the kit's
    example of sculpting in code (start a new organic prop from it: kit new asset x --from tree_stump)
  size: ~0.45 m trunk, roots spreading ~1.2 m, ~0.33 m tall (a real oak / beech stump of a 45 cm tree)
  silhouette: a squat trunk flaring into five roots that dive into the soil; a flat sawn top
  big shapes / medium / small details: trunk + flare / roots, buttresses / bark ridges up the trunk, lumps, growth
    rings and saw marks on the top
  palette: dark grey-brown bark, pale end grain on the cut, a darker heart

How it is SCULPTED (a.sculpt — clay in code, meshed by OpenVDB into one closed surface):
  1 masses: the trunk (a tapered capsule) + the root flare (an ellipsoid), blended 60 mm
  2 roots: five tapered strokes radiating from the flare down into the ground, each blended into it
  3 trim: everything above the saw cut and below the ground taken away (keep)
  4 surface: big lumps (fbm, 120 mm) everywhere, then bark ridges stretched UP the trunk (ridged, 14 x 90 mm)
     everywhere but the cut, a crease for the felling notch
  5 the cut face gets its own material (a.zone: faces pointing up at the top)
"""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

MM = 280.0                    # mm per stud (Roblox's 0.28 m)
TOP = 330.0                   # the saw cut, mm above the ground
a = rbx.Asset("tree_stump", tex=2048, size=(4.3, 1.2, 4.3), stage="master")   # (kit optimize: the game version)
a.real_scale(MM)

# LOOKS (kit/materials/looks.json — lune run kit materials --looks): bark, weathered (life heavy: dirt in its fissures,
# lumps of tone); the cut: end grain, its growth rings round the trunk's vertical axis (grain=), a fresh cut (light)
a.material("bark", **rbx.look("bark"), life="heavy")
a.material("endgrain", **rbx.look("end_grain", pattern_mm=6.0), grain=(0, 1, 0), life="light")   # (a fast-growing tree: rings that read at prop distance)

s = a.sculpt("Stump", "bark", voxel_mm=3.0)
G = rbx.sculpt_shapes
s.capsule((0, -60, 0), (0, TOP + 80, 0), 235, 215)                 # the trunk, a little narrower up top
s.ellipsoid((0, 40, 0), (330, 130, 315), blend=70)                # the flare where it meets the roots
for i, ang in enumerate((8, 80, 150, 222, 290)):                  # five roots, uneven like a real stump's
    t = math.radians(ang)
    reach = 560 + 70 * ((i * 37) % 3)                             # (some longer than others)
    out = [(r * math.cos(t), y, r * math.sin(t)) for r, y in ((160, 150), (330, 70), (reach * 0.8, 10), (reach, -60))]
    s.stroke(out, [105, 72, 42, 22], blend=45)
s.noise(10.0, 120.0, kind="fbm", seed=3)                           # the trunk's lumps and swellings, THEN
s.keep(G.Box((0, (TOP + 0) / 2, 0), (1800, TOP, 1800)), blend=6)  # sawn flat on top, cut off at the ground
below_cut = G.Box((0, (TOP - 40) / 2, 0), (1800, TOP - 40, 1800))
s.noise(5.0, (14.0, 90.0, 14.0), kind="ridged", seed=5, where=below_cut, falloff=25)   # bark ridges up the trunk
s.crease([(-240, 260, -40), (-250, 250, 60)], 14.0)                # the felling notch's lip
s.done(adaptivity=0.1)

# the cut: every face looking up at the top is end grain
a.zone("Stump", "endgrain", lambda c, n: n[1] > 0.85 and c[1] * MM > TOP - 12)

# SMALL DETAIL a real stump carries — each seated INTO the stump (nothing floats): bracket fungi on the bark (sculpted),
# wood chips from the felling against the flare, pebbles between the roots (sculpted), a sapling sprouting at the base
a.material("fungus", color=(0.42, 0.3, 0.17), rough=0.85, vary=0.45, life="light")
a.material("chipwood", **rbx.look("oak_wood"), life="light")
a.material("pebble", **rbx.look("rock"), life="used")
a.material("leaf", color=(0.07, 0.15, 0.03), rough=0.55, vary=0.35)


def ring(r_mm, ang_deg, y_mm):
    """a point r mm out from the trunk's axis at an angle, y mm up -> studs"""
    t = math.radians(ang_deg)
    return (r_mm * math.cos(t) / MM, y_mm / MM, r_mm * math.sin(t) / MM)


for i, (ang, y, w) in enumerate(((115, 210, 1.0), (128, 170, 0.8), (300, 240, 0.7))):   # shelf fungi, in tiers
    f = a.sculpt(f"Fungus{i + 1}", "fungus", voxel_mm=1.0, pos=ring(215, ang, y), rot=(0, -ang, 0))
    f.ellipsoid((22 * w, 0, 0), (40 * w, 9 * w, 34 * w))                  # a half-disc shelf, its back in the bark
    f.ellipsoid((14 * w, -4 * w, 0), (26 * w, 6 * w, 24 * w), blend=4)    # the thicker lip under it
    f.noise(1.0 * w, 7.0, kind="fbm", seed=i)
    f.crease([(50 * w, 9 * w * 0.6, -20 * w), (55 * w, 9 * w * 0.6, 0), (50 * w, 9 * w * 0.6, 20 * w)], 3.2)  # a growth ring
    f.done(adaptivity=0.2)
for i, (ang, y, yaw) in enumerate(((40, 18, 30), (60, 14, -20), (190, 16, 75), (250, 18, 10), (265, 12, -40))):
    a.box(f"Chip{i + 1}", (0.16, 0.025, 0.07), ring(325, ang, y), "chipwood", rot=(8, yaw, 14), bevel=0.004)
for i, (ang, r, size) in enumerate(((45, 318, 26), (115, 312, 20), (185, 318, 30), (330, 314, 22))):
    pb = a.sculpt(f"Pebble{i + 1}", "pebble", voxel_mm=1.0, pos=ring(r, ang, size * 0.35))
    pb.ellipsoid((0, 0, 0), (size, size * 0.6, size * 0.8), rot=(0, ang, 0))
    pb.noise(size * 0.08, size * 0.6, kind="cells", seed=i)
    pb.done(adaptivity=0.3)
base = ring(300, 330, 40)
tip = (base[0] + 0.05, base[1] + 0.42, base[2] - 0.04)
a.tube("Sprout", [base, (base[0] + 0.02, base[1] + 0.2, base[2] - 0.02), tip], 0.012, "leaf", segments=12)
for i, (frac, yaw) in enumerate(((1.0, 20), (0.8, 200), (0.62, 110))):   # leaves set ON the stem, pointing out
    q = [base[k] + (tip[k] - base[k]) * frac for k in range(3)]
    t = math.radians(yaw)
    a.sphere(f"Leaf{i + 1}", 0.06, (q[0] + 0.045 * math.cos(t), q[1], q[2] - 0.045 * math.sin(t)), "leaf",
             scale=(1.0, 0.12, 0.55), rot=(10, yaw, 15), segments=12, rings=6)
a.build()
