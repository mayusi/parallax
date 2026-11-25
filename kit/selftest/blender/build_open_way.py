"""build_open_way.py — POSITIVE fixture for A NAMED OPENING (a.open_way, rbx_through; the owner's limitations page,
D-R12): a block with a square bore cut right through it, and the bore NAMED as a way that must stay open. The build
looks down it on the parts and on the exported mesh: open both times ("openings: 2 open" - the second, "Port", is a
round hole across the block, named inside a turned frame: it is only open if the way is read in that frame). With
the argument
`plugged` after `--` a plug is left standing in the bore (build_open_way_plugged.py): the build must fail
`open_ways`, naming the opening and the plug. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

PLUGGED = "plugged" in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else False

a = rbx.Asset("_selftest_open_way_plugged" if PLUGGED else "_selftest_open_way", tex=64, size=(2.0, 1.0, 4.0),
              ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.box("Block", (2.0, 1.0, 4.0), (0, 0.5, 0), "iron", bevel=0)
a.cut("Block", a.box("BoreCut", (0.5, 0.5, 4.4), (0, 0.5, 0), "iron", bevel=0), through=True)
if PLUGGED:   # a plug left in the middle of the bore, touching its walls
    a.box("Plug", (0.5, 0.5, 0.3), (0, 0.5, 0.6), "iron", bevel=0)
a.open_way("Bore", (0, 0.5, -2.2), (0, 0.5, 2.2), 0.5)
# a round port ACROSS the block (along X) at z = -1.2, cut and named inside a frame turned a quarter about Y
a.cut("Block", a.cylinder("PortCut", 0.15, 2.4, (0, 0.5, -1.2), "iron", axis="X", segments=16), through=True)
with a.frame(pos=(0, 0.5, -1.2), rot=(0, 90, 0)):
    a.open_way("Port", (0, 0, -1.2), (0, 0, 1.2), 0.3)        # the frame's own Z runs along the model's X
a.build()
