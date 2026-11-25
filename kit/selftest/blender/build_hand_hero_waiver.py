"""build_hand_hero_waiver.py — a HAND-WRITTEN hero that declares a hero check off (stage_gate=False): the owner,
2026-11-11 (kit card 38a9, "Yes, allow them"), let hand-written heroes build only when they pass every hero check with
NO waiver. Everything else is in order (its part review answered: selftest_hand_hero_waiver.parts.md), so the one
thing that must REFUSE it is `declared` - an error for a hand-written hero. Used by `lune run kit selftest`. Never "fix"
this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("selftest_hand_hero_waiver", tex=64, size=(0.6, 0.3, 0.9), stage="master", quality="hero", ground=True,
              stage_gate=False)
a.material("steel", color=(0.55, 0.56, 0.6), metal=0.9, rough=0.35)
a.box("Base", (0.6, 0.08, 0.9), (0, 0.04, 0), "steel", bevel=0.01)
a.cylinder("Post", 0.08, 0.22, (0, 0.19, 0), "steel", segments=48, bevel=0.006)
a.build()
