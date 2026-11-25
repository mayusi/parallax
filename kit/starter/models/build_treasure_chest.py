"""build_treasure_chest.py — STARTER: banded treasure chest. Shows: a barrel lid built from slats that follow the arch
(each slat an outline extruded across the width — exact, no rotations — over a dark core, so seams read and nothing
is see-through), real boards on the base, wood grain that follows every board (pattern="wood"), gold bands, rim and
corner caps, a shield lock with a keyhole cut and a hasp hung on a knuckle, black-painted iron strap hinges on the
back and side handles on mounts (chipped paint: chip= + under=), and rivets baked in as floaters (zero triangles).
Outlines are just lists of points — use math for arches, gears, stars, teeth. Run: lune run kit asset treasure_chest
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

a = rbx.Asset("treasure_chest", size=(4.75, 3.05, 2.85), symmetric=True, bevel=0)  # (the side handles count)
a.material("wood", (0.42, 0.22, 0.1), rough=0.8, wear=0.3, grime=0.3, pattern="wood")
a.material("core", (0.1, 0.06, 0.04), rough=0.95)
a.material("gold", (0.86, 0.63, 0.2), metal=1.0, rough=0.3, wear=0.35)
a.material("iron", (0.1, 0.1, 0.11), metal=0.4, rough=0.6, chip=0.3, under=(0.42, 0.42, 0.44))  # black-painted iron

W, D, F = 4.0, 2.6, 0.2  # width, depth, foot height
T = 0.08  # board thickness
TOP = F + 1.7  # where the base ends and the lid starts
WALL, RISE = 0.3, 0.75  # the lid's straight wall, then its arch
g = 0.07  # how far the gold stands out of the wood


def arch(half_depth, base, rise, wall, steps=16):
    """the lid's side profile (u = toward the front, v = up): a wall, then a half-ellipse"""
    pts = [(-half_depth, base), (half_depth, base), (half_depth, base + wall)]
    for k in range(1, steps):
        t = math.pi * k / steps
        pts.append((half_depth * math.cos(t), base + wall + rise * math.sin(t)))
    return pts + [(-half_depth, base + wall)]


# ---- base: a dark core, three boards on every side
a.box("Core", (W - 2 * T + 0.02, 1.7, D - 2 * T + 0.02), (0, F + 0.85, 0), "core")
gap = 0.03
bw = (1.7 - 2 * gap) / 3
for i in range(3):
    y = F + bw / 2 + i * (bw + gap)
    with a.mirror("Z"):
        a.box(f"BoardF{i}", (W, bw, T), (0, y, -D / 2 + T / 2), "wood", bevel=0.02)
    with a.mirror("X"):
        a.box(f"BoardS{i}", (T, bw, D - 2 * T), (W / 2 - T / 2, y, 0), "wood", bevel=0.02)

# ---- lid: a core, a wall board front and back, end panels, and seven slats round the arch
a.extrude("LidCore", arch(D / 2 - T, TOP, RISE - T, WALL), W - 2 * T + 0.02, "core", plane="side")
with a.mirror("Z"):
    a.box("LidWall", (W, WALL, T), (0, TOP + WALL / 2, -D / 2 + T / 2), "wood", bevel=0.02)
with a.mirror("X"):
    a.extrude("LidEnd", arch(D / 2 - T, TOP, RISE - T, WALL), T, "wood", plane="side", pos=(W / 2 - T / 2, 0, 0))


def ellipse(th, grow=0.0):
    return ((D / 2 + grow) * math.cos(th), TOP + WALL + (RISE + grow) * math.sin(th))


# split the arch into slats of EQUAL width (equal arc length, not equal angle: boards are all one width)
ths = [math.pi * k / 400 for k in range(401)]
arc = [0.0]
for k in range(1, 401):
    (u0, v0), (u1, v1) = ellipse(ths[k - 1]), ellipse(ths[k])
    arc.append(arc[-1] + math.hypot(u1 - u0, v1 - v0))
SLATS = 7
edges = [ths[min(range(401), key=lambda k: abs(arc[k] - arc[-1] * j / SLATS))] for j in range(SLATS + 1)]
for j in range(SLATS):
    t0, t1 = edges[j] + 0.006, edges[j + 1] - 0.006  # a hairline seam between slats (the dark core shows)
    outer = [ellipse(t0 + (t1 - t0) * k / 2) for k in range(3)]
    inner = [ellipse(t1 - (t1 - t0) * k / 2, -T) for k in range(3)]
    a.extrude(f"Slat{j}", outer + inner, W, "wood", plane="side", bevel=0.02)

