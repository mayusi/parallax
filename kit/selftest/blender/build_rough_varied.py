"""build_rough_varied.py — POSITIVE fixture: build_rough_flat.py's panel with a used surface — a paint micro-texture
(pattern="coat"), wear patches and grime: its roughness varies at every scale. The foot (a small flat-roughness part,
under 5% of the surface) is detail, not judged. Must NOT be named: roughness_variation. Used by
`lune run kit selftest`."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_rough_varied", tex=512, size=(3, 2.2, 0.3))
a.material("paint", **rbx.finish("painted_metal", color=(0.3, 0.32, 0.35)), pattern="coat", wear=0.4, grime=0.4)
a.material("trim", **rbx.finish("polymer"))
a.box("Panel", (3, 2, 0.3), (0, 1.2, 0), "paint")
a.box("Foot", (0.3, 0.2, 0.3), (0, 0.1, 0), "trim")
a.build()
