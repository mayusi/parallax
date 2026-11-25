"""build_crate.py — STARTER: wooden supply crate. Shows: plank seams (panel_line), metal frames on every side
(frame + mirror), a diagonal brace, bolts at the corners, rope-style handles. Run: lune run kit asset crate
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

a = rbx.Asset("g_crate_old", size=(4.1, 3.1, 3.3), symmetric=True)
a.material("wood", (0.55, 0.36, 0.2), rough=0.85, wear=0.45)
a.material("seam", (0.2, 0.12, 0.07), rough=0.9)
a.material("metal", (0.32, 0.33, 0.35), metal=0.85, rough=0.45, wear=0.35)

S = 3.0  # body edge (studs)
H = S / 2
a.box("Body", (S, S, S), (0, H, 0), "wood", bevel=0.05)

# plank seams on the four sides and the lid
with a.mirror("Z"):
    for i, y in enumerate((1.0, 2.0)):
        P.panel_line(a, "Body", f"SeamF{i}", (-H, y, -H), (H, y, -H), "seam", facing="-Z")
with a.mirror("X"):
    for i, y in enumerate((1.0, 2.0)):
        P.panel_line(a, "Body", f"SeamS{i}", (H, y, -H), (H, y, H), "seam", facing="+X")
for i, x in enumerate((-0.5, 0.5)):
    P.panel_line(a, "Body", f"SeamTop{i}", (x, S, -H), (x, S, H), "seam", facing="+Y")

# metal frames: front/back and both sides, with a diagonal brace and corner bolts on front/back
with a.mirror("Z"):
    P.frame(a, "FrameF", (S + 0.1, S + 0.1), (0, H, -H), "metal", thickness=0.32, depth=0.12, facing="-Z")
    a.box("Brace", (3.25, 0.32, 0.1), (0, H, -H - 0.05), "metal", rot=(0, 0, 45))
    P.bolts(
        a,
        "BoltF",
        [(x, y, -H - 0.12) for x in (-1.36, 1.36) for y in (0.16 + 0, S - 0.16)],
        "seam",
        facing="-Z",
        radius=0.09,
    )
with a.mirror("X"):
    P.frame(a, "FrameS", (S + 0.1, S + 0.1), (H, H, 0), "metal", thickness=0.32, depth=0.12, facing="+X")
    P.handle(a, "Handle", (H + 0.12, 2.1, -0.55), (H + 0.12, 2.1, 0.55), "seam", radius=0.07, lift=0.3, facing="+X")
a.build()
