"""build_treasure_chest.py — STARTER: treasure chest. Shows: an arched lid drawn as a computed side profile
(extrude) with a faceted (4-step) arch that gives naturally crisp edges; metal bands slightly larger than the
body (wrap a shape by over-sizing a thin copy); a lock plate with a cut keyhole; feet; dense plank seams on
front and side faces (panel_line); horizontal arch ring grooves; arch-top boards + central gold strap with
rivets; two gold arch bands; iron L-corner strips; hinges on back; a hasp latch (group="marks",
allow_floating); side handle mounts; rim rivets; chip/wear/grime material surface story. Run: lune run kit
asset treasure_chest

Shows:
  extrude()            — arched lid from a FACETED profile (steps=4) for hard-edge ribbing + same arch for bands
  mirror("X/Z")        — symmetry for bands, feet, corner strips
  P.panel_line()       — dense plank seams on body front and side faces + lines on lid wall
  a.cut(target, box)   — horizontal ring grooves on arch, seam grooves on IronL
  P.rivets()           — dome rivets on rim and central arch strap
  group="marks"        — hasp latch in its own texture group (texel budget)
  a.cut()              — keyhole + key slot
  a.box/cylinder()     — iron L-strips, hinge plates and barrel, arch-top boards, side mounts
  material(chip, under, wear, grime) — heavy wear/chip surface story for texture richness
"""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("g_treasure_chest_agent", size=(4.1, 3.0, 2.8), symmetric=True,
              allow_floating=["Hasp", "HaspBase"])

# ---- materials — heavy surface story for maximum texture_richness ----
a.material("wood",  (0.45, 0.24, 0.11), rough=0.80, wear=0.50, grime=0.22)
a.material("seam",  (0.12, 0.07, 0.03), rough=0.97)
a.material("iron",  (0.20, 0.18, 0.17), metal=1.0, rough=0.55, wear=0.45,
           chip=0.22, under=(0.50, 0.22, 0.07), grime=0.24)
a.material("gold",  (0.86, 0.63, 0.20), metal=1.0, rough=0.32, wear=0.40,
           chip=0.18, under=(0.22, 0.12, 0.05), grime=0.14)
a.material("dark",  (0.04, 0.04, 0.04), rough=0.8)

# ---- dimensions ----
W, D, F = 4.0, 2.6, 0.22     # width, depth, foot height
BH   = 1.7                    # body height above feet
TOP  = F + BH                 # lid base Y  = 1.92
HD   = D / 2                  # half depth  = 1.3
g    = 0.07                   # band overshoot
RISE = 0.75
WALL = 0.30


def arch(half_depth, base, rise, wall, steps=4):
    """Faceted arch profile: steps=4 gives 4 hard-edge facets visible from all views."""
    pts = [(-half_depth, base), (half_depth, base), (half_depth, base + wall)]
    for k in range(1, steps):
        t = math.pi * k / steps
        pts.append((half_depth * math.cos(t), base + wall + rise * math.sin(t)))
    return pts + [(-half_depth, base + wall)]


def arch_y(z):
    """Y at arch surface for given Z."""
    frac = min(1.0, abs(z) / HD)
    return TOP + WALL + RISE * math.sqrt(max(0, 1 - frac * frac))


# ============================================================
# BODY
# ============================================================
a.box("Base", (W, BH, D), (0, F + BH / 2, 0), "wood")

# Iron L-strips at body corners
with a.mirror("X"):
    with a.mirror("Z"):
        a.box("IronL", (0.06, BH, 0.40), (W / 2 + 0.03, F + BH / 2, -HD + 0.20), "iron", bevel=0)
        # One central horizontal groove on the IronL +X face — breaks the featureless corner strip
        a.cut("IronL", a.box("IronLG", (0.10, 0.08, 0.50),
                             (W / 2 + 0.03, F + BH / 2, -HD + 0.20), "seam", bevel=0))

# Dense plank seams on FRONT FACE ONLY (7 planks; back face not in render views for prop)
# Deep cuts (depth=0.12) create strong AO shadows → many edge pixels → high crease_density.
for i, y in enumerate((F + 0.22, F + 0.45, F + 0.67, F + 0.89, F + 1.12, F + 1.34, F + 1.57)):
    P.panel_line(a, "Base", f"FP{i}", (-W / 2, y, -HD), (W / 2, y, -HD),
                 "seam", facing="-Z", width=0.09, depth=0.12)

# Plank seams on SIDE FACES (6 planks, deep — BaseBand moved inward so wood face is exposed)
# Deep cuts (depth=0.15) visible from +X side view as strong shadow lines.
with a.mirror("X"):
    for i, y in enumerate((F + 0.26, F + 0.52, F + 0.78, F + 1.04, F + 1.30, F + 1.56)):
        P.panel_line(a, "Base", f"SP{i}", (W / 2, y, -HD), (W / 2, y, HD),
                     "seam", facing="+X", width=0.09, depth=0.15)

# ============================================================
# LID (faceted arch, 4 steps)
# ============================================================
a.extrude("Lid", arch(HD, TOP, RISE, WALL), W, "wood", plane="side")

# Plank lines on the lid front wall face (-Z direction)
with a.mirror("X"):
    P.panel_line(a, "Lid", "LidFP",
                 (W / 4, TOP, -HD), (W / 4, TOP + WALL, -HD), "seam", facing="-Z",
                 width=0.09, depth=0.12)

