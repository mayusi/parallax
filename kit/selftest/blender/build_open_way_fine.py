"""build_open_way_fine.py — a MASTER for the named opening's EXPORT pass (a.open_way, rbx_through; the review of
D-R12): a block with a FINE round bore (0.12 studs across, 600 sides) named open. As a master it builds with the bore
open. Built as its GAME version with a retopology (`--optimize --budget=400 --retopo`) the rebuilt surface loses
the bore: the parts were open, the exported mesh is not - the build must FAIL `open_ways` there (a game version is
blocked by it: its master never sees the reduction). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_open_way_fine", tex=64, size=(2.0, 2.0, 4.0), ground=True, stage="master")
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.box("Block", (2.0, 2.0, 4.0), (0, 1.0, 0), "iron", bevel=0)
a.cut("Block", a.cylinder("BoreCut", 0.06, 4.4, (0, 1.0, 0), "iron", axis="Z", segments=600), through=True)
a.open_way("FineBore", (0, 1.0, -2.2), (0, 1.0, 2.2), 0.1)
a.build()
