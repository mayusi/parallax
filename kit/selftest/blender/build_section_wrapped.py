"""build_section_wrapped.py — POSITIVE fixture: the grip LOFTED through its reference's own measured slices
(cad_parts.loft_sections(from_levels(...)) with the levels of kit/selftest/refs/_round_grip.measure.json). Must NOT
be named: section_match. Never "fix" this file. Data -> build -> check: the reference's numbers make the grip, and the
grip is measured against them. Used by `lune run kit selftest` (needs the cad env).
"""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

REF = os.path.join(_root, "kit", "selftest", "refs", "_round_grip.measure.json")
with open(REF, encoding="utf-8") as fh:
    LEVELS = json.load(fh)["levels"]
a = rbx.Asset("_selftest_wrap_lofted", tex=64, size=(0.30, 1.15, 2.0))
a.real_scale(100.0)
a.material("steel", color=(0.5, 0.5, 0.52))
a.box("Body", (0.30, 0.35, 2.0), (0, 0, 0), "steel", bevel=0)
# the object is 115 mm tall (its centre 40 mm below the body's middle) and 200 mm long; the loft's last station
# repeats the top one 8 mm higher, into the body, so the grip meets it
a.cad("Grip", "st = from_levels(P['levels'], 115, 200, hs=(0.05, 0.15, 0.3, 0.45, 0.6, 0.65))\n"
              "st.append(dict(st[-1], at=st[-1]['at'] + 8))\n"
              "part = loft_sections(st)\n", "steel", pos=(0, -0.40, 0), params={"levels": LEVELS})
a.section_match(REF, levels=(0.15, 0.3, 0.45))
a.build()
