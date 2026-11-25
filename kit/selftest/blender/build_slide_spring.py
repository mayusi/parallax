"""build_slide_spring.py — POSITIVE fixture for SOFT parts in the mechanism gate: a slide racking back into its recoil
spring (a part named ...Spring) compresses it — the mechanism working, as a pistol's does: must NOT be named:
mechanism. Its twin (KIT_SLIDE_SPRING=steel: the same block named RecoilStop, solid) is a jam and must be named.
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

variant = os.environ.get("KIT_SLIDE_SPRING", "ok")
a = rbx.Asset(f"_selftest_slide_spring_{variant}", tex=64, size=(1.0, 0.3, 0.3), ground=False)
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Frame", (1.0, 0.1, 0.3), (0, 0.05, 0), "body", bevel=0)                             # (y 0 .. 0.1)
a.box("Slide", (0.4, 0.15, 0.2), (-0.25, 0.175, 0), "trim", bevel=0, group="slide")        # (x -0.45 .. -0.05, on it)
a.cylinder("RecoilSpring" if variant == "ok" else "RecoilStop", 0.06, 0.3, (0.2, 0.17, 0), "body", axis="X")
a.joint("Slide", "slide", "slide", axis=(1, 0, 0), max=0.25)                               # (racks into it 0.2)
a.build()
