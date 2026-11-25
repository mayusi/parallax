"""build_relayer.py — POSITIVE fixture for THE PASSES KEPT: a painted box with a steel cap, its paint chipped, grimy
and dusty. Built twice by the selftest: as it is, then with `--more-dirt` (the SAME shapes and materials, only the
wear numbers higher: more mottle, more chips, more grime, more dust). The second build must not unwrap or bake
again: it reads the first one's Cycles passes off bakecache/_selftest_relayer.passes.npz and only layers the wear
anew - its summary must say "passes kept: main" (facts.passes_kept.main: every pass kept, none baked).
More switches for kit/test/python/test_relayer.py: `--no-dust` (no dust layer: a later build WITH dust needs
one pass the file lacks - that one is baked, the rest kept), `--bigger-cap` (another shape: nothing is kept) and
`--life=<word>` (the steel cap's wear from a life word - new, light, used, heavy - instead of its own numbers: a
changed word is a changed wear=, and must keep the passes too), `--no-mottle` (the paint's wear= 0: with
`--life=new` nothing on the piece is mottled, and a later build that is needs the noise's pass).
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
DUST = 0.0 if "--no-dust" in sys.argv else (0.5 if MORE else 0.2)
a = rbx.Asset("_selftest_relayer", size=(2.0, 1.0, 2.0), ground=True)
LIFE = next((x[7:] for x in sys.argv if x.startswith("--life=")), None)
a.material("paint", color=(0.2, 0.35, 0.25), rough=0.6,
           wear=0.0 if "--no-mottle" in sys.argv else (0.5 if MORE else 0.2), chip=0.6 if MORE else 0.3,
           grime=0.7 if MORE else 0.3, dust=DUST)
a.material("steel", color=(0.55, 0.56, 0.6), metal=1.0, rough=0.4,
           **({"life": LIFE} if LIFE else {"grime": 0.5 if MORE else 0.2}))
a.box("Body", (2.0, 0.8, 2.0), (0, 0.4, 0), "paint", bevel=0.03)
a.cylinder("Cap", 0.6 if "--bigger-cap" in sys.argv else 0.5, 0.2, (0, 0.8 + 0.1 - 0.01, 0), "steel", segments=32,
           bevel=0.01)
a.build()
