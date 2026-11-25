"""build_hand_hero_ok.py — a HAND-WRITTEN hero that passes every hero check (the owner, 2026-11-11, kit card 38a9:
"Yes, allow them" - a hand-written hero script builds when it passes the hero checks). It names NO quality=: its brief
beside it (selftest_hand_hero_ok.brief.md) says hero, so it builds at hero (the brief-tier default, "Yes, turn them
on"); every part family is answered in its part review (selftest_hand_hero_ok.parts.md, a reference on disk each);
nothing is declared off; and its outline is MEASURED: its side view is traced (the stand's own side outline, written
at run time in build/selftest/) and registered with a.trace_match - since the owner's "Yes, make it fail"
(2026-11-12, kit card a3xx) a hero whose outline is measured against nothing is refused, so a hero that passes every
hero check has one (the same stand WITHOUT it is what that rule's own fixture refuses: build_stage_unmeasured.py).
The kit must BUILD it (status pass, tier hero from its brief). Used by `lune run kit selftest`. Never "fix" this file.
"""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
# the stand from its side, in shares of its length (0.9 studs): the base plate 0.08 high, the post 0.16 wide to 0.30
trace = {"name": "_hand_hero_ok_side", "source": "kit/selftest/refs/revolver_b4_side_ref.png", "front": "right",
         "height_ratio": 0.3333, "holes": [],
         "outline": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.0889], [0.5889, 0.0889], [0.5889, 0.3333], [0.4111, 0.3333],
                     [0.4111, 0.0889], [0.0, 0.0889]]}
with open(os.path.join(out, "_hand_hero_ok_side.trace.json"), "w", encoding="utf-8") as fh:
    json.dump(trace, fh)

a = rbx.Asset("selftest_hand_hero_ok", tex=64, size=(0.6, 0.3, 0.9), stage="master", ground=True)
a.material("steel", color=(0.55, 0.56, 0.6), metal=0.9, rough=0.35)
a.box("Base", (0.6, 0.08, 0.9), (0, 0.04, 0), "steel", bevel=0.01)
a.cylinder("Post", 0.08, 0.22, (0, 0.19, 0), "steel", segments=48, bevel=0.006)
a.trace_match(os.path.join(out, "_hand_hero_ok_side.trace.json"))
a.build()
