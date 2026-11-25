"""build_r6wear_soup.py — the soup case of build_r6wear.py (R6 clothes to the game's standard). Used by `lune run kit
selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("soup")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_r6wear.py"), run_name="__main__")
