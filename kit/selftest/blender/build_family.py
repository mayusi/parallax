"""build_family.py - fixture for A FAMILY OF MODULES THAT SNAP (a.module(grid, family=), rbx_family, kit family; the
3D methods audit's PARTLY "a family of parts that snap to each other (dovetail joints, hallway tiles)").
A hall on a 4-stud grid, one module a run (after `--`):
  Straight  a floor and two walls 0.5 thick: its two open ends (+X, -X) are one U-shaped cut - it meets itself
  End       the same, closed at +X by a back wall: its -X end meets Straight; its +X is a full wall
  Bad       walls 0.6 thick: its ends ALMOST meet Straight's - the seam a player sees, `kit family` must fail it
And a second family, walls whose DEPTH the grid leaves free (a.module((4, 4, 0))): WallA 0.5 deep, WallB 0.7 deep -
their ends ALMOST meet (review 2026-11-17: a free depth compared as "different", never as the seam it is).
Used by kit/test/python/test_family_build.py. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
WHICH = next((a_ for a_ in args if a_ in ("Straight", "End", "Bad", "WallA", "WallB")), "Straight")
T = 0.6 if WHICH == "Bad" else 0.5
if WHICH in ("WallA", "WallB"):
    D = 0.5 if WHICH == "WallA" else 0.7
    a = rbx.Asset(f"_selftest_wall_{WHICH}", tex=64, size=(4.0, 4.0, D))
    a.material("stone", (0.45, 0.44, 0.42), rough=0.85)
    a.module((4, 4, 0), family="SelftestWall")
    a.box("Wall", (4.0, 4.0, D), (2.0, 2.0, 0.0), "stone", bevel=0)
    a.build()
    raise SystemExit(0)

a = rbx.Asset(f"_selftest_hall_{WHICH}", tex=64, size=(4.0, 4.0, 4.0))
a.material("stone", (0.45, 0.44, 0.42), rough=0.85)
a.module((4, 4, 4), family="SelftestHall")
a.box("Floor", (4.0, 0.5, 4.0), (2.0, 0.25, 2.0), "stone", bevel=0)
a.box("WallL", (4.0, 4.0, T), (2.0, 2.0, T / 2), "stone", bevel=0)
a.box("WallR", (4.0, 4.0, T), (2.0, 2.0, 4.0 - T / 2), "stone", bevel=0)
if WHICH == "End":
    a.box("Back", (0.5, 4.0, 4.0), (3.75, 2.0, 2.0), "stone", bevel=0)
a.build()
