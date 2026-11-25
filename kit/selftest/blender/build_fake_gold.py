"""build_fake_gold.py — a material NAMED like a real substance that looks nothing like it: "gold" that is grey plastic
(and "brass" that is not a metal). The selftest requires the material_values warning: a name promises the measured
colour and metalness (rbx.real, physicallybased.info). Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_fake_gold", size=(1, 1, 1), symmetric=True)
a.material("gold", (0.45, 0.45, 0.47), metal=0.0, rough=0.6)  # grey plastic, called gold
a.material("brass", (0.91, 0.78, 0.42), metal=0.0, rough=0.5)  # the right colour, but not a metal
a.box("Body", (1, 0.6, 1), (0, 0.3, 0), "gold")
a.box("Lid", (1, 0.2, 1), (0, 0.7, 0), "brass")
a.build()
