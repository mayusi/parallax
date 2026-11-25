"""build_mask_unplaced.py — NEGATIVE twin of build_mask.py: the paint's rust layer names where="mask:stain" and the
script never places a mask of that name. The build must STOP and say which mask is missing and which the model has
(an error in the script, not a verdict). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("unplaced")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_mask.py"), run_name="__main__")
