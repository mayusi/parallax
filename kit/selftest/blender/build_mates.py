"""build_mates.py — fixtures for SOCKETS AND MATES (a.socket, a.at, a.mate; his D-R04; the 3D methods audit, stage
L). A body with a WELL named on its top, a peg with its FOOT named on its underside, the peg put where the well
is (pos from a.at) and the two said to meet with a fit. By the word after `--`:
  (none)   everything from the same numbers. Must pass, and say: sockets: 2 on their parts, 1 of 1 mates held.
  grown    the body made half a stud taller - but its well, and the peg, left at the old height. Must FAIL
           `mates`: the well is said to lie 0.5 studs off "Body" (build_mates_grown.py).
  fat      a peg wider than the well. Must FAIL `mates`: it does not go in (build_mates_fat.py).
  apart    the peg moved aside by hand instead of placed by a.at, its foot with it. Must FAIL `mates`: the two
           are said to be 0.4 studs apart (build_mates_apart.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((w for w in ("grown", "fat", "apart") if w in ARGS), "good")

H = 1.0                                   # the body's height: the well is said from it
BODY = H + 0.5 if HOW == "grown" else H   # (grown: the box changed and nothing else followed)
PEG = 0.6 if HOW == "fat" else 0.46
SIDE = 0.4 if HOW == "apart" else 0.0

a = rbx.Asset("_selftest_mates_" + HOW, tex=64, size=(2.0, BODY + 0.8, 2.0), bevel=0)
a.material("body", color=(0.5, 0.52, 0.56))
a.material("peg", color=(0.75, 0.6, 0.25), metal=1.0, rough=0.4)
a.box("Body", (2.0, BODY, 2.0), (0, BODY / 2, 0), "body", bevel=0)
a.socket("Well", "Body", (0, H, 0), axis=(0, 1, 0), size=0.5)
x, y, z = a.at("Well")
a.cylinder("Peg", PEG / 2, 0.8, (x + SIDE, y + 0.4, z), "peg", axis="Y", segments=24)
a.socket("PegFoot", "Peg", (x + SIDE, y, z), axis=(0, -1, 0), size=PEG)
a.mate("Peg in Well", "PegFoot", "Well", fit=(0.01, 0.05))
a.build()
