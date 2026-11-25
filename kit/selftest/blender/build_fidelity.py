"""build_fidelity.py — POSITIVE fixture for THE GAME'S SETTINGS of a mesh (rbx_fidelity: the collision shape and
the level of detail, chosen by rule). Four groups, one of each collision shape:
    main  a crate                                   -> Box
    ball  a sphere 6 studs across                   -> Hull (its box's corners would be solid air)
    bowl  a slab with a hollow nobody stands in     -> Default
    arch  a wall with a doorway 4 wide, 6 tall      -> PreciseConvexDecomposition (a character walks through)
    gate  the same doorway in a wall half a stud thick -> PreciseConvexDecomposition (through a thin wall too)
    pile  a block with a second block sunk into it  -> Box (parts that overlap are solid, not a hollow)
The summary must say each ("in game: arch PreciseConvexDecomposition / Automatic, ..."). With the argument `closed`
after `--` the arch DECLARES a hull: the doorway would be shut, and the build must fail `collision` by name. Used by
`lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

CLOSED = "closed" in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else False

a = rbx.Asset("_selftest_fidelity_closed" if CLOSED else "_selftest_fidelity", size=(52.0, 8.0, 8.0), ground=True,
              allow_floating=["Crate", "Ball", "ArchLeft", "ArchRight", "ArchTop", "GateLeft", "GateRight",
                              "GateTop", "Pile", "PileCore"])   # (four things in a row)
a.material("stone", color=(0.5, 0.5, 0.48), rough=0.8)
a.material("wood", color=(0.42, 0.3, 0.18), rough=0.7)
a.box("Crate", (4.0, 4.0, 4.0), (-12.0, 2.0, 0), "wood", bevel=0.05)
a.sphere("Ball", 3.0, (-4.0, 3.0, 0), "stone", group="ball")
# a slab 8 x 3 x 8 with a hollow 4 x 2 x 4 sunk into its top
a.box("Bowl", (8.0, 3.0, 8.0), (4.0, 1.5, 0), "stone", group="bowl", bevel=0)
a.cut("Bowl", a.box("BowlHollow", (4.0, 2.2, 4.0), (4.0, 2.1, 0), "stone", group="bowl", bevel=0))
# a wall 6 wide (along Z), 8 tall, 2 thick with a doorway 4 wide and 6 tall, of three blocks
a.box("ArchLeft", (2.0, 8.0, 1.0), (12.0, 4.0, -2.5), "stone", group="arch", bevel=0)
a.box("ArchRight", (2.0, 8.0, 1.0), (12.0, 4.0, 2.5), "stone", group="arch", bevel=0)
a.box("ArchTop", (2.0, 2.0, 4.0), (12.0, 7.0, 0), "stone", group="arch", bevel=0)
a.box("GateLeft", (0.5, 8.0, 1.0), (18.0, 4.0, -2.5), "stone", group="gate", bevel=0)
a.box("GateRight", (0.5, 8.0, 1.0), (18.0, 4.0, 2.5), "stone", group="gate", bevel=0)
a.box("GateTop", (0.5, 2.0, 4.0), (18.0, 7.0, 0), "stone", group="gate", bevel=0)
a.box("Pile", (6.0, 6.0, 6.0), (-22.0, 3.0, 0), "wood", group="pile", bevel=0)
a.box("PileCore", (2.0, 5.0, 2.0), (-22.0, 3.0, 0), "wood", group="pile", bevel=0)
if CLOSED:
    a.collision("arch", "hull")
a.build()
