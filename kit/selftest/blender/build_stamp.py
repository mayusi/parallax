"""build_stamp.py — fixture: a.stamp bakes detail into the NORMAL map, no triangles (AAA-5). A flat steel plate 1.0 x
1.0 x 0.1 studs with a rivet row and a panel line stamped on its front face; `--control` builds the same plate with
no stamps (_selftest_stamp_ctl). kit/test/python/test_stamp_bake.py compares the two normal maps and reads the
facts; a stamp inside a.mirror must be refused (the marker in facts). Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

import json  # noqa: E402

control = "--control" in sys.argv
a = rbx.Asset("_selftest_stamp_ctl" if control else "_selftest_stamp", tex=256, size=(1.0, 1.0, 0.1))
a.real_scale(280.0)
a.material("steel", (0.4, 0.4, 0.42), metal=1.0, rough=0.4)
a.box("Plate", (1.0, 1.0, 0.1), (0, 0.5, 0), "steel")
if not control:
    a.stamp("rivets", at=(0.25, 0.7, -0.05), size=(0.4, 0.06), facing="-Z", count=5)
    a.stamp("panel_line", at=(-0.2, 0.35, -0.05), size=(0.4, 0.3), facing="-Z", width_mm=3.0)
    try:
        with a.mirror("X"):
            a.stamp("rivets", at=(0.25, 0.2, -0.05), size=(0.2, 0.05), facing="-Z")
        verdict = "accepted"
    except ValueError:
        verdict = "refused"
    os.makedirs(os.path.join(_root, "build", "models"), exist_ok=True)
    with open(os.path.join(_root, "build", "models", "_selftest_stamp.mirror.json"), "w", encoding="utf-8") as fh:
        json.dump({"stamp_in_mirror": verdict}, fh)
a.build()
