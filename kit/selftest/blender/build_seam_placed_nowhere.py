"""build_seam_placed_nowhere.py — NEGATIVE twin of build_seam_placed.py: its rule names a place no edge of the part is at. The build must STOP and say the rule cut no edge (an error in the script, not a verdict).
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("nowhere")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_seam_placed.py"), run_name="__main__")
