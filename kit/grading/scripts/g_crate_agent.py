"""build_crate.py — STARTER: wooden supply crate. Shows: dense plank seams (panel_line) on every face,
metal frames on all sides (frame + mirror), diagonal brace, corner bolts, handle eye-brackets with rope
U-handles seated into them, small inset lid panels, a stencil marking (a.text), a lid latch, inset panels
on the side faces, chip + grime on wood and metal. Run: lune run kit asset crate
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

a = rbx.Asset("g_crate_agent", size=(4.1, 3.1, 3.3), symmetric=True, allow_floating=["Stencil"])

# ── materials ──────────────────────────────────────────────────────────────────
a.material("wood",    (0.55, 0.36, 0.20), rough=0.85, wear=0.80, chip=0.65, under=(0.28, 0.16, 0.07), grime=0.60)
a.material("seam",    (0.18, 0.10, 0.06), rough=0.92)
a.material("metal",   (0.30, 0.31, 0.33), metal=0.85, rough=0.50, wear=0.70, chip=0.75, under=(0.15, 0.15, 0.16), grime=0.55)
a.material("rope",    (0.50, 0.38, 0.24), rough=0.95, wear=0.60, grime=0.50)
a.material("stencil", (0.10, 0.10, 0.10), rough=0.70)

S = 3.0   # body edge (studs)
H = S / 2  # half = 1.5

# ── body ──────────────────────────────────────────────────────────────────────
a.box("Body", (S, S, S), (0, H, 0), "wood", bevel=0.05)

# ── plank seams: front/back — 3 horizontal seams (4 planks) ──────────────────
# Third seam at y=2.45 breaks up the wide empty upper band
with a.mirror("Z"):
    # Dense front seams: 5 horizontal (every ~0.5 studs) + 2 vertical
    for i, y in enumerate((0.45, 0.90, 1.40, 1.90, 2.45)):
        P.panel_line(a, "Body", f"SeamF{i}", (-H, y, -H), (H, y, -H), "seam", width=0.05, depth=0.07, facing="-Z")
    # Vertical seams to triple-split the front face
    P.panel_line(a, "Body", "SeamFV0", (0.0, 0.05, -H), (0.0, S - 0.05, -H), "seam",
                 width=0.04, depth=0.05, facing="-Z")
    P.panel_line(a, "Body", "SeamFVn", (-0.75, 0.05, -H), (-0.75, S - 0.05, -H), "seam",
                 width=0.04, depth=0.05, facing="-Z")

# ── plank seams: side faces — horizontal + vertical for dense coverage ─────────
# 4 horizontal seams + 1 vertical seam on each side
with a.mirror("X"):
    # 11 horizontal seams — dense coverage to near edge
    for i, y in enumerate((0.07, 0.30, 0.60, 0.90, 1.20, 1.50, 1.80, 2.10, 2.40, 2.70, 2.93)):
        P.panel_line(a, "Body", f"SeamS{i}", (H, y, -H), (H, y, H), "seam",
                     width=0.05, depth=0.06, facing="+X")
    # Three vertical seams at z=±0.5, z=0 (quad-splits the face)
    for k, z in enumerate((-0.5, 0.0, 0.5)):
        P.panel_line(a, "Body", f"SeamSV{k}", (H, 0.05, z), (H, S - 0.05, z), "seam",
                     width=0.04, depth=0.05, facing="+X")

# ── lid seam lines: 5 lines across top + 6 cross-grooves ─────────────────────
for i, x in enumerate((-1.0, -0.5, 0.0, 0.5, 1.0)):
    P.panel_line(a, "Body", f"SeamTop{i}", (x, S, -H), (x, S, H), "seam", width=0.05, depth=0.07, facing="+Y")
# Cross-grooves: at z=±0.7 (between panel rows), z=±0.35 (inside outer rows), z=±0.0 (centre)
for j, z in enumerate((-0.70, -0.56, -0.42, -0.28, -0.14, 0.14, 0.28, 0.42, 0.56, 0.70)):
    P.panel_line(a, "Body", f"SeamTopX{j}", (-H, S, z), (H, S, z), "seam", width=0.05, depth=0.07, facing="+Y")

# ── inset panels on the side faces (4 small panels per side, mirrored) ────────
# Placed in the gaps between seam lines (y=0 to 0.55, 0.55 to 1.10, 1.65 to 2.20, 2.20 to 3.0)
# and between the vertical seam (z<0 and z>0 halves)
# Side face: small inset panels in even gaps (seams every ~0.30 studs)
# Panel height ≈ 0.20 studs to fit within gaps
with a.mirror("X"):
    for gi, (y0, y1) in enumerate([(0.10, 0.27), (0.40, 0.57), (0.70, 0.87),
                                    (1.00, 1.17), (1.30, 1.47), (1.60, 1.77),
                                    (1.90, 2.07), (2.20, 2.37), (2.50, 2.67), (2.80, 2.90)]):
        P.inset_panel(a, "Body", f"SidePa{gi}", [(-1.35, y0), (-0.57, y0), (-0.57, y1), (-1.35, y1)],
                      "seam", plane="side", surface=H, side=1, depth=0.025, chamfer=0.006)
        P.inset_panel(a, "Body", f"SidePb{gi}", [(-0.43, y0), ( 0.43, y0), ( 0.43, y1), (-0.43, y1)],
                      "seam", plane="side", surface=H, side=1, depth=0.025, chamfer=0.006)
        P.inset_panel(a, "Body", f"SidePc{gi}", [( 0.57, y0), ( 1.35, y0), ( 1.35, y1), ( 0.57, y1)],
                      "seam", plane="side", surface=H, side=1, depth=0.025, chamfer=0.006)

# ── inset panels on front face — break up the large empty strips ──────────────
# plane="front" uses (u=x, v=y); surface=-H (front face at z=-H); side=-1 (outward -Z)
with a.mirror("Z"):
    # Upper strip (y=1.96..2.40)
    P.inset_panel(a, "Body", "FrontPUL", [(-1.2, 1.96), (-0.12, 1.96), (-0.12, 2.40), (-1.2, 2.40)],
                  "seam", plane="front", surface=-H, side=-1, depth=0.03, chamfer=0.010)
    P.inset_panel(a, "Body", "FrontPUR", [(0.12, 1.96), (1.2, 1.96), (1.2, 2.40), (0.12, 2.40)],
                  "seam", plane="front", surface=-H, side=-1, depth=0.03, chamfer=0.010)
    # Middle right — right half of middle plank (y=0.95..1.85, x=0.12..1.2)
    P.inset_panel(a, "Body", "FrontPMR", [(0.12, 0.95), (1.2, 0.95), (1.2, 1.85), (0.12, 1.85)],
                  "seam", plane="front", surface=-H, side=-1, depth=0.03, chamfer=0.010)
    # Lower-left strip (y=0.06..0.82)
    P.inset_panel(a, "Body", "FrontPLL", [(-1.2, 0.06), (-0.12, 0.06), (-0.12, 0.82), (-1.2, 0.82)],
                  "seam", plane="front", surface=-H, side=-1, depth=0.03, chamfer=0.010)

# ── inset panels on the lid — 3×2 grid, gaps at z=±0.7 for SeamTopX ─────────
# left half: 3 panels (z from -1.08 to -0.75 | -0.65 to -0.07 | +0.07 to +1.08)
# keeping 0.10 gap around SeamTopX at z=-0.7 and +0.7
P.inset_panel(a, "Body", "LidL1", [(-1.35, -1.08), (-0.12, -1.08), (-0.12, -0.75), (-1.35, -0.75)],
              "seam", plane="top", surface=S, side=1, depth=0.04, chamfer=0.010)
P.inset_panel(a, "Body", "LidL2", [(-1.35, -0.65), (-0.12, -0.65), (-0.12, -0.07), (-1.35, -0.07)],
              "seam", plane="top", surface=S, side=1, depth=0.04, chamfer=0.010)
P.inset_panel(a, "Body", "LidL3", [(-1.35,  0.07), (-0.12,  0.07), (-0.12,  0.65), (-1.35,  0.65)],
              "seam", plane="top", surface=S, side=1, depth=0.04, chamfer=0.010)
P.inset_panel(a, "Body", "LidL4", [(-1.35,  0.75), (-0.12,  0.75), (-0.12,  1.08), (-1.35,  1.08)],
              "seam", plane="top", surface=S, side=1, depth=0.04, chamfer=0.010)
# right half: same layout
P.inset_panel(a, "Body", "LidR1", [(0.12, -1.08), (1.35, -1.08), (1.35, -0.75), (0.12, -0.75)],
              "seam", plane="top", surface=S, side=1, depth=0.04, chamfer=0.010)
P.inset_panel(a, "Body", "LidR2", [(0.12, -0.65), (1.35, -0.65), (1.35, -0.07), (0.12, -0.07)],
              "seam", plane="top", surface=S, side=1, depth=0.04, chamfer=0.010)
P.inset_panel(a, "Body", "LidR3", [(0.12,  0.07), (1.35,  0.07), (1.35,  0.65), (0.12,  0.65)],
              "seam", plane="top", surface=S, side=1, depth=0.04, chamfer=0.010)
P.inset_panel(a, "Body", "LidR4", [(0.12,  0.75), (1.35,  0.75), (1.35,  1.08), (0.12,  1.08)],
              "seam", plane="top", surface=S, side=1, depth=0.04, chamfer=0.010)

# ── metal frames on all four faces ─────────────────────────────────────────────
with a.mirror("Z"):
    P.frame(a, "FrameF", (S + 0.1, S + 0.1), (0, H, -H), "metal", thickness=0.32, depth=0.12, facing="-Z")
    # diagonal brace on front face
    a.box("Brace", (3.25, 0.28, 0.1), (0, H, -H - 0.05), "metal", rot=(0, 0, 45))
    # corner bolts at frame junctions
    P.bolts(
        a, "BoltF",
        [(x, y, -H - 0.12) for x in (-1.36, 1.36) for y in (0.16, S - 0.16)],
        "seam", facing="-Z", radius=0.09,
    )
    # mid-height bolts on both frame bar faces
    P.bolts(a, "BoltFMidR", [(1.41, y, -H - 0.12) for y in (1.0, 2.0)], "metal", facing="-Z", radius=0.07)
    P.bolts(a, "BoltFMidL", [(-1.41, y, -H - 0.12) for y in (1.0, 2.0)], "metal", facing="-Z", radius=0.07)
    # latch: pushed slightly into body (z=-H+0.01) so it overlaps
    P.latch(a, "Latch", (0.0, S - 0.42, -H + 0.01), "metal", facing="-Z", size=(0.14, 0.24))

with a.mirror("X"):
    P.frame(a, "FrameS", (S + 0.1, S + 0.1), (H, H, 0), "metal", thickness=0.32, depth=0.12, facing="+X")
    # Horizontal grooves on FrameS top/bottom bar faces (detail in side-view edge strips)
    # FrameSTop center: x=H+0.06, y=H + (S+0.1)/2 - 0.32/2 = 1.56, 1.5+1.55-0.16=2.89, z=0
    # Seam lines on FrameS top/bottom bar faces to break up the smooth metal strip
    # FrameSTop visible face is at x=H+0.12=1.62, y≈2.89; bar spans z=-1.55..+1.55
    Hx = H + 0.12   # outer face x-coord of FrameS bars
    Ytop = H + (S + 0.1) / 2 - 0.32 / 2  # FrameSTop center y = 2.89
    Ybot = H - (S + 0.1) / 2 + 0.32 / 2  # FrameSBottom center y = 0.11
    Zspan = (S + 0.1) / 2                  # z half-span = 1.55
    # Two seams on FrameSTop: centre and lower edge
    P.panel_line(a, "FrameSTop", "FSTSeamA", (Hx, Ytop,        -Zspan), (Hx, Ytop,        Zspan), "seam", width=0.04, depth=0.06, facing="+X")
    P.panel_line(a, "FrameSTop", "FSTSeamB", (Hx, Ytop - 0.10, -Zspan), (Hx, Ytop - 0.10, Zspan), "seam", width=0.04, depth=0.06, facing="+X")
    # Two seams on FrameSBottom
    P.panel_line(a, "FrameSBottom", "FSBSeamA", (Hx, Ybot,        -Zspan), (Hx, Ybot,        Zspan), "seam", width=0.04, depth=0.06, facing="+X")
    P.panel_line(a, "FrameSBottom", "FSBSeamB", (Hx, Ybot + 0.10, -Zspan), (Hx, Ybot + 0.10, Zspan), "seam", width=0.04, depth=0.06, facing="+X")

# ── handles — eye-brackets with seated rope U-handles ─────────────────────────
with a.mirror("X"):
    # Bracket plates: x from H-0.01 to H+0.09 (overlaps body), bevel for chamfered edges
    a.box("BracketA", (0.10, 0.30, 0.24), (H + 0.04, 2.1, -0.55), "metal", bevel=0.015)
    a.box("BracketB", (0.10, 0.30, 0.24), (H + 0.04, 2.1,  0.55), "metal", bevel=0.015)
    # Mounting bolts through each bracket into body
    P.bolts(a, "BrktBolt", [(H + 0.12, 2.1, z) for z in (-0.55, 0.55)], "metal", facing="+X", radius=0.065)
    # Handle tube: endpoints at x=H+0.09 → inset at -0.07 = x=H+0.02 (inside bracket/body)
    P.handle(a, "Handle", (H + 0.09, 2.1, -0.55), (H + 0.09, 2.1, 0.55), "rope", radius=0.07, lift=0.28, facing="+X")

# ── stencil on front face ──────────────────────────────────────────────────────
# Lower plank right half: y=0.50 (between bottom frame bar y≈0.27 and first seam at y=0.9).
# x=0.5 (right of centre). At y=0.5 the diagonal brace is at x≈-1.0, nowhere near the text.
# Width ≈ 1.28 studs → spans x=-0.14..1.14 (clear of right frame bar at x≈1.39).
a.text("Stencil", "SUPPLIES 07", (0.50, 0.50, -H - 0.005), "stencil",
       size=0.20, facing="-Z", up="+Y", depth=0.01)

a.build()
