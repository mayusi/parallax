"""build_agree.py — fixtures for THE REFERENCES, SOLVED TOGETHER (a.cite, rbx_agree; his D-R01; the 3D methods
audit, stage L). A bar 1000 mm long and 250 high by a maker's drawing, with a side photo's own proportion cited
and two side photos' own proportions cited beside it. By the word after `--`:
  (none)   both photos say the height is 0.25 of the length: everything agrees. Must pass, and say: references: 4
           statements agree.
  odd      the second photo says 0.33 (a picture of another variant): must FAIL `reference_agree`, which names
           THAT photo alone - the drawing and the first photo agree against it (build_agree_odd.py).
  tall     the references agree, but the bar is BUILT 300 mm high: must flag `reference_fit` (a warning) with
           the height they agree on (build_agree_tall.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((w for w in ("odd", "tall") if w in ARGS), "good")

HIGH = 1.2 if HOW == "tall" else 1.0
a = rbx.Asset("_selftest_agree_" + HOW, tex=64, size=(0.4, 1.0, 4.0), bevel=0)
a.real_scale(250)                                   # 250 mm a stud: 4 studs = 1000 mm
a.material("steel", color=(0.5, 0.52, 0.56), metal=1.0, rough=0.4)
a.box("Bar", (0.4, HIGH, 4.0), (0, HIGH / 2, 0), "steel", bevel=0)
a.cite("the maker's drawing, length", 1000, axis="length", trust="high")
a.cite("the maker's drawing, height", 250, axis="height", trust="high")
a.cite("a side photo", 0.25, of=("height", "length"))
a.cite("another side photo", 0.33 if HOW == "odd" else 0.25, of=("height", "length"))
a.build()
