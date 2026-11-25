"""build_gem_glass.py — fixture: a P.gem stone (a sapphire, IOR 1.77) set on a plate. kit/test/python/test_gem_glass.py
builds it, then runs rbx_parts.glass_gems on the saved .blend the way the showcase does: the stone's faces (and only
those) get a refracting twin of their material. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("_selftest_gem_glass", tex=256, size=(0.2, 0.06, 0.2), ground=False, allow_floating=["Stone"])
a.real_scale(280.0)
a.material("steel", (0.55, 0.55, 0.57), metal=1.0, rough=0.3)
a.material("blue", (0.05, 0.12, 0.6), rough=0.1, emit=0.9)
a.box("Plate", (0, 0, 0), (0.2, 0.02, 0.2), "steel")
P.gem(a, "Stone", (0, 0.01, 0), 0.05, "blue", facing="+Y", ior="sapphire")
a.build()
