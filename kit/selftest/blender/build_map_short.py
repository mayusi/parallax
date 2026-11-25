"""build_map_short.py — NEGATIVE fixture: a hero slab (0.55 x 0.1 x 0.8 m: 1.15 square metres of surface) whose
script asks for a 256 map. A hero piece is judged from 0.75 m, where one texel a screen pixel is 1028 px a metre; this
map gives it a fifth of that. Must be named: texel_bar (with what a larger map would give).
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_map_short", tex=256, size=(5.5, 1.0, 8.0), quality="hero", stage_gate=False)
a.real_scale(100.0)
a.material("steel", color=(0.5, 0.5, 0.52))
a.box("Slab", (5.5, 1.0, 8.0), (0, 0, 0), "steel", bevel=0.02)
a.build()
