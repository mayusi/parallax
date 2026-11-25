"""build_cycle_fade.py - NEGATIVE fixture for THE FADES A GAME PLAYS (rbx_cycleplay.fades; the 3D methods audit's
"cycles blend ... the poses inside a fade are not checked"): build_cycle_loop.py's wheel, lug and pin, one cycle
"Hold" that only holds the wheel half round with the pin down - clear, the lug on the far side. But Models.play
fades into it from REST along a straight line in the joints: the wheel turns past the top while the pin is half way
down, and the lug drives into the pin. mechanism_cycle passes (the cycle never takes that pose); the build must FAIL
`cycle_fade`, saying "from rest into Hold". Used by kit/test/python/test_cycle_fade_build.py. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_cycle_fade", tex=64, size=(1.0, 1.2, 0.4))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Base", (0.9, 0.1, 0.3), (0, 0.05, 0), "body", bevel=0)
a.box("Post", (0.08, 0.4, 0.08), (0, 0.3, -0.12), "body", bevel=0)
a.cylinder("Wheel", 0.25, 0.1, (0, 0.5, 0), "trim", axis="Z", segments=32, group="wheel")
a.box("Lug", (0.12, 0.06, 0.1), (0.31, 0.5, 0), "trim", bevel=0, group="wheel")
a.box("Pin", (0.06, 0.2, 0.06), (0, 1.0, 0), "body", bevel=0, group="pin")
a.joint("Wheel", "wheel", "hinge", axis=(0, 0, 1), pivot=(0, 0.5, 0), max=180)
a.joint("Pin", "pin", "slide", axis=(0, -1, 0), max=0.12)
a.cycle("Hold", [(1, {"Wheel": 180, "Pin": "max"}), (13, {"Wheel": 180, "Pin": "max"})])
a.build()
