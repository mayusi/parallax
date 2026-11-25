"""build_travel_pin.py — NEGATIVE fixture for the mechanism gate's TRAVEL (rbx_travel; the owner's limitations page,
D-R05): a runner 0.3 studs deep slides 4 studs along a bed, and a pin 0.1 thick stands in its path at x = -0.5 -
BETWEEN the old five stops (the runner's middle at -2, -1, 0, 1, 2: at -1 it has not reached the pin, at 0 it is
past it). Five stops read "clear"; the stops set from the travel pose the runner on the pin. Must be flagged:
mechanism, naming the bed's group. With the argument `clear` after `--` the pin stands BESIDE the path
(build_travel_clear.py): the same travel, nothing in the way - it must pass. Used by `lune run kit selftest`.
Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

CLEAR = "clear" in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else False

a = rbx.Asset("_selftest_travel_clear" if CLEAR else "_selftest_travel_pin", tex=64, size=(6.0, 0.6, 1.5))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Bed", (6.0, 0.2, 1.5), (0, 0.1, 0), "body", bevel=0)
a.box("Pin", (0.1, 0.4, 0.1), (-0.5, 0.4, 0.6 if CLEAR else 0.0), "body", bevel=0)      # y 0.2 .. 0.6, on the bed
a.box("Runner", (0.3, 0.3, 0.3), (-2.0, 0.35, 0), "trim", bevel=0, group="runner")     # y 0.2 .. 0.5, on the bed
a.joint("Runner", "runner", "slide", axis=(1, 0, 0), max=4.0)
a.build()
