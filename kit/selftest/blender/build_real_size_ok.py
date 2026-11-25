"""build_real_size_ok.py — POSITIVE fixture: a chair at real size (0.45 m wide, 0.92 m tall, 0.42 m deep at
Roblox's 1 stud = 0.28 m). Must NOT be named: size_plausible. Used by `lune run kit selftest`.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

S = 1.0  # the chair's scale: 1 = real size
a = rbx.Asset("_selftest_real_size_ok", tex=64, size=(1.6 * S, 3.3 * S, 1.5 * S), kind="chair")
a.material("wood", color=(0.45, 0.3, 0.18))
for i, (x, z) in enumerate(((-0.7, -0.65), (0.7, -0.65), (-0.7, 0.65), (0.7, 0.65))):
    a.box(f"Leg{i + 1}", (0.15 * S, 1.6 * S, 0.15 * S), (x * S, 0.8 * S, z * S), "wood", bevel=0)
a.box("Seat", (1.6 * S, 0.15 * S, 1.5 * S), (0, 1.675 * S, 0), "wood", bevel=0)
a.box("Back", (1.6 * S, 1.55 * S, 0.15 * S), (0, 2.525 * S, 0.675 * S), "wood", bevel=0)
a.build()
