"""build_trim_wall.py — POSITIVE fixture for A PART LAID INTO A TRIM SHEET and A MODULE OF A KIT (a.trim, a.module,
rbx_trim; the 3D methods audit, S2): a wall module 8 x 4 studs on a 4-stud grid - a panel 3.5 tall laid into the
sheet's "planks" band (4 tall) and a cap half a stud tall laid into its "edge" band (1 tall: within the stretch
the build lets by). The group bakes NOTHING: its maps in the manifest are the sheet's own files, its faces run along the
bands (the panel 8 studs = once round the sheet), and the build says so ("trim: main on _selftest_trim_sheet",
"module: 2 x 1 cells"). Needs build_trim_sheet.py built first, in the same build folder.
With `off` after `--` (build_trim_wall_off.py) the wall is 7.5 studs long and its panel is laid into the half-stud
"rivets" band: it must fail `module_grid` and warn `trim_fit`, each by name. After the build one line `TRIM {json}`:
every face of the BUILT mesh with its part, its normal, its corners (the model's frame) and where each was laid on
the sheet - read by kit/test/python/test_trim_build.py. Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

OFF = "off" in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else False
LENGTH = 7.5 if OFF else 8.0

a = rbx.Asset("_selftest_trim_wall_off" if OFF else "_selftest_trim_wall", tex=64, size=(LENGTH, 4.0, 1.0),
              ground=True)
a.material("any", color=(0.5, 0.5, 0.5), rough=0.7)
# built from a grid point: the wall's lower left corner at the origin, running along +X
a.box("Panel", (LENGTH, 3.5, 1.0), (LENGTH / 2, 1.75, 0.5), "any", bevel=0)
a.box("Cap", (LENGTH, 0.5, 1.0), (LENGTH / 2, 3.75, 0.5), "any", bevel=0)
a.trim("Panel", "_selftest_trim_sheet", "rivets" if OFF else "planks", along=(1, 0, 0))
a.trim("Cap", "_selftest_trim_sheet", "edge", along=(1, 0, 0))
a.module((4, 4, 0))
a.build()

import bpy  # noqa: E402

obj = bpy.data.objects[a.name]
names, attr = list(obj.get("kit_parts") or []), obj.data.attributes.get("kit_part")
back = rbx.BL_FROM_RBX.inverted() @ obj.matrix_world
uv = obj.data.uv_layers.active.data
rows = []
for poly in obj.data.polygons:
    rows.append({"part": names[attr.data[poly.index].value],
                 "n": [round(c, 2) for c in (back.to_3x3() @ poly.normal)],
                 "pts": [[round(c, 3) for c in back @ obj.data.vertices[v].co] for v in poly.vertices],
                 "uv": [[round(c, 4) for c in uv[li].uv] for li in poly.loop_indices]})
print("TRIM " + json.dumps(rows))
