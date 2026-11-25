"""build_hand_hero.py — a HAND-BUILT hero master: its first line lacks the kit-make marker, and its name is not one
the selftest exemption covers. The kit-make rule must REFUSE it as a new build (`kit asset`), and must let
`kit optimize` (--optimize) of it through once its master build exists (made with the owner's KIT_HAND_BUILD=1, as an old hand-built hero was).
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("selftest_hand_hero", tex=64, size=(0.6, 0.3, 0.9), stage="master", quality="hero", ground=True)
a.material("steel", color=(0.55, 0.56, 0.6), metal=0.9, rough=0.35)
a.box("Base", (0.6, 0.08, 0.9), (0, 0.04, 0), "steel", bevel=0.01)
a.cylinder("Post", 0.08, 0.22, (0, 0.19, 0), "steel", segments=48, bevel=0.006)
a.build()
