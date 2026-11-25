"""build_blaster.py — STARTER: sci-fi blaster (handheld, barrel = front -Z). Shows: a side-profile body and an
angled grip (extrude plane="side"), a trigger guard made by cutting one outline out of another, a barrel with a
cut bore, vents and glowing energy cells on both sides (mirror X). Run: lune run kit asset blaster
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

a = rbx.Asset("g_blaster_old", size=(0.75, 1.6, 3.1), ground=False, symmetric=True)
a.material("shell", (0.88, 0.89, 0.9), metal=0.1, rough=0.45)
a.material("dark", (0.1, 0.11, 0.13), metal=0.5, rough=0.5)
a.material("glow", (0.1, 0.85, 1.0), rough=0.2)
a.material("accent", (1.0, 0.45, 0.05), rough=0.4)

# side profiles: u = toward the FRONT (barrel), v = up
body = [(-1.1, 1.0), (1.2, 1.0), (1.2, 1.45, 0.08), (0.2, 1.52), (-0.9, 1.52, 0.15), (-1.15, 1.2, 0.1)]
a.extrude("Body", body, 0.42, "shell", plane="side")
a.extrude("Grip", [(-0.95, 1.05), (-0.38, 1.05), (-0.52, 0.02, 0.08), (-1.08, 0.05, 0.12)], 0.36, "dark", plane="side")
a.extrude("TriggerGuard", [(-0.42, 1.02), (0.28, 1.02), (0.28, 0.6, 0.15), (-0.48, 0.58)], 0.12, "dark", plane="side")
hole = [(-0.34, 0.95), (0.2, 0.95), (0.2, 0.68, 0.1), (-0.38, 0.68)]
a.cut("TriggerGuard", a.extrude("GuardHole", hole, 0.4, "dark", plane="side", bevel=0))
a.extrude("Trigger", [(-0.12, 1.0), (0.0, 1.0), (-0.05, 0.75, 0.04), (-0.14, 0.78)], 0.08, "accent", plane="side")

# barrel along -Z, muzzle ring, bore cut through both
a.cylinder("Barrel", 0.14, 0.75, (0, 1.25, -1.55), "dark", axis="Z", segments=16)
a.cylinder("Muzzle", 0.2, 0.18, (0, 1.25, -1.85), "shell", axis="Z", segments=16)
a.cut(["Muzzle", "Barrel"], a.cylinder("Bore", 0.08, 0.6, (0, 1.25, -1.9), "dark", axis="Z", segments=12, bevel=0))
a.box("Rail", (0.16, 0.1, 1.3), (0, 1.55, -0.15), "dark")
a.box("Sight", (0.08, 0.12, 0.12), (0, 1.64, -0.75), "accent")

with a.mirror("X"):
    a.cylinder("Cell", 0.12, 0.8, (0.24, 1.22, 0.15), "glow", axis="Z", segments=12)
    a.box("CellCap", (0.1, 0.3, 0.12), (0.24, 1.22, 0.58), "dark")
    P.vent(a, "Body", "Vent", (0.21, 1.27, -0.65), (0.6, 0.3), "dark", facing="+X", slats=3, depth=0.05)
    P.bolts(a, "Bolt", [(0.21, 1.1, -1.0), (0.21, 1.1, 0.75)], "dark", facing="+X", radius=0.05, height=0.04)
a.build()