# ---- gold: two bands over the lid and down the base, a rim at the seam, caps on the bottom corners
with a.mirror("X"):
    a.extrude("LidBand", arch(D / 2 + g, TOP - g, RISE + g, WALL + g), 0.32, "gold", plane="side", pos=(1.3, 0, 0))
    a.box("BaseBand", (0.32, 1.7, D + 2 * g), (1.3, F + 0.85, 0), "gold")
    with a.mirror("Z"):
        a.box("CornerCap", (0.4, 0.5, 0.4), (W / 2 + 0.03 - 0.2, F + 0.25, -D / 2 - 0.03 + 0.2), "gold")
        a.box("Foot", (0.42, F + 0.02, 0.42), (W / 2 - 0.3, (F + 0.02) / 2, -D / 2 + 0.3), "iron")
a.box("Rim", (W + 0.1, 0.18, D + 0.1), (0, TOP - 0.09, 0), "gold")

# ---- iron: strap hinges on the back (over the lid, a knuckle at the seam, down the base) and a handle each end
with a.mirror("X"):
    th = [math.pi - (math.pi * 0.38) * k / 6 for k in range(7)]  # from the back wall up over the arch
    strap = [(-(D / 2 + 0.04), TOP + 0.02)] + [ellipse(t, 0.04) for t in th]
    strap += [ellipse(t, -0.01) for t in reversed(th)] + [(-(D / 2 - 0.01), TOP + 0.02)]
    a.extrude("HingeStrap", strap, 0.2, "iron", plane="side", pos=(0.7, 0, 0))
    a.box("HingeLeaf", (0.2, 0.55, 0.05), (0.7, TOP - 0.3, D / 2 + 0.02), "iron")
    a.cylinder("HingeKnuckle", 0.07, 0.24, (0.7, TOP + 0.01, D / 2 + 0.05), "iron", axis="X", segments=10)
    with a.mirror("Z"):
        a.box("HandleMount", (0.06, 0.3, 0.2), (W / 2 + 0.02, 1.2, -0.45), "iron")
    P.handle(a, "Handle", (W / 2 + 0.05, 1.2, -0.45), (W / 2 + 0.05, 1.2, 0.45), "iron", radius=0.05, lift=0.24,
             facing="+X", segments=6)

# ---- lock: a shield plate on the base with a keyhole cut through it, and the hasp hanging over it from the lid
shield = [(-0.34, 0.36, 0.08), (0.34, 0.36, 0.08), (0.34, -0.12), (0, -0.44), (-0.34, -0.12)]
a.extrude("Lock", [(u, TOP - 0.42 + v, *r) for u, v, *r in shield], 0.1, "gold", plane="front", pos=(0, 0, -D / 2 - 0.05))
a.cut("Lock", a.cylinder("Keyhole", 0.07, 0.3, (0, TOP - 0.52, -D / 2 - 0.1), "iron", axis="Z", segments=10))
a.cut("Lock", a.box("KeySlot", (0.06, 0.18, 0.3), (0, TOP - 0.62, -D / 2 - 0.1), "iron"))
hasp = [(-0.12, -0.3, 0.05), (0.12, -0.3, 0.05), (0.12, 0.2), (-0.12, 0.2)]
a.extrude("Hasp", [(u, TOP + v, *r) for u, v, *r in hasp], 0.05, "gold", plane="front", pos=(0, 0, -D / 2 - 0.125))
a.cylinder("HaspHinge", 0.06, 0.3, (0, TOP + 0.18, -D / 2 - 0.06), "gold", axis="X", segments=10)  # hangs it on the lid

# ---- rivets on every band, baked into the maps (floaters): domes with no triangles of their own
with a.floaters():
    with a.mirror("X"):
        for k in range(7):
            th = math.pi * (k + 0.5) / 7
            u, v = ellipse(th, g)
            a.sphere(f"LidRivet{k}", 0.05, (1.3, v, -u), "gold", segments=8, rings=4)
        with a.mirror("Z"):
            a.sphere("WallRivet", 0.05, (1.3, TOP + 0.13, -D / 2 - g), "gold", segments=8, rings=4)
            P.rivets(a, "BandRivet", (1.3, F + 0.3, -D / 2 - g), (1.3, F + 1.35, -D / 2 - g), 3, "gold")
            a.sphere("CapRivetF", 0.045, (W / 2 - 0.17, F + 0.25, -D / 2 - 0.03), "gold", segments=8, rings=4)
            a.sphere("CapRivetS", 0.045, (W / 2 + 0.03, F + 0.25, -D / 2 + 0.17), "gold", segments=8, rings=4)
    with a.mirror("X"):
        a.sphere("LockRivet", 0.04, (0.22, TOP - 0.2, -D / 2 - 0.1), "gold", segments=8, rings=4)
a.build()
