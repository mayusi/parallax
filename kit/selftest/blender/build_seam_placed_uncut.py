"""build_seam_placed_uncut.py — NEGATIVE twin of build_seam_placed.py: its caps are cut off (sharp=60) and nobody cuts the tube open: it cannot lie flat. The build must FAIL the check `seam_placed`.
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("uncut")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_seam_placed.py"), run_name="__main__")
