"""build_blaster.py — STARTER: sci-fi blaster (handheld, barrel = front -Z). Shows: a side-profile body and an
angled grip (extrude plane="side"), a trigger guard made by cutting one outline out of another, a barrel with a
cut bore, vents and glowing energy cells on both sides (mirror X), inset panels and raised plates on the body,
panel lines breaking featureless flanks, screws at panel corners, LEDs as status indicators, a connector port,
and a text serial in its own group — surface story with wear/chip/grime/under/emit materials.
Run: lune run kit asset blaster
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("g_blaster_agent", size=(0.75, 1.6, 3.1), ground=False, symmetric=True)

# ── materials: worn paint over bare steel, not plain plastic ──────────────────
a.material("shell",  (0.88, 0.89, 0.9),  metal=0.15, rough=0.42, wear=0.25,
           chip=0.18, under=(0.56, 0.57, 0.60), grime=0.08)
a.material("dark",   (0.10, 0.11, 0.13), metal=0.65, rough=0.40, wear=0.20,
           chip=0.10, under=(0.40, 0.42, 0.45), grime=0.06)
a.material("glow",   (0.10, 0.85, 1.0),  rough=0.15, emit=3.0)
a.material("accent", (1.0,  0.45, 0.05), rough=0.38, wear=0.15, chip=0.08,
           under=(0.56, 0.57, 0.60))
a.material("steel",  (0.56, 0.57, 0.60), metal=0.90, rough=0.30, wear=0.30,
           pattern="brushed", pattern_scale=0.8)

# ── side profiles: u = toward the FRONT (barrel, -Z), v = up ─────────────────
body = [(-1.1, 1.0), (1.2, 1.0), (1.2, 1.45, 0.08), (0.2, 1.52), (-0.9, 1.52, 0.15), (-1.15, 1.2, 0.1)]
a.extrude("Body", body, 0.42, "shell", plane="side")
a.extrude("Grip", [(-0.95, 1.05), (-0.38, 1.05), (-0.52, 0.02, 0.08), (-1.08, 0.05, 0.12)], 0.36, "dark", plane="side")
a.extrude("TriggerGuard", [(-0.42, 1.02), (0.28, 1.02), (0.28, 0.6, 0.15), (-0.48, 0.58)], 0.12, "dark", plane="side")
hole = [(-0.34, 0.95), (0.2, 0.95), (0.2, 0.68, 0.1), (-0.38, 0.68)]
a.cut("TriggerGuard", a.extrude("GuardHole", hole, 0.4, "dark", plane="side", bevel=0))
a.extrude("Trigger", [(-0.12, 1.0), (0.0, 1.0), (-0.05, 0.75, 0.04), (-0.14, 0.78)], 0.08, "accent", plane="side")

# ── barrel, muzzle, bore, rail, sight ────────────────────────────────────────
# 10 segments reads as round at game viewing distance while saving tris
a.cylinder("Barrel", 0.14, 0.75, (0, 1.25, -1.55), "dark", axis="Z", segments=10)
a.cylinder("Muzzle", 0.2, 0.18, (0, 1.25, -1.85), "shell", axis="Z", segments=10)
a.cut(["Muzzle", "Barrel"], a.cylinder("Bore", 0.08, 0.6, (0, 1.25, -1.9), "dark", axis="Z", segments=8, bevel=0))
a.box("Rail", (0.16, 0.1, 1.3), (0, 1.55, -0.15), "dark")
a.box("Sight", (0.08, 0.12, 0.12), (0, 1.64, -0.75), "accent")
# Rear sight — sits on Rail (Rail top y=1.60, RearSight center y=1.545 → bottom 1.505, overlaps)
a.box("RearSight", (0.10, 0.08, 0.10), (0, 1.545, 0.90), "accent")

# ── barrel shroud ring (heat collar) — 8 segments is enough for this size ─────
a.cylinder("ShroudRing", 0.18, 0.055, (0, 1.25, -1.30), "steel", axis="Z", segments=8)

# ── panel lines: break up the flat body flanks ────────────────────────────────
P.panel_line(a, "Body", "BodyDivH",
             start=(0.21, 1.25, -0.85), end=(0.21, 1.25, 0.95),
             mat="dark", width=0.04, depth=0.030, facing="+X")
P.panel_line(a, "Body", "BodyDivV",
             start=(0.21, 1.00, -0.10), end=(0.21, 1.25, -0.10),
             mat="dark", width=0.04, depth=0.030, facing="+X")

# ── inset panel on the rear body flank ────────────────────────────────────────
# plane="side": u→-Z, v→Y; surface=0.21 = body +X face; side=1 = +X
# RearPanel floor sits at X = 0.21 - 0.022 = 0.188 (the solid inset floor depth)
P.inset_panel(a, "Body", "RearPanel",
              [(-0.45, 1.14), (0.72, 1.14), (0.72, 1.44), (-0.45, 1.44)],
              "dark", plane="side", surface=0.21, side=1, depth=0.022, chamfer=0.010)

# ── raised data-port cover box on the inset panel floor ───────────────────────
# A flat steel box sitting ON the inset floor (X=0.188 + small clearance into the floor).
# Using a.box() avoids plate_support because it's a solid, not a thin plate.
# World coords: X=0.20 (inside body solid, close to inset floor), Y=1.28, Z=-0.10
# DataCover at z=-0.60 is in the fore-body area, outside the cell (cell z ends at -0.25)
# and outside the ForePanel inset (ForePanel: z≈-0.12..+0.35). Clear flat body face.
a.box("DataCover", (0.025, 0.18, 0.28), (0.20, 1.28, -0.60), "steel", bevel=0.006)

# ── screws at panel corners ───────────────────────────────────────────────────
# Radius 0.024 saves tris vs 0.028; positions clear of the energy cell (cell z-range ≈-0.25..0.55)
P.screws(a, "PanelScrew", [
    (0.22, 1.16,  0.68),
    (0.22, 1.42,  0.43),
], "dark", facing="+X", radius=0.024)

# ── fore-body inset panel (covers z≈0.13/y≈1.22 featureless area) ─────────────
# u=-0.35..+0.12 maps to z=0.35..-0.12; v=1.12..1.42 maps to y=1.12..1.42
P.inset_panel(a, "Body", "ForePanel",
              [(-0.35, 1.12), (0.12, 1.12), (0.12, 1.42), (-0.35, 1.42)],
              "dark", plane="side", surface=0.21, side=1, depth=0.020, chamfer=0.008)
# Panel line across ForePanel floor — breaks up the flat inset surface (no solid object to bury)
P.panel_line(a, "Body", "ForeDivV",
             start=(0.19, 1.15, 0.10), end=(0.19, 1.40, 0.10),
             mat="dark", width=0.030, depth=0.015, facing="+X")

# ── connector port (charge/sync) on grip side ────────────────────────────────
# At z=0.72/y=0.60 the grip solid is present (grip bottom at z=0.72 is y≈0.50).
# X=0.165: collar (radius*1.4=0.048) spans X=0.124..0.189, overlapping grip face at 0.18.
P.connector(a, "ChargePort", pos=(0.165, 0.60, 0.72), mat="steel",
            facing="+X", radius=0.034, ring_mat="dark")

# ── grip horizontal divider — breaks the z≈0.64/y≈0.79 featureless grip face ──
# Panel line on the Grip face (Grip x-face at X=0.18) at Y=0.72, from z=0.40 to z=0.90
P.panel_line(a, "Grip", "GripDiv",
             start=(0.18, 0.72, 0.40), end=(0.18, 0.72, 0.90),
             mat="dark", width=0.035, depth=0.025, facing="+X")

# ── mirrored side details ──────────────────────────────────────────────────────
with a.mirror("X"):
    # Energy cell (10 segments — saves ~40 tris vs 12 while staying round at game distance)
    a.cylinder("Cell", 0.12, 0.8, (0.24, 1.22, 0.15), "glow", axis="Z", segments=10)
    a.box("CellCap", (0.1, 0.3, 0.12), (0.24, 1.22, 0.58), "dark")

    # Vents on the barrel zone (3 slats, cut into Body)
    P.vent(a, "Body", "Vent", (0.21, 1.27, -0.65), (0.6, 0.3), "dark", facing="+X", slats=3, depth=0.05)

    # Bolts along the body/grip seam
    P.bolts(a, "Bolt", [(0.21, 1.1, -1.0), (0.21, 1.1, 0.75)], "dark", facing="+X", radius=0.04, height=0.04)

    # LED status indicator above the cell (8 segments is enough at this small radius)
    P.led(a, "StatusLed", pos=(0.22, 1.46, 0.55), mat_glow="glow", mat_housing="dark",
          facing="+X", radius=0.020)

    # Screw on the +Z face of CellCap: CellCap spans z=0.52..0.64, so +Z face is at z=0.64
    P.bolt(a, "CellCapBolt", pos=(0.24, 1.22, 0.645), mat="dark", facing="+Z", radius=0.026, height=0.022)

# ── serial number in its own "marks" group ────────────────────────────────────
# RearPanel floor is the clearest single flat face: X≈0.189, y=1.14..1.44, z=-0.45..0.72.
# Place at the floor center (X=0.19, Y=1.29, Z=0.15) away from all edges and DataCover.
# facing="+X", up="+Y"; group="marks" gives a separate texture → texel density fine.
# z=0.65 is past the cell (cell z-range ends at ≈0.55) and within RearPanel (z≤0.72)
a.text("Serial", "XV-331", pos=(0.19, 1.29, 0.65), mat="dark",
       size=0.07, facing="+X", depth=0.006, align="CENTER", up="+Y", group="marks")

a.build()
