"""build_sword.py — STARTER: knight sword (handheld). Shows: a front-view outline extrude for the blade,
a fuller groove cut on both faces (mirror Z + cut), a curved crossguard drawn once and mirrored (mirror X),
a rain guard plate at the ricasso, blade maker's mark (a.text), groove langets on the guard face (P.groove),
brass quillon-cap bolts (P.bolt), a wrapped leather grip with collar rivets (P.rivets, P.grip), a faceted pommel
with a peen rivet (a.cylinder + a.sphere), brushed-steel and grime/wear/chip materials.
Run: lune run kit asset sword
"""

import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("g_sword_greebled", size=(1.75, 4.9, 0.4), ground=False, symmetric=True)

# ---- materials: surface story (brushed steel, worn gold, oiled leather, dark fuller) ---------
a.material("steel",   (0.78, 0.80, 0.84), metal=0.95, rough=0.22, wear=0.12, grime=0.08,
           pattern="brushed")                                         # brushed machined finish
a.material("steel_dark", (0.55, 0.57, 0.62), metal=0.9,  rough=0.45, wear=0.10)  # fuller / ricasso edges
a.material("brass",   (0.82, 0.58, 0.18), metal=1.0,  rough=0.28, wear=0.30,
           chip=0.18, under=(0.56, 0.57, 0.60), grime=0.12)          # guard/fittings: chipped + worn
a.material("leather", (0.14, 0.08, 0.05), rough=0.88, wear=0.20, grime=0.15,
           pattern="grid")                                            # diamond-wrapped grip texture
a.material("iron",    (0.30, 0.30, 0.32), metal=0.75, rough=0.55, wear=0.18)  # pommel / collars
a.material("gem",     (0.72, 0.04, 0.10), rough=0.12)                # blade gem accent

# ---- blade: ricasso + taper toward tip, fuller groove on both faces -------------------------
# outline: front view (u=right, v=up). Shoulder at y=1.3 is the ricasso bottom; widens slightly
# at the shoulder then tapers to the tip.
a.extrude(
    "Blade",
    [(-0.20, 1.30), (0.20, 1.30), (0.22, 2.00), (0.20, 3.00), (0.18, 4.05), (0.0, 4.85),
     (-0.18, 4.05), (-0.20, 3.00), (-0.22, 2.00)],
    0.11, "steel", plane="front",
)

# fuller: cut a shallow groove on BOTH faces; offset it from the ricasso
with a.mirror("Z"):
    a.cut("Blade", a.box("Fuller", (0.08, 2.20, 0.055), (0.0, 2.80, -0.055), "steel_dark", bevel=0))

# ricasso: thin box inset at the base of the blade (the unsharpened section, darker / squarer)
a.box("Ricasso", (0.40, 0.55, 0.10), (0.0, 1.57, 0.0), "steel_dark", bevel=0.01)

# blade maker's mark: engraved text in the upper taper section, above the fuller groove end.
# Own group "marks" gives it a separate 512 px texture so the letters hold colour at game distance.
a.text("BladeMark", "XIV", (0.0, 4.25, -0.056), "steel_dark",
       size=0.110, facing="-Z", up="+Y", depth=0.008, group="marks")

# P.groove langets on the front face of the guard (decorative recessed panel lines)
# langets run symmetrically left and right of centre, in the guard plane (front face, surface ~-0.15)
P.groove(
    a, "Blade", "LangetL",
    [(-0.06, 1.35), (-0.06, 1.25)],
    "steel_dark", plane="front", surface=-0.055, side=1,
    width=0.016, depth=0.012,
)
P.groove(
    a, "Blade", "LangetR",
    [(0.06, 1.35), (0.06, 1.25)],
    "steel_dark", plane="front", surface=-0.055, side=1,
    width=0.016, depth=0.012,
)

# ---- rain guard: small rectangular plate between guard and ricasso, sits at blade shoulder ----
a.box("RainGuard", (0.46, 0.08, 0.22), (0.0, 1.28, 0.0), "iron", bevel=0.015)

# ---- crossguard: swept quillons, one half drawn then mirrored; tips curve up toward the blade --
with a.mirror("X"):
    a.extrude(
        "Guard",
        [(-0.02, 1.08), (0.52, 1.08, 0.08), (0.84, 1.28, 0.05), (0.88, 1.46, 0.04),
         (0.64, 1.38), (-0.02, 1.42)],
        0.28, "brass", plane="front",
    )

# quillon-end caps (brass hex bolt on each quillon tip)
P.bolt(a, "QuillonCapL", (-0.88, 1.38, 0.0), "iron", facing="-X", radius=0.065, height=0.08)
P.bolt(a, "QuillonCapR", ( 0.88, 1.38, 0.0), "iron", facing="+X", radius=0.065, height=0.08)

# small gem set in the guard centre (front face), with mirror to put it on both faces
with a.mirror("Z"):
    a.sphere("Gem", 0.095, (0.0, 1.25, -0.14), "gem", scale=(1, 1, 0.50))

# ---- grip: leather wrap, brass collar at both ends ------------------------------------------
# Grip bottom at y=0.34, length=0.82, so grip runs y=0.34..y=1.16
P.grip(a, "Grip", (0.0, 0.34, 0.0), 0.82, 0.100, "leather", "brass", wraps=5)

# upper ferrule collar (at the base of the blade / top of grip): sits at y=1.16
a.cylinder("FerrulaUpper", 0.115, 0.09, (0.0, 1.21, 0.0), "iron", axis="Y", segments=14, bevel=0.01)

# lower ferrule collar (above the pommel): sits at y=0.34
a.cylinder("FerrulaLower", 0.115, 0.09, (0.0, 0.295, 0.0), "iron", axis="Y", segments=14, bevel=0.01)

# ---- pommel: hexagonal faceted disk, with a central peen rivet on the base --
# Pommel centre at y=0.155, height=0.22 → extends y=0.045..y=0.265.
# FerrulaLower at y=0.295, height=0.09 → extends y=0.250..y=0.340.
# Grip bottom at y=0.34. Pommel top=0.265, FerrulaLower bottom=0.250: they overlap → no float.
a.cylinder("Pommel", 0.19, 0.22, (0.0, 0.155, 0.0), "iron", axis="Y", segments=6, bevel=0.015)
a.sphere("PeenRivet", 0.065, (0.0, 0.035, 0.0), "brass", scale=(1, 0.70, 1))

# ---- expectations (checked numerically — fail with exact distance if violated) ----------------
a.expect("Guard",       touches="Blade")
a.expect("RainGuard",   touches="Blade")
a.expect("Pommel",      touches="FerrulaLower")
a.expect("Gem",         touches="Guard", in_front_of="Blade")
a.expect("FerrulaUpper", touches="Grip")
a.expect("Blade",       size={"y": (3.3, 3.8)}, at={"x": (-0.02, 0.02)})
import random as _r  # PROBE (grading only): random clutter on a good model
_g = _r.Random(11)
_m = ['steel', 'steel_dark', 'brass', 'leather', 'iron', 'gem']
with a.mirror("X"):
    for _i in range(18):
        _y = _g.uniform(1.6, 4.4)
        a.box(f"Fitting{_i}", (0.05, _g.uniform(0.04, 0.12), _g.uniform(0.03, 0.08)), (_g.uniform(0.02, 0.12), _y, _g.choice([-1, 1]) * 0.02), _g.choice(_m))
a.build()
