"""build_nosheet.py — a BAD fixture of the model sheet lock (kit/lib/lanelocks.luau): a hero piece with a build script
and no model sheet the owner approved. Never built: the lock reads the files beside it and refuses."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("nosheet", tex=64, ground=False)
a.material("body", (0.18, 0.19, 0.22), metal=0.4, rough=0.5)
a.box("Body", (0.4, 0.5, 1.6), (0, 0.75, 0.2), "body", bevel=0.03)
a.build()
