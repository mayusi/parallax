"""build_tile_ball.py — twin of build_tile.py with the word `ball` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("ball")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_tile.py"), run_name="__main__")
