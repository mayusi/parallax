"""build_repair_named.py — fixtures for A REPAIR STEERED BY A NAMED OPENING (his D-R12, the rest: "repair ... does
not know every intended opening"; the 3D methods audit, stage L). A bin given as a sheet of faces: its top is open
(its MOUTH, named with a.open_way) and half its bottom is missing (a tear). By the word after `--`:
  (none)   a.repair caps the tear and leaves the mouth (it used to cap both, and the build then failed open_ways);
           a.two_sided gives the walls their back. Must pass, and say: left open as named: Mouth.
  thin     the same without a.two_sided: the bin is still a sheet. Must FAIL `openings`, which names the mouth and
           says what gives the wall its thickness (build_repair_named_thin.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = "thin" if "thin" in ARGS else "good"

a = rbx.Asset("_selftest_repair_named_" + HOW, tex=64, size=(1.0, 1.0, 1.0), bevel=0)
a.material("tin", color=(0.5, 0.52, 0.55), metal=1.0, rough=0.45)
V = [(-0.5, 0, -0.5), (0.5, 0, -0.5), (0.5, 0, 0.5), (-0.5, 0, 0.5),
     (-0.5, 1, -0.5), (0.5, 1, -0.5), (0.5, 1, 0.5), (-0.5, 1, 0.5), (0, 0, -0.5), (0, 0, 0.5)]
F = [(0, 8, 9, 3),                  # the bottom's left half (its right half is the tear)
     (0, 4, 5, 1, 8), (3, 9, 2, 6, 7), (1, 5, 6, 2), (0, 3, 7, 4)]   # four walls; no top: the mouth
a.mesh("Bin", V, F, "tin")
a.open_way("Mouth", (0, 1.4, 0), (0, 0.4, 0), 0.6)     # (said BEFORE the repair: a repair reads the names there are)
a.repair("Bin")
if HOW == "good":
    a.two_sided("Bin", thickness=0.03)
a.build()
