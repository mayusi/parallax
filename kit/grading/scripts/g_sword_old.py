"""build_sword.py — STARTER: knight sword (handheld). Shows: a front-view outline extrude for the blade, a
shallow fuller groove cut on both faces (mirror Z + cut), a curved crossguard drawn once and mirrored (mirror X),
a wrapped grip (rbx_parts.grip), a gem accent. Run: lune run kit asset sword
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

a = rbx.Asset("g_sword_old", size=(1.75, 4.9, 0.4), ground=False, symmetric=True)
a.material("steel", (0.78, 0.8, 0.84), metal=0.95, rough=0.25)
a.material("dark", (0.07, 0.07, 0.08), metal=0.6, rough=0.5)
a.material("gold", (0.85, 0.62, 0.2), metal=1.0, rough=0.3, wear=0.25)
a.material("leather", (0.16, 0.09, 0.06), rough=0.85)
a.material("gem", (0.75, 0.05, 0.1), rough=0.15)

# blade: drawn as seen from the front (u = right, v = up), 0.12 thick
a.extrude("Blade", [(-0.2, 1.3), (0.2, 1.3), (0.2, 4.05), (0, 4.85), (-0.2, 4.05)], 0.12, "steel", plane="front")
with a.mirror("Z"):  # the same shallow groove on BOTH faces
    a.cut("Blade", a.box("Fuller", (0.07, 2.4, 0.06), (0, 2.7, -0.06), "dark", bevel=0))

# crossguard: one half drawn, the other mirrored; the tips curve up toward the blade
with a.mirror("X"):
    a.extrude(
        "Guard",
        [(-0.02, 1.1), (0.55, 1.1, 0.1), (0.86, 1.3, 0.06), (0.86, 1.46, 0.05), (0.6, 1.36), (-0.02, 1.4)],
        0.3,
        "gold",
        plane="front",
    )
with a.mirror("Z"):
    a.sphere("Gem", 0.11, (0, 1.25, -0.15), "gem", scale=(1, 1, 0.55))

P.grip(a, "Grip", (0, 0.24, 0), 0.9, 0.105, "leather", "gold", wraps=4)
a.sphere("Pommel", 0.18, (0, 0.14, 0), "gold", scale=(1, 0.85, 1))

# stated intentions — the build MEASURES these (no eyeballing): it fails with the exact distance if one breaks
a.expect("Guard", touches="Blade")
a.expect("Pommel", touches="Grip")
a.expect("Gem", touches="Guard", in_front_of="Blade")
a.expect("Blade", size={"y": (3.4, 3.7)}, at={"x": (-0.02, 0.02)})
a.build()
