"""build_missing_lines.py — NEGATIVE fixture for the INTERNAL LINES check (kit/vision/lines.py): the reference
(lines_ref.png, a synthetic side view) shows a vertical groove, a panel seam and a slot INSIDE the outline; this box
has the same outline and none of them. The silhouette matches — only the lines check can see what is missing.
Must be flagged: "missing lines". Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_lines", tex=64, size=(0.4, 0.6, 2.0),
              reference={"side": "kit/selftest/blender/lines_ref.png"})
a.material("body", color=(0.44, 0.45, 0.47))
a.box("Body", (0.4, 0.6, 2.0), (0, 0.3, 0), "body", bevel=0)  # 2.0 long x 0.6 tall, like the reference's 400 x 120 px
a.build()
