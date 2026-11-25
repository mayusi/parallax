"""build_library_match_ok.py — POSITIVE fixture: a model matched against a REFERENCE MODEL's views. Must NOT be named:
reference_side, reference_front. Never "fix" this file.
kit/selftest/refs/_library_pistol.glb is a staged 'library model' (a 200 mm body and grip in its author's units, on a
backdrop, a tool lying apart); its side and front outlines (kit/selftest/refs/_library_pistol_<view>.trace.json) were
made by the real pipeline: `lune run kit refs measure kit/selftest/refs/_library_pistol.glb --name _library_pistol
--length-mm 200` (the backdrop and the tool left out). This model is the same body and grip: a.trace_match takes a
library model's views like any traced picture. Used by `lune run kit selftest`.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

REFS = os.path.join(_root, "kit", "selftest", "refs")
a = rbx.Asset("_selftest_library_match_ok", tex=64, size=(0.30, 1.15, 2.0))
a.real_scale(100.0)  # 1 stud = 100 mm: the body 200 mm long, like the reference model
a.material("body", color=(0.5, 0.5, 0.52))
a.box("Body", (0.30, 0.35, 2.0), (0, 0, 0), "body", bevel=0)
a.box("Grip", (0.28, 0.80, 0.30), (0, -0.575, 0.70), "body", bevel=0)  # at the BACK: a kit model faces -Z (Roblox)
for view in ("side", "front"):
    a.trace_match(os.path.join(REFS, f"_library_pistol_{view}.trace.json"), view=view)
a.build()
