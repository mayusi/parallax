"""build_crate.py — STARTER: steel-framed wooden supply crate. Shows: real boards (separate bevelled parts over a
dark core, so the gaps read as seams) in a pattern="wood" material (grain along each board, a tone per board), a
steel frame with corner caps, a wooden diagonal brace, handles bolted on through mounting plates (attached, never
floating), and baked floaters for everything smaller than a finger: bolt heads, nail heads, stencils (zero
triangles). Detail here is what a real crate has — never grooves carved into a plank to raise the score.
Run: lune run kit asset crate
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

a = rbx.Asset("g_crate_mine", size=(3.8, 3.15, 3.25), symmetric=True, bevel=0)
# pattern="wood": grain along every board's own length + a tone of its own (no two boards alike)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.35, pattern="wood")
a.material("wood_light", (0.6, 0.42, 0.25), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("core", (0.12, 0.08, 0.05), rough=0.95)
a.material("steel", (0.25, 0.27, 0.3), metal=0.6, rough=0.5, wear=0.35, chip=0.15, under=(0.42, 0.43, 0.45))
a.material("iron", (0.15, 0.15, 0.16), metal=0.9, rough=0.45)
a.material("paint", (0.86, 0.83, 0.74), rough=0.9)

S, T, F = 3.0, 0.09, 0.1  # crate edge, board thickness, how far the frame stands out of the boards
H = S / 2

# the dark core: what shows in the seams between the boards
a.box("Core", (S - 2 * T + 0.02, S - T + 0.01, S - 2 * T + 0.02), (0, (S - T + 0.01) / 2, 0), "core")

# boards: four per face (crate boards are narrow), 0.03 apart, each a bevelled part of its own (its own grain + tone)
N, gap = 4, 0.03
w = (S - (N - 1) * gap) / N
for i in range(N):
    c = -H + w / 2 + i * (w + gap)  # the board's centre across its face
    with a.mirror("Z"):
        a.box(f"BoardF{i}", (S, w, T), (0, H + c, -H + T / 2), "wood", bevel=0.02)
    with a.mirror("X"):
        a.box(f"BoardS{i}", (T, w, S), (H - T / 2, H + c, 0), "wood", bevel=0.02)
    a.box(f"BoardTop{i}", (w, T, S), (c, S - T / 2, 0), "wood", bevel=0.02)

# steel frame on the four sides, a rim round the top, caps on all eight corners
with a.mirror("Z"):
    P.frame(a, "FrameF", (S, S), (0, H, -H), "steel", thickness=0.3, depth=F, facing="-Z")
    a.box("RimF", (S + 2 * F, F, 0.4), (0, S + F / 2, -(H + F) + 0.2), "steel")
with a.mirror("X"):
    P.frame(a, "FrameS", (S, S), (H, H, 0), "steel", thickness=0.3, depth=F, facing="+X")
    a.box("RimS", (0.4, F, S + 2 * F), (H + F - 0.2, S + F / 2, 0), "steel")
C = 0.42  # corner cap, standing 0.025 proud of the frame on every side it covers
cx = H + F + 0.025 - C / 2
top = S + F + 0.025 - C / 2
with a.mirror("X"), a.mirror("Z"):
    a.box("CapLow", (C, C, C), (cx, C / 2, -cx), "steel")
    a.box("CapTop", (C, C, C), (cx, top, -cx), "steel")

# diagonal brace across the front and back, nailed at both ends and where it crosses the middle board
with a.mirror("Z"):
    a.box("Brace", (3.6, 0.3, 0.07), (0, H, -H - 0.035), "wood_light", rot=(0, 0, 45), bevel=0.02)

# handles: a mounting plate at each end, the handle's ends sunk into the plates
with a.mirror("X"):
    with a.mirror("Z"):
        a.box("Mount", (0.07, 0.34, 0.24), (H + 0.025, 2.45, -0.65), "steel")
    P.handle(a, "Handle", (H + 0.06, 2.45, -0.65), (H + 0.06, 2.45, 0.65), "iron", radius=0.055, lift=0.28, facing="+X",
             segments=6)

# everything smaller than a finger is baked into the maps (floaters): no triangles, no exact contact needed
with a.floaters():
    with a.mirror("X"), a.mirror("Z"):
        P.bolts(a, "CapBoltF", [(cx, C / 2, -(H + F + 0.025)), (cx, top, -(H + F + 0.025))], "iron", facing="-Z", radius=0.07)
        P.bolts(a, "CapBoltS", [(H + F + 0.025, C / 2, -cx), (H + F + 0.025, top, -cx)], "iron", facing="+X", radius=0.07)
        P.bolt(a, "CapBoltTop", (cx, S + F + 0.025, -cx), "iron", facing="+Y", radius=0.07)
        P.bolts(a, "MountBolt", [(H + 0.06, 2.45 + 0.11, -0.65), (H + 0.06, 2.45 - 0.11, -0.65)], "iron", facing="+X", radius=0.04)
    with a.mirror("Z"):
        for k, d in enumerate((-1.25, -0.536, 0.536, 1.25)):  # near both ends + where it crosses the middle boards
            for j, s in enumerate((-0.07, 0.07)):
                x, y = d * 0.7071 - s * 0.7071, H + d * 0.7071 + s * 0.7071
                a.cylinder(f"BraceNail{k}{j}", 0.03, 0.02, (x, y, -H - 0.075), "iron", axis="Z", segments=8)
    for i in range(N):
        c = -H + w / 2 + i * (w + gap)
        with a.mirror("Z"):
            for j, s in enumerate((-0.18, 0.18)):
                if abs(c + s) < H + F - 0.4 - 0.05:  # (a nail under the rim would never be seen)
                    a.cylinder(f"TopNail{i}{j}", 0.03, 0.02, (c + s, S + 0.005, -H + 0.5), "iron", axis="Y", segments=8)
    # every board is nailed near both ends, just inside the frame's opening — nails under the frame bars or the
    # brace would never be seen, so none are placed there
    for i in range(N):
        c = -H + w / 2 + i * (w + gap)
        for j, x in enumerate((-1.11, 1.11)):
            for k, dy in enumerate((-0.2, 0.2)):
                y = H + c + dy
                if not 0.3 + 0.05 < y < S - 0.3 - 0.05:
                    continue
                if abs(y - H - x) / 1.414 > 0.24:
                    with a.mirror("Z"):
                        a.cylinder(f"BoardNailF{i}{j}{k}", 0.03, 0.02, (x, y, -H - 0.005), "iron", axis="Z", segments=8)
                with a.mirror("X"):
                    a.cylinder(f"BoardNailS{i}{j}{k}", 0.03, 0.02, (H + 0.005, y, x), "iron", axis="X", segments=8)
    # stencils: text is never mirrored (it would read backwards) — one per face, each facing out
    a.text("StencilR", "SUPPLY", (H + 0.001, 1.12, 0), "paint", size=0.36, facing="+X")
    a.text("StencilL", "SUPPLY", (-H - 0.001, 1.12, 0), "paint", size=0.36, facing="-X")
    a.text("NumberF", "07", (-0.62, 1.88, -H - 0.001), "paint", size=0.5, facing="-Z")
    a.text("NumberB", "07", (-0.62, 1.88, H + 0.001), "paint", size=0.5, facing="+Z")
a.build()
