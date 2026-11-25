"""build_sweep_twist.py — fixture for A TWISTED SWEEP CUT OPEN ON ITS OWN (LIMITATIONS_FIXES_V4 Phase 1, 3D-X: rbx.Asset.
sweep, SWEEP_SEAM): a flat bar twisted two whole turns standing on a slab, and a six-sided rope twisted three turns
lying on it. A section turned more than half a turn about its path is a helicoid: the automatic unwrap laid the bar out
stretched (8.8% of it over 2x longer than wide - uv_stretch failed). The build must cut both open along their seam
line (facts.sweeps[].cut_open, facts.seams_placed) and its map must stretch nothing past the bar. With the cut off
(KIT_SWEEP_CUT=0) the same build fails uv_stretch (each twisted part is its own group: the stretch is measured on
it). Used by kit/test/python/test_sweep_cut.py. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_sweep_twist", tex=512, size=(2.0, 1.8, 2.0), ground=True)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("hemp", color=(0.55, 0.45, 0.28), rough=0.8)
a.box("Slab", (2.0, 0.2, 2.0), (0, 0.1, 0), "iron", bevel=0.02)
a.sweep("Bar", [(0.4, 0.2, 0.4), (0.4, 1.8, 0.4)], [(-0.16, -0.05), (0.16, -0.05), (0.16, 0.05), (-0.16, 0.05)],
        "iron", twist=720, group="bar")
a.sweep("Rope", [(-0.8, 0.26, -0.6), (-0.3, 0.26, -0.2), (0.3, 0.26, -0.5)], 0.06, "hemp", sides=6, twist=1080, group="rope")
a.build()
