"""build_strip_ok.py — POSITIVE fixture for the take-apart gate (a.disassembly): a box with a lid on it and a bar lying
across the lid. Taken apart in the right order — the bar slides out sideways, THEN the lid lifts off — every step is
clear and every part comes off: must NOT be named: disassembly. Its twins (KIT_STRIP=blocked: the lid lifted first,
into the bar; KIT_STRIP=incomplete: the lid never taken off) must be named. Used by `lune run kit selftest`.
Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

variant = os.environ.get("KIT_STRIP", "ok")
a = rbx.Asset(f"_selftest_strip_{variant}", tex=64, size=(2.0, 0.65, 1.0), ground=False)
a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
a.box("Body", (1.0, 0.4, 1.0), (0, 0.2, 0), "steel", bevel=0)
a.box("Lid", (1.0, 0.1, 1.0), (0, 0.45, 0), "steel", bevel=0)
a.cylinder("Bar", 0.05, 2.0, (0, 0.55, 0), "steel", axis="X")  # (lying across the lid, touching its top)
BAR_OUT = {"name": "bar out", "parts": ["Bar"], "move": (2.2, 0, 0)}
LID_OFF = {"name": "lid off", "parts": ["Lid"], "move": (0, 0.8, 0)}
steps = {"ok": [BAR_OUT, LID_OFF], "blocked": [LID_OFF, BAR_OUT], "incomplete": [BAR_OUT]}[variant]
a.disassembly(steps, base=["Body"])
a.build()
