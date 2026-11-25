"""build_pbr_ok.py — POSITIVE fixture: the same kind of object in values a real surface has — finishes and measured
materials (rbx.finish / rbx.real): a parkerized frame (a coating: metal 0), a bare iron slide, cast bronze, black
rubber (measured tyre, 42 sRGB), a chipped painted part over the default bare steel, a satin cloth (satin=True: a
partial metalness on purpose) and a stylised toy-gold badge opted out (pbr=False). Must NOT be named: pbr_values.
Used by `lune run kit selftest`."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_pbr_ok", tex=64, size=(0.4, 0.62, 1.6), ground=False)
a.material("frame", **rbx.finish("gunmetal_parkerized"))
a.material("slide", **rbx.real("Iron", rough=0.4))
a.material("bronze", **rbx.finish("cast_bronze"))
a.material("rubber", **rbx.finish("rubber"))
a.material("paint", **rbx.finish("painted_metal", color=(0.3, 0.05, 0.04)), chip=0.3)
a.material("cloth", (0.35, 0.3, 0.4), metal=0.4, rough=0.5, satin=True)
a.material("toy_gold", (1.0, 0.85, 0.0), metal=0.5, rough=0.2, pbr=False)  # stylised on purpose
a.box("Frame", (0.4, 0.3, 1.6), (0, 0.15, 0), "frame", bevel=0)
a.box("Slide", (0.36, 0.2, 1.4), (0, 0.4, 0), "slide", bevel=0)
a.box("Pad", (0.3, 0.06, 0.3), (0, 0.53, 0.4), "rubber", bevel=0)
a.box("Ring", (0.3, 0.06, 0.2), (0, 0.53, -0.3), "bronze", bevel=0)
a.box("Panel", (0.02, 0.2, 0.6), (0.21, 0.15, 0), "paint", bevel=0)
a.box("Strap", (0.02, 0.2, 0.4), (-0.21, 0.15, 0.3), "cloth", bevel=0)
a.box("Badge", (0.02, 0.15, 0.2), (-0.21, 0.15, -0.3), "toy_gold", bevel=0)
a.build()
