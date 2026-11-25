"""build_trim_sheet.py — fixture: A TRIM SHEET (a.trim_sheet, rbx_trim; the 3D methods audit, S2): four bands -
worn planks 4 studs tall, stone 1.5, an iron edge 1 and a row of iron half a stud - over 8 studs of surface, each
at the sheet's one scale. The build must lay each band on its own stretch of the map, bake it, make the maps repeat
along their length and say so ("trim sheet: 4 bands over 8 studs, repeats along its length"), and write the bands
to the manifest. The other trim
fixtures (build_trim_wall*.py) take their bands from THIS sheet: it is built first. Used by `lune run kit selftest`.
Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_trim_sheet", tex=512, size=(8.0, 0, 8.5), ground=True,
              allow_floating=["Band_planks", "Band_stone", "Band_edge", "Band_rivets"])
a.material("planks", color=(0.42, 0.3, 0.18), rough=0.7, wear=0.6, grime=0.4)
a.material("stone", color=(0.5, 0.5, 0.48), rough=0.8, wear=0.5)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5, wear=0.5)
a.trim_sheet([("planks", "planks", 4.0), ("stone", "stone", 1.5), ("edge", "iron", 1.0), ("rivets", "iron", 0.5)],
             studs=8.0)
a.build()
