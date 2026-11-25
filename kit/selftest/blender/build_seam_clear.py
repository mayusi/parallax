"""build_seam_clear.py — POSITIVE fixture: a slide that sits CLEAR in a slot of its frame, the frame made of two
blocks that share a face exactly (a seam made on one raster, as rbx_trace.region(minus=...) makes them). Rays from the
slide cross that seam where one block ends and the next begins; counted as one crossing, the parity flipped and a
clear part read as buried (the Gjallarhorn's drum, 2026-10-06). Must NOT be flagged: mechanism.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_seam", tex=64, size=(1.0, 2.0, 2.0))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
# two big blocks sharing the face x = 0; the slot ends 0.05 short of it, so most rays from the slide reach the seam
a.box("FrameLeft", (0.5, 2.0, 2.0), (-0.25, 1.0, 0), "body", bevel=0)  # x -0.5 .. 0
a.box("FrameRight", (0.5, 2.0, 2.0), (0.25, 1.0, 0), "body", bevel=0)  # x 0 .. 0.5: the SAME face at x = 0
a.cut("FrameLeft", a.box("SlotCut", (0.5, 0.2, 0.2), (-0.3, 1.0, 0), "trim", bevel=0))  # x -0.55 .. -0.05, open at -0.5
a.box("Slide", (0.4, 0.16, 0.16), (-0.3, 1.0, 0), "trim", bevel=0, group="slide")  # x -0.5 .. -0.1: clear all round
a.joint("Slide", "slide", "slide", axis=(-1, 0, 0), max=0.2)
a.build()
