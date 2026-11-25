"""build_contact_use.py — fixture: a.contact by PART and the DRIP kind (AAA-7). A painted steel plate 1.0 x 1.0 x 0.1
studs standing up, a fitting near its top and a handle bar low on its face: the handle's box comes from the part
(part=, pad=), and streaks run down from the fitting (kind="drip") — kit/test/python/test_contact_use.py reads the
share of the map each kind touched (facts.contacts). Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_contact_use", tex=256, size=(1.0, 1.0, 0.18))
a.real_scale(280.0)
a.material("paint", **rbx.look("painted_steel_worn"), life="light")
a.box("Plate", (1.0, 1.0, 0.1), (0, 0.5, 0), "paint", bevel=0.01)
a.box("Fitting", (0.1, 0.1, 0.08), (0, 0.85, -0.09), "paint", bevel=0.01)
a.box("Handle", (0.4, 0.06, 0.06), (0, 0.2, -0.08), "paint", bevel=0.01)
a.contact("drip", part="Fitting", falloff=0.45)
a.contact("hand", part="Handle", pad=0.01)
a.build()
