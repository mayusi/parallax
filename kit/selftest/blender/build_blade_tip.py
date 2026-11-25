"""build_blade_tip.py — POSITIVE fixture: a pointed blade (a feather, a sword's tip: its two edges converge at ~20
degrees and thin out to the point by design), seated on a host. The sliver gate took the converging edges for a
parallel shelf and reported the tip as a 1.1 mm sliver (the Gjallarhorn's feathers, the arming sword's tip,
2026-10-06). Must NOT be flagged: slivers. Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_blade_tip", tex=64, size=(0.08, 0.4, 0.5), ground=False)
a.real_scale(280.0)
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.6, 0.6, 0.65))
a.box("Host", (0.05, 0.4, 0.5), (0, 0, 0), "body", bevel=0)
# a 50 mm feather, 13 mm wide at the root, pointed, 3.4 mm thick, seated on the host's +X face
blade = [(0.0, 0.0232), (0.089, 0.0179), (0.179, 0.0), (0.089, -0.0179), (0.0, -0.0232)]
a.extrude("Feather", blade, 0.0121, "trim", pos=(0.025 + 0.006 - 0.0018, 0, -0.09), bevel=0.002)
a.build()