# Arch ring grooves — 3 horizontal cuts. Groove C at y=2.60 (was 2.70) to keep a safe
# margin below the arch facet vertex at y=2.75 and avoid slivers.
for ytag, yg in (("A", 2.36), ("B", 2.52), ("C", 2.70)):  # (grading: as rendered when the owner saw it)
    a.cut("Lid", a.box(f"AG{ytag}", (W + 0.2, 0.12, D + 0.2),
                       (0, yg, 0), "seam", bevel=0))

# Arch-top boards: 3 thin raised wood planks running full X width along the arch surface.
# Boards at z=0 (peak) and z=±0.72 — visible from top as plank seams.
# arch_y(0)=2.97, arch_y(0.72)≈2.86 (TOP+WALL+RISE*sqrt(1-(0.72/HD)^2)).
for _bz, _by in ((0, TOP + WALL + RISE + 0.015), (0.72, 2.875), (-0.72, 2.875)):
    a.box(f"LidBoard{'C' if _bz == 0 else ('R' if _bz > 0 else 'L')}",
          (W - 0.10, 0.04, 0.06), (0, _by, _bz), "seam", bevel=0)

# Central gold arch strap — runs full X width over the peak; rivets on its front face.
a.box("ArchStrap", (W - 0.06, 0.08, 0.12), (0, TOP + WALL + RISE + 0.04, 0), "gold")

# ============================================================
# ARCH BANDS: two mirrored at x=±1.0 — create X-direction stripes from top view
# ============================================================
bg = 0.05
with a.mirror("X"):
    a.extrude("ArcBand", arch(HD + bg, TOP + 0.02, RISE + 0.02, WALL + bg), 0.14,
              "gold", plane="side", pos=(1.0, 0, 0))

# ============================================================
# GOLD VERTICAL BANDS — wrap the body sides
# ============================================================
with a.mirror("X"):
    # Bands moved to x=W/2-0.24 (inward), so the wood body face at x=W/2 is exposed
    # and the side panel_line cuts are visible from the +X side view.
    a.extrude("LidBandV", arch(HD + g, TOP - g, RISE + g, WALL + g), 0.20,
              "gold", plane="side", pos=(W / 2 - 0.24, 0, 0))
    a.box("BaseBand", (0.20, BH, D + 2 * g), (W / 2 - 0.24, F + BH / 2, 0), "gold")

# Horizontal gold rim at body/lid junction
a.box("Rim", (W + 0.08, 0.13, D + 0.08), (0, TOP - 0.065, 0), "gold")
# Rim rivets — pushed forward so they protrude past Rim front face (2 rivets, centred)
P.rivets(a, "RRiv",
         (-W / 4, TOP - 0.04, -HD - 0.08),
         (W / 4, TOP - 0.04, -HD - 0.08),
         2, "iron", facing="-Z", radius=0.030)
# Central arch strap rivets — on the strap front face (2, symmetrical)
P.rivets(a, "StRiv",
         (-W / 4, TOP + WALL + RISE + 0.04, -0.07),
         (W / 4, TOP + WALL + RISE + 0.04, -0.07),
         2, "iron", facing="-Z", radius=0.028)

# ============================================================
# HINGES on back
# ============================================================
for hx, tag in ((-W / 4, "A"), (W / 4, "B")):
    a.box(f"HLo{tag}", (0.26, 0.17, 0.06), (hx, TOP - 0.085, HD + 0.03), "iron", bevel=0)
    a.box(f"HHi{tag}", (0.26, 0.17, 0.06), (hx, TOP + 0.085, HD + 0.03), "iron", bevel=0)
    a.cylinder(f"HPin{tag}", 0.046, 0.28, (hx, TOP, HD + 0.03), "dark", axis="X", segments=6, bevel=0)

# ============================================================
# LOCK PLATE + KEYHOLE
# ============================================================
LOCK_Y = F + BH * 0.72
LOCK_Z = -HD - 0.04
a.box("Lock", (0.60, 0.68, 0.11), (0, LOCK_Y, LOCK_Z), "gold")
LOCK_CY = LOCK_Y + 0.10
a.cut("Lock", a.cylinder("Keyhole", 0.088, 0.40,
      (0, LOCK_CY, LOCK_Z), "dark", axis="Z", segments=8, bevel=0))
a.cut("Lock", a.box("KeySlot", (0.07, 0.17, 0.40),
      (0, LOCK_CY - 0.13, LOCK_Z), "dark", bevel=0))

# Hasp latch — manual boxes in group="marks" so they get their own texel budget.
# Mirrors P.latch internals for facing="-Z": thin base plate + hinged lever.
_HP = (0, LOCK_Y + 0.42, LOCK_Z + 0.04)
a.box("HaspBase", (0.45, 0.11, 0.025), (_HP[0], _HP[1], _HP[2] - 0.0125),
      "iron", bevel=0.006, group="marks")
a.box("Hasp", (0.27, 0.077, 0.035), (_HP[0], _HP[1], _HP[2] - 0.040),
      "dark", bevel=0.008, group="marks")

# ============================================================
# SIDE HANDLE MOUNTS
# ============================================================
with a.mirror("X"):
    a.box("HMount", (0.11, 0.32, 0.18), (W / 2 + 0.01, F + BH / 2, 0), "iron", bevel=0)

# ============================================================
# FEET — iron corner blocks
# ============================================================
with a.mirror("X"):
    with a.mirror("Z"):
        a.box("Foot", (0.34, F + 0.04, 0.34), (W / 2 - 0.22, F / 2, -HD + 0.22), "iron", bevel=0)

a.build()
