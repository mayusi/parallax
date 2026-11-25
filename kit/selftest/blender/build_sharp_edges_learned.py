"""build_sharp_edges_learned.py — NEGATIVE fixture: the bevel bar comes from what REAL models do (a.learned_from).
Must be named: sharp_edges. Never "fix" this file.
A hero FRAME with only its 4 long edges rounded (1 mm): ~74% of its hard edges bevelled — over the default hero bar
(50%), so without knowledge it would pass. Its knowledge (kit/selftest/refs/_learned_frames.json: two models' frames
bevel 94% and 96%, as kit learn records them) raises the bar for a part whose role is "frame" to their typical: it
must be named, with their typical bevel size. Used by `lune run kit selftest` (needs the cad env).
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_bevel_learned", tex=64, size=(0.4, 0.5, 2.1), quality="hero", stage_gate=False)
a.real_scale(100.0)
a.learned_from(os.path.join(_root, "kit", "selftest", "refs", "_learned_frames.json"))
a.material("steel", color=(0.5, 0.5, 0.52))
a.cad("Frame", "with BuildPart() as part:\n    Box(30, 40, 200)\n    fillet(part.edges().filter_by(Axis.Z), 1.0)\n",
      "steel")
a.build()
