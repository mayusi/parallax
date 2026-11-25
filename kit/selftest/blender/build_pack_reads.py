"""build_pack_reads.py — POSITIVE fixture: a part built ONLY from its asset's pack (_selftest_pack_reads.pack.json
beside this script): its outline from a traced mm profile, its thickness from a sourced size, its colour and roughness
as measured — no number typed in. Must build and be judged (a pack value that cannot be read raises, and a crash
fails the selftest); its verdict lists what it read (facts.pack). Used by `lune run kit selftest`. Never "fix" this
file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_pack_reads", tex=64)
pk = a.pack()
MM = 1 / 280.0  # studs per mm
a.real_scale(280)
outline = [(f * MM, h * MM) for f, h in pk.profile("slab")]
a.material("slab", color=pk.colour("slab"), rough=pk.rough("slab"), metal=pk.metal("slab"))
a.extrude("Slab", outline, pk.size("slab.depth") * MM, "slab", plane="side", pos=(0, pk.extents("slab")[3] * MM, 0))
assert abs(pk.length_mm - 120.0) < 1e-9
a.build()
