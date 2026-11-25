"""build_plank_comb_fused.py — NOISE, carved the slyest way: 28 grooves cut by four combs, each FUSED of two
materials (a dark spine that touches nothing, steel teeth that carve). Tagging only a cutter's first material saw the
spine's faces — none — and counted one region per comb; the selftest requires the wood_grooves flag AND a score below
the clean board box (build_plank_grained.py): every material of a cutter is traced. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_plank_comb_fused", size=(2.0, 1.5, 2.0), symmetric=True, bevel=0)
a.material("wood", (0.5, 0.32, 0.17), rough=0.85, wear=0.3, grime=0.3, pattern="wood")
a.material("seam", (0.12, 0.08, 0.05), rough=0.95)
a.material("steel", (0.56, 0.57, 0.6), metal=1.0, rough=0.4)
S = 2.0
a.box("Body", (S, 1.5, S), (0, 0.75, 0), "wood", bevel=0.03)
rows = [0.12 + i * 0.2 for i in range(7)]


def comb(tag, spine_size, spine_pos, tooth_size, tooth_at):
    """a spine (seam) just off the face and one steel tooth per row reaching 0.06 into the block, fused into one cutter"""
    a.box(f"Spine{tag}", spine_size, spine_pos, "seam", bevel=0)
    teeth = []
    for i, v in enumerate(rows):
        a.box(f"Tooth{tag}{i}", tooth_size, tooth_at(v), "steel", bevel=0)
        teeth.append(f"Tooth{tag}{i}")
    return a.fuse(f"Spine{tag}", *teeth, radius=0)


for tag, z in (("F", -1.0), ("B", 1.0)):  # the front and the back (no mirror: each comb is its own)
    out = -1 if z < 0 else 1
    a.cut("Body", comb(tag, (2.2, 1.46, 0.06), (0, 0.75, z + out * 0.07), (2.2, 0.04, 0.12), lambda v, z=z: (0, v, z)))
for tag, x in (("R", 1.0), ("L", -1.0)):  # the right side and the left
    out = 1 if x > 0 else -1
    a.cut("Body", comb(tag, (0.06, 1.46, 1.96), (x + out * 0.07, 0.75, 0), (0.12, 0.04, 1.96),
                       lambda v, x=x: (x, v, 0)))
a.build()
