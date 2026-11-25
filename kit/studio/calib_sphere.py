"""calib_sphere.py - the CALIBRATION object for the Roblox-look rig (kit/tools/studio_calibrate.py): a smooth matte
sphere of one known grey, so its lit side and its shaded side read the sun's share and the ambient's share of the
light apart, in Studio and in its Blender twin alike.

blender -b --factory-startup --python-exit-code 2 -P kit/studio/calib_sphere.py -- --no-preview
    (KIT_BUILD=build/_calib: never among the game's models)"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

GREY = 0.5   # the sphere's colour, linear (sRGB 188): mid-grey that neither clips in the sun nor sinks in the shade

a = rbx.Asset("_kit_calib_sphere", tex=256, size=(2.0, 2.0, 2.0), ground=False)
a.material("matte", (GREY, GREY, GREY), rough=1.0, metal=0.0)
a.sphere("Ball", 1.0, (0, 0, 0), "matte", segments=64, rings=32)
a.build()
