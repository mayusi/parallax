"""build_contact.py — fixture: a.contact (where use touches it). A polymer block 0.6 x 0.4 x 1.0 studs held by a HAND
over its back half and resting on the GROUND: the bake's wear follows them — kit/test/python/test_contact.py reads the
share of the map each kind touched (facts.contacts) and the roughness where the hand polished it. Never "fix" this
file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_contact", tex=256, size=(0.6, 0.4, 1.0))
a.real_scale(280.0)
a.material("polymer", **rbx.look("polymer_frame"), life="light")
a.box("Block", (0.6, 0.4, 1.0), (0, 0.2, 0), "polymer", bevel=0.02)
a.contact("hand", at=(0, 0.2, 0.25), size=(0.7, 0.5, 0.5))     # the back half, all round
a.contact("ground", at=(0, 0.0, 0), size=(0.7, 0.06, 1.1))     # the face it rests on
a.build()
