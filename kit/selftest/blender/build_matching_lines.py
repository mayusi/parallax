"""build_matching_lines.py — POSITIVE fixture for the INTERNAL LINES check (kit/vision/lines.py): the same box as
build_missing_lines.py, WITH the reference's (lines_ref.png) vertical groove, panel seam and slot cut where the picture
has them. Must NOT be flagged "missing lines" — a lines check that flags a correct model is as broken as one that
misses a wrong one. Used by `lune run kit selftest`. Never "fix" this file.

Where the picture's features land (lines_ref.png: the box spans x 56..455, y 40..159 px; the side view looks along -X
with the FRONT (-Z) on the right, so u = (x - 56) / 400 -> z = 1 - 2u; y up from the box's bottom):
  groove x 214..218 -> z 0.185..0.21   seam y 98..101 -> y 0.29..0.31   slot x 300..372, y 62..84 -> z -0.58..-0.22, y 0.38..0.49
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_lines_ok", tex=64, size=(0.4, 0.6, 2.0),
              reference={"side": "kit/selftest/blender/lines_ref.png"})
a.material("body", color=(0.44, 0.45, 0.47))
a.material("dark", color=(0.08, 0.08, 0.09))
a.box("Body", (0.4, 0.6, 2.0), (0, 0.3, 0), "body", bevel=0.04)  # the picture's lit top bevel
a.cut("Body", a.box("Groove", (0.06, 0.7, 0.025), (0.2, 0.3, 0.1975), "dark", bevel=0))
a.cut("Body", a.box("Seam", (0.05, 0.02, 2.2), (0.2, 0.3025, 0), "dark", bevel=0))
a.cut("Body", a.box("Slot", (0.12, 0.11, 0.36), (0.2, 0.435, -0.4), "dark", bevel=0))
a.build()
