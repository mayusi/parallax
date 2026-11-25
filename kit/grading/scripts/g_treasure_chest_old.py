"""build_treasure_chest.py — STARTER: treasure chest. Shows: an arched lid drawn as a computed side profile
(extrude), metal bands slightly larger than the body (wrap a shape by over-sizing a thin copy), a lock plate with a
cut keyhole, feet so the base reads as furniture. Run: lune run kit asset treasure_chest
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

a = rbx.Asset("g_treasure_chest_old", size=(4.1, 3.0, 2.8), symmetric=True)
a.material("wood", (0.5, 0.27, 0.13), rough=0.8, wear=0.4)
a.material("seam", (0.18, 0.1, 0.05), rough=0.9)
a.material("gold", (0.86, 0.63, 0.2), metal=1.0, rough=0.3, wear=0.3)
a.material("dark", (0.05, 0.05, 0.05), rough=0.7)

W, D, F = 4.0, 2.6, 0.2  # width, depth, foot height
TOP = F + 1.7  # where the base ends and the lid starts
a.box("Base", (W, 1.7, D), (0, F + 0.85, 0), "wood")
with a.mirror("Z"):
    for i, y in enumerate((F + 0.57, F + 1.13)):
        P.panel_line(a, "Base", f"Seam{i}", (-W / 2, y, -D / 2), (W / 2, y, -D / 2), "seam", facing="-Z")

# lid: a side profile (u = toward the front, v = up) computed as a half-ellipse arch, extruded across the width.
# Outlines are just lists of points — use math for arches, gears, stars, teeth.
def arch(half_depth, base, rise, wall, steps=12):
    pts = [(-half_depth, base), (half_depth, base), (half_depth, base + wall)]
    for k in range(1, steps):
        t = math.pi * k / steps
        pts.append((half_depth * math.cos(t), base + wall + rise * math.sin(t)))
    return pts + [(-half_depth, base + wall)]


a.extrude("Lid", arch(D / 2, TOP, 0.75, 0.3), W, "wood", plane="side")

# gold bands: the same arch grown by g and thin across X, so they wrap the lid; the base band wraps the base
g = 0.07
with a.mirror("X"):
    a.extrude("LidBand", arch(D / 2 + g, TOP - g, 0.75 + g, 0.3 + g), 0.35, "gold", plane="side", pos=(1.35, 0, 0))
    a.box("BaseBand", (0.35, 1.7, D + 2 * g), (1.35, F + 0.85, 0), "gold")
    with a.mirror("Z"):
        P.bolts(a, "BandBolt", [(1.35, F + 0.3, -D / 2 - g), (1.35, F + 1.4, -D / 2 - g)], "dark", facing="-Z")
        a.box("Foot", (0.45, F + 0.05, 0.45), (W / 2 - 0.3, F / 2, -D / 2 + 0.3), "dark")
a.box("Rim", (W + 0.1, 0.18, D + 0.1), (0, TOP - 0.09, 0), "gold")

# lock: plate over the seam, keyhole cut through it with the dark material
a.box("Lock", (0.65, 0.8, 0.12), (0, TOP - 0.05, -D / 2 - 0.1), "gold")
a.cut("Lock", a.cylinder("Keyhole", 0.08, 0.4, (0, TOP + 0.02, -D / 2 - 0.1), "dark", axis="Z", segments=10, bevel=0))
a.cut("Lock", a.box("KeySlot", (0.07, 0.2, 0.4), (0, TOP - 0.12, -D / 2 - 0.1), "dark", bevel=0))
a.build()
