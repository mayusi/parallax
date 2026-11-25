"""build_seams_meet.py — POSITIVE twin of build_seams_line.py: the same ball, its soot laid by the noise ON THE MODEL
(noise_3d=True): the soot runs on across every seam. Must NOT be flagged: seams.
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("on")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_noise3.py"), run_name="__main__")
