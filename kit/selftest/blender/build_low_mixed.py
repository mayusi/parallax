"""build_low_mixed.py — fixture for THE HIGH-AND-LOW ROUTE WITH CAD AND NON-CAD PARTS IN ONE GROUP (LIMITATIONS_FIXES_V4
Phase 1, 3D-X: "mixed low=True CAD+primitive hits 97.11% misses"): a filleted a.cad plate with an a.box block and an
a.cylinder post standing on it, one group. The box and the post have no high of their own: their own surface is their
high (the exploded bake bakes them from it). The group's bake source must carry them too, so the checks that read it
(bake_misses, the cage, the silhouette) see the same surface the bake did: facts.low.groups.g.bake_misses.missed under
rbx_bakecage.MISSES with no part named. Used by kit/test/python/test_low_mixed.py. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

MM = 280.0
a = rbx.Asset("_selftest_low_mixed", tex=512, size=(1.2, 0.56, 1.2), ground=True, low=True)
a.material("iron", color=(0.3, 0.3, 0.32), metal=1.0, rough=0.6)
a.cad("Plate", f"part = Pos(0, {0.06 * MM / 2}, 0) * fillet(Box({1.2 * MM}, {0.06 * MM}, {1.2 * MM}).edges(), 4)\n",
      "iron", group="g")
a.box("Block", (0.3, 0.3, 0.3), (-0.3, 0.06 + 0.15, -0.3), "iron", bevel=0.01, group="g")
a.cylinder("Post", 0.08, 0.5, (0.3, 0.06 + 0.25, 0.3), "iron", axis="Y", segments=24, bevel=0.0, group="g")
a.build()
