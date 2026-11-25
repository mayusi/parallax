"""build_maker.py — fixture: a.maker() reads a maker's design language (KIT_MAKER_DIR, written by
kit/test/python/test_design_maker.py) and records it in the facts; a box built to its edge radius. Never "fix"
this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_maker", tex=256, size=(0.2, 0.2, 0.2), ground=False, allow_floating=["Block"])
a.real_scale(280.0)
lang = a.maker("Brightwind", folder=os.environ["KIT_MAKER_DIR"])
a.material("brass", (0.7, 0.5, 0.2), metal=1.0, rough=0.3)
a.box("Block", (0.1, 0.1, 0.1), (0, 0, 0), "brass", bevel=lang["radius_mm"] / 280.0)
a.build()
