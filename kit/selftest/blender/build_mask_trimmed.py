"""build_mask_trimmed.py — NEGATIVE fixture (card yp3e): a part laid into a trim sheet (a.trim) takes the sheet's
finish and bakes nothing of its own, so a placed mask named on it would never be laid - the build must STOP and say
so, by the mask's and the part's names. Needs build_trim_sheet.py built first. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_mask_trimmed", tex=64, size=(8.0, 4.0, 1.0), ground=True)
a.material("any", color=(0.5, 0.5, 0.5), rough=0.7,
           layers=[rbx.layer("soot", where="mask:stripe", amount=1.0, breakup=0.0)])
a.box("Panel", (8.0, 4.0, 1.0), (4.0, 2.0, 0.5), "any", bevel=0)
a.trim("Panel", "_selftest_trim_sheet", "planks", along=(1, 0, 0))
a.mask("stripe", keep=lambda p: p[1] > 2.0, parts=["Panel"])
a.build()
