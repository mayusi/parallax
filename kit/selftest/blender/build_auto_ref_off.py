"""build_auto_ref_off.py — NEGATIVE fixture: a HERO build with a traced side view and NO trace_match — its trace
shows the handle under the middle, the model has it under the rear. Must be named: reference_side_local (the body
overlaps, the handle does not). Every traced view of a hero is matched: the Glock 17 build once had traces nothing
compared it with. Never "fix" this file. Used by `lune run kit selftest`."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

# design units: u = (2 - z) / 4 (the back z = +2 -> 0, the front z = -2 -> 1), v = (y + 1.7) / 4; height 2.2 / 4
RIGHT = [[0, 0.3], [0.125, 0.3], [0.125, 0.0], [0.275, 0.0], [0.275, 0.3], [1, 0.3], [1, 0.55], [0, 0.55]]
WRONG = [[0, 0.3], [0.45, 0.3], [0.45, 0.0], [0.6, 0.0], [0.6, 0.3], [1, 0.3], [1, 0.55], [0, 0.55]]  # (its handle
#   under the MIDDLE: the model's is under the rear — not a mirror image, which the build names as one)
TOP = [[0, 0.0], [1, 0.0], [1, 0.125], [0, 0.125]]


def write_traces(name, traces):
    """the asset's traces where a build finds them by name: assets/models/<name>_<label>.trace.json"""
    paths = []
    for label, outline in traces.items():
        p = os.path.join(_root, "assets", "models", f"{name}_{label}.trace.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"name": f"{name}_{label}", "front": "right", "holes": [], "outline": outline,
                       "height_ratio": round(max(v for _u, v in outline), 6)}, fh)
        paths.append(p)
    return paths


def build(name, traces, excluded=None):
    paths = write_traces(name, traces)
    try:
        a = rbx.Asset(name, tex=64, size=(0.5, 2.2, 4.0), ground=False, quality="hero")
        a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
        a.material("grip", (0.1, 0.1, 0.1), rough=0.7)
        a.box("Body", (0.5, 1.0, 4.0), (0, 0, 0), "steel", bevel=0)
        a.box("Handle", (0.4, 1.2, 0.6), (0, -1.1, 1.2), "grip", bevel=0)
        for label, why in (excluded or {}).items():
            a.not_reference(f"{name}_{label}", why=why)
        a.build()   # (no trace_match: every trace is found by its name)
    finally:
        for p in paths:
            os.remove(p)


build("_selftest_auto_ref_off", {"photo_side": WRONG})
