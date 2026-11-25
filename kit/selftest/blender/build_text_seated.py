"""build_text_seated.py — POSITIVE fixture: lettering and a badge SEATED on a curved part by the kit's own a.seat —
the letters across a drum's rounded flank (a.text(..., on="Drum")) and a badge plate on its other flank (a.seat's
centre and thickness for a.extrude). The surface is measured by rays, so nothing floats over the curve and nothing is
buried in it (a Glock's moulded grip logo on its lofted grip, 2026-10-09). Must NOT be flagged: floating_parts,
plate_support. Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_text_seated", tex=64, size=(0.36, 0.36, 0.7), ground=False)
a.real_scale(100.0)
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.cylinder("Drum", 0.18, 0.7, (0, 0, 0), "body", axis="Z", segments=48, bevel=0)
# the letters on the -X flank: their height runs round the curve (the drum bends away under them)
a.text("Stamp", "SEATED", (0, 0, 0), "trim", size=0.08, facing="-X", depth=0.006, on="Drum")
# a badge plate on the +X flank: a.seat gives its centre and the thickness the curve needs
centre, thick = a.seat("Drum", (0, 0, 0), "+X", size=(0.3, 0.12), raised=0.004, sunk=0.002)
a.extrude("Badge", [(-0.15, -0.06), (0.15, -0.06), (0.15, 0.06), (-0.15, 0.06)], thick, "trim", plane="side",
          pos=centre)
a.build()
