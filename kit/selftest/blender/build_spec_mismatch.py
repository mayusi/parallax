"""build_spec_mismatch.py — NEGATIVE fixture against its design spec (given inline): the spec's Hinge was never
modelled; the Lid hovers 30 mm off the Body it must attach to (beyond attach_gaps' 14 mm reach, so only the Badge
can trip that gate); the Badge touches the Body only with its foot while its face stands 3 mm off (daylight all
round); and a part exists that the spec never describes.
Must be flagged: spec_parts, spec_attach, attach_gaps, spec_undocumented.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_spec", tex=64, size=(1.2, 1.2, 1.2))
a.real_scale(100)
a.spec({
    "name": "_selftest_spec",
    "parts": [
        {"name": "Body", "what": "the housing", "visible": "exterior"},
        {"name": "Lid", "what": "the lid, closing the top", "attaches": ["Body"]},
        {"name": "Badge", "what": "the maker's badge, flat on the side", "attaches": ["Body"]},
        {"name": "Hinge", "what": "the lid hinge", "attaches": ["Body", "Lid"]},
    ],
})
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Body", (1, 1, 1), (0, 0.5, 0), "body", bevel=0)
a.box("Lid", (0.8, 0.05, 0.8), (0, 1.325, 0), "body", bevel=0)  # bottom at 1.3: 30 mm above the body
# front view (u = right, v = up): a foot on the body's +X face, the plate 3 mm out from it
a.extrude("Badge", [(0.50, 0.30), (0.55, 0.30), (0.55, 0.60), (0.53, 0.60), (0.53, 0.35), (0.50, 0.35)], 0.3, "trim",
          plane="front", bevel=0)
a.box("Mystery", (0.1, 0.1, 0.1), (0, 0.5, -0.55), "trim", bevel=0)  # not in the spec
a.build()
