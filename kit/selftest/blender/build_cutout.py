"""build_cutout.py — POSITIVE fixture for CUT-OUTS (a.cutout, rbx_cutout): on a base slab, a grille (one upright
sheet of faces, given its back, its bars cut by a RULE), a leaf (a sheet cut by a rule to a pointed oval) and a
round sign (a square sheet cut by a PICTURE of a disc). The
geometry stays plain sheets: the colour map's alpha says where they show. Its summary must say how much of each
map is cut away ("cut out: ..."), and its manifest must mark the group for Roblox's cut-out mode. Used by `lune
run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_cutout", size=(3.0, 1.2, 1.4), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("black", color=(0.06, 0.06, 0.07), metal=1.0, rough=0.4)
a.material("leaf", color=(0.2, 0.45, 0.16), rough=0.6)
a.box("Base", (3.0, 0.2, 1.4), (0, 0.1, 0), "iron", bevel=0.02)
# a grille: an upright sheet 1.2 wide, 1.0 tall - six bars and a frame, cut by a rule
a.mesh("Grille", [(-1.3, 0.2, 0.0), (-0.1, 0.2, 0.0), (-0.1, 1.2, 0.0), (-1.3, 1.2, 0.0)], [(0, 1, 2, 3)], "black",
       group="cut")
a.two_sided("Grille")
a.cutout("Grille", keep=lambda p: ((p[0] + 1.3) % 0.2) < 0.07 or p[1] < 0.27 or p[1] > 1.13
         or p[0] < -1.23 or p[0] > -0.17)
# a leaf: a sheet 1.0 long, 0.5 wide, lying a little above the base - a pointed oval of it stays
a.mesh("Leaf", [(0.4, 0.45, -0.25), (1.4, 0.45, -0.25), (1.4, 0.45, 0.25), (0.4, 0.45, 0.25)], [(0, 1, 2, 3)],
       "leaf", group="cut")
a.two_sided("Leaf")
a.cutout("Leaf", keep=lambda p: abs(p[2]) < 0.25 * (1 - (2 * (p[0] - 0.9)) ** 2))
a.box("Stem", (0.04, 0.26, 0.04), (0.9, 0.32, 0), "iron", bevel=0)
# a sign: an upright square sheet cut by a PICTURE (a disc, drawn here into the build folder: solid where it has
# alpha) - a round sign from four points
import bpy  # noqa: E402
import numpy as np  # noqa: E402

side = 64
yy, xx = np.mgrid[0:side, 0:side]
disc = np.zeros((side, side, 4), np.float32)
disc[..., 3] = ((xx - 31.5) ** 2 + (yy - 31.5) ** 2 <= 30.0 ** 2).astype(np.float32)
pic = bpy.data.images.new("_selftest_cutout_disc", side, side, alpha=True)
pic.pixels.foreach_set(disc.ravel())
pic.filepath_raw = os.path.join(rbx.RENDERS, "_selftest_cutout_disc.png")
pic.file_format = "PNG"
os.makedirs(rbx.RENDERS, exist_ok=True)
pic.save()
a.mesh("Sign", [(0.1, 0.2, -0.5), (0.1, 0.2, -0.1), (0.1, 0.6, -0.1), (0.1, 0.6, -0.5)], [(0, 1, 2, 3)], "black",
       group="cut")
a.two_sided("Sign")
a.cutout("Sign", picture=pic.filepath_raw)
a.build()
