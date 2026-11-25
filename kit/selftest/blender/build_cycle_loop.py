"""build_cycle_loop.py — POSITIVE fixture for A MODEL'S OWN MOTION IN THE GAME (rbx_cycleplay; the 3D methods audit,
G3): a wheel with a lug and a pin on a base, and two action cycles - "Turn" (the wheel half round and back, the pin
dipping while the lug is away: LOOPED, it ends where it began) and "Seat" (the pin let down once: not looped, with a
mark). The build must write each cycle to the manifest as the table the game plays (`play`: joints, times, values,
length, loop, marks) and say nothing against the loop. With the argument `jump` after `--` the looped cycle ends
half a turn from where it began (build_cycle_loop_jump.py): the build must fail `cycle_loop`, naming the joint.
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

JUMP = "jump" in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else False

a = rbx.Asset("_selftest_cycle_loop_jump" if JUMP else "_selftest_cycle_loop", tex=64, size=(1.0, 1.2, 0.4))
a.material("body", color=(0.55, 0.56, 0.6))
a.material("trim", color=(0.2, 0.2, 0.22))
a.box("Base", (0.9, 0.1, 0.3), (0, 0.05, 0), "body", bevel=0)
a.box("Post", (0.08, 0.4, 0.08), (0, 0.3, -0.12), "body", bevel=0)
a.cylinder("Wheel", 0.25, 0.1, (0, 0.5, 0), "trim", axis="Z", segments=32, group="wheel")
a.box("Lug", (0.12, 0.06, 0.1), (0.31, 0.5, 0), "trim", bevel=0, group="wheel")       # sweeps radius 0.25 .. 0.37
a.box("Pin", (0.06, 0.2, 0.06), (0, 1.0, 0), "body", bevel=0, group="pin")           # y 0.90 .. 1.10 at rest
a.joint("Wheel", "wheel", "hinge", axis=(0, 0, 1), pivot=(0, 0.5, 0), max=180)
a.joint("Pin", "pin", "slide", axis=(0, -1, 0), max=0.12)                            # down to y 0.78 .. 0.98
if JUMP:   # the fault: said to loop, the wheel ends half a turn from where it began
    a.cycle("Turn", [(1, {"Wheel": 0, "Pin": 0}), (25, {"Wheel": 180})], loop=True)
else:      # out and back: the wheel returns, the pin dips only while the lug is at the far side
    a.cycle("Turn", [(1, {"Wheel": 0, "Pin": 0}), (25, {"Wheel": 180}), (27, {"Pin": 0}), (31, {"Pin": "max"}),
                     (35, {"Pin": 0}), (37, {"Wheel": 180}), (61, {"Wheel": 0})], loop=True)
    a.cycle("Seat", [(1, {"Pin": 0, "Wheel": 180}), (13, {"Pin": "max"})], marks={"seated": 13})
a.build()
