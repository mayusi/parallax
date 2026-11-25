"""build_seams_line.py — NEGATIVE fixture for THE SEAM CHECK (card 7cka: "no gate case builds a seamed model for real"):
build_noise3.py's sculpted ball under soot laid by a noise drawn ACROSS THE MAP (noise_3d=False): the soot ends in a
line at every UV seam. Must be flagged: seams (its many short seam edges judged along their seam lines).
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("off")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_noise3.py"), run_name="__main__")
