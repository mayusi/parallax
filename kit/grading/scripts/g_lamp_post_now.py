"""build_lamp_post.py — STARTER: street lamp (10 studs). Shows: a stepped octagonal stone base with cast-iron
collar; a.cylinder with segments=8/12/6 for octa/dodeca/hex cross-sections; P.bolts for 4 ground anchors and
door bolts; an access door (a.box) with P.latch centred on it; brass accent rings (a separate material) at
three collar heights to break up the pole; P.panel_line casting-seam cuts on ±Z pole faces; a flat maker's
plaque (a.box overlapping into the pole + a.text on its front face, both group="marks") so the lettering gets
its own texture and enough texels; P.screws on the hex lantern plate; six iron frame bars enclosing the hex
glass group (group="glass"); a cone roof and sphere finial. Material story: chip= + under= paint chipping,
grime= dirt in crevices, wear= scuff patches, pattern="brushed" micro-relief on iron.
Run: lune run kit asset lamp_post
"""

import math
import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("g_lamp_post_now", size=(1.4, 10.5, 1.4), symmetric=True)

# ── Materials ────────────────────────────────────────────────────────────────
# Cast iron base: rough stone-grey, chips reveal lighter under, grime in crevices
a.material("stone", (0.32, 0.32, 0.34), metal=0.0, rough=0.92, wear=0.55,
           chip=0.28, under=(0.55, 0.54, 0.52), grime=0.35)
# Cast iron pole/fittings: dark gunmetal, chipped paint edges, low grime
a.material("iron", (0.11, 0.12, 0.13), metal=0.82, rough=0.42, wear=0.35,
           chip=0.38, under=(0.52, 0.52, 0.55), grime=0.28, pattern="brushed")
# Aged brass accent for rings and collar bands
a.material("brass", (0.62, 0.50, 0.22), metal=0.9, rough=0.38, wear=0.25,
           chip=0.18, under=(0.42, 0.35, 0.18), grime=0.22)
# Glass panes: warm-tinted glass, semi-transparent
a.material("glass", (1.0, 0.82, 0.48), rough=0.08, alpha=0.50)
# Maker's plate / text inlay — slightly lighter iron, worn lettering
a.material("decal", (0.70, 0.68, 0.64), metal=0.3, rough=0.65, wear=0.4,
           chip=0.12, grime=0.15)

# ── Base (stepped octagonal ground plate) ────────────────────────────────────
a.cylinder("Base",  0.70, 0.50, (0, 0.25, 0), "stone", segments=8)
a.cylinder("Step",  0.52, 0.30, (0, 0.65, 0), "stone", segments=8)
# Collar between base step and pole — top at y=1.12, overlaps pole bottom (1.10)
a.cylinder("Collar", 0.28, 0.22, (0, 0.91, 0), "iron", segments=12)

# Ground anchor bolts — 4 at cardinal points on the base top face
P.bolts(a, "AnchorBolt", [
    ( 0.48,  0.50,  0.00),
    (-0.48,  0.50,  0.00),
    ( 0.00,  0.50,  0.48),
    ( 0.00,  0.50, -0.48),
], "iron", facing="+Y", radius=0.055, height=0.055)

# Access door — a raised panel plate on the front of the base step
# (maintenance access for wiring). Overlaps slightly into the step, sits proud on the outside.
# Step octa-front face apothem = 0.52 * cos(22.5°) ≈ 0.480 → place door back at z=-0.47 (inside step), front at -0.50
a.box("AccessDoor", (0.40, 0.20, 0.06), (0.00, 0.65, -0.50), "iron", bevel=0.012)
# Latch centered on the access door (symmetric about X)
P.latch(a, "PanelLatch", (0.00, 0.65, -0.535), "brass", facing="-Z", size=(0.09, 0.15))
# Two small bolts holding the door plate (symmetric ±X)
P.bolts(a, "DoorBolt", [
    ( 0.16, 0.65, -0.534),
    (-0.16, 0.65, -0.534),
], "iron", facing="-Z", radius=0.038, height=0.035)

# ── Pole ─────────────────────────────────────────────────────────────────────
# Pole: bottom y=0.97 (overlaps Collar top 1.02), top y=9.03 (overlaps LanternPlate bottom 8.95)
# center = (0.97+9.03)/2=5.00, height=9.03-0.97=8.06
a.cylinder("Pole", 0.145, 8.06, (0, 5.00, 0), "iron", segments=12)

# Decorative rings — brass accent collars at three heights
# Ring1 at y=1.12: bottom=1.055, top=1.185 — overlaps Pole (0.97–8.87) at full height
for i, y in enumerate((1.12, 1.75, 8.05)):
    a.cylinder(f"Ring{i + 1}", 0.24, 0.13, (0, y, 0), "brass", segments=12)

# Casting seam on the rear (±Z) sides of the pole — front face left clear for the maker's plaque
P.panel_line(a, "Pole", "SeamBack",
    (0.00,  1.20,  0.147), (0.00,  8.95,  0.147),
    "iron", width=0.028, depth=0.018, facing="+Z")
P.panel_line(a, "Pole", "SeamSide",
    (-0.147, 1.20,  0.00), (-0.147, 8.95,  0.00),
    "iron", width=0.028, depth=0.018, facing="-X")

# Maker's plate — a small cast-iron plaque on the front (−Z) face of the pole,
# centred at x=0 so it is symmetric. Pole 12-sided apothem on −Z face = 0.140.
# Back of plate at z=−0.130 (inside the pole), front at z=−0.163 (0.033 thick).
# Both plate and text go in group="marks" → own 1024px texture → enough texels.
a.box("PlaquePlate", (0.28, 0.11, 0.033), (0.00, 1.44, -0.1465),
      "decal", bevel=0.007, group="marks")
a.text("MakerPlate", "R.E.Co.", (0.00, 1.44, -0.163), "decal",
       size=0.075, facing="-Z", up="+Y", depth=0.006, group="marks")

# ── Lantern ──────────────────────────────────────────────────────────────────
# Bottom plate (hex)
lplate = a.cylinder("LanternPlate", 0.56, 0.10, (0, 9.00, 0), "iron", segments=6)

# Four screws around the lantern base plate
P.screws(a, "PlateScrew", [
    ( 0.42,  9.04,  0.00),
    (-0.42,  9.04,  0.00),
    ( 0.00,  9.04,  0.42),
    ( 0.00,  9.04, -0.42),
], "iron", facing="+Y", radius=0.045)

# Glass cylinder (separate group for FBX export)
a.cylinder("Glass", 0.43, 1.05, (0, 9.58, 0), "glass", segments=6, group="glass")

# Six vertical frame bars around the glass (structural lantern cage)
# Bars: bottom at y=8.97 (inside LanternPlate 8.95–9.05), top at y=10.10 (inside LanternRing 10.07–10.17)
# bar center y=9.535, height=1.13
for k in range(6):
    ang = math.radians(60 * k)
    a.cylinder(f"Bar{k + 1}", 0.042, 1.13,
               (math.cos(ang) * 0.475, 9.535, math.sin(ang) * 0.475),
               "iron", segments=6, bevel=0)

# Upper ring where bars meet the roof plate
a.cylinder("LanternRing", 0.54, 0.10, (0, 10.12, 0), "iron", segments=6)

# Cone roof (hex)
a.cylinder("Roof", 0.60, 0.46, (0, 10.40, 0), "iron", segments=6, radius_top=0.075)

# Finial — sphere cap
a.sphere("Finial", 0.10, (0, 10.67, 0), "iron")

# ── Build ─────────────────────────────────────────────────────────────────────
a.build()
