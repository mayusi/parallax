"""build_r6wear.py — fixture for R6 CLOTHES TO THE GAME'S STANDARD (LIMITATIONS_FIXES_V4 3D-X: "R6 < 4k-tri quad
clothing"; a.r6_wear + rbx_r6wear). A shirt on the R6 torso (2 x 2 x 1 studs, centred at y = 3 in the rig's frame).
By the word after `--`:
  ok    rbx_r6wear.shell: a quad-loft shell, 0.035 studs off the block's faces, 0.022 at its corners, closed rims,
        3,000 triangles. Must NOT be named: r6_tris, r6_quads, r6_closed, r6_clearance.
  soup  the Hero way (card 88sn, 1/10): a ROUND tube round the square block (its corners poke through), dense
        triangles (24,000) jittered and split by random diagonals (soup), open at both ends (the build closes its
        openings itself: r6_closed is held by the unit tests). Must be named: r6_tris, r6_quads, r6_clearance.
Used by `lune run kit selftest` and kit/test/python/test_r6wear.py. Never "fix" this file."""

import math
import random
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_r6wear as W  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = "soup" if "soup" in ARGS else "ok"

a = rbx.Asset(f"_selftest_r6wear_{HOW}", tex=256, size=(2.2, 2.0, 1.2), ground=False)
a.material("cloth", color=(0.2, 0.25, 0.4), rough=0.8)
if HOW == "ok":
    W.shell(a, "Shirt", "cloth", on="Torso", group="shirt")
else:   # (a sculpt's soup: the points jittered, each cell split by a random diagonal - no loops to pair back)
    rng = random.Random(3)
    U, V = 200, 60
    verts, faces = [], []
    for i in range(V + 1):
        for j in range(U):
            y = 2.0 + 2.0 * min(max(i + (0.45 * (rng.random() - 0.5) if 0 < i < V else 0.0), 0), V) / V
            t = 2 * math.pi * (j + 0.45 * (rng.random() - 0.5)) / U
            verts.append((1.05 * math.cos(t), y, 0.6 * math.sin(t)))
    for i in range(V):
        for j in range(U):
            p, q, r_, s = i * U + j, i * U + (j + 1) % U, (i + 1) * U + (j + 1) % U, (i + 1) * U + j
            faces += [(p, r_, q), (p, s, r_)] if rng.random() < 0.5 else [(p, s, q), (q, s, r_)]
    a.mesh("Shirt", verts, faces, "cloth", group="shirt")
a.r6_wear("shirt", on="Torso")
a.build()
