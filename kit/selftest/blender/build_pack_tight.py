"""build_pack_tight.py — POSITIVE fixture: a plate carrying two large discs, four long rails and forty small blocks
of many sizes (one mesh, automatic UVs). Blender's packer sets its islands down in rows and leaves the gaps round the
discs and beside the long rails empty; the kit's packer (rbx_uvpack) places them by their real shape and
drops the small ones into those holes. Its summary must say so: "packed by shape: main" with the share of the map
the faces covered before and after (facts.uv_pack.main: blender, kit, kept "kit").
Used by `lune run kit selftest`. Never "fix" this file.
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_pack_tight", size=(6.0, 0.5, 6.0), ground=True)
a.material("steel", color=(0.55, 0.56, 0.6), metal=1.0, rough=0.4)
a.material("paint", color=(0.2, 0.3, 0.45), rough=0.6)
a.box("Plate", (6.0, 0.2, 6.0), (0, 0.1, 0), "paint", bevel=0.02)
a.cylinder("RingA", 1.6, 0.3, (-1.2, 0.2 + 0.15 - 0.01, -1.2), "steel", segments=48)
a.cylinder("RingB", 1.1, 0.3, (1.6, 0.2 + 0.15 - 0.01, 1.4), "steel", segments=48)
for i in range(4):
    a.box(f"Rail{i + 1}", (0.25, 0.25, 5.6), (-2.7 + i * 0.3 + (3.9 if i > 1 else 0), 0.2 + 0.125 - 0.01, 0), "steel",
          bevel=0.02)
n = 0
for ix in range(8):
    for iz in range(5):
        n += 1
        w, h, d = 0.12 + 0.05 * ((ix * 3 + iz) % 5), 0.1 + 0.04 * ((ix + iz * 2) % 4), 0.12 + 0.06 * ((ix + iz) % 4)
        a.box(f"Block{n}", (w, h, d), (-1.9 + ix * 0.5, 0.2 + h / 2 - 0.01, -2.4 + iz * 0.42 + (2.6 if ix > 3 else 0)),
              "paint", bevel=0.01)
a.build()
