"""build_repair_bowl.py — fixture for A LARGE OPENING A REPAIR CAPS (card b7qe: "a.repair's flat-hole rule reads the
rim only: an open bowl, a cup or a lampshade is capped into a solid when asked"): a shallow tray listed without its
top - its opening is 70% of its surface. The rim alone cannot tell a tray from a box missing its lid, so:
  (none)  a.repair("Tray"): capped as asked, and the build WARNS repair_large_cap (keep it: a.open_way or cap=False)
  kept    a.open_way("Top", ...) down through the opening BEFORE a.repair: left open as named, no warning - and,
          a tray being a wall with no thickness, a.two_sided gives it its back (the build's own advice): it passes
Used by kit/test/python/test_repair_bowl.py. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

KEPT = "kept" in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
W, H = 1.0, 0.1
tray = [(px * W - W / 2, py * H, pz * W - W / 2) for px, py, pz in CUBE]
a = rbx.Asset("_selftest_repair_bowl" + ("_kept" if KEPT else ""), size=(1.0, 0.1, 1.0), ground=True)
a.material("tin", color=(0.6, 0.6, 0.62), metal=1.0, rough=0.4)
a.mesh("Tray", tray, [f for k, f in enumerate(FACES) if k != 4], "tin")   # no top (+Y)
if KEPT:
    a.open_way("Top", (0, 0.3, 0), (0, 0.05, 0), 0.6)
a.repair("Tray")
if KEPT:
    a.two_sided("Tray")
a.build()
