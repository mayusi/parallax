"""build_rig_fold.py - fixture for a CHAIN'S POSE CHECKED WHOLE (the 3D methods audit's 2.10, stage P): the arm of
build_rig.py with a named pose that folds the lower arm back through the upper arm - each joint's own travel is
clear (each is checked alone), only the two posed together meet. Must FAIL `reach_clear` by the chain's name and
the pose's. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("fold")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_rig.py"), run_name="__main__")
