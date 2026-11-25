"""build_rough_flat.py — NEGATIVE fixture: a big painted panel at ONE roughness (no wear, grime, pattern or scan): the
"plastic" read — real surfaces vary (smudges, wear, machining marks). Measured on the baked roughness map. Must be
named: roughness_variation (a warning at every tier). Its A/B twin: build_rough_varied.py. Used by
`lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_rough_flat", tex=512, size=(3, 2.2, 0.3))
a.material("paint", **rbx.finish("painted_metal", color=(0.3, 0.32, 0.35)))  # one roughness, nothing on it
a.material("trim", **rbx.finish("polymer"))
a.box("Panel", (3, 2, 0.3), (0, 1.2, 0), "paint")
a.box("Foot", (0.3, 0.2, 0.3), (0, 0.1, 0), "trim")
a.build()
