"""build_ratchet_stale.py — the RATCHET after a measuring change: the accepted build (_selftest_ratchet_stale.accepted.json
beside this script) was measured by OTHER measuring code and made by ANOTHER script. Not comparable, it used to only
warn — so every floor stopped holding after each measuring change. The selftest requires the "ratchet" error: a floor
that cannot be compared vouches only for its own script. Never "fix" this file or its accepted record."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_ratchet_stale", size=(2, 2, 2), symmetric=True)
a.material("paint", (0.5, 0.5, 0.52), rough=0.6)
a.box("Body", (2, 2, 2), (0, 1, 0), "paint")
a.build()
