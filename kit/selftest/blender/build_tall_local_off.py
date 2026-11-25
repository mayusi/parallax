"""build_tall_local_off.py — NEGATIVE fixture: the same tall object with a chunk 8 mm deep and 20 mm tall missing from
one side halfway up — the whole outline still overlaps well. Must be named: reference_front_local. Never "fix" this
file. Used by `lune run kit selftest`."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

# a long object seen from the FRONT: a column 30 mm wide, 140 tall (1 stud = 100 mm); the trace: u across, v up in
# widths (140 / 30 = 4.667)
H_W = 140.0 / 30.0
TRACE = {"name": "_tall", "front": "right", "holes": [], "height_ratio": round(H_W, 6),
         "outline": [[0, 0], [1, 0], [1, H_W], [0, H_W]]}


def build(name, width_mm, notch=False):
    out = os.path.join(rbx.BUILD, "selftest")
    os.makedirs(out, exist_ok=True)
    trace = os.path.join(out, f"{name}.trace.json")
    with open(trace, "w", encoding="utf-8") as fh:
        json.dump(TRACE, fh)
    a = rbx.Asset(name, tex=64, size=(width_mm / 100.0, 1.4, 1.0), ground=False)
    a.real_scale(100.0)
    a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
    a.box("Column", (width_mm / 100.0, 1.4, 1.0), (0, 0, 0), "steel", bevel=0)
    if notch:   # (a real fault: a chunk 8 mm deep, 20 mm tall missing from one side halfway up)
        a.cut("Column", a.box("Notch", (0.16, 0.2, 1.2), (width_mm / 200.0, 0, 0), "steel", bevel=0))
    a.trace_match(trace, view="front", bar=0.5)
    a.build()


build("_selftest_tall_local_off", 30.0, notch=True)
