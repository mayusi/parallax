"""build_layers.py — POSITIVE fixture for A MATERIAL'S OWN LAYERS (a.material(layers=), rbx_layers): a painted box
with a steel cap; the paint chipped and grimy, with RUST where it chipped and creeping out of its cavities and SOOT
low down; the cap with a layer of its own colour on its flats. Built twice by the selftest: as it is, then with
`--more-dirt` (the SAME shapes, materials and wear numbers - only the layers' amounts higher). The second build must
not unwrap or bake again: it reads the first one's passes and lays the layers anew - its summary must say
"layers: main" (what each layer covered) and "passes kept: main".
More switches for kit/test/python/test_layer_stack.py: `--no-soot` (the soot layer taken out: only its texels may
change), `--no-layers` (none: the maps a build without layers gives), `--snow` (a layer on the up faces: the one
helper pass it reads is baked, the rest kept), `--nowhere` (rust "where chipped" on the cap, which has no paint to
chip: laid nowhere, and said), `--no-first` (the FIRST layer taken out: every other layer's patches stay), `--plain`
(the paint with no chips and no grime - no material has a wear number: the first layers bake one helper pass, and
taken out and put back they bake nothing), `--flat` (every layer a stain: thick_mm=0 - the normal map a build
without layers gives), `--mud` (a thick layer low down: more relief than the rust's), `--big` (a 2048 map: twice
the texels a millimetre - the same layers' banks are steeper).
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

MORE = "--more-dirt" in sys.argv
NONE = "--no-layers" in sys.argv
a = rbx.Asset("_selftest_layers", size=(2.0, 1.0, 2.0), ground=True, **({"tex": 2048} if "--big" in sys.argv else {}))
PLAIN = "--plain" in sys.argv
paint = [rbx.layer("rust", where="chipped", amount=1.0 if MORE else 0.8),
         rbx.layer("rust", amount=0.4 if MORE else 0.15)]
if "--no-first" in sys.argv:
    paint = paint[1:]
if "--mud" in sys.argv:
    paint.append(rbx.layer("mud", amount=0.5))
if "--no-soot" not in sys.argv:
    paint.append(rbx.layer("soot", where="low", amount=0.5 if MORE else 0.3, opacity=0.6))
cap = [rbx.layer("blueing", color=(0.02, 0.03, 0.08), rough=0.35, where="flats", amount=0.5 if MORE else 0.25)]
if "--snow" in sys.argv:
    cap.append(rbx.layer("snow", amount=0.6))
if "--nowhere" in sys.argv:
    cap.append(rbx.layer("rust", where="chipped", amount=0.5))
if "--flat" in sys.argv:
    paint, cap = [dict(d, thick_mm=0.0) for d in paint], [dict(d, thick_mm=0.0) for d in cap]
a.material("paint", color=(0.2, 0.35, 0.25), rough=0.6, layers=None if NONE else paint,
           **({} if PLAIN else {"chip": 0.4, "grime": 0.3}))
a.material("steel", color=(0.55, 0.56, 0.6), metal=1.0, rough=0.4, layers=None if NONE else cap)
a.box("Body", (2.0, 0.8, 2.0), (0, 0.4, 0), "paint", bevel=0.03)
a.cylinder("Cap", 0.5, 0.2, (0, 0.8 + 0.1 - 0.01, 0), "steel", segments=32, bevel=0.01)
a.build()
