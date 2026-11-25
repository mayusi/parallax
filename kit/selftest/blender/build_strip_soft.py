"""build_strip_soft.py — POSITIVE fixture for the take-apart gate's SOFT parts: a rubber sleeve round a post, pulled off
the top over the post's lip (wider than the sleeve's opening) — rubber stretches over it, as a real grip sleeve rolls
off a frame: must NOT be named: disassembly. Its twin (KIT_SOFT=steel: the same sleeve in steel) jams on the lip and
must be named. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

variant = os.environ.get("KIT_SOFT", "rubber")
a = rbx.Asset(f"_selftest_strip_soft_{variant}", tex=64, size=(0.8, 1.3, 0.8), ground=False)
a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
if variant == "rubber":
    a.material("rubber", (0.03, 0.03, 0.03), rough=0.9)
a.box("Post", (0.4, 1.0, 0.4), (0, 0.5, 0), "steel", bevel=0)
a.box("Lip", (0.56, 0.1, 0.56), (0, 1.05, 0), "steel", bevel=0)  # (wider than the sleeve's 0.4 opening)
# the sleeve round the post: four walls 0.06 thick, hugging it
for nm, size, pos in (("SleeveLeft", (0.06, 0.3, 0.52), (-0.23, 0.3, 0)), ("SleeveRight", (0.06, 0.3, 0.52), (0.23, 0.3, 0)),
                      ("SleeveFront", (0.4, 0.3, 0.06), (0, 0.3, -0.23)), ("SleeveBack", (0.4, 0.3, 0.06), (0, 0.3, 0.23))):
    a.box(nm, size, pos, "rubber" if variant == "rubber" else "steel", bevel=0)
a.disassembly([{"name": "sleeve off over the lip", "parts": ["Sleeve*"], "move": (0, 1.2, 0)}],
              base=["Post", "Lip"])
a.build()
