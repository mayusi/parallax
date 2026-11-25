"""build_stage_unmeasured.py — NEGATIVE fixture: the HERO block of build_stage_outline_ok.py with NO traced view
registered (no a.trace_match): its outline is measured against nothing. The stage gate must FAIL it on `stage`
(unmeasured: no traced view registered) and hold nothing back - the owner, 2026-11-12: "Yes, make it fail" (the
Gjallarhorn's build never registered one, the gate read its silhouette as "unmeasured" and let it pass, and its lower
rear stayed misread for 7 rounds). Never "fix" this file.
Used by `lune run kit selftest`. A hero build writes its part review to assets/models/: removed again after.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_stage_unmeasured", tex=64, size=(0.5, 1.0, 4.0), quality="hero")
a.material("body", color=(0.55, 0.56, 0.6))
a.box("Body", (0.5, 1.0, 4.0), (0, 0.5, 0), "body", bevel=0)
try:
    a.build()
finally:
    review = os.path.join(rbx.REPO, "assets", "models", f"{a.name}.parts.md")
    if os.path.isfile(review):
        os.remove(review)
