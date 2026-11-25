"""build_blaster.py — STARTER: sci-fi blaster (handheld). Shows: side-profile extrudes for a two-tone receiver and lower
frame, a raked ergonomic grip LOFTED through rounded-rectangle stations (each station offset: no rotations), a barrel
with cooling rings and a glowing emitter in the bore, recessed power windows (inset_panel + a glow strip), vents, a holo
sight, and floaters for the small stuff (screws, LEDs, the maker mark). Run: lune run kit asset blaster
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

a = rbx.Asset("blaster", size=(0.45, 1.75, 3.1), ground=False, symmetric=True)
a.material("shell", (0.88, 0.89, 0.9), metal=0.1, rough=0.4, pattern="coat", chip=0.12, under=(0.3, 0.31, 0.33))
a.material("dark", (0.11, 0.12, 0.14), metal=0.5, rough=0.5, wear=0.25)
a.material("grip", (0.13, 0.13, 0.15), rough=0.75, pattern="grid")
a.material("glow", (0.1, 0.85, 1.0), rough=0.2, emit=3)
a.material("accent", (1.0, 0.45, 0.05), rough=0.4)

# side profiles: u = toward the FRONT (the barrel, -Z), v = up; a third number rounds that corner
receiver = [(-1.12, 1.05, 0.06), (0.92, 1.05), (1.1, 1.22, 0.04), (1.1, 1.36, 0.04), (0.55, 1.5, 0.06),
            (-0.75, 1.55, 0.1), (-1.0, 1.5, 0.08), (-1.18, 1.3, 0.08)]
a.extrude("Receiver", receiver, 0.44, "shell", plane="side")
a.extrude("Frame", [(-0.98, 1.08), (0.78, 1.08), (0.7, 0.9, 0.05), (-0.9, 0.9, 0.05)], 0.38, "dark", plane="side")

# the grip: rounded-rectangle sections from the butt up, each set further forward (a raked grip, a palm swell)
# loft axis Y: (y, half-depth along Z, half-width along X, (z offset, x offset), squareness)
a.loft("Grip", [(0.05, 0.24, 0.16, (0.84, 0), 3.0), (0.15, 0.25, 0.17, (0.81, 0), 3.0), (0.45, 0.26, 0.18, (0.74, 0), 3.0),
                (0.75, 0.27, 0.18, (0.67, 0), 3.0), (0.97, 0.26, 0.17, (0.62, 0), 3.0)], "grip", axis="Y", segments=16)
a.box("Butt", (0.38, 0.08, 0.56), (0, 0.06, 0.85), "dark", bevel=0.02)
a.extrude("TriggerGuard", [(-0.36, 0.95), (0.3, 0.95), (0.3, 0.62, 0.14), (-0.5, 0.56)], 0.12, "dark", plane="side")
a.cut("TriggerGuard", a.extrude("GuardHole", [(-0.3, 0.91), (0.22, 0.91), (0.22, 0.68, 0.1), (-0.34, 0.64)], 0.4, "dark",
                                plane="side", bevel=0))
a.extrude("Trigger", [(-0.1, 0.93), (0.02, 0.93), (-0.04, 0.72, 0.04), (-0.13, 0.75)], 0.08, "accent", plane="side")

# barrel along -Z: cooling rings, a flared emitter, a glowing core at the bottom of its bore
a.cylinder("Barrel", 0.12, 0.8, (0, 1.24, -1.35), "dark", axis="Z", segments=16)
for i, z in enumerate((-1.28, -1.4, -1.52)):
    a.cylinder(f"CoolRing{i}", 0.17, 0.06, (0, 1.24, z), "dark", axis="Z", segments=16)
a.cylinder("Emitter", 0.21, 0.22, (0, 1.24, -1.84), "shell", axis="Z", segments=16, radius_top=0.17)
a.cut("Emitter", a.cylinder("Bore", 0.11, 0.3, (0, 1.24, -1.95), "dark", axis="Z", segments=16, bevel=0))
a.cylinder("Core", 0.105, 0.04, (0, 1.24, -1.81), "glow", axis="Z", segments=16, bevel=0)  # (inside the bore wall, never on it)

# top: a holo sight at the back (its window cut through, a lens inside), a front post with an orange tip
a.extrude("Sight", [(-0.86, 1.5), (-0.42, 1.5), (-0.47, 1.76, 0.03), (-0.81, 1.76, 0.03)], 0.24, "dark", plane="side")
a.cut("Sight", a.box("SightWindow", (0.14, 0.13, 0.6), (0, 1.66, 0.64), "dark", bevel=0))
a.box("Lens", (0.15, 0.14, 0.02), (0, 1.66, 0.64), "glow", bevel=0)
a.box("FrontPost", (0.07, 0.12, 0.08), (0, 1.53, -0.5), "dark")
a.box("PostTip", (0.072, 0.04, 0.082), (0, 1.6, -0.5), "accent")

with a.mirror("X"):
    # a recessed power window on each side, a glowing cell strip inside it
    P.inset_panel(a, "Receiver", "Window", [(-0.55, 1.19, 0.04), (0.25, 1.19, 0.04), (0.25, 1.35, 0.04), (-0.55, 1.35, 0.04)],
                  "dark", plane="side", surface=0.22, side=1, depth=0.06)
    a.box("Cell", (0.04, 0.12, 0.76), (0.18, 1.27, 0.15), "glow", bevel=0)
    P.vent(a, "Receiver", "Vent", (0.22, 1.28, -0.75), (0.3, 0.18), "dark", facing="+X", slats=3, depth=0.04)

# everything smaller than a finger is baked into the maps (floaters): screws, LEDs, the maker mark
with a.floaters():
    with a.mirror("X"):
        P.bolts(a, "Screw", [(0.22, 1.12, 0.95), (0.22, 1.44, 0.7), (0.22, 1.12, -0.6), (0.22, 1.42, 0.45)], "dark",
                facing="+X", radius=0.035, height=0.02)
        P.bolts(a, "GripScrew", [(0.18, 0.55, 0.73)], "dark", facing="+X", radius=0.035, height=0.02)
    for i, x in enumerate((-0.08, 0.08)):
        P.led(a, f"Led{i}", (x, 1.2, 1.158), "glow", "dark", facing="+Z", radius=0.025)
    a.text("MarkR", "MK-2", (0.221, 1.13, 0.28), "dark", size=0.07, facing="+X")
    a.text("MarkL", "MK-2", (-0.221, 1.13, 0.28), "dark", size=0.07, facing="-X")
a.build()
