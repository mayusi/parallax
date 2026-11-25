"""build_ratchet.py — the RATCHET: an asset whose ACCEPTED build scored 95 (_selftest_ratchet.accepted.json beside
this script) is rebuilt as a plain box that scores far lower. The selftest requires the "ratchet" error: once a build
is accepted, nothing worse may pass — the drift that turned the starters into noise is blocked at its first step.
Never "fix" this file or its accepted record."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_ratchet", size=(2, 2, 2), symmetric=True)
a.material("paint", (0.5, 0.5, 0.52), rough=0.6)
a.box("Body", (2, 2, 2), (0, 1, 0), "paint")
a.build()
