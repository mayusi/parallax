"""build_calibration.py — ONE-TIME orientation + scale check for the whole pipeline.

Import build/models/calibration.fbx into Studio once. If the kit is right you will see:
  - a 4x4x4 stud frame (Studio's size readout says 4, 4, 4)
  - the red arrow points to the model's FRONT (-Z, the way a Part's front face / LookVector points)
  - the green fin points UP (+Y), the blue ball sits on the RIGHT (+X)
If any of that is wrong, fix BL_FROM_RBX in kit/blender/rbx.py — never patch individual asset scripts.
Run: lune run kit calibrate
"""

import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("calibration", tex=256, ground=False, allow_floating=("FrontShaft", "FrontTip", "RightBall", "UpFin"))
a.material("frame", color=(0.8, 0.8, 0.8), rough=0.7)
a.material("front", color=(0.9, 0.1, 0.1))
a.material("up", color=(0.1, 0.8, 0.2))
a.material("right", color=(0.15, 0.3, 0.95))
n = 0
for x in (-1.9, 1.9):
    for z in (-1.9, 1.9):
        n += 1
        a.box(f"Post{n}", (0.2, 4, 0.2), (x, 2, z), "frame")
for y in (0.1, 3.9):
    for z in (-1.9, 1.9):
        n += 1
        a.box(f"RailX{n}", (3.6, 0.2, 0.2), (0, y, z), "frame")
    for x in (-1.9, 1.9):
        n += 1
        a.box(f"RailZ{n}", (0.2, 0.2, 3.6), (x, y, 0), "frame")
# arrow: shaft along Z, cone tip at the -Z end (radius_top is the +axis end, so flip it with ry=180)
a.cylinder("FrontShaft", 0.25, 2.0, (0, 2, -1.0), "front", axis="Z")
a.cylinder("FrontTip", 0.5, 1.0, (0, 2, -2.5), "front", axis="Z", rot=(0, 180, 0), radius_top=0.0)
a.box("UpFin", (0.15, 1.2, 0.8), (0, 3.2, 0), "up")
a.sphere("RightBall", 0.4, (1.4, 2, 0), "right")
a.build()
