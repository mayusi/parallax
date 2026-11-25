"""build_master_floaters.py — POSITIVE fixture: a MASTER (stage="master") whose rivets are floaters. A master is the
high-fidelity model, so its floaters must stay REAL geometry (seated on the plate they decorate) — baked away, the
rivets the spec names would be missing from the master (found by the Gjallarhorn test, 2026-10-06: "the floaters are
targeted towards low quality — what if I want high quality?"). Must NOT be flagged: spec_parts.
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_master_floaters", tex=64, size=(1.0, 0.2, 1.0), stage="master")
a.real_scale(100)
a.spec({
    "name": "_selftest_master_floaters",
    "parts": [
        {"name": "Plate", "what": "a steel plate", "visible": "exterior"},
        {"name": "Rivet*", "what": "the rivets holding it, domed heads on its top face", "attaches": ["Plate"]},
    ],
})
a.material("steel", color=(0.55, 0.56, 0.6))
a.box("Plate", (1.0, 0.1, 1.0), (0, 0.05, 0), "steel", bevel=0)
with a.floaters():
    for i, (x, z) in enumerate(((-0.4, -0.4), (0.4, -0.4), (0.4, 0.4), (-0.4, 0.4))):
        a.cylinder(f"Rivet{i + 1}", 0.04, 0.03, (x, 0.1 + 0.01, z), "steel", segments=16)  # 0.005 into the plate
a.build()
