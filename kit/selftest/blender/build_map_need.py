"""build_map_need.py — POSITIVE fixture: a hero MASTER slab (1.0 x 0.1 x 1.7 m: 3.9 square metres of surface)
whose script names NO map size. At a master's usual 2048 no layout of it reaches the 1028 px a metre a hero piece
needs (2048 px over almost four square metres). The build sizes its map by the need: its summary must say
"maps by need: main 4096" (read off the baked file), and texel_bar must NOT be named.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_map_need", size=(10.0, 1.0, 17.0), quality="hero", stage="master", stage_gate=False)
a.real_scale(100.0)
a.material("steel", color=(0.5, 0.5, 0.52))
a.box("Slab", (10.0, 1.0, 17.0), (0, 0, 0), "steel", bevel=0.02)
a.build()
