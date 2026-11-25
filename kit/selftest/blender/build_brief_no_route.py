"""build_brief_no_route.py — NEGATIVE fixture: a HERO build whose brief (_selftest_brief_no_route.brief.md beside
this script) names a hero feature with NO ROUTE (the grip wrap: nobody said how it gets made) and one only a far
picture shows (the wolf head: a 42 px box for 30 mm, 1.4 px/mm). Must be named: routes and coverage.
Used by `lune run kit selftest`. Never "fix" this file or its brief. A hero build writes its part review to
assets/models/: removed again after.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_brief_no_route", tex=64, size=(1.0, 0.5, 1.0), quality="hero")
a.material("body", color=(0.55, 0.56, 0.6))
a.box("Body", (1.0, 0.5, 1.0), (0, 0.25, 0), "body", bevel=0)
try:
    a.build()
finally:
    review = os.path.join(rbx.REPO, "assets", "models", f"{a.name}.parts.md")
    if os.path.isfile(review):
        os.remove(review)
