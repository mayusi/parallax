"""build_library_match_off.py — NEGATIVE fixture: a model missing a part its REFERENCE MODEL has. Must be named:
reference_side. Never "fix" this file.
The same reference as build_library_match_ok.py (a library model's side and front outlines, made by kit refs measure
from kit/selftest/refs/_library_pistol.glb) — this model has the body but NO grip: against a library model's views it
must fail exactly as it would against a traced photo. Used by `lune run kit selftest`.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

REFS = os.path.join(_root, "kit", "selftest", "refs")
a = rbx.Asset("_selftest_library_match_off", tex=64, size=(0.30, 0.35, 2.0))
a.real_scale(100.0)
a.material("body", color=(0.5, 0.5, 0.52))
a.box("Body", (0.30, 0.35, 2.0), (0, 0, 0), "body", bevel=0)
for view in ("side", "front"):
    a.trace_match(os.path.join(REFS, f"_library_pistol_{view}.trace.json"), view=view)
a.build()
