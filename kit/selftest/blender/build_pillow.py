"""build_pillow.py — fixture: a.pillow() inflates traced outlines into SCULPTED plate parts: a 40 mm disc domed both
sides (core 1, h 3, edge 4, crown 0.5), an L-shaped panel with a hole domed on one side only (a grip on a frame, ZY
plane, its back at x = 2 mm), and a strip 3 mm wide — thinner than 2 x edge, so a round top; the L zoned (its left 20 mm 3 mm thicker each side); a small square
RIDING on the disc's dome (sitting 0.3 mm into it, not floating); a one-sided gold TRIM, a curved band 1 mm wide
(all outline samples: its flat back once came out with 20 open edges); a rider running 10 mm PAST the disc's
edge (the part off the host keeps the nearest height, never its flat back); a rider given SEVERAL hosts (only the
disc lies under it) sits on the disc's other face. kit/test/python/test_pillow.py reads
facts.pillow[]. Never "fix" this file."""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

DISC = [(20 * math.cos(2 * math.pi * k / 96), 20 * math.sin(2 * math.pi * k / 96)) for k in range(96)]
L_SHAPE = [(0, 0), (60, 0), (60, 12), (20, 12), (20, 30), (0, 30)]
HOLE = [(6 + 3 * math.cos(-2 * math.pi * k / 32), 6 + 3 * math.sin(-2 * math.pi * k / 32)) for k in range(32)]
STRIP = [(0, 0), (50, 0), (50, 3), (0, 3)]
a = rbx.Asset("_selftest_pillow", tex=256, size=(0.65, 0.18, 0.23), ground=False,
              allow_floating=["Disc", "Panel", "Strip", "Zoned", "Rider", "Trim", "Overhang", "Rider2"])
a.real_scale(280.0)
a.material("black", (0.04, 0.04, 0.045), rough=0.4)
a.pillow("Disc", DISC, "black", core=1.0, h=3.0, edge=4.0, top=0.5, pos=(-0.2, 0, 0), group="disc")
a.pillow("Panel", L_SHAPE, "black", core=0.6, h=2.0, edge=2.4, holes=[HOLE], side="+", plane="ZY", base=2.0,
         pos=(0.0, 0, 0), group="panel")
a.pillow("Strip", STRIP, "black", core=0.0, h=2.0, edge=2.5, pos=(0.2, 0, 0), group="strip")
a.pillow("Zoned", L_SHAPE, "black", core=1.0, h=1.0, edge=1.0, pos=(0.0, -0.06, 0), group="panel",
         zones=[{"outline": [(0, 0), (20, 0), (20, 30), (0, 30)], "core": 3.0, "blend": 1.0}])
a.pillow("Rider", [(-4, -4), (4, -4), (4, 4), (-4, 4)], "black", core=0.0, h=0.8, edge=0.8, side="+", ride="Disc",
         sink=0.3, pos=(-0.2, 0, 0), group="disc")
a.pillow("Overhang", [(12, -3), (30, -3), (30, 3), (12, 3)], "black", core=0.0, h=0.8, edge=0.8, side="+",
         ride="Disc", sink=0.3, pos=(-0.2, 0, 0), group="disc")   # (runs 10 mm past the disc's edge)
a.pillow("Rider2", [(-4, -4), (4, -4), (4, 4), (-4, 4)], "black", core=0.0, h=0.8, edge=0.8, side="-",
         ride=["Strip", "Disc"], sink=0.3, pos=(-0.2, 0, 0), group="disc")   # (several hosts: the one under it wins)
TRIM = ([(15 * math.cos(a), 15 * math.sin(a)) for a in (0.2 + 2.4 * k / 39 for k in range(40))]
        + [(14 * math.cos(a), 14 * math.sin(a)) for a in (2.6 - 2.4 * k / 39 for k in range(40))])
a.pillow("Trim", TRIM, "black", core=0.0, h=0.85, edge=0.5, side="+", pos=(0.2, -0.06, 0), group="strip")
a.build()
