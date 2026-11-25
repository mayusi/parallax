"""build_pack_cube.py — a plain square tile: two equal square faces and four hairline edges. Two equal squares
cannot be laid fuller on a square map than side by side at half its width (half the map), and Blender's packer by
boxes does that. The kit's packer (rbx_uvpack) gets a percent or two more out of the edges' pads (0.512 against
0.504) - a layout it keeps, and no news: the build must NOT say "packed by shape" (said from a 3% gain up). The
fault this catches: a build that claims a gain that is none. (A cube will not do: Blender's boxes leave 1.5 to
6% of its six squares' best layout unused, and the kit's packer rightly takes that.)
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_pack_cube", size=(2.0, 0.04, 2.0), ground=True)
a.material("paint", color=(0.3, 0.32, 0.36), rough=0.6)
a.box("Tile", (2.0, 0.04, 2.0), (0, 0.02, 0), "paint", bevel=0)
a.build()
