"""build_tile_torus.py — fixture for A TILE WHOSE NOISE IS ON A FLAT TORUS (card s4wc; rbx_wear.wrap_xz, perlin4):
the tile fixture's worn paint with noise_3d on - every noise field (the kit's own and the wear / variation noise
nodes, 4D) drawn on a torus each way the tile's width long, so the tile repeats along x AND z AS BAKED: no cross-fade
smearing its edges (facts.trim_sheet.faded false, trim_fade not named, tile_seam passing).
Used by kit/test/python/test_tile_torus.py. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_tile_torus", tex=256, size=(8.0, 0.1, 8.0), noise_3d=True, spec_occlusion=0.0)
a.material("paint", color=(0.35, 0.42, 0.3), rough=0.7, wear=0.4)
a.tile("paint", studs=8)
a.build()
