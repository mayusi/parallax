"""build_ratchet_empty.py — the RATCHET with a broken floor: the accepted record beside this script is an empty JSON
object ({}). Read as "no floor", it silently switched the ratchet off; the selftest requires the "ratchet" error: a
floor without measurements is broken, and a broken floor fails the build. Never "fix" this file or its record."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_ratchet_empty", size=(2, 2, 2), symmetric=True)
a.material("paint", (0.5, 0.5, 0.52), rough=0.6)
a.box("Body", (2, 2, 2), (0, 1, 0), "paint")
a.build()
