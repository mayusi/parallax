"""build_sheetgun.py — the fixture of the model sheet and the blockout (kit/tools/sheet.py, kit/tools/blockout.py): a
small block blaster in a project of its own (kit/selftest/sheet/: its brief, its side trace, its reference picture —
drawn from these same numbers, 100 px a stud, its LEFT side with the front on the left).

    lune run kit sheet sheetgun --root kit/selftest/sheet --out <file.png>        the sheet (kit selftest draws it)
    KIT_BUILD=<a scratch folder> blender -b --factory-startup --python-exit-code 2 \
        -P kit/selftest/sheet/assets/models/build_sheetgun.py -- --geo --blockout  the blockout round (a SMOKE run:
    python kit/tools/blockout.py sheetgun --root kit/selftest/sheet --build <that folder> --out <file.png>   pictures)
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
a = rbx.Asset("sheetgun", tex=64, ground=False)  # (its brief says complex: it builds at the prop gates)
a.trace_match(os.path.join(HERE, "sheetgun_side.trace.json"), view="side", bar=0.9, lines=False)
a.material("body", (0.18, 0.19, 0.22), metal=0.4, rough=0.5, wear=0.2)
a.material("steel", (0.55, 0.57, 0.6), metal=1.0, rough=0.35)
a.material("grip", (0.12, 0.12, 0.13), rough=0.8)
a.material("glow", (0.1, 0.8, 0.95), rough=0.2, emit=3)
a.material("badge", (0.85, 0.08, 0.06), rough=0.6)
a.box("Body", (0.4, 0.5, 1.6), (0, 0.75, 0.2), "body", bevel=0.03)
a.box("Glow", (0.42, 0.08, 0.9), (0, 0.78, 0.25), "glow", bevel=0)
a.box("Badge", (0.03, 0.12, 0.12), (-0.205, 0.66, 0.36), "badge", bevel=0)  # on the LEFT face (-x) only
a.cylinder("Barrel", 0.09, 1.4, (0, 0.8, -1.3), "steel", axis="Z")
a.cylinder("Muzzle", 0.12, 0.12, (0, 0.8, -2.0), "steel", axis="Z")
a.box("Grip", (0.3, 0.57, 0.32), (0, 0.205, 0.75), "grip", bevel=0.02, group="grip")  # y -0.08 .. 0.49
a.joint("Grip", "grip", "slide", axis=(0, -1, 0), max=0.4)
a.build()
