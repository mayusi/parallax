"""build_sharp_edges_ok.py — POSITIVE fixture: the same hero slide with its edges bevelled (a.box bevel=), and a CAD
part whose fillet OpenCASCADE REFUSES outright (a 20 mm fillet on a 10 mm thick plate): a.cad bevels its still-sharp
edges on the mesh instead (cad[].bevel_fallback_mm). Must NOT be named: sharp_edges. Never "fix" this file. Used by
`lune run kit selftest` (needs the cad env).
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_bevel_ok", tex=64, size=(0.6, 0.6, 2.0), quality="hero", stage_gate=False)
a.real_scale(100.0)
a.material("steel", color=(0.5, 0.5, 0.52))
a.box("Slide", (0.30, 0.35, 2.0), (0, 0, 0), "steel", bevel=0.012)  # 1.2 mm rounded edges
a.cad("Plate", "with BuildPart() as part:\n    Box(30, 10, 30)\n    fillet_soft(part.edges(), 20)\n", "steel",
      pos=(0, 0.225, 0))
a.build()
